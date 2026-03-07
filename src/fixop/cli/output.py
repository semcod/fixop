"""CLI output formatting — text and JSON renderers for issues.

Extracted from: fixop/cli.py (_output_issues)
Split into pure functions: filter, group, format.
"""

from __future__ import annotations

import json

from ..models import Issue, Severity


def output_issues(issues: list[Issue], fmt: str = "text") -> None:
    """Print issues in the requested format."""
    if fmt == "json":
        print(_format_json(issues))
    else:
        print(_format_text(issues))


def _format_json(issues: list[Issue]) -> str:
    """Serialize issues to JSON string."""
    data = [
        {
            "category": i.category.value,
            "severity": i.severity.value,
            "message": i.message,
            "fix_strategy": i.fix_strategy.value,
            "fix_command": i.fix_command,
            "details": i.details,
            "host": i.host,
        }
        for i in issues
    ]
    return json.dumps(data, indent=2)


def _format_text(issues: list[Issue]) -> str:
    """Render issues as grouped, human-readable text."""
    if not issues:
        return "✅ No issues found."

    grouped = _group_by_category(issues)
    lines: list[str] = []

    for cat, cat_issues in sorted(grouped.items()):
        lines.append(f"\n── {cat.upper()} ──")
        for i in cat_issues:
            lines.append(f"  {i}")
            if i.details:
                for detail_line in i.details.splitlines():
                    lines.append(f"    {detail_line}")
            if i.fix_command:
                lines.append(f"    Fix: {i.fix_command}")

    errors, warnings, fixable = _summarize(issues)
    icon = "❌" if errors else "⚠" if warnings else "ℹ"
    lines.append(f"\n{icon} {len(issues)} issues ({errors} errors, {warnings} warnings, {fixable} fixable)")

    return "\n".join(lines)


def _group_by_category(issues: list[Issue]) -> dict[str, list[Issue]]:
    """Group issues by category value."""
    by_cat: dict[str, list[Issue]] = {}
    for i in issues:
        by_cat.setdefault(i.category.value, []).append(i)
    return by_cat


def _summarize(issues: list[Issue]) -> tuple[int, int, int]:
    """Return (error_count, warning_count, fixable_count)."""
    errors = sum(1 for i in issues if i.severity in (Severity.ERROR, Severity.CRITICAL))
    warnings = sum(1 for i in issues if i.severity == Severity.WARNING)
    fixable = sum(1 for i in issues if i.fix_command)
    return errors, warnings, fixable
