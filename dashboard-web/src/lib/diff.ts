import type { ReportBundle } from "../types";

export interface DiffRow {
  path: string;
  change: "ADDED" | "REMOVED" | "MODIFIED";
  before: unknown;
  after: unknown;
}

function flatten(value: unknown, prefix = "", result: Record<string, unknown> = {}) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => flatten(item, `${prefix}[${index}]`, result));
  } else if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, item]) => flatten(item, prefix ? `${prefix}.${key}` : key, result));
  } else {
    result[prefix] = value;
  }
  return result;
}

export function compareBundles(before: ReportBundle, after: ReportBundle): DiffRow[] {
  const left = flatten({
    quality: before.quality.overall_status,
    report: before.dashboard.report_data,
  });
  const right = flatten({
    quality: after.quality.overall_status,
    report: after.dashboard.report_data,
  });
  return [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter((path) => JSON.stringify(left[path]) !== JSON.stringify(right[path]))
    .map((path) => ({
      path,
      change: !(path in left) ? "ADDED" : !(path in right) ? "REMOVED" : "MODIFIED",
      before: left[path],
      after: right[path],
    }));
}
