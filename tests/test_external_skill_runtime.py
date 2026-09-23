from __future__ import annotations

import pytest
from conftest import REQUEST_1, FakeLLM, make_skill_package, run_dynamic_build

from pebs import provider_edu, skills_mgr
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
        # §7 生命周期与 provider_edu 生产入口一致：allowlist → enable
        provider_edu.add_to_allowlist(name)
        skills_mgr.enable(name, True)
    return name


def _select_explicitly(engine, request: str, name: str) -> str:
    """§43 Explicit User Choice：外部 Skill 只能显式选择，不靠自动偏好进入。

    permissions 要在这之后再构造——它在构造时读 allowlist.json（§7 顺序）。
    """
    from pebs.permissions import PermissionManager

    engine.permissions = PermissionManager()
    return f"{request} /{name}"


@pytest.fixture(autouse=True)
def _skip_sandbox_probe(monkeypatch):
    """导入的 Skill 默认 execution_policy=SANDBOX_ONLY，权限闸门会走 sandbox.available()。

    临时 registry 下探测缓存是冷的，probe_all 在本机要 ~25s；本文件只有沙滩用例
    关心沙箱，其余一律按“有可用适配器”处理（见 test_sandbox_...  自行改回 False）。
    """
    from pebs import sandbox

    monkeypatch.setattr(sandbox, "available", lambda refresh=False: True)
    return True


def test_approved_pinned_external_skill_enters_resolver_without_pipeline_change(registry_env, engine):
    name = _install(registry_env, registry_env, "ext-plan")
    candidates = resolver.candidates("teaching_plan")
    assert name in {item["name"] for item in candidates}
    chosen = resolver.choose("teaching_plan", prefer=[name])
    assert chosen["name"] == name

    from pebs.engine import _pinned_skill_names

    assert name not in _pinned_skill_names(), "§18：外部 Skill 不得靠 pin 进入自动偏好"
    start, status = run_dynamic_build(engine, _select_explicitly(engine, REQUEST_1, name))
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
    start, status = run_dynamic_build(engine, _select_explicitly(engine, REQUEST_1, name))
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    joined = "\n".join(engine.llm.prompts)
    assert "canonical schema" in joined
    assert "strategies" in joined, "canonical teaching_plan 字段应出现在 prompt 中"
    assert "pck_notes" in joined


def test_section_scoped_external_skill_is_called_per_section(registry_env, engine):
    """M6：分节产物必须分节调用，各节内容不得相同（§17 A/B 发现的问题）。"""
    from conftest import REQUEST_2, run_dynamic_build

    name = _install(registry_env, registry_env, "ext-per-section-plan")
    engine.llm = FakeLLM(
        external_skill_payloads=[
            {"strategies": [{"goal_ref": "g1", "knowledge_type": "concept", "strategy": "explicit-instruction", "rationale": "sec1"}], "pck_notes": ["sec1 的教学说明"]},
            {"strategies": [{"goal_ref": "g1", "knowledge_type": "concept", "strategy": "explicit-instruction", "rationale": "sec2"}], "pck_notes": ["sec2 的教学说明"]},
        ]
    )
    start, status = run_dynamic_build(engine, _select_explicitly(engine, REQUEST_2, name))
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    requirements = engine.store.get_revision(engine.store.revisions_of("requirements")[-1])["content"]
    section_ids = [section["section_id"] for section in requirements["sections"]]
    assert len(section_ids) >= 2
    notes = {}
    for section_id in section_ids:
        revisions = engine.store.revisions_of(f"teaching_plan:{section_id}")
        assert revisions, f"{section_id} 应由外部 Skill 产出"
        notes[section_id] = engine.store.get_revision(revisions[-1])["content"].get("pck_notes")
    assert notes[section_ids[0]] != notes[section_ids[1]], notes
    assert notes[section_ids[0]] == ["sec1 的教学说明"]
    assert notes[section_ids[1]] == ["sec2 的教学说明"]
    # 每次外部调用都计入预算（§31/§35）
    assert engine.store.get_run(start["run_id"])["calls_used"] > 0


def test_unapproved_external_skill_is_not_selectable(registry_env, engine):
    name = _install(registry_env, registry_env, "ext-unapproved-plan", approve=False)
    names = {item["name"] for item in resolver.candidates("teaching_plan")}
    assert name not in names
    chosen = resolver.choose("teaching_plan", prefer=[name])
    assert chosen["name"] != name


