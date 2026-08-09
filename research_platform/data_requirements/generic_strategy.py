from .types import COMMON_FALLBACK, COMMON_PRIMARY, requirement

REQUIREMENTS = (
    requirement("scope_evidence", "CRITICAL", "验证研究范围、对象和关键定义", primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK),
    requirement("decision_metrics", "CRITICAL", "回答重点问题所需的关键指标", periods=2, primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK, proxy=True),
    requirement("stakeholders", "IMPORTANT", "识别关键参与者和利益相关方", proxy=True),
    requirement("risks", "IMPORTANT", "识别可验证风险和触发条件", proxy=True),
    requirement("opportunities", "IMPORTANT", "识别可验证机会和约束", proxy=True),
)
