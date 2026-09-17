from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import config

PROFILES_DIR = config.ROOT / "profiles"


def load_research_profile(name: str = "psychology") -> dict[str, Any]:
    path = PROFILES_DIR / "research" / f"{name}.yaml"
    if not path.exists():
        return {"profile": name, "sources": [], "missing": True}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["missing"] = False
    return data


def implemented_sources(profile: dict[str, Any]) -> list[str]:
    return [item["id"] for item in profile.get("sources", []) if item.get("status") == "implemented"]


def unimplemented_sources(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in profile.get("sources", []) if item.get("status") != "implemented"]


def validate_configured_sources(profile: dict[str, Any], configured: list[str]) -> list[str]:
    implemented = set(implemented_sources(profile))
    return [source for source in configured if source not in implemented]
