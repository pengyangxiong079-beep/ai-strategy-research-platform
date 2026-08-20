from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import main
from dashboard.exporter import DashboardExportError, generate_dashboard_html
from pipeline_v2.agent_provider import create_ready_agent_registry
from pipeline_v2.ids import stable_id
from pipeline_v2.service import PipelineV2Service
from pipeline_v2.orchestrator import PipelineV2Orchestrator
from pipeline_v2.revision import RevisionExecutor, RevisionPlan, plan_revision
from pipeline_v2.model import load_run_state
from ui.repository import invalidate_file_cache, read_json


def save_draft(draft):
    root = Path(".workspace/drafts")
    root.mkdir(parents=True, exist_ok=True)
    draft_id = stable_id("decision", draft.get("topic"), draft.get("analysis_date"))
    path = root / f"{draft_id}.json"
    path.write_text(json.dumps({"draft_id": draft_id, **draft}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def prepare_and_run(scope_inputs, progress_callback=None, prepared_callback=None):
    # Authentication is checked before prepare_analysis_run creates immutable
    # audit artifacts. A missing login must never create a doomed RUNNING run.
    registry = create_ready_agent_registry()
    prepared = main.prepare_analysis_run(scope_inputs)
    if prepared_callback:
        prepared_callback(prepared)
    state = load_run_state(prepared["output_folder"])
    if state and state.get("configuration", {}).get("strict_structured_output"):
        if progress_callback:
            progress_callback("Pipeline V2", "正在按严格JSON Envelope执行Data至Fact Check。")
        result = PipelineV2Orchestrator(registry).execute(
            prepared["output_folder"], stages=["scope", "data", "research", "review", "fact_check", "human"],
            stop_before_human=True,
        )
    else:
        result = main.run_research_phase(
            prepared["scope"]["topic"], output_folder=prepared["output_folder"],
            analysis_scope=prepared["scope"], progress_callback=progress_callback,
        )
    invalidate_file_cache()
    return prepared, result


def record_decision(run, decision, choice, note):
    if run.get("read_only"):
        raise PermissionError("Legacy运行只读")
    folder = Path(run["folder"])
    path = folder / "human/feedback.json"
    payload = read_json(path, {"schema_version": "2.0", "feedback": []})
    existing = next((
        row for row in reversed(payload.get("feedback", []))
        if row.get("decision_id") == decision["decision_id"]
        and row.get("choice") == choice and str(row.get("note") or "") == str(note or "")
        and row.get("status") == ("PENDING" if choice.startswith("暂缓") else "RESOLVED")
    ), None)
    if existing:
        return existing
    record = {
        "feedback_id": stable_id("feedback", decision["decision_id"], choice, note),
        "decision_id": decision["decision_id"], "display_id": None,
        "review_id": decision.get("review_id"),
        "source_stage": decision.get("source_stage"), "choice": choice,
        "note": note, "impact_scope": ["strategy", "report", "dashboard", "quality"],
        "status": "PENDING" if choice.startswith("暂缓") else "RESOLVED",
        "decision_snapshot": {
            "title": decision.get("title"),
            "issue": decision.get("issue") or decision.get("why"),
            "evidence": decision.get("evidence"),
            "required_action": decision.get("required_action") or decision.get("agent_suggestion"),
            "severity": decision.get("severity"),
            "category": decision.get("category"),
            "claim_ids": list(decision.get("claim_ids") or []),
            "source_ids": list(decision.get("source_ids") or []),
        },
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    payload.setdefault("feedback", []).append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PipelineV2Service(folder.parent).apply_change(folder, "human", f"Decision {decision['decision_id']}：{choice}")
    invalidate_file_cache()
    return record


def start_targeted_gap_search(run, targets, progress_callback=None):
    """Run a user-confirmed, gap-only data revision and stop at Human Review."""
    if run.get("read_only"):
        raise PermissionError("Legacy runs are read-only")
    # Authenticate before creating an immutable revision or changing state.
    registry = create_ready_agent_registry()
    executor = RevisionExecutor(PipelineV2Orchestrator(registry))
    base = Path(run.get("base_folder") or run["folder"])
    source = Path(run["folder"])
    settings = read_json(Path(".workspace/settings.json"), {})
    gap_limit = max(0, min(2, int(settings.get("gap_limit", 2) or 0)))
    plan, _ = executor.create_targeted_gap_search(
        base, source, list(targets or []), max_rounds=gap_limit,
    )
    if progress_callback:
        datasets = ", ".join(dict.fromkeys(row.get("dataset_id", "") for row in targets))
        progress_callback("Data", f"正在定向补搜：{datasets}")
        progress_callback("Pipeline V2", "新增证据将重新经过 Research、Review 与 Fact Check，然后停在人工决策。")
    result = executor.execute(base, plan.revision_id)
    invalidate_file_cache()
    return {**result, "revision_id": plan.revision_id}


def continue_strategy(run, progress_callback=None):
    state = load_run_state(run["folder"])
    if state and state.get("configuration", {}).get("strict_structured_output"):
        if state.get("stages", {}).get("fact_check", {}).get("status") not in {
            "COMPLETE", "COMPLETE_WITH_WARNINGS",
        }:
            raise RuntimeError(
                "Fact Check 尚未通过，禁止启动 Strategy。请切换到已恢复的 Revision，"
                "或先在研究流程页执行本地恢复。"
            )
        feedback = read_json(Path(run["folder"]) / "human/feedback.json", {"schema_version": "2.0", "feedback": []})
        registry = create_ready_agent_registry()
        if progress_callback:
            progress_callback("Pipeline V2", "正在执行Human Gate、Strategy、Renderer、Dashboard与Quality。")
        orchestrator = PipelineV2Orchestrator(registry)
        if run.get("revision_id") not in {None, "", "rev_000"} and run.get("base_folder"):
            output = RevisionExecutor(orchestrator).resume(
                run["base_folder"], run["revision_id"], human_feedback=feedback,
            )
        else:
            output = orchestrator.execute(
                # Dashboard consumes quality/summary.json. Keep the canonical
                # dependency order so a newly generated board never embeds a
                # stale or PENDING quality status.
                run["folder"], stages=["human", "strategy", "report", "quality", "dashboard"],
                human_feedback=feedback,
            )
        # Prebuild the self-contained dashboard while the workflow progress UI
        # is still visible. Results can then open/download it immediately.
        # Export is a derived view and must not change a completed audit status.
        try:
            dashboard_path = generate_dashboard_html(
                run.get("base_folder") or run["folder"], run.get("revision_id"),
            )
            output["dashboard_html"] = str(dashboard_path)
        except (DashboardExportError, OSError, TypeError, ValueError) as error:
            output["dashboard_html_error"] = str(error)
        invalidate_file_cache()
        return output
    result = main.load_run_history(run["run_id"])
    feedback = read_json(Path(run["folder"]) / "human/feedback.json", {"feedback": []})
    feedback_text = "\n".join(f"- {x.get('choice')}：{x.get('note','')}" for x in feedback.get("feedback", []))
    output = main.run_strategy_phase(result, human_feedback=feedback_text, progress_callback=progress_callback)
    invalidate_file_cache()
    return output


def rebuild_stale_local(run):
    if run.get("read_only"):
        raise PermissionError("Legacy运行只读")
    result = main.rerun_local_revision(run["folder"], "Pipeline V2：重建STALE本地产物")
    invalidate_file_cache()
    return result


def retry_failed_run(run, progress_callback=None):
    if run.get("read_only"):
        raise PermissionError("Legacy运行只读")
    # Authenticate before writing a revision plan or revision directory.
    executor = _revision_executor(run)
    plan = plan_revision(
        run["folder"], "TECHNICAL_RETRY",
        requested_changes=[f"Recover technical failure at {run.get('current_stage')}"],
    )
    executor.create(run["folder"], plan)
    if progress_callback:
        progress_callback("Pipeline V2", f"正在新建 {plan.revision_id} 并从 {run.get('current_stage')} 阶段恢复")
    result = executor.execute(run["folder"], plan.revision_id)
    invalidate_file_cache()
    return {**result, "revision_id": plan.revision_id}


def recover_blocked_fact_check(run):
    """Revalidate a saved Fact Check candidate; never invokes a live Agent."""
    if run.get("read_only"):
        raise PermissionError("Legacy runs are read-only")
    from pipeline_v2.fake_agent_registry import FakeAgentRegistry

    executor = RevisionExecutor(PipelineV2Orchestrator(FakeAgentRegistry()))
    result = executor.recover_blocked_fact_check(
        run.get("base_folder") or run["folder"], feedback_source=run["folder"],
    )
    invalidate_file_cache()
    return result


def recover_blocked_strategy(run):
    """Normalize and validate a saved Strategy candidate; never invokes a live Agent."""
    if run.get("read_only"):
        raise PermissionError("Legacy runs are read-only")
    from pipeline_v2.fake_agent_registry import FakeAgentRegistry

    registry = FakeAgentRegistry()
    executor = RevisionExecutor(PipelineV2Orchestrator(registry))
    result = executor.recover_blocked_strategy(run.get("base_folder") or run["folder"])
    if registry.call_count():
        raise RuntimeError("Local Strategy recovery unexpectedly attempted an Agent call")
    invalidate_file_cache()
    return result


def migrate_decisions_to_revision(base_run, revision_id):
    """Copy prior human decisions into a recovered revision without Agent calls."""
    base = Path(base_run["folder"])
    revision = base / "revisions" / revision_id
    if not revision.is_dir():
        raise FileNotFoundError(f"Revision not found: {revision_id}")
    source = read_json(base / "human/feedback.json", {"schema_version": "2.0", "feedback": []})
    target = read_json(revision / "human/feedback.json", {"schema_version": "2.0", "feedback": []})
    review = read_json(revision / "review/review_issues.json", {"issues": []})
    decisions = {
        stable_id("decision", base_run.get("run_id"), row.get("review_id")): row
        for row in review.get("issues", [])
    }
    known = {row.get("feedback_id") for row in target.get("feedback", [])}
    migrated = []
    for original in source.get("feedback", []):
        if original.get("feedback_id") in known:
            continue
        row = dict(original)
        item = decisions.get(row.get("decision_id"), {})
        row.setdefault("review_id", item.get("review_id"))
        row.setdefault("decision_snapshot", {
            "title": item.get("title") or item.get("issue") or item.get("reason"),
            "issue": item.get("issue") or item.get("reason"),
            "evidence": item.get("evidence"),
            "required_action": item.get("required_action") or item.get("suggested_action"),
            "severity": item.get("severity"),
            "category": item.get("category"),
            "claim_ids": list(item.get("claim_ids") or ([item["claim_id"]] if item.get("claim_id") else [])),
            "source_ids": list(item.get("source_ids") or []),
        })
        migrated.append(row)
    target.setdefault("feedback", []).extend(migrated)
    path = revision / "human/feedback.json"
    path.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    invalidate_file_cache()
    return {"revision_id": revision_id, "migrated": len(migrated)}


def repair_revision_report(run):
    if not run.get("base_folder") or run.get("revision_id") in {None, "", "rev_000"}:
        raise ValueError("请选择被 Report 阻断的 Revision")
    from pipeline_v2.fake_agent_registry import FakeAgentRegistry

    registry = FakeAgentRegistry()
    result = RevisionExecutor(PipelineV2Orchestrator(registry)).repair_report_and_resume_locally(
        run["base_folder"], run["revision_id"],
    )
    if registry.call_count():
        raise RuntimeError("Local report repair unexpectedly attempted an Agent call")
    invalidate_file_cache()
    return result


def _revision_executor(run):
    registry = create_ready_agent_registry()
    return RevisionExecutor(PipelineV2Orchestrator(registry))


def generate_revision_preview(run, revision_type, *, requested_changes=(), affected_object_ids=(), scope_changed=False, scope_diff=None, data_as_of_date=""):
    if run.get("read_only"):
        raise PermissionError("Legacy运行只读")
    plan = plan_revision(
        run["folder"], revision_type, requested_changes=requested_changes,
        affected_object_ids=affected_object_ids, scope_changed=scope_changed,
        scope_diff=scope_diff, data_as_of_date=data_as_of_date,
    )
    invalidate_file_cache()
    return plan.to_dict()


def confirm_revision(run, plan_payload):
    if run.get("read_only"):
        raise PermissionError("Legacy运行只读")
    plan = RevisionPlan(**plan_payload)
    path = _revision_executor(run).create(run["folder"], plan)
    invalidate_file_cache()
    return path


def execute_revision(run, revision_id, *, human_feedback=None):
    result = _revision_executor(run).execute(run["folder"], revision_id, human_feedback=human_feedback)
    invalidate_file_cache()
    return result


def pause_revision(run, revision_id):
    result = _revision_executor(run).pause(run["folder"], revision_id)
    invalidate_file_cache(); return result


def resume_revision(run, revision_id, *, human_feedback=None):
    result = _revision_executor(run).resume(run["folder"], revision_id, human_feedback=human_feedback)
    invalidate_file_cache(); return result


def retry_revision_stage(run, revision_id, *, human_feedback=None):
    result = _revision_executor(run).retry_failed_stage(run["folder"], revision_id, human_feedback=human_feedback)
    invalidate_file_cache(); return result


def cancel_revision(run, revision_id):
    result = _revision_executor(run).cancel(run["folder"], revision_id)
    invalidate_file_cache(); return result
