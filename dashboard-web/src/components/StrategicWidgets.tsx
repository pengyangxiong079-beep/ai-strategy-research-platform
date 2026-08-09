import { useMemo } from "react";
import type {
  CompetitorComparison, GeographyDatum, MatrixDataset, Metric, Recommendation,
  RoadmapItem, Scenario, StrategicItem, TimeSeries,
} from "../types";
import { comparisonCanRank, validateMetric } from "../lib/validation";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";
import { StrategyTimeline } from "./StrategyTimeline";

export function HorizontalBarChart({ comparisons }: { comparisons: CompetitorComparison[] }) {
  const comparison = comparisons.find(comparisonCanRank);
  const option = useMemo(() => comparison ? {
    tooltip: { formatter: (item: { name: string; value: number }) => `${item.name}: ${item.value} ${comparison.unit ?? ""}<br/>${comparison.period} · ${comparison.geography}<br/>${comparison.comparison_basis}<br/>${comparison.source_fact_ids.join("、")}` },
    grid: { left: 118, right: 28, top: 24, bottom: 48 },
    xAxis: { type: "value" as const, name: [comparison.unit, comparison.currency].filter(Boolean).join(" ") },
    yAxis: { type: "category" as const, data: comparison.values?.filter((item) => typeof item.value === "number").map((item) => item.entity) },
    series: [{ type: "bar", data: comparison.values?.filter((item) => typeof item.value === "number").map((item) => item.value), itemStyle: { color: "#2563eb" } }],
  } : null, [comparison]);
  if (!option || !comparison) return <EmptyState reason="缺少可比的条形图数据；不可比值仅保留在证据说明中。" />;
  return <section className="panel"><header><h2>{comparison.metric}</h2><p>{comparison.comparison_basis}</p></header><EChart option={option} ariaLabel={`${comparison.metric}横向比较图`} /><p className="source-note">来源：{comparison.source_fact_ids.join("、")}</p></section>;
}

export function SlopeChart({ series }: { series: TimeSeries[] }) {
  const usable = series.filter((item) => item.points.filter((point) => !validateMetric(point).length).length === 2);
  const periods = [...new Set(usable.flatMap((item) => item.points.map((point) => point.period ?? "")))];
  const option = useMemo(() => usable.length && periods.length === 2 ? {
    tooltip: { trigger: "axis" as const }, legend: { type: "scroll" as const },
    grid: { left: 55, right: 35, top: 52, bottom: 52 },
    xAxis: { type: "category" as const, data: periods }, yAxis: { type: "value" as const, name: usable[0]?.points[0]?.unit ?? "" },
    series: usable.map((item) => ({ name: item.label, type: "line", data: periods.map((period) => item.points.find((point) => point.period === period)?.value ?? null), symbolSize: 9 })),
  } : null, [usable, periods]);
  if (!option) return <EmptyState reason="Slope Chart需要至少一组口径一致且恰好包含两个期间的数据。" />;
  return <section className="panel"><header><h2>两期变化</h2><p>仅比较相同指标定义、单位与地区</p></header><EChart option={option} ariaLabel="两期指标变化斜率图" /></section>;
}

