"""M6 §13/§48：PCK 证据状态政策（默认只允许 SUPPORTED，操作者可显式放行 QUALIFY_REQUIRED）。

放行的是带限定语的文本，不是"确定结论"；Evidence Gate 本身不降低。
"""

from __future__ import annotations

import pytest

from pebs import config, preconditions


class _FakeEvidence:
    def __init__(self, status: str):
        self.status = status

    def claim_status(self, claim_id, version):
        return self.status

    def latest_version(self, claim_id):
        return 1

    def get_claim(self, claim_id, version=None):
        return {"population": "大学生", "usage": "讲解", "text": "（已带限定语）"}


class _FakeCtx:
    def __init__(self, status: str):
        self.evidence = _FakeEvidence(status)

    def content(self, artifact_id):
        if artifact_id == "evidence_index":
            return {"claims": [{"claim_id": "clm_demo", "version": 1}]}
        return None


def _rules(statuses: list[str]) -> dict:
    rules = dict(config.RULES)
    rules["evidence"] = {"pck_claim_statuses": statuses}
    return rules


def test_default_policy_only_allows_supported(monkeypatch):
    monkeypatch.setattr(config, "RULES", _rules(["SUPPORTED"]))
    assert preconditions.allowed_claim_statuses() == ["SUPPORTED"]
    problems = preconditions.check_supported_claims(_FakeCtx("QUALIFY_REQUIRED"), inputs=["evidence_index"], usage_scope=["讲解"])
    assert problems and "QUALIFY_REQUIRED" in problems[0]
    assert preconditions.check_supported_claims(_FakeCtx("SUPPORTED"), inputs=["evidence_index"], usage_scope=["讲解"]) == []


def test_operator_can_opt_in_qualify_required_for_practice_courses(monkeypatch):
    monkeypatch.setattr(config, "RULES", _rules(["SUPPORTED", "QUALIFY_REQUIRED"]))
    assert preconditions.allowed_claim_statuses() == ["SUPPORTED", "QUALIFY_REQUIRED"]
    assert (
        preconditions.check_supported_claims(
            _FakeCtx("QUALIFY_REQUIRED"), inputs=["evidence_index"], usage_scope=["讲解"]
        )
        == []
    )
    # 仍未放行的状态继续 fail closed
    problems = preconditions.check_supported_claims(
        _FakeCtx("PENDING"), inputs=["evidence_index"], usage_scope=["讲解"]
    )
    assert problems and "PENDING" in problems[0]


def test_unknown_status_is_never_consumed(monkeypatch):
    monkeypatch.setattr(config, "RULES", _rules(["SUPPORTED", "QUALIFY_REQUIRED", "DISPUTED"]))
    problems = preconditions.check_supported_claims(
        _FakeCtx("UNSUPPORTED"), inputs=["evidence_index"], usage_scope=["讲解"]
    )
    assert problems and "UNSUPPORTED" in problems[0]
