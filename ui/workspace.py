from pathlib import Path
import os
import streamlit as st

from pipeline_v2.service import PipelineV2Service


def service():
    return PipelineV2Service(Path(os.getenv("WORKSPACE_OUTPUTS_ROOT", "outputs")))


def runs():
    return service().list_runs()


def run_view_for_revision(run, revision_id=None):
    if not run or not revision_id:
        return run
    revision_folder = Path(run["folder"]) / "revisions" / revision_id
    state = service().load(revision_folder) if revision_folder.is_dir() else None
    if not state:
        return run
    return {
        **state,
        "folder": str(revision_folder.resolve()),
        "project_id": run.get("project_id") or run.get("run_id"),
        "base_folder": run["folder"],
        "base_run_id": run.get("run_id"),
        "read_only": False,
        "legacy": False,
    }


def selected_run():
    selected = st.session_state.get("selected_run_id")
    items = runs()
    if not selected and items:
        selected = items[0]["run_id"]
        st.session_state.selected_run_id = selected
        st.session_state.selected_project_id = selected
    run = next((x for x in items if x["run_id"] == selected), None)
    return run_view_for_revision(run, st.session_state.get("selected_revision_id"))


def require_run():
    run = selected_run()
    if not run:
        st.info("尚未选择研究项目。请先在“项目”页面创建或打开一个分析。", icon=":material/folder_open:")
        st.stop()
    return run
