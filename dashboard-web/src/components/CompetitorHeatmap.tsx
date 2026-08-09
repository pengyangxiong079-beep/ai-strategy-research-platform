import { useMemo } from "react";
import type { CompetitorComparison } from "../types";
import { comparisonCanRank } from "../lib/validation";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["comparison_id", "entities", "metric", "values"] as const;

export function CompetitorHeatmap({ comparisons }: { comparisons: CompetitorComparison[] }) {
  const usable = comparisons.filter(comparisonCanRank);
  const option = useMemo(() => {
    if (usable.length < 2) return null;
    const entities = [...new Set(usable.flatMap((item) => item.entities))];
    const data = usable.flatMap((item, y) => item.values?.flatMap((value) => typeof value.value === "number" ? [{ value: [entities.indexOf(value.entity), y, value.value], facts: item.source_fact_ids, basis: item.comparison_basis }] : []) ?? []);
    return {
      tooltip: { formatter: (item: { data: { value: [number, number, number]; facts: string[]; basis: string } }) => `${entities[item.data.value[0]]} · ${usable[item.data.value[1]].metric}: ${item.data.value[2]}<br/>${item.data.basis}<br/>${item.data.facts.join(", ")}` },
      grid: { left: 120, right: 60, top: 28, bottom: 70 },
      xAxis: { type: "category" as const, data: entities, axisLabel: { rotate: 15 } },
      yAxis: { type: "category" as const, data: usable.map((item) => item.metric) },
      visualMap: { min: Math.min(...data.map((item) => item.value[2])), max: Math.max(...data.map((item) => item.value[2])), calculable: true, orient: "horizontal" as const, left: "center", bottom: 4 },
      series: [{ type: "heatmap", data }],
    };
  }, [usable]);
  if (!option) return <EmptyState reason="热力图至少需要两个具有数值的比较维度。" />;
  return <section className="panel"><header><h2>竞品多维比较</h2><p>颜色仅表示各披露值，不代表综合排名</p></header><EChart option={option} ariaLabel="竞品比较热力图" /></section>;
}
