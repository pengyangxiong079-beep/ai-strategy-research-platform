import os
import json
import re
import shutil
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import main


RESEARCH = """# Research Brief

【事实】产品A已发布。[官方来源](https://example.com/a)

【事实】旧套餐曾经提供。[官方来源](https://example.com/b)

【推断】目标用户可能偏向企业。
"""

REVIEW = """# Review Notes

### R1

应明确旧套餐的停止服务时间，并避免把历史信息写成当前事实。

【新增事实】OpenAI已正式发布GPT-5.6。[发布说明](https://example.com/gpt-5-6)

【新增事实】OpenAI条款说明模型输出可能不准确。[服务条款](https://example.com/terms)
"""

FACT_CHECK = """# Fact Check

### F1
- 输入范围：RESEARCH
- 原始事实：产品A已发布。
- 核验结果：VERIFIED
- 来源：[官方来源](https://example.com/a)（一手官方）
- 修改建议：产品A已发布。
- source_grade：B
- as_of_date：2026-08-06
- geography：全球
- unit：N/A
- currency：N/A
- original_claim：产品A已发布。
- corrected_claim：产品A已发布。

### F2
- 输入范围：RESEARCH
- 原始事实：旧套餐曾经提供。
- 核验结果：OUTDATED
- 来源：[官方来源](https://example.com/b)（一手官方）
- 修改建议：仅作为带日期的历史背景提及，不得表述为当前事实。
- source_grade：B
- as_of_date：2026-08-06
- geography：全球
- unit：N/A
- currency：N/A
- original_claim：旧套餐曾经提供。
- corrected_claim：旧套餐仅可作为历史背景提及。

### F3
- 输入范围：REVIEW
- 原始事实：OpenAI已正式发布GPT-5.6。
- 核验结果：VERIFIED
- 来源：[发布说明](https://example.com/gpt-5-6)（一手官方）
- 修改建议：OpenAI已正式发布GPT-5.6。
- source_grade：B
- as_of_date：2026-08-06
- geography：全球
- unit：N/A
- currency：N/A
- original_claim：OpenAI已正式发布GPT-5.6。
- corrected_claim：OpenAI已正式发布GPT-5.6。

### F4
- 输入范围：REVIEW
- 原始事实：OpenAI条款说明模型输出可能不准确。
- 核验结果：VERIFIED
- 来源：[服务条款](https://example.com/terms)（一手官方）
- 修改建议：OpenAI条款说明模型输出可能不准确。
- source_grade：A
- as_of_date：2026-08-06
- geography：全球
- unit：N/A
- currency：N/A
- original_claim：OpenAI条款说明模型输出可能不准确。
- corrected_claim：OpenAI条款说明模型输出可能不准确。
"""

FINAL = """# 产品A公司战略分析报告

## 分析范围与口径
| 项目 | 内容 |
|---|---|
| 分析对象 | 产品A |
| 分析类型 | 公司分析 |
| 行业 | 自动判断为软件行业 |
| 地区 | 全球 |
| 基准日 | 2026-08-06 |
| 时间范围 | 未指定 |
| 采用模板 | general |
| 数据口径限制 | 市场规模暂无可靠统一口径，不虚构数值 |

选择商业模式和竞品矩阵，因为目标是判断产品定位；不机械套用其他框架。

## 行业/产品定位
【事实】产品A已发布（核验：F1）。[来源1](https://example.com/a)

【推断】目标用户可能偏向企业。[来源2](https://example.com/2)

## 市场规模与增长
【推断】市场规模和增长率暂无统一可靠数据，保持待验证。[来源3](https://example.com/3)

## 产业链与价值链
【推断】价值链仍需根据供应商和渠道资料补充。[来源4](https://example.com/4)

## 客户与需求
【推断】客户结构仍需通过用户研究验证。[来源5](https://example.com/5)

## 核心能力与壁垒
【事实】OpenAI已正式发布GPT-5.6（核验：F3）。[发布说明](https://example.com/gpt-5-6)

## 商业模式
【推断】商业模式与盈利模式仍需观察。[来源6](https://example.com/6)

## 竞争格局
【推断】竞争较为激烈。[来源7](https://example.com/7)

## 政策、技术及宏观趋势
【推断】政策和技术趋势仍需持续跟踪。

## 风险与机会
【事实】OpenAI条款说明模型输出可能不准确（核验：F4）。[服务条款](https://example.com/terms)

旧套餐信息已经过时（核验：F2），未作为当前事实使用。

## 战略建议
【建议】先验证企业需求。

## 尚待验证问题
需确认能力限制。

## Review问题处理情况
| 问题编号 | 处理方式 | 结果 |
|---|---|---|
| R1 | 将F2降级为历史背景 | 已处理 |

## Human Feedback处理情况
| 人工意见 | 处理方式 | 状态 |
|---|---|---|
| H1 | 已重点分析风险并采用可执行建议 | COMPLETED |
"""

