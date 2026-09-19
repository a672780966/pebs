"""Re-evaluate a stored benchmark project with the CURRENT check code (no model calls).

Usage:  python tools/reevaluate_checks.py <case_id> <project_id>

Useful after fixing a checker: confirm the fix removes the false positives on the exact
artifacts that produced them, without spending provider quota on a new run.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebs import config  # noqa: E402
from pebs.benchmark import cases, checks  # noqa: E402
from pebs.store import Store  # noqa: E402


def latest_content(store: Store, artifact_id: str):
    revisions = store.revisions_of(artifact_id)
    if not revisions:
        return {}
    return store.get_revision(revisions[-1])["content"] or {}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 1
    case_id, project_id = argv[1], argv[2]
    case = cases.get_case(case_id)
    store = Store(project_id, config.project_dir(project_id))
    try:
        plan = latest_content(store, "build_plan_dynamic")
        route = latest_content(store, "router_result")
        result = checks.evaluate(store, case.get("expect") or {}, plan=plan, route=route)
    finally:
        store.close()
    print("issues:", len(result["issues"]))
    print("counts:", json.dumps(result["counts"], ensure_ascii=False))
    for issue in result["issues"]:
        print(" -", issue["kind"], issue["detail"][:160])
    return 0 if not result["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
