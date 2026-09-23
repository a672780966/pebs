from __future__ import annotations

import difflib
import json
import sys
import threading
from pathlib import Path
from typing import Any

from . import config, gates, memory, pipeline, pii, project_rules
from .evidence import EvidenceStore
from .hooks import Hooks
from .permissions import PermissionDenied, PermissionManager
from .providers import get_llm, get_research
from .runtime.step_context import step_scope
from .store import BudgetExceeded, ConflictError, Store, StoreError, canonical_json, now_iso


class PlanEditRejected(Exception):
    pass


def _pinned_skill_names() -> list[str]:
    """自动偏好的 pinned Skill。

    M6 §18：Provider 安装的外部 Skill 不自动偏好——
    生产默认仍用 Builtin；外部 Skill 必须通过显式 `/skill-name`（§43 Explicit User
    Choice）或 benchmark 实验指定，直到 §68 的 promotion 门槛达成（M7 才会把历史
    表现用于路由）。

    判据是来源而非执行 provider：`provider` 记录的是该 Skill 允许在哪些执行来源
    下运行（`permissions.py` 把它当白名单用），内置记录本身也标注 `default-llm` /
    `default-research`，所以“provider 非空即跳过”会误排除将来 pin 住的 Builtin；
    而通用导入路径（`skills_mgr.derive_contract`）对未声明 provider 的上游会把
    `provider` 落成 `[]`，只看 provider 又会让外部导入溜进自动偏好。

    `self_implemented` 才是导入路径显式写入的来源标志（外部导入恒为 False，见
    `skills_mgr`），`resolver.choose()` 亦用它优先 Builtin。字段缺失按外部处理：
    宁可漏掉一次自动偏好，也不能让外部 Skill 自动上路由。
    """
    from . import registry

    names = []
    for name, record in registry.load_skills().items():
        if not record.get("pinned_version") or record.get("status") not in ("APPROVED", "PATCHED"):
            continue
        if record.get("self_implemented") is not True:
            continue
        names.append(name)
    return sorted(names)


class PiiBlocked(Exception):
    pass


class ExplicitSkillDenied(Exception):
    pass


def _last_frame() -> str:
    """最后一个 traceback 帧的 `文件:行号`（便于从 step 错误直接定位语句）。"""
    import traceback

    frames = traceback.extract_tb(sys.exc_info()[2])
    if not frames:
        return "无 traceback"
    last = frames[-1]
    return f"{Path(last.filename).name}:{last.lineno} {last.name}"


