from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, run_build


def _latest(engine, artifact_id):
    return engine.store.get_revision(engine.store.revisions_of(artifact_id)[-1])["content"]


def test_weird_enums_from_provider_are_normalized(engine):
    engine.llm = FakeLLM(weird_enums=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    assert engine.store.get_run(run_id)["status"] == "succeeded"

    claims = engine.evidence.claims()
    assert claims and claims[0]["claim_type"] == "descriptive"

    assessment = _latest(engine, "assessment:sec1")
    assert assessment["items"][0]["kind"] == "formative"

    media = _latest(engine, "media_plan:sec1")
    assert media["items"][0]["recommended_medium"] in ("text", "diagram", "animation")
    assert media["items"][0]["knowledge_function"] == "structure"

    plan = _latest(engine, "slide_plan")
    for row in plan["rows"]:
        assert row["layout_archetype"] in ("cover", "section_title", "bullets", "diagram", "table", "closing")
        assert row["density"] in ("low", "medium", "high")

    storyboard = _latest(engine, "storyboard:sec1")
    assert storyboard["shots"] and storyboard["shots"][0]["duration"] == 8.0
    assert storyboard["rendered"] is False
