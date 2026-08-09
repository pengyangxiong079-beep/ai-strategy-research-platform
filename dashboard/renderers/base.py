class BaseRenderer:
    def __init__(self, configuration=None):
        self.configuration = configuration or {}

    def validate(self, data):
        raise NotImplementedError

    def render(self, data, st_module):
        raise NotImplementedError

    @staticmethod
    def display_value(metric):
        value = metric.get("value")
        unit = metric.get("unit") or ""
        currency = metric.get("currency") or ""
        suffix = " ".join(item for item in (unit, currency) if item)
        return f"{value:,} {suffix}".strip() if isinstance(value, (int, float)) else str(value)
