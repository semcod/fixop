"""HTTP/TCP endpoint health checks.

Covers:
- HTTP endpoint health (status code, response time)
- SSH service availability
- TCP port connectivity

Extracted from: taskfile/health.py (check_http_endpoint, check_ssh_service)
Uses only stdlib: urllib, socket, subprocess — zero external dependencies.
"""

from __future__ import annotations

import socket
import subprocess
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import HostContext


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    url: str
    status: str  # "healthy", "unhealthy", "unknown"
    status_code: int | None = None
    response_time_ms: float = 0.0
    error: str | None = None


@dataclass
class HealthReport:
    """Aggregated health check report."""

    overall: str  # "healthy", "degraded", "unhealthy"
    checks: list[HealthCheckResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "healthy")

    @property
    def unhealthy_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "unhealthy")


def check_http_endpoint(
    name: str,
    url: str,
    expected_status: int = 200,
    timeout: int = 10,
    retries: int = 1,
) -> HealthCheckResult:
    """Check HTTP endpoint health.

    Args:
        name: Service name for display.
        url: URL to check.
        expected_status: Expected HTTP status code.
        timeout: Request timeout in seconds.
        retries: Number of retry attempts.
    """
    start = time.time()

    for attempt in range(retries):
        try:
            req = Request(url, method="GET", headers={"User-Agent": "fixop-health/1.0"})
            response = urlopen(req, timeout=timeout)

            status_code = response.getcode()
            if status_code == expected_status:
                return HealthCheckResult(
                    name=name,
                    url=url,
                    status="healthy",
                    status_code=status_code,
                    response_time_ms=(time.time() - start) * 1000,
                )
            if attempt == retries - 1:
                return _unhealthy(name, url, start, f"Unexpected status: {status_code}", status_code)
            time.sleep(1)

        except HTTPError as e:
            if attempt == retries - 1:
                return _unhealthy(name, url, start, f"HTTP error: {e.code}", e.code)
            time.sleep(1)

        except URLError as e:
            if attempt == retries - 1:
                reason = str(e.reason) if hasattr(e, "reason") else str(e)
                return _unhealthy(name, url, start, f"Connection error: {reason[:50]}")
            time.sleep(1)

        except Exception as e:
            if attempt == retries - 1:
                return _unhealthy(name, url, start, f"Error: {str(e)[:50]}")
            time.sleep(1)

    return HealthCheckResult(name=name, url=url, status="unknown", error="Unknown error")


def check_ssh_service(
    name: str,
    host: str,
    user: str,
    ssh_key: str | None = None,
    port: int = 22,
    timeout: int = 10,
) -> HealthCheckResult:
    """Check SSH service availability.

    Args:
        name: Service name for display.
        host: SSH host.
        user: SSH user.
        ssh_key: Path to SSH private key.
        port: SSH port.
        timeout: Connection timeout.
    """
    start = time.time()

    cmd = ["ssh", "-p", str(port)]
    if ssh_key:
        cmd += ["-i", ssh_key]
    cmd += [
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "BatchMode=yes",
        f"{user}@{host}",
        "echo healthy",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = (time.time() - start) * 1000

        if result.returncode == 0 and "healthy" in result.stdout:
            return HealthCheckResult(
                name=name,
                url=f"ssh://{user}@{host}:{port}",
                status="healthy",
                response_time_ms=elapsed,
            )
        else:
            return HealthCheckResult(
                name=name,
                url=f"ssh://{user}@{host}:{port}",
                status="unhealthy",
                response_time_ms=elapsed,
                error=f"SSH failed: {result.stderr[:100]}",
            )
    except subprocess.TimeoutExpired:
        elapsed = (time.time() - start) * 1000
        return HealthCheckResult(
            name=name,
            url=f"ssh://{user}@{host}:{port}",
            status="unhealthy",
            response_time_ms=elapsed,
            error="SSH connection timeout",
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return HealthCheckResult(
            name=name,
            url=f"ssh://{user}@{host}:{port}",
            status="unhealthy",
            response_time_ms=elapsed,
            error=f"SSH error: {str(e)[:50]}",
        )


def check_tcp_port(host: str, port: int, timeout: int = 5) -> HealthCheckResult:
    """Check if a TCP port is reachable."""
    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.time() - start) * 1000
            return HealthCheckResult(
                name=f"TCP {host}:{port}",
                url=f"tcp://{host}:{port}",
                status="healthy",
                response_time_ms=elapsed,
            )
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        elapsed = (time.time() - start) * 1000
        return HealthCheckResult(
            name=f"TCP {host}:{port}",
            url=f"tcp://{host}:{port}",
            status="unhealthy",
            response_time_ms=elapsed,
            error=str(e)[:80],
        )


def run_health_checks(
    ctx: HostContext,
    domains: list[str] | None = None,
    check_ssh: bool = True,
) -> HealthReport:
    """Run comprehensive health checks.

    Args:
        ctx: SSH connection context.
        domains: Domains to check HTTPS endpoints for.
        check_ssh: Whether to check SSH connectivity.
    """
    checks: list[HealthCheckResult] = []

    if check_ssh:
        checks.append(check_ssh_service("SSH", ctx.host, ctx.user, ctx.key, ctx.port))

    for domain in domains or []:
        checks.append(check_http_endpoint(domain, f"https://{domain}"))

    unhealthy = sum(1 for c in checks if c.status == "unhealthy")
    healthy = sum(1 for c in checks if c.status == "healthy")

    if unhealthy == 0:
        overall = "healthy"
    elif healthy > unhealthy:
        overall = "degraded"
    else:
        overall = "unhealthy"

    return HealthReport(overall=overall, checks=checks)


def _unhealthy(name: str, url: str, start: float, error: str, status_code: int | None = None) -> HealthCheckResult:
    return HealthCheckResult(
        name=name,
        url=url,
        status="unhealthy",
        status_code=status_code,
        response_time_ms=(time.time() - start) * 1000,
        error=error,
    )
