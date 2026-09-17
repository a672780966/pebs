"""M6 §15：External Skill Acceptance Test。

两类覆盖：
1. 合成 provider（hermetic，CI 必跑）：证明 Provider 适配器与完整生命周期可用，
   且未执行任何上游文件、未引入网络/文件系统访问。
2. 真实 provider（本地已安装时）：逐个验收 14 个教育 Skill 的契约、pin、补丁与加载。
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
import yaml
from conftest import REQUEST_1, FakeLLM, run_dynamic_build

from pebs import config, provider_edu, registry, skills_mgr
from pebs.agents import AgentContractError, IsolationViolation, RestrictedContext
from pebs.planner import resolver
from pebs.runtime import skill_loader

REAL_SKILLS = (
    "backwards-design-unit-planner",
    "learning-progression-builder",
    "discipline-specific-critical-thinking-task-designer",
    "cognitive-load-analyser",
    "dual-coding-designer",
    "worked-example-fading-designer",
    "explicit-instruction-sequence-builder",
    "experiential-learning-cycle-designer",
    "hinge-question-designer",
    "checking-for-understanding-protocol-designer",
    "criterion-referenced-rubric-generator",
    "udl-barrier-anticipator",
    "udl-options-designer",
    "udl-lesson-auditor",
)

PATCHED = {
    "cognitive-load-analyser": "cognitive-load-analyser-pebs-1",
    "hinge-question-designer": "hinge-question-designer-pebs-1",
    "udl-barrier-anticipator": "udl-barrier-anticipator-pebs-1",
}


def _synthetic_provider(tmp_path: Path, *, with_scripts: bool = False) -> tuple[dict, Path]:
    """构造一个最小上游仓库（不含真实仓库内容）用于 hermetic 验收。"""
    sha = "a" * 40
    root = tmp_path / "upstream"
    skill_dir = root / "skills" / "assessment" / "synthetic-rubric-designer"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Synthetic rubric designer\n\nDesign a criterion-referenced rubric for the given goals.\n",
        encoding="utf-8",
    )
    if with_scripts:
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "evil.sh").write_text("#!/bin/sh\necho SHOULD-NOT-RUN > pwned.txt\n", encoding="utf-8")
    (root / "LICENSE").write_text("CC BY-SA 4.0 (synthetic fixture)\n", encoding="utf-8")
    manifest = {
        "provider_id": "synthetic-provider",
        "repository": {"url": "https://example.invalid/synthetic", "commit_sha": sha, "license": "CC-BY-SA-4.0"},
        "update_policy": "manual",
        "default_enabled": False,
        "skills": [
            {
                "upstream_name": "synthetic-rubric-designer",
                "local_alias": "synthetic-rubric-designer",
                "status": "PLANNED",
                "patch": "",
                "review": {"source_review": "synthetic", "audit": "synthetic"},
                "contract": {
                    "agent": "qa-agent",
                    "domain": "education",
                    "requires": ["learning_design"],
                    "produces": ["assessment"],
                    "artifact_ids": {"assessment": "assessment:{section_id}"},
                    "risk_level": "low",
                    "estimated_model_calls": 1,
                },
            }
        ],
    }
    return manifest, root


def test_synthetic_provider_runs_full_lifecycle(registry_env, tmp_path):
    manifest, root = _synthetic_provider(tmp_path)
    results = provider_edu.install(provider=manifest, root=root)
    assert len(results) == 1
    info = results[0]
    assert info["status"] == "APPROVED"
    assert info["runtime"] == "prompt_skill"
    assert info["pinned_version"] == "a" * 40
    assert info["produces"] == ["assessment"]

    verification = provider_edu.verify(provider=manifest)
    assert verification["ok"] is True

    loaded = skill_loader.load("synthetic-rubric-designer")
    assert "criterion-referenced rubric" in loaded.skill_md
    assert loaded.manifest["agent"] == "qa-agent"

    record = registry.get("synthetic-rubric-designer")
    assert record["handler"]["artifact_ids"] == {"assessment": "assessment:{section_id}"}
    assert record["invocation"]["explicit"] is True
    assert record["network"] is False
    assert record["filesystem"] == "none"


def test_provider_never_executes_upstream_files(registry_env, tmp_path):
    manifest, root = _synthetic_provider(tmp_path, with_scripts=True)
    results = provider_edu.install(provider=manifest, root=root)
    assert results[0]["runtime"] == "sandbox_skill"  # scripts/ ⇒ 只能走沙箱
    quarantine = Path(registry.get("synthetic-rubric-designer")["handler"]["skill_path"])
    candidates = [path for path in list(tmp_path.rglob("pwned.txt")) + list(quarantine.rglob("pwned.txt"))]
    assert candidates == [], "上游脚本绝不能在导入/安装阶段执行"


@pytest.fixture
def synthetic_provider(registry_env, tmp_path):
    manifest, root = _synthetic_provider(tmp_path)
    provider_edu.install(provider=manifest, root=root)
    return manifest


@pytest.fixture
def provider_engine(synthetic_provider, engine):
    """安装完成后再构造 permissions，保证 allowlist 生效（§7 顺序）。"""
    from pebs.permissions import PermissionManager

    engine.permissions = PermissionManager()
    return engine


def test_acceptance_checklist_for_a_provider_skill(synthetic_provider, provider_engine):
    """§15：load / route / plan / execute / 声明产物 / 拒绝未声明访问 / schema。"""
    engine = provider_engine

    loaded = skill_loader.load("synthetic-rubric-designer")
    assert loaded.version == "a" * 40

    candidates = resolver.candidates("assessment")
    assert "synthetic-rubric-designer" in {item["name"] for item in candidates}
    chosen = resolver.choose("assessment", prefer=["synthetic-rubric-designer"])
    assert chosen["name"] == "synthetic-rubric-designer"

    engine.llm = FakeLLM(
        external_skill_payloads=[
            {
                "section_id": "sec1",
                "items": [
                    {
                        "assessment_id": "q1",
                        "kind": "hinge_question",
                        "question": "?" ,
                        "options": ["a", "b"],
                        "answer": "a",
                        "target_goal": "g1",
                    }
                ],
            }
        ]
    )
    start, status = run_dynamic_build(engine, REQUEST_1 + " /synthetic-rubric-designer")
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    produced = engine.store.revisions_of("assessment:sec1")
    assert produced, "外部 Skill 必须产出声明的 artifact"
    step = next(item for item in status["steps"] if item["step_id"] == "synthetic-rubric-designer")
    assert step["status"] == "SUCCEEDED"


def test_restricted_context_enforces_declared_only_access():
    class Inner:
        def __init__(self):
            self.outputs = {"learning_design:sec1": "learning_design:sec1@r1"}

        def content(self, artifact_id):
            return {"artifact_id": artifact_id}

        def rev(self, artifact_id):
            return self.outputs.get(artifact_id)

        def artifact_ids_of_type(self, artifact_type):
            return [aid for aid in self.outputs if aid.split(":", 1)[0] == artifact_type]

        def content_by_type(self, artifact_type):
            ids = self.artifact_ids_of_type(artifact_type)
            return self.content(ids[0]) if ids else None

        def emit(self, artifact_id, artifact_type, content, produced_by, deps=None):
            self.outputs[artifact_id] = f"{artifact_id}@r2"
            return {"revision_id": f"{artifact_id}@r2"}

        def sections(self):
            return [{"section_id": "sec1", "title": "t"}]

    ctx = RestrictedContext(
        Inner(), agent="qa-agent", allowed_inputs=("learning_design",), produces=("assessment",), strict_reads=True
    )
    assert ctx.content("learning_design:sec1") == {"artifact_id": "learning_design:sec1"}
    with pytest.raises(IsolationViolation):
        ctx.content("evidence_index")
    ctx.emit("assessment:sec1", "assessment", {}, "qa-agent")
    with pytest.raises(AgentContractError):
        ctx.emit("script:sec1", "script", {}, "qa-agent")


@pytest.mark.external
def test_real_provider_skills_are_installed_and_pinnned():
    manifest = provider_edu.load_manifest()
    report = provider_edu.verify(provider=manifest)
    if not report["ok"]:
        pytest.skip("education-agent-skills provider 未安装（本地运行 provider install 后再验）")
    assert report["license"] == "CC-BY-SA-4.0"
    assert len(report["skills"]) == 14
    sha = manifest["repository"]["commit_sha"]
    for item in report["skills"]:
        assert item["status"] in ("APPROVED", "PATCHED")
        assert item["pinned_version"] == sha
        record = registry.get(item["skill"])
        assert record["handler"]["artifact_ids"], item["skill"]
        assert record["network"] is False
        assert record["filesystem"] == "none"


@pytest.mark.external
def test_real_patched_skills_load_pebs_contract_and_policy():
    manifest = provider_edu.load_manifest()
    report = provider_edu.verify(provider=manifest)
    if not report["ok"]:
        pytest.skip("provider 未安装")
    for alias, patch_version in PATCHED.items():
        loaded = skill_loader.load(alias)
        assert patch_version in str(loaded.path), f"{alias} 应加载补丁版本"
        assert "PEBS 输出契约" in loaded.skill_md
        assert "CC BY-SA" in loaded.skill_md
    load_md = skill_loader.load("cognitive-load-analyser").skill_md
    assert "4–7 elements" not in load_md and "4-7 elements" not in load_md
    udl_md = skill_loader.load("udl-barrier-anticipator").skill_md
    assert "individual_support_review_flags" in udl_md
    hinge_md = skill_loader.load("hinge-question-designer").skill_md
    assert "answer_verification" in hinge_md and "distractors_detail" in hinge_md


@pytest.mark.external
def test_real_external_skill_is_selected_by_explicit_user_choice(engine):
    """§43 Explicit User Choice：显式 `/dual-coding-designer` 时不由 Builtin 抢占。"""
    manifest = provider_edu.load_manifest()
    if not provider_edu.verify(provider=manifest)["ok"]:
        pytest.skip("provider 未安装")
    engine.llm = FakeLLM(
        external_skill_payloads=[
            {
                "section_id": "sec1",
                "items": [
                    {
                        "item_id": "m1",
                        "goal_ref": "g1",
                        "knowledge_function": "structure",
                        "temporal_dependency": False,
                        "spatial_dependency": True,
                        "comparison_dependency": False,
                        "persistence_need": False,
                        "learner_interaction_need": False,
                        "recommended_medium": "diagram",
                        "rationale": "结构关系适合图示",
                    }
                ],
            }
        ]
    )
    start, status = run_dynamic_build(engine, REQUEST_1 + " /dual-coding-designer")
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    step = next(item for item in status["steps"] if item["step_id"] == "dual-coding-designer")
    assert step["status"] == "SUCCEEDED"
    assert "外部 Skill 执行" in (step["note"] or "")
    revisions = engine.store.revisions_of("media_plan:sec1")
    assert revisions, "media_plan:sec1 应由外部 Skill 产出"
    assert engine.store.get_revision(revisions[-1])["produced_by"] == "dual-coding-designer"