export function PositioningMatrix({ matrices, title = "定位矩阵" }: { matrices: MatrixDataset[]; title?: string }) {
  const matrix = matrices.find((item) => item.points?.some((point) => typeof point.x === "number" && typeof point.y === "number" && point.methodology));
  const option = useMemo(() => matrix ? {
    tooltip: { formatter: (item: { data: { value: [number, number, number]; label: string; facts: string[]; methodology: string } }) => `${item.data.label}<br/>X: ${item.data.value[0]} · Y: ${item.data.value[1]}<br/>${item.data.methodology}<br/>${item.data.facts.join("、")}` },
    grid: { left: 58, right: 30, top: 35, bottom: 55 },
    xAxis: { type: "value" as const, name: matrix.points[0]?.x_label ?? "维度 X", splitLine: { show: true } },
    yAxis: { type: "value" as const, name: matrix.points[0]?.y_label ?? "维度 Y", splitLine: { show: true } },
    series: [{ type: "scatter", symbolSize: (value: number[]) => Math.max(12, Math.min(42, value[2] || 18)), data: matrix.points.filter((point) => typeof point.x === "number" && typeof point.y === "number").map((point) => ({ value: [point.x, point.y, point.size ?? 18], label: point.label, facts: point.source_fact_ids, methodology: point.methodology, itemStyle: { borderType: point.is_analyst_judgment ? "dashed" : "solid" } })), label: { show: true, formatter: (item: { data: { label: string } }) => item.data.label, position: "top" as const } }],
  } : null, [matrix]);
  if (!matrix || !option) return <EmptyState reason="缺少具有透明评分依据和来源的二维定位数据，因此不自动生成气泡位置。" />;
  return <section className="panel"><header><h2>{matrix.label || title}</h2><p>{matrix.points.some((item) => item.is_analyst_judgment) ? "含分析师判断；悬停查看方法与来源" : "基于结构化指标"}</p></header><EChart option={option} ariaLabel={`${matrix.label || title}二维定位图`} /></section>;
}

export function PortfolioMatrix(props: { matrices: MatrixDataset[] }) {
  return <PositioningMatrix {...props} title="业务组合矩阵" />;
}

export function OpportunityMatrix({ opportunities }: { opportunities: StrategicItem[] }) {
  if (!opportunities.length) return <EmptyState reason="缺少结构化机会条目；不会自动生成机会评分。" />;
  return <section className="panel"><h2>战略机会</h2><div className="recommendations">{opportunities.map((item) => <article key={item.item_id}><strong>{item.label}</strong><p>{item.description}</p><small>{item.priority ?? "优先级待判断"} · {item.source_fact_ids.join("、") || "无事实编号"}</small></article>)}</div></section>;
}

export function ScenarioChart({ scenarios }: { scenarios: Scenario[] }) {
  const usable = scenarios.filter((scenario) => (scenario.points ?? []).filter((point) => !validateMetric(point).length).length > 1);
  const periods = [...new Set(usable.flatMap((scenario) => scenario.points?.map((point) => point.period ?? "") ?? []))];
  const option = useMemo(() => usable.length ? {
    tooltip: { trigger: "axis" as const },
    legend: { type: "scroll" as const },
    grid: { left: 56, right: 24, top: 52, bottom: 52 },
    xAxis: { type: "category" as const, data: periods, name: "期间" },
    yAxis: { type: "value" as const, name: usable[0].points?.[0]?.unit ?? "" },
    series: usable.map((scenario) => ({ name: scenario.label, type: "line", lineStyle: { type: "dashed" }, data: periods.map((period) => scenario.points?.find((point) => point.period === period)?.value ?? null) })),
  } : null, [usable, periods]);
  if (!option) return <EmptyState reason="缺少保守、基准或乐观情景的结构化假设与至少两个时间点。" />;
  return <section className="panel"><header><h2>情景分析</h2><p>虚线表示情景或未来计划；不是历史事实</p></header><EChart option={option} ariaLabel="战略情景趋势图" /></section>;
}

export function WaterfallChart({ metrics }: { metrics: Metric[] }) {
  const deltas = metrics.filter((metric) => metric.is_delta === true && !validateMetric(metric).length);
  const option = useMemo(() => deltas.length ? {
    tooltip: { trigger: "axis" as const },
    grid: { left: 56, right: 20, top: 30, bottom: 72 },
    xAxis: { type: "category" as const, data: deltas.map((item) => item.label), axisLabel: { rotate: 22 } },
    yAxis: { type: "value" as const, name: deltas[0]?.unit ?? "" },
    series: [{ type: "bar", data: deltas.map((item) => ({ value: item.value, itemStyle: { color: (item.value ?? 0) >= 0 ? "#157347" : "#b42318" } })) }],
  } : null, [deltas]);
  if (!option) return <EmptyState reason="缺少明确标记为增量（is_delta）的可追溯数据，因此不生成伪造的瀑布分解。" />;
  return <section className="panel"><header><h2>贡献分解</h2><p>仅显示可验证增量，不推算缺失桥接项</p></header><EChart option={option} ariaLabel="贡献增减瀑布图" /></section>;
}

