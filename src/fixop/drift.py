"""File drift detection — compare markpact README blocks against files on disk.

Checks whether extracted files in a directory still match the content
defined in markpact:file blocks in a README.md. Reports drifted, missing,
and untracked files as Issues.

Zero external dependencies — uses only stdlib + fixop models.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import Category, FixStrategy, Issue, Severity


# ─── Block parsing (minimal, standalone — no markpact dependency) ─────────────

_BLOCK_RE = re.compile(
    r"```(?:\w+\s+)?markpact:file\s+path=(\S+)[^\n]*\n([\s\S]*?)\n```"
)


def _extract_blocks(readme_text: str) -> dict[str, str]:
    """Extract markpact:file blocks from README text.

    Returns:
        Dict mapping relative path → block body content.
    """
    blocks: dict[str, str] = {}
    for m in _BLOCK_RE.finditer(readme_text):
        rel_path = m.group(1)
        body = m.group(2).strip()
        blocks[rel_path] = body
    return blocks


def _sha256(content: str) -> str:
    """Compute SHA-256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ─── Public API ──────────────────────────────────────────────────────────────


def check_file_drift(
    readme_path: str | Path,
    extracted_dir: str | Path,
    *,
    ignore_whitespace: bool = False,
) -> list[Issue]:
    """Compare markpact:file blocks in README against files on disk.

    Reports:
    - DRIFTED: file on disk differs from README block content
    - MISSING: file defined in README but not found on disk

    Args:
        readme_path: Path to README.md containing markpact:file blocks.
        extracted_dir: Directory where files were extracted (e.g., sandbox/).
        ignore_whitespace: If True, strip trailing whitespace before comparing.

    Returns:
        List of Issues for drifted or missing files.
    """
    readme = Path(readme_path)
    target = Path(extracted_dir)
    issues: list[Issue] = []

    if not readme.exists():
        issues.append(Issue(
            category=Category.DEPLOY,
            severity=Severity.ERROR,
            message=f"README not found: {readme}",
        ))
        return issues

    text = readme.read_text(encoding="utf-8")
    blocks = _extract_blocks(text)

    if not blocks:
        return issues

    for rel_path, readme_body in blocks.items():
        file_path = target / rel_path

        if not file_path.exists():
            issues.append(Issue(
                category=Category.DEPLOY,
                severity=Severity.WARNING,
                message=f"File defined in README but missing on disk: {rel_path}",
                fix_strategy=FixStrategy.AUTO,
                details=f"Run 'markpact {readme}' to extract, or remove the block from README.",
            ))
            continue

        try:
            disk_content = file_path.read_text(encoding="utf-8").rstrip("\n")
        except Exception as e:
            issues.append(Issue(
                category=Category.DEPLOY,
                severity=Severity.ERROR,
                message=f"Cannot read file {rel_path}: {e}",
            ))
            continue

        readme_content = readme_body.rstrip("\n")

        if ignore_whitespace:
            disk_lines = [l.rstrip() for l in disk_content.splitlines()]
            readme_lines = [l.rstrip() for l in readme_content.splitlines()]
            disk_content = "\n".join(disk_lines)
            readme_content = "\n".join(readme_lines)

        if disk_content != readme_content:
            disk_hash = _sha256(disk_content)
            readme_hash = _sha256(readme_content)
            issues.append(Issue(
                category=Category.DEPLOY,
                severity=Severity.WARNING,
                message=(
                    f"File drifted from README: {rel_path} "
                    f"(disk:{disk_hash} ≠ readme:{readme_hash})"
                ),
                fix_strategy=FixStrategy.MANUAL,
                details=(
                    f"File on disk differs from markpact:file block in README.\n"
                    f"To sync disk → README: markpact sync {readme}\n"
                    f"To sync README → disk: markpact {readme}"
                ),
            ))

    return issues


def check_untracked_files(
    readme_path: str | Path,
    extracted_dir: str | Path,
    *,
    exclude_dirs: set[str] | None = None,
) -> list[Issue]:
    """Find files in extracted_dir not tracked by any markpact:file block.

    Args:
        readme_path: Path to README.md.
        extracted_dir: Directory to scan.
        exclude_dirs: Directory names to skip (default: .venv, __pycache__, etc.)

    Returns:
        List of Issues for untracked files.
    """
    readme = Path(readme_path)
    target = Path(extracted_dir)
    issues: list[Issue] = []

    if not readme.exists() or not target.exists():
        return issues

    default_exclude = {
        ".venv", "venv", "node_modules", "__pycache__", ".git",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "build", "dist", ".egg-info",
    }
    dirs_to_skip = exclude_dirs if exclude_dirs is not None else default_exclude

    text = readme.read_text(encoding="utf-8")
    tracked = set(_extract_blocks(text).keys())

    untracked: list[str] = []
    for file_path in sorted(target.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(target)
        if any(part in dirs_to_skip for part in rel.parts):
            continue
        rel_str = str(rel)
        if rel_str not in tracked:
            untracked.append(rel_str)

    if untracked:
        summary = ", ".join(untracked[:5])
        if len(untracked) > 5:
            summary += f" (+{len(untracked) - 5} more)"
        issues.append(Issue(
            category=Category.DEPLOY,
            severity=Severity.INFO,
            message=f"{len(untracked)} file(s) in {target.name}/ not tracked in README: {summary}",
            fix_strategy=FixStrategy.MANUAL,
            details="Run 'markpact sync --missing' to see all untracked files.",
        ))

    return issues
