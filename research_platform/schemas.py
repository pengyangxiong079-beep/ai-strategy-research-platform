"""Local JSON Schema validation for data acquisition artifacts."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMA_FILES = {
    "requirements": "requirements.schema.json",
    "observations": "observations.schema.json",
    "source_registry": "source_registry.schema.json",
    "sufficiency": "sufficiency.schema.json",
    "search_plan": "search_plan.schema.json",
    "search_log": "search_log.schema.json",
    "gap_search_plan": "gap_search_plan.schema.json",
    "acquisition": "acquisition.schema.json",
}


class DataSchemaError(ValueError):
    def __init__(self, kind, errors):
        self.kind = kind
        self.errors = errors
        super().__init__(f"{kind} schema validation failed: " + "; ".join(errors))


def load_schema(kind):
    return json.loads((SCHEMA_DIR / SCHEMA_FILES[kind]).read_text(encoding="utf-8"))


def validate_payload(kind, payload):
    candidate = payload
    # Compatibility input is upgraded before validation; canonical persisted
    # observations always contain the full V2 lineage/scope fields.
    if kind == "observations" and isinstance(payload, dict):
        from .normalization import normalize_observation
        rows = payload.get("observations")
        if isinstance(rows, list):
            candidate = {**payload, "observations": [
                normalize_observation(row) if isinstance(row, dict) and all(row.get(key) for key in ("dataset_id", "entity", "metric", "source_id")) else row
                for row in rows
            ]}
    validator = Draft202012Validator(load_schema(kind))
    errors = [
        f"{'/'.join(map(str, error.path)) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(candidate), key=lambda item: list(item.path))
    ]
    if errors:
        raise DataSchemaError(kind, errors)
    return payload
