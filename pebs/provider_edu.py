"""Education Agent Skills Provider 适配器（M6 §6–§10）。

把上游 Agent-Skills 归档（`skills/<category>/<name>/SKILL.md`）包装成 PEBS Skill 包：

1. 只读取上游文件，绝不执行（无 import hooks、无 scripts 执行）。
2. 为每个 Skill 生成 PEBS 契约 `skill.yaml`（requires/produces/artifact_ids/output_schema），
   契约由 provider manifest 中的 reviewed mapping 提供；没有契约的 Skill 不会被导入。
3. 附带 CC BY-SA 4.0 归属与许可说明（本地补丁同为 CC BY-SA 4.0）。
4. 之后完整走 M5 生命周期：import → quarantine → review → publish(pin) → patch。
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import config, skills_mgr

PROVIDER_ID = "education-agent-skills"
REVIEWER = "pebs-m6"


class ProviderError(Exception):
    pass


def provider_dir() -> Path:
    return Path(config.PROVIDERS_DIR) / PROVIDER_ID


def manifest_path() -> Path:
    return provider_dir() / "provider.yaml"


def load_manifest() -> dict[str, Any]:
    path = manifest_path()
    if not path.exists():
        raise ProviderError(f"provider manifest 不存在：{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ProviderError("provider manifest 必须是 mapping")
    return data


def save_manifest(data: dict[str, Any]) -> Path:
    path = manifest_path()
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def cache_root() -> Path:
    return Path(config.SKILLS_DIR) / "provider-cache" / PROVIDER_ID


def fetch(*, manifest: dict[str, Any] | None = None, client: httpx.Client | None = None) -> Path:
    """下载并解压固定 commit 的上游归档（只读，不执行）。返回解压后的仓库根目录。"""
    manifest = manifest or load_manifest()
    repository = manifest.get("repository") or {}
    sha = str(repository.get("commit_sha") or "")
    if not sha or sha == "PENDING_PIN" or len(sha) < 7:
        raise ProviderError("provider repository.commit_sha 未固定（§10）")
    url = str(repository.get("archive_url") or "").format(sha=sha) or (
        f"https://codeload.github.com/{_repo_slug(repository)}/tar.gz/{sha}"
    )
    target = cache_root() / sha
    if (target / ".ready").exists():
        return _repo_root(target)
    target.mkdir(parents=True, exist_ok=True)
    owns_client = client is None
    client = client or httpx.Client(timeout=120, follow_redirects=True)
    try:
        response = client.get(url)
        response.raise_for_status()
        package = response.content
    finally:
        if owns_client:
            client.close()
    digest = hashlib.sha256(package).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(package)) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts:
                raise ProviderError(f"归档路径越界：{member.name}")
            if member.issym() or member.islnk():
                raise ProviderError(f"归档包含链接，拒绝解压：{member.name}")
        archive.extractall(target)
    (target / ".ready").write_text(json.dumps({"sha256": digest, "url": url}, ensure_ascii=False), encoding="utf-8")
    return _repo_root(target)


def _repo_slug(repository: dict[str, Any]) -> str:
    url = str(repository.get("url") or "")
    return url.replace("https://github.com/", "").strip("/")


def _repo_root(target: Path) -> Path:
    children = [child for child in target.iterdir() if child.is_dir() and child.name != "__pycache__"]
    for child in children:
        if (child / "skills").is_dir() or (child / "README.md").exists():
            return child
    raise ProviderError(f"无法定位归档根目录：{target}")


def _license_text(root: Path) -> str:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        path = root / name
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _find_skill_dir(root: Path, upstream_name: str) -> Path:
    matches = [path.parent for path in root.rglob("SKILL.md") if path.parent.name == upstream_name]
    if not matches:
        raise ProviderError(f"上游缺少 Skill：{upstream_name}")
    if len(matches) > 1:
        raise ProviderError(f"上游存在重名 Skill：{upstream_name}")
    return matches[0]


def _contract_for(entry: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    contract = dict(entry.get("contract") or {})
    required = ("requires", "produces", "artifact_ids")
    missing = [field for field in required if not contract.get(field) and contract.get(field) != []]
    if missing:
        raise ProviderError(f"{entry.get('local_alias')}: provider manifest 缺少契约字段 {missing}")
    if not contract.get("produces"):
        raise ProviderError(f"{entry.get('local_alias')}: 必须声明 produces（§65 四问答）")
    repository = provider.get("repository") or {}
    return {
        "name": entry["local_alias"],
        "version": str(repository.get("commit_sha") or "0.0.0")[:12],
        "description": str(entry.get("description") or contract.get("description") or entry["upstream_name"]),
        "requires": [str(item) for item in contract.get("requires") or []],
        "produces": [str(item) for item in contract.get("produces") or []],
        "optional_requires": [str(item) for item in contract.get("optional_requires") or []],
        "artifact_ids": dict(contract.get("artifact_ids") or {}),
        "provider": [PROVIDER_ID],
        "tools": [],
        "network": False,
        "filesystem": "none",
        "risk_level": str(contract.get("risk_level") or "low"),
        "estimated_model_calls": int(contract.get("estimated_model_calls") or 1),
        "agent": str(contract.get("agent") or ""),
        "domain": str(contract.get("domain") or "education"),
        "emits": [str(item) for item in contract.get("emits") or []],
        "invocation": {"auto": True, "explicit": True},
        "execution_policy": "NO_CODE",
        "license": str(repository.get("license") or ""),
        "source": {
            "provider": PROVIDER_ID,
            "repository": str(repository.get("url") or ""),
            "commit_sha": str(repository.get("commit_sha") or ""),
            "upstream_name": entry["upstream_name"],
            "upstream_path": str(entry.get("upstream_path") or f"skills/{entry['upstream_name']}"),
        },
        "invocation": {"auto": True, "explicit": True},
    }


def build_package(
    entry: dict[str, Any],
    root: Path,
    out_dir: Path,
    *,
    provider: dict[str, Any],
) -> Path:
    """生成 PEBS 可导入的 skill 包（tar.gz）。只复制文件，不执行任何内容。"""
    alias = entry["local_alias"]
    skill_dir = _find_skill_dir(root, entry["upstream_name"])
    staging = Path(out_dir) / alias
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copyfile(skill_dir / "SKILL.md", staging / "SKILL.md")
    for extra in sorted(skill_dir.rglob("*")):
        if extra.is_file() and extra.name != "SKILL.md":
            relative = extra.relative_to(skill_dir)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(extra, destination)

    contract = _contract_for(entry, provider)
    (staging / "skill.yaml").write_text(yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding="utf-8")
    schema = _schema_for(contract)
    if schema:
        (staging / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    license_text = _license_text(root)
    (staging / "LICENSE.upstream.txt").write_text(license_text, encoding="utf-8")
    (staging / "NOTICE.md").write_text(_notice(entry, provider), encoding="utf-8")

    archive = Path(out_dir) / f"{alias}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(staging, arcname=alias)
    return archive


def _schema_for(contract: dict[str, Any]) -> dict[str, Any] | None:
    artifact_type = (contract.get("produces") or [None])[0]
    if not artifact_type:
        return None
    from . import registry

    schema_name = registry.ARTIFACT_SCHEMAS.get(artifact_type)
    if not schema_name:
        return None
    path = Path(config.SCHEMA_DIR) / f"{schema_name}.schema.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _notice(entry: dict[str, Any], provider: dict[str, Any]) -> str:
    repository = provider.get("repository") or {}
    return (
        f"# 归属与许可（{entry['local_alias']}）\n\n"
        f"- 上游：{repository.get('url')} @ {repository.get('commit_sha')}\n"
        f"- 上游 Skill：{entry['upstream_name']}\n"
        f"- 许可：{repository.get('license')}\n"
        f"- 本包由 PEBS M6 Provider 适配器生成；PEBS 契约（skill.yaml）与补丁为本地新增内容，\n"
        f"  依据上游许可（CC BY-SA 4.0）以相同许可发布，并已注明修改。\n"
        f"- 未执行任何上游文件；仅进行文本打包与契约声明。\n"
    )


def install(
    *,
    entries: list[dict[str, Any]] | None = None,
    provider: dict[str, Any] | None = None,
    root: Path | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """走完整生命周期：导入 → 审查 → 发布（pin）→ （可选）本地补丁。"""
    provider = provider or load_manifest()
    aliases = {entry["local_alias"] for entry in entries} if entries else None
    selected = [entry for entry in provider.get("skills", []) if aliases is None or entry["local_alias"] in aliases]
    root = root or fetch(manifest=provider)
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        for entry in selected:
            alias = entry["local_alias"]
            archive = build_package(entry, root, Path(tmp), provider=provider)
            if force:
                _remove_existing(alias)
            skills_mgr.import_candidate(
                f"file:///{archive}",
                name=alias,
                commit_sha=str((provider.get("repository") or {}).get("commit_sha") or ""),
            )
            review = entry.get("review") or {}
            skills_mgr.review(alias, "IN_REVIEW", reviewer=REVIEWER, evidence=str(review.get("source_review") or "Provider 适配器导入"))
            skills_mgr.review(
                alias,
                "APPROVED",
                reviewer=REVIEWER,
                evidence=str(review.get("audit") or "SKILL.md 无 scripts/，无网络与文件系统访问"),
                adoption_decision="adopt",
            )
            skills_mgr.publish(alias)
            patch_version = str(entry.get("patch") or "")
            if patch_version:
                patch_dir = provider_dir() / "patches" / alias / patch_version
                if not patch_dir.is_dir():
                    raise ProviderError(f"补丁目录缺失：{patch_dir}")
                skills_mgr.apply_patch(
                    alias,
                    patch_dir,
                    patch_version=patch_version,
                    reviewer=REVIEWER,
                    patch_reason=str(entry.get("patch_reason") or "PEBS 输出契约与政策修订"),
                    tests=str(entry.get("regression_suite") or ""),
                )
            add_to_allowlist(alias)
            skills_mgr.enable(alias, True)
            results.append(status_for(alias, provider=provider))
    return results


def add_to_allowlist(alias: str) -> list[str]:
    """M6 §7：Provider 验收通过的 Skill 才写入 allowlist（显式 `/skill-name` 的权限前置）。"""
    path = Path(config.REGISTRY_DIR) / "allowlist.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"skills": []}
    skills = list(data.get("skills") or [])
    if alias not in skills:
        skills.append(alias)
    data["skills"] = sorted(skills)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data["skills"]


def remove_from_allowlist(alias: str) -> list[str]:
    path = Path(config.REGISTRY_DIR) / "allowlist.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    data["skills"] = sorted(skill for skill in data.get("skills", []) if skill != alias)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data["skills"]


def _remove_existing(alias: str) -> None:
    """force 重装：清掉派生目录，避免"补丁版本已存在"阻塞幂等安装。"""
    for base in (Path(config.PATCHED_DIR), Path(config.UPSTREAM_DIR), Path(config.QUARANTINE_DIR)):
        target = base / alias
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)


def status_for(alias: str, *, provider: dict[str, Any] | None = None) -> dict[str, Any]:
    from . import registry

    record = registry.get(alias) or {}
    entry = next(
        (item for item in (provider or load_manifest()).get("skills", []) if item["local_alias"] == alias),
        {},
    )
    patches = record.get("patches") or []
    return {
        "skill": alias,
        "upstream_name": entry.get("upstream_name", alias),
        "status": record.get("status", "MISSING"),
        "runtime": record.get("runtime", ""),
        "pinned_version": record.get("pinned_version"),
        "patch": record["patches"][-1]["patch_version"] if patches else "",
        "produces": record.get("produces", []),
        "requires": record.get("requires", []),
    }


def status(*, provider: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    provider = provider or load_manifest()
    return [status_for(entry["local_alias"], provider=provider) for entry in provider.get("skills", [])]


def verify(*, provider: dict[str, Any] | None = None) -> dict[str, Any]:
    """安装完备性检查（§15/§16 的静态部分）。"""
    from . import registry as registry_mod

    provider = provider or load_manifest()
    repo = provider.get("repository") or {}
    report: dict[str, Any] = {
        "provider_id": provider.get("provider_id"),
        "commit_sha": repo.get("commit_sha"),
        "license": repo.get("license"),
        "skills": [],
        "ok": True,
    }
    allowed = set((registry_mod.load_allowlist() or {}).get("skills") or [])
    for entry in provider.get("skills", []):
        info = status_for(entry["local_alias"], provider=provider)
        expected_patch = str(entry.get("patch") or "")
        problems = []
        if info["status"] not in ("APPROVED", "PATCHED"):
            problems.append(f"status={info['status']}")
        if not info["pinned_version"]:
            problems.append("未 pin")
        if expected_patch and info["patch"] != expected_patch:
            problems.append(f"patch={info['patch']}，期望 {expected_patch}")
        if not info["produces"]:
            problems.append("无 produces 契约")
        if info["skill"] not in allowed:
            problems.append("未加入 allowlist")
        info["problems"] = problems
        report["ok"] = report["ok"] and not problems
        report["skills"].append(info)
    return report
