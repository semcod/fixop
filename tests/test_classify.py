"""Tests for fixop.classify module."""

from __future__ import annotations

import pytest

from fixop.classify import (
    classify_error,
    get_tip_for_failure,
    extract_missing_binary,
    EXIT_CODE_MAP,
    STDERR_PATTERNS,
)
from fixop.models import Category, Severity


class TestClassifyError:
    def test_exit_code_137_oom(self):
        issue = classify_error(137, "", "podman run app")
        assert issue.category == Category.CONTAINER
        assert issue.severity == Severity.CRITICAL
        assert "OOM" in issue.message or "killed" in issue.message.lower()

    def test_exit_code_255_ssh(self):
        issue = classify_error(255, "", "ssh root@server")
        assert issue.category == Category.SSH

    def test_exit_code_127_not_found(self):
        issue = classify_error(127, "", "foobar --version")
        assert issue.category == Category.DEPLOY
        assert "not found" in issue.message.lower()

    def test_stderr_dns_timeout(self):
        issue = classify_error(1, "lookup acme-v02.api.letsencrypt.org on 10.89.0.1:53: i/o timeout", "")
        assert issue.category == Category.DNS
        assert issue.severity == Severity.CRITICAL

    def test_stderr_connection_refused(self):
        issue = classify_error(1, "dial tcp 10.0.0.1:5432: connection refused", "")
        assert issue.category == Category.FIREWALL

    def test_stderr_port_conflict(self):
        issue = classify_error(1, "Error: address already in use :8080", "")
        assert issue.category == Category.PORT

    def test_stderr_self_signed(self):
        issue = classify_error(1, "x509: self-signed certificate in chain", "")
        assert issue.category == Category.TLS

    def test_stderr_no_such_image(self):
        issue = classify_error(1, "Error: no such image: myapp:latest", "")
        assert issue.category == Category.CONTAINER

    def test_stderr_takes_priority_over_exit_code(self):
        # Even with exit code 1 (CONTAINER), stderr pattern for DNS should win
        issue = classify_error(1, "lookup foo on 10.89.0.1:53: i/o timeout", "")
        assert issue.category == Category.DNS

    def test_unknown_error(self):
        issue = classify_error(42, "something weird happened", "my_cmd")
        assert issue.category == Category.CONTAINER
        assert issue.severity == Severity.ERROR


class TestGetTipForFailure:
    def test_ssh_exit_255(self):
        tip = get_tip_for_failure("ssh root@server 'deploy'", 255)
        assert tip is not None
        assert "SSH" in tip

    def test_scp_exit_1(self):
        tip = get_tip_for_failure("scp deploy/app.container root@server:/etc/", 1)
        assert tip is not None
        assert "Missing files" in tip or "deploy" in tip.lower()

    def test_exit_126_permission(self):
        tip = get_tip_for_failure("./scripts/deploy.sh", 126)
        assert tip is not None
        assert "chmod" in tip

    def test_exit_127_not_found(self):
        tip = get_tip_for_failure("foobar --version", 127)
        assert tip is not None
        assert "not found" in tip.lower()

    def test_no_tip(self):
        tip = get_tip_for_failure("echo hello", 0)
        assert tip is None


class TestExtractMissingBinary:
    def test_bash_style(self):
        assert extract_missing_binary("bash: foobar: command not found") == "foobar"

    def test_generic_style(self):
        assert extract_missing_binary("foobar: command not found") == "foobar"

    def test_no_match(self):
        assert extract_missing_binary("some random error") == "unknown"


class TestDispatchTables:
    def test_exit_code_map_coverage(self):
        """All mapped exit codes should produce valid category."""
        for code, (cat, msg, sev) in EXIT_CODE_MAP.items():
            assert isinstance(cat, Category)
            assert isinstance(sev, Severity)
            assert len(msg) > 0

    def test_stderr_patterns_compile(self):
        """All stderr patterns should be valid regex."""
        import re
        for pattern, cat, msg, sev in STDERR_PATTERNS:
            compiled = re.compile(pattern, re.IGNORECASE)
            assert compiled is not None
