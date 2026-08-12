import sys

import pytest

from pipeline_v2.agent_provider import (
    AgentProviderConfigurationError,
    create_agent_registry,
    get_agent_provider_status,
    is_real_agent_enabled,
)
from pipeline_v2.fake_agent_registry import FakeAgentRegistry
from pipeline_v2.model import load_run_state
from ui import actions


def test_create_agent_registry_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("STRATEGY_PLATFORM_MODE", raising=False)
    sys.modules.pop("pipeline_v2.agents", None)

    registry = create_agent_registry()

    assert isinstance(registry, FakeAgentRegistry)
    assert "pipeline_v2.agents" not in sys.modules
    assert "openai_codex" not in sys.modules
    assert get_agent_provider_status().mode == "offline"


def test_codex_provider_only_activates_when_explicit(monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "codex")
    monkeypatch.setenv("STRATEGY_PLATFORM_MODE", "live")

    registry = create_agent_registry()

    from pipeline_v2.agents import CodexAgentRegistry

    assert isinstance(registry, CodexAgentRegistry)
    assert is_real_agent_enabled()
    assert "openai_codex" not in sys.modules  # imported only when a stage runs


def test_offline_mode_rejects_codex_without_fake_fallback(monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "codex")
    monkeypatch.setenv("STRATEGY_PLATFORM_MODE", "offline")

    with pytest.raises(AgentProviderConfigurationError, match="conflicts"):
        create_agent_registry()


def test_openai_compatibility_name_never_enables_metered_api(monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    monkeypatch.setenv("STRATEGY_PLATFORM_MODE", "live")

    assert not is_real_agent_enabled()
    with pytest.raises(AgentProviderConfigurationError, match="compatibility-only"):
        create_agent_registry()


def test_streamlit_action_uses_provider_factory(monkeypatch, tmp_path):
    registry = FakeAgentRegistry()
    calls = []
    monkeypatch.setattr(actions, "create_agent_registry", lambda: calls.append("factory") or registry)
    monkeypatch.setattr(actions.main, "PIPELINE_V2_DEFAULT", True)
    monkeypatch.chdir(tmp_path)
    scope = {
        "analysis_type": "公司战略", "topic": "Fixture", "industry": "generic",
        "geography": "Testland", "analysis_date": "2026-01-02", "time_horizon": "",
        "objective": "offline", "focus_questions": [], "competitors": [],
        "depth": "标准版", "currency": "", "language": "中文",
    }

    prepared, state = actions.prepare_and_run(scope)

    assert calls == ["factory"]
    assert state["overall_status"] == "AWAITING_HUMAN_REVIEW"
    assert load_run_state(prepared["output_folder"])["agent_calls"]["total"] == 4


def test_legacy_production_entry_rejects_fake_before_starting_codex(monkeypatch, tmp_path):
    import main

    monkeypatch.setenv("AGENT_PROVIDER", "fake")
    monkeypatch.setenv("STRATEGY_PLATFORM_MODE", "offline")
    monkeypatch.setattr(main, "Codex", None)
    with pytest.raises(RuntimeError, match="不允许 legacy Codex"):
        main.revise_strategy_report(tmp_path, "offline")
