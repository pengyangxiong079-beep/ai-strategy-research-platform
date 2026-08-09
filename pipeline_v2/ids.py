"""Stable content-derived identities; display numbering is intentionally separate."""

from __future__ import annotations

import json
import uuid

NAMESPACE = uuid.UUID("2cdcc2c0-19c2-53a6-a619-e7e1fb77db31")
PREFIXES = {
    "source": "SRC", "observation": "OBS", "claim": "CLM", "review": "REV",
    "feedback": "HFB", "recommendation": "REC", "metric": "MET", "decision": "DEC",
}


def stable_id(kind: str, *identity_parts) -> str:
    """Return the same opaque ID for the same canonical identity inputs."""
    prefix = PREFIXES[kind]
    canonical = json.dumps(identity_parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{uuid.uuid5(NAMESPACE, canonical).hex}"


def assign_display_ids(items, prefix: str):
    """Assign presentation-only sequential IDs without changing stable identities."""
    return [{**item, "display_id": item.get("display_id") or f"{prefix}{index}"} for index, item in enumerate(items, 1)]

