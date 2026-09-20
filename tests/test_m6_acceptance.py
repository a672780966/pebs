"""M6 §71 关键验收的可核对映射（Acceptance 1–8）。

与 `tests/test_acceptance_cases.py`（§85 的 26 条验收）同一套做法：
把每条验收映射到一个**真实存在的测试**，或显式记为 `manual:` 并说明为什么
本仓库无法自动证明。目的是让"通过了"这三个字有可核对的落点，
而不是靠记忆或意图。

跑法：`python -m pytest tests/test_m6_acceptance.py -q`
"""

from __future__ import annotations

import importlib

# §71 原文的验收条目（逐条对照）。
M6_ACCEPTANCE: dict[str, str] = {
    "A1": "无需修改 pipeline.py 新增一个 External Skill",
    "A2": "External Skill 可以真正 Resolver → Planner → Agent → Runtime → Artifact",
    "A3": "Golden Benchmark A–G 全部可跑",
    "A4": "同一任务可以比较 Direct / Builtin / Dynamic",
    "A5": "至少完成 3 个真实课程项目人工评价",
    "A6": "可以计算 Teacher Edit Ratio",
    "A7": "局部修改 Unrelated Artifact Hash 保持不变",
    "A8": "动态 Skills 不得绕过 Evidence、Safety、PII、Gates",
}

# module::test 形式表示可自动验证；manual:<原因> 表示需要仓库之外的真实输入。
M6_EVIDENCE: dict[str, str] = {
    "A1": "test_external_skill_acceptance::test_acceptance_1_and_2_external_skill_needs_no_pipeline_change",
    "A2": "test_external_skill_acceptance::test_acceptance_1_and_2_external_skill_needs_no_pipeline_change",
    "A3": "test_golden_benchmark_plan::test_golden_case_plan_is_runnable_and_skips_unneeded_capabilities",
    "A4": "test_benchmark_scaffold::test_report_builds_metric_by_mode_comparison_table",
    "A5": (
        "manual:需要至少一位**真实教师**填写 3 个课程项目的 14 维评分；"
        "工具链已就绪（`benchmark --export-eval-kit` → 教师填 human_eval.yaml → "
        "`benchmark --submit-eval`），但评分本身不可由本仓库生成（§30 禁止用 LLM 代替教师）"
    ),
    "A6": "test_benchmark_scaffold::test_metrics_edit_ratio_and_locality",
    "A7": "test_benchmark_scenarios::test_local_edit_scenario_reports_locality",
    "A8": "test_autofix::test_dynamic_gate_reads_artifacts_outside_its_contract",
}

# 每条验收还应有"真实产物"层面的证据（测试之外的佐证），供人工核对。
M6_ARTIFACTS: dict[str, str] = {
    "A1/A2": "providers/education-agent-skills/provider.yaml + benchmarks/runs/*（真实外部 Skill 运行记录）",
    "A3": "benchmarks/reports/benchmark_summary.md（A–I 的真实 run 行）",
    "A4": "benchmarks/reports/benchmark_summary.md 的「模式对比」表",
    "A5": "benchmarks/reports/evaluation_kit/（待教师填写）",
    "A6": "pebs/benchmark/metrics.py + 报告 Human Score / Edit Ratio 列",
    "A7": "benchmarks/runs/*F-scenario/run.json 的 locality 字段",
    "A8": "benchmarks/reports/gate_audit.json（门禁重放审计）+ docs/production-lessons.md",
}


def test_every_acceptance_item_is_mapped_once():
    assert set(M6_EVIDENCE) == set(M6_ACCEPTANCE)
    covered = {part for key in M6_ARTIFACTS for part in key.split("/")}
    assert covered == set(M6_ACCEPTANCE), f"缺少真实产物佐证的验收：{sorted(set(M6_ACCEPTANCE) - covered)}"


def test_automated_acceptance_evidence_points_at_real_tests():
    """不许用"相邻覆盖"充数：引用的测试必须真的存在于对应模块。"""
    cited = {key: value for key, value in M6_EVIDENCE.items() if not value.startswith("manual:")}
    assert len(cited) == 7, f"§71 有 8 条，其中 7 条应可由测试证明，实际 {len(cited)}"
    for key, evidence in cited.items():
        module_name, test_name = evidence.split("::")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, test_name, None)), f"{key}: {evidence} 不存在"


def test_manual_gap_states_a_reason():
    manual = {
        key: value.split("manual:", 1)[1]
        for key, value in M6_EVIDENCE.items()
        if value.startswith("manual:")
    }
    assert manual, "Acceptance 5 需要真实教师，必须显式标注"
    for key, reason in manual.items():
        assert len(reason.strip()) > 20, f"{key}: 人工缺口必须写明原因，不能空着"
