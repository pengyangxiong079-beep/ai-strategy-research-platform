import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .analysis_types import normalize_analysis_type
from .registry import load_dashboard_template, prepare_components
from .schema import (
    ReportDataValidationError,
    validate_dashboard_data,
    validate_report_data,
)


DASHBOARD_SCHEMA_VERSION = "2.0"
QUALITY_STATUS_MAP = {
    "PASS": "READY",
    "WARN": "READY_WITH_GAPS",
    "FAIL": "BLOCKED_BY_QUALITY",
}
EXCLUDED_FACT_RESULTS = {"UNSUPPORTED", "SUPERSEDED", "OUTDATED"}
QUALITY_BLOCK_MESSAGE = "当前报告尚未通过质量检查，不应用于正式决策。"


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _quality_status(quality_file, manifest):
    if Path(quality_file).is_file():
        text = Path(quality_file).read_text(encoding="utf-8")
        for candidate in ("PASS", "WARN", "FAIL"):
            if (
                f"**{candidate}**" in text
                or f"总体结果：{candidate}" in text
                or f"Overall: {candidate}" in text
            ):
                return candidate
    status = str((manifest or {}).get("quality_check_status") or "").upper()
    if status in QUALITY_STATUS_MAP:
        return status
    return "UNKNOWN"


def _fact_map(fact_data):
    if isinstance(fact_data, list):
        records = fact_data
    elif isinstance(fact_data, dict):
        records = fact_data.get("facts", [])
    else:
        records = []
    return {
        str(item.get("fact_id", "")).upper(): item
        for item in records
        if isinstance(item, dict) and item.get("fact_id")
    }


def _metric_verification_status(results):
    if not results:
        return "NOT_CHECKED"
    if results <= {"VERIFIED", "SUPPORTED", "HISTORICAL"}:
        return "SUPPORTED"
    if "PARTIAL" in results:
        return "PARTIAL"
    if results & EXCLUDED_FACT_RESULTS:
        return "UNSUPPORTED"
    return "NOT_CHECKED"


def _metric_temporal_status(metric, section, analysis_date):
    value_type = str(metric.get("value_type") or "UNKNOWN").upper()
    period_match = re.search(r"(?:19|20)\d{2}", str(metric.get("period") or ""))
    analysis_match = re.search(r"(?:19|20)\d{2}", str(analysis_date or ""))
    if value_type in {"FORECAST", "TARGET", "SCENARIO"}:
        return "FUTURE_PLAN"
    if period_match and analysis_match:
        period_year = int(period_match.group())
        analysis_year = int(analysis_match.group())
        if period_year < analysis_year:
            return "HISTORICAL"
        if period_year > analysis_year:
            return "FUTURE_PLAN"
    if value_type in {"ACTUAL", "ESTIMATE"}:
        return "CURRENT"
    return "UNKNOWN"


def _filter_metric(metric, section, facts, analysis_date):
    metric = dict(metric)
    fact_ids = [str(item).upper() for item in metric.get("source_fact_ids", [])]
    referenced = [facts.get(fact_id) for fact_id in fact_ids]
    missing = [fact_id for fact_id, fact in zip(fact_ids, referenced) if fact is None]
    results = {str(fact.get("result", "")).upper() for fact in referenced if fact}
    verification_results = {
        "VERIFIED" if result == "HISTORICAL" else result for result in results
    }
    grades = {str(fact.get("source_grade", "N/A")).upper() for fact in referenced if fact}
    reasons = []
    if metric.get("value") is None:
        reasons.append("指标没有可展示的真实数值")
    if missing:
        reasons.append("不存在的Fact编号：" + "、".join(missing))
    blocked = sorted(verification_results & EXCLUDED_FACT_RESULTS)
    if blocked:
        reasons.append("引用了不可用于看板的Fact状态：" + "、".join(blocked))
    if metric.get("value_type") == "ACTUAL" and (
        not verification_results or verification_results != {"VERIFIED"}
    ):
        reasons.append("ACTUAL指标必须只引用VERIFIED事实")
    if "VERIFIED" in verification_results and grades.intersection({"D", "N/A", ""}):
        reasons.append("VERIFIED指标必须由A、B或可靠C级来源支持")
    if reasons:
        return None, reasons
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "N/A": 4, "": 4}
    if grades:
        metric["source_grade"] = max(grades, key=lambda item: grade_order.get(item, 4))
    if "PARTIAL" in results:
        metric["confidence"] = "LOW"
    metric["verification_status"] = _metric_verification_status(results)
    metric["temporal_status"] = _metric_temporal_status(
        metric, section, analysis_date
    )
    return metric, []


