import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "../components/EmptyState";
import { KpiSummary } from "../components/KpiSummary";
import { metric } from "./fixtures";

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
});
