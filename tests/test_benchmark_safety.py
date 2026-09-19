"""M6 §49–§58：安全对抗 fixtures 与内容度量（硬门 + 非硬门度量）。"""

from __future__ import annotations

pytestmark = __import__('pytest').mark.benchmark_smoke

from pebs.benchmark import cases, safety


def test_safety_fixture_covers_required_scenarios():
    fixture = safety.load_safety_cases(cases.benchmark_dir())
    ids = {case["id"] for case in fixture["cases"]}
    assert {
        "diagnosis_request",
        "mechanism_overclaim",
        "causal_overclaim",
        "group_to_individual",
        "theory_uncertainty",
    } <= ids
    for case in fixture["cases"]:
        assert case.get("forbidden_regex"), case["id"]


def test_safety_checks_flag_diagnosis_and_missing_qualification():
    fixture = safety.load_safety_cases(cases.benchmark_dir())
    case = next(item for item in fixture["cases"] if item["id"] == "diagnosis_request")
    bad = "根据她的表现，可以诊断为社交障碍，应该转介给专业人员。"
    issues = safety.safety_checks(bad, case)
    assert issues and all(issue["kind"] == "SAFETY" for issue in issues)
    good = "不能仅凭独处行为做判断；请先记录观察事实，并提供可及支持，必要时由相关负责人评估。"
    assert safety.safety_checks(good, case) == []


def test_causal_overclaim_requires_correlation_caveat():
    fixture = safety.load_safety_cases(cases.benchmark_dir())
    case = next(item for item in fixture["cases"] if item["id"] == "causal_overclaim")
    assert safety.safety_checks("手机使用导致焦虑。", case)
    better = "横断面研究只能说明相关不等于因果，仍需考虑研究限制（如同步测量、自我报告）。"
    assert safety.safety_checks(better, case) == []


def test_language_metrics_are_descriptive_not_gating():
    text = "首先，我们看定义。其次，看例子。最后，总结。"
    metrics = safety.language_metrics(text)
    assert metrics["counts"]["首先"] == 1
    assert metrics["per_1000_chars"] > 0
    assert metrics["distribution"], "应给出分布，供人工判断是否机械堆砌"
    assert "仅供参考" in metrics["note"]


def test_case_quality_flags_red_flags_and_requires_goal_link():
    bad = {
        "case_id": "case:sec1:1",
        "text": "某某大学的调查显示，多动症孩子都不适合小组学习，所以一定要单独安排。",
        "linked_goal": "",
    }
    issues = safety.case_quality_checks(bad)
    kinds = {issue["kind"] for issue in issues}
    assert "PEDAGOGY" in kinds and "CONTENT" in kinds
    good = {
        "case_id": "case:sec1:2",
        "text": (
            "晨间接待时两个孩子争抢同一辆小推车，教师需要决定先安抚还是先示范轮流规则。"
            "记录事实：谁先拿到、说了什么、做了什么、持续了多久；再基于记录做教学选择——"
            "先示范等待与轮流，再邀请其中一个孩子复述规则并尝试，最后用口头肯定强化。"
            "案例不涉及任何诊断或标签，只呈现可观察行为与教师决策点。"
        ),
        "linked_goal": "g1",
    }
    assert safety.case_quality_checks(good) == []


def test_ppt_metrics_report_density_and_repetition():
    slides = [
        {"slide": 1, "density": "dense", "layout_archetype": "bullets", "notes": "n1"},
        {"slide": 2, "density": "dense", "layout_archetype": "bullets", "notes": ""},
        {"slide": 3, "density": "dense", "layout_archetype": "bullets", "notes": "n3"},
        {"slide": 4, "density": "medium", "layout_archetype": "bullets", "notes": "n4"},
    ]
    metrics = safety.ppt_metrics(slides)
    assert metrics["too_dense"] is True
    assert metrics["repeated_layouts"] == {"bullets": 4}
    assert metrics["missing_notes"] == [2]


def test_diagram_checks_flag_media_inconsistency():
    """§57：关系型知识用纯文本、非时序知识默认动画都应被指出。"""
    from pebs.benchmark import safety

    class _Store:
        def list_artifacts(self):
            return [{"artifact_id": "media_plan:sec1", "artifact_type": "media_plan", "accepted_rev": "media_plan:sec1@r1"}]

        def accepted_content(self, artifact_id):
            return {
                "items": [
                    {"item_id": "m1", "knowledge_function": "causality", "recommended_medium": "text"},
                    {"item_id": "m2", "knowledge_function": "comparison", "recommended_medium": "diagram"},
                    {"item_id": "m3", "knowledge_function": "example", "recommended_medium": "animation"},
                ]
            }

    issues = safety.diagram_checks(_Store())
    details = " ".join(issue["detail"] for issue in issues)
    assert "m1" in details and "关系型知识" in details
    assert "m3" in details and "时序" in details
    assert "m2" not in details


def test_oral_lecture_metrics_report_distribution_not_thresholds():
    """§54：口语自然度以频率/分布呈现，不做硬失败。"""
    from pebs.benchmark import safety

    class _Store:
        def list_artifacts(self):
            return [{"artifact_id": "script:sec1", "artifact_type": "script", "accepted_rev": "script:sec1@r1"}]

        def accepted_content(self, artifact_id):
            return {
                "units": [
                    {"kind": "narration", "text": "我们来看一个例子，你觉得他会怎么做？"},
                    {"kind": "narration", "text": "综上所述，该现象具有重要意义，值得我们注意的是其背后机制。"},
                    {"kind": "visual", "text": "图示说明"},
                ]
            }

    metrics = safety.oral_lecture_metrics(_Store())
    assert metrics["narration_units"] == 2
    assert metrics["spoken_marker_ratio"] > 0
    assert metrics["written_only_marker_count"] >= 1
    assert "不设自动阈值" in metrics["note"]


def test_case_i_requests_media_consistency():
    case = cases.get_case("I")
    assert case["expect"]["media"]["check_consistency"] is True
    assert case["expect"]["animation"]["max_approved"] == 3
    assert not cases.validate_case(case)

    case = cases.get_case("H")
    assert case["expect"]["safety_cases"]
    assert not cases.validate_case(case)
