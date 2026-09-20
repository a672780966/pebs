from __future__ import annotations

from conftest import REQUEST_1, FakeLLM, run_dynamic_build
from pebs.benchmark import evaluation as eval_mod


def test_probe_gate_lines(engine, tmp_path, monkeypatch):
    from pebs import config

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    engine.project_id = "proj"
    engine.llm = FakeLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    engine.accept(start["changeset_id"])
    lines = eval_mod._gate_lines(engine.store)
    print("\nGATE LINES:", lines[:6])
    for item in engine.store.list_artifacts():
        if item["artifact_type"] == "gate_result":
            revs = engine.store.revisions_of(item["artifact_id"])
            content = engine.store.get_revision(revs[-1])["content"]
            print(" CONTENT KEYS", item["artifact_id"], sorted(content.keys())[:8])
            break
