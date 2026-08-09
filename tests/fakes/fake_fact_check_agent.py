from .fake_agent_registry import FakeStageAgent

class FakeFactCheckAgent(FakeStageAgent):
    def __init__(self, modes=None): super().__init__("fact_check", modes or ["success"])
