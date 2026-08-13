import streamlit as st

from ui.actions import continue_strategy, record_decision
from ui.components import empty_state, page_header
from ui.view_models import decisions_view_model
from ui.workspace import require_run


run = require_run()
vm = decisions_view_model(run)
page_header(
    "人工决策",
    "逐项查看具体问题、判断依据和处理影响；完成后再进入 Strategy。",
    status=run.get("overall_status"),
)

st.subheader(f"待处理 · {len(vm['pending'])}")
if not vm["pending"]:
    empty_state(
        "当前没有待处理事项",
        "所有人工决策已完成，或当前流程尚未到达 Human Review。",
        icon=":material/check_circle:",
    )
else:
    for index, decision in enumerate(vm["pending"]):
        with st.container(border=True):
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.markdown(f"**{decision['title']}**")
                st.badge(decision.get("severity", "UNKNOWN"))
            st.caption(
                f"事项 {decision.get('review_id') or decision['decision_id']} · "
                f"类别 {decision.get('category', 'general')} · 来源 {decision['source_stage']}"
            )
            st.markdown("**具体问题**")
            st.write(decision["issue"])
            st.markdown("**判断依据**")
            st.write(decision["evidence"])
            st.markdown("**建议处理**")
            st.write(decision["required_action"])
            if decision.get("claim_ids") or decision.get("source_ids"):
                with st.expander("关联证据 ID", icon=":material/link:"):
                    if decision.get("claim_ids"):
                        st.write("Claim：", decision["claim_ids"])
                    if decision.get("source_ids"):
                        st.write("Source：", decision["source_ids"])
            with st.form(f"decision_{decision['decision_id']}"):
                choice = st.selectbox("处理方式", decision["options"])
                note = st.text_area(
                    "补充说明",
                    placeholder="可说明接受的边界、需要排除的结论或待补充的数据。",
                )
                submitted = st.form_submit_button(
                    "提交决定",
                    disabled=vm["read_only"],
                    type="primary" if index == 0 else "secondary",
                )
            if submitted:
                record_decision(run, decision, choice, note)
                st.toast("决定已保存，并将作为 Strategy 的结构化输入。", icon=":material/check_circle:")
                st.rerun()

if vm["resolved"]:
    with st.expander(f"已处理 · {len(vm['resolved'])}", icon=":material/task_alt:"):
        for item in vm["resolved"]:
            st.markdown(f"**{item.get('review_id') or item.get('decision_id')} · {item.get('choice')}**")
            snapshot = item.get("decision_snapshot") or {}
            if snapshot.get("issue"):
                st.write(snapshot["issue"])
            if item.get("note"):
                st.caption(item["note"])

if vm.get("deferred") and not vm["read_only"]:
    st.info(
        "你已选择暂缓并补充证据。请在“数据与质量”页确认目标后启动定向补搜；"
        "系统会创建新 Revision，不覆盖当前结果。",
        icon=":material/search:",
    )
    if st.button("前往数据与质量", icon=":material/arrow_forward:", key="go_to_gap_search"):
        st.switch_page("app_pages/data_quality.py")

if (
    not vm["pending"]
    and not vm.get("deferred")
    and run.get("overall_status") in {"AWAITING_HUMAN_REVIEW", "REVISION_IN_PROGRESS"}
    and not vm["read_only"]
):
    strategy_running = run.get("stages", {}).get("strategy", {}).get("status") == "RUNNING"
    if strategy_running:
        st.info("Strategy Agent 正在运行。请等待当前调用完成，不要重复提交。", icon=":material/progress_activity:")
    if st.button(
        "继续生成 Strategy", type="primary", icon=":material/play_arrow:",
        disabled=strategy_running,
    ):
        status = st.status("正在生成 Strategy、报告与可视化看板", expanded=True)
        try:
            def progress(stage, message):
                status.write(f"**{stage}** · {message}")

            output = continue_strategy(run, progress)
            if output.get("plan_status") == "FAILED":
                raise RuntimeError(f"Revision 在 {output.get('failed_stage')} 阶段被阻断")
            status.update(label="Strategy 与质量检查完成", state="complete")
            st.switch_page("app_pages/results.py")
        except Exception as error:
            status.update(label="Strategy 执行失败，已保留产物", state="error")
            st.error(str(error))
