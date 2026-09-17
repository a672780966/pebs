"""Benchmark Report（M6 §42）：Direct Codex / Builtin / Dynamic 对比表。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import cases

COLUMNS = ("direct_codex", "builtin", "dynamic", "mixed")

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


def quality_score(record: dict[str, Any]) -> float | None:
    """把 §31 的 14 维 1–5 分（含 §54 spoken naturalness 可选维度）平均。"""
    scores = record.get("scores") or {}
    values = [float(value) for key, value in scores.items() if key in RUBRIC_DIMENSIONS + ("spoken_naturalness",)]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def load_runs(runs_dir: Path | None = None) -> list[dict[str, Any]]:
    """每个 (case, mode) 只取最新一次 run（重试不累加指标），并保留状态与证据政策。"""
    directory = runs_dir or cases.runs_dir()
    if not directory.exists():
        return []
    latest: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
    for path in sorted(directory.glob("*/run.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        key = (str(record.get("case_id")), str(record.get("mode")))
        mtime = path.stat().st_mtime
        if key not in latest or mtime >= latest[key][0]:
            record["_run_json"] = str(path)
            latest[key] = (mtime, record)
    return [item[1] for item in sorted(latest.values(), key=lambda pair: (pair[1].get("case_id", ""), pair[1].get("mode", "")))]


def _row_for(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("metrics") or {}
    human = run.get("human_eval") or {}
    return {
        "run_id": run.get("run_id"),
        "case_id": run.get("case_id"),
        "mode": run.get("mode"),
        "status": run.get("run_status"),
        "evidence_policy": run.get("evidence_policy"),
        "human_score": quality_score(human) if human else None,
        "edit_ratio": human.get("edit_ratio"),
        "major_edit_rate": human.get("major_edit_rate"),
        "evidence_errors": human.get("evidence_errors"),
        "routing_errors": human.get("routing_errors"),
        "plan_errors": human.get("plan_errors"),
        "model_calls": metrics.get("model_calls"),
        "research_calls": metrics.get("research_calls"),
        "runtime_seconds": metrics.get("wall_time_seconds") or run.get("wall_time_seconds"),
        "skill_failure_rate": metrics.get("skill_failure_rate"),
        "locality_preservation_rate": metrics.get("locality_preservation_rate"),
        "automatic_issues": len((run.get("automatic_issues") or {}).get("issues", [])),
    }


def summarize(runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    runs = runs if runs is not None else load_runs()
    rows = [_row_for(run) for run in runs]
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(str(row.get("case_id")), []).append(row)

    table: list[dict[str, Any]] = []
    for case_id in sorted(by_case):
        entry: dict[str, Any] = {"case_id": case_id}
        for mode in COLUMNS:
            matching = [row for row in by_case[case_id] if row["mode"] == mode]
            if not matching:
                entry[mode] = None
                continue
            entry[mode] = {
                "status": matching[-1].get("status"),
                "evidence_policy": matching[-1].get("evidence_policy"),
                "human_score": _mean(row["human_score"] for row in matching),
                "edit_ratio": _mean(row["edit_ratio"] for row in matching),
                "major_edit_rate": _mean(row["major_edit_rate"] for row in matching),
                "evidence_errors": _sum(row["evidence_errors"] for row in matching),
                "routing_errors": _sum(row["routing_errors"] for row in matching),
                "plan_errors": _sum(row["plan_errors"] for row in matching),
                "model_calls": _sum(row["model_calls"] for row in matching),
                "runtime_seconds": _sum(row["runtime_seconds"] for row in matching),
                "automatic_issues": _sum(row["automatic_issues"] for row in matching),
                "runs": len(matching),
            }
        table.append(entry)
    return {"generated_at": _now(), "cases": table, "runs": len(rows), "rows": rows}


def _mean(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers) / len(numbers), 3) if numbers else None


def _sum(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers), 3) if numbers else None


def _now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# M6 Benchmark Summary",
        "",
        f"生成时间：{summary.get('generated_at')}；run 数（每 case×mode 取最新）：{summary.get('runs', 0)}",
        "",
        "| Case | Mode | Status | Human Score | Edit Ratio | Evidence Errors | Routing Errors | Plan Errors | Model Calls | Runtime(s) | Auto Issues |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in summary.get("cases", []):
        for mode in COLUMNS:
            entry = case.get(mode)
            if not entry:
                continue
            lines.append(
                "| {case} | {mode} | {status} | {human} | {edit} | {evidence} | {routing} | {plan} | {calls} | {runtime} | {issues} |".format(
                    case=case["case_id"],
                    mode=mode,
                    status=entry.get("status"),
                    human=entry.get("human_score"),
                    edit=entry.get("edit_ratio"),
                    evidence=entry.get("evidence_errors"),
                    routing=entry.get("routing_errors"),
                    plan=entry.get("plan_errors"),
                    calls=entry.get("model_calls"),
                    runtime=entry.get("runtime_seconds"),
                    issues=entry.get("automatic_issues"),
                )
            )
    lines.append("")
    return "\n".join(lines)


def write_report(summary: dict[str, Any] | None = None, *, path: Path | None = None) -> Path:
    summary = summary or summarize()
    target = path or (cases.reports_dir() / "benchmark_summary.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(summary), encoding="utf-8")
    (target.parent / "benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target
