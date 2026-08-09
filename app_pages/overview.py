import streamlit as st

from ui.components import empty_state, page_header, workflow_stepper
from ui.view_models import overview_view_model
from ui.workspace import require_run

run = require_run()
vm = overview_view_model(run)
page_header("运行概览", "快速理解当前阶段、阻塞原因和唯一下一步。", status=vm["overall_status"])

with st.container(horizontal=True):
    for item in vm["summary_metrics"]:
        st.metric(item["label"], item["value"], border=True)

st.subheader("研究进度")
workflow_stepper(vm.get("stages", {}), vm.get("current_stage"))
st.progress(vm["progress"], text=f"已完成 {vm['progress']:.0%}")

with st.container(border=True):
    st.subheader("下一步")
    st.write(vm["primary_action"]["label"])
    target = {
        "new_analysis": "app_pages/new_analysis.py", "pipeline": "app_pages/pipeline.py",
        "decisions": "app_pages/decisions.py", "data_quality": "app_pages/data_quality.py",
        "results": "app_pages/results.py", "revisions": "app_pages/revisions.py", "projects": "app_pages/projects.py",
    }[vm["primary_action"]["page"]]
    if st.button(vm["primary_action"]["label"], type="primary", icon=":material/arrow_forward:"):
        st.switch_page(target)

left, right = st.columns(2)
with left:
    st.subheader("最近活动")
    if vm["recent_activity"]:
        for event in vm["recent_activity"]:
            st.caption(f"{event.get('at', '—')} · {event.get('stage', '—')} · {event.get('event', '—')}")
    else:
        empty_state("暂无活动", "运行事件将在阶段变化时记录。")
with right:
    st.subheader("关键问题")
    if vm["key_issues"]:
        for issue in vm["key_issues"]:
            st.warning(f"{issue['title']}：{issue['count']}", icon=":material/warning:")
    else:
        empty_state("没有关键阻塞", "当前没有需要在Overview展开的重大问题。", icon=":material/check_circle:")

if run.get("legacy"):
    st.info("这是历史V1运行：当前以只读Legacy视图打开，不会修改原文件。", icon=":material/history:")

