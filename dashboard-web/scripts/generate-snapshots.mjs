import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const dashboardRoot = join(projectRoot, "dashboard-web");
const baseHtml = await readFile(join(dashboardRoot, "dist", "index.html"), "utf8");
const catalog = JSON.parse(await readFile(join(dashboardRoot, "public", "data", "index.json"), "utf8"));
const reports = {};
for (const entry of catalog.reports) {
  const filename = entry.data_url.split("/").at(-1);
  reports[`${entry.run_id}::${entry.revision}`] = JSON.parse(await readFile(join(dashboardRoot, "public", "data", filename), "utf8"));
}

function safeJson(value) {
  return JSON.stringify(value).replaceAll("<", "\\u003c").replaceAll("\u2028", "\\u2028").replaceAll("\u2029", "\\u2029");
}

let count = 0;
for (const entry of catalog.reports) {
  const runEntries = catalog.reports.filter((item) => item.run_id === entry.run_id);
  const runReports = Object.fromEntries(runEntries.map((item) => [`${item.run_id}::${item.revision}`, reports[`${item.run_id}::${item.revision}`]]));
  const embedded = { catalog: { ...catalog, reports: runEntries }, reports: runReports, selected_key: `${entry.run_id}::${entry.revision}` };
  const script = `<script id="dashboard-embedded-data" type="application/json">${safeJson(embedded)}</script>`;
  const html = baseHtml.replace("</head>", `${script}</head>`);
  const runFolder = join(projectRoot, "outputs", entry.run_id);
  const destination = entry.revision === "current"
    ? join(runFolder, "dashboard", "dashboard.html")
    : join(runFolder, "revisions", entry.revision, "dashboard", "dashboard.html");
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, html, "utf8");
  count += 1;
  if (entry.revision === runEntries.at(-1)?.revision) {
    const latestDestination = join(runFolder, "dashboard", "dashboard.html");
    await mkdir(dirname(latestDestination), { recursive: true });
    await writeFile(latestDestination, html, "utf8");
  }
}
console.log(`Generated ${count} offline dashboard snapshots.`);
