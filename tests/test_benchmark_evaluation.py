"""M6 §30–§34 / §62：人工评价入口（rubric 校验 + Artifact 落库 + performance 绑定）。"""

from __future__ import annotations

pytestmark = __import__('pytest').mark.benchmark_smoke

import pytest
from conftest import REQUEST_1, FakeLLM, run_build, run_dynamic_build

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


def test_performance_records_skill_versions_from_trace(registry_env):
    from pebs.benchmark import performance

    trace = {
        "skills": [
            {
                "skill": "dual-coding-designer",
                "version": "6bbbce418f82",
                "upstream_sha": "6bbbce418f82e11044009c9f3b7373a354de5bd0",
                "package_sha256": "pkg-1",
                "patch": "dual-coding-pebs-1",
                "domain": "media",
                "status": "SUCCEEDED",
            },
            {
                "skill": "hinge-question-designer",
                "version": "6bbbce418f82",
                "status": "FAILED",
                "error": "外部 Skill 输出两次均未通过 Schema 校验",
            },
        ]
    }
    records = performance.record_trace(trace)
    assert len(records) == 2
    data = performance.load_performance()
    dual = data["skills"]["dual-coding-designer"]
    assert dual["runs"] == 1
    assert dual["success_rate"] == 1.0
    assert dual["provider_sha"].startswith("6bbbce41")
    assert dual["patch"] == "dual-coding-pebs-1"
    hinge = data["skills"]["hinge-question-designer"]
    assert hinge["schema_failure_rate"] == 1.0
    assert hinge["known_failure_modes"]


def test_human_eval_worksheet_round_trip(tmp_path):
    from pebs.benchmark import report as report_mod

    run = {
        "case_id": "A",
        "mode": "dynamic",
        "run_id": "run_demo",
        "run_status": "succeeded",
        "artifact_hashes": {"script:sec1": "abc"},
        "evidence_policy": ["SUPPORTED"],
    }
    written = report_mod.write_worksheets([run], directory=tmp_path / "worksheets")
    assert len(written) == 1
    payload = report_mod.load_worksheet(written[0])
    assert payload["reviewer"] == ""
    assert payload["scores"] == {}, "未填写的维度不应进入 payload"
    errors = evaluation.validate_eval(payload)
    assert any("reviewer" in error for error in errors)
    assert any("scores" in error for error in errors)
    assert any("comment" in error for error in errors)

    import yaml

    data = yaml.safe_load(written[0].read_text(encoding="utf-8"))
    data["reviewer"] = "李老师"
    data["comment"] = "结构清楚，案例需要更贴近本校情境。"
    data["scores"] = {key: 4 for key in data["scores"]}
    data["edits"]["items"] = [{"category": "case replacement", "severity": "S3"}]
    written[0].write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    filled = report_mod.load_worksheet(written[0])
    assert evaluation.validate_eval(filled) == []
    assert filled["run_id"] == "run_demo"


def test_trace_resolves_pipeline_steps_to_registry_skills(engine, registry_env):
    """§40：静态模式的 step id 必须解析回 Skill 名，不能用步骤标题当 skill。"""
    engine.llm = FakeLLM()
    run_id, changeset_id = run_build(engine, REQUEST_1)
    from pebs.benchmark import trace as trace_mod

    skill_trace = trace_mod.build_trace(engine, run_id)
    names = {entry["skill"] for entry in skill_trace["skills"]}
    assert "docx-exporter" in names, names
    assert "preview-builder" in names, names
    assert all(" " not in name for name in names), names
    unresolved = [name for name in names if name.startswith("step:")]
    assert not unresolved, unresolved
    # §39：Trace 需要 per-skill 时长与调用结果，便于定位慢步骤与失败模式
    for entry in skill_trace["skills"]:
        assert "duration" in entry
        assert entry["status"] in ("SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED", "PENDING", "RUNNING")
    succeeded = [entry for entry in skill_trace["skills"] if entry["status"] == "SUCCEEDED"]
    assert any(entry["duration"] is not None for entry in succeeded), "已完成的步骤应记录时长"


def test_engine_build_trace_records_performance(engine, registry_env):
    """真实 Trace（FakeLLM 构建）写入 performance registry：绑定版本/provider/patch。"""
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["step"], step.get("error")) for step in status["steps"]
    ]
    from pebs.benchmark import performance, trace as trace_mod

    skill_trace = trace_mod.build_trace(engine, start["run_id"])
    recorded = performance.record_trace(skill_trace)
    assert recorded, "Trace 中的 skill 必须全部落库"
    data = performance.load_performance()
    assert data["skills"]
    assert all(item["runs"] >= 1 for item in data["skills"].values())
    assert all(item["last_verified"] for item in data["skills"].values())


def test_benchmark_report_renders_status_and_issues():
    from pebs.benchmark import report as report_mod

    record = {
        "case_id": "A",
        "mode": "dynamic",
        "run_id": "run_x",
        "run_status": "succeeded",
        "metrics": {"model_calls": 22, "wall_time_seconds": 770.7},
        "automatic_issues": {"issues": [{"kind": "SAFETY", "detail": "x"}]},
        "evidence_policy": ["SUPPORTED"],
    }
    summary = report_mod.summarize([record])
    markdown = report_mod.render_markdown(summary)
    assert "| A | dynamic | succeeded |" in markdown
    assert "22" in markdown and "770.7" in markdown


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
