from __future__ import annotations

from typing import Any


class LegacyStepSkill:
    """Wraps existing pipeline steps so the dynamic planner can execute them (M5.2 adapter)."""

    def __init__(self, steps_registry: dict[str, Any]):
        self.steps_registry = steps_registry

    def execute(self, ctx: Any, node: dict[str, Any]) -> dict[str, Any]:
        from ..pipeline import StepFailed

        notes: list[str] = []
        for step_id in node.get("steps", []):
            handler = self.steps_registry.get(step_id)
            if handler is None:
                raise StepFailed(f"未实现步骤：{step_id}")
            result = handler(ctx)
            if isinstance(result, dict):
                notes.extend(str(item) for item in result.get("notes", [])[:8])
        return {"notes": notes}
