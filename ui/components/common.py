from __future__ import annotations

import streamlit as st

STATUS_COLORS = {
    "COMPLETE": "green", "COMPLETED": "green", "PASS": "green",
    "RUNNING": "blue", "AWAITING_USER": "orange", "AWAITING_HUMAN_REVIEW": "orange",
    "BLOCKED": "red", "BLOCKED_DATA": "red", "BLOCKED_QUALITY": "red",
    "STALE": "violet", "PENDING": "gray", "FAILED_TECHNICAL": "red",
    "COMPLETE_WITH_WARNINGS": "orange", "COMPLETED_WITH_WARNINGS": "orange",
}


def status_badge(status):
    color = STATUS_COLORS.get(str(status), "gray")
    st.badge(str(status or "UNKNOWN"), color=color)


def page_header(title, description="", *, icon=None, status=None):
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        with st.container(gap=None):
            st.title(title)
            if description:
                st.caption(description)
        if status:
            status_badge(status)


def context_bar(run):
    if not run:
        return
    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{run.get('topic', '未命名项目')}**")
        st.caption(f"类型：{run.get('normalized_analysis_type', '—')}")
        st.caption(f"地区：{run.get('geography', '—')}")
        st.caption(f"版本：{run.get('revision_id', 'rev_000')}")
        status_badge(run.get("overall_status", "UNKNOWN"))
        st.caption(f"更新：{run.get('updated_at', '—')}")


def workflow_stepper(stages, current_stage):
    labels = {"scope": "Scope", "data": "Data", "research": "Research", "review": "Review", "fact_check": "Fact check", "human": "Human review", "strategy": "Strategy", "quality": "Quality", "report": "Complete"}
    with st.container(horizontal=True):
        for name in ("scope", "data", "research", "review", "fact_check", "human", "strategy", "quality", "report"):
            status = (stages.get(name) or {}).get("status", "PENDING")
            marker = "●" if name == current_stage else ("✓" if status == "COMPLETE" else "○")
            st.caption(f"{marker} {labels[name]}\n{status}")


def empty_state(title, body, *, icon=":material/inbox:"):
    with st.container(border=True, horizontal_alignment="center"):
        st.markdown(icon)
        st.subheader(title)
        st.caption(body)


def issue_list(issues):
    if not issues:
        empty_state("没有问题", "当前筛选条件下没有质量问题。", icon=":material/check_circle:")
        return
    for item in issues:
        with st.container(border=True):
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.markdown(f"**{item.get('rule_id', 'ISSUE')}** · {item.get('stage', 'unknown')}")
                status_badge(item.get("severity", "WARNING"))
            st.write(item.get("reason") or item.get("detail") or "未提供原因")
            st.caption(f"位置：{item.get('artifact') or item.get('file') or '—'} {item.get('location') or item.get('line_number') or ''}")
            st.caption(f"建议：{item.get('suggested_action') or item.get('suggested_fix') or item.get('suggestion') or '人工复核'}")

