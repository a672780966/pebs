"""M6 生产修正：Claim.usage 是多值字段，usage_scope 必须按 token 交集匹配。

回归：真实证据索引里的 Claim usage 形如"讲解/案例/评价"，此前整串比较永远不匹配，
PCK 前置条件因此永远阻塞（即使 Claim 已是 SUPPORTED）。
"""

from __future__ import annotations

from pebs import preconditions


def test_usage_tokens_split_multi_value_strings():
    assert preconditions.usage_tokens("讲解/案例/评价") == {"讲解", "案例", "评价"}
    assert preconditions.usage_tokens("讲解、案例") == {"讲解", "案例"}
    assert preconditions.usage_tokens(" 讲解 ") == {"讲解"}
    assert preconditions.usage_tokens("") == set()


class _FakeEvidence:
    def claim_status(self, claim_id, version):
        return "SUPPORTED"

    def latest_version(self, claim_id):
        return 1

    def get_claim(self, claim_id, version=None):
        return {"population": "大学生", "usage": "讲解/案例/评价"}


class _FakeCtx:
    def __init__(self):
        self.evidence = _FakeEvidence()

    def content(self, artifact_id):
        if artifact_id == "evidence_index":
            return {"claims": [{"claim_id": "clm_demo", "version": 1}]}
        return None


def test_multi_value_usage_matches_scope():
    problems = preconditions.check_supported_claims(_FakeCtx(), inputs=["evidence_index"], usage_scope=["讲解"])
    assert problems == []


def test_out_of_scope_usage_still_skipped():
    ctx = _FakeCtx()
    ctx.evidence.get_claim = lambda claim_id, version=None: {"population": "大学生", "usage": "评价"}
    problems = preconditions.check_supported_claims(ctx, inputs=["evidence_index"], usage_scope=["讲解"])
    assert problems and "PCK" in problems[0]
