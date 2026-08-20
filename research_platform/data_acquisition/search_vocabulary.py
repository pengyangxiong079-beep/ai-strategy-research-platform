"""Dataset and industry-aware search vocabulary without paid search APIs."""

from __future__ import annotations

from dataclasses import dataclass
import re


PRICE_DATASETS = {
    "prices", "price_observations", "product_prices", "pricing", "comparable_products"
}


@dataclass(frozen=True)
class SearchVocabulary:
    english_keywords: tuple[str, ...]
    local_keywords: dict[str, tuple[str, ...]]
    industry_keywords: tuple[str, ...] = ()
    preferred_source_types: tuple[str, ...] = ()
    proxy_metrics: tuple[str, ...] = ()
    forbidden_keywords: tuple[str, ...] = ()


INDUSTRY_ROUTES = {
    "aviation": ("航空", "airline", "aviation", "air transport"),
    "automotive": ("汽车", "automotive", "vehicle", "auto industry"),
    "food_beverage": ("餐饮", "茶饮", "食品", "饮料", "food", "beverage", "restaurant"),
    "software_ai": ("软件", "人工智能", "ai产品", "software", "artificial intelligence", "saas"),
    "retail": ("零售", "retail"),
    "banking": ("银行", "banking", "financial institution"),
    "manufacturing": ("制造", "manufacturing", "industrial"),
    "healthcare": ("医疗", "医药", "healthcare", "pharma", "biotech"),
    "energy": ("能源", "电力", "油气", "energy", "utilities", "oil and gas"),
}

# Ensure Unicode routes are explicit even when legacy source text came from an
# older Windows code page.
INDUSTRY_ROUTES["energy"] = (
    "能源", "电力", "光伏", "太阳能", "photovoltaic", "photovoltaik",
    "solar", "energy", "utilities", "oil and gas",
)

INDUSTRY_TERMS = {
    "aviation": ("traffic figures", "passenger airlines", "air transport"),
    "automotive": ("registrations", "vehicle sales", "model range"),
    "food_beverage": ("menu", "store network", "same-store sales"),
    "software_ai": ("product documentation", "pricing", "release notes"),
    "retail": ("store network", "same-store sales", "retail sales"),
    "banking": ("net interest margin", "cost income ratio", "capital ratio"),
    "manufacturing": ("production volume", "capacity utilization", "order intake"),
    "healthcare": ("regulatory approval", "clinical trial", "patient volume"),
    "energy": ("generation", "production volume", "capacity factor"),
    "generic": ("official data", "annual report"),
}


def _vocab(en, *, de=(), zh=(), sources=(), proxy=(), forbidden=("price data",)):
    return SearchVocabulary(
        tuple(en), {"de": tuple(de), "zh": tuple(zh)},
        preferred_source_types=tuple(sources), proxy_metrics=tuple(proxy),
        forbidden_keywords=tuple(forbidden),
    )


