import unittest
from unittest.mock import patch

import main


class AnalysisTemplateTests(unittest.TestCase):
    def test_every_industry_template_has_required_structure_without_agent(self):
        expected_ids = {
            "general",
            "ai_software",
            "consumer_retail",
            "manufacturing",
            "automotive",
            "finance",
            "healthcare_pharma",
            "energy",
            "internet_platform",
        }
        required_fields = {
            "template_id",
            "template_name",
            "applicable_industries",
            "required_sections",
            "optional_sections",
            "industry_metrics",
            "preferred_sources",
            "risk_dimensions",
            "comparison_dimensions",
        }
        with patch.object(
            main,
            "Codex",
            side_effect=AssertionError("模板结构测试不得调用Agent"),
        ) as codex:
            templates = main.load_analysis_templates()

        self.assertEqual(codex.call_count, 0)
        self.assertEqual(set(templates), expected_ids)
        for template_id, template in templates.items():
            with self.subTest(template_id=template_id):
                self.assertEqual(template["template_id"], template_id)
                self.assertTrue(required_fields <= set(template))
                for field in required_fields - {"template_id", "template_name"}:
                    self.assertIsInstance(template[field], list)
                    self.assertTrue(template[field])

    def test_general_template_contains_all_required_sections(self):
        general = main.load_analysis_templates()["general"]
        expected_sections = {
            "分析范围与口径",
            "行业/产品定位",
            "市场规模与增长",
            "产业链与价值链",
            "客户与需求",
            "商业模式",
            "竞争格局",
            "核心能力与壁垒",
            "政策、技术及宏观趋势",
            "风险与机会",
            "战略建议",
            "尚待验证问题",
            "Review问题处理情况",
            "Human Feedback处理情况",
        }
        self.assertEqual(set(general["required_sections"]), expected_sections)

    def test_scope_is_local_and_selects_industry_template(self):
        with patch.object(
            main,
            "Codex",
            side_effect=AssertionError("范围生成不得调用Agent"),
        ) as codex:
            scope = main.build_analysis_scope(
                analysis_type="行业分析",
                topic="中国新能源汽车",
                industry="汽车",
                geography="中国",
                analysis_date="2026-08-06",
                focus_questions="销量趋势\n供应链风险",
                competitors="比亚迪\n特斯拉",
                depth="深度版",
                currency="CNY",
                language="中文",
            )

        self.assertEqual(codex.call_count, 0)
        self.assertEqual(scope["selected_template"], "automotive")
        self.assertEqual(scope["focus_questions"], ["销量趋势", "供应链风险"])
        self.assertEqual(scope["competitors"], ["比亚迪", "特斯拉"])
        self.assertIn("销量、车型与价格带", scope["required_sections"])

    def test_dynamic_quality_rules_are_local(self):
        scope = main.build_analysis_scope(
            analysis_type="竞品比较",
            topic="甲公司与乙公司",
            industry="消费",
            geography="中国",
            analysis_date="2026-08-06",
        )
        final_text = """
## 市场规模与增长
【推断】市场规模为100亿。

## 竞争格局
【推断】甲公司排名高于乙公司。

## 风险与机会
【事实】甲公司是行业第一。

## 战略建议
2028年销量达到100万辆。
"""
        fact_entries = {
            "F1": {
                "fields": {
                    "original_claim": "甲公司营收为100亿元。",
                    "source_grade": "D",
                }
            }
        }
        with patch.object(
            main,
            "Codex",
            side_effect=AssertionError("动态质量检查不得调用Agent"),
        ) as codex:
            issues = main.data_quality_issues(final_text, scope, fact_entries)

        self.assertEqual(codex.call_count, 0)
        self.assertTrue(issues["market_scope"])
        self.assertTrue(issues["currency"])
        self.assertTrue(issues["forecast"])
        self.assertTrue(issues["self_claim"])
        self.assertEqual(issues["financial_source"], ["F1"])
        self.assertTrue(issues["comparison"])

    def test_required_sections_are_template_driven(self):
        missing = main.missing_required_sections(
            "## 分析范围与口径\n内容\n## 风险与机会\n内容",
            ["分析范围与口径", "风险与机会", "战略建议"],
        )
        self.assertEqual(missing, ["战略建议"])


if __name__ == "__main__":
    unittest.main()
