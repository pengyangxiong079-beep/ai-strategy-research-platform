import copy
import json
import re
from datetime import date
from pathlib import Path

import streamlit as st

from dashboard.open_component import render_dashboard_html_action
from dashboard.registry import render_component

from main import (
    WorkflowError,
    build_run_zip,
    ensure_initial_revision,
    list_run_manifests,
    list_revision_versions,
    load_manifest,
    load_revision_version,
    load_run_history,
    mark_manifest_failed,
    prepare_analysis_run,
    rerun_local_revision,
    revise_strategy_report,
    run_revision_research_phase,
    run_gap_search,
    run_research_phase,
    run_strategy_phase,
    sanitize_error_message,
)
from research_platform.pipeline import import_local_observations, load_data_coverage


NOT_STARTED = "尚未开始"
SCOPE_PENDING = "等待确认研究范围"
RESEARCHING = "正在研究"
AWAITING_APPROVAL = "等待人工审核"
GENERATING_FINAL = "正在生成最终报告"
COMPLETED = "已完成"
FAILED = "运行失败"
REVISING = "修订中"

QUALITY_DISCLAIMER = (
    "PASS仅代表本地结构与规则检查通过，不代表网页内容和事实真实性已经得到保证。"
)

HISTORY_STATUS_BADGES = {
    "COMPLETED": "🟢",
    "COMPLETED_WITH_WARNINGS": "🟠",
    "NEEDS_REVISION": "🔴",
    "ERROR": "⚫",
}

CURRENT_ANALYSIS_KEYS = (
    "topic_input",
    "analysis_type_input",
    "industry_input",
    "auto_industry_input",
    "geography_input",
    "analysis_date_input",
    "time_horizon_input",
    "objective_input",
    "focus_questions_input",
    "competitors_input",
    "depth_input",
    "currency_input",
    "language_input",
    "analysis_scope",
    "scope_report",
    "topic",
    "workflow_phase",
    "current_stage",
    "status_message",
    "research_report",
    "review_report",
    "fact_report",
    "human_feedback",
    "feedback_input",
    "final_report",
    "quality_report",
    "quality_status",
    "output_folder",
    "workflow_files",
    "run_manifest",
    "selected_run_id",
    "human_feedback_report",
    "error_state",
    "revision_center_open",
    "revision_request_input",
    "revision_version_select",
    "dashboard_compare_left",
    "dashboard_compare_right",
    "local_observation_upload",
)


