from __future__ import annotations

import pytest
from conftest import REQUEST_1, FakeResearch, run_build

from pebs import gates, providers
from pebs.engine import Engine
from pebs.hooks import HookFailure, Hooks
from pebs.evidence import EvidenceStore
from pebs.permissions import PermissionDenied, PermissionManager
from pebs.providers import CrossrefResearch, ProviderError


def test_cancel_marks_run_cancelled(engine):
    run_id = engine.store.create_run(request="cancel me")
    engine.store.add_step(run_id, "parse_inputs", "解析")
    engine.store.set_step(run_id, "parse_inputs", status="RUNNING")
    result = engine.cancel(run_id)
    assert result["run"]["status"] == "cancelled"


def test_interrupted_run_is_recovered_on_restart(tmp_path):
    base = tmp_path / "proj"
    engine = Engine("recover", base_dir=base)
    run_id = engine.store.create_run(request="interrupted")
    engine.store.add_step(run_id, "scripts", "生成课程脚本")
    engine.store.set_step(run_id, "scripts", status="RUNNING")
    engine.close()

    engine2 = Engine("recover", base_dir=base)
    status = engine2.run_status(run_id)
    assert status["run"]["status"] == "interrupted"
    step = status["steps"][0]
    assert step["status"] == "BLOCKED"
    assert "待恢复" in (step["error"] or "")
    engine2.close()


def test_rerun_from_gates_rebuilds_downstream_and_keeps_scripts(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    script_rev = engine.store.accepted_rev_id("script:sec1")
    gate_rev = engine.store.accepted_rev_id("gate:G2:script:sec1")
    result = engine.rerun_from("gates")
    assert result["steps"][0] == "gates"
    status = engine.run_status(result["run_id"])
    assert status["run"]["status"] == "succeeded"
    engine.accept(result["changeset_id"])
    assert engine.store.accepted_rev_id("script:sec1") == script_rev
    assert engine.store.accepted_rev_id("gate:G2:script:sec1") != gate_rev
    assert gates.export_readiness(engine.store)["ready"] is True


def test_rerun_from_parse_inputs_reuses_saved_inputs(engine, tmp_path):
    template = tmp_path / "t.md"
    template.write_text("# 模板\n\n| 教师讲解 | 画面提示 |\n|---|---|\n|  |  |\n", encoding="utf-8")
    run_id, changeset_id = run_build(engine, REQUEST_1, template_path=template)
    engine.accept(changeset_id)
    result = engine.rerun_from("parse_inputs")
    spec = engine.store.get_revision(
        [r for r in engine.store.revisions_of("template_spec")][-1]
    )["content"]
    assert spec["kind"] == "markdown"
    assert result["steps"][0] == "parse_inputs"


def test_fixture_run_cannot_formally_export(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1, environment="test_fixture")
    engine.accept(changeset_id)
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    assert any("测试夹具" in item for item in readiness["blocking"])
    result = engine.export_now("formal")
    assert result["ok"] is False
    draft = engine.export_now("draft")
    assert draft["ok"] is True
    assert all(f["label"] == "草稿—未通过 QA" for f in draft["manifest"]["files"])


class StubResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_crossref_retries_transient_failures_then_succeeds(monkeypatch):
    monkeypatch.setattr(providers, "RETRY_BASE_DELAY", 0.0)
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return StubResponse(500)
        return StubResponse(
            200, {"message": {"items": [{"title": "T", "DOI": "10.1/x", "issued": {"date-parts": [[2020]]}}]}}
        )

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    research = CrossrefResearch({"enabled": True, "allowed_sources": ["crossref"], "require_api_key": False})
    results = research.search("test")
    assert calls["n"] == 3
    assert len(results) == 1


def test_crossref_raises_after_bounded_retries(monkeypatch):
    monkeypatch.setattr(providers, "RETRY_BASE_DELAY", 0.0)
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return StubResponse(500)

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    research = CrossrefResearch({"enabled": True, "allowed_sources": ["crossref"], "require_api_key": False})
    with pytest.raises(ProviderError) as excinfo:
        research.search("test")
    assert "已重试" in str(excinfo.value)
    assert calls["n"] == 3


def test_injected_authorization_cannot_trigger_external_writes(tmp_path):
    from pebs.store import Store

    store = Store("hooks", tmp_path / "proj")
    hooks = Hooks(store, EvidenceStore(store), PermissionManager())
    with pytest.raises(HookFailure):
        hooks.before_external_action("cnki_download")
    with pytest.raises(PermissionDenied):
        hooks.permissions.external_action("cnki_download")
    store.close()


def test_crossref_retries_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(providers, "RETRY_BASE_DELAY", 0.0)
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return StubResponse(429, headers={"Retry-After": "0"})
        return StubResponse(200, {"message": {"items": [{"title": "T", "DOI": "10.1/x"}]}})

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    research = CrossrefResearch({"enabled": True, "allowed_sources": ["crossref"], "require_api_key": False})
    assert len(research.search("q")) == 1
    assert calls["n"] == 2


def test_crossref_rate_limit_exhausts_retries(monkeypatch):
    monkeypatch.setattr(providers, "RETRY_BASE_DELAY", 0.0)
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return StubResponse(429, headers={"Retry-After": "0"})

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    research = CrossrefResearch({"enabled": True, "allowed_sources": ["crossref"], "require_api_key": False})
    with pytest.raises(ProviderError) as excinfo:
        research.search("q")
    assert "已重试" in str(excinfo.value)
    assert calls["n"] == 3


def test_crossref_contact_email_used_in_user_agent(monkeypatch):
    monkeypatch.setattr(providers, "RETRY_BASE_DELAY", 0.0)
    captured = {}

    def fake_get(*args, **kwargs):
        captured.update(kwargs.get("headers", {}))
        return StubResponse(200, {"message": {"items": []}})

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    research = CrossrefResearch(
        {"enabled": True, "allowed_sources": ["crossref"], "require_api_key": False, "contact_email": "t@example.org"}
    )
    research.search("q")
    assert "t@example.org" in captured.get("User-Agent", "")


def test_missing_renderer_metadata_still_reports_docx_qa(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    result = engine.export_now("formal")
    manifest = result["manifest"]
    assert manifest["renderer"]["docx"].startswith("python-docx")
    g8 = engine.store.accepted_content("gate:G8:export_manifest")
    assert g8["renderer"].startswith("python-docx")
