from __future__ import annotations

from typing import Any

from .skill_loader import declared_artifact_types


def build_context(
    *,
    task: str,
    skill_record: dict[str, Any],
    artifacts: dict[str, Any],
    project_rules: str = "",
    constraints: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    output_schema: dict[str, Any] | None = None,
    extra_allowed: list[str] | None = None,
) -> dict[str, Any]:
    allowed = set(declared_artifact_types(skill_record)) | set(extra_allowed or [])
    inputs: dict[str, Any] = {}
    excluded: list[str] = []
    for artifact_type, content in artifacts.items():
        if artifact_type in allowed:
            inputs[artifact_type] = content
        else:
            excluded.append(artifact_type)
    context: dict[str, Any] = {
        "task": task,
        "skill": skill_record.get("name"),
        "inputs": inputs,
        "project_rules": project_rules,
        "constraints": constraints or {},
        "output_schema": output_schema,
        "evidence": evidence or [],
    }
    context["_minimal_context_report"] = {
        "allowed": sorted(allowed),
        "included": sorted(inputs.keys()),
        "excluded_count": len(excluded),
        "excluded_samples": sorted(excluded)[:10],
    }
    return context


def context_report(context: dict[str, Any]) -> dict[str, Any]:
    return dict(context.get("_minimal_context_report", {}))
