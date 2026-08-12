"""File-backed acquisition pipeline. Dataset failures are isolated by design."""

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .data_requirements import build_requirements
from .normalization import (
    canonicalize_entity, dedupe_observations, dedupe_sources, is_valid_observation,
)
from .schemas import DataSchemaError, validate_payload
from .search import build_search_plan
from .sufficiency import build_gap_search_plan, evaluate_sufficiency
from pipeline_v2.ids import stable_id as v2_stable_id
from pipeline_v2.contracts import validate_stage as validate_v2_stage
from pipeline_v2.service import PipelineV2Service


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temp = Path(name)
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def data_files(output_folder):
    root = Path(output_folder) / "data"
    return {
        "root": root, "requirements": root / "requirements.json", "search_plan": root / "search_plan.json",
        "search_log": root / "search_log.json", "source_registry": root / "source_registry.json",
        "sources": root / "sources.json",
        "observations": root / "observations.json", "datasets": root / "datasets",
        "sufficiency": root / "sufficiency.json", "data_coverage": root / "data_coverage.json", "gap_search_plan": root / "gap_search_plan.json",
        "summary": root / "acquisition_summary.md",
    }


def initialize_data_pipeline(output_folder, scope):
    files = data_files(output_folder)
    files["datasets"].mkdir(parents=True, exist_ok=True)
    requirements = build_requirements(scope)
    validate_payload("requirements", requirements)
    search_plan = build_search_plan(scope, requirements)
    validate_payload("search_plan", search_plan)
    _write_json(files["requirements"], requirements)
    _write_json(files["search_plan"], search_plan)
    for key, payload in (("search_log", {"schema_version": "1.0", "entries": [], "rounds_completed": 0, "stop_reason": ""}), ("source_registry", {"schema_version": "1.0", "sources": []}), ("observations", {"schema_version": "1.0", "observations": []})):
        if not files[key].is_file():
            if key in {"search_log", "source_registry", "observations"}:
                validate_payload(key, payload)
            _write_json(files[key], payload)
    sufficiency = run_sufficiency_check(output_folder, scope)
    _write_json(files["sources"], _read(files["source_registry"], {"schema_version": "1.0", "sources": []}))
    return {"files": files, "requirements": requirements, "search_plan": search_plan, "sufficiency": sufficiency}


def parse_acquisition_response(text):
    match = re.search(r"<acquisition_json>\s*(.*?)\s*</acquisition_json>", str(text), re.I | re.S)
    research = re.search(r"<research_brief>\s*(.*?)\s*</research_brief>", str(text), re.I | re.S)
    if not match:
        return None, (research.group(1).strip() if research else str(text).strip())
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", match.group(1).strip(), flags=re.I)
    try:
        return json.loads(raw), (research.group(1).strip() if research else "")
    except (ValueError, TypeError):
        return None, (research.group(1).strip() if research else str(text).strip())


def _write_dataset_files(files, observations):
    grouped = {}
    for row in observations:
        grouped.setdefault(row.get("dataset_id") or "unclassified", []).append(row)
    for dataset_id, rows in grouped.items():
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", dataset_id)
        payload = {"schema_version": "1.0", "dataset_id": dataset_id, "observations": rows}
        validate_payload("observations", payload)
        _write_json(files["datasets"] / f"{safe_name}.json", payload)


def _reconcile_required_datasets(observations, requirements):
    requirement_ids = {
        item.get("dataset_id")
        for item in (requirements.get("datasets") or [])
        if item.get("dataset_id")
    }
    changed = False
    for row in observations:
        metric_dataset = str(row.get("metric_id") or "")
        if metric_dataset in requirement_ids and row.get("dataset_id") != metric_dataset:
            row["dataset_id"] = metric_dataset
            changed = True
    return changed


