"""M6 §22/§48：概念/态度型课程"无实证 Claim"的显式政策（默认阻塞，可选放行）。

B 课（大学生心理健康第一课：理解心理学有什么用）实测：Router 正确识别为
concept/reflection/attitude/transfer，但 claim-extractor 提取 0 条实证 Claim，
导致证据契约为空、PCK 阻塞。放行必须是操作者显式决定，并且限制必须被记录。
"""

from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, run_build

from pebs import config, preconditions


class _EmptyClaimsLLM(FakeLLM):
    def generate_json(self, *, task, system, prompt, **kwargs):
        if task == "claims":
            self._bump(task)
            return {"claims": []}
        return super().generate_json(task=task, system=system, prompt=prompt, **kwargs)


def _rules(allow_empty: bool) -> dict:
    rules = dict(config.RULES)
    evidence = dict(rules.get("evidence") or {})
    evidence["allow_empty_claims"] = allow_empty
    rules["evidence"] = evidence
    return rules


def test_allow_empty_claims_lets_the_run_continue_with_a_recorded_limitation(engine, monkeypatch):
    monkeypatch.setattr(config, "RULES", _rules(True))
    engine.llm = _EmptyClaimsLLM()
    run_id, changeset_id = run_build(engine, REQUEST_1)
    status = engine.run_status(run_id)
    claims_step = next(item for item in status["steps"] if item["step_id"] == "claims")
    assert claims_step["status"] == "SUCCEEDED"
    assert "无实证" in (claims_step["note"] or "") or "实证性 Claim" in (claims_step["note"] or "")

    claims_rev = engine.store.revisions_of("claims")[-1]
    claims_doc = engine.store.get_revision(claims_rev)["content"]
    assert claims_doc["claims"] == []
    assert claims_doc["no_empirical_claims"] is True

    evidence_rev = engine.store.revisions_of("evidence_index")[-1]
    index = engine.store.get_revision(evidence_rev)["content"]
    assert index["claims"] == []
    assert index["declared_no_empirical_claims"] is True

    # PCK 前置条件在"已声明 + 政策放行"时视为满足
    assert preconditions.check_supported_claims(_ctx(index), inputs=["evidence_index"], usage_scope=["讲解"]) == []


def _ctx(index: dict, *, status: str = "UNSUPPORTED", usage: str = "讲解"):
    class _Evidence:
        def claim_status(self, claim_id, version):
            return status

        def latest_version(self, claim_id):
            return 1

        def get_claim(self, claim_id, version=None):
            return {"population": "大学生", "usage": usage}

    class _C:
        evidence = _Evidence()

        def content(self, artifact_id):
            return index if artifact_id == "evidence_index" else None

    return _C()


def test_default_policy_still_blocks_empty_claims(engine, monkeypatch):
    monkeypatch.setattr(config, "RULES", _rules(False))
    engine.llm = _EmptyClaimsLLM()
    run_id, changeset_id = run_build(engine, REQUEST_1)
    status = engine.run_status(run_id)
    claims_step = next(item for item in status["steps"] if item["step_id"] == "claims")
    assert claims_step["status"] == "FAILED"
    assert "不会用空证据继续生产" in (claims_step["error"] or "")


def test_precondition_needs_both_the_flag_and_the_declaration(monkeypatch):
    monkeypatch.setattr(config, "RULES", _rules(True))
    # 有政策但索引未声明 → 仍然阻塞
    problems = preconditions.check_supported_claims(
        _ctx({"claims": [], "declared_no_empirical_claims": False}), inputs=["evidence_index"]
    )
    assert problems and "证据索引为空" in problems[0]


def test_unverified_pck_policy_covers_claims_that_cannot_be_supported(monkeypatch):
    """B 课实测：Claim 被提取但全部不可支持（实践/态度型）。

    默认阻塞；allow_unverified_pck=true 且索引已声明"无可用证据"时，PCK 可继续，
    但证据门、安全门、PII 门本身不降级。
    """
    rules = dict(config.RULES)
    evidence = dict(rules.get("evidence") or {})
    evidence["allow_unverified_pck"] = False
    rules["evidence"] = evidence
    monkeypatch.setattr(config, "RULES", rules)
    index = {"claims": [], "excluded_claims": [{"claim_id": "c1", "version": 1, "status": "UNSUPPORTED"}], "declared_no_consumable_claims": True}
    problems = preconditions.check_supported_claims(_ctx(index), inputs=["evidence_index"], usage_scope=["讲解"])
    assert problems and "证据索引为空" in problems[0]

    evidence["allow_unverified_pck"] = True
    monkeypatch.setattr(config, "RULES", rules)
    assert preconditions.check_supported_claims(_ctx(index), inputs=["evidence_index"], usage_scope=["讲解"]) == []

    # consumed==0（Claim 存在但不在 usage_scope 内）同样受该政策覆盖
    index2 = {
        "claims": [{"claim_id": "c1", "version": 1}],
        "excluded_claims": [{"claim_id": "c2", "version": 1, "status": "UNSUPPORTED"}],
        "declared_no_consumable_claims": True,
    }
    ctx2 = _ctx(index2, status="SUPPORTED", usage="评价")
    assert preconditions.check_supported_claims(ctx2, inputs=["evidence_index"], usage_scope=["讲解"]) == []
