"""fixop — Infrastructure fix operations.

Detect and repair DNS, firewall, containers, TLS, systemd issues
on local and remote servers. Zero external dependencies.

Usage as library:
    from fixop import HostContext, check_host_dns, check_ufw_forward_policy, fix_resolv_conf

Usage as CLI:
    fixop check --host myserver.com
    fixop fix --host myserver.com --auto
    fixop validate deploy/
"""

__version__ = "0.1.8"

# ── Core types ─────────────────────────────────────────
from .models import (
    Category,
    FixResult,
    FixStrategy,
    HostContext,
    Issue,
    Severity,
)

# ── Checks (detect problems) ──────────────────────────
from .ssh import check_ssh_connectivity, check_ssh_key
from .dns import check_host_dns, check_container_dns, check_systemd_resolved
from .firewall import check_ufw_forward_policy, check_nat_masquerade
from .containers import check_runtime, check_containers_running, check_disk_usage, check_memory
from .systemd import check_unit_status, check_quadlet_loaded
from .tls import check_certificate, check_certificates
from .deploy import check_unresolved_vars, check_placeholders, check_files_exist
from .classify import classify_error

# ── Fixes (repair problems) ───────────────────────────
from .dns import fix_resolv_conf, fix_disable_systemd_resolved, generate_container_resolv_conf
from .firewall import fix_ufw_allow_routed, fix_nat_masquerade as fix_nat_masquerade_rule
from .systemd import daemon_reload, graceful_restart, graceful_restart_all

# ── Convenience: run all checks ───────────────────────


def check_all(
    ctx: HostContext,
    domains: list[str] | None = None,
    containers: list[str] | None = None,
) -> list[Issue]:
    """Run all infrastructure checks on a remote host.

    Args:
        ctx: SSH connection context.
        domains: Domains to check TLS certificates for.
        containers: Expected container names to verify.
    """
    issues: list[Issue] = []

    # SSH
    ssh_issues = check_ssh_connectivity(ctx)
    issues.extend(ssh_issues)
    if ssh_issues:
        return issues  # can't check anything else without SSH

    # DNS
    issues.extend(check_host_dns(ctx))
    issues.extend(check_systemd_resolved(ctx))
    if containers:
        for c in containers[:1]:  # check DNS in first container only
            issues.extend(check_container_dns(ctx, container=c))

    # Firewall
    issues.extend(check_ufw_forward_policy(ctx))

    # Containers
    issues.extend(check_runtime(ctx))
    if containers:
        issues.extend(check_containers_running(ctx, expected=containers))

    # Systemd
    if containers:
        issues.extend(check_unit_status(ctx, containers))

    # Resources
    issues.extend(check_disk_usage(ctx))
    issues.extend(check_memory(ctx))

    # TLS
    if domains:
        issues.extend(check_certificates(domains))

    return issues


__all__ = [
    # Types
    "Category", "FixResult", "FixStrategy", "HostContext", "Issue", "Severity",
    # Checks
    "check_ssh_connectivity", "check_ssh_key",
    "check_host_dns", "check_container_dns", "check_systemd_resolved",
    "check_ufw_forward_policy", "check_nat_masquerade",
    "check_runtime", "check_containers_running", "check_disk_usage", "check_memory",
    "check_unit_status", "check_quadlet_loaded",
    "check_certificate", "check_certificates",
    "check_unresolved_vars", "check_placeholders", "check_files_exist",
    "classify_error",
    # Fixes
    "fix_resolv_conf", "fix_disable_systemd_resolved", "generate_container_resolv_conf",
    "fix_ufw_allow_routed", "fix_nat_masquerade_rule",
    "daemon_reload", "graceful_restart", "graceful_restart_all",
    # Convenience
    "check_all",
]