GENERIC_DATASET_VOCABULARY = {
    "company_profile": _vocab(("company profile", "group structure"), de=("Unternehmensprofil", "Konzernstruktur"), zh=("公司概况", "集团结构")),
    "financial_time_series": _vocab(("revenue", "adjusted EBIT", "free cash flow", "capital expenditure"), de=("Umsatz", "Adjusted EBIT", "Free Cashflow", "Investitionen"), zh=("收入", "调整后EBIT", "自由现金流", "资本开支"), sources=("annual report", "quarterly report", "investor relations")),
    "business_segments": _vocab(("segment revenue", "segment result", "business segments"), de=("Segmentumsatz", "Segmentergebnis", "Geschäftsfelder"), zh=("业务分部收入", "分部利润")),
    "products_or_services": _vocab(("products and services", "service portfolio"), de=("Produkte und Dienstleistungen", "Leistungsportfolio"), zh=("产品与服务", "服务组合")),
    "geographic_structure": _vocab(("revenue by region", "geographic segments"), de=("Umsatz nach Regionen", "geografische Segmente"), zh=("地区收入", "区域结构")),
    "strategic_initiatives": _vocab(("strategic initiatives", "transformation programme", "fleet renewal"), de=("strategische Initiativen", "Transformationsprogramm", "Flottenerneuerung"), zh=("战略行动", "转型计划")),
    "market_position": _vocab(("market position", "market share", "network position"), de=("Marktposition", "Marktanteil", "Netzwerkposition"), zh=("市场地位", "市场份额")),
    "competitors": _vocab(("peer comparison", "competitor operating metrics"), de=("Wettbewerbervergleich", "operative Kennzahlen"), zh=("竞争对手比较", "同业指标")),
    "capabilities": _vocab(("capabilities", "operational capabilities"), de=("Fähigkeiten", "operative Fähigkeiten"), zh=("核心能力", "运营能力")),
    "investments": _vocab(("capital expenditure", "investments", "fleet investment"), de=("Investitionen", "Flotteninvestitionen"), zh=("资本开支", "投资")),
    "risks": _vocab(("risk report", "principal risks", "risk management"), de=("Risikobericht", "wesentliche Risiken", "Risikomanagement"), zh=("风险报告", "主要风险")),
    "regulations": _vocab(("regulation", "regulatory requirements"), de=("Regulierung", "regulatorische Anforderungen"), zh=("法规", "监管要求")),
    "opportunities": _vocab(("growth opportunities", "strategic opportunities"), de=("Wachstumschancen", "strategische Chancen"), zh=("增长机会", "战略机会")),
    "competitor_profiles": _vocab(
        ("company profile", "business scope", "target customers"),
        de=("Unternehmensprofil", "Geschäftsbereiche", "Zielkunden"),
        zh=("公司概况", "业务范围", "目标客户"),
        sources=("official website", "annual report", "investor relations"),
    ),
    "product_portfolios": _vocab(
        ("product portfolio", "products and services", "product catalog"),
        de=("Produktportfolio", "Produkte und Dienstleistungen", "Produktkatalog"),
        zh=("产品组合", "产品与服务", "产品目录"),
        sources=("official product page", "product catalog", "official documentation"),
    ),
    "positioning": _vocab(
        ("market positioning", "value proposition", "customer segment"),
        de=("Marktpositionierung", "Wertversprechen", "Kundensegment"),
        zh=("市场定位", "价值主张", "客户群体"),
        sources=("official website", "investor presentation", "annual report"),
    ),
    "channel_or_store_coverage": _vocab(
        ("store network", "sales channels", "geographic coverage"),
        de=("Filialnetz", "Vertriebskanäle", "regionale Abdeckung"),
        zh=("门店网络", "销售渠道", "地区覆盖"),
        sources=("annual report", "official store locator", "official channel page"),
    ),
    "customer_segments": _vocab(
        ("customer segments", "customer profile", "target market"),
        de=("Kundensegmente", "Kundenprofil", "Zielmarkt"),
        zh=("客户细分", "用户画像", "目标市场"),
        sources=("annual report", "official website", "investor presentation"),
    ),
    "product_features": _vocab(
        ("product features", "technical specifications", "feature comparison"),
        de=("Produktfunktionen", "technische Daten", "Funktionsvergleich"),
        zh=("产品功能", "技术规格", "功能对比"),
        sources=("official documentation", "official product page", "technical datasheet"),
    ),
    "marketing_activity": _vocab(
        ("marketing campaign", "brand campaign", "partnership announcement"),
        de=("Marketingkampagne", "Markenkampagne", "Partnerschaft"),
        zh=("营销活动", "品牌活动", "合作公告"),
        sources=("official newsroom", "official social channel", "annual report"),
    ),
    "financial_or_operational_metrics": _vocab(
        ("revenue", "operating metrics", "key performance indicators"),
        de=("Umsatz", "operative Kennzahlen", "Leistungsindikatoren"),
        zh=("收入", "运营指标", "关键绩效指标"),
        sources=("annual report", "regulatory filing", "investor relations"),
    ),
    "prices": _vocab(("prices", "pricing", "price list"), de=("Preise", "Preisliste"), zh=("价格", "价目表"), forbidden=()),
    "price_observations": _vocab(("prices", "pricing", "price list"), de=("Preise", "Preisliste"), zh=("价格", "菜单价格"), forbidden=()),
    "product_prices": _vocab(("product prices", "price list"), de=("Produktpreise", "Preisliste"), zh=("产品价格", "价目表"), forbidden=()),
    "pricing": _vocab(("pricing", "price list"), de=("Preisgestaltung", "Preisliste"), zh=("定价", "价目表"), forbidden=()),
    "comparable_products": _vocab(("comparable products", "product prices"), de=("vergleichbare Produkte", "Produktpreise"), zh=("可比产品", "产品价格"), forbidden=()),
}

