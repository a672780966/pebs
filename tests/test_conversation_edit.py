from __future__ import annotations

import pytest
from conftest import REQUEST_2, run_build

from pebs.engine import PlanEditRejected
from pebs.store import ConflictError


def _accepted(engine):
    run_id, changeset_id = run_build(engine, REQUEST_2)
    engine.accept(changeset_id)
    return run_id


def test_conversation_edit_localizes_case_and_locks_other_sections(engine):
    _accepted(engine)
    case_before = engine.store.accepted_rev_id("case:sec2:1")
    script_sec1_before = engine.store.accepted_rev_id("script:sec1")
    design_before = engine.store.accepted_rev_id("learning_design:sec1")
    design_sec2_before = engine.store.accepted_rev_id("learning_design:sec2")
    evidence_before = engine.store.accepted_rev_id("evidence_index")

    result = engine.conversation_edit("第2节案例太理论了，换成大学宿舍里的情境，第1节不要动")

    assert result["run_status"] == "succeeded", result
    assert result["intent"]["intent"] in ("replace", "revise")
    assert "case:sec2:1" in result["affected_artifacts"]
    assert "learning_design:sec1" in result["locked_artifacts"]
    assert "evidence_index" in result["locked_artifacts"]
    assert any("section_1" == item for item in result["intent"]["preserve"])
    assert "export_manifest" in result["affected_artifacts"]
    assert engine.store.is_locked("learning_design:sec1") is True

    accepted = engine.accept(result["changeset_id"])
    assert accepted.get("ok", True) is not False

    assert engine.store.accepted_rev_id("case:sec2:1") != case_before
    assert engine.store.accepted_rev_id("learning_design:sec1") == design_before
    assert engine.store.accepted_rev_id("learning_design:sec2") == design_sec2_before
    assert engine.store.accepted_rev_id("script:sec1") == script_sec1_before
    assert engine.store.accepted_rev_id("evidence_index") == evidence_before
    assert engine.store.is_locked("learning_design:sec1") is False


def test_locked_artifacts_reject_new_changeset_items(engine):
    _accepted(engine)
    result = engine.conversation_edit("第2节案例换掉")
    assert result["run_status"] == "succeeded"
    assert engine.store.is_locked("learning_design:sec1") is True
    with pytest.raises(ConflictError):
        engine.store.add_changeset_item(
            result["changeset_id"],
            engine.store.accepted_rev_id("learning_design:sec1"),
            "learning_design:sec1",
        )
    engine.reject(result["changeset_id"])
    assert engine.store.is_locked("learning_design:sec1") is False


def test_patch_plan_is_persisted_as_an_artifact(engine):
    _accepted(engine)
    result = engine.conversation_edit("第2节案例换掉", execute=False)
    patch = engine.store.accepted_content("patch_plan")
    assert patch["plan_id"] == result["plan_id"]
    assert patch["locked_artifacts"] == result["locked_artifacts"]
    assert patch["resolved_targets"]["section_ids"] == ["sec2"]
    assert patch["requires_confirmation"] is True


def test_execute_false_does_not_create_a_changeset(engine):
    _accepted(engine)
    before = len(engine.store.list_changesets())
    engine.conversation_edit("第2节案例换掉", execute=False)
    assert len(engine.store.list_changesets()) == before


def test_store_lock_blocks_the_patch_run_itself(engine):
    _accepted(engine)
    before = engine.store.accepted_rev_id("case:sec2:1")
    engine.store.set_locked("case:sec2:1", True)
    try:
        result = engine.conversation_edit("第2节案例换掉")
        assert result["run_status"] in ("blocked", "failed")
        assert engine.store.accepted_rev_id("case:sec2:1") == before
        steps = engine.run_status(result["run_id"])["steps"]
        case_step = next(step for step in steps if step["step_id"] == "cases")
        assert case_step["status"] == "BLOCKED"
        assert "preserve 契约" in (case_step["error"] or "")
    finally:
        engine.store.set_locked("case:sec2:1", False)


def test_unresolvable_message_is_rejected(engine):
    _accepted(engine)
    with pytest.raises(PlanEditRejected):
        engine.conversation_edit("让整体氛围更活泼一点")


def test_edit_re_runs_gates_only_for_the_affected_section(engine):
    _accepted(engine)
    result = engine.conversation_edit("第2节案例换掉")
    assert result["run_status"] == "succeeded", result

    steps = {step["step_id"]: step["status"] for step in engine.run_status(result["run_id"])["steps"]}
    assert steps.get("gates") == "SUCCEEDED", steps

    produced = {item["artifact_id"] for item in engine.store.run_changeset_items(result["run_id"])}
    assert "gate:G1:script:sec2" in produced
    assert "gate:G1:script:sec1" not in produced
