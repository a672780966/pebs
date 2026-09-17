from __future__ import annotations

from conftest import REQUEST_1, make_skill_package, run_dynamic_build

from pebs import skills_mgr


def _install(registry_env, name: str):
    archive = make_skill_package(
        registry_env,
        name,
        produces=["teaching_plan"],
        requires=["learning_design"],
        artifact_ids={"teaching_plan": "teaching_plan:{section_id}"},
        skill_md="# 外部教学计划 Skill\n\n只消费学习设计，输出 strategies 与 pck_notes。",
    )
    skills_mgr.import_candidate(f"file:///{archive}", name=name, commit_sha="ctx-1")
    skills_mgr.review(name, "IN_REVIEW", reviewer="tester")
    skills_mgr.review(name, "APPROVED", reviewer="tester", evidence="上下文最小化测试包")
    skills_mgr.publish(name)
    return name


def test_external_skill_prompt_is_minimal_and_pii_free(registry_env, engine, tmp_path):
    name = _install(registry_env, "ext-ctx")
    material = tmp_path / "家长联系表.txt"
    material.write_text("学生：张三 学号：20230001 家长李四 手机 13800138000", encoding="utf-8")

    start, status = run_dynamic_build(engine, REQUEST_1, material_paths=[material])
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]

    external_prompts = [prompt for prompt in engine.llm.prompts if "外部教学计划 Skill" in prompt]
    assert external_prompts, "external skill should have been invoked"
    prompt = external_prompts[0]
    assert '"learning_design"' in prompt
    for forbidden in ('"materials"', '"script"', '"claims_set"', '"diagram"', '"teaching_plan"'):
        assert forbidden not in prompt, f"undeclared artifact leaked into prompt: {forbidden}"
    assert "张三" not in prompt
    assert "13800138000" not in prompt

    step = next(item for item in status["steps"] if item["step_id"] == name)
    assert "learning_design" in (step["note"] or "")
    assert "materials" not in (step["note"] or "")


def test_builtin_skill_prompts_also_exclude_sensitive_materials(engine, tmp_path):
    from conftest import run_build

    material = tmp_path / "学生名单.txt"
    material.write_text("姓名：王五 学号：20239999", encoding="utf-8")
    run_id, changeset_id = run_build(engine, REQUEST_1, material_paths=[material])
    assert engine.llm.prompts
    assert all("王五" not in prompt and "20239999" not in prompt for prompt in engine.llm.prompts)
    materials = engine.store.get_revision(engine.store.revisions_of("materials")[-1])["content"]
    assert materials["files"][0]["sensitive"] is True
