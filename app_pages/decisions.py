import streamlit as st

from ui.actions import continue_strategy, record_decision
from ui.components import empty_state, page_header
from ui.view_models import decisions_view_model
from ui.workspace import require_run

run = require_run()
vm = decisions_view_model(run)
page_header("人工决策", "这里只处理当前流程中的人工判断；报告完成后的修改请进入“修订与版本”。")

st.subheader(f"待处理 · {len(vm['pending'])}")
if not vm["pending"]:
    empty_state("当前没有需要人工处理的事项", "所有人工决策已完成，或当前流程尚未到达Human Review。", icon=":material/check_circle:")
else:
    for index, decision in enumerate(vm["pending"]):
        with st.container(border=True):
            st.markdown(f"**{decision['title']}**")
            st.caption(f"{decision['decision_id']} · 来源阶段：{decision['source_stage']}")
            st.write(decision["why"])
            if decision.get("agent_suggestion"):
                st.caption(f"Agent建议：{decision['agent_suggestion']}")
            with st.form(f"decision_{decision['decision_id']}"):
                choice = st.selectbox("决策", decision["options"])
                note = st.text_area("用户说明", placeholder="说明接受、修改或补搜的具体边界")
                submitted = st.form_submit_button("提交决策", disabled=vm["read_only"], type="primary" if index == 0 else "secondary")
            if submitted:
                record_decision(run, decision, choice, note)
                st.toast("决策已持久化，并将Strategy及下游标记为STALE。", icon=":material/check_circle:")
                st.rerun()

if vm["resolved"]:
    with st.expander(f"已处理 · {len(vm['resolved'])}", icon=":material/task_alt:"):
        for item in vm["resolved"]:
            st.markdown(f"- `{item.get('feedback_id')}` · {item.get('choice')} · {item.get('note') or '无说明'}")

if not vm["pending"] and run.get("overall_status") in {"AWAITING_HUMAN_REVIEW", "REVISION_IN_PROGRESS"} and not vm["read_only"]:
    if st.button("继续生成Strategy", type="primary", icon=":material/play_arrow:"):
        status = st.status("正在生成Strategy与本地质量检查", expanded=True)
        try:
            def progress(stage, message): status.write(f"**{stage}** · {message}")
            continue_strategy(run, progress)
            status.update(label="Strategy与质量检查完成", state="complete")
            st.switch_page("app_pages/results.py")
        except Exception as error:
            status.update(label="Strategy执行失败，已保留产物", state="error")
            st.error(str(error))

