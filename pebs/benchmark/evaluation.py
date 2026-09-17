"""M6 §30–§34 / §62：人工评价入口。

人工评分必须以 Artifact 形式落库（对话/评分不是系统状态，产物才是），
并同步更新 `registry/performance.json`（§19/§40 要求绑定 skill 版本）。
"""

from __future__ import annotations

from typing import Any

from .. import config
from ..store import now_iso

RUBRIC_DIMENSIONS = (
    "subject_accuracy",
    "teaching_logic",
    "goal_clarity",
    "content_alignment",
    "concept_clarity",
    "case_quality",
    "executability",
    "student_engagement",
    "cognitive_challenge",
    "assessment_design",
    "language_naturalness",
    "visual_necessity",
    "coherence",
    "teacher_usability",
)
OPTIONAL_DIMENSIONS = ("spoken_naturalness",)
EDIT_CATEGORIES = (
    "fact correction",
    "teaching restructure",
    "tone edit",
    "case replacement",
    "media correction",
    "assessment correction",
    "template correction",
)
EDIT_SEVERITIES = ("S0", "S1", "S2", "S3", "S4", "S5")


def validate_eval(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(payload.get("reviewer") or "").strip():
        errors.append("必须提供 reviewer（至少一位真实教师）")
    scores = payload.get("scores") or {}
    if not isinstance(scores, dict) or not scores:
        errors.append("必须提供 scores")
    else:
        for dimension, value in scores.items():
            if dimension not in RUBRIC_DIMENSIONS + OPTIONAL_DIMENSIONS:
                errors.append(f"未知评分维度：{dimension}")
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                errors.append(f"{dimension} 不是数字：{value}")
                continue
            if not 1 <= numeric <= 5:
                errors.append(f"{dimension} 超出 1–5：{value}")
    if not str(payload.get("comment") or "").strip():
        errors.append("必须提供 comment（文字备注，不能只有数字）")
    edits = payload.get("edits") or {}
    for entry in edits.get("items", []) if isinstance(edits, dict) else []:
        if entry.get("category") and entry["category"] not in EDIT_CATEGORIES:
            errors.append(f"未知修改类别：{entry['category']}")
        if entry.get("severity") and entry["severity"] not in EDIT_SEVERITIES:
            errors.append(f"未知严重度：{entry['severity']}")
    return errors


def overall_score(payload: dict[str, Any]) -> float | None:
    scores = [float(value) for value in (payload.get("scores") or {}).values() if value is not None]
    return round(sum(scores) / len(scores), 3) if scores else None


def record(engine: Any, payload: dict[str, Any], *, run_id: str = "", mode: str = "") -> dict[str, Any]:
    from . import metrics

    errors = validate_eval(payload)
    if errors:
        raise ValueError("；".join(errors))
    edits = payload.get("edits") or {}
    generated = str(edits.get("generated_text") or "")
    edited = str(edits.get("edited_text") or "")
    ratio = None
    if generated and edited:
        ratio = metrics.teacher_edit_ratio(generated, edited)["edit_ratio"]
    elif edits.get("edit_ratio") is not None:
        ratio = float(edits["edit_ratio"])
    severity_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for entry in edits.get("items", []):
        severity = str(entry.get("severity") or "")
        category = str(entry.get("category") or "")
        if severity:
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1
    content = {
        "reviewer": payload["reviewer"],
        "role": str(payload.get("role") or "teacher"),
        "scores": {key: float(value) for key, value in (payload.get("scores") or {}).items()},
        "overall": overall_score(payload),
        "comment": payload.get("comment", ""),
        "must_fix": list(payload.get("must_fix") or []),
        "nice_to_have": list(payload.get("nice_to_have") or []),
        "edit_ratio": ratio,
        "major_edit_rate": (
            round((severity_counts.get("S4", 0) + severity_counts.get("S5", 0)) / max(sum(severity_counts.values()), 1), 3)
            if severity_counts
            else None
        ),
        "edit_severities": severity_counts,
        "edit_categories": category_counts,
        "evidence_errors": int(payload.get("evidence_errors") or 0),
        "routing_errors": int(payload.get("routing_errors") or 0),
        "plan_errors": int(payload.get("plan_errors") or 0),
        "run_id": run_id,
        "mode": mode,
        "created_at": now_iso(),
        "rubric": "benchmarks/rubrics/human_eval.yaml",
    }
    info = engine.store.add_revision(
        artifact_id="human_eval",
        artifact_type="review_record",
        content=content,
        produced_by=f"teacher:{payload['reviewer']}",
        rules_version=config.RULES_VERSION,
    )
    engine.store.set_accepted("human_eval", info["revision_id"])
    return content


def latest(engine: Any) -> dict[str, Any] | None:
    return engine.store.accepted_content("human_eval")


def update_performance(engine: Any, trace: dict[str, Any], human: dict[str, Any]) -> None:
    """把人工结果绑定到 skill 版本（§40）写入 performance registry。"""
    from . import performance

    score = human.get("overall")
    ratio = human.get("edit_ratio")
    for skill in trace.get("skills", []):
        status = skill.get("status")
        performance.record_run(
            skill=str(skill.get("skill")),
            version=str(skill.get("version") or ""),
            provider_sha=str(skill.get("upstream_sha") or ""),
            package_sha256=str(skill.get("package_sha256") or ""),
            patch=str(skill.get("patch") or ""),
            domain="",
            success=status == "SUCCEEDED",
            schema_failure=bool(skill.get("error") and "Schema" in str(skill.get("error"))),
            model_calls=0,
            latency=0.0,
            failure_mode=str(skill.get("error") or "")[:120] if status in ("FAILED", "BLOCKED") else "",
            human_score=score,
            edit_ratio=ratio,
        )
