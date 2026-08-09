from .base import StageContract
from .validators import scope_gate
CONTRACT = StageContract("scope", (), "scope.schema.json", ("draft_saved",), ("template_routed",), ("missing_scope",), (), "LOCAL_REPAIRABLE", ("data", "research", "review", "fact_check", "human", "strategy", "report", "dashboard", "quality"), scope_gate)
