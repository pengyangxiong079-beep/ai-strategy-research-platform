"""Explicit artifact dependency graph and STALE propagation."""

from __future__ import annotations

from .model import STAGE_ORDER, now_iso

DEPENDENCIES = {
    "scope": ("data", "research", "review", "fact_check", "human", "strategy", "report", "dashboard", "quality"),
    "data": ("research", "review", "fact_check", "human", "strategy", "report", "dashboard", "quality"),
    "research": ("review", "fact_check", "human", "strategy", "report", "dashboard", "quality"),
    "review": ("fact_check", "human", "strategy", "report", "dashboard", "quality"),
    "fact_check": ("strategy", "report", "dashboard", "quality"),
    "human": ("strategy", "report", "dashboard", "quality"),
    "strategy": ("report", "dashboard", "quality"),
    "report": ("dashboard", "quality"),
    "dashboard": (), "quality": (),
    "dashboard_css": ("dashboard",),
}

REVISION_IMPACTS = {
    "LOCAL_REPAIR": ("report", "dashboard", "quality"),
    "STRATEGY_ONLY": ("strategy", "report", "dashboard", "quality"),
    "FACT_VERIFICATION": ("fact_check", "strategy", "report", "dashboard", "quality"),
    "FULL_RE_RESEARCH": STAGE_ORDER,
    "FULL_RESEARCH": STAGE_ORDER,
}


def mark_stale(state, changed_stage: str, reason: str):
    targets = DEPENDENCIES.get(changed_stage, ())
    for stage_name in targets:
        stage = state["stages"][stage_name]
        if stage.get("status") not in {"PENDING", "RUNNING"}:
            stage["status"] = "STALE"
        stage["stale_reason"] = reason
        state["dependency_state"][stage_name] = "STALE"
    state.setdefault("events", []).append({"at": now_iso(), "stage": changed_stage, "event": "DOWNSTREAM_STALE", "detail": reason})
    return state


def revision_impact(revision_type: str):
    stages = list(REVISION_IMPACTS.get(revision_type, REVISION_IMPACTS["FULL_RE_RESEARCH"]))
    agent_stages = [stage for stage in stages if stage in {"data", "research", "review", "fact_check", "strategy"}]
    local_stages = [stage for stage in stages if stage not in agent_stages]
    return {"stale_stages": stages, "agent_stages": agent_stages, "local_rebuild_stages": local_stages, "uses_codex": bool(agent_stages)}
