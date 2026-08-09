import type { RoadmapItem } from "../types";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["item_id", "label", "start", "end", "status", "source_fact_ids"] as const;

export function StrategyTimeline({ items }: { items: RoadmapItem[] }) {
  const valid = items.filter((item) => item.start || item.end);
  if (!valid.length) return <EmptyState reason="路线图缺少真实起止时间。" />;
  return <section className="timeline" aria-label="战略路线图">{valid.map((item) => <article key={item.item_id} className="timeline-item" tabIndex={0}><div className="timeline-period">{item.start ?? "待定"} — {item.end ?? "持续"}</div><div><strong>{item.label}</strong><span className="badge">{item.status}</span><p>{item.description}</p><small>{item.source_fact_ids.join("、")}</small></div></article>)}</section>;
}
