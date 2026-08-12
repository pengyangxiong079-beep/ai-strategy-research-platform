import json
from pathlib import Path
import streamlit as st

from ui.components import page_header
from pipeline_v2.readiness import pipeline_v2_readiness, workspace_v2_readiness
from pipeline_v2.agent_provider import get_agent_provider_status

page_header("设置", "配置工作台默认值；当前run操作不放在这里。")
pipeline_ready = pipeline_v2_readiness()
workspace_ready = workspace_v2_readiness()
provider_status = get_agent_provider_status()
with st.container(border=True):
    st.subheader("Agent Provider")
    st.write(f"当前 Provider：`{provider_status.provider}`")
    st.write(f"当前运行模式：`{provider_status.mode}`")
    st.write(f"允许真实 Agent 调用：`{'是' if provider_status.real_agent_calls_allowed else '否'}`")
path = Path(".workspace/settings.json")
try:
    current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
except ValueError:
    current = {}

with st.form("workspace_settings"):
    language = st.selectbox("默认语言", ["中文", "英文"], index=0 if current.get("language", "中文") == "中文" else 1)
    depth = st.selectbox("默认深度", ["简版", "标准版", "深度版"], index=["简版", "标准版", "深度版"].index(current.get("depth", "标准版")))
    output_dir = st.text_input("输出目录", value=current.get("output_dir", "outputs"))
    gap_limit = st.number_input("自动补搜上限", min_value=0, max_value=2, value=int(current.get("gap_limit", 2)))
    repair_limit = st.number_input("整个run自动修复上限", min_value=0, max_value=6, value=int(current.get("repair_limit", 6)))
    pipeline_v2 = st.toggle("新运行默认使用Pipeline V2", value=bool(current.get("pipeline_v2", False) and pipeline_ready["ready"] and workspace_ready["ready"]), disabled=not (pipeline_ready["ready"] and workspace_ready["ready"]))
    dashboard_address = st.text_input("Dashboard地址", value=current.get("dashboard_address", "本地自包含HTML"))
    debug = st.toggle("显示调试信息", value=current.get("debug", False))
    submitted = st.form_submit_button("保存设置", type="primary", icon=":material/save:")
if submitted:
    payload = {"language": language, "depth": depth, "output_dir": output_dir, "gap_limit": gap_limit, "repair_limit": repair_limit, "pipeline_v2": pipeline_v2, "dashboard_address": dashboard_address, "debug": debug}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    st.session_state.debug_mode = debug
    st.toast("设置已保存。", icon=":material/check_circle:")

st.caption("本平台继续使用当前Codex认证方式，不要求OPENAI_API_KEY，也不接入付费搜索API。")

with st.expander("V2 production readiness", icon=":material/fact_check:"):
    st.write(f"Pipeline V2：{'READY' if pipeline_ready['ready'] else 'NOT READY'}")
    if pipeline_ready["blocking"]:
        st.caption("阻塞项：" + "、".join(pipeline_ready["blocking"]))
    st.write(f"Workspace V2：{'READY' if workspace_ready['ready'] else 'NOT READY'}")
    if workspace_ready["blocking"]:
        st.caption("阻塞项：" + "、".join(workspace_ready["blocking"]))
