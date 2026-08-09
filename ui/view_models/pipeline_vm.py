from pipeline_v2.model import STAGE_ORDER

LABELS = {"scope":"Scope confirmation", "data":"Data requirements & acquisition", "research":"Research", "review":"Review", "fact_check":"Fact verification", "human":"Human review", "strategy":"Strategy", "report":"Report rendering", "dashboard":"Dashboard", "quality":"Quality"}


def pipeline_view_model(run):
    rows = []
    for index, name in enumerate(STAGE_ORDER, 1):
        stage = run.get("stages", {}).get(name, {})
        rows.append({"index": index, "id": name, "label": LABELS[name], **stage, "is_current": name == run.get("current_stage")})
    return {"stages": rows, "can_rebuild": any(x.get("status") == "STALE" for x in rows), "read_only": bool(run.get("read_only"))}

