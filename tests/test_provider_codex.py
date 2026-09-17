from __future__ import annotations

from pathlib import Path

from pebs import config, providers
from pebs.providers import CodexExecLLM, ProviderError


class _Result:
    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def test_missing_cli_is_reported(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: None)
    llm = CodexExecLLM({"enabled": True, "kind": "codex_exec"})
    status = llm.availability()
    assert status["available"] is False
    assert any("codex" in reason for reason in status["reasons"])


def test_disabled_provider_reports_disabled(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: "codex")
    llm = CodexExecLLM({"enabled": False})
    status = llm.availability()
    assert status["available"] is False
    assert any("enabled=false" in reason for reason in status["reasons"])


def test_codex_provider_reads_last_message_file(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: "codex")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input", "")
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text('```json\n{"status": "ok", "units": []}\n```', encoding="utf-8")
        return _Result()

    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    llm = CodexExecLLM({"enabled": True, "kind": "codex_exec", "reasoning_effort": "low"})
    assert llm.availability()["available"] is True
    result = llm.generate_json(task="t", system="系统指令", prompt="任务内容")
    assert result == {"status": "ok", "units": [], "_usage": {}}
    assert "--ephemeral" in captured["cmd"]
    assert "--ignore-user-config" in captured["cmd"]
    assert "model_reasoning_effort=low" in captured["cmd"]
    assert "系统指令" in captured["input"] and "任务内容" in captured["input"]


def test_codex_provider_raises_on_failure(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: "codex")

    def fake_run(cmd, **kwargs):
        return _Result(rc=1, stderr="not logged in")

    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    llm = CodexExecLLM({"enabled": True, "kind": "codex_exec"})
    try:
        llm.generate_json(task="t", system="s", prompt="p")
        raised = False
    except ProviderError as exc:
        raised = True
        assert "codex exec 失败" in str(exc)
    assert raised


def test_get_llm_dispatches_on_kind(monkeypatch):
    monkeypatch.setattr(config, "PROVIDERS", {"llm": {"kind": "codex_exec", "enabled": False}})
    assert isinstance(providers.get_llm(), CodexExecLLM)
    monkeypatch.setattr(config, "PROVIDERS", {"llm": {"kind": "openai_compatible", "enabled": False}})
    assert isinstance(providers.get_llm(), providers.OpenAICompatLLM)
