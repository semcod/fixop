"""Systemd unit management with race condition prevention.

Covers:
- Graceful restart (stop → wait → verify → start)
- daemon-reload
- Unit status checks
- Quadlet unit detection

Addresses the race condition where 'systemctl restart' rebinds ports
before the old process fully releases them.
"""

from __future__ import annotations

import time

from .models import Category, FixResult, FixStrategy, HostContext, Issue, Severity
from .transport import run_remote


def check_unit_status(ctx: HostContext, units: list[str]) -> list[Issue]:
    """Check if systemd units are active.

    Args:
        ctx: SSH connection context.
        units: List of unit names to check (without .service suffix).
    """
    issues: list[Issue] = []

    for unit in units:
        result = run_remote(ctx, f"systemctl is-active {unit} 2>/dev/null")
        status = result.stdout.strip()

        if status == "active":
            continue
        elif status == "inactive":
            issues.append(
                Issue(
                    category=Category.SYSTEMD,
                    severity=Severity.WARNING,
                    message=f"Unit '{unit}' is inactive on {ctx.host}",
                    fix_strategy=FixStrategy.CONFIRM,
                    fix_command=f"systemctl start {unit}",
                    host=ctx.host,
                )
            )
        elif status == "failed":
            # Get failure reason
            journal = run_remote(ctx, f"journalctl -u {unit} --no-pager -n 5 2>/dev/null")
            details = journal.stdout.strip()[-300:] if journal.returncode == 0 else ""
            issues.append(
                Issue(
                    category=Category.SYSTEMD,
                    severity=Severity.ERROR,
                    message=f"Unit '{unit}' has failed on {ctx.host}",
                    fix_strategy=FixStrategy.MANUAL,
                    fix_command=f"systemctl restart {unit}",
                    details=f"Recent logs:\n{details}" if details else None,
                    host=ctx.host,
                )
            )
        elif "could not be found" in (result.stderr or "").lower() or result.returncode == 4:
            issues.append(
                Issue(
                    category=Category.SYSTEMD,
                    severity=Severity.INFO,
                    message=f"Unit '{unit}' not found on {ctx.host}",
                    fix_strategy=FixStrategy.MANUAL,
                    details=f"Unit may not be deployed yet. Check: ls /etc/containers/systemd/{unit}.container",
                    host=ctx.host,
                )
            )
        else:
            issues.append(
                Issue(
                    category=Category.SYSTEMD,
                    severity=Severity.WARNING,
                    message=f"Unit '{unit}' status: {status} on {ctx.host}",
                    host=ctx.host,
                )
            )

    return issues


def check_quadlet_loaded(ctx: HostContext, units: list[str]) -> list[Issue]:
    """Check if Quadlet .container files are recognized by systemd.

    Quadlet files in /etc/containers/systemd/ are auto-converted to systemd units.
    """
    issues: list[Issue] = []

    for unit in units:
        result = run_remote(ctx, f"ls /etc/containers/systemd/{unit}.container 2>/dev/null")
        if result.returncode != 0:
            issues.append(
                Issue(
                    category=Category.SYSTEMD,
                    severity=Severity.WARNING,
                    message=f"Quadlet file not found: /etc/containers/systemd/{unit}.container on {ctx.host}",
                    fix_strategy=FixStrategy.MANUAL,
                    details="Upload the .container file and run: systemctl daemon-reload",
                    host=ctx.host,
                )
            )
            continue

        # Check if systemd recognizes the generated unit
        check = run_remote(ctx, f"systemctl cat {unit} 2>/dev/null")
        if check.returncode != 0:
            issues.append(
                Issue(
                    category=Category.SYSTEMD,
                    severity=Severity.WARNING,
                    message=f"Quadlet file exists but unit '{unit}' not loaded on {ctx.host}",
                    fix_strategy=FixStrategy.CONFIRM,
                    fix_command="systemctl daemon-reload",
                    details="Run daemon-reload to pick up new/changed Quadlet files.",
                    host=ctx.host,
                )
            )

    return issues


# ── Fixes ──────────────────────────────────────────────


def daemon_reload(ctx: HostContext) -> FixResult:
    """Run systemctl daemon-reload on remote host."""
    result = run_remote(ctx, "systemctl daemon-reload")
    issue = Issue(
        category=Category.SYSTEMD,
        severity=Severity.INFO,
        message=f"Ran daemon-reload on {ctx.host}",
        host=ctx.host,
    )
    return FixResult(
        issue=issue,
        success=result.returncode == 0,
        output=result.stdout.strip(),
        error=result.stderr.strip(),
    )


def graceful_restart(ctx: HostContext, unit: str, delay: int = 3) -> FixResult:
    """Graceful restart: stop → wait → verify stopped → start.

    Prevents port binding race conditions that occur with plain 'systemctl restart'.
    The delay ensures the old process fully releases sockets before the new one starts.

    Args:
        ctx: SSH connection context.
        unit: Systemd unit name.
        delay: Seconds to wait between stop and start.
    """
    # Stop the unit
    stop = run_remote(ctx, f"systemctl stop {unit}")
    if stop.returncode != 0:
        issue = Issue(
            category=Category.SYSTEMD,
            severity=Severity.ERROR,
            message=f"Failed to stop {unit} on {ctx.host}",
            host=ctx.host,
        )
        return FixResult(issue=issue, success=False, error=stop.stderr.strip())

    # Wait for process to release resources
    time.sleep(delay)

    # Verify it's actually stopped
    verify = run_remote(ctx, f"systemctl is-active {unit} 2>/dev/null")
    if verify.stdout.strip() == "active":
        # Still running — wait more
        time.sleep(delay)

    # Start the unit
    start = run_remote(ctx, f"systemctl start {unit}")
    if start.returncode != 0:
        issue = Issue(
            category=Category.SYSTEMD,
            severity=Severity.ERROR,
            message=f"Failed to start {unit} on {ctx.host}",
            host=ctx.host,
        )
        return FixResult(issue=issue, success=False, error=start.stderr.strip())

    # Verify it started
    check = run_remote(ctx, f"systemctl is-active {unit} 2>/dev/null")
    started = check.stdout.strip() == "active"

    issue = Issue(
        category=Category.SYSTEMD,
        severity=Severity.INFO,
        message=f"Graceful restart of {unit} on {ctx.host}",
        host=ctx.host,
    )
    return FixResult(
        issue=issue,
        success=started,
        output=f"stop → {delay}s delay → start → {'active' if started else check.stdout.strip()}",
        error="" if started else f"Unit status after start: {check.stdout.strip()}",
    )


def graceful_restart_all(
    ctx: HostContext,
    units: list[str],
    delay: int = 3,
) -> list[FixResult]:
    """Graceful restart multiple units sequentially.

    Each unit is fully stopped and verified before starting the next.
    """
    results: list[FixResult] = []
    for unit in units:
        result = graceful_restart(ctx, unit, delay=delay)
        results.append(result)
        if not result.success:
            break  # stop on first failure
    return results
