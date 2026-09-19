"""Frozen Stage E evidence contract: PCK may consume only SUPPORTED, current, in-scope claims.

The acceptable status is a single immutable authority
(pebs.preconditions.PCK_REQUIRED_STATUS) - no rules key, CLI flag, benchmark argument,
environment variable or project setting may widen it. This module owns the negative
policy controls.
"""

from __future__ import annotations

import pathlib

import pytest
from conftest import REQUEST_1, run_build

from pebs import cli, config, preconditions

ALLOWED = preconditions.PCK_REQUIRED_STATUS
OTHER_STATUSES = ["QUALIFY_REQUIRED", "PENDING", "UNSUPPORTED", "DISPUTED", "HUMAN_REVIEW_REQUIRED"]


class _FakeEvidence:
    def __init__(self, status: str, usage: str = "讲解"):
        self.status = status
        self.usage = usage

    def claim_status(self, claim_id, version):
        return self.status

    def latest_version(self, claim_id):
        return 1

    def get_claim(self, claim_id, version=None):
        return {"population": "大学生", "usage": self.usage, "text": "（已带限定语）"}


class _FakeCtx:
    def __init__(self, status: str, usage: str = "讲解", index: dict | None = None):
        self.evidence = _FakeEvidence(status, usage)
        self._index = index if index is not None else {"claims": [{"claim_id": "clm_demo", "version": 1}]}

    def content(self, artifact_id):
        return self._index if artifact_id == "evidence_index" else None


def _check(status: str, *, usage: str = "讲解", scope=("讲解",), index: dict | None = None):
    return preconditions.check_supported_claims(
        _FakeCtx(status, usage, index), inputs=["evidence_index"], usage_scope=list(scope) or None
    )


def test_supported_in_scope_passes():
    assert _check(ALLOWED) == []


@pytest.mark.parametrize("status", OTHER_STATUSES)
def test_every_other_status_blocks(status):
    problems = _check(status)
    assert problems and status in problems[0], problems


def test_qualify_required_never_satisfies_the_precondition():
    problems = _check("QUALIFY_REQUIRED")
    assert problems
    assert ALLOWED in problems[0]


def test_multi_token_usage_intersecting_the_scope_is_consumed():
    assert _check(ALLOWED, usage="讲解/案例/评价", scope=("讲解",)) == []


def test_multi_token_usage_without_intersection_is_ignored():
    problems = _check(ALLOWED, usage="案例/评价", scope=("讲解",))
    assert problems, "an out-of-scope claim is not consumed and must not satisfy PCK"
    assert "证据契约范围内没有可用于 PCK 的 SUPPORTED Claim" in problems[0]


def test_config_cannot_widen_the_consumable_status(monkeypatch):
    """The frozen policy must not be weakenable through configuration."""
    monkeypatch.setattr(
        config,
        "RULES",
        {
            **config.RULES,
            "evidence": {
                "pck_claim_statuses": [ALLOWED, "QUALIFY_REQUIRED"],
                "allow_empty_claims": True,
                "allow_unverified_pck": True,
            },
        },
    )
    problems = _check("QUALIFY_REQUIRED")
    assert problems and "QUALIFY_REQUIRED" in problems[0]


def test_no_configuration_driven_status_helper_exists():
    source = pathlib.Path(preconditions.__file__).read_text(encoding="utf-8")
    assert "allowed_claim_statuses" not in source
    assert "pck_claim_statuses" not in source
    assert "allow_empty_claims" not in source
    assert "allow_unverified_pck" not in source


def test_rules_no_longer_declare_an_evidence_policy():
    assert "pck_claim_statuses" not in (config.RULES.get("evidence") or {})
    rules_text = pathlib.Path(config.CONFIG_DIR, "rules.yaml").read_text(encoding="utf-8")
    for key in ("pck_claim_statuses", "allow_empty_claims", "allow_unverified_pck"):
        assert key not in rules_text


def test_cli_no_longer_exposes_any_relaxation_flag():
    source = pathlib.Path(cli.__file__).read_text(encoding="utf-8")
    for flag in ("--allow-qualified-claims", "--allow-empty-claims", "--allow-unverified-pck"):
        assert flag not in source
    for name in ("allow_qualified_claims", "allow_empty_claims", "allow_unverified_pck"):
        assert name not in source


def test_evidence_index_separates_consumable_from_excluded_claims(engine):
    """Every indexed claim is auditable, and only SUPPORTED ones are consumable."""
    run_id, _ = run_build(engine, REQUEST_1)
    index = engine.store.get_revision(engine.store.revisions_of("evidence_index")[-1])["content"]
    consumed = index["claims"]
    excluded = index.get("excluded_claims", [])

    assert all(item["status"] == ALLOWED for item in consumed), consumed
    assert all(item["status"] != ALLOWED for item in excluded), excluded
    for item in excluded:
        assert item.get("reason"), item

    claims_doc = engine.store.get_revision(engine.store.revisions_of("claims")[-1])["content"]
    handled = {(item["claim_id"], item["version"]) for item in claims_doc.get("claims", [])}
    seen = {(item["claim_id"], item["version"]) for item in consumed + excluded}
    assert seen == handled, (sorted(seen), sorted(handled))
    assert run_id
