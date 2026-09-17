from __future__ import annotations

import pytest

from pebs.permissions import PermissionDenied, PermissionManager


@pytest.fixture
def permissions():
    return PermissionManager()


def test_unknown_and_unapproved_skills_are_denied(permissions):
    with pytest.raises(PermissionDenied):
        permissions.skill("does-not-exist")
    with pytest.raises(PermissionDenied):
        permissions.skill("skills-mgr")


def test_approved_skill_passes(permissions):
    record = permissions.skill("script-writer")
    assert record["status"] == "APPROVED"
    assert record["runtime"] == "builtin"
    exporter = permissions.skill("docx-exporter")
    assert exporter["execution_policy"] == "TRUSTED_RUNNER"


def test_external_write_actions_are_denied_in_m1(permissions):
    for action in ["cnki_download", "zotero_write", "publish", "email", "git_push"]:
        with pytest.raises(PermissionDenied):
            permissions.external_action(action)


def test_provider_must_be_allowed_for_skill(permissions):
    permissions.provider("script-writer", "default-llm")
    with pytest.raises(PermissionDenied):
        permissions.provider("template-parser", "default-llm")
    with pytest.raises(PermissionDenied):
        permissions.tool("shell_exec")
