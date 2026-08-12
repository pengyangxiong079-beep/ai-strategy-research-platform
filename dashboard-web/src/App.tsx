import { useEffect, useMemo, useState } from "react";
import type { Catalog, ReportBundle } from "./types";
import { embeddedPayload, loadBundle, loadCatalog } from "./lib/loader";
import { hasDataset, toDashboardView } from "./lib/validation";
import { getAvailablePages, getDashboardTemplate } from "./templates";
import type { DisplayCondition } from "./templates/types";
import { WidgetRenderer } from "./components/WidgetRenderer";
import { EmptyState } from "./components/EmptyState";
import { DecisionBrief } from "./components/DecisionBrief";

function initialQuery() {
  const query = new URLSearchParams(window.location.search);
  const hashQuery = new URLSearchParams(window.location.hash.replace(/^#\??/, ""));
  const embeddedSelection = embeddedPayload()?.selected_key?.split("::") ?? [];
  return {
    runId: query.get("run_id") ?? hashQuery.get("run_id") ?? embeddedSelection[0] ?? "",
    revision: query.get("revision") ?? hashQuery.get("revision") ?? embeddedSelection[1] ?? "",
  };
}

function conditionMatches(condition: DisplayCondition, view: NonNullable<ReturnType<typeof toDashboardView>>) {
  if (condition.operator === "NON_EMPTY") return hasDataset(view, condition.dataset);
  const value = view[condition.dataset as keyof typeof view];
  if (condition.operator === "MIN_ITEMS") return Array.isArray(value) && value.length >= Number(condition.value ?? 1);
  return String(value) === String(condition.value);
}

function App() {
  const query = initialQuery();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [bundle, setBundle] = useState<ReportBundle | null>(null);
  const [runId, setRunId] = useState(query.runId);
  const [revision, setRevision] = useState(query.revision);
  const [page, setPage] = useState("");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [theme, setTheme] = useState<"light" | "dark">(() => window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const [error, setError] = useState("");

  useEffect(() => {
    loadCatalog().then((loaded) => {
      setCatalog(loaded);
      const selectedRun = runId && loaded.reports.some((item) => item.run_id === runId) ? runId : loaded.reports[0]?.run_id ?? "";
      const revisions = loaded.reports.filter((item) => item.run_id === selectedRun);
      const selectedRevision = revision && revisions.some((item) => item.revision === revision) ? revision : revisions.at(-1)?.revision ?? "";
      setRunId(selectedRun);
      setRevision(selectedRevision);
    }).catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  const entriesForRun = useMemo(() => catalog?.reports.filter((item) => item.run_id === runId) ?? [], [catalog, runId]);

  useEffect(() => {
    if (!catalog || !runId || !revision) return;
    const entry = catalog.reports.find((item) => item.run_id === runId && item.revision === revision);
    if (!entry) return;
    setError("");
    loadBundle(entry.data_url, runId, revision).then(setBundle).catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
    if (location.protocol !== "blob:") {
      const params = new URLSearchParams({ run_id: runId, revision });
      history.replaceState(null, "", `${location.pathname}?${params}`);
    }
  }, [catalog, runId, revision]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
  }, [theme, language]);

  const view = useMemo(() => bundle ? toDashboardView(bundle.dashboard) : null, [bundle]);
  const analysisType = bundle?.dashboard.meta?.analysis_type ?? view?.report.scope.analysis_type ?? bundle?.scope.analysis_type;
  const template = getDashboardTemplate(analysisType);
  const availablePages = useMemo(
    () => getAvailablePages(template, bundle?.revision_count ?? 0),
    [template, bundle?.revision_count],
  );

  useEffect(() => {
    if (!availablePages.length) return;
    if (!availablePages.some((item) => item.id === page)) setPage(availablePages[0].id);
  }, [availablePages, page]);

  const scope = view?.report.scope ?? bundle?.scope ?? {};
  const quality = bundle?.quality.overall_status ?? "UNKNOWN";
  const workflowStatus = String(bundle?.revision_manifest?.final_status ?? bundle?.run_manifest.final_status ?? "UNKNOWN");
  const currentPage = availablePages.find((item) => item.id === page) ?? availablePages[0];
  const missingRequired = view ? template.requiredDatasets.filter((dataset) => !hasDataset(view, dataset)) : template.requiredDatasets;

  const changeRun = (nextRun: string) => {
    setRunId(nextRun);
    const revisions = catalog?.reports.filter((item) => item.run_id === nextRun) ?? [];
    setRevision(revisions.at(-1)?.revision ?? "");
    setPage("");
  };

  const renderPage = () => {
    if (!bundle || !catalog || !view || !currentPage) return <EmptyState reason="当前运行尚无可验证的结构化看板数据。" />;
    const visibleWidgets = currentPage.widgets
      .filter((spec) => !spec.showWhen || spec.showWhen.every((condition) => conditionMatches(condition, view)))
      .sort((left, right) => left.priority - right.priority)
      .filter((spec) => spec.required || hasDataset(view, spec.dataset));
    return (
      <>
        <section className="page-purpose"><strong>{currentPage.label}</strong><p>{currentPage.purpose}</p></section>
        {currentPage.id === availablePages[0]?.id && <DecisionBrief view={view} />}
        <div className="page-widgets">
          {visibleWidgets.length ? visibleWidgets.map((spec) => (
            <WidgetRenderer key={spec.id} spec={spec} view={view} locale={language} catalog={catalog} current={bundle} />
          )) : <EmptyState reason={template.emptyStateMessage} />}
        </div>
      </>
    );
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span>STRATEGY RESEARCH</span><strong>{language === "en" ? template.title.replace("看板", "Dashboard") : template.title}</strong></div>
        <div className="header-actions">
          <button onClick={() => setLanguage(language === "zh" ? "en" : "zh")} aria-label="切换中英文">{language === "zh" ? "EN" : "中文"}</button>
          <button onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label="切换深色和浅色主题">{theme === "light" ? "深色" : "浅色"}</button>
          <button onClick={() => window.print()}>打印 / PDF</button>
        </div>
      </header>
      <section className="report-selector" aria-label="报告选择">
        <label>{language === "en" ? "Analysis" : "分析对象"}<select value={runId} onChange={(event) => changeRun(event.target.value)}>{[...new Map(catalog?.reports.map((entry) => [entry.run_id, entry]) ?? []).values()].map((entry) => <option value={entry.run_id} key={entry.run_id}>{entry.topic}</option>)}</select></label>
        <label>Revision<select value={revision} onChange={(event) => setRevision(event.target.value)}>{entriesForRun.map((entry) => <option value={entry.revision} key={entry.revision}>{entry.revision}</option>)}</select></label>
        <dl>
          <div><dt>分析类型</dt><dd>{template.id}</dd></div><div><dt>行业</dt><dd>{String(scope.industry ?? "—")}</dd></div>
          <div><dt>地区</dt><dd>{String(scope.geography ?? "—")}</dd></div><div><dt>基准日</dt><dd>{String(scope.analysis_date ?? "—")}</dd></div>
          <div><dt>时间范围</dt><dd>{String(scope.time_horizon ?? "—")}</dd></div><div><dt>Revision</dt><dd>{bundle?.revision ?? "—"}</dd></div>
          <div><dt>工作流</dt><dd>{workflowStatus}</dd></div><div><dt>Quality</dt><dd><span className={`status ${quality.toLowerCase()}`}>{quality}</span></dd></div>
        </dl>
      </section>
      {quality === "FAIL" && <div className="quality-banner fail">Quality Check为FAIL：失败字段已从主图排除，看板保留为审阅草稿。</div>}
      {quality === "WARN" && <div className="quality-banner warn">存在质量警告；PARTIAL数据带提示，请结合Evidence Quality页面解读。</div>}
      {missingRequired.length > 0 && <div className="dataset-banner">模板核心数据缺口：{missingRequired.join("、")}。核心组件将显示Empty State，非核心组件自动隐藏。</div>}
      <section className="decision-question"><span>核心决策问题</span><strong>{template.decisionQuestion}</strong></section>
      <nav className="page-nav" aria-label="Dashboard pages">{availablePages.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} aria-current={page === item.id ? "page" : undefined} onClick={() => setPage(item.id)}>{language === "en" ? item.labelEn ?? item.label : item.label}</button>)}</nav>
      <main><header className="page-heading"><div><span>{template.id}</span><h1>{String(scope.topic ?? "战略研究报告")}</h1></div><p>{bundle?.revision} · {bundle?.dashboard.dashboard_status}</p></header>{error ? <EmptyState reason={error} /> : renderPage()}</main>
      <footer className="site-footer">结构化战略看板 · 不从Markdown提取数字 · {new Date().getFullYear()}</footer>
    </div>
  );
}

export default App;
