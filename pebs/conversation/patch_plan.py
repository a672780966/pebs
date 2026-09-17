from __future__ import annotations

import time
import uuid
from typing import Any

from .. import registry


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def steps_for_artifacts(affected: list[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact_type in affected:
        for name in registry.producers_of(artifact_type):
            record = registry.get(name) or {}
            if record.get("runtime") != "builtin":
                for step in record.get("handler", {}).get("steps", []):
                    if step not in seen:
                        seen.add(step)
                        steps.append({"skill": name, "steps": [step], "artifact_type": artifact_type})
                continue
            for step in record.get("handler", {}).get("steps", []):
                if step not in seen:
                    seen.add(step)
                    steps.append({"skill": name, "steps": [step], "artifact_type": artifact_type})
    return steps


def build(
    *,
    message: str,
    intent: dict[str, Any],
    resolved: dict[str, Any],
    impact_result: dict[str, Any],
    accepted_artifacts: dict[str, dict[str, Any]],
    locked_artifacts: list[str],
) -> dict[str, Any]:
    affected = impact_result["order"]
    affected_types = sorted({artifact_id.split(":", 1)[0] for artifact_id in affected})
    return {
        "plan_id": "patch_" + uuid.uuid4().hex[:10],
        "message": message,
        "intent": intent,
        "resolved_targets": resolved,
        "affected_artifacts": affected,
        "affected_types": affected_types,
        "step_order": [step["steps"][0] for step in steps_for_artifacts(affected_types)],
        "locked_artifacts": sorted(locked_artifacts),
        "editable_artifacts": sorted(
            artifact_id for artifact_id in affected if artifact_id not in set(locked_artifacts)
        ),
        "impact_edges": impact_result["edges"],
        "unresolved": impact_result.get("unresolved", []) + resolved.get("unmapped", []),
        "requires_confirmation": True,
        "created_at": now_iso(),
    }
