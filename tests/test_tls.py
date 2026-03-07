"""Tests for fixop.tls module."""

from __future__ import annotations

import socket
import ssl
from unittest.mock import patch, MagicMock

import pytest

from fixop.tls import check_certificate, check_certificates
from fixop.models import Category, Severity


class TestCheckCertificate:
    def test_valid_certificate(self):
        mock_cert = {
            "notAfter": "Dec 31 23:59:59 2030 GMT",
            "issuer": ((("commonName", "Let's Encrypt"),),),
            "subject": ((("commonName", "example.com"),),),
        }
        with patch("fixop.tls.socket.create_connection") as mock_conn, \
             patch("fixop.tls.ssl.create_default_context") as mock_ctx:
            mock_ssock = MagicMock()
            mock_ssock.getpeercert.return_value = mock_cert
            mock_ctx_inst = MagicMock()
            mock_ctx.return_value = mock_ctx_inst
            mock_ctx_inst.wrap_socket.return_value.__enter__ = lambda s: mock_ssock
            mock_ctx_inst.wrap_socket.return_value.__exit__ = lambda s, *a: None
            mock_conn.return_value.__enter__ = lambda s: MagicMock()
            mock_conn.return_value.__exit__ = lambda s, *a: None

            issues = check_certificate("example.com")
            assert len(issues) == 0

    def test_self_signed_certificate(self):
        mock_cert = {
            "notAfter": "Dec 31 23:59:59 2030 GMT",
            "issuer": ((("commonName", "example.com"),),),
            "subject": ((("commonName", "example.com"),),),
        }
        with patch("fixop.tls.socket.create_connection") as mock_conn, \
             patch("fixop.tls.ssl.create_default_context") as mock_ctx:
            mock_ssock = MagicMock()
            mock_ssock.getpeercert.return_value = mock_cert
            mock_ctx_inst = MagicMock()
            mock_ctx.return_value = mock_ctx_inst
            mock_ctx_inst.wrap_socket.return_value.__enter__ = lambda s: mock_ssock
            mock_ctx_inst.wrap_socket.return_value.__exit__ = lambda s, *a: None
            mock_conn.return_value.__enter__ = lambda s: MagicMock()
            mock_conn.return_value.__exit__ = lambda s, *a: None

            issues = check_certificate("example.com")
            assert any("Self-signed" in i.message for i in issues)

    def test_connection_refused(self):
        with patch("fixop.tls.socket.create_connection") as mock_conn, \
             patch("fixop.tls.ssl.create_default_context"):
            mock_conn.side_effect = ConnectionRefusedError("Connection refused")
            issues = check_certificate("example.com")
            assert len(issues) == 1
            assert issues[0].severity == Severity.ERROR
            assert "refused" in issues[0].message.lower()

    def test_timeout(self):
        with patch("fixop.tls.socket.create_connection") as mock_conn, \
             patch("fixop.tls.ssl.create_default_context"):
            mock_conn.side_effect = socket.timeout("timed out")
            issues = check_certificate("example.com")
            assert len(issues) == 1
            assert "timed out" in issues[0].message.lower()


class TestCheckCertificates:
    def test_multiple_domains(self):
        with patch("fixop.tls.check_certificate") as mock_check:
            mock_check.return_value = []
            issues = check_certificates(["a.com", "b.com", "c.com"])
            assert mock_check.call_count == 3
