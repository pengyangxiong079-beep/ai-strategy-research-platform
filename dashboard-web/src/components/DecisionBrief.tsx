import type { DashboardView } from "../lib/validation";

function evidenceStats(summary: Record<string, number>) {
  const supported = Number(summary.verified ?? summary.supported ?? 0);
  const total = supported + Number(summary.partial ?? 0) + Number(summary.unsupported ?? 0) + Number(summary.superseded ?? 0);
  return { supported, total, rate: total ? supported / total : null };
}

export function DecisionBrief({ view }: { view: DashboardView }) {
  const recommendation = view.recommendations[0];
  const gap = view.data_gaps[0];
  const evidence = evidenceStats(view.evidence_summary);
  const posture = recommendation ? (gap ? "有条件推进" : "建议推进") : "待形成建议";
  const title = recommendation?.title ?? recommendation?.label ?? "尚无结构化战略建议";
  const rationale = recommendation?.rationale ?? recommendation?.description ?? view.executive_summary;
  return (
    <section className="decision-brief" aria-label="管理层决策简报">
      <header><div><span>Management decision</span><h2>{title}</h2></div><strong className={`decision-posture ${gap ? "conditional" : "ready"}`}>{posture}</strong></header>
      <p className="decision-rationale">{rationale}</p>
      <dl>
        <div><dt>决策依据</dt><dd>{view.executive_summary || "待补充结构化结论"}</dd></div>
        <div><dt>决策护栏</dt><dd>{gap ? `${gap.label}：${gap.required_action ?? gap.reason}` : "当前没有未关闭的结构化数据缺口"}</dd></div>
        <div><dt>证据置信</dt><dd>{evidence.rate === null ? "待评估" : `${Math.round(evidence.rate * 100)}% 已支持（${evidence.supported}/${evidence.total}）`}</dd></div>
        <div><dt>下一道门</dt><dd>{recommendation?.kpi ?? recommendation?.time_horizon ?? recommendation?.timeframe ?? "责任人与验收指标待定义"}</dd></div>
      </dl>
    </section>
  );
}
