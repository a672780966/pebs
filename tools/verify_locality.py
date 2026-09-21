"""Acceptance 7 verification on current code with minimal quota.

Copies an existing built project, runs the real local edit there (so the stored
project is untouched), and measures locality with the same code path the
benchmark uses.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from pebs import config  # noqa: E402
from pebs.benchmark import cases, metrics  # noqa: E402
from pebs.engine import Engine  # noqa: E402

def _pick_source() -> Path:
    """挑一个 base 课程真正建成的 F run（否则没有可编辑的已接受产物）。"""
    candidates = []
    for path in sorted(Path("benchmarks/runs").glob("*F-scenario/run.json")):
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        if record.get("base_run_status") == "succeeded":
            candidates.append((path.parent, record.get("run_status")))
    if not candidates:
        raise SystemExit("no F scenario run with a succeeded base course")
    # 优先取本次 scenario 也成功的（有完整 locality 记录），否则取最新
    for path, status in reversed(candidates):
        if status == "succeeded":
            return path
    return candidates[-1][0]


source_run = _pick_source()
print("source run:", source_run.name)
record = json.loads((source_run / "run.json").read_text(encoding="utf-8-sig"))
project_id = record["project_id"]
original = config.project_dir(project_id)
scratch = Path(tempfile.mkdtemp(prefix="fverify-")) / project_id
shutil.copytree(original, scratch)

case = cases.get_case("F")
instruction = str(case.get("edit_instruction") or case["request"])
preserve = [str(item) for item in (case.get("preserve") or [])]

engine = Engine(project_id, base_dir=scratch)
try:
    before = metrics.snapshot_hashes(engine.store)
    result = engine.conversation_edit(instruction)
    status = result.get("run_status")
    if status == "succeeded":
        engine.accept(result["changeset_id"])
    after = metrics.snapshot_hashes(engine.store)
    locality = metrics.locality_report(
        before, after, preserve=preserve, expected=result.get("affected_artifacts") or []
    )
    print("status:", status)
    run_id = result.get("run_id")
    if run_id:
        for step in engine.store.get_steps(run_id):
            if step["status"] not in ("SUCCEEDED",):
                print("  failing step:", step["step_id"], step["status"], (step.get("error") or "")[:160])
        for artifact in engine.store.list_artifacts():
            if artifact["artifact_type"] != "gate_result":
                continue
            revisions = engine.store.revisions_of(artifact["artifact_id"])
            if not revisions:
                continue
            content = engine.store.get_revision(revisions[-1])["content"]
            if content.get("status") in ("FAIL", "NEEDS_REVIEW") and "sec2" in artifact["artifact_id"]:
                print("  gate:", artifact["artifact_id"], content.get("status"),
                      [issue.get("reason", "")[:70] for issue in content.get("issues", [])][:2])
    print("calls:", engine.store.get_run(run_id)["calls_used"] if run_id else 0)
    print("affected:", result.get("affected_artifacts"))
    print("locked:", len(result.get("locked_artifacts") or []))
    print("locality_preservation_rate:", locality["locality_preservation_rate"])
    print("preserve_violations:", locality["preserve_violations"])
    print("unnecessary_regeneration:", locality["unnecessary_regeneration"])
finally:
    engine.close()
    shutil.rmtree(scratch.parent, ignore_errors=True)
