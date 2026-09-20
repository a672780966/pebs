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
    content = evaluation.record(engine, _valid_payload(), run_id=start["run_id"], mode="dynamic")
    assert content["overall"] == pytest.approx(3.857, abs=0.01)
    assert content["edit_ratio"] > 0
    assert content["edit_severities"] == {"S3": 1, "S1": 1}
    assert evaluation.latest(engine)["reviewer"] == "张老师"

    # §40：record() 自身就必须把评分绑定到 skill 版本（真实提交路径不做第二次手动调用）
    performance_data = performance.load_performance()
    script_writer = performance_data["skills"].get("script-writer")
    assert script_writer, "performance registry 必须记录被评分的 skill"
    assert script_writer["runs"] >= 1
    assert script_writer["human_score"] is not None
    assert script_writer["teacher_edit_ratio"] is not None

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


def test_worksheets_are_only_written_for_runs_that_produced_a_course(tmp_path):
    """§30/§32：失败且无产物的 run 不生成评分表（否则诱导教师给不存在的课程打分）。"""
    from pebs.benchmark import report as report_mod

    runs = [
        {"case_id": "B", "mode": "builtin", "run_id": "r_failed", "run_status": "failed"},
        {
            "case_id": "B",
            "mode": "builtin",
            "run_id": "r_blocked",
            "run_status": "blocked",
            "artifact_hashes": {"x": "h"},  # 有 2 个系统产物也不算完成课程
        },
    ]
    assert report_mod.write_worksheets(runs, directory=tmp_path) == []
    assert not list(tmp_path.glob("*-human_eval.yaml"))

    ok = {
        "case_id": "B",
        "mode": "dynamic",
        "run_id": "r_ok",
        "run_status": "succeeded",
        "artifact_hashes": {"lesson_plan:sec1": "h"},
    }
    written = report_mod.write_worksheets([ok], directory=tmp_path)
    assert [p.name for p in written] == ["B-dynamic-human_eval.yaml"]


def test_worksheet_regeneration_never_overwrites_teacher_scores(tmp_path):
    """§30–§32：教师评分是不可再生的外部输入，重新生成报告不得清空已填工作表。"""
    import yaml

    from pebs.benchmark import report as report_mod

    run = {
        "case_id": "C",
        "mode": "dynamic",
        "run_id": "run_1",
        "run_status": "succeeded",
        "artifact_hashes": {"script:sec1": "h"},
    }
    report_mod.write_worksheets([run], directory=tmp_path)
    path = tmp_path / "C-dynamic-human_eval.yaml"
    filled = yaml.safe_load(path.read_text(encoding="utf-8"))
    filled["reviewer"] = "张老师"
    filled["scores"]["subject_accuracy"] = 5
    filled["comment"] = "案例贴合托育场景"
    path.write_text(yaml.safe_dump(filled, allow_unicode=True, sort_keys=False), encoding="utf-8")

    report_mod.write_worksheets(
        [{**run, "run_id": "run_2", "artifact_hashes": {"script:sec1": "h2"}}],
        directory=tmp_path,
    )
    kept = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert kept["reviewer"] == "张老师"
    assert kept["scores"]["subject_accuracy"] == 5
    assert kept["run"]["run_id"] == "run_1"

    # 空白工作表仍然要刷新到最新 run（否则教师会评错产物）
    report_mod.write_worksheets([{**run, "run_id": "run_2"}], directory=tmp_path)
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["run"]["run_id"] == "run_1"
    blank = tmp_path / "D-dynamic-human_eval.yaml"
    assert not blank.exists()
    report_mod.write_worksheets(
        [
            {
                "case_id": "D",
                "mode": "dynamic",
                "run_id": "run_9",
                "run_status": "succeeded",
                "artifact_hashes": {"script:sec1": "h"},
            }
        ],
        directory=tmp_path,
    )
    assert yaml.safe_load(blank.read_text(encoding="utf-8"))["run"]["run_id"] == "run_9"


def test_representative_run_uses_run_timestamp_not_file_mtime(tmp_path, monkeypatch):
    """§41：复评工具会重写旧 run.json，代表 run 不能因此漂移。"""
    import json
    import os
    import time

    from pebs.benchmark import cases
    from pebs.benchmark import report as report_mod

    runs = tmp_path / "runs"
    for stamp, run_id in (("20260101-000000", "run_old"), ("20260102-000000", "run_new")):
        target = runs / f"{stamp}-A-dynamic"
        target.mkdir(parents=True)
        (target / "run.json").write_text(
            json.dumps({"case_id": "A", "mode": "dynamic", "run_id": run_id, "run_status": "succeeded"}),
            encoding="utf-8",
        )
    os.utime(runs / "20260101-000000-A-dynamic" / "run.json", (time.time() + 60, time.time() + 60))
    monkeypatch.setattr(cases, "runs_dir", lambda: runs)

    reps = report_mod.load_runs()
    assert len(reps) == 1
    assert reps[0]["run_id"] == "run_new"
    assert reps[0]["_attempts"] == 2 and reps[0]["_succeeded"] == 2


