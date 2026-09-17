from __future__ import annotations

from typing import Any

from .legacy import LegacyStepSkill


class BuiltinStepExecutor:
    def __init__(self, steps_registry: dict[str, Any]):
        self.legacy = LegacyStepSkill(steps_registry)

    def execute(self, ctx: Any, node: dict[str, Any], *, skill_record: dict[str, Any]) -> dict[str, Any]:
        return self.legacy.execute(ctx, node)
