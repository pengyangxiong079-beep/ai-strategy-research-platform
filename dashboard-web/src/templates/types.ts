import type { AnalysisType } from "../types";

export type DashboardDataset =
  | "metrics" | "time_series" | "comparisons" | "matrices" | "segments"
  | "geographies" | "risks" | "opportunities" | "strategic_options"
  | "recommendations" | "initiatives" | "scenarios" | "evidence"
  | "quality" | "revision" | "data_gaps" | "observations" | "data_coverage";

export interface DisplayCondition {
  dataset: DashboardDataset;
  operator: "NON_EMPTY" | "MIN_ITEMS" | "EQUALS";
  value?: number | string | boolean;
}

export interface EvidencePolicy {
  allowPartial?: boolean;
  requireComparable?: boolean;
  requireSources?: boolean;
}

export interface ComparisonRule {
  fields: string[];
  behavior: "NO_RANKING" | "HIDE" | "ANNOTATE";
  message: string;
}

export interface WidgetSpec {
  id: string;
  component: string;
  title: string;
  dataset: DashboardDataset;
  priority: number;
  required: boolean;
  showWhen?: DisplayCondition[];
  evidencePolicy?: EvidencePolicy;
  emptyState?: string;
}

export interface DashboardPageSpec {
  id: string;
  label: string;
  labelEn?: string;
  purpose: string;
  widgets: WidgetSpec[];
}

export interface DashboardTemplate {
  id: AnalysisType;
  title: string;
  decisionQuestion: string;
  storyline: string[];
  pages: DashboardPageSpec[];
  priorityMetrics: string[];
  requiredDatasets: DashboardDataset[];
  optionalDatasets: DashboardDataset[];
  allowedComponents: string[];
  comparisonRules?: ComparisonRule[];
  emptyStateMessage: string;
}