def test_run_json_with_utf8_bom_is_still_loaded(tmp_path, monkeypatch):
    """§41：带 BOM 的 run.json 曾让该 run 从报告里静默消失（Windows 写入常见）。"""
    import json

    from pebs.benchmark import cases
    from pebs.benchmark import report as report_mod

    runs = tmp_path / "runs"
    target = runs / "20260101-000000-A-dynamic"
    target.mkdir(parents=True)
    payload = json.dumps({"case_id": "A", "mode": "dynamic", "run_id": "run_bom", "run_status": "succeeded"})
    (target / "run.json").write_text(payload, encoding="utf-8-sig")
    monkeypatch.setattr(cases, "runs_dir", lambda: runs)

    reps = report_mod.load_runs()
    assert [rep["run_id"] for rep in reps] == ["run_bom"]


def test_report_reads_teacher_scores_back_from_the_project(engine, registry_env, tmp_path, monkeypatch):
    """§30/§33/§42：教师评分落在项目 Store，报告必须读回来（否则指标列永远为空）。"""
    from pebs import config
    from pebs.benchmark import evaluation, report as report_mod

    # 报告按 config.project_dir(project_id) 找 Store，这里让二者指向同一目录
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    engine.project_id = "proj"
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    engine.accept(start["changeset_id"])
    evaluation.record(engine, _valid_payload(), run_id=start["run_id"], mode="dynamic")

    run = {
        "case_id": "A",
        "mode": "dynamic",
        "run_id": start["run_id"],
        "run_status": "succeeded",
        "project_id": "proj",
        "metrics": {"model_calls": 7},
    }
    summary = report_mod.summarize([run])
    entry = summary["cases"][0]["dynamic"]
    assert entry["human_score"] == pytest.approx(3.857, abs=0.01)
    assert entry["edit_ratio"] and entry["edit_ratio"] > 0
    assert entry["evidence_errors"] == 1
    assert entry["reviewers"] == ["张老师"]
    assert entry["human_eval_stale"] is False
    markdown = report_mod.render_markdown(summary)
    assert "3.857" in markdown

    # 评分指向另一版产物时必须标 stale，而不是静默丢弃
    stale = dict(run, run_id="run_other")
    stale_summary = report_mod.summarize([stale])
    assert stale_summary["cases"][0]["dynamic"]["human_eval_stale"] is True
    assert stale_summary["cases"][0]["dynamic"]["human_score"] is None


def test_trace_carries_selection_trace_for_the_ui(engine, registry_env):
    """§63：Evaluation Tab 的高级模式要显示"为什么选它/为什么拒绝别的"，trace 必须带上。"""
    from pebs.benchmark import trace as trace_mod

    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    skill_trace = trace_mod.build_trace(engine, start["run_id"])
    selection = skill_trace["plan"]["selection_trace"]
    assert selection, "trace.plan.selection_trace 不能为空"
    assert all(entry["selected"] and entry["reason"] for entry in selection)
    contested = [entry for entry in selection if entry["rejected_candidates"]]
    assert contested, "至少有一个产物类型存在多个候选 Skill，才谈得上选择理由"
    assert contested[0]["rejected_candidates"][0]["rejected_because"]


def test_trace_records_per_skill_inputs_outputs_and_model_calls(engine, registry_env):
    """§39：Skill Trace 的每项必须带 input_artifacts / output_artifacts / model_calls。

    这些值由执行器在节点前后取快照写入 steps 表（内置/外部/沙箱三条路径通用），
    旧数据的回退路径只能给出 artifact_id 且会重复。
    """
    from pebs.benchmark import trace as trace_mod

    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    skill_trace = trace_mod.build_trace(engine, start["run_id"])
    by_skill = {item["skill"]: item for item in skill_trace["skills"]}

    designer = by_skill["learning-designer"]
    assert "requirements" in designer["input_artifacts"], designer["input_artifacts"]
    assert any(item.startswith("learning_design") for item in designer["output_artifacts"])
    # 去重：同一产物多个 revision 只算一次
    assert len(designer["output_artifacts"]) == len(set(designer["output_artifacts"]))

    writer = by_skill["script-writer"]
    assert "teaching_plan" in {item.split(":", 1)[0] for item in writer["input_artifacts"]}
    assert writer["model_calls"] > 0, "script-writer 至少调用一次模型"

    total = sum(int(item.get("model_calls") or 0) for item in skill_trace["skills"])
    assert total == int(engine.store.get_run(start["run_id"])["calls_used"]), (
        "per-skill model_calls 之和必须等于 run 的 calls_used"
    )

    # §19：per-skill 调用量/耗时必须真的写进 performance registry（否则该字段恒为 0）
    performance.record_trace(
        skill_trace,
        latency_by_skill={item["skill"]: float(item.get("duration") or 0.0) for item in skill_trace["skills"]},
        model_calls_by_skill={item["skill"]: int(item.get("model_calls") or 0) for item in skill_trace["skills"]},
    )
    record = performance.load_performance()["skills"]["script-writer"]
    assert record["average_model_calls"] > 0
    assert record["average_latency"] >= 0


