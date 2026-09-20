from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "blocked"}


class _Result:
    """sqlite3 游标的安全替身：行已在锁内取完，允许跨线程/延后迭代。"""

    def __init__(self, rows: list[Any], rowcount: int = -1) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, index: int) -> Any:
        return self._rows[index]

    def __bool__(self) -> bool:
        return bool(self._rows)


class SharedConnection:
    """线程安全的 sqlite3 连接代理。

    并行 DAG 中多个 Subagent / Skill 节点共享同一连接：所有语句与提交都在
    同一把可重入锁下串行化，且行在锁内物化，避免共享游标被其他线程重置。
    """

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock
        self._closed = False
        self.isolation_level = conn.isolation_level
        self.row_factory = conn.row_factory

    def _guard(self) -> None:
        """Refuse cleanly once closed instead of raising from inside sqlite.

        A worker thread that outlives the run reaches this after teardown; a
        named error is diagnosable, whereas sqlite's `ProgrammingError` from a
        closed connection surfaces as an unhandled thread exception.
        """
        if self._closed:
            raise StoreError("store is closed")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> _Result:
        with self._lock:
            self._guard()
            cursor = self._conn.execute(sql, tuple(params))
            return _Result(cursor.fetchall(), cursor.rowcount)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> _Result:
        with self._lock:
            self._guard()
            cursor = self._conn.executemany(sql, [tuple(row) for row in rows])
            return _Result(cursor.fetchall(), cursor.rowcount)

    def executescript(self, script: str) -> _Result:
        with self._lock:
            self._guard()
            cursor = self._conn.executescript(script)
            return _Result(cursor.fetchall(), cursor.rowcount)

    def commit(self) -> None:
        with self._lock:
            self._guard()
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._guard()
            self._conn.rollback()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'production',
  baseline TEXT NOT NULL DEFAULT '{}',
  budget_model_calls INTEGER NOT NULL DEFAULT 40,
  budget_research INTEGER NOT NULL DEFAULT 20,
  budget_seconds INTEGER NOT NULL DEFAULT 1800,
  calls_used INTEGER NOT NULL DEFAULT 0,
  research_used INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  ended_at TEXT,
  request TEXT NOT NULL DEFAULT '',
  inputs TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS steps (
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  ended_at TEXT,
  error TEXT,
  note TEXT,
  input_revs TEXT NOT NULL DEFAULT '[]',
  output_revs TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY (run_id, step_id)
);
CREATE TABLE IF NOT EXISTS revisions (
  revision_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  produced_by TEXT NOT NULL DEFAULT '',
  produced_by_run TEXT,
  rules_version TEXT,
  fixture INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deps (
  downstream_rev TEXT NOT NULL,
  upstream_rev TEXT NOT NULL,
  mapping TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (downstream_rev, upstream_rev, mapping)
);
CREATE TABLE IF NOT EXISTS pointers (
  artifact_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  accepted_rev TEXT,
  stale INTEGER NOT NULL DEFAULT 0,
  locked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS changesets (
  changeset_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  run_id TEXT,
  reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'candidate',
  baseline TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  decided_at TEXT
);
CREATE TABLE IF NOT EXISTS changeset_items (
  changeset_id TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  PRIMARY KEY (changeset_id, revision_id)
);
CREATE TABLE IF NOT EXISTS search_logs (
  log_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  run_id TEXT,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def current_signoffs(store: "Store") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for artifact in store.list_artifacts():
        if artifact["artifact_type"] != "review_record" or not artifact["accepted_rev"]:
            continue
        content = store.accepted_content(artifact["artifact_id"]) or {}
        versions = content.get("artifact_versions") or {}
        if not versions:
            continue
        if all(store.accepted_rev_id(artifact_id) == revision_id for artifact_id, revision_id in versions.items()):
            results.append(
                {
                    "changeset_id": content.get("changeset_id"),
                    "reviewer": content.get("reviewer"),
                    "basis": content.get("basis"),
                    "changes": content.get("changes"),
                    "created_at": content.get("created_at"),
                }
            )
    return results


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class StoreError(Exception):
    pass


class ConflictError(StoreError):
    pass


class BudgetExceeded(StoreError):
    pass


class Store:
    def __init__(self, project_id: str, base_dir: Path):
        self.project_id = project_id
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        raw = sqlite3.connect(
            str(self.base_dir / "state.db"), check_same_thread=False, isolation_level=None
        )
        raw.row_factory = sqlite3.Row
        self.conn = SharedConnection(raw, self._lock)
        with self._lock:
            self.conn.executescript(SCHEMA)
            self._migrate()
            self.conn.commit()

    def _migrate(self) -> None:
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(runs)")}
        if "inputs" not in columns:
            self.conn.execute("ALTER TABLE runs ADD COLUMN inputs TEXT NOT NULL DEFAULT '{}'")
        # §39/§35：Skill Trace 需要 per-skill model_calls（成本核算与 schema 修复率都依赖它）
        step_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(steps)")}
        if "model_calls" not in step_columns:
            self.conn.execute("ALTER TABLE steps ADD COLUMN model_calls INTEGER NOT NULL DEFAULT 0")

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cur

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, tuple(params)))

    # ---------------------------------------------------------------- artifacts

    def ensure_artifact(self, artifact_id: str, artifact_type: str) -> None:
        self._exec(
            "INSERT OR IGNORE INTO pointers (artifact_id, project_id, artifact_type, accepted_rev, stale, locked) "
            "VALUES (?, ?, ?, NULL, 0, 0)",
            (artifact_id, self.project_id, artifact_type),
        )

    def add_revision(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        content: Any,
        produced_by: str,
        run_id: str | None = None,
        rules_version: str | None = None,
        deps: Iterable[str] = (),
        fixture: bool = False,
        note: str = "",
    ) -> dict[str, Any]:
        payload = canonical_json(content)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self._lock:
            self.ensure_artifact(artifact_id, artifact_type)
            # A locked artifact is frozen for the whole edit window, not only at
            # accept time: without this an edit run could write a revision that
            # accept_changeset would then refuse, leaving a stranded revision.
            if self.is_locked(artifact_id):
                raise ConflictError(f"artifact locked: {artifact_id}")
            row = self._query(
                "SELECT COALESCE(MAX(version), 0) AS v FROM revisions WHERE artifact_id = ? AND project_id = ?",
                (artifact_id, self.project_id),
            )[0]
            version = int(row["v"]) + 1
            revision_id = f"{artifact_id}@r{version}"
            self._exec(
                "INSERT INTO revisions (revision_id, project_id, artifact_id, artifact_type, version, content, "
                "content_hash, produced_by, produced_by_run, rules_version, fixture, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    revision_id,
                    self.project_id,
                    artifact_id,
                    artifact_type,
                    version,
                    payload,
                    digest,
                    produced_by,
                    run_id,
                    rules_version,
                    1 if fixture else 0,
                    note,
                    now_iso(),
                ),
            )
            for dep in deps:
                self._exec(
                    "INSERT OR IGNORE INTO deps (downstream_rev, upstream_rev, mapping) VALUES (?, ?, '')",
                    (revision_id, dep),
                )
            return {"revision_id": revision_id, "version": version, "content_hash": digest}

    def get_revision(self, revision_id: str) -> dict[str, Any]:
        rows = self._query("SELECT * FROM revisions WHERE revision_id = ?", (revision_id,))
        if not rows:
            raise StoreError(f"revision not found: {revision_id}")
        row = dict(rows[0])
        row["content"] = json.loads(row["content"])
        return row

    def accepted_rev_id(self, artifact_id: str) -> str | None:
        rows = self._query("SELECT accepted_rev FROM pointers WHERE artifact_id = ?", (artifact_id,))
        return rows[0]["accepted_rev"] if rows else None

    def accepted_revision(self, artifact_id: str) -> dict[str, Any] | None:
        rev = self.accepted_rev_id(artifact_id)
        return self.get_revision(rev) if rev else None

    def accepted_content(self, artifact_id: str) -> Any | None:
        rev = self.accepted_revision(artifact_id)
        return rev["content"] if rev else None

    def is_locked(self, artifact_id: str) -> bool:
        rows = self._query("SELECT locked FROM pointers WHERE artifact_id = ?", (artifact_id,))
        return bool(rows[0]["locked"]) if rows else False

    def is_stale(self, artifact_id: str) -> bool:
        rows = self._query("SELECT stale FROM pointers WHERE artifact_id = ?", (artifact_id,))
        return bool(rows[0]["stale"]) if rows else False

    def set_locked(self, artifact_id: str, locked: bool) -> None:
        self._exec("UPDATE pointers SET locked = ? WHERE artifact_id = ?", (1 if locked else 0, artifact_id))

    def set_stale(self, artifact_id: str, stale: bool) -> None:
        self._exec("UPDATE pointers SET stale = ? WHERE artifact_id = ?", (1 if stale else 0, artifact_id))

    def list_artifacts(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT p.artifact_id, p.artifact_type, p.accepted_rev, p.stale, p.locked, "
            "(SELECT COUNT(*) FROM revisions r WHERE r.artifact_id = p.artifact_id) AS revision_count "
            "FROM pointers p WHERE p.project_id = ? ORDER BY p.artifact_type, p.artifact_id",
            (self.project_id,),
        )
        return [dict(r) for r in rows]

    def dependents_of_rev(self, revision_id: str) -> list[str]:
        rows = self._query("SELECT downstream_rev FROM deps WHERE upstream_rev = ?", (revision_id,))
        return [r["downstream_rev"] for r in rows]

    def upstream_revs(self, revision_id: str) -> list[str]:
        rows = self._query("SELECT upstream_rev FROM deps WHERE downstream_rev = ?", (revision_id,))
        return [r["upstream_rev"] for r in rows]

    def set_accepted(self, artifact_id: str, revision_id: str) -> None:
        rev = self.get_revision(revision_id)
        self.ensure_artifact(artifact_id, rev["artifact_type"])
        self._exec(
            "UPDATE pointers SET accepted_rev = ?, stale = 0 WHERE artifact_id = ?", (revision_id, artifact_id)
        )

    def transitive_dependent_revisions(self, revision_ids: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        queue = list(revision_ids)
        while queue:
            rev = queue.pop()
            for dep in self.dependents_of_rev(rev):
                if dep not in seen:
                    seen.add(dep)
                    queue.append(dep)
        return sorted(seen)

    def mark_dependents_stale(self, changed_artifacts: Iterable[str], exclude: Iterable[str] = ()) -> list[str]:
        changed = set(changed_artifacts)
        excluded = set(exclude)
        affected: set[str] = set()
        for artifact_id in changed:
            for rev_id in self.revisions_of(artifact_id):
                for dep_rev in self.transitive_dependent_revisions([rev_id]):
                    row = self._query("SELECT artifact_id FROM revisions WHERE revision_id = ?", (dep_rev,))
                    if row and row[0]["artifact_id"] not in changed:
                        affected.add(row[0]["artifact_id"])
        targets = sorted(a for a in affected if a not in excluded)
        for artifact_id in targets:
            self.set_stale(artifact_id, True)
        return targets

    def revisions_of(self, artifact_id: str) -> list[str]:
        rows = self._query(
            "SELECT revision_id FROM revisions WHERE artifact_id = ? ORDER BY version", (artifact_id,)
        )
        return [r["revision_id"] for r in rows]

    def materialize(self, revision_id: str) -> Path:
        rev = self.get_revision(revision_id)
        target_dir = self.base_dir / "artifacts" / rev["artifact_type"]
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]", "_", rev["artifact_id"])
        target = target_dir / f"{safe_id}.r{rev['version']}.json"
        target.write_text(canonical_json(rev["content"]), encoding="utf-8")
        return target

    # ---------------------------------------------------------------- changesets

    def create_changeset(self, run_id: str | None, reason: str, baseline: dict[str, str | None]) -> str:
        changeset_id = "cs_" + uuid.uuid4().hex[:12]
        self._exec(
            "INSERT INTO changesets (changeset_id, project_id, run_id, reason, status, baseline, created_at) "
            "VALUES (?, ?, ?, ?, 'candidate', ?, ?)",
            (changeset_id, self.project_id, run_id, reason, canonical_json(baseline), now_iso()),
        )
        return changeset_id

    def add_changeset_item(self, changeset_id: str, revision_id: str, artifact_id: str) -> None:
        # Same window as add_revision: a changeset must not be able to reference a
        # locked artifact at all, so the refusal happens when the item is added.
        if self.is_locked(artifact_id):
            raise ConflictError(f"artifact locked: {artifact_id}")
        self._exec(
            "INSERT OR IGNORE INTO changeset_items (changeset_id, revision_id, artifact_id) VALUES (?, ?, ?)",
            (changeset_id, revision_id, artifact_id),
        )

    def get_changeset(self, changeset_id: str) -> dict[str, Any]:
        rows = self._query("SELECT * FROM changesets WHERE changeset_id = ?", (changeset_id,))
        if not rows:
            raise StoreError(f"changeset not found: {changeset_id}")
        cs = dict(rows[0])
        cs["baseline"] = json.loads(cs["baseline"])
        items = self._query(
            "SELECT revision_id, artifact_id FROM changeset_items WHERE changeset_id = ?", (changeset_id,)
        )
        cs["items"] = [dict(i) for i in items]
        for item in cs["items"]:
            item["revision"] = self.get_revision(item["revision_id"])
        return cs

    def list_changesets(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT changeset_id, status, reason, created_at, decided_at FROM changesets "
            "WHERE project_id = ? ORDER BY created_at DESC, rowid DESC",
            (self.project_id,),
        )
        result = []
        for row in rows:
            cs = dict(row)
            count = self._query(
                "SELECT COUNT(*) AS n FROM changeset_items WHERE changeset_id = ?", (cs["changeset_id"],)
            )[0]["n"]
            cs["item_count"] = int(count)
            result.append(cs)
        return result

    def _set_changeset_status(self, changeset_id: str, status: str) -> None:
        self._exec(
            "UPDATE changesets SET status = ?, decided_at = ? WHERE changeset_id = ?",
            (status, now_iso(), changeset_id),
        )

    def accept_changeset(self, changeset_id: str) -> dict[str, Any]:
        cs = self.get_changeset(changeset_id)
        if cs["status"] != "candidate":
            raise ConflictError(f"changeset {changeset_id} is {cs['status']}, not candidate")
        items = cs["items"]
        if not items:
            raise ConflictError(f"changeset {changeset_id} is empty")
        target_artifacts = {item["artifact_id"] for item in items}
        with self._lock:
            for item in items:
                artifact_id = item["artifact_id"]
                if self.is_locked(artifact_id):
                    raise ConflictError(f"artifact locked: {artifact_id}")
                current = self.accepted_rev_id(artifact_id)
                expected = cs["baseline"].get(artifact_id)
                if current != expected:
                    self._set_changeset_status(changeset_id, "conflict")
                    raise ConflictError(
                        f"baseline conflict on {artifact_id}: accepted is {current}, expected {expected}"
                    )
            stale_marked: set[str] = set()
            for item in items:
                artifact_id = item["artifact_id"]
                old = self.accepted_rev_id(artifact_id)
                self._exec(
                    "UPDATE pointers SET accepted_rev = ?, stale = 0 WHERE artifact_id = ?",
                    (item["revision_id"], artifact_id),
                )
                self.materialize(item["revision_id"])
                if old and old != item["revision_id"]:
                    for dep_artifact in self.mark_dependents_stale([artifact_id], exclude=target_artifacts):
                        stale_marked.add(dep_artifact)
            self._set_changeset_status(changeset_id, "accepted")
        return {"changeset_id": changeset_id, "status": "accepted", "stale_artifacts": sorted(stale_marked)}

    def reject_changeset(self, changeset_id: str) -> dict[str, Any]:
        cs = self.get_changeset(changeset_id)
        if cs["status"] != "candidate":
            raise ConflictError(f"changeset {changeset_id} is {cs['status']}, not candidate")
        self._set_changeset_status(changeset_id, "rejected")
        return {"changeset_id": changeset_id, "status": "rejected"}

    def current_baseline(self) -> dict[str, str | None]:
        rows = self._query("SELECT artifact_id, accepted_rev FROM pointers WHERE project_id = ?", (self.project_id,))
        return {r["artifact_id"]: r["accepted_rev"] for r in rows}

    # ---------------------------------------------------------------- runs

    def create_run(
        self,
        *,
        environment: str = "production",
        request: str = "",
        budgets: dict[str, int] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> str:
        budgets = budgets or {}
        run_id = "run_" + uuid.uuid4().hex[:12]
        rules = {**{"model_calls": 40, "research_requests": 20, "run_seconds": 1800}}
        self._exec(
            "INSERT INTO runs (run_id, project_id, created_at, status, environment, baseline, "
            "budget_model_calls, budget_research, budget_seconds, request, inputs) "
            "VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                self.project_id,
                now_iso(),
                environment,
                canonical_json(self.current_baseline()),
                int(budgets.get("model_calls", rules["model_calls"])),
                int(budgets.get("research_requests", rules["research_requests"])),
                int(budgets.get("run_seconds", rules["run_seconds"])),
                request,
                canonical_json(inputs or {}),
            ),
        )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any]:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if not rows:
            raise StoreError(f"run not found: {run_id}")
        run = dict(rows[0])
        run["inputs"] = json.loads(run.get("inputs") or "{}")
        return run

    def latest_run(self) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT run_id FROM runs WHERE project_id = ? ORDER BY rowid DESC LIMIT 1", (self.project_id,)
        )
        return self.get_run(rows[0]["run_id"]) if rows else None

    def interrupted_runs(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT run_id FROM runs WHERE project_id = ? AND status = 'running'", (self.project_id,)
        )
        return [self.get_run(r["run_id"]) for r in rows]

    def set_run_status(self, run_id: str, status: str) -> None:
        self._exec("UPDATE runs SET status = ?, ended_at = ? WHERE run_id = ?", (status, now_iso(), run_id))

    def add_step(self, run_id: str, step_id: str, title: str, status: str = "PENDING") -> None:
        self._exec(
            "INSERT OR REPLACE INTO steps (run_id, step_id, title, status) VALUES (?, ?, ?, ?)",
            (run_id, step_id, title, status),
        )

    def set_step(
        self,
        run_id: str,
        step_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
        note: str | None = None,
        input_revs: list[str] | None = None,
        output_revs: list[str] | None = None,
        model_calls: int | None = None,
        bump_attempt: bool = False,
    ) -> None:
        rows = self._query("SELECT * FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id))
        if not rows:
            self.add_step(run_id, step_id, step_id)
            rows = self._query("SELECT * FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id))
        row = rows[0]
        self._exec(
            "UPDATE steps SET status = ?, error = ?, note = ?, input_revs = ?, output_revs = ?, "
            "model_calls = ?, "
            "started_at = COALESCE(started_at, CASE WHEN ? = 'RUNNING' THEN ? ELSE started_at END), "
            "ended_at = CASE WHEN ? IN ('SUCCEEDED','FAILED','BLOCKED','CANCELLED','STALE') THEN ? ELSE ended_at END, "
            "attempts = attempts + ? WHERE run_id = ? AND step_id = ?",
            (
                status if status is not None else row["status"],
                error if error is not None else row["error"],
                note if note is not None else row["note"],
                canonical_json(input_revs) if input_revs is not None else row["input_revs"],
                canonical_json(output_revs) if output_revs is not None else row["output_revs"],
                int(model_calls) if model_calls is not None else row["model_calls"],
                status,
                now_iso(),
                status,
                now_iso(),
                1 if bump_attempt else 0,
                run_id,
                step_id,
            ),
        )

    def get_steps(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM steps WHERE run_id = ? ORDER BY rowid", (run_id,))
        return [dict(r) for r in rows]

    def bump_calls(self, run_id: str, n: int = 1, *, step_id: str = "") -> None:
        self._exec("UPDATE runs SET calls_used = calls_used + ? WHERE run_id = ?", (n, run_id))
        # §39：同时记到发起调用的节点上（并行调度下这是唯一准确的口径）
        if step_id:
            rows = self._query(
                "SELECT 1 FROM steps WHERE run_id = ? AND step_id = ?", (run_id, step_id)
            )
            if not rows:
                self.add_step(run_id, step_id, step_id)
            self._exec(
                "UPDATE steps SET model_calls = model_calls + ? WHERE run_id = ? AND step_id = ?",
                (n, run_id, step_id),
            )

    def bump_research(self, run_id: str, n: int = 1) -> None:
        self._exec("UPDATE runs SET research_used = research_used + ? WHERE run_id = ?", (n, run_id))

    def budget_remaining(self, run_id: str) -> dict[str, int]:
        """M6 §31：执行层也需要知道剩余预算，以便降级（不是执行到一半才 BLOCKED）。"""
        run = self.get_run(run_id)
        started = time.mktime(time.strptime(run["created_at"], "%Y-%m-%dT%H:%M:%S"))
        return {
            "model_calls": int(run["budget_model_calls"]) - int(run["calls_used"]),
            "research_requests": int(run["budget_research"]) - int(run["research_used"]),
            "run_seconds": int(run["budget_seconds"]) - int(time.time() - started),
        }

    def check_budget(self, run_id: str, *, model_calls: int = 0, research: int = 0) -> None:
        run = self.get_run(run_id)
        if run["calls_used"] + model_calls > run["budget_model_calls"]:
            raise BudgetExceeded("model call budget exhausted")
        if run["research_used"] + research > run["budget_research"]:
            raise BudgetExceeded("research request budget exhausted")
        started = time.mktime(time.strptime(run["created_at"], "%Y-%m-%dT%H:%M:%S"))
        if time.time() - started > run["budget_seconds"]:
            raise BudgetExceeded("run time budget exhausted")

    def set_budgets(self, run_id: str, budgets: dict[str, int]) -> dict[str, int]:
        """Section 84 resume affordance: adjust a run's budget and report it.

        A key left out (or set to None) keeps its current value; a zero budget is
        honoured as given.
        """
        run = self.get_run(run_id)
        requested = {key: value for key, value in budgets.items() if value is not None}
        model_calls = int(requested.get("model_calls", run["budget_model_calls"]))
        research = int(requested.get("research_requests", run["budget_research"]))
        seconds = int(requested.get("run_seconds", run["budget_seconds"]))
        self._exec(
            "UPDATE runs SET budget_model_calls = ?, budget_research = ?, budget_seconds = ? WHERE run_id = ?",
            (model_calls, research, seconds, run_id),
        )
        return {"model_calls": model_calls, "research_requests": research, "run_seconds": seconds}

    def run_changeset_items(self, run_id: str) -> list[dict[str, Any]]:
        """Revisions this run already produced, oldest first.

        Resume primes the context with these so completed work is reused
        instead of being executed a second time.
        """
        return [
            dict(row)
            for row in self._query(
                "SELECT i.revision_id, i.artifact_id FROM changeset_items i "
                "JOIN changesets c ON c.changeset_id = i.changeset_id "
                "WHERE c.run_id = ? ORDER BY i.rowid",
                (run_id,),
            )
        ]

    def cancel_run(self, run_id: str) -> None:
        self._exec("UPDATE runs SET status = 'cancelled', ended_at = ? WHERE run_id = ?", (now_iso(), run_id))

    # ---------------------------------------------------------------- search logs

    def add_search_log(self, payload: dict[str, Any], run_id: str | None = None) -> str:
        log_id = "log_" + uuid.uuid4().hex[:10]
        self._exec(
            "INSERT INTO search_logs (log_id, project_id, run_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (log_id, self.project_id, run_id, canonical_json(payload), now_iso()),
        )
        return log_id

    def list_search_logs(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT payload FROM search_logs WHERE project_id = ? ORDER BY created_at DESC, rowid DESC", (self.project_id,)
        )
        return [json.loads(r["payload"]) for r in rows]
