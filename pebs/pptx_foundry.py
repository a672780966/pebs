from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import config, skills_mgr


def _runtime_tool(tool: str) -> Path | None:
    try:
        runtime = skills_mgr.resolve_runtime("ppt-foundry")
    except skills_mgr.SkillError:
        return None
    path = Path(runtime["path"])
    candidates = [path / "scripts" / tool]
    for child in path.iterdir() if path.exists() else []:
        candidates.append(child / "scripts" / tool)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def available() -> bool:
    return _runtime_tool("pptx_delivery_check.py") is not None


def delivery_check(pptx_path: Path, *, timeout: int = 180) -> dict[str, Any] | None:
    tool = _runtime_tool("pptx_delivery_check.py")
    if tool is None:
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), str(pptx_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(tool.parent),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}
    output = (proc.stdout or "").strip()
    try:
        return json.loads(output)
    except ValueError:
        return {
            "status": "error",
            "returncode": proc.returncode,
            "error": ((proc.stderr or "") + output)[-300:],
        }


def provenance() -> dict[str, Any]:
    try:
        runtime = skills_mgr.resolve_runtime("ppt-foundry")
    except skills_mgr.SkillError:
        return {"skill": "ppt-foundry", "pinned_version": None, "path": None}
    return {"skill": "ppt-foundry", "pinned_version": runtime["version"], "path": runtime["path"]}
