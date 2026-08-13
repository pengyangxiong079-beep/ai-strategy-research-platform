"""Build self-contained HTML dashboard snapshots for one strategy report run."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


SENSITIVE_KEY = re.compile(
    r"token|cookie|authorization|credential|secret|password|thread.?id|environment|account",
    re.IGNORECASE,
)


class DashboardExportError(RuntimeError):
    """Raised when a report cannot be exported as an offline dashboard."""


def _read_json(path: Path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return fallback


def _sanitize(value):
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if not SENSITIVE_KEY.search(str(key))
        }
    return value


def _safe_json(value) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _revision_candidates(output_folder: Path):
    revisions_root = output_folder / "revisions"
    revisions = (
        sorted(
            path
            for path in revisions_root.iterdir()
            if path.is_dir() and re.fullmatch(r"rev_\d+", path.name)
        )
        if revisions_root.is_dir()
        else []
    )
    if revisions:
        return [(path.name, path) for path in revisions]
    return [("current", output_folder)]


def _report_bundle(
    output_folder: Path,
    source_folder: Path,
    revision: str,
    revision_count: int,
    run_manifest: dict,
    scope: dict,
):
    dashboard = _read_json(source_folder / "06_dashboard_data.json")
    if not isinstance(dashboard, dict):
        return None
    if not dashboard.get("report_data"):
        # Pipeline V2 originally emitted canonical dashboard fields without
        # the legacy-compatible report_data view required by the web client.
        # Adapt structured JSON only; never extract values from Markdown.
        from pipeline_v2.report_protocol import dashboard_report_data, normalize_strategic_items

        report_data = _read_json(source_folder / "04_report_data.json", {})
        claims = _read_json(source_folder / "fact_check/verified_claims.json", {}).get("claims", [])
        report_model = _read_json(source_folder / "strategy/report_model.json", {})
        if not isinstance(report_data, dict) or not report_data:
            return None
        report_data = dict(report_data)
        if not report_data.get("risks"):
            report_data["risks"] = normalize_strategic_items(report_model, claims, "risks")
        if not report_data.get("opportunities"):
            report_data["opportunities"] = normalize_strategic_items(report_model, claims, "opportunities")
        compatible = dashboard_report_data(scope, report_data, claims)
        dashboard = {
            **dashboard,
            "quality_status": dashboard.get("quality_status") or "UNKNOWN",
            "scope": compatible["scope"],
            "report_version": revision,
            "template_id": compatible["scope"]["analysis_type"],
            "industry_template_id": compatible["scope"].get("selected_template") or "general",
            "components": dashboard.get("components", []),
            "excluded_metrics": dashboard.get("excluded_metrics", []),
            "validation_errors": dashboard.get("validation_errors", []),
            "risks": compatible["risks"],
            "opportunities": compatible["opportunities"],
            "report_data": compatible,
        }

    revision_manifest = (
        None
        if revision == "current"
        else _read_json(source_folder / "revision_manifest.json", {})
    )
    quality_data = _read_json(source_folder / "05_quality_check.json", {})
    quality_status = (
        quality_data.get("overall_status")
        or (revision_manifest or {}).get("quality_check_status")
        or dashboard.get("quality_status")
        or run_manifest.get("quality_check_status")
        or "UNKNOWN"
    )
    dashboard = dict(dashboard)
    dashboard["quality_status"] = quality_status
    return _sanitize(
        {
            "schema_version": "1.0",
            "run_id": run_manifest.get("run_id") or output_folder.name,
            "revision": revision,
            "revision_count": revision_count,
            "scope": scope,
            "run_manifest": run_manifest,
            "revision_manifest": revision_manifest,
            "quality": {
                "overall_status": quality_status,
                "quality_issues": quality_data.get("quality_issues")
                or (revision_manifest or {}).get("quality_issues")
                or run_manifest.get("quality_issues")
                or [],
            },
            "dashboard": dashboard,
        }
    )


def generate_dashboard_html(output_folder, revision_id=None, *, web_root=None) -> Path:
    """Generate one offline HTML file with data for every revision in the run."""
    output_folder = Path(output_folder).resolve()
    web_root = (
        Path(web_root).resolve()
        if web_root
        else Path(__file__).resolve().parents[1] / "dashboard-web"
    )
    base_html_path = web_root / "dist" / "index.html"
    if not base_html_path.is_file():
        raise DashboardExportError(
            "看板前端尚未构建；请先在 dashboard-web 目录运行 npm run build。"
        )

    run_manifest = _read_json(output_folder / "run_manifest.json", {})
    scope = _read_json(output_folder / "00_analysis_scope.json", {})
    candidates = _revision_candidates(output_folder)
    bundles = []
    for revision, source_folder in candidates:
        bundle = _report_bundle(
            output_folder,
            source_folder,
            revision,
            len(candidates),
            run_manifest,
            scope,
        )
        if bundle:
            bundles.append((revision, source_folder, bundle))

    if not bundles:
        raise DashboardExportError("当前报告没有可用于 HTML 看板的结构化数据。")

    available_revisions = [revision for revision, _, _ in bundles]
    selected_revision = str(revision_id) if revision_id else available_revisions[-1]
    if selected_revision not in available_revisions:
        selected_revision = available_revisions[-1]
    run_id = str(run_manifest.get("run_id") or output_folder.name)
    catalog_entries = []
    report_bundles = {}
    for revision, _, bundle in bundles:
        report_bundles[f"{run_id}::{revision}"] = bundle
        revision_manifest = bundle.get("revision_manifest") or {}
        catalog_entries.append(
            {
                "run_id": run_id,
                "topic": run_manifest.get("topic") or scope.get("topic") or output_folder.name,
                "revision": revision,
                "revision_count": sum(revision != "rev_000" for revision, _, _ in bundles),
                "quality_status": bundle["quality"]["overall_status"],
                "final_status": revision_manifest.get("final_status")
                or run_manifest.get("final_status")
                or "UNKNOWN",
                "analysis_date": scope.get("analysis_date")
                or run_manifest.get("analysis_date")
                or "",
                "industry": scope.get("industry") or run_manifest.get("industry") or "",
                "geography": scope.get("geography")
                or run_manifest.get("geography")
                or "",
                "data_url": "./data/embedded.json",
            }
        )

    embedded = {
        "catalog": {
            "schema_version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "reports": catalog_entries,
        },
        "reports": report_bundles,
        "selected_key": f"{run_id}::{selected_revision}",
    }
    embedded_script = (
        '<script id="dashboard-embedded-data" type="application/json">'
        f"{_safe_json(embedded)}</script>"
    )
    base_html = base_html_path.read_text(encoding="utf-8")
    if "</head>" not in base_html:
        raise DashboardExportError("看板前端构建产物无效：缺少 </head>。")
    html = base_html.replace("</head>", f"{embedded_script}</head>", 1)

    source_folder = next(
        folder for revision, folder, _ in bundles if revision == selected_revision
    )
    destination = source_folder / "dashboard" / "dashboard.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".html.tmp")
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(destination)

    if selected_revision == available_revisions[-1]:
        latest_destination = output_folder / "dashboard" / "dashboard.html"
        if latest_destination != destination:
            latest_destination.parent.mkdir(parents=True, exist_ok=True)
            latest_temporary = latest_destination.with_suffix(".html.tmp")
            latest_temporary.write_text(html, encoding="utf-8")
            latest_temporary.replace(latest_destination)
    return destination
