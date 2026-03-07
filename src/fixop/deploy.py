"""Deploy artifact validation.

Covers:
- Unresolved ${VAR} in YAML/container files
- Placeholder detection (example.com, changeme, your-*)
- File existence checks before SCP

Extracted from: taskfile/diagnostics/checks.py (_scan_file_for_unresolved, check_deploy_artifacts)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import Category, FixStrategy, Issue, Severity

# Patterns for unresolved variables
_UNRESOLVED_VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
_UNRESOLVED_TMPL_RE = re.compile(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}')

# Placeholder values that indicate unconfigured files
_PLACEHOLDER_RE = re.compile(
    r'(?:example\.com|your[-_]?domain|changeme|CHANGEME|your[-_]?email'
    r'|TODO|FIXME|xxx+|placeholder|replace[-_]?me)',
    re.IGNORECASE,
)

# Default file globs to scan
DEFAULT_DEPLOY_GLOBS = (
    "**/*.yml",
    "**/*.yaml",
    "**/*.container",
    "**/*.conf",
    "**/*.toml",
    "**/*.env",
)


def check_unresolved_vars(
    paths: list[str],
    patterns: Optional[list[str]] = None,
) -> list[Issue]:
    """Scan files for unresolved ${VAR} and {{VAR}} patterns.

    Args:
        paths: File paths to scan.
        patterns: Additional regex patterns to match (optional).
    """
    issues: list[Issue] = []

    extra_patterns = [re.compile(p) for p in (patterns or [])]

    for path_str in paths:
        filepath = Path(path_str)
        if not filepath.is_file():
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Check ${VAR}
            for m in _UNRESOLVED_VAR_RE.finditer(line):
                var_name = m.group(1)
                issues.append(Issue(
                    category=Category.DEPLOY,
                    severity=Severity.WARNING,
                    message=f"Unresolved variable ${{{var_name}}} in {filepath.name}:{lineno}",
                    fix_strategy=FixStrategy.MANUAL,
                    details=f"Set {var_name} in your .env file, then regenerate deploy files. Line: {stripped[:120]}",
                ))

            # Check {{VAR}} (Jinja/Go template style)
            for m in _UNRESOLVED_TMPL_RE.finditer(line):
                var_name = m.group(1)
                if var_name.startswith("."):
                    continue  # Skip Go template syntax like {{ .Name }}
                issues.append(Issue(
                    category=Category.DEPLOY,
                    severity=Severity.WARNING,
                    message=f"Unresolved template {{{{{var_name}}}}} in {filepath.name}:{lineno}",
                    fix_strategy=FixStrategy.MANUAL,
                    details=f"Set {var_name} in your variables section. Line: {stripped[:120]}",
                ))

            # Check extra patterns
            for pat in extra_patterns:
                if pat.search(line):
                    issues.append(Issue(
                        category=Category.DEPLOY,
                        severity=Severity.WARNING,
                        message=f"Pattern match in {filepath.name}:{lineno}: {stripped[:80]}",
                    ))

    return issues


def check_placeholders(paths: list[str]) -> list[Issue]:
    """Detect placeholder values in deploy files (example.com, changeme, your-*).

    Args:
        paths: File paths to scan.
    """
    issues: list[Issue] = []

    for path_str in paths:
        filepath = Path(path_str)
        if not filepath.is_file():
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            if _PLACEHOLDER_RE.search(stripped):
                issues.append(Issue(
                    category=Category.DEPLOY,
                    severity=Severity.WARNING,
                    message=f"Placeholder value in {filepath.name}:{lineno}: {stripped[:80]}",
                    fix_strategy=FixStrategy.MANUAL,
                    details="Replace placeholder values with real configuration before deploying.",
                ))

    return issues


def check_files_exist(file_patterns: list[str], base_dir: str = ".") -> list[Issue]:
    """Verify deploy files exist before upload (pre-SCP gate).

    Args:
        file_patterns: Glob patterns relative to base_dir.
        base_dir: Base directory to resolve patterns from.
    """
    issues: list[Issue] = []
    base = Path(base_dir)

    for pattern in file_patterns:
        matches = list(base.glob(pattern))
        if not matches:
            issues.append(Issue(
                category=Category.DEPLOY,
                severity=Severity.ERROR,
                message=f"No files matching '{pattern}' in {base_dir}",
                fix_strategy=FixStrategy.MANUAL,
                details="Generate deploy files before uploading. Check your build/generate step.",
            ))

    return issues


def scan_deploy_dir(
    deploy_dir: str,
    globs: tuple[str, ...] = DEFAULT_DEPLOY_GLOBS,
) -> list[Issue]:
    """Scan a deploy directory for all common issues.

    Combines check_unresolved_vars + check_placeholders for all matching files.
    """
    dirpath = Path(deploy_dir)
    if not dirpath.is_dir():
        return []

    scanned: set[str] = set()
    all_paths: list[str] = []

    for pattern in globs:
        for filepath in dirpath.glob(pattern):
            if not filepath.is_file():
                continue
            key = str(filepath.resolve())
            if key in scanned:
                continue
            scanned.add(key)
            all_paths.append(str(filepath))

    issues: list[Issue] = []
    issues.extend(check_unresolved_vars(all_paths))
    issues.extend(check_placeholders(all_paths))
    return issues
