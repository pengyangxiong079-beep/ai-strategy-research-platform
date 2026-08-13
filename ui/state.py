import streamlit as st

DEFAULTS = {
    "selected_project_id": None,
    "selected_run_id": None,
    "selected_revision_id": None,
    "current_wizard_step": 1,
    "analysis_draft": {},
    "revision_preview": None,
    "debug_mode": False,
    "pending_run_selection_id": None,
    "pending_revision_selection_id": None,
    "auto_revision_selection_runs": [],
    "workspace_selection_schema_version": 0,
}

WORKSPACE_SELECTION_SCHEMA_VERSION = 1


def initialize_workspace_state():
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value.copy() if isinstance(value, dict) else value)


def request_run_selection(run_id, project_id=None):
    """Request a shared run change without mutating an already-rendered widget."""
    st.session_state.selected_run_id = run_id
    st.session_state.selected_project_id = project_id or run_id
    st.session_state.selected_revision_id = None
    st.session_state.pending_run_selection_id = run_id


def request_revision_selection(revision_id):
    st.session_state.selected_revision_id = None if revision_id == "current" else revision_id
    st.session_state.pending_revision_selection_id = revision_id


def reconcile_revision_selection(revisions):
    requested = st.session_state.pop("pending_revision_selection_id", None)
    widget = st.session_state.get("workspace_revision_selector")
    selected = st.session_state.get("selected_revision_id") or "current"
    target = requested if requested in revisions else widget if widget in revisions else selected if selected in revisions else "current"
    if widget != target:
        st.session_state.workspace_revision_selector = target
    return target


def resolve_run_selection(ids, *, requested=None, widget=None, selected=None, migrate=False):
    """Resolve the sidebar run deterministically before its widget is rendered."""
    if not ids:
        return None
    if requested in ids:
        return requested
    if migrate:
        return ids[0]
    if widget in ids:
        return widget
    if selected in ids:
        return selected
    return ids[0]


def preferred_revision_for_run(run, revisions):
    """Prefer an available repaired revision over a known-bad base snapshot."""
    if not run or run.get("revision_id") not in {None, "", "rev_000"}:
        return "current"
    if (
        run.get("overall_status") == "BLOCKED_QUALITY"
        and run.get("stages", {}).get("fact_check", {}).get("status") == "BLOCKED"
    ):
        candidates = sorted(
            (value for value in revisions if value != "current"), reverse=True
        )
        if candidates:
            return candidates[0]
    return "current"


def format_run_option(run):
    """Make same-topic runs distinguishable by status and creation time."""
    run_id = str(run.get("run_id") or "")
    stamp = run_id[:15].replace("_", " ") if len(run_id) >= 15 else run_id
    topic = str(run.get("topic") or run_id)
    status = str(run.get("overall_status") or "UNKNOWN")
    return f"{topic} · {status} · {stamp}"


def reconcile_run_selection(ids):
    """Synchronize shared selection and persistent sidebar widget state."""
    requested = st.session_state.pop("pending_run_selection_id", None)
    migrate = (
        int(st.session_state.get("workspace_selection_schema_version", 0))
        < WORKSPACE_SELECTION_SCHEMA_VERSION
    )
    target = resolve_run_selection(
        ids,
        requested=requested,
        widget=st.session_state.get("workspace_run_selector"),
        selected=st.session_state.get("selected_run_id"),
        migrate=migrate,
    )
    previous_widget = st.session_state.get("workspace_run_selector")
    previous_selected = st.session_state.get("selected_run_id")
    if target is not None and previous_widget != target:
        # This runs before either sidebar widget is instantiated.
        st.session_state["workspace_run_selector"] = target
    if target is not None and target != previous_selected:
        st.session_state["workspace_revision_selector"] = "current"
        st.session_state.selected_revision_id = None
    st.session_state.selected_run_id = target
    st.session_state.selected_project_id = target
    st.session_state.workspace_selection_schema_version = WORKSPACE_SELECTION_SCHEMA_VERSION
    return target
