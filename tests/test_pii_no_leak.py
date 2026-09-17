"""C6: pre-send exclusion and no-leak for identifiable input (spec 57.1, A20).

Section 57.1 and A20 require identifiable data to be excluded before any external
send and to leave no trace in logs, memory or retrieval requests. No UNREVIEWED
lifecycle is assumed here: this module only proves the documented behaviour.

The original material is a local file by design, and the project keeps a record of
which material was withheld so a teacher can inspect it. The leak surfaces checked
below are therefore the ones the owner document names: provider prompts, retrieval
requests, memory and logs.
"""

from __future__ import annotations

from conftest import REQUEST_1, run_build

STUDENT_NAME = "张三"
STUDENT_ID = "20230001"
PHONE = "13800138000"
CREDENTIAL = "sk-live-9f8e7d6c5b4a"
SECRETS = (STUDENT_NAME, STUDENT_ID, PHONE, CREDENTIAL)


def _sensitive_material(tmp_path):
    material = tmp_path / "家长联系表.txt"
    material.write_text(
        f"学生：{STUDENT_NAME} 学号：{STUDENT_ID} 家长李四 手机 {PHONE}\n研究者凭据 {CREDENTIAL}\n",
        encoding="utf-8",
    )
    return material


def test_identifiable_material_reaches_no_persisted_surface(engine, tmp_path):
    material = _sensitive_material(tmp_path)
    run_id, changeset_id = run_build(engine, REQUEST_1, material_paths=[material])
    engine.accept(changeset_id)

    # 1. It is excluded before any external send.
    assert engine.llm.prompts, "the build must have produced prompts"
    for prompt in engine.llm.prompts:
        for secret in SECRETS:
            assert secret not in prompt, f"{secret} leaked into a provider prompt"

    # 2. It does not leak into the named persistence surfaces.
    surfaces: dict[str, str] = {}
    for index, log in enumerate(engine.store.list_search_logs()):
        surfaces[f"search_log:{index}"] = str(log)
    for step in engine.store.get_steps(run_id):
        surfaces[f"step:{step['step_id']}"] = f"{step.get('note') or ''} {step.get('error') or ''}"
    for source in engine.evidence.sources():
        surfaces[f"evidence_source:{source.get('source_id')}"] = str(source)
    for folder in ("memory", "logs"):
        directory = engine.base / folder
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                surfaces[f"{folder}:{path.name}"] = path.read_text(encoding="utf-8", errors="replace")

    assert surfaces, "expected at least one persisted surface to inspect"
    for surface, text in surfaces.items():
        for secret in SECRETS:
            assert secret not in text, f"{secret} leaked into {surface}"


def test_withheld_material_is_recorded_as_sensitive_but_not_as_evidence(engine, tmp_path):
    """The exclusion is visible to the teacher without becoming an evidence source."""
    material = _sensitive_material(tmp_path)
    run_id, _ = run_build(engine, REQUEST_1, material_paths=[material])

    materials = engine.store.get_revision(engine.store.revisions_of("materials")[-1])["content"]
    entry = materials["files"][0]
    assert entry["sensitive"] is True
    assert "student_id" in entry["pii_types"]

    # The withheld material must not enter the evidence base or the retrieval surface.
    assert [s for s in engine.evidence.sources() if s["source_type"] == "user_material"] == []
    assert all(STUDENT_ID not in str(log) for log in engine.store.list_search_logs())
