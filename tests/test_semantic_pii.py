from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, MissingLLM, run_build

from pebs import pii, policies, profiles, registry


def test_semantic_review_refuses_to_guess_without_provider():
    assert pii.semantic_review(MissingLLM(), "某班级三名幼儿在教室午睡") is None


def test_semantic_review_rejects_invalid_payload():
    llm = FakeLLM(privacy_payload={"risk": "MAYBE", "reasons": ["x"]})
    assert pii.semantic_review(llm, "文本") is None


def test_high_risk_material_is_excluded_and_flagged_for_manual_review(engine, tmp_path):
    engine.llm = FakeLLM(
        privacy_payload={
            "risk": "HIGH",
            "reidentifiable": True,
            "reasons": ["小样本班级 + 地点 + 特殊经历可指向具体幼儿"],
            "suggestions": ["删除地点与特殊经历细节"],
        }
    )
    material = tmp_path / "个案观察记录.txt"
    material.write_text("本班只有三名幼儿，其中一人在康复中心接受训练，家长提供了详细经历说明。", encoding="utf-8")
    run_id, changeset_id = run_build(engine, REQUEST_1, material_paths=[material])

    materials = engine.store.get_revision(engine.store.revisions_of("materials")[-1])["content"]
    entry = materials["files"][0]
    assert entry["sensitive"] is True
    assert entry["pii_layer"] == pii.LAYER_L2
    assert entry["manual_review_required"] is True
    assert entry["pii_reasons"]
    content_prompts = [prompt for prompt in engine.llm.prompts if "可重识别风险复核" not in prompt]
    assert content_prompts
    assert all("康复中心" not in prompt for prompt in content_prompts)
    review_prompts = [prompt for prompt in engine.llm.prompts if "可重识别风险复核" in prompt]
    assert review_prompts, "L2 隐私复核必须在隔离的专用请求中进行"
    step = next(s for s in engine.store.get_steps(run_id) if s["step_id"] == "parse_inputs")
    assert "语义隐私复核" in (step["note"] or "")


def test_low_risk_material_still_flows(engine, tmp_path):
    material = tmp_path / "教学笔记.txt"
    material.write_text("观察记录应区分事实与判断，这是通用教学要点。", encoding="utf-8")
    run_id, changeset_id = run_build(engine, REQUEST_1, material_paths=[material])
    materials = engine.store.get_revision(engine.store.revisions_of("materials")[-1])["content"]
    entry = materials["files"][0]
    assert entry["sensitive"] is False
    assert entry.get("pii_review") == "LOW"
    assert entry["pii_layer"] == "none"


def test_patch_policies_block_numeric_load_and_referral():
    load_skill = {"name": "cognitive-load-analyser"}
    errors = policies.apply_output_policies(load_skill, {"cognitive_load": "认知负荷=7.8"})
    assert errors and "数字化" in errors[0]
    assert policies.apply_output_policies(load_skill, {"level": "LOW", "reasons": [], "uncertainty": []}) == []

    udl_skill = {"name": "udl-barrier-anticipator"}
    referral = policies.apply_output_policies(udl_skill, {"note": "该学生需要转介"})
    assert referral and "referral" in referral[0]
    flags = policies.apply_output_policies(
        udl_skill, {"individual_support_review_flags": ["需要个别化支持评估（依据已有资料由教师判断）"]}
    )
    assert flags == []


def test_trauma_informed_policy_requires_disabled():
    record = {"name": "trauma-informed-skill", "status": "APPROVED", "enabled_by_default": True}
    errors = policies.check_skill_record(record)
    assert errors
    disabled = {"name": "trauma-informed-skill", "status": "DISABLED", "enabled_by_default": False}
    assert policies.check_skill_record(disabled) == []


def test_pck_policy_requires_gate_declaration():
    assert policies.check_skill_record({"name": "pck-developer", "status": "APPROVED", "gates_before": ["G2"]}) == []
    assert policies.check_skill_record({"name": "pck-developer", "status": "APPROVED", "gates_before": []})


def test_registry_entries_satisfy_patch_policies():
    for name, record in registry.load_skills().items():
        assert policies.check_skill_record(record) == [], f"{name} violates patch policies"


def test_education_provider_allowlist_is_data_only():
    providers = policies.load_providers()["providers"]
    entry = providers["education-agent-skills"]
    assert len(entry["initial_allowlist"]) == 14
    assert entry["status"] == "allowlist_only"
    assert policies.external_provider_allowed("dual-coding-designer", "education-agent-skills")
    assert not policies.external_provider_allowed("random-skill", "education-agent-skills")


def test_psychology_research_profile_reports_implemented_and_planned():
    profile = profiles.load_research_profile("psychology")
    assert profile["missing"] is False
    implemented = profiles.implemented_sources(profile)
    assert {"crossref", "openalex", "semantic_scholar", "pubmed"} <= set(implemented)
    unimplemented = {item["id"] for item in profiles.unimplemented_sources(profile)}
    assert {"eric", "psycinfo", "cnki"} <= unimplemented
    assert profiles.validate_configured_sources(profile, ["crossref", "eric"]) == ["eric"]

    from pebs import providers

    status = providers.provider_status()
    assert status["research"]["profile"]["name"] == "psychology"
    assert "eric" in status["research"]["profile"]["unimplemented"]
