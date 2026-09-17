from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SCHEMA_DIR = CONFIG_DIR / "schemas"
REGISTRY_DIR = ROOT / "registry"
PROJECTS_DIR = ROOT / "projects"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


RULES: dict[str, Any] = load_yaml(CONFIG_DIR / "rules.yaml")
PROVIDERS: dict[str, Any] = load_yaml(CONFIG_DIR / "providers.yaml")
ROUTER: dict[str, Any] = load_yaml(CONFIG_DIR / "router.yaml")
RISK: dict[str, Any] = load_yaml(CONFIG_DIR / "risk.yaml")
SKILLS_SOURCES: dict[str, Any] = load_yaml(CONFIG_DIR / "skills_sources.yaml")
SLIDE_FAMILIES: dict[str, Any] = load_yaml(CONFIG_DIR / "slide_families.yaml")

SKILLS_DIR = ROOT / "skills"
QUARANTINE_DIR = SKILLS_DIR / "quarantine"
UPSTREAM_DIR = SKILLS_DIR / "upstream"
PATCHED_DIR = SKILLS_DIR / "patched"
PATCHES_DIR = ROOT / "patches"

RULES_VERSION = "rules-" + hashlib.sha256((CONFIG_DIR / "rules.yaml").read_bytes()).hexdigest()[:12]

CHECK_VERSIONS = {
    "G1": "g1-1.0",
    "G2": "g2-1.0",
    "G3": "g3-1.0",
    "G4": "g4-1.0",
    "G5": "g5-1.0",
    "G6": "g6-1.0",
    "G7": "g7-1.0",
    "G8": "g8-1.0",
}
EVIDENCE_METHOD_VERSION = "ev-gate-1.0"
FORMAL_GATES = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]


def env_present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def ensure_project_dirs(project_id: str) -> Path:
    base = project_dir(project_id)
    for sub in ["inputs", "artifacts", "snapshots", "outputs/draft", "outputs/formal", "memory", "logs"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base
