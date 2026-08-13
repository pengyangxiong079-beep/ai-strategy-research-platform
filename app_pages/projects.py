import pandas as pd
import streamlit as st

from ui.components import empty_state, page_header
from ui.view_models import project_view_model
from ui.workspace import runs
from ui.state import request_run_selection

page_header("项目", "选择研究项目，或创建一个新的战略分析。")
all_runs = runs()

with st.form("project_filters", border=False):
    with st.container(horizontal=True, vertical_alignment="bottom"):
        query = st.text_input("搜索项目", placeholder="输入topic或run ID", key="project_search")
        statuses = ["全部", *sorted({x.get("overall_status") for x in all_runs if x.get("overall_status")})]
        status = st.selectbox("状态", statuses)
        types = ["全部", *sorted({x.get("normalized_analysis_type") for x in all_runs if x.get("normalized_analysis_type")})]
        analysis_type = st.selectbox("分析类型", types)
        st.form_submit_button("筛选", icon=":material/filter_list:")

vm = project_view_model(all_runs, query, status, analysis_type)
if vm["empty"]:
    empty_state("尚无研究项目", "创建第一个分析，系统将从Scope和数据需求规划开始。", icon=":material/create_new_folder:")
    if st.button("新建分析", type="primary", icon=":material/add:"):
        st.switch_page("app_pages/new_analysis.py")
else:
    frame = pd.DataFrame(vm["projects"])
    display = frame[["项目", "分析类型", "行业", "地区", "当前阶段", "状态", "质量", "版本", "更新时间", "Legacy"]]
    event = st.dataframe(display, hide_index=True, on_select="rerun", selection_mode="single-row", key="projects_table")
    selected_rows = event.selection.rows
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("打开项目", type="primary", icon=":material/open_in_new:", disabled=not selected_rows):
            selected = vm["projects"][selected_rows[0]]
            request_run_selection(selected["run_id"], selected["project_id"])
            st.switch_page("app_pages/overview.py")
        if st.button("新建分析", icon=":material/add:"):
            st.switch_page("app_pages/new_analysis.py")
    st.caption(f"共 {vm['count']} 个项目；默认按最后更新时间排序。Legacy项目为只读。")