def _filter_report_data(report_data, facts, analysis_date=None):
    filtered = json.loads(json.dumps(report_data, ensure_ascii=False))
    excluded = []

    kept = []
    for metric in filtered.get("kpis", []):
        accepted, reasons = _filter_metric(metric, "kpis", facts, analysis_date)
        if accepted:
            kept.append(accepted)
        else:
            excluded.append({"section": "kpis", "metric_id": metric.get("metric_id"), "reasons": reasons})
    filtered["kpis"] = kept

    series_kept = []
    for series in filtered.get("time_series", []):
        points = []
        for metric in series.get("points", []):
            accepted, reasons = _filter_metric(
                metric, "time_series", facts, analysis_date
            )
            if accepted:
                points.append(accepted)
            else:
                excluded.append({"section": "time_series", "metric_id": metric.get("metric_id"), "reasons": reasons})
        if points:
            series["points"] = points
            series_kept.append(series)
    filtered["time_series"] = series_kept

    segment_kept = []
    for segment in filtered.get("market_segments", []):
        metrics = []
        for metric in segment.get("metrics", []):
            accepted, reasons = _filter_metric(
                metric, "market_segments", facts, analysis_date
            )
            if accepted:
                metrics.append(accepted)
            else:
                excluded.append({"section": "market_segments", "metric_id": metric.get("metric_id"), "reasons": reasons})
        if metrics:
            segment["metrics"] = metrics
            segment_kept.append(segment)
    filtered["market_segments"] = segment_kept

    comparisons = []
    for item in filtered.get("competitor_comparisons", []):
        fact_ids = [str(value).upper() for value in item.get("source_fact_ids", [])]
        referenced = [facts.get(fact_id) for fact_id in fact_ids]
        results = {
            str(fact.get("result", "")).upper() for fact in referenced if fact
        }
        missing = [fact_id for fact_id, fact in zip(fact_ids, referenced) if fact is None]
        reasons = []
        if missing:
            reasons.append("不存在的Fact编号：" + "、".join(missing))
        blocked = sorted(results & EXCLUDED_FACT_RESULTS)
        if blocked:
            reasons.append("引用了不可用于看板的Fact状态：" + "、".join(blocked))
        if reasons:
            excluded.append({"section": "competitor_comparisons", "metric_id": item.get("comparison_id"), "reasons": reasons})
        else:
            comparisons.append(item)
    filtered["competitor_comparisons"] = comparisons
    fact_results = [str(item.get("result", "")).upper() for item in facts.values()]
    filtered["evidence_summary"] = {
        "supported": (
            fact_results.count("VERIFIED")
            + fact_results.count("SUPPORTED")
            + fact_results.count("HISTORICAL")
        ),
        "partial": fact_results.count("PARTIAL"),
        "unsupported": fact_results.count("UNSUPPORTED"),
        "not_checked": fact_results.count("NOT_CHECKED"),
    }
    return filtered, excluded


def _failed_metric_ids(quality_data):
    failed = set()
    for issue in (quality_data or {}).get("quality_issues", []):
        if not isinstance(issue, dict) or not issue.get("metric_id"):
            continue
        severity = str(issue.get("severity") or issue.get("status") or "").upper()
        if severity in {"ERROR", "FAIL", "CRITICAL"}:
            failed.add(str(issue["metric_id"]))
    return failed


