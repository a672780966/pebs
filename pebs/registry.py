from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config

CONTRACT_FIELDS = [
    "name",
    "version",
    "domain",
    "description",
    "status",
    "invocation",
    "requires",
    "produces",
    "optional_requires",
    "input_schema",
    "output_schema",
    "provider",
    "tools",
    "risk_level",
    "network",
    "filesystem",
    "external_side_effects",
    "runtime",
    "handler",
    "gates_before",
    "gates_after",
    "parallelizable",
    "estimated_cost",
]

STATUSES = {"APPROVED", "PATCHED", "REFERENCE_ONLY", "DISABLED", "ACTION_ONLY", "SANDBOX_ONLY"}
RUNTIMES = {"builtin", "prompt_skill", "external_skill", "sandbox_skill"}

ARTIFACT_SCHEMAS: dict[str, str] = {
    "template_spec": "template_spec",
    "materials": "materials",
    "requirements": "requirements",
    "learning_design": "learning_design",
    "claims_set": "claims_set",
    "evidence_index": "evidence_index",
    "teaching_plan": "teaching_plan",
    "lesson_plan": "lesson_plan",
    "case": "case",
    "assessment": "assessment",
    "worksheet": "worksheet",
    "script": "script",
    "media_plan": "media_plan",
    "diagrams": "diagrams",
    "animation_decisions": "animation_decisions",
    "storyboard": "storyboard",
    "load_review": "load_review",
    "evidence_assets": "evidence_assets",
    "slide_plan": "slide_plan",
    "pptx_deck": "pptx_deck",
    "gate_result": "gate_result",
    "preview": "preview",
    "export_manifest": "export_manifest",
    "skill_invocations": "skill_invocations",
    "build_plan": "build_plan",
    "build_plan_v2": "build_plan_v2",
    "router_result": "router_result",
    "review_record": "signoff",
}


class RegistryError(Exception):
    pass


def _skills_path() -> Path:
    return Path(config.REGISTRY_DIR) / "skills.json"