def test_evaluation_kit_includes_the_direct_baseline_output(tmp_path):
    """§28：Direct 基线没有项目 Store，但它的产物必须进入教师材料包（否则对比缺一条腿）。"""
    from pebs.benchmark import evaluation as eval_mod

    run_dir = tmp_path / "20260101-A-direct_codex"
    run_dir.mkdir(parents=True)
    (run_dir / "direct_output.md").write_text("# 直接生成的教学内容\n\n这是 baseline 输出。", encoding="utf-8")
    run = {
        "case_id": "A",
        "mode": "direct_codex",
        "_variant": "direct_codex",
        "run_id": "",
        "run_status": "succeeded",
        "project_id": "bench-a-direct_codex-does-not-exist",
        "run_dir": str(run_dir),
        "metrics": {"model_calls": 1},
    }
    exported = eval_mod.export_kit([run], directory=tmp_path / "kit")
    assert exported and exported[0]["variant"] == "direct_codex"
    course = (tmp_path / "kit" / "A-direct_codex" / "course.md").read_text(encoding="utf-8")
    assert "direct_output.md" in course
    assert "这是 baseline 输出" in course


def test_evaluation_kit_shows_gates_and_automatic_issues(engine, registry_env, tmp_path, monkeypatch):
    """§30–§32：教师材料包必须包含门禁结论与自动命中问题（教师据此确认/推翻系统判断）。"""
    from pebs import config
    from pebs.benchmark import evaluation as eval_mod

    # export_kit 按 config.project_dir(project_id) 打开 Store：让它指向本测试引擎的实际目录，
    # 且 project_id 必须与 Store 构造时的一致（list_artifacts 按 project_id 过滤）
    monkeypatch.setattr(config, "project_dir", lambda pid: engine.base)
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    engine.accept(start["changeset_id"])

    run = {
        "case_id": "C",
        "mode": "dynamic",
        "variant": "dynamic",
        "_variant": "dynamic",
        "run_id": start["run_id"],
        "run_status": "succeeded",
        "project_id": engine.project_id,
        "artifact_hashes": {"script:sec1": "h"},
        "metrics": {"model_calls": 7, "research_calls": 0},
        "automatic_issues": {
            "issues": [{"kind": "SAFETY", "detail": "脚本命中禁用表达：x"}],
            "counts": {"SAFETY": 1},
        },
    }
    exported = eval_mod.export_kit([run], directory=tmp_path)
    assert exported, "材料包必须导出"
    assert eval_mod._gate_lines(engine.store), "该 run 必须有门禁结论可展示"
    course = (tmp_path / "C-dynamic" / "course.md").read_text(encoding="utf-8")
    assert "自动检查命中的问题" in course
    assert "SAFETY" in course
    assert "门禁结论" in course
    assert "script:sec1" in course


def test_evaluation_endpoints_expose_trace_and_accept_scores(client):
    client.post("/api/projects", json={"project_id": "evaltest"})
    evaluation_payload = _valid_payload()
    res = client.post("/api/projects/evaltest/evaluation", json=evaluation_payload)
    assert res.status_code == 200, res.text
    assert res.json()["reviewer"] == evaluation_payload["reviewer"]

    invalid = client.post("/api/projects/evaltest/evaluation", json={"reviewer": "", "scores": {}, "comment": ""})
    assert invalid.status_code == 409

    data = client.get("/api/projects/evaltest/evaluation").json()
    assert data["human_eval"]["reviewer"] == evaluation_payload["reviewer"]
    assert "trace" in data and "performance" in data and "comparison" in data


def test_evaluation_payload_exposes_benchmark_run_issues(client, tmp_path, monkeypatch):
    """§62/§63：Evaluation Tab 必须能看到该项目的 benchmark run 与自动问题清单。"""
    import json

    from pebs.benchmark import cases

    runs = tmp_path / "runs"
    (runs / "20260101-A-dynamic").mkdir(parents=True)
    (runs / "20260101-A-dynamic" / "run.json").write_text(
        json.dumps(
            {
                "case_id": "A",
                "mode": "dynamic",
                "_variant": "dynamic",
                "project_id": "evalbench",
                "run_status": "succeeded",
                "evidence_policy": ["SUPPORTED"],
                "quality_metrics": {"language": {"per_1000_chars": 0.99}, "ppt": {"dense_ratio": 0.0}},
                "automatic_issues": {
                    "issues": [{"kind": "SAFETY", "severity": "S2", "detail": "不应贴标签", "artifact": "script_1"}]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cases, "runs_dir", lambda: runs)

    client.post("/api/projects", json={"project_id": "evalbench"})
    data = client.get("/api/projects/evalbench/evaluation").json()
    assert data["benchmark_run"]["case_id"] == "A"
    assert data["benchmark_run"]["issues"][0]["kind"] == "SAFETY"
    assert data["benchmark_run"]["quality_metrics"]["language"]["per_1000_chars"] == 0.99

    other = client.get("/api/projects/evaltest/evaluation").json()
    assert other["benchmark_run"] is None
