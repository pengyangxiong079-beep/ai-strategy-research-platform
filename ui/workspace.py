from pathlib import Path
import os
import streamlit as st

from pipeline_v2.service import PipelineV2Service


def service():
    return PipelineV2Service(Path(os.getenv("WORKSPACE_OUTPUTS_ROOT", "outputs")))


def runs():
    return service().list_runs()


def selected_run():
    selected = st.session_state.get("selected_run_id")
    items = runs()
    if not selected and items:
        selected = items[0]["run_id"]
        st.session_state.selected_run_id = selected
        st.session_state.selected_project_id = selected
    return next((x for x in items if x["run_id"] == selected), None)


def require_run():
    run = selected_run()
    if not run:
        st.info("尚未选择研究项目。请先在“项目”页面创建或打开一个分析。", icon=":material/folder_open:")
        st.stop()
    return run
