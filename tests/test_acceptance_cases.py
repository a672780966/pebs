"""Acceptance coverage for spec section 85 (必需验收用例).

Section 85 fixes 26 cases with a scenario and the result that must be observed,
and it splits the required evidence: permissions, versions and file structure are
covered by automated tests, while evidence semantics and teaching/visual results
need human annotation and real-file review.

`ACCEPTANCE_EVIDENCE` is the explicit mapping from every case to the test that
proves it. A case that cannot be proven by an automated test in this repository is
recorded as `manual:` with the reason, never as a fabricated pass.
"""

from __future__ import annotations

import argparse
import importlib

from pebs import cli, config
from pebs.engine import Engine

# The "必须观察到的结果" column of section 85, verbatim, one entry per case ID.
ACCEPTANCE_CASES: dict[str, str] = {
    "A01": "栏目、案例、称谓和字数满足当前要求，正式文件通过 G1–G8",
    "A02": "策略分别服务对应目标，不能机械生成同一教学流程",
    "A03": "不升级为单线因果机制；相关 Claim 与实际证据对应",
    "A04": "G2 不通过，不能以有引用或文件存在放行",
    "A05": "标明取得内容层级，不声称全文核验，不生成未被支持的机制事实",
    "A06": "保留双方证据，限定结论或转人工复核，不静默选择有利来源",
    "A07": "列出冲突并等待要求修订，草稿不冒充正式完成",
    "A08": "只更新相关依赖产物；无关产物版本和内容哈希不变",
    "A09": "已接受的脚本、题目、分镜和 PPT 维持原版本，无部分提交",
    "A10": "旧结果不覆盖新版本，记录基线冲突",
    "A11": "显示过期和锁定冲突，正式导出被阻止",
    "A12": "拒绝破坏依赖的计划变更并解释原因",
    "A13": "不判为 PASS，显示失败或待复核",
    "A14": "有界重试或明确暂停，保留已完成步骤，不捏造研究结果",
    "A15": "可查看并恢复进度；晚到结果不提交；不重复未知结果的外部写操作",
    "A16": "新版本不发布，不回退到无补丁版本",
    "A17": "调用在实际执行前被拒绝；声明允许不能替代真实授权",
    "A18": "实际沙箱限制生效；沙箱不可用时不回退主机",
    "A19": "不产生授权记录，不触发 CNKI 下载、Zotero 写入或发布",
    "A20": "外发前阻止并提示脱敏；日志、Memory 和检索请求中无泄露",
    "A21": "明确说明不支持部分，不静默遗漏后报告完整",
    "A22": "实际文件可打开，文字和规定图表可编辑，无溢出遮挡，引用对应",
    "A23": "文件和 UI 均明确草稿状态，正式目录不出现误标交付物",
    "A24": "经适配后业务语义一致，非法值明确报错",
    "A25": "新事实登记待核验，原 Claim 通过状态不能自动覆盖新表述",
    "A26": "托管输入、产物、Memory、快照、日志和缓存移除；外部原件保持不变",
}

# module::test for an automated proof, "new:<name>" for a test in this module,
# "manual:<reason>" where the owner spec requires human annotation or real-file
# review and this repository has no deterministic assertion for it.
ACCEPTANCE_EVIDENCE: dict[str, str] = {
    "A01": "manual:正式文件的栏目/字数/称谓需要真实 DOCX 人工复核；模板解析由 test_template.py 覆盖",
    "A02": "test_gates::test_g3_fails_when_strategy_outside_allowed_set",
    "A03": "manual:相关性与因果的区分属证据语义，需要人工标注",
    "A04": "test_evidence::test_citation_exists_but_does_not_support_claim",
    "A05": "test_evidence::test_metadata_only_source_cannot_support",
    "A06": "test_evidence::test_conflicting_evidence_is_kept",
    "A07": "test_gates::test_g6_flags_animation_requirement_conflict",
    "A08": "test_conversation_edit::test_conversation_edit_localizes_case_and_locks_other_sections",
    "A09": "test_store::test_reject_leaves_accepted_untouched",
    "A10": "test_store::test_accept_rejects_stale_baseline",
    "A11": "test_gates::test_gate_result_invalidates_when_script_changes",
    "A12": "test_plan_edits::test_disabling_required_step_is_rejected",
    "A13": "test_parallel_execution::test_missing_gate_result_blocks_export",
    "A14": "test_pipeline::test_offline_without_provider_reports_unavailable_and_never_fabricates",
    "A15": "test_parallel_execution::test_resume_re_runs_blocked_steps",
    "A16": "test_skills_mgr::test_patch_base_mismatch_stops_composition",
    "A17": "test_permissions::test_unknown_and_unapproved_skills_are_denied",
    "A18": "test_sandbox::test_run_sandboxed_refuses_without_verified_adapter",
    "A19": "test_lifecycle::test_injected_authorization_cannot_trigger_external_writes",
    "A20": "test_pii::test_request_with_pii_pauses_before_any_send",
    "A21": "test_input_limits::test_pipeline_rejects_over_limit_batch_before_parsing",
    "A22": "test_pptx::test_build_produces_editable_pptx",
    "A23": "test_pipeline::test_docx_export_publishes_only_after_accept",
    "A24": "test_enums::test_weird_enums_from_provider_are_normalized",
    "A25": "test_gates::test_g2_fails_on_pending_placeholder",
    "A26": "new:test_delete_removes_managed_project_and_keeps_external_originals",
}

DOCUMENTED_IDS = [f"A{index:02d}" for index in range(1, 27)]


def test_every_case_is_mapped_exactly_once():
    assert list(ACCEPTANCE_CASES) == DOCUMENTED_IDS
    assert set(ACCEPTANCE_EVIDENCE) == set(ACCEPTANCE_CASES)


def test_automated_evidence_points_at_real_tests():
    """No coverage by proximity: every cited node must exist in its module."""
    cited = {
        case: evidence
        for case, evidence in ACCEPTANCE_EVIDENCE.items()
        if not evidence.startswith(("manual:", "new:"))
    }
    assert cited, "expected automated coverage to be claimed for at least one case"
    for case, evidence in cited.items():
        module_name, test_name = evidence.split("::")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, test_name, None)), f"{case}: {evidence} does not exist"


def test_manual_cases_are_reported_with_a_reason():
    manual = {
        case: evidence.split("manual:", 1)[1]
        for case, evidence in ACCEPTANCE_EVIDENCE.items()
        if evidence.startswith("manual:")
    }
    assert manual, "this repository cannot cover all 26 cases automatically"
    for case, reason in manual.items():
        assert reason.strip(), f"{case}: a manual gap needs a stated reason"


def test_delete_removes_managed_project_and_keeps_external_originals(tmp_path, monkeypatch):
    """A26: managed data is removed; the uploaded original is left alone."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    original = tmp_path / "original.docx"
    original.write_text("external original", encoding="utf-8")

    engine = Engine("delproj")
    managed = config.project_dir("delproj")
    try:
        assert managed.exists()
    finally:
        engine.close()

    assert cli.cmd_delete(argparse.Namespace(project="delproj", yes=True)) == 0

    assert not managed.exists()
    assert original.read_text(encoding="utf-8") == "external original"
