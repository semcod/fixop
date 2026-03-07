"""Standalone CLI for fixop.

Usage:
    fixop check --host myserver.com [--user root] [--category dns,firewall,tls]
    fixop fix --host myserver.com [--auto | --interactive]
    fixop validate deploy/
    fixop check-tls domain1.com domain2.com
    fixop drift README.md sandbox/
    fixop check --host myserver.com --format json
"""

from __future__ import annotations

import argparse
import sys

from ..models import Severity


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

    # ── drift ──
    drift_p = sub.add_parser("drift", help="Check file drift between README markpact blocks and disk")
    drift_p.add_argument("readme", nargs="?", default="README.md", help="Path to README.md (default: README.md)")
    drift_p.add_argument("source_dir", nargs="?", default="sandbox/", help="Source directory (default: sandbox/)")
    drift_p.add_argument("--ignore-whitespace", action="store_true", help="Ignore trailing whitespace differences")
    drift_p.add_argument("--untracked", action="store_true", help="Also report untracked files")
    drift_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

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
        from .. import __version__
        print(f"fixop {__version__}")
        return 0

    if not args.command:
        parser.print_help()
        return 1

    dispatch = {
        "check": _dispatch_check,
        "fix": _dispatch_fix,
        "validate": _dispatch_validate,
        "check-tls": _dispatch_check_tls,
        "drift": _dispatch_drift,
        "doctor": _dispatch_doctor,
    }
    handler = dispatch.get(args.command)
    return handler(args) if handler else 0


def _has_errors(issues) -> bool:
    """Return True if any issue is ERROR or CRITICAL."""
    return any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues)


def _dispatch_check(args) -> int:
    from .check_cmd import cmd_check
    return cmd_check(args)


def _dispatch_fix(args) -> int:
    from .fix_cmd import cmd_fix
    return cmd_fix(args)


def _dispatch_validate(args) -> int:
    from .validate_cmd import cmd_validate
    return cmd_validate(args)


def _dispatch_check_tls(args) -> int:
    from .validate_cmd import cmd_check_tls
    return cmd_check_tls(args)


def _dispatch_drift(args) -> int:
    from .drift_cmd import cmd_drift
    return cmd_drift(args)


def _dispatch_doctor(args) -> int:
    from .check_cmd import cmd_doctor
    return cmd_doctor(args)


if __name__ == "__main__":
    sys.exit(main())
