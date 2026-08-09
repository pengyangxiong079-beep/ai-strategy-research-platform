import streamlit as st

DEFAULTS = {
    "selected_project_id": None,
    "selected_run_id": None,
    "selected_revision_id": None,
    "current_wizard_step": 1,
    "analysis_draft": {},
    "revision_preview": None,
    "debug_mode": False,
}


def initialize_workspace_state():
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value.copy() if isinstance(value, dict) else value)

