import { catalogSchema, reportBundleSchema } from "../schema";
import type { Catalog, EmbeddedDashboardPayload, ReportBundle } from "../types";

declare global {
  interface Window {
    __DASHBOARD_EMBEDDED__?: EmbeddedDashboardPayload;
  }
}

export function embeddedPayload(): EmbeddedDashboardPayload | null {
  if (window.__DASHBOARD_EMBEDDED__) return window.__DASHBOARD_EMBEDDED__;
  const node = document.getElementById("dashboard-embedded-data");
  if (!node?.textContent) return null;
  try {
    return JSON.parse(node.textContent) as EmbeddedDashboardPayload;
  } catch {
    return null;
  }
}

export async function loadCatalog(): Promise<Catalog> {
  const embedded = embeddedPayload();
  if (embedded) return catalogSchema.parse(embedded.catalog) as Catalog;
  const response = await fetch("./data/index.json");
  if (!response.ok) throw new Error(`报告索引加载失败：${response.status}`);
  return catalogSchema.parse(await response.json()) as Catalog;
}

export async function loadBundle(dataUrl: string, runId: string, revision: string): Promise<ReportBundle> {
  const embedded = embeddedPayload();
  const key = `${runId}::${revision}`;
  if (embedded?.reports[key]) return reportBundleSchema.parse(embedded.reports[key]) as ReportBundle;
  const response = await fetch(dataUrl);
  if (!response.ok) throw new Error(`报告数据加载失败：${response.status}`);
  return reportBundleSchema.parse(await response.json()) as ReportBundle;
}
