import { useMemo } from "react";
import type { CompetitorComparison } from "../types";
import { comparisonCanRank } from "../lib/validation";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["comparison_id", "entities", "metric", "period", "geography", "unit", "comparison_basis", "source_fact_ids"] as const;

export function DotComparisonChart({ comparisons }: { comparisons: CompetitorComparison[] }) {
  const comparison = comparisons.find(comparisonCanRank);
  const option = useMemo(() => comparison ? {
    tooltip: { formatter: (item: { data: { value: [number, string]; facts: string[] } }) => `${item.data.value[1]}: ${item.data.value[0]} ${comparison.unit ?? ""}<br/>${comparison.period} · ${comparison.geography}<br/>${item.data.facts.join(", ")}` },
    grid: { left: 110, right: 30, top: 30, bottom: 50 },
    xAxis: { type: "value" as const, name: [comparison.unit, comparison.currency].filter(Boolean).join(" ") },
    yAxis: { type: "category" as const, data: comparison.values?.map((item) => item.entity) },
    series: [{ type: "scatter", symbolSize: 15, data: comparison.values?.filter((item) => typeof item.value === "number").map((item) => ({ value: [item.value, item.entity], facts: comparison.source_fact_ids })) }],
  } : null, [comparison]);
  if (!comparison || !option) return <EmptyState reason="缺少地区、期间、单位、定义均一致的竞品比较数据；不可比数据不会生成位置或排名。" />;
  return <section className="panel"><header><h2>{comparison.metric}</h2><p>{comparison.comparison_basis}</p></header><EChart option={option} ariaLabel={`${comparison.metric}竞品点图`} /><p className="source-note">{comparison.source_fact_ids.join("、")}</p></section>;
}
