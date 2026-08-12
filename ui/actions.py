from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import main
from pipeline_v2.agent_provider import create_agent_registry
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


def prepare_and_run(scope_inputs, progress_callback=None):
    prepared = main.prepare_analysis_run(scope_inputs)
    state = load_run_state(prepared["output_folder"])
    if state and state.get("configuration", {}).get("strict_structured_output"):
        registry = create_agent_registry()
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
    record = {
        "feedback_id": stable_id("feedback", decision["decision_id"], choice, note),
        "decision_id": decision["decision_id"], "display_id": None,
        "source_stage": decision.get("source_stage"), "choice": choice,
        "note": note, "impact_scope": ["strategy", "report", "dashboard", "quality"],
        "status": "RESOLVED" if choice != "暂缓" else "PENDING",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    payload.setdefault("feedback", []).append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PipelineV2Service(folder.parent).apply_change(folder, "human", f"Decision {decision['decision_id']}：{choice}")
    invalidate_file_cache()
    return record


def continue_strategy(run, progress_callback=None):
    state = load_run_state(run["folder"])
    if state and state.get("configuration", {}).get("strict_structured_output"):
        feedback = read_json(Path(run["folder"]) / "human/feedback.json", {"schema_version": "2.0", "feedback": []})
        registry = create_agent_registry()
        if progress_callback:
            progress_callback("Pipeline V2", "正在执行Human Gate、Strategy、Renderer、Dashboard与Quality。")
        output = PipelineV2Orchestrator(registry).execute(
            run["folder"], stages=["human", "strategy", "report", "dashboard", "quality"],
            human_feedback=feedback,
        )
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


def _revision_executor(run):
    registry = create_agent_registry()
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
