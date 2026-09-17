from __future__ import annotations

from typing import Any

from . import intent, semantic

OUTPUT_SYNONYMS = {
    "docx": ["script", "lesson_plan", "worksheet"],
    "markdown": ["script", "lesson_plan", "worksheet"],
}

RESEARCH_HINTS = ["研究", "文献", "证据", "核验", "引用", "理论依据"]


def fallback_route(deterministic: dict[str, Any]) -> dict[str, Any]:
    requested = list(deterministic["requested_outputs"])
    if not requested and not deterministic.get("audit_only"):
        requested = ["script"]
    outputs = list(requested)
    for synonym, implied in OUTPUT_SYNONYMS.items():
        if synonym in outputs:
            outputs.extend(implied)
    knowledge_types = ["concept"] if any(item in outputs for item in ("script", "lesson_plan")) else []
    research_need = "VERIFY" if any(hint in str(deterministic) for hint in RESEARCH_HINTS) else "NONE"
    if deterministic.get("audit_only"):
        research_need = "VERIFY"
    media_need = "DIAGRAM" if "diagram" in outputs else "STATIC"
    return {
        "task_intent": "生成教学资材（确定性路由）",
        "primary_outputs": sorted(set(outputs)),
        "secondary_outputs": [],
        "delivery_mode": deterministic["delivery_mode"],
        "learner_profile": {},
        "sections": deterministic["sections"],
        "knowledge_types": knowledge_types,
        "research_need": research_need,
        "media_need": media_need,
        "assessment_need": "assessment" in outputs or "worksheet" in outputs,
        "requested_outputs": sorted(set(outputs)),
        "constraints": {
            "word_min": deterministic["word_min"],
            "word_max": deterministic["word_max"],
            "terminology": deterministic["terminology"],
            "required_components": deterministic["required_components"],
            "disallowed": deterministic["disallowed"],
            "no_animation": deterministic["no_animation"],
            "needs_ppt": "pptx" in outputs,
            "language": deterministic["language"],
            "explicit_skills": deterministic["explicit_skills"],
            "template_present": deterministic["template_present"],
            "audit_only": bool(deterministic.get("audit_only")),
        },
        "risk_flags": [],
        "confidence": 0.4,
        "uncertainties": ["LLM 语义层不可用，使用确定性回退路由"],
        "source": "deterministic_fallback",
        "provenance": {"deterministic": deterministic, "llm": None},
    }


def _coerce_outputs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    allowed = set(semantic.KNOWLEDGE_TYPES) | {
        "script",
        "lesson_plan",
        "worksheet",
        "case",
        "assessment",
        "pptx",
        "docx",
        "markdown",
        "diagram",
        "storyboard",
    }
    return [str(item) for item in raw if str(item) in allowed]


def merge(deterministic: dict[str, Any], llm_data: dict[str, Any] | None) -> dict[str, Any]:
    base = fallback_route(deterministic)
    if not llm_data:
        return base

    delivery = str(llm_data.get("delivery_mode") or base["delivery_mode"])
    if delivery not in {"asynchronous_video", "live_class", "workshop", "blended", "document_only"}:
        delivery = base["delivery_mode"]

    knowledge_types = [item for item in llm_data.get("knowledge_types", []) if item in semantic.KNOWLEDGE_TYPES]
    research_need = str(llm_data.get("research_need") or base["research_need"]).upper()
    if research_need not in {"NONE", "VERIFY", "LITERATURE", "DEEP"}:
        research_need = base["research_need"]
    media_need = str(llm_data.get("media_need") or base["media_need"]).upper()
    if media_need not in {"NONE", "STATIC", "DIAGRAM", "ANIMATION_CANDIDATE"}:
        media_need = base["media_need"]

    requested = _coerce_outputs(llm_data.get("requested_outputs")) or base["requested_outputs"]
    requested = sorted(set(requested) | set(deterministic["requested_outputs"]))

    constraints = dict(base["constraints"])
    constraints["no_animation"] = bool(constraints["no_animation"] or deterministic["no_animation"])
    if deterministic["no_ppt"]:
        requested = [item for item in requested if item != "pptx"]
        constraints["needs_ppt"] = False
    if "pptx" in requested and not constraints["no_animation"]:
        constraints["needs_ppt"] = True
    if constraints["no_animation"] and media_need == "ANIMATION_CANDIDATE":
        media_need = "DIAGRAM"

    confidence = llm_data.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = min(max(confidence, 0.0), 1.0)

    uncertainties = [str(item) for item in llm_data.get("uncertainties", []) if str(item).strip()]
    return {
        "task_intent": str(llm_data.get("task_intent") or base["task_intent"]),
        "primary_outputs": sorted(set(_coerce_outputs(llm_data.get("primary_outputs")) or requested)),
        "secondary_outputs": sorted(set(_coerce_outputs(llm_data.get("secondary_outputs")))),
        "delivery_mode": delivery,
        "learner_profile": llm_data.get("learner_profile") or {},
        "sections": deterministic["sections"],
        "knowledge_types": knowledge_types or base["knowledge_types"],
        "research_need": research_need,
        "media_need": media_need,
        "assessment_need": bool(llm_data.get("assessment_need", base["assessment_need"])),
        "requested_outputs": requested,
        "constraints": constraints,
        "risk_flags": [str(item) for item in llm_data.get("risk_flags", []) if str(item).strip()],
        "confidence": confidence,
        "uncertainties": uncertainties,
        "source": "hybrid",
        "provenance": {"deterministic": deterministic, "llm": llm_data},
    }
