"""Dependency-injected Agent registry interfaces for Pipeline V2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


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
        import json
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


def strict_output_instructions(stage: str) -> str:
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
