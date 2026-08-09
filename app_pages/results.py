import json
from pathlib import Path
import streamlit as st

from dashboard.open_component import render_dashboard_html_action
from ui.components import empty_state, page_header
from ui.view_models import results_view_model
from ui.workspace import require_run

run = require_run()
vm = results_view_model(run)
page_header("研究成果", "查看最终交付物、打开专业看板并导出文件。", status=vm["status"])

if not vm["available"]:
    empty_state("最终报告尚未生成", "完成Human Review和Strategy后，最终报告会显示在这里。", icon=":material/pending_actions:")
    st.stop()

with st.container(horizontal=True):
    st.metric("报告状态", vm["status"], border=True)
    st.metric("Revision", vm["revision"], border=True)
    st.metric("数据缺口", len(vm["data_gaps"]), border=True)
    st.metric("战略建议", len(vm["report_data"].get("recommendations", [])), border=True)

st.subheader("Executive view")
if vm["executive_summary"]:
    st.write(vm["executive_summary"])
else:
    st.caption("结构化Executive Summary尚不可用，请查看最终报告。")

summary_cols = st.columns(3)
with summary_cols[0]:
    with st.container(border=True, height="stretch"):
        st.markdown("**关键机会**")
        for item in vm["opportunities"]:
            st.write(f"- {item.get('title') or item.get('label') or item}")
with summary_cols[1]:
    with st.container(border=True, height="stretch"):
        st.markdown("**关键风险**")
        for item in vm["risks"]:
            st.write(f"- {item.get('title') or item.get('label') or item}")
with summary_cols[2]:
    with st.container(border=True, height="stretch"):
        st.markdown("**战略优先级**")
        for item in vm["recommendations"]:
            st.write(f"- {item.get('title') or item.get('label') or item}")

st.subheader("Final report")
with st.container(border=True):
    st.markdown(vm["final_markdown"])

st.subheader("Professional dashboard")
st.caption("看板在新标签页打开；Streamlit继续作为工作流控制台。生成HTML不调用Agent。")
render_dashboard_html_action(run["folder"], st.session_state.get("selected_revision_id"), title=run.get("topic"))

st.subheader("导出")
with st.container(horizontal=True):
    st.download_button("下载Markdown", vm["final_markdown"], file_name=Path(vm["final_path"]).name, mime="text/markdown", icon=":material/download:")
    st.download_button("下载结构化JSON", json.dumps(vm["report_data"], ensure_ascii=False, indent=2), file_name="04_report_data.json", mime="application/json", icon=":material/download:")
    dashboard_file = Path(run["folder"]) / "dashboard/dashboard.html"
    if dashboard_file.is_file():
        st.download_button("下载HTML", dashboard_file.read_bytes(), file_name="dashboard.html", mime="text/html", icon=":material/download:")

support = st.expander("Supporting artifacts", icon=":material/folder_open:", on_change="rerun")
if support.open:
    with support:
        artifact = st.selectbox("研究支持材料", [x["label"] for x in vm["supporting"]]) if vm["supporting"] else None
        selected = next((x for x in vm["supporting"] if x["label"] == artifact), None)
        if selected:
            st.markdown(selected["content"])

