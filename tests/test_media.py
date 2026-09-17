from __future__ import annotations

from pathlib import Path

from conftest import REQUEST_1, FakeLLM, run_build

from pebs import gates, media, schemas
from pebs.pipeline import _enforce_medium


def test_build_produces_media_artifacts_and_files(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    assert engine.store.get_run(run_id)["status"] == "succeeded"
    plan = engine.store.get_revision(engine.store.revisions_of("media_plan:sec1")[-1])["content"]
    assert [item["recommended_medium"] for item in plan["items"]] == ["diagram", "animation"]

    diagrams = engine.store.get_revision(engine.store.revisions_of("diagrams:sec1")[-1])["content"]
    assert len(diagrams["diagrams"]) == 1
    svg_path = Path(diagrams["diagrams"][0]["svg_path"])
    assert svg_path.exists()
    assert media.validate_svg(svg_path.read_text(encoding="utf-8")) == []

    decisions = engine.store.get_revision(
        engine.store.revisions_of("animation_decisions:sec1")[-1]
    )["content"]
    assert decisions["decisions"][0]["decision"] == "ANIMATION"

    storyboard = engine.store.get_revision(engine.store.revisions_of("storyboard:sec1")[-1])["content"]
    assert storyboard["rendered"] is False
    assert len(storyboard["shots"]) == 2
    assert storyboard["video_prompt"].strip()
    assert storyboard["static_terminal_state"].strip()
    assert (Path(engine.store.base_dir) / "media" / "prompts" / "sec1.txt").exists()
    assert (Path(engine.store.base_dir) / "media" / "storyboard" / "sec1.md").exists()

    engine.accept(changeset_id)
    g6 = engine.store.accepted_content("gate:G6:script:sec1")
    assert g6["status"] == "PASS"


def test_export_includes_media_files_and_formal_publish(engine, no_pptx):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    assert gates.export_readiness(engine.store)["ready"] is True
    result = engine.export_now("formal")
    assert result["ok"] is True
    kinds = {entry["kind"] for entry in result["manifest"]["files"]}
    assert {"docx", "markdown", "svg", "json", "txt"} <= kinds
    roles = {entry.get("role") for entry in result["manifest"]["files"]}
    assert {"lesson_script", "diagram", "storyboard", "prompt"} <= roles
    accept = engine.accept(result["changeset_id"])
    assert accept["status"] == "accepted"
    formal = Path(engine.store.base_dir) / "outputs" / "formal"
    names = [path.name for path in formal.iterdir()]
    assert any(name.endswith(".svg") for name in names)
    assert any(name.endswith(".txt") for name in names)


def test_animation_gate_enforces_temporal_necessity(engine):
    engine.llm = FakeLLM(animation_gate_bad=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    decisions = engine.store.get_revision(
        engine.store.revisions_of("animation_decisions:sec1")[-1]
    )["content"]
    decision = decisions["decisions"][0]
    assert decision["decision"] == "STATIC"
    assert "temporal_necessity" in (decision.get("enforced") or "")
    storyboard = engine.store.get_revision(engine.store.revisions_of("storyboard:sec1")[-1])["content"]
    assert storyboard["shots"] == []


def test_svg_validator_rejects_unsafe_markup():
    assert media.validate_svg("<svg viewBox='0 0 10 10'><text>x</text></svg>") == []
    assert any(
        "script" in error
        for error in media.validate_svg("<svg viewBox='0 0 1 1'><script>alert(1)</script><text>x</text></svg>")
    )
    assert any(
        "事件属性" in error
        for error in media.validate_svg("<svg viewBox='0 0 1 1'><text onclick='x()'>x</text></svg>")
    )
    assert any(
        "外部引用" in error
        for error in media.validate_svg("<svg viewBox='0 0 1 1'><image href='https://x/y.png'/><text>x</text></svg>")
    )
    assert any("viewBox" in error for error in media.validate_svg("<svg><text>x</text></svg>"))
    assert any("text" in error for error in media.validate_svg("<svg viewBox='0 0 1 1'></svg>"))


def test_storyboard_schema_forbids_rendered_true():
    bad = {"section_id": "sec1", "shots": [], "video_prompt": "", "static_terminal_state": "", "rendered": True}
    raised = False
    try:
        schemas.validate(bad, "storyboard")
    except schemas.SchemaError:
        raised = True
    assert raised


def test_g6_fails_when_recommended_diagram_missing(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    content = engine.store.accepted_content("diagrams:sec1")
    content["diagrams"] = []
    info = engine.store.add_revision(
        artifact_id="diagrams:sec1", artifact_type="diagrams", content=content, produced_by="test"
    )
    engine.store.set_accepted("diagrams:sec1", info["revision_id"])
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g6_multimedia(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("未生成对应 SVG" in issue["reason"] for issue in result["issues"])


def test_media_plan_downgrades_animation_without_temporal_dependency():
    item = {
        "recommended_medium": "animation",
        "temporal_dependency": False,
        "comparison_dependency": True,
        "rationale": "误判",
    }
    out = _enforce_medium(item)
    assert out["recommended_medium"] == "diagram"
    assert "系统校正" in out["rationale"]