class Engine:
    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_id = project_id
        if base_dir is None:
            base = config.ensure_project_dirs(project_id)
        else:
            base = Path(base_dir)
            for sub in ["inputs", "artifacts", "snapshots", "outputs/draft", "outputs/formal", "memory", "logs"]:
                (base / sub).mkdir(parents=True, exist_ok=True)
        self.base = base
        project_rules.ensure_project_rules(base)
        self.store = Store(project_id, base)
        self.evidence = EvidenceStore(self.store)
        self.permissions = PermissionManager()
        self.hooks = Hooks(self.store, self.evidence, self.permissions)
        self.llm = get_llm()
        self.research = get_research()
        self._run_threads: list[threading.Thread] = []
        self._thread_lock = threading.Lock()
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        for run in self.store.interrupted_runs():
            for step in self.store.get_steps(run["run_id"]):
                if step["status"] == "RUNNING":
                    self.store.set_step(
                        run["run_id"],
                        step["step_id"],
                        status="BLOCKED",
                        error="应用中途中止；重启后待恢复，需核对输入与已完成产物后重跑",
                    )
            self.store.set_run_status(run["run_id"], "interrupted")

    def close(self, *, join_timeout: float | None = 30.0) -> None:
        """Join in-flight run threads before closing the store.

        A worker still running when the connection closes would fail with an
        unhandled thread exception and could leave a run record half-written, so
        the teardown order is: stop accepting work, join, then close.
        """
        self._join_run_threads(join_timeout)
        self.store.close()

    def _join_run_threads(self, timeout: float | None) -> None:
        with self._thread_lock:
            threads = [thread for thread in self._run_threads if thread.is_alive()]
            self._run_threads = threads
        for thread in threads:
            thread.join(timeout)

    def _track_run_thread(self, thread: threading.Thread) -> None:
        """Start a run thread and keep it for the close-time join."""
        thread.start()
        with self._thread_lock:
            self._run_threads = [item for item in self._run_threads if item.is_alive()]
            self._run_threads.append(thread)

    # ------------------------------------------------------------------ context

    def _start_dynamic_build(
        self,
        request: str,
        *,
        template_path: Path | None,
        material_paths: list[Path],
        environment: str,
        explicit_skills: list[str],
        budgets: dict[str, int],
    ) -> dict[str, Any]:
        from . import planner, router_v2

        template_spec = self.store.accepted_content("template_spec")
        rules_path = Path(self.base) / "PROJECT_RULES.md"
        project_rules = rules_path.read_text(encoding="utf-8") if rules_path.exists() else ""
        artifacts = self.store.list_artifacts()
        route = router_v2.route(
            request,
            llm=self.llm,
            template_spec=template_spec if isinstance(template_spec, dict) else None,
            materials=[str(path) for path in material_paths],
            explicit_skills=explicit_skills,
            existing_artifacts=artifacts,
            project_rules=project_rules,
        )
        errors = router_v2.validate(route)
        if errors:
            from .routing import fallback as routing_fallback
            from .routing import intent as routing_intent

            route = routing_fallback.fallback_route(
                routing_intent.extract_deterministic(
                    request,
                    template_spec=template_spec if isinstance(template_spec, dict) else None,
                    materials=[str(path) for path in material_paths],
                    explicit_skills=explicit_skills,
                )
            )
            route["uncertainties"].extend(errors)
        dynamic_plan = planner.plan(
            route=route,
            goal=request,
            existing_artifacts=artifacts,
            budgets=budgets,
            prefer=explicit_skills,
            pinned=_pinned_skill_names(),
        )
        for artifact_id, artifact_type, content in (
            ("router_result", "router_result", route),
            ("build_plan_dynamic", "build_plan_v2", dynamic_plan),
        ):
            info = self.store.add_revision(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                content=content,
                produced_by="dynamic-planner",
                rules_version=config.RULES_VERSION,
            )
            self.store.set_accepted(artifact_id, info["revision_id"])

        run_id = self.store.create_run(
            environment=environment,
            request=request,
            budgets=budgets,
            inputs={
                "template_path": str(template_path) if template_path else None,
                "material_paths": [str(p) for p in material_paths],
                "explicit_skills": explicit_skills,
                "planner": "dynamic",
                "plan_id": dynamic_plan.get("plan_id"),
            },
        )
        changeset_id = self.store.create_changeset(
            run_id, f"dynamic build: {request[:60]}", self.store.current_baseline()
        )
        for node in dynamic_plan.get("nodes", []):
            self.store.add_step(run_id, node["node_id"], node["title"])
        thread = threading.Thread(
            target=self._execute_dynamic,
            args=(run_id, changeset_id, request, template_path, material_paths, environment, dynamic_plan),
            daemon=True,
        )
        self._track_run_thread(thread)
        return {
            "run_id": run_id,
            "changeset_id": changeset_id,
            "planner": "dynamic",
            "plan_id": dynamic_plan.get("plan_id"),
            "terminals": dynamic_plan.get("terminal_outputs"),
            "degraded": dynamic_plan.get("degraded"),
        }

    def _execute_dynamic(
        self,
        run_id: str,
        changeset_id: str,
        request: str,
        template_path: Path | None,
        material_paths: list[Path],
        environment: str,
        dynamic_plan: dict[str, Any],
    ) -> None:
        from .runtime.executor import execute_plan

        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=request,
            template_path=template_path,
            material_paths=material_paths,
            environment=environment,
            explicit_skills=pipeline.parse_explicit_skills(request),
        )
        execute_plan(engine=self, run_id=run_id, ctx=ctx, plan=dynamic_plan)

    def _new_context(
        self,
        *,
        run_id: str,
        changeset_id: str,
        request: str,
        template_path: Path | None,
        material_paths: list[Path],
        environment: str,
        explicit_skills: list[str] | None = None,
    ) -> pipeline.PipelineContext:
        return pipeline.PipelineContext(
            store=self.store,
            evidence=self.evidence,
            hooks=self.hooks,
            permissions=self.permissions,
            llm=self.llm,
            research=self.research,
            project_id=self.project_id,
            run_id=run_id,
            changeset_id=changeset_id,
            request=request,
            environment=environment,
            template_path=template_path,
            material_paths=material_paths,
            explicit_skills=list(explicit_skills or []),
        )

    def save_plan(self, plan: dict[str, Any]) -> str:
        info = self.store.add_revision(
            artifact_id="build_plan",
            artifact_type="build_plan",
            content=plan,
            produced_by="planner",
            rules_version=config.RULES_VERSION,
        )
        self.store.set_accepted("build_plan", info["revision_id"])
        return info["revision_id"]

    def current_plan(self) -> dict[str, Any]:
        content = self.store.accepted_content("build_plan")
        if content is None:
            return {"plan_id": "plan_m1", "project_id": self.project_id, "created_at": "", "steps": pipeline.plan_steps()}
        return content

    # ------------------------------------------------------------------ build

    def start_build(
        self,
        request: str,
        *,
        template_path: Path | None = None,
        material_paths: list[Path] | None = None,
        environment: str = "production",
        budgets: dict[str, int] | None = None,
        planner_mode: str | None = None,
    ) -> dict[str, Any]:
        material_paths = material_paths or []
        hits = pii.scan(request)
        if hits:
            raise PiiBlocked(
                "请求文本包含可识别学生资料（" + pii.summarize(hits) + "），已在发送前暂停；请脱敏后重试"
            )
        explicit_skills = pipeline.parse_explicit_skills(request)
        for name in explicit_skills:
            try:
                self.permissions.skill(name)
            except PermissionDenied as exc:
                raise ExplicitSkillDenied(f"显式调用被拒绝：/{name}（{exc}）") from exc
        effective_budgets = budgets or config.RULES.get("budgets", {})
        mode = str(
            planner_mode or config.RULES.get("planner", {}).get("mode", "static")
        ).strip().lower()
        if mode == "dynamic":
            return self._start_dynamic_build(
                request,
                template_path=template_path,
                material_paths=material_paths,
                environment=environment,
                explicit_skills=explicit_skills,
                budgets=effective_budgets,
            )
        plan = self.current_plan()
        run_id = self.store.create_run(
            environment=environment,
            request=request,
            budgets=budgets or config.RULES.get("budgets", {}),
            inputs={
                "template_path": str(template_path) if template_path else None,
                "material_paths": [str(p) for p in material_paths],
                "explicit_skills": explicit_skills,
            },
        )
        changeset_id = self.store.create_changeset(run_id, f"build: {request[:60]}", self.store.current_baseline())
        for step in plan["steps"]:
            self.store.add_step(run_id, step["step_id"], step["title"])
        thread = threading.Thread(
            target=self._execute,
            args=(run_id, changeset_id, request, template_path, material_paths, environment),
            daemon=True,
        )
        self._track_run_thread(thread)
        return {"run_id": run_id, "changeset_id": changeset_id}

    def _execute(
        self,
        run_id: str,
        changeset_id: str,
        request: str,
        template_path: Path | None,
        material_paths: list[Path],
        environment: str,
    ) -> None:
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=request,
            template_path=template_path,
            material_paths=material_paths,
            environment=environment,
            explicit_skills=pipeline.parse_explicit_skills(request),
        )
        self._run_steps(ctx, run_id)

    def _run_steps(self, ctx: pipeline.PipelineContext, run_id: str, step_ids: set[str] | None = None) -> None:
        plan = self.current_plan()
        steps = {s["step_id"]: s for s in plan["steps"]}
        order = [s["step_id"] for s in plan["steps"]]
        tracked = set(order) if step_ids is None else set(step_ids)
        for step_id in order:
            step = steps[step_id]
            if step_ids is not None and step_id not in step_ids:
                continue
            if step.get("disabled"):
                self.store.set_step(run_id, step_id, status="CANCELLED", note="用户禁用")
                continue
            if ctx.store.get_run(run_id)["status"] == "cancelled":
                self.store.set_step(run_id, step_id, status="CANCELLED", note="运行已取消")
                continue
            blocked_by = [
                dep
                for dep in step["depends_on"]
                if dep in tracked and self._step_status(run_id, dep) != "SUCCEEDED"
            ]
            if blocked_by:
                self.store.set_step(
                    run_id,
                    step_id,
                    status="BLOCKED",
                    error="依赖步骤未成功：" + "、".join(blocked_by),
                )
                continue
            self.store.set_step(run_id, step_id, status="RUNNING", bump_attempt=True)
            handler = pipeline.STEPS.get(step_id)
            try:
                if handler is None:
                    raise pipeline.StepFailed(f"未实现步骤：{step_id}")
                # §39：静态链路也要把模型调用记到步骤上（否则 builtin 基线 per-skill 成本恒为 0）
                with step_scope(step_id):
                    result = handler(ctx)
                notes = result.get("notes", []) if isinstance(result, dict) else []
                self.store.set_step(
                    run_id,
                    step_id,
                    status="SUCCEEDED",
                    note="；".join(str(n) for n in notes[:8]),
                    output_revs=list(ctx.outputs.values())[-8:] if ctx.outputs else [],
                )
            except pipeline.StepBlocked as exc:
                self.store.set_step(run_id, step_id, status="BLOCKED", error=str(exc))
            except ConflictError as exc:
                self.store.set_step(run_id, step_id, status="BLOCKED", error=f"preserve 契约阻止写入：{exc}")
            except pipeline.StepFailed as exc:
                self.store.set_step(run_id, step_id, status="FAILED", error=str(exc))
            except BudgetExceeded as exc:
                self.store.set_step(run_id, step_id, status="BLOCKED", error=f"预算耗尽：{exc}")
                break
            except pipeline.CancelledRun:
                self.store.set_step(run_id, step_id, status="CANCELLED", error="运行已取消")
                continue
            except Exception as exc:  # noqa: BLE001 - unexpected failures must be recorded
                # 记下最后一帧位置：`未预期错误：unhashable type: 'list'` 这种信息无法定位，
                # 但加上 `pipeline.py:1901` 就能直接找到出问题的语句。
                self.store.set_step(
                    run_id, step_id, status="FAILED", error=f"未预期错误：{exc}（{_last_frame()}）"
                )
        statuses = [s["status"] for s in self.store.get_steps(run_id)]
        final = self._compute_run_status(statuses)
        self.store.set_run_status(run_id, final)

    @staticmethod
    def _compute_run_status(statuses: list[str]) -> str:
        if "FAILED" in statuses:
            return "failed"
        if "BLOCKED" in statuses:
            return "blocked"
        if "CANCELLED" in statuses and "PENDING" not in statuses and "RUNNING" not in statuses:
            return "cancelled"
        return "succeeded"

    def _finalize_run_status(self, run_id: str) -> None:
        statuses = [s["status"] for s in self.store.get_steps(run_id)]
        self.store.set_run_status(run_id, self._compute_run_status(statuses))

    def _step_status(self, run_id: str, step_id: str) -> str:
        rows = [s for s in self.store.get_steps(run_id) if s["step_id"] == step_id]
        return rows[0]["status"] if rows else "PENDING"

    def run_status(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        run["baseline"] = json.loads(run["baseline"])
        return {"run": run, "steps": self.store.get_steps(run_id)}

    def cancel(self, run_id: str) -> dict[str, Any]:
        self.store.cancel_run(run_id)
        return self.run_status(run_id)

    def resume(self, run_id: str, *, budgets: dict[str, int] | None = None) -> dict[str, Any]:
        """Section 84 resume: adjust the budget, then re-dispatch budget-blocked steps.

        Only steps whose recorded failure is a budget abort are re-dispatched; a
        step blocked for any other reason would fail the same way again. Work
        this run already produced is primed into the context, so completed nodes
        are reused rather than executed a second time.
        """
        run = self.store.get_run(run_id)
        applied = self.store.set_budgets(run_id, budgets) if budgets else None
        blocked = [
            step["step_id"]
            for step in self.store.get_steps(run_id)
            if step["status"] == "BLOCKED" and "预算耗尽" in (step.get("error") or "")
        ]
        if not blocked:
            self._finalize_run_status(run_id)
            return {
                "run_id": run_id,
                "resumed": [],
                "budgets": applied,
                "reason": "没有预算阻塞的步骤",
                "run_status": self.store.get_run(run_id)["status"],
            }
        inputs = run.get("inputs") or {}
        changeset_id = self.store.create_changeset(
            run_id, f"resume: {run_id}", self.store.current_baseline()
        )
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=run["request"],
            template_path=Path(inputs["template_path"]) if inputs.get("template_path") else None,
            material_paths=[Path(path) for path in inputs.get("material_paths", [])],
            environment=run["environment"],
            explicit_skills=inputs.get("explicit_skills") or [],
        )
        for item in self.store.run_changeset_items(run_id):
            ctx.outputs.setdefault(item["artifact_id"], item["revision_id"])
        self.store.set_run_status(run_id, "running")
        if inputs.get("planner") == "dynamic":
            plan = self.store.accepted_content("build_plan_dynamic") or {}
            if not plan.get("nodes"):
                raise PlanEditRejected("找不到可恢复的动态计划")
            from .runtime import executor as executor_mod

            executor_mod.execute_plan(engine=self, run_id=run_id, ctx=ctx, plan=plan)
        else:
            self._run_steps(ctx, run_id, step_ids=set(blocked))
        return {
            "run_id": run_id,
            "resumed": sorted(blocked),
            "budgets": applied,
            "changeset_id": changeset_id,
            "run_status": self.store.get_run(run_id)["status"],
        }

    def rerun_from(self, step_id: str, *, environment: str | None = None) -> dict[str, Any]:
        plan = self.current_plan()
        steps = plan["steps"]
        order = [s["step_id"] for s in steps]
        if step_id not in order:
            raise PlanEditRejected(f"未知步骤：{step_id}")
        selected = order[order.index(step_id):]
        last_run = self.store.latest_run()
        inputs = (last_run.get("inputs") if last_run else {}) or {}
        env = environment or (last_run["environment"] if last_run else "production")
        template_path = Path(inputs["template_path"]) if inputs.get("template_path") else None
        material_paths = [Path(p) for p in inputs.get("material_paths", [])]
        run_id = self.store.create_run(
            environment=env,
            request=(last_run["request"] if last_run else "") or f"rerun from {step_id}",
            budgets=config.RULES.get("budgets", {}),
            inputs=inputs,
        )
        changeset_id = self.store.create_changeset(
            run_id, f"rerun from {step_id}", self.store.current_baseline()
        )
        for sid in selected:
            step = next(s for s in steps if s["step_id"] == sid)
            self.store.add_step(run_id, sid, step["title"])
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=(last_run["request"] if last_run else "") or "",
            template_path=template_path,
            material_paths=material_paths,
            environment=env,
        )
        self._run_steps(ctx, run_id, step_ids=set(selected))
        return {"run_id": run_id, "changeset_id": changeset_id, "steps": selected}

    # ------------------------------------------------------------------ plan edits

    def edit_plan(self, op: str, step_id: str, index: int | None = None) -> dict[str, Any]:
        plan = self.current_plan()
        steps = plan["steps"]
        step = next((s for s in steps if s["step_id"] == step_id), None)
        if step is None:
            raise PlanEditRejected(f"未知步骤：{step_id}")
        if op == "disable":
            if step.get("kind") in ("gate", "export") or step.get("required") and any(
                step_id in other["depends_on"] for other in steps if not other.get("disabled")
            ):
                raise PlanEditRejected("该步骤是必需依赖，禁用会破坏依赖顺序或绕过质量门禁")
            step["disabled"] = True
        elif op == "enable":
            step["disabled"] = False
        elif op == "lock":
            step["locked"] = True
        elif op == "unlock":
            step["locked"] = False
        elif op == "move":
            if index is None or not (0 <= index < len(steps)):
                raise PlanEditRejected("非法的目标位置")
            steps.remove(step)
            steps.insert(index, step)
            position = {s["step_id"]: i for i, s in enumerate(steps)}
            for candidate in steps:
                for dep in candidate["depends_on"]:
                    if position[dep] >= position[candidate["step_id"]]:
                        raise PlanEditRejected(
                            f"移动后 {candidate['step_id']} 早于其依赖 {dep}，违反依赖顺序"
                        )
        else:
            raise PlanEditRejected(f"未知操作：{op}")
        self.save_plan(plan)
        return plan

    # ------------------------------------------------------------------ changesets

    def accept(self, changeset_id: str) -> dict[str, Any]:
        try:
            result = self.store.accept_changeset(changeset_id)
        except ConflictError as exc:
            return {"ok": False, "reason": str(exc)}
        self._release_patch_locks(changeset_id)
        result["published"] = self._publish_formal(changeset_id)
        memory.write_memory(self.store)
        return result

    def reject(self, changeset_id: str) -> dict[str, Any]:
        try:
            result = self.store.reject_changeset(changeset_id)
        except ConflictError as exc:
            return {"ok": False, "reason": str(exc)}
        self._release_patch_locks(changeset_id)
        self._discard_staging(changeset_id)
        return result

    def _patch_locks(self, changeset_id: str) -> list[str]:
        """Conversational Patch 的 preserve 集合：由 Store 强制执行（accept/reject 时释放）。"""
        try:
            changeset = self.store.get_changeset(changeset_id)
            run = self.store.get_run(changeset["run_id"]) if changeset.get("run_id") else None
        except Exception:  # noqa: BLE001 - 无 run 的 changeset 没有 patch 锁
            return []
        raw_inputs = (run or {}).get("inputs") or {}
        if isinstance(raw_inputs, str):
            try:
                raw_inputs = json.loads(raw_inputs)
            except json.JSONDecodeError:
                raw_inputs = {}
        plan_id = raw_inputs.get("patch_plan")
        if not plan_id:
            return []
        content = self.store.accepted_content("patch_plan") or {}
        if content.get("plan_id") != plan_id:
            return []
        return list(content.get("locked_artifacts", []))

    def _release_patch_locks(self, changeset_id: str) -> None:
        for artifact_id in self._patch_locks(changeset_id):
            self.store.set_locked(artifact_id, False)

    def _staging_dir(self, changeset_id: str) -> Path:
        return Path(self.store.base_dir) / "outputs" / "staging" / changeset_id

    def _publish_formal(self, changeset_id: str) -> list[str]:
        import shutil

        staging = self._staging_dir(changeset_id)
        if not staging.exists():
            return []
        formal = Path(self.store.base_dir) / "outputs" / "formal"
        formal.mkdir(parents=True, exist_ok=True)
        published: list[str] = []
        cs = self.store.get_changeset(changeset_id)
        for item in cs["items"]:
            revision = item["revision"]
            if revision["artifact_type"] != "export_manifest":
                continue
            content = revision["content"]
            if content.get("mode") != "formal":
                continue
            for entry in content.get("files", []):
                source = Path(entry["path"])
                if source.exists() and staging in source.parents:
                    target = formal / source.name
                    shutil.move(str(source), str(target))
                    published.append(str(target))
        shutil.rmtree(staging, ignore_errors=True)
        return published

    def _discard_staging(self, changeset_id: str) -> None:
        import shutil

        shutil.rmtree(self._staging_dir(changeset_id), ignore_errors=True)

    def diff(self, changeset_id: str, max_lines: int = 400) -> list[dict[str, Any]]:
        cs = self.store.get_changeset(changeset_id)
        diffs = []
        for item in cs["items"]:
            artifact_id = item["artifact_id"]
            new_rev = item["revision"]
            old_rev_id = cs["baseline"].get(artifact_id) or self.store.accepted_rev_id(artifact_id)
            old_content = None
            if old_rev_id and old_rev_id != item["revision_id"]:
                try:
                    old_content = self.store.get_revision(old_rev_id)["content"]
                except StoreError:
                    old_content = None
            if old_content is None:
                lines = ["+++ 新建 " + artifact_id]
                lines += ("+ " + line for line in canonical_json(new_rev["content"])[:2000].splitlines())
            else:
                old_lines = canonical_json(old_content).splitlines()
                new_lines = canonical_json(new_rev["content"]).splitlines()
                lines = list(
                    difflib.unified_diff(
                        old_lines,
                        new_lines,
                        fromfile=f"{artifact_id}@{old_rev_id}",
                        tofile=item["revision_id"],
                        lineterm="",
                    )
                )[:max_lines]
            diffs.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": new_rev["artifact_type"],
                    "revision_id": item["revision_id"],
                    "old_revision_id": old_rev_id,
                    "changed": old_content is None or old_content != new_rev["content"],
                    "diff": lines,
                }
            )
        return diffs

    # ------------------------------------------------------------------ case replace

    def case_replace(
        self,
        case_artifact_id: str,
        instruction: str,
        *,
        environment: str = "production",
    ) -> dict[str, Any]:
        old_rev_id = self.store.accepted_rev_id(case_artifact_id)
        if not old_rev_id:
            raise StoreError(f"case not accepted: {case_artifact_id}")
        if self.store.is_locked(case_artifact_id):
            raise ConflictError(f"artifact locked: {case_artifact_id}")
        old_case = self.store.get_revision(old_rev_id)["content"]
        run_id = self.store.create_run(environment=environment, request=f"replace {case_artifact_id}: {instruction}")
        changeset_id = self.store.create_changeset(
            run_id, f"replace {case_artifact_id}", self.store.current_baseline()
        )
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=instruction,
            template_path=None,
            material_paths=[],
            environment=environment,
        )
        affected_sections: list[str] = []
        for artifact in self.store.list_artifacts():
            if artifact["artifact_type"] != "script" or not artifact["accepted_rev"]:
                continue
            if old_rev_id in self.store.upstream_revs(artifact["accepted_rev"]):
                affected_sections.append(artifact["artifact_id"].split(":", 1)[1])
        try:
            new_case = pipeline.replace_case(ctx, case_artifact_id, old_case, instruction)
            ctx.outputs[case_artifact_id] = new_case["revision_id"]
            if affected_sections:
                ctx.section_filter = affected_sections
                for step_id in [
                    "scripts",
                    "media_plan",
                    "diagrams",
                    "storyboard",
                    "evidence_assets",
                    "slide_plan",
                    "pptx",
                    "gates",
                    "preview",
                    "export",
                ]:
                    handler = pipeline.STEPS[step_id]
                    self.store.set_step(run_id, step_id, status="RUNNING", bump_attempt=True)
                    with step_scope(step_id):
                        result = handler(ctx)
                    self.store.set_step(
                        run_id, step_id, status="SUCCEEDED", note="；".join(str(n) for n in result.get("notes", [])[:8])
                    )
            self.store.set_run_status(run_id, "succeeded")
        except pipeline.StepBlocked as exc:
            self.store.set_step(run_id, "case_replace", status="BLOCKED", error=str(exc))
            self.store.set_run_status(run_id, "blocked")
        except pipeline.StepFailed as exc:
            self.store.set_step(run_id, "case_replace", status="FAILED", error=str(exc))
            self.store.set_run_status(run_id, "failed")
        return {
            "run_id": run_id,
            "changeset_id": changeset_id,
            "affected_sections": affected_sections,
        }

    def edit_slide(self, slide_number: int, patch: dict[str, Any]) -> dict[str, Any]:
        allowed = {"title", "points", "core_message", "notes", "density"}
        unknown = set(patch) - allowed
        if unknown:
            raise PlanEditRejected(f"不支持的幻灯片字段：{sorted(unknown)}")
        if not patch:
            raise PlanEditRejected("没有需要修改的字段")
        if patch.get("points") is not None and len(patch["points"]) > 6:
            raise PlanEditRejected("每页要点不超过 6 条")
        source_rev = self.store.accepted_rev_id("slide_plan")
        if not source_rev:
            raise StoreError("slide_plan 尚未接受，先接受变更集再编辑")
        content = json.loads(json.dumps(self.store.get_revision(source_rev)["content"]))
        rows = content.get("rows", [])
        target = next((row for row in rows if int(row.get("slide", 0)) == int(slide_number)), None)
        if target is None:
            raise PlanEditRejected(f"找不到第 {slide_number} 页")
        target.update(patch)
        run_id = self.store.create_run(request=f"edit slide {slide_number}")
        changeset_id = self.store.create_changeset(
            run_id, f"edit slide {slide_number}", self.store.current_baseline()
        )
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=f"edit slide {slide_number}",
            template_path=None,
            material_paths=[],
            environment="production",
        )
        ctx.emit("slide_plan", "slide_plan", content, "slide-editor", deps=[source_rev])
        for step_id in ["pptx", "gates", "preview", "export"]:
            handler = pipeline.STEPS[step_id]
            self.store.set_step(run_id, step_id, status="RUNNING", bump_attempt=True)
            try:
                with step_scope(step_id):
                    result = handler(ctx)
            except pipeline.StepBlocked as exc:
                self.store.set_step(run_id, step_id, status="BLOCKED", error=str(exc))
                self.store.set_run_status(run_id, "blocked")
                return {"ok": False, "reason": str(exc), "changeset_id": changeset_id}
            except pipeline.StepFailed as exc:
                self.store.set_step(run_id, step_id, status="FAILED", error=str(exc))
                self.store.set_run_status(run_id, "failed")
                return {"ok": False, "reason": str(exc), "changeset_id": changeset_id}
            self.store.set_step(
                run_id, step_id, status="SUCCEEDED", note="；".join(str(n) for n in result.get("notes", [])[:8])
            )
        self.store.set_run_status(run_id, "succeeded")
        return {
            "ok": True,
            "run_id": run_id,
            "changeset_id": changeset_id,
            "slide": slide_number,
            "patched": sorted(patch),
        }

    def record_signoff(self, changeset_id: str, *, reviewer: str, basis: str, changes: str = "") -> dict[str, Any]:
        if not reviewer.strip():
            raise PlanEditRejected("签署必须记录复核人")
        if not basis.strip():
            raise PlanEditRejected("签署必须记录复核依据（不能只点击按钮）")
        cs = self.store.get_changeset(changeset_id)
        if cs["status"] != "accepted":
            raise PlanEditRejected("只能对已接受的变更集签署")
        versions = {item["artifact_id"]: item["revision_id"] for item in cs["items"]}
        content = {
            "changeset_id": changeset_id,
            "reviewer": reviewer.strip(),
            "basis": basis.strip(),
            "changes": changes.strip(),
            "artifact_versions": versions,
            "items": len(versions),
            "created_at": now_iso(),
        }
        info = self.store.add_revision(
            artifact_id=f"signoff:{changeset_id}",
            artifact_type="review_record",
            content=content,
            produced_by="teacher-review",
        )
        self.store.set_accepted(f"signoff:{changeset_id}", info["revision_id"])
        return content

    def review_claim(self, claim_id: str, version: int, **kwargs: Any) -> dict[str, Any]:
        return self.evidence.review_claim(claim_id, version, **kwargs)

    def conversation_edit(self, message: str, *, execute: bool = True) -> dict[str, Any]:
        from . import registry as skill_registry
        from .conversation import impact as impact_mod
        from .conversation import interpreter as interpreter_mod
        from .conversation import patch_plan as patch_mod
        from .conversation import resolver as resolver_mod

        if not (message or "").strip():
            raise PlanEditRejected("修改消息为空")
        requirements = self.store.accepted_content("requirements") or {}
        sections = requirements.get("sections", [])
        artifacts = self.store.list_artifacts()
        slides = (self.store.accepted_content("slide_plan") or {}).get("rows", [])
        script_units: list[dict[str, Any]] = []
        for section in sections:
            script = self.store.accepted_content(f"script:{section['section_id']}") or {}
            for unit in script.get("units", []):
                script_units.append({"section_id": section["section_id"], "text": unit.get("text", "")})

        intent = interpreter_mod.interpret(message, llm=self.llm, sections=sections)
        resolved = resolver_mod.resolve(
            message, intent, sections=sections, artifacts=artifacts, slides=slides, script_units=script_units
        )
        target_ids = list(resolved["artifact_ids"])
        if not target_ids and resolved["section_ids"]:
            for artifact in artifacts:
                if not artifact.get("accepted_rev"):
                    continue
                parts = artifact["artifact_id"].split(":")[1:]
                if any(section_id in parts for section_id in resolved["section_ids"]):
                    target_ids.append(artifact["artifact_id"])
        if not target_ids:
            raise PlanEditRejected(f"无法定位修改目标：{message}")

        impact_result = impact_mod.impact(self.store, target_ids)
        write_types: set[str] = set()
        for artifact_id in impact_result["affected"]:
            type_name = artifact_id.split(":", 1)[0]
            for producer in skill_registry.producers_of(type_name):
                record = skill_registry.get(producer) or {}
                write_types.update(record.get("emits") or record.get("produces", []))
        affected = set(impact_result["affected"])
        target_set = set(target_ids)
        section_scope = set(resolved["section_ids"])
        for artifact in artifacts:
            if not artifact.get("accepted_rev") or artifact["artifact_type"] not in write_types:
                continue
            artifact_id = artifact["artifact_id"]
            if ":" in artifact_id and section_scope:
                parts = artifact_id.split(":")[1:]
                if not any(part in section_scope for part in parts):
                    continue
            affected.add(artifact_id)
        impact_result["affected"] = sorted(affected)
        ordered = [artifact_id for artifact_id in impact_result["order"] if artifact_id in affected]
        impact_result["order"] = ordered + sorted(affected - set(ordered))
        step_filter = set()
        # Producers are indexed by pointer artifact_type: a gate artifact is
        # registered as `gate_result` while its id reads `gate:G1:script:sec2`.
        # Resolve both, or the gate step is never re-run and a rebuilt section
        # keeps the stale gate results of the previous revision.
        producer_types = {artifact_id.split(":", 1)[0] for artifact_id in affected}
        producer_types.update(
            artifact["artifact_type"] for artifact in artifacts if artifact["artifact_id"] in affected
        )
        for type_name in producer_types:
            for producer in skill_registry.producers_of(type_name):
                record = skill_registry.get(producer) or {}
                step_filter.update(record.get("handler", {}).get("steps", []))
        locked = sorted(
            artifact["artifact_id"]
            for artifact in artifacts
            if artifact.get("accepted_rev")
            and artifact["artifact_id"] not in affected
            and artifact["artifact_id"] not in target_set
        )
        patch = patch_mod.build(
            message=message,
            intent=intent,
            resolved=resolved,
            impact_result=impact_result,
            accepted_artifacts={artifact["artifact_id"]: artifact for artifact in artifacts},
            locked_artifacts=locked,
        )
        info = self.store.add_revision(
            artifact_id="patch_plan",
            artifact_type="patch_plan",
            content=patch,
            produced_by="conversation",
            rules_version=config.RULES_VERSION,
        )
        self.store.set_accepted("patch_plan", info["revision_id"])
        if not execute:
            return patch

        run_id = self.store.create_run(
            request=message,
            budgets=config.RULES.get("budgets", {}),
            inputs={"conversation": True, "patch_plan": patch["plan_id"]},
        )
        changeset_id = self.store.create_changeset(
            run_id, f"conversation: {message[:60]}", self.store.current_baseline()
        )
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=message,
            template_path=None,
            material_paths=[],
            environment="production",
        )
        ctx.section_filter = resolved["section_ids"] or None
        for artifact_id in locked:
            self.store.set_locked(artifact_id, True)
        self._run_steps(ctx, run_id, step_ids=step_filter)
        return {
            **patch,
            "run_id": run_id,
            "changeset_id": changeset_id,
            "run_status": self.store.get_run(run_id)["status"],
        }

    # ------------------------------------------------------------------ export on demand

    def export_now(self, mode: str = "draft") -> dict[str, Any]:
        from . import export as export_mod
        from .hooks import HookFailure

        run_id = self.store.create_run(request=f"export {mode}")
        changeset_id = self.store.create_changeset(run_id, f"export {mode}", self.store.current_baseline())
        ctx = self._new_context(
            run_id=run_id,
            changeset_id=changeset_id,
            request=f"export {mode}",
            template_path=None,
            material_paths=[],
            environment="production",
        )
        gate_ctx = gates.GateContext(store=self.store, evidence=self.evidence, run_id=run_id, environment="production")
        readiness = gates.export_readiness_with_overrides(gate_ctx)
        try:
            if mode == "formal":
                self.hooks.before_final_export(readiness)
        except HookFailure as exc:
            self.store.set_run_status(run_id, "blocked")
            return {"ok": False, "reason": str(exc), "changeset_id": changeset_id}
        manifest = export_mod.write_exports(ctx, mode=mode, gate_ctx=gate_ctx)
        info = ctx.emit("export_manifest", "export_manifest", manifest, "docx-exporter")
        gate_ctx.overrides["export_manifest"] = info["revision_id"]
        g8 = gates.g8_artifact(gate_ctx, "export_manifest")
        if mode == "formal" and g8["status"] != "PASS":
            manifest = export_mod.write_exports(
                ctx, mode="draft", gate_ctx=gate_ctx, note="正式导出未通过 G8，已降级为草稿"
            )
            info = ctx.emit(
                "export_manifest", "export_manifest", manifest, "docx-exporter", deps=[info["revision_id"]]
            )
            gate_ctx.overrides["export_manifest"] = info["revision_id"]
            g8 = gates.g8_artifact(gate_ctx, "export_manifest")
            mode = "draft"
        ctx.emit(
            gates.gate_artifact_id("G8", "export_manifest"),
            "gate_result",
            g8,
            "gate-runner",
            deps=[info["revision_id"]],
        )
        self.store.set_run_status(run_id, "succeeded")
        return {
            "ok": True,
            "changeset_id": changeset_id,
            "mode": mode,
            "manifest": manifest,
            "g8": g8["status"],
        }
