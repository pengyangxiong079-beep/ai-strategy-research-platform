from datetime import date
import pandas as pd
import streamlit as st

import main
from research_platform.data_requirements import build_requirements
from ui.actions import prepare_and_run, save_draft
from ui.components import page_header

page_header("新建分析", "按五个步骤确认研究任务、范围、问题和数据计划。")
step = int(st.session_state.current_wizard_step)
draft = st.session_state.analysis_draft
labels = ["分析任务", "研究范围", "重点问题与竞品", "模板与数据计划", "确认并运行"]
st.progress(step / 5, text=f"第 {step}/5 步 · {labels[step-1]}")

if step == 1:
    with st.form("wizard_task"):
        analysis_type = st.selectbox("分析类型", main.ANALYSIS_TYPES, index=main.ANALYSIS_TYPES.index(draft.get("analysis_type", "公司战略")) if draft.get("analysis_type", "公司战略") in main.ANALYSIS_TYPES else 0)
        topic = st.text_input("分析主题", value=draft.get("topic", ""), placeholder="例如：汉莎航空集团业务组合战略分析")
        objective = st.text_area("研究目标", value=draft.get("objective", "形成可验证的战略研究结论"))
        submitted = st.form_submit_button("下一步", type="primary", icon=":material/arrow_forward:")
    if submitted:
        if not topic.strip():
            st.error("请填写分析主题。")
        else:
            draft.update(analysis_type=analysis_type, topic=topic.strip(), objective=objective.strip())
            st.session_state.current_wizard_step = 2
            st.rerun()

elif step == 2:
    with st.form("wizard_scope"):
        industry = st.text_input("行业", value=draft.get("industry", "自动判断"))
        geography = st.text_input("地区", value=draft.get("geography", "全球"))
        analysis_date = st.date_input("分析基准日", value=date.fromisoformat(draft.get("analysis_date", date.today().isoformat())))
        time_horizon = st.text_input("时间范围", value=draft.get("time_horizon", "未来3年"))
        depth = st.segmented_control("研究深度", ["简版", "标准版", "深度版"], default=draft.get("depth", "标准版"))
        with st.container(horizontal=True):
            currency = st.text_input("币种", value=draft.get("currency", "未指定"))
            language = st.selectbox("报告语言", ["中文", "英文"], index=0 if draft.get("language", "中文") == "中文" else 1)
        back = st.form_submit_button("返回上一步")
        next_step = st.form_submit_button("下一步", type="primary", icon=":material/arrow_forward:")
    if back:
        st.session_state.current_wizard_step = 1; st.rerun()
    if next_step:
        if not geography.strip():
            st.error("请填写研究地区。")
        else:
            draft.update(industry=industry.strip(), geography=geography.strip(), analysis_date=analysis_date.isoformat(), time_horizon=time_horizon.strip(), depth=depth or "标准版", currency=currency.strip(), language=language)
            st.session_state.current_wizard_step = 3; st.rerun()

elif step == 3:
    with st.form("wizard_questions"):
        focus = st.text_area("重点问题（每行一个）", value="\n".join(draft.get("focus_questions", [])), height=160)
        competitors = st.text_area("竞品（每行一个）", value="\n".join(draft.get("competitors", [])), height=140)
        back = st.form_submit_button("返回上一步")
        next_step = st.form_submit_button("下一步", type="primary", icon=":material/arrow_forward:")
    if back:
        st.session_state.current_wizard_step = 2; st.rerun()
    if next_step:
        draft["focus_questions"] = [x.strip() for x in focus.splitlines() if x.strip()]
        draft["competitors"] = [x.strip() for x in competitors.splitlines() if x.strip()]
        st.session_state.current_wizard_step = 4; st.rerun()

else:
    try:
        scope = main.build_analysis_scope(**{key: draft.get(key) for key in ("analysis_type", "topic", "industry", "geography", "analysis_date", "time_horizon", "objective", "focus_questions", "competitors", "depth", "currency", "language")})
        requirements = build_requirements(scope)
    except (TypeError, ValueError) as error:
        st.error(f"Scope无效：{error}")
        if st.button("返回修改"):
            st.session_state.current_wizard_step = 1; st.rerun()
        st.stop()

    if step == 4:
        with st.container(border=True):
            st.subheader("模板路由")
            st.json({"normalized_analysis_type": scope["analysis_type_id"], "base_template": scope["base_template"], "industry_templates": scope["industry_templates"], "effective_templates": scope["effective_templates"], "required_sections": scope["required_sections"]}, expanded=False)
        rows = [{"数据集": x["dataset_id"], "优先级": x["priority"], "最少实体": x["minimum_entities"], "每实体最少Observation": x["minimum_observations_per_entity"]} for x in requirements["datasets"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        with st.form("wizard_plan_actions", border=False):
            back = st.form_submit_button("返回上一步")
            next_step = st.form_submit_button("下一步", type="primary", icon=":material/arrow_forward:")
        if back:
            st.session_state.current_wizard_step = 3; st.rerun()
        if next_step:
            st.session_state.current_wizard_step = 5; st.rerun()
    else:
        with st.container(border=True):
            st.subheader(scope["topic"])
            st.json({key: scope[key] for key in ("analysis_type_id", "industry", "geography", "analysis_date", "time_horizon", "depth", "focus_questions", "competitors", "effective_templates")}, expanded=True)
        with st.form("wizard_confirm"):
            confirm = st.checkbox("我已确认研究范围；运行将调用必要的Research Agent。")
            back = st.form_submit_button("返回上一步")
            save = st.form_submit_button("保存草稿", icon=":material/save:")
            run = st.form_submit_button("确认研究范围并开始", type="primary", icon=":material/play_arrow:", disabled=not confirm)
        if back:
            st.session_state.current_wizard_step = 4; st.rerun()
        if save:
            path = save_draft(draft); st.toast(f"草稿已保存：{path.name}", icon=":material/check_circle:")
        if run:
            status = st.status("正在启动Pipeline V2", expanded=True)
            def progress(stage, message):
                status.write(f"**{stage}** · {message}")
            try:
                prepared, _ = prepare_and_run({key: draft.get(key) for key in ("analysis_type", "topic", "industry", "geography", "analysis_date", "time_horizon", "objective", "focus_questions", "competitors", "depth", "currency", "language")}, progress)
                st.session_state.selected_run_id = prepared["run_id"]
                st.session_state.selected_project_id = prepared["run_id"]
                st.session_state.current_wizard_step = 1
                st.session_state.analysis_draft = {}
                status.update(label="已完成研究与核验，等待人工决策", state="complete")
                st.switch_page("app_pages/decisions.py")
            except Exception as error:
                status.update(label="运行发生技术错误，已保留产物", state="error")
                st.error(str(error))