def process_acquisition_response(output_folder, scope, payload, *, is_gap=False, include_optional_gaps=False):
    files = data_files(output_folder)
    payload = dict(payload or {})
    try:
        search_round = int(payload.get("search_round", 0) or 0)
    except (TypeError, ValueError):
        search_round = 0
    payload = {
        "schema_version": "1.0",
        "search_round": max(0, min(3, search_round)),
        "sources": list(payload.get("sources") or []),
        "observations": list(payload.get("observations") or []),
        "search_log_entries": list(payload.get("search_log_entries") or []),
        "resolved_datasets": list(payload.get("resolved_datasets") or []),
        "remaining_gaps": list(payload.get("remaining_gaps") or []),
        "stop_reason": str(payload.get("stop_reason") or ""),
    }
    validate_payload("acquisition", payload)
    registry = _read(files["sources"], _read(files["source_registry"], {"schema_version": "1.0", "sources": []}))
    observation_file = _read(files["observations"], {"schema_version": "1.0", "observations": []})
    log = _read(files["search_log"], {"schema_version": "1.0", "entries": [], "rounds_completed": 0, "stop_reason": ""})
    search_plan = _read(files["search_plan"], {"budget": {}})
    budget = search_plan.get("budget") or {}
    max_sources = int(budget.get("max_source_pages", 25))
    max_queries = int(budget.get("max_queries", 16))
    remaining_sources = max(0, max_sources - len(registry.get("sources", [])))
    incoming_sources = (payload.get("sources") or [])[:remaining_sources] if isinstance(payload, dict) else []
    v2_enabled = (Path(output_folder) / "run_state.json").is_file()
    source_aliases = {}
    if v2_enabled:
        canonical_sources = []
        for raw_source in [*registry.get("sources", []), *incoming_sources]:
            raw_source = dict(raw_source)
            old_id = raw_source.get("source_id")
            new_id = old_id if str(old_id or "").startswith("SRC_") else v2_stable_id("source", raw_source.get("url"), raw_source.get("title"), raw_source.get("publisher"))
            if old_id:
                source_aliases[old_id] = new_id
            raw_source["source_id"] = new_id
            canonical_sources.append(raw_source)
        incoming_sources = canonical_sources[len(registry.get("sources", [])):]
        registry["sources"] = canonical_sources[:len(registry.get("sources", []))]
    sources = dedupe_sources([*registry.get("sources", []), *incoming_sources])
    incoming_observations = payload.get("observations") or [] if isinstance(payload, dict) else []
    combined_observations = [*observation_file.get("observations", []), *incoming_observations]
    if v2_enabled:
        combined_observations = [
            {**row, "source_id": source_aliases.get(row.get("source_id"), row.get("source_id")), "observation_id": None}
            for row in combined_observations
        ]
    normalized_observations = dedupe_observations(
        combined_observations,
        sources, scope.get("industry"),
    )
    # Agents occasionally place an Observation in a neighboring dataset even
    # though its normalized metric_id is exactly a required dataset ID (for
    # example industry_definition under market_segments). Reconcile this
    # deterministic one-to-one case before IDs and sufficiency are computed.
    _reconcile_required_datasets(
        normalized_observations, _read(files["requirements"], {})
    )
    if v2_enabled:
        for row in normalized_observations:
            row["observation_id"] = v2_stable_id(
                "observation", *[row.get(key) for key in ("dataset_id", "entity", "metric_id", "product_name", "value", "text_value", "unit", "currency", "period", "geography", "channel", "price_type", "source_id")]
            )
    topic_entity = re.split(r"在|进入|公司战略|的竞品|行业分析", str(scope.get("topic", "")), maxsplit=1)[0].strip()
    known_entities = [scope.get("target_entity") or topic_entity, *(scope.get("competitors") or [])]
    for row in normalized_observations:
        row["entity"] = canonicalize_entity(row.get("entity"), known_entities)
    source_ids = {item["source_id"] for item in sources}
    observations, rejected_reasons = [], []
    for row in normalized_observations:
        valid, reason = is_valid_observation(row, source_ids)
        if valid:
            observations.append(row)
        else:
            rejected_reasons.append(reason)
    rejected_observation_count = len(rejected_reasons)
    registry = {"schema_version": "1.0", "sources": sources}
    observation_file = {"schema_version": "1.0", "observations": observations}
    validate_payload("source_registry", registry)
    validate_payload("observations", observation_file)
    remaining_queries = max(0, max_queries - len(log.get("entries", [])))
    normalized_entries = []
    for index, raw in enumerate(((payload or {}).get("search_log_entries") or [])[:remaining_queries], 1):
        row = dict(raw)
        query_text = str(row.get("query_text") or row.get("query") or "")
        executed_at = row.get("executed_at")
        result_count = row.get("result_count")
        opened = list(row.get("opened_sources") or [])
        accepted = list(row.get("accepted_sources") or row.get("candidate_sources") or [])
        rejected = list(row.get("rejected_sources") or [])
        try:
            extracted_count = int(row.get("extracted_observation_count") or 0)
        except (TypeError, ValueError):
            extracted_count = 0
        execution_evidence = bool(opened or accepted or rejected or extracted_count)
        if execution_evidence and not executed_at:
            executed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        if execution_evidence and result_count is None:
            result_count = max(len(opened), len(accepted), len(rejected), extracted_count)
        normalized_entries.append({
            **row,
            "query_id": row.get("query_id") or f"Q_R{payload['search_round']}_{index:03d}",
            "gap_id": row.get("gap_id") or "",
            "query_text": query_text,
            "query": query_text,
            "language": row.get("language") or "unknown",
            "domain_filter": row.get("domain_filter") or "",
            "executed_at": executed_at,
            "result_count": result_count,
            "opened_sources": opened,
            "accepted_sources": accepted,
            "rejected_sources": rejected,
            "rejection_reasons": list(row.get("rejection_reasons") or []),
            "execution_status": "COMPLETED" if executed_at and result_count is not None else "PLANNED_NOT_EXECUTED",
        })
    log["entries"] = [*log.get("entries", []), *normalized_entries]
    if rejected_observation_count:
        reason_counts = {reason: rejected_reasons.count(reason) for reason in dict.fromkeys(rejected_reasons)}
        log["entries"].append({"round": int((payload or {}).get("search_round", 0)), "query_id": f"Q_SCHEMA_{len(log['entries']) + 1:03d}", "gap_id": "", "query_text": "LOCAL_SCHEMA_VALIDATION", "query": "LOCAL_SCHEMA_VALIDATION", "language": "N/A", "domain_filter": "", "executed_at": datetime.now().astimezone().isoformat(timespec="seconds"), "result_count": 0, "candidate_sources": [], "opened_sources": [], "accepted_sources": [], "rejected_sources": [], "rejection_reasons": [f"{count}条：{reason}" for reason, count in reason_counts.items()], "extracted_observation_count": 0, "remaining_gaps": [], "execution_status": "COMPLETED"})
    executed_this_round = any(row.get("execution_status") == "COMPLETED" for row in normalized_entries)
    if not is_gap or executed_this_round:
        log["rounds_completed"] = max(int(log.get("rounds_completed", 0)), int((payload or {}).get("search_round", 1)))
    log["stop_reason"] = str((payload or {}).get("stop_reason") or log.get("stop_reason") or "")
    validate_payload("search_log", log)
    _write_json(files["source_registry"], registry)
    _write_json(files["sources"], registry)
    _write_json(files["observations"], observation_file)
    _write_json(files["search_log"], log)
    _write_dataset_files(files, observations)
    gap_executed = bool(is_gap and executed_this_round)
    rounds = _read(files["sufficiency"], {}).get("gap_search_rounds_completed", 0) + (1 if gap_executed else 0)
    sufficiency = run_sufficiency_check(
        output_folder, scope, gap_rounds_completed=rounds,
        stop_reason=log["stop_reason"], include_optional_gaps=include_optional_gaps,
    )
    if v2_enabled:
        gate = validate_v2_stage(
            "data", {"observations": observations},
            {"sources": sources, "sufficiency": sufficiency},
        )
        PipelineV2Service(Path(output_folder).parent).record_gate_result(output_folder, "data", gate)
    return {"sources": sources, "observations": observations, "search_log": log, "sufficiency": sufficiency, "gap_executed": gap_executed}


