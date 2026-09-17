"""M6 §30–§34 / §62：人工评价入口（rubric 校验 + Artifact 落库 + performance 绑定）。"""

from __future__ import annotations

pytestmark = __import__('pytest').mark.benchmark_smoke

import pytest
from conftest import REQUEST_1, FakeLLM, run_dynamic_build

from pebs.benchmark import evaluation, performance


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from pebs import config
    from pebs import server as server_mod

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    server_mod._engines.clear()
    return TestClient(server_mod.app)


def _valid_payload(**overrides):
    payload = {
        "reviewer": "张老师",
        "role": "teacher",
        "scores": {
            "subject_accuracy": 4,
            "teaching_logic": 4,
            "goal_clarity": 5,
            "content_alignment": 4,
            "concept_clarity": 4,
            "case_quality": 3,
            "executability": 4,
            "student_engagement": 3,
            "cognitive_challenge": 4,
            "assessment_design": 3,
            "language_naturalness": 4,
            "visual_necessity": 4,
            "coherence": 4,
            "teacher_usability": 4,
        },
        "comment": "整体可用，案例需要更贴近本园情境。",
        "must_fix": ["8.2 案例中的机构名是虚构的"],
        "nice_to_have": ["补一张概念对比图"],
        "edits": {
            "generated_text": "一二三四五六七八九十",
            "edited_text": "一二三四五六七八九十十一十二十三",
            "items": [
                {"category": "case replacement", "severity": "S3"},
                {"category": "tone edit", "severity": "S1"},
            ],
        },
        "evidence_errors": 1,
        "routing_errors": 0,
        "plan_errors": 0,
    }
    payload.update(overrides)
    return payload


def test_rubric_validation_requires_reviewer_scores_and_comment():
    errors = evaluation.validate_eval({"scores": {}, "comment": ""})
    assert any("reviewer" in error for error in errors)
    assert any("scores" in error for error in errors)
    assert any("comment" in error for error in errors)
    bad = _valid_payload(scores={"subject_accuracy": 9})
    assert any("超出 1–5" in error for error in evaluation.validate_eval(bad))
    bad_dimension = _valid_payload(scores={"unknown_dim": 3})
    assert any("未知评分维度" in error for error in evaluation.validate_eval(bad_dimension))
    assert evaluation.validate_eval(_valid_payload()) == []


def test_human_eval_is_recorded_as_artifact_and_updates_performance(engine, registry_env):
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    engine.accept(start["changeset_id"])
    from pebs.benchmark import trace as trace_mod

    skill_trace = trace_mod.build_trace(engine, start["run_id"])
    content = evaluation.record(engine, _valid_payload(), run_id=start["run_id"], mode="dynamic")
    assert content["overall"] == pytest.approx(3.857, abs=0.01)
    assert content["edit_ratio"] > 0
    assert content["edit_severities"] == {"S3": 1, "S1": 1}
    assert evaluation.latest(engine)["reviewer"] == "张老师"

    evaluation.update_performance(engine, skill_trace, content)
    performance_data = performance.load_performance()
    script_writer = performance_data["skills"].get("script-writer")
    assert script_writer, "performance registry 必须记录被评分的 skill"
    assert script_writer["runs"] >= 1
    assert script_writer["human_score"] is not None

    promoted = performance.promotion_decision(script_writer)
    assert promoted["eligible"] in (True, False)


def test_evaluation_endpoints_expose_trace_and_accept_scores(client):
    client.post("/api/projects", json={"project_id": "evaltest"})
    evaluation_payload = _valid_payload()
    res = client.post("/api/projects/evaltest/evaluation", json=evaluation_payload)
    assert res.status_code == 200, res.text
    assert res.json()["reviewer"] == "张老师"

    invalid = client.post("/api/projects/evaltest/evaluation", json={"reviewer": "", "scores": {}, "comment": ""})
    assert invalid.status_code == 409

    data = client.get("/api/projects/evaltest/evaluation").json()
    assert data["human_eval"]["reviewer"] == "张老师"
    assert "trace" in data and "performance" in data and "comparison" in data
