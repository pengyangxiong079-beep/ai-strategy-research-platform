from .base import StageContract
from .validators import report_gate
CONTRACT = StageContract("report", ("strategy/recommendations.json", "research/claims.json"), "report_model.schema.json", ("strategy_gate_passed",), ("renderable",), ("missing_section", "unlinked_fact"), (), "LOCAL_REPAIRABLE", ("dashboard", "quality"), report_gate)