AVIATION_VOCABULARY = {
    "operating_metrics": _vocab(
        ("passengers", "flights", "available seat kilometres", "ASK", "revenue seat kilometres", "RPK", "passenger load factor", "yield", "unit revenue", "RASK", "unit cost", "CASK", "punctuality", "regularity"),
        de=("Passagiere", "Flüge", "angebotene Sitzkilometer", "verkaufte Sitzkilometer", "Sitzladefaktor", "Durchschnittserlös", "Stückerlöse", "Stückkosten", "Pünktlichkeit", "Regelmäßigkeit"),
        zh=("旅客量", "航班量", "可用座公里", "收入客公里", "客座率", "收益率", "单位收入", "单位成本", "准点率"),
        sources=("annual report", "traffic figures", "quarterly report", "investor relations"),
    ),
    "employee_metrics": _vocab(
        ("employees", "workforce", "employees at end of period", "average number of employees", "personnel expenses"),
        de=("Mitarbeiter", "Beschäftigte", "Personalaufwand", "durchschnittliche Mitarbeiterzahl"),
        zh=("员工人数", "平均员工人数", "人工成本"), sources=("annual report", "sustainability report"),
    ),
    "ESG_metrics": _vocab(
        ("specific CO2 emissions", "fuel efficiency", "emissions", "sustainable aviation fuel", "environmental data"),
        de=("spezifische CO2-Emissionen", "Kraftstoffeffizienz", "Emissionen", "nachhaltiger Flugkraftstoff", "Umweltkennzahlen"),
        zh=("单位二氧化碳排放", "燃油效率", "可持续航空燃料", "环境指标"), sources=("annual report", "sustainability report"),
    ),
    "detailed_unit_economics": _vocab(
        ("RASK", "CASK", "yield", "unit revenue", "unit cost", "ancillary revenue", "fuel cost per ASK", "irregularity cost"),
        de=("Stückerlöse", "Stückkosten", "Durchschnittserlös", "Zusatzerlöse", "Treibstoffkosten"),
        zh=("单位收入", "单位成本", "收益率", "辅助收入", "每座公里燃油成本"), sources=("annual report", "investor presentation"),
    ),
}

