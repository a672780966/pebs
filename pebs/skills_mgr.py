from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from . import config
from .store import now_iso


class SkillError(Exception):
    pass


class SourceNotAllowed(SkillError):
    pass


class PackageRejected(SkillError):
    pass


class ReviewTransitionRejected(SkillError):
    pass


def _skills_dir() -> Path:
    return Path(config.SKILLS_DIR)


def _quarantine_dir() -> Path:
    return Path(config.QUARANTINE_DIR)


def _upstream_dir() -> Path:
    return Path(config.UPSTREAM_DIR)


def _patched_dir() -> Path:
    return Path(config.PATCHED_DIR)


def _patches_dir() -> Path:
    return Path(config.PATCHES_DIR)


def _registry_path() -> Path:
    return Path(config.REGISTRY_DIR) / "skills.json"


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_registry(registry: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def check_source_allowed(url: str) -> str:
    if ".." in url or url.strip() != url:
        raise SourceNotAllowed(f"非法来源 URL: {url}")
    for source in config.SKILLS_SOURCES.get("sources", []):
        if not source.get("enabled", True):
            continue
        for prefix in source.get("prefixes", []):
            if url.startswith(prefix):
                return str(source.get("id", "unknown"))
    raise SourceNotAllowed(f"来源不在 allowlist 中：{url}")


def _limits() -> dict[str, int]:
    limits = config.SKILLS_SOURCES.get("limits", {})
    return {
        "max_files": int(limits.get("max_files", 500)),
        "max_file_bytes": int(limits.get("max_file_mib", 5)) * 1024 * 1024,
        "max_total_bytes": int(limits.get("max_total_mib", 50)) * 1024 * 1024,
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    limits = _limits()
    members = [m for m in tar.getmembers() if m.isfile() or m.isdir()]
    if len([m for m in members if m.isfile()]) > limits["max_files"]:
        raise PackageRejected(f"文件数超过限制 {limits['max_files']}")
    total = 0
    for member in tar.getmembers():
        if member.issym() or member.islnk():
            raise PackageRejected(f"包含符号/硬链接，已拒绝：{member.name}")
        pure = PurePosixPath(member.name)
        if pure.is_absolute() or ".." in pure.parts:
            raise PackageRejected(f"路径越界，已拒绝：{member.name}")
        if member.isfile():
            if member.size > limits["max_file_bytes"]:
                raise PackageRejected(f"单文件超过限制：{member.name}")
            total += member.size
    if total > limits["max_total_bytes"]:
        raise PackageRejected(f"包体超过总大小限制 {limits['max_total_bytes']}")
    return members


def _download(url: str, timeout: int = 120) -> bytes:
    if url.startswith("file://"):
        path = Path(url.replace("file:///", "", 1).replace("file://", "", 1))
        if not path.exists():
            raise SkillError(f"本地归档不存在：{path}")
        data = path.read_bytes()
    else:
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise SkillError(f"下载失败：{exc}") from exc
        if response.status_code >= 400:
            raise SkillError(f"下载失败：HTTP {response.status_code}")
        data = response.content
    if not data.startswith(b"\x1f\x8b"):
        raise PackageRejected("仅接受 .tar.gz 归档（gzip magic 检查失败）")
    return data


def _derive_name(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if "codeload" in parsed.netloc and len(parts) >= 2:
        return parts[1].removesuffix(".git")
    if "archive" in parts:
        index = parts.index("archive")
        if index > 0:
            return parts[index - 1].removesuffix(".git")
    basename = parts[-1] if parts else "skill"
    return basename.removesuffix(".tar.gz").removesuffix(".tgz") or "skill"


def _read_skill_manifest(root: Path) -> dict[str, Any]:
    import yaml

    for candidate in root.rglob("skill.yaml"):
        try:
            data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("name"):
            data["_manifest_path"] = str(candidate)
            return data
    return {}


def _has_scripts(root: Path) -> bool:
    for path in root.rglob("scripts"):
        if path.is_dir() and any(child.is_file() for child in path.iterdir()):
            return True
    return False


def derive_contract(quarantine: Path) -> dict[str, Any]:
    manifest = _read_skill_manifest(quarantine)
    runtime_kind = "sandbox_skill" if _has_scripts(quarantine) else "prompt_skill"
    return {
        "description": str(manifest.get("description") or ""),
        "requires": [str(item) for item in (manifest.get("requires") or []) if str(item)],
        "produces": [str(item) for item in (manifest.get("produces") or []) if str(item)],
        "optional_requires": [str(item) for item in (manifest.get("optional_requires") or []) if str(item)],
        "provider": [str(item) for item in (manifest.get("provider") or []) if str(item)],
        "tools": [str(item) for item in (manifest.get("tools") or []) if str(item)],
        "network": bool(manifest.get("network", False)),
        "filesystem": str(manifest.get("filesystem", "none")),
        "risk_level": str(manifest.get("risk_level", "unknown")),
        "runtime": runtime_kind,
        "entrypoint": manifest.get("entrypoint"),
        "artifact_ids": manifest.get("artifact_ids") or {},
        "outputs": manifest.get("outputs") or [],
        "manifest": manifest,
    }


def import_candidate(
    url: str,
    *,
    ref: str | None = None,
    commit_sha: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    source_id = check_source_allowed(url)
    data = _download(url)
    package_hash = _sha256_bytes(data)
    stem = name or _derive_name(url)
    if "@" in stem:
        stem, embedded_ref = stem.rsplit("@", 1)
        ref = ref or embedded_ref
    name = name or stem or f"skill_{package_hash[:8]}"

    files: list[dict[str, Any]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = _safe_members(tar)
        file_members = [m for m in members if m.isfile()]
        if not file_members:
            raise PackageRejected("归档中没有文件")
        quarantine = _quarantine_dir() / f"{name}-{package_hash[:12]}"
        if quarantine.exists():
            shutil.rmtree(quarantine, ignore_errors=True)
        quarantine.mkdir(parents=True, exist_ok=True)
        for member in file_members:
            target = quarantine / PurePosixPath(member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                raise PackageRejected(f"无法读取成员：{member.name}")
            payload = extracted.read()
            target.write_bytes(payload)
            files.append(
                {
                    "path": member.name,
                    "sha256": _sha256_bytes(payload),
                    "size": len(payload),
                }
            )
    manifest = {
        "name": name,
        "source_id": source_id,
        "repository_url": url,
        "ref": ref,
        "commit_sha": commit_sha or ref or "unknown",
        "package_sha256": package_hash,
        "files": sorted(files, key=lambda f: f["path"]),
        "imported_at": now_iso(),
        "license": _detect_license(quarantine),
        "executed": [],
    }
    (quarantine / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    registry = _load_registry()
    existing = registry.get(name, {})
    contract = derive_contract(quarantine)
    record = {
        "name": name,
        "version": existing.get("version", "0.0.0"),
        "domain": "external",
        "description": contract["description"] or existing.get("description", "未审查的外部 Skill 候选"),
        "status": "REFERENCE_ONLY",
        "invocation": {"auto": True, "explicit": True},
        "requires": contract["requires"],
        "produces": contract["produces"],
        "optional_requires": contract["optional_requires"],
        "aliases": [],
        "input_schema": None,
        "output_schema": None,
        "provider": contract["provider"],
        "tools": contract["tools"],
        "risk_level": contract["risk_level"],
        "network": contract["network"],
        "filesystem": contract["filesystem"] or "none",
        "external_side_effects": False,
        "runtime": contract["runtime"],
        "handler": {
            "skill_path": str(quarantine),
            "entrypoint": contract["entrypoint"],
            "artifact_ids": contract["artifact_ids"],
            "outputs": contract["outputs"],
        },
        "gates_before": [],
        "gates_after": [],
        "parallelizable": False,
        "estimated_cost": {"model_calls": int(contract["manifest"].get("estimated_model_calls", 1) or 1), "research_calls": 0},
        "self_implemented": False,
        "user_invocable": False,
        "auto_invocable": False,
        "review_status": "UNVERIFIED",
        "adoption_decision": "REFERENCE_ONLY",
        "role": "ACTION_SKILL",
        "execution_policy": "SANDBOX_ONLY",
        "enabled_by_default": False,
        "source": {
            "repository_url": url,
            "ref": ref,
            "commit_sha": manifest["commit_sha"],
            "license": manifest["license"],
            "package_sha256": package_hash,
            "imported_at": manifest["imported_at"],
            "quarantine_path": str(quarantine),
        },
        "review": {"reviewed_at": None, "reviewed_by": None, "evidence": None},
        "versions": existing.get("versions", []),
        "pinned_version": existing.get("pinned_version"),
        "patches": existing.get("patches", []),
    }
    registry[name] = record
    _save_registry(registry)
    return record


def _detect_license(root: Path) -> str:
    candidates: list[Path] = []
    for name in ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "license"]:
        candidates.append(root / name)
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        for name in ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "license"]:
            candidates.append(child / name)
    for path in candidates:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:200]
            except OSError:
                continue
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
            return first_line or "present (unparsed)"
    return "unknown"


def review(
    name: str,
    decision: str,
    *,
    reviewer: str | None = None,
    evidence: str | None = None,
    adoption_decision: str | None = None,
) -> dict[str, Any]:
    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    current = record.get("review_status", "UNVERIFIED")
    allowed = {
        "UNVERIFIED": {"IN_REVIEW", "REJECTED"},
        "IN_REVIEW": {"APPROVED", "REJECTED"},
        "APPROVED": {"REJECTED"},
        "REJECTED": {"IN_REVIEW"},
    }
    target = decision.upper()
    if target not in allowed.get(current, set()):
        raise ReviewTransitionRejected(f"非法状态迁移：{current} → {target}")
    config_review = config.SKILLS_SOURCES.get("review", {})
    if config_review.get("require_reviewer", True) and not (reviewer or "").strip():
        raise ReviewTransitionRejected("审查必须记录 reviewed_by")
    if target == "APPROVED" and config_review.get("require_evidence", True) and not (evidence or "").strip():
        raise ReviewTransitionRejected("批准必须提供审查证据（源码/哈希/测试记录位置）")
    record["review_status"] = target
    if target == "APPROVED":
        record["status"] = "APPROVED"
    elif target == "REJECTED":
        record["status"] = "DISABLED"
    elif target == "IN_REVIEW":
        record["status"] = "REFERENCE_ONLY"
    record["review"] = {
        "reviewed_at": now_iso(),
        "reviewed_by": reviewer,
        "evidence": evidence,
    }
    if target == "APPROVED":
        record["adoption_decision"] = adoption_decision or record.get("adoption_decision", "REFERENCE_ONLY")
    if target == "REJECTED":
        record["enabled_by_default"] = False
    registry[name] = record
    _save_registry(registry)
    return record


def enable(name: str, enabled: bool = True) -> dict[str, Any]:
    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    if enabled and record.get("review_status") != "APPROVED":
        raise ReviewTransitionRejected("只有 APPROVED 的技能可以启用")
    record["enabled_by_default"] = bool(enabled)
    registry[name] = record
    _save_registry(registry)
    return record


def _verify_quarantine(record: dict[str, Any]) -> Path:
    quarantine = Path(record["source"]["quarantine_path"])
    manifest_path = quarantine / "manifest.json"
    if not manifest_path.exists():
        raise SkillError(f"隔离区缺失 manifest：{quarantine}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_sha256") != record["source"].get("package_sha256"):
        raise PackageRejected("package_sha256 与登记不一致")
    for entry in manifest.get("files", []):
        path = quarantine / PurePosixPath(entry["path"])
        if not path.exists():
            raise PackageRejected(f"缺少文件：{entry['path']}")
        if _sha256_bytes(path.read_bytes()) != entry["sha256"]:
            raise PackageRejected(f"文件哈希不一致：{entry['path']}")
    return quarantine


def publish(name: str, *, version: str | None = None) -> dict[str, Any]:
    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    if record.get("review_status") != "APPROVED":
        raise ReviewTransitionRejected("只有 APPROVED 的技能可以发布")
    quarantine = _verify_quarantine(record)
    sha = record["source"].get("commit_sha")
    fallback = record["source"]["package_sha256"][:12]
    resolved_version = version or (sha if sha and sha != "unknown" else fallback)
    target = _upstream_dir() / name / resolved_version
    if target.exists():
        raise SkillError(f"版本已存在，不覆盖历史版本：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".tmp-{uuid.uuid4().hex[:8]}"
    shutil.copytree(quarantine, staging)
    os.replace(staging, target)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    versions = [v for v in record.get("versions", []) if v.get("version") != resolved_version]
    versions.append(
        {
            "version": resolved_version,
            "upstream_sha": manifest.get("commit_sha"),
            "package_sha256": manifest.get("package_sha256"),
            "published_at": now_iso(),
            "path": str(target),
        }
    )
    record["versions"] = versions
    record["pinned_version"] = resolved_version
    registry[name] = record
    _save_registry(registry)
    return record


def pin(name: str, version: str) -> dict[str, Any]:
    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    if version not in {v["version"] for v in record.get("versions", [])}:
        raise SkillError(f"未发布的版本：{version}")
    record["pinned_version"] = version
    registry[name] = record
    _save_registry(registry)
    return record


def apply_patch(
    name: str,
    patch_files_dir: Path,
    *,
    patch_version: str,
    patch_reason: str,
    reviewer: str,
    tests: str | None = None,
) -> dict[str, Any]:
    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    if record.get("review_status") != "APPROVED":
        raise ReviewTransitionRejected("只有 APPROVED 的技能可以打补丁")
    pinned = record.get("pinned_version")
    if not pinned:
        raise SkillError("未 pin 版本，先发布并 pin")
    base = next((v for v in record.get("versions", []) if v["version"] == pinned), None)
    if base is None:
        raise SkillError(f"pin 的版本不存在：{pinned}")
    source_dir = Path(base["path"])
    if not source_dir.exists():
        raise SkillError(f"上游版本目录缺失：{source_dir}")
    patch_files_dir = Path(patch_files_dir)
    if not patch_files_dir.exists():
        raise SkillError(f"补丁目录不存在：{patch_files_dir}")
    overlay: list[str] = []
    for path in sorted(patch_files_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(patch_files_dir)
        if ".." in rel.parts or rel.is_absolute():
            raise PackageRejected(f"补丁路径越界：{rel}")
        overlay.append(rel.as_posix())
    if not overlay:
        raise PackageRejected("补丁目录为空")
    target = _patched_dir() / name / f"{pinned}+{patch_version}"
    if target.exists():
        raise SkillError(f"补丁版本已存在：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".tmp-{uuid.uuid4().hex[:8]}"
    shutil.copytree(source_dir, staging)
    for rel in overlay:
        destination = staging / PurePosixPath(rel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(patch_files_dir / PurePosixPath(rel), destination)
    os.replace(staging, target)
    patch_record = {
        "patch_version": patch_version,
        "upstream_version": pinned,
        "upstream_sha": base.get("upstream_sha"),
        "patch_reason": patch_reason,
        "reviewed_by": reviewer,
        "tests": tests or "",
        "files": overlay,
        "applied_at": now_iso(),
        "path": str(target),
    }
    patches = [p for p in record.get("patches", []) if p.get("patch_version") != patch_version]
    patches.append(patch_record)
    record["patches"] = patches
    registry[name] = record
    _save_registry(registry)
    patch_meta_dir = _patches_dir() / name
    patch_meta_dir.mkdir(parents=True, exist_ok=True)
    (patch_meta_dir / f"{patch_version}.json").write_text(
        json.dumps(patch_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def resolve_runtime(name: str) -> dict[str, Any]:
    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    if record.get("review_status") != "APPROVED":
        raise ReviewTransitionRejected(f"技能未批准：{name} ({record.get('review_status')})")
    pinned = record.get("pinned_version")
    if not pinned:
        raise SkillError(f"技能未 pin 版本：{name}")
    base = next((v for v in record.get("versions", []) if v["version"] == pinned), None)
    if base is None:
        raise SkillError(f"pin 的版本不存在：{pinned}")
    upstream_dir = Path(base["path"])
    if not upstream_dir.exists():
        raise SkillError(f"上游目录缺失：{upstream_dir}")
    current_manifest = {}
    manifest_path = upstream_dir / "manifest.json"
    if manifest_path.exists():
        current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if current_manifest.get("package_sha256") not in (None, base.get("package_sha256")):
        raise SkillError("上游包哈希与发布记录不一致，停止合成（不猜测套用补丁）")
    patched = [
        p for p in record.get("patches", []) if p.get("upstream_version") == pinned
    ]
    if patched:
        latest_patch = sorted(patched, key=lambda p: p["applied_at"])[-1]
        if latest_patch.get("upstream_sha") not in (None, base.get("upstream_sha")):
            raise SkillError("补丁基准与上游 SHA 不一致，停止合成")
        return {
            "name": name,
            "path": latest_patch["path"],
            "version": f"{pinned}+{latest_patch['patch_version']}",
            "patched": True,
            "record": record,
        }
    return {"name": name, "path": str(upstream_dir), "version": pinned, "patched": False, "record": record}


def list_skills() -> list[dict[str, Any]]:
    registry = _load_registry()
    items = []
    for name, record in sorted(registry.items()):
        items.append(
            {
                "name": name,
                "review_status": record.get("review_status"),
                "adoption_decision": record.get("adoption_decision"),
                "execution_policy": record.get("execution_policy"),
                "enabled_by_default": record.get("enabled_by_default"),
                "self_implemented": record.get("self_implemented", False),
                "pinned_version": record.get("pinned_version"),
                "versions": [v.get("version") for v in record.get("versions", [])],
                "patches": [p.get("patch_version") for p in record.get("patches", [])],
                "source": record.get("source"),
            }
        )
    return items


def _count_pytest(output: str, keyword: str) -> int:
    import re as _re

    match = _re.search(rf"(\d+)\s+{keyword}", output or "")
    return int(match.group(1)) if match else 0


def verify_skill(name: str, python_exe: str | None = None) -> dict[str, Any]:
    import subprocess
    import sys

    registry = _load_registry()
    record = registry.get(name)
    if record is None:
        raise SkillError(f"未登记的技能：{name}")
    node_ids = record.get("tests") or []
    if not node_ids:
        raise SkillError(f"技能未登记回归测试：{name}")
    cmd = [python_exe or sys.executable, "-m", "pytest", "-q", "--tb=no", *node_ids]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(config.ROOT))
    record_result = {
        "skill": name,
        "version": record.get("pinned_version") or record.get("version"),
        "rules_version": config.RULES_VERSION,
        "run_at": now_iso(),
        "last_verified": now_iso(),
        "command": cmd,
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "tests_passed": _count_pytest(proc.stdout, "passed"),
        "tests_failed": _count_pytest(proc.stdout, "failed"),
        "domains": [record.get("domain")] if record.get("domain") else [],
        "quality": {
            "schema": bool(record.get("output_schema")),
            "safety": bool(record.get("risk_level")),
            "evidence": bool(record.get("gates_before") or record.get("requires")),
            "stability": proc.returncode == 0,
        },
        "known_failures": [] if proc.returncode == 0 else [(proc.stdout or proc.stderr or "")[-400:]],
        "output_tail": (proc.stdout or proc.stderr or "")[-2000:],
    }
    regression_path = Path(config.REGISTRY_DIR) / "regression.json"
    history = []
    if regression_path.exists():
        history = json.loads(regression_path.read_text(encoding="utf-8"))
    history.append(record_result)
    regression_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return record_result
