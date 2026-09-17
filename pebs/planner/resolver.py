from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config, registry

DOMAIN_FIT = {"education": 0.5, "psychology": 0.5, "media": 0.3, "presentation": 0.3}
RISK_FIT = {"low": 0.2, "medium": 0.4, "high": 0.6}


def regression_scores() -> dict[str, float]:
    path = Path(config.REGISTRY_DIR) / "regression.json"
    if not path.exists():
        return {}
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    totals: dict[str, list[int]] = {}
    for record in history:
        skill = record.get("skill")
        if not skill:
            continue
        passed, failed = totals.setdefault(skill, [0, 0])
        if record.get("passed"):
            totals[skill] = [passed + 1, failed]
        else:
            totals[skill] = [passed, failed + 1]
    scores: dict[str, float] = {}
    for skill, (passed, failed) in totals.items():
        total = passed + failed
        scores[skill] = (passed / total) if total else 0.0
    return scores


def _score(record: dict[str, Any], artifact_type: str, task_type: str | None, risk: str | None, scores: dict[str, float]) -> float:
    score = 0.0
    if artifact_type in record.get("produces", []):
        score += 2.0
    if record.get("status") == "APPROVED":
        score += 1.0
    elif record.get("status") == "PATCHED":
        score += 0.5
    score += DOMAIN_FIT.get(str(record.get("domain", "")), 0.0)
    if risk:
        score += RISK_FIT.get(str(record.get("risk_level", "")), 0.0)
    cost = record.get("estimated_cost", {}) or {}
    score -= 0.05 * float(cost.get("model_calls", 0))
    score += scores.get(str(record.get("name")), 0.0)
    return score


def candidates(
    artifact_type: str,
    *,
    task_type: str | None = None,
    knowledge_types: list[str] | None = None,
    risk: str | None = None,
) -> list[dict[str, Any]]:
    scores = regression_scores()
    results = []
    for name in registry.producers_of(artifact_type):
        record = registry.get(name)
        if record is None:
            continue
        if record.get("status") not in ("APPROVED", "PATCHED"):
            continue
        runtime_kind = record.get("runtime")
        if runtime_kind != "builtin":
            artifact_ids = (record.get("handler") or {}).get("artifact_ids") or {}
            if artifact_type not in artifact_ids:
                continue
        results.append({"name": name, "record": record, "score": _score(record, artifact_type, task_type, risk, scores)})
    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def choose(
    artifact_type: str,
    *,
    prefer: list[str] | None = None,
    pinned: list[str] | None = None,
    task_type: str | None = None,
    knowledge_types: list[str] | None = None,
    risk: str | None = None,
) -> dict[str, Any] | None:
    options = candidates(artifact_type, task_type=task_type, knowledge_types=knowledge_types, risk=risk)
    if not options:
        return None
    by_name = {item["name"]: item for item in options}
    for name in list(pinned or []) + list(prefer or []):
        canonical = registry.resolve_alias(name) or name
        if canonical in by_name:
            return by_name[canonical]
    self_implemented = [item for item in options if item["record"].get("self_implemented")]
    if self_implemented:
        return self_implemented[0]
    return options[0]


def rank_report(artifact_type: str, **kwargs: Any) -> list[dict[str, Any]]:
    return [
        {"name": item["name"], "score": round(item["score"], 3), "status": item["record"].get("status")}
        for item in candidates(artifact_type, **kwargs)
    ]
