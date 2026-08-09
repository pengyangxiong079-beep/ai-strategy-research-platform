import json
from pathlib import Path

from .renderers import RENDERERS


TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / "templates"


def load_dashboard_template(template_id="general"):
    requested = TEMPLATE_DIRECTORY / f"{template_id}.json"
    if not requested.is_file():
        requested = TEMPLATE_DIRECTORY / "general.json"
    return json.loads(requested.read_text(encoding="utf-8"))


def prepare_components(report_data, template):
    prepared = []
    for configuration in template.get("components", []):
        component_id = configuration.get("component_id")
        renderer_id = configuration.get("renderer", component_id)
        renderer_class = RENDERERS.get(renderer_id)
        if renderer_class is None:
            prepared.append({**configuration, "status": "INSUFFICIENT_DATA", "reason": "未注册的renderer"})
            continue
        renderer = renderer_class(configuration)
        valid, reason = renderer.validate(report_data)
        prepared.append({
            **configuration,
            "renderer": renderer_id,
            "status": "READY" if valid else "INSUFFICIENT_DATA",
            "reason": "" if valid else reason,
        })
    return prepared


def render_component(component, report_data, st_module):
    renderer_class = RENDERERS.get(component.get("renderer"))
    if renderer_class is None:
        st_module.info(component.get("reason") or "组件不可用。")
        return False
    try:
        renderer = renderer_class(component)
        valid, reason = renderer.validate(report_data)
        if not valid:
            st_module.info(reason or "当前结构化数据不足，未生成该组件。")
            return False
        renderer.render(report_data, st_module)
        return True
    except Exception as error:
        st_module.info(f"组件暂不可用：{str(error)[:160]}")
        return False
