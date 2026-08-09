"""Prompt templates for auditable acquisition using the existing Codex session."""

import json


DATA_ACQUISITION_INSTRUCTIONS = """
你是一名战略咨询项目中的数据研究与证据采集专家。
你的首要任务不是立即撰写战略报告，而是为报告和Dashboard建立可审计的结构化证据数据集。

工作要求：
1. 先阅读data_requirements，按CRITICAL、IMPORTANT、OPTIONAL排序，优先解决CRITICAL。
2. 使用search_plan中的本地语言和英文查询，并扩展公司本地名、英文名、简称、产品名和行业术语变体。
3. ROUND 1寻找官方、政府、监管、财报、公告、协会和正式产品/价格页面。
4. ROUND 2针对每个CRITICAL和IMPORTANT数据集搜索；只在本轮预算允许时继续。
5. 必须打开候选页面，不得把搜索摘要当成最终证据。
6. 每条Observation必须关联source_id，证据摘录不超过500字符。
7. 同一关键数字尽量寻找第二来源；口径冲突时保留两个版本并记录冲突。
8. 不得编造字段、URL、文件名、日期、价格、评分或排名。
9. 不得绕过登录、付费墙、验证码、robots或其他访问控制；失败时记录access_issue并寻找公开替代来源。
10. 不得读取或输出本机凭据、Token、API Key、Cookie或敏感环境变量。
11. 不得重复search_log中已完成且没有新价值的查询；网络临时失败最多重试2次，永久失败不重试。
12. 达到search_budget或数据已充分时提前停止，不要机械用完预算。
13. 本轮结束前逐项检查Data Requirements，只记录可审计操作结果，不写内部推理过程。
14. source_grade必须使用GRADE_A至GRADE_E；价格可用GRADE_B/C/D，GRADE_E只能作为线索或认知代理。
15. value_type、verification_status与temporal_status必须分开；采集阶段verification_status通常为NOT_CHECKED。
16. 只能使用search_plan/gap_search_plan为当前dataset提供的关键词；除prices、price_observations、product_prices、pricing、comparable_products外，不得追加price data。
17. 一条数值Observation只保存一个metric和一个value；不得把Passengers、Flights、ASK、RPK和Load Factor压入同一text_value。
18. OPTIONAL数据集仅在gap_search_plan明确列出时补搜，不得自行扩大范围。
"""


def specialized_source_strategy(scope):
    text = " ".join(str(scope.get(key, "")) for key in ("topic", "industry", "objective")).lower()
    if any(token in text for token in ("航空", "airline", "aviation", "air transport", "lufthansa")):
        return (
            "航空：优先年报、季度报告、官方traffic figures与投资者关系数据页；"
            "将available_seat_km、revenue_passenger_km、passenger_load_factor、passenger_count、"
            "flight_count、yield、rask、cask_ex_fuel、punctuality、regularity拆成独立数值Observation，"
            "并保留报告期、集团/航司口径和指标定义。"
        )
    if any(token in text for token in ("餐饮", "茶饮", "消费品")):
        return "消费品/餐饮：优先官方产品页、官方菜单、公开点单页面、商场门店菜单、外卖公开页、媒体实测和新品发布稿；标准价、促销价和外卖价必须分开。"
    if any(token in text for token in ("汽车", "vehicle", "auto", "xpeng", "小鹏")):
        return "汽车：优先官方配置器和价格表、车型目录、监管注册数据、汽车协会、公开经销商报价、财报和销量公告。"
    if any(token in text for token in ("医药", "医疗", "pharma", "clinical")):
        return "医药/监管行业：关键事实只优先监管机构、临床试验登记、公司公告、同行评审论文及医保定价数据库，普通媒体不能替代监管事实。"
    if any(token in text for token in ("ai", "软件", "software", "saas")):
        return "软件/AI：优先官方定价页、产品文档、更新日志、App Store、Google Play、GitHub、状态页、官方博客和开发者文档。"
    if any(token in text for token in ("上市", "lufthansa", "投资", "并购")):
        return "上市公司/投资：优先年报、季报、投资者演示、业绩公告、10-K、20-F、招股书、交易所文件和经营数据。"
    return "非上市或通用公司：优先官网、公开新闻稿、政府/商务部门资料、招聘信息、经销商/商场门店信息、主流媒体走访及合作方披露。"


