"""DNS diagnostics and fixes.

Covers the exact problems encountered in Podman + Traefik deployments:
1. Container DNS: Podman bridge gateway (10.89.0.1) doesn't forward DNS
2. Host DNS: systemd-resolved on 127.0.0.53 sometimes stops resolving
3. resolv.conf generation for container mounts

Extracted from: taskfile-example troubleshooting (DNS timeout → ACME failure → no Let's Encrypt certs)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .models import HostContext, Issue, FixResult, Category, Severity, FixStrategy
from .ssh import run_remote

DEFAULT_NAMESERVERS = ["8.8.8.8", "1.1.1.1"]
TEST_DOMAIN = "acme-v02.api.letsencrypt.org"  # critical for ACME cert generation


def check_host_dns(ctx: HostContext, domain: str = TEST_DOMAIN) -> list[Issue]:
    """Check if the host can resolve external domains.

    Detects: systemd-resolved failures, broken /etc/resolv.conf.
    """
    issues: list[Issue] = []
    try:
        result = run_remote(ctx, f"nslookup {domain} 2>&1 | head -5", timeout=15)
        if result.returncode != 0 or "NXDOMAIN" in result.stdout or "timed out" in result.stdout.lower():
            # Check what nameserver is configured
            resolv = run_remote(ctx, "cat /etc/resolv.conf 2>/dev/null | grep nameserver | head -3")
            nameservers = resolv.stdout.strip() if resolv.returncode == 0 else "unknown"

            issues.append(Issue(
                category=Category.DNS,
                severity=Severity.CRITICAL,
                message=f"Host DNS cannot resolve {domain}",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command=f"echo 'nameserver 8.8.8.8' > /etc/resolv.conf && echo 'nameserver 1.1.1.1' >> /etc/resolv.conf",
                details=f"Current nameservers:\n{nameservers}",
                host=ctx.host,
            ))
    except subprocess.TimeoutExpired:
        issues.append(Issue(
            category=Category.DNS,
            severity=Severity.CRITICAL,
            message=f"DNS check timed out on {ctx.host} — likely systemd-resolved is hanging",
            fix_strategy=FixStrategy.CONFIRM,
            fix_command="systemctl stop systemd-resolved && echo 'nameserver 8.8.8.8' > /etc/resolv.conf",
            host=ctx.host,
        ))
    return issues


def check_container_dns(
    ctx: HostContext,
    container: str = "traefik",
    domain: str = TEST_DOMAIN,
) -> list[Issue]:
    """Check if a container can resolve external domains.

    The #1 cause of ACME failures: Podman bridge DNS (10.89.0.1) doesn't forward external queries.
    Symptom in Traefik logs: 'lookup acme-v02.api.letsencrypt.org on 10.89.0.1:53: i/o timeout'
    """
    issues: list[Issue] = []
    try:
        # First check if container exists and is running
        check = run_remote(ctx, f"podman inspect {container} --format '{{{{.State.Running}}}}' 2>/dev/null")
        if check.returncode != 0 or "true" not in check.stdout.lower():
            return []  # container not running — skip

        # Check network mode — host network bypasses the problem
        net_check = run_remote(ctx, f"podman inspect {container} --format '{{{{.HostConfig.NetworkMode}}}}'")
        if net_check.returncode == 0 and "host" in net_check.stdout.strip().lower():
            return []  # host network — DNS follows host, no container DNS issue

        # Try DNS resolution from inside the container
        result = run_remote(
            ctx,
            f"podman exec {container} nslookup {domain} 2>&1 | head -5",
            timeout=20,
        )
        if result.returncode != 0 or "timed out" in result.stdout.lower() or "NXDOMAIN" in result.stdout:
            issues.append(Issue(
                category=Category.DNS,
                severity=Severity.CRITICAL,
                message=f"Container '{container}' cannot resolve {domain} — ACME certs will fail",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command=None,  # fix options below
                details=(
                    "Fix options (pick one):\n"
                    f"  1. Switch to host network: set Network=host in {container}.container\n"
                    "  2. Mount custom resolv.conf: Volume=./resolv.conf:/etc/resolv.conf:ro\n"
                    "  3. Fix Podman DNS: add dns=8.8.8.8 to containers.conf"
                ),
                host=ctx.host,
            ))
    except subprocess.TimeoutExpired:
        issues.append(Issue(
            category=Category.DNS,
            severity=Severity.ERROR,
            message=f"DNS check timed out inside container '{container}' on {ctx.host}",
            host=ctx.host,
        ))
    return issues


def check_systemd_resolved(ctx: HostContext) -> list[Issue]:
    """Check if systemd-resolved is active and potentially blocking DNS.

    systemd-resolved listens on 127.0.0.53 — if it hangs, all DNS fails on the host
    AND in host-network containers.
    """
    issues: list[Issue] = []
    result = run_remote(ctx, "systemctl is-active systemd-resolved 2>/dev/null")
    if result.returncode == 0 and "active" in result.stdout:
        # It's running — check if it actually resolves
        test = run_remote(ctx, "resolvectl query google.com 2>&1 | head -3", timeout=10)
        if test.returncode != 0 or "no appropriate query" in test.stdout.lower():
            issues.append(Issue(
                category=Category.DNS,
                severity=Severity.WARNING,
                message=f"systemd-resolved is active but may not be resolving on {ctx.host}",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command="systemctl stop systemd-resolved && systemctl disable systemd-resolved",
                details="If disabled, you must set static nameservers in /etc/resolv.conf",
                host=ctx.host,
            ))
    return issues


# ── Fixes ──────────────────────────────────────────────

def fix_resolv_conf(ctx: HostContext, nameservers: Optional[list[str]] = None) -> FixResult:
    """Write public DNS nameservers to /etc/resolv.conf on remote host."""
    ns = nameservers or DEFAULT_NAMESERVERS
    commands = " && ".join(
        [f"echo 'nameserver {n}' {'>' if i == 0 else '>>'} /etc/resolv.conf" for i, n in enumerate(ns)]
    )
    result = run_remote(ctx, commands)
    issue = Issue(
        category=Category.DNS, severity=Severity.CRITICAL,
        message=f"Set /etc/resolv.conf to {', '.join(ns)} on {ctx.host}",
        host=ctx.host,
    )
    return FixResult(
        issue=issue,
        success=result.returncode == 0,
        output=result.stdout.strip(),
        error=result.stderr.strip(),
    )


def fix_disable_systemd_resolved(ctx: HostContext) -> FixResult:
    """Stop and disable systemd-resolved, then set static resolv.conf."""
    cmd = (
        "systemctl stop systemd-resolved 2>/dev/null; "
        "systemctl disable systemd-resolved 2>/dev/null; "
        "rm -f /etc/resolv.conf; "  # it might be a symlink to resolved stub
        "echo 'nameserver 8.8.8.8' > /etc/resolv.conf; "
        "echo 'nameserver 1.1.1.1' >> /etc/resolv.conf"
    )
    result = run_remote(ctx, cmd)
    issue = Issue(
        category=Category.DNS, severity=Severity.CRITICAL,
        message=f"Disabled systemd-resolved and set static DNS on {ctx.host}",
        host=ctx.host,
    )
    return FixResult(
        issue=issue,
        success=result.returncode == 0,
        output=result.stdout.strip(),
        error=result.stderr.strip(),
    )


def generate_container_resolv_conf(
    output_path: str = "deploy/resolv.conf",
    nameservers: Optional[list[str]] = None,
) -> str:
    """Generate resolv.conf file for mounting into containers.

    Used when container network doesn't have working DNS.
    Mount with: Volume=./resolv.conf:/etc/resolv.conf:ro in .container file.
    """
    ns = nameservers or DEFAULT_NAMESERVERS
    content = "# Generated by fixop — public DNS for containers\n"
    content += "\n".join(f"nameserver {n}" for n in ns) + "\n"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content)
    return output_path
