from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import registry, skills_mgr


class SkillRuntimeBlocked(Exception):
    pass


@dataclass
class LoadedSkill:
    name: str
    version: str
    path: Path
    skill_md: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    references: list[str] = field(default_factory=list)

    def reference(self, relative: str) -> str:
        target = (self.path / relative).resolve()
        base = self.path.resolve()
        if base not in target.parents and target != base:
            raise SkillRuntimeBlocked(f"reference 路径越界：{relative}")
        if not target.is_file():
            raise SkillRuntimeBlocked(f"reference 不存在：{relative}")
        return target.read_text(encoding="utf-8")


def _find(root: Path, filename: str) -> Path | None:
    direct = root / filename
    if direct.exists():
        return direct
    for candidate in root.rglob(filename):
        return candidate
    return None


def load(name: str) -> LoadedSkill:
    try:
        runtime = skills_mgr.resolve_runtime(name)
    except skills_mgr.SkillError as exc:
        raise SkillRuntimeBlocked(f"skill 运行时不满足（review/pin/patch）：{exc}") from exc
    path = Path(runtime["path"])
    if not path.exists():
        raise SkillRuntimeBlocked(f"skill 目录不存在：{path}")
    root = path
    if not (root / "SKILL.md").exists() and not (root / "skill.yaml").exists():
        children = [child for child in root.iterdir() if child.is_dir()]
        if len(children) == 1:
            root = children[0]
    loaded = LoadedSkill(name=name, version=runtime["version"], path=root)
    skill_md = _find(root, "SKILL.md")
    if skill_md:
        loaded.skill_md = skill_md.read_text(encoding="utf-8", errors="replace")
    manifest_path = _find(root, "skill.yaml")
    if manifest_path:
        import yaml

        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise SkillRuntimeBlocked(f"skill.yaml 解析失败：{exc}") from exc
        if isinstance(manifest, dict):
            loaded.manifest = manifest
    schema_path = _find(root, "schema.json")
    if schema_path:
        import json

        try:
            loaded.output_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SkillRuntimeBlocked(f"schema.json 解析失败：{exc}") from exc
    references_dir = root / "references"
    if references_dir.is_dir():
        loaded.references = sorted(
            str(item.relative_to(root)) for item in references_dir.rglob("*") if item.is_file()
        )
    return loaded


def instruction_text(loaded: LoadedSkill, *, max_chars: int = 12000) -> str:
    parts = []
    if loaded.skill_md.strip():
        parts.append(loaded.skill_md.strip()[:max_chars])
    elif loaded.manifest.get("instructions"):
        parts.append(str(loaded.manifest["instructions"])[:max_chars])
    elif loaded.manifest.get("description"):
        parts.append(str(loaded.manifest["description"])[:max_chars])
    for relative in loaded.manifest.get("load_references", []) or []:
        try:
            parts.append(f"【参考：{relative}】\n" + loaded.reference(str(relative))[:4000])
        except SkillRuntimeBlocked:
            continue
    if not parts:
        raise SkillRuntimeBlocked(f"skill 没有任何指令内容：{loaded.name}")
    return "\n\n".join(parts)


def declared_artifact_types(skill_record: dict[str, Any]) -> list[str]:
    return list(skill_record.get("requires", [])) + list(skill_record.get("optional_requires", []))


def output_artifact_type(skill_record: dict[str, Any]) -> str | None:
    produces = list(skill_record.get("produces", []))
    return produces[0] if produces else None


def schema_for(skill_record: dict[str, Any]) -> tuple[str | None, str | None]:
    artifact_type = output_artifact_type(skill_record)
    if artifact_type is None:
        return None, None
    return registry.ARTIFACT_SCHEMAS.get(artifact_type), artifact_type
