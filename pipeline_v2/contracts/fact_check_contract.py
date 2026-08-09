from .base import StageContract
from .validators import fact_check_gate
CONTRACT = StageContract("fact_check", ("research/claims.json", "data/sources.json", "data/observations.json", "02_review_notes.json"), "verified_claims.schema.json", ("review_gate_passed",), ("supported_has_source", "observation_lineage"), ("verified_without_source", "missing_observation"), (), "UPSTREAM_DATA_REQUIRED", ("strategy", "report", "quality", "dashboard"), fact_check_gate)
