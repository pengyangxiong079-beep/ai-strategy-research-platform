"""Canonical Fact Check normalization across claim and observation ledgers."""

from __future__ import annotations

from collections import defaultdict


STATUS_RANK = {"SUPPORTED": 1, "PARTIAL": 2, "NOT_CHECKED": 3, "UNSUPPORTED": 4}
VALID_STATUSES = set(STATUS_RANK)


def _status(value):
    normalized = str(value or "NOT_CHECKED").strip().upper()
    return normalized if normalized in VALID_STATUSES else "NOT_CHECKED"


def _conservative_status(values):
    rows = [_status(value) for value in values]
    return max(rows, key=lambda value: STATUS_RANK[value]) if rows else "NOT_CHECKED"


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def normalize_fact_check(artifact, research_claims, observations, sources):
    """Return claim verification plus a complete Observation verification ledger.

    Live agents have returned both claim-centric and observation-centric records.
    This function accepts either representation and deterministically fills only
    bookkeeping fields. Missing verification remains ``NOT_CHECKED``.
    """
    if isinstance(artifact, list):
        rows = artifact
        explicit_claims = [row for row in rows if isinstance(row, dict) and row.get("claim_id")]
        explicit_observations = [
            row for row in rows
            if isinstance(row, dict) and row.get("observation_id") and not row.get("claim_id")
        ]
    elif isinstance(artifact, dict):
        explicit_claims = artifact.get("claims") if isinstance(artifact.get("claims"), list) else []
        explicit_observations = artifact.get("observation_verifications")
        if not isinstance(explicit_observations, list):
            explicit_observations = artifact.get("verification_records")
        if not isinstance(explicit_observations, list):
            explicit_observations = []
    else:
        explicit_claims, explicit_observations = [], []

    research_map = {
        row.get("claim_id"): row for row in research_claims
        if isinstance(row, dict) and row.get("claim_id")
    }
    source_map = {
        row.get("source_id"): row for row in sources
        if isinstance(row, dict) and row.get("source_id")
    }
    by_claim = defaultdict(list)
    by_observation = defaultdict(list)
    for row in explicit_observations:
        if not isinstance(row, dict):
            continue
        if row.get("observation_id"):
            by_observation[row["observation_id"]].append(row)
        for claim_id in row.get("claim_ids") or []:
            by_claim[claim_id].append(row)
    for row in explicit_claims:
        if not isinstance(row, dict):
            continue
        if row.get("claim_id"):
            by_claim[row["claim_id"]].append(row)
        for observation_id in row.get("observation_ids") or []:
            by_observation[observation_id].append(row)

    claims = []
    all_claim_ids = list(research_map)
    all_claim_ids.extend(
        row.get("claim_id") for row in explicit_claims
        if isinstance(row, dict) and row.get("claim_id") not in research_map
    )
    for claim_id in _unique(all_claim_ids):
        base = dict(research_map.get(claim_id) or {})
        records = by_claim.get(claim_id, [])
        explicit = next((row for row in explicit_claims if row.get("claim_id") == claim_id), {})
        observation_ids = _unique([
            *(explicit.get("observation_ids") or base.get("observation_ids") or []),
            *(row.get("observation_id") for row in records),
        ])
        # A claim-centric response is authoritative: an explicitly empty
        # source_ids array must still fail the SUPPORTED-source gate.  For an
        # observation-centric response, map its verified sources and retain
        # the already-linked research sources as deterministic bookkeeping.
        source_ids = _unique([
            *(explicit.get("source_ids") or []),
            *(value for row in records for value in (row.get("source_ids") or [])),
            *((base.get("source_ids") or []) if not explicit else []),
        ])
        grades = [
            source_map[source_id].get("source_grade") for source_id in source_ids
            if source_id in source_map
        ]
        grades = [value for value in grades if value]
        claims.append({
            **base,
            **explicit,
            "claim_id": claim_id,
            "text": explicit.get("text") or base.get("text") or base.get("statement") or "",
            "observation_ids": observation_ids,
            "source_ids": source_ids,
            "verification_status": _conservative_status(
                [row.get("verification_status") for row in records]
                or [explicit.get("verification_status")]
            ),
            "temporal_status": explicit.get("temporal_status") or next(
                (row.get("temporal_status") for row in records if row.get("temporal_status")),
                base.get("temporal_status") or "UNKNOWN",
            ),
            "source_grade_max": explicit.get("source_grade_max") or (sorted(grades)[0] if grades else None),
            "status": explicit.get("status") or base.get("status") or "ACTIVE",
        })

    normalized_claim_map = {row["claim_id"]: row for row in claims}
    ledger = []
    for observation in observations:
        observation_id = observation.get("observation_id")
        if not observation_id:
            continue
        records = by_observation.get(observation_id, [])
        linked_claim_ids = _unique([
            *(value for row in records for value in (row.get("claim_ids") or [])),
            *(row["claim_id"] for row in claims if observation_id in row.get("observation_ids", [])),
        ])
        linked_claims = [normalized_claim_map[value] for value in linked_claim_ids if value in normalized_claim_map]
        statuses = [row.get("verification_status") for row in records]
        if not statuses:
            statuses = [row.get("verification_status") for row in linked_claims]
        ledger.append({
            "observation_id": observation_id,
            "claim_ids": linked_claim_ids,
            "verification_status": _conservative_status(statuses),
            "temporal_status": next(
                (row.get("temporal_status") for row in records if row.get("temporal_status")),
                observation.get("temporal_status") or "UNKNOWN",
            ),
            "source_ids": _unique([
                *(value for row in records for value in (row.get("source_ids") or [])),
                *(value for row in linked_claims for value in (row.get("source_ids") or [])),
                observation.get("source_id"),
            ]),
        })
    return {"claims": claims, "observation_verifications": ledger}
