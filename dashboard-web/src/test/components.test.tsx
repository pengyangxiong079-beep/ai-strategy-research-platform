import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "../components/EmptyState";
import { KpiSummary } from "../components/KpiSummary";
import { metric } from "./fixtures";
import { DataCoverageChart, EntityEvidenceChart } from "../components/EvidenceCoverageCharts";

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
});
