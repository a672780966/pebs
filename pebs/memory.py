from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import Store, now_iso


def write_memory(store: Store) -> Path:
    requirements = store.accepted_content("requirements") or {}
    template_spec = store.accepted_content("template_spec") or {}
    cases = []
    for artifact in store.list_artifacts():
        if artifact["artifact_type"] != "case" or not artifact["accepted_rev"]:
            continue
        case = store.accepted_content(artifact["artifact_id"]) or {}
        cases.append(
            {
                "artifact_id": artifact["artifact_id"],
                "title": case.get("title"),
                "kind": case.get("kind"),
                "section_id": case.get("section_id"),
            }
        )
    decisions: dict[str, Any] = {
        "course": requirements.get("course"),
        "language": requirements.get("language"),
        "terminology": requirements.get("terminology", []),
        "word_rules": requirements.get("word_rules", {}),
        "outputs": requirements.get("outputs", []),
        "template": {
            "kind": template_spec.get("kind"),
            "columns": [c.get("name") for c in template_spec.get("columns", [])],
            "sha256": template_spec.get("sha256"),
        },
        "approved_cases": cases,
        "section_titles": [s.get("title") for s in requirements.get("sections", [])],
        "updated_at": now_iso(),
    }
    path = Path(store.base_dir) / "memory" / "project_memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_memory(store: Store) -> dict[str, Any] | None:
    path = Path(store.base_dir) / "memory" / "project_memory.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
