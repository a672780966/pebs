"""Golden Course Benchmark（M6 §20–§27）：case 定义加载与校验。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .. import config

VALID_MODES = ("direct_codex", "builtin", "dynamic", "mixed")
REQUIRED_FIELDS = ("id", "title", "request", "expect")


def benchmark_dir() -> Path:
    return Path(config.BENCHMARKS_DIR)


def cases_dir() -> Path:
    return benchmark_dir() / "cases"


def fixtures_dir() -> Path:
    return benchmark_dir() / "fixtures"


def runs_dir() -> Path:
    return benchmark_dir() / "runs"


def reports_dir() -> Path:
    return benchmark_dir() / "reports"


def load_case(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"benchmark case must be a mapping: {path}")
    data["_path"] = str(path)
    data.setdefault("mode_targets", list(VALID_MODES))
    data.setdefault("template_fixture", "")
    data.setdefault("material_fixtures", [])
    return data


def load_cases() -> list[dict[str, Any]]:
    directory = cases_dir()
    if not directory.exists():
        return []
    return [load_case(path) for path in sorted(directory.glob("*.yaml"))]


def get_case(case_id: str) -> dict[str, Any]:
    for case in load_cases():
        if case.get("id") == case_id:
            return case
    raise KeyError(f"unknown benchmark case: {case_id}")


def validate_case(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not case.get(field):
            errors.append(f"{case.get('id', '?')}: missing field '{field}'")
    for mode in case.get("mode_targets", []):
        if mode not in VALID_MODES:
            errors.append(f"{case.get('id', '?')}: invalid mode '{mode}'")
    expect = case.get("expect") or {}
    if not isinstance(expect, dict):
        errors.append(f"{case.get('id', '?')}: expect must be a mapping")
    routing = expect.get("routing") or {}
    if routing and not isinstance(routing, dict):
        errors.append(f"{case.get('id', '?')}: expect.routing must be a mapping")
    for fixture in [case.get("template_fixture")] + list(case.get("material_fixtures") or []):
        if fixture and not (benchmark_dir() / fixture).exists():
            errors.append(f"{case.get('id', '?')}: fixture missing: {fixture}")
    return errors


def fixture_path(case: dict[str, Any], key: str) -> Path | None:
    value = case.get(key)
    if not value:
        return None
    path = benchmark_dir() / str(value)
    return path if path.exists() else None
