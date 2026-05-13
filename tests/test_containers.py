"""Tests for fixop.containers module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fixop.containers import (
    check_runtime,
    check_containers_running,
    check_disk_usage,
    check_memory,
)
from fixop.models import Category, HostContext, Severity
from fixop.ssh import RemoteResult


@pytest.fixture
def ctx():
    return HostContext(host="test.example.com", user="root")


class TestCheckRuntime:
    def test_podman_installed(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "podman version 4.9.3", "")
            issues = check_runtime(ctx)
            assert len(issues) == 0

    def test_podman_not_installed(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "NOT_FOUND", "")
            issues = check_runtime(ctx)
            assert len(issues) == 1
            assert issues[0].category == Category.CONTAINER


class TestCheckContainersRunning:
    def test_all_running(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "traefik\nweb\nlanding\n", "")
            issues = check_containers_running(ctx, expected=["traefik", "web"])
            assert len(issues) == 0

    def test_missing_container(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "traefik\n", ""),  # ps
                RemoteResult(1, "", ""),  # ps -a for 'web'
            ]
            issues = check_containers_running(ctx, expected=["traefik", "web"])
            assert len(issues) == 1
            assert "web" in issues[0].message

    def test_no_expected(self, ctx):
        issues = check_containers_running(ctx, expected=None)
        assert len(issues) == 0


class TestCheckDiskUsage:
    def test_enough_disk(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "15000M", "")
            issues = check_disk_usage(ctx)
            assert len(issues) == 0

    def test_low_disk(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "300", "")
            issues = check_disk_usage(ctx)
            assert len(issues) == 1
            assert issues[0].severity == Severity.WARNING

    def test_critical_disk(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "50", "")
            issues = check_disk_usage(ctx)
            assert len(issues) == 1
            assert issues[0].severity == Severity.CRITICAL


class TestCheckMemory:
    def test_normal_memory(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "1024 4096", "")
            issues = check_memory(ctx)
            assert len(issues) == 0

    def test_high_memory(self, ctx):
        with patch("fixop.containers.run_remote") as mock:
            mock.return_value = RemoteResult(0, "3800 4096", "")
            issues = check_memory(ctx)
            assert len(issues) == 1
            assert issues[0].severity == Severity.WARNING
