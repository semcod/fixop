"""Core data models for fixop.

All modules return list[Issue] from check_*() functions
and FixResult from fix_*() functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Category(Enum):
    DNS = "dns"
    FIREWALL = "firewall"
    CONTAINER = "container"
    SYSTEMD = "systemd"
    TLS = "tls"
    PORT = "port"
    SSH = "ssh"
    DEPLOY = "deploy"


class FixStrategy(Enum):
    AUTO = "auto"        # fixop can fix without confirmation
    CONFIRM = "confirm"  # needs user confirmation
    MANUAL = "manual"    # provides instructions only
    SKIP = "skip"        # informational, no fix needed


@dataclass
class Issue:
    """A detected infrastructure problem."""

    category: Category
    severity: Severity
    message: str
    fix_strategy: FixStrategy = FixStrategy.MANUAL
    fix_command: Optional[str] = None
    details: Optional[str] = None
    host: Optional[str] = None

    def __str__(self) -> str:
        icon = {"info": "ℹ", "warning": "⚠", "error": "❌", "critical": "🔴"}
        return f"{icon.get(self.severity.value, '?')} [{self.category.value}] {self.message}"


@dataclass
class FixResult:
    """Result of applying a fix."""

    issue: Issue
    success: bool
    output: str = ""
    error: str = ""

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return f"{status} {self.issue.message}"


@dataclass
class HostContext:
    """SSH connection context for remote operations."""

    host: str
    user: str = "root"
    port: int = 22
    key: str = "~/.ssh/id_ed25519"
    timeout: int = 10

    @property
    def ssh_cmd(self) -> list[str]:
        """Base SSH command args (without the remote command)."""
        return [
            "ssh",
            "-p", str(self.port),
            "-i", self.key,
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={self.timeout}",
            f"{self.user}@{self.host}",
        ]

    @property
    def scp_cmd(self) -> list[str]:
        """Base SCP command args."""
        return [
            "scp",
            "-P", str(self.port),
            "-i", self.key,
            "-o", "StrictHostKeyChecking=accept-new",
        ]

    def __str__(self) -> str:
        return f"{self.user}@{self.host}:{self.port}"
