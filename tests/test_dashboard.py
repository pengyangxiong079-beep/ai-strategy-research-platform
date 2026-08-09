import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from dashboard.analysis_types import normalize_analysis_type
from dashboard.compiler import compile_dashboard
from dashboard.exporter import generate_dashboard_html
from dashboard.registry import load_dashboard_template, prepare_components
from dashboard.schema import (
    ReportDataValidationError,
    validate_dashboard_data,
    validate_report_data,
)


def metric(**changes):
    value = {
        "metric_id": "M1",
        "label": "市场收入",
        "value": 10.0,
        "unit": "million",
        "currency": "EUR",
        "geography": "Germany",
        "period": "2025",
        "value_type": "ACTUAL",
        "source_fact_ids": ["F1"],
        "source_grade": "A",
        "confidence": "HIGH",
    }
    value.update(changes)
    return value


def report_data(**changes):
    value = {
        "schema_version": "1.0",
        "scope": {
            "topic": "测试公司",
            "analysis_type": "公司分析",
            "industry": "汽车",
            "geography": "Germany",
            "analysis_date": "2026-08-06",
            "selected_template": "automotive",
        },
        "executive_summary": "测试摘要",
        "kpis": [metric()],
        "time_series": [],
        "market_segments": [],
        "competitor_comparisons": [],
        "risks": [],
        "opportunities": [],
        "recommendations": [],
        "roadmap": [],
        "evidence_summary": {
            "verified": 1,
            "partial": 0,
            "unsupported": 0,
            "superseded": 0,
        },
        "data_gaps": [],
    }
    value.update(changes)
    return value


