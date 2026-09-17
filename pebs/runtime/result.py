from __future__ import annotations

from typing import Any

from .. import schemas


def canonical_schema_name(artifact_type: str | None) -> str | None:
    from .. import registry

    if artifact_type is None:
        return None
    return registry.ARTIFACT_SCHEMAS.get(artifact_type)


def validate_result(
    content: Any,
    *,
    artifact_type: str | None,
    inline_schema: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(content, dict):
        return ["输出必须是 JSON 对象"]
    schema_name = canonical_schema_name(artifact_type)
    if schema_name:
        try:
            schemas.validate(content, schema_name)
        except schemas.SchemaError as exc:
            errors.append(f"canonical schema({schema_name}) 校验失败：{exc}")
    if inline_schema:
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(inline_schema)
        for error in sorted(validator.iter_errors(content), key=lambda item: list(item.absolute_path))[:5]:
            location = "/".join(str(part) for part in error.absolute_path) or "<root>"
            errors.append(f"skill schema 校验失败 at {location}: {error.message}")
    return errors
