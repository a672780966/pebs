from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, run_build

from pebs.pipeline import _strip_claim_prefix


def test_strip_claim_prefix_variants():
    assert _strip_claim_prefix("【待核验】观察记录应区分事实与判断。") == "观察记录应区分事实与判断。"
    assert _strip_claim_prefix("[待核实] 某结论。") == "某结论。"
    assert _strip_claim_prefix("待核验：某结论。") == "某结论。"
    assert _strip_claim_prefix("  正常 Claim  ") == "正常 Claim"


def test_qualify_required_claim_is_rewritten_and_reassessed(engine):
    engine.llm = FakeLLM(qualify_flow=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    claims = engine.evidence.claims()
    claim_id = claims[0]["claim_id"]
    versions = [c for c in claims if c["claim_id"] == claim_id]
    assert len(versions) == 2
    assert versions[0]["status"] == "QUALIFY_REQUIRED"
    assert versions[-1]["status"] == "SUPPORTED"
    assert "相关" in versions[-1]["text"]
    assessments = engine.evidence.assessments(claim_id)
    results = [a["result"] for a in assessments]
    assert "QUALIFY_REQUIRED" in results and "SUPPORTED" in results

    claims_doc = engine.store.get_revision(engine.store.revisions_of("claims")[-1])["content"]
    assert claims_doc["claims"][0]["version"] == 2

    # The published evidence index must reference the final claim revision, that
    # revision must be SUPPORTED, and PCK must therefore be allowed to author.
    index = engine.store.get_revision(engine.store.revisions_of("evidence_index")[-1])["content"]
    entry = index["claims"][0]
    assert entry["version"] == engine.evidence.latest_version(entry["claim_id"])
    assert engine.evidence.claim_status(entry["claim_id"], entry["version"]) == "SUPPORTED"
    stored = engine.evidence.get_claim(entry["claim_id"], entry["version"])
    assert stored["usage"] == "讲解"
    steps = {step["step_id"]: step for step in engine.store.get_steps(run_id)}
    assert steps["teaching_plan"]["status"] == "SUCCEEDED"

    g2 = engine.store.accepted_content("gate:G2:script:sec1")
    assert g2["status"] == "PASS"


def test_indirect_support_with_human_flag_maps_to_qualify(engine):
    engine.llm = FakeLLM(qualify_flow=True, human_review_first=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    claim_id = engine.evidence.claims()[0]["claim_id"]
    first_assessment = engine.evidence.assessments(claim_id)[0]
    assert first_assessment["support"] == "contextual"
    assert first_assessment["result"] == "QUALIFY_REQUIRED"


def test_case_introduced_facts_are_verified_in_run(engine):
    engine.llm = FakeLLM(case_new_facts=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    claims = engine.evidence.claims()
    case_claim = next(claim for claim in claims if claim["usage"] == "案例")
    assert case_claim["status"] == "SUPPORTED"
    claims_doc = engine.store.get_revision(engine.store.revisions_of("claims")[-1])["content"]
    assert any(entry["claim_id"] == case_claim["claim_id"] for entry in claims_doc["claims"])
    engine.accept(changeset_id)
    g2 = engine.store.accepted_content("gate:G2:script:sec1")
    assert g2["status"] == "PASS", g2["issues"]


def test_direct_support_with_human_flag_requires_review(engine):
    engine.llm = FakeLLM(human_review_first=True)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    claim = engine.evidence.claims()[0]
    assert claim["status"] == "HUMAN_REVIEW_REQUIRED"
    assessments = engine.evidence.assessments(claim["claim_id"])
    assert assessments and assessments[0]["support"] == "direct"
    assert assessments[0]["result"] == "HUMAN_REVIEW_REQUIRED"
