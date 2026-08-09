import json
from pathlib import Path
import re


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_run"


def _load(name):
    return json.loads((SAMPLE / name).read_text(encoding="utf-8"))


def test_public_sample_is_synthetic_and_has_complete_lineage():
    scope = _load("00_analysis_scope.json")
    fact = _load("03_fact_check.json")
    report = _load("04_report_data.json")
    dashboard = _load("06_dashboard_data.json")
    observations = _load("data/observations.json")["observations"]
    sources = _load("data/sources.json")["sources"]

    assert scope["is_test_fixture"] is True
    observation_ids = {row["observation_id"] for row in observations}
    source_ids = {row["source_id"] for row in sources}
    assert {value for row in fact["claims"] for value in row["observation_ids"]} == observation_ids
    assert {value for row in fact["claims"] for value in row["source_ids"]} == source_ids
    assert set(report["_meta"]["observation_ids"]) == observation_ids
    assert {row["observation_id"] for row in dashboard["observations"]} == observation_ids


def test_public_sample_contains_no_personal_windows_path_or_secret():
    text = "\n".join(path.read_text(encoding="utf-8") for path in SAMPLE.rglob("*") if path.is_file())
    assert not re.search(r"(?i)C:\\Users\\", text)
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{16,}\b", text)
    assert not re.search(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}", text)
