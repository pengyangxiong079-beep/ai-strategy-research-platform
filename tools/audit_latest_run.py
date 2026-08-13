"""Offline integrity audit for the latest canonical strategy research run.

Usage: python -m tools.audit_latest_run --run latest --revision latest --offline --report
Exit codes: 0 PASS, 1 WARN_ONLY, 2 DETERMINISTIC_FAIL, 3 INCOMPLETE_RUN, 4 TOOL_ERROR.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path
import re
import sys

from pipeline_v2.quality import aggregate_root_causes
from pipeline_v2.review import validate_review_notes


EXIT_PASS, EXIT_WARN, EXIT_FAIL, EXIT_INCOMPLETE, EXIT_TOOL_ERROR = range(5)
REQUIRED_RUN_FILES = (
    "00_analysis_scope.json", "01_research_brief.md", "03_fact_check.json",
    "04_final_report.md", "04_report_data.json", "05_quality_check.json",
    "06_dashboard_data.json", "run_manifest.json",
)
FACT_TAG = re.compile(r"【\s*事实(?:\s*[｜|]\s*F\d+)?\s*】")
RANGE_REVIEW = re.compile(r"R\d+\s*(?:-|–|—|~|至)\s*R?\d+", re.I)


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {} if default is None else default


def _timestamp(manifest):
    value = manifest.get("updated_at") or manifest.get("completed_at") or manifest.get("created_at") or ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _complete(folder: Path):
    missing = [name for name in REQUIRED_RUN_FILES if not (folder / name).is_file()]
    if not ((folder / "02_review_notes.json").is_file() or (folder / "02_review_notes.md").is_file()):
        missing.append("02_review_notes.json|md")
    return not missing, missing


def _repository_root(run_folder: Path):
    """Resolve the repository independently of outputs/example nesting depth."""
    for candidate in (run_folder, *run_folder.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").is_file():
            return candidate
    return run_folder.parents[1]


def discover_runs(outputs_root: Path):
    rows = []
    for manifest_path in outputs_root.rglob("run_manifest.json") if outputs_root.is_dir() else []:
        # A revision manifest is named differently; nested copied run manifests are ignored.
        if "revisions" in manifest_path.parts:
            continue
        manifest = _json(manifest_path, {})
        if not manifest:
            continue
        complete, missing = _complete(manifest_path.parent)
        rows.append({"folder": manifest_path.parent, "manifest": manifest, "timestamp": _timestamp(manifest), "complete": complete, "missing": missing})
    return sorted(rows, key=lambda row: (row["timestamp"], str(row["folder"])), reverse=True)


def select_run(rows, requested="latest"):
    if not rows:
        raise FileNotFoundError("No outputs/**/run_manifest.json found")
    latest = rows[0]
    if requested != "latest":
        matches = [row for row in rows if row["manifest"].get("run_id") == requested or row["folder"].name == requested]
        if not matches:
            raise FileNotFoundError(f"Run not found: {requested}")
        selected = matches[0]
        return selected, selected if not selected["complete"] else None
    if latest["complete"]:
        return latest, None
    completed = next((row for row in rows if row["complete"]), None)
    if completed is None:
        return latest, latest
    return completed, latest


def select_revision(run_folder: Path, manifest: dict, requested="latest"):
    revisions = run_folder / "revisions"
    if requested in {None, "current"}:
        return "current", run_folder
    revision_id = manifest.get("latest_revision") if requested == "latest" else requested
    if revision_id and (revisions / revision_id).is_dir():
        return revision_id, revisions / revision_id
    return "current", run_folder


def _walk_values(value, key):
    found = []
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key and isinstance(child, list):
                found.extend(child)
            found.extend(_walk_values(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_values(child, key))
    return found


def _periods_from_series(series):
    values = set()
    for item in series or []:
        for point in item.get("points", []) if isinstance(item, dict) else []:
            if isinstance(point, dict) and point.get("period"):
                values.add(str(point["period"]))
    return values


def _issue(rule_id, reason, artifact, *, priority="P0", severity="ERROR", pointer="/", repair_type="STAGE_RETRY", classification="deterministic real error", affected=None):
    return {
        "rule_id": rule_id, "stage": "audit", "priority": priority,
        "severity": severity, "reason": reason, "artifact": artifact,
        "location": pointer, "json_pointer": pointer,
        "repair_type": repair_type, "classification": classification,
        "affected_items": list(affected or []), "resolved": False,
    }


def _fact_rows(payload):
    return payload.get("facts") or payload.get("claims") or []


def _fact_id(row):
    return str(row.get("fact_id") or row.get("display_id") or "")


def audit_run(run_row, revision_id, source_folder: Path, incomplete_latest=None):
    root = run_row["folder"]
    manifest = run_row["manifest"]
    scope = _json(root / "00_analysis_scope.json", {})
    final_path = source_folder / "04_final_report.md"
    final_text = final_path.read_text(encoding="utf-8") if final_path.is_file() else ""
    review_path = next((path for path in (source_folder / "02_review_notes.json", root / "02_review_notes.json", source_folder / "review/review_notes.json") if path.is_file()), None)
    fact = _json(source_folder / "03_fact_check.json", _json(root / "03_fact_check.json", {}))
    report = _json(source_folder / "04_report_data.json", {})
    quality = _json(source_folder / "quality/summary.json", {})
    if not quality:
        quality = _json(source_folder / "05_quality_check.json", {})
    dashboard = _json(source_folder / "06_dashboard_data.json", {})
    observations = _json(source_folder / "data/observations.json", _json(root / "data/observations.json", {"observations": []})).get("observations", [])
    sources = _json(source_folder / "data/sources.json", _json(root / "data/sources.json", _json(root / "data/source_registry.json", {"sources": []}))).get("sources", [])
    coverage = _json(source_folder / "data/data_coverage.json", _json(root / "data/data_coverage.json", _json(root / "data/sufficiency.json", {})))
    search_log = _json(source_folder / "data/search_log.json", _json(root / "data/search_log.json", {"entries": []}))
    gap_plan = _json(source_folder / "data/gap_search_plan.json", _json(root / "data/gap_search_plan.json", {"queries": []}))
    issues = []
    run_state = _json(source_folder / "run_state.json", _json(root / "run_state.json", {}))

    for field in ("analysis_type", "industry", "geography", "analysis_date", "time_horizon", "selected_template", "required_sections"):
        if not scope.get(field):
            issues.append(_issue("SCOPE_REQUIRED_FIELD", f"Scope missing {field}", "00_analysis_scope.json", pointer=f"/{field}"))
    for field in ("focus_questions", "competitors"):
        if not isinstance(scope.get(field, []), list):
            issues.append(_issue("SCOPE_LIST_TYPE", f"{field} must be an array", "00_analysis_scope.json", pointer=f"/{field}"))
    competitors = scope.get("competitors") or []
    if len(competitors) == 1 and re.search(r"[,，;；]", str(competitors[0])):
        issues.append(_issue("SCOPE_COMPETITORS_MERGED", "Competitors appear merged into one punctuation-delimited string", "00_analysis_scope.json", priority="P1", pointer="/competitors"))

    if review_path is None:
        issues.append(_issue("REVIEW_CANONICAL_JSON_MISSING", "Canonical 02_review_notes.json is missing; Markdown cannot be promoted to source of truth", "02_review_notes.json", repair_type="REQUIRES_LIVE_RERUN"))
        review_ids = set()
    else:
        notes = _json(review_path, {}).get("issues", [])
        for row in validate_review_notes(notes):
            issues.append(_issue(row["rule_id"], row["reason"], str(review_path.relative_to(source_folder if review_path.is_relative_to(source_folder) else root)), pointer=row["location"]))
        review_ids = {row.get("review_id") for row in notes}
    referenced_reviews = set(re.findall(r"\bR\d+\b", final_text))
    if referenced_reviews - review_ids:
        issues.append(_issue("FINAL_UNKNOWN_REVIEW_ID", "Final references Review IDs absent from canonical Review JSON", "04_final_report.md", affected=sorted(referenced_reviews - review_ids), repair_type="REQUIRES_LIVE_RERUN"))

    facts = _fact_rows(fact)
    ids = [_fact_id(row) for row in facts if _fact_id(row)]
    if len(ids) != len(set(ids)):
        issues.append(_issue("FACT_ID_DUPLICATE", "Fact IDs are not unique", "03_fact_check.json", pointer="/facts"))
    numeric = [int(match.group(1)) for value in ids if (match := re.fullmatch(r"F(\d+)", value))]
    if numeric and sorted(numeric) != list(range(1, max(numeric) + 1)):
        issues.append(_issue("FACT_ID_SEQUENCE", "Fact IDs are not a continuous F1…Fn sequence", "03_fact_check.json", pointer="/facts"))
    allowed_results = {"VERIFIED", "PARTIAL", "UNSUPPORTED", "OUTDATED", "SUPPORTED", "NOT_CHECKED", "HISTORICAL", "SUPERSEDED"}
    for index, row in enumerate(facts):
        result = str(row.get("result") or row.get("verification_status") or "").upper()
        if result not in allowed_results:
            issues.append(_issue("FACT_RESULT_INVALID", f"Unsupported Fact result: {result or 'EMPTY'}", "03_fact_check.json", pointer=f"/facts/{index}/result"))
        if result == "OUTDATED" and not row.get("corrected_claim"):
            issues.append(_issue("FACT_OUTDATED_CORRECTION", "OUTDATED fact must include corrected_claim", "03_fact_check.json", pointer=f"/facts/{index}/corrected_claim"))
    if "【事实" in final_text and not FACT_TAG.search(final_text):
        issues.append(_issue("FACT_TAG_PROTOCOL", "Final contains a fact-like tag that the canonical parser cannot recognize", "04_final_report.md"))

    canonical_obs_ids = {str(row.get("observation_id")) for row in observations if row.get("observation_id")}
    coverage_count = coverage.get("observation_count")
    fact_obs_ids = {str(row.get("observation_id")) for row in fact.get("observation_verifications", []) if row.get("observation_id")}
    report_obs_ids = {str(value) for value in _walk_values(report, "source_observation_ids") + (report.get("_meta", {}).get("observation_ids") or []) if value}
    dashboard_obs_ids = {str(row.get("observation_id")) for row in dashboard.get("observations", []) if isinstance(row, dict) and row.get("observation_id")}
    dashboard_obs_ids.update(str(value) for value in _walk_values(dashboard, "source_observation_ids") if value)
    for label, count, artifact in (
        ("Coverage", coverage_count, "data/data_coverage.json"),
        ("Fact Check", len(fact_obs_ids), "03_fact_check.json"),
        ("Report Data", len(report_obs_ids), "04_report_data.json"),
        ("Dashboard", len(dashboard_obs_ids), "06_dashboard_data.json"),
    ):
        if count is None or int(count) != len(canonical_obs_ids):
            issues.append(_issue("OBSERVATION_LINEAGE_COUNT_MISMATCH", f"{label} Observation count {count} != canonical count {len(canonical_obs_ids)}", artifact, pointer="/observation_count" if label == "Coverage" else "/"))
    source_ids = {row.get("source_id") for row in sources}
    for index, row in enumerate(observations):
        if not row.get("source_id") or row.get("source_id") not in source_ids:
            issues.append(_issue("OBSERVATION_SOURCE_MISSING", "Observation cannot resolve to Source Registry", "data/observations.json", pointer=f"/observations/{index}/source_id"))

    coverage_periods = {str(period) for item in coverage.get("datasets", []) for period in item.get("periods", []) if period}
    report_periods = _periods_from_series(report.get("time_series", []))
    exclusions = {str(row.get("period")) for row in (report.get("_meta", {}).get("time_series_exclusions") or []) if row.get("period") and row.get("exclusion_reason")}
    unexplained = sorted(coverage_periods - report_periods - exclusions)
    if unexplained:
        issues.append(_issue("TIME_SERIES_PERIOD_TRUNCATION", "Coverage periods are absent from Report Data without exclusion_reason", "04_report_data.json", affected=unexplained))

    has_three_scenarios = all(term in final_text for term in ("保守", "基准", "乐观"))
    if has_three_scenarios and len(report.get("scenarios", [])) < 3:
        issues.append(_issue("REPORT_SCENARIOS_MISSING", "Final contains three scenarios but Report Data has fewer than three structured scenarios", "04_report_data.json", pointer="/scenarios"))
    if has_three_scenarios and len(dashboard.get("scenarios", [])) < 3:
        issues.append(_issue("DASHBOARD_SCENARIOS_MISSING", "Final contains three scenarios but Dashboard has fewer than three structured scenarios", "06_dashboard_data.json", pointer="/scenarios"))
    for artifact, rows in (("04_report_data.json", report.get("scenarios", [])), ("06_dashboard_data.json", dashboard.get("scenarios", []))):
        for index, row in enumerate(rows):
            if row.get("value_type") not in {"MODELLED", "QUALITATIVE"}:
                issues.append(_issue("SCENARIO_VALUE_TYPE", "Scenario value_type must be MODELLED or QUALITATIVE", artifact, pointer=f"/scenarios/{index}/value_type"))

    expected_hash = (report.get("meta") or report.get("_meta") or {}).get("final_report_sha256")
    actual_hash = hashlib.sha256(final_path.read_bytes()).hexdigest() if final_path.is_file() else ""
    if not expected_hash or expected_hash != actual_hash:
        issues.append(_issue("REPORT_HASH_MISMATCH", "Report Data hash does not match the actual Final Report file bytes", "04_report_data.json", pointer="/_meta/final_report_sha256"))

    rounds = int(coverage.get("gap_search_rounds_completed", 0) or 0)
    executed = [row for row in search_log.get("entries", []) if row.get("execution_status") == "COMPLETED" or (row.get("executed_at") and row.get("result_count") is not None)]
    valid_executed = [row for row in executed if row.get("executed_at") and row.get("result_count") is not None and row.get("opened_sources")]
    if rounds > len(valid_executed):
        issues.append(_issue("GAP_SEARCH_FALSE_COMPLETION", "Gap Search is marked completed without query execution and opened source logs", "data/search_log.json", priority="P1", pointer="/entries"))
    for index, query in enumerate(gap_plan.get("queries", [])):
        text = str(query.get("query_text") or query.get("query") or "")
        if re.search(r"annual report\s+\d{4}\s+[\"']?[a-z0-9_]+", text, re.I) and str(scope.get("topic") or "") in text:
            issues.append(_issue("GAP_QUERY_MECHANICAL", "Gap query contains the full topic plus annual report and dataset identifier", "data/gap_search_plan.json", priority="P1", pointer=f"/queries/{index}"))

    quality_status = str(
        quality.get("status") or quality.get("overall_status")
        or manifest.get("quality_check_status") or "UNKNOWN"
    ).upper()
    dashboard_status = str(dashboard.get("dashboard_status") or "UNKNOWN").upper()
    if quality_status == "FAIL" and dashboard_status not in {"BLOCKED_BY_QUALITY", "UNAVAILABLE"}:
        issues.append(_issue("DASHBOARD_QUALITY_STATUS", "Quality FAIL must not produce a READY dashboard", "06_dashboard_data.json", pointer="/dashboard_status"))
    if quality_status in {"PASS", "WARN", "PASS_WITH_WARNINGS"} and dashboard_status == "BLOCKED_BY_QUALITY":
        issues.append(_issue("DASHBOARD_QUALITY_STATUS", "Passing Quality must not leave Dashboard blocked", "06_dashboard_data.json", pointer="/dashboard_status"))
    for index, component in enumerate(dashboard.get("components", [])):
        if component.get("status") == "READY" and str(component.get("reason") or "").strip():
            issues.append(_issue("DASHBOARD_READY_WITH_MISSING_REASON", "READY component cannot also carry a missing-data reason", "06_dashboard_data.json", priority="P1", pointer=f"/components/{index}/reason"))
    if dashboard.get("derived_from_markdown"):
        issues.append(_issue("DASHBOARD_MARKDOWN_EXTRACTION", "Dashboard must use structured JSON, not Markdown number extraction", "06_dashboard_data.json"))

    revision_manifest = _json(source_folder / "revision_manifest.json", {}) if revision_id not in {"current", "rev_000"} else {}
    required_revision = ("status", "revision_type", "parent_revision", "rerun_stages", "preserved_stages", "invalidated_artifacts", "input_hashes", "output_hashes", "started_at", "completed_at", "error_message")
    if revision_manifest:
        missing = [field for field in required_revision if field not in revision_manifest]
        if missing:
            issues.append(_issue("REVISION_MANIFEST_FIELDS", "Revision Manifest is missing required V2 fields", str((source_folder / "revision_manifest.json").relative_to(root)), affected=missing))

    for q in quality.get("quality_issues", quality.get("issues", [])):
        if str(q.get("status") or "").upper() == "WARN" and q.get("severity") == "ERROR":
            issues.append(_issue("QUALITY_SEVERITY_CONFLICT", "WARN issue cannot carry ERROR severity", "05_quality_check.json", priority="P2", severity="WARNING", classification="parser false positive"))

    repository_root = _repository_root(root)
    secret_scan = scan_repository(repository_root)
    required_public = ("README.md", ".gitignore", ".env.example", "CONTRIBUTING.md", "SECURITY.md", ".github/workflows/offline-ci.yml")
    missing_public = [name for name in required_public if not (repository_root / name).is_file()]
    git_repository = (repository_root / ".git").exists()
    license_present = any((repository_root / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"))
    github_ready = not missing_public and not secret_scan["findings"] and not secret_scan["large_files"] and git_repository and license_present
    github_readiness = {
        "status": "READY" if github_ready else "PARTIAL",
        "missing_files": missing_public,
        "secret_scan": secret_scan,
        "git_repository": git_repository,
        "license_present": license_present,
    }
    if missing_public:
        issues.append(_issue("GITHUB_FILES_MISSING", "Public repository files are missing", "repository", priority="P2", severity="WARNING", repair_type="LOCAL_REPAIRABLE", affected=missing_public))

    if incomplete_latest and incomplete_latest.get("folder") == root:
        # Missing downstream artifacts are an expected consequence of a gate
        # stopping the run. Diagnose the blocking stage instead of manufacturing
        # lineage/hash root causes for files that do not exist yet.
        missing = set(incomplete_latest.get("missing") or [])
        issues = [
            row for row in issues
            if row.get("artifact") == "repository"
            or (row.get("artifact") not in missing and (source_folder / str(row.get("artifact"))).exists())
        ]
        canonical_issues = _json(
            source_folder / "quality/issues.json",
            _json(root / "quality/issues.json", {"issues": []}),
        ).get("issues", [])
        issues.extend(canonical_issues)
        current_stage = run_state.get("current_stage") or manifest.get("current_stage") or "unknown"
        overall = run_state.get("overall_status") or manifest.get("final_status") or "INCOMPLETE"
        blocked_on_data = current_stage == "data" and overall == "BLOCKED_DATA"
        awaiting_human = current_stage == "human" and overall == "AWAITING_HUMAN_REVIEW"
        issues.append(_issue(
            "RUN_INCOMPLETE_AT_GATE",
            f"Run stopped at {current_stage} with status {overall}",
            "run_state.json" if run_state else "run_manifest.json",
            pointer=f"/stages/{current_stage}" if run_state else "/current_stage",
            repair_type=(
                "REQUIRES_LIVE_RERUN" if blocked_on_data
                else "HUMAN_REQUIRED" if awaiting_human
                else "STAGE_RETRY"
            ),
        ))

    roots = aggregate_root_causes(issues)
    status = "DETERMINISTIC_FAIL" if any(row["severity"] == "ERROR" for row in issues) else ("WARN_ONLY" if issues else "PASS")
    if incomplete_latest:
        status = "INCOMPLETE_RUN"
    selected = {"path": str(root.resolve()), "run_id": manifest.get("run_id"), "report_version": dashboard.get("report_version") or revision_id, "manifest_latest_revision": manifest.get("latest_revision"), "selection_basis": "highest parsed updated_at among runs with the required artifact chain"}
    return {
        "schema_version": "1.0", "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "OFFLINE", "selected_run": selected, "selected_revision": revision_id,
        "incomplete_latest_run": ({
            "path": str(incomplete_latest["folder"].resolve()),
            "run_id": incomplete_latest["manifest"].get("run_id"),
            "missing": incomplete_latest["missing"],
            "current_stage": (_json(incomplete_latest["folder"] / "run_state.json", {}).get("current_stage") or incomplete_latest["manifest"].get("current_stage")),
            "overall_status": (_json(incomplete_latest["folder"] / "run_state.json", {}).get("overall_status") or incomplete_latest["manifest"].get("final_status")),
        } if incomplete_latest else None),
        "overall_status": status, "root_causes": roots, "raw_issues": issues,
        "affected_artifacts": sorted({row["artifact"] for row in issues}),
        "automatic_fixes": ["Generated deterministic audit reports; original outputs were not modified."],
        "remaining_gaps": [row for row in issues if row.get("repair_type") == "REQUIRES_LIVE_RERUN"],
        "lineage_counts": {"coverage": coverage_count, "canonical_observations": len(canonical_obs_ids), "fact_check": len(fact_obs_ids), "report_data": len(report_obs_ids), "dashboard": len(dashboard_obs_ids)},
        "hashes": {"final_report_expected": expected_hash, "final_report_actual_bytes": actual_hash},
        "test_results": {
            "audit_execution": "PASS",
            "run_discovery": "PASS",
            "offline_mode": "PASS",
            "external_test_suites": "NOT_RUN_BY_AUDIT_COMMAND"
        },
        "github_readiness": github_readiness,
    }


def scan_repository(repo: Path):
    patterns = [
        ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
        ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
        ("PERSONAL_WINDOWS_PATH", re.compile(r"(?i)C:\\Users\\(?!<user>|username|user\\)[^\\\s]+\\")),
    ]
    excluded = {".git", ".venv", "node_modules", "outputs", "dist", ".pytest_cache", "audit", "__pycache__"}
    findings = []
    files = []
    # A release scan should cover exactly what Git can publish: tracked files
    # plus unignored untracked files.  This avoids recursively walking local
    # caches and generated workspaces that are outside the release surface.
    if (repo / ".git").exists():
        try:
            completed = subprocess.run(
                ["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                check=True, capture_output=True, timeout=30,
            )
            files = [repo / value.decode("utf-8", errors="surrogateescape") for value in completed.stdout.split(b"\0") if value]
        except (OSError, subprocess.SubprocessError):
            files = []
    if not files:
        for current, directory_names, file_names in os.walk(repo):
            directory_names[:] = [name for name in directory_names if name not in excluded]
            files.extend(Path(current) / name for name in file_names)
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 2_000_000:
            continue
        try:
            # Avoid Windows universal-newline translation, which is extremely
            # slow for minified bundles containing very long lines.
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, pattern in patterns:
            for match in pattern.finditer(text):
                findings.append({"rule_id": name, "file": str(path.relative_to(repo)), "line": text.count("\n", 0, match.start()) + 1})
    large_files = []
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 10_000_000:
            large_files.append({"file": str(path.relative_to(repo)), "bytes": size})
    return {"status": "PASS" if not findings else "FAIL", "findings": findings, "large_files": large_files}


def render_markdown(payload):
    run = payload["selected_run"]
    lines = ["# Latest run audit", "", f"- Status: **{payload['overall_status']}**", f"- Run: `{run['run_id']}`", f"- Path: `{run['path']}`", f"- Revision: `{payload['selected_revision']}`", f"- Report version: `{run['report_version']}`", f"- Selection: {run['selection_basis']}", "", "## Lineage counts", "", "| Coverage | Canonical | Fact Check | Report Data | Dashboard |", "|---:|---:|---:|---:|---:|", f"| {payload['lineage_counts']['coverage']} | {payload['lineage_counts']['canonical_observations']} | {payload['lineage_counts']['fact_check']} | {payload['lineage_counts']['report_data']} | {payload['lineage_counts']['dashboard']} |", "", "## Root causes", ""]
    if not payload["root_causes"]:
        lines.append("No issues found.")
    for row in payload["root_causes"]:
        lines.extend([f"### {row['root_cause_id']} · {row['rule_id']}", "", f"- Stage: {row['stage']}", f"- Cause: {row['root_cause']}", f"- Affected items: {len(row['affected_items'])}", f"- Recommended action: {row['recommended_action']}", ""])
    lines.extend(["## GitHub readiness", "", f"- Status: {payload['github_readiness']['status']}", f"- Git repository present: {payload['github_readiness']['git_repository']}", f"- Secret scan: {payload['github_readiness']['secret_scan']['status']}", ""])
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="latest")
    parser.add_argument("--revision", default="latest")
    parser.add_argument("--fix", action="store_true", help="Apply safe deterministic derived-artifact fixes only")
    parser.add_argument("--offline", action="store_true", default=True)
    parser.add_argument("--report", action="store_true", help="Write audit/latest_run_audit.json and .md")
    parser.add_argument("--outputs-root", default="outputs")
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        rows = discover_runs(Path(args.outputs_root))
        run_row, incomplete = select_run(rows, args.run)
        revision_id, source_folder = select_revision(run_row["folder"], run_row["manifest"], args.revision)
        selected_state = _json(source_folder / "run_state.json", {})
        if (
            revision_id not in {"current", "rev_000"}
            and selected_state.get("overall_status") in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
        ):
            incomplete = None
        payload = audit_run(run_row, revision_id, source_folder, incomplete)
        report_dir = Path("audit")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "latest_run_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (report_dir / "latest_run_audit.md").write_text(render_markdown(payload) + "\n", encoding="utf-8")
        print(json.dumps({"status": payload["overall_status"], "run_id": payload["selected_run"]["run_id"], "revision": revision_id, "issues": len(payload["raw_issues"]), "report": str((report_dir / 'latest_run_audit.json').resolve())}, ensure_ascii=False))
        return {"PASS": EXIT_PASS, "WARN_ONLY": EXIT_WARN, "DETERMINISTIC_FAIL": EXIT_FAIL, "INCOMPLETE_RUN": EXIT_INCOMPLETE}.get(payload["overall_status"], EXIT_TOOL_ERROR)
    except Exception as error:
        print(json.dumps({"status": "TOOL_ERROR", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_TOOL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
