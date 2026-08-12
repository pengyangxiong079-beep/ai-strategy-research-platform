"""Reusable offline V2 agents for production and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

from pipeline_v2.envelope import make_envelope


def _source():
    return {
        "source_id": "SRC_fixture",
        "title": "Fixture filing",
        "publisher": "Example Group",
        "url": "https://example.invalid/fixture",
        "source_type": "TEST_FIXTURE",
        "source_grade": "GRADE_A",
        "publication_date": "2026-01-01",
        "accessed_at": "2026-01-02",
        "language": "en",
        "geography": "Testland",
        "is_primary_source": True,
        "datasets_supported": ["financial_time_series"],
        "access_status": "SUCCESS",
        "access_issue": "",
        "is_test_fixture": True,
    }


def valid_artifacts(stage: str) -> dict:
    claim = {
        "claim_id": "CLM_fixture_revenue",
        "display_id": None,
        "parent_claim_id": None,
        "claim_type": "FACT",
        "text": "Example Group fixture revenue was 120 test units in 2025.",
        "atomicity_status": "ATOMIC",
        "observation_ids": ["OBS_fixture_revenue"],
        "source_ids": ["SRC_fixture"],
        "verification_status": "SUPPORTED",
        "temporal_status": "HISTORICAL",
        "source_grade_max": "GRADE_A",
        "scope": {"geography": "Testland", "period": "2025"},
        "used_by": [],
        "status": "ACTIVE",
        "is_test_fixture": True,
    }
    if stage == "data":
        return {
            "requirements": {
                "schema_version": "1.0",
                "analysis_type": "COMPANY_STRATEGY",
                "datasets": [{
                    "dataset_id": "financial_time_series",
                    "priority": "CRITICAL",
                    "required_fields": ["entity", "metric", "value", "unit", "period", "source_id"],
                    "minimum_entities": 1,
                    "minimum_observations_per_entity": 1,
                }],
            },
            "source_registry": {"schema_version": "1.0", "sources": [_source()]},
            "observations": {"schema_version": "1.0", "observations": [{
                "observation_id": "OBS_fixture_revenue",
                "dataset_id": "financial_time_series",
                "entity": "Example Group",
                "metric": "revenue",
                "metric_id": "revenue",
                "value": 120,
                "text_value": "",
                "unit": "test units",
                "currency": "TST",
                "period": "2025",
                "period_type": "FISCAL_YEAR",
                "observed_at": "2026-01-02",
                "as_of_date": "2026-01-02",
                "geography": "Testland",
                "entity_scope": "GROUP",
                "channel": "filing",
                "channel_scope": "FILINGS",
                "price_type": "",
                "value_type": "HISTORICAL",
                "metric_definition": "Fixture consolidated revenue",
                "source_id": "SRC_fixture",
                "source_url": "https://example.invalid/fixture",
                "evidence_excerpt": "Synthetic fixture value.",
                "source_grade": "GRADE_A",
                "verification_status": "SUPPORTED",
                "temporal_status": "HISTORICAL",
                "confidence": 1.0,
                "comparability_group": "revenue|TST|Testland|annual|group",
                "notes": "Synthetic fixture only",
                "is_test_fixture": True,
            }]},
            "sufficiency": {
                "schema_version": "1.0",
                "overall_status": "PASS",
                "observation_count": 1,
                "datasets": [{
                    "dataset_id": "financial_time_series",
                    "priority": "CRITICAL",
                    "status": "PASS",
                    "observation_count": 1,
                    "gaps": [],
                }],
            },
        }
    if stage == "research":
        return {
            "claims": [claim],
            "research_sections": [{
                "section_id": "overview",
                "title": "Fixture overview",
                "claim_ids": [claim["claim_id"]],
                "analysis": "Synthetic fixture analysis only.",
            }],
        }
    if stage == "review":
        return {"review_notes": []}
    if stage == "fact_check":
        return {"verified_claims": [claim]}
    if stage == "strategy":
        return {
            "recommendations": [{
                "recommendation_id": "REC_fixture_focus",
                "title": "Protect fixture margin",
                "rationale": "Synthetic test rationale",
                "priority": "HIGH",
                "time_horizon": "12 months",
                "responsible_function": "Strategy",
                "required_capabilities": ["planning"],
                "related_risks": [],
                "related_opportunities": [],
                "claim_ids": [claim["claim_id"]],
                "kpi": "Fixture margin",
                "is_test_fixture": True,
            }],
            "report_model": {
                "schema_version": "2.0",
                "title": "Example Group strategy fixture",
                "paragraphs": [
                    {
                        "section_id": "overview",
                        "section_title": "Overview",
                        "label": "FACT",
                        "text": claim["text"],
                        "claim_ids": [claim["claim_id"]],
                        "recommendation_ids": [],
                    },
                    {
                        "section_id": "strategy",
                        "section_title": "Strategy",
                        "label": "RECOMMENDATION",
                        "text": "Protect fixture margin.",
                        "claim_ids": [claim["claim_id"]],
                        "recommendation_ids": ["REC_fixture_focus"],
                    },
                ],
            },
        }
    raise KeyError(stage)


def semantic_error_artifacts(stage: str) -> dict:
    artifacts = valid_artifacts(stage)
    if stage == "research":
        artifacts["claims"][0]["atomicity_status"] = "COMPOSITE"
    elif stage == "review":
        artifacts["review_notes"] = [{
            "review_id": "R1—R11",
            "severity": "ERROR",
            "category": "structure",
            "issue": "Range ID",
            "evidence": "fixture",
            "required_action": "split issues",
            "status": "OPEN",
        }]
    elif stage == "fact_check":
        artifacts["verified_claims"][0]["source_ids"] = []
    elif stage == "strategy":
        artifacts["recommendations"][0]["claim_ids"] = []
    elif stage == "data":
        artifacts["sufficiency"]["datasets"][0]["status"] = "INSUFFICIENT"
        artifacts["sufficiency"]["overall_status"] = "INSUFFICIENT"
    return artifacts


@dataclass
class FakeStageAgent:
    stage: str
    modes: list[str] = field(default_factory=lambda: ["success"])
    calls: list[dict] = field(default_factory=list)

    def run(self, request: dict):
        self.calls.append(request)
        index = min(len(self.calls) - 1, len(self.modes) - 1)
        mode = self.modes[index]
        if mode == "technical":
            raise ConnectionError("synthetic technical failure")
        if mode == "legacy":
            return "# Legacy Markdown\n\nThis must never pass V2."
        if mode == "invalid_json":
            return "{not-json"
        artifacts = semantic_error_artifacts(self.stage) if mode in {"semantic_error", "upstream"} else valid_artifacts(self.stage)
        if mode == "upstream" and self.stage == "fact_check":
            artifacts["verified_claims"][0]["source_ids"] = ["SRC_missing"]
        envelope = make_envelope(
            run_id=request["run_id"],
            revision_id=request["revision_id"],
            stage=self.stage,
            attempt=request["attempt"],
            artifacts=artifacts,
            agent_role=f"Fake {self.stage} Agent",
        )
        return json.dumps(envelope, ensure_ascii=False)

    @property
    def call_count(self):
        return len(self.calls)


class FakeAgentRegistry:
    def __init__(self, modes: dict[str, list[str] | str] | None = None):
        modes = modes or {}
        self.agents = {}
        for stage in ("data", "research", "review", "fact_check", "strategy"):
            configured = modes.get(stage, ["success"])
            if isinstance(configured, str):
                configured = [configured]
            self.agents[stage] = FakeStageAgent(stage, list(configured))

    def get(self, stage):
        return self.agents[stage]

    def call_count(self, stage=None):
        return self.agents[stage].call_count if stage else sum(x.call_count for x in self.agents.values())