def load_skills() -> dict[str, Any]:
    path = _skills_path()
    if not path.exists():
        raise RegistryError(f"skills registry missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_allowlist() -> dict[str, Any]:
    path = Path(config.REGISTRY_DIR) / "allowlist.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"skills": []}


def load_denylist() -> dict[str, Any]:
    path = Path(config.REGISTRY_DIR) / "denylist.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"skills": [], "prefixes": []}


def get(name: str) -> dict[str, Any] | None:
    return load_skills().get(name)


def resolve_alias(name: str) -> str | None:
    for skill_name, record in load_skills().items():
        if skill_name == name or name in record.get("aliases", []):
            return skill_name
    return None


def is_denied(name: str) -> bool:
    denylist = load_denylist()
    if name in denylist.get("skills", []):
        return True
    return any(name.startswith(prefix) for prefix in denylist.get("prefixes", []))


def handler_steps(skill_name: str) -> list[str]:
    record = get(skill_name)
    if record is None:
        return []
    return list(record.get("handler", {}).get("steps", []))


def explicit_skill_map() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for name, record in load_skills().items():
        invocation = record.get("invocation", {})
        if not invocation.get("explicit"):
            continue
        steps = list(record.get("handler", {}).get("steps", []))
        mapping[name] = steps
        for alias in record.get("aliases", []):
            mapping[alias] = steps
    return mapping


def validate(skills: dict[str, Any] | None = None) -> list[str]:
    skills = skills or load_skills()
    errors: list[str] = []
    for name, record in skills.items():
        for field in CONTRACT_FIELDS:
            if field not in record:
                errors.append(f"{name}: missing contract field '{field}'")
        if record.get("name") != name:
            errors.append(f"{name}: name field mismatch")
        if record.get("status") not in STATUSES:
            errors.append(f"{name}: invalid status {record.get('status')}")
        runtime = record.get("runtime")
        if runtime not in RUNTIMES:
            errors.append(f"{name}: invalid runtime {runtime}")
        handler = record.get("handler") or {}
        if runtime == "builtin":
            if not handler.get("builtin_function") or not handler.get("steps"):
                errors.append(f"{name}: builtin skill must declare builtin_function and steps")
        elif runtime in ("external_skill", "prompt_skill", "sandbox_skill"):
            if not handler.get("skill_path"):
                errors.append(f"{name}: non-builtin skill must declare handler.skill_path")
        for artifact_type in list(record.get("requires", [])) + list(record.get("produces", [])) + list(
            record.get("optional_requires", [])
        ):
            if artifact_type not in ARTIFACT_SCHEMAS:
                errors.append(f"{name}: unknown artifact type '{artifact_type}'")
        emits = list(record.get("emits", []))
        for artifact_type in emits:
            if artifact_type not in ARTIFACT_SCHEMAS:
                errors.append(f"{name}: unknown emitted artifact type '{artifact_type}'")
        missing_emits = [t for t in record.get("produces", []) if t not in (emits or record.get("produces", []))]
        if emits and missing_emits:
            errors.append(f"{name}: emits must include every produced type (missing {missing_emits})")
        if record.get("invocation", {}).get("auto") and record.get("status") not in ("APPROVED", "PATCHED"):
            errors.append(f"{name}: auto-invocable skill must be APPROVED/PATCHED (status={record.get('status')})")
        from .agents.kinds import AGENT_NAMES

        if record.get("agent") not in AGENT_NAMES:
            errors.append(f"{name}: invalid or missing subagent '{record.get('agent')}'")
        from . import policies

        errors.extend(policies.check_skill_record(record))
    return errors


def build_runtime_index(skills: dict[str, Any] | None = None) -> dict[str, Any]:
    skills = skills or load_skills()
    index: dict[str, Any] = {"format": 1, "skills": {}}
    for name, record in sorted(skills.items()):
        index["skills"][name] = {
            "runtime": record.get("runtime"),
            "status": record.get("status"),
            "agent": record.get("agent"),
            "handler": record.get("handler"),
            "requires": record.get("requires", []),
            "produces": record.get("produces", []),
            "optional_requires": record.get("optional_requires", []),
            "invocation": record.get("invocation", {}),
            "aliases": record.get("aliases", []),
            "parallelizable": record.get("parallelizable", False),
            "estimated_cost": record.get("estimated_cost", {}),
            "gates_before": record.get("gates_before", []),
            "gates_after": record.get("gates_after", []),
        }
    return index


def runtime_index_path() -> Path:
    return Path(config.REGISTRY_DIR) / "runtime_index.json"


def write_runtime_index() -> Path:
    path = runtime_index_path()
    path.write_text(json.dumps(build_runtime_index(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def runtime_index() -> dict[str, Any]:
    path = runtime_index_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return build_runtime_index()


def search(
    *,
    query: str | None = None,
    domain: str | None = None,
    requires: list[str] | None = None,
    produces: list[str] | None = None,
    status: str | None = None,
    risk: str | None = None,
    runtime: str | None = None,
) -> list[dict[str, Any]]:
    results = []
    for name, record in load_skills().items():
        if domain and record.get("domain") != domain:
            continue
        if status and record.get("status") != status:
            continue
        if risk and record.get("risk_level") != risk:
            continue
        if runtime and record.get("runtime") != runtime:
            continue
        if requires and not set(requires).issubset(set(record.get("requires", [])) | set(record.get("optional_requires", []))):
            continue
        if produces and not set(produces).issubset(set(record.get("produces", []))):
            continue
        if query:
            haystack = " ".join(
                [name, str(record.get("description", "")), " ".join(record.get("produces", [])), " ".join(record.get("requires", []))]
            ).lower()
            tokens = [token for token in query.lower().split() if token]
            if tokens and not any(token in haystack for token in tokens):
                continue
        results.append({"name": name, **record})
    return results


def producers_of(artifact_type: str) -> list[str]:
    return sorted(
        name for name, record in load_skills().items() if artifact_type in record.get("produces", [])
    )


def consumers_of(artifact_type: str) -> list[str]:
    return sorted(
        name
        for name, record in load_skills().items()
        if artifact_type in record.get("requires", []) or artifact_type in record.get("optional_requires", [])
    )


def parse_explicit_skills(request: str) -> list[str]:
    found = re.findall(r"(?:^|\s)/([a-z][a-z0-9\-]{2,40})(?![\w/\-])", request or "")
    return sorted(dict.fromkeys(found))
