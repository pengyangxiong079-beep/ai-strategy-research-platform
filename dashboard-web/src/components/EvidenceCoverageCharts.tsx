import { useMemo } from "react";
import type { DataCoverage, Observation } from "../types";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

const statusColors: Record<string, string> = {
  PASS: "#157347", PARTIAL: "#b7791f", INSUFFICIENT: "#b42318", NOT_APPLICABLE: "#64748b",
};

export function DataCoverageChart({ coverage }: { coverage: DataCoverage }) {
  const rows = [...(coverage.datasets ?? [])].sort((left, right) => {
    const priority = { CRITICAL: 0, IMPORTANT: 1, OPTIONAL: 2 };
    return priority[left.priority] - priority[right.priority] || right.observation_count - left.observation_count;
  });
  const option = useMemo(() => rows.length ? ({
    tooltip: {
      formatter: (item: { data: { value: number; row: typeof rows[number] } }) => {
        const row = item.data.row;
        const comparability = row.comparability_rate === null ? "N/A" : `${Math.round(row.comparability_rate * 100)}%`;
        return `<strong>${row.dataset_id}</strong><br/>${row.priority} · ${row.status}<br/>Observation: ${row.observation_count}<br/>实体: ${row.entity_count}<br/>可比率: ${comparability}`;
      },
    },
    grid: { left: 150, right: 38, top: 24, bottom: 48 },
    xAxis: { type: "value" as const, minInterval: 1, name: "有效 Observation" },
    yAxis: { type: "category" as const, data: rows.map((row) => row.dataset_id), axisLabel: { width: 130, overflow: "truncate" as const } },
    series: [{
      type: "bar",
      data: rows.map((row) => ({ value: row.observation_count, row, itemStyle: { color: statusColors[row.status] ?? "#2563eb" } })),
      label: { show: true, position: "right" as const },
    }],
  }) : null, [rows]);
  if (!option) return <EmptyState reason="尚无确定性数据充分性检查结果。" />;
  return <section className="panel"><header><h2>数据集覆盖与看板就绪度</h2><p>颜色表示 PASS、PARTIAL 或 INSUFFICIENT；OPTIONAL 不阻塞流程</p></header><EChart option={option} ariaLabel="数据集覆盖与看板就绪度" height={Math.max(320, rows.length * 34)} /></section>;
}

function EvidenceDistribution({ observations, groupBy, title }: { observations: Observation[]; groupBy: "dataset_id" | "entity"; title: string }) {
  const rows = useMemo(() => {
    const counts = new Map<string, { supported: number; partial: number }>();
    observations.forEach((item) => {
      const label = String(item[groupBy] || "未分类");
      const current = counts.get(label) ?? { supported: 0, partial: 0 };
      if (String(item.verification_status).toUpperCase() === "PARTIAL") current.partial += 1;
      else current.supported += 1;
      counts.set(label, current);
    });
    return [...counts.entries()]
      .map(([label, count]) => ({ label, ...count, total: count.supported + count.partial }))
      .sort((left, right) => right.total - left.total)
      .slice(0, 12);
  }, [observations, groupBy]);
  const option = useMemo(() => rows.length ? ({
    tooltip: { trigger: "axis" as const },
    legend: { data: ["SUPPORTED", "PARTIAL"] },
    grid: { left: 142, right: 28, top: 48, bottom: 42 },
    xAxis: { type: "value" as const, minInterval: 1, name: "结构化证据条数" },
    yAxis: { type: "category" as const, data: rows.map((row) => row.label), axisLabel: { width: 124, overflow: "truncate" as const } },
    series: [
      { name: "SUPPORTED", type: "bar", stack: "evidence", data: rows.map((row) => row.supported), itemStyle: { color: "#157347" } },
      { name: "PARTIAL", type: "bar", stack: "evidence", data: rows.map((row) => row.partial), itemStyle: { color: "#d97706" } },
    ],
  }) : null, [rows]);
  if (!option) return <EmptyState reason="没有可用于覆盖分析的SUPPORTED或PARTIAL Observation。" />;
  return <section className="panel"><header><h2>{title}</h2><p>表示公开证据覆盖，不代表市场规模、企业排名或战略评分</p></header><EChart option={option} ariaLabel={title} height={Math.max(320, rows.length * 34)} /></section>;
}

export function ObservationCoverageChart({ observations }: { observations: Observation[] }) {
  return <EvidenceDistribution observations={observations} groupBy="dataset_id" title="结构化证据覆盖" />;
}

export function EntityEvidenceChart({ observations }: { observations: Observation[] }) {
  return <EvidenceDistribution observations={observations} groupBy="entity" title="主要实体公开证据覆盖" />;
}
