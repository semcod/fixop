"""Standalone CLI for fixop.

Usage:
    fixop check --host myserver.com [--user root] [--category dns,firewall,tls]
    fixop fix --host myserver.com [--auto | --interactive]
    fixop validate deploy/
    fixop check-tls domain1.com domain2.com
    fixop check --host myserver.com --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .models import Category, FixStrategy, HostContext, Issue, Severity


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="fixop",
        description="Infrastructure fix operations — detect and repair DNS, firewall, containers, TLS, systemd issues",
    )
    parser.add_argument("--version", action="store_true", help="Show version")

    sub = parser.add_subparsers(dest="command")

    # ── check ──
    check_p = sub.add_parser("check", help="Run infrastructure checks on a remote host")
    check_p.add_argument("--host", required=True, help="Remote host to check")
    check_p.add_argument("--user", default="root", help="SSH user (default: root)")
    check_p.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    check_p.add_argument("--key", default="~/.ssh/id_ed25519", help="SSH key path")
    check_p.add_argument("--category", help="Comma-separated categories: dns,firewall,tls,container,systemd,ssh")
    check_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    check_p.add_argument("--domains", help="Comma-separated domains for TLS checks")
    check_p.add_argument("--containers", help="Comma-separated expected container names")

    # ── fix ──
    fix_p = sub.add_parser("fix", help="Apply fixes for detected issues")
    fix_p.add_argument("--host", required=True, help="Remote host to fix")
    fix_p.add_argument("--user", default="root", help="SSH user")
    fix_p.add_argument("--port", type=int, default=22, help="SSH port")
    fix_p.add_argument("--key", default="~/.ssh/id_ed25519", help="SSH key path")
    fix_p.add_argument("--auto", action="store_true", help="Auto-fix without confirmation")
    fix_p.add_argument("--interactive", action="store_true", help="Confirm each fix interactively")
    fix_p.add_argument("--category", help="Only fix issues in these categories")

    # ── validate ──
    val_p = sub.add_parser("validate", help="Validate deploy artifacts locally")
    val_p.add_argument("path", nargs="?", default="deploy/", help="Directory to validate (default: deploy/)")
    val_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # ── check-tls ──
    tls_p = sub.add_parser("check-tls", help="Check TLS certificates for domains")
    tls_p.add_argument("domains", nargs="+", help="Domains to check")
    tls_p.add_argument("--port", type=int, default=443, help="TLS port (default: 443)")
    tls_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # ── doctor ──
    doc_p = sub.add_parser("doctor", help="Full diagnostic + fix pipeline")
    doc_p.add_argument("--host", required=True, help="Remote host")
    doc_p.add_argument("--user", default="root", help="SSH user")
    doc_p.add_argument("--port", type=int, default=22, help="SSH port")
    doc_p.add_argument("--key", default="~/.ssh/id_ed25519", help="SSH key path")
    doc_p.add_argument("--fix", action="store_true", help="Auto-fix what can be fixed")
    doc_p.add_argument("--domains", help="Comma-separated domains for TLS checks")
    doc_p.add_argument("--containers", help="Comma-separated expected container names")

    args = parser.parse_args(argv)

    if args.version:
        from . import __version__
        print(f"fixop {__version__}")
        return 0

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "check":
        return _cmd_check(args)
    elif args.command == "fix":
        return _cmd_fix(args)
    elif args.command == "validate":
        return _cmd_validate(args)
    elif args.command == "check-tls":
        return _cmd_check_tls(args)
    elif args.command == "doctor":
        return _cmd_doctor(args)

    return 0


def _cmd_check(args) -> int:
    """Run infrastructure checks."""
    from . import check_all

    ctx = HostContext(host=args.host, user=args.user, port=args.port, key=args.key)
    domains = args.domains.split(",") if args.domains else None
    containers = args.containers.split(",") if args.containers else None

    issues = check_all(ctx, domains=domains, containers=containers)

    # Filter by category if specified
    if args.category:
        cats = {c.strip().lower() for c in args.category.split(",")}
        issues = [i for i in issues if i.category.value in cats]

    _output_issues(issues, fmt=args.format)
    return 1 if any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues) else 0


def _cmd_fix(args) -> int:
    """Apply fixes."""
    from . import check_all
    from .ssh import run_remote

    ctx = HostContext(host=args.host, user=args.user, port=args.port, key=args.key)
    issues = check_all(ctx)

    # Filter by category
    if args.category:
        cats = {c.strip().lower() for c in args.category.split(",")}
        issues = [i for i in issues if i.category.value in cats]

    fixable = [i for i in issues if i.fix_command and i.fix_strategy in (FixStrategy.AUTO, FixStrategy.CONFIRM)]

    if not fixable:
        print("No auto-fixable issues found.")
        return 0

    fixed = 0
    for issue in fixable:
        if args.auto or issue.fix_strategy == FixStrategy.AUTO:
            print(f"  Fixing: {issue.message}")
            result = run_remote(ctx, issue.fix_command)
            if result.returncode == 0:
                print(f"  ✅ Fixed")
                fixed += 1
            else:
                print(f"  ❌ Failed: {result.stderr[:100]}")
        elif args.interactive:
            print(f"\n  {issue}")
            print(f"  Fix: {issue.fix_command}")
            answer = input("  Apply? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                result = run_remote(ctx, issue.fix_command)
                if result.returncode == 0:
                    print(f"  ✅ Fixed")
                    fixed += 1
                else:
                    print(f"  ❌ Failed: {result.stderr[:100]}")

    print(f"\n{fixed}/{len(fixable)} issues fixed.")
    return 0


def _cmd_validate(args) -> int:
    """Validate deploy artifacts locally."""
    from .deploy import scan_deploy_dir

    issues = scan_deploy_dir(args.path)
    _output_issues(issues, fmt=args.format)
    return 1 if issues else 0


def _cmd_check_tls(args) -> int:
    """Check TLS certificates."""
    from .tls import check_certificates

    issues = check_certificates(args.domains, port=args.port)
    _output_issues(issues, fmt=args.format)
    return 1 if any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues) else 0


def _cmd_doctor(args) -> int:
    """Full diagnostic + optional fix pipeline."""
    from . import check_all
    from .ssh import run_remote

    ctx = HostContext(host=args.host, user=args.user, port=args.port, key=args.key)
    domains = args.domains.split(",") if args.domains else None
    containers = args.containers.split(",") if args.containers else None

    print(f"🔍 Checking {ctx.host}...\n")
    issues = check_all(ctx, domains=domains, containers=containers)

    if not issues:
        print("✅ No issues found!")
        return 0

    _output_issues(issues, fmt="text")

    if args.fix:
        fixable = [i for i in issues if i.fix_command and i.fix_strategy in (FixStrategy.AUTO, FixStrategy.CONFIRM)]
        if fixable:
            print(f"\n🔧 Applying {len(fixable)} fixes...\n")
            fixed = 0
            for issue in fixable:
                print(f"  Fixing: {issue.message}")
                result = run_remote(ctx, issue.fix_command)
                if result.returncode == 0:
                    print(f"  ✅ Done")
                    fixed += 1
                else:
                    print(f"  ❌ Failed: {result.stderr[:100]}")
            print(f"\n{fixed}/{len(fixable)} fixes applied.")

    errors = sum(1 for i in issues if i.severity in (Severity.ERROR, Severity.CRITICAL))
    return 1 if errors else 0


# ── Output helpers ──────────────────────────────────────


def _output_issues(issues: list[Issue], fmt: str = "text") -> None:
    """Print issues in the requested format."""
    if fmt == "json":
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
        print(json.dumps(data, indent=2))
    else:
        if not issues:
            print("✅ No issues found.")
            return

        # Group by category
        by_cat: dict[str, list[Issue]] = {}
        for i in issues:
            by_cat.setdefault(i.category.value, []).append(i)

        for cat, cat_issues in sorted(by_cat.items()):
            print(f"\n── {cat.upper()} ──")
            for i in cat_issues:
                print(f"  {i}")
                if i.details:
                    for line in i.details.splitlines():
                        print(f"    {line}")
                if i.fix_command:
                    print(f"    Fix: {i.fix_command}")

        # Summary
        errors = sum(1 for i in issues if i.severity in (Severity.ERROR, Severity.CRITICAL))
        warnings = sum(1 for i in issues if i.severity == Severity.WARNING)
        fixable = sum(1 for i in issues if i.fix_command)
        print(f"\n{'❌' if errors else '⚠' if warnings else 'ℹ'} {len(issues)} issues "
              f"({errors} errors, {warnings} warnings, {fixable} fixable)")


if __name__ == "__main__":
    sys.exit(main())
