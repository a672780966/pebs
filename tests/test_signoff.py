from __future__ import annotations

import pytest
from conftest import REQUEST_1, run_build

from pebs.engine import PlanEditRejected


def _claimed_engine(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    claim = engine.evidence.claims()[0]
    return engine, changeset_id, claim


def test_signoff_requires_accepted_changeset_and_basis(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    with pytest.raises(PlanEditRejected):
        engine.record_signoff(changeset_id, reviewer="teacher", basis="教学检查")
    engine.accept(changeset_id)
    with pytest.raises(PlanEditRejected):
        engine.record_signoff(changeset_id, reviewer="", basis="依据")
    with pytest.raises(PlanEditRejected):
        engine.record_signoff(changeset_id, reviewer="teacher", basis="")
    content = engine.record_signoff(
        changeset_id,
        reviewer="王老师",
        basis="逐节通读脚本与教案，核对引用与术语，确认适龄表述",
        changes="无需修改",
    )
    assert content["reviewer"] == "王老师"
    from pebs.store import current_signoffs

    signoffs = current_signoffs(engine.store)
    assert signoffs and signoffs[-1]["reviewer"] == "王老师"


def test_signoff_appears_in_export_manifest(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    engine.record_signoff(changeset_id, reviewer="王老师", basis="抽查三页并核对引用")
    result = engine.export_now("draft")
    signoffs = result["manifest"]["signoffs"]
    assert any(entry["reviewer"] == "王老师" for entry in signoffs)


def test_signoff_does_not_cover_newer_revisions(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    engine.record_signoff(changeset_id, reviewer="王老师", basis="基线签署")
    from pebs.store import current_signoffs

    assert current_signoffs(engine.store)
    engine.edit_slide(1, {"title": "改标题"})
    last = engine.store.list_changesets()[0]
    engine.accept(last["changeset_id"])
    assert current_signoffs(engine.store) == []


def test_human_review_cannot_force_support_without_locatable_quote(engine):
    engine, changeset_id, claim = _claimed_engine(engine)
    source = engine.evidence.add_source(
        source_type="user_material",
        title="人工复核材料",
        content_level="full_text",
        snapshot_text="观察记录应区分事实与判断，这是本材料的明确表述。",
    )
    with pytest.raises(ValueError):
        engine.review_claim(
            claim["claim_id"],
            claim["version"],
            decision="supported",
            reviewer="王老师",
            basis="依据材料批准",
            source_id=source["source_id"],
            quote="材料里根本没有这句话",
        )
    with pytest.raises(ValueError):
        engine.review_claim(
            claim["claim_id"], claim["version"], decision="supported", reviewer="王老师", basis="无引用"
        )
    result = engine.review_claim(
        claim["claim_id"],
        claim["version"],
        decision="supported",
        reviewer="王老师",
        basis="材料第 1 句明确支持",
        source_id=source["source_id"],
        quote="观察记录应区分事实与判断",
        quote_location="第 1 句",
    )
    assert result["result"] == "SUPPORTED"
    assert engine.evidence.claim_status(claim["claim_id"], claim["version"]) == "SUPPORTED"
    assessments = engine.evidence.assessments(claim["claim_id"], claim["version"])
    assert any(item["method"] == "human-review" for item in assessments)


def test_human_review_unsupported_keeps_honesty(engine):
    engine, changeset_id, claim = _claimed_engine(engine)
    result = engine.review_claim(
        claim["claim_id"],
        claim["version"],
        decision="unsupported",
        reviewer="王老师",
        basis="查证后无法找到支持来源",
    )
    assert result["result"] == "UNSUPPORTED"
    assert engine.evidence.claim_status(claim["claim_id"], claim["version"]) == "UNSUPPORTED"
