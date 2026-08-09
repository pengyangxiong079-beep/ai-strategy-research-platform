"""Streamlit Components v2 control for generating and opening an HTML dashboard."""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from .exporter import DashboardExportError, generate_dashboard_html


_COMPONENT_HTML = """
<button id="open-dashboard" type="button">
  <span class="material-symbols-rounded" aria-hidden="true">dashboard</span>
  <span class="button-label">生成并打开 HTML 可视化看板</span>
  <span class="material-symbols-rounded trailing" aria-hidden="true">open_in_new</span>
</button>
<span id="dashboard-status" role="status" aria-live="polite"></span>
"""

_COMPONENT_CSS = """
:host { display: block; font-family: var(--st-font); }
#open-dashboard {
  align-items: center;
  background: var(--st-primary-color);
  border: 1px solid var(--st-primary-color);
  border-radius: var(--st-button-radius, 0.5rem);
  color: var(--st-white-color, #fff);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 600;
  gap: 0.45rem;
  justify-content: center;
  min-height: 2.5rem;
  padding: 0.45rem 0.9rem;
}
#open-dashboard:hover { filter: brightness(0.94); }
#open-dashboard:focus-visible {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 2px;
}
#open-dashboard:disabled { cursor: wait; opacity: 0.7; }
.material-symbols-rounded {
  font-family: "Material Symbols Rounded";
  font-size: 1.15rem;
  font-style: normal;
  font-weight: normal;
  line-height: 1;
}
.trailing { margin-left: 0.1rem; }
#dashboard-status {
  color: var(--st-text-color);
  display: block;
  font-size: 0.82rem;
  margin-top: 0.35rem;
  min-height: 1.1rem;
  opacity: 0.75;
}
"""

_COMPONENT_JS = """
const popupByElement = new WeakMap()
const handledRequestByElement = new WeakMap()

function loadingDocument(title) {
  const safeTitle = String(title || "HTML 可视化看板")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
  return `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
    <title>${safeTitle}</title><style>
    body{font-family:system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;
    color:#263238;background:#f6f8fb}.box{text-align:center}.spinner{width:32px;height:32px;margin:0 auto 16px;
    border:3px solid #d9e1e8;border-top-color:#0068c9;border-radius:50%;animation:spin .8s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}</style></head><body><div class="box">
    <div class="spinner"></div><strong>正在生成可视化看板…</strong></div></body></html>`
}

export default function(component) {
  const { data, parentElement, setTriggerValue } = component
  const button = parentElement.querySelector("#open-dashboard")
  const label = parentElement.querySelector(".button-label")
  const status = parentElement.querySelector("#dashboard-status")
  if (!button || !label || !status) return

  const requestId = data?.request_id
  if (requestId && handledRequestByElement.get(parentElement) !== requestId) {
    handledRequestByElement.set(parentElement, requestId)
    button.disabled = false
    label.textContent = "生成并打开 HTML 可视化看板"
    if (data?.html) {
      const blob = new Blob([data.html], { type: "text/html;charset=utf-8" })
      const url = URL.createObjectURL(blob)
      let popup = popupByElement.get(parentElement)
      const params = new URLSearchParams({ run_id: data.run_id || "", revision: data.revision || "current" })
      const dashboardUrl = `${url}#${params}`
      if (!popup || popup.closed) popup = window.open(dashboardUrl, "_blank")
      else popup.location.replace(dashboardUrl)
      if (popup) {
        popup.focus()
        status.textContent = `已生成 ${data.filename || "dashboard.html"}，并在新标签页打开。`
        setTimeout(() => URL.revokeObjectURL(url), 60000)
      } else {
        status.textContent = "浏览器阻止了新标签页，请允许本站弹出窗口后重试。"
        URL.revokeObjectURL(url)
      }
    } else if (data?.error) {
      status.textContent = data.error
    }
  }

  button.onclick = () => {
    const popup = window.open("", "_blank")
    if (!popup) {
      status.textContent = "浏览器阻止了新标签页，请允许本站弹出窗口后重试。"
      return
    }
    popup.document.open()
    popup.document.write(loadingDocument(data?.title))
    popup.document.close()
    popupByElement.set(parentElement, popup)
    button.disabled = true
    label.textContent = "正在生成…"
    status.textContent = "正在创建自包含 HTML 文件，不会调用 Agent。"
    const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    setTriggerValue("generate", id)
  }
}
"""


def _register_component():
    return st.components.v2.component(
        "strategy_dashboard_html_opener",
        html=_COMPONENT_HTML,
        css=_COMPONENT_CSS,
        js=_COMPONENT_JS,
    )


_OPEN_DASHBOARD = _register_component()


def _component_key(output_folder, revision_id) -> str:
    identity = f"{Path(output_folder).resolve()}::{revision_id or 'current'}"
    return "dashboard_html_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def render_dashboard_html_action(output_folder, revision_id=None, *, title=None):
    """Render a one-click HTML generator that opens its result in a new tab."""
    if not output_folder:
        st.info("最终战略报告生成后，可在这里创建 HTML 可视化看板。")
        return

    component_key = _component_key(output_folder, revision_id)
    result_key = f"{component_key}_result"
    st.session_state.setdefault(result_key, {})

    def generate_for_request():
        component_state = st.session_state.get(component_key, {})
        request_id = getattr(component_state, "generate", None)
        if request_id is None and isinstance(component_state, dict):
            request_id = component_state.get("generate")
        if not request_id:
            return
        try:
            destination = generate_dashboard_html(output_folder, revision_id)
            st.session_state[result_key] = {
                "request_id": request_id,
                "html": destination.read_text(encoding="utf-8"),
                "filename": destination.name,
                "error": "",
            }
        except (DashboardExportError, OSError, TypeError, ValueError) as error:
            st.session_state[result_key] = {
                "request_id": request_id,
                "html": "",
                "filename": "",
                "error": f"HTML 看板生成失败：{error}",
            }

    result = st.session_state[result_key]
    mount_options = {
        "key": component_key,
        "data": {
            "title": title or "HTML 可视化看板",
            "run_id": Path(output_folder).resolve().name,
            "revision": str(revision_id or "current"),
            "request_id": result.get("request_id"),
            "html": result.get("html", ""),
            "filename": result.get("filename", ""),
            "error": result.get("error", ""),
        },
        "on_generate_change": generate_for_request,
    }
    global _OPEN_DASHBOARD
    try:
        _OPEN_DASHBOARD(**mount_options)
    except ValueError as error:
        # AppTest can reset the component registry while keeping imported modules cached.
        if "is not registered" not in str(error):
            raise
        _OPEN_DASHBOARD = _register_component()
        _OPEN_DASHBOARD(**mount_options)
