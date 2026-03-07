"""CLI fix command — discover, confirm, apply fixes.

Extracted from: fixop/cli.py (_cmd_fix)
Split into: discover → confirm → apply → report pipeline.
"""

from __future__ import annotations

from ..models import FixStrategy, HostContext, Issue


def cmd_fix(args) -> int:
    """Apply fixes for detected issues."""
    from .. import check_all

    ctx = HostContext(host=args.host, user=args.user, port=args.port, key=args.key)
    issues = check_all(ctx)

    if args.category:
        cats = {c.strip().lower() for c in args.category.split(",")}
        issues = [i for i in issues if i.category.value in cats]

    fixable = _discover_fixable(issues)

    if not fixable:
        print("No auto-fixable issues found.")
        return 0

    results = _apply_all(ctx, fixable, auto=args.auto, interactive=args.interactive)
    _report_fixes(results, len(fixable))
    return 0


def _discover_fixable(issues: list[Issue]) -> list[Issue]:
    """Filter issues to those with an applicable fix command."""
    return [i for i in issues if i.fix_command and i.fix_strategy in (FixStrategy.AUTO, FixStrategy.CONFIRM)]


def _confirm_fix(issue: Issue) -> bool:
    """Ask user to confirm a single fix interactively."""
    print(f"\n  {issue}")
    print(f"  Fix: {issue.fix_command}")
    answer = input("  Apply? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _apply_single(ctx: HostContext, issue: Issue) -> bool:
    """Execute a single fix command on the remote host. Returns True on success."""
    from ..transport import run_remote

    print(f"  Fixing: {issue.message}")
    result = run_remote(ctx, issue.fix_command)
    if result.returncode == 0:
        print(f"  ✅ Fixed")
        return True
    print(f"  ❌ Failed: {result.stderr[:100]}")
    return False


def _apply_all(
    ctx: HostContext,
    fixable: list[Issue],
    auto: bool = False,
    interactive: bool = False,
) -> list[bool]:
    """Apply fixes based on mode (auto / interactive / strategy-based)."""
    results: list[bool] = []
    for issue in fixable:
        if auto or issue.fix_strategy == FixStrategy.AUTO:
            results.append(_apply_single(ctx, issue))
        elif interactive:
            if _confirm_fix(issue):
                results.append(_apply_single(ctx, issue))
            else:
                results.append(False)
    return results


def _report_fixes(results: list[bool], total: int) -> None:
    """Print fix summary."""
    fixed = sum(results)
    print(f"\n{fixed}/{total} issues fixed.")
