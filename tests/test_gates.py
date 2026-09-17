from __future__ import annotations

import json

import pytest
from conftest import REQUEST_1, FakeLLM, run_build

from pebs import gates


def _mutate_accepted(engine, artifact_id, mutate):
    content = json.loads(json.dumps(engine.store.accepted_content(artifact_id)))
    mutate(content)
    info = engine.store.add_revision(
        artifact_id=artifact_id,
        artifact_type=engine.store.get_revision(engine.store.accepted_rev_id(artifact_id))["artifact_type"],
        content=content,
        produced_by="test-mutant",
    )
    engine.store.set_accepted(artifact_id, info["revision_id"])
    return content


@pytest.fixture
def accepted_build(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    return engine


def test_g2_fails_when_claim_not_supported(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine, "script:sec1", lambda c: c["units"][1].update({"claim_refs": ["clm_deadbeef00@v1"]})
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g2_evidence(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("未获支持的 Claim" in issue["reason"] for issue in result["issues"])


def test_g2_fails_on_pending_placeholder(accepted_build):
    engine = accepted_build

    def mutate(content):
        content["units"][1]["placeholder"] = True

    _mutate_accepted(engine, "script:sec1", mutate)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g2_evidence(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("待核验" in issue["reason"] for issue in result["issues"])


def test_g4_fails_on_diagnosis_and_labeling(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine,
        "script:sec1",
        lambda c: c["units"][1].update({"text": "该学生患有焦虑症，应建议转介。"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g4_safety(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    reasons = " ".join(issue["reason"] for issue in result["issues"])
    assert "诊断" in reasons or "转介" in reasons or "标签" in reasons


def test_g4_needs_review_for_individual_inference(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine,
        "script:sec1",
        lambda c: c["units"][1].update({"text": "该学生注意力不集中，需要调整活动。"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g4_safety(ctx, "script:sec1")
    assert result["status"] == "NEEDS_REVIEW"


def test_g3_fails_when_strategy_outside_allowed_set(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine,
        "teaching_plan:sec1",
        lambda c: c["strategies"][0].update({"strategy": "pure-lecture"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g3_pedagogy(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("不在知识类型" in issue["reason"] for issue in result["issues"])


def test_g6_flags_animation_requirement_conflict(engine):
    engine.llm = FakeLLM(animation_rejected=True)
    run_id, changeset_id = run_build(engine, "任务1 观察记录。每节 10–9999 字，每节至少 1 个案例和 1 个动画。")
    engine.accept(changeset_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g6_multimedia(ctx, "script:sec1")
    assert result["status"] == "NEEDS_REVIEW"
    assert any("未通过 Animation Gate" in issue["reason"] for issue in result["issues"])
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False


def test_g6_not_applicable_requires_reason(engine):
    engine.llm = FakeLLM(animation_item=False)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g6_multimedia(ctx, "script:sec1")
    assert result["status"] == "NOT_APPLICABLE"
    assert result.get("not_applicable_reason")


def test_gate_result_invalidates_when_script_changes(accepted_build):
    engine = accepted_build
    assert gates.export_readiness(engine.store)["ready"] is True
    _mutate_accepted(engine, "script:sec1", lambda c: c["units"][1].update({"text": "改写后的讲解。"}))
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    assert any("已过期" in item for item in readiness["blocking"])


def _with_referral_wording(content, phrase="该学生需要转介，由校外机构接手"):
    """Place the banned wording inside the UDL payload (option text)."""
    options = content.setdefault("udl", {}).setdefault("options", [])
    assert options, "fixture teaching plan must contain udl.options"
    options[0]["representation"] = phrase


def _with_barrier_referral_wording(content, phrase="建议转介"):
    """Same ban, reached through the barrier analysis instead of an option."""
    barriers = content.setdefault("udl", {}).setdefault("barriers", [])
    if barriers and isinstance(barriers[0], dict):
        barriers[0]["mitigation"] = phrase
    else:
        barriers.append(phrase)


def test_g5_fails_on_prohibited_referral_wording(accepted_build):
    engine = accepted_build
    _mutate_accepted(engine, "teaching_plan:sec1", _with_referral_wording)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g5_udl(ctx, "script:sec1")
    # A deterministic policy violation fails; it is never a soft review state.
    assert result["status"] == "FAIL"
    assert result["status"] != "NEEDS_REVIEW"
    assert any("禁止的转介措辞" in issue["reason"] for issue in result["issues"])


def test_g5_fails_on_referral_wording_inside_barriers(accepted_build):
    engine = accepted_build
    _mutate_accepted(engine, "teaching_plan:sec1", _with_barrier_referral_wording)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g5_udl(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("禁止的转介措辞" in issue["reason"] for issue in result["issues"])


def test_g5_passes_without_prohibited_wording(accepted_build):
    ctx = gates.GateContext(store=accepted_build.store, evidence=accepted_build.evidence)
    result = gates.g5_udl(ctx, "script:sec1")
    assert result["status"] == "PASS", result["issues"]


def test_g5_failure_is_visible_to_export_readiness(accepted_build):
    engine = accepted_build
    _mutate_accepted(engine, "teaching_plan:sec1", _with_referral_wording)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g5_udl(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    # Record the re-evaluated result the way the gate runner does, then accept it.
    written = gates.write_gate_results(engine.store, [result], "run_g5_regression")
    assert written
    engine.store.set_accepted(gates.gate_artifact_id("G5", "script:sec1"), written[-1])
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    assert any("G5 状态为 FAIL" in item for item in readiness["blocking"]), readiness["blocking"]


HYPOTHESIS_TEXT = "把工作记忆容量当作固定常数"


def _with_model_hypothesis(content):
    content.setdefault("difficulties", []).append({"text": HYPOTHESIS_TEXT, "basis": "model_hypothesis"})


def test_g3_fails_when_model_hypothesis_enters_facts(accepted_build):
    engine = accepted_build
    _mutate_accepted(engine, "learning_design:sec1", _with_model_hypothesis)
    _mutate_accepted(
        engine,
        "script:sec1",
        lambda c: c["units"][0].update({"text": f"讲解要点。{HYPOTHESIS_TEXT}，因此按此设计练习。"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g3_pedagogy(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("模型假设进入正式教材事实部分" in issue["reason"] for issue in result["issues"])


def test_g3_allows_model_hypothesis_kept_out_of_facts(accepted_build):
    engine = accepted_build
    _mutate_accepted(engine, "learning_design:sec1", _with_model_hypothesis)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g3_pedagogy(ctx, "script:sec1")
    assert result["status"] == "PASS", result["issues"]


def test_progression_basis_accepts_only_the_documented_values(accepted_build):
    """Spec 19 lists four bases; anything else fails closed at the schema."""
    from pebs import schemas

    content = accepted_build.store.accepted_content("learning_design:sec1")
    for value in ("evidence_supported", "source_derived", "instructor_provided", "model_hypothesis"):
        content["difficulties"] = [{"text": "标记契约", "basis": value}]
        schemas.validate(content, "learning_design")

    content["difficulties"] = [{"text": "标记契约", "basis": "model_guess"}]
    with pytest.raises(schemas.SchemaError):
        schemas.validate(content, "learning_design")
