import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


def base_report_data():
    return {
        "schema_version": "1.0",
        "scope": {
            "topic": "德国汽车市场",
            "analysis_type": "市场进入分析",
            "industry": "汽车",
            "geography": "德国",
            "analysis_date": "2026-08-06",
            "selected_template": "automotive",
        },
        "executive_summary": "测试",
        "kpis": [
            {
                "metric_id": "DE_BEV_2025",
                "label": "德国BEV注册量",
                "value": 545000,
                "unit": "辆",
                "currency": None,
                "geography": "德国",
                "period": "2025",
                "value_type": "ACTUAL",
                "source_fact_ids": ["F1"],
                "source_grade": "A",
                "confidence": "HIGH",
            }
        ],
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


class QualityPolicyTests(unittest.TestCase):
    def test_quality_policy_has_required_guardrails(self):
        policy = main.load_quality_policy()
        self.assertEqual(
            policy,
            {
                "deterministic_failure_enabled": True,
                "heuristic_max_severity": "WARN",
                "require_location_for_fail": True,
                "markdown_semantic_checks": "WARN_ONLY",
            },
        )

    def test_heuristic_fail_is_always_downgraded(self):
        checks = []
        main.add_check(
            checks,
            "测试语义规则",
            "FAIL",
            "关键词疑似不匹配",
            rule_id="TEST_HEURISTIC",
            rule_type=main.QUALITY_RULE_TYPE_HEURISTIC,
            issue_details=[
                {
                    "line_number": 3,
                    "excerpt": "不作领先判断",
                    "reason": "语义规则",
                    "suggested_fix": "人工复核",
                }
            ],
        )
        _, issues = main.apply_quality_policy(checks, Path.cwd())
        self.assertEqual(checks[0]["status"], "WARN")
        self.assertEqual(issues[0]["severity"], "WARNING")
        self.assertEqual(issues[0]["rule_type"], "HEURISTIC")

    def test_complete_german_market_metric_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            final_file = folder / "04_final_report.md"
            final_file.write_text("德国市场报告", encoding="utf-8")
            (folder / "04_report_data.json").write_text(
                json.dumps(base_report_data(), ensure_ascii=False), encoding="utf-8"
            )
            checks = []
            with patch.object(main, "Codex", side_effect=AssertionError("不得调用Agent")) as codex:
                main.add_structured_data_checks(checks, final_file, "德国市场报告", True)
        self.assertEqual(codex.call_count, 0)
        by_name = {check["name"]: check for check in checks}
        self.assertEqual(by_name["结构化市场指标"]["status"], "PASS")
        self.assertEqual(by_name["金额币种"]["status"], "PASS")

    def test_missing_market_field_names_metric_and_source(self):
        data = base_report_data()
        data["kpis"][0]["period"] = None
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            final_file = folder / "04_final_report.md"
            final_file.write_text("德国市场报告", encoding="utf-8")
            (folder / "04_report_data.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            checks = []
            main.add_structured_data_checks(checks, final_file, "德国市场报告", True)
            market_check = next(check for check in checks if check["name"] == "结构化市场指标")
            _, issues = main.apply_quality_policy(checks, folder)
        self.assertEqual(market_check["status"], "FAIL")
        self.assertIn("metric_id=DE_BEV_2025", market_check["detail"])
        self.assertIn("value=545000", market_check["detail"])
        self.assertIn("missing=period", market_check["detail"])
        issue = next(issue for issue in issues if issue["rule_id"] == "STRUCTURED_MARKET_FIELDS")
        self.assertEqual(issue["metric_id"], "DE_BEV_2025")
        self.assertEqual(issue["missing_fields"], ["period"])
        self.assertIn("kpis[0]", issue["source_location"])

    def test_negative_ranking_language_never_fails(self):
        data = base_report_data()
        data["competitor_comparisons"] = [
            {
                "comparison_id": "C1",
                "entities": ["小鹏", "特斯拉"],
                "metric": "综合性能",
                "geography": "德国",
                "period": "2025",
                "unit": "N/A",
                "currency": None,
                "comparable": False,
                "comparison_basis": "缺少统一口径",
                "ranking_claim": True,
                "source_fact_ids": ["F1"],
            }
        ]
        negative_lines = "\n".join(
            [
                "小鹏与特斯拉不能排名。",
                "本报告不作排名，也不作领先判断。",
                "缺少统一口径，数据不可比，结果待验证。",
                "该表不代表性能排名。",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            final_file = folder / "04_final_report.md"
            final_file.write_text(negative_lines, encoding="utf-8")
            (folder / "04_report_data.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            checks = []
            main.add_structured_data_checks(checks, final_file, negative_lines, True)
        competitor_checks = [check for check in checks if "竞品" in check["name"]]
        self.assertTrue(competitor_checks)
        self.assertNotIn("FAIL", {check["status"] for check in competitor_checks})

    def test_uncomparable_explicit_ranking_can_fail_with_location(self):
        data = base_report_data()
        data["competitor_comparisons"] = [
            {
                "comparison_id": "C1",
                "entities": ["小鹏", "特斯拉"],
                "metric": "综合性能",
                "geography": "德国",
                "period": "2025",
                "unit": "N/A",
                "currency": None,
                "comparable": False,
                "comparison_basis": "口径不同",
                "ranking_claim": True,
                "source_fact_ids": ["F1"],
            }
        ]
        final_text = "小鹏综合性能优于特斯拉。"
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            final_file = folder / "04_final_report.md"
            final_file.write_text(final_text, encoding="utf-8")
            (folder / "04_report_data.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            checks = []
            main.add_structured_data_checks(checks, final_file, final_text, True)
            _, issues = main.apply_quality_policy(checks, folder)
        check = next(check for check in checks if check["name"] == "结构化竞品比较")
        self.assertEqual(check["status"], "FAIL")
        issue = next(issue for issue in issues if issue["rule_id"] == "STRUCTURED_COMPARISON")
        self.assertEqual(issue["line_number"], 1)
        self.assertEqual(issue["metric_id"], "C1")
        self.assertEqual(issue["rule_type"], "DETERMINISTIC")
        required_fields = {
            "rule_id", "rule_type", "severity", "file", "line_number",
            "metric_id", "excerpt", "missing_fields", "reason",
            "suggested_fix", "confidence",
        }
        self.assertTrue(required_fields <= set(issue))

    def test_manifest_preserves_rich_quality_issue_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            main.create_manifest("test-run", "测试", folder)
            issue = {
                "check": "结构化市场指标",
                "status": "FAIL",
                "detail": "metric_id=M1 missing=period",
                "rule_id": "STRUCTURED_MARKET_FIELDS",
                "rule_type": "DETERMINISTIC",
                "severity": "ERROR",
                "file": "04_report_data.json",
                "line_number": None,
                "metric_id": "M1",
                "excerpt": '{"metric_id":"M1","value":10}',
                "missing_fields": ["period"],
                "reason": "结构化市场指标缺少必填口径字段",
                "suggested_fix": "补充period",
                "confidence": "HIGH",
                "source_location": "04_report_data.json:kpis[0]",
            }
            main.update_manifest(folder, quality_issues=[issue])
            saved = main.load_manifest(folder)["quality_issues"][0]
        required_fields = {
            "rule_id", "rule_type", "severity", "file", "line_number",
            "metric_id", "excerpt", "missing_fields", "reason",
            "suggested_fix", "confidence",
        }
        self.assertTrue(required_fields <= set(saved))
        self.assertEqual(saved["metric_id"], "M1")
        self.assertEqual(saved["missing_fields"], ["period"])


if __name__ == "__main__":
    unittest.main()
