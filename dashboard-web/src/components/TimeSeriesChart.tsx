import { useMemo } from "react";
import type { TimeSeries } from "../types";
import { valueTypeStyles } from "../lib/styles";
import { validateMetric } from "../lib/validation";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["series_id", "label", "points.metric_id", "points.value", "points.period"] as const;

export function TimeSeriesChart({ series }: { series: TimeSeries[] }) {
  const usable = series.find((item) => item.points.filter((point) => validateMetric(point).length === 0).length > 1);
  const option = useMemo(() => {
    if (!usable) return null;
    const points = usable.points.filter((point) => validateMetric(point).length === 0);
    const isFuture = (valueType: string) => ["FORECAST", "SCENARIO"].includes(valueType);
    const isTarget = (valueType: string) => valueType === "TARGET";
    const lastObservedIndex = points.reduce((last, point, index) => !isFuture(point.value_type) && !isTarget(point.value_type) ? index : last, -1);
    const actualData = points.map((point) => !isFuture(point.value_type) && !isTarget(point.value_type) ? { value: point.value, metric: point } : null);
    const forecastData = points.map((point, index) => {
      if (isFuture(point.value_type) || index === lastObservedIndex) return { value: point.value, metric: point };
      return null;
    });
    const targetData = points.map((point) => isTarget(point.value_type) ? { value: point.value, metric: point } : null);
    return {
      tooltip: {
        trigger: "axis" as const,
        formatter: (items: Array<{ data: { value: number; metric: typeof points[number] } }>) => {
          const unique = [...new Map(items.filter((item) => item.data?.metric).map((item) => [item.data.metric.metric_id, item.data])).values()];
          return unique.map((item) => {
            const m = item.metric;
            return `<strong>${m.label}</strong><br/>${m.period}: ${item.value} ${m.unit ?? ""} ${m.currency ?? ""}<br/>${m.geography}<br/>${m.value_type} / ${m.temporal_status}<br/>${m.source_fact_ids.join(", ")} · Grade ${m.source_grade}`;
          }).join("<br/><br/>");
        },
      },
      legend: { data: ["实际/历史", "预测/情景", "目标"] },
      grid: { left: 52, right: 24, top: 44, bottom: 52 },
      xAxis: { type: "category" as const, data: points.map((point) => point.period), name: "期间" },
      yAxis: { type: "value" as const, name: points[0]?.unit ?? "" },
      series: [
        { name: "实际/历史", type: usable.chart_type === "BAR" ? "bar" : "line", smooth: false, symbolSize: 8, connectNulls: false, lineStyle: { type: "solid", width: 3 }, itemStyle: { color: valueTypeStyles.ACTUAL.color }, data: actualData },
        { name: "预测/情景", type: "line", smooth: false, symbolSize: 8, connectNulls: false, lineStyle: { type: "dashed", width: 3 }, itemStyle: { color: valueTypeStyles.FORECAST.color }, data: forecastData },
        { name: "目标", type: "scatter", symbol: "diamond", symbolSize: 13, itemStyle: { color: valueTypeStyles.TARGET.color }, data: targetData },
      ],
    };
  }, [usable]);
  if (!usable || !option) return <EmptyState reason="缺少至少两个口径完整、可追溯的时间点。" />;
  const first = usable.points[0];
  return (
    <section className="panel">
      <header><h2>{usable.label}</h2><p>{first?.geography} · 单位：{first?.unit}{first?.currency ? ` · ${first.currency}` : ""}</p></header>
      <EChart option={option} ariaLabel={`${usable.label}时间趋势`} />
      <p className="source-note">来源：{[...new Set(usable.points.flatMap((point) => point.source_fact_ids))].join("、")}</p>
    </section>
  );
}