export function GeographicMap({ geographies }: { geographies: GeographyDatum[] }) {
  const points = geographies.filter((item) => typeof item.longitude === "number" && typeof item.latitude === "number" && typeof item.value === "number");
  const option = useMemo(() => points.length ? {
    tooltip: { formatter: (item: { data: { name: string; value: [number, number, number]; facts: string[]; unit?: string | null } }) => `${item.data.name}: ${item.data.value[2]} ${item.data.unit ?? ""}<br/>${item.data.facts.join("、")}` },
    grid: { left: 52, right: 25, top: 25, bottom: 52 },
    xAxis: { type: "value" as const, name: "经度" },
    yAxis: { type: "value" as const, name: "纬度" },
    series: [{ type: "scatter", symbolSize: (value: number[]) => Math.max(10, Math.min(38, Math.sqrt(Math.abs(value[2])) * 2)), data: points.map((item) => ({ name: item.label, value: [item.longitude, item.latitude, item.value], facts: item.source_fact_ids, unit: item.unit })), label: { show: true, formatter: "{b}", position: "top" as const } }],
  } : null, [points]);
  if (!option) return <EmptyState reason="缺少带经纬度、期间和来源的地区数据，无法绘制地理分布。" />;
  return <section className="panel"><header><h2>地区机会分布</h2><p>点大小表示结构化指标值</p></header><EChart option={option} ariaLabel="地区机会地理分布图" /></section>;
}

export function ValueChainDiagram({ items }: { items: StrategicItem[] }) {
  if (!items.length) return <EmptyState reason="缺少结构化价值链环节与来源。" />;
  return <section className="value-chain panel" aria-label="价值链图">{items.map((item, index) => <article key={item.item_id}><span>{index + 1}</span><strong>{item.label}</strong><p>{item.description}</p><small>{item.source_fact_ids.join("、")}</small></article>)}</section>;
}

export function RecommendationsPanel({ recommendations }: { recommendations: Recommendation[] }) {
  if (!recommendations.length) return <EmptyState reason="缺少结构化战略建议。" />;
  return <section className="panel"><h2>战略建议</h2><div className="recommendations">{recommendations.map((item) => <article key={item.recommendation_id ?? item.item_id}><div className="recommendation-title"><strong>{item.title ?? item.label}</strong><span className="badge">{item.priority ?? "待排序"}</span></div><p>{item.rationale ?? item.description}</p><dl><div><dt>时间</dt><dd>{item.time_horizon ?? item.timeframe ?? "待定"}</dd></div><div><dt>责任</dt><dd>{item.responsible_function ?? item.owner ?? "待定"}</dd></div><div><dt>KPI</dt><dd>{item.kpi ?? "待定义"}</dd></div></dl>{Boolean(item.required_capabilities?.length) && <small>所需能力：{item.required_capabilities?.join("、")}</small>}<footer>{item.source_fact_ids.join("、") || "无事实编号"}</footer></article>)}</div></section>;
}

export function InitiativeRoadmap({ initiatives }: { initiatives: RoadmapItem[] }) {
  return <StrategyTimeline items={initiatives} />;
}

export function QualityIssuePanel({ issues }: { issues: Array<Record<string, unknown>> }) {
  if (!issues.length) return <EmptyState title="质量检查无问题" reason="当前版本没有结构化WARN或FAIL问题。" />;
  return <section className="gap-panel"><h2>Quality Check问题</h2>{issues.map((issue, index) => <article key={`${String(issue.rule_id ?? "issue")}-${index}`}><strong>{String(issue.severity ?? issue.status ?? "WARNING")} · {String(issue.rule_id ?? "未命名规则")}</strong><p>{String(issue.reason ?? issue.detail ?? "未提供原因")}</p><small>{String(issue.file ?? "未知文件")}{issue.metric_id ? ` · ${String(issue.metric_id)}` : ""}</small></article>)}</section>;
}
