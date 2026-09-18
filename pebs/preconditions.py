"""Execution preconditions: contracts a skill must satisfy BEFORE it may author.

These are deliberately separate from the G1-G8 QA gates. A QA gate evaluates an
artifact that already exists; a precondition decides whether authoring may start.
Keeping the two apart is what stops a QA gate from being reinterpreted as an entry
check, and it lets a precondition fail closed without inventing a gate result.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from . import config

# The pipeline marks a claim that is only a pending placeholder in the script with
# this usage value; such a claim must never be consumed by PCK authoring.
PLACEHOLDER_USAGE = "脚本待核验"

# Single owner of the precondition-kind contract: which inputs a checker kind
# actually consumes. Static validation reads this map, so a declaration can
# never claim an input the checker does not read.
PRECONDITION_CONTRACTS: dict[str, dict[str, Any]] = {
    "supported_claims": {"required_inputs": ["evidence_index"]},
}
PRECONDITION_KINDS = list(PRECONDITION_CONTRACTS)


def usage_tokens(usage: str) -> set[str]:
    """Claim.usage 是多值字段（例如"讲解/案例/评价"）；范围匹配按 token 交集。

    M6 生产修正：此前用整串与 usage_scope 精确比较，真实 Claim 永远不在范围里，
    导致 PCK 永远被阻塞（证据其实是 SUPPORTED）。
    """
    return {token.strip() for token in re.split(r"[/、,，;；|]", str(usage or "")) if token.strip()}


def allowed_claim_statuses() -> list[str]:
    """M6 §13/§48：默认只允许 SUPPORTED；操作者可在 rules.yaml 显式放行 QUALIFY_REQUIRED。

    放行的是"带限定语的文本"，不是"确定结论"；因此不降低 Evidence Gate，
    但允许实践型课程在文献只支持到 qualify 时继续生产（限定语必须保留）。
    """
    configured = (config.RULES.get("evidence") or {}).get("pck_claim_statuses")
    statuses = [str(item) for item in (configured or ["SUPPORTED"])]
    return statuses or ["SUPPORTED"]


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
    contract = PRECONDITION_CONTRACTS["supported_claims"]
    index = ctx.content(contract["required_inputs"][0]) or {}
    entries = index.get("claims")
    if not isinstance(entries, list) or not entries:
        # M6 §22/§48：概念/态度型课程可能没有实证 Claim。默认失败；操作者显式允许
        # （rules.evidence.allow_empty_claims=true）且 claims 步骤已声明时，PCK 可继续，
        # 限制必须已记录在 evidence_index 与 step note 中。
        allow_empty = bool((config.RULES.get("evidence") or {}).get("allow_empty_claims"))
        if allow_empty and index.get("declared_no_empirical_claims"):
            return []
        return ["证据索引为空，没有可用的 SUPPORTED Claim"]

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
        if scope is not None and not (usage_tokens(usage) & scope):
            continue
        consumed += 1
        status = ctx.evidence.claim_status(claim_id, version)
        allowed = allowed_claim_statuses()
        if status not in allowed:
            problems.append(
                f"{claim_id}@v{version} 状态为 {status}；PCK 只允许消费 {allowed} 证据（见 rules.evidence.pck_claim_statuses）"
            )
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
