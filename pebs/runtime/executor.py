from __future__ import annotations

from typing import Any

from .. import config, gates, pipeline
from ..store import BudgetExceeded
from .legacy import LegacyStepSkill


def _gate_status(results: dict[str, dict[str, Any]], gate_id: str, artifact_id: str) -> dict[str, Any] | None:
    return results.get(gates.gate_artifact_id(gate_id, artifact_id))


def execute_plan(*, engine: Any, run_id: str, ctx: pipeline.PipelineContext, plan: dict[str, Any]) -> None:
    legacy = LegacyStepSkill(pipeline.STEPS)
    nodes = plan.get("nodes", [])
    for node in nodes:
        node_id = node["node_id"]
        if ctx.store.get_run(run_id)["status"] == "cancelled":
            engine.store.set_step(run_id, node_id, status="CANCELLED", note="运行已取消")
            continue
        reused_outputs = [output for output in node.get("outputs", []) if output in ctx.outputs]
        if node.get("reused") or len(reused_outputs) == len(node.get("outputs", [])):
            for output in node.get("outputs", []):
                accepted = ctx.store.accepted_rev_id(output)
                if accepted:
                    ctx.outputs[output] = accepted
            engine.store.set_step(
                run_id, node_id, status="SUCCEEDED", note="复用已接受产物：" + "、".join(node.get("outputs", []))
            )
            continue
        missing = [
            dep for dep in node.get("depends_on", []) if engine._step_status(run_id, dep) != "SUCCEEDED"
        ]
        if missing:
            engine.store.set_step(run_id, node_id, status="BLOCKED", error="依赖未成功：" + "、".join(missing))
            continue
        gate_note = ""
        if node.get("gate_before"):
            results = gates.latest_gate_results(ctx.store, ctx.outputs)
            failed = []
            for gate_id in node["gate_before"]:
                for output in node.get("inputs", []):
                    result = _gate_status(results, gate_id, output)
                    if result and result.get("status") in ("FAIL", "NEEDS_REVIEW"):
                        failed.append(f"{gate_id}@{output}")
            if failed:
                engine.store.set_step(run_id, node_id, status="BLOCKED", error="前置门禁未通过：" + "、".join(failed))
                continue
            gate_note = "前置门禁：" + "、".join(node["gate_before"])
        engine.store.set_step(run_id, node_id, status="RUNNING", bump_attempt=True)
        try:
            result = legacy.execute(ctx, node)
            note = "；".join(result.get("notes", [])[:8]) if result.get("notes") else ""
            engine.store.set_step(
                run_id,
                node_id,
                status="SUCCEEDED",
                note="；".join(part for part in [gate_note, note] if part),
            )
        except pipeline.StepBlocked as exc:
            engine.store.set_step(run_id, node_id, status="BLOCKED", error=str(exc))
        except pipeline.StepFailed as exc:
            engine.store.set_step(run_id, node_id, status="FAILED", error=str(exc))
        except BudgetExceeded as exc:
            engine.store.set_step(run_id, node_id, status="BLOCKED", error=f"预算耗尽：{exc}")
            engine.store.set_run_status(run_id, "blocked")
            return
        except pipeline.CancelledRun:
            engine.store.set_step(run_id, node_id, status="CANCELLED", error="运行已取消")
        except Exception as exc:  # noqa: BLE001 - unexpected failures must be recorded
            engine.store.set_step(run_id, node_id, status="FAILED", error=f"未预期错误：{exc}")
    engine._finalize_run_status(run_id)
