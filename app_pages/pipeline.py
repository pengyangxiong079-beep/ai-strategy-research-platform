import streamlit as st

from ui.actions import (
    migrate_decisions_to_revision, rebuild_stale_local,
    recover_blocked_fact_check, recover_blocked_strategy,
    repair_revision_report, retry_failed_run,
)
from ui.components import page_header, status_badge
from ui.view_models import pipeline_view_model
from ui.workspace import require_run
from ui.state import request_revision_selection

run = require_run()
vm = pipeline_view_model(run)
page_header("研究流程", "查看阶段输入、输出、验证状态与STALE依赖。", status=run.get("overall_status"))

for stage in vm["stages"]:
    expander = st.expander(f"{stage['index']}. {stage['label']} · {stage.get('status', 'PENDING')}", expanded=stage["is_current"], icon=":material/radio_button_checked:" if stage["is_current"] else None)
    with expander:
        with st.container(horizontal=True):
            status_badge(stage.get("status"))
            st.caption(f"attempt：{stage.get('attempt', 0)}")
            st.caption(f"validation：{stage.get('validation_status', 'PENDING')}")
            st.caption(f"开始：{stage.get('started_at') or '—'}")
            st.caption(f"完成：{stage.get('completed_at') or '—'}")
        if stage.get("stale_reason"):
            st.warning(stage["stale_reason"], icon=":material/history_toggle_off:")
        st.markdown("**输入**")
        st.write(stage.get("input_artifacts") or "—")
        st.markdown("**输出**")
        st.write(stage.get("output_artifacts") or "—")
        if stage.get("error_codes"):
            st.code("\n".join(stage["error_codes"]), language="text")

if run.get("overall_status") == "FAILED_TECHNICAL" and not vm["read_only"]:
    latest = next(
        (event for event in reversed(run.get("events", [])) if event.get("event") == "FAILED_TECHNICAL"),
        {},
    )
    st.error(
        f"{run.get('current_stage', 'Agent')} 阶段发生技术故障：{latest.get('detail') or '未记录详细信息'}",
        icon=":material/error:",
    )
    st.caption("确认网络与 Codex 登录状态恢复后，可从失败阶段继续；已完成阶段和原始产物不会被覆盖。")
    confirm_retry = st.checkbox("我已确认网络与 Codex 登录状态可用", key="confirm_failed_run_retry")
    if st.button(
        "重试失败阶段", type="primary", icon=":material/refresh:",
        disabled=not confirm_retry, key="retry_failed_run",
    ):
        with st.status("正在恢复失败阶段", expanded=True) as status:
            try:
                result = retry_failed_run(
                    run, lambda stage, message: status.write(f"**{stage}** · {message}")
                )
                request_revision_selection(result["revision_id"])
                if result.get("plan_status") == "FAILED":
                    raise RuntimeError(f"Revision 仍在 {result.get('failed_stage')} 阶段失败")
                status.update(label=f"恢复结果：{result.get('plan_status')}", state="complete")
                st.rerun()
            except Exception as error:
                status.update(label="恢复失败，运行记录已保留", state="error")
                st.error(f"{type(error).__name__}: {error}")

if (
    run.get("overall_status") == "BLOCKED_QUALITY"
    and run.get("current_stage") == "fact_check"
    and not vm["read_only"]
):
    st.error("Fact Check 被旧版结构契约阻断。若已有结构化候选结果，可在新 Revision 中本地重新验证。")
    st.caption("此操作不会调用 Agent、不会消耗额度，也不会覆盖原运行；成功后将进入人工决策阶段。")
    if st.button("本地恢复 Fact Check", type="primary", icon=":material/fact_check:", key="recover_fact_contract"):
        with st.status("正在本地重新验证 Fact Check", expanded=True) as status:
            try:
                result = recover_blocked_fact_check(run)
                request_revision_selection(result["revision_id"])
                status.update(label="Fact Check 已恢复，等待人工决策", state="complete")
                st.rerun()
            except Exception as error:
                status.update(label="本地恢复失败，原运行未被修改", state="error")
                st.error(f"{type(error).__name__}: {error}")

