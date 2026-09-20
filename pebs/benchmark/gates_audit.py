"""Gate False Positive / False Negative audit（M6 §35, §67）。

门禁结论只有在"用同一套产物重放"时才能判定对错：本模块用**当前**门禁代码
重放已存项目，与当时写入的 gate_result 比对，得到两个 §35 要求的指标：

- Gate False Negative Rate：当时 PASS，重放为 FAIL（漏检，真实缺陷被放过）
- Gate False Positive Rate：当时 FAIL/NEEDS_REVIEW，重放为 PASS（误报，冤枉了产物）

重放不调用模型，因此可以在配额不可用时评估历史 run 的门禁可信度。
注意：这是"相对当前门禁实现"的口径，不是绝对真值；它衡量的是**门禁演进**带来的结论漂移。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import config, gates
from ..evidence import EvidenceStore
from ..store import Store
from . import cases, report

FAILED_STATUSES = ("FAIL", "NEEDS_REVIEW")


def latest_rev_overrides(store: Store) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for artifact in store.list_artifacts():
        revisions = store.revisions_of(artifact["artifact_id"])
        if revisions:
            overrides[artifact["artifact_id"]] = revisions[-1]
    return overrides


def replay_project(project_id: str) -> dict[str, Any]:
    """在已存项目上重放 G1–G7，返回逐条比对结果。项目不可读时返回 skipped。"""
    try:
        store = Store(project_id, config.project_dir(project_id))
    except Exception:  # noqa: BLE001 - 项目已清理
        return {"project": project_id, "skipped": "project unavailable", "rows": []}
    try:
        overrides = latest_rev_overrides(store)
        if not overrides:
            return {"project": project_id, "skipped": "no artifacts", "rows": []}
        ctx = gates.GateContext(
            store=store,
            evidence=EvidenceStore(store),
            run_id="",
            environment="production",
            overrides=overrides,
        )
        rows: list[dict[str, Any]] = []
        for artifact_id in sorted(item for item in overrides if item.startswith("script:")):
            for result in gates.run_section_gates(ctx, artifact_id):
                stored_revs = store.revisions_of(f"gate:{result['gate_id']}:{artifact_id}")
                stored = store.get_revision(stored_revs[-1])["content"].get("status") if stored_revs else None
                rows.append(
                    {
                        "artifact": artifact_id,
                        "gate": result["gate_id"],
                        "stored": stored,
                        "now": result["status"],
                        "changed": stored != result["status"],
                        "issues": [issue.get("reason", "") for issue in result.get("issues", [])],
                    }
                )
        return {"project": project_id, "skipped": "", "rows": rows}
    finally:
        store.close()


def gate_rates(records: list[dict[str, Any]]) -> dict[str, Any]:
    """§35：把重放比对汇总成 Gate False Negative / Positive Rate。"""
    checked = 0
    false_negative = 0
    false_positive = 0
    false_negative_pass = 0
    false_positive_fail = 0
    per_gate: dict[str, dict[str, int]] = {}
    for record in records:
        for row in record.get("rows", []):
            checked += 1
            bucket = per_gate.setdefault(row["gate"], {"checked": 0, "false_negative": 0, "false_positive": 0})
            bucket["checked"] += 1
            if row["stored"] == "PASS":
                false_negative_pass += 1
                if row["now"] in FAILED_STATUSES:
                    false_negative += 1
                    bucket["false_negative"] += 1
            elif row["stored"] in FAILED_STATUSES:
                false_positive_fail += 1
                if row["now"] == "PASS":
                    false_positive += 1
                    bucket["false_positive"] += 1
    return {
        "checked": checked,
        "runs": len(records),
        "runs_with_changes": sum(1 for record in records if any(row["changed"] for row in record.get("rows", []))),
        "gate_false_negative_rate": round(false_negative / false_negative_pass, 4) if false_negative_pass else None,
        "gate_false_positive_rate": round(false_positive / false_positive_fail, 4) if false_positive_fail else None,
        "false_negative": false_negative,
        "false_positive": false_positive,
        "per_gate": per_gate,
        "caveat": "重放口径：以当前门禁实现为准衡量历史 run 的门禁结论漂移，不是绝对真值",
    }


def audit(runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    runs = runs if runs is not None else report.load_runs()
    records = [replay_project(str(run.get("project_id"))) for run in runs if run.get("project_id")]
    summary = gate_rates(records)
    summary["reports"] = records
    return summary


def write_audit(summary: dict[str, Any] | None = None, *, path: Path | None = None) -> Path:
    import json

    summary = summary or audit()
    target = path or (cases.reports_dir() / "gate_audit.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def section(summary: dict[str, Any] | None = None, *, path: Path | None = None) -> list[str]:
    """报告里的一小段：只读已生成的 gate_audit.json，避免每次生成报告都重放。"""
    import json

    target = path or (cases.reports_dir() / "gate_audit.json")
    if not target.exists():
        return []
    try:
        summary = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [
        "",
        "## 门禁重放审计（§35 Gate FP/FN；以当前门禁实现为准，非绝对真值）",
        "",
        f"- 重放覆盖：{summary.get('checked')} 条 gate 判定 / {summary.get('runs')} 个 run；"
        f"{summary.get('runs_with_changes')} 个 run 结论发生变化",
        f"- Gate False Negative Rate（当时 PASS，重放 FAIL）：{summary.get('gate_false_negative_rate')}"
        f"（{summary.get('false_negative')} 条）",
        f"- Gate False Positive Rate（当时 FAIL/NEEDS_REVIEW，重放 PASS）：{summary.get('gate_false_positive_rate')}"
        f"（{summary.get('false_positive')} 条）",
        f"- 口径说明：{summary.get('caveat')}",
        "",
    ]
