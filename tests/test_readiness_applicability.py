"""E/2: formal readiness is decided by the deliverable contract, not by artifact luck.

Applicability comes from requirements.outputs (the schema-required contract).
An applicable gate with no result blocks; an inapplicable gate is reported as
NOT_APPLICABLE with a deterministic reason instead of PASS. Readiness only
aggregates results: it never re-runs or re-judges a gate.
"""

from __future__ import annotations

import json

import pytest
from conftest import REQUEST_1, run_build

from pebs import gates


def _accepted(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    return run_id


def _set_contract(engine, outputs):
    reqs = json.loads(json.dumps(engine.store.accepted_content("requirements")))
    reqs["outputs"] = list(outputs)
    info = engine.store.add_revision(
        artifact_id="requirements",
        artifact_type="requirements",
        content=reqs,
        produced_by="test-contract",
    )
    engine.store.set_accepted("requirements", info["revision_id"])


def _entry(readiness, gate_id):
    return next(item for item in readiness["summary"] if item["gate_id"] == gate_id)


def _script_contract_engine(engine, outputs=("script",)):
    """A script deliverable with a declared contract and no gate results yet."""
    rev = engine.store.add_revision(
        artifact_id="script:sec1", artifact_type="script", content={"units": []}, produced_by="test"
    )
    engine.store.set_accepted("script:sec1", rev["revision_id"])
    reqs = engine.store.add_revision(
        artifact_id="requirements",
        artifact_type="requirements",
        content={
            "project_id": "testproj",
            "course": "course",
            "language": "zh",
            "outputs": list(outputs),
            "sections": [],
            "items": [],
        },
        produced_by="test",
    )
    engine.store.set_accepted("requirements", reqs["revision_id"])
    return rev["revision_id"]


def test_full_script_route_applicability_is_unchanged(engine):
    """The most important regression: a script contract behaves exactly as before."""
    _accepted(engine)
    assert "script" in engine.store.accepted_content("requirements")["outputs"]

    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is True
    for gate_id in gates.GATE_ORDER:
        entry = _entry(readiness, gate_id)
        assert entry["status"] in gates.PASSING
        assert entry["current"] is True
        assert not entry.get("not_applicable_reason")


@pytest.mark.parametrize("outputs", [("ppt",), ("lesson_plan",), ("lesson_plan", "ppt")])
def test_script_gates_are_not_applicable_without_a_script_deliverable(engine, outputs):
    _accepted(engine)
    _set_contract(engine, outputs)

    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is True
    assert readiness["blocking"] == []
    for gate_id in gates.GATE_ORDER:
        entry = _entry(readiness, gate_id)
        assert entry["status"] == "NOT_APPLICABLE"
        assert entry["status"] != "PASS"  # it was not evaluated, so it is not a pass
        assert entry["not_applicable_reason"]
        assert gate_id in entry["not_applicable_reason"]


def test_lesson_plus_pptx_does_not_require_the_script_package(engine):
    _accepted(engine)
    _set_contract(engine, ["lesson_plan", "ppt"])
    readiness = gates.export_readiness(engine.store)
    assert all(_entry(readiness, gate_id)["status"] == "NOT_APPLICABLE" for gate_id in gates.GATE_ORDER)
    assert not any("尚无脚本产物" in item for item in readiness["blocking"])
    assert not any("尚未在" in item for item in readiness["blocking"])


def test_not_applicable_reasons_are_deterministic(engine):
    _accepted(engine)
    _set_contract(engine, ["ppt"])
    first = {e["gate_id"]: e["not_applicable_reason"] for e in gates.export_readiness(engine.store)["summary"]}
    second = {e["gate_id"]: e["not_applicable_reason"] for e in gates.export_readiness(engine.store)["summary"]}
    explicit = {
        e["gate_id"]: e["not_applicable_reason"]
        for e in gates.export_readiness(engine.store, outputs={"ppt"})["summary"]
    }
    assert first == second == explicit
    assert all(reason.strip() for reason in first.values())


def test_missing_applicable_gate_blocks_instead_of_becoming_not_applicable(engine):
    _script_contract_engine(engine)
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    assert any("尚未在 script:sec1 上运行" in item for item in readiness["blocking"])
    assert _entry(readiness, "G2")["status"] is None  # missing, never inferred
    assert not _entry(readiness, "G2").get("not_applicable_reason")


@pytest.mark.parametrize("status", ["FAIL", "NEEDS_REVIEW"])
def test_non_passing_applicable_gate_blocks(engine, status):
    rev_id = _script_contract_engine(engine)
    result = gates.make_result(
        "G2",
        target_artifact="script:sec1",
        target_rev_id=rev_id,
        target_hash="hash",
        status=status,
        issues=[{"location": "script:sec1", "reason": "probe", "next_step": "probe"}],
        dep_versions={},
        run_id="run_probe",
        environment="production",
    )
    written = gates.write_gate_results(engine.store, [result], "run_probe")
    engine.store.set_accepted(gates.gate_artifact_id("G2", "script:sec1"), written[-1])

    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    assert any(f"G2 状态为 {status}" in item for item in readiness["blocking"])
    assert _entry(readiness, "G2")["status"] == status


def test_g8_remains_the_hard_gate_for_a_pptx_only_contract(engine):
    """Script gates become N/A; the export-manifest gate is still required."""
    _accepted(engine)
    _set_contract(engine, ["ppt"])
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is True
    assert gates.gate_applicability("G8", {"ppt"}).applicable is True
    assert gates.GATE_SCOPE["G8"] == "export_manifest"

    before = len(engine.store.revisions_of("export_manifest"))
    result = engine.export_now("formal")
    after = engine.store.revisions_of("export_manifest")
    if result.get("ok") is False:
        # The formal gate refused before publishing any manifest.
        assert len(after) == before
    else:
        assert after, "a completed export must publish a manifest"
        assert engine.store.get_revision(after[-1])["content"]["mode"] != "formal"
