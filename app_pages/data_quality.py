import pandas as pd
import streamlit as st

from ui.components import empty_state, issue_list, page_header
from ui.view_models import quality_view_model
from ui.workspace import require_run

run = require_run()
vm = quality_view_model(run)
page_header("数据与质量", "集中处理数据覆盖、来源、质量问题和高级审计信息。")

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
        gap_count = sum(len(x.get("gaps", [])) for x in vm["datasets"] if x.get("priority") in {"CRITICAL", "IMPORTANT"})
        if gap_count and not vm["read_only"]:
            st.info(f"存在 {gap_count} 个可自动处理的CRITICAL/IMPORTANT缺口。定向补搜不会重新运行全部研究。")
            if st.button("自动补搜数据缺口", type="primary", icon=":material/search:"):
                st.warning("请在运行流程页确认当前阶段后执行；该操作可能调用Data Acquisition Agent。")

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
