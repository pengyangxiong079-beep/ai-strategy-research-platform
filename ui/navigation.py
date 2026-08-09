import streamlit as st


def workspace_navigation():
    return st.navigation(
        {
            "研究工作台": [
                st.Page("app_pages/projects.py", title="项目", icon=":material/folder:"),
                st.Page("app_pages/new_analysis.py", title="新建分析", icon=":material/add_circle:"),
                st.Page("app_pages/overview.py", title="运行概览", icon=":material/home:"),
                st.Page("app_pages/pipeline.py", title="研究流程", icon=":material/account_tree:"),
                st.Page("app_pages/decisions.py", title="人工决策", icon=":material/approval:"),
                st.Page("app_pages/results.py", title="研究成果", icon=":material/description:"),
                st.Page("app_pages/data_quality.py", title="数据与质量", icon=":material/fact_check:"),
                st.Page("app_pages/revisions.py", title="修订与版本", icon=":material/history:"),
            ],
            "系统": [
                st.Page("app_pages/settings.py", title="设置", icon=":material/settings:"),
            ],
        },
        position="sidebar",
    )

