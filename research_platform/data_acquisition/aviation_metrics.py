"""Deterministic aviation metric names and compound observation expansion."""

from __future__ import annotations

from copy import deepcopy
import re


AVIATION_METRICS = {
    "available_seat_km": ("million seat-km", "Available seat-kilometres (ASK), expressed in millions."),
    "revenue_passenger_km": ("million passenger-km", "Revenue passenger kilometres (RPK), expressed in millions."),
    "passenger_load_factor": ("%", "Revenue passenger kilometres divided by available seat-kilometres."),
    "passenger_count": ("passengers", "Number of passengers transported in the reporting period."),
    "flight_count": ("flights", "Number of operated flights in the reporting period."),
    "yield": ("euro_cents/passenger-km", "Passenger traffic revenue per revenue passenger-kilometre."),
    "rask": ("euro_cents/ASK", "Passenger traffic unit revenue per available seat-kilometre."),
    "cask_ex_fuel": ("euro_cents/ASK", "Unit cost per available seat-kilometre excluding fuel and emissions trading expenses."),
    "punctuality": ("%", "Share of flights arriving or departing within the disclosed punctuality threshold."),
    "regularity": ("%", "Share of scheduled flights operated, according to the issuer definition."),
    "employee_count": ("employees", "Number of employees at the stated reporting date or period average."),
    "specific_co2_emissions": ("g CO2/passenger-km", "Specific carbon dioxide emissions per passenger-kilometre."),
    "adjusted_ebit_margin": ("%", "Adjusted EBIT divided by revenue for the stated airline or group."),
}

METRIC_ALIASES = {
    "available_seat_km": ("available seat kilometres", "available seat-kilometres", "available seat kilometers", "ask", "angebotene sitzkilometer", "可用座公里", "可用座千米"),
    "revenue_passenger_km": ("revenue seat kilometres", "revenue seat-kilometres", "revenue passenger kilometres", "rpk", "rsk", "verkaufte sitzkilometer", "收入客公里"),
    "passenger_load_factor": ("passenger load factor", "load factor", "sitzladefaktor", "客座率"),
    "passenger_count": ("passengers", "passagiere", "fluggäste", "旅客", "乘客量"),
    "flight_count": ("number of flights", "flights", "flüge", "航班", "航班量"),
    "yield": ("yields", "yield", "durchschnittserlös", "收益率", "平均收益"),
    "rask": ("unit revenue", "rask", "stückerlöse", "单位收入"),
    "cask_ex_fuel": ("cask ex fuel", "cask without fuel", "unit cost", "stückkosten", "非燃油cask", "单位成本"),
    "punctuality": ("punctuality", "pünktlichkeit", "准点率"),
    "regularity": ("regularity", "regelmäßigkeit", "航班正常率"),
    "employee_count": ("employees", "employee count", "mitarbeiter", "beschäftigte", "员工人数"),
    "specific_co2_emissions": ("specific co2 emissions", "spezifische co2-emissionen", "单位二氧化碳排放"),
    "adjusted_ebit_margin": ("adjusted ebit margin", "adjusted ebit利润率", "调整后ebit利润率"),
}


def standardize_aviation_metric(value):
    text = re.sub(r"[^0-9a-zA-Z%\u4e00-\u9fffäöüß]+", " ", str(value or "")).strip().lower()
    if text in AVIATION_METRICS:
        return text
    for metric_id, aliases in METRIC_ALIASES.items():
        if any(alias in text for alias in aliases):
            return metric_id
    return str(value or "").strip()


def metric_definition(metric_id):
    return AVIATION_METRICS.get(metric_id, ("", metric_id))[1]


def standard_unit(metric_id):
    return AVIATION_METRICS.get(metric_id, ("", ""))[0]


def _number(value):
    text = str(value or "").strip().replace("\u2212", "-").replace("−", "-")
    if not text:
        return None
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


def _child(row, metric_id, value, unit=None, *, entity=None, entity_scope=None):
    item = deepcopy(row)
    item.pop("observation_id", None)
    item.pop("comparability_group", None)
    item["metric"] = metric_id
    item["metric_id"] = metric_id
    item["value"] = value
    item["text_value"] = ""
    item["unit"] = unit or standard_unit(metric_id)
    item["currency"] = "EUR" if metric_id in {"yield", "rask", "cask_ex_fuel"} else ""
    item["metric_definition"] = metric_definition(metric_id)
    item["entity"] = entity or item.get("entity")
    item["entity_scope"] = entity_scope or item.get("entity_scope") or (
        "GROUP" if "group" in str(item.get("entity") or "").lower() else "AIRLINE"
    )
    item["value_type"] = item.get("value_type") if item.get("value_type") not in {None, "", "UNKNOWN"} else "ACTUAL"
    return item


