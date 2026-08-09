"""Evidence-based production readiness checks; never self-certify missing QA."""

from __future__ import annotations

import json
from pathlib import Path


def _json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def pipeline_v2_readiness(project_root=".") -> dict:
    root = Path(project_root)
    results = _json(root / "tests/artifacts/test-results.json", {})
    event_log = _json(root / "tests/artifacts/v2-e2e-event-log.json", {})
    checks = {
        "strict_structured_output": (root / "pipeline_v2/envelope.py").is_file(),
        "no_v2_legacy_fallback": results.get("strict_v2") is True,
        "offline_canonical_e2e": event_log.get("overall_status") in {"COMPLETED", "COMPLETED_WITH_WARNINGS"},
        "revision_executor": results.get("revision_executor") is True,
        "stage_retry": results.get("stage_retry") is True,
        "dependency_tests": results.get("python_tests_passed") is True,
        "renderer_tests": results.get("python_tests_passed") is True,
        "legacy_read_only": results.get("legacy_read_only") is True,
    }
    return {"ready": all(checks.values()), "checks": checks, "blocking": [x for x, ok in checks.items() if not ok]}


def workspace_v2_readiness(project_root=".") -> dict:
    root = Path(project_root)
    results = _json(root / "tests/artifacts/test-results.json", {})
    required_pages = ["projects", "new_analysis", "overview", "pipeline", "decisions", "results", "data_quality", "revisions"]
    expected = {
        "1440": required_pages,
        "1024": ["overview", "pipeline", "decisions", "results", "data_quality", "revisions"],
        "768": ["overview", "new_analysis", "decisions", "results", "revisions"],
    }
    screenshots = all((root / f"tests/artifacts/ui-qa/{width}/{page}-{width}.png").is_file() for width, pages in expected.items() for page in pages)
    checks = {
        "core_pages": all((root / f"app_pages/{page}.py").is_file() for page in required_pages),
        "state_driven_cta": results.get("workspace_tests_passed") is True,
        "revision_ui_executor": results.get("revision_ui_executor") is True,
        "decisions_state": results.get("workspace_tests_passed") is True,
        "browser_three_widths": screenshots and results.get("browser_interactions_passed") is True,
        "no_blocking_visual_issues": results.get("visual_qa_passed") is True,
    }
    return {"ready": all(checks.values()), "checks": checks, "blocking": [x for x, ok in checks.items() if not ok]}


def is_pipeline_v2_ready(project_root=".") -> bool:
    return pipeline_v2_readiness(project_root)["ready"]


def is_workspace_v2_ready(project_root=".") -> bool:
    return workspace_v2_readiness(project_root)["ready"]
