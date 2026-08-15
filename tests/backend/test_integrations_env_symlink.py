"""Regression test: _upsert_env_vars must write through symlinks.

The .env path used by the custom-integrations API is /workspace/.env, which
entrypoint.sh creates as a symlink to /workspace/config/.env (a persistent
volume). If the upsert writes via os.replace() directly on the symlink, it
swaps the link for a regular file and values land in the container's
ephemeral layer — lost on the next redeploy.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dashboard.backend.routes.integrations import _upsert_env_vars  # noqa: E402


def test_upsert_preserves_symlink_and_writes_through_to_target(tmp_path):
    target = tmp_path / "config" / "env"
    target.parent.mkdir()
    target.write_text("EXISTING=keep\n", encoding="utf-8")

    link = tmp_path / ".env"
    link.symlink_to(target)

    _upsert_env_vars(link, {"GROQ_API_KEY": "gsk_test123"}, section_comment="custom-int-groq")

    assert link.is_symlink(), "symlink must be preserved (not replaced by os.replace)"
    assert os.path.realpath(link) == str(target)

    content = target.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=\"gsk_test123\"\n" in content
    assert "EXISTING=keep\n" in content


def test_upsert_updates_existing_value_through_symlink(tmp_path):
    target = tmp_path / "config" / "env"
    target.parent.mkdir()
    target.write_text('GROQ_API_KEY="gsk_old"\n', encoding="utf-8")

    link = tmp_path / ".env"
    link.symlink_to(target)

    _upsert_env_vars(link, {"GROQ_API_KEY": "gsk_new"})

    assert link.is_symlink()
    content = target.read_text(encoding="utf-8")
    assert 'GROQ_API_KEY="gsk_new"\n' in content
    assert "gsk_old" not in content
