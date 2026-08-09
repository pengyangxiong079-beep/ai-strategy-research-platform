from pathlib import Path
from ui.repository import read_json
from pipeline_v2.service import PipelineV2Service


def revision_view_model(run, revision_type="LOCAL_REPAIR"):
    folder = Path(run["folder"])
    state = read_json(folder / "run_state.json", {})
    versions = [{"revision_id": "rev_000", "label": "Initial Snapshot", "revision_type": "INITIAL_SNAPSHOT", "status": "COMPLETE", "is_initial_snapshot": True}]
    root = folder / "revisions"
    if root.is_dir():
        for child in sorted(root.glob("rev_*")):
            manifest = read_json(child / "revision_manifest.json", {})
            execution = read_json(child / "execution_state.json", {})
            if child.name == "rev_000":
                continue
            versions.append({"revision_id": child.name, "label": child.name, "revision_type": manifest.get("revision_type"), "created_at": manifest.get("created_at"), "reason": manifest.get("revision_request") or manifest.get("revision_type"), "base_revision": manifest.get("base_revision"), "status": execution.get("plan_status") or manifest.get("status") or manifest.get("final_status"), "scope": manifest.get("revision_type"), "current_stage": execution.get("current_stage"), "completed_stages": execution.get("completed_stages", []), "pending_stages": execution.get("pending_stages", [])})
    revision_count = sum(not row.get("is_initial_snapshot") for row in versions)
    return {"versions": versions, "revision_count": revision_count, "show_comparison": revision_count >= 1, "impact": PipelineV2Service.revision_impact(revision_type), "read_only": bool(run.get("read_only")), "active_revision_id": state.get("active_revision_id", state.get("revision_id"))}
