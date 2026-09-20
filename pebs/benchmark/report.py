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


def _run_order_key(path: Path) -> tuple[str, float]:
    """§41：run 的先后顺序取自 run 目录名里的时间戳，而不是文件 mtime。

    复评工具（tools/reevaluate_checks.py）会重写 run.json，mtime 一变，
    "最新一次成功 run"就会漂移，报告与教师工作表会指向另一个产物。"""
    stamp = path.parent.name.split("-", 2)[:2]
    if len(stamp) == 2 and stamp[0].isdigit() and stamp[1].isdigit():
        return ("-".join(stamp), path.stat().st_mtime)
    return ("", path.stat().st_mtime)


def load_runs(runs_dir: Path | None = None) -> list[dict[str, Any]]:
    """每个 (case, mode, experiment) 取一个代表 run，并统计尝试次数与成功次数。

    真实运行的证据核验存在模型波动：同一 case 可能一次 succeeded、一次 blocked。
    只显示"最新一次"会误导；因此代表 run 优先取最近的成功记录（没有成功记录才取最新），
    并附 attempts/succeeded 计数。"""
    directory = runs_dir or cases.runs_dir()
    if not directory.exists():
        return []
    grouped: dict[tuple[str, str, str], list[tuple[tuple[str, float], dict[str, Any]]]] = {}
    for path in sorted(directory.glob("*/run.json")):
        try:
            # 用 utf-8-sig 读取：Windows 上写出的 run.json 可能带 BOM，
            # 带 BOM 时 json.loads 会抛 JSONDecodeError，这个 run 就会从报告里静默消失。
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        # §46：Builtin / External / Hybrid 是不同实验，必须分行对比而不是互相覆盖
        key = (
            str(record.get("case_id")),
            str(record.get("mode")),
            str(record.get("experiment") or ""),
        )
        grouped.setdefault(key, []).append((_run_order_key(path), record))
    representatives: list[dict[str, Any]] = []
    for (case_id, mode, experiment), items in sorted(grouped.items()):
        items.sort(key=lambda pair: pair[0])
        succeeded = [pair for pair in items if pair[1].get("run_status") == "succeeded"]
        chosen = succeeded[-1][1] if succeeded else items[-1][1]
        chosen["_attempts"] = len(items)
        chosen["_succeeded"] = len(succeeded)
        chosen["_variant"] = f"{mode} [+{experiment}]" if experiment else mode
        representatives.append(chosen)
    return representatives


