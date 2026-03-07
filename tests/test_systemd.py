"""Tests for fixop.systemd module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fixop.systemd import check_unit_status, check_quadlet_loaded, daemon_reload
from fixop.models import Category, HostContext, Severity
from fixop.ssh import RemoteResult


@pytest.fixture
def ctx():
    return HostContext(host="test.example.com", user="root")


class TestCheckUnitStatus:
    def test_all_active(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.return_value = RemoteResult(0, "active", "")
            issues = check_unit_status(ctx, ["traefik", "web"])
            assert len(issues) == 0

    def test_inactive_unit(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "active", ""),
                RemoteResult(3, "inactive", ""),
            ]
            issues = check_unit_status(ctx, ["traefik", "web"])
            assert len(issues) == 1
            assert "inactive" in issues[0].message
            assert issues[0].fix_command == "systemctl start web"

    def test_failed_unit(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(3, "failed", ""),
                RemoteResult(0, "some journal output", ""),
            ]
            issues = check_unit_status(ctx, ["web"])
            assert len(issues) == 1
            assert issues[0].severity == Severity.ERROR


class TestCheckQuadletLoaded:
    def test_quadlet_found_and_loaded(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "/etc/containers/systemd/web.container", ""),
                RemoteResult(0, "[Unit]\nDescription=...", ""),
            ]
            issues = check_quadlet_loaded(ctx, ["web"])
            assert len(issues) == 0

    def test_quadlet_missing(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.return_value = RemoteResult(1, "", "")
            issues = check_quadlet_loaded(ctx, ["web"])
            assert len(issues) == 1
            assert "not found" in issues[0].message


class TestDaemonReload:
    def test_success(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.return_value = RemoteResult(0, "", "")
            result = daemon_reload(ctx)
            assert result.success is True

    def test_failure(self, ctx):
        with patch("fixop.systemd.run_remote") as mock:
            mock.return_value = RemoteResult(1, "", "Permission denied")
            result = daemon_reload(ctx)
            assert result.success is False
