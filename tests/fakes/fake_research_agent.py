from .fake_agent_registry import FakeStageAgent

class FakeResearchAgent(FakeStageAgent):
    def __init__(self, modes=None): super().__init__("research", modes or ["success"])
