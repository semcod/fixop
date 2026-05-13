"""Container runtime diagnostics — Podman/Docker health checks.

Covers:
- Runtime availability (podman/docker installed)
- Container status (running, stopped, missing)
- Disk usage on remote host
- Memory usage on remote host

Extracted from: taskfile/diagnostics/checks_ssh.py (check_remote_health),
               taskfile/diagnostics/checks.py (check_docker),
               taskfile/deploy_utils.py (check_remote_podman, check_remote_disk)
"""

from __future__ import annotations

from .models import Category, FixStrategy, HostContext, Issue, Severity
from .transport import run_remote


def check_runtime(ctx: HostContext, runtime: str = "podman") -> list[Issue]:
    """Check if container runtime (podman/docker) is installed on remote host."""
    issues: list[Issue] = []

    result = run_remote(ctx, f"{runtime} --version 2>/dev/null || echo NOT_FOUND")
    if "NOT_FOUND" in result.stdout or result.returncode != 0:
        issues.append(
            Issue(
                category=Category.CONTAINER,
                severity=Severity.WARNING,
                message=f"{runtime} not installed on {ctx.host}",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command=f"apt-get update -qq && apt-get install -y -qq {runtime}",
                details=f"Install {runtime} on the remote server to run containers.",
                host=ctx.host,
            )
        )

    return issues


def check_containers_running(
    ctx: HostContext,
    expected: list[str] | None = None,
    runtime: str = "podman",
) -> list[Issue]:
    """Check if expected containers are running.

    Args:
        ctx: SSH connection context.
        expected: List of container names that should be running.
        runtime: Container runtime (podman or docker).
    """
    issues: list[Issue] = []
    if not expected:
        return issues

    result = run_remote(ctx, f"{runtime} ps --format '{{{{.Names}}}}' 2>/dev/null")
    if result.returncode != 0:
        issues.append(
            Issue(
                category=Category.CONTAINER,
                severity=Severity.ERROR,
                message=f"Cannot list containers on {ctx.host} — {runtime} may not be running",
                host=ctx.host,
            )
        )
        return issues

    running = set(result.stdout.strip().splitlines())

    for name in expected:
        if name not in running:
            # Check if it exists but stopped
            check = run_remote(ctx, f"{runtime} ps -a --filter name=^{name}$ --format '{{{{.Status}}}}' 2>/dev/null")
            status_info = check.stdout.strip() if check.returncode == 0 else ""

            if status_info:
                issues.append(
                    Issue(
                        category=Category.CONTAINER,
                        severity=Severity.ERROR,
                        message=f"Container '{name}' exists but not running on {ctx.host}: {status_info}",
                        fix_strategy=FixStrategy.CONFIRM,
                        fix_command=f"{runtime} start {name}",
                        host=ctx.host,
                    )
                )
            else:
                issues.append(
                    Issue(
                        category=Category.CONTAINER,
                        severity=Severity.WARNING,
                        message=f"Container '{name}' not found on {ctx.host}",
                        fix_strategy=FixStrategy.MANUAL,
                        details=f"Deploy the container or check systemd unit: systemctl status {name}",
                        host=ctx.host,
                    )
                )

    return issues


def check_disk_usage(ctx: HostContext, warn_mb: int = 500) -> list[Issue]:
    """Check available disk space on remote host.

    Args:
        ctx: SSH connection context.
        warn_mb: Warn if free space is below this many MB.
    """
    issues: list[Issue] = []

    result = run_remote(ctx, "df -BM / | tail -1 | awk '{print $4}'")
    if result.returncode != 0:
        return issues

    disk_str = result.stdout.strip().rstrip("M")
    try:
        free_mb = int(disk_str)
    except ValueError:
        return issues

    if free_mb < 100:
        issues.append(
            Issue(
                category=Category.CONTAINER,
                severity=Severity.CRITICAL,
                message=f"Critical disk space on {ctx.host}: {free_mb}MB free",
                fix_strategy=FixStrategy.MANUAL,
                fix_command="podman system prune -af",
                details="Immediately free disk space — clean unused images and containers.",
                host=ctx.host,
            )
        )
    elif free_mb < warn_mb:
        issues.append(
            Issue(
                category=Category.CONTAINER,
                severity=Severity.WARNING,
                message=f"Low disk space on {ctx.host}: {free_mb}MB free",
                fix_strategy=FixStrategy.MANUAL,
                fix_command="podman system prune -af",
                details="Free disk space before deploying — clean unused images.",
                host=ctx.host,
            )
        )

    return issues


def check_memory(ctx: HostContext, warn_percent: int = 90) -> list[Issue]:
    """Check memory usage on remote host."""
    issues: list[Issue] = []

    result = run_remote(ctx, "free -m | awk '/^Mem:/ {printf \"%d %d\", $3, $2}'")
    if result.returncode != 0:
        return issues

    parts = result.stdout.strip().split()
    if len(parts) < 2:
        return issues

    try:
        used_mb = int(parts[0])
        total_mb = int(parts[1])
    except ValueError:
        return issues

    if total_mb == 0:
        return issues

    usage_pct = (used_mb * 100) // total_mb
    if usage_pct >= warn_percent:
        issues.append(
            Issue(
                category=Category.CONTAINER,
                severity=Severity.WARNING,
                message=f"High memory usage on {ctx.host}: {usage_pct}% ({used_mb}/{total_mb}MB)",
                fix_strategy=FixStrategy.MANUAL,
                details="Check for memory leaks or consider scaling up the server.",
                host=ctx.host,
            )
        )

    return issues
