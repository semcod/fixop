"""Port conflict detection and resolution.

Covers:
- Check if a port is free
- Find alternative free port
- Identify process using a port
- Detect Docker/Podman processes on ports

Extracted from: taskfile/diagnostics/checks_ports.py (pure logic, no taskfile deps)
"""

from __future__ import annotations

import socket
import subprocess

from .models import Category, FixStrategy, Issue, Severity


def is_port_free(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a TCP port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
        return True
    except OSError:
        return False


def find_free_port_near(start: int, span: int = 50) -> int | None:
    """Find a free port near the given port number.

    Searches forward from start, then backward to 1024.
    Returns None if no free port is found.
    """
    for p in range(start, start + span + 1):
        if is_port_free(p):
            return p
    for p in range(max(1024, start - span), start):
        if is_port_free(p):
            return p
    return None


def who_uses_port(port: int) -> tuple[int | None, str | None]:
    """Find PID and process name using a port.

    Returns (pid, process_name) or (None, None).
    """
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split("\n")[0])
            ps = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True, text=True, timeout=5,
            )
            name = ps.stdout.strip() if ps.returncode == 0 else None
            return pid, name
    except Exception:
        pass
    return None, None


def is_container_process(process_name: str | None) -> bool:
    """Check if a process name belongs to a container runtime."""
    if not process_name:
        return False
    return any(x in process_name.lower() for x in ("docker", "containerd", "podman"))


def check_port(port: int) -> list[Issue]:
    """Check if a single port is free. Returns issues if occupied."""
    issues: list[Issue] = []

    if is_port_free(port):
        return issues

    pid, process = who_uses_port(port)
    msg = f"Port {port} is in use"
    if process:
        msg += f" by '{process}' (pid {pid})"

    fix_cmd = None
    if process and is_container_process(process):
        fix_cmd = f"docker stop {process}"

    suggested = find_free_port_near(port)
    details = f"Suggested alternative: {suggested}" if suggested else None

    issues.append(Issue(
        category=Category.PORT,
        severity=Severity.WARNING,
        message=msg,
        fix_strategy=FixStrategy.CONFIRM if fix_cmd else FixStrategy.MANUAL,
        fix_command=fix_cmd,
        details=details,
    ))

    return issues


def check_ports(ports: list[int]) -> list[Issue]:
    """Check if multiple ports are free."""
    issues: list[Issue] = []
    for port in ports:
        issues.extend(check_port(port))
    return issues
