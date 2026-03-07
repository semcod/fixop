"""Remote command transport — execute commands on remote hosts via SSH.

Decoupled from ssh.py checks so that domain modules (dns, firewall, containers,
systemd, tls) depend on this lightweight transport module instead of the full
ssh module.  This eliminates ssh.py as a hub (fan-in was 7 → now 1).

Extracted from: fixop/ssh.py
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .models import HostContext


@dataclass
class RemoteResult:
    """Result of a remote command execution."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Combined stdout + stderr (backward compat)."""
        return (self.stdout + self.stderr).strip()


def run_remote(
    ctx: HostContext,
    command: str,
    timeout: int | None = None,
) -> RemoteResult:
    """Execute a command on a remote host via SSH.

    Args:
        ctx: SSH connection context.
        command: Shell command to execute remotely.
        timeout: Override default timeout (seconds).

    Returns:
        RemoteResult with returncode, stdout, stderr.

    Raises:
        subprocess.TimeoutExpired: if command exceeds timeout.
    """
    effective_timeout = timeout or (ctx.timeout + 20)
    cmd = ctx.ssh_cmd + [command]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
        return RemoteResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired:
        raise
    except Exception as e:
        return RemoteResult(returncode=-1, stdout="", stderr=str(e))


def test_ssh_connection(
    ctx: HostContext,
    timeout: int = 10,
) -> RemoteResult:
    """Quick SSH connectivity test — runs 'echo ok' on remote."""
    cmd = [
        "ssh",
        "-o", f"ConnectTimeout={min(timeout, ctx.timeout)}",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", str(ctx.port),
        f"{ctx.user}@{ctx.host}",
        "echo ok",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 5,
        )
        return RemoteResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return RemoteResult(returncode=-1, stdout="", stderr="Connection timeout")
    except Exception as e:
        return RemoteResult(returncode=-1, stdout="", stderr=str(e))
