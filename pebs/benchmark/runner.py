"""Benchmark 执行器（M6 §28–§29, §41）：三种模式跑同一个 Golden Case 并落盘。

- builtin: 固定 Pipeline（planner=static）
- dynamic: Semantic Router + Dynamic DAG（planner=dynamic）
- direct_codex: 固定 baseline prompt 直接调用同一 LLM Provider（公平对照）
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .. import config, preconditions, providers
from ..engine import Engine
from . import cases, checks, metrics, trace

DIRECT_BASELINE_SYSTEM = (
    "你是一位资深教师教育设计者。请直接完成用户给出的课程生产任务，"
    "输出完整、可直接使用的教学产品；不要解释你的过程，不要省略内容。"
)


DIRECT_BASELINE_MATERIAL_BUDGET = 12000


def _baseline_inputs(case: dict[str, Any]) -> str:
    """§29：Direct baseline 必须拿到与 PEBS 相同的用户材料（模板 + 素材）。

    之前只给 request，PEBS 侧却同时拿到模板与素材文件，这对 baseline 不公平。
    素材按固定上限截断（§60 输入预算），避免把 benchmark 变成上下文长度竞赛。
    """
    from .. import template_parse

    blocks: list[str] = []
    template_path = cases.fixture_path(case, "template_fixture")
    if template_path is not None:
        try:
            spec = template_parse.parse_template(template_path)
            blocks.append(
                "模板结构（用户提供了一个 DOCX 模板，必须按它的栏目组织内容）：\n"
                + json.dumps(spec, ensure_ascii=False)[:2000]
            )
        except Exception:  # noqa: BLE001 - 解析失败时退化为只声明模板存在
            blocks.append(f"用户提供了一个 DOCX 模板：{template_path.name}")
    used = 0
    for name in case.get("material_fixtures") or []:
        path = cases.benchmark_dir() / name
        if not path.exists():
            continue
        try:
            text = str((template_parse.extract_text(path) or {}).get("text") or "")
        except Exception:  # noqa: BLE001
            continue
        remaining = max(DIRECT_BASELINE_MATERIAL_BUDGET - used, 0)
        if not remaining:
            break
        chunk = text[:remaining]
        used += len(chunk)
        blocks.append(f"用户提供的材料（{name}）：\n{chunk}")
    if not blocks:
        return ""
    return "用户材料：\n" + "\n\n".join(blocks) + "\n\n"


def direct_baseline_prompt(case: dict[str, Any]) -> str:
    """§29：Direct Codex baseline prompt 固定，给足信息，不故意写差。"""
    return (
        "任务：\n"
        f"{case['request']}\n\n"
        + _baseline_inputs(case)
        + "要求：\n"
        "- 输出语言文字与用户任务一致（中文）。\n"
        "- 结构化输出：先列学习目标，再按章节（或 8.1/8.2…）给出完整教学内容。\n"
        "- 每节包含教学策略、案例、讲解要点；案例必须可核查、不编造机构或研究。\n"
        "- 心理学结论保持审慎：区分相关与因果，标注理论不确定性。\n"
        "- 不做诊断、不给学生贴标签。\n"
    )


def seed_case_artifacts(engine: Engine, case: dict[str, Any]) -> list[str]:
    """把 case 声明的"既有产物"（如已有讲稿）以 accepted revision 写入 Store。

    这是 benchmark harness 的输入准备（§25 "输入一份已有心理学讲稿"），
    不新增任何 pipeline 能力；真实产品中的导入能力由 M7 评估。
    """
    from .. import config

    seeded: list[str] = []
    for entry in case.get("seed_artifacts") or []:
        artifact_id = entry["artifact_id"]
        artifact_type = entry["artifact_type"]
        if entry.get("from_markdown"):
            path = cases.benchmark_dir() / str(entry["from_markdown"])
            text = path.read_text(encoding="utf-8")
            section_id = str(entry.get("section_id") or "sec1")
            paragraphs = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith(("#", ">"))]
            units = [
                {"unit_id": f"u{index}", "kind": "narration", "text": paragraph, "claim_refs": []}
                for index, paragraph in enumerate(paragraphs, start=1)
            ]
            content = {
                "section_id": section_id,
                "title": str(entry.get("title") or "已有讲稿"),
                "units": units,
                "word_count": {
                    "count": sum(len(unit["text"]) for unit in units),
                    "min": 0,
                    "max": 99999,
                },
            }
        else:
            content = dict(entry.get("content") or {})
        info = engine.store.add_revision(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content=content,
            produced_by=str(entry.get("produced_by") or "benchmark-seed"),
            rules_version=config.RULES_VERSION,
        )
        engine.store.set_accepted(artifact_id, info["revision_id"])
        seeded.append(artifact_id)
    return seeded


def run_scenario(
    case_id: str,
    *,
    budgets: dict[str, int] | None = None,
    accept: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    """§26/§27：先跑完并接受基线课程，再执行 scenario（局部修改 / 只出 PPT）。

    - local_edit：调用 conversation_edit，并用 preserve 集合校验无关产物 hash 未变；
    - ppt_only：复用已有 learning_design/teaching_plan/script，只跑 media → slide_plan → pptx → QA。
    """
    case = cases.get_case(case_id)
    base_id = str(case.get("depends_on") or "")
    if not base_id:
        raise ValueError(f"{case_id} 未声明 depends_on，无法构造 scenario")
    base = cases.get_case(base_id)
    project = project_id or f"bench-{case_id.lower()}-{time.strftime('%H%M%S', time.localtime())}"
    target = run_dir(case_id, "scenario")
    target.mkdir(parents=True, exist_ok=True)
    started = time.time()

    engine = Engine(project)
    effective_budgets = dict(config.RULES.get("budgets") or {})
    effective_budgets.update(budgets or {})
    seed_case_artifacts(engine, base)
    base_start = engine.start_build(
        base["request"],
        template_path=cases.fixture_path(base, "template_fixture"),
        material_paths=[cases.benchmark_dir() / name for name in base.get("material_fixtures") or []],
        budgets=effective_budgets,
        planner_mode="dynamic",
    )
    base_status = _wait(engine, base_start["run_id"])
    if accept and base_status["run"]["status"] == "succeeded":
        engine.accept(base_start["changeset_id"])
    record: dict[str, Any] = {
        "case_id": case["id"],
        "case_title": case.get("title", ""),
        "mode": "scenario",
        "scenario": str(case.get("scenario")),
        "base_case": base_id,
        "base_run_id": base_start["run_id"],
        "base_run_status": base_status["run"]["status"],
        "project_id": project,
    }
    if base_status["run"]["status"] != "succeeded":
        record.update(
            {
                "run_status": base_status["run"]["status"],
                "note": "基线课程未成功，scenario 未执行",
                "metrics": {},
                "run_dir": str(target),
            }
        )
        (target / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return record

    before = metrics.snapshot_hashes(engine.store)
    scenario = str(case.get("scenario"))
    scenario_skills: list[dict[str, Any]] = []
    if scenario == "local_edit":
        instruction = str(case.get("edit_instruction") or case["request"])
        result = engine.conversation_edit(instruction)
        if accept and result.get("run_status") == "succeeded":
            engine.accept(result["changeset_id"])
        after = metrics.snapshot_hashes(engine.store)
        preserve = [str(item) for item in (case.get("preserve") or [])]
        locality = metrics.locality_report(
            before, after, preserve=preserve, expected=result.get("affected_artifacts") or []
        )
        record.update(
            {
                "run_id": result.get("run_id"),
                "run_status": result.get("run_status"),
                "edit": {
                    "instruction": instruction,
                    "plan_id": result.get("plan_id"),
                    "affected_artifacts": result.get("affected_artifacts"),
                    "locked_artifacts": result.get("locked_artifacts"),
                    "changeset_id": result.get("changeset_id"),
                },
                "locality": locality,
                "metrics": {
                    "locality_preservation_rate": locality["locality_preservation_rate"],
                    "unnecessary_regeneration": len(locality["unnecessary_regeneration"]),
                    "unnecessary_regeneration_rate": locality["unnecessary_regeneration_rate"],
                    "model_calls": int(engine.store.get_run(result["run_id"])["calls_used"]) if result.get("run_id") else 0,
                },
                "artifact_hashes": after,
            }
        )
    elif scenario == "ppt_only":
        start = engine.start_build(case["request"], budgets=effective_budgets, planner_mode="dynamic")
        status = _wait(engine, start["run_id"])
        if accept and status["run"]["status"] == "succeeded":
            engine.accept(start["changeset_id"])
        revisions = engine.store.revisions_of("build_plan_dynamic")
        plan = engine.store.get_revision(revisions[-1])["content"] if revisions else {}
        nodes = [(node.get("skill"), bool(node.get("reused"))) for node in plan.get("nodes", [])]
        reused = [skill for skill, flag in nodes if flag]
        try:
            scenario_trace = trace.build_trace(engine, start["run_id"], case_id=case["id"], mode="scenario")
            scenario_skills = scenario_trace.get("skills", [])
        except Exception:  # noqa: BLE001 - 场景 run 的 provenance 尽力而为
            scenario_skills = []
        record.update(
            {
                "run_id": start["run_id"],
                "run_status": status["run"]["status"],
                "plan_nodes": nodes,
                "metrics": {
                    "locality_preservation_rate": 1.0 if reused else 0.0,
                    "reuse_rate": round(len(reused) / max(len(nodes), 1), 3),
                    "model_calls": int(engine.store.get_run(start["run_id"])["calls_used"]),
                    "reused_skills": reused,
                },
                "artifact_hashes": metrics.snapshot_hashes(engine.store),
            }
        )
    else:
        record.update({"run_status": "blocked", "note": f"未知 scenario：{scenario}", "metrics": {}})

    record.update(
        {
            "wall_time_seconds": round(time.time() - started, 2),
            "fixtures": _fixture_hashes(case),
            "reproducibility": trace.reproducibility(
                fixture_hashes=_fixture_hashes(case), skills=scenario_skills
            ),
            "run_dir": str(target),
        }
    )
    record.setdefault("metrics", {})["wall_time_seconds"] = record["wall_time_seconds"]
    (target / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def run_dir(case_id: str, mode: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return cases.runs_dir() / f"{stamp}-{case_id}-{mode}"


def _fixture_hashes(case: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key in ("template_fixture",):
        path = cases.fixture_path(case, key)
        if path:
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    for name in case.get("material_fixtures") or []:
        path = cases.benchmark_dir() / str(name)
        if path.exists():
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return hashes


class _UnavailableLLM:
    """§46 无配额对照：只走确定性路由 + Planner，不调用任何模型。"""

    def availability(self) -> dict[str, Any]:
        return {"available": False, "reasons": ["benchmark plan-only：不调用 provider"], "id": "plan-only"}


def plan_only_case(case_id: str, *, extra_skills: list[str] | None = None, budgets: dict[str, int] | None = None) -> dict[str, Any]:
    """§46：对比同一任务在 Builtin / 显式外部 Skill 下的 DAG 与选择理由（零模型调用）。"""
    from .. import planner, router_v2

    case = cases.get_case(case_id)
    extra_skills = [str(item) for item in (extra_skills or [])]
    request = case["request"]
    if extra_skills:
        request = request.rstrip() + " " + " ".join(f"/{name}" for name in extra_skills)
    template_spec = None
    template_path = cases.fixture_path(case, "template_fixture")
    if template_path:
        from ..template_parse import parse_template

        try:
            template_spec = parse_template(template_path)
        except Exception:  # noqa: BLE001 - 解析失败时按无模板处理
            template_spec = None
    llm = _UnavailableLLM()
    route = router_v2.route(
        request,
        llm=llm,
        template_spec=template_spec,
        materials=[str(cases.benchmark_dir() / name) for name in case.get("material_fixtures") or []],
        explicit_skills=extra_skills,
    )
    plan = planner.plan(
        route=route,
        goal=request,
        existing_artifacts=[],
        budgets=budgets or dict(config.RULES.get("budgets") or {}),
        prefer=extra_skills,
        pinned=_pinned_skill_names(),
    )
    return {
        "case_id": case["id"],
        "mode": "plan",
        "variant": ("plan [+" + ",".join(extra_skills) + "]") if extra_skills else "plan [builtin]",
        "experiment": ",".join(extra_skills),
        "run_status": "planned",
        "route": {
            "task_intent": route.get("task_intent"),
            "knowledge_types": route.get("knowledge_types"),
            "requested_outputs": route.get("requested_outputs"),
            "research_need": route.get("research_need"),
            "media_need": route.get("media_need"),
            "source": route.get("source"),
        },
        "plan_nodes": [(node.get("skill"), bool(node.get("reused"))) for node in plan.get("nodes", [])],
        "terminal_outputs": plan.get("terminal_outputs", []),
        "selection_trace": plan.get("selection_trace", []),
        "explicit_skills_note": (plan.get("route_notes") or {}).get("explicit_skills", []),
        "metrics": {"model_calls": 0, "research_calls": 0, "node_count": len(plan.get("nodes", []))},
    }


def _pinned_skill_names() -> list[str]:
    from ..engine import _pinned_skill_names as engine_pinned

    return engine_pinned()


def run_case(
    case_id: str,
    *,
    mode: str = "dynamic",
    project_id: str | None = None,
    budgets: dict[str, int] | None = None,
    accept: bool = True,
    extra_skills: list[str] | None = None,
    experiment: str = "",
) -> dict[str, Any]:
    case = cases.get_case(case_id)
    if case.get("scenario"):
        # F（local edit）/ G（ppt-only）等场景必须先有"已完成课程"，由 run_scenario 处理
        return run_scenario(case_id, budgets=budgets, accept=accept)
    extra_skills = [str(item) for item in (extra_skills or [])]
    if extra_skills:
        # §46 Skill Selection Experiment：显式 `/skill-name` 追加到请求，
        # 用于 Builtin only / External only / Hybrid 对照（不改 case 定义）。
        case = dict(case)
        case["request"] = case["request"].rstrip() + " " + " ".join(f"/{name}" for name in extra_skills)
    errors = cases.validate_case(case)
    if errors:
        raise ValueError("; ".join(errors))
    if mode not in cases.VALID_MODES:
        raise ValueError(f"unknown mode: {mode}")
    # §31：把预算交给 Planner，使其在预算不足时生成降级 Plan（而不是执行到一半 BLOCKED）
    effective_budgets = dict(config.RULES.get("budgets") or {})
    effective_budgets.update(budgets or {})
    # 默认给每次 benchmark run 一个独立项目：否则第二次跑同一 case 会复用上一次的
    # 已接受产物（calls=0、Plan 全 reuse），得到不可比的"空跑"结果。
    project = project_id or f"bench-{case_id.lower()}-{mode}-{time.strftime('%H%M%S', time.localtime())}"
    target = run_dir(case_id, mode)
    target.mkdir(parents=True, exist_ok=True)
    started = time.time()

    if mode == "direct_codex":
        record = _run_direct(case, target)
    else:
        record = _run_pebs(case, mode=mode, project=project, budgets=effective_budgets, accept=accept)

    record.update(
        {
            "case_id": case["id"],
            "case_title": case.get("title", ""),
            "mode": mode,
            "project_id": project,
            # §35/§41：本次运行实际生效的证据政策（来自冻结契约的唯一权威常量），
            # 该字段此前只被报告/UI/材料包/API 读取，从未写过分毫。
            "evidence_policy": [preconditions.PCK_REQUIRED_STATUS],
            "wall_time_seconds": round(time.time() - started, 2),
            "fixtures": _fixture_hashes(case),
            "reproducibility": (record.get("trace") or {}).get("reproducibility")
            or trace.reproducibility(fixture_hashes=_fixture_hashes(case)),
            "experiment": experiment or ("+".join(extra_skills) if extra_skills else ""),
            "extra_skills": extra_skills,
            "run_dir": str(target),
        }
    )
    record.setdefault("metrics", {})["wall_time_seconds"] = record["wall_time_seconds"]
    (target / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def _static_plan(engine: Any, run_id: str) -> dict[str, Any]:
    """把静态 Pipeline 的实际执行步骤合成为 plan 形状，供 plan 期望检查使用。

    静态模式没有 DAG，但"这一 case 必须具备哪些能力"对 Builtin 基线同样成立：
    合成节点的 skill/steps/outputs 都来自注册表，不编造。DAG 专属期望
    （terminal_outputs / 复用率）在 `plan_checks(static_plan=True)` 里跳过。
    """
    from .. import registry

    nodes: list[dict[str, Any]] = []
    for step in engine.store.get_steps(run_id):
        skill = trace._skill_for_step(step["step_id"])
        record = registry.get(skill) if skill else None
        nodes.append(
            {
                "node_id": step["step_id"],
                "skill": skill or step["step_id"],
                "steps": [step["step_id"]],
                "outputs": list((record or {}).get("produces") or []),
                "reused": False,
                "status": step["status"],
            }
        )
    return {"plan_id": f"static:{run_id}", "nodes": nodes, "terminal_outputs": [], "reused_artifacts": []}


def _run_pebs(case: dict[str, Any], *, mode: str, project: str, budgets: dict[str, int] | None, accept: bool) -> dict[str, Any]:
    engine = Engine(project)
    seed_case_artifacts(engine, case)
    request = case["request"]
    template_path = cases.fixture_path(case, "template_fixture")
    material_paths = [cases.benchmark_dir() / name for name in case.get("material_fixtures") or []]
    planner_mode = "dynamic" if mode in ("dynamic", "mixed") else "static"
    start = engine.start_build(
        request,
        template_path=template_path,
        material_paths=material_paths,
        budgets=budgets,
        planner_mode=planner_mode,
    )
    run_id = start["run_id"]
    status = _wait(engine, run_id)
    if status["run"]["status"] == "running":
        # harness 已到等待上限仍在运行：如实标记为 interrupted，避免留下悬挂的 "running"
        engine.store.set_run_status(run_id, "interrupted")
        status = engine.run_status(run_id)
    if accept and status["run"]["status"] == "succeeded":
        engine.accept(start["changeset_id"])

    steps = status["steps"]
    run_record = engine.store.get_run(run_id)
    skill_trace = trace.build_trace(
        engine,
        run_id,
        case_id=case["id"],
        mode=mode,
        fixture_hashes=_fixture_hashes(case),
    )
    summary = metrics.summarize_run(skill_trace)
    hashes = metrics.snapshot_hashes(engine.store)
    plan = engine.store.accepted_content("build_plan_dynamic") or {}
    static_run = planner_mode != "dynamic"
    # 静态 Pipeline 不产出 DAG 产物：若不合成，plan 期望会对空计划逐条报"缺少"，
    # 让 Builtin 基线凭空多出 5+ 条 PLAN 错误，直接污染 §28 的 Builtin vs Dynamic 对比。
    plan_for_checks = _static_plan(engine, run_id) if static_run and not plan else plan
    route = engine.store.accepted_content("router_result") or {}
    automatic = checks.evaluate(
        engine.store, case.get("expect") or {}, plan=plan_for_checks, route=route, static_plan=static_run
    )
    from . import safety as safety_mod

    # §19/§39/§40：每次 benchmark run 都记入 performance registry（只 observe/record）
    from . import performance as performance_mod

    performance_mod.record_trace(
        skill_trace,
        latency_by_skill={
            str(item.get("skill")): float(item.get("duration") or 0.0)
            for item in skill_trace.get("skills", [])
            if item.get("skill")
        },
        model_calls_by_skill={
            str(item.get("skill")): int(item.get("model_calls") or 0)
            for item in skill_trace.get("skills", [])
            if item.get("skill")
        },
    )

    return {
        "run_id": run_id,
        "changeset_id": start["changeset_id"],
        "run_status": status["run"]["status"],
        "steps": [(step["step_id"], step["status"], step.get("error") or "") for step in steps],
        "metrics": {
            **summary,
            "model_calls": int(run_record.get("calls_used", 0)),
            "research_calls": int(run_record.get("research_used", 0)),
        },
        "artifact_hashes": hashes,
        "automatic_issues": automatic,
        "quality_metrics": safety_mod.content_metrics(engine.store),
        "trace": skill_trace,
    }


def _run_direct(case: dict[str, Any], target: Path) -> dict[str, Any]:
    llm = providers.get_llm()
    availability = llm.availability()
    if not availability.get("available"):
        return {
            "run_id": "",
            "run_status": "blocked",
            "metrics": {"model_calls": 0, "research_calls": 0},
            "artifact_hashes": {},
            "trace": {},
            "blocked_reason": "; ".join(availability.get("reasons", [])),
        }
    prompt = direct_baseline_prompt(case)
    response = llm.generate_text(system=DIRECT_BASELINE_SYSTEM, prompt=prompt) if hasattr(llm, "generate_text") else None
    if response is None:
        data = llm.generate_json(
            task="benchmark_direct",
            system=DIRECT_BASELINE_SYSTEM,
            prompt=prompt + "\n输出 JSON：{\"content\": \"...\"}",
        )
        response = str(data.get("content") or "")
    (target / "direct_output.md").write_text(str(response), encoding="utf-8")
    (target / "direct_prompt.txt").write_text(prompt, encoding="utf-8")
    return {
        "run_id": "",
        "run_status": "succeeded",
        "metrics": {"model_calls": 1, "research_calls": 0, "output_chars": metrics.char_count(str(response))},
        "artifact_hashes": {},
        "trace": {},
        "output_chars": metrics.char_count(str(response)),
    }


def _wait_timeout(run: dict[str, Any]) -> float:
    """等待上限必须≥运行自身的时间预算，否则 harness 会在 run 仍运行时误报 running。"""
    budget = int(run.get("budget_seconds") or 0)
    return float(max(3600, budget + 600))


def _wait(engine: Engine, run_id: str, timeout: float | None = None) -> dict[str, Any]:
    if timeout is None:
        try:
            timeout = _wait_timeout(engine.store.get_run(run_id))
        except Exception:  # noqa: BLE001 - 取不到 budget 时退回 1 小时
            timeout = 3600.0
    deadline = time.time() + timeout
    status = engine.run_status(run_id)
    while status["run"]["status"] == "running" and time.time() < deadline:
        time.sleep(1.0)
        status = engine.run_status(run_id)
    return status


def simulate_local_edit(case_id: str, *, project: str, instruction: str, preserve: list[str]) -> dict[str, Any]:
    """§26 / Acceptance 7：在动态模式完成后执行自然语言局部修改，并验证 preserve 集 hash 不变。"""
    engine = Engine(project)
    before = metrics.snapshot_hashes(engine.store)
    result = engine.conversation_edit(instruction)
    after = metrics.snapshot_hashes(engine.store)
    locality = metrics.locality_report(before, after, preserve=preserve)
    if result.get("run_status") == "succeeded":
        engine.accept(result["changeset_id"])
        locality["accepted"] = True
    return {"edit": result, "locality": locality}
