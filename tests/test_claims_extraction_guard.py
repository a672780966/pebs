"""M6 生产修正：Claim 提取为空必须 fail fast，而不是在 PCK 处才以"证据索引为空"阻塞。

真实运行（Golden Benchmark B）中，模型返回 0 条 Claim，系统继续执行到 PCK 才失败，
错误信息指向"证据索引为空"，无法定位到上游提取环节。
"""

from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, run_build

from pebs import pipeline


class _EmptyClaimsLLM(FakeLLM):
    def generate_json(self, *, task, system, prompt, **kwargs):
        if task == "claims":
            self._bump(task)
            return {"claims": []}
        return super().generate_json(task=task, system=system, prompt=prompt, **kwargs)


def test_empty_claim_extraction_fails_fast(engine):
    engine.llm = _EmptyClaimsLLM()
    run_id, changeset_id = run_build(engine, REQUEST_1)
    status = engine.run_status(run_id)
    step = next(item for item in status["steps"] if item["step_id"] == "claims")
    assert step["status"] == "FAILED"
    assert "Claim 提取结果为空" in (step["error"] or "")
    assert "不会用空证据继续生产" in (step["error"] or "")
    assert engine.store.revisions_of("claims") == []


def test_claims_step_still_emits_when_claims_present(engine):
    engine.llm = FakeLLM()
    run_id, changeset_id = run_build(engine, REQUEST_1)
    status = engine.run_status(run_id)
    step = next(item for item in status["steps"] if item["step_id"] == "claims")
    assert step["status"] == "SUCCEEDED"
    assert engine.store.revisions_of("claims")
