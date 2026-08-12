import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const outputsRoot = process.env.STRATEGY_OUTPUTS_ROOT
  ? resolve(process.env.STRATEGY_OUTPUTS_ROOT)
  : join(projectRoot, "outputs");
const sampleRunsRoot = join(projectRoot, "examples", "sample_run");
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
    source_grade: String(metric.source_grade ?? "N/A").replace(/^GRADE_/, ""),
    verification_status: verification,
    temporal_status: temporal,
    metric_definition: metric.metric_definition ?? metric.label ?? "",
    comparability_group: metric.comparability_group ?? [metric.geography, metric.period, metric.unit, metric.currency, metric.metric_definition ?? metric.label].filter(Boolean).join("|"),
  };
}

function portableReportData(reportData, scope, dashboard) {
  if (reportData?.scope && Array.isArray(reportData.kpis)) return reportData;
  const metrics = reportData?.metrics ?? dashboard?.metrics ?? [];
  return {
    schema_version: "1.0",
    scope: {
      topic: scope.topic ?? dashboard?.meta?.topic ?? "Offline demo",
      analysis_type: scope.analysis_type_id ?? scope.analysis_type ?? dashboard?.meta?.analysis_type ?? "GENERIC_STRATEGY",
      industry: scope.industry ?? null,
      geography: scope.geography ?? "Testland",
      analysis_date: scope.analysis_date ?? "",
      selected_template: scope.selected_template ?? null,
    },
    executive_summary: dashboard?.meta?.topic ?? scope.topic ?? "Offline demo",
    kpis: metrics,
    time_series: reportData?.time_series ?? dashboard?.time_series ?? [],
    market_segments: reportData?.market_segments ?? dashboard?.segments ?? [],
    competitor_comparisons: reportData?.comparisons ?? dashboard?.comparisons ?? [],
    risks: reportData?.risks ?? dashboard?.risks ?? [],
    opportunities: reportData?.opportunities ?? dashboard?.opportunities ?? [],
    recommendations: reportData?.recommendations ?? dashboard?.recommendations ?? [],
    roadmap: reportData?.roadmap ?? dashboard?.initiatives ?? [],
    evidence_summary: { supported: metrics.length },
    data_gaps: reportData?.data_gaps ?? [],
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
  const dashboardSource = await readJson(join(sourceFolder, "06_dashboard_data.json"));
  if (!dashboardSource) return null;
  const reportDataSource = dashboardSource.report_data ?? await readJson(join(sourceFolder, "04_report_data.json"));
  if (!reportDataSource) return null;
  const qualityData = await readJson(join(sourceFolder, "05_quality_check.json"), {});
  const qualityStatus = qualityData.overall_status ?? qualityData.status ?? revisionManifest?.quality_check_status ?? dashboardSource.quality_status ?? runManifest.quality_check_status ?? "UNKNOWN";
  const reportData = portableReportData(reportDataSource, scope, dashboardSource);
  const normalizedDashboard = {
    ...dashboardSource,
    quality_status: qualityStatus,
    scope,
    report_version: dashboardSource.report_version ?? revision,
    template_id: dashboardSource.template_id ?? scope.selected_template ?? "general",
    components: dashboardSource.components ?? [],
    excluded_metrics: dashboardSource.excluded_metrics ?? [],
    validation_errors: dashboardSource.validation_errors ?? [],
    report_data: normalizeReportData(reportData),
  };
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
const runFolders = [
  ...runNames.map((name) => ({ name, folder: join(outputsRoot, name), isSample: false })),
  { name: "sample_run", folder: sampleRunsRoot, isSample: true },
];

for (const runEntry of runFolders) {
  const runName = runEntry.name;
  const runFolder = runEntry.folder;
  const scope = await readJson(join(runFolder, "00_analysis_scope.json"), {});
  const sampleDashboard = runEntry.isSample ? await readJson(join(runFolder, "06_dashboard_data.json"), {}) : {};
  const runManifest = await readJson(join(runFolder, "run_manifest.json")) ?? (runEntry.isSample ? {
    schema_version: "2.0",
    run_id: sampleDashboard.meta?.run_id ?? "public_fixture_company_strategy",
    topic: scope.topic ?? sampleDashboard.meta?.topic ?? "Offline demo",
    industry: scope.industry ?? "",
    geography: scope.geography ?? "",
    analysis_date: scope.analysis_date ?? "",
    final_status: "COMPLETED",
    quality_check_status: "PASS",
    is_test_fixture: true,
  } : null);
  if (!runManifest) continue;
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
