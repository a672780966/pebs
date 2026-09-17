from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from .store import Store, now_iso

CLAIM_TYPES = [
    "descriptive",
    "correlational",
    "predictive",
    "causal",
    "mechanistic",
    "theoretical",
    "speculative",
]
SUPPORT_RELATIONS = ["direct", "indirect", "contextual", "contradictory", "insufficient"]
ASSESSMENT_RESULTS = [
    "PENDING",
    "SUPPORTED",
    "QUALIFY_REQUIRED",
    "UNSUPPORTED",
    "DISPUTED",
    "HUMAN_REVIEW_REQUIRED",
]
_SEVERITY = ["DISPUTED", "UNSUPPORTED", "HUMAN_REVIEW_REQUIRED", "QUALIFY_REQUIRED", "SUPPORTED", "PENDING"]

EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
  revision_id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  text TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  population TEXT NOT NULL DEFAULT '',
  usage TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'PENDING',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
  revision_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  identifiers TEXT NOT NULL DEFAULT '{}',
  publish_date TEXT,
  publish_date_unknown INTEGER NOT NULL DEFAULT 1,
  fetched_at TEXT NOT NULL,
  content_level TEXT NOT NULL,
  snapshot_path TEXT,
  sha256 TEXT,
  retrieval_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS assessments (
  assessment_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  claim_rev TEXT NOT NULL,
  source_rev TEXT NOT NULL,
  quote TEXT NOT NULL,
  quote_location TEXT NOT NULL DEFAULT '',
  support TEXT NOT NULL DEFAULT 'insufficient',
  design_note TEXT NOT NULL DEFAULT '',
  scope TEXT NOT NULL DEFAULT '',
  limitations TEXT NOT NULL DEFAULT '',
  uncertainty TEXT NOT NULL DEFAULT '',
  method TEXT NOT NULL,
  method_version TEXT NOT NULL,
  verified_at TEXT NOT NULL,
  result TEXT NOT NULL DEFAULT 'PENDING',
  note TEXT NOT NULL DEFAULT ''
);
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _slug(text: str) -> str:
    digest = hashlib.sha1(_normalize(text).encode("utf-8")).hexdigest()
    return digest[:10]


