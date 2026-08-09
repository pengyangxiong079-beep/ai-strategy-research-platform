import type { DiffRow } from "../lib/diff";
import { EmptyState } from "./EmptyState";

function category(path: string) {
  if (path.includes("source_fact_ids")) return "来源变化";
  if (path.includes("verification_status")) return "核验状态";
  if (path.includes("recommendations")) return "战略建议";
  if (path.includes("risks") && path.endsWith("severity")) return "风险等级";
  if (path.includes("kpis") || path.includes("metrics")) return "KPI/目标";
  return "其他字段";
}

export function RevisionDiffTable({ rows }: { rows: DiffRow[] }) {
  if (!rows.length) return <EmptyState title="无变化" reason="两个版本的结构化字段相同。" />;
  return <div className="table-scroll"><table><thead><tr><th>类型</th><th>类别</th><th>字段</th><th>旧值</th><th>新值</th></tr></thead><tbody>{rows.slice(0, 300).map((row) => <tr key={row.path}><td><span className={`change ${row.change.toLowerCase()}`}>{row.change}</span></td><td>{category(row.path)}</td><td>{row.path}</td><td>{String(row.before ?? "—")}</td><td>{String(row.after ?? "—")}</td></tr>)}</tbody></table></div>;
}

