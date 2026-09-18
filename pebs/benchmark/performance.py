"""Skill Performance Registry（M6 §19, §40, §68, §69）。

记录必须绑定 Skill 版本（provider SHA / package hash / patch），否则升级后历史数据失效。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .. import config

MODES = ("direct_codex", "builtin", "dynamic", "mixed")

PROMOTION_THRESHOLD = {
    "min_runs": 10,
    "max_schema_failure_rate": 0.1,
    "min_human_score": 3.5,
    "forbid_unresolved_safety": True,
}


def performance_path() -> Path:
    return Path(config.REGISTRY_DIR) / "performance.json"


def load_performance() -> dict[str, Any]:
    path = performance_path()
    if not path.exists():
        return {"format": 1, "skills": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("skills", {})
    return data


def save_performance(data: dict[str, Any]) -> Path:
    path = performance_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _empty_record(skill: str, version: str) -> dict[str, Any]:
    return {
        "skill": skill,
        "version": version,
        "provider_sha": "",
        "package_sha256": "",
        "patch": "",
        "domain": "",
        "status": "EXPERIMENTAL",
        "runs": 0,
        "success_rate": 0.0,
        "schema_failure_rate": 0.0,
        "human_score": None,
        "teacher_edit_ratio": None,
        "average_model_calls": 0.0,
        "average_latency": 0.0,
        "known_failure_modes": [],
        "last_verified": "",
    }


def record_run(
    *,
    skill: str,
    version: str = "",
    provider_sha: str = "",
    package_sha256: str = "",
    patch: str = "",
    domain: str = "",
    success: bool,
    schema_failure: bool = False,
    model_calls: int = 0,
    latency: float = 0.0,
    failure_mode: str = "",
    human_score: float | None = None,
    edit_ratio: float | None = None,
) -> dict[str, Any]:
    data = load_performance()
    record = data["skills"].get(skill) or _empty_record(skill, version)
    if version:
        record["version"] = version
    if provider_sha:
        record["provider_sha"] = provider_sha
    if package_sha256:
        record["package_sha256"] = package_sha256
    if patch:
        record["patch"] = patch
    if domain:
        record["domain"] = domain
    runs = int(record.get("runs", 0)) + 1
    successes = round(float(record.get("success_rate", 0.0)) * (runs - 1)) + (1 if success else 0)
    schema_failures = round(float(record.get("schema_failure_rate", 0.0)) * (runs - 1)) + (1 if schema_failure else 0)
    model_total = float(record.get("average_model_calls", 0.0)) * (runs - 1) + max(int(model_calls), 0)
    latency_total = float(record.get("average_latency", 0.0)) * (runs - 1) + max(float(latency), 0.0)
    record.update(
        {
            "runs": runs,
            "success_rate": round(successes / runs, 4),
            "schema_failure_rate": round(schema_failures / runs, 4),
            "average_model_calls": round(model_total / runs, 2),
            "average_latency": round(latency_total / runs, 2),
            "last_verified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        }
    )
    if human_score is not None:
        previous = record.get("human_score")
        record["human_score"] = round(
            human_score if previous is None else (float(previous) + human_score) / 2, 3
        )
    if edit_ratio is not None:
        previous = record.get("teacher_edit_ratio")
        record["teacher_edit_ratio"] = round(
            edit_ratio if previous is None else (float(previous) + edit_ratio) / 2, 4
        )
    modes = list(dict.fromkeys(list(record.get("known_failure_modes", [])) + ([failure_mode] if failure_mode else [])))
    record["known_failure_modes"] = modes[-10:]
    data["skills"][skill] = record
    save_performance(data)
    return record


def record_trace(
    trace: dict[str, Any],
    *,
    human_score: float | None = None,
    edit_ratio: float | None = None,
    latency_by_skill: dict[str, float] | None = None,
    model_calls_by_skill: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """§19/§39/§40：把一次 Build 的 Skill Trace 写入 performance registry。

    记录必须绑定 skill version / provider SHA / package hash / patch；
    只做 observe/record（§47：M6 不允许历史表现影响路由）。
    """
    latency_by_skill = latency_by_skill or {}
    model_calls_by_skill = model_calls_by_skill or {}
    recorded: list[dict[str, Any]] = []
    for skill in trace.get("skills", []):
        name = str(skill.get("skill") or "")
        if not name:
            continue
        status = str(skill.get("status") or "")
        error = str(skill.get("error") or "")
        recorded.append(
            record_run(
                skill=name,
                version=str(skill.get("version") or ""),
                provider_sha=str(skill.get("upstream_sha") or ""),
                package_sha256=str(skill.get("package_sha256") or ""),
                patch=str(skill.get("patch") or ""),
                domain=str(skill.get("domain") or ""),
                success=status == "SUCCEEDED",
                schema_failure=bool(status == "FAILED" and "Schema" in error),
                model_calls=int(model_calls_by_skill.get(name, 0) or 0),
                latency=float(latency_by_skill.get(name, 0.0) or 0.0),
                failure_mode=(error[:120] if status in ("FAILED", "BLOCKED") else ""),
                human_score=human_score,
                edit_ratio=edit_ratio,
            )
        )
    return recorded


def review_promotions(*, unresolved_safety: dict[str, bool] | None = None) -> dict[str, Any]:
    """§68/§69：只做观察与判定，不改变路由（§47：M6 不允许历史表现影响 Resolver）。"""
    unresolved_safety = unresolved_safety or {}
    data = load_performance()
    promote: list[dict[str, Any]] = []
    stay: list[dict[str, Any]] = []
    demote: list[dict[str, Any]] = []
    for name, record in sorted(data.get("skills", {}).items()):
        decision = promotion_decision(record, unresolved_safety=bool(unresolved_safety.get(name)))
        row = {
            "skill": name,
            "version": record.get("version"),
            "runs": record.get("runs", 0),
            "success_rate": record.get("success_rate"),
            "schema_failure_rate": record.get("schema_failure_rate"),
            "human_score": record.get("human_score"),
            "teacher_edit_ratio": record.get("teacher_edit_ratio"),
            "current_status": record.get("status", "EXPERIMENTAL"),
            "target_status": decision["target"],
            "blocking": decision["reasons"],
        }
        (promote if decision["eligible"] else stay).append(row)
        if record.get("status") == "DISABLED":
            demote.append({**row, "reason": "已禁用（历史降级）"})
    return {
        "promote_candidates": promote,
        "experimental": stay,
        "disabled": demote,
        "thresholds": PROMOTION_THRESHOLD,
        "note": "§47：M6 仅记录与判定；promotion 的实际生效由 M7 的 performance-aware routing 决定",
    }


def promotion_decision(record: dict[str, Any], *, unresolved_safety: bool = False) -> dict[str, Any]:
    """§68：EXPERIMENTAL → STABLE 的门槛；数据不足时不让外部 Skill 默认优先。"""
    reasons: list[str] = []
    if int(record.get("runs", 0)) < PROMOTION_THRESHOLD["min_runs"]:
        reasons.append(f"runs<{PROMOTION_THRESHOLD['min_runs']}")
    if float(record.get("schema_failure_rate", 0.0)) > PROMOTION_THRESHOLD["max_schema_failure_rate"]:
        reasons.append("schema_failure_rate too high")
    score = record.get("human_score")
    if score is None or float(score) < PROMOTION_THRESHOLD["min_human_score"]:
        reasons.append("human_score below threshold")
    if unresolved_safety:
        reasons.append("unresolved safety failure")
    return {"eligible": not reasons, "reasons": reasons, "target": "STABLE" if not reasons else "EXPERIMENTAL"}


def demotion_decision(*, evidence_error: bool = False, safety_regression: bool = False, schema_instability: bool = False) -> dict[str, Any]:
    """§69：出现证据/安全/schema 退化时自动降级。"""
    triggers = [
        name
        for name, flag in (
            ("evidence_error", evidence_error),
            ("safety_regression", safety_regression),
            ("schema_instability", schema_instability),
        )
        if flag
    ]
    return {"demote": bool(triggers), "triggers": triggers, "action": "DISABLED" if triggers else "KEEP"}
