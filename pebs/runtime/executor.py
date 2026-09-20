from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .. import config, gates, pipeline, registry
from ..agents import AgentContractError, IsolationViolation, for_skill
from ..store import BudgetExceeded, ConflictError
from .builtin import BuiltinStepExecutor
from .prompt_skill import PromptSkillExecutor, SkillExecutionFailed
from .sandbox_skill import SandboxSkillExecutor
from .skill_loader import SkillRuntimeBlocked
from .step_context import step_scope

# step note 里标记 Schema 修复的稳定前缀（trace 以此计算 §35 Schema Repair Rate）
SCHEMA_REPAIR_NOTE = "Schema 修复 "


def _step_input_revs(node: dict[str, Any], before_outputs: dict[str, str]) -> list[str]:
    """§39：把节点声明的输入类型解析成本轮真实存在的产物 id（可追溯"读了什么"）。"""
    declared = set(node.get("inputs") or []) | set(node.get("optional_requires") or [])
    if not declared:
        return []
    resolved: list[str] = []
    for artifact_id in before_outputs:
        if artifact_id.split(":", 1)[0] in declared and artifact_id not in resolved:
            resolved.append(artifact_id)
    return sorted(resolved)


def _step_output_revs(
    before_outputs: dict[str, str], after_outputs: dict[str, str]
) -> list[str]:
    """§39：本节点新产出的 revision（去重，保持 artifact 出现顺序）。"""
    seen: list[str] = []
    for artifact_id in after_outputs:
        revision_id = after_outputs[artifact_id]
        if before_outputs.get(artifact_id) != revision_id and revision_id not in seen:
            seen.append(revision_id)
    return seen


def _node_kind(record: dict[str, Any]) -> str:
    runtime_kind = str(record.get("runtime", "builtin"))
    if runtime_kind == "sandbox_skill":
        return "sandbox"
    if runtime_kind in ("prompt_skill", "external_skill"):
        return "llm"
    cost = record.get("estimated_cost", {}) or {}
    if int(cost.get("research_calls", 0) or 0) > 0:
        return "research"
    if int(cost.get("model_calls", 0) or 0) > 0:
        return "llm"
    return "local"


def _emit_external_artifacts(ctx: pipeline.PipelineContext, record: dict[str, Any], content: dict[str, Any]) -> list[str]:
    mapping = (record.get("handler") or {}).get("artifact_ids") or {}
    produced: list[str] = []
    deps = [rev for rev in (ctx.rev(item) for item in record.get("requires", [])) if rev]
    section_payloads = content.get("_sections") if isinstance(content, dict) else None
    for artifact_type in record.get("produces", []):
        template = str(mapping.get(artifact_type) or "")
        if not template:
            raise SkillRuntimeBlocked(f"{record.get('name')} 未声明 artifact_ids.{artifact_type}")
        if "{section_id}" in template:
            for section in ctx.sections():
                section_id = section["section_id"]
                if isinstance(section_payloads, dict) and section_id in section_payloads:
                    # M6：分节调用时使用该节自己的 payload（不再把同一内容复制到每一节）
                    source = section_payloads[section_id]
                    payload = dict(source) if isinstance(source, dict) else {"items": source}
                else:
                    payload = {key: value for key, value in content.items() if key != "_sections"}
                payload.setdefault("section_id", section_id)
                payload.setdefault("title", section.get("title", ""))
                artifact_id = template.format(section_id=section_id)
                info = ctx.emit(artifact_id, artifact_type, payload, str(record.get("name")), deps=deps)
                produced.append(info["revision_id"])
        else:
            payload = {key: value for key, value in content.items() if key != "_sections"} if isinstance(content, dict) else content
            info = ctx.emit(template, artifact_type, payload, str(record.get("name")), deps=deps)
            produced.append(info["revision_id"])
    return produced


def _gate_status(results: dict[str, dict[str, Any]], gate_id: str, artifact_id: str) -> dict[str, Any] | None:
    return results.get(gates.gate_artifact_id(gate_id, artifact_id))


