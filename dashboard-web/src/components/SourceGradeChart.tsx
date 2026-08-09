import { useMemo } from "react";
import type { ReportData } from "../types";
import { gradeColors } from "../lib/styles";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["source_grade"] as const;

export function SourceGradeChart({ report }: { report: ReportData }) {
  const metrics = [...report.kpis, ...report.time_series.flatMap((item) => item.points), ...report.market_segments.flatMap((item) => item.metrics)];
  const counts = metrics.reduce<Record<string, number>>((acc, metric) => ({ ...acc, [metric.source_grade]: (acc[metric.source_grade] ?? 0) + 1 }), {});
  const data = Object.entries(counts);
  const option = useMemo(() => data.length ? {
    tooltip: { trigger: "axis" as const },
    grid: { left: 60, right: 25, top: 25, bottom: 45 },
    xAxis: { type: "category" as const, data: data.map(([grade]) => `Grade ${grade}`) },
    yAxis: { type: "value" as const, minInterval: 1 },
    series: [{ type: "bar", data: data.map(([grade, value]) => ({ value, itemStyle: { color: gradeColors[grade] } })) }],
  } : null, [data]);
  if (!option) return <EmptyState reason="没有可统计来源等级的指标。" />;
  return <section className="panel"><header><h2>指标来源等级</h2></header><EChart option={option} ariaLabel="来源等级统计图" height={300} /></section>;
}
