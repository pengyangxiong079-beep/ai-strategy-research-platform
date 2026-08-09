import type { StrategicItem } from "../types";
import { EmptyState } from "./EmptyState";

export const requiredFields = ["item_id", "label", "description", "source_fact_ids"] as const;

export function RiskMatrix({ risks, opportunities }: { risks: StrategicItem[]; opportunities: StrategicItem[] }) {
  if (!risks.length && !opportunities.length) return <EmptyState reason="缺少结构化风险与机会条目。" />;
  const column = (title: string, items: StrategicItem[]) => (
    <section className="risk-column"><h2>{title}</h2>{items.length ? items.map((item) => <article key={item.item_id} className="list-card" tabIndex={0}><strong>{item.label}</strong><p>{item.description}</p><small>{item.timeframe ?? "时间待定"} · {item.source_fact_ids.join("、") || "无量化F证据"}</small></article>) : <EmptyState reason={`暂无${title}数据。`} />}</section>
  );
  return <><p className="method-note">未提供真实概率与影响评分，因此不生成虚假气泡矩阵。</p><div className="two-column">{column("风险", risks)}{column("机会", opportunities)}</div></>;
}
