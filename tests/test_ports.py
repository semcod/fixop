"""Tests for fixop.ports module."""

from __future__ import annotations

from unittest.mock import patch


from fixop.ports import is_port_free, find_free_port_near, is_container_process, check_port
from fixop.models import Category


class TestIsPortFree:
    def test_free_port(self):
        with patch("fixop.ports.socket.socket") as mock_sock:
            mock_inst = mock_sock.return_value.__enter__.return_value
            mock_inst.bind.return_value = None
            assert is_port_free(9999) is True

    def test_occupied_port(self):
        with patch("fixop.ports.socket.socket") as mock_sock:
            mock_inst = mock_sock.return_value.__enter__.return_value
            mock_inst.bind.side_effect = OSError("Address in use")
            assert is_port_free(80) is False


class TestFindFreePortNear:
    def test_finds_same_port(self):
        with patch("fixop.ports.is_port_free") as mock:
            mock.return_value = True
            result = find_free_port_near(8080)
            assert result == 8080

    def test_finds_next_port(self):
        with patch("fixop.ports.is_port_free") as mock:
            mock.side_effect = lambda p: p != 8080
            result = find_free_port_near(8080)
            assert result == 8081

    def test_no_free_port(self):
        with patch("fixop.ports.is_port_free") as mock:
            mock.return_value = False
            result = find_free_port_near(8080, span=2)
            assert result is None


class TestIsContainerProcess:
    def test_docker(self):
        assert is_container_process("docker-proxy") is True

    def test_podman(self):
        assert is_container_process("podman") is True

    def test_nginx(self):
        assert is_container_process("nginx") is False

    def test_none(self):
        assert is_container_process(None) is False


class TestCheckPort:
    def test_free_port(self):
        with patch("fixop.ports.is_port_free", return_value=True):
            issues = check_port(8080)
            assert len(issues) == 0

    def test_occupied_port(self):
        with (
            patch("fixop.ports.is_port_free", return_value=False),
            patch("fixop.ports.who_uses_port", return_value=(1234, "nginx")),
            patch("fixop.ports.find_free_port_near", return_value=8081),
        ):
            issues = check_port(8080)
            assert len(issues) == 1
            assert issues[0].category == Category.PORT
            assert "nginx" in issues[0].message