if (
    run.get("revision_id") == "rev_000"
    and run.get("overall_status") == "BLOCKED_QUALITY"
    and run.get("current_stage") == "strategy"
    and not vm["read_only"]
):
    st.error("Strategy 返回内容有效，但集合被多包装了一层，旧契约因此误判失败。")
    st.caption("本地恢复会在新 Revision 中规范化已保存候选并继续报告、质量和看板；不会再次调用 Agent，也不会覆盖原运行。")
    if st.button("本地恢复 Strategy 并完成报告", type="primary", icon=":material/build:", key="recover_strategy_contract"):
        with st.status("正在本地恢复 Strategy、报告和看板", expanded=True) as status:
            try:
                result = recover_blocked_strategy(run)
                request_revision_selection(result["revision_id"])
                if result.get("plan_status") != "COMPLETED":
                    raise RuntimeError(
                        f"Revision 在 {result.get('failed_stage') or result.get('current_stage')} 阶段仍被阻断"
                    )
                status.update(label="Strategy、报告和看板已完成", state="complete")
                st.rerun()
            except Exception as error:
                status.update(label="本地恢复失败，原产物已保留", state="error")
                st.error(f"{type(error).__name__}: {error}")

if (
    run.get("revision_id") == "rev_000"
    and run.get("overall_status") == "BLOCKED_QUALITY"
    and run.get("current_stage") == "quality"
    and run.get("stages", {}).get("fact_check", {}).get("status") == "BLOCKED"
    and not vm["read_only"]
):
    st.error("当前显示的是旧版 rev_000；其 Fact Check 从未通过，因此后续 Quality 必然再次阻断。")
    st.caption("系统已保留你的人工选择。点击后会将它们迁移到已修复的 rev_001，不调用 Agent。")
    if st.button("迁移决定并切换到 rev_001", type="primary", icon=":material/move_up:"):
        try:
            result = migrate_decisions_to_revision(run, "rev_001")
            request_revision_selection(result["revision_id"])
            st.toast(f"已迁移 {result['migrated']} 条决定", icon=":material/check_circle:")
            st.rerun()
        except Exception as error:
            st.error(f"{type(error).__name__}: {error}")

if (
    run.get("revision_id") not in {None, "", "rev_000"}
    and run.get("overall_status") == "BLOCKED_QUALITY"
    and run.get("current_stage") == "report"
    and not vm["read_only"]
):
    st.error("Report Gate 发现了可本地修复的流程标签问题；Strategy 已通过，无需重新调用 Agent。")
    st.caption("本地修复只把 Human Feedback 状态段从外部事实改为流程记录，真实 FACT 的 Claim 引用规则保持不变。")
    if st.button("修复 Report 并继续本地检查", type="primary", icon=":material/build:"):
        with st.status("正在修复 Report、Quality 与 Dashboard", expanded=True) as status:
            try:
                result = repair_revision_report(run)
                if result.get("plan_status") != "COMPLETED":
                    raise RuntimeError(
                        f"Revision 在 {result.get('failed_stage') or result.get('current_stage')} 阶段仍被阻断"
                    )
                status.update(label="报告和看板已完成", state="complete")
                st.rerun()
            except Exception as error:
                status.update(label="本地修复失败，原产物已保留", state="error")
                st.error(f"{type(error).__name__}: {error}")

if vm["can_rebuild"] and not vm["read_only"]:
    st.warning("存在STALE下游产物。本操作只重建本地报告映射、Dashboard和Quality，不重新运行全部Agent。")
    confirm = st.checkbox("确认重建受影响的本地产物")
    if st.button("重建STALE下游", type="primary", icon=":material/build:", disabled=not confirm):
        with st.status("正在本地重建", expanded=True) as status:
            try:
                rebuild_stale_local(run)
                status.update(label="本地重建完成", state="complete")
                st.rerun()
            except Exception as error:
                status.update(label="本地重建失败", state="error")
                st.error(str(error))
