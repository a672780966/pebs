from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator

from . import config


class SchemaError(Exception):
    pass


_validators: dict[str, Draft202012Validator] = {}


def _validator(name: str) -> Draft202012Validator:
    if name not in _validators:
        path = config.SCHEMA_DIR / f"{name}.schema.json"
        if not path.exists():
            raise SchemaError(f"unknown schema: {name}")
        with path.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)
        _validators[name] = Draft202012Validator(schema)
    return _validators[name]


def validate(instance: Any, name: str) -> None:
    errors = sorted(_validator(name).iter_errors(instance), key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.absolute_path)
        raise SchemaError(f"{name} invalid at {loc or '<root>'}: {first.message}")


def is_valid(instance: Any, name: str) -> bool:
    try:
        validate(instance, name)
        return True
    except SchemaError:
        return False
