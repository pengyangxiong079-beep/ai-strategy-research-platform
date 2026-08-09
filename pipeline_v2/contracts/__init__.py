"""Stage-contract registry."""

from .dashboard_contract import CONTRACT as DASHBOARD
from .data_contract import CONTRACT as DATA
from .fact_check_contract import CONTRACT as FACT_CHECK
from .human_contract import CONTRACT as HUMAN
from .report_contract import CONTRACT as REPORT
from .research_contract import CONTRACT as RESEARCH
from .review_contract import CONTRACT as REVIEW
from .scope_contract import CONTRACT as SCOPE
from .strategy_contract import CONTRACT as STRATEGY

REGISTRY = {contract.stage: contract for contract in (SCOPE, DATA, RESEARCH, REVIEW, FACT_CHECK, HUMAN, STRATEGY, REPORT, DASHBOARD)}


def validate_stage(stage, payload, context=None):
    return REGISTRY[stage].validate(payload, context or {})