class DashboardTests(unittest.TestCase):
    def make_run(self, folder, *, quality="PASS", facts=None, data=None, legacy_manifest=False):
        folder = Path(folder)
        scope = report_data()["scope"]
        (folder / "00_analysis_scope.json").write_text(
            json.dumps(scope, ensure_ascii=False), encoding="utf-8"
        )
        (folder / "03_fact_check.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "facts": facts
                    or [{"fact_id": "F1", "result": "VERIFIED", "source_grade": "A"}],
                }
            ),
            encoding="utf-8",
        )
        (folder / "04_final_report.md").write_text("# Final", encoding="utf-8")
        (folder / "04_report_data.json").write_text(
            json.dumps(data or report_data(), ensure_ascii=False), encoding="utf-8"
        )
        (folder / "05_quality_check.md").write_text(
            f"# 本地质量检查报告\n\n## 总体结果\n\n**{quality}**\n",
            encoding="utf-8",
        )
        manifest = {"topic": "测试公司", "quality_check_status": quality}
        if not legacy_manifest:
            manifest.update({"schema_version": "2.1", "latest_revision": "rev_001"})
        (folder / "run_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

    def test_schema_validation(self):
        self.assertEqual(validate_report_data(report_data())["schema_version"], "1.0")

    def test_report_schema_accepts_complete_modelled_scenario(self):
        scenario = {
            "scenario_id": "SC_BASE", "label": "Base", "base_period": "2025", "end_period": "2030",
            "value_type": "MODELLED", "starting_value": 100,
            "annual_points": [{"period": "2030", "value": 125}],
            "assumptions": ["Synthetic fixture"], "formula": "100 * 1.25",
            "target_value": 125, "target_gap": 0,
            "trigger_conditions": ["Fixture trigger"], "risks": [],
            "source_fact_ids": ["F1"], "source_observation_ids": ["OBS1"],
            "confidence": "MEDIUM",
        }
        validated = validate_report_data(report_data(scenarios=[scenario]))
        self.assertEqual(validated["scenarios"][0]["value_type"], "MODELLED")

    def test_money_requires_currency(self):
        with self.assertRaises(ReportDataValidationError) as context:
            validate_report_data(report_data(kpis=[metric(currency=None)]))
        self.assertIn("currency", " ".join(context.exception.errors))

    def test_rpk_volume_is_not_misclassified_as_money(self):
        data = report_data(
            kpis=[
                metric(
                    metric_id="lh_rpk_2025",
                    label="集团RPK",
                    value=2817.65,
                    unit="亿收入客公里",
                    currency=None,
                )
            ]
        )
        self.assertEqual(validate_report_data(data)["kpis"][0]["currency"], None)

    def test_cost_percentage_change_is_not_misclassified_as_money(self):
        data = report_data(
            market_segments=[
                {
                    "segment_id": "passenger_airlines",
                    "label": "Passenger Airlines",
                    "metrics": [
                        metric(
                            metric_id="passenger_cask_ex_fuel_carbon_change_2025",
                            label="非燃油及碳成本CASK同比变化",
                            value=1.9,
                            unit="%",
                            currency=None,
                        )
                    ],
                }
            ],
            kpis=[],
        )
        validated = validate_report_data(data)
        self.assertIsNone(validated["market_segments"][0]["metrics"][0]["currency"])

    def test_market_metric_requires_period(self):
        with self.assertRaises(ReportDataValidationError) as context:
            validate_report_data(report_data(kpis=[metric(period=None)]))
        self.assertIn("period", " ".join(context.exception.errors))

    def test_unsupported_fact_is_excluded_without_agent(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            main, "Codex", side_effect=AssertionError("compiler不得调用Agent")
        ) as codex:
            self.make_run(
                temporary,
                facts=[{"fact_id": "F1", "result": "UNSUPPORTED", "source_grade": "D"}],
            )
            dashboard = compile_dashboard(temporary)
        self.assertEqual(codex.call_count, 0)
        self.assertEqual(dashboard["report_data"]["kpis"], [])
        self.assertEqual(dashboard["excluded_metrics"][0]["metric_id"], "M1")

    def test_compiler_adds_verification_and_temporal_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(temporary)
            dashboard = compile_dashboard(temporary)
        compiled = dashboard["report_data"]["kpis"][0]
        self.assertEqual(compiled["verification_status"], "SUPPORTED")
        self.assertEqual(compiled["temporal_status"], "HISTORICAL")

    def test_analysis_type_aliases_and_generic_fallback(self):
        self.assertEqual(normalize_analysis_type("竞争对手分析"), "COMPETITOR_ANALYSIS")
        self.assertEqual(normalize_analysis_type("国际市场进入"), "MARKET_ENTRY")
        self.assertEqual(normalize_analysis_type("未知类型"), "GENERIC_STRATEGY")

    def test_compiler_writes_valid_dashboard_v2(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(temporary)
            dashboard = compile_dashboard(temporary)
        self.assertEqual(dashboard["schema_version"], "2.0")
        self.assertEqual(dashboard["meta"]["analysis_type"], "COMPANY_STRATEGY")
        self.assertEqual(validate_dashboard_data(dashboard)["schema_version"], "2.0")

    def test_quality_fail_excludes_only_the_failed_metric(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = report_data(kpis=[metric(metric_id="GOOD"), metric(metric_id="BAD")])
            self.make_run(root, quality="FAIL", data=data)
            (root / "05_quality_check.json").write_text(
                json.dumps(
                    {
                        "overall_status": "FAIL",
                        "quality_issues": [
                            {"metric_id": "BAD", "severity": "ERROR", "reason": "口径失败"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            dashboard = compile_dashboard(root)
        self.assertEqual([item["metric_id"] for item in dashboard["metrics"]], ["GOOD"])
        self.assertEqual(dashboard["dashboard_status"], "BLOCKED_BY_QUALITY")
        self.assertTrue(any(item.get("metric_id") == "BAD" for item in dashboard["quality"]["excluded_fields"]))

    def test_non_comparable_data_is_never_marked_rankable(self):
        comparison = {
            "comparison_id": "C1",
            "entities": ["A", "B"],
            "metric": "门店数",
            "geography": None,
            "period": "2026",
            "unit": "家",
            "currency": None,
            "comparable": True,
            "comparison_basis": "地区范围不同",
            "ranking_claim": False,
            "source_fact_ids": ["F1"],
            "values": [{"entity": "A", "value": 10}, {"entity": "B", "value": 20}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(temporary, data=report_data(competitor_comparisons=[comparison]))
            dashboard = compile_dashboard(temporary)
        self.assertFalse(dashboard["comparisons"][0]["is_comparable"])
        self.assertIn("缺少统一地区", dashboard["comparisons"][0]["comparability_issues"])

    def test_legacy_historical_fact_is_valid_for_trend_analysis(self):
        series = {
            "series_id": "S1",
            "label": "历史趋势",
            "chart_type": "LINE",
            "points": [metric(metric_id="H1", period="2024")],
        }
        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(
                temporary,
                facts=[{"fact_id": "F1", "result": "HISTORICAL", "source_grade": "A"}],
                data=report_data(kpis=[], time_series=[series]),
            )
            dashboard = compile_dashboard(temporary)
        point = dashboard["time_series"][0]["points"][0]
        self.assertEqual(point["verification_status"], "SUPPORTED")
        self.assertEqual(point["temporal_status"], "HISTORICAL")

    def test_partial_fact_forces_low_confidence_and_cannot_be_actual(self):
        partial_fact = [{"fact_id": "F1", "result": "PARTIAL", "source_grade": "C"}]
        with tempfile.TemporaryDirectory() as temporary:
            data = report_data(kpis=[metric(value_type="ESTIMATE", confidence="HIGH")])
            self.make_run(temporary, facts=partial_fact, data=data)
            dashboard = compile_dashboard(temporary)
        self.assertEqual(dashboard["report_data"]["kpis"][0]["confidence"], "LOW")

        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(temporary, facts=partial_fact)
            dashboard = compile_dashboard(temporary)
        self.assertEqual(dashboard["report_data"]["kpis"], [])

    def test_missing_component_data_does_not_fail_dashboard(self):
        components = prepare_components(
            report_data(kpis=[]), load_dashboard_template("general")
        )
        self.assertTrue(components)
        self.assertTrue(any(item["status"] == "INSUFFICIENT_DATA" for item in components))

    def test_quality_fail_produces_viewable_draft_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(temporary, quality="FAIL")
            dashboard = compile_dashboard(temporary)
        self.assertEqual(dashboard["dashboard_status"], "BLOCKED_BY_QUALITY")
        self.assertIn("不应用于正式决策", dashboard["warning"])

    def test_automotive_template_loads_without_renderer_duplication(self):
        template = load_dashboard_template("automotive")
        component_ids = {item["component_id"] for item in template["components"]}
        self.assertEqual(template["template_id"], "automotive")
        self.assertTrue(
            {"bev_registration_trend", "powertrain_mix", "model_price_comparison",
             "channel_coverage", "charging_infrastructure", "market_entry_roadmap"}
            <= component_ids
        )

    def test_legacy_manifest_is_compatible(self):
        normalized = main.normalize_manifest({"topic": "旧报告"})
        self.assertEqual(normalized["dashboard_status"], "UNAVAILABLE")
        with tempfile.TemporaryDirectory() as temporary:
            self.make_run(temporary, legacy_manifest=True)
            dashboard = compile_dashboard(temporary)
        self.assertEqual(dashboard["dashboard_status"], "READY")

    def test_revision_switch_loads_each_versions_own_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            revisions = root / "revisions"
            for number, summary in ((0, "旧版"), (1, "新版")):
                folder = revisions / f"rev_{number:03d}"
                folder.mkdir(parents=True)
                data = report_data(executive_summary=summary)
                (folder / "revision_request.md").write_text("request", encoding="utf-8")
                (folder / "04_final_report.md").write_text(summary, encoding="utf-8")
                (folder / "05_quality_check.md").write_text("**PASS**", encoding="utf-8")
                (folder / "04_report_data.json").write_text(json.dumps(data), encoding="utf-8")
                (folder / "06_dashboard_data.json").write_text(
                    json.dumps({"report_data": data, "dashboard_status": "READY"}),
                    encoding="utf-8",
                )
                (folder / "revision_manifest.json").write_text(
                    json.dumps({"revision_id": f"rev_{number:03d}"}), encoding="utf-8"
                )
            old = main.load_revision_version(root, "rev_000")
            new = main.load_revision_version(root, "rev_001")
        self.assertEqual(old["report_data"]["executive_summary"], "旧版")
        self.assertEqual(new["dashboard"]["report_data"]["executive_summary"], "新版")

    def test_html_export_is_self_contained_and_selects_requested_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            web_root = Path(temporary) / "dashboard-web"
            root.mkdir()
            (web_root / "dist").mkdir(parents=True)
            (web_root / "dist" / "index.html").write_text(
                "<!doctype html><html><head></head><body><div id='root'></div></body></html>",
                encoding="utf-8",
            )
            (root / "00_analysis_scope.json").write_text(
                json.dumps(report_data()["scope"], ensure_ascii=False), encoding="utf-8"
            )
            (root / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "topic": "测试<公司>",
                        "final_status": "COMPLETED",
                        "api_token": "must-not-leak",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            for number, summary in ((0, "旧版"), (1, "新版")):
                folder = root / "revisions" / f"rev_{number:03d}"
                folder.mkdir(parents=True)
                data = report_data(executive_summary=summary)
                (folder / "06_dashboard_data.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "1.0",
                            "dashboard_status": "READY",
                            "quality_status": "PASS",
                            "report_data": data,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                (folder / "revision_manifest.json").write_text(
                    json.dumps(
                        {
                            "revision_id": f"rev_{number:03d}",
                            "quality_check_status": "PASS",
                        }
                    ),
                    encoding="utf-8",
                )

            destination = generate_dashboard_html(
                root, "rev_000", web_root=web_root
            )
            html = destination.read_text(encoding="utf-8")

        self.assertEqual(
            destination.relative_to(root).as_posix(),
            "revisions/rev_000/dashboard/dashboard.html",
        )
        self.assertIn('"selected_key":"run-1::rev_000"', html)
        self.assertIn('"revision_count":2', html)
        self.assertIn("测试\\u003c公司>", html)
        self.assertNotIn("must-not-leak", html)
        self.assertIn("dashboard-embedded-data", html)


if __name__ == "__main__":
    unittest.main()
