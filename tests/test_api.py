from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pebs import config
from pebs import server as server_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(
        config,
        "PROVIDERS",
        {
            "llm": {"kind": "openai_compatible", "enabled": False, "api_key_env": "PEBS_LLM_API_KEY"},
            "research": {"enabled": False},
        },
    )
    server_mod._engines.clear()
    return TestClient(server_mod.app)


def test_status_reports_provider_availability(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    body = res.json()
    assert "providers" in body
    assert "llm" in body["providers"]
    assert body["rules_version"].startswith("rules-")


def test_project_lifecycle_and_blocked_run(client):
    res = client.post("/api/projects", json={"project_id": "apitest"})
    assert res.status_code == 200

    res = client.post(
        "/api/projects/apitest/build",
        json={"request": "任务1 观察记录。每节 10–9999 字。"},
    )
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/projects/apitest/runs/{run_id}").json()
        if status["run"]["status"] != "running":
            break
        time.sleep(0.3)
    assert status is not None
    assert status["run"]["status"] in ("blocked", "failed", "succeeded")
    steps = {s["step_id"]: s["status"] for s in status["steps"]}
    assert steps["parse_inputs"] == "SUCCEEDED"
    if not client.get("/api/status").json()["providers"]["llm"]["available"]:
        assert steps["learning_design"] == "BLOCKED"

    outputs = client.get("/api/projects/apitest/outputs").json()
    assert "manifest" in outputs
    assert "formal_files" in outputs


def test_invalid_project_id_rejected(client):
    res = client.post("/api/projects", json={"project_id": "..\\escape"})
    assert res.status_code == 400


def test_build_with_pii_is_rejected_before_send(client):
    client.post("/api/projects", json={"project_id": "piitest"})
    res = client.post(
        "/api/projects/piitest/build",
        json={"request": "给张三同学写评语，电话 13800138000。"},
    )
    assert res.status_code == 409
    assert "发送前暂停" in res.json()["detail"]


def test_build_with_unknown_explicit_skill_rejected(client):
    client.post("/api/projects", json={"project_id": "skilltest"})
    res = client.post(
        "/api/projects/skilltest/build",
        json={"request": "/not-a-real-skill 写一节课程"},
    )
    assert res.status_code == 409


def test_dynamic_plan_and_conversation_endpoints(client):
    client.post("/api/projects", json={"project_id": "plantest"})
    res = client.get("/api/projects/plantest/dynamic-plan")
    assert res.status_code == 200
    assert res.json()["mode"] == "static"

    res = client.post(
        "/api/projects/plantest/conversation",
        json={"message": "\u8ba9\u6574\u4f53\u6c1b\u56f4\u66f4\u6d3b\u6cfc\u4e00\u70b9"},
    )
    assert res.status_code == 409
    assert "reason" in res.json()

    assert client.get("/api/projects/plantest/patch-plan").status_code == 404


def test_human_steps_translate_internal_nodes():
    """§40: the default Plan view is human language; node_id/skill live under advanced."""
    from pebs import server as server_mod

    plan = {
        "mode": "dynamic",
        "nodes": [
            {"node_id": "requirements-builder", "skill": "requirements-builder", "title": "整理课程要求", "depends_on": []},
            {"node_id": "evidence-reviewer", "skill": "evidence-reviewer", "depends_on": ["requirements-builder"]},
            {"node_id": "docx-exporter", "skill": "docx-exporter", "depends_on": [], "reused": True},
        ],
    }
    steps = server_mod.human_steps(plan)
    assert [step["title"] for step in steps] == ["整理课程要求", "核验心理学事实", "导出正式文档"]
    assert steps[2]["status"] == "reuse"
    assert steps[1]["advanced"]["node_id"] == "evidence-reviewer"
    assert steps[1]["advanced"]["agent"] == "research-agent"
    assert "node_id" not in steps[1]