def run_sufficiency_check(output_folder, scope, *, gap_rounds_completed=None, stop_reason=None, include_optional_gaps=False):
    files = data_files(output_folder)
    requirements = _read(files["requirements"], build_requirements(scope))
    observations = _read(files["observations"], {"observations": []}).get("observations", [])
    if _reconcile_required_datasets(observations, requirements):
        observation_payload = {"schema_version": "1.0", "observations": observations}
        validate_payload("observations", observation_payload)
        _write_json(files["observations"], observation_payload)
        _write_dataset_files(files, observations)
    sources = _read(files["sources"], _read(files["source_registry"], {"sources": []})).get("sources", [])
    previous = _read(files["sufficiency"], {})
    result = evaluate_sufficiency(requirements, observations, sources, scope, gap_rounds_completed=(previous.get("gap_search_rounds_completed", 0) if gap_rounds_completed is None else gap_rounds_completed), stop_reason=(previous.get("search_stop_reason", "") if stop_reason is None else stop_reason))
    validate_payload("sufficiency", result)
    search_plan = _read(files["search_plan"], build_search_plan(scope, requirements))
    gap_plan = build_gap_search_plan(result, search_plan, include_optional=include_optional_gaps)
    validate_payload("gap_search_plan", gap_plan)
    _write_json(files["sufficiency"], result)
    _write_json(files["data_coverage"], result)
    _write_json(files["gap_search_plan"], gap_plan)
    _write_summary(files["summary"], result, sources, observations)
    return result


