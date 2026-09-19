"""Empty / unverifiable evidence must fail closed - there is no bypass.

The former rules.evidence.allow_empty_claims and allow_unverified_pck switches are
gone; these controls prove that neither configuration nor a declared "no evidence"
flag can let PCK author without consumable SUPPORTED evidence.
"""

from __future__ import annotations

import pytest
from conftest import REQUEST_1

from pebs import config, pipeline, preconditions

ALLOWED = preconditions.PCK_REQUIRED_STATUS


class _FakeEvidence:
    def __init__(self, status: str = ALLOWED):
        self.status = status

    def claim_status(self, claim_id, version):
        return self.status

    def latest_version(self, claim_id):
        return 1

    def get_claim(self, claim_id, version=None):
        return {"population": "大学生", "usage": "讲解", "text": "probe"}


class _FakeCtx:
    def __init__(self, index: dict):
        self._index = index
        self.evidence = _FakeEvidence()

    def content(self, artifact_id):
        return self._index if artifact_id == "evidence_index" else None


def _check(index: dict):
    return preconditions.check_supported_claims(
        _FakeCtx(index), inputs=["evidence_index"], usage_scope=["讲解"]
    )


def test_empty_evidence_index_blocks():
    problems = _check({"claims": []})
    assert problems and "证据索引为空" in problems[0]


def test_missing_claims_key_blocks():
    problems = _check({})
    assert problems and "证据索引为空" in problems[0]


def test_no_supported_claim_blocks():
    index = {"claims": [{"claim_id": "clm_x", "version": 1}], "excluded_claims": []}
    ctx = _FakeCtx(index)
    ctx.evidence = _FakeEvidence(status="QUALIFY_REQUIRED")
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"], usage_scope=["讲解"])
    assert problems and "QUALIFY_REQUIRED" in problems[0]


def test_declared_no_empirical_claims_cannot_bypass(monkeypatch):
    """The removed allow_empty_claims switch must not be replaceable by a declared flag."""
    monkeypatch.setattr(
        config,
        "RULES",
        {**config.RULES, "evidence": {"allow_empty_claims": True, "allow_unverified_pck": True}},
    )
    index = {
        "claims": [],
        "declared_no_empirical_claims": True,
        "declared_no_consumable_claims": True,
        "no_empirical_claims": True,
    }
    problems = _check(index)
    assert problems and "证据索引为空" in problems[0]


def test_declared_no_consumable_claims_cannot_bypass(monkeypatch):
    """...and neither can the removed allow_unverified_pck switch."""
    monkeypatch.setattr(
        config,
        "RULES",
        {**config.RULES, "evidence": {"allow_unverified_pck": True}},
    )
    index = {
        "claims": [],
        "declared_no_consumable_claims": True,
    }
    problems = _check(index)
    assert problems and "证据索引为空" in problems[0]


def test_zero_claims_fails_at_extraction_not_downstream(engine, monkeypatch):
    """An empty claim set fails at the claim-extractor, before PCK is ever reached."""
    original = pipeline._llm_json

    def fake(ctx, *, task, **kwargs):
        if task == "claims":
            return {"claims": []}
        return original(ctx, task=task, **kwargs)

    monkeypatch.setattr(pipeline, "_llm_json", fake)
    run_id = engine.store.create_run(request=REQUEST_1)
    changeset_id = engine.store.create_changeset(run_id, "empty claims probe", engine.store.current_baseline())
    ctx = engine._new_context(
        run_id=run_id,
        changeset_id=changeset_id,
        request=REQUEST_1,
        template_path=None,
        material_paths=[],
        environment="production",
    )
    with pytest.raises(pipeline.StepFailed) as excinfo:
        pipeline.step_claims(ctx)
    message = str(excinfo.value)
    assert "Claim 提取结果为空" in message
    assert "不会用空证据继续生产" in message
    # nothing reached the evidence contract or PCK
    assert not engine.store.revisions_of("evidence_index")
    assert not engine.store.revisions_of("teaching_plan:sec1")