REPORT_DATA = {
    "schema_version": "1.0",
    "scope": {
        "topic": "产品A",
        "analysis_type": "公司分析",
        "industry": "软件",
        "geography": "全球",
        "analysis_date": "2026-08-06",
        "selected_template": "general",
    },
    "executive_summary": "产品A测试摘要",
    "kpis": [],
    "time_series": [],
    "market_segments": [],
    "competitor_comparisons": [],
    "risks": [],
    "opportunities": [],
    "recommendations": [],
    "roadmap": [],
    "evidence_summary": {"verified": 3, "partial": 0, "unsupported": 0, "superseded": 1},
    "data_gaps": [],
}
STRATEGY_OUTPUT = (
    "<final_report>\n" + FINAL + "</final_report>\n"
    "<report_data_json>\n"
    + json.dumps(REPORT_DATA, ensure_ascii=False)
    + "\n</report_data_json>"
)


class FakeResult:
    def __init__(self, final_response):
        self.final_response = final_response


class FakeThread:
    def __init__(self, response, prompts):
        self.response = response
        self.prompts = prompts

    def run(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return FakeResult(self.response)


class FakeCodex:
    responses = [RESEARCH, REVIEW, FACT_CHECK, STRATEGY_OUTPUT]
    prompts = []
    thread_count = 0
    response_index = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def thread_start(self, **kwargs):
        del kwargs
        response = type(self).responses[type(self).response_index]
        type(self).response_index += 1
        type(self).thread_count += 1
        return FakeThread(response, type(self).prompts)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        FakeCodex.responses = [RESEARCH, REVIEW, FACT_CHECK, STRATEGY_OUTPUT]
        FakeCodex.prompts = []
        FakeCodex.thread_count = 0
        FakeCodex.response_index = 0

    def _create_portable_run(self, root, topic="Portable fixture"):
        original_cwd = Path.cwd()
        with patch.object(main, "Codex", FakeCodex):
            os.chdir(root)
            try:
                return main.run_workflow(topic)["output_folder"].resolve()
            finally:
                os.chdir(original_cwd)

    def test_credentials_are_redacted(self):
        sensitive = (
            "Authorization: Bearer " + "abcdefghijklmnop" + "\n"
            "Cookie: session=secret-cookie-value\n"
            "refresh_token=refresh-secret-value"
        )
        redacted = main.redact_sensitive_text(sensitive)
        self.assertNotIn("abcdefghijklmnop", redacted)
        self.assertNotIn("secret-cookie-value", redacted)
        self.assertNotIn("refresh-secret-value", redacted)

    def test_auto_approval_runs_four_threads_and_six_outputs(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                result = main.run_workflow("测试产品", human_feedback="重点分析风险")
            finally:
                os.chdir(original_cwd)

        self.assertEqual(FakeCodex.thread_count, 4)
        self.assertEqual(len(FakeCodex.prompts), 4)
        self.assertIn(RESEARCH, FakeCodex.prompts[1])
        self.assertIn(RESEARCH, FakeCodex.prompts[2])
        self.assertIn(REVIEW, FakeCodex.prompts[2])
        self.assertIn(RESEARCH, FakeCodex.prompts[3])
        self.assertIn(REVIEW, FakeCodex.prompts[3])
        self.assertIn(FACT_CHECK, FakeCodex.prompts[3])
        self.assertIn("<analysis_scope>", FakeCodex.prompts[0])
        self.assertIn("<industry_template>", FakeCodex.prompts[0])
        self.assertIn("source_grade", FakeCodex.prompts[2])
        self.assertEqual(result["files"]["scope"].name, "00_analysis_scope.json")
        self.assertEqual(result["files"]["research"].name, "01_research_brief.md")
        self.assertEqual(result["files"]["review"].name, "02_review_notes.md")
        self.assertEqual(result["files"]["fact"].name, "03_fact_check.md")
        self.assertEqual(result["files"]["feedback"].name, "03_human_feedback.md")
        self.assertEqual(result["files"]["final"].name, "04_final_report.md")
        self.assertEqual(result["files"]["quality"].name, "05_quality_check.md")
        self.assertEqual(result["quality_status"], "PASS")
        self.assertIn(
            "PASS仅代表本地结构与规则检查通过，不代表网页内容和事实真实性已经得到保证。",
            result["contents"]["quality"],
        )
        self.assertIn(
            "F编号结构及关键词对应检查通过；完整语义对应仍需人工复核。",
            result["contents"]["quality"],
        )

    def test_research_phase_stops_before_strategy(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                result = main.run_research_phase("测试产品")
                self.assertEqual(FakeCodex.thread_count, 3)
                self.assertEqual(result["workflow_stage"], "等待人工审核")
                self.assertIsNone(result["contents"]["final"])
                self.assertIsNone(result["contents"]["quality"])
                self.assertFalse(result["files"]["final"].exists())
                self.assertFalse(result["files"]["quality"].exists())
                self.assertTrue(result["files"]["feedback"].exists())
            finally:
                os.chdir(original_cwd)

    def test_approval_passes_feedback_to_strategy(self):
        original_cwd = Path.cwd()
        feedback = "删除未经支持的增长结论，并重点处理PARTIAL事实。"
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                research_result = main.run_research_phase("测试产品")
                result = main.run_strategy_phase(research_result, human_feedback=feedback)
                self.assertEqual(FakeCodex.thread_count, 4)
                self.assertIn(feedback, FakeCodex.prompts[3])
                self.assertIn(
                    feedback,
                    result["files"]["feedback"].read_text(encoding="utf-8"),
                )
                self.assertEqual(result["workflow_stage"], "已完成")
            finally:
                os.chdir(original_cwd)

    def test_reresearch_passes_feedback_to_research_without_strategy(self):
        revised_research = RESEARCH.replace("产品A已发布", "产品A已正式发布")
        FakeCodex.responses = [
            RESEARCH,
            REVIEW,
            FACT_CHECK,
            revised_research,
            REVIEW,
            FACT_CHECK.replace("产品A已发布", "产品A已正式发布"),
        ]
        feedback = "补充监管机构来源，并删除旧套餐结论。"
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                first = main.run_research_phase("测试产品")
                second = main.run_research_phase(
                    "测试产品",
                    human_feedback=feedback,
                    output_folder=first["output_folder"],
                )
                self.assertEqual(FakeCodex.thread_count, 6)
                self.assertIn(feedback, FakeCodex.prompts[3])
                self.assertEqual(second["workflow_stage"], "等待人工审核")
                self.assertIsNone(second["contents"]["final"])
                self.assertIn(feedback, second["contents"]["feedback"])
            finally:
                os.chdir(original_cwd)

    def test_cli_require_approval_can_stop_after_research(self):
        original_cwd = Path.cwd()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(main, "Codex", FakeCodex),
            patch("builtins.input", side_effect=["请补充官方来源", "n"]),
        ):
            os.chdir(temp_dir)
            try:
                exit_code = main.main(["测试产品", "--require-approval"])
                self.assertEqual(exit_code, 0)
                self.assertEqual(FakeCodex.thread_count, 3)
            finally:
                os.chdir(original_cwd)

    def test_manifest_history_and_zip_are_reproducible(self):
        required_fields = {
            "schema_version",
            "run_id",
            "topic",
            "analysis_type",
            "industry",
            "geography",
            "analysis_date",
            "selected_template",
            "created_at",
            "updated_at",
            "current_stage",
            "final_status",
            "research_status",
            "review_status",
            "fact_check_status",
            "approval_status",
            "strategy_status",
            "quality_check_status",
            "human_feedback",
            "stage_durations_seconds",
            "output_files",
            "error_message",
            "quality_issues",
        }
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                result = main.run_workflow("OpenAI GPT-5.6", human_feedback="重点分析风险")
                manifest = json.loads(
                    (result["output_folder"] / "run_manifest.json").read_text(encoding="utf-8")
                )
                self.assertTrue(required_fields <= set(manifest))
                self.assertRegex(
                    manifest["run_id"],
                    r"^\d{8}_\d{6}_openai-gpt-5-6$",
                )
                self.assertEqual(result["output_folder"].name, manifest["run_id"])
                self.assertEqual(manifest["final_status"], "COMPLETED")
                self.assertEqual(manifest["research_status"], "COMPLETED")
                self.assertEqual(manifest["review_status"], "COMPLETED")
                self.assertEqual(manifest["fact_check_status"], "COMPLETED")
                self.assertEqual(manifest["approval_status"], "APPROVED")
                self.assertEqual(manifest["strategy_status"], "COMPLETED")
                self.assertEqual(manifest["quality_check_status"], "PASS")
                self.assertEqual(manifest["schema_version"], "2.2")
                self.assertEqual(manifest["human_feedback"], "重点分析风险")
                self.assertTrue(
                    all(
                        isinstance(value, (int, float)) and value >= 0
                        for value in manifest["stage_durations_seconds"].values()
                    )
                )
                self.assertFalse(list(result["output_folder"].glob(".run_manifest_*.tmp")))

                history = main.list_run_manifests(Path(temp_dir) / "outputs")
                self.assertEqual(len(history), 1)
                loaded = main.load_run_history(
                    manifest["run_id"], Path(temp_dir) / "outputs"
                )
                self.assertEqual(loaded["contents"]["final"], FINAL.strip())

                with zipfile.ZipFile(BytesIO(main.build_run_zip(result["output_folder"]))) as archive:
                    names = set(archive.namelist())
                self.assertIn("run_manifest.json", names)
                self.assertIn("00_analysis_scope.json", names)
                self.assertIn("01_research_brief.md", names)
                self.assertIn("03_human_feedback.md", names)
                self.assertIn("05_quality_check.md", names)
            finally:
                os.chdir(original_cwd)

    def test_failure_manifest_is_sanitized_and_keeps_completed_files(self):
        FakeCodex.responses = [
            RESEARCH,
            RuntimeError("Authorization: Bearer " + "abcdefghijklmnop"),
        ]
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                with self.assertRaises(main.WorkflowError):
                    main.run_research_phase("失败测试")
                run_folders = list((Path(temp_dir) / "outputs").iterdir())
                self.assertEqual(len(run_folders), 1)
                output_folder = run_folders[0]
                manifest = json.loads(
                    (output_folder / "run_manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["final_status"], "ERROR")
                self.assertEqual(manifest["research_status"], "COMPLETED")
                self.assertEqual(manifest["review_status"], "FAILED")
                self.assertEqual(manifest["current_stage"], "Review Agent")
                self.assertNotIn("abcdefghijklmnop", manifest["error_message"])
                self.assertTrue((output_folder / "01_research_brief.md").is_file())
                self.assertFalse((output_folder / "02_review_notes.md").exists())
            finally:
                os.chdir(original_cwd)

    def test_outdated_fact_cannot_remain_labeled_as_fact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            research_file = output_dir / "01_research_brief.md"
            review_file = output_dir / "02_review_notes.md"
            fact_file = output_dir / "03_fact_check.md"
            report_file = output_dir / "04_final_report.md"
            research_file.write_text(RESEARCH, encoding="utf-8")
            review_file.write_text(REVIEW, encoding="utf-8")
            fact_file.write_text(FACT_CHECK, encoding="utf-8")
            report_file.write_text(
                FINAL.replace(
                    "旧套餐信息已经过时（核验：F2），未作为当前事实使用。",
                    "【事实】旧套餐当前仍提供（核验：F2）。[来源](https://example.com/b)",
                ),
                encoding="utf-8",
            )

            status, quality_file = main.validate_outputs(
                research_file,
                review_file,
                fact_file,
                report_file,
            )

            self.assertEqual(status, "FAIL")
            self.assertIn(
                "UNSUPPORTED/OUTDATED/SUPERSEDED仍标为事实：F2",
                quality_file.read_text(encoding="utf-8"),
            )

    def test_semantically_unrelated_f_id_is_warn_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            files = {
                "research": output_dir / "01_research_brief.md",
                "review": output_dir / "02_review_notes.md",
                "fact": output_dir / "03_fact_check.md",
                "feedback": output_dir / "03_human_feedback.md",
                "final": output_dir / "04_final_report.md",
            }
            files["research"].write_text(RESEARCH, encoding="utf-8")
            files["review"].write_text(REVIEW, encoding="utf-8")
            files["fact"].write_text(FACT_CHECK, encoding="utf-8")
            files["feedback"].write_text(
                "# 人工补充意见\n\n### H1\n\n- 人工意见：重点分析风险。\n",
                encoding="utf-8",
            )
            files["final"].write_text(
                FINAL.replace("模型输出可能不准确（核验：F4）", "模型输出可能不准确（核验：F3）"),
                encoding="utf-8",
            )

            status, quality_file = main.validate_outputs(
                files["research"], files["review"], files["fact"], files["final"], files["feedback"]
            )

            self.assertEqual(status, "WARN")
            self.assertIn(
                "F编号与事实陈述可能语义不匹配：F3",
                quality_file.read_text(encoding="utf-8"),
            )

    def test_review_added_fact_requires_its_own_f_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            research_file = output_dir / "01_research_brief.md"
            review_file = output_dir / "02_review_notes.md"
            fact_file = output_dir / "03_fact_check.md"
            report_file = output_dir / "04_final_report.md"
            research_file.write_text(RESEARCH, encoding="utf-8")
            review_file.write_text(REVIEW, encoding="utf-8")
            fact_file.write_text(FACT_CHECK.split("\n### F4", 1)[0], encoding="utf-8")
            report_file.write_text(FINAL, encoding="utf-8")

            status, quality_file = main.validate_outputs(
                research_file, review_file, fact_file, report_file
            )

            self.assertEqual(status, "FAIL")
            self.assertIn(
                "Review有1条新增事实未找到语义对应的F记录",
                quality_file.read_text(encoding="utf-8"),
            )

    def test_verified_release_cannot_be_pending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            research_file = output_dir / "01_research_brief.md"
            review_file = output_dir / "02_review_notes.md"
            fact_file = output_dir / "03_fact_check.md"
            report_file = output_dir / "04_final_report.md"
            research_file.write_text(RESEARCH, encoding="utf-8")
            review_file.write_text(REVIEW, encoding="utf-8")
            fact_file.write_text(FACT_CHECK, encoding="utf-8")
            report_file.write_text(
                FINAL.replace(
                    "【事实】OpenAI已正式发布GPT-5.6（核验：F3）",
                    "【待验证】OpenAI是否已正式发布GPT-5.6（核验：F3）",
                ),
                encoding="utf-8",
            )

            status, quality_file = main.validate_outputs(
                research_file, review_file, fact_file, report_file
            )

            self.assertEqual(status, "FAIL")
            self.assertIn(
                "以下VERIFIED事实不得写为【待验证】：F3",
                quality_file.read_text(encoding="utf-8"),
            )

    def test_non_atomic_fact_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            research_file = output_dir / "01_research_brief.md"
            review_file = output_dir / "02_review_notes.md"
            fact_file = output_dir / "03_fact_check.md"
            feedback_file = output_dir / "03_human_feedback.md"
            report_file = output_dir / "04_final_report.md"
            research_file.write_text(RESEARCH, encoding="utf-8")
            review_file.write_text(REVIEW, encoding="utf-8")
            fact_file.write_text(
                FACT_CHECK.replace(
                    "产品A已发布。",
                    "产品A价格为10美元；费用从预充值余额扣除，且官方计划涨价。",
                    1,
                ),
                encoding="utf-8",
            )
            feedback_file.write_text("# 人工补充意见\n\n", encoding="utf-8")
            report_file.write_text(FINAL, encoding="utf-8")

            status, quality_file = main.validate_outputs(
                research_file,
                review_file,
                fact_file,
                report_file,
                feedback_file,
            )

            quality = quality_file.read_text(encoding="utf-8")
            self.assertEqual(status, "FAIL")
            self.assertIn("Fact Check原子事实", quality)
            self.assertIn("F1", quality)
            self.assertIn("价格、支付机制、价格变更计划", quality)

    def test_human_feedback_status_controls_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            files = {
                "research": output_dir / "01_research_brief.md",
                "review": output_dir / "02_review_notes.md",
                "fact": output_dir / "03_fact_check.md",
                "feedback": output_dir / "03_human_feedback.md",
                "final": output_dir / "04_final_report.md",
            }
            files["research"].write_text(RESEARCH, encoding="utf-8")
            files["review"].write_text(REVIEW, encoding="utf-8")
            files["fact"].write_text(FACT_CHECK, encoding="utf-8")
            files["feedback"].write_text(
                "# 人工补充意见\n\n### H1\n\n- 人工意见：加入具体竞品对比\n",
                encoding="utf-8",
            )
            partial_final = FINAL.replace(
                "已重点分析风险并采用可执行建议 | COMPLETED",
                "仅提供待评测维度和评测框架 | COMPLETED",
            ).replace(
                "【推断】竞争较为激烈。[来源7](https://example.com/7)",
                "【推断】竞争较为激烈；应进行的具体对比需使用真实任务评测框架。"
                "[来源7](https://example.com/7)",
            )
            files["final"].write_text(partial_final, encoding="utf-8")

            status, quality_file = main.validate_outputs(
                files["research"],
                files["review"],
                files["fact"],
                files["final"],
                files["feedback"],
            )

            quality = quality_file.read_text(encoding="utf-8")
            self.assertEqual(status, "WARN")
            self.assertIn("H1=PARTIAL", quality)
            self.assertIn("没有实际竞品对比数据", quality)

            files["final"].write_text(
                partial_final.replace("PARTIAL", "NOT_COMPLETED"),
                encoding="utf-8",
            )
            # Framework-only detection remains PARTIAL even if the model over/understates it.
            status, _ = main.validate_outputs(
                files["research"],
                files["review"],
                files["fact"],
                files["final"],
                files["feedback"],
            )
            self.assertEqual(status, "WARN")

    def test_legacy_manifest_gets_safe_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy",
                        "topic": "旧AI分析",
                        "created_at": "2025-01-01T00:00:00+00:00",
                        "updated_at": "2025-01-01T00:00:00+00:00",
                        "final_status": "COMPLETED",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = main.load_manifest(output_dir)
            self.assertEqual(manifest["analysis_type"], "公司分析")
            self.assertEqual(manifest["geography"], "全球")
            self.assertEqual(manifest["selected_template"], "general")
            self.assertEqual(manifest["quality_issues"], [])

    def test_not_completed_human_feedback_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            research_file = output_dir / "01_research_brief.md"
            review_file = output_dir / "02_review_notes.md"
            fact_file = output_dir / "03_fact_check.md"
            feedback_file = output_dir / "03_human_feedback.md"
            report_file = output_dir / "04_final_report.md"
            research_file.write_text(RESEARCH, encoding="utf-8")
            review_file.write_text(REVIEW, encoding="utf-8")
            fact_file.write_text(FACT_CHECK, encoding="utf-8")
            feedback_file.write_text(
                "# 人工补充意见\n\n### H1\n\n- 人工意见：删除不可靠结论\n",
                encoding="utf-8",
            )
            report_file.write_text(
                FINAL.replace("COMPLETED", "NOT_COMPLETED"),
                encoding="utf-8",
            )
            status, quality_file = main.validate_outputs(
                research_file,
                review_file,
                fact_file,
                report_file,
                feedback_file,
            )
            self.assertEqual(status, "FAIL")
            self.assertIn("H1=NOT_COMPLETED", quality_file.read_text(encoding="utf-8"))

    def test_deepseek_regression_validate_run_never_calls_agent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_run = self._create_portable_run(temp_dir)
            with patch.object(
                main,
                "Codex",
                side_effect=AssertionError("validate_run不得调用Agent"),
            ) as codex:
                manifest = main.validate_run(copied_run)

            self.assertEqual(codex.call_count, 0)
            self.assertIn(manifest["quality_check_status"], {"PASS", "WARN", "FAIL"})
            self.assertIn(manifest["final_status"], {"COMPLETED", "COMPLETED_WITH_WARNINGS", "NEEDS_REVISION"})
            self.assertEqual(manifest["error_message"], "")
            self.assertIsInstance(manifest["quality_issues"], list)
            self.assertTrue((copied_run / "05_quality_check.md").is_file())

    def test_local_revision_uses_no_agent_and_versions_portable_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_run = self._create_portable_run(temp_dir)
            with patch.object(
                main,
                "Codex",
                side_effect=AssertionError("本地复检不得调用Agent"),
            ) as codex:
                result = main.rerun_local_revision(copied_run, "仅重新验收人工修改")

            self.assertEqual(codex.call_count, 0)
            versions = main.list_revision_versions(copied_run)
            self.assertGreaterEqual(len(versions), 2)
            self.assertEqual(versions[0]["revision_id"], "rev_000")
            self.assertEqual(result["revision"]["revision_type"], "LOCAL_RECHECK")
            self.assertEqual(result["manifest"]["latest_revision"], versions[-1]["revision_id"])
            self.assertEqual(result["quality_status"], result["manifest"]["quality_check_status"])
            self.assertIn(result["manifest"]["final_status"], {"COMPLETED", "COMPLETED_WITH_WARNINGS", "NEEDS_REVISION"})
            for filename in (
                "revision_request.md",
                "04_final_report.md",
                "05_quality_check.md",
                "05_quality_check.json",
                "revision_manifest.json",
            ):
                self.assertTrue((Path(versions[-1]["revision_folder"]) / filename).is_file())
            quality_text = (copied_run / "05_quality_check.md").read_text(encoding="utf-8")
            self.assertIn("结构化市场指标 | DETERMINISTIC | PASS", quality_text)
            self.assertIn("结构化竞品比较 | DETERMINISTIC | PASS", quality_text)
            self.assertIn("竞品比较口径 | HEURISTIC | PASS", quality_text)
            self.assertNotIn("处市场规模类数字缺少年份或地区", quality_text)
            self.assertNotIn("处竞品排名未声明统一或可比口径", quality_text)
            for issue in versions[-1]["quality_issues"]:
                self.assertTrue(
                    {"severity", "rule_id", "file", "line", "original", "suggestion"}
                    <= set(issue)
                )

    def test_strategy_revision_starts_exactly_one_strategy_thread(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                initial = main.run_workflow("测试产品")
                FakeCodex.responses = [STRATEGY_OUTPUT]
                FakeCodex.prompts = []
                FakeCodex.thread_count = 0
                FakeCodex.response_index = 0
                result = main.revise_strategy_report(
                    initial["output_folder"],
                    "修复当前质量问题",
                )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(FakeCodex.thread_count, 1)
        self.assertEqual(len(FakeCodex.prompts), 1)
        self.assertIn("当前任务仅修订已经生成的最终报告", FakeCodex.prompts[0])
        self.assertEqual(result["revision"]["revision_type"], "STRATEGY_REVISION")
        self.assertEqual(result["revision"]["revision_id"], "rev_001")

    def test_transactional_revision_does_not_replace_final_without_report_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            files = {
                "final": folder / "04_final_report.md",
                "report_data": folder / "04_report_data.json",
            }
            files["final"].write_text(FINAL, encoding="utf-8")
            files["report_data"].write_text(
                json.dumps(REPORT_DATA, ensure_ascii=False), encoding="utf-8"
            )
            original_final = files["final"].read_bytes()
            original_data = files["report_data"].read_bytes()

            with self.assertRaisesRegex(ValueError, "输出不完整"):
                main.save_strategy_outputs(
                    "<final_report>不完整修订</final_report>",
                    files,
                    transactional=True,
                )

            self.assertEqual(files["final"].read_bytes(), original_final)
            self.assertEqual(files["report_data"].read_bytes(), original_data)

    def test_completion_revision_restores_dashboard_with_one_strategy_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_run = self._create_portable_run(temp_dir)
            current_final = (copied_run / "04_final_report.md").read_text(encoding="utf-8")
            prior_data = json.loads(
                (copied_run / "04_report_data.json").read_text(
                    encoding="utf-8"
                )
            )
            FakeCodex.responses = [
                "<report_data_json>"
                + json.dumps(prior_data, ensure_ascii=False)
                + "</report_data_json>"
            ]
            FakeCodex.prompts = []
            FakeCodex.thread_count = 0
            FakeCodex.response_index = 0

            with patch.object(main, "Codex", FakeCodex):
                result = main.revise_strategy_report(copied_run, "完成")

            self.assertEqual(FakeCodex.thread_count, 1)
            self.assertIn("只补齐或重建", FakeCodex.prompts[0])
            self.assertEqual(
                (copied_run / "04_final_report.md").read_text(encoding="utf-8"),
                current_final,
            )
            self.assertEqual(result["quality_status"], result["manifest"]["quality_check_status"])
            self.assertIn(result["manifest"]["final_status"], {"COMPLETED", "COMPLETED_WITH_WARNINGS", "NEEDS_REVISION"})
            self.assertIn(result["manifest"]["dashboard_status"], {"READY", "READY_WITH_GAPS", "BLOCKED_BY_QUALITY"})
            self.assertTrue((copied_run / "04_report_data.json").is_file())

    def test_first_quarter_is_not_a_promotional_first_claim(self):
        self.assertFalse(main.contains_promotional_superlative("2026年第一季度集团收入增长"))
        self.assertTrue(main.contains_promotional_superlative("公司是行业第一"))

    def test_revision_research_runs_three_threads_then_waits_for_approval(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(main, "Codex", FakeCodex):
            os.chdir(temp_dir)
            try:
                initial = main.run_workflow("测试产品")
                FakeCodex.responses = [RESEARCH, REVIEW, FACT_CHECK]
                FakeCodex.prompts = []
                FakeCodex.thread_count = 0
                FakeCodex.response_index = 0
                result = main.run_revision_research_phase(
                    initial["output_folder"],
                    "补充最新价格、竞品数据和行业指标",
                )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(FakeCodex.thread_count, 3)
        self.assertEqual(len(FakeCodex.prompts), 3)
        self.assertIn("补充最新价格、竞品数据和行业指标", FakeCodex.prompts[0])
        self.assertEqual(result["workflow_stage"], "等待人工审核")
        self.assertEqual(result["manifest"]["final_status"], "AWAITING_APPROVAL")
        self.assertEqual(result["manifest"]["revision_status"], "AWAITING_APPROVAL")


if __name__ == "__main__":
    unittest.main()
