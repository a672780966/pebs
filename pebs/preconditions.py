"""Execution preconditions: contracts a skill must satisfy BEFORE it may author.

These are deliberately separate from the G1-G8 QA gates. A QA gate evaluates an
artifact that already exists; a precondition decides whether authoring may start.
Keeping the two apart is what stops a QA gate from being reinterpreted as an entry
check, and it lets a precondition fail closed without inventing a gate result.
"""

from __future__ import annotations

from typing import Any, Callable

# The pipeline marks a claim that is only a pending placeholder in the script with
# this usage value; such a claim must never be consumed by PCK authoring.
PLACEHOLDER_USAGE = "脚本待核验"

PRECONDITION_KINDS = ["supported_claims"]


def check_supported_claims(
    ctx: Any, *, inputs: list[str], usage_scope: list[str] | None = None
) -> list[str]:
    """Claims consumed by PCK must be SUPPORTED, current and in scope.

    The check runs over the claims listed in the declared evidence contract
    (evidence_index), never over claim history, so a superseded version that still
    exists in the store cannot poison an otherwise valid execution. A claim whose
    declared usage is outside `usage_scope` is not consumed by PCK and is ignored;
    a claim with no declared usage is ambiguous and fails closed.
    """
    index = ctx.content("evidence_index") or {}
    entries = index.get("claims")
    if not isinstance(entries, list) or not entries:
        return ["证据索引为空：没有可消费的 SUPPORTED Claim"]

    scope = {str(item) for item in usage_scope} if usage_scope else None
    problems: list[str] = []
    consumed = 0
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"证据索引条目格式非法：{entry!r}")
            continue
        claim_id = str(entry.get("claim_id") or "")
        version = entry.get("version")
        if not claim_id or not isinstance(version, int):
            problems.append(f"证据索引条目缺少 claim_id/version：{entry!r}")
            continue
        try:
            claim = ctx.evidence.get_claim(claim_id, version)
        except KeyError:
            problems.append(f"{claim_id}@v{version} 在证据库中不存在，无法确认证据状态")
            continue
        usage = str(claim.get("usage") or "").strip()
        if not usage:
            problems.append(f"{claim_id}@v{version} 未声明 usage，无法确认是否属于 PCK 证据契约")
            continue
        if scope is not None and usage not in scope:
            continue
        consumed += 1
        status = ctx.evidence.claim_status(claim_id, version)
        if status != "SUPPORTED":
            problems.append(f"{claim_id}@v{version} 状态为 {status}，PCK 只能消费 SUPPORTED 证据")
            continue
        if int(ctx.evidence.latest_version(claim_id)) != int(version):
            problems.append(f"{claim_id}@v{version} 已被新版本取代，需重新核验后才可消费")
            continue
        if not str(claim.get("population") or "").strip():
            problems.append(f"{claim_id}@v{version} 未声明 population，无法确认适用人群")
        if usage == PLACEHOLDER_USAGE:
            problems.append(f"{claim_id}@v{version} 的 usage 为「{usage}」，属于待核验占位")
    if not problems and consumed == 0:
        problems.append("证据契约范围内没有可用于 PCK 的 Claim")
    return problems


CHECKERS: dict[str, Callable[..., list[str]]] = {"supported_claims": check_supported_claims}


def evaluate(ctx: Any, node: dict[str, Any]) -> list[str]:
    """Blocking reasons for a node's declared preconditions (empty = satisfied)."""
    problems: list[str] = []
    for precondition in node.get("preconditions") or []:
        kind = str(precondition.get("kind") or "")
        checker = CHECKERS.get(kind)
        if checker is None:
            problems.append(f"未实现的前置条件：{kind or '<empty>'}")
            continue
        problems.extend(
            checker(
                ctx,
                inputs=list(precondition.get("inputs") or []),
                usage_scope=list(precondition.get("usage_scope") or []) or None,
            )
        )
    return problems


def block_reason(ctx: Any, node: dict[str, Any]) -> str | None:
    problems = evaluate(ctx, node)
    if not problems:
        return None
    return "执行前置条件未满足：" + "；".join(problems[:5])
