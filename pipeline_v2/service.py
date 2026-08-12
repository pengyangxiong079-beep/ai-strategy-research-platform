"""Pipeline V2 state transitions, canonical artifact projection and UI queries."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

from .dependencies import mark_stale, revision_impact
from .ids import stable_id
from .legacy import is_v2_run, legacy_view
from .model import STAGE_ORDER, create_run_state, load_run_state, now_iso, save_run_state
from .quality import aggregate_quality

CANONICAL_DIRS = ("data", "research", "review", "fact_check", "human", "strategy", "quality", "dashboard", "rendered")
ARTIFACT_PROJECTION = {
    "01_research_brief.md": "rendered/01_research_brief.md",
    "02_review_notes.md": "rendered/02_review_notes.md",
    "03_fact_check.md": "rendered/03_fact_check.md",
    "03_human_feedback.md": "rendered/03_human_feedback.md",
    "04_final_report.md": "rendered/04_final_report.md",
    "05_quality_check.md": "rendered/05_quality_check.md",
    "06_dashboard_data.json": "dashboard/dashboard_data.json",
    "05_quality_check.json": "quality/summary.json",
}


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_urls(text):
    return re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", str(text or ""))


class PipelineV2Service:
    def __init__(self, outputs_root="outputs"):
        self.outputs_root = Path(outputs_root)

    def initialize(self, folder, run_id, scope):
        folder = Path(folder)
        for name in CANONICAL_DIRS:
            (folder / name).mkdir(parents=True, exist_ok=True)
        state = create_run_state(run_id, scope)
        save_run_state(folder, state)
        for path, payload in {
            "data/requirements.json": {"schema_version": "1.0", "datasets": []},
            "data/source_registry.json": {"schema_version": "1.0", "sources": []},
            "data/sources.json": {"schema_version": "1.0", "sources": []},
            "data/observations.json": {"schema_version": "1.0", "observations": []},
            "data/sufficiency.json": {"schema_version": "1.0", "overall_status": "PENDING", "datasets": []},
            "data/data_coverage.json": {"schema_version": "1.0", "overall_status": "PENDING", "observation_count": 0, "datasets": []},
            "research/claims.json": {"schema_version": "2.0", "claims": []},
            "research/research_model.json": {"schema_version": "2.0", "sections": []},
            "review/review_issues.json": {"schema_version": "2.0", "issues": []},
            "review/review_notes.json": {"schema_version": "2.0", "issues": []},
            "02_review_notes.json": {"schema_version": "2.0", "issues": []},
            "fact_check/verified_claims.json": {"schema_version": "2.0", "claims": []},
            "human/feedback.json": {"schema_version": "2.0", "feedback": []},
            "strategy/recommendations.json": {"schema_version": "2.0", "recommendations": []},
            "strategy/report_model.json": {"schema_version": "2.0", "title": "", "paragraphs": []},
            "quality/issues.json": {"schema_version": "2.0", "issues": []},
        }.items():
            target = folder / path
            if not target.exists():
                _write_json(target, payload)
        return state

    def load(self, folder):
        return load_run_state(folder) if is_v2_run(folder) else legacy_view(folder)

    def list_runs(self):
        if not self.outputs_root.is_dir():
            return []
        rows = []
        for folder in self.outputs_root.iterdir():
            if not folder.is_dir() or not ((folder / "run_manifest.json").is_file() or (folder / "run_state.json").is_file()):
                continue
            view = self.load(folder)
            rows.append({**view, "folder": str(folder.resolve()), "project_id": view.get("run_id")})
        return sorted(rows, key=lambda x: x.get("updated_at", ""), reverse=True)

    def sync_manifest(self, folder, manifest):
        folder = Path(folder)
        state = load_run_state(folder)
        if not state:
            return None
        legacy_to_overall = {
            "AWAITING_SCOPE_CONFIRMATION": "AWAITING_SCOPE_CONFIRMATION", "AWAITING_APPROVAL": "AWAITING_HUMAN_REVIEW",
            "COMPLETED": "COMPLETED" if manifest.get("quality_check_status") == "PASS" else "COMPLETED_WITH_WARNINGS",
            "ERROR": "FAILED_TECHNICAL", "FAILED": "FAILED_TECHNICAL", "RUNNING": "RUNNING",
        }
        state["overall_status"] = legacy_to_overall.get(manifest.get("final_status"), state["overall_status"])
        state["current_stage"] = self._stage_from_manifest(manifest)
        state["revision_id"] = manifest.get("latest_revision") or state.get("revision_id", "rev_000")
        state["primary_action"] = self.primary_action(state["overall_status"])["id"]
        status_fields = {"research": "research_status", "review": "review_status", "fact_check": "fact_check_status", "human": "approval_status", "strategy": "strategy_status", "quality": "quality_check_status"}
        for stage, field in status_fields.items():
            raw = manifest.get(field)
            if raw in {"COMPLETED", "APPROVED", "PASS"}:
                state["stages"][stage]["status"] = "COMPLETE"
                state["stages"][stage]["validation_status"] = "PASS"
            elif raw in {"RUNNING"}:
                state["stages"][stage]["status"] = "RUNNING"
            elif raw in {"AWAITING_APPROVAL"}:
                state["stages"][stage]["status"] = "AWAITING_USER"
            elif raw in {"FAILED", "FAIL"}:
                state["stages"][stage]["status"] = "BLOCKED" if field == "quality_check_status" else "FAILED_TECHNICAL"
        issues = manifest.get("quality_issues", [])
        state["quality_summary"] = {
            "status": manifest.get("quality_check_status", "PENDING"),
            "blocking": sum(x.get("status") == "FAIL" for x in issues),
            "warnings": sum(x.get("status") == "WARN" for x in issues), "resolved": 0,
        }
        if state["stages"]["data"].get("status") == "BLOCKED":
            state["overall_status"] = "BLOCKED_DATA"
        elif any(stage.get("status") == "BLOCKED" for name, stage in state["stages"].items() if name != "data"):
            state["overall_status"] = "BLOCKED_QUALITY"
        state.setdefault("events", []).append({"at": now_iso(), "stage": state["current_stage"], "event": "MANIFEST_SYNC"})
        self.project_artifacts(folder, state)
        return save_run_state(folder, state)

    def sync_manifest_from_state(self, folder, state=None):
        """Project canonical V2 state into the discovery manifest.

        ``run_state.json`` remains authoritative. This projection keeps run
        discovery, audit and legacy UI consumers from observing stale status.
        """
        folder = Path(folder)
        state = state or load_run_state(folder)
        if not state:
            return None
        manifest_path = folder / "run_manifest.json"
        manifest = _read_json(manifest_path, {})
        scope = _read_json(folder / "00_analysis_scope.json", {})
        stage_status = {
            "COMPLETE": "COMPLETED", "COMPLETE_WITH_WARNINGS": "COMPLETED",
            "RUNNING": "RUNNING", "AWAITING_USER": "AWAITING_APPROVAL",
            "BLOCKED": "FAILED", "FAILED_TECHNICAL": "FAILED", "PENDING": "PENDING",
            "STALE": "STALE", "VALIDATING": "RUNNING",
        }
        stages = state.get("stages", {})
        data_status = stage_status.get(stages.get("data", {}).get("status"), "PENDING")
        quality_status = stages.get("quality", {}).get("validation_status", "PENDING")
        if quality_status == "BLOCKED":
            quality_status = "FAIL"
        elif quality_status == "PASS_WITH_WARNINGS":
            quality_status = "WARN"
        current = str(state.get("current_stage") or "scope")
        latest_event = (state.get("events") or [{}])[-1]
        error_message = latest_event.get("detail", "") if latest_event.get("event") == "FAILED_TECHNICAL" else ""
        manifest.update({
            "schema_version": manifest.get("schema_version") or "2.2",
            "pipeline_version": "2.0",
            "run_id": state.get("run_id"), "revision_id": state.get("revision_id", "rev_000"),
            "topic": state.get("topic") or scope.get("topic", ""),
            "analysis_type": scope.get("analysis_type", state.get("normalized_analysis_type", "")),
            "industry": scope.get("industry", state.get("industry", "")),
            "geography": scope.get("geography", ""), "analysis_date": scope.get("analysis_date", ""),
            "selected_template": scope.get("selected_template", "general"),
            "created_at": manifest.get("created_at") or state.get("created_at"),
            "updated_at": state.get("updated_at") or now_iso(),
            "current_stage": current, "final_status": state.get("overall_status"),
            "data_requirements_status": data_status, "data_acquisition_status": data_status,
            "data_sufficiency_status": data_status,
            "research_status": stage_status.get(stages.get("research", {}).get("status"), "PENDING"),
            "review_status": stage_status.get(stages.get("review", {}).get("status"), "PENDING"),
            "fact_check_status": stage_status.get(stages.get("fact_check", {}).get("status"), "PENDING"),
            "approval_status": stage_status.get(stages.get("human", {}).get("status"), "PENDING"),
            "strategy_status": stage_status.get(stages.get("strategy", {}).get("status"), "PENDING"),
            "quality_check_status": quality_status,
            "dashboard_status": (
                "READY" if stages.get("dashboard", {}).get("status") == "COMPLETE"
                else "READY_WITH_GAPS" if stages.get("dashboard", {}).get("status") == "COMPLETE_WITH_WARNINGS"
                else "UNAVAILABLE"
            ),
            "error_message": str(error_message)[:500],
            "quality_issues": _read_json(folder / "quality/issues.json", {"issues": []}).get("issues", []),
            "latest_revision": None if state.get("revision_id", "rev_000") == "rev_000" else state.get("revision_id"),
            "is_test_fixture": bool(scope.get("is_test_fixture")),
        })
        from main import atomic_write_json
        atomic_write_json(manifest_path, manifest)
        return manifest

    @staticmethod
    def _stage_from_manifest(manifest):
        text = str(manifest.get("current_stage", "")).lower()
        for token, stage in (("scope", "scope"), ("范围", "scope"), ("data", "data"), ("数据", "data"), ("research", "research"), ("review", "review"), ("fact", "fact_check"), ("人工", "human"), ("strategy", "strategy"), ("质量", "quality"), ("dashboard", "dashboard")):
            if token in text:
                return stage
        return "report" if manifest.get("final_status") == "COMPLETED" else "scope"

    def project_artifacts(self, folder, state=None):
        folder = Path(folder)
        state = state or load_run_state(folder)
        for source_name, target_name in ARTIFACT_PROJECTION.items():
            source, target = folder / source_name, folder / target_name
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                state.setdefault("artifacts", {})[target_name] = {"path": target_name, "status": "CURRENT", "updated_at": now_iso()}
        self._project_claims(folder)
        return state

    def _project_claims(self, folder):
        fact_data = _read_json(Path(folder) / "03_fact_check.json", {})
        if not fact_data.get("facts"):
            return
        registry = _read_json(Path(folder) / "data/source_registry.json", {"sources": []})
        by_url = {x.get("url"): x.get("source_id") for x in registry.get("sources", [])}
        claims = []
        result_map = {"VERIFIED": "SUPPORTED", "OUTDATED": "SUPPORTED"}
        temporal_map = {"OUTDATED": "SUPERSEDED"}
        for fact in fact_data.get("facts", []):
            text = fact.get("corrected_claim") or fact.get("original_claim") or ""
            source_ids = [by_url[url] for url in _source_urls(fact.get("source")) if url in by_url]
            observation_ids = [fact.get("observation_id")] if str(fact.get("observation_id", "")).startswith("OBS_") or str(fact.get("observation_id", "")).startswith("O") else []
            claims.append({
                "claim_id": stable_id("claim", text, fact.get("scope"), fact.get("as_of_date")),
                "display_id": fact.get("fact_id"), "parent_claim_id": None, "claim_type": "FACT", "text": text,
                "atomicity_status": "ATOMIC", "observation_ids": observation_ids, "source_ids": source_ids,
                "verification_status": result_map.get(fact.get("result"), fact.get("result", "NOT_CHECKED")),
                "temporal_status": temporal_map.get(fact.get("result"), "HISTORICAL" if str(fact.get("as_of_date", ""))[:4].isdigit() else "UNKNOWN"),
                "source_grade_max": f"GRADE_{fact['source_grade']}" if fact.get("source_grade") in "ABCDE" else None,
                "scope": {"geography": fact.get("geography"), "period": fact.get("as_of_date")}, "used_by": [], "status": "ACTIVE",
            })
        payload = {"schema_version": "2.0", "claims": claims}
        _write_json(Path(folder) / "research/claims.json", payload)
        _write_json(Path(folder) / "fact_check/verified_claims.json", payload)

    def apply_change(self, folder, changed_stage, reason):
        state = load_run_state(folder)
        mark_stale(state, changed_stage, reason)
        state["overall_status"] = "REVISION_IN_PROGRESS"
        return save_run_state(folder, state)

    def record_gate_result(self, folder, stage, result):
        folder = Path(folder)
        state = load_run_state(folder)
        if not state:
            return None
        stage_state = state["stages"][stage]
        stage_state["validation_status"] = result.status
        stage_state["error_codes"] = [x.get("rule_id") for x in result.errors]
        if result.errors:
            stage_state["status"] = "BLOCKED"
            state["overall_status"] = "BLOCKED_DATA" if stage == "data" else "BLOCKED_QUALITY"
        elif result.warnings and stage_state.get("status") == "COMPLETE":
            stage_state["status"] = "COMPLETE_WITH_WARNINGS"
        elif not result.warnings:
            stage_state["status"] = "COMPLETE"
        issues_path = folder / "quality/issues.json"
        payload = _read_json(issues_path, {"schema_version": "2.0", "issues": []})
        retained = [x for x in payload.get("issues", []) if x.get("stage") != stage]
        issues = [*retained, *result.errors, *result.warnings]
        _write_json(issues_path, {"schema_version": "2.0", "issues": issues})
        state["quality_summary"] = aggregate_quality(issues, data_blocked=stage == "data" and bool(result.errors))
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "GATE_VALIDATED", "detail": result.status})
        return save_run_state(folder, state)

    @staticmethod
    def primary_action(status):
        return {
            "AWAITING_SCOPE_CONFIRMATION": {"id": "CONFIRM_SCOPE", "label": "确认研究范围", "page": "new_analysis"},
            "RUNNING": {"id": "VIEW_PIPELINE", "label": "查看研究进度", "page": "pipeline"},
            "AWAITING_HUMAN_REVIEW": {"id": "REVIEW_DECISIONS", "label": "处理待审核事项", "page": "decisions"},
            "BLOCKED_DATA": {"id": "VIEW_DATA_GAPS", "label": "查看数据缺口", "page": "data_quality"},
            "BLOCKED_QUALITY": {"id": "VIEW_QUALITY", "label": "查看质量问题", "page": "data_quality"},
            "COMPLETED": {"id": "VIEW_RESULTS", "label": "查看研究成果", "page": "results"},
            "COMPLETED_WITH_WARNINGS": {"id": "VIEW_RESULTS", "label": "查看成果与限制", "page": "results"},
            "REVISION_IN_PROGRESS": {"id": "VIEW_REVISIONS", "label": "查看修订影响", "page": "revisions"},
        }.get(status, {"id": "VIEW_PROJECTS", "label": "返回项目", "page": "projects"})

    @staticmethod
    def revision_impact(revision_type):
        return revision_impact(revision_type)
