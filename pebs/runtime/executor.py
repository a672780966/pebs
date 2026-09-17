from __future__ import annotations

from typing import Any

from .. import config, gates, pipeline, registry
from ..store import BudgetExceeded
from .builtin import BuiltinStepExecutor
from .legacy import LegacyStepSkill
from .prompt_skill import PromptSkillExecutor, SkillExecutionFailed
from .sandbox_skill import SandboxSkillExecutor
from .skill_loader import SkillRuntimeBlocked


def _emit_external_artifacts(ctx: pipeline.PipelineContext, node: dict[str, Any], record: dict[str, Any], content: dict[str, Any]) -> list[str]:
    mapping = (record.get("handler") or {}).get("artifact_ids") or {}
    produced: list[str] = []
    deps = [rev for rev in (ctx.rev(item) for item in record.get("requires", [])) if rev]
    for artifact_type in record.get("produces", []):
        template = str(mapping.get(artifact_type) or "")
        if not template:
            raise SkillRuntimeBlocked(f"{record.get('name')} 未声明 artifact_ids.{artifact_type}")
        if "{section_id}" in template:
            for section in ctx.sections():
                payload = dict(content)
                payload.setdefault("section_id", section["section_id"])
                payload.setdefault("title", section.get("title", ""))
                artifact_id = template.format(section_id=section["section_id"])
                info = ctx.emit(artifact_id, artifact_type, payload, str(record.get("name")), deps=deps)
                produced.append(info["revision_id"])
        else:
            info = ctx.emit(template, artifact_type, content, str(record.get("name")), deps=deps)
            produced.append(info["revision_id"])
    return produced


def _gate_status(results: dict[str, dict[str, Any]], gate_id: str, artifact_id: str) -> dict[str, Any] | None:
    return results.get(gates.gate_artifact_id(gate_id, artifact_id))


def execute_plan(*, engine: Any, run_id: str, ctx: pipeline.PipelineContext, plan: dict[str, Any]) -> None:
    builtin = BuiltinStepExecutor(pipeline.STEPS)
    prompt_executor = PromptSkillExecutor(engine.llm)
    sandbox_executor = SandboxSkillExecutor()
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
        record = registry.get(node["skill"]) or {}
        runtime_kind = str(record.get("runtime", "builtin"))
        engine.store.set_step(run_id, node_id, status="RUNNING", bump_attempt=True)
        try:
            if runtime_kind == "builtin":
                result = builtin.execute(ctx, node, skill_record=record)
                note = "；".join(result.get("notes", [])[:8]) if result.get("notes") else ""
            elif runtime_kind in ("prompt_skill", "external_skill"):
                content = prompt_executor.execute(ctx, node, skill_record=record)
                revisions = _emit_external_artifacts(ctx, node, record, content)
                report = node.get("_context_report") or {}
                note = (
                    f"外部 Skill 执行：{record.get('name')}；上下文仅含 "
                    + ("、".join(report.get("included", [])) or "无")
                    + f"；产出 {len(revisions)} 个产物"
                )
            elif runtime_kind == "sandbox_skill":
                outputs = sandbox_executor.execute(ctx, node, skill_record=record)
                revisions = []
                for item in outputs:
                    artifact_type = item["artifact_type"]
                    template = str(((record.get("handler") or {}).get("artifact_ids") or {}).get(artifact_type) or "")
                    if not template:
                        raise SkillRuntimeBlocked(f"{record.get('name')} 未声明 artifact_ids.{artifact_type}")
                    info = ctx.emit(template, artifact_type, item["content"], str(record.get("name")))
                    revisions.append(info["revision_id"])
                note = f"沙箱 Skill 执行：{record.get('name')}；产出 {len(revisions)} 个产物"
            else:
                engine.store.set_step(run_id, node_id, status="BLOCKED", error=f"未知 runtime 类型：{runtime_kind}")
                continue
            engine.store.set_step(
                run_id,
                node_id,
                status="SUCCEEDED",
                note="；".join(part for part in [gate_note, note] if part),
            )
        except (pipeline.StepBlocked, SkillRuntimeBlocked) as exc:
            engine.store.set_step(run_id, node_id, status="BLOCKED", error=str(exc))
        except (pipeline.StepFailed, SkillExecutionFailed) as exc:
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
