from __future__ import annotations

import json
from pathlib import Path

import pytest

from pebs import config, pipeline, registry


def _runtime_steps() -> set[str]:
    return set(pipeline.STEPS.keys())


def _builtin_registry_steps() -> set[str]:
    skills = registry.load_skills()
    steps: set[str] = set()
    for record in skills.values():
        if record.get("runtime") == "builtin":
            steps.update(record.get("handler", {}).get("steps", []))
    return steps


def test_a_runtime_skills_are_registered():
    registered = _builtin_registry_steps()
    missing = _runtime_steps() - registered
    assert not missing, f"runtime steps missing from registry: {sorted(missing)}"


def test_b_enabled_skills_have_runtime_handlers():
    skills = registry.load_skills()
    runtime_steps = _runtime_steps()
    for name, record in skills.items():
        if record.get("runtime") != "builtin" or not record.get("invocation", {}).get("auto"):
            continue
        if record.get("status") not in ("APPROVED", "PATCHED"):
            continue
        steps = set(record.get("handler", {}).get("steps", []))
        assert steps, f"{name} has no steps"
        assert steps <= runtime_steps, f"{name} declares steps without handlers: {sorted(steps - runtime_steps)}"


def test_c_auto_invocable_skills_must_be_approved():
    for name, record in registry.load_skills().items():
        if record.get("invocation", {}).get("auto"):
            assert record.get("status") in ("APPROVED", "PATCHED"), f"{name} auto-invocable but status={record.get('status')}"
        if record.get("invocation", {}).get("explicit"):
            assert record.get("status") in ("APPROVED", "PATCHED"), f"{name} explicit-invocable but status={record.get('status')}"


def test_d_explicit_skills_resolve():
    explicit_map = registry.explicit_skill_map()
    assert "evidence-review" in explicit_map
    assert "diagram-design" in explicit_map
    assert "udl-lesson-auditor" in explicit_map
    for name, steps in explicit_map.items():
        assert name == registry.resolve_alias(name) or registry.resolve_alias(name) is not None
        assert steps, f"{name} explicit but no steps"
        assert set(steps) <= _runtime_steps()


def test_e_artifact_types_have_schemas():
    for artifact_type, schema_name in registry.ARTIFACT_SCHEMAS.items():
        schema_path = config.SCHEMA_DIR / f"{schema_name}.schema.json"
        assert schema_path.exists(), f"missing schema for artifact type {artifact_type}: {schema_path.name}"
    errors = registry.validate()
    assert not errors, errors


def test_f_no_registry_runtime_drift():
    registry_steps = _builtin_registry_steps()
    runtime_steps = _runtime_steps()
    assert registry_steps == runtime_steps, (
        f"drift detected. registry-only={sorted(registry_steps - runtime_steps)} "
        f"runtime-only={sorted(runtime_steps - registry_steps)}"
    )


def test_runtime_index_is_fresh():
    path = registry.runtime_index_path()
    assert path.exists(), "registry/runtime_index.json missing; run pebs.registry.write_runtime_index()"
    committed = json.loads(path.read_text(encoding="utf-8"))
    regenerated = registry.build_runtime_index()
    assert committed == regenerated, "runtime_index.json is stale; regenerate it"


def test_contract_validation_catches_bad_skill():
    broken = {
        "demo": {
            "name": "demo",
            "version": "0.1.0",
            "domain": "test",
            "description": "x",
            "status": "APPROVED",
            "invocation": {"auto": True, "explicit": False},
            "requires": [],
            "produces": ["unknown_artifact_type"],
            "optional_requires": [],
            "input_schema": None,
            "output_schema": None,
            "provider": [],
            "tools": [],
            "risk_level": "low",
            "network": False,
            "filesystem": "none",
            "external_side_effects": False,
            "runtime": "builtin",
            "handler": {"builtin_function": "", "steps": []},
            "gates_before": [],
            "gates_after": [],
            "parallelizable": False,
            "estimated_cost": {},
        }
    }
    errors = registry.validate(broken)
    assert any("unknown artifact type" in error for error in errors)
    assert any("builtin_function" in error for error in errors)


def test_g_runtime_skill_calls_resolve_in_registry():
    import re

    source = (Path(__file__).resolve().parent.parent / "pebs" / "pipeline.py").read_text(encoding="utf-8")
    called = sorted(set(re.findall(r'_skill\(ctx,\s*"([a-z0-9\-]+)"\)', source)))
    assert called, "expected pipeline to declare runtime skill calls"
    unresolved = [name for name in called if registry.resolve_alias(name) is None]
    assert not unresolved, f"runtime skill calls not in registry: {unresolved}"
    for name in called:
        canonical = registry.resolve_alias(name)
        record = registry.get(canonical)
        assert record is not None
        assert record.get("status") in ("APPROVED", "PATCHED"), f"{name} used at runtime but status={record.get('status')}"


def test_denylist_blocks_skill():
    assert registry.is_denied("skills-mgr")
    assert not registry.is_denied("script-writer")


def test_search_by_artifact_and_domain():
    producers = registry.producers_of("script")
    assert "script-writer" in producers
    consumers = registry.consumers_of("script")
    assert "media-router" in consumers
    media = registry.search(domain="media")
    names = {item["name"] for item in media}
    assert {"media-router", "diagram-designer", "animation-gate", "storyboard-designer", "load-reviewer"} <= names
