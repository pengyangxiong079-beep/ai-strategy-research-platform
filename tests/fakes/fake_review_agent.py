from .fake_agent_registry import FakeStageAgent

class FakeReviewAgent(FakeStageAgent):
    def __init__(self, modes=None): super().__init__("review", modes or ["success"])
