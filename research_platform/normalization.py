"""Deterministic normalization and de-duplication for acquired evidence."""

import hashlib
import re
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .data_acquisition.aviation_metrics import (
    AVIATION_METRICS,
    expand_compound_aviation_observation,
    metric_definition as aviation_metric_definition,
    standard_unit as aviation_standard_unit,
    standardize_aviation_metric,
)
from .data_acquisition.search_vocabulary import route_industry


CURRENCY_ALIASES = {
    "¥": "CNY", "￥": "CNY", "RMB": "CNY", "人民币": "CNY", "元": "CNY",
    "€": "EUR", "EURO": "EUR", "欧元": "EUR",
    "$": "USD", "US$": "USD", "美元": "USD",
    "£": "GBP", "英镑": "GBP", "JPY": "JPY", "日元": "JPY", "円": "JPY",
}
UNIT_ALIASES = {
    "人民币元": "元", "rmb": "元", "yuan": "元", "亿元人民币": "亿元",
    "%": "%", "percent": "%", "percentage": "%", "家门店": "家", "stores": "家",
    "vehicles": "辆", "cars": "辆", "million": "百万", "billion": "十亿",
    "thousands": "thousand", "in 1,000": "thousand", "千人": "thousand",
    "number": "count", "flights": "flights", "架次": "flights",
    "million seat-kilometres": "million seat-km", "million seat-kilometers": "million seat-km",
    "百万座公里": "million seat-km", "百万座千米": "million seat-km",
    "million passenger-kilometres": "million passenger-km", "million revenue seat-kilometres": "million passenger-km",
    "百万客公里": "million passenger-km", "百万收入客公里": "million passenger-km",
    "€ cents": "euro_cents", "in € cents": "euro_cents", "euro cents": "euro_cents", "欧分": "euro_cents",
}
PRICE_TYPE_ALIASES = {"原价": "标准价", "门店价": "标准价", "常规价": "标准价", "折扣价": "促销价", "优惠价": "促销价", "外卖到手价": "外卖价"}
CHANNEL_ALIASES = {"直营店": "直营", "加盟店": "加盟", "direct": "直营", "franchise": "加盟", "online": "线上", "offline": "线下"}
GEOGRAPHY_ALIASES = {"全球": "global", "全世界": "global", "德国": "Germany", "欧洲": "Europe", "中国": "China"}
METRIC_ALIASES = {"销售网点数": "销售网点数", "网点数": "销售网点数", "门店数量": "门店数", "店数": "门店数"}
PLACEHOLDERS = {
    "n/a", "na", "unknown", "tbd", "待补充", "待搜索", "暂无", "无数据", "not available",
    "placeholder", "dataset description", "search query only", "仅搜索查询", "自动生成的数据集说明",
}
COMPARABILITY_DATASETS = {
    "financial_time_series", "operating_metrics", "competitors", "prices",
    "price_observations", "product_prices", "pricing", "comparable_products",
    "market_size", "business_segments", "geographies", "geographic_structure",
}


def normalize_url(url):
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"}:
            return ""
        query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))
    except ValueError:
        return value


def normalize_currency(value):
    text = str(value or "").strip()
    return CURRENCY_ALIASES.get(text.upper(), CURRENCY_ALIASES.get(text, text.upper()))


def normalize_unit(value):
    text = str(value or "").strip()
    return UNIT_ALIASES.get(text.lower(), UNIT_ALIASES.get(text, text))


def _parse_numeric_value(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value or "").strip().replace("\u2212", "-").replace("−", "-")
    if not text:
        return None
    text = re.sub(r"^(?:EUR|USD|CNY|€|\$|¥)\s*", "", text, flags=re.I)
    text = re.sub(r"(?:%|欧分|€\s*cents?|million|thousand|千|百万)\s*$", "", text, flags=re.I).strip()
    if not re.fullmatch(r"-?[0-9][0-9.,\s]*", text):
        return None
    text = text.replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:,\d{3})+", text):
        text = text.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _entity_scope(entity, explicit=""):
    if explicit:
        return str(explicit).strip().upper()
    text = str(entity or "").lower()
    if "group" in text or "集团" in text:
        return "GROUP"
    if any(token in text for token in ("airlines", "airways", "航空", "swiss", "eurowings")):
        return "AIRLINE"
    return "ENTITY"


def normalize_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"(\d{4})[年/.\-](\d{1,2})(?:[月/.\-](\d{1,2})日?)?", text)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day or 1):02d}"
    if re.fullmatch(r"\d{4}", text):
        return text
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return text


