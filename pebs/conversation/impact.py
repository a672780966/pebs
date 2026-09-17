from __future__ import annotations

from typing import Any


def _artifact_of_revision(store: Any, revision_id: str) -> str | None:
    try:
        return store.get_revision(revision_id)["artifact_id"]
    except Exception:  # noqa: BLE001 - unknown revision means no dependency
        return None


def _upstream_artifacts(store: Any, revision_id: str) -> set[str]:
    """沿着 revision 依赖向上取闭包，映射到 artifact 级别。

    同一个 artifact 的后续 revision（例如 draft 降级时的 export_manifest@r2）会指向
    自己更早的 revision，因此必须做传递闭包，否则会漏掉真实的上游产物。
    """
    seen: set[str] = set()
    queue = [revision_id]
    artifacts: set[str] = set()
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for upstream in store.upstream_revs(current):
            if upstream in seen:
                continue
            artifact_id = _artifact_of_revision(store, upstream)
            if artifact_id:
                artifacts.add(artifact_id)
            queue.append(upstream)
    return artifacts


def impact(store: Any, artifact_ids: list[str]) -> dict[str, Any]:
    accepted = {
        item["artifact_id"]: item
        for item in store.list_artifacts()
        if item.get("accepted_rev")
    }
    seeds = [artifact_id for artifact_id in artifact_ids if artifact_id in accepted]
    if not seeds:
        return {"affected": [], "order": [], "edges": [], "unresolved": list(artifact_ids)}

    upstream_map: dict[str, set[str]] = {}
    downstream: dict[str, set[str]] = {}
    for artifact_id, item in accepted.items():
        revision = store.get_revision(item["accepted_rev"])
        upstream_artifacts = {
            upstream
            for upstream in _upstream_artifacts(store, revision["revision_id"])
            if upstream in accepted and upstream != artifact_id
        }
        upstream_map[artifact_id] = upstream_artifacts
        for upstream in upstream_artifacts:
            downstream.setdefault(upstream, set()).add(artifact_id)

    affected: set[str] = set()
    queue = list(seeds)
    while queue:
        current = queue.pop()
        if current in affected:
            continue
        affected.add(current)
        for dependent in downstream.get(current, set()):
            if dependent not in affected:
                queue.append(dependent)

    dependencies: dict[str, set[str]] = {
        artifact_id: {upstream for upstream in upstream_map.get(artifact_id, set()) if upstream in affected}
        for artifact_id in affected
    }

    order: list[str] = []
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        visited.add(artifact_id)
        for dependency in sorted(dependencies.get(artifact_id, set())):
            visit(dependency)
        order.append(artifact_id)

    for artifact_id in sorted(affected):
        visit(artifact_id)

    edges = [
        {"from": dependency, "to": artifact_id}
        for artifact_id, deps in sorted(dependencies.items())
        for dependency in sorted(deps)
    ]
    unresolved = [artifact_id for artifact_id in artifact_ids if artifact_id not in accepted]
    return {"affected": sorted(affected), "order": order, "edges": edges, "unresolved": unresolved}
