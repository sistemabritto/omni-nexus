"""Regression tests — only github:/https: sources are accepted.

Local filesystem paths, file://, ssh://, and other schemes must be rejected
by resolve_source and resolve_source_with_sha with a ValueError. This closes
the doc/code mismatch from the Plugins v1 review — the SKILL.md promised
rejection, the code accepted anything.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from plugin_loader import PluginInstaller  # noqa: E402


REJECTED_SOURCES = [
    "/etc",
    "/etc/passwd",
    "/root/.ssh/id_rsa",
    "/Users/someone/projects/plugin",
    "./relative/path",
    "../escape",
    "~/plugin",
    "file:///etc/passwd",
    "ssh://git@github.com/owner/repo",
    "git@github.com:owner/repo.git",
    "",
    "plugin.yaml",
]


@pytest.mark.parametrize("source", REJECTED_SOURCES)
def test_resolve_source_rejects_non_http(source):
    with pytest.raises(ValueError):
        PluginInstaller.resolve_source(source)


@pytest.mark.parametrize("source", REJECTED_SOURCES)
def test_resolve_source_with_sha_rejects_non_http(source):
    with pytest.raises(ValueError):
        PluginInstaller().resolve_source_with_sha(source)


def test_resolve_source_rejects_github_without_slash():
    with pytest.raises(ValueError):
        PluginInstaller.resolve_source("github:owneronly")


# ---------------------------------------------------------------------------
# Upload flow regression (Wave 2.5): preview() must accept a path already
# staged under STAGING_DIR (the upload endpoint returns that exact path).
# ---------------------------------------------------------------------------


def test_resolve_source_with_sha_accepts_staged_upload(tmp_path):
    """A path under STAGING_DIR (uploaded archive) must resolve without SHA."""
    import plugin_loader
    staged_root = tmp_path / "plugins" / ".staging"
    staged = staged_root / "upload-1234-abcd" / "reach"
    staged.mkdir(parents=True)
    (staged / "plugin.yaml").write_text("id: reach\n", encoding="utf-8")

    with patch.object(plugin_loader, "STAGING_DIR", staged_root):
        path, sha = PluginInstaller().resolve_source_with_sha(str(staged))

    assert path.resolve() == staged.resolve()
    assert sha == ""


def test_resolve_source_with_sha_still_rejects_other_local_paths(tmp_path):
    """Arbitrary local dirs outside STAGING_DIR must still be rejected."""
    import plugin_loader
    outside = tmp_path / "somewhere" / "plugin"
    outside.mkdir(parents=True)
    (outside / "plugin.yaml").write_text("id: x\n", encoding="utf-8")

    with patch.object(plugin_loader, "STAGING_DIR", tmp_path / "plugins" / ".staging"):
        with pytest.raises(ValueError):
            PluginInstaller().resolve_source_with_sha(str(outside))
