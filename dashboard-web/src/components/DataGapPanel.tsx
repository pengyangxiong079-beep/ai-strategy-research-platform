import type { ReportData } from "../types";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["gap_id", "label", "reason"] as const;

export function DataGapPanel({ gaps, excluded = [] }: { gaps: ReportData["data_gaps"]; excluded?: Array<Record<string, unknown>> }) {
  if (!gaps.length && !excluded.length) return <EmptyState title="数据完整" reason="当前结构化看板未报告数据缺口或被排除指标。" />;
  return <section className="gap-panel"><h2>数据缺口与排除项</h2>{gaps.map((gap) => <article key={gap.gap_id}><strong>{gap.label}</strong><p>{gap.reason}</p>{gap.required_action && <small>建议：{gap.required_action}</small>}</article>)}{excluded.map((item, index) => <article key={`excluded-${index}`}><strong>已排除：{String(item.metric_id ?? "未知指标")}</strong><p>{Array.isArray(item.reasons) ? item.reasons.join("；") : String(item.reason ?? "不满足可视化规则")}</p></article>)}</section>;
}