def _row_for(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("metrics") or {}
    human = run.get("human_eval") or {}
    return {
        "run_id": run.get("run_id"),
        "case_id": run.get("case_id"),
        "mode": run.get("mode"),
        "variant": run.get("_variant") or run.get("mode"),
        "experiment": run.get("experiment") or "",
        "status": run.get("run_status"),
        "attempts": run.get("_attempts", 1),
        "succeeded": run.get("_succeeded", 1 if run.get("run_status") == "succeeded" else 0),
        "evidence_policy": run.get("evidence_policy"),
        "human_score": quality_score(human) if human else None,
        "edit_ratio": human.get("edit_ratio"),
        "major_edit_rate": human.get("major_edit_rate"),
        "evidence_errors": human.get("evidence_errors"),
        "routing_errors": human.get("routing_errors"),
        "plan_errors": human.get("plan_errors"),
        "reviewer": human.get("reviewer"),
        "human_eval_run_id": human.get("run_id"),
        "human_eval_stale": bool(run.get("human_eval_stale")),
        "model_calls": metrics.get("model_calls"),
        "research_calls": metrics.get("research_calls"),
        "runtime_seconds": metrics.get("wall_time_seconds") or run.get("wall_time_seconds"),
        "skill_failure_rate": metrics.get("skill_failure_rate"),
        "schema_repair_rate": metrics.get("schema_repair_rate"),
        "locality_preservation_rate": metrics.get("locality_preservation_rate"),
        "automatic_issues": len((run.get("automatic_issues") or {}).get("issues", [])),
        # §35/§71-8：门禁 FAIL 与"自动问题"是两层，报告必须能同时看到，
        # 否则会出现"Auto Issues = 0 但 G6 FAIL"这种互相矛盾的行。
        "gate_fail": len([g for g in (run.get("trace") or {}).get("gates", []) if g.get("status") == "FAIL"]),
        "gate_review": len(
            [g for g in (run.get("trace") or {}).get("gates", []) if g.get("status") == "NEEDS_REVIEW"]
        ),
    }


def human_eval_for_run(run: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """§30/§33/§42：把项目里已接受的教师评分绑回它的 run。

    评分以 Artifact 形式落在项目 Store（`human_eval`），而不是 run.json；
    报告必须主动读回来，否则 Human Score / Edit Ratio / Evidence Errors 列永远是空的。
    返回 `(bound, stale)`：评分记录的 run_id 为空或与该 run 一致时是 bound；
    指向另一版产物时是 stale（仍然显示，但标明"评分针对另一版产物"，不静默丢弃）。
    """
    project_id = str(run.get("project_id") or "")
    if not project_id:
        return None, None
    try:
        from .. import config
        from ..store import Store

        base = config.project_dir(project_id)
        if not (base / "state.db").exists():
            return None, None
        store = Store(project_id, base)
    except Exception:  # noqa: BLE001 - 项目已被清理/不可读时视为未评分
        return None, None
    try:
        content = store.accepted_content("human_eval")
    except Exception:  # noqa: BLE001
        content = None
    finally:
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass
    if not isinstance(content, dict):
        return None, None
    bound_run = str(content.get("run_id") or "")
    if bound_run and bound_run != str(run.get("run_id") or ""):
        return None, content
    return content, None


def _with_human_eval(run: dict[str, Any]) -> dict[str, Any]:
    if run.get("human_eval") or run.get("human_eval_stale"):
        return run
    bound, stale = human_eval_for_run(run)
    if bound is None and stale is None:
        return run
    enriched = dict(run)
    if bound is not None:
        enriched["human_eval"] = bound
    if stale is not None:
        enriched["human_eval_stale"] = stale
    return enriched


def summarize(runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    runs = runs if runs is not None else load_runs()
    runs = [_with_human_eval(run) for run in runs]
    rows = [_row_for(run) for run in runs]
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(str(row.get("case_id")), []).append(row)

    table: list[dict[str, Any]] = []
    for case_id in sorted(by_case):
        entry: dict[str, Any] = {"case_id": case_id}
        variants: dict[str, list[dict[str, Any]]] = {}
        for row in by_case[case_id]:
            variants.setdefault(str(row.get("variant") or row["mode"]), []).append(row)
        for variant, matching in sorted(variants.items()):
            entry[variant] = {
                "status": matching[-1].get("status"),
                "attempts": matching[-1].get("attempts"),
                "succeeded": matching[-1].get("succeeded"),
                "evidence_policy": matching[-1].get("evidence_policy"),
                "human_score": _mean(row["human_score"] for row in matching),
                "edit_ratio": _mean(row["edit_ratio"] for row in matching),
                "major_edit_rate": _mean(row["major_edit_rate"] for row in matching),
                "evidence_errors": _sum(row["evidence_errors"] for row in matching),
                "routing_errors": _sum(row["routing_errors"] for row in matching),
                "plan_errors": _sum(row["plan_errors"] for row in matching),
                "model_calls": _sum(row["model_calls"] for row in matching),
                "runtime_seconds": _sum(row["runtime_seconds"] for row in matching),
                "skill_failure_rate": _mean(row["skill_failure_rate"] for row in matching),
                "schema_repair_rate": _mean(row["schema_repair_rate"] for row in matching),
                "locality_preservation_rate": _mean(row["locality_preservation_rate"] for row in matching),
                "automatic_issues": _sum(row["automatic_issues"] for row in matching),
                "gate_fail": _sum(row["gate_fail"] for row in matching),
                "gate_review": _sum(row["gate_review"] for row in matching),
                "reviewers": sorted({str(row["reviewer"]) for row in matching if row.get("reviewer")}),
                "human_eval_stale": any(row.get("human_eval_stale") for row in matching),
                "runs": len(matching),
            }
        table.append(entry)
    summary = {"generated_at": _now(), "cases": table, "runs": len(rows), "rows": rows}
    summary["mode_comparison"] = mode_comparison(summary)
    return summary


def _mean(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers) / len(numbers), 3) if numbers else None


def _sum(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers), 3) if numbers else None


def _now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def failure_category_section(runs: list[dict[str, Any]] | None = None) -> list[str]:
    """§65：把自动失败按 taxonomy 类别分布写进报告。

    只统计"当前代表 run"的自动问题；类别为空的 case 不占行。
    若出现不在 `failure_taxonomy.yaml` 里的 kind，单独列出（不静默丢弃）。
    """
    runs = runs if runs is not None else load_runs()
    totals: dict[str, int] = {}
    unknown: dict[str, list[str]] = {}
    for run in runs:
        automatic = run.get("automatic_issues") or {}
        for kind, count in (automatic.get("counts") or {}).items():
            totals[str(kind)] = totals.get(str(kind), 0) + int(count)
        for kind in automatic.get("unknown_categories") or []:
            unknown.setdefault(str(kind), []).append(str(run.get("case_id")))
    if not totals and not unknown:
        return []
    lines = ["", "## 失败类别分布（§65 failure taxonomy；仅统计代表 run 的自动问题）", ""]
    if totals:
        lines.append("| 类别 | 次数 |")
        lines.append("| --- | ---: |")
        for kind in sorted(totals, key=lambda item: (-totals[item], item)):
            lines.append(f"| {kind} | {totals[kind]} |")
        lines.append("")
    if unknown:
        lines.append("> ⚠ 以下 kind 不在 failure_taxonomy.yaml 中（分类无效）：")
        for kind, case_ids in sorted(unknown.items()):
            lines.append(f"> - {kind}（{ '、'.join(sorted(set(case_ids))) }）")
        lines.append("")
    return lines


def _gate_audit_section() -> list[str]:
    """§35 Gate FP/FN：读已生成的 gate_audit.json（重放昂贵，不在生成报告时重跑）。"""
    from . import gates_audit

    try:
        return gates_audit.section()
    except Exception:  # noqa: BLE001 - 审计缺失不应让报告生成失败
        return []


def _base_mode(variant: str) -> str:
    """把 `dynamic [+external-media]` 这类实验变体归回它的基础模式（§28/§46）。"""
    return variant.split(" ", 1)[0].strip() or variant


def mode_comparison(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """§42：Metric × Direct Codex / Builtin / Dynamic 汇总（每个基础模式一行）。

    Human Score 按 case 取均值（避免调用量大的 case 压过其他 case），
    计数类指标求和。混合模式（mixed）单独一行。
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    for case in summary.get("cases", []):
        for variant, entry in case.items():
            if variant == "case_id" or not isinstance(entry, dict):
                continue
            buckets.setdefault(_base_mode(str(variant)), []).append(entry)

    def mean(key: str, entries: list[dict[str, Any]]) -> float | None:
        values = [float(entry[key]) for entry in entries if entry.get(key) is not None]
        return round(sum(values) / len(values), 3) if values else None

    def total(key: str, entries: list[dict[str, Any]]) -> float | None:
        values = [float(entry[key]) for entry in entries if entry.get(key) is not None]
        return round(sum(values), 3) if values else None

    order = [mode for mode in COLUMNS if mode in buckets]
    order += sorted(mode for mode in buckets if mode not in COLUMNS)
    return {
        mode: {
            "variants": len(buckets[mode]),
            "human_score": mean("human_score", buckets[mode]),
            "edit_ratio": mean("edit_ratio", buckets[mode]),
            "evidence_errors": total("evidence_errors", buckets[mode]),
            "routing_errors": total("routing_errors", buckets[mode]),
            "plan_errors": total("plan_errors", buckets[mode]),
            "schema_repair_rate": mean("schema_repair_rate", buckets[mode]),
            "skill_failure_rate": mean("skill_failure_rate", buckets[mode]),
            "model_calls": total("model_calls", buckets[mode]),
            "runtime_seconds": total("runtime_seconds", buckets[mode]),
            "succeeded": total("succeeded", buckets[mode]),
            "attempts": total("attempts", buckets[mode]),
        }
        for mode in order
    }


def render_mode_comparison(summary: dict[str, Any]) -> list[str]:
    comparison = mode_comparison(summary)
    if not comparison:
        return []
    lines = [
        "",
        "## 模式对比（§42：Metric × Direct Codex / Builtin / Dynamic）",
        "",
        "| Metric | " + " | ".join(comparison) + " |",
        "| --- | " + " | ".join("---:" for _ in comparison) + " |",
    ]
    metrics = (
        ("Human Score（1–5 均值）", "human_score"),
        ("Teacher Edit Ratio（均值）", "edit_ratio"),
        ("Evidence Errors（合计）", "evidence_errors"),
        ("Routing Errors（合计）", "routing_errors"),
        ("Plan Errors（合计）", "plan_errors"),
        ("Skill Failure Rate（均值）", "skill_failure_rate"),
        ("Schema Repair Rate（均值）", "schema_repair_rate"),
        ("Model Calls（合计）", "model_calls"),
        ("Runtime(s)（合计）", "runtime_seconds"),
        ("Succeeded / Attempts", None),
    )
    for label, key in metrics:
        cells = []
        for mode in comparison:
            entry = comparison[mode]
            if key is None:
                cells.append(f"{entry.get('succeeded') or 0} / {entry.get('attempts') or 0}")
            else:
                cells.append("—" if entry.get(key) is None else str(entry.get(key)))
        lines.append("| " + label + " | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# M6 Benchmark Summary",
        "",
        f"生成时间：{summary.get('generated_at')}；run 数（每 case×mode 取最新）：{summary.get('runs', 0)}",
        "",
        "| Case | Variant | Status | Attempts | Human Score | Edit Ratio | Evidence Errors | Routing Errors | Plan Errors | Model Calls | Runtime(s) | Auto Issues | Gate FAIL/Review |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in summary.get("cases", []):
        for variant, entry in sorted(case.items()):
            if variant == "case_id" or not isinstance(entry, dict):
                continue
            note = ""
            if entry.get("human_eval_stale"):
                note = " ⚠评分针对另一版产物"
            reviewers = entry.get("reviewers") or []
            lines.append(
                "| {case} | {mode} | {status} | {attempts} | {human} | {edit} | {evidence} | {routing} | {plan} | {calls} | {runtime} | {issues} | {gates} |".format(
                    case=case["case_id"],
                    mode=variant,
                    status=entry.get("status"),
                    attempts=f"{entry.get('succeeded', 0)}/{entry.get('attempts', 1)}",
                    human=entry.get("human_score"),
                    edit=entry.get("edit_ratio"),
                    evidence=entry.get("evidence_errors"),
                    routing=entry.get("routing_errors"),
                    plan=entry.get("plan_errors"),
                    calls=entry.get("model_calls"),
                    runtime=entry.get("runtime_seconds"),
                    issues=entry.get("automatic_issues"),
                    gates=f"{entry.get('gate_fail') or 0}/{entry.get('gate_review') or 0}",
                )
            )
            if reviewers or note:
                lines.append(f"| | 教师：{('、'.join(reviewers)) or '—'}{note} | | | | | | | | | | | |")
    lines.extend(render_mode_comparison(summary))
    lines.extend(failure_category_section())
    lines.extend(_gate_audit_section())
    lines.extend(quality_section())
    lines.extend(performance_section())
    lines.append("")
    return "\n".join(lines)


def _worksheet_is_filled(data: dict[str, Any]) -> bool:
    """教师是否已经在这份工作表里填过东西（§30–§32）。"""
    if str(data.get("reviewer") or "").strip():
        return True
    if str(data.get("comment") or "").strip():
        return True
    if any(value is not None for value in (data.get("scores") or {}).values()):
        return True
    edits = data.get("edits") or {}
    if str(edits.get("generated_text") or "").strip() or str(edits.get("edited_text") or "").strip():
        return True
    return any(item.get("category") or item.get("severity") for item in (edits.get("items") or []))


def is_evaluable(run: dict[str, Any]) -> bool:
    """§30/§32：只有真正产出了课程产物的 run 才值得教师评分。

    失败的基线（0 产物）也生成工作表，会诱导教师给一份不存在的课程打 14 个维度分；
    这类 run 应该在报告的 Status/Attempts 列里被看到，而不是变成一张评分表。
    direct_codex 的产物是 run 目录里的 direct_output.md，不是 store 产物。
    """
    if str(run.get("run_status") or "") != "succeeded":
        return False
    if run.get("artifact_hashes"):
        return True
    run_dir = str(run.get("run_dir") or "")
    return bool(run_dir) and (Path(run_dir) / "direct_output.md").exists()


def write_worksheets(
    runs: list[dict[str, Any]] | None = None,
    *,
    directory: Path | None = None,
    preserve_filled: bool = True,
) -> list[Path]:
    """§30–§32：为每次 run 生成教师评分工作表（人工填写后可用 CLI 回收）。

    教师填写的评分是不可再生的外部输入：重新生成报告时绝不能覆盖已填写的工作表，
    否则一位老师刚写好的 14 个维度评分会被 `--report` 静默清空。
    `preserve_filled=True`（默认）下只刷新空白工作表里的 run 绑定信息。"""
    import yaml

    runs = runs if runs is not None else load_runs()
    target_dir = directory or (cases.reports_dir() / "worksheets")
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for run in runs:
        if not is_evaluable(run):
            # 失败/无产物的 run 不生成评分表：教师无法给一份不存在的课程打 14 个维度分，
            # 它的信息已经在报告的 Status / Attempts / Auto Issues 列里
            continue
        case_id = str(run.get("case_id") or "?")
        mode = str(run.get("mode") or "?")
        # §46：实验变体（external-assessment 等）是不同产物，工作表必须分开命名，
        # 否则「只生成 PPT」这类变体会覆盖该 case 的主工作表。
        experiment = str(run.get("experiment") or "")
        stem = f"{case_id}-{mode}-{experiment}" if experiment else f"{case_id}-{mode}"
        path = target_dir / f"{stem}-human_eval.yaml"
        if preserve_filled and path.exists():
            try:
                existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                existing = {}
            if _worksheet_is_filled(existing):
                continue
        template = {
            "run": {
                "case_id": case_id,
                "mode": mode,
                "run_id": run.get("run_id"),
                "run_status": run.get("run_status"),
                "run_dir": run.get("run_dir"),
                "artifact_count": len(run.get("artifact_hashes") or {}),
                "evidence_policy": run.get("evidence_policy"),
            },
            "reviewer": "",
            "role": "teacher",
            "scores": {
                "subject_accuracy": None,
                "teaching_logic": None,
                "goal_clarity": None,
                "content_alignment": None,
                "concept_clarity": None,
                "case_quality": None,
                "executability": None,
                "student_engagement": None,
                "cognitive_challenge": None,
                "assessment_design": None,
                "language_naturalness": None,
                "visual_necessity": None,
                "coherence": None,
                "teacher_usability": None,
                "spoken_naturalness": None,
            },
            "comment": "",
            "must_fix": [],
            "nice_to_have": [],
            "evidence_errors": 0,
            "routing_errors": 0,
            "plan_errors": 0,
            "edits": {
                "generated_text": "",
                "edited_text": "",
                "items": [{"category": "", "severity": ""}],
            },
            "notes": [
                "填写说明见 benchmarks/reports/worksheets/README.md",
                "scores 使用 1–5；spoken_naturalness 仅脚本类任务必填",
                "edits.items 的 category 取值：fact correction / teaching restructure / tone edit / case replacement / media correction / assessment correction / template correction",
                "edits.items 的 severity 取值：S0 cosmetic / S1 wording / S2 local teaching improvement / S3 conceptual correction / S4 factual-evidence correction / S5 major redesign",
            ],
        }
        path.write_text(yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
        written.append(path)
    readme = target_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# 教师评分工作表（M6 §30–§32）\n\n"
            "1. 打开对应的 `<case>-<mode>-human_eval.yaml`，在 `scores` 中给 1–5 分（14 个维度；脚本类任务另填 `spoken_naturalness`）。\n"
            "2. `comment` 必填（文字备注），`must_fix` / `nice_to_have` 选填。\n"
            "3. 若做过人工修改，把修改前后的文本填入 `edits.generated_text` / `edits.edited_text`，并按类别与严重度登记 `edits.items`。\n"
            "4. 提交：`python -m pebs.cli benchmark --submit-eval <worksheet.yaml> --project <project_id>`\n"
            "   （等价于 POST /api/projects/<project_id>/evaluation；评分以 Artifact 形式落库并绑定 Skill 版本）\n",
            encoding="utf-8",
        )
    return written


def load_worksheet(path: Path) -> dict[str, Any]:
    """把教师填写的工作表转换成 /evaluation 的 payload。"""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    scores = {key: value for key, value in (data.get("scores") or {}).items() if value is not None}
    edits = data.get("edits") or {}
    edits["items"] = [item for item in (edits.get("items") or []) if item.get("category") or item.get("severity")]
    run = data.get("run") or {}
    return {
        "reviewer": str(data.get("reviewer") or ""),
        "role": str(data.get("role") or "teacher"),
        "run_id": str(run.get("run_id") or ""),
        "mode": str(run.get("mode") or ""),
        "scores": scores,
        "comment": str(data.get("comment") or ""),
        "must_fix": list(data.get("must_fix") or []),
        "nice_to_have": list(data.get("nice_to_have") or []),
        "evidence_errors": int(data.get("evidence_errors") or 0),
        "routing_errors": int(data.get("routing_errors") or 0),
        "plan_errors": int(data.get("plan_errors") or 0),
        "edits": edits,
    }


def performance_section(*, provider_skills: set[str] | None = None) -> list[str]:
    """§19/§68：把 Skill Performance Registry 摘要写进报告（只观察，不改路由）。"""
    from . import performance as performance_mod

    data = performance_mod.load_performance().get("skills", {})
    if not data:
        return []
    rows = []
    for name, record in sorted(data.items()):
        if provider_skills is not None and name not in provider_skills:
            continue
        rows.append(
            "| {name} | {version} | {runs} | {success} | {schema} | {human} | {edit} | {status} |".format(
                name=name,
                version=str(record.get("version") or "")[:12],
                runs=record.get("runs", 0),
                success=record.get("success_rate"),
                schema=record.get("schema_failure_rate"),
                human=record.get("human_score"),
                edit=record.get("teacher_edit_ratio"),
                status=record.get("status", "EXPERIMENTAL"),
            )
        )
    if not rows:
        return []
    return [
        "",
        "## Skill Performance Registry（§19/§40；内部 skills 全部记录）",
        "",
        "| Skill | Version | Runs | Success | Schema Fail | Human | Edit Ratio | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        *rows,
        "",
    ]


def render_selection_report(records: list[dict[str, Any]]) -> str:
    """§46 Skill Selection Experiment（零模型调用）：Builtin vs 显式外部 Skill 的 DAG 差异。"""
    lines = [
        "# M6 Skill Selection Experiment（plan-only）",
        "",
        "同一任务在不同 Skill 组合下的 DAG 与选择理由；不调用任何模型，可离线复现（§46/§47）。",
        "",
        "| Case | Variant | Nodes | Terminal outputs | Explicit-skill note |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {case} | {variant} | {nodes} | {terminals} | {note} |".format(
                case=record.get("case_id"),
                variant=record.get("variant"),
                nodes=len(record.get("plan_nodes") or []),
                terminals="、".join(record.get("terminal_outputs") or []),
                note="；".join(record.get("explicit_skills_note") or []) or "—",
            )
        )
    lines.append("")
    for record in records:
        trace = record.get("selection_trace") or []
        if not trace:
            continue
        lines.append(f"## {record.get('case_id')} / {record.get('variant')}")
        lines.append("")
        lines.append("| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |")
        lines.append("| --- | --- | ---: | --- | --- |")
        for entry in trace:
            rejected_items = entry.get("rejected_candidates", [])
            rejected = "；".join(
                f"{item['candidate']}({item['score']})"
                + (f" — {item['rejected_because']}" if item.get("rejected_because") else "")
                for item in rejected_items[:3]
            )
            if len(rejected_items) > 3:
                rejected += f"；等 {len(rejected_items)} 个候选"
            lines.append(
                f"| {entry.get('artifact')} | {entry.get('selected')} | {entry.get('selected_score')} | {rejected or '—'} | {entry.get('reason')} |"
            )
        lines.append("")
    return "\n".join(lines)


def find_run_for_project(project_id: str) -> dict[str, Any] | None:
    """§62：Evaluation Tab 需要把项目映射回它的 benchmark run（含自动问题清单）。"""
    if not project_id:
        return None
    for run in load_runs():
        if str(run.get("project_id") or "") == project_id:
            return run
    return None


def quality_section(runs: list[dict[str, Any]] | None = None) -> list[str]:
    """§53/§54/§58：把语言、口语、PPT 的频度/分布写进报告（供人工评分参考，不做硬门）。"""
    runs = runs if runs is not None else load_runs()
    rows: list[str] = []
    for run in runs:
        quality = run.get("quality_metrics") or {}
        language = quality.get("language") or {}
        oral = quality.get("oral") or {}
        ppt = quality.get("ppt") or {}
        if not (language or oral or ppt):
            continue
        rows.append(
            "| {case} | {variant} | {per1000} | {long} | {spoken} | {dense} | {notes} |".format(
                case=run.get("case_id"),
                variant=run.get("_variant") or run.get("mode"),
                per1000=language.get("per_1000_chars", "—"),
                long=oral.get("long_sentence_ratio", "—"),
                spoken=oral.get("spoken_marker_ratio", "—"),
                dense=ppt.get("dense_ratio", "—"),
                notes=len(ppt.get("missing_notes") or []) if ppt else "—",
            )
        )
    if not rows:
        return []
    return [
        "",
        "## 质量指标（§53/§54/§58；频度与分布，人工评分参考，不设自动阈值）",
        "",
        "| Case | Variant | 机械连接词/千字 | 长句比例 | 口语标记比例 | 密集页比例 | 缺 Teacher Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        *rows,
        "",
    ]


def write_selection_report(records: list[dict[str, Any]], *, path: Path | None = None) -> Path:
    target = path or (cases.reports_dir() / "skill_selection.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_selection_report(records), encoding="utf-8")
    (target.parent / "skill_selection.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def write_report(summary: dict[str, Any] | None = None, *, path: Path | None = None) -> Path:
    summary = summary or summarize()
    target = path or (cases.reports_dir() / "benchmark_summary.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(summary), encoding="utf-8")
    (target.parent / "benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target