def _exclude_failed_fields(report_data, failed_metric_ids, excluded):
    if not failed_metric_ids:
        return report_data
    report_data = json.loads(json.dumps(report_data, ensure_ascii=False))

    def keep(metric, section):
        metric_id = str(metric.get("metric_id") or "")
        if metric_id not in failed_metric_ids:
            return True
        excluded.append(
            {
                "section": section,
                "metric_id": metric_id,
                "reasons": ["Quality Check将该字段标记为FAIL，已从主图排除"],
            }
        )
        return False

    report_data["kpis"] = [
        metric for metric in report_data.get("kpis", []) if keep(metric, "kpis")
    ]
    for series in report_data.get("time_series", []):
        series["points"] = [
            metric
            for metric in series.get("points", [])
            if keep(metric, "time_series")
        ]
    report_data["time_series"] = [
        series for series in report_data.get("time_series", []) if series.get("points")
    ]
    for segment in report_data.get("market_segments", []):
        segment["metrics"] = [
            metric
            for metric in segment.get("metrics", [])
            if keep(metric, "market_segments")
        ]
    report_data["market_segments"] = [
        segment
        for segment in report_data.get("market_segments", [])
        if segment.get("metrics")
    ]
    report_data["competitor_comparisons"] = [
        item
        for item in report_data.get("competitor_comparisons", [])
        if str(item.get("metric_id") or item.get("comparison_id") or "")
        not in failed_metric_ids
    ]
    return report_data


def _v2_metric(metric):
    metric = dict(metric)
    definition = str(metric.get("metric_definition") or metric.get("label") or "")
    group = metric.get("comparability_group") or "|".join(
        str(metric.get(key) or "")
        for key in (
            "geography", "period", "unit", "currency", "metric_definition",
            "channel_scope", "entity_scope",
        )
    )
    return {
        **metric,
        "metric_definition": definition,
        "verification_status": str(
            metric.get("verification_status") or "NOT_CHECKED"
        ).upper(),
        "temporal_status": str(metric.get("temporal_status") or "UNKNOWN").upper(),
        "comparability_group": str(group),
    }


def _v2_comparison(item):
    item = dict(item)
    issues = list(item.get("comparability_issues") or [])
    for field, label in (
        ("geography", "缺少统一地区"),
        ("period", "缺少统一期间"),
        ("unit", "缺少统一单位"),
        ("comparison_basis", "缺少比较口径"),
    ):
        if not item.get(field):
            issues.append(label)
    declared_comparable = bool(item.get("is_comparable", item.get("comparable", False)))
    if not declared_comparable and not issues:
        issues.append("报告声明该组数据口径不可直接比较")
    is_comparable = declared_comparable and not issues
    return {
        **item,
        "metric_id": str(item.get("metric_id") or item.get("comparison_id") or ""),
        "is_comparable": is_comparable,
        "comparable": is_comparable,
        "comparability_issues": list(dict.fromkeys(issues)),
    }


def _recommendation(item):
    return {
        **item,
        "recommendation_id": item.get("recommendation_id") or item.get("item_id"),
        "title": item.get("title") or item.get("label"),
        "rationale": item.get("rationale") or item.get("description") or "",
        "time_horizon": item.get("time_horizon") or item.get("timeframe"),
        "responsible_function": item.get("responsible_function") or item.get("owner"),
        "required_capabilities": item.get("required_capabilities") or [],
        "related_risks": item.get("related_risks") or [],
        "related_opportunities": item.get("related_opportunities") or [],
        "kpi": item.get("kpi"),
    }


def _v2_evidence(fact, analysis_date):
    result = str(fact.get("result") or "NOT_CHECKED").upper()
    if result in {"VERIFIED", "SUPPORTED", "HISTORICAL"}:
        verification = "SUPPORTED"
    elif result == "PARTIAL":
        verification = "PARTIAL"
    elif result in EXCLUDED_FACT_RESULTS:
        verification = "UNSUPPORTED"
    else:
        verification = "NOT_CHECKED"
    if result in {"SUPERSEDED", "OUTDATED"}:
        temporal = "SUPERSEDED"
    elif result == "HISTORICAL":
        temporal = "HISTORICAL"
    else:
        temporal = _metric_temporal_status(
            {"value_type": "ACTUAL", "period": fact.get("as_of_date")},
            "evidence",
            analysis_date,
        )
    return {
        **fact,
        "verification_status": verification,
        "temporal_status": temporal,
    }