def _write_summary(path, sufficiency, sources, observations):
    lines = ["# 数据采集摘要", "", f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}", f"- 总体状态：{sufficiency.get('overall_status')}", f"- 来源数量：{len(sources)}", f"- Observation数量：{len(observations)}", f"- Gap Search轮次：{sufficiency.get('gap_search_rounds_completed', 0)}", f"- 停止原因：{sufficiency.get('search_stop_reason') or '尚未达到停止条件'}", "", "## 数据集覆盖", ""]
    for item in sufficiency.get("datasets", []):
        comparability = "N/A" if item.get("comparability_rate") is None else f"{item['comparability_rate']:.0%}"
        lines.append(f"- {item['dataset_id']} [{item['priority']} / {item['status']}]：{item['observation_count']}条，{item['entity_count']}个实体，可比率{comparability}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_data_coverage(output_folder):
    files = data_files(output_folder)
    return {key: _read(path, None) for key, path in files.items() if key not in {"root", "datasets", "summary"}}


def import_local_observations(output_folder, scope, payload):
    if isinstance(payload, list):
        payload = {"schema_version": "1.0", "observations": payload}
    validate_payload("observations", payload)
    return process_acquisition_response(output_folder, scope, {"sources": [], "observations": payload["observations"], "search_log_entries": [], "search_round": 0, "stop_reason": "本地数据已导入"})


def apply_observation_verification(output_folder, verification_rows):
    files = data_files(output_folder)
    payload = _read(files["observations"], {"schema_version": "1.0", "observations": []})
    grouped = {}
    for verdict in verification_rows:
        observation_id = str(verdict.get("observation_id") or "")
        if observation_id:
            grouped.setdefault(observation_id, []).append(verdict)
    for row in payload["observations"]:
        verdicts = grouped.get(row.get("observation_id"), [])
        if not verdicts:
            continue
        normalized_results = [
            {"VERIFIED": "SUPPORTED", "HISTORICAL": "SUPPORTED", "SUPPORTED": "SUPPORTED", "PARTIAL": "PARTIAL", "UNSUPPORTED": "UNSUPPORTED", "OUTDATED": "UNSUPPORTED", "SUPERSEDED": "UNSUPPORTED"}.get(
                str(verdict.get("verification_status") or verdict.get("result") or "NOT_CHECKED").upper(),
                "NOT_CHECKED",
            )
            for verdict in verdicts
        ]
        if "UNSUPPORTED" in normalized_results:
            row["verification_status"] = "UNSUPPORTED"
        elif "PARTIAL" in normalized_results:
            row["verification_status"] = "PARTIAL"
        elif "SUPPORTED" in normalized_results:
            row["verification_status"] = "SUPPORTED"
        else:
            row["verification_status"] = "NOT_CHECKED"
        fact_ids = [verdict.get("fact_id") for verdict in verdicts if verdict.get("fact_id")]
        row["source_fact_ids"] = list(dict.fromkeys([*(row.get("source_fact_ids") or []), *fact_ids]))
        temporal_values = [verdict.get("temporal_status") for verdict in verdicts if verdict.get("temporal_status")]
        if temporal_values:
            row["temporal_status"] = temporal_values[-1]
        grades = [str(verdict.get("source_grade") or "").upper() for verdict in verdicts]
        grade_order = {"GRADE_A": 0, "GRADE_B": 1, "GRADE_C": 2, "GRADE_D": 3, "GRADE_E": 4, "UNKNOWN": 5, "": 5}
        if grades:
            row["source_grade"] = min(grades, key=lambda value: grade_order.get(value, 5))
    validate_payload("observations", payload)
    _write_json(files["observations"], payload)
    _write_dataset_files(files, payload["observations"])
    return payload