def stable_id(prefix, parts):
    digest = hashlib.sha256("|".join(str(item or "").strip().lower() for item in parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{digest}"


def normalize_source(source):
    item = dict(source or {})
    item["url"] = normalize_url(item.get("url"))
    item["source_id"] = str(item.get("source_id") or stable_id("S", [item.get("url"), item.get("title")]))
    item["title"] = str(item.get("title") or "").strip()
    item["publisher"] = str(item.get("publisher") or "").strip()
    item["source_type"] = str(item.get("source_type") or "OTHER").strip().upper()
    grade = str(item.get("source_grade") or "UNKNOWN").upper().replace(" ", "_")
    if grade in {"A", "B", "C", "D", "E"}:
        grade = f"GRADE_{grade}"
    item["source_grade"] = grade if grade in {"GRADE_A", "GRADE_B", "GRADE_C", "GRADE_D", "GRADE_E"} else "UNKNOWN"
    item["publication_date"] = normalize_date(item.get("publication_date"))
    item["accessed_at"] = normalize_date(item.get("accessed_at")) or date.today().isoformat()
    item["language"] = str(item.get("language") or "UNKNOWN")
    item["geography"] = str(item.get("geography") or "")
    item["is_primary_source"] = bool(item.get("is_primary_source"))
    item["datasets_supported"] = list(dict.fromkeys(str(x) for x in item.get("datasets_supported") or []))
    status = str(item.get("access_status") or "SUCCESS").upper().replace(" ", "_")
    status = {
        "OK": "SUCCESS", "OPENED": "SUCCESS", "ACCESSED": "SUCCESS",
        "ACCEPTED": "SUCCESS", "EXTRACTED": "SUCCESS", "COMPLETED": "SUCCESS",
        "LOGIN": "LOGIN_REQUIRED", "ROBOTS": "ROBOTS_BLOCKED",
    }.get(status, status)
    allowed = {"SUCCESS", "PAYWALL", "LOGIN_REQUIRED", "CAPTCHA", "ROBOTS_BLOCKED", "NOT_FOUND", "NETWORK_ERROR", "REJECTED"}
    item["access_status"] = status if status in allowed else "REJECTED"
    item["access_issue"] = str(item.get("access_issue") or "")
    return item


def normalize_observation(observation, source_lookup=None, industry=None):
    item = dict(observation or {})
    for key in ("dataset_id", "entity", "metric", "product_name", "category", "text_value", "geography", "channel", "price_type", "metric_definition", "source_id", "notes"):
        item[key] = str(item.get(key) or "").strip()
    item["channel"] = CHANNEL_ALIASES.get(item["channel"].lower(), CHANNEL_ALIASES.get(item["channel"], item["channel"]))
    item["geography"] = GEOGRAPHY_ALIASES.get(item["geography"], item["geography"])
    item["price_type"] = PRICE_TYPE_ALIASES.get(item["price_type"], item["price_type"])
    item["metric"] = METRIC_ALIASES.get(item["metric"], item["metric"])
    if route_industry(industry) == "aviation":
        item["metric"] = standardize_aviation_metric(item.get("metric_id") or item["metric"])
    item["metric_id"] = str(item.get("metric_id") or item["metric"]).strip()
    item["source_url"] = normalize_url(item.get("source_url"))
    if source_lookup and item["source_id"] in source_lookup and not item["source_url"]:
        item["source_url"] = source_lookup[item["source_id"]].get("url", "")
    raw_value = item.get("value")
    if raw_value is None and str(item.get("text_value") or "").strip().lower() not in PLACEHOLDERS:
        # Move only scalar text into value; narrative observations remain qualitative.
        raw_value = item.get("text_value") if re.fullmatch(r"\s*(?:EUR|USD|CNY|€|\$|¥)?\s*-?[0-9][0-9.,\s]*(?:%|欧分|€\s*cents?|million|thousand|千|百万)?\s*", str(item.get("text_value") or ""), re.I) else None
    item["value"] = _parse_numeric_value(raw_value)
    if raw_value is not None and item["value"] is not None and str(item.get("text_value") or "").strip() == str(raw_value).strip():
        item["text_value"] = ""
    item["unit"] = normalize_unit(item.get("unit"))
    if item["metric_id"] in AVIATION_METRICS:
        raw_unit = item["unit"]
        metric_unit = aviation_standard_unit(item["metric_id"])
        if item["metric_id"] == "passenger_count" and raw_unit == "thousand" and item["value"] is not None:
            item["value"] *= 1_000
            item["unit"] = "passengers"
        elif raw_unit == "euro_cents":
            item["unit"] = metric_unit
        elif metric_unit:
            item["unit"] = metric_unit
    item["currency"] = normalize_currency(item.get("currency"))
    item["period"] = normalize_date(item.get("period"))
    item["period_type"] = str(item.get("period_type") or ("FISCAL_YEAR" if "FY" in str(observation.get("period") or "").upper() else "CALENDAR_PERIOD" if item["period"] else "UNKNOWN"))
    item["period_type"] = item["period_type"].upper()
    if re.search(r"(?:^|\s)Q[1-4](?:\s|$)", str(item["period"]), re.IGNORECASE):
        item["period_type"] = "QUARTER"
    item["entity_scope"] = _entity_scope(item.get("entity"), item.get("entity_scope"))
    item["channel_scope"] = str(item.get("channel_scope") or item.get("channel") or "ALL").strip().upper()
    if route_industry(industry) == "aviation" and item["metric_id"] in {
        "available_seat_km", "revenue_passenger_km", "passenger_load_factor",
        "passenger_count", "flight_count",
    } and item["entity_scope"] in {"GROUP", "GROUP_INCL_CARGO"}:
        # ASK/RPK/passengers/flights are passenger-traffic measures; retain one
        # group scope so annual and quarterly observations form valid series.
        item["entity_scope"] = "GROUP"
    item["tax_basis"] = str(item.get("tax_basis") or "UNKNOWN").upper()
    item["observed_at"] = normalize_date(item.get("observed_at")) or date.today().isoformat()
    item["as_of_date"] = normalize_date(item.get("as_of_date")) or item["observed_at"]
    value_type = str(item.get("value_type") or "UNKNOWN").upper()
    item["value_type"] = value_type if value_type in {"ACTUAL", "HISTORICAL", "ESTIMATE", "FORECAST", "SCENARIO", "TARGET", "PROXY", "UNKNOWN"} else "UNKNOWN"
    inherited_grade = (
        source_lookup.get(item["source_id"], {}).get("source_grade")
        if source_lookup and item["source_id"] in source_lookup else None
    )
    grade = str(item.get("source_grade") or inherited_grade or "UNKNOWN").upper()
    if grade in {"A", "B", "C", "D", "E"}:
        grade = f"GRADE_{grade}"
    item["source_grade"] = grade if grade in {"GRADE_A", "GRADE_B", "GRADE_C", "GRADE_D", "GRADE_E"} else "UNKNOWN"
    verification = str(item.get("verification_status") or "NOT_CHECKED").upper()
    item["verification_status"] = verification if verification in {"SUPPORTED", "PARTIAL", "UNSUPPORTED", "NOT_CHECKED"} else "NOT_CHECKED"
    temporal = str(item.get("temporal_status") or "UNKNOWN").upper()
    item["temporal_status"] = temporal if temporal in {"CURRENT", "HISTORICAL", "FUTURE_PLAN", "SUPERSEDED", "UNKNOWN"} else "UNKNOWN"
    excerpt = str(item.get("evidence_excerpt") or "").strip()
    item["evidence_excerpt"] = excerpt[:500]
    item["confidence"] = item.get("confidence")
    if item["metric_id"] in AVIATION_METRICS and not item["metric_definition"]:
        item["metric_definition"] = aviation_metric_definition(item["metric_id"])
    group_fields = ["metric_id", "unit", "currency", "geography", "period_type", "entity_scope"]
    if item["dataset_id"] in {"prices", "price_observations", "product_prices", "pricing", "comparable_products"}:
        group_fields.extend(("period", "channel", "price_type"))
    item["comparability_group"] = stable_id("CG_", [item.get(k) for k in group_fields])
    item["observation_id"] = str(item.get("observation_id") or stable_id("O", [item.get(k) for k in ("dataset_id", "entity", "metric", "product_name", "value", "unit", "currency", "period", "geography", "channel", "price_type", "source_id")]))
    return item


def is_valid_observation(item, source_ids=None):
    if not item.get("dataset_id") or not item.get("entity") or not item.get("metric"):
        return False, "缺少dataset_id、entity或metric"
    if not item.get("source_id"):
        return False, "缺少source_id"
    if source_ids is not None and item.get("source_id") not in source_ids:
        return False, "source_id无法关联source_registry"
    text = str(item.get("text_value") or "").strip()
    if item.get("value") is None and (not text or text.lower() in PLACEHOLDERS):
        return False, "value与text_value均无有效提取结果"
    if item.get("value") is None and re.search(r"(?:search query|搜索查询|dataset说明|数据集说明)", text, re.I):
        return False, "搜索查询或自动数据集说明不是Observation"
    return True, ""


def canonicalize_entity(value, known_entities):
    text = str(value or "").strip()
    if not text:
        return ""
    def key(item):
        normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(item)).lower()
        return re.sub(r"(?:股份有限公司|有限责任公司|有限公司|集团|公司|inc|corp|ltd)$", "", normalized)
    value_key = key(text)
    for candidate in known_entities or []:
        candidate_key = key(candidate)
        if value_key == candidate_key or (min(len(value_key), len(candidate_key)) >= 4 and (value_key in candidate_key or candidate_key in value_key)):
            return str(candidate).strip()
    return text


def dedupe_sources(sources):
    result, seen_urls, seen_ids = [], set(), set()
    for raw in sources:
        item = normalize_source(raw)
        identity = item["url"] or item["source_id"]
        if identity in seen_urls or item["source_id"] in seen_ids:
            continue
        seen_urls.add(identity)
        seen_ids.add(item["source_id"])
        result.append(item)
    return result


def dedupe_observations(observations, sources=None, industry=None):
    lookup = {item["source_id"]: item for item in (sources or [])}
    result, seen = [], set()
    for raw in observations:
        expanded = expand_compound_aviation_observation(raw) if route_industry(industry) == "aviation" else [raw]
        for candidate in expanded:
            item = normalize_observation(candidate, lookup, industry)
            signature = tuple(item.get(key) for key in ("dataset_id", "entity", "metric_id", "product_name", "category", "value", "text_value", "unit", "currency", "period", "geography", "channel", "price_type", "source_id"))
            if signature in seen:
                continue
            seen.add(signature)
            result.append(item)
    return result
