import { useMemo } from "react";
import type { DataCoverage, Observation } from "../types";
import { EChart } from "./EChart";
import { EmptyState } from "./EmptyState";

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function priceCoverageLevel(entityCount: number, rankingReady: boolean) {
  return entityCount >= 3 ? (rankingReady ? 4 : 3) : entityCount === 2 ? 2 : entityCount === 1 ? 1 : 0;
}

export function AdaptivePriceChart({ observations, coverage }: { observations: Observation[]; coverage: DataCoverage }) {
  const rows = observations.filter((item) => ["price_observations", "prices"].includes(item.dataset_id) && typeof item.value === "number");
  const entities = [...new Set(rows.map((item) => item.entity).filter(Boolean))];
  const coverageRow = coverage.datasets?.find((item) => item.dataset_id === "price_observations" || item.dataset_id === "prices");
  const rankingReady = Boolean(coverageRow?.dashboard_readiness?.PriceRanking);
  const level = priceCoverageLevel(entities.length, rankingReady);
  const option = useMemo(() => {
    if (level === 1) {
      const values = rows.map((item) => item.value as number);
      return {
        tooltip: {}, xAxis: { type: "category", data: ["最低价", "中位数", "最高价"] },
        yAxis: { type: "value", name: [rows[0]?.currency, rows[0]?.unit].filter(Boolean).join("/") },
        series: [{ type: "bar", data: [Math.min(...values), median(values), Math.max(...values)], itemStyle: { color: "#4776e6" } }],
      };
    }
    return {
      tooltip: { formatter: (params: { data: { value: [string, number]; product: string; category: string } }) => `${params.data.value[0]}<br/>${params.data.product || "未命名单品"}<br/>${params.data.value[1]} ${rows[0]?.currency || ""}<br/>${params.data.category || "未分类"}` },
      xAxis: { type: "category", data: entities, axisLabel: { interval: 0, overflow: "truncate" } },
      yAxis: { type: "value", name: [rows[0]?.currency, rows[0]?.unit].filter(Boolean).join("/") },
      series: [{ type: "scatter", symbolSize: 12, data: rows.map((item) => ({ value: [item.entity, item.value], product: item.product_name, category: item.category, itemStyle: { opacity: item.verification_status === "PARTIAL" ? 0.55 : 0.9 } })) }],
    };
  }, [entities, level, rows]);
  if (!level) return <EmptyState reason="尚无通过核验的价格Observation。请在Data Coverage中查看具体缺失品牌、价格类型、城市和采集日期。" />;
  const descriptions: Record<number, string> = {
    1: "LEVEL 1：仅一个品牌有数据，展示该品牌样本最低价、中位数和最高价，不进行竞品排名。",
    2: "LEVEL 2：两个品牌有可比样本，展示单品价格分布，不生成完整市场排名。",
    3: "LEVEL 3：三个及以上品牌有数据，展示价格分布；口径尚不足以确定性排名。",
    4: "LEVEL 4：至少三个品牌且地区、时间、渠道和价格类型高度一致，允许显示统计摘要；排名仍需明确指标定义。",
  };
  const sourceLinks = [...new Map(rows.filter((item) => item.source_url).map((item) => [item.source_url, item])).values()].slice(0, 5);
  return <section>
    <div className={`coverage-level level-${level}`}>{descriptions[level]}</div>
    <EChart option={option} ariaLabel={`价格数据覆盖等级${level}，覆盖${entities.length}个品牌`} />
    <p className="chart-source">来源：{sourceLinks.length ? sourceLinks.map((item, index) => <span key={item.source_url}>{index ? "；" : ""}<a href={item.source_url} target="_blank" rel="noreferrer">{item.source_id}</a>（{item.source_grade}）</span>) : "结构化Observation未提供可访问来源链接"}</p>
  </section>;
}
