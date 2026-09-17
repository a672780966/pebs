from __future__ import annotations

import json
from pathlib import Path

import pytest

from pebs import config, sandbox


class _Result:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def test_docker_missing_reports_unavailable(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)
    report = sandbox.DockerSandbox().probe()
    assert report.available is False
    assert any("docker" in detail for detail in report.details)


def test_docker_probe_verifies_controls(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "docker")

    def fake_run(cmd, **kwargs):
        if "info" in cmd:
            return _Result(0, "27.0.0")
        script = cmd[-1]
        if "FS_OK" in script:
            return _Result(0, "FS_OK")
        if "NET_OK" in script:
            return _Result(0, "NET_OK")
        return _Result(137, "", "killed")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    report = sandbox.DockerSandbox().probe()
    assert report.available is True
    assert report.controls["filesystem"] is True
    assert report.controls["network_off"] is True
    assert report.controls["memory_limit"] is True


def test_docker_probe_detects_leaks(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "docker")

    def fake_run(cmd, **kwargs):
        if "info" in cmd:
            return _Result(0, "27.0.0")
        script = cmd[-1]
        if "FS_OK" in script:
            return _Result(0, "FS_LEAK")
        if "NET_OK" in script:
            return _Result(0, "NET_LEAK")
        return _Result(0, "MEM_LEAK")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    report = sandbox.DockerSandbox().probe()
    assert report.available is False
    assert report.controls["filesystem"] is False
    assert report.controls["network_off"] is False
    assert report.controls["memory_limit"] is False


def test_docker_daemon_down_reports_unavailable(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(
        sandbox.subprocess,
        "run",
        lambda cmd, **kwargs: _Result(1, "", "daemon not running"),
    )
    report = sandbox.DockerSandbox().probe()
    assert report.available is False
    assert any("daemon" in detail for detail in report.details)


def test_subprocess_probe_reports_unenforced_controls(monkeypatch):
    monkeypatch.setattr(sandbox.subprocess, "run", lambda cmd, **kwargs: _Result(0))
    monkeypatch.setattr(sandbox.SubprocessSandbox, "_probe_memory_limit", lambda self: True)
    report = sandbox.SubprocessSandbox().probe()
    assert report.controls["filesystem"] is False
    assert report.controls["network_off"] is False
    assert report.available is False


def test_run_sandboxed_refuses_without_verified_adapter(registry_env, monkeypatch):
    (config.REGISTRY_DIR / "sandbox_report.json").write_text(
        json.dumps(
            [
                {
                    "adapter": "subprocess_job",
                    "available": False,
                    "controls": {},
                    "details": ["filesystem 未隔离"],
                    "probed_at": "2026-01-01T00:00:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.run_sandboxed(["echo", "hi"], workdir=Path(config.SKILLS_DIR) / "tmp")


def test_run_sandboxed_uses_docker_command(registry_env, monkeypatch):
    (config.REGISTRY_DIR / "sandbox_report.json").write_text(
        json.dumps(
            [
                {
                    "adapter": "docker",
                    "available": True,
                    "controls": {"filesystem": True, "network_off": True, "memory_limit": True},
                    "details": [],
                    "probed_at": "2026-01-01T00:00:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result(0, "ok", "")

    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    result = sandbox.run_sandboxed(["sh", "-c", "echo hi"], workdir=Path(config.SKILLS_DIR) / "work")
    assert result["returncode"] == 0
    cmd = captured["cmd"]
    assert "--network" in cmd and "none" in cmd
    assert "--memory" in cmd
    assert any(":/work" in part for part in cmd)


def test_load_report_reads_cache_without_probing(registry_env, monkeypatch):
    (config.REGISTRY_DIR / "sandbox_report.json").write_text(
        json.dumps(
            [
                {
                    "adapter": "docker",
                    "available": True,
                    "controls": {"filesystem": True},
                    "details": [],
                    "probed_at": "2026-01-01T00:00:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def boom():
        raise AssertionError("probe should not run when cache exists")

    monkeypatch.setattr(sandbox, "probe_all", boom)
    report = sandbox.load_report()
    assert report.available is True
    assert report.adapter == "docker"
