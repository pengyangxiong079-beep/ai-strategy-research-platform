import pandas as pd
import streamlit as st

from ui.actions import start_targeted_gap_search
from ui.components import empty_state, issue_list, page_header
from ui.state import request_revision_selection
from ui.view_models import quality_view_model
from ui.workspace import require_run

run = require_run()
vm = quality_view_model(run)
page_header("数据与质量", "集中处理数据覆盖、来源、质量问题和高级审计信息。")

with st.container(horizontal=True):
    st.metric("证据支持率", f"{vm['support_rate']:.0%}" if vm["support_rate"] is not None else "—", border=True)
    st.metric("决策数据缺口", len(vm["decision_gaps"]), border=True)
    st.metric("Blocking", len(vm["blocking"]), border=True)
    st.metric("Warnings", len(vm["warnings"]), border=True)

if vm["decision_gaps"]:
    with st.container(border=True):
        st.subheader("决策前必须关闭的缺口")
        st.dataframe(
            pd.DataFrame([{
                "缺口": gap.get("label"), "为什么重要": gap.get("reason"),
                "关闭动作": gap.get("required_action") or "待定义",
            } for gap in vm["decision_gaps"]]),
            hide_index=True,
        )

view = st.segmented_control("视图", ["数据覆盖", "来源", "质量问题", "Claim ledger"], default="数据覆盖", key="quality_view")

if view == "数据覆盖":
    if not vm["datasets"]:
        empty_state("暂无数据覆盖结果", "Data Requirements运行后会生成确定性覆盖检查。")
    else:
        rows = []
        for item in vm["datasets"]:
            completeness = item.get("field_completeness", {})
            rows.append({"dataset": item.get("dataset_id"), "priority": item.get("priority"), "status": item.get("status"), "observations": item.get("observation_count"), "entities": item.get("entity_count"), "periods": len(item.get("periods", [])), "completeness": min(completeness.values()) if completeness else None, "comparability": item.get("comparability_rate"), "ready_charts": ", ".join(k for k,v in item.get("dashboard_readiness", {}).items() if v), "gaps": len(item.get("gaps", []))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={"completeness": st.column_config.ProgressColumn("completeness", min_value=0, max_value=1, format="percent"), "comparability": st.column_config.NumberColumn("comparability", format="percent")})
        gap_search = vm["targeted_gap_search"]
        if gap_search["target_count"] and not vm["read_only"]:
            st.info(
                f"存在 {gap_search['target_count']} 个可定向补搜的 CRITICAL/IMPORTANT 缺口。"
                f"已执行 {gap_search['attempt_count']}/{gap_search['limit']} 轮。"
            )
            with st.expander("查看补搜目标与查询", expanded=True, icon=":material/manage_search:"):
                target_rows = []
                for target in gap_search["targets"]:
                    queries = [
                        (query.get("query_text") or query.get("query") or "")
                        if isinstance(query, dict) else str(query)
                        for query in target.get("recommended_queries") or []
                    ]
                    target_rows.append({
                        "数据集": target.get("dataset_id"), "优先级": target.get("priority"),
                        "缺口": target.get("missing_field") or target.get("reason") or target.get("gap_id"),
                        "计划查询": "；".join(query for query in queries if query) or "由目标数据集生成受限查询",
                    })
                st.dataframe(pd.DataFrame(target_rows), hide_index=True)
                st.caption(
                    "执行范围：Data → Research → Review → Fact Check，然后自动停在人工决策。"
                    "仅补搜所列目标；无法公开验证的数据会继续保留为缺口，不会虚构。"
                )
            if gap_search["blocker"]:
                st.warning(gap_search["blocker"], icon=":material/info:")
            with st.container(border=True):
                confirmed = st.checkbox(
                    "我确认创建新 Revision，并允许调用 Data、Research、Review 和 Fact Check Agent",
                    key=f"confirm_gap_search_{run.get('run_id')}_{run.get('revision_id')}",
                )
                search = st.button(
                    "确认并启动定向补搜", type="primary", icon=":material/search:",
                    disabled=not confirmed or not gap_search["can_start"],
                    key=f"start_gap_search_{run.get('run_id')}_{run.get('revision_id')}",
                )
            if search:
                status = st.status("正在执行定向补搜", expanded=True)
                try:
                    result = start_targeted_gap_search(
                        run, gap_search["targets"],
                        lambda stage, message: status.write(f"**{stage}** · {message}"),
                    )
                    request_revision_selection(result["revision_id"])
                    if result.get("plan_status") == "FAILED":
                        raise RuntimeError(f"Revision 在 {result.get('failed_stage')} 阶段失败")
                    if result.get("plan_status") != "AWAITING_HUMAN_REVIEW":
                        raise RuntimeError(f"补搜结束状态异常：{result.get('plan_status')}")
                    status.update(label="定向补搜与事实核验完成，等待人工决策", state="complete")
                    st.switch_page("app_pages/decisions.py")
                except Exception as error:
                    status.update(label="定向补搜未完成，原版本已保留", state="error")
                    st.error(f"{type(error).__name__}: {error}")

elif view == "来源":
    if not vm["sources"]:
        empty_state("暂无来源", "Data Acquisition完成后会显示Source Registry。")
    else:
        fields = ["source_id", "publisher", "source_grade", "source_type", "publication_date", "datasets_supported", "access_status", "url"]
        st.dataframe(pd.DataFrame([{k: x.get(k) for k in fields} for x in vm["sources"]]), hide_index=True, column_config={"url": st.column_config.LinkColumn("url")})

elif view == "质量问题":
    st.subheader("Root Causes / 根因汇总")
    root_causes = vm.get("root_causes", [])
    if root_causes:
        st.caption(
            f"原始问题 {len(vm.get('raw_issues', []))} 条 · 根因 {len(root_causes)} 个 · "
            f"受影响项 {vm.get('affected_items', 0)} · 建议动作 {vm.get('recommended_revision_type', 'NONE')}"
        )
        st.dataframe(
            pd.DataFrame([{
                "root_cause": item.get("root_cause"),
                "rule_id": item.get("rule_id"),
                "stage": item.get("stage"),
                "affected_items": len(item.get("affected_items", [])),
                "automatic_fixability": item.get("automatic_fixability"),
                "recommended_action": item.get("recommended_action"),
            } for item in root_causes]),
            hide_index=True,
        )
    else:
        st.success("当前没有需要聚合的质量根因。")
    st.subheader(f"Blocking · {len(vm['blocking'])}")
    issue_list(vm["blocking"])
    st.subheader(f"Warnings · {len(vm['warnings'])}")
    issue_list(vm["warnings"])
    if vm["resolved"]:
        with st.expander(f"Resolved · {len(vm['resolved'])}"):
            issue_list(vm["resolved"])

else:
    st.caption("Claim Ledger属于高级审计功能，不是默认研究成果。")
    if not vm["claims"]:
        empty_state("Claim Ledger为空", "V2 Research/Fact Verification完成后会写入稳定Claim。")
    else:
        fields = ["display_id", "claim_id", "claim_type", "text", "verification_status", "temporal_status", "source_grade_max", "status"]
        st.dataframe(pd.DataFrame([{k: x.get(k) for k in fields} for x in vm["claims"]]), hide_index=True)
        raw = st.expander("原始JSON", icon=":material/code:", on_change="rerun")
        if raw.open:
            with raw: st.json({"claims": vm["claims"]}, expanded=False)
