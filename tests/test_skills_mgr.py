from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from pebs import config, skills_mgr


def _make_archive(tmp_path: Path, files: dict[str, str], name: str = "archive.tar.gz") -> Path:
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as tar:
        for rel, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _make_evil_archive(tmp_path: Path, member: str) -> Path:
    path = tmp_path / "evil.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        data = b"evil"
        info = tarfile.TarInfo(member)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return path


@pytest.fixture
def archive_fixture(registry_env, tmp_path):
    return _make_archive(tmp_path, SKILL_FILES)


SKILL_FILES = {
    "SKILL.md": "# Demo Skill\n\n说明",
    "schema.json": "{}",
    "scripts/run.py": "print('should never run during import')",
    "LICENSE": "MIT License",
}


def test_derive_name_from_github_archive_urls():
    assert (
        skills_mgr._derive_name("https://github.com/octocat/Hello-World/archive/refs/heads/master.tar.gz")
        == "Hello-World"
    )
    assert (
        skills_mgr._derive_name("https://codeload.github.com/octocat/Hello-World/tar.gz/refs/heads/master")
        == "Hello-World"
    )
    assert skills_mgr._derive_name("file:///tmp/demo-skill.tar.gz") == "demo-skill"


def test_import_quarantines_without_executing(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}")
    assert record["review_status"] == "UNVERIFIED"
    assert record["enabled_by_default"] is False
    assert record["execution_policy"] == "SANDBOX_ONLY"
    quarantine = Path(record["source"]["quarantine_path"])
    manifest = json.loads((quarantine / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["executed"] == []
    assert manifest["license"] == "MIT License"
    assert {f["path"] for f in manifest["files"]} == set(SKILL_FILES)


def test_import_rejects_path_traversal(registry_env, tmp_path):
    archive = _make_evil_archive(tmp_path, "../evil.txt")
    with pytest.raises(skills_mgr.PackageRejected):
        skills_mgr.import_candidate(f"file:///{archive}")
    assert not (tmp_path / "evil.txt").exists()


def test_import_rejects_absolute_member(registry_env, tmp_path):
    archive = _make_evil_archive(tmp_path, "/tmp/abs.txt")
    with pytest.raises(skills_mgr.PackageRejected):
        skills_mgr.import_candidate(f"file:///{archive}")


def test_import_rejects_links(registry_env, tmp_path):
    path = tmp_path / "link.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)
    with pytest.raises(skills_mgr.PackageRejected):
        skills_mgr.import_candidate(f"file:///{path}")


def test_import_rejects_disallowed_source(registry_env, tmp_path):
    with pytest.raises(skills_mgr.SourceNotAllowed):
        skills_mgr.import_candidate("https://evil.example.com/skill.tar.gz")


def test_import_enforces_file_count_limit(registry_env, tmp_path, monkeypatch):
    monkeypatch.setattr(
        config, "SKILLS_SOURCES", {"sources": [{"id": "local", "prefixes": ["file://"], "enabled": True}], "limits": {"max_files": 2, "max_file_mib": 5, "max_total_mib": 50}}
    )
    archive = _make_archive(tmp_path, {"a.txt": "a", "b.txt": "b", "c.txt": "c"})
    with pytest.raises(skills_mgr.PackageRejected):
        skills_mgr.import_candidate(f"file:///{archive}")


def _approve(record, **kwargs):
    skills_mgr.review(record["name"], "IN_REVIEW", reviewer="tester", evidence=None)
    return skills_mgr.review(
        record["name"], "APPROVED", reviewer="tester", evidence=kwargs.get("evidence", "quarantine manifest sha256 + manual read")
    )


def test_review_transitions_and_evidence_required(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}")
    with pytest.raises(skills_mgr.ReviewTransitionRejected):
        skills_mgr.review(record["name"], "APPROVED", reviewer="tester", evidence="x")
    skills_mgr.review(record["name"], "IN_REVIEW", reviewer="tester")
    with pytest.raises(skills_mgr.ReviewTransitionRejected):
        skills_mgr.review(record["name"], "APPROVED", reviewer="tester", evidence="")
    approved = skills_mgr.review(record["name"], "APPROVED", reviewer="tester", evidence="manual audit #1")
    assert approved["review_status"] == "APPROVED"
    assert approved["review"]["reviewed_by"] == "tester"


def test_publish_requires_approval_then_pins_version(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}", commit_sha="abc123")
    with pytest.raises(skills_mgr.ReviewTransitionRejected):
        skills_mgr.publish(record["name"])
    _approve(record)
    published = skills_mgr.publish(record["name"])
    assert published["pinned_version"] == "abc123"
    version_dir = Path(published["versions"][0]["path"])
    assert (version_dir / "SKILL.md").exists()
    with pytest.raises(skills_mgr.SkillError):
        skills_mgr.publish(record["name"])


def test_publish_falls_back_to_package_hash_when_sha_unknown(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}")
    _approve(record)
    published = skills_mgr.publish(record["name"])
    assert published["pinned_version"] == record["source"]["package_sha256"][:12]


def test_runtime_resolution_requires_approved_and_pinned(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}", commit_sha="abc123")
    with pytest.raises(skills_mgr.ReviewTransitionRejected):
        skills_mgr.resolve_runtime(record["name"])
    _approve(record)
    skills_mgr.publish(record["name"])
    runtime = skills_mgr.resolve_runtime(record["name"])
    assert runtime["patched"] is False
    assert Path(runtime["path"]).name == "abc123"


def test_patch_overlay_applied_and_preferred(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}", commit_sha="abc123")
    _approve(record)
    skills_mgr.publish(record["name"])
    patch_dir = tmp_path / "patch"
    (patch_dir / "scripts").mkdir(parents=True)
    (patch_dir / "scripts" / "run.py").write_text("print('patched')", encoding="utf-8")
    (patch_dir / "PATCH.md").write_text("局部补丁说明", encoding="utf-8")
    updated = skills_mgr.apply_patch(
        record["name"],
        patch_dir,
        patch_version="p1",
        patch_reason="移除上游示例中的错误计算",
        reviewer="tester",
        tests="tests/test_skills_mgr.py",
    )
    assert updated["patches"][0]["patch_version"] == "p1"
    runtime = skills_mgr.resolve_runtime(record["name"])
    assert runtime["patched"] is True
    assert runtime["version"] == "abc123+p1"
    assert (Path(runtime["path"]) / "scripts" / "run.py").read_text(encoding="utf-8") == "print('patched')"


def test_patch_base_mismatch_stops_composition(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}", commit_sha="abc123")
    _approve(record)
    skills_mgr.publish(record["name"])
    registry = json.loads((config.REGISTRY_DIR / "skills.json").read_text(encoding="utf-8"))
    upstream_path = registry[record["name"]]["versions"][0]["path"]
    registry[record["name"]]["patches"].append(
        {
            "patch_version": "p0",
            "upstream_version": "abc123",
            "upstream_sha": "different-sha",
            "patch_reason": "x",
            "reviewed_by": "tester",
            "tests": "",
            "files": [],
            "applied_at": "2026-01-01T00:00:00",
            "path": upstream_path,
        }
    )
    (config.REGISTRY_DIR / "skills.json").write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(skills_mgr.SkillError, match="基准"):
        skills_mgr.resolve_runtime(record["name"])


def test_enable_requires_approval(registry_env, tmp_path):
    archive = _make_archive(tmp_path, SKILL_FILES)
    record = skills_mgr.import_candidate(f"file:///{archive}")
    with pytest.raises(skills_mgr.ReviewTransitionRejected):
        skills_mgr.enable(record["name"])
    _approve(record)
    enabled = skills_mgr.enable(record["name"])
    assert enabled["enabled_by_default"] is True


def test_sandbox_only_skill_denied_without_verified_adapter(registry_env, monkeypatch):
    from pebs import sandbox
    from pebs.permissions import PermissionDenied, PermissionManager

    (config.REGISTRY_DIR / "allowlist.json").write_text(
        json.dumps({"skills": ["ext-skill"], "tools": [], "network_hosts": [], "providers": []}), encoding="utf-8"
    )
    (config.REGISTRY_DIR / "skills.json").write_text(
        json.dumps(
            {
                "ext-skill": {
                    "name": "ext-skill",
                    "review_status": "APPROVED",
                    "enabled_by_default": True,
                    "execution_policy": "SANDBOX_ONLY",
                    "version": "0.1.0",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sandbox, "available", lambda refresh=False: False)
    permissions = PermissionManager()
    with pytest.raises(PermissionDenied, match="sandbox"):
        permissions.skill("ext-skill")
    monkeypatch.setattr(sandbox, "available", lambda refresh=False: True)
    assert permissions.skill("ext-skill")["name"] == "ext-skill"