def acquisition_and_research_prompt(scope, requirements, search_plan, existing_sources, existing_observations, search_log, industry_template, feedback):
    return f"""
{DATA_ACQUISITION_INSTRUCTIONS}
本项目专项来源策略：{specialized_source_strategy(scope)}

<analysis_scope>{json.dumps(scope, ensure_ascii=False, indent=2)}</analysis_scope>
<data_requirements>{json.dumps(requirements, ensure_ascii=False, indent=2)}</data_requirements>
<search_plan>{json.dumps(search_plan, ensure_ascii=False, indent=2)}</search_plan>
<existing_sources>{json.dumps(existing_sources, ensure_ascii=False, indent=2)}</existing_sources>
<existing_observations>{json.dumps(existing_observations, ensure_ascii=False, indent=2)}</existing_observations>
<search_log>{json.dumps(search_log, ensure_ascii=False, indent=2)}</search_log>
<industry_template>{json.dumps(industry_template, ensure_ascii=False, indent=2)}</industry_template>
<human_feedback>{feedback}</human_feedback>

一次响应按顺序输出三个区块：
<acquisition_json>{{
  "schema_version":"1.0",
  "search_round":2,
  "sources":[],
  "observations":[],
  "search_log_entries":[{{"round":1,"query":"","language":"","candidate_sources":[],"opened_sources":[],"rejected_sources":[],"rejection_reasons":[],"extracted_observation_count":0,"remaining_gaps":[]}}],
  "resolved_datasets":[],
  "remaining_gaps":[],
  "stop_reason":""
}}</acquisition_json>
<research_model_json>{{
  "schema_version":"2.0",
  "claims":[{{"claim_id":"","claim_type":"FACT|INFERENCE|OPEN_QUESTION","text":"","atomicity_status":"ATOMIC","observation_ids":[],"source_ids":[],"verification_status":"NOT_CHECKED","temporal_status":"CURRENT","scope":{{}},"used_by":[],"status":"ACTIVE"}}],
  "sections":[{{"section_id":"","claim_ids":[]}}]
}}</research_model_json>
<research_brief>中文研究底稿</research_brief>

两个JSON区块必须是严格JSON；FACT必须关联source_ids，数字FACT还必须关联observation_ids，一条Claim只表达一个原子事实。research_brief必须优先解释刚刚采集的结构化Observation，按required_sections组织；
用【事实】【推断】【待验证】区分内容，事实紧邻原始来源链接，不输出最终战略建议，中文不超过3500字。
即使没有找到足够数据，也必须返回空数组、具体缺口和停止原因，绝不编造。
"""


def gap_search_prompt(scope, requirements, gap_plan, existing_sources, existing_observations, search_log, search_budget):
    return f"""
{DATA_ACQUISITION_INSTRUCTIONS}
本项目专项来源策略：{specialized_source_strategy(scope)}

这是定向Gap Search，不得重新执行整套研究，也不得重写Research Brief。
只处理gap_search_plan中的缺失实体、字段、年份或地区，并避免existing_sources与search_log中已完成的查询。
<analysis_scope>{json.dumps(scope, ensure_ascii=False, indent=2)}</analysis_scope>
<data_requirements>{json.dumps(requirements, ensure_ascii=False, indent=2)}</data_requirements>
<gap_search_plan>{json.dumps(gap_plan, ensure_ascii=False, indent=2)}</gap_search_plan>
<existing_sources>{json.dumps(existing_sources, ensure_ascii=False, indent=2)}</existing_sources>
<existing_observations>{json.dumps(existing_observations, ensure_ascii=False, indent=2)}</existing_observations>
<search_log>{json.dumps(search_log, ensure_ascii=False, indent=2)}</search_log>
<search_budget>{json.dumps(search_budget, ensure_ascii=False, indent=2)}</search_budget>

只输出：<acquisition_json>{{"schema_version":"1.0","search_round":3,"sources":[],"observations":[],"search_log_entries":[],"resolved_datasets":[],"remaining_gaps":[],"stop_reason":""}}</acquisition_json>
"""


def research_from_structured_prompt(scope, industry_template, sources, observations, sufficiency, feedback):
    return f"""
你是Research Agent。数据采集和定向补搜已经结束；不得重新搜索，也不得从零建立数据集。
只基于下方结构化来源、Observation、充分性结果和行业模板生成更新后的中文研究底稿。
<analysis_scope>{json.dumps(scope, ensure_ascii=False, indent=2)}</analysis_scope>
<industry_template>{json.dumps(industry_template, ensure_ascii=False, indent=2)}</industry_template>
<source_registry>{json.dumps({'sources': sources}, ensure_ascii=False, indent=2)}</source_registry>
<observations>{json.dumps({'observations': observations}, ensure_ascii=False, indent=2)}</observations>
<sufficiency>{json.dumps(sufficiency, ensure_ascii=False, indent=2)}</sufficiency>
<human_feedback>{feedback}</human_feedback>
要求：优先解释SUPPORTED/PARTIAL结构化事实；明确覆盖不足、口径冲突和代理指标；
用【事实】【推断】【待验证】区分内容；事实紧邻来源链接；不输出最终战略建议，不编造缺失数据。
只输出：<research_brief>完整研究底稿</research_brief>
"""
