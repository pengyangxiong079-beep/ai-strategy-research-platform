from .fake_agent_registry import FakeStageAgent

class FakeDataAgent(FakeStageAgent):
    def __init__(self, modes=None): super().__init__("data", modes or ["success"])
