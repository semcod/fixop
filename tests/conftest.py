"""Shared test fixtures for fixop tests.

Provides SSH mock fixtures so tests don't require actual remote hosts.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fixop.models import HostContext


@pytest.fixture
def ctx():
    """Default test HostContext."""
    return HostContext(host="test.example.com", user="root", port=22, key="~/.ssh/id_ed25519")


@pytest.fixture
def mock_run_remote():
    """Mock run_remote to return configurable RemoteResult.

    Usage:
        def test_something(mock_run_remote):
            mock_run_remote.return_value = RemoteResult(0, "output", "")
            # ... test code that calls run_remote()
    """
    with patch("fixop.ssh.subprocess.run") as mock_run:

        def _make_result(returncode=0, stdout="", stderr=""):
            result = MagicMock()
            result.returncode = returncode
            result.stdout = stdout
            result.stderr = stderr
            return result

        mock_run.side_effect = lambda *a, **kw: _make_result()
        mock_run._make_result = _make_result
        yield mock_run


@pytest.fixture
def tmp_deploy_dir(tmp_path):
    """Create a temporary deploy directory with sample files."""
    deploy = tmp_path / "deploy"
    deploy.mkdir()

    # Valid YAML
    (deploy / "traefik.yml").write_text("entryPoints:\n  web:\n    address: ':80'\n")

    # YAML with unresolved vars
    (deploy / "web.container").write_text(
        "[Container]\nImage=${REGISTRY}/web:${VERSION}\nEnvironment=DB_HOST=${DB_HOST}\n"
    )

    # File with placeholders
    (deploy / "config.yml").write_text("domain: your-domain.example.com\nemail: changeme@example.com\n")

    return deploy
