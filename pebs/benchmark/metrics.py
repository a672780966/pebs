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


# 这些产物由运行/规划层写入，不是"被重建的教学产物"，不计入 Unnecessary Regeneration
SYSTEM_ARTIFACTS = frozenset(
    {"patch_plan", "human_eval", "build_plan_dynamic", "router_result", "build_plan", "skill_invocations"}
)


def locality_report(
    before_hashes: dict[str, str],
    after_hashes: dict[str, str],
    *,
    preserve: list[str],
    expected: list[str] | None = None,
) -> dict[str, Any]:
    """§26 / §38 / Acceptance 7。

    - preserve 集合必须 hash 不变（违反即 preserve_violations）；
    - 预期受影响集合（expected，即 Impact Analyzer 的输出）内的变化是正常的；
    - 系统产物（patch_plan / 运行记录）不算重建；
    - 其余变化才是 Unnecessary Regeneration。
    """
    violated = [
        artifact_id
        for artifact_id in preserve
        if after_hashes.get(artifact_id) != before_hashes.get(artifact_id)
    ]
    expected_set = set(expected or []) | SYSTEM_ARTIFACTS
    changed = {
        artifact_id
        for artifact_id, digest in after_hashes.items()
        if before_hashes.get(artifact_id) not in (None, digest)
    }
    new_artifacts = {
        artifact_id for artifact_id in after_hashes if artifact_id not in before_hashes
    }
    unnecessary = sorted(
        artifact_id
        for artifact_id in changed | new_artifacts
        if artifact_id not in expected_set and artifact_id not in set(preserve)
    )
    return {
        "preserve": sorted(preserve),
        "expected": sorted(expected_set),
        "preserve_violations": sorted(violated),
        "locality_preservation_rate": round(
            (len(preserve) - len(violated)) / len(preserve), 4
        )
        if preserve
        else 1.0,
        "changed_artifacts": sorted(changed | new_artifacts),
        "unnecessary_regeneration": unnecessary,
        "unnecessary_regeneration_rate": round(
            len(unnecessary) / max(len(changed | new_artifacts), 1), 4
        ),
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
