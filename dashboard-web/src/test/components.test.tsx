import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "../components/EmptyState";
import { KpiSummary } from "../components/KpiSummary";
import { metric } from "./fixtures";
import { DataCoverageChart, EntityEvidenceChart } from "../components/EvidenceCoverageCharts";
import { DecisionBrief } from "../components/DecisionBrief";
import { ScenarioChart } from "../components/StrategicWidgets";
import { WidgetRenderer } from "../components/WidgetRenderer";
import { toDashboardView } from "../lib/validation";
import { bundle, catalog } from "./fixtures";

vi.mock("../components/EChart", () => ({ EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));

describe("responsive components", () => {
  it("shows an explicit empty state", () => {
    render(<EmptyState reason="缺少真实数据" />);
    expect(screen.getByText("缺少真实数据")).toBeInTheDocument();
  });

  it("shows no more than four KPI cards with provenance", () => {
    render(<KpiSummary metrics={[1, 2, 3, 4].map((index) => metric({ metric_id: `M${index}`, label: `KPI ${index}` }))} locale="zh" />);
    expect(screen.getAllByText(/KPI \d/)).toHaveLength(4);
    expect(screen.getAllByText(/F1 · 来源等级 A/)).toHaveLength(4);
  });

  it("renders professional coverage charts without inventing market rankings", () => {
    const { rerender } = render(<DataCoverageChart coverage={{ datasets: [{ dataset_id: "market_size", priority: "CRITICAL", status: "PASS", entity_count: 1, observation_count: 9, comparability_rate: 1, dashboard_readiness: { TimeSeriesChart: true }, gaps: [] }] }} />);
    expect(screen.getByText("数据集覆盖与看板就绪度")).toBeInTheDocument();
    rerender(<EntityEvidenceChart observations={[{ observation_id: "O1", dataset_id: "major_players", entity: "品牌A", metric: "market_position", product_name: "", category: "", value: null, text_value: "公开披露", unit: "", currency: "", period: "2025", geography: "China", channel: "", price_type: "", verification_status: "SUPPORTED", temporal_status: "CURRENT", comparability_group: "", source_id: "S1", source_url: "https://example.test", source_grade: "GRADE_A", notes: "" }]} />);
    expect(screen.getByText(/不代表市场规模、企业排名或战略评分/)).toBeInTheDocument();
  });

  it("turns recommendations, evidence and gaps into a conditional management decision", () => {
    const fixture = bundle();
    const report = fixture.dashboard.report_data!;
    report.recommendations = [{ item_id: "R1", label: "先试点后扩张", description: "以里程碑控制资本暴露。", priority: "P0", source_fact_ids: ["F1"] }];
    report.data_gaps = [{ gap_id: "G1", label: "渠道转化率", reason: "尚无付费样板", required_action: "完成两个样板项目" }];
    const view = toDashboardView(fixture.dashboard)!;
    render(<DecisionBrief view={view} />);
    expect(screen.getByText("有条件推进")).toBeInTheDocument();
    expect(screen.getByText("先试点后扩张")).toBeInTheDocument();
    expect(screen.getByText(/完成两个样板项目/)).toBeInTheDocument();
  });

  it("shows scenario assumptions and decision triggers beside modelled outcomes", () => {
    const scenarioMetric = metric({ value_type: "SCENARIO", temporal_status: "FUTURE_PLAN" });
    render(<ScenarioChart scenarios={[{
      scenario_id: "S1", label: "基准情景", assumptions: ["转化率达到18%"],
      trigger_conditions: ["两个付费样板达标"], source_fact_ids: ["F1"], confidence: "MEDIUM",
      points: [{ ...scenarioMetric, metric_id: "S1A", period: "2027" }, { ...scenarioMetric, metric_id: "S1B", period: "2029", value: 4.1 }],
    }]} />);
    expect(screen.getByText("关键假设").parentElement).toHaveTextContent("转化率达到18%");
    expect(screen.getByText("触发条件").parentElement).toHaveTextContent("两个付费样板达标");
  });

  it("shows qualitative scenario cards without inventing chart points", () => {
    render(<ScenarioChart scenarios={[{
      scenario_id: "S2", label: "审慎情景", value_type: "QUALITATIVE",
      assumptions: ["资本回报证据不足"], trigger_conditions: ["利用率未达内部门槛"],
      implications: "暂停未经验证的扩张", actions: ["优先补全证据"],
      source_fact_ids: [], confidence: "LOW", points: [],
    }]} />);
    expect(screen.getByText("证据不足以支持数值预测，以下为定性决策情景")).toBeInTheDocument();
    expect(screen.getByText("审慎情景")).toBeInTheDocument();
    expect(screen.getByText("战略影响").parentElement).toHaveTextContent("暂停未经验证的扩张");
    expect(screen.getByText("应对行动").parentElement).toHaveTextContent("优先补全证据");
  });

  it("uses canonical availability to explain an empty required widget", () => {
    const fixture = bundle();
    fixture.dashboard.component_availability = {
      matrices: {
        status: "PARTIAL", reason: "已有证据，但缺少统一的二维评分口径。",
        required_action: "补充同期间、同口径的两个维度。",
      },
    };
    const view = toDashboardView(fixture.dashboard)!;
    render(<WidgetRenderer
      spec={{ id: "portfolio", component: "PortfolioMatrix", title: "业务组合", dataset: "matrices", priority: 1, required: true }}
      view={view} locale="zh" catalog={catalog()} current={fixture}
    />);
    expect(screen.getByText("业务组合暂不可用")).toBeInTheDocument();
    expect(screen.getByText(/补充同期间、同口径的两个维度/)).toBeInTheDocument();
  });
});
