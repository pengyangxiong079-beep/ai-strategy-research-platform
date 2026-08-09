import type { DashboardPageSpec, DashboardTemplate, WidgetSpec } from "./types";

export function widget(
  id: string,
  component: string,
  title: string,
  dataset: WidgetSpec["dataset"],
  priority: number,
  required = false,
  emptyState?: string,
): WidgetSpec {
  return {
    id, component, title, dataset, priority, required, emptyState,
    evidencePolicy: { allowPartial: true, requireSources: true },
  };
}

export const evidencePage: DashboardPageSpec = {
  id: "evidence",
  label: "证据质量",
  labelEn: "Evidence quality",
  purpose: "解释数据支持程度、来源等级、质量问题和被排除字段。",
  widgets: [
    widget("evidence-status", "EvidenceStatusChart", "证据核验状态", "evidence", 1, true),
    widget("source-grade", "SourceGradeChart", "来源等级分布", "evidence", 2, false),
    widget("quality-issues", "QualityIssuePanel", "质量检查问题", "quality", 3, true),
    widget("data-gaps", "DataGapPanel", "数据缺口与排除项", "data_gaps", 4, true),
  ],
};

export const revisionPage: DashboardPageSpec = {
  id: "revision",
  label: "版本比较",
  labelEn: "Revision comparison",
  purpose: "比较同一运行中结构化字段、证据状态和战略建议的变化。",
  widgets: [widget("revision-diff", "RevisionComparison", "Revision变化", "revision", 1, true)],
};

export function finalizeTemplate(
  template: Omit<DashboardTemplate, "allowedComponents">,
): DashboardTemplate {
  const pages = [...template.pages, evidencePage, revisionPage];
  return {
    ...template,
    pages,
    allowedComponents: [...new Set(pages.flatMap((page) => page.widgets.map((item) => item.component)))],
  };
}

