"""CLI check and doctor commands.

Extracted from: fixop/cli.py (_cmd_check, _cmd_doctor)
"""

from __future__ import annotations

from ..models import FixStrategy, HostContext, Severity
from .output import output_issues


def cmd_check(args) -> int:
    """Run infrastructure checks."""
    from .. import check_all

    ctx = HostContext(host=args.host, user=args.user, port=args.port, key=args.key)
    domains = args.domains.split(",") if args.domains else None
    containers = args.containers.split(",") if args.containers else None

    issues = check_all(ctx, domains=domains, containers=containers)

    if args.category:
        cats = {c.strip().lower() for c in args.category.split(",")}
        issues = [i for i in issues if i.category.value in cats]

    output_issues(issues, fmt=args.format)
    return 1 if any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues) else 0


def cmd_doctor(args) -> int:
    """Full diagnostic + optional fix pipeline."""
    from .. import check_all

    ctx = HostContext(host=args.host, user=args.user, port=args.port, key=args.key)
    domains = args.domains.split(",") if args.domains else None
    containers = args.containers.split(",") if args.containers else None

    print(f"🔍 Checking {ctx.host}...\n")
    issues = check_all(ctx, domains=domains, containers=containers)

    if not issues:
        print("✅ No issues found!")
        return 0

    output_issues(issues, fmt="text")

    if args.fix:
        _apply_fixes(ctx, issues)

    errors = sum(1 for i in issues if i.severity in (Severity.ERROR, Severity.CRITICAL))
    return 1 if errors else 0


def _apply_fixes(ctx: HostContext, issues) -> None:
    """Apply auto-fixable issues from a doctor run."""
    from ..transport import run_remote

    fixable = [i for i in issues if i.fix_command and i.fix_strategy in (FixStrategy.AUTO, FixStrategy.CONFIRM)]
    if not fixable:
        return

    print(f"\n🔧 Applying {len(fixable)} fixes...\n")
    fixed = 0
    for issue in fixable:
        print(f"  Fixing: {issue.message}")
        result = run_remote(ctx, issue.fix_command)
        if result.returncode == 0:
            print("  ✅ Done")
            fixed += 1
        else:
            print(f"  ❌ Failed: {result.stderr[:100]}")
    print(f"\n{fixed}/{len(fixable)} fixes applied.")
