import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const outputsRoot = join(projectRoot, "outputs");
const publicData = join(projectRoot, "dashboard-web", "public", "data");
const sensitiveKey = /token|cookie|authorization|credential|secret|password|thread.?id|environment|account/i;

async function readJson(path, fallback = null) {
  try { return JSON.parse(await readFile(path, "utf8")); } catch { return fallback; }
}

function sanitize(value) {
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).filter(([key]) => !sensitiveKey.test(key)).map(([key, item]) => [key, sanitize(item)]));
  }
  return value;
}

function yearFrom(value) {
  const match = String(value ?? "").match(/(?:19|20)\d{2}/);
  return match ? Number(match[0]) : null;
}

function normalizeMetric(metric, section, analysisDate) {
  const type = String(metric.value_type ?? "UNKNOWN").toUpperCase();
  const verificationRaw = String(metric.verification_status ?? "NOT_CHECKED").toUpperCase();
  const verification = verificationRaw === "VERIFIED" ? "SUPPORTED"
    : ["SUPERSEDED", "OUTDATED", "UNKNOWN"].includes(verificationRaw)
      ? verificationRaw === "UNKNOWN" ? "NOT_CHECKED" : "UNSUPPORTED"
      : verificationRaw;
  const analysisYear = yearFrom(analysisDate);
  const periodYear = yearFrom(metric.period);
  let temporal = metric.temporal_status;
  if (!temporal) {
    temporal = ["FORECAST", "TARGET", "SCENARIO"].includes(type)
      ? "FUTURE_PLAN"
      : analysisYear && periodYear && periodYear < analysisYear
        ? "HISTORICAL"
        : type === "ACTUAL" ? "CURRENT" : "UNKNOWN";
  }
  if (["FORECAST", "TARGET", "SCENARIO"].includes(temporal)) temporal = "FUTURE_PLAN";
  return {
    ...metric,
    verification_status: verification,
    temporal_status: temporal,
    metric_definition: metric.metric_definition ?? metric.label ?? "",
    comparability_group: metric.comparability_group ?? [metric.geography, metric.period, metric.unit, metric.currency, metric.metric_definition ?? metric.label].filter(Boolean).join("|"),
  };
}

function normalizeReportData(reportData) {
  if (!reportData) return null;
  const analysisDate = reportData.scope?.analysis_date;
  return {
    ...reportData,
    kpis: (reportData.kpis ?? []).map((metric) => normalizeMetric(metric, "kpis", analysisDate)),
    time_series: (reportData.time_series ?? []).map((series) => ({ ...series, points: (series.points ?? []).map((metric) => normalizeMetric(metric, "time_series", analysisDate)) })),
    market_segments: (reportData.market_segments ?? []).map((segment) => ({ ...segment, metrics: (segment.metrics ?? []).map((metric) => normalizeMetric(metric, "market_segments", analysisDate)) })),
  };
}

function dataFilename(runId, revision) {
  return `${createHash("sha256").update(runId).digest("hex").slice(0, 16)}-${revision}.json`;
}

async function candidateBundle(runFolder, runManifest, scope, revision, sourceFolder, revisionManifest, revisionCount) {
  const dashboard = await readJson(join(sourceFolder, "06_dashboard_data.json"));
  if (!dashboard?.report_data) return null;
  const qualityData = await readJson(join(sourceFolder, "05_quality_check.json"), {});
  const qualityStatus = qualityData.overall_status ?? revisionManifest?.quality_check_status ?? dashboard.quality_status ?? runManifest.quality_check_status ?? "UNKNOWN";
  const normalizedDashboard = { ...dashboard, report_data: normalizeReportData(dashboard.report_data), quality_status: qualityStatus };
  return sanitize({
    schema_version: "1.0",
    run_id: runManifest.run_id ?? runFolder.split(/[\\/]/).at(-1),
    revision,
    revision_count: revisionCount,
    scope,
    run_manifest: runManifest,
    revision_manifest: revisionManifest,
    quality: {
      overall_status: qualityStatus,
      quality_issues: qualityData.quality_issues ?? revisionManifest?.quality_issues ?? runManifest.quality_issues ?? [],
    },
    dashboard: normalizedDashboard,
  });
}

await mkdir(publicData, { recursive: true });
const catalog = { schema_version: "1.0", generated_at: new Date().toISOString(), reports: [] };
let runNames = [];
try { runNames = await readdir(outputsRoot); } catch { runNames = []; }

for (const runName of runNames) {
  const runFolder = join(outputsRoot, runName);
  const runManifest = await readJson(join(runFolder, "run_manifest.json"));
  if (!runManifest) continue;
  const scope = await readJson(join(runFolder, "00_analysis_scope.json"), {});
  const revisionsRoot = join(runFolder, "revisions");
  let revisions = [];
  if (existsSync(revisionsRoot)) {
    revisions = (await readdir(revisionsRoot)).filter((name) => /^rev_\d+$/.test(name)).sort();
  }
  const candidates = revisions.length ? revisions.map((revision) => ({ revision, folder: join(revisionsRoot, revision) })) : [{ revision: "current", folder: runFolder }];
  const prepared = [];
  for (const candidate of candidates) {
    const revisionManifest = candidate.revision === "current" ? null : await readJson(join(candidate.folder, "revision_manifest.json"), {});
    const bundle = await candidateBundle(runFolder, runManifest, scope, candidate.revision, candidate.folder, revisionManifest, 0);
    if (!bundle) continue;
    prepared.push({ candidate, revisionManifest, bundle });
  }
  for (const { candidate, revisionManifest, bundle } of prepared) {
    bundle.revision_count = prepared.length;
    const filename = dataFilename(bundle.run_id, candidate.revision);
    await writeFile(join(publicData, filename), `${JSON.stringify(bundle, null, 2)}\n`, "utf8");
    catalog.reports.push({
      run_id: bundle.run_id,
      topic: runManifest.topic ?? scope.topic ?? runName,
      revision: candidate.revision,
      revision_count: prepared.length,
      quality_status: bundle.quality.overall_status,
      final_status: revisionManifest?.final_status ?? runManifest.final_status ?? "UNKNOWN",
      analysis_date: scope.analysis_date ?? runManifest.analysis_date ?? "",
      industry: scope.industry ?? runManifest.industry ?? "",
      geography: scope.geography ?? runManifest.geography ?? "",
      data_url: `./data/${filename}`,
    });
  }
}

catalog.reports.sort((left, right) => left.run_id.localeCompare(right.run_id) || left.revision.localeCompare(right.revision));
await writeFile(join(publicData, "index.json"), `${JSON.stringify(sanitize(catalog), null, 2)}\n`, "utf8");
console.log(`Prepared ${catalog.reports.length} report revisions without Agent calls.`);
