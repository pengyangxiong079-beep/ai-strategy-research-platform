import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from .test_workflow import FACT_CHECK, FINAL, RESEARCH, REVIEW


class StreamlitApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_folder = Path(self.temp_dir.name)
        self.files = {
            "scope": self.output_folder / "00_analysis_scope.json",
            "research": self.output_folder / "01_research_brief.md",
            "review": self.output_folder / "02_review_notes.md",
            "fact": self.output_folder / "03_fact_check.md",
            "feedback": self.output_folder / "03_human_feedback.md",
            "final": self.output_folder / "04_final_report.md",
            "quality": self.output_folder / "05_quality_check.md",
        }
        self.scope = {
            "schema_version": "1.0",
            "analysis_type": "公司分析",
            "topic": "测试产品",
            "industry": "自动判断",
            "geography": "全球",
            "analysis_date": "2026-08-06",
            "time_horizon": "未指定",
            "objective": "形成可验证的战略研究结论",
            "focus_questions": [],
            "competitors": [],
            "depth": "标准版",
            "currency": "未指定",
            "language": "中文",
            "selected_template": "general",
            "required_sections": [],
            "optional_sections": [],
        }
        self.scope_text = json.dumps(self.scope, ensure_ascii=False, indent=2)
        self.files["scope"].write_text(self.scope_text, encoding="utf-8")
        self.files["research"].write_text(RESEARCH, encoding="utf-8")
        self.files["review"].write_text(REVIEW, encoding="utf-8")
        self.files["fact"].write_text(FACT_CHECK, encoding="utf-8")
        self.files["feedback"].write_text("# 人工补充意见\n\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def research_result(self):
        return {
            "topic": "测试产品",
            "output_folder": self.output_folder,
            "workflow_stage": "等待人工审核",
            "quality_status": None,
            "manifest": self.manifest("AWAITING_APPROVAL"),
            "files": self.files,
            "contents": {
                "scope": self.scope_text,
                "research": RESEARCH,
                "review": REVIEW,
                "fact": FACT_CHECK,
                "feedback": "# 人工补充意见\n\n",
                "final": None,
                "quality": None,
            },
        }

    def final_result(self):
        quality = "# 本地质量检查报告\n\n**PASS**"
        self.files["final"].write_text(FINAL, encoding="utf-8")
        self.files["quality"].write_text(quality, encoding="utf-8")
        manifest = self.manifest("COMPLETED")
        (self.output_folder / "run_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "topic": "测试产品",
            "output_folder": self.output_folder,
            "workflow_stage": "已完成",
            "quality_status": "PASS",
            "manifest": manifest,
            "files": self.files,
            "contents": {
                "scope": self.scope_text,
                "research": RESEARCH,
                "review": REVIEW,
                "fact": FACT_CHECK,
                "feedback": "# 人工补充意见\n\n重点分析风险。\n",
                "final": FINAL,
                "quality": quality,
            },
        }

    def manifest(self, final_status):
        return {
            "schema_version": "1.0",
            "run_id": "20260806_120000_测试产品",
            "topic": "测试产品",
            "analysis_type": "公司分析",
            "industry": "自动判断",
            "geography": "全球",
            "analysis_date": "2026-08-06",
            "selected_template": "general",
            "created_at": "2026-08-06T12:00:00+02:00",
            "updated_at": "2026-08-06T12:01:00+02:00",
            "current_stage": "已完成" if final_status == "COMPLETED" else "等待人工审核",
            "final_status": final_status,
            "research_status": "COMPLETED",
            "review_status": "COMPLETED",
            "fact_check_status": "COMPLETED",
            "approval_status": "APPROVED" if final_status == "COMPLETED" else "AWAITING_APPROVAL",
            "strategy_status": "COMPLETED" if final_status == "COMPLETED" else "PENDING",
            "quality_check_status": "PASS" if final_status == "COMPLETED" else "PENDING",
            "human_feedback": "重点分析风险。",
            "stage_durations_seconds": {
                "research": 1.0,
                "review": 2.0,
                "fact_check": 3.0,
                "human_approval": 4.0,
                "strategy": 5.0,
                "quality_check": 0.1,
            },
            "output_files": {},
            "error_message": "",
            "quality_issues": [],
        }

    def prepared_result(self):
        manifest = self.manifest("AWAITING_SCOPE_CONFIRMATION")
        manifest["current_stage"] = "等待确认研究范围"
        return {
            "run_id": manifest["run_id"],
            "output_folder": self.output_folder,
            "scope": self.scope,
            "manifest": manifest,
        }

    def revision_result(self):
        manifest = self.manifest("COMPLETED")
        manifest["latest_revision"] = "rev_001"
        manifest["revision_status"] = "COMPLETED"
        return {
            "manifest": manifest,
            "revision": {
                "revision_id": "rev_001",
                "revision_type": "LOCAL_RECHECK",
            },
            "quality_status": "PASS",
            "quality": "# 本地质量检查报告\n\n**PASS**",
        }

    @staticmethod
    def button(app, label):
        return next(button for button in app.button if button.label == label)

    def test_human_approval_state_machine_and_refresh_deduplication(self):
        with (
            patch(
                "main.prepare_analysis_run", return_value=self.prepared_result()
            ) as prepare_scope,
            patch("main.run_research_phase", return_value=self.research_result()) as research,
            patch("main.run_strategy_phase", return_value=self.final_result()) as strategy,
        ):
            app_path = Path(__file__).resolve().parents[1] / "app.py"
            app = AppTest.from_file(str(app_path)).run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual([tab.label for tab in app.tabs], [
                "Analysis Scope",
                "Data Coverage",
                "Research Brief",
                "Review Notes",
                "Fact Check",
            ])
            self.assertTrue(self.button(app, "批准并生成最终报告").disabled)

            next(
                item for item in app.text_input if item.label == "分析对象（topic）*"
            ).set_value("测试产品")
            self.button(app, "开始研究").click()
            app.run(timeout=20)

            self.assertEqual(prepare_scope.call_count, 1)
            self.assertEqual(app.session_state["workflow_phase"], "等待确认研究范围")
            self.assertEqual(research.call_count, 0)
            self.button(app, "确认研究范围").click()
            app.run(timeout=20)

            self.assertEqual(research.call_count, 1)
            self.assertEqual(app.session_state["workflow_phase"], "等待人工审核")
            self.assertFalse(self.button(app, "批准并生成最终报告").disabled)
            self.assertEqual([tab.label for tab in app.tabs], [
                "Analysis Scope",
                "Data Coverage",
                "Research Brief",
                "Review Notes",
                "Fact Check",
            ])

            # 普通刷新不会重新执行前三个Agent。
            app.run(timeout=20)
            self.assertEqual(research.call_count, 1)

            next(
                item for item in app.text_area if item.label == "人工补充意见"
            ).set_value("请补充官方来源。")
            self.button(app, "根据意见重新研究").click()
            app.run(timeout=20)
            self.assertEqual(research.call_count, 2)
            self.assertEqual(
                research.call_args_list[1].kwargs["human_feedback"],
                "请补充官方来源。",
            )
            self.assertEqual(app.session_state["workflow_phase"], "等待人工审核")
            self.assertEqual(strategy.call_count, 0)

            next(
                item for item in app.text_area if item.label == "人工补充意见"
            ).set_value("重点分析风险。")
            self.button(app, "批准并生成最终报告").click()
            app.run(timeout=20)

            self.assertEqual(strategy.call_count, 1)
            self.assertEqual(app.session_state["workflow_phase"], "已完成")
            self.assertEqual([tab.label for tab in app.tabs], [
                "Analysis Scope",
                "Data Coverage",
                "Research Brief",
                "Review Notes",
                "Fact Check",
                "Human Feedback",
                "Final Report",
                "Quality Check",
                "Dashboard",
            ])

            app.run(timeout=20)
            self.assertEqual(strategy.call_count, 1)

    def test_opening_history_reads_files_without_agent_calls(self):
        history_result = self.final_result()
        history_manifest = history_result["manifest"]
        history_record = dict(history_manifest)
        history_record["output_folder"] = self.output_folder
        history_record["manifest_path"] = self.output_folder / "run_manifest.json"

        with (
            patch(
                "main.prepare_analysis_run",
                return_value=self.prepared_result(),
            ),
            patch("main.list_run_manifests", return_value=[history_record]),
            patch("main.load_run_history", return_value=history_result) as load_history,
            patch("main.build_run_zip", return_value=b"zip-data") as build_zip,
            patch(
                "main.rerun_local_revision",
                return_value=self.revision_result(),
            ) as local_revision,
            patch("main.run_research_phase") as research,
            patch("main.run_strategy_phase") as strategy,
        ):
            app_path = Path(__file__).resolve().parents[1] / "app.py"
            app = AppTest.from_file(str(app_path)).run(timeout=20)
            history_search = next(
                item for item in app.text_input if item.label == "按主题搜索"
            )
            history_search.set_value("不存在的主题")
            app.run(timeout=20)
            self.assertFalse(any("测试产品" in button.label for button in app.button))
            history_search = next(
                item for item in app.text_input if item.label == "按主题搜索"
            )
            history_search.set_value("测试产品")
            app.run(timeout=20)
            history_button = next(
                button for button in app.button if "测试产品" in button.label
            )
            history_button.click()
            app.run(timeout=20)

            self.assertEqual(load_history.call_count, 1)
            self.assertEqual(research.call_count, 0)
            self.assertEqual(strategy.call_count, 0)
            self.assertTrue(app.session_state["viewing_history"])
            self.assertEqual([tab.label for tab in app.tabs], [
                "Analysis Scope",
                "Data Coverage",
                "Research Brief",
                "Review Notes",
                "Fact Check",
                "Human Feedback",
                "Final Report",
                "Quality Check",
                "Dashboard",
            ])
            self.assertGreaterEqual(build_zip.call_count, 1)

            self.assertFalse(self.button(app, "进入修订").disabled)
            self.button(app, "进入修订").click()
            app.run(timeout=20)
            self.assertTrue(app.session_state["revision_center_open"])
            self.assertTrue(any(item.label == "仅重新运行本地检查" for item in app.button))
            self.assertTrue(any(item.label == "让Strategy Agent修订报告" for item in app.button))
            self.assertTrue(any(item.label == "根据问题重新研究" for item in app.button))
            self.button(app, "仅重新运行本地检查").click()
            app.run(timeout=20)
            self.assertEqual(local_revision.call_count, 1)
            app.run(timeout=20)
            self.assertEqual(local_revision.call_count, 1)
            self.button(app, "返回报告").click()
            app.run(timeout=20)

            # 可以从历史记录返回打开历史前的当前页面，不触发Agent。
            self.button(app, "当前分析").click()
            app.run(timeout=20)
            self.assertFalse(app.session_state["viewing_history"])
            self.assertEqual(app.session_state["workflow_phase"], "尚未开始")
            self.assertEqual(research.call_count, 0)
            self.assertEqual(strategy.call_count, 0)

            # 新分析会清空当前页面状态，但不会删除历史记录。
            history_button = next(
                button for button in app.button if "测试产品" in button.label
            )
            history_button.click()
            app.run(timeout=20)
            self.assertTrue(app.session_state["viewing_history"])
            self.button(app, "新分析").click()
            app.run(timeout=20)
            self.assertFalse(app.session_state["viewing_history"])
            self.assertEqual(app.session_state["workflow_phase"], "尚未开始")
            self.assertEqual(app.session_state["topic_input"], "")
            self.assertEqual(research.call_count, 0)
            self.assertEqual(strategy.call_count, 0)


if __name__ == "__main__":
    unittest.main()
