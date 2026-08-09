import { useMemo } from "react";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["verified", "partial", "unsupported", "superseded"] as const;

export function EvidenceStatusChart({ summary }: { summary: Record<string, number> }) {
  const aliases: Record<string, string> = { verified: "SUPPORTED", supported: "SUPPORTED", partial: "PARTIAL", unsupported: "UNSUPPORTED", not_checked: "NOT_CHECKED", superseded: "UNSUPPORTED" };
  const counts = Object.entries(summary).reduce<Record<string, number>>((acc, [key, value]) => {
    const normalized = aliases[key.toLowerCase()] ?? key.toUpperCase();
    acc[normalized] = (acc[normalized] ?? 0) + value;
    return acc;
  }, {});
  const data = ["SUPPORTED", "PARTIAL", "UNSUPPORTED", "NOT_CHECKED"].map((key) => [key, counts[key] ?? 0] as const);
  const option = useMemo(() => data.length ? {
    tooltip: { trigger: "axis" as const },
    grid: { left: 80, right: 30, top: 25, bottom: 45 },
    xAxis: { type: "value" as const, minInterval: 1 },
    yAxis: { type: "category" as const, data: data.map(([key]) => key.toUpperCase()) },
    series: [{ type: "bar", data: data.map(([, value]) => value), itemStyle: { color: "#2563eb" } }],
  } : null, [data]);
  if (!Object.keys(summary).length || !option) return <EmptyState reason="缺少证据状态统计。" />;
  return <section className="panel"><header><h2>证据状态</h2></header><EChart option={option} ariaLabel="证据状态统计图" height={300} /></section>;
}
