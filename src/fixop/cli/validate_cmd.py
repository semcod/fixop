"""CLI validate and check-tls commands.

Extracted from: fixop/cli.py (_cmd_validate, _cmd_check_tls)
"""

from __future__ import annotations

from ..models import Severity
from .output import output_issues


def cmd_validate(args) -> int:
    """Validate deploy artifacts locally."""
    from ..deploy import scan_deploy_dir

    issues = scan_deploy_dir(args.path)
    output_issues(issues, fmt=args.format)
    return 1 if issues else 0


def cmd_check_tls(args) -> int:
    """Check TLS certificates."""
    from ..tls import check_certificates

    issues = check_certificates(args.domains, port=args.port)
    output_issues(issues, fmt=args.format)
    return 1 if any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues) else 0
