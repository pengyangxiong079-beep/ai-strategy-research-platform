from .base import StageContract
from .validators import human_gate
CONTRACT = StageContract("human", ("fact_check/verified_claims.json",), "feedback.schema.json", ("fact_check_complete",), ("feedback_stable_id",), ("feedback_missing_id",), (), "HUMAN_REQUIRED", ("strategy", "report", "dashboard", "quality"), human_gate)
