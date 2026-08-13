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

brief = vm["decision_brief"]
st.subheader("管理层决策简报")
with st.container(border=True):
    st.badge(brief["posture"], color="orange" if brief["critical_gap"] else "green", icon=":material/strategy:")
    primary = brief["primary"]
    st.markdown(f"### {primary.get('label') or primary.get('title') or '战略建议待形成'}")
    st.write(primary.get("rationale") or primary.get("description") or vm["executive_summary"] or "暂无结构化建议说明。")
    st.caption(vm["executive_summary"] or "结构化 Executive Summary 尚不可用。")

with st.container(horizontal=True):
    st.metric("决策置信度", brief["confidence"], border=True)
    st.metric("证据支持率", f"{brief['support_rate']:.0%}" if brief["support_rate"] is not None else "—", border=True)
    st.metric("未关闭缺口", len(vm["data_gaps"]), border=True)
    st.metric("情景数量", brief["scenario_count"], border=True)

gate_left, gate_right = st.columns(2)
with gate_left:
    with st.container(border=True, height="stretch"):
        st.markdown("**下一道决策门**")
        if brief["critical_gap"]:
            gap = brief["critical_gap"]
            st.write(gap.get("label"))
            st.caption(gap.get("required_action") or gap.get("reason"))
        else:
            st.write(primary.get("kpi") or "按路线图进入执行复盘。")
with gate_right:
    with st.container(border=True, height="stretch"):
        st.markdown("**建议边界**")
        st.write(primary.get("time_horizon") or primary.get("timeframe") or "时间范围待定义")
        st.caption(f"责任：{primary.get('responsible_function') or primary.get('owner') or '待指定'}")

summary_cols = st.columns(3)
with summary_cols[0]:
    with st.container(border=True, height="stretch"):
        st.markdown("**关键机会**")
        if vm["opportunities"]:
            for item in vm["opportunities"]:
                st.write(f"- {item.get('title') or item.get('label') or item}")
        else:
            st.caption("当前证据不足以形成结构化机会判断；未生成虚假条目。")
with summary_cols[1]:
    with st.container(border=True, height="stretch"):
        st.markdown("**关键风险**")
        if vm["risks"]:
            for item in vm["risks"]:
                st.write(f"- {item.get('title') or item.get('label') or item}")
        else:
            st.caption("当前证据不足以形成结构化风险判断；未生成虚假条目。")
with summary_cols[2]:
    with st.container(border=True, height="stretch"):
        st.markdown("**战略优先级**")
        for item in vm["recommendations"]:
            st.write(f"- {item.get('title') or item.get('label') or item}")

st.subheader("完整报告")
with st.container(border=True):
    st.markdown(vm["final_markdown"])

if vm["recommendations"]:
    st.subheader("战略优先级与问责")
    st.dataframe(
        [{
            "优先级": item.get("priority"), "行动": item.get("label") or item.get("title"),
            "期限": item.get("time_horizon") or item.get("timeframe"),
            "责任": item.get("responsible_function") or item.get("owner"),
            "KPI": item.get("kpi"), "证据": "、".join(item.get("source_fact_ids", [])),
        } for item in vm["recommendations"]],
        hide_index=True,
    )

st.subheader("专业可视化看板")
st.caption("看板在新标签页打开；Streamlit继续作为工作流控制台。生成HTML不调用Agent。")
render_dashboard_html_action(run["folder"], st.session_state.get("selected_revision_id"), title=run.get("topic"))

st.subheader("导出")
with st.container(horizontal=True):
    st.download_button("下载Markdown", vm["final_markdown"], file_name=Path(vm["final_path"]).name, mime="text/markdown", icon=":material/download:")
    st.download_button("下载结构化JSON", json.dumps(vm["report_data"], ensure_ascii=False, indent=2), file_name="04_report_data.json", mime="application/json", icon=":material/download:")
    dashboard_file = Path(run["folder"]) / "dashboard/dashboard.html"
    if dashboard_file.is_file():
        st.download_button("下载HTML", dashboard_file.read_bytes(), file_name="dashboard.html", mime="text/html", icon=":material/download:")

support = st.expander("支撑材料", icon=":material/folder_open:", on_change="rerun")
if support.open:
    with support:
        artifact = st.selectbox("研究支持材料", [x["label"] for x in vm["supporting"]]) if vm["supporting"] else None
        selected = next((x for x in vm["supporting"] if x["label"] == artifact), None)
        if selected:
            st.markdown(selected["content"])