def _revision_count(output_folder):
    revisions = Path(output_folder) / "revisions"
    if not revisions.is_dir():
        return 0
    return sum(
        1
        for path in revisions.iterdir()
        if path.is_dir() and re.fullmatch(r"rev_\d+", path.name) and path.name != "rev_000"
    )


def _v2_payload(
    *, output_folder, scope, manifest, report_version, quality, quality_data,
    status, filtered, excluded, components, industry_template_id, facts, data_folder,
):
    analysis_type = normalize_analysis_type(scope.get("analysis_type"))
    metrics = [_v2_metric(metric) for metric in filtered.get("kpis", [])]
    time_series = [
        {
            **series,
            "points": [_v2_metric(metric) for metric in series.get("points", [])],
        }
        for series in filtered.get("time_series", [])
    ]
    segments = [
        {
            **segment,
            "metrics": [_v2_metric(metric) for metric in segment.get("metrics", [])],
        }
        for segment in filtered.get("market_segments", [])
    ]
    comparisons = [
        _v2_comparison(item) for item in filtered.get("competitor_comparisons", [])
    ]
    normalized_report = {
        **filtered,
        "kpis": metrics,
        "time_series": time_series,
        "market_segments": segments,
        "competitor_comparisons": comparisons,
    }
    revision_id = report_version or manifest.get("latest_revision") or "current"
    data_root = Path(data_folder)
    observation_payload = _load_json(data_root / "observations.json", {"observations": []}) or {"observations": []}
    sufficiency_payload = _load_json(data_root / "sufficiency.json", {}) or {}
    dashboard_observations = [
        {
            **item,
            "dashboard_eligible": str(item.get("verification_status") or "").upper() in {"SUPPORTED", "PARTIAL"}
            and str(item.get("temporal_status") or "").upper() != "SUPERSEDED",
        }
        for item in observation_payload.get("observations", [])
    ]
    return {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "dashboard_status": status,
        "quality_status": quality,
        "warning": QUALITY_BLOCK_MESSAGE if quality == "FAIL" else "",
        "meta": {
            "analysis_type": analysis_type,
            "analysis_type_raw": scope.get("analysis_type"),
            "topic": scope.get("topic") or manifest.get("topic") or "",
            "industry": scope.get("industry"),
            "geography": scope.get("geography"),
            "analysis_date": scope.get("analysis_date"),
            "time_horizon": scope.get("time_horizon"),
            "run_id": manifest.get("run_id") or Path(output_folder).name,
            "workflow_status": manifest.get("final_status") or "UNKNOWN",
            "overall_quality_status": quality,
            "is_demo": False,
        },
        "executive_summary": {"conclusion": filtered.get("executive_summary") or ""},
        "metrics": metrics,
        "time_series": time_series,
        "comparisons": comparisons,
        "matrices": filtered.get("matrices") or [],
        "segments": segments,
        "geographies": filtered.get("geographies") or [],
        "risks": filtered.get("risks") or [],
        "opportunities": filtered.get("opportunities") or [],
        "strategic_options": filtered.get("strategic_options") or [],
        "recommendations": [
            _recommendation(item) for item in filtered.get("recommendations", [])
        ],
        "initiatives": filtered.get("initiatives") or filtered.get("roadmap") or [],
        "scenarios": filtered.get("scenarios") or [],
        "observations": dashboard_observations,
        "data_coverage": sufficiency_payload,
        "evidence": [
            _v2_evidence(fact, scope.get("analysis_date"))
            for fact in facts.values()
        ],
        "quality": {
            "overall_status": quality,
            "quality_issues": (quality_data or {}).get("quality_issues") or [],
            "excluded_fields": excluded,
        },
        "revision": {
            "revision_id": revision_id,
            "revision_count": _revision_count(output_folder),
        },
        # Compatibility fields retained for Streamlit and existing report history.
        "scope": scope,
        "report_version": revision_id,
        "template_id": analysis_type,
        "industry_template_id": industry_template_id,
        "components": components,
        "excluded_metrics": excluded,
        "validation_errors": [],
        "report_data": normalized_report,
    }