FOOD_BEVERAGE_VOCABULARY = {
    "industry_definition": _vocab(
        ("industry definition", "freshly made beverages definition"),
        zh=("行业定义", "现制饮品 定义 范围"),
        sources=("prospectus", "industry association", "government standard"),
    ),
    "market_size": _vocab(
        ("market size", "GMV", "retail sales"),
        zh=("市场规模", "GMV", "零售额"),
        sources=("prospectus", "government statistics", "industry association"),
    ),
    "historical_growth": _vocab(
        ("historical market growth", "GMV time series", "historical CAGR"),
        zh=("历史市场规模", "GMV 历年", "历史复合增长率"),
        sources=("prospectus", "annual report", "industry report"),
    ),
    "forecast_growth": _vocab(
        ("market forecast", "forecast CAGR", "GMV forecast"),
        zh=("市场预测", "预测复合增长率", "GMV 预测"),
        sources=("prospectus", "research institute", "industry report"),
    ),
    "market_segments": _vocab(
        ("market segments", "segment GMV", "coffee tea segment share"),
        zh=("市场细分", "细分市场 GMV", "咖啡 茶饮 细分占比"),
        sources=("prospectus", "annual report", "industry association"),
    ),
    "major_players": _vocab(
        ("major players", "market share", "store network"),
        zh=("主要企业", "市场份额", "门店网络"),
        sources=("prospectus", "annual report", "official announcement"),
    ),
    "concentration": _vocab(
        ("market concentration", "top five market share", "CR5"),
        zh=("市场集中度", "前五市场份额", "CR5"),
        sources=("prospectus", "industry report"),
    ),
    "value_chain": _vocab(
        ("industry value chain", "franchise supply chain", "store economics"),
        zh=("行业价值链", "加盟供应链", "门店经营链条"),
        sources=("prospectus", "annual report", "industry association"),
    ),
    "profit_pools": _vocab(
        ("profit pool", "gross margin", "franchisee economics"),
        zh=("利润池", "毛利率", "加盟商盈利模型"),
        sources=("annual report", "prospectus", "investor presentation"),
    ),
    "technology_trends": _vocab(
        ("digital ordering", "supply chain technology", "store automation"),
        zh=("数字化点单", "供应链技术", "门店自动化"),
        sources=("annual report", "official announcement", "industry report"),
    ),
    "demand_drivers": _vocab(
        ("consumer demand drivers", "consumption frequency", "customer segments"),
        zh=("消费需求驱动", "消费频次", "客户结构"),
        sources=("consumer survey", "prospectus", "industry report"),
    ),
}

ENERGY_VOCABULARY = {
    "market_size": _vocab(
        ("installed photovoltaic capacity", "solar electricity generation", "annual net additions"),
        de=("installierte Photovoltaik-Leistung", "Stromerzeugung Photovoltaik", "Nettozubau Solaranlagen"),
        zh=("光伏装机容量", "太阳能发电量", "年度净新增装机"),
        sources=("regulator database", "government statistics", "research institute"),
    ),
    "historical_growth": _vocab(
        ("photovoltaic capacity additions", "solar generation time series"),
        de=("Photovoltaik Zubau Zeitreihe", "Solarstrom Erzeugung Zeitreihe"),
        zh=("光伏新增装机时间序列", "太阳能发电时间序列"),
        sources=("regulator database", "government statistics"),
    ),
    "forecast_growth": _vocab(
        ("photovoltaic capacity target", "solar deployment forecast"),
        de=("Photovoltaik Ausbauziel", "Solar Ausbauprognose"),
        zh=("光伏装机目标", "太阳能发展预测"),
        sources=("law", "government plan", "research institute"),
    ),
    "regulation": _vocab(
        ("Renewable Energy Sources Act photovoltaic target", "solar auction regulation"),
        de=("EEG Photovoltaik Ausbauziel", "Solaranlagen Ausschreibung Zuschlagswert"),
        zh=("德国可再生能源法 光伏目标", "光伏招标 中标价格"), sources=("law", "regulator"),
    ),
    "regulations": _vocab(
        ("Renewable Energy Sources Act photovoltaic target", "solar auction regulation"),
        de=("EEG Photovoltaik Ausbauziel", "Solaranlagen Ausschreibung Zuschlagswert"),
        zh=("德国可再生能源法 光伏目标", "光伏招标 中标价格"), sources=("law", "regulator"),
    ),
    "geographies": _vocab(
        ("photovoltaic capacity by federal state", "solar installations by region"),
        de=("Photovoltaik installierte Leistung Bundesland", "Solaranlagen nach Bundesland"),
        zh=("德国各州光伏装机",), sources=("regulator database", "government statistics"),
    ),
}


