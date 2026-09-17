"""生产指标（M6 §33–§38）：从 Skill Trace 与 Store 计算可对比的数值。"""

from __future__ import annotations

import json
import re
from typing import Any

CJK = re.compile(r"[\u4e00-\u9fff]")


def char_count(text: str) -> int:
    return len(CJK.findall(text or ""))


def teacher_edit_ratio(generated_text: str, edited_text: str) -> dict[str, float | int]:
    """§33：字符级编辑比例 + 中文净编辑字符数。"""
    generated_chars = char_count(generated_text)
    edited_chars = char_count(edited_text)
    base = max(generated_chars, 1)
    return {
        "generated_chars": generated_chars,
        "edited_chars": edited_chars,
        "edit_ratio": round(abs(edited_chars - generated_chars) / base, 4),
        "semantic_edit_hint": round(min(generated_chars, edited_chars) / base, 4),
    }


EDIT_SEVERITIES = {
    "S0": "cosmetic",
    "S1": "wording",
    "S2": "local_teaching_improvement",
    "S3": "conceptual_correction",
    "S4": "factual_evidence_correction",
    "S5": "major_redesign",
}

EDIT_CATEGORIES = (
    "fact correction",
    "teaching restructure",
    "tone edit",
    "case replacement",
    "media correction",
    "assessment correction",
    "template correction",
)


def summarize_run(trace: dict[str, Any]) -> dict[str, Any]:
    """单次 run 的核心生产指标（§35）。"""
    skills = trace.get("skills", [])
    total = len(skills)
    failed = [skill for skill in skills if skill.get("status") == "FAILED"]
    blocked = [skill for skill in skills if skill.get("status") == "BLOCKED"]
    gates = trace.get("gates", [])
    gate_fail = [gate for gate in gates if gate.get("status") == "FAIL"]
    gate_review = [gate for gate in gates if gate.get("status") == "NEEDS_REVIEW"]
    reuse = [skill for skill in skills if skill.get("reused")]
    plan = trace.get("plan", {})
    return {
        "run_id": trace.get("run_id"),
        "case_id": trace.get("case_id"),
        "mode": trace.get("mode"),
        "run_status": trace.get("run_status"),
        "skill_count": total,
        "skill_failure_rate": round(len(failed) / total, 4) if total else 0.0,
        "skill_blocked_rate": round(len(blocked) / total, 4) if total else 0.0,
        "reuse_rate": round(len(reuse) / total, 4) if total else 0.0,
        "gate_fail_count": len(gate_fail),
        "gate_review_count": len(gate_review),
        "plan_node_count": plan.get("node_count", 0),
        "plan_degraded": bool(plan.get("degraded")),
    }


def locality_report(
    before_hashes: dict[str, str],
    after_hashes: dict[str, str],
    *,
    preserve: list[str],
) -> dict[str, Any]:
    """§38 / Acceptance 7：preserve 集合中不应有任何 hash 变化。"""
    violated = [
        artifact_id
        for artifact_id in preserve
        if after_hashes.get(artifact_id) != before_hashes.get(artifact_id)
    ]
    unrelated_changed = sorted(
        artifact_id
        for artifact_id, digest in after_hashes.items()
        if artifact_id not in preserve and before_hashes.get(artifact_id) not in (None, digest)
    )
    return {
        "preserve": sorted(preserve),
        "preserve_violations": sorted(violated),
        "locality_preservation_rate": round(
            (len(preserve) - len(violated)) / len(preserve), 4
        )
        if preserve
        else 1.0,
        "unexpected_changes": unrelated_changed,
    }


def snapshot_hashes(store: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for artifact in store.list_artifacts():
        if artifact.get("accepted_rev"):
            revision = store.get_revision(artifact["accepted_rev"])
            result[artifact["artifact_id"]] = revision["content_hash"]
    return result


def load_metrics(path: Any) -> dict[str, Any]:
    return json.loads(open(path, encoding="utf-8").read())
