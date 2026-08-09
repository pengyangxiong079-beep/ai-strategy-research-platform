from .fake_agent_registry import FakeStageAgent

class FakeStrategyAgent(FakeStageAgent):
    def __init__(self, modes=None): super().__init__("strategy", modes or ["success"])
