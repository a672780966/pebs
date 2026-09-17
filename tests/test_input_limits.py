from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from conftest import REQUEST_2, run_build

from pebs import config
from pebs import server as server_mod
from pebs.template_parse import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    ImportLimitExceeded,
    check_import_limits,
)

MIB = 1024 * 1024

# Owner decisions (spec 83.2, 输入): per-file 25 MiB, per-import 20 files,
# per-import aggregate 100 MiB, rejected before parsing and never truncated.
# Transport mapping: byte-size violations 413, the batch file-count 400.


def _sized(path, size):
    """Create a file of exactly `size` bytes without paying for the bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def test_exact_boundaries_are_accepted(tmp_path):
    # 20 files x 5 MiB hits both MAX_FILES and MAX_TOTAL_BYTES exactly.
    files = [_sized(tmp_path / f"f{index}.bin", 5 * MIB) for index in range(MAX_FILES)]
    assert sum(path.stat().st_size for path in files) == MAX_TOTAL_BYTES
    assert check_import_limits(files) == []


def test_single_file_exactly_at_limit_is_accepted(tmp_path):
    assert check_import_limits([_sized(tmp_path / "exactly.bin", MAX_FILE_BYTES)]) == []


def test_file_count_over_limit_is_rejected_with_400(tmp_path):
    files = [_sized(tmp_path / f"f{index}.bin", 1) for index in range(MAX_FILES + 1)]
    with pytest.raises(ImportLimitExceeded) as excinfo:
        check_import_limits(files)
    assert excinfo.value.http_status == 400
    assert str(MAX_FILES) in str(excinfo.value)


def test_single_file_over_limit_is_rejected_with_413(tmp_path):
    oversized = _sized(tmp_path / "huge.bin", MAX_FILE_BYTES + 1)
    with pytest.raises(ImportLimitExceeded) as excinfo:
        check_import_limits([oversized])
    assert excinfo.value.http_status == 413
    assert "huge.bin" in str(excinfo.value)
    assert "25 MiB" in str(excinfo.value)


def test_aggregate_over_limit_is_rejected_with_413(tmp_path):
    # Every file is under the per-file cap; only the batch total is over.
    files = [_sized(tmp_path / f"f{index}.bin", 21 * MIB) for index in range(5)]
    assert all(path.stat().st_size <= MAX_FILE_BYTES for path in files)
    assert sum(path.stat().st_size for path in files) > MAX_TOTAL_BYTES
    with pytest.raises(ImportLimitExceeded) as excinfo:
        check_import_limits(files)
    assert excinfo.value.http_status == 413
    assert "100 MiB" in str(excinfo.value)


def test_pipeline_rejects_over_limit_batch_before_parsing(engine, tmp_path):
    files = [_sized(tmp_path / f"f{index}.bin", 1) for index in range(MAX_FILES + 1)]
    run_id, _ = run_build(engine, REQUEST_2, material_paths=files)

    steps = {step["step_id"]: step for step in engine.store.get_steps(run_id)}
    assert steps["parse_inputs"]["status"] == "FAILED"
    assert str(MAX_FILES) in (steps["parse_inputs"]["error"] or "")

    # Rejected up front: the batch never reached template parsing.
    artifacts = {artifact["artifact_id"] for artifact in engine.store.list_artifacts()}
    assert "template_spec" not in artifacts


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(
        config,
        "PROVIDERS",
        {
            "llm": {"kind": "openai_compatible", "enabled": False, "api_key_env": "PEBS_LLM_API_KEY"},
            "research": {"enabled": False},
        },
    )
    server_mod._engines.clear()
    return TestClient(server_mod.app)


def test_api_build_rejects_count_violation_with_400(client, tmp_path):
    files = [_sized(tmp_path / f"m{index}.bin", 1) for index in range(MAX_FILES + 1)]
    response = client.post(
        "/api/projects/limitproj/build",
        json={"request": REQUEST_2, "material_paths": [str(path) for path in files]},
    )
    assert response.status_code == 400
    assert str(MAX_FILES) in response.json()["detail"]


def test_api_build_rejects_oversized_material_with_413(client, tmp_path):
    oversized = _sized(tmp_path / "huge.bin", MAX_FILE_BYTES + 1)
    response = client.post(
        "/api/projects/limitproj/build",
        json={"request": REQUEST_2, "material_paths": [str(oversized)]},
    )
    assert response.status_code == 413
    assert "huge.bin" in response.json()["detail"]


def test_api_upload_rejects_oversized_file_and_stores_nothing(client, tmp_path):
    payload = io.BytesIO(b"\0" * (MAX_FILE_BYTES + 1))
    response = client.post(
        "/api/projects/limitproj/upload",
        files={"file": ("big.bin", payload, "application/octet-stream")},
    )
    assert response.status_code == 413
    assert "big.bin" in response.json()["detail"]
    # The refused upload must not leave a truncated artifact behind.
    inputs = tmp_path / "projects" / "limitproj" / "inputs"
    assert list(inputs.glob("*")) == []
