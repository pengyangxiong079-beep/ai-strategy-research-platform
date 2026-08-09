from .base import StageContract
from .validators import research_gate
CONTRACT = StageContract("research", ("data/observations.json", "data/source_registry.json"), "claims.schema.json", ("data_gate_passed",), ("facts_atomic",), ("fact_without_source", "non_atomic"), (), "STAGE_RETRY", ("review", "fact_check", "human", "strategy", "report", "dashboard", "quality"), research_gate)
