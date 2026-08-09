import streamlit as st

from ui.actions import rebuild_stale_local
from ui.components import page_header, status_badge
from ui.view_models import pipeline_view_model
from ui.workspace import require_run

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
