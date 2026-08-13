"""Generate the auditable, network-free Pipeline V2 fixture artifact set."""

from __future__ import annotations

import argparse
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


DEFAULT_ARTIFACTS = ROOT / "tests/artifacts"


def main(output_root=None):
    artifacts = Path(output_root).resolve() if output_root else DEFAULT_ARTIFACTS
    run = artifacts / "v2-company-strategy-run"
    if run.exists():
        shutil.rmtree(run)
    run.mkdir(parents=True)
    scope = json.loads((ROOT / "tests/fixtures/v2_company_strategy/scope.json").read_text(encoding="utf-8"))
    (run / "00_analysis_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
    PipelineV2Service(artifacts).initialize(run, "fixture_company_strategy", scope)
    registry = create_agent_registry("fake")
    feedback = {"schema_version": "2.0", "feedback": [{"feedback_id": "HFB_fixture", "decision_id": "DEC_fixture", "claim_ids": [], "choice": "接受", "status": "RESOLVED"}]}
    state = PipelineV2Orchestrator(registry).execute(run, human_feedback=feedback)
    log = {"schema_version": "2.0", "is_test_fixture": True, "run_id": state["run_id"], "overall_status": state["overall_status"], "agent_calls": state["agent_calls"], "events": state["events"]}
    (artifacts / "v2-e2e-event-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run": str(run), "status": state["overall_status"], "agent_calls": registry.call_count()}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root", type=Path, default=None,
        help="Optional disposable artifact root; defaults to tests/artifacts.",
    )
    args = parser.parse_args()
    main(args.output_root)
