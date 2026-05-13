"""Runtime error classification.

Maps exit codes + stderr patterns to infrastructure categories.
Uses dispatch tables instead of if/elif chains (CC=17 → CC=3).

Extracted from: taskfile/diagnostics/llm_repair.py (classify_runtime_error),
               taskfile/runner/commands.py (_classify_exit_code, _get_tip_for_failure)
"""

from __future__ import annotations

import re

from .models import Category, Issue, Severity

# ── Exit code dispatch table ──────────────────────────

EXIT_CODE_MAP: dict[int, tuple[Category, str, Severity]] = {
    1: (Category.CONTAINER, "General error", Severity.ERROR),
    2: (Category.DEPLOY, "Misuse of shell command", Severity.ERROR),
    124: (Category.CONTAINER, "Command timed out", Severity.ERROR),
    126: (Category.DEPLOY, "Permission denied or not executable", Severity.ERROR),
    127: (Category.DEPLOY, "Command not found", Severity.ERROR),
    128: (Category.CONTAINER, "Invalid exit signal", Severity.ERROR),
    137: (Category.CONTAINER, "Container killed (OOM or SIGKILL)", Severity.CRITICAL),
    143: (Category.CONTAINER, "Container terminated (SIGTERM)", Severity.WARNING),
    255: (Category.SSH, "SSH connection failed", Severity.ERROR),
}

# ── Stderr pattern table ──────────────────────────────

STDERR_PATTERNS: list[tuple[str, Category, str, Severity]] = [
    (r"lookup.*on.*:53.*timeout", Category.DNS, "DNS resolution timeout", Severity.CRITICAL),
    (r"dial tcp.*connection refused", Category.FIREWALL, "Connection refused", Severity.ERROR),
    (r"address already in use", Category.PORT, "Port conflict", Severity.ERROR),
    (r"self[- ]signed certificate", Category.TLS, "Self-signed cert detected", Severity.WARNING),
    (r"ACME.*unable to obtain", Category.TLS, "ACME cert generation failed", Severity.ERROR),
    (r"permission denied", Category.SSH, "SSH permission denied", Severity.ERROR),
    (r"no such image", Category.CONTAINER, "Container image not found", Severity.ERROR),
    (r"command not found", Category.DEPLOY, "Command not found", Severity.ERROR),
    (r"no route to host", Category.FIREWALL, "No route to host", Severity.ERROR),
    (r"name or service not known", Category.DNS, "DNS resolution failed", Severity.ERROR),
    (r"connection timed out", Category.FIREWALL, "Connection timed out", Severity.ERROR),
    (r"unable to pull", Category.CONTAINER, "Image pull failed", Severity.ERROR),
]

# Compiled patterns (lazy init)
_COMPILED_PATTERNS: list[tuple[re.Pattern, Category, str, Severity]] | None = None


def _get_compiled_patterns() -> list[tuple[re.Pattern, Category, str, Severity]]:
    global _COMPILED_PATTERNS
    if _COMPILED_PATTERNS is None:
        _COMPILED_PATTERNS = [(re.compile(pat, re.IGNORECASE), cat, msg, sev) for pat, cat, msg, sev in STDERR_PATTERNS]
    return _COMPILED_PATTERNS


def classify_error(exit_code: int, stderr: str = "", cmd: str = "") -> Issue:
    """Classify runtime error by exit code and stderr patterns.

    Checks stderr patterns first (more specific), then falls back to exit code map.

    Args:
        exit_code: Process exit code.
        stderr: Standard error output.
        cmd: The command that was executed.

    Returns:
        Issue with classified category, severity, and details.
    """
    # 1. Try stderr patterns (most specific)
    for pattern, category, message, severity in _get_compiled_patterns():
        if pattern.search(stderr):
            return Issue(
                category=category,
                severity=severity,
                message=f"{message}: {_truncate(stderr, 100)}",
                details=f"Command: {_truncate(cmd, 200)}" if cmd else None,
            )

    # 2. Try exit code map
    if exit_code in EXIT_CODE_MAP:
        category, message, severity = EXIT_CODE_MAP[exit_code]
        detail_parts = []
        if cmd:
            detail_parts.append(f"Command: {_truncate(cmd, 200)}")
        if stderr:
            detail_parts.append(f"Stderr: {_truncate(stderr, 200)}")
        return Issue(
            category=category,
            severity=severity,
            message=f"{message} (exit {exit_code})",
            details="\n".join(detail_parts) if detail_parts else None,
        )

    # 3. Default: generic runtime error
    return Issue(
        category=Category.CONTAINER,
        severity=Severity.ERROR,
        message=f"Task failed (exit {exit_code}): {_truncate(stderr or cmd, 100)}",
        details=f"Command: {_truncate(cmd, 200)}" if cmd else None,
    )


def get_tip_for_failure(cmd: str, exit_code: int) -> str | None:
    """Return a learning tip relevant to a specific failure.

    Extracted from: taskfile/runner/commands.py (_get_tip_for_failure)
    """
    cmd_lower = cmd.lower()

    if exit_code == 1 and ("scp" in cmd_lower or "rsync" in cmd_lower):
        return "Missing files? Check that deploy artifacts exist before uploading. Run: fixop validate deploy/"

    if exit_code == 255 and ("ssh" in cmd_lower or "scp" in cmd_lower):
        return (
            "SSH error (exit 255). Common causes:\n"
            "- Host unreachable — check hostname/IP\n"
            "- Key rejected — check SSH key permissions (chmod 600)\n"
            "- Run: fixop check --host <server> --category ssh"
        )

    if exit_code == 126:
        return (
            "Permission denied. Check:\n- Script is executable: chmod +x scripts/*.sh\n- Correct path in script field"
        )

    if exit_code == 127:
        return "Command not found. Check:\n- Tool is installed: which <command>\n- PATH includes the tool's directory"

    return None


def extract_missing_binary(stderr: str) -> str:
    """Extract binary name from 'command not found' stderr."""
    for line in stderr.splitlines():
        if "command not found" in line.lower():
            parts = line.split(":")
            if len(parts) >= 2:
                return parts[-2].strip()
    return "unknown"


def _truncate(s: str, max_len: int) -> str:
    """Truncate string to max_len characters."""
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."
