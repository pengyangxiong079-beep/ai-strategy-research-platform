import type { ValueType } from "../types";

export const valueTypeStyles: Record<ValueType, { color: string; lineType: "solid" | "dashed" | "dotted"; label: string }> = {
  ACTUAL: { color: "#2563eb", lineType: "solid", label: "实际" },
  HISTORICAL: { color: "#1d4ed8", lineType: "solid", label: "历史" },
  FORECAST: { color: "#7c3aed", lineType: "dashed", label: "预测" },
  TARGET: { color: "#dc2626", lineType: "dotted", label: "目标" },
  SCENARIO: { color: "#d97706", lineType: "dashed", label: "情景" },
  ESTIMATE: { color: "#0891b2", lineType: "dotted", label: "估算" },
  PROXY: { color: "#64748b", lineType: "dotted", label: "代理指标" },
  UNKNOWN: { color: "#64748b", lineType: "dotted", label: "未知" },
};

export const gradeColors: Record<string, string> = {
  A: "#15803d",
  B: "#2563eb",
  C: "#d97706",
  D: "#dc2626",
  "N/A": "#64748b",
};
