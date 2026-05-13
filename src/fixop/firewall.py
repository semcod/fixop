"""Firewall diagnostics and fixes.

Covers:
- UFW DEFAULT_FORWARD_POLICY check (remote)
- iptables NAT masquerade for container networks
- Port forwarding rules

Extracted from: taskfile/diagnostics/checks.py (_check_ufw_forward_policy)
"""

from __future__ import annotations

from .models import Category, FixResult, FixStrategy, HostContext, Issue, Severity
from .transport import run_remote


def check_ufw_forward_policy(ctx: HostContext) -> list[Issue]:
    """Check if UFW blocks container forwarding (DEFAULT_FORWARD_POLICY=DROP).

    When UFW is active with FORWARD=DROP (default), containers cannot
    reach the internet or each other across networks. This is the #1
    cause of 'podman pull' failures on fresh VPS setups.
    """
    issues: list[Issue] = []

    # Check if ufw is installed and active
    status = run_remote(ctx, "command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null || echo INACTIVE")
    if "INACTIVE" in status.stdout or "inactive" in status.stdout.lower():
        return issues

    # Check /etc/default/ufw for DEFAULT_FORWARD_POLICY
    result = run_remote(ctx, "grep -E '^DEFAULT_FORWARD_POLICY' /etc/default/ufw 2>/dev/null")
    if result.returncode != 0:
        return issues

    line = result.stdout.strip()
    if "DROP" in line.upper():
        issues.append(
            Issue(
                category=Category.FIREWALL,
                severity=Severity.WARNING,
                message=f"UFW DEFAULT_FORWARD_POLICY=DROP on {ctx.host} — containers cannot reach the internet",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command='sed -i \'s/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/\' /etc/default/ufw && ufw reload',
                details=(
                    "Podman and Docker containers need FORWARD=ACCEPT to pull images, "
                    "resolve DNS, and communicate across networks."
                ),
                host=ctx.host,
            )
        )

    return issues


def check_nat_masquerade(ctx: HostContext, subnet: str = "10.88.0.0/16") -> list[Issue]:
    """Check if NAT masquerade exists for container subnet.

    Without masquerade, containers on bridge networks cannot reach the internet.
    """
    issues: list[Issue] = []

    result = run_remote(ctx, f"iptables -t nat -L POSTROUTING -n 2>/dev/null | grep -i masquerade | grep '{subnet}'")
    if result.returncode != 0 or not result.stdout.strip():
        issues.append(
            Issue(
                category=Category.FIREWALL,
                severity=Severity.WARNING,
                message=f"No NAT masquerade for container subnet {subnet} on {ctx.host}",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command=f"iptables -t nat -A POSTROUTING -s {subnet} ! -d {subnet} -j MASQUERADE",
                details=(
                    f"Containers on subnet {subnet} need NAT masquerade to reach external networks. "
                    "Without it, outbound traffic from containers is dropped."
                ),
                host=ctx.host,
            )
        )

    return issues


# ── Fixes ──────────────────────────────────────────────


def fix_ufw_allow_routed(ctx: HostContext) -> FixResult:
    """Set UFW DEFAULT_FORWARD_POLICY to ACCEPT and reload."""
    cmd = 'sed -i \'s/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/\' /etc/default/ufw && ufw reload'
    result = run_remote(ctx, cmd)
    issue = Issue(
        category=Category.FIREWALL,
        severity=Severity.WARNING,
        message=f"Set UFW FORWARD=ACCEPT on {ctx.host}",
        host=ctx.host,
    )
    return FixResult(
        issue=issue,
        success=result.returncode == 0,
        output=result.stdout.strip(),
        error=result.stderr.strip(),
    )


def fix_nat_masquerade(ctx: HostContext, subnet: str = "10.88.0.0/16") -> FixResult:
    """Add iptables NAT masquerade rule for container subnet."""
    cmd = f"iptables -t nat -A POSTROUTING -s {subnet} ! -d {subnet} -j MASQUERADE"
    result = run_remote(ctx, cmd)
    issue = Issue(
        category=Category.FIREWALL,
        severity=Severity.WARNING,
        message=f"Added NAT masquerade for {subnet} on {ctx.host}",
        host=ctx.host,
    )
    return FixResult(
        issue=issue,
        success=result.returncode == 0,
        output=result.stdout.strip(),
        error=result.stderr.strip(),
    )
