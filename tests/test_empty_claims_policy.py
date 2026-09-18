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


def _ctx(index: dict):
    class _C:
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
