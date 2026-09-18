from __future__ import annotations

import pytest
from conftest import REQUEST_1, FakeLLM, make_skill_package, run_dynamic_build

from pebs import skills_mgr
from pebs.planner import resolver


def _install(registry_env, tmp_path, name: str, *, with_scripts: bool = False, approve: bool = True):
    archive = make_skill_package(
        tmp_path,
        name,
        produces=["teaching_plan"],
        requires=["learning_design"],
        artifact_ids={"teaching_plan": "teaching_plan:{section_id}"},
        with_scripts=with_scripts,
        skill_md="# 外部教学计划 Skill\n\n只输出 JSON：strategies 与 pck_notes。",
    )
    skills_mgr.import_candidate(f"file:///{archive}", name=name, commit_sha="ext-abc")
    if approve:
        skills_mgr.review(name, "IN_REVIEW", reviewer="tester")
        skills_mgr.review(name, "APPROVED", reviewer="tester", evidence="测试包逐文件哈希 + 人工阅读")
        skills_mgr.publish(name)
    return name


def test_approved_pinned_external_skill_enters_resolver_without_pipeline_change(registry_env, engine):
    name = _install(registry_env, registry_env, "ext-plan")
    candidates = resolver.candidates("teaching_plan")
    assert name in {item["name"] for item in candidates}
    chosen = resolver.choose("teaching_plan", pinned=[name])
    assert chosen["name"] == name

    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    plan = engine.store.accepted_content("build_plan_dynamic")
    node = next(item for item in plan["nodes"] if item["skill"] == name)
    assert node["inputs"] == ["learning_design"]
    step = next(item for item in status["steps"] if item["step_id"] == name)
    assert step["status"] == "SUCCEEDED"
    assert "外部 Skill 执行" in (step["note"] or "")
    teaching_plan = engine.store.get_revision(engine.store.revisions_of("teaching_plan:sec1")[-1])["content"]
    assert teaching_plan["pck_notes"] == ["外部 Skill 提供的教学说明"]
    assert engine.store.get_run(start["run_id"])["status"] == "succeeded"


def test_external_skill_prompt_includes_the_canonical_schema(registry_env, engine):
    """M6 §22：prompt 必须给出 canonical schema 的必需字段。

    真实运行中，模型因看不到 media_plan 的必需字段（knowledge_function /
    temporal_dependency）而两次校验失败——这是外部 Skill 可靠性的关键修复。
    """
    from conftest import run_dynamic_build

    name = _install(registry_env, registry_env, "ext-schema-plan")
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    joined = "\n".join(engine.llm.prompts)
    assert "canonical schema" in joined
    assert "strategies" in joined, "canonical teaching_plan 字段应出现在 prompt 中"
    assert "pck_notes" in joined


def test_unapproved_external_skill_is_not_selectable(registry_env, engine):
    name = _install(registry_env, registry_env, "ext-unapproved-plan", approve=False)
    names = {item["name"] for item in resolver.candidates("teaching_plan")}
    assert name not in names
    chosen = resolver.choose("teaching_plan", prefer=[name])
    assert chosen["name"] != name


def test_sandbox_external_skill_blocks_without_verified_adapter(registry_env, engine, monkeypatch):
    from pebs import sandbox

    name = _install(registry_env, registry_env, "ext-sandbox-plan", with_scripts=True)
    monkeypatch.setattr(sandbox, "available", lambda refresh=False: False)
    start, status = run_dynamic_build(engine, REQUEST_1)
    step = next(item for item in status["steps"] if item["step_id"] == name)
    assert step["status"] == "BLOCKED"
    assert "沙箱" in (step["error"] or "")
    assert engine.store.revisions_of("teaching_plan:sec1") == []
    assert status["run"]["status"] == "blocked"


def test_external_skill_result_schema_failure_is_failed_not_guessed(registry_env, engine):
    name = _install(registry_env, registry_env, "ext-bad-output")
    engine.llm = FakeLLM(external_skill_payloads=[{"strategies": []}, {"strategies": []}])
    start, status = run_dynamic_build(engine, REQUEST_1)
    step = next(item for item in status["steps"] if item["step_id"] == name)
    assert step["status"] == "FAILED"
    assert "Schema" in (step["error"] or "")
    assert engine.store.revisions_of("teaching_plan:sec1") == []