ENTITY_PROFILES = (
    {
        "tokens": ("咖啡及茶饮", "咖啡和茶饮", "coffee and tea", "freshly made beverage"),
        "names": ("China freshly made coffee and tea market", "China freshly made beverage market"),
        "local_names": ("中国现制咖啡及茶饮市场", "中国现制饮品市场"),
        "domains": (),
    },
    {
        "tokens": ("nintendo switch 2", "任天堂 switch 2", "任天堂switch 2"),
        "names": ("Nintendo Switch 2", "Nintendo Co., Ltd."),
        "local_names": ("Nintendo Switch 2", "任天堂 Switch 2"),
        "domains": ("nintendo.com", "nintendo.co.jp/ir"),
    },
    {
        "tokens": ("german solar", "germany solar", "deutschland photovoltaik", "德国光伏"),
        "names": ("Germany photovoltaic market", "Germany solar market"),
        "local_names": ("Deutschland Photovoltaik", "Photovoltaik Deutschland"),
        "domains": ("bundesnetzagentur.de", "gesetze-im-internet.de", "energy-charts.info"),
    },
    {
        "tokens": ("lufthansa", "汉莎"),
        "names": ("Lufthansa Group", "Deutsche Lufthansa AG", "Lufthansa Airlines"),
        "local_names": ("Lufthansa Group", "Deutsche Lufthansa AG", "Lufthansa Airlines"),
        "domains": (
            "report.lufthansagroup.com/2025/annual-report",
            "report.lufthansagroup.com",
            "investor-relations.lufthansagroup.com",
        ),
    },
    {
        "tokens": ("xpeng", "小鹏"),
        "names": ("XPeng", "XPeng Motors"),
        "local_names": ("小鹏汽车", "XPeng Deutschland"),
        "domains": ("xpeng.com", "ir.xiaopeng.com"),
    },
)


def route_industry(industry):
    text = str(industry or "").lower()
    for route, tokens in INDUSTRY_ROUTES.items():
        if any(token in text for token in tokens):
            return route
    return "generic"


def _scope_industry_text(scope):
    """Infer routing from the full Scope when industry is still 自动判断."""
    return " ".join(
        str(scope.get(key) or "")
        for key in ("industry", "topic", "objective", "target_entity")
    )


def entity_search_profile(scope, entity=None):
    # An explicit peer must not inherit the target company's aliases/domains.
    # Otherwise a query for a competitor can incorrectly become
    # ``site:target.com \"competitor\" ...`` and systematically return no data.
    text = str(entity).lower() if entity else " ".join(
        str(scope.get(key) or "") for key in ("topic", "target_entity", "industry")
    ).lower()
    for profile in ENTITY_PROFILES:
        if any(token in text for token in profile["tokens"]):
            result = {key: tuple(value) for key, value in profile.items() if key != "tokens"}
            if entity and entity not in result["names"]:
                result["names"] = (str(entity), *result["names"])
            return result
    target = str(entity or scope.get("target_entity") or "").strip()
    if not target:
        target = re.split(
            r"盈利能力|运营效率|业务组合|战略分析|公司战略|竞品分析|市场进入|行业分析|在",
            str(scope.get("topic") or ""), maxsplit=1,
        )[0].strip(" -—、，,：:")
    target = re.split(
        r"(?:全球|区域|公司|产品|生态|增长|竞争|行业|市场|业务).{0,12}(?:战略|分析|研究|诊断)|"
        r"(?:global|regional|company|product|growth|competition|industry|market).{0,20}(?:strategy|analysis|research)",
        target, maxsplit=1, flags=re.IGNORECASE,
    )[0].strip(" -—、，,;；")
    if len(target.split()) > 8:
        target = " ".join(target.split()[:8])
    target = target[:60] or "target entity"
    return {"names": (target,), "local_names": (target,), "domains": ()}


def compact_geographies(scope):
    text = str(scope.get("geography") or "").lower()
    values = []
    if any(token in text for token in ("德国", "germany", "deutschland")):
        values.append("Germany")
    if any(token in text for token in ("欧洲", "europe", "eu")):
        values.append("Europe")
    if any(token in text for token in ("全球", "global", "洲际")):
        values.append("global")
    if any(token in text for token in ("中国", "china")):
        values.append("China")
    if any(token in text for token in ("湖南", "hunan")):
        values.append("Hunan")
    return tuple(dict.fromkeys(values)) or ("global",)


