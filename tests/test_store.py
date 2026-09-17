from __future__ import annotations

import pytest

from conftest import REQUEST_2
from pebs.store import ConflictError, Store, StoreError


@pytest.fixture
def store(tmp_path):
    s = Store("testproj", tmp_path / "proj")
    yield s
    s.close()


def add(store, artifact_id, content, deps=()):
    return store.add_revision(
        artifact_id=artifact_id, artifact_type="doc", content=content, produced_by="test", deps=deps
    )


def accept(store, items):
    cs = store.create_changeset(None, "test", store.current_baseline())
    for revision_id, artifact_id in items:
        store.add_changeset_item(cs, revision_id, artifact_id)
    return store.accept_changeset(cs)["status"], cs


def test_revision_is_immutable_and_versioned(store):
    first = add(store, "doc", {"v": 1})
    second = add(store, "doc", {"v": 2})
    assert first["version"] == 1
    assert second["version"] == 2
    assert store.get_revision(first["revision_id"])["content"] == {"v": 1}
    assert store.get_revision(first["revision_id"])["content_hash"] == first["content_hash"]


def test_staleness_propagates_along_dependencies(store):
    up = add(store, "up", {"v": 1})
    mid = add(store, "mid", {"v": 1}, deps=[up["revision_id"]])
    leaf = add(store, "leaf", {"v": 1}, deps=[mid["revision_id"]])
    assert accept(store, [(up["revision_id"], "up"), (mid["revision_id"], "mid"), (leaf["revision_id"], "leaf")])[0] == "accepted"
    up2 = add(store, "up", {"v": 2}, deps=[])
    status, _ = accept(store, [(up2["revision_id"], "up")])
    assert status == "accepted"
    assert store.is_stale("mid") is True
    assert store.is_stale("leaf") is True


def test_accept_rejects_stale_baseline(store):
    rev1 = add(store, "doc", {"v": 1})
    accept(store, [(rev1["revision_id"], "doc")])
    late = add(store, "doc", {"v": 2})
    late_cs = store.create_changeset(None, "late", store.current_baseline())
    store.add_changeset_item(late_cs, late["revision_id"], "doc")
    newer = add(store, "doc", {"v": 3})
    accept(store, [(newer["revision_id"], "doc")])
    with pytest.raises(ConflictError):
        store.accept_changeset(late_cs)
    assert store.get_changeset(late_cs)["status"] == "conflict"
    assert store.accepted_rev_id("doc") == newer["revision_id"]


def test_reject_leaves_accepted_untouched(store):
    rev1 = add(store, "doc", {"v": 1})
    accept(store, [(rev1["revision_id"], "doc")])
    rev2 = add(store, "doc", {"v": 2})
    cs = store.create_changeset(None, "candidate", store.current_baseline())
    store.add_changeset_item(cs, rev2["revision_id"], "doc")
    assert store.reject_changeset(cs)["status"] == "rejected"
    assert store.accepted_rev_id("doc") == rev1["revision_id"]
    assert store.accepted_content("doc") == {"v": 1}


def test_locked_artifact_cannot_be_modified(store):
    """A changeset built before the lock must not be able to accept it."""
    rev1 = add(store, "doc", {"v": 1})
    accept(store, [(rev1["revision_id"], "doc")])
    rev2 = add(store, "doc", {"v": 2})
    cs = store.create_changeset(None, "candidate", store.current_baseline())
    store.add_changeset_item(cs, rev2["revision_id"], "doc")
    # The lock arrives after the changeset exists: accept still refuses.
    store.set_locked("doc", True)
    with pytest.raises(ConflictError):
        store.accept_changeset(cs)
    assert store.accepted_rev_id("doc") == rev1["revision_id"]


def test_locked_artifact_rejects_write_before_accept(store):
    """The write window is closed too: no revision and no changeset item."""
    rev1 = add(store, "doc", {"v": 1})
    accept(store, [(rev1["revision_id"], "doc")])
    store.set_locked("doc", True)

    with pytest.raises(ConflictError):
        add(store, "doc", {"v": 2})
    with pytest.raises(ConflictError):
        store.add_changeset_item("cs_absent", rev1["revision_id"], "doc")

    # Nothing was written, and unlocking restores the ordinary path.
    assert store.get_revision(rev1["revision_id"])["content"] == {"v": 1}
    store.set_locked("doc", False)
    rev2 = add(store, "doc", {"v": 2})
    assert rev2["version"] == 2


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_run_teardown_leaves_no_thread_exception(engine):
    """close() joins the run threads before closing the connection.

    A worker that outlives teardown would touch a closed sqlite connection and
    raise inside its own thread, which pytest reports as an unhandled thread
    exception. Cancelling first makes the race real rather than theoretical.
    """
    start = engine.start_build(REQUEST_2, material_paths=[], planner_mode="dynamic")
    engine.cancel(start["run_id"])

    engine.close(join_timeout=30)

    assert all(not thread.is_alive() for thread in engine._run_threads)
    with pytest.raises(StoreError):
        engine.store.list_artifacts()
    # The joined worker left a terminal record on disk, not a half-written run.
    reopened = Store("testproj", engine.base)
    try:
        assert reopened.get_run(start["run_id"])["status"] in {
            "cancelled",
            "blocked",
            "succeeded",
            "failed",
        }
    finally:
        reopened.close()


def test_accept_excludes_changeset_items_from_staleness(store):
    up = add(store, "up", {"v": 1})
    down = add(store, "down", {"v": 1}, deps=[up["revision_id"]])
    accept(store, [(up["revision_id"], "up"), (down["revision_id"], "down")])
    up2 = add(store, "up", {"v": 2})
    down2 = add(store, "down", {"v": 2}, deps=[up2["revision_id"]])
    cs = store.create_changeset(None, "rebuild", store.current_baseline())
    store.add_changeset_item(cs, up2["revision_id"], "up")
    store.add_changeset_item(cs, down2["revision_id"], "down")
    result = store.accept_changeset(cs)
    assert result["stale_artifacts"] == []
    assert store.is_stale("down") is False


def test_budget_enforced(store):
    run_id = store.create_run(budgets={"model_calls": 1, "research_requests": 0, "run_seconds": 60})
    store.bump_calls(run_id, 1)
    from pebs.store import BudgetExceeded

    with pytest.raises(BudgetExceeded):
        store.check_budget(run_id, model_calls=1)