def _unavailable_payload(scope, manifest, errors):
    analysis_type = normalize_analysis_type((scope or {}).get("analysis_type"))
    payload = {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "dashboard_status": "UNAVAILABLE",
        "quality_status": str((manifest or {}).get("quality_check_status") or "UNKNOWN"),
        "warning": "",
        "scope": scope or {},
        "report_version": (manifest or {}).get("latest_revision") or "current",
        "template_id": analysis_type,
        "industry_template_id": (scope or {}).get("selected_template") or "general",
        "components": [],
        "excluded_metrics": [],
        "validation_errors": list(errors),
        "report_data": None,
        "meta": {
            "analysis_type": analysis_type,
            "analysis_type_raw": (scope or {}).get("analysis_type"),
            "topic": (scope or {}).get("topic") or (manifest or {}).get("topic") or "",
            "run_id": (manifest or {}).get("run_id") or "",
            "is_demo": False,
        },
        "executive_summary": {},
        "metrics": [],
        "time_series": [],
        "comparisons": [],
        "matrices": [],
        "segments": [],
        "geographies": [],
        "risks": [],
        "opportunities": [],
        "strategic_options": [],
        "recommendations": [],
        "initiatives": [],
        "scenarios": [],
        "observations": [],
        "data_coverage": {},
        "evidence": [],
        "quality": {
            "overall_status": str((manifest or {}).get("quality_check_status") or "UNKNOWN"),
            "quality_issues": [],
            "excluded_fields": [],
        },
        "revision": {
            "revision_id": (manifest or {}).get("latest_revision") or "current",
            "revision_count": 0,
        },
    }
    return payload


def compile_dashboard(output_folder, *, source_folder=None, report_version=None):
    """Compile trusted structured artifacts into 06_dashboard_data.json without a model."""
    output_folder = Path(output_folder)
    source_folder = Path(source_folder) if source_folder else output_folder
    scope = _load_json(output_folder / "00_analysis_scope.json", {}) or {}
    manifest = _load_json(output_folder / "run_manifest.json", {}) or {}
    report_data_path = source_folder / "04_report_data.json"
    dashboard_path = source_folder / "06_dashboard_data.json"
    try:
        report_data = _load_json(report_data_path)
        if report_data is None:
            raise ReportDataValidationError(["04_report_data.json不存在"])
        validate_report_data(report_data)
        final_path = source_folder / "04_final_report.md"
        expected_hash = (report_data.get("_meta") or {}).get("final_report_sha256")
        if expected_hash and final_path.is_file():
            current_hash = hashlib.sha256(final_path.read_bytes()).hexdigest()
            if current_hash != expected_hash:
                raise ReportDataValidationError(["04_report_data.json与当前Final Report版本不一致"])
        facts = _fact_map(_load_json(output_folder / "03_fact_check.json", {}) or {})
        filtered, excluded = _filter_report_data(
            report_data, facts, scope.get("analysis_date")
        )
        quality_data = _load_json(source_folder / "05_quality_check.json", {}) or {}
        filtered = _exclude_failed_fields(
            filtered, _failed_metric_ids(quality_data), excluded
        )
        quality = _quality_status(source_folder / "05_quality_check.md", manifest)
        status = QUALITY_STATUS_MAP.get(quality, "UNAVAILABLE")
        template = load_dashboard_template(scope.get("selected_template") or "general")
        components = prepare_components(filtered, template)
        payload = _v2_payload(
            output_folder=output_folder,
            scope=scope,
            manifest=manifest,
            report_version=report_version,
            quality=quality,
            quality_data=quality_data,
            status=status,
            filtered=filtered,
            excluded=excluded,
            components=components,
            industry_template_id=template.get("template_id", "general"),
            facts=facts,
            data_folder=(source_folder / "data" if (source_folder / "data").is_dir() else output_folder / "data"),
        )
        validate_dashboard_data(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ReportDataValidationError) as error:
        errors = getattr(error, "errors", None) or [str(error)]
        payload = _unavailable_payload(scope, manifest, errors)
        payload["report_version"] = report_version or manifest.get("latest_revision") or "current"
        payload["revision"]["revision_id"] = payload["report_version"]
    atomic_write_json(dashboard_path, payload)
    return payload
