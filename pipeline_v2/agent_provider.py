"""Single Agent provider configuration and registry factory.

The default is deliberately network-free.  Codex is loaded lazily only after an
explicit ``AGENT_PROVIDER=codex`` selection.  The ``openai`` name remains a
compatibility value, but this project does not create a metered API client.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline_v2.agents import AgentRegistry


OFFLINE_MODES = {"offline", "fake", "test", "ci"}
LIVE_MODES = {"live", "codex", "real"}
SUPPORTED_PROVIDERS = {"fake", "codex", "openai"}


class AgentProviderConfigurationError(RuntimeError):
    """Raised for an explicit but unsafe or unsupported provider selection."""


@dataclass(frozen=True)
class AgentProviderStatus:
    provider: str
    mode: str
    real_agent_calls_allowed: bool


def _provider_name(provider: str | None = None) -> str:
    value = (provider if provider is not None else os.getenv("AGENT_PROVIDER", "fake"))
    name = str(value).strip().lower() or "fake"
    if name not in SUPPORTED_PROVIDERS:
        raise AgentProviderConfigurationError(
            f"Unsupported AGENT_PROVIDER={name!r}; use fake or codex."
        )
    return name


def _mode_name(provider: str) -> str:
    configured = os.getenv("STRATEGY_PLATFORM_MODE", "").strip().lower()
    if configured:
        if configured in OFFLINE_MODES:
            return "offline"
        if configured in LIVE_MODES:
            return "live"
        raise AgentProviderConfigurationError(
            f"Unsupported STRATEGY_PLATFORM_MODE={configured!r}; use offline or live."
        )
    return "live" if provider == "codex" else "offline"


def get_agent_provider_status(provider: str | None = None) -> AgentProviderStatus:
    name = _provider_name(provider)
    mode = _mode_name(name)
    return AgentProviderStatus(
        provider=name,
        mode=mode,
        real_agent_calls_allowed=name == "codex" and mode == "live",
    )


def is_real_agent_enabled(provider: str | None = None) -> bool:
    return get_agent_provider_status(provider).real_agent_calls_allowed


def create_agent_registry(provider: str | None = None) -> "AgentRegistry":
    status = get_agent_provider_status(provider)
    if status.provider == "fake":
        from pipeline_v2.fake_agent_registry import FakeAgentRegistry

        return FakeAgentRegistry()
    if status.provider == "openai":
        raise AgentProviderConfigurationError(
            "AGENT_PROVIDER=openai is compatibility-only and is not a configured "
            "runtime. This project does not require OPENAI_API_KEY or enable a "
            "metered OpenAI API path; use fake or explicitly select codex."
        )
    if status.mode == "offline":
        raise AgentProviderConfigurationError(
            "AGENT_PROVIDER=codex conflicts with STRATEGY_PLATFORM_MODE=offline. "
            "No Agent was started; set STRATEGY_PLATFORM_MODE=live explicitly."
        )

    # Lazy import is a tested boundary: offline runs must not import the module
    # containing the openai_codex adapter.
    from pipeline_v2.agents import CodexAgentRegistry

    return CodexAgentRegistry()
