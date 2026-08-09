from .base import StageContract
from .validators import review_gate
CONTRACT = StageContract("review", ("research/claims.json",), "review_notes.schema.json", ("research_gate_passed",), ("sequential_ids", "required_fields"), ("range_id", "duplicate_id", "missing_action"), (), "STAGE_RETRY", ("fact_check", "human", "strategy", "report", "quality", "dashboard"), review_gate)
