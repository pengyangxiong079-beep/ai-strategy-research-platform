from .base import BaseRenderer


class KpiSummaryRenderer(BaseRenderer):
    def validate(self, data):
        return (bool(data.get("kpis")), "缺少可核验的KPI数据。")

    def render(self, data, st_module):
        metrics = data.get("kpis", [])[:3]
        columns = st_module.columns(len(metrics))
        for column, metric in zip(columns, metrics):
            column.metric(metric.get("label", "KPI"), self.display_value(metric))


class TimeTrendRenderer(BaseRenderer):
    def validate(self, data):
        series = data.get("time_series", [])
        return (bool(series and series[0].get("points")), "缺少具有年份与可核验来源的时间序列。")

    def render(self, data, st_module):
        series = data["time_series"][0]
        points = [
            {"period": str(point.get("period")), "value": point.get("value")}
            for point in series.get("points", [])
        ]
        st_module.subheader(series.get("label", "时间趋势"))
        if series.get("chart_type") == "BAR":
            st_module.bar_chart(points, x="period", y="value")
        elif series.get("chart_type") == "BAR_LINE":
            st_module.vega_lite_chart(
                points,
                {
                    "layer": [
                        {"mark": "bar", "encoding": {"x": {"field": "period"}, "y": {"field": "value", "type": "quantitative"}}},
                        {"mark": {"type": "line", "point": True}, "encoding": {"x": {"field": "period"}, "y": {"field": "value", "type": "quantitative"}}},
                    ]
                },
                width="stretch",
            )
        else:
            st_module.line_chart(points, x="period", y="value")


class MarketCompositionRenderer(BaseRenderer):
    def validate(self, data):
        segments = data.get("market_segments", [])
        return (bool(segments and any(item.get("metrics") for item in segments)), "缺少口径一致的市场构成数据。")

    def render(self, data, st_module):
        rows = []
        for segment in data.get("market_segments", []):
            for metric in segment.get("metrics", []):
                rows.append({"构成": segment.get("label"), "期间": metric.get("period"), "值": metric.get("value")})
        st_module.bar_chart(rows, x="期间", y="值", color="构成", stack=True)


class CompetitorComparisonRenderer(BaseRenderer):
    def validate(self, data):
        return (bool(data.get("competitor_comparisons")), "缺少口径一致的竞品比较数据。")

    def render(self, data, st_module):
        rows = []
        for item in data.get("competitor_comparisons", []):
            values = item.get("values") or [{"entity": "、".join(item.get("entities", [])), "value": None}]
            for value in values:
                rows.append(
                    {
                        "竞品": value.get("entity"),
                        "指标": item.get("metric"),
                        "值": value.get("value"),
                        "单位": item.get("unit"),
                        "期间": item.get("period"),
                        "地区": item.get("geography"),
                        "可比": item.get("comparable"),
                        "比较口径": item.get("comparison_basis"),
                    }
                )
        st_module.dataframe(rows, width="stretch", hide_index=True)


class RiskOpportunityRenderer(BaseRenderer):
    def validate(self, data):
        return (bool(data.get("risks") or data.get("opportunities")), "缺少结构化风险与机会条目。")

    def render(self, data, st_module):
        rows = []
        for item_type, items in (("风险", data.get("risks", [])), ("机会", data.get("opportunities", []))):
            for item in items:
                rows.append({"类型": item_type, "名称": item.get("label"), "说明": item.get("description")})
        st_module.dataframe(rows, width="stretch", hide_index=True)


class RoadmapRenderer(BaseRenderer):
    def validate(self, data):
        return (bool(data.get("roadmap")), "缺少具有时间范围的战略路线图。")

    def render(self, data, st_module):
        rows = [
            {
                "阶段": item.get("label"),
                "开始": item.get("start"),
                "结束": item.get("end"),
                "行动": item.get("description"),
                "状态": item.get("status"),
            }
            for item in data.get("roadmap", [])
        ]
        if rows and all(item.get("开始") and item.get("结束") for item in rows):
            st_module.vega_lite_chart(
                rows,
                {
                    "mark": "bar",
                    "encoding": {
                        "y": {"field": "阶段", "type": "nominal", "sort": None},
                        "x": {"field": "开始", "type": "temporal"},
                        "x2": {"field": "结束"},
                        "tooltip": ["阶段", "开始", "结束", "行动", "状态"],
                    },
                },
                width="stretch",
            )
        else:
            st_module.dataframe(rows, width="stretch", hide_index=True)


class EvidenceQualityRenderer(BaseRenderer):
    def validate(self, data):
        return (bool(data.get("evidence_summary")), "缺少证据质量汇总。")

    def render(self, data, st_module):
        summary = data.get("evidence_summary", {})
        rows = [{"指标": key, "值": value} for key, value in summary.items()]
        st_module.dataframe(rows, width="stretch", hide_index=True)


class DataGapRenderer(BaseRenderer):
    def validate(self, data):
        return (bool(data.get("data_gaps")), "当前未登记结构化数据缺口。")

    def render(self, data, st_module):
        for gap in data.get("data_gaps", []):
            if isinstance(gap, dict):
                st_module.warning(gap.get("description") or gap.get("reason") or str(gap))
            else:
                st_module.warning(str(gap))
