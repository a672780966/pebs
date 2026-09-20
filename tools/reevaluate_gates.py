"""Re-run the G1–G7 gates over a stored benchmark project with the CURRENT gate code.

Usage:  python tools/reevaluate_gates.py <case_id> <project_id>

Why: before commit 5f99507 the dynamic path handed the gate context a
contract-filtered artifact view, so checks that read artifacts outside
gate-runner's `requires` (G1 word count/terminology, G3 pedagogy, G6 media,
G7 template, ...) were silently skipped. Stored runs therefore carry gate
statuses produced by a weaker gate. This tool replays the current gate code over
the artifacts of an existing project — no model calls — so the old runs can be
compared honestly instead of re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebs import config, gates  # noqa: E402
from pebs.benchmark import cases, checks  # noqa: E402
from pebs.evidence import EvidenceStore  # noqa: E402
from pebs.store import Store  # noqa: E402


def latest_content(store: Store, artifact_id: str):
    revisions = store.revisions_of(artifact_id)
    if not revisions:
        return {}
    return store.get_revision(revisions[-1])["content"] or {}


def all_overrides(store: Store) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for artifact in store.list_artifacts():
        revisions = store.revisions_of(artifact["artifact_id"])
        if revisions:
            overrides[artifact["artifact_id"]] = revisions[-1]
    return overrides


def stored_status(store: Store, gate_id: str, artifact_id: str) -> str | None:
    content = latest_content(store, f"gate:{gate_id}:{artifact_id}")
    return content.get("status") if content else None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 1
    case_id, project_id = argv[1], argv[2]
    cases.get_case(case_id)  # 校验 case 存在
    store = Store(project_id, config.project_dir(project_id))
    try:
        overrides = all_overrides(store)
        ctx = gates.GateContext(
            store=store,
            evidence=EvidenceStore(store),
            run_id="",
            environment="production",
            overrides=overrides,
        )
        script_ids = sorted(
            artifact_id
            for artifact_id in overrides
            if artifact_id.startswith("script:") and len(artifact_id.split(":")) > 1
        )
        rows = []
        for artifact_id in script_ids:
            for result in gates.run_section_gates(ctx, artifact_id):
                gate_id = result["gate_id"]
                before = stored_status(store, gate_id, artifact_id)
                rows.append(
                    {
                        "artifact": artifact_id,
                        "gate": gate_id,
                        "stored": before,
                        "now": result["status"],
                        "changed": before != result["status"],
                        "issues": [issue["reason"] for issue in result.get("issues", [])],
                    }
                )
        changed = [row for row in rows if row["changed"]]
        print(json.dumps({"project": project_id, "rows": len(rows), "changed": changed}, ensure_ascii=False, indent=1))
        return 0 if not changed else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
