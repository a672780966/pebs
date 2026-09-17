"""M6 Golden Benchmark A–G 的 Plan 层可执行性（§20–§27, Acceptance 3 的离线部分）。

不调用真实模型：用不可用的 LLM 强制确定性路由 + 动态 Planner，
验证每个 Golden Case 都能形成正确的 DAG（该跳过的能力不进入 Plan）。
真实三模式对比由 `pebs.benchmark.runner` 在 provider 可用时执行。
"""

from __future__ import annotations

import time

import pytest
from conftest import FakeResearch, MissingLLM

from pebs import config
from pebs.benchmark import cases, checks
from pebs.engine import Engine

GOLDEN_IDS = ("A", "B", "C", "D", "E", "F", "G")

PLAN_ONLY_EXPECT_KEYS = {"plan", "routing", "content", "animation"}


@pytest.fixture
def bench_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def _new_engine(project: str) -> Engine:
    engine = Engine(project)
    engine.research = FakeResearch()
    return engine


def _wait(engine: Engine, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    status = engine.run_status(run_id)
    while status["run"]["status"] == "running" and time.time() < deadline:
        time.sleep(0.05)
        status = engine.run_status(run_id)
    return status


def _bootstrap_dependency(engine: Engine, case: dict) -> None:
    """§26/§27：依赖前序案例的 case（G 依赖 C 已完成课程）先补跑依赖案例。"""
    dependency_id = case.get("depends_on")
    if not dependency_id:
        return
    if any(item.get("accepted_rev") for item in engine.store.list_artifacts()):
        return
    from conftest import FakeLLM

    dependency = cases.get_case(dependency_id)
    # 只请求该案例真正要求的能力（默认 FakeLLM 语义层会附加 pptx，需要按案例约束）
    engine.llm = FakeLLM(
        route_payload={
            "task_intent": "课程脚本生产",
            "primary_outputs": ["script"],
            "secondary_outputs": [],
            "delivery_mode": "asynchronous_video",
            "learner_profile": {"level": "在职教师", "discipline": "托育", "prior_knowledge": "有"},
            "knowledge_types": ["concept", "case_analysis"],
            "research_need": "VERIFY",
            "media_need": "DIAGRAM",
            "assessment_need": True,
            "requested_outputs": ["script"],
            "risk_flags": [],
            "confidence": 0.8,
            "uncertainties": [],
        }
    )
    start = engine.start_build(
        dependency["request"],
        template_path=cases.fixture_path(dependency, "template_fixture"),
        material_paths=[cases.benchmark_dir() / name for name in dependency.get("material_fixtures") or []],
        planner_mode="dynamic",
    )
    status = _wait(engine, start["run_id"])
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    engine.accept(start["changeset_id"])


def _latest_content(engine: Engine, artifact_id: str) -> dict:
    """取最新 revision（candidate 也算），避免读到 bootstrap 依赖案例的 accepted 计划。"""
    revisions = engine.store.revisions_of(artifact_id)
    if not revisions:
        return {}
    return engine.store.get_revision(revisions[-1])["content"] or {}


def _plan_case(case: dict, project: str) -> tuple[dict, dict, dict]:
    engine = _new_engine(project)
    _bootstrap_dependency(engine, case)
    engine.llm = MissingLLM()
    from pebs.benchmark import runner

    runner.seed_case_artifacts(engine, case)
    template = cases.fixture_path(case, "template_fixture")
    materials = [cases.benchmark_dir() / name for name in case.get("material_fixtures") or []]
    start = engine.start_build(
        case["request"],
        template_path=template,
        material_paths=materials,
        planner_mode="dynamic",
    )
    deadline = time.time() + 30
    status = engine.run_status(start["run_id"])
    while status["run"]["status"] == "running" and time.time() < deadline:
        time.sleep(0.05)
        status = engine.run_status(start["run_id"])
    plan = _latest_content(engine, "build_plan_dynamic")
    route = _latest_content(engine, "router_result")
    return plan, route, status


@pytest.mark.parametrize("case_id", GOLDEN_IDS)
def test_golden_case_plan_is_runnable_and_skips_unneeded_capabilities(bench_projects, case_id):
    case = cases.get_case(case_id)
    plan, route, status = _plan_case(case, f"bench-{case_id.lower()}")
    assert plan.get("nodes"), f"{case_id}: planner produced no nodes"
    assert status["run"]["status"] in ("blocked", "failed", "succeeded", "cancelled")

    issues = checks.plan_checks(plan, case.get("expect") or {})
    assert not issues, f"{case_id}: {issues}"

    # §64：每个节点都要能解释为什么被选中
    trace = plan.get("selection_trace")
    assert trace, f"{case_id}: 缺少 selection_trace"
    for entry in trace:
        assert entry["selected"] and entry["reason"]


def test_benchmark_case_b_avoids_script_and_storyboard(bench_projects):
    case = cases.get_case("B")
    plan, _, _ = _plan_case(case, "bench-b-skip")
    skills = {node["skill"] for node in plan["nodes"]}
    assert "script-writer" not in skills
    assert "storyboard-designer" not in skills
    assert "pptx-deck" not in skills and {"presentation-planner", "presentation-composer"} <= skills


def test_benchmark_case_e_is_review_only(bench_projects):
    case = cases.get_case("E")
    plan, _, _ = _plan_case(case, "bench-e-review")
    executed = {node["skill"] for node in plan["nodes"] if not node.get("reused")}
    assert "script-writer" not in executed, "审阅任务不得重写已有讲稿"
    assert "presentation-composer" not in executed
    assert {"claim-extractor", "evidence-reviewer"} <= executed
    reused = {node["skill"] for node in plan["nodes"] if node.get("reused")}
    assert "script-writer" in reused, "已有讲稿应被复用为审阅对象"


def test_benchmark_case_g_reuses_existing_course(bench_projects):
    """§27：PPT-only 必须复用已有教案/脚本，而不是重写课程。"""
    from conftest import REQUEST_1, FakeLLM, run_dynamic_build

    engine = _new_engine("bench-g-reuse")
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    engine.accept(start["changeset_id"])
    plan, route, _ = _plan_case(cases.get_case("G"), "bench-g-reuse")
    assert plan["nodes"]
    reused = [node for node in plan["nodes"] if node.get("reused")]
    assert reused, "PPT-only 计划必须复用已有产物"
    executed = {node["skill"] for node in plan["nodes"] if not node.get("reused")}
    assert "script-writer" not in executed