def expand_compound_aviation_observation(row):
    """Split narrative aviation rows only when labels and values are unambiguous."""
    if str(row.get("dataset_id") or "") != "operating_metrics" or row.get("value") is not None:
        return [row]
    text = str(row.get("text_value") or "")
    if not text:
        return [row]
    children = []
    patterns = (
        ("flight_count", r"(?:航班|flights?)\s*([0-9][\d,.]*)\s*(?:架次)?", "flights"),
        ("passenger_count", r"(?:旅客|passengers?)\s*([0-9][\d,.]*)\s*(百万|million|千人|thousand)?", "passengers"),
        ("available_seat_km", r"(?:ASK|available seat[- ]kilomet(?:res|ers)|可用座公里)\s*([0-9][\d,.]*)\s*(?:百万|million)?", "million seat-km"),
        ("revenue_passenger_km", r"(?:RPK|RSK|revenue (?:seat|passenger)[- ]kilomet(?:res|ers)|收入客公里)\s*([0-9][\d,.]*)\s*(?:百万|million)?", "million passenger-km"),
        ("passenger_load_factor", r"(?:客座率|passenger load factor|load factor)\s*(?:为|was|at)?\s*(-?[0-9]+(?:[.,][0-9]+)?)\s*%", "%"),
    )
    for metric_id, pattern, unit in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw_value = match.group(1)
        scale = (match.group(2) or "").lower() if metric_id == "passenger_count" else ""
        if metric_id == "passenger_count" and scale in {"百万", "million"} and re.fullmatch(r"\d{1,3}[.,]\d{1,3}", raw_value):
            value = float(raw_value.replace(",", "."))
        else:
            value = _number(raw_value)
        if value is None:
            continue
        if metric_id == "passenger_count":
            if scale in {"百万", "million"}:
                value *= 1_000_000
            elif scale in {"千人", "thousand"}:
                value *= 1_000
        children.append(_child(row, metric_id, value, unit))

    metric_text = str(row.get("metric") or "")
    if "利润率" in f"{metric_text} {text}" or "adjusted ebit" in metric_text.lower() or "adjusted ebit margin" in text.lower():
        declared_entities = [value.strip() for value in re.split(r"[;；]", str(row.get("entity") or "")) if value.strip()]
        declared_values = []
        sequence = re.search(r"分别为\s*((?:-?[0-9]+(?:[.,][0-9]+)?%?[、,，;；]?\s*){2,})", text)
        if sequence:
            declared_values = re.findall(r"-?[0-9]+(?:[.,][0-9]+)?(?=\s*%)", sequence.group(1))
        if len(declared_entities) >= 2 and len(declared_values) >= len(declared_entities):
            children.extend(
                _child(row, "adjusted_ebit_margin", _number(value), "%", entity=entity, entity_scope="AIRLINE")
                for entity, value in zip(declared_entities, declared_values)
            )
        for entity in ("Lufthansa Airlines", "SWISS", "Austrian Airlines", "Brussels Airlines", "Eurowings"):
            if any(item.get("entity") == entity for item in children):
                continue
            match = re.search(rf"{re.escape(entity)}[^0-9-]*(-?[0-9]+(?:[.,][0-9]+)?)\s*%", text, re.IGNORECASE)
            if match:
                children.append(_child(row, "adjusted_ebit_margin", _number(match.group(1)), "%", entity=entity, entity_scope="AIRLINE"))
        if not children:
            values = re.findall(r"-?[0-9]+(?:[.,][0-9]+)?(?=%)", text)
            entities = ("Lufthansa Airlines", "SWISS", "Austrian Airlines", "Brussels Airlines", "Eurowings")
            if len(values) >= len(entities):
                children.extend(_child(row, "adjusted_ebit_margin", _number(value), "%", entity=entity, entity_scope="AIRLINE") for entity, value in zip(entities, values))
    return children or [row]
