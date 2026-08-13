"""Dependency-injected Agent registry interfaces for Pipeline V2."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Callable, Protocol


STAGE_OUTPUT_CONTRACTS = {
    "data": {
        "artifacts": {
            "requirements": "Object with schema_version and datasets array; never return a bare array.",
            "source_registry": "Object with schema_version and sources array; never return a bare array.",
            "observations": "Object with schema_version and observations array; never return a bare array.",
            "sufficiency": "Object with schema_version, overall_status, observation_count and datasets array; never return a bare array.",
        },
        "rules": [
            "Every Observation links to a registered Source.",
            "sufficiency.observation_count equals the Observation array length.",
            "Declare missing evidence as a gap; never invent it.",
            "On retry, preserve valid previous sources and observations, then perform a bounded gap search only for CRITICAL datasets named in error_packet.",
            "When repair_context.mode is BOUNDED_CRITICAL_GAP_SEARCH, execute its targets and recommended_queries; do not treat the retry as metadata-only repair.",
            "If a CRITICAL gap remains after bounded search, keep it INSUFFICIENT with explicit gaps; never manufacture a PASS.",
        ],
    },
    "research": {
        "artifacts": {
            "claims": "Atomic claims; FACT claims use only registered source_ids and observation_ids.",
            "research_sections": "Sections with section_id, title, claim_ids and analysis.",
        },
        "rules": ["atomicity_status is ATOMIC", "Do not invent IDs or sources"],
    },
    "review": {
        "artifact": "review_notes", "type": "array",
        "item_required": ["review_id", "severity", "category", "issue", "evidence", "required_action", "status"],
        "rules": {
            "review_id": "Consecutive atomic IDs R1, R2, ...; ranges are forbidden.",
            "severity": {"enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "ERROR", "WARNING", "INFO"]},
            "status": {"enum": ["OPEN", "RESOLVED", "ACCEPTED", "DEFERRED"]},
            "required_action": "Required and non-empty for OPEN items.",
            "evidence_review": "Use the supplied Source Registry, Observations and sufficiency records; do not claim they are absent when present in inputs.",
        },
        "example": [{
            "review_id": "R1", "severity": "HIGH", "category": "evidence",
            "issue": "A material claim has one supporting observation.",
            "evidence": "CLM_example links only OBS_example.",
            "required_action": "Add evidence or narrow the claim.", "status": "OPEN",
        }],
    },
    "fact_check": {
        "artifact": {
            "verified_claims": {
                "claims": "One record per input research Claim, preserving claim_id and observation_ids.",
                "observation_verifications": "One record per canonical Observation; unclaimed observations use NOT_CHECKED and empty claim_ids.",
            }
        },
        "rules": [
            "Account for every canonical Observation, including NOT_CHECKED records.",
            "SUPPORTED requires a linked GRADE_A, GRADE_B or reliable GRADE_C source.",
            "Use only IDs present in inputs.",
            "Do not collapse claim verification and observation coverage into one ambiguous array.",
        ],
    },
    "strategy": {
        "artifacts": {
            "recommendations": "A bare JSON array of evidence-linked action objects with claim_ids and existing review_ids. Do not wrap it in an object.",
            "report_model": "Professional paragraphs, structured risks, structured opportunities, and structured scenarios whenever scenario language is used.",
        },
        "rules": [
            "Never use UNSUPPORTED claims as recommendation evidence.",
            "FACT paragraphs reference valid claim_ids.",
            "Separate FACT, INFERENCE, RECOMMENDATION and PENDING labels.",
            "Cover every required_sections value from input 00_analysis_scope.json with at least one paragraph section_id.",
            "Write for senior decision-makers: conclusion first, quantified evidence where supported, explicit uncertainty, accountable actions, time horizons and KPIs.",
            "report_model.risks and report_model.opportunities each contain 1-5 concise items with label, description, claim_ids, priority/severity, timeframe and confidence; distinguish evidence from analyst judgment.",
        ],
    },
}


def stage_output_contract(stage: str) -> dict:
    return STAGE_OUTPUT_CONTRACTS.get(stage, {})


class StageAgent(Protocol):
    def run(self, request: dict): ...


class AgentRegistry(Protocol):
    def get(self, stage: str) -> StageAgent: ...


@dataclass
class CallableAgent:
    runner: Callable[[dict], object]

    def run(self, request: dict):
        return self.runner(request)


@dataclass
class CodexAgentRegistry:
    """Production adapter boundary.

    Thread creation belongs in injected runners, never in the orchestrator. This
    keeps the business workflow offline-testable and prevents hidden fallbacks.
    """

    runners: dict[str, Callable[[dict], object]] = field(default_factory=dict)
    model: str = "gpt-5.6-terra"

    def get(self, stage: str) -> StageAgent:
        if stage in self.runners:
            return CallableAgent(self.runners[stage])
        return CodexStageAgent(stage, self.model)

    @staticmethod
    def runtime():
        """Load the ChatGPT-authenticated Codex runtime only in live mode."""
        from openai_codex import Codex, Sandbox

        return Codex, Sandbox


@dataclass
class CodexStageAgent:
    stage: str
    model: str

    def run(self, request: dict):
        # The SDK boundary is intentionally isolated here. Tests inject Fake agents
        # and never import or call this method.
        Codex, Sandbox = CodexAgentRegistry.runtime()

        prompt = strict_output_instructions(self.stage) + "\n\n" + json.dumps(request, ensure_ascii=False, indent=2)
        with Codex() as codex:
            thread = codex.thread_start(model=self.model, sandbox=Sandbox.read_only)
            result = thread.run(prompt)
        for attr in ("final_response", "output_text", "text"):
            value = getattr(result, attr, None)
            if isinstance(value, str) and value.strip():
                return value
        if isinstance(result, str):
            return result
        raise RuntimeError(f"{self.stage} Agent未返回可解析响应")


def _legacy_strict_output_instructions(stage: str) -> str:
    base = (
        f"仅返回Pipeline V2 {stage} Envelope对应的一个JSON对象；不得使用Markdown代码围栏，"
        "不得添加JSON之外的解释。返回前检查所有必填字段，不得用未定义字段替代必填字段。"
    )
    if stage == "review":
        base += (
            "artifacts.review_notes必须是数组；每条必须包含review_id、severity、category、issue、"
            "evidence、required_action、status。review_id必须严格按R1、R2…连续编号，禁止R1—R11、"
            "R1-R5等范围编号；OPEN项必须给required_action。"
        )
    if stage == "strategy":
        base += "recommendation.review_ids只能引用输入02_review_notes.json中实际存在的ID。"
    return base


def strict_output_instructions(stage: str) -> str:
    """Provide an executable contract, including exact enums and repair behavior."""
    base = (
        f"Return exactly one Pipeline V2 {stage} Envelope JSON object. Do not use Markdown fences or add prose outside JSON. "
        "Copy run_id, revision_id, stage and attempt exactly from the request. Set schema_version and pipeline_version to '2.0' and status to 'COMPLETE'. "
        "Before responding, validate every required field, enum and referenced ID. Never invent evidence, sources, observations, claims or numeric values. "
        "When error_packet is non-empty, repair every listed JSON pointer while preserving already valid content. "
        "Use previous_invalid_output to recover valid content from a malformed prior response when available. "
        "Always include metadata.generated_at and metadata.agent_role; these are Envelope provenance fields, not evidence. "
    )
    if stage == "review":
        base += (
            "artifacts.review_notes is an array. Use consecutive atomic IDs R1, R2, ... and never range IDs. "
            "severity is exactly one of CRITICAL, HIGH, MEDIUM, LOW, ERROR, WARNING, INFO; never use BLOCKER. "
            "status is exactly one of OPEN, RESOLVED, ACCEPTED, DEFERRED. OPEN requires required_action. "
        )
    if stage == "strategy":
        base += (
            "artifacts.recommendations must be a bare JSON array, never "
            "{\"recommendations\": [...]}. recommendation.review_ids may reference only IDs "
            "in input 02_review_notes.json. "
            "report_model.risks and report_model.opportunities must be JSON arrays of evidence-linked decision items, not prose headings. "
        )
    if stage == "data":
        base += (
            "If repair_context.mode is BOUNDED_CRITICAL_GAP_SEARCH, perform the listed bounded source search now, "
            "using each target's requirement, gaps and recommended_queries. Prefer primary sources, preserve valid prior evidence, "
            "and recompute sufficiency after adding only verifiable observations. Do not return a metadata-only repair. "
            "If repair_context.mode is TARGETED_GAP_SEARCH, search only its target_dataset_ids and queries, merge newly verified "
            "Sources and Observations with every valid existing input artifact, and return the complete merged artifacts. "
            "Never delete existing evidence merely because a targeted source cannot be accessed; keep unresolved gaps explicit. "
        )
    if stage == "fact_check":
        base += (
            "artifacts.verified_claims is an object with claims and observation_verifications arrays. "
            "The claims array covers every input research claim. The observation_verifications array covers every input observation exactly once. "
            "For observations not used by a claim, use verification_status NOT_CHECKED and claim_ids []. "
        )
    return base + "\nStage-specific contract:\n" + json.dumps(
        stage_output_contract(stage), ensure_ascii=False, indent=2
    )