class EvidenceStore:
    def __init__(self, store: Store):
        self.store = store
        self.conn = store.conn
        self.conn.executescript(EVIDENCE_SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ claims

    def add_claim(
        self,
        text: str,
        claim_type: str,
        *,
        population: str = "",
        usage: str = "",
        claim_id: str | None = None,
    ) -> dict[str, Any]:
        if claim_type not in CLAIM_TYPES:
            raise ValueError(f"invalid claim_type: {claim_type}")
        claim_id = claim_id or ("clm_" + _slug(text))
        version = self.latest_version(claim_id) + 1
        revision_id = f"{claim_id}@v{version}"
        self.conn.execute(
            "INSERT INTO claims (revision_id, claim_id, project_id, version, text, claim_type, population, usage, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)",
            (
                revision_id,
                claim_id,
                self.store.project_id,
                version,
                text,
                claim_type,
                population,
                usage,
                now_iso(),
            ),
        )
        self.conn.commit()
        return {"claim_id": claim_id, "version": version, "revision_id": revision_id, "status": "PENDING"}

    def latest_version(self, claim_id: str) -> int:
        rows = list(
            self.conn.execute("SELECT MAX(version) AS v FROM claims WHERE claim_id = ?", (claim_id,))
        )
        return int(rows[0]["v"] or 0)

    def get_claim(self, claim_id: str, version: int | None = None) -> dict[str, Any]:
        if version is None:
            version = self.latest_version(claim_id)
        rows = list(
            self.conn.execute(
                "SELECT * FROM claims WHERE claim_id = ? AND version = ?", (claim_id, version)
            )
        )
        if not rows:
            raise KeyError(f"claim not found: {claim_id}@v{version}")
        row = dict(rows[0])
        row["identifiers"] = None
        return row

    def claims(self) -> list[dict[str, Any]]:
        rows = list(
            self.conn.execute(
                "SELECT * FROM claims WHERE project_id = ? ORDER BY created_at, claim_id", (self.store.project_id,)
            )
        )
        return [dict(r) for r in rows]

    def set_claim_status(self, claim_rev: str, status: str) -> None:
        if status not in ASSESSMENT_RESULTS:
            raise ValueError(f"invalid status: {status}")
        self.conn.execute("UPDATE claims SET status = ? WHERE revision_id = ?", (status, claim_rev))
        self.conn.commit()

    def recompute_claim_status(self, claim_id: str, version: int) -> str:
        rows = list(
            self.conn.execute(
                "SELECT result FROM assessments WHERE claim_rev = ?", (f"{claim_id}@v{version}",)
            )
        )
        results = [r["result"] for r in rows]
        if not results:
            status = "PENDING"
        elif all(r == "SUPPORTED" for r in results):
            status = "SUPPORTED"
        else:
            status = next((s for s in _SEVERITY if s in results), "PENDING")
        self.set_claim_status(f"{claim_id}@v{version}", status)
        return status

    # ------------------------------------------------------------------ sources

    def add_source(
        self,
        *,
        source_type: str,
        title: str,
        identifiers: dict[str, Any] | None = None,
        publish_date: str | None = None,
        content_level: str,
        snapshot_text: str | None = None,
        retrieval_note: str = "",
        source_id: str | None = None,
    ) -> dict[str, Any]:
        identifiers = identifiers or {}
        if source_id is None:
            doi = identifiers.get("doi")
            source_id = "src_doi_" + _slug(str(doi)) if doi else "src_" + _slug(title + str(sorted(identifiers.items())))
        existing = list(self.conn.execute("SELECT MAX(version) AS v FROM sources WHERE source_id = ?", (source_id,)))
        version = int(existing[0]["v"] or 0) + 1
        revision_id = f"{source_id}@v{version}"
        snapshot_path = None
        digest = None
        if snapshot_text is not None:
            snap_dir = self.store.base_dir / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_file = snap_dir / f"{source_id}.v{version}.txt"
            snap_file.write_text(snapshot_text, encoding="utf-8")
            snapshot_path = str(snap_file)
            digest = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
        import json as _json

        self.conn.execute(
            "INSERT INTO sources (revision_id, source_id, project_id, version, source_type, title, identifiers, "
            "publish_date, publish_date_unknown, fetched_at, content_level, snapshot_path, sha256, retrieval_note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                revision_id,
                source_id,
                self.store.project_id,
                version,
                source_type,
                title,
                _json.dumps(identifiers, ensure_ascii=False, sort_keys=True),
                publish_date,
                1 if not publish_date else 0,
                now_iso(),
                content_level,
                snapshot_path,
                digest,
                retrieval_note,
            ),
        )
        self.conn.commit()
        return {"source_id": source_id, "version": version, "revision_id": revision_id, "content_level": content_level}

    def get_source(self, source_id: str, version: int | None = None) -> dict[str, Any]:
        if version is None:
            rows = list(
                self.conn.execute("SELECT MAX(version) AS v FROM sources WHERE source_id = ?", (source_id,))
            )
            version = int(rows[0]["v"] or 0)
        rows = list(
            self.conn.execute("SELECT * FROM sources WHERE source_id = ? AND version = ?", (source_id, version))
        )
        if not rows:
            raise KeyError(f"source not found: {source_id}@v{version}")
        return dict(rows[0])

    def sources(self) -> list[dict[str, Any]]:
        rows = list(
            self.conn.execute(
                "SELECT * FROM sources WHERE project_id = ? ORDER BY fetched_at, source_id", (self.store.project_id,)
            )
        )
        return [dict(r) for r in rows]

    def source_text(self, source_rev: str) -> str | None:
        rows = list(self.conn.execute("SELECT snapshot_path FROM sources WHERE revision_id = ?", (source_rev,)))
        if not rows or not rows[0]["snapshot_path"]:
            return None
        path = Path(rows[0]["snapshot_path"])
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def quote_present(self, source_rev: str, quote: str) -> bool:
        text = self.source_text(source_rev)
        if text is None:
            return False
        return _normalize(quote) in _normalize(text)

    # -------------------------------------------------------------- assessments

    def add_assessment(
        self,
        *,
        claim_id: str,
        claim_version: int,
        source_id: str,
        source_version: int,
        quote: str,
        quote_location: str,
        support: str,
        result: str,
        method: str,
        method_version: str,
        design_note: str = "",
        scope: str = "",
        limitations: str = "",
        uncertainty: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        if support not in SUPPORT_RELATIONS:
            raise ValueError(f"invalid support relation: {support}")
        if result not in ASSESSMENT_RESULTS:
            raise ValueError(f"invalid result: {result}")
        claim_rev = f"{claim_id}@v{claim_version}"
        source_rev = f"{source_id}@v{source_version}"
        if quote and not self.quote_present(source_rev, quote):
            raise ValueError("quote not locatable in source snapshot; refusing to record assessment")
        assessment_id = "asm_" + uuid.uuid4().hex[:10]
        self.conn.execute(
            "INSERT INTO assessments (assessment_id, project_id, claim_rev, source_rev, quote, quote_location, support, "
            "design_note, scope, limitations, uncertainty, method, method_version, verified_at, result, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                assessment_id,
                self.store.project_id,
                claim_rev,
                source_rev,
                quote,
                quote_location,
                support,
                design_note,
                scope,
                limitations,
                uncertainty,
                method,
                method_version,
                now_iso(),
                result,
                note,
            ),
        )
        self.conn.commit()
        self.recompute_claim_status(claim_id, claim_version)
        return {"assessment_id": assessment_id, "claim_id": claim_id, "claim_version": claim_version, "source_id": source_id, "source_version": source_version, "result": result}

    def review_claim(
        self,
        claim_id: str,
        version: int,
        *,
        decision: str,
        reviewer: str,
        basis: str,
        source_id: str | None = None,
        source_version: int | None = None,
        quote: str = "",
        quote_location: str = "",
    ) -> dict[str, Any]:
        if not (reviewer or "").strip():
            raise ValueError("人工复核必须记录复核人")
        if not (basis or "").strip():
            raise ValueError("人工复核必须记录依据（不能只点击按钮强制批准）")
        mapping = {
            "supported": "SUPPORTED",
            "qualify": "QUALIFY_REQUIRED",
            "unsupported": "UNSUPPORTED",
            "disputed": "DISPUTED",
            "human_review": "HUMAN_REVIEW_REQUIRED",
        }
        result = mapping.get(decision)
        if result is None:
            raise ValueError(f"未知复核决定：{decision}")
        if result == "SUPPORTED":
            if not source_id or not quote.strip():
                raise ValueError("转为 SUPPORTED 必须提供来源与可定位原文引用")
            source = self.get_source(source_id, source_version)
            if not self.quote_present(source["revision_id"], quote):
                raise ValueError("引用无法在来源快照中定位；拒绝强制批准")
            return self.add_assessment(
                claim_id=claim_id,
                claim_version=version,
                source_id=source["source_id"],
                source_version=source["version"],
                quote=quote.strip(),
                quote_location=quote_location,
                support="direct",
                result="SUPPORTED",
                method="human-review",
                method_version="manual-1.0",
                design_note=f"人工复核：{basis.strip()}",
                note=f"reviewer={reviewer.strip()}",
            )
        return self.add_assessment(
            claim_id=claim_id,
            claim_version=version,
            source_id=source_id or "manual_review",
            source_version=source_version or 1,
            quote=quote.strip(),
            quote_location=quote_location,
            support="insufficient" if result == "UNSUPPORTED" else "contextual",
            result=result,
            method="human-review",
            method_version="manual-1.0",
            design_note=f"人工复核：{basis.strip()}",
            note=f"reviewer={reviewer.strip()}",
        )

    def assessments(self, claim_id: str | None = None, version: int | None = None) -> list[dict[str, Any]]:
        if claim_id is not None:
            claim_rev = f"{claim_id}@v{version}" if version else None
            if claim_rev:
                rows = list(
                    self.conn.execute("SELECT * FROM assessments WHERE claim_rev = ?", (claim_rev,))
                )
            else:
                rows = list(
                    self.conn.execute(
                        "SELECT * FROM assessments WHERE claim_rev LIKE ?", (f"{claim_id}@v%",)
                    )
                )
        else:
            rows = list(
                self.conn.execute("SELECT * FROM assessments WHERE project_id = ?", (self.store.project_id,))
            )
        return [dict(r) for r in rows]

    def claim_status(self, claim_id: str, version: int) -> str:
        rows = list(
            self.conn.execute("SELECT status FROM claims WHERE claim_id = ? AND version = ?", (claim_id, version))
        )
        if not rows:
            raise KeyError(f"claim not found: {claim_id}@v{version}")
        return rows[0]["status"]

    def is_supported(self, claim_ref: str) -> bool:
        if "@v" not in claim_ref:
            return False
        claim_id, version_text = claim_ref.split("@v", 1)
        try:
            version = int(version_text)
        except ValueError:
            return False
        rows = list(
            self.conn.execute("SELECT status FROM claims WHERE claim_id = ? AND version = ?", (claim_id, version))
        )
        return bool(rows) and rows[0]["status"] == "SUPPORTED"
