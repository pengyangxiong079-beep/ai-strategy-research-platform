import type { ReactNode } from "react";
import type { Catalog, ReportBundle } from "../types";
import type { WidgetSpec } from "../templates/types";
import { datasetValue, type DashboardView } from "../lib/validation";
import { KpiSummary } from "./KpiSummary";
import { TimeSeriesChart } from "./TimeSeriesChart";
import { StackedCompositionChart } from "./StackedCompositionChart";
import { DotComparisonChart } from "./DotComparisonChart";
import { CompetitorHeatmap } from "./CompetitorHeatmap";
import { RiskMatrix } from "./RiskMatrix";
import { StrategyTimeline } from "./StrategyTimeline";
import { EvidenceStatusChart } from "./EvidenceStatusChart";
import { SourceGradeChart } from "./SourceGradeChart";
import { DataGapPanel } from "./DataGapPanel";
import { RevisionComparison } from "./RevisionComparison";
import { EmptyState } from "./EmptyState";
import { AdaptivePriceChart } from "./AdaptivePriceChart";
import { DataCoverageChart, EntityEvidenceChart, ObservationCoverageChart } from "./EvidenceCoverageCharts";
import {
  GeographicMap, HorizontalBarChart, OpportunityMatrix, PortfolioMatrix,
  InitiativeRoadmap, PositioningMatrix, QualityIssuePanel, RecommendationsPanel,
  ScenarioChart, SlopeChart, ValueChainDiagram, WaterfallChart,
} from "./StrategicWidgets";

interface Props {
  spec: WidgetSpec;
  view: DashboardView;
  locale: string;
  catalog: Catalog;
  current: ReportBundle;
}

export function WidgetRenderer({ spec, view, locale, catalog, current }: Props) {
  const components: Record<string, () => ReactNode> = {
    KpiSummary: () => <KpiSummary metrics={view.metrics} locale={locale} />,
    TimeSeriesChart: () => <TimeSeriesChart series={view.time_series} />,
    StackedCompositionChart: () => <StackedCompositionChart segments={view.segments} />,
    HorizontalBarChart: () => <HorizontalBarChart comparisons={view.comparisons} />,
    SlopeChart: () => <SlopeChart series={view.time_series} />,
    DotComparisonChart: () => <DotComparisonChart comparisons={view.comparisons} />,
    CompetitorHeatmap: () => <CompetitorHeatmap comparisons={view.comparisons} />,
    AdaptivePriceChart: () => <AdaptivePriceChart observations={view.observations} coverage={view.data_coverage} />,
    PositioningMatrix: () => <PositioningMatrix matrices={view.matrices} title={spec.title} />,
    PortfolioMatrix: () => <PortfolioMatrix matrices={view.matrices} />,
    RiskMatrix: () => <RiskMatrix risks={view.risks} opportunities={view.opportunities} />,
    OpportunityMatrix: () => <OpportunityMatrix opportunities={view.opportunities} />,
    ScenarioChart: () => <ScenarioChart scenarios={view.scenarios} />,
    WaterfallChart: () => <WaterfallChart metrics={view.metrics} />,
    GeographicMap: () => <GeographicMap geographies={view.geographies} />,
    ValueChainDiagram: () => <ValueChainDiagram items={view.strategic_options} />,
    StrategyTimeline: () => <StrategyTimeline items={view.initiatives} />,
    InitiativeRoadmap: () => <InitiativeRoadmap initiatives={view.initiatives} />,
    RecommendationsPanel: () => <RecommendationsPanel recommendations={view.recommendations} />,
    EvidenceStatusChart: () => <EvidenceStatusChart summary={view.evidence_summary} />,
    SourceGradeChart: () => <SourceGradeChart report={view.report} observations={view.observations} />,
    DataCoverageChart: () => <DataCoverageChart coverage={view.data_coverage} />,
    ObservationCoverageChart: () => <ObservationCoverageChart observations={view.observations} />,
    EntityEvidenceChart: () => <EntityEvidenceChart observations={view.observations} />,
    QualityIssuePanel: () => <QualityIssuePanel issues={(view.quality.quality_issues ?? []) as Array<Record<string, unknown>>} />,
    DataGapPanel: () => <DataGapPanel gaps={view.data_gaps} excluded={view.excluded} />,
    RevisionComparison: () => <RevisionComparison catalog={catalog} current={current} />,
  };
  const render = components[spec.component];
  if (!render) return <EmptyState reason={`组件 ${spec.component} 尚未注册。`} />;
  const dataset = datasetValue(view, spec.dataset);
  const empty = Array.isArray(dataset) ? dataset.length === 0 : !dataset;
  const availability = view.visual_availability[spec.dataset];
  if (empty && availability && availability.status !== "AVAILABLE") {
    const action = availability.required_action ? ` 建议：${availability.required_action}` : "";
    return <div className="widget-block" data-widget={spec.id} aria-label={spec.title}><EmptyState title={`${spec.title}暂不可用`} reason={`${availability.reason}${action}`} /></div>;
  }
  return <div className="widget-block" data-widget={spec.id} aria-label={spec.title}>{render()}</div>;
}
