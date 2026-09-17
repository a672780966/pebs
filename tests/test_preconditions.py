"""Execution preconditions (owner decision A): QA gates vs entry contracts.

G1-G8 stay artifact QA gates; the PCK entry check is a precondition with an
implementation behind it, so it fails closed instead of being an unsatisfiable
`gates_before: ["G2"]` declaration that the runtime could never evaluate.
"""

from __future__ import annotations

from conftest import REQUEST_1, run_build

import pytest

from pebs import gates, pipeline, preconditions, registry
from pebs.conversation import impact as _impact  # noqa: F401  (import order parity)


class _FakeEvidence:
    def __init__(self, *, status="SUPPORTED", latest=1, population="大学生", usage="讲解"):
        self.status = status
        self.latest = latest
        self.claim = {"population": population, "usage": usage}

    def claim_status(self, claim_id, version):
        return self.status

    def latest_version(self, claim_id):
        return self.latest

    def get_claim(self, claim_id, version=None):
        return dict(self.claim)


class _FakeCtx:
    def __init__(self, index, evidence=None):
        self._index = index
        self.evidence = evidence or _FakeEvidence()

    def content(self, artifact_id):
        return self._index if artifact_id == "evidence_index" else None


def _index(*entries):
    return {"claims": list(entries)}


ONE = {"claim_id": "clm_demo", "version": 1, "status": "SUPPORTED"}


def test_empty_evidence_index_blocks():
    problems = preconditions.check_supported_claims(_FakeCtx({}), inputs=["evidence_index"])
    assert problems and "证据索引为空" in problems[0]


def test_unsupported_claim_blocks():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(status="PENDING"))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"])
    assert any("PENDING" in item and "SUPPORTED" in item for item in problems)


def test_stale_claim_version_blocks():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(latest=2))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"])
    assert any("已被新版本取代" in item for item in problems)


def test_claim_without_population_blocks():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(population=""))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"])
    assert any("population" in item for item in problems)


def test_claim_without_usage_blocks():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(usage=""))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"])
    assert any("usage" in item for item in problems)


def test_placeholder_usage_blocks():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(usage=preconditions.PLACEHOLDER_USAGE))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"])
    assert any("待核验占位" in item for item in problems)


def test_supported_in_scope_claim_passes():
    ctx = _FakeCtx(_index(ONE))
    assert preconditions.check_supported_claims(ctx, inputs=["evidence_index"]) == []


def test_unknown_precondition_kind_blocks_fail_closed():
    ctx = _FakeCtx(_index(ONE))
    problems = preconditions.evaluate(ctx, {"preconditions": [{"kind": "not_implemented"}]})
    assert any("未实现的前置条件" in item for item in problems)


def _primed_ctx(engine, run_id, changeset_id):
    ctx = engine._new_context(
        run_id=run_id,
        changeset_id=changeset_id,
        request=REQUEST_1,
        template_path=None,
        material_paths=[],
        environment="production",
    )
    for artifact in engine.store.list_artifacts():
        if artifact.get("accepted_rev"):
            ctx.outputs[artifact["artifact_id"]] = artifact["accepted_rev"]
    return ctx


def _accepted_engine(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    return run_id


def test_pck_step_blocks_when_a_consumed_claim_is_unsupported(engine):
    run_id = _accepted_engine(engine)
    index = engine.store.accepted_content("evidence_index")
    claim = index["claims"][0]
    engine.evidence.set_claim_status(f"{claim['claim_id']}@v{claim['version']}", "UNSUPPORTED")

    ctx = _primed_ctx(engine, run_id, engine.store.create_changeset(run_id, "pck precondition", engine.store.current_baseline()))
    with pytest.raises(pipeline.StepBlocked) as excinfo:
        pipeline.step_teaching_plan(ctx)
    message = str(excinfo.value)
    assert "执行前置条件未满足" in message
    assert "SUPPORTED" in message


def test_pck_step_runs_when_evidence_is_supported_and_in_scope(engine):
    run_id = _accepted_engine(engine)
    ctx = _primed_ctx(engine, run_id, engine.store.create_changeset(run_id, "pck ok", engine.store.current_baseline()))
    pipeline.step_teaching_plan(ctx)
    assert "teaching_plan:sec1" in ctx.outputs


def test_post_generation_g2_still_runs_on_the_script(engine):
    _accepted_engine(engine)
    # G2 remains a post-authoring evidence gate evaluated by the gate runner.
    assert engine.store.accepted_rev_id("gate:G2:script:sec1") is not None
    assert gates.GATE_SCOPE["G2"] == "script"


def test_registry_no_longer_declares_unsatisfiable_gate_contracts():
    skills = registry.load_skills()
    assert skills["pck-developer"]["gates_before"] == []
    assert skills["script-writer"]["gates_before"] == []
    assert skills["evidence-reviewer"]["gates_after"] == []
    kinds = {item["kind"] for item in skills["pck-developer"]["preconditions"]}
    assert kinds == {"supported_claims"}
    # PCK declares which usage slot it consumes, so unrelated claims stay out of scope.
    assert skills["pck-developer"]["preconditions"][0]["usage_scope"] == ["讲解"]
    assert set(preconditions.PRECONDITION_KINDS) >= kinds
    for gate, scope in gates.GATE_SCOPE.items():
        assert gate in gates.ALL_GATES
        assert scope in ("script", "export_manifest")


class _ScopeEvidence(_FakeEvidence):
    """An in-scope SUPPORTED claim alongside an unrelated PENDING one."""

    def get_claim(self, claim_id, version=None):
        if claim_id == "clm_case":
            return {"population": "大学生", "usage": "案例"}
        return {"population": "大学生", "usage": "讲解"}

    def claim_status(self, claim_id, version):
        return "PENDING" if claim_id == "clm_case" else "SUPPORTED"


def test_out_of_scope_claim_does_not_poison_pck():
    """A pending claim in another usage slot must not block a valid PCK run."""
    entries = _index(ONE, {"claim_id": "clm_case", "version": 1, "status": "SUPPORTED"})
    problems = preconditions.check_supported_claims(
        _FakeCtx(entries, _ScopeEvidence()), inputs=["evidence_index"], usage_scope=["讲解"]
    )
    assert problems == []


def test_in_scope_unsupported_claim_blocks_under_declared_scope():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(status="PENDING", usage="讲解"))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"], usage_scope=["讲解"])
    assert any("PENDING" in item for item in problems)


def test_no_in_scope_claims_blocks_fail_closed():
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(usage="评价"))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"], usage_scope=["讲解"])
    assert any("证据契约范围内" in item for item in problems)


def test_undeclared_scope_still_validates_every_indexed_claim():
    """Without a declared scope nothing is filtered: fail closed on all of it."""
    ctx = _FakeCtx(_index(ONE), _FakeEvidence(status="DISPUTED", usage="案例"))
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"])
    assert any("DISPUTED" in item for item in problems)