def dataset_vocabulary(dataset_id, industry):
    dataset_id = str(dataset_id or "")
    route = route_industry(industry)
    base = AVIATION_VOCABULARY.get(dataset_id) if route == "aviation" else None
    if base is None and route == "food_beverage":
        base = FOOD_BEVERAGE_VOCABULARY.get(dataset_id)
    if base is None and route == "energy":
        base = ENERGY_VOCABULARY.get(dataset_id)
    if base is None:
        base = GENERIC_DATASET_VOCABULARY.get(dataset_id)
    if base is None:
        words = dataset_id.replace("_", " ") or "official data"
        base = _vocab((words,), de=(words,), zh=(words,))
    return SearchVocabulary(
        english_keywords=base.english_keywords,
        local_keywords=base.local_keywords,
        industry_keywords=INDUSTRY_TERMS[route],
        preferred_source_types=base.preferred_source_types,
        proxy_metrics=base.proxy_metrics,
        forbidden_keywords=() if dataset_id in PRICE_DATASETS else tuple(dict.fromkeys((*base.forbidden_keywords, "price data"))),
    )


def _years(scope):
    values = [int(value) for value in re.findall(r"(?:19|20)\d{2}", " ".join(str(scope.get(key) or "") for key in ("analysis_date", "time_horizon")))]
    current = int(str(scope.get("analysis_date") or "2026")[:4])
    prior = current - 1
    return current, prior if prior in values or not values else max((value for value in values if value < current), default=prior)


def _clean_query(query, forbidden):
    result = re.sub(r"\s+", " ", str(query)).strip()
    for phrase in forbidden:
        result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip()


def build_dataset_queries(scope, dataset_id, *, entity=None, languages=None, limit=5):
    """Build short, auditable queries from dataset and industry vocabulary."""
    industry_text = _scope_industry_text(scope)
    vocabulary = dataset_vocabulary(dataset_id, industry_text)
    profile = entity_search_profile(scope, entity)
    names = profile["names"]
    local_names = profile["local_names"]
    domains = profile["domains"]
    current_year, prior_year = _years(scope)
    languages = tuple(languages or ("en", "de" if route_industry(industry_text) == "aviation" else "zh"))
    english = vocabulary.english_keywords
    local = vocabulary.local_keywords.get("de" if "de" in languages else "zh", ()) or english
    queries = []

    # High-value aviation/Lufthansa templates keep metric pairs short and preserve official domains.
    route = route_industry(industry_text)
    if route == "automotive" and "XPeng" in names and dataset_id in {"market_size", "prices", "regulation", "customer_demand"}:
        automotive_queries = {
            "market_size": [("de", "XPeng Deutschland Zulassungen KBA Neuzulassungen Elektroauto")],
            "prices": [("de", "XPeng Deutschland Preise Konfigurator Preisliste PDF")],
            "regulation": [("en", "EU tariff Chinese EV official regulation")],
            "customer_demand": [("de", "Deutschland Elektroauto Förderung Nachfrage Statistik")],
        }
        queries.extend(automotive_queries[dataset_id])
    if route == "aviation" and dataset_id == "operating_metrics" and "Lufthansa Group" in names:
        queries.extend([
            ("en", 'site:report.lufthansagroup.com/2025/annual-report "Passenger load factor" "Available seat-kilometres"'),
            ("en", "site:report.lufthansagroup.com/2025/annual-report Lufthansa RASK CASK Yield"),
            ("en", f"site:investor-relations.lufthansagroup.com Lufthansa traffic figures {current_year}"),
            ("de", f"site:report.lufthansagroup.com Lufthansa Passagiere Flüge Sitzladefaktor {prior_year}"),
            ("en", f'filetype:pdf "Lufthansa Group" ASK RPK "passenger load factor" {current_year}'),
        ])
    elif not queries:
        metric_one = english[0]
        metric_two = english[1] if len(english) > 1 else english[0]
        local_metric = local[0]
        if domains:
            queries.append(("en", f'site:{domains[0]} "{names[0]}" "{metric_one}" {prior_year}'))
            queries.append(("en", f'site:{domains[-1]} "{names[0]}" {metric_one} {metric_two}'))
        queries.extend([
            ("en", f'"{names[0]}" annual report {prior_year} "{metric_one}"'),
            ("de" if "de" in languages else languages[0], f'"{local_names[0]}" {local_metric} {prior_year}'),
            ("en", f'filetype:pdf "{names[0]}" "{metric_one}" {prior_year}'),
        ])
    cleaned, seen = [], set()
    for language, query in queries:
        query = _clean_query(query, vocabulary.forbidden_keywords)
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        cleaned.append({"language": language, "query": query})
    return cleaned[:limit]