def initialize_state():
    defaults = {
        "topic_input": "",
        "analysis_type_input": "公司战略",
        "industry_input": "",
        "auto_industry_input": True,
        "geography_input": "全球",
        "analysis_date_input": date.today(),
        "time_horizon_input": "",
        "objective_input": "",
        "focus_questions_input": "",
        "competitors_input": "",
        "depth_input": "标准版",
        "currency_input": "",
        "language_input": "中文",
        "analysis_scope": None,
        "scope_report": None,
        "topic": "",
        "workflow_phase": NOT_STARTED,
        "current_stage": NOT_STARTED,
        "status_message": "请输入研究对象并点击“开始研究”。",
        "research_report": None,
        "review_report": None,
        "fact_report": None,
        "human_feedback": "",
        "feedback_input": "",
        "final_report": None,
        "quality_report": None,
        "quality_status": None,
        "output_folder": None,
        "workflow_files": None,
        "run_manifest": None,
        "viewing_history": False,
        "selected_run_id": None,
        "history_search": "",
        "human_feedback_report": None,
        "error_state": None,
        "revision_center_open": False,
        "revision_request_input": "",
        "revision_version_select": None,
        "dashboard_compare_left": None,
        "dashboard_compare_right": None,
        "local_observation_upload": None,
        "is_running": False,
        "pending_action": None,
        "action_counter": 0,
        "queued_action_id": None,
        "executed_action_id": None,
        "current_analysis_snapshot": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def has_intermediate_reports():
    return bool(
        st.session_state.output_folder
        and st.session_state.workflow_files
        and st.session_state.research_report
        and st.session_state.review_report
        and st.session_state.fact_report
    )


def queue_action(action):
    st.session_state.action_counter += 1
    st.session_state.queued_action_id = st.session_state.action_counter
    st.session_state.pending_action = action
    st.session_state.is_running = True
    st.session_state.error_state = None


def request_research():
    if st.session_state.is_running:
        return
    topic = st.session_state.topic_input.strip()
    geography = st.session_state.geography_input.strip()
    analysis_date_value = st.session_state.analysis_date_input
    if not topic or not geography or not analysis_date_value:
        st.session_state.error_state = "topic、analysis_type、geography和analysis_date为必填项。"
        st.session_state.workflow_phase = NOT_STARTED
        return

    st.session_state.topic = topic
    st.session_state.workflow_phase = SCOPE_PENDING
    st.session_state.current_stage = "正在生成分析范围"
    st.session_state.status_message = "正在本地生成分析范围，不调用Agent。"
    st.session_state.research_report = None
    st.session_state.review_report = None
    st.session_state.fact_report = None
    st.session_state.human_feedback = ""
    st.session_state.feedback_input = ""
    st.session_state.final_report = None
    st.session_state.quality_report = None
    st.session_state.quality_status = None
    st.session_state.output_folder = None
    st.session_state.workflow_files = None
    st.session_state.run_manifest = None
    st.session_state.viewing_history = False
    st.session_state.selected_run_id = None
    st.session_state.human_feedback_report = None
    st.session_state.analysis_scope = None
    st.session_state.scope_report = None
    queue_action("prepare_scope")


def request_scope_confirmation():
    if st.session_state.is_running or not st.session_state.analysis_scope:
        return
    if st.session_state.workflow_phase != SCOPE_PENDING:
        return
    st.session_state.workflow_phase = RESEARCHING
    st.session_state.current_stage = RESEARCHING
    st.session_state.status_message = "范围已确认，正在启动数据需求规划、采集、充分性检查和Research。"
    queue_action("research")


def request_final_report():
    if st.session_state.is_running or not has_intermediate_reports():
        st.session_state.error_state = "前三阶段尚未完成，不能生成最终报告。"
        return
    if st.session_state.workflow_phase != AWAITING_APPROVAL:
        return

    st.session_state.human_feedback = st.session_state.feedback_input.strip()
    st.session_state.workflow_phase = GENERATING_FINAL
    st.session_state.current_stage = GENERATING_FINAL
    st.session_state.status_message = "人工审核已批准，正在启动Strategy Agent。"
    queue_action("strategy")


def request_reresearch():
    if st.session_state.is_running or not has_intermediate_reports():
        st.session_state.error_state = "前三阶段尚未完成，不能重新研究。"
        return
    if st.session_state.workflow_phase != AWAITING_APPROVAL:
        return

    st.session_state.human_feedback = st.session_state.feedback_input.strip()
    st.session_state.workflow_phase = RESEARCHING
    st.session_state.current_stage = RESEARCHING
    st.session_state.status_message = "正在根据人工意见重新运行前三个Agent。"
    st.session_state.final_report = None
    st.session_state.quality_report = None
    st.session_state.quality_status = None
    queue_action("reresearch")


def request_gap_search():
    if st.session_state.is_running or not st.session_state.output_folder:
        return
    st.session_state.current_stage = "Gap Search"
    st.session_state.status_message = "正在只针对Data Coverage中的关键缺口执行定向补搜。"
    queue_action("gap_search")


def request_optional_gap_search():
    if st.session_state.is_running or not st.session_state.output_folder:
        return
    st.session_state.current_stage = "Optional Gap Search"
    st.session_state.status_message = "正在只针对用户主动选择的OPTIONAL数据缺口执行定向补搜。"
    queue_action("optional_gap_search")


def revision_is_available():
    manifest = st.session_state.run_manifest or {}
    return bool(
        st.session_state.output_folder
        and manifest.get("final_status")
        in {"NEEDS_REVISION", "COMPLETED_WITH_WARNINGS", "COMPLETED"}
        and st.session_state.final_report
        and st.session_state.quality_report
    )


def open_revision_center():
    if st.session_state.is_running or not revision_is_available():
        return
    ensure_initial_revision(st.session_state.output_folder)
    versions = list_revision_versions(st.session_state.output_folder)
    st.session_state.revision_version_select = (
        versions[-1]["revision_id"] if versions else None
    )
    st.session_state.revision_center_open = True
    st.session_state.revision_request_input = ""


def close_revision_center():
    if not st.session_state.is_running:
        st.session_state.revision_center_open = False


def request_local_revision():
    if st.session_state.is_running or not revision_is_available():
        return
    st.session_state.workflow_phase = REVISING
    st.session_state.current_stage = "仅重新运行本地检查"
    st.session_state.status_message = "正在运行本地检查；不消耗模型额度。"
    queue_action("revision_local")


def request_strategy_revision():
    if st.session_state.is_running or not revision_is_available():
        return
    st.session_state.workflow_phase = REVISING
    st.session_state.current_stage = "Strategy Agent修订"
    st.session_state.status_message = "只调用Strategy Agent修订现有最终报告。"
    queue_action("revision_strategy")


def request_revision_research():
    if st.session_state.is_running or not revision_is_available():
        return
    revision_request = st.session_state.revision_request_input.strip()
    st.session_state.human_feedback = revision_request
    st.session_state.feedback_input = revision_request
    st.session_state.workflow_phase = REVISING
    st.session_state.current_stage = "根据问题重新研究"
    st.session_state.status_message = "将重新运行前三个Agent，完成后再次等待人工审核。"
    st.session_state.revision_center_open = False
    queue_action("revision_research")


def store_revision_result(result):
    output_folder = Path(st.session_state.output_folder)
    st.session_state.run_manifest = result["manifest"]
    st.session_state.final_report = (output_folder / "04_final_report.md").read_text(
        encoding="utf-8"
    )
    st.session_state.quality_report = result["quality"]
    st.session_state.quality_status = result["quality_status"]
    st.session_state.workflow_phase = COMPLETED
    st.session_state.current_stage = "修订完成"
    st.session_state.status_message = (
        f"修订版本{result['revision']['revision_id']}已保存，质量结果："
        f"{result['quality_status']}。"
    )
    st.session_state.revision_version_select = result["revision"]["revision_id"]


def safe_ui_error(error):
    message = sanitize_error_message(error)
    return re.sub(r"(?i)\btoken\b\s*[:=]\s*[^\s,;]+", "[REDACTED]", message)


def save_current_analysis_snapshot():
    st.session_state.current_analysis_snapshot = {
        key: copy.deepcopy(st.session_state.get(key))
        for key in CURRENT_ANALYSIS_KEYS
    }


def return_to_current_analysis():
    if st.session_state.is_running or not st.session_state.current_analysis_snapshot:
        return
    for key, value in st.session_state.current_analysis_snapshot.items():
        st.session_state[key] = copy.deepcopy(value)
    st.session_state.viewing_history = False


def start_new_analysis():
    if st.session_state.is_running:
        return
    defaults = {
        "topic_input": "",
        "analysis_type_input": "公司战略",
        "industry_input": "",
        "auto_industry_input": True,
        "geography_input": "全球",
        "analysis_date_input": date.today(),
        "time_horizon_input": "",
        "objective_input": "",
        "focus_questions_input": "",
        "competitors_input": "",
        "depth_input": "标准版",
        "currency_input": "",
        "language_input": "中文",
        "analysis_scope": None,
        "scope_report": None,
        "topic": "",
        "workflow_phase": NOT_STARTED,
        "current_stage": NOT_STARTED,
        "status_message": "请输入研究对象并点击“开始研究”。",
        "research_report": None,
        "review_report": None,
        "fact_report": None,
        "human_feedback": "",
        "feedback_input": "",
        "final_report": None,
        "quality_report": None,
        "quality_status": None,
        "output_folder": None,
        "workflow_files": None,
        "run_manifest": None,
        "selected_run_id": None,
        "human_feedback_report": None,
        "error_state": None,
        "revision_center_open": False,
        "revision_request_input": "",
        "revision_version_select": None,
        "dashboard_compare_left": None,
        "dashboard_compare_right": None,
        "local_observation_upload": None,
    }
    for key, value in defaults.items():
        st.session_state[key] = value
    st.session_state.viewing_history = False
    st.session_state.current_analysis_snapshot = None


def store_research_result(result):
    st.session_state.topic = result["topic"]
    st.session_state.output_folder = result["output_folder"]
    st.session_state.workflow_files = result["files"]
    st.session_state.research_report = result["contents"]["research"]
    st.session_state.review_report = result["contents"]["review"]
    st.session_state.fact_report = result["contents"]["fact"]
    st.session_state.human_feedback_report = result["contents"].get("feedback")
    st.session_state.human_feedback = st.session_state.feedback_input.strip()
    st.session_state.final_report = None
    st.session_state.quality_report = None
    st.session_state.quality_status = None
    st.session_state.run_manifest = result.get("manifest")
    st.session_state.scope_report = result["contents"].get("scope")
    st.session_state.viewing_history = False
    st.session_state.selected_run_id = (
        result.get("manifest", {}).get("run_id") if result.get("manifest") else None
    )


def store_final_result(result):
    st.session_state.output_folder = result["output_folder"]
    st.session_state.workflow_files = result["files"]
    st.session_state.research_report = result["contents"]["research"]
    st.session_state.review_report = result["contents"]["review"]
    st.session_state.fact_report = result["contents"]["fact"]
    st.session_state.final_report = result["contents"]["final"]
    st.session_state.quality_report = result["contents"]["quality"]
    st.session_state.quality_status = result["quality_status"]
    st.session_state.human_feedback_report = result["contents"].get("feedback")
    st.session_state.run_manifest = result.get("manifest")
    st.session_state.scope_report = result["contents"].get("scope")
    st.session_state.viewing_history = False
    st.session_state.selected_run_id = (
        result.get("manifest", {}).get("run_id") if result.get("manifest") else None
    )
    st.session_state.revision_version_select = result.get("manifest", {}).get(
        "latest_revision"
    )


def research_result_from_state():
    return {
        "topic": st.session_state.topic,
        "output_folder": Path(st.session_state.output_folder),
        "workflow_stage": AWAITING_APPROVAL,
        "quality_status": None,
        "manifest": st.session_state.run_manifest,
        "files": st.session_state.workflow_files,
        "contents": {
            "research": st.session_state.research_report,
            "review": st.session_state.review_report,
            "fact": st.session_state.fact_report,
            "feedback": None,
            "final": None,
            "quality": None,
            "scope": st.session_state.scope_report,
        },
    }


def open_history_run(run_id):
    if st.session_state.is_running:
        return
    if not st.session_state.viewing_history:
        save_current_analysis_snapshot()
    try:
        result = load_run_history(run_id)
    except Exception as error:
        st.session_state.error_state = safe_ui_error(error)
        return

    manifest = result["manifest"]
    st.session_state.topic = result["topic"]
    st.session_state.topic_input = result["topic"]
    st.session_state.output_folder = result["output_folder"]
    st.session_state.workflow_files = result["files"]
    st.session_state.research_report = result["contents"].get("research")
    st.session_state.scope_report = result["contents"].get("scope")
    if st.session_state.scope_report:
        try:
            st.session_state.analysis_scope = json.loads(st.session_state.scope_report)
        except (ValueError, TypeError):
            st.session_state.analysis_scope = None
    else:
        st.session_state.analysis_scope = None
    st.session_state.review_report = result["contents"].get("review")
    st.session_state.fact_report = result["contents"].get("fact")
    st.session_state.human_feedback_report = result["contents"].get("feedback")
    st.session_state.human_feedback = manifest.get("human_feedback", "")
    st.session_state.feedback_input = manifest.get("human_feedback", "")
    st.session_state.final_report = result["contents"].get("final")
    st.session_state.quality_report = result["contents"].get("quality")
    st.session_state.quality_status = manifest.get("quality_check_status")
    st.session_state.run_manifest = manifest
    st.session_state.viewing_history = True
    st.session_state.selected_run_id = manifest.get("run_id")
    st.session_state.current_stage = manifest.get("current_stage", "历史记录")
    final_status = manifest.get("final_status")
    if final_status in {
        "COMPLETED",
        "COMPLETED_WITH_WARNINGS",
        "NEEDS_REVISION",
    }:
        st.session_state.workflow_phase = COMPLETED
    elif final_status in {"ERROR", "FAILED"}:
        st.session_state.workflow_phase = FAILED
    elif final_status in {"AWAITING_APPROVAL", "NOT_APPROVED"}:
        st.session_state.workflow_phase = AWAITING_APPROVAL
    elif final_status == "AWAITING_SCOPE_CONFIRMATION":
        st.session_state.workflow_phase = SCOPE_PENDING
    else:
        st.session_state.workflow_phase = manifest.get("current_stage", NOT_STARTED)
    st.session_state.status_message = "已打开历史记录；未调用任何Agent。"
    st.session_state.error_state = (
        manifest.get("error_message") if final_status in {"ERROR", "FAILED"} else None
    )
    if final_status in {"NEEDS_REVISION", "COMPLETED_WITH_WARNINGS", "COMPLETED"}:
        ensure_initial_revision(result["output_folder"])
        versions = list_revision_versions(result["output_folder"])
        st.session_state.run_manifest = load_manifest(result["output_folder"])
        st.session_state.revision_version_select = (
            versions[-1]["revision_id"] if versions else None
        )
    st.session_state.revision_center_open = False


def render_report_tab(
    tab,
    content,
    file_path,
    title,
    disclaimer=None,
    dashboard_output_folder=None,
    dashboard_revision_id=None,
):
    with tab:
        if disclaimer:
            st.warning(disclaimer)
        if not content:
            st.info("对应阶段完成后将在这里显示内容。")
            return

        if file_path:
            st.download_button(
                label=f"下载 {Path(file_path).name}",
                data=content.encode("utf-8"),
                file_name=Path(file_path).name,
                mime="text/markdown",
                key=f"download_{Path(file_path).name}",
            )
        st.markdown(f"### {title}")
        st.markdown(content)
        if dashboard_output_folder:
            st.divider()
            st.markdown("#### HTML 可视化看板")
            st.caption("基于当前报告的结构化数据生成独立 HTML；不会再次调用 Agent。")
            render_dashboard_html_action(
                dashboard_output_folder,
                dashboard_revision_id,
                title=f"{title} · 可视化看板",
            )


def read_json_file(path):
    if not path or not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def flatten_json(value, prefix=""):
    rows = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.update(flatten_json(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.update(flatten_json(item, f"{prefix}[{index}]"))
    else:
        rows[prefix] = value
    return rows


def revision_change_rows(left_data, right_data):
    left = flatten_json(left_data or {})
    right = flatten_json(right_data or {})
    return [
        {"字段": key, "旧值": left.get(key), "新值": right.get(key)}
        for key in sorted(set(left) | set(right))
        if left.get(key) != right.get(key)
    ]


def render_dashboard(tab, dashboard_data, output_folder, revision_id=None):
    with tab:
        if not dashboard_data:
            st.info("该报告没有可用的结构化看板数据；不会从Markdown临时提取数字。")
            return
        scope = dashboard_data.get("scope") or {}
        quality = dashboard_data.get("quality_status", "UNKNOWN")
        header = st.columns(5)
        header[0].metric("分析对象", scope.get("topic") or "N/A")
        header[1].metric("地区", scope.get("geography") or "N/A")
        header[2].metric("基准日", scope.get("analysis_date") or "N/A")
        header[3].metric("报告版本", revision_id or dashboard_data.get("report_version") or "current")
        header[4].metric("Quality状态", quality)

        status = dashboard_data.get("dashboard_status", "UNAVAILABLE")
        if status == "BLOCKED_BY_QUALITY":
            st.error("当前报告尚未通过质量检查，不应用于正式决策。")
        elif status == "READY_WITH_GAPS":
            st.warning("Dashboard可查看，但仍存在质量警告或数据缺口。")
        elif status == "UNAVAILABLE":
            reasons = dashboard_data.get("validation_errors") or ["结构化报告数据不可用。"]
            st.info("Dashboard UNAVAILABLE：" + "；".join(map(str, reasons)))
            return

        report_data = dashboard_data.get("report_data") or {}
        components = dashboard_data.get("components") or []
        page_names = [
            "Overview",
            "Market",
            "Competition",
            "Risk & Opportunity",
            "Strategy Roadmap",
            "Evidence Quality",
        ]
        page_tabs = st.tabs(page_names)
        for page_tab, page_name in zip(page_tabs, page_names):
            with page_tab:
                page_components = [item for item in components if item.get("page") == page_name]
                if not page_components:
                    st.info("当前模板未配置该页面组件。")
                    continue
                # 每页最多一个主视图和一个辅助拆分/表格；KPI renderer内部最多显示3项。
                for component in page_components[:2]:
                    st.markdown(f"#### {component.get('title', component.get('component_id', '组件'))}")
                    render_component(component, report_data, st)

        versions = list_revision_versions(output_folder) if output_folder else []
        version_ids = [item.get("revision_id") for item in versions]
        if len(version_ids) >= 2:
            with st.expander("比较同一运行的两个revision（字段变化）"):
                left_column, right_column = st.columns(2)
                default_left = version_ids[-2]
                default_right = version_ids[-1]
                if st.session_state.dashboard_compare_left not in version_ids:
                    st.session_state.dashboard_compare_left = default_left
                if st.session_state.dashboard_compare_right not in version_ids:
                    st.session_state.dashboard_compare_right = default_right
                left_id = left_column.selectbox(
                    "旧版本", version_ids, key="dashboard_compare_left"
                )
                right_id = right_column.selectbox(
                    "新版本", version_ids, key="dashboard_compare_right"
                )
                left_revision = load_revision_version(output_folder, left_id)
                right_revision = load_revision_version(output_folder, right_id)
                changes = revision_change_rows(
                    left_revision.get("report_data"), right_revision.get("report_data")
                )
                if changes:
                    st.dataframe(changes, width="stretch", hide_index=True)
                else:
                    st.info("两个版本的结构化报告数据没有字段变化，或均不可用。")


def render_data_coverage(tab, output_folder, analysis_scope):
    with tab:
        st.markdown("### Data Coverage / 数据覆盖")
        if not output_folder:
            st.info("确认研究范围后将生成数据需求、搜索计划和充分性检查。")
            return
        coverage = load_data_coverage(output_folder)
        requirements = coverage.get("requirements") or {}
        sufficiency = coverage.get("sufficiency") or {}
        search_log = coverage.get("search_log") or {}
        sources = (coverage.get("source_registry") or {}).get("sources", [])
        observations = (coverage.get("observations") or {}).get("observations", [])
        if not requirements:
            st.info("该历史运行尚未生成Data Requirements；不会从Markdown反向提取数据。")
            return

        with st.container(horizontal=True):
            st.metric("总体充分性", sufficiency.get("overall_status", "PENDING"), border=True)
            st.metric("来源", len(sources), border=True)
            st.metric("Observations", len(observations), border=True)
            st.metric("补搜轮次", sufficiency.get("gap_search_rounds_completed", 0), border=True)

        rows = []
        for item in sufficiency.get("datasets", []):
            completeness = item.get("field_completeness") or {}
            rows.append({
                "数据集": item.get("dataset_id"), "优先级": item.get("priority"),
                "状态": item.get("status"), "来源数": item.get("source_count", 0),
                "Observation": item.get("observation_count", 0), "覆盖企业": item.get("entity_count", 0),
                "覆盖年份": len(item.get("periods") or []),
                "最低字段完整率": min(completeness.values()) if completeness else 0,
                "可比率": "N/A" if item.get("comparability_rate") is None else f"{item['comparability_rate']:.0%}",
                "可生成图表": "、".join(name for name, ready in (item.get("dashboard_readiness") or {}).items() if ready) or "—",
                "缺口数": len(item.get("gaps") or []),
            })
        if rows:
            st.dataframe(
                rows, hide_index=True, key="data_coverage_table",
                column_config={
                    "最低字段完整率": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
                },
            )

        gaps = [{"数据集": dataset.get("dataset_id"), **gap} for dataset in sufficiency.get("datasets", []) for gap in dataset.get("gaps", [])]
        if gaps:
            st.markdown("#### 具体数据缺口")
            st.dataframe(gaps, hide_index=True, key="data_gap_table")
        stop_reason = sufficiency.get("search_stop_reason") or search_log.get("stop_reason")
        if stop_reason:
            st.caption(f"搜索停止原因：{stop_reason}")

        gap_queries = (coverage.get("gap_search_plan") or {}).get("queries") or []
        st.button(
            "自动补搜数据缺口", icon=":material/search:", type="primary",
            on_click=request_gap_search,
            disabled=(st.session_state.is_running or st.session_state.viewing_history or not gap_queries),
            help="只执行gap_search_plan中的查询，不会重跑完整Research。",
        )
        optional_gaps = [
            item for item in sufficiency.get("datasets", [])
            if item.get("priority") == "OPTIONAL" and item.get("status") != "PASS"
        ]
        st.button(
            "补充可选数据", icon=":material/add_chart:",
            on_click=request_optional_gap_search,
            disabled=(st.session_state.is_running or st.session_state.viewing_history or not optional_gaps),
            help="仅在用户主动选择时为OPTIONAL数据集生成并执行补搜计划；不会阻塞主要工作流。",
        )
        uploader = st.file_uploader(
            "本地Observation JSON（可选）", type=["json"], key="local_observation_upload",
            disabled=st.session_state.is_running or st.session_state.viewing_history,
            help="文件必须符合observations.json Schema；人工补充不是默认要求。",
        )
        if st.button(
            "补充本地数据", icon=":material/upload_file:",
            disabled=st.session_state.is_running or st.session_state.viewing_history or uploader is None,
        ):
            try:
                payload = json.loads(uploader.getvalue().decode("utf-8"))
                result = import_local_observations(output_folder, analysis_scope or {}, payload)
                st.success(f"已导入并去重；当前共有{len(result['observations'])}条Observation，充分性为{result['sufficiency'].get('overall_status')}。")
                st.rerun()
            except Exception as error:
                st.error(f"本地数据未导入：{safe_ui_error(error)}")


st.set_page_config(page_title="通用战略研究平台", page_icon="📊", layout="wide")
initialize_state()

with st.sidebar:
    st.subheader("导航")
    st.button(
        "当前分析",
        on_click=return_to_current_analysis,
        disabled=(
            st.session_state.is_running
            or not st.session_state.viewing_history
            or not st.session_state.current_analysis_snapshot
        ),
        width="stretch",
    )
    st.button(
        "新分析",
        on_click=start_new_analysis,
        disabled=st.session_state.is_running,
        width="stretch",
    )
    st.divider()
    st.subheader("历史分析")
    history_query = st.text_input(
        "按主题搜索",
        key="history_search",
        placeholder="输入主题关键词",
        disabled=st.session_state.is_running,
    ).strip().lower()
    history_runs = [
        run
        for run in list_run_manifests()
        if not history_query or history_query in str(run.get("topic", "")).lower()
    ]
    if not history_runs:
        st.caption("暂无匹配的历史运行。")
    else:
        for run in history_runs:
            created_at = str(run.get("created_at", "")).replace("T", " ")
            created_at = created_at[:19]
            history_status = run.get("final_status", "UNKNOWN")
            status_badge = HISTORY_STATUS_BADGES.get(history_status, "⚪")
            label = (
                f"{run.get('topic', '未命名')}\n"
                f"{created_at} · {status_badge} {history_status}"
            )
            st.button(
                label,
                key=f"history_{run.get('run_id')}",
                on_click=open_history_run,
                args=(run.get("run_id"),),
                disabled=st.session_state.is_running,
                width="stretch",
            )

st.title("通用行业与公司战略研究平台")
st.caption(
    "范围确认 → Research → Review → Fact Verification → 人工审核 → Strategy → 本地质量检查"
)

can_start = not st.session_state.is_running and st.session_state.workflow_phase in {
    NOT_STARTED,
    COMPLETED,
    FAILED,
}
input_left, input_right = st.columns(2)
with input_left:
    st.selectbox(
        "分析类型（analysis_type）*",
        ["公司战略", "产品战略", "行业分析", "竞品分析", "市场进入分析", "增长战略", "商业模式分析", "投资并购分析", "通用战略"],
        key="analysis_type_input",
        disabled=not can_start,
    )
    st.text_input(
        "分析对象（topic）*",
        key="topic_input",
        placeholder="例如：比亚迪、中国新能源汽车、瑞幸与星巴克",
        disabled=not can_start,
    )
    st.text_input(
        "分析地区（geography）*",
        key="geography_input",
        disabled=not can_start,
    )
    st.date_input(
        "报告基准日（analysis_date）*",
        key="analysis_date_input",
        disabled=not can_start,
    )
    st.text_input(
        "历史及预测时间范围（time_horizon）",
        key="time_horizon_input",
        placeholder="例如：2021–2030",
        disabled=not can_start,
    )
    st.selectbox(
        "分析深度（depth）",
        ["简版", "标准版", "深度版"],
        key="depth_input",
        disabled=not can_start,
    )
with input_right:
    st.checkbox(
        "缺少行业时自动判断",
        key="auto_industry_input",
        disabled=not can_start,
    )
    st.text_input(
        "所属行业（industry）",
        key="industry_input",
        placeholder="留空并勾选自动判断",
        disabled=not can_start or st.session_state.auto_industry_input,
    )
    st.text_input(
        "分析目的（objective）",
        key="objective_input",
        disabled=not can_start,
    )
    st.text_area(
        "重点问题（focus_questions）",
        key="focus_questions_input",
        height=90,
        disabled=not can_start,
    )
    st.text_area(
        "指定竞品（competitors，可选）",
        key="competitors_input",
        height=90,
        disabled=not can_start,
    )
    currency_col, language_col = st.columns(2)
    with currency_col:
        st.text_input(
            "主要货币（currency）",
            key="currency_input",
            placeholder="例如：CNY、USD",
            disabled=not can_start,
        )
    with language_col:
        st.text_input(
            "报告语言（language）",
            key="language_input",
            disabled=not can_start,
        )
st.button(
    "开始研究",
    type="primary",
    on_click=request_research,
    disabled=not can_start,
    width="stretch",
)

if st.session_state.analysis_scope:
    st.markdown("### 分析范围（Agent尚未运行）")
    st.json(st.session_state.analysis_scope)
    st.button(
        "确认研究范围",
        type="primary",
        on_click=request_scope_confirmation,
        disabled=(
            st.session_state.is_running
            or st.session_state.workflow_phase != SCOPE_PENDING
            or st.session_state.viewing_history
        ),
        width="stretch",
    )

stage_column, status_column = st.columns(2)
with stage_column:
    stage_metric = st.empty()
    stage_metric.metric("当前阶段", st.session_state.current_stage)
with status_column:
    phase_metric = st.empty()
    phase_metric.metric("工作流状态", st.session_state.workflow_phase)
message_panel = st.empty()
message_panel.info(st.session_state.status_message)

if st.session_state.pending_action:
    action_id = st.session_state.queued_action_id
    if st.session_state.executed_action_id != action_id:
        # 先消费动作。刷新或脚本重启不会再次执行同一组Agent调用。
        action = st.session_state.pending_action
        st.session_state.pending_action = None
        st.session_state.executed_action_id = action_id
        status_panel = st.status(st.session_state.status_message, expanded=True)

        def update_progress(stage, message):
            st.session_state.current_stage = stage
            st.session_state.status_message = message
            stage_metric.metric("当前阶段", stage)
            phase_metric.metric("工作流状态", st.session_state.workflow_phase)
            message_panel.info(message)
            status_panel.update(label=message, state="running", expanded=True)
            status_panel.write(message)

        try:
            if action == "prepare_scope":
                scope_inputs = {
                    "analysis_type": st.session_state.analysis_type_input,
                    "topic": st.session_state.topic,
                    "industry": (
                        "自动判断"
                        if st.session_state.auto_industry_input
                        else st.session_state.industry_input
                    ),
                    "geography": st.session_state.geography_input,
                    "analysis_date": st.session_state.analysis_date_input.isoformat(),
                    "time_horizon": st.session_state.time_horizon_input,
                    "objective": st.session_state.objective_input,
                    "focus_questions": st.session_state.focus_questions_input,
                    "competitors": st.session_state.competitors_input,
                    "depth": st.session_state.depth_input,
                    "currency": st.session_state.currency_input,
                    "language": st.session_state.language_input,
                }
                prepared = prepare_analysis_run(scope_inputs)
                st.session_state.output_folder = prepared["output_folder"]
                st.session_state.analysis_scope = prepared["scope"]
                st.session_state.scope_report = (
                    Path(prepared["output_folder"]) / "00_analysis_scope.json"
                ).read_text(encoding="utf-8")
                st.session_state.run_manifest = prepared["manifest"]
                st.session_state.workflow_files = {
                    "scope": Path(prepared["output_folder"]) / "00_analysis_scope.json"
                }
                st.session_state.workflow_phase = SCOPE_PENDING
                st.session_state.current_stage = SCOPE_PENDING
                st.session_state.status_message = (
                    "分析范围已在本地生成。确认范围后才会调用Agent。"
                )
            elif action in {"research", "reresearch"}:
                output_folder = st.session_state.output_folder
                result = run_research_phase(
                    st.session_state.topic,
                    human_feedback=(
                        st.session_state.human_feedback
                        if action == "reresearch"
                        else ""
                    ),
                    output_folder=output_folder,
                    progress_callback=update_progress,
                    analysis_scope=st.session_state.analysis_scope,
                )
                store_research_result(result)
                st.session_state.workflow_phase = AWAITING_APPROVAL
                st.session_state.current_stage = AWAITING_APPROVAL
                st.session_state.status_message = (
                    "前三个Agent已完成。请审核报告、填写人工补充意见并选择下一步。"
                )
            elif action == "strategy":
                result = run_strategy_phase(
                    research_result_from_state(),
                    human_feedback=st.session_state.human_feedback,
                    progress_callback=update_progress,
                )
                store_final_result(result)
                st.session_state.workflow_phase = COMPLETED
                st.session_state.current_stage = COMPLETED
                st.session_state.status_message = (
                    f"最终报告和本地质量检查已完成（{result['quality_status']}）。"
                )
            elif action == "revision_local":
                result = rerun_local_revision(
                    st.session_state.output_folder,
                    st.session_state.revision_request_input,
                )
                store_revision_result(result)
                st.session_state.status_message += " 本操作不消耗模型额度。"
            elif action == "revision_strategy":
                result = revise_strategy_report(
                    st.session_state.output_folder,
                    st.session_state.revision_request_input,
                    progress_callback=update_progress,
                )
                store_revision_result(result)
            elif action == "revision_research":
                result = run_revision_research_phase(
                    st.session_state.output_folder,
                    st.session_state.human_feedback,
                    progress_callback=update_progress,
                )
                store_research_result(result)
                st.session_state.workflow_phase = AWAITING_APPROVAL
                st.session_state.current_stage = AWAITING_APPROVAL
                st.session_state.status_message = (
                    "重新研究的前三阶段已完成。请人工审核后再运行Strategy和Quality Check。"
                )
            elif action == "gap_search":
                sufficiency = run_gap_search(
                    st.session_state.output_folder,
                    progress_callback=update_progress,
                )
                st.session_state.run_manifest = load_manifest(
                    st.session_state.output_folder
                )
                st.session_state.current_stage = "数据补搜完成"
                st.session_state.status_message = (
                    "定向补搜完成，当前数据充分性："
                    f"{sufficiency.get('overall_status', 'UNKNOWN')}。"
                )
            elif action == "optional_gap_search":
                sufficiency = run_gap_search(
                    st.session_state.output_folder,
                    progress_callback=update_progress,
                    include_optional=True,
                )
                st.session_state.run_manifest = load_manifest(
                    st.session_state.output_folder
                )
                st.session_state.current_stage = "可选数据补搜完成"
                st.session_state.status_message = (
                    "可选数据定向补搜完成；OPTIONAL不足不会改变主要工作流状态。"
                )

            status_panel.update(
                label=st.session_state.status_message,
                state="complete",
                expanded=False,
            )
        except WorkflowError as error:
            st.session_state.workflow_phase = FAILED
            st.session_state.current_stage = error.stage
            st.session_state.error_state = safe_ui_error(error)
            st.session_state.status_message = "工作流执行失败，已保留此前生成的文件。"
            manifest_path = Path(error.output_folder) / "run_manifest.json"
            if manifest_path.is_file():
                st.session_state.output_folder = Path(error.output_folder)
                st.session_state.run_manifest = load_manifest(error.output_folder)
                st.session_state.workflow_files = {
                    key: Path(error.output_folder) / filename
                    for key, filename in st.session_state.run_manifest.get(
                        "output_files", {}
                    ).items()
                    if key != "manifest"
                }
            status_panel.update(
                label=st.session_state.status_message,
                state="error",
                expanded=True,
            )
        except Exception as error:
            st.session_state.workflow_phase = FAILED
            st.session_state.current_stage = FAILED
            st.session_state.error_state = safe_ui_error(error)
            st.session_state.status_message = "工作流发生未预期错误。"
            status_panel.update(
                label=st.session_state.status_message,
                state="error",
                expanded=True,
            )
        finally:
            st.session_state.is_running = False

        st.rerun()
elif st.session_state.is_running:
    # 动作已消费但没有完成，说明页面刷新或脚本重启中断了调用；绝不自动重试。
    interrupted_stage = st.session_state.current_stage
    st.session_state.is_running = False
    st.session_state.workflow_phase = FAILED
    st.session_state.current_stage = interrupted_stage or FAILED
    st.session_state.status_message = "上一次运行被中断，未自动重复调用Agent。"
    st.session_state.error_state = st.session_state.status_message
    if st.session_state.output_folder:
        mark_manifest_failed(
            st.session_state.output_folder,
            interrupted_stage or FAILED,
            st.session_state.status_message,
        )
        manifest_path = Path(st.session_state.output_folder) / "run_manifest.json"
        if manifest_path.is_file():
            st.session_state.run_manifest = load_manifest(
                st.session_state.output_folder
            )

if st.session_state.error_state:
    st.error(st.session_state.error_state)

if st.session_state.output_folder:
    st.caption(f"输出目录：{st.session_state.output_folder}")
    manifest = st.session_state.run_manifest
    if manifest:
        summary_columns = st.columns(3)
        summary_columns[0].metric("主题", manifest.get("topic", ""))
        summary_columns[1].metric("创建时间", str(manifest.get("created_at", ""))[:19])
        summary_columns[2].metric("记录状态", manifest.get("final_status", "UNKNOWN"))
        try:
            zip_data = build_run_zip(st.session_state.output_folder)
            st.download_button(
                "下载完整结果ZIP",
                data=zip_data,
                file_name=f"{manifest.get('run_id', 'analysis')}.zip",
                mime="application/zip",
                disabled=st.session_state.is_running,
                width="stretch",
            )
        except Exception as error:
            st.warning(f"暂时无法创建ZIP：{safe_ui_error(error)}")

        st.markdown("### 各阶段耗时")
        duration_labels = {
            "data_requirements": "Data requirements",
            "data_acquisition": "Data acquisition",
            "data_sufficiency": "Data sufficiency",
            "gap_search": "Gap search",
            "research": "Research",
            "review": "Review",
            "fact_check": "Fact Check",
            "human_approval": "Human Approval",
            "strategy": "Strategy",
            "quality_check": "Quality Check",
        }
        durations = manifest.get("stage_durations_seconds") or {}
        st.table(
            [
                {
                    "阶段": label,
                    "耗时（秒）": round(float(durations.get(key, 0.0) or 0.0), 3),
                }
                for key, label in duration_labels.items()
            ]
        )

if revision_is_available() and not st.session_state.revision_center_open:
    st.button(
        "进入修订",
        type="primary",
        on_click=open_revision_center,
        disabled=st.session_state.is_running,
        width="stretch",
    )

if st.session_state.revision_center_open and revision_is_available():
    st.markdown("## 报告生成后修订中心")
    st.caption("这里独立于Strategy之前的人工审核；修订操作始终以最新报告为基础。")
    versions = list_revision_versions(st.session_state.output_folder)
    version_ids = [item["revision_id"] for item in versions]
    if version_ids:
        if st.session_state.revision_version_select not in version_ids:
            st.session_state.revision_version_select = version_ids[-1]
        st.selectbox(
            "当前报告版本",
            version_ids,
            key="revision_version_select",
            disabled=st.session_state.is_running,
        )
        selected_revision = load_revision_version(
            st.session_state.output_folder,
            st.session_state.revision_version_select,
        )
        revision_manifest = selected_revision["manifest"]
        version_columns = st.columns(3)
        version_columns[0].metric("版本", revision_manifest.get("revision_id", ""))
        version_columns[1].metric(
            "Quality Check",
            revision_manifest.get("quality_check_status", "UNKNOWN"),
        )
        version_columns[2].metric(
            "最终状态",
            revision_manifest.get("final_status", "UNKNOWN"),
        )
        with st.expander("当前报告内容", expanded=True):
            st.markdown(selected_revision["final"])
            st.divider()
            st.markdown("#### HTML 可视化看板")
            st.caption("基于当前报告版本生成独立 HTML；不会再次调用 Agent。")
            render_dashboard_html_action(
                st.session_state.output_folder,
                revision_manifest.get("revision_id"),
                title="Final Strategy Report · 可视化看板",
            )
        with st.expander("当前Quality Check结果", expanded=False):
            st.warning(QUALITY_DISCLAIMER)
            st.markdown(selected_revision["quality"])

        st.markdown("### quality_issues")
        issues = revision_manifest.get("quality_issues") or []
        if issues:
            st.dataframe(
                [
                    {
                        "severity": issue.get("severity"),
                        "rule_id": issue.get("rule_id"),
                        "rule_type": issue.get("rule_type"),
                        "文件": issue.get("file"),
                        "行号": issue.get("line_number", issue.get("line")),
                        "metric_id": issue.get("metric_id"),
                        "原文": issue.get("excerpt", issue.get("original")),
                        "缺失字段": "、".join(issue.get("missing_fields") or []),
                        "原因": issue.get("reason", issue.get("detail")),
                        "修改建议": issue.get("suggested_fix", issue.get("suggestion")),
                        "confidence": issue.get("confidence"),
                    }
                    for issue in issues
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.success("当前版本没有WARN或FAIL质量问题。")

    st.text_area(
        "我的修订要求",
        key="revision_request_input",
        height=150,
        placeholder="说明希望修复的问题、需要补充的来源或重新研究的指标。",
        disabled=st.session_state.is_running,
    )
    st.info("“仅重新运行本地检查”只调用validate_outputs()，不消耗模型额度。")
    local_column, strategy_column, research_column = st.columns(3)
    with local_column:
        st.button(
            "仅重新运行本地检查",
            on_click=request_local_revision,
            disabled=st.session_state.is_running,
            width="stretch",
        )
    with strategy_column:
        st.button(
            "让Strategy Agent修订报告",
            type="primary",
            on_click=request_strategy_revision,
            disabled=st.session_state.is_running,
            width="stretch",
        )
    with research_column:
        st.button(
            "根据问题重新研究",
            on_click=request_revision_research,
            disabled=st.session_state.is_running,
            width="stretch",
        )
    st.button(
        "返回报告",
        on_click=close_revision_center,
        disabled=st.session_state.is_running,
    )
    st.stop()

intermediate_ready = has_intermediate_reports()
st.markdown("### Revision Center / 人工审核")
feedback_disabled = (
    st.session_state.is_running
    or st.session_state.viewing_history
    or st.session_state.workflow_phase != AWAITING_APPROVAL
)
st.text_area(
    "人工补充意见",
    key="feedback_input",
    height=160,
    placeholder=(
        "可填写：需要补充的来源、需要删除的结论、需要重点分析的问题，"
        "以及对PARTIAL或UNSUPPORTED事实的处理要求。"
    ),
    disabled=feedback_disabled,
)

approve_column, rerun_column = st.columns(2)
approval_disabled = (
    st.session_state.is_running
    or st.session_state.viewing_history
    or st.session_state.workflow_phase != AWAITING_APPROVAL
    or not intermediate_ready
)
with approve_column:
    st.button(
        "批准并生成最终报告",
        type="primary",
        on_click=request_final_report,
        disabled=approval_disabled,
        width="stretch",
    )
with rerun_column:
    st.button(
        "根据意见重新研究",
        on_click=request_reresearch,
        disabled=approval_disabled,
        width="stretch",
    )

if st.session_state.workflow_files and st.session_state.workflow_files.get("feedback"):
    feedback_path = st.session_state.workflow_files["feedback"]
    saved_feedback = st.session_state.human_feedback_report or (
        "# 人工补充意见\n\n尚未提交人工补充意见。\n"
    )
    st.download_button(
        "下载 03_human_feedback.md",
        data=saved_feedback.encode("utf-8"),
        file_name=Path(feedback_path).name,
        mime="text/markdown",
        disabled=st.session_state.is_running,
    )

tab_labels = ["Analysis Scope", "Data Coverage", "Research Brief", "Review Notes", "Fact Check"]
show_complete_record = (
    st.session_state.viewing_history
    or st.session_state.workflow_phase == COMPLETED
)
display_final_report = st.session_state.final_report
display_quality_report = st.session_state.quality_report
display_quality_status = st.session_state.quality_status
display_dashboard_data = read_json_file(files.get("dashboard") if (files := (st.session_state.workflow_files or {})) else None)
display_revision_id = (st.session_state.run_manifest or {}).get("latest_revision")
if show_complete_record and st.session_state.viewing_history and st.session_state.output_folder:
    history_versions = list_revision_versions(st.session_state.output_folder)
    history_version_ids = [item["revision_id"] for item in history_versions]
    if history_version_ids:
        if st.session_state.revision_version_select not in history_version_ids:
            st.session_state.revision_version_select = history_version_ids[-1]
        st.selectbox(
            "历史报告版本",
            history_version_ids,
            key="revision_version_select",
            disabled=st.session_state.is_running,
        )
        history_revision = load_revision_version(
            st.session_state.output_folder,
            st.session_state.revision_version_select,
        )
        display_final_report = history_revision["final"]
        display_quality_report = history_revision["quality"]
        display_quality_status = history_revision["manifest"].get(
            "quality_check_status"
        )
        display_dashboard_data = history_revision.get("dashboard")
        display_revision_id = history_revision["manifest"].get("revision_id")
elif show_complete_record and st.session_state.output_folder:
    current_versions = list_revision_versions(st.session_state.output_folder)
    if current_versions:
        latest_revision = load_revision_version(
            st.session_state.output_folder, current_versions[-1].get("revision_id")
        )
        display_dashboard_data = latest_revision.get("dashboard") or display_dashboard_data
        display_revision_id = latest_revision["manifest"].get("revision_id")
if show_complete_record:
    tab_labels.extend(["Human Feedback", "Final Report", "Quality Check", "Dashboard"])
tabs = st.tabs(tab_labels)
files = st.session_state.workflow_files or {}
render_report_tab(
    tabs[0], st.session_state.scope_report, files.get("scope"), "Analysis Scope"
)
render_data_coverage(
    tabs[1], st.session_state.output_folder, st.session_state.analysis_scope
)
render_report_tab(
    tabs[2], st.session_state.research_report, files.get("research"), "Research Brief"
)
render_report_tab(
    tabs[3], st.session_state.review_report, files.get("review"), "Review Notes"
)
render_report_tab(
    tabs[4], st.session_state.fact_report, files.get("fact"), "Fact Verification Report"
)

if show_complete_record:
    if display_quality_status == "FAIL":
        st.error("本地质量检查结果为FAIL，请查看Quality Check并修正报告。")
    elif display_quality_status == "WARN":
        st.warning("本地质量检查结果为WARN，请进行人工复核。")
    else:
        if st.session_state.workflow_phase == COMPLETED:
            st.success("最终报告及本地质量检查已完成。")
    render_report_tab(
        tabs[5],
        st.session_state.human_feedback_report,
        files.get("feedback"),
        "Human Feedback",
    )
    render_report_tab(
        tabs[6],
        display_final_report,
        files.get("final"),
        "Final Strategy Report",
        dashboard_output_folder=st.session_state.output_folder,
        dashboard_revision_id=display_revision_id,
    )
    render_report_tab(
        tabs[7],
        display_quality_report,
        files.get("quality"),
        "Local Quality Check",
        disclaimer=QUALITY_DISCLAIMER,
    )
    render_dashboard(
        tabs[8],
        display_dashboard_data,
        st.session_state.output_folder,
        display_revision_id,
    )
