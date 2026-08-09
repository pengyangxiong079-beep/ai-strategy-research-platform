import pandas as pd
import streamlit as st

from ui.actions import (
    cancel_revision, confirm_revision, execute_revision, generate_revision_preview,
    pause_revision, resume_revision, retry_revision_stage,
)
from ui.components import empty_state, page_header
from ui.view_models import revision_view_model
from ui.workspace import require_run

run = require_run()
page_header("修订与版本", "先生成真实依赖计划，再创建和执行；不完整版本不会成为当前版本。")

types = {
    "本地修复": "LOCAL_REPAIR", "仅修订战略": "STRATEGY_ONLY",
    "事实核验修订": "FACT_VERIFICATION", "完整重新研究": "FULL_RESEARCH",
}
revision_label = st.segmented_control("修订类型", list(types), default="本地修复", key="revision_type", persist_state="session")
vm = revision_view_model(run, types[revision_label])
real_versions = [item for item in vm["versions"] if not item.get("is_initial_snapshot")]

st.subheader("版本时间线")
if not vm["versions"]:
    empty_state("尚无Revision", "完成首版报告后，可以从Dry Run影响预览创建修订。")
else:
    st.caption(f"当前生效版本：{vm['active_revision_id']}")
    st.dataframe(pd.DataFrame(vm["versions"]), hide_index=True)

st.subheader("创建Revision")
with st.form("revision_request", border=True):
    objective = st.text_input("修订目标", key="revision_objective")
    requested = st.text_area("请求的变更", key="revision_requested_changes")
    claims = st.text_area("受影响对象ID（每行一个）", key="revision_claims")
    scope_changed = st.checkbox("研究范围发生变化", disabled=types[revision_label] != "FULL_RESEARCH")
    data_as_of = st.text_input("数据基准日", placeholder="YYYY-MM-DD")
    preview_clicked = st.form_submit_button("生成影响预览", type="primary", icon=":material/preview:", disabled=vm["read_only"])

if preview_clicked:
    try:
        preview = generate_revision_preview(
            run, types[revision_label], requested_changes=[objective, *requested.splitlines()],
            affected_object_ids=claims.splitlines(), scope_changed=scope_changed,
            scope_diff={"requested_scope_change": requested} if scope_changed else {}, data_as_of_date=data_as_of,
        )
        st.session_state.revision_preview = preview
    except Exception as error:
        st.error(str(error), icon=":material/error:")

preview_data = st.session_state.get("revision_preview")
if preview_data:
    with st.container(border=True):
        st.subheader("Impact preview")
        st.write(f"Base revision：`{preview_data['base_revision_id']}`")
        st.write(f"Revision type：`{preview_data['revision_type']}`")
        st.write(f"保留阶段：{', '.join(preview_data['preserved_stages']) or '无'}")
        st.write(f"失效阶段：{', '.join(preview_data['invalidated_stages']) or '无'}")
        st.write(f"执行阶段：{', '.join(preview_data['execution_stages']) or '无'}")
        st.write(f"预计Agent调用：{preview_data['estimated_agent_calls']} · 本地步骤：{preview_data['estimated_local_steps']}")
        st.write(f"人工审核：{'需要' if preview_data['requires_human_review'] else '不需要'}")
        st.caption("原版本始终保留；只有全部执行成功后才切换active revision。")
        confirmed = st.checkbox("我确认影响范围并保留原版本", key="revision_confirmed")
        if st.button("确认并创建Revision", icon=":material/add:", disabled=not confirmed or vm["read_only"]):
            try:
                path = confirm_revision(run, preview_data)
                st.session_state.revision_preview = None
                st.toast(f"已创建 {path.name}", icon=":material/check_circle:")
                st.rerun()
            except Exception as error:
                st.error(str(error), icon=":material/error:")

if real_versions:
    st.subheader("执行控制")
    revision_id = st.selectbox("Revision", [x["revision_id"] for x in reversed(real_versions)], key="revision_executor_selection")
    selected = next(x for x in real_versions if x["revision_id"] == revision_id)
    st.caption(f"状态：{selected['status']} · 当前阶段：{selected.get('current_stage') or '无'}")
    with st.container(horizontal=True):
        actions = {
            "执行Revision": lambda: execute_revision(run, revision_id),
            "暂停": lambda: pause_revision(run, revision_id),
            "继续": lambda: resume_revision(run, revision_id),
            "重试失败阶段": lambda: retry_revision_stage(run, revision_id),
            "取消Revision": lambda: cancel_revision(run, revision_id),
        }
        for label, callback in actions.items():
            if st.button(label, key=f"revision_{label}_{revision_id}", disabled=vm["read_only"]):
                try:
                    callback()
                    st.rerun()
                except Exception as error:
                    st.error(str(error), icon=":material/error:")

if vm["show_comparison"]:
    st.subheader("Revision comparison")
    choices = [x["revision_id"] for x in vm["versions"]]
    left, right = st.columns(2)
    old = left.selectbox("旧版本", choices, index=max(0, len(choices) - 2))
    new = right.selectbox("新版本", choices, index=len(choices) - 1)
    st.caption(f"比较 {old} → {new} 的Claim、数据、来源、建议、风险、KPI和质量状态。")