class _Runner:
    def __init__(self, engine: Any, ctx: pipeline.PipelineContext):
        self.engine = engine
        self.ctx = ctx
        self.builtin = BuiltinStepExecutor(pipeline.STEPS)
        self.prompt = PromptSkillExecutor(engine.llm, store=engine.store)
        self.sandbox = SandboxSkillExecutor()
        self.write_lock = threading.Lock()
        self.aborted = threading.Event()
        self.abort_reason: str | None = None
        runtime_cfg = config.RULES.get("runtime", {}) or {}
        self.semaphores = {
            "llm": threading.Semaphore(int(runtime_cfg.get("max_parallel_llm", 3) or 1)),
            "research": threading.Semaphore(int(runtime_cfg.get("max_parallel_research", 2) or 1)),
            "sandbox": threading.Semaphore(int(runtime_cfg.get("max_parallel_sandbox", 1) or 1)),
        }
        self.max_workers = (
            int(runtime_cfg.get("max_parallel_llm", 3) or 1)
            + int(runtime_cfg.get("max_parallel_research", 2) or 1)
            + int(runtime_cfg.get("max_parallel_sandbox", 1) or 1)
            + 2
        )

    # ------------------------------------------------------------- handlers
    def abort_run(self, reason: str) -> None:
        """Stop dispatching: a budget abort must not let later nodes re-fail."""
        self.abort_reason = reason
        self.aborted.set()

    def skip_after_abort(self, run_id: str, node: dict[str, Any]) -> bool:
        """Record a node that will not be attempted because the run aborted.

        The status stays BLOCKED with a budget reason so that section 84 resume
        can find these steps and re-dispatch them once the budget is raised.
        """
        if not self.aborted.is_set():
            return False
        self.engine.store.set_step(
            run_id,
            node["node_id"],
            status="BLOCKED",
            error=f"预算耗尽：本次运行已中止后续步骤（{self.abort_reason}）",
        )
        return True

    def _builtin_handler(self, ctx: Any, node: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        return self.builtin.execute(ctx, node, skill_record=record)

    def _prompt_handler(self, ctx: Any, node: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        content = self.prompt.execute(ctx, node, skill_record=record)
        with self.write_lock:
            revisions = _emit_external_artifacts(ctx, record, content)
        return {
            "content": content,
            "revisions": revisions,
            "schema_repairs": int(node.get("_schema_repairs", 0) or 0),
        }

    def _sandbox_handler(self, ctx: Any, node: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        outputs = self.sandbox.execute(ctx, node, skill_record=record)
        revisions: list[str] = []
        with self.write_lock:
            for item in outputs:
                artifact_type = item["artifact_type"]
                template = str(((record.get("handler") or {}).get("artifact_ids") or {}).get(artifact_type) or "")
                if not template:
                    raise SkillRuntimeBlocked(f"{record.get('name')} 未声明 artifact_ids.{artifact_type}")
                info = ctx.emit(template, artifact_type, item["content"], str(record.get("name")))
                revisions.append(info["revision_id"])
        return {"revisions": revisions}

    def execute_node(self, run_id: str, node: dict[str, Any]) -> None:
        node_id = node["node_id"]
        store = self.engine.store
        if store.get_run(run_id)["status"] == "cancelled":
            store.set_step(run_id, node_id, status="CANCELLED", note="运行已取消")
            return
        if self.skip_after_abort(run_id, node):
            return
        reused_outputs = [output for output in node.get("outputs", []) if output in self.ctx.outputs]
        if node.get("reused") or len(reused_outputs) == len(node.get("outputs", [])):
            with self.write_lock:
                for output in node.get("outputs", []):
                    accepted = store.accepted_rev_id(output)
                    if accepted:
                        self.ctx.outputs[output] = accepted
            store.set_step(
                run_id, node_id, status="SUCCEEDED", note="复用已接受产物：" + "、".join(node.get("outputs", []))
            )
            return
        missing = [
            dep for dep in node.get("depends_on", []) if self.engine._step_status(run_id, dep) != "SUCCEEDED"
        ]
        if missing:
            store.set_step(run_id, node_id, status="BLOCKED", error="依赖未成功：" + "、".join(missing))
            return
        gate_note = ""
        if node.get("gate_before"):
            results = gates.latest_gate_results(store, self.ctx.outputs)
            failed = []
            for gate_id in node["gate_before"]:
                for output in node.get("inputs", []):
                    result = _gate_status(results, gate_id, output)
                    if result and result.get("status") in ("FAIL", "NEEDS_REVIEW"):
                        failed.append(f"{gate_id}@{output}")
            if failed:
                store.set_step(run_id, node_id, status="BLOCKED", error="前置门禁未通过：" + "、".join(failed))
                return
            gate_note = "前置门禁：" + "、".join(node["gate_before"])
        record = registry.get(node["skill"]) or {}
        runtime_kind = str(record.get("runtime", "builtin"))
        kind = _node_kind(record)
        semaphore = self.semaphores.get(kind)
        agent = for_skill(record, self.engine.llm)
        # §39：per-skill input_artifacts / output_artifacts / model_calls。
        # 用节点执行前后的快照求差，内置/外部/沙箱三条路径都能覆盖，不必逐个 handler 改。
        before_outputs = dict(self.ctx.outputs)

        def _finalize(status: str, **fields: Any) -> None:
            """所有终态都带上 §39 的 per-skill 产物（失败节点也要可追溯）。

            model_calls 不在这里记：并行调度下共享计数器差分会被同批节点污染，
            改由 `store.bump_calls(..., step_id=current_step())` 在调用点精确记账。
            """
            store.set_step(
                run_id,
                node_id,
                status=status,
                input_revs=_step_input_revs(node, before_outputs),
                output_revs=_step_output_revs(before_outputs, self.ctx.outputs),
                **fields,
            )

        store.set_step(run_id, node_id, status="RUNNING", bump_attempt=True)
        try:
            if semaphore is not None:
                semaphore.acquire()
            _scope = None
            try:
                # §39：让本次节点内的所有模型调用都记到这个 step 上（线程局部，支持并行）
                _scope = step_scope(node_id)
                _scope.__enter__()
                if runtime_kind == "builtin":
                    outcome = agent.run_node(
                        self.ctx, node=node, record=record, handler=self._builtin_handler
                    )
                    result = outcome["result"]
                    note = "；".join(result.get("notes", [])[:8]) if result.get("notes") else ""
                elif runtime_kind in ("prompt_skill", "external_skill"):
                    outcome = agent.run_node(
                        self.ctx, node=node, record=record, handler=self._prompt_handler
                    )
                    result = outcome["result"]
                    revisions = result.get("revisions", [])
                    report = node.get("_context_report") or {}
                    note = (
                        f"外部 Skill 执行：{record.get('name')}；上下文仅含 "
                        + ("、".join(report.get("included", [])) or "无")
                        + f"；产出 {len(revisions)} 个产物"
                    )
                    # §35：Schema 修复次数必须出现在 trace 里（否则 Repair Rate 无从计算）
                    if int(result.get("schema_repairs") or 0) > 0:
                        note += f"；{SCHEMA_REPAIR_NOTE}{result['schema_repairs']} 次"
                elif runtime_kind == "sandbox_skill":
                    outcome = agent.run_node(
                        self.ctx, node=node, record=record, handler=self._sandbox_handler
                    )
                    result = outcome["result"]
                    note = f"沙箱 Skill 执行：{record.get('name')}；产出 {len(result.get('revisions', []))} 个产物"
                else:
                    store.set_step(run_id, node_id, status="BLOCKED", error=f"未知 runtime 类型：{runtime_kind}")
                    return
            finally:
                if _scope is not None:
                    _scope.__exit__(None, None, None)
                if semaphore is not None:
                    semaphore.release()
            _finalize("SUCCEEDED", note="；".join(part for part in [gate_note, note] if part))
        except (pipeline.StepBlocked, SkillRuntimeBlocked) as exc:
            _finalize("BLOCKED", error=str(exc))
        except ConflictError as exc:
            _finalize("BLOCKED", error=f"preserve 契约阻止写入：{exc}")
        except (pipeline.StepFailed, SkillExecutionFailed) as exc:
            _finalize("FAILED", error=str(exc))
        except (IsolationViolation, AgentContractError) as exc:
            _finalize("FAILED", error=f"Subagent 契约违规：{exc}")
        except BudgetExceeded as exc:
            self.abort_run(str(exc))
            _finalize("BLOCKED", error=f"预算耗尽：{exc}")
        except pipeline.CancelledRun:
            _finalize("CANCELLED", error="运行已取消")
        except Exception as exc:  # noqa: BLE001 - unexpected failures must be recorded
            _finalize("FAILED", error=f"未预期错误：{exc}")


def execute_plan(*, engine: Any, run_id: str, ctx: pipeline.PipelineContext, plan: dict[str, Any]) -> None:
    runner = _Runner(engine, ctx)
    groups: dict[int, list[dict[str, Any]]] = {}
    for node in plan.get("nodes", []):
        groups.setdefault(int(node.get("parallel_group", 0) or 0), []).append(node)
    for level in sorted(groups):
        batch = sorted(groups[level], key=lambda item: item["node_id"])
        if len(batch) == 1:
            runner.execute_node(run_id, batch[0])
            continue
        with ThreadPoolExecutor(max_workers=min(runner.max_workers, len(batch))) as pool:
            futures = []
            for node in batch:
                if runner.skip_after_abort(run_id, node):
                    continue
                futures.append(pool.submit(runner.execute_node, run_id, node))
            for future in futures:
                future.result()
    engine._finalize_run_status(run_id)
