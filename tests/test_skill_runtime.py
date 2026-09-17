from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import FakeLLM, make_skill_package

from pebs import sandbox, skills_mgr
from pebs.runtime import context as context_mod
from pebs.runtime import result as result_mod
from pebs.runtime import skill_loader
from pebs.runtime.prompt_skill import PromptSkillExecutor, SkillExecutionFailed
from pebs.runtime.skill_loader import SkillRuntimeBlocked


def _install_prompt_skill(registry_env, tmp_path, name="ext-teaching-plan", requires=None, inline_schema=None):
    archive = make_skill_package(
        tmp_path,
        name,
        produces=["teaching_plan"],
        requires=requires or ["learning_design"],
        artifact_ids={"teaching_plan": "teaching_plan:{section_id}"},
        skill_md="# 外部教学计划 Skill\n\n根据学习设计生成教学策略。",
        inline_schema=inline_schema,
    )
    skills_mgr.import_candidate(f"file:///{archive}", name=name, commit_sha="ext123")
    skills_mgr.review(name, "IN_REVIEW", reviewer="tester")
    skills_mgr.review(name, "APPROVED", reviewer="tester", evidence="MIT 测试包，逐文件哈希校验")
    record = skills_mgr.publish(name)
    return name, record


def test_import_derives_contract_from_skill_yaml(registry_env, tmp_path):
    name, record = _install_prompt_skill(registry_env, tmp_path)
    assert record["runtime"] == "prompt_skill"
    assert record["requires"] == ["learning_design"]
    assert record["produces"] == ["teaching_plan"]
    assert record["handler"]["artifact_ids"] == {"teaching_plan": "teaching_plan:{section_id}"}
    assert record["status"] == "APPROVED"
    assert record["pinned_version"]


def test_loader_reads_pinned_version_and_guards_references(registry_env, tmp_path):
    name, record = _install_prompt_skill(registry_env, tmp_path)
    loaded = skill_loader.load(name)
    assert loaded.skill_md.startswith("# 外部教学计划 Skill")
    assert loaded.manifest["name"] == name
    assert loaded.version == record["pinned_version"]
    with pytest.raises(SkillRuntimeBlocked):
        loaded.reference("../outside.md")


def test_loader_blocks_unpinned_or_unapproved_skill(registry_env, tmp_path):
    archive = make_skill_package(
        tmp_path, "ext-unapproved", produces=["teaching_plan"], artifact_ids={"teaching_plan": "teaching_plan:{section_id}"}
    )
    skills_mgr.import_candidate(f"file:///{archive}", name="ext-unapproved")
    with pytest.raises(SkillRuntimeBlocked):
        skill_loader.load("ext-unapproved")


def test_result_validation_uses_canonical_and_inline_schema():
    good = {"section_id": "sec1", "strategies": [{"goal_ref": "g1", "knowledge_type": "concept", "strategy": "x", "rationale": "y"}], "pck_notes": ["n"]}
    assert result_mod.validate_result(good, artifact_type="teaching_plan") == []
    bad = {"strategies": []}
    assert result_mod.validate_result(bad, artifact_type="teaching_plan")
    inline = {"type": "object", "required": ["must_have"], "properties": {"must_have": {"type": "string"}}}
    errors = result_mod.validate_result(good, artifact_type="teaching_plan", inline_schema=inline)
    assert any("must_have" in error for error in errors)


def test_context_builder_only_includes_declared_artifacts():
    record = {"name": "ext-teaching-plan", "requires": ["learning_design"], "optional_requires": []}
    context = context_mod.build_context(
        task="t",
        skill_record=record,
        artifacts={
            "learning_design": {"goals": []},
            "script": {"units": []},
            "materials": {"files": [{"text": "学生张三"}]},
            "claims_set": {"claims": []},
        },
        project_rules="规则",
    )
    assert set(context["inputs"].keys()) == {"learning_design"}
    report = context_mod.context_report(context)
    assert report["excluded_count"] == 3
    assert "materials" in report["excluded_samples"]
    assert "学生张三" not in json.dumps(context, ensure_ascii=False)


def test_prompt_executor_repairs_once_then_fails(registry_env, tmp_path):
    name, _ = _install_prompt_skill(registry_env, tmp_path, name="ext-repair")
    llm = FakeLLM(external_skill_payloads=[{"strategies": []}, {"pck_notes": ["n"]}, None])
    executor = PromptSkillExecutor(llm)
    per_section = {
        "command": {"result": {}},
    }
    with pytest.raises(SkillExecutionFailed):
        executor.execute(_FakeCtx(), {"node_id": "ext-repair", "reason": "测试", "outputs": ["teaching_plan"], "inputs": ["learning_design"]}, skill_record=skills_mgr._load_registry()[name])
    assert llm.calls.get("external_skill_repair:ext-repair") == 1


def test_prompt_executor_succeeds_and_reports_context(registry_env, tmp_path):
    name, record = _install_prompt_skill(registry_env, tmp_path, name="ext-ok")
    llm = FakeLLM()
    executor = PromptSkillExecutor(llm)
    node = {"node_id": name, "reason": "生成教学计划", "outputs": ["teaching_plan"], "inputs": ["learning_design"]}
    content = executor.execute(_FakeCtx(), node, skill_record=record)
    assert content["pck_notes"]
    assert node["_context_report"]["included"] == ["learning_design"]
    assert llm.calls.get(f"external_skill:{name}") == 1
    prompt = llm.prompts[-1]
    assert "外部教学计划 Skill" in prompt
    assert "learning_design" in prompt


def test_sandbox_skill_denied_without_verified_adapter(registry_env, tmp_path, monkeypatch):
    archive = make_skill_package(
        tmp_path,
        "ext-sandbox",
        produces=["teaching_plan"],
        requires=["learning_design"],
        artifact_ids={"teaching_plan": "teaching_plan:{section_id}"},
        with_scripts=True,
    )
    skills_mgr.import_candidate(f"file:///{archive}", name="ext-sandbox", commit_sha="sb1")
    record = skills_mgr._load_registry()["ext-sandbox"]
    assert record["runtime"] == "sandbox_skill"
    skills_mgr.review("ext-sandbox", "IN_REVIEW", reviewer="tester")
    skills_mgr.review("ext-sandbox", "APPROVED", reviewer="tester", evidence="已审查脚本仅作测试")
    skills_mgr.publish("ext-sandbox")
    monkeypatch.setattr(sandbox, "available", lambda refresh=False: False)
    from pebs.runtime.sandbox_skill import SandboxSkillExecutor

    with pytest.raises(SkillRuntimeBlocked) as excinfo:
        SandboxSkillExecutor().execute(_FakeCtx(), {"node_id": "ext-sandbox"}, skill_record=skills_mgr._load_registry()["ext-sandbox"])
    assert "沙箱" in str(excinfo.value)


class _FakeCtx:
    def __init__(self):
        self.store = None
        self.project_rules = ""
        self._design = {
            "section_id": "sec1",
            "goals": [{"goal_id": "g1", "knowledge_type": "concept"}],
            "difficulties": [],
            "assessment_evidence": [],
            "sequence": [],
        }

    def sections(self):
        return [{"section_id": "sec1", "title": "测试节"}]

    def artifact_ids_of_type(self, artifact_type):
        return ["learning_design:sec1"] if artifact_type == "learning_design" else []

    def content(self, artifact_id):
        if artifact_id == "learning_design:sec1":
            return self._design
        return None
