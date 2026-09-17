from __future__ import annotations

from conftest import FakeLLM, MissingLLM

from pebs import router_v2

REQUEST = (
    "写《托育机构管理实务》任务1 观察记录课程脚本，每节 300–400 字，每节至少 1 个案例，"
    "称谓统一使用「婴幼儿」，不要动画，不需要 PPT。"
)


def test_deterministic_extraction():
    det = router_v2.extract_deterministic(REQUEST)
    assert (det["word_min"], det["word_max"]) == (300, 400)
    assert "case" in det["required_components"]
    assert det["no_animation"] is True
    assert det["no_ppt"] is True
    assert det["needs_ppt"] is False
    assert "婴幼儿" in det["terminology"]
    assert det["sections"]
    assert det["audit_only"] is False


def test_hybrid_merge_respects_deterministic_constraints():
    result = router_v2.route(REQUEST, llm=FakeLLM())
    assert result["source"] == "hybrid"
    assert result["knowledge_types"]
    assert result["learner_profile"]["level"]
    assert "pptx" not in result["requested_outputs"]
    assert result["constraints"]["no_animation"] is True
    assert result["constraints"]["needs_ppt"] is False
    assert result["confidence"] > 0.5
    assert router_v2.validate(result) == []


def test_fallback_without_llm_is_deterministic():
    result = router_v2.route("写一节观察记录课程脚本。", llm=MissingLLM())
    assert result["source"] == "deterministic_fallback"
    assert result["confidence"] <= 0.5
    assert result["uncertainties"]
    assert "script" in result["requested_outputs"]
    assert router_v2.validate(result) == []


def test_bad_llm_payload_falls_back():
    result = router_v2.route("写一节观察记录课程脚本。", llm=FakeLLM(semantic_route_bad=True))
    assert result["source"] == "deterministic_fallback"


def test_audit_only_detected():
    det = router_v2.extract_deterministic("只审核现有课程有没有理论错误。")
    assert det["audit_only"] is True
    result = router_v2.route("只审核现有课程有没有理论错误。", llm=MissingLLM())
    assert result["constraints"]["audit_only"] is True


def test_validate_flags_conflicts():
    result = router_v2.route("写一节课程脚本。", llm=MissingLLM())
    result["constraints"]["no_animation"] = True
    result["media_need"] = "ANIMATION_CANDIDATE"
    assert router_v2.validate(result)


def test_llm_cannot_override_deterministic_word_range_and_no_ppt():
    payload = {
        "task_intent": "x",
        "primary_outputs": ["pptx"],
        "secondary_outputs": [],
        "delivery_mode": "live_class",
        "knowledge_types": ["concept"],
        "research_need": "DEEP",
        "media_need": "ANIMATION_CANDIDATE",
        "assessment_need": True,
        "requested_outputs": ["pptx", "docx"],
        "risk_flags": [],
        "confidence": 0.9,
        "uncertainties": [],
    }
    result = router_v2.route(REQUEST, llm=FakeLLM(route_payload=payload))
    assert (result["constraints"]["word_min"], result["constraints"]["word_max"]) == (300, 400)
    assert "pptx" not in result["requested_outputs"]
    assert result["media_need"] != "ANIMATION_CANDIDATE"
    assert result["constraints"]["no_animation"] is True
