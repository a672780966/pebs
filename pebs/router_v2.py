from __future__ import annotations

from typing import Any

from .routing import fallback, intent, semantic

__all__ = ["route", "validate", "extract_deterministic"]


def extract_deterministic(request: str, **kwargs: Any) -> dict[str, Any]:
    return intent.extract_deterministic(request, **kwargs)


def route(
    request: str,
    *,
    llm: Any,
    template_spec: dict[str, Any] | None = None,
    materials: list[str] | None = None,
    explicit_skills: list[str] | None = None,
    existing_artifacts: list[dict[str, Any]] | None = None,
    project_rules: str = "",
) -> dict[str, Any]:
    deterministic = intent.extract_deterministic(
        request,
        template_spec=template_spec,
        materials=materials,
        explicit_skills=explicit_skills,
    )
    context = {
        "existing_artifacts": [
            {"artifact_id": item.get("artifact_id"), "type": item.get("artifact_type"), "stale": bool(item.get("stale"))}
            for item in (existing_artifacts or [])
        ],
        "project_rules": project_rules,
    }
    llm_data = semantic.classify(llm, request, deterministic, context)
    result = fallback.merge(deterministic, llm_data)
    result["provenance"]["context"] = {
        "existing_artifacts": len(existing_artifacts or []),
        "materials": len(materials or []),
        "template_present": deterministic["template_present"],
        "project_rules_chars": len(project_rules or ""),
    }
    return result


def validate(result: dict[str, Any]) -> list[str]:
    from . import schemas

    try:
        schemas.validate(result, "router_result")
    except schemas.SchemaError as exc:
        return [str(exc)]
    errors: list[str] = []
    constraints = result.get("constraints", {})
    if constraints.get("no_animation") and result.get("media_need") == "ANIMATION_CANDIDATE":
        errors.append("no_animation 与 media_need=ANIMATION_CANDIDATE 冲突")
    if constraints.get("no_ppt") and "pptx" in result.get("requested_outputs", []):
        errors.append("no_ppt 与 requested_outputs 含 pptx 冲突")
    if not result.get("requested_outputs"):
        errors.append("requested_outputs 为空")
    return errors
