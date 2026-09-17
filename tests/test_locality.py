from __future__ import annotations

from conftest import REQUEST_2, run_build


def test_case_replacement_only_rebuilds_dependent_sections(engine):
    run_id, changeset_id = run_build(engine, REQUEST_2)
    assert engine.store.get_run(run_id)["status"] == "succeeded"
    assert engine.accept(changeset_id)["status"] == "accepted"

    sec1_rev_before = engine.store.accepted_rev_id("script:sec1")
    sec2_rev_before = engine.store.accepted_rev_id("script:sec2")
    sec1_hash_before = engine.store.get_revision(sec1_rev_before)["content_hash"]
    gate_sec1_before = {
        a["artifact_id"]: a["accepted_rev"]
        for a in engine.store.list_artifacts()
        if a["artifact_id"].startswith("gate:") and a["artifact_id"].endswith("script:sec1")
    }

    result = engine.case_replace("case:sec2:1", "换成一个托育园午睡管理的案例")
    assert result["affected_sections"] == ["sec2"]
    accept = engine.accept(result["changeset_id"])
    assert accept["status"] == "accepted"
    assert "script:sec1" not in accept.get("stale_artifacts", [])

    sec1_rev_after = engine.store.accepted_rev_id("script:sec1")
    sec2_rev_after = engine.store.accepted_rev_id("script:sec2")
    assert sec1_rev_after == sec1_rev_before
    assert engine.store.get_revision(sec1_rev_after)["content_hash"] == sec1_hash_before
    assert sec2_rev_after != sec2_rev_before

    gate_sec1_after = {
        a["artifact_id"]: a["accepted_rev"]
        for a in engine.store.list_artifacts()
        if a["artifact_id"].startswith("gate:") and a["artifact_id"].endswith("script:sec1")
    }
    assert gate_sec1_after == gate_sec1_before
    assert engine.store.is_stale("script:sec1") is False


def test_reject_case_replacement_keeps_original_versions(engine):
    run_id, changeset_id = run_build(engine, REQUEST_2)
    engine.accept(changeset_id)
    sec2_rev = engine.store.accepted_rev_id("script:sec2")
    result = engine.case_replace("case:sec2:1", "换成完全不同的案例")
    reject = engine.reject(result["changeset_id"])
    assert reject["status"] == "rejected"
    assert engine.store.accepted_rev_id("script:sec2") == sec2_rev
    assert engine.store.accepted_content("case:sec2:1")["title"] == "午睡观察记录"
