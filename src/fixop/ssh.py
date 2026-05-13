"""SSH transport and connectivity checks.

Provides:
- run_remote(): execute commands on remote hosts via SSH subprocess
- check_ssh_connectivity(): verify SSH access
- check_ssh_key(): verify local SSH key exists

Extracted from: taskfile/runner/ssh.py, taskfile/diagnostics/checks_ssh.py, taskfile/deploy_utils.py
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import Category, FixStrategy, HostContext, Issue, Severity
from .transport import RemoteResult, run_remote, test_ssh_connection  # noqa: F401 — re-export


# ── Checks ──────────────────────────────────────────────


def check_ssh_key(key_path: str = "~/.ssh/id_ed25519") -> list[Issue]:
    """Check if an SSH key exists locally.

    Returns issues if ~/.ssh directory or the specified key is missing.
    """
    issues: list[Issue] = []
    ssh_dir = Path.home() / ".ssh"

    if not ssh_dir.exists():
        issues.append(
            Issue(
                category=Category.SSH,
                severity=Severity.ERROR,
                message="~/.ssh directory not found",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command="mkdir -p ~/.ssh && chmod 700 ~/.ssh",
                details="SSH directory must exist before generating keys.",
            )
        )
        return issues

    expanded = Path(os.path.expanduser(key_path))
    if not expanded.exists():
        # Check if any key exists
        keys = list(ssh_dir.glob("id_*"))
        if not keys:
            issues.append(
                Issue(
                    category=Category.SSH,
                    severity=Severity.WARNING,
                    message=f"No SSH keys found (checked {key_path})",
                    fix_strategy=FixStrategy.CONFIRM,
                    fix_command="ssh-keygen -t ed25519 -N ''",
                    details="Generate an SSH key pair for remote access.",
                )
            )
    return issues


def check_ssh_connectivity(ctx: HostContext) -> list[Issue]:
    """Check SSH connectivity to a remote host.

    Distinguishes: missing key, connection refused, auth failure, timeout.
    """
    issues: list[Issue] = []

    # Check local key first
    key_path = Path(os.path.expanduser(ctx.key))
    if not key_path.exists():
        issues.append(
            Issue(
                category=Category.SSH,
                severity=Severity.ERROR,
                message=f"SSH key {ctx.key} not found",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command=f"ssh-keygen -t ed25519 -f {ctx.key} -N ''",
                host=ctx.host,
            )
        )
        return issues

    # Test connection
    result = test_ssh_connection(ctx)

    if result.returncode == 0:
        return issues  # all good

    if result.returncode == 255:
        stderr_lower = result.stderr.lower()
        if "connection refused" in stderr_lower:
            issues.append(
                Issue(
                    category=Category.SSH,
                    severity=Severity.ERROR,
                    message=f"SSH to {ctx.host}: connection refused",
                    fix_strategy=FixStrategy.MANUAL,
                    details=(
                        "Server is reachable but SSH daemon is not running or port is blocked. "
                        "Check: 1) Is SSH service running? 2) Is firewall blocking port 22?"
                    ),
                    host=ctx.host,
                )
            )
        elif "timed out" in stderr_lower or "timeout" in stderr_lower:
            issues.append(
                Issue(
                    category=Category.SSH,
                    severity=Severity.ERROR,
                    message=f"SSH to {ctx.host}: connection timed out",
                    fix_strategy=FixStrategy.MANUAL,
                    details="Host unreachable — check network, DNS, or firewall rules.",
                    host=ctx.host,
                )
            )
        else:
            issues.append(
                Issue(
                    category=Category.SSH,
                    severity=Severity.ERROR,
                    message=f"SSH to {ctx.host}: failed (exit 255) — {result.stderr[:100]}",
                    host=ctx.host,
                )
            )
    elif result.returncode == 5:
        issues.append(
            Issue(
                category=Category.SSH,
                severity=Severity.ERROR,
                message=f"SSH auth failed for {ctx.host}",
                fix_strategy=FixStrategy.CONFIRM,
                fix_command=f"ssh-copy-id -i {ctx.key} {ctx.user}@{ctx.host}",
                details="Key not authorized on the server. Copy public key with ssh-copy-id.",
                host=ctx.host,
            )
        )
    elif result.returncode == -1:
        issues.append(
            Issue(
                category=Category.SSH,
                severity=Severity.ERROR,
                message=f"SSH to {ctx.host}: {result.stderr[:100]}",
                host=ctx.host,
            )
        )
    else:
        issues.append(
            Issue(
                category=Category.SSH,
                severity=Severity.WARNING,
                message=f"SSH to {ctx.host}: unexpected exit code {result.returncode}",
                host=ctx.host,
            )
        )

    return issues
