"""Tests for fixop.firewall module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fixop.firewall import check_ufw_forward_policy, check_nat_masquerade
from fixop.models import Category, HostContext
from fixop.ssh import RemoteResult


@pytest.fixture
def ctx():
    return HostContext(host="test.example.com", user="root")


class TestCheckUfwForwardPolicy:
    def test_ufw_not_installed(self, ctx):
        with patch("fixop.firewall.run_remote") as mock:
            mock.return_value = RemoteResult(0, "INACTIVE", "")
            issues = check_ufw_forward_policy(ctx)
            assert len(issues) == 0

    def test_ufw_inactive(self, ctx):
        with patch("fixop.firewall.run_remote") as mock:
            mock.return_value = RemoteResult(0, "Status: inactive", "")
            issues = check_ufw_forward_policy(ctx)
            assert len(issues) == 0

    def test_ufw_forward_accept(self, ctx):
        with patch("fixop.firewall.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "Status: active", ""),
                RemoteResult(0, 'DEFAULT_FORWARD_POLICY="ACCEPT"', ""),
            ]
            issues = check_ufw_forward_policy(ctx)
            assert len(issues) == 0

    def test_ufw_forward_drop(self, ctx):
        with patch("fixop.firewall.run_remote") as mock:
            mock.side_effect = [
                RemoteResult(0, "Status: active\nTo Action From\n22 ALLOW Anywhere", ""),
                RemoteResult(0, 'DEFAULT_FORWARD_POLICY="DROP"', ""),
            ]
            issues = check_ufw_forward_policy(ctx)
            assert len(issues) == 1
            assert issues[0].category == Category.FIREWALL
            assert "DROP" in issues[0].message


class TestCheckNatMasquerade:
    def test_masquerade_exists(self, ctx):
        with patch("fixop.firewall.run_remote") as mock:
            mock.return_value = RemoteResult(0, "MASQUERADE  all  --  10.88.0.0/16  0.0.0.0/0", "")
            issues = check_nat_masquerade(ctx)
            assert len(issues) == 0

    def test_masquerade_missing(self, ctx):
        with patch("fixop.firewall.run_remote") as mock:
            mock.return_value = RemoteResult(1, "", "")
            issues = check_nat_masquerade(ctx)
            assert len(issues) == 1
            assert issues[0].category == Category.FIREWALL
            assert issues[0].fix_command is not None
