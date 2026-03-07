"""CLI drift command — check file drift between README and disk.

Usage:
    fixop drift README.md sandbox/
    fixop drift --ignore-whitespace
    fixop drift --untracked
    fixop drift --format json
"""

from __future__ import annotations

from .output import output_issues


def cmd_drift(args) -> int:
    """Check file drift between markpact README blocks and files on disk."""
    from ..drift import check_file_drift, check_untracked_files

    issues = check_file_drift(
        args.readme,
        args.source_dir,
        ignore_whitespace=args.ignore_whitespace,
    )

    if args.untracked:
        issues += check_untracked_files(args.readme, args.source_dir)

    output_issues(issues, fmt=args.format)

    # Any drift = out of sync → exit 1
    return 1 if issues else 0
