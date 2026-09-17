from __future__ import annotations

import pytest

from pebs.evidence import EvidenceStore
from pebs.store import Store


@pytest.fixture
def env(tmp_path):
    store = Store("testproj", tmp_path / "proj")
    evidence = EvidenceStore(store)
    yield store, evidence
    store.close()


def _source_with(evidence, text):
    return evidence.add_source(
        source_type="journal_article",
        title="测试来源",
        content_level="full_text",
        snapshot_text=text,
    )


def test_quote_must_be_locatable(env):
    _, evidence = env
    claim = evidence.add_claim("观察应区分事实与判断。", "descriptive")
    source = _source_with(evidence, "观察记录应区分事实与判断。这是第二句。")
    with pytest.raises(ValueError):
        evidence.add_assessment(
            claim_id=claim["claim_id"],
            claim_version=claim["version"],
            source_id=source["source_id"],
            source_version=source["version"],
            quote="模型中编造的、原文没有的引用",
            quote_location="",
            support="direct",
            result="SUPPORTED",
            method="test",
            method_version="0",
        )


def test_citation_exists_but_does_not_support_claim(env):
    _, evidence = env
    claim = evidence.add_claim("压力一定导致失眠。", "causal")
    source = _source_with(evidence, "压力与某些生理反应相关，但研究未支持单一因果方向。")
    evidence.add_assessment(
        claim_id=claim["claim_id"],
        claim_version=claim["version"],
        source_id=source["source_id"],
        source_version=source["version"],
        quote="研究未支持单一因果方向",
        quote_location="句 2",
        support="contradictory",
        result="DISPUTED",
        method="test",
        method_version="0",
    )
    assert evidence.claim_status(claim["claim_id"], claim["version"]) == "DISPUTED"
    assert not evidence.is_supported(f"{claim['claim_id']}@v{claim['version']}")


def test_metadata_only_source_cannot_support(env):
    _, evidence = env
    claim = evidence.add_claim("某结论。", "descriptive")
    source = evidence.add_source(
        source_type="journal_article",
        title="只有元数据",
        content_level="metadata",
        snapshot_text=None,
    )
    assert evidence.quote_present(source["revision_id"], "任意引用") is False
    with pytest.raises(ValueError):
        evidence.add_assessment(
            claim_id=claim["claim_id"],
            claim_version=claim["version"],
            source_id=source["source_id"],
            source_version=source["version"],
            quote="任意引用",
            quote_location="",
            support="direct",
            result="SUPPORTED",
            method="test",
            method_version="0",
        )


def test_conflicting_evidence_is_kept(env):
    _, evidence = env
    claim = evidence.add_claim("相关不等于因果。", "theoretical")
    good = _source_with(evidence, "相关不等于因果。")
    bad = _source_with(evidence, "有人主张相关就可以推出因果。")
    evidence.add_assessment(
        claim_id=claim["claim_id"],
        claim_version=claim["version"],
        source_id=good["source_id"],
        source_version=good["version"],
        quote="相关不等于因果",
        quote_location="句 1",
        support="direct",
        result="SUPPORTED",
        method="test",
        method_version="0",
    )
    evidence.add_assessment(
        claim_id=claim["claim_id"],
        claim_version=claim["version"],
        source_id=bad["source_id"],
        source_version=bad["version"],
        quote="相关就可以推出因果",
        quote_location="句 1",
        support="contradictory",
        result="DISPUTED",
        method="test",
        method_version="0",
    )
    status = evidence.claim_status(claim["claim_id"], claim["version"])
    assert status == "DISPUTED"
    assert len(evidence.assessments(claim["claim_id"], claim["version"])) == 2
