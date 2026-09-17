from __future__ import annotations

from conftest import REQUEST_1, run_build

from pebs import memory as memory_mod


def test_memory_written_on_accept(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    assert memory_mod.read_memory(engine.store) is None
    engine.accept(changeset_id)
    memory = memory_mod.read_memory(engine.store)
    assert memory is not None
    assert memory["course"]
    assert memory["word_rules"]["min"] == 10
    assert memory["approved_cases"] and memory["approved_cases"][0]["title"] == "午睡观察记录"
    assert memory["template"]["kind"] == "none"
    assert memory["updated_at"]


def test_memory_not_written_when_rejected(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.reject(changeset_id)
    assert memory_mod.read_memory(engine.store) is None
