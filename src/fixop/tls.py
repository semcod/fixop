"""TLS certificate diagnostics.

Covers:
- Let's Encrypt cert validation (expiry, issuer)
- Self-signed cert detection
- ACME challenge readiness (DNS + port 443 open)

Uses only stdlib: ssl, socket — zero external dependencies.
"""

from __future__ import annotations

import socket
import ssl
from datetime import datetime, timezone

from .models import Category, FixStrategy, HostContext, Issue, Severity
from .transport import run_remote


def _connect_and_get_cert(domain: str, port: int) -> dict | None:
    """Connect via TLS and return the peer certificate dict, or raise on error."""
    ctx = ssl.create_default_context()
    with socket.create_connection((domain, port), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
            return ssock.getpeercert()


def _validate_expiry(cert: dict, domain: str, warn_days: int) -> list[Issue]:
    """Check certificate expiry. Returns issues for expired or soon-expiring certs."""
    not_after = cert.get("notAfter", "")
    if not not_after:
        return []
    expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    days_left = (expiry - datetime.now(timezone.utc)).days

    if days_left < 0:
        return [
            Issue(
                category=Category.TLS,
                severity=Severity.CRITICAL,
                message=f"Certificate for {domain} expired {abs(days_left)} days ago",
                fix_strategy=FixStrategy.MANUAL,
                details="Renew the certificate. If using Let's Encrypt, check ACME configuration.",
            )
        ]
    if days_left < warn_days:
        return [
            Issue(
                category=Category.TLS,
                severity=Severity.WARNING,
                message=f"Certificate for {domain} expires in {days_left} days",
                fix_strategy=FixStrategy.MANUAL,
                details="Certificate will expire soon. Check auto-renewal is working.",
            )
        ]
    return []


def _validate_issuer(cert: dict, domain: str) -> list[Issue]:
    """Check if certificate is self-signed."""
    issuer = dict(x[0] for x in cert.get("issuer", ()))
    subject = dict(x[0] for x in cert.get("subject", ()))
    if issuer == subject:
        return [
            Issue(
                category=Category.TLS,
                severity=Severity.WARNING,
                message=f"Self-signed certificate detected for {domain}",
                fix_strategy=FixStrategy.MANUAL,
                details="Use Let's Encrypt or another CA for production certificates.",
            )
        ]
    return []


def _handle_connection_error(e: Exception, domain: str, port: int) -> Issue:
    """Convert a connection exception to an Issue."""
    if isinstance(e, ssl.SSLCertVerificationError):
        return Issue(
            category=Category.TLS,
            severity=Severity.ERROR,
            message=f"TLS verification failed for {domain}: {str(e)[:100]}",
            fix_strategy=FixStrategy.MANUAL,
            details="Certificate is invalid or not trusted. Check ACME configuration.",
        )
    if isinstance(e, ssl.SSLError):
        return Issue(
            category=Category.TLS,
            severity=Severity.ERROR,
            message=f"TLS error for {domain}: {str(e)[:100]}",
        )
    if isinstance(e, socket.timeout):
        return Issue(
            category=Category.TLS,
            severity=Severity.ERROR,
            message=f"Connection to {domain}:{port} timed out",
            details="Port may be blocked by firewall or service not running.",
        )
    if isinstance(e, ConnectionRefusedError):
        return Issue(
            category=Category.TLS,
            severity=Severity.ERROR,
            message=f"Connection refused to {domain}:{port}",
            details="No service listening on port 443. Check Traefik/reverse proxy.",
        )
    return Issue(
        category=Category.TLS,
        severity=Severity.ERROR,
        message=f"Cannot connect to {domain}:{port}: {str(e)[:80]}",
    )


def check_certificate(domain: str, port: int = 443, warn_days: int = 14) -> list[Issue]:
    """Check if domain has a valid TLS certificate.

    Args:
        domain: Domain name to check.
        port: TLS port (default 443).
        warn_days: Warn if cert expires within this many days.
    """
    try:
        cert = _connect_and_get_cert(domain, port)
    except (ssl.SSLError, socket.timeout, ConnectionRefusedError, OSError) as e:
        return [_handle_connection_error(e, domain, port)]

    if not cert:
        return [
            Issue(
                category=Category.TLS,
                severity=Severity.ERROR,
                message=f"No certificate returned for {domain}:{port}",
            )
        ]

    return _validate_expiry(cert, domain, warn_days) + _validate_issuer(cert, domain)


def check_certificates(domains: list[str], port: int = 443, warn_days: int = 14) -> list[Issue]:
    """Check TLS certificates for multiple domains."""
    issues: list[Issue] = []
    for domain in domains:
        issues.extend(check_certificate(domain, port=port, warn_days=warn_days))
    return issues


def check_acme_readiness(ctx: HostContext, container: str = "traefik") -> list[Issue]:
    """Check if ACME (Let's Encrypt) can issue certificates.

    Verifies:
    1. DNS resolves from inside the container
    2. Port 443 is reachable from outside
    3. No rate limit indicators
    """
    issues: list[Issue] = []

    # Check if traefik container is running
    check = run_remote(ctx, f"podman inspect {container} --format '{{{{.State.Running}}}}' 2>/dev/null")
    if check.returncode != 0 or "true" not in check.stdout.lower():
        return []

    # Check if ACME endpoint is resolvable from container
    dns_check = run_remote(
        ctx,
        f"podman exec {container} nslookup acme-v02.api.letsencrypt.org 2>&1 | head -3",
        timeout=15,
    )
    if dns_check.returncode != 0 or "timed out" in dns_check.stdout.lower():
        issues.append(
            Issue(
                category=Category.TLS,
                severity=Severity.CRITICAL,
                message=f"ACME endpoint unreachable from container '{container}' on {ctx.host}",
                fix_strategy=FixStrategy.MANUAL,
                details=(
                    "Let's Encrypt ACME server cannot be reached from inside the container. "
                    "Fix container DNS first (see: fixop check --category dns)."
                ),
                host=ctx.host,
            )
        )

    # Check for ACME-related errors in traefik logs
    logs = run_remote(ctx, f"podman logs --tail 50 {container} 2>&1 | grep -i 'acme\\|letsencrypt\\|certificate'")
    if logs.returncode == 0 and logs.stdout.strip():
        log_lower = logs.stdout.lower()
        if "rate limit" in log_lower:
            issues.append(
                Issue(
                    category=Category.TLS,
                    severity=Severity.WARNING,
                    message=f"Let's Encrypt rate limit detected in {container} logs on {ctx.host}",
                    fix_strategy=FixStrategy.MANUAL,
                    details="Wait for rate limit to reset (1 hour for most limits) or use staging endpoint.",
                    host=ctx.host,
                )
            )
        if "unable to obtain" in log_lower or "acme: error" in log_lower:
            issues.append(
                Issue(
                    category=Category.TLS,
                    severity=Severity.ERROR,
                    message=f"ACME certificate generation failing in {container} on {ctx.host}",
                    fix_strategy=FixStrategy.MANUAL,
                    details=f"Recent ACME logs:\n{logs.stdout.strip()[-300:]}",
                    host=ctx.host,
                )
            )

    return issues
