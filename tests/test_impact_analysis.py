from __future__ import annotations

from conftest import REQUEST_1, run_build

from pebs.conversation import impact


def _accepted_project(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    return run_id


def test_impact_contains_downstream_only(engine):
    _accepted_project(engine)
    result = impact.impact(engine.store, ["case:sec1:1"])
    affected = set(result["affected"])
    assert "case:sec1:1" in affected
    assert "script:sec1" in affected
    assert "media_plan:sec1" in affected
    assert "pptx_deck" in affected
    assert "preview" in affected
    assert "export_manifest" in affected
    assert "learning_design:sec1" not in affected
    assert "evidence_index" not in affected
    assert "requirements" not in affected


def test_impact_excludes_upstream_and_unknown(engine):
    _accepted_project(engine)
    result = impact.impact(engine.store, ["case:sec1:1", "case:does-not-exist"])
    assert "case:does-not-exist" in result["unresolved"]
    upstream = {"learning_design:sec1", "requirements", "claims", "evidence_index"}
    assert not (upstream & set(result["affected"]))


def test_impact_order_respects_dependencies(engine):
    _accepted_project(engine)
    result = impact.impact(engine.store, ["case:sec1:1"])
    order = result["order"]
    assert order.index("script:sec1") < order.index("pptx_deck")
    assert order.index("pptx_deck") < order.index("export_manifest")
    edges = {(edge["from"], edge["to"]) for edge in result["edges"]}
    assert ("case:sec1:1", "script:sec1") in edges


def test_impact_of_lesson_plan_keeps_design_and_evidence(engine):
    _accepted_project(engine)
    result = impact.impact(engine.store, ["lesson_plan:sec1"])
    affected = set(result["affected"])
    assert "export_manifest" in affected
    assert "learning_design:sec1" not in affected
    assert "evidence_index" not in affected
