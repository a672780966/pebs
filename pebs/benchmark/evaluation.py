"""M6 §30–§34 / §62：人工评价入口。

人工评分必须以 Artifact 形式落库（对话/评分不是系统状态，产物才是），
并同步更新 `registry/performance.json`（§19/§40 要求绑定 skill 版本）。
"""

from __future__ import annotations

import json
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
        "created_at": now_iso(),        "rubric": "benchmarks/rubrics/human_eval.yaml",
    }
    info = engine.store.add_revision(
        artifact_id="human_eval",
        artifact_type="review_record",
        content=content,
        produced_by=f"teacher:{payload['reviewer']}",
        rules_version=config.RULES_VERSION,
    )
    engine.store.set_accepted("human_eval", info["revision_id"])
    # §40：评分必须绑定到具体 skill 版本，否则升级后历史数据失效。
    # 之前 update_performance 只在测试里被调用，真实提交（CLI/API）从不更新 registry。
    if run_id:
        try:
            from . import trace as trace_mod

            skill_trace = trace_mod.build_trace(engine, run_id, mode=mode)
            update_performance(engine, skill_trace, content)
        except Exception:  # noqa: BLE001 - 评分本身已落库；绑定失败不应吞掉评分
            pass
    return content


def export_kit(runs: list[dict[str, Any]] | None = None, *, directory: Any = None) -> list[dict[str, Any]]:
    """§30/§31：把待评课程导出成教师可直接阅读的材料包 + 评分表。

    教师不需要运行 PEBS：每个 run 一个目录，含 course.md（关键产物）、run.json 摘要与
    human_eval.yaml（待填）。
    """
    from pathlib import Path

    from ..store import Store
    from . import report as report_mod

    runs = runs if runs is not None else report_mod.load_runs()
    target_dir = Path(directory) if directory else (Path(__file__).resolve().parents[2] / "benchmarks" / "reports" / "evaluation_kit")
    target_dir.mkdir(parents=True, exist_ok=True)
    exported: list[dict[str, Any]] = []
    for run in runs:
        project_id = str(run.get("project_id") or "")
        if not project_id:
            continue
        case_id = str(run.get("case_id") or "?")
        variant = str(run.get("_variant") or run.get("mode") or "?")
        slug = f"{case_id}-{variant}".replace(" ", "").replace("[", "").replace("]", "").replace("+", "_")
        base = target_dir / slug
        base.mkdir(parents=True, exist_ok=True)
        try:
            store = Store(project_id, config.project_dir(project_id))
        except Exception:  # noqa: BLE001 - 项目已被清理时跳过
            continue
        lines = [
            f"# {case_id} / {variant}",
            "",
            f"- run: {run.get('run_id')} status={run.get('run_status')}",
            f"- 模式：{run.get('mode')} 实验：{run.get('experiment') or '（无）'}",
            f"- 模型调用：{(run.get('metrics') or {}).get('model_calls')} 研究请求：{(run.get('metrics') or {}).get('research_calls')}",
            f"- 证据政策：{run.get('evidence_policy')}",
            "",
            "> 评分说明见同目录 human_eval.yaml 与 benchmarks/reports/evaluation_kit/README.md",
            "",
        ]
        for artifact_id in (
            "lesson_plan:sec1", "lesson_plan:sec2", "lesson_plan:sec3", "lesson_plan:sec4",
            "script:sec1", "script:sec2", "script:sec3", "script:sec4",
            "slide_plan", "pptx_deck", "assessment:sec1", "case:sec1:1",
        ):
            content = store.accepted_content(artifact_id)
            if content is None:
                continue
            lines.append(f"## {artifact_id}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(content, ensure_ascii=False, indent=2)[:20000])
            lines.append("```")
            lines.append("")
        (base / "course.md").write_text("\n".join(lines), encoding="utf-8")
        (base / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        worksheets = report_mod.write_worksheets([run], directory=base)
        exported.append({"case_id": case_id, "variant": variant, "dir": str(base), "worksheet": str(worksheets[0]) if worksheets else ""})
        store.close()
    return exported


def latest(engine: Any) -> dict[str, Any] | None:
    return engine.store.accepted_content("human_eval")


def update_performance(engine: Any, trace: dict[str, Any], human: dict[str, Any]) -> None:
    """把人工结果绑定到 skill 版本（§40）写入 performance registry。"""
    from . import performance

    performance.record_trace(
        trace,
        human_score=human.get("overall"),
        edit_ratio=human.get("edit_ratio"),
    )