# V2 gap-aware builder. This later definition intentionally supersedes the
# compatibility implementation above while preserving its `query` field.
def build_dataset_queries(
    scope, dataset_id, *, entity=None, languages=None, limit=5,
    missing_field=None, missing_metric=None, period=None, geography=None,
    source_type=None, preferred_domains=None, gap_id=None,
):
    industry_text = _scope_industry_text(scope)
    vocabulary = dataset_vocabulary(dataset_id, industry_text)
    profile = entity_search_profile(scope, entity)
    route = route_industry(industry_text)
    current_year, prior_year = _years(scope)
    period = str(period or prior_year)
    languages = tuple(languages or (("de", "en", "zh") if "Germany" in compact_geographies(scope) else ("en", "zh")))
    names = profile["names"]
    local_names = profile["local_names"]
    domains = tuple(preferred_domains or profile["domains"])
    metric = str(missing_metric or "").replace("_", " ").strip()
    english = tuple([metric] if metric else []) + vocabulary.english_keywords
    local_key = "de" if "de" in languages else "zh"
    local = vocabulary.local_keywords.get(local_key, ()) or english
    queries = []

    # Agency-led German photovoltaic searches: short subject, explicit metric,
    # period and downloadable format. No report title or dataset_id is inserted.
    solar_case = route == "energy" and "Germany" in compact_geographies(scope)
    if solar_case:
        solar = {
            "market_size": [
                ("de", "bundesnetzagentur.de", f"site:bundesnetzagentur.de Photovoltaik MaStR Juni {current_year} PDF", "PDF", "regulator database"),
                ("de", "bundesnetzagentur.de", f"Deutschland Photovoltaik installierte Leistung Bundesland {period} MaStR", "", "regulator database"),
                ("en", "energy-charts.info", f"Germany solar electricity generation {period} Fraunhofer PDF", "PDF", "research institute"),
            ],
            "historical_growth": [
                ("de", "bundesnetzagentur.de", f"site:bundesnetzagentur.de Photovoltaik Zubau Zeitreihe {period} XLSX", "XLSX", "regulator database"),
                ("en", "energy-charts.info", f"Germany solar electricity generation {period} Fraunhofer PDF", "PDF", "research institute"),
            ],
            "forecast_growth": [
                ("de", "gesetze-im-internet.de", "site:gesetze-im-internet.de EEG Photovoltaik 215 GW 2030", "", "law"),
                ("de", "bundesnetzagentur.de", f"site:bundesnetzagentur.de Photovoltaik Ausbauziel {period} PDF", "PDF", "regulator"),
            ],
            "regulation": [
                ("de", "gesetze-im-internet.de", "site:gesetze-im-internet.de EEG Photovoltaik 215 GW 2030", "", "law"),
                ("de", "bundesnetzagentur.de", f"site:bundesnetzagentur.de Solaranlagen Ausschreibung Zuschlagswert {period} XLSX", "XLSX", "regulator"),
            ],
            "regulations": [
                ("de", "gesetze-im-internet.de", "site:gesetze-im-internet.de EEG Photovoltaik 215 GW 2030", "", "law"),
                ("de", "bundesnetzagentur.de", f"site:bundesnetzagentur.de Solaranlagen Ausschreibung Zuschlagswert {period} XLSX", "XLSX", "regulator"),
            ],
            "geographies": [
                ("de", "bundesnetzagentur.de", f"Deutschland Photovoltaik installierte Leistung Bundesland {period} MaStR", "", "regulator database"),
            ],
        }
        queries.extend(solar.get(dataset_id, []))

    if route == "automotive" and "XPeng" in names:
        automotive = {
            "market_size": [("de", "kba.de", "XPeng Deutschland Zulassungen KBA Neuzulassungen Elektroauto", "", "regulator statistics")],
            "prices": [("de", "xpeng.com", "XPeng Deutschland Preise Konfigurator Preisliste PDF", "PDF", "official price list")],
            "regulation": [("en", "europa.eu", "EU tariff Chinese EV official regulation", "", "regulation")],
            "customer_demand": [("de", "", "Deutschland Elektroauto Förderung Nachfrage Statistik", "", "government statistics")],
        }
        queries.extend(automotive.get(dataset_id, []))

    if route == "aviation" and dataset_id == "operating_metrics" and "Lufthansa Group" in names:
        queries.extend([
            ("en", "report.lufthansagroup.com/2025/annual-report", 'site:report.lufthansagroup.com/2025/annual-report "Passenger load factor" "Available seat-kilometres"', "", "annual report"),
            ("en", "report.lufthansagroup.com/2025/annual-report", "site:report.lufthansagroup.com/2025/annual-report Lufthansa RASK CASK Yield", "", "annual report"),
            ("en", "investor-relations.lufthansagroup.com", f"site:investor-relations.lufthansagroup.com Lufthansa traffic figures {current_year}", "", "quarterly report"),
            ("de", "report.lufthansagroup.com", f"site:report.lufthansagroup.com Lufthansa Passagiere Flüge Sitzladefaktor {period}", "", "annual report"),
        ])

    if not queries:
        name = names[0]
        local_name = local_names[0]
        metric_one = english[0] if english else "official data"
        metric_two = english[1] if len(english) > 1 else metric_one
        local_metric = local[0] if local else metric_one
        preferred_source = source_type or (
            vocabulary.preferred_source_types[0]
            if vocabulary.preferred_source_types else "official report"
        )
        if domains:
            queries.append(("en", domains[0], f'site:{domains[0]} "{name}" "{metric_one}" {period}', "", preferred_source))
        generic_queries = [
            ("en", "", f'"{name}" {preferred_source} {period} "{metric_one}"', "", preferred_source),
            (local_key, "", f'"{local_name}" {local_metric} {period}', "", preferred_source),
            ("en", "", f'filetype:pdf "{name}" {metric_one} {metric_two} {period}', "PDF", preferred_source),
        ]
        # For local-market research, the first bounded query should use the
        # market language. This matters when the planner assigns one query per
        # entity/dataset to maximize cohort coverage.
        if languages and languages[0] not in {"en", "unknown"}:
            generic_queries[0], generic_queries[1] = generic_queries[1], generic_queries[0]
        queries.extend(generic_queries)

    output, seen = [], set()
    for index, (language, domain, query, file_type, preferred_type) in enumerate(queries, 1):
        query = _clean_query(query, vocabulary.forbidden_keywords)
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        output.append({
            "query_id": f"Q_{dataset_id}_{index:03d}", "gap_id": gap_id or "",
            "dataset_id": dataset_id, "query": query, "query_text": query,
            "language": language, "domain_filter": domain, "file_type": file_type,
            "source_type": preferred_type, "entity": entity or names[0],
            "geography": geography or compact_geographies(scope)[0], "period": period,
            "metric": metric or (english[0] if english else ""),
            "missing_field": missing_field or "", "gap_reason": missing_field or missing_metric or "dataset coverage",
        })
    return output[:limit]
