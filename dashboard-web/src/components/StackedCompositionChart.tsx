import { useMemo } from "react";
import type { MarketSegment } from "../types";
import { validateMetric } from "../lib/validation";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["segment_id", "label", "metrics.metric_id", "metrics.value", "metrics.unit"] as const;

export function StackedCompositionChart({ segments }: { segments: MarketSegment[] }) {
  const valid = segments.map((segment) => ({ ...segment, metrics: segment.metrics.filter((m) => !validateMetric(m).length) })).filter((s) => s.metrics.length);
  const option = useMemo(() => {
    if (!valid.length) return null;
    const labels = [...new Set(valid.flatMap((segment) => segment.metrics.map((metric) => metric.label)))];
    return {
      tooltip: {
        trigger: "axis" as const,
        formatter: (items: Array<{ seriesName: string; data: { value: number; facts: string[]; grade: string; period: string } }>) =>
          items.map((item) => `${item.seriesName}: ${item.data.value}<br/>${item.data.period} · ${item.data.facts.join(", ")} · Grade ${item.data.grade}`).join("<br/>")
      },
      legend: { type: "scroll" as const },
      grid: { left: 48, right: 20, top: 56, bottom: 64 },
      xAxis: { type: "category" as const, data: valid.map((segment) => segment.label), axisLabel: { rotate: 18 } },
      yAxis: { type: "value" as const, name: "同口径数值" },
      series: labels.map((label) => ({
        name: label,
        type: "bar",
        stack: "composition",
        data: valid.map((segment) => {
          const metric = segment.metrics.find((item) => item.label === label);
          return metric ? { value: metric.value, facts: metric.source_fact_ids, grade: metric.source_grade, period: metric.period } : null;
        }),
      })),
    };
  }, [valid]);
  if (!option) return <EmptyState reason="没有口径完整的市场构成或业务板块数据。" />;
  return <section className="panel"><header><h2>市场与业务构成</h2><p>堆积展示；仅比较相同指标口径</p></header><EChart option={option} ariaLabel="市场与业务构成堆积图" /></section>;
}
