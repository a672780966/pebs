from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, run_build

from pebs import gates


def _latest(engine, artifact_id):
    return engine.store.get_revision(engine.store.revisions_of(artifact_id)[-1])["content"]


def test_load_review_artifact_and_g6_pass(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    review = _latest(engine, "load_review:sec1")
    assert review["cognitive_load"]["level"] == "MEDIUM"
    assert review["cognitive_load"]["uncertainties"]
    pairing = review["dual_coding"]["pairings"][0]
    assert pairing["knowledge_function"] == "comparison"
    assert pairing["diagram_id"] == "d1"
    engine.accept(changeset_id)
    g6 = engine.store.accepted_content("gate:G6:script:sec1")
    assert g6["status"] == "PASS", g6["issues"]


def test_high_cognitive_load_triggers_needs_review(engine):
    engine.llm = FakeLLM(load_high=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    g6 = engine.store.accepted_content("gate:G6:script:sec1")
    assert g6["status"] == "NEEDS_REVIEW"
    assert any("认知负荷评估为 HIGH" in issue["reason"] for issue in g6["issues"])


def test_invalid_diagram_id_is_cleared_with_note(engine):
    engine.llm = FakeLLM(load_bad_diagram=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    review = _latest(engine, "load_review:sec1")
    pairing = review["dual_coding"]["pairings"][0]
    assert pairing["diagram_id"] == ""
    assert "图示 id 无效" in pairing["note"]


def test_null_fields_from_provider_are_normalized(engine):
    engine.llm = FakeLLM(load_null_fields=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    review = _latest(engine, "load_review:sec1")
    pairing = review["dual_coding"]["pairings"][0]
    assert pairing["diagram_id"] == ""
    assert pairing["verbal"] == ""
    assert pairing["knowledge_function"] == "structure"
    assert pairing["pairing_ok"] is False
    assert review["cognitive_load"]["uncertainties"] == []
    assert engine.store.get_run(run_id)["status"] == "succeeded"


def test_pairing_failure_is_hard_fail(engine):
    engine.llm = FakeLLM()
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    content = engine.store.accepted_content("load_review:sec1")
    content["dual_coding"]["pairings"][0]["pairing_ok"] = False
    info = engine.store.add_revision(
        artifact_id="load_review:sec1", artifact_type="load_review", content=content, produced_by="test"
    )
    engine.store.set_accepted("load_review:sec1", info["revision_id"])
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g6_multimedia(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("双重编码配对未通过" in issue["reason"] for issue in result["issues"])