def test_approved_external_skill_is_not_preferred_without_explicit_choice(registry_env):
    """M6 §18：默认不假设外部 Skill 更好；命名 A/B 的自动选择必须落在 Builtin。"""
    from pebs import registry
    from pebs.engine import _pinned_skill_names

    pairs = (
        ("learning_design", "learning-designer", "backwards-design-unit-planner"),
        ("assessment", "assessment-designer", "hinge-question-designer"),
        ("media_plan", "media-router", "dual-coding-designer"),
    )
    for artifact, builtin, external in pairs:
        builtin_record = registry.get(builtin)
        external_record = registry.get(external)
        assert builtin_record is not None and external_record is not None
        assert builtin_record.get("self_implemented") is True
        assert external_record.get("self_implemented") is not True
        assert external_record.get("status") == "APPROVED"
        assert external not in _pinned_skill_names()
        assert resolver.choose(artifact)["name"] == builtin


def test_pinned_builtin_using_default_provider_remains_auto_pinnable(monkeypatch):
    """自动偏好排除的是外部来源，而不是执行 provider 标注。

    内置记录可能标注 default-llm；若将来 pin 住，这类 Builtin 仍应可自动偏好，
    而外部导入的 Skill 绝不能仅凭 pin 进入自动偏好——包括通用导入路径把 provider
    落成 [] 的那种（derive_contract 对未声明 provider 的上游即如此）。
    """
    from pebs import registry
    from pebs.engine import _pinned_skill_names

    monkeypatch.setattr(
        registry,
        "load_skills",
        lambda: {
            "builtin-plan": {
                "status": "APPROVED",
                "pinned_version": "builtin-v1",
                "provider": ["default-llm"],
                "self_implemented": True,
            },
            "builtin-legacy-plan": {
                "status": "APPROVED",
                "pinned_version": "builtin-v0",
                "provider": "default-llm",
                "self_implemented": True,
            },
            "external-plan": {
                "status": "APPROVED",
                "pinned_version": "6bbbce418f82e11044009c9f3b7373a354de5bd0",
                "provider": ["education-agent-skills"],
                "self_implemented": False,
            },
            "external-legacy-plan": {
                "status": "APPROVED",
                "pinned_version": "6bbbce418f82e11044009c9f3b7373a354de5bd0",
                "provider": "education-agent-skills",
                "self_implemented": False,
            },
            # 通用导入（skills_mgr.derive_contract）：上游未声明 provider 时为 []，
            # 只有 self_implemented 还能表明它来自外部。
            "imported-external-plan": {
                "status": "APPROVED",
                "pinned_version": "6bbbce418f82e11044009c9f3b7373a354de5bd0",
                "provider": [],
                "self_implemented": False,
            },
            # 来源标志缺失：按外部处理，宁可漏一次自动偏好。
            "unflagged-plan": {
                "status": "APPROVED",
                "pinned_version": "mystery-v1",
                "provider": [],
            },
        },
    )
    assert _pinned_skill_names() == ["builtin-legacy-plan", "builtin-plan"]


def test_sandbox_external_skill_blocks_without_verified_adapter(registry_env, engine, monkeypatch):
    """M6：没有验证通过的沙箱适配器时，SANDBOX_ONLY 外部 Skill 连启动都不允许。

    沙箱不可用时，权限闸门先于执行闸门生效，所以这里断言的是 ExplicitSkillDenied
    而不是 step 级 BLOCKED：两道闸门看的是同一个 sandbox.available()，
    权限闸门更早（run 尚未建立）。
    """
    from pebs import sandbox
    from pebs.engine import ExplicitSkillDenied

    name = _install(registry_env, registry_env, "ext-sandbox-plan", with_scripts=True)
    monkeypatch.setattr(sandbox, "available", lambda refresh=False: False)
    with pytest.raises(ExplicitSkillDenied) as excinfo:
        engine.start_build(_select_explicitly(engine, REQUEST_1, name), planner_mode="dynamic")
    assert "sandbox adapter" in str(excinfo.value)
    assert engine.store.revisions_of("teaching_plan:sec1") == []


def test_external_skill_result_schema_failure_is_failed_not_guessed(registry_env, engine):
    name = _install(registry_env, registry_env, "ext-bad-output")
    engine.llm = FakeLLM(external_skill_payloads=[{"strategies": []}, {"strategies": []}])
    start, status = run_dynamic_build(engine, _select_explicitly(engine, REQUEST_1, name))
    step = next(item for item in status["steps"] if item["step_id"] == name)
    assert step["status"] == "FAILED"
    assert "Schema" in (step["error"] or "")
    assert engine.store.revisions_of("teaching_plan:sec1") == []
