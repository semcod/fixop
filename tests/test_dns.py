"""Tests for fixop.dns module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fixop.dns import (
    check_host_dns,
    check_container_dns,
    check_systemd_resolved,
    generate_container_resolv_conf,
)
from fixop.models import Category, HostContext, Severity
from fixop.ssh import RemoteResult


@pytest.fixture
def ctx():
    return HostContext(host="test.example.com", user="root")


class TestCheckHostDns:
    def test_healthy_dns(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.return_value = RemoteResult(0, "Server: 8.8.8.8\nAddress: 1.2.3.4\n", "")
            issues = check_host_dns(ctx)
            assert len(issues) == 0

    def test_broken_dns_nxdomain(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "** server can't find: NXDOMAIN", ""),
                RemoteResult(0, "nameserver 127.0.0.53", ""),
            ]
            issues = check_host_dns(ctx)
            assert len(issues) == 1
            assert issues[0].category == Category.DNS
            assert issues[0].severity == Severity.CRITICAL

    def test_dns_timeout(self, ctx):
        import subprocess

        with patch("fixop.dns.run_remote") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=15)
            issues = check_host_dns(ctx)
            assert len(issues) == 1
            assert "timed out" in issues[0].message.lower()


class TestCheckContainerDns:
    def test_container_not_running(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.return_value = RemoteResult(1, "", "")
            issues = check_container_dns(ctx, container="traefik")
            assert len(issues) == 0

    def test_host_network_skip(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "true", ""),  # container running
                RemoteResult(0, "host", ""),  # host network
            ]
            issues = check_container_dns(ctx, container="traefik")
            assert len(issues) == 0

    def test_broken_container_dns(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "true", ""),  # container running
                RemoteResult(0, "bridge", ""),  # bridge network
                RemoteResult(1, "timed out", ""),  # DNS fails
            ]
            issues = check_container_dns(ctx, container="traefik")
            assert len(issues) == 1
            assert issues[0].severity == Severity.CRITICAL
            assert "ACME" in issues[0].message


class TestCheckSystemdResolved:
    def test_not_active(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.return_value = RemoteResult(3, "inactive", "")
            issues = check_systemd_resolved(ctx)
            assert len(issues) == 0

    def test_active_and_working(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "active", ""),
                RemoteResult(0, "google.com: 142.250.x.x", ""),
            ]
            issues = check_systemd_resolved(ctx)
            assert len(issues) == 0

    def test_active_but_broken(self, ctx):
        with patch("fixop.dns.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "active", ""),
                RemoteResult(1, "no appropriate query", ""),
            ]
            issues = check_systemd_resolved(ctx)
            assert len(issues) == 1
            assert issues[0].severity == Severity.WARNING


class TestGenerateContainerResolvConf:
    def test_default_nameservers(self, tmp_path):
        path = str(tmp_path / "resolv.conf")
        result = generate_container_resolv_conf(path)
        assert result == path
        content = open(path).read()
        assert "8.8.8.8" in content
        assert "1.1.1.1" in content

    def test_custom_nameservers(self, tmp_path):
        path = str(tmp_path / "resolv.conf")
        generate_container_resolv_conf(path, nameservers=["9.9.9.9"])
        content = open(path).read()
        assert "9.9.9.9" in content
        assert "8.8.8.8" not in content
