import os
import streamlit as st

from ui.components import context_bar
from ui.design_tokens import apply_design_tokens
from ui.navigation import workspace_navigation
from ui.state import initialize_workspace_state
from ui.workspace import runs, selected_run

st.set_page_config(page_title="战略研究工作台", page_icon=":material/strategy:", layout="wide")
initialize_workspace_state()
apply_design_tokens()

workspace_v2 = os.getenv("WORKSPACE_V2", "0").strip().lower() not in {"0", "false", "off"}
if not workspace_v2:
    st.warning("WORKSPACE_V2 已关闭。请运行 `streamlit run app.py` 使用旧版控制台。")
    st.stop()

available = runs()
with st.sidebar:
    st.markdown("### 战略研究工作台")
    st.caption("Pipeline V2 · control plane")
    if available:
        ids = [x["run_id"] for x in available]
        current = st.session_state.get("selected_run_id")
        if current not in ids:
            current = ids[0]
        chosen = st.selectbox(
            "当前运行", ids, index=ids.index(current), key="workspace_run_selector",
            format_func=lambda value: next((x.get("topic") for x in available if x["run_id"] == value), value),
            persist_state="session",
        )
        st.session_state.selected_run_id = chosen
        st.session_state.selected_project_id = chosen
        revisions = ["current"]
        selected_folder = next(x["folder"] for x in available if x["run_id"] == chosen)
        from pathlib import Path
        revision_root = Path(selected_folder) / "revisions"
        if revision_root.is_dir():
            revisions += [x.name for x in sorted(revision_root.glob("rev_*"), reverse=True)]
        revision = st.selectbox("当前版本", revisions, key="workspace_revision_selector", persist_state="session")
        st.session_state.selected_revision_id = None if revision == "current" else revision
    else:
        st.caption("尚无项目")
    st.space("small")
    st.caption("本地结构化验证不消耗Codex额度。")

page = workspace_navigation()
context_bar(selected_run())
page.run()
