import { useEffect, useMemo, useState } from "react";
import type { Catalog, ReportBundle } from "../types";
import { loadBundle } from "../lib/loader";
import { compareBundles } from "../lib/diff";
import { EmptyState } from "./EmptyState";
import { RevisionDiffTable } from "./RevisionDiffTable";

export const requiredFields = ["run_id", "revision", "dashboard.report_data"] as const;

export function RevisionComparison({ catalog, current }: { catalog: Catalog; current: ReportBundle }) {
  const entries = useMemo(() => catalog.reports.filter((item) => item.run_id === current.run_id), [catalog, current.run_id]);
  const [leftRevision, setLeftRevision] = useState(entries.at(-2)?.revision ?? entries[0]?.revision ?? "");
  const [rightRevision, setRightRevision] = useState(current.revision);
  const [left, setLeft] = useState<ReportBundle | null>(null);
  const [right, setRight] = useState<ReportBundle | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        setError("");
        const leftEntry = entries.find((item) => item.revision === leftRevision);
        const rightEntry = entries.find((item) => item.revision === rightRevision);
        if (!leftEntry || !rightEntry) return;
        const [leftBundle, rightBundle] = await Promise.all([
          loadBundle(leftEntry.data_url, leftEntry.run_id, leftEntry.revision),
          loadBundle(rightEntry.data_url, rightEntry.run_id, rightEntry.revision),
        ]);
        setLeft(leftBundle);
        setRight(rightBundle);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    };
    void load();
  }, [entries, leftRevision, rightRevision]);

  if (entries.length < 2) return <EmptyState reason="当前运行只有一个revision，无法进行版本比较。" />;
  const rows = left && right ? compareBundles(left, right) : [];
  const kpiChanges = rows.filter((row) => row.path.includes(".kpis[") && row.path.endsWith(".value"));
  return (
    <section>
      <div className="comparison-controls">
        <label>版本 A<select value={leftRevision} onChange={(event) => setLeftRevision(event.target.value)}>{entries.map((entry) => <option key={entry.revision}>{entry.revision}</option>)}</select></label>
        <label>版本 B<select value={rightRevision} onChange={(event) => setRightRevision(event.target.value)}>{entries.map((entry) => <option key={entry.revision}>{entry.revision}</option>)}</select></label>
      </div>
      {error && <EmptyState reason={error} />}
      {left && right && <div className="status-compare"><strong>Quality</strong><span>{left.revision}: {left.quality.overall_status}</span><span>→</span><span>{right.revision}: {right.quality.overall_status}</span></div>}
      {kpiChanges.length > 0 && <section className="panel"><h2>KPI变化</h2><div className="table-scroll"><table><thead><tr><th>字段</th><th>版本 A</th><th>版本 B</th></tr></thead><tbody>{kpiChanges.map((row) => <tr key={row.path}><td>{row.path}</td><td>{String(row.before ?? "—")}</td><td>{String(row.after ?? "—")}</td></tr>)}</tbody></table></div></section>}
      <section className="panel"><h2>字段变化</h2><RevisionDiffTable rows={rows} /></section>
    </section>
  );
}
