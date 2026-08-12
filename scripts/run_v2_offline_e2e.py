"""Generate the auditable, network-free Pipeline V2 fixture artifact set."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline_v2.orchestrator import PipelineV2Orchestrator
from pipeline_v2.service import PipelineV2Service
from pipeline_v2.agent_provider import create_agent_registry


ARTIFACTS = ROOT / "tests/artifacts"
RUN = ARTIFACTS / "v2-company-strategy-run"


def main():
    if RUN.exists():
        shutil.rmtree(RUN)
    RUN.mkdir(parents=True)
    scope = json.loads((ROOT / "tests/fixtures/v2_company_strategy/scope.json").read_text(encoding="utf-8"))
    (RUN / "00_analysis_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
    PipelineV2Service(ARTIFACTS).initialize(RUN, "fixture_company_strategy", scope)
    registry = create_agent_registry("fake")
    feedback = {"schema_version": "2.0", "feedback": [{"feedback_id": "HFB_fixture", "decision_id": "DEC_fixture", "claim_ids": [], "choice": "接受", "status": "RESOLVED"}]}
    state = PipelineV2Orchestrator(registry).execute(RUN, human_feedback=feedback)
    log = {"schema_version": "2.0", "is_test_fixture": True, "run_id": state["run_id"], "overall_status": state["overall_status"], "agent_calls": state["agent_calls"], "events": state["events"]}
    (ARTIFACTS / "v2-e2e-event-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run": str(RUN), "status": state["overall_status"], "agent_calls": registry.call_count()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
