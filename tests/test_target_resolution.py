from __future__ import annotations

from pebs.conversation import interpreter, resolver

SECTIONS = [
    {"section_id": "sec1", "title": "观察记录"},
    {"section_id": "sec2", "title": "事实与判断"},
    {"section_id": "sec3", "title": "常见误区"},
]
ARTIFACTS = [
    {"artifact_id": "case:sec1:1", "artifact_type": "case", "accepted_rev": "case:sec1:1@r1"},
    {"artifact_id": "case:sec2:1", "artifact_type": "case", "accepted_rev": "case:sec2:1@r1"},
    {"artifact_id": "storyboard:sec1", "artifact_type": "storyboard", "accepted_rev": "storyboard:sec1@r1"},
    {"artifact_id": "storyboard:sec2", "artifact_type": "storyboard", "accepted_rev": "storyboard:sec2@r1"},
    {"artifact_id": "script:sec2", "artifact_type": "script", "accepted_rev": "script:sec2@r1"},
    {"artifact_id": "lesson_plan:sec1", "artifact_type": "lesson_plan", "accepted_rev": "lesson_plan:sec1@r1"},
    {"artifact_id": "lesson_plan:sec2", "artifact_type": "lesson_plan", "accepted_rev": "lesson_plan:sec2@r1"},
]
SLIDES = [{"slide": 7, "section_id": "sec2"}, {"slide": 9, "section_id": "sec2"}]
SCRIPT_UNITS = [
    {"section_id": "sec1", "text": "观察记录应该区分事实与判断的差异"},
    {"section_id": "sec2", "text": "事实与判断的分界在于是否可被第三方复核"},
]


def _resolve(message: str) -> dict:
    intent = interpreter.interpret(message, llm=None, sections=SECTIONS)
    return resolver.resolve(
        message, intent, sections=SECTIONS, artifacts=ARTIFACTS, slides=SLIDES, script_units=SCRIPT_UNITS
    )


def test_ordinal_resolves_section_and_artifact_kind():
    resolved = _resolve("第2节案例太理论了，换成大学宿舍里的情境")
    intent, _, _ = interpreter.deterministic_intent("第2节案例太理论了，换成大学宿舍里的情境")
    assert intent in ("replace", "revise")
    assert resolved["section_ids"] == ["sec2"]
    assert resolved["artifact_kinds"] == ["case"]
    assert resolved["artifact_ids"] == ["case:sec2:1"]


def test_slide_number_resolves_to_slide_plan():
    resolved = _resolve("第7页换成对比图")
    assert resolved["slide_ids"] == [7]
    assert resolved["artifact_ids"] == ["slide_plan"]


def test_last_animation_resolves_to_last_storyboard():
    resolved = _resolve("最后一个动画删掉")
    assert resolved["artifact_kinds"] == ["storyboard"]
    assert resolved["artifact_ids"] == ["storyboard:sec2"]


def test_text_fragment_resolves_to_section():
    resolved = _resolve("事实与判断那一段太短了，扩写一下")
    assert resolved["section_ids"] == ["sec2"]
    assert resolved["artifact_ids"] == ["script:sec2"]


def test_unmapped_target_is_reported_not_guessed():
    resolved = _resolve("第9节案例换掉")
    assert resolved["section_ids"] == []
    assert "第9节" in resolved["unmapped"]
    assert resolved["artifact_ids"] == []


def test_activity_ordinal_resolves_to_lesson_plan():
    resolved = _resolve("第二个活动不够有冲击力，换一个，但心理学理论部分不要改")
    assert resolved["artifact_kinds"] == ["lesson_plan"]
    assert resolved["activity_index"] == [2]
    assert resolved["artifact_ids"] == ["lesson_plan:sec1"]


def test_preserve_clause_is_parsed_deterministically():
    intent = interpreter.interpret("第2节案例换掉，第1节不要动", llm=None, sections=SECTIONS)
    assert intent["preserve_sections"] == [1]
    assert any("section_1" == item for item in intent["preserve"])


def test_llm_layer_cannot_override_deterministic_intent():
    from conftest import FakeLLM

    llm = FakeLLM(
        conversation_payload={
            "intent": "expand",
            "section_ids": ["sec3"],
            "artifact_kinds": [],
            "slide_numbers": [],
            "preserve": ["evidence"],
            "expected_scope": "global",
            "confidence": 0.9,
        }
    )
    intent = interpreter.interpret("删掉第2节的案例", llm=llm, sections=SECTIONS)
    assert intent["intent"] == "remove"
    assert intent["llm_intent"] == "expand"
    assert "sec3" in intent["targets"]["section_ids"]
    assert "evidence" in intent["preserve"]
    assert intent["source"] == "hybrid"
