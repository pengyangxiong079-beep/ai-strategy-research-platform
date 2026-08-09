from .base import StageContract
from .validators import strategy_gate
CONTRACT = StageContract("strategy", ("fact_check/verified_claims.json", "human/feedback.json"), "recommendations.schema.json", ("human_resolved",), ("recommendations_traceable",), ("unsupported_used",), (), "STAGE_RETRY", ("report", "dashboard", "quality"), strategy_gate)
