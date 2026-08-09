import type { Metric } from "../types";
import { formatMetricValue, validateMetric } from "../lib/validation";
import { EmptyState } from "./EmptyState";

export const requiredFields = [
  "metric_id", "label", "value", "unit", "geography", "period", "value_type",
  "verification_status", "temporal_status", "source_fact_ids", "source_grade", "confidence",
] as const;

export function KpiSummary({ metrics, locale }: { metrics: Metric[]; locale: string }) {
  const valid = metrics.filter((metric) => validateMetric(metric).length === 0).slice(0, 4);
  if (!valid.length) return <EmptyState reason="没有同时具备数值、单位、期间、地区和有效F证据的核心KPI。" />;
  return (
    <div className="kpi-grid">
      {valid.map((metric) => (
        <article className="kpi-card" key={metric.metric_id} tabIndex={0}>
          <span>{metric.label}</span>
          <strong>{formatMetricValue(metric, locale)}</strong>
          <small>{metric.period} · {metric.geography}</small>
          <small>{metric.value_type} · {metric.temporal_status} · {metric.verification_status} · {metric.confidence}</small>
          {metric.verification_status === "PARTIAL" && <span className="quality-hint">部分支持</span>}
          <footer>{metric.source_fact_ids.join(" · ")} · 来源等级 {metric.source_grade}</footer>
        </article>
      ))}
    </div>
  );
}
