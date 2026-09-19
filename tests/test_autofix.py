from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, FakeResearch, run_build

from pebs.pipeline import _fix_prompt

REQUEST = "任务1 观察记录。每节 100–200 字，每节至少 1 个案例。"


def test_fix_prompt_includes_exact_count_guidance():
    over = {"word_count": {"count": 413, "min": 300, "max": 400}, "units": []}
    prompt = _fix_prompt({"section_id": "sec1", "title": "t"}, over, [], {})
    assert "超出上限 13 字" in prompt
    assert "至少删减 13 字" in prompt
    under = {"word_count": {"count": 280, "min": 300, "max": 400}, "units": []}
    prompt = _fix_prompt({"section_id": "sec1", "title": "t"}, under, [], {})
    assert "不足下限 20 字" in prompt
    assert "至少补足 20 字" in prompt


def test_research_uses_llm_generated_english_query(engine):
    engine.research = FakeResearch()
    run_build(engine, REQUEST_1)
    assert engine.research.queries == ["observation record fact judgment preschool"]


def test_teaching_plan_strategy_violation_triggers_regeneration(engine):
    engine.llm = FakeLLM(invalid_strategy_first=True)
    run_id, changeset_id = run_build(engine, REQUEST)
    assert engine.llm.calls.get("teaching_plan") == 1
    assert engine.llm.calls.get("teaching_plan_fix") == 1
    engine.accept(changeset_id)
    g3 = engine.store.accepted_content("gate:G3:script:sec1")
    assert g3["status"] == "PASS"


def test_auto_fix_round_makes_g1_pass(engine):
    engine.llm = FakeLLM(undershoot_first=1)
    run_id, changeset_id = run_build(engine, REQUEST)
    assert engine.store.get_run(run_id)["status"] == "succeeded"
    revisions = engine.store.revisions_of("script:sec1")
    assert len(revisions) == 2
    assert engine.llm.calls["script_fix"] == 1
    engine.accept(changeset_id)
    g1 = engine.store.accepted_content("gate:G1:script:sec1")
    assert g1["status"] == "PASS"
    assert engine.store.get_revision(revisions[-1])["content"]["word_count"]["in_range"] is True


def test_auto_fix_capped_at_two_rounds(engine):
    engine.llm = FakeLLM(undershoot_first=99, fix_bad=True)
    run_id, changeset_id = run_build(engine, REQUEST)
    assert engine.llm.calls["script_fix"] == 2
    assert len(engine.store.revisions_of("script:sec1")) == 3
    engine.accept(changeset_id)
    g1 = engine.store.accepted_content("gate:G1:script:sec1")
    assert g1["status"] == "FAIL"
    step = next(s for s in engine.store.get_steps(run_id) if s["step_id"] == "gates")
    assert "上限" in (step["note"] or "")
    draft = engine.export_now("draft")
    assert draft["ok"] is True
    assert all(f["label"] == "草稿—未通过 QA" for f in draft["manifest"]["files"])


def test_safety_fix_removes_diagnosis_wording(engine):
    engine.llm = FakeLLM(unsafe_first=1)
    run_id, changeset_id = run_build(engine, REQUEST)
    assert engine.llm.calls["script_fix"] == 1
    engine.accept(changeset_id)
    g4 = engine.store.accepted_content("gate:G4:script:sec1")
    assert g4["status"] == "PASS"


def test_dynamic_auto_fix_survives_the_subagent_contract(engine):
    """真实生产发现：动态链路里 QA 自动修正会被 Subagent 契约挡下。

    gate-runner（qa-agent）契约只声明 produces=gate_result，但 `fix_script` 会在
    门禁节点内重写 `script:<sec>`（AUTO_FIX_GATES = G1/G4/G7），
    于是动态运行直接 FAILED："qa-agent 不允许产出 artifact 类型：script"。
    静态路径（run_build）没有契约层，所以这个缺陷此前没有被测到。
    """
    from conftest import run_dynamic_build

    # 用紧字数控（每节 100–200 字）才会真的触发 G1 FAIL → 自动修正
    engine.llm = FakeLLM(undershoot_first=1)
    start, status = run_dynamic_build(engine, REQUEST)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    gate_step = next(step for step in status["steps"] if step["step_id"] == "gate-runner")
    assert gate_step["status"] == "SUCCEEDED"
    # 自动修正确实在门禁节点内重写了脚本（否则第二个 revision 不会存在）
    assert len(engine.store.revisions_of("script:sec1")) >= 2, gate_step.get("note")


def test_dynamic_gate_reads_artifacts_outside_its_contract(engine):
    """§71-8 Gate False Negative：门禁必须能看到本轮 run 的全部产物。

    `ctx.outputs` 是 Subagent 契约过滤后的视图，gate-runner 的 requires 里没有
    `requirements`，于是 G1 的字数检查会拿到空 requirements 并**静默 PASS**
    ——动态链路的门禁被悄悄削弱。修好后 G1 必须先 FAIL，再被自动修正。
    """
    from conftest import run_dynamic_build

    engine.llm = FakeLLM(undershoot_first=1)
    start, status = run_dynamic_build(engine, REQUEST)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]

    # 门禁必须真的看到 requirements 里的字数要求：
    # 先在 25 字的脚本上 FAIL，再自动修正到范围内（只 emit 最终结果，故查 note）
    gate_step = next(step for step in status["steps"] if step["step_id"] == "gate-runner")
    note = gate_step.get("note") or ""
    assert "自动修正" in note, note
    assert "25 字" in note, note

    scripts = engine.store.revisions_of("script:sec1")
    assert len(scripts) >= 2, note
    first = engine.store.get_revision(scripts[0])["content"]
    last = engine.store.get_revision(scripts[-1])["content"]
    assert first["word_count"]["in_range"] is False
    assert last["word_count"]["in_range"] is True


def test_unverifiable_evidence_blocks_pck_and_downstream_authoring(engine):
    """With no evidence provider, PCK must not author and nothing may bypass that."""
    engine.research = FakeResearch(available=False)
    run_id, changeset_id = run_build(engine, REQUEST_1)

    steps = {step["step_id"]: step for step in engine.store.get_steps(run_id)}
    assert steps["teaching_plan"]["status"] == "BLOCKED"
    assert "执行前置条件未满足" in (steps["teaching_plan"]["error"] or "")

    # Downstream authoring cannot bypass the blocked precondition.
    for downstream in ("scripts", "gates", "preview"):
        assert steps[downstream]["status"] == "BLOCKED"
    assert engine.store.revisions_of("script:sec1") == []
    assert not engine.store.revisions_of("preview")
