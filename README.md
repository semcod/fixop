# fixop — Infrastructure Fix Operations

## AI Cost Tracking

![AI Cost](https://img.shields.io/badge/AI%20Cost-$1.20-green) ![AI Model](https://img.shields.io/badge/AI%20Model-openrouter%2Fqwen%2Fqwen3-coder-next-lightgrey)

This project uses AI-generated code. Total cost: **$1.2000** with **8** AI commits.

Generated on 2026-06-29 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/models/openrouter/qwen/qwen3-coder-next)

---



Detect and repair DNS, firewall, containers, TLS, systemd issues on local and remote servers. **Zero external dependencies** — uses only Python stdlib.

## Install

```bash
pip install fixop
```

## Usage as CLI

```bash
# Check remote server
fixop check --host myserver.com --user root

# Check specific categories
fixop check --host myserver.com --category dns,firewall,tls

# Auto-fix what can be fixed
fixop fix --host myserver.com --auto

# Interactive fix (confirm each)
fixop fix --host myserver.com --interactive

# Validate deploy artifacts locally
fixop validate deploy/

# Check TLS certificates
fixop check-tls app.example.com api.example.com

# Full diagnostic + fix pipeline
fixop doctor --host myserver.com --fix

# JSON output (for CI)
fixop check --host myserver.com --format json
```

## Usage as Library

```python
from fixop import HostContext, check_host_dns, check_ufw_forward_policy, fix_resolv_conf

ctx = HostContext(host="myserver.com", user="root")

# Detect issues
issues = check_host_dns(ctx)
for issue in issues:
    print(issue)  # [dns] Host DNS cannot resolve acme-v02.api.letsencrypt.org

# Run all checks at once
from fixop import check_all
issues = check_all(ctx, domains=["app.example.com"], containers=["traefik", "web"])

# Fix issues
result = fix_resolv_conf(ctx, nameservers=["8.8.8.8", "1.1.1.1"])
print(result)  # Set /etc/resolv.conf to 8.8.8.8, 1.1.1.1

# Classify runtime errors
from fixop import classify_error
issue = classify_error(exit_code=137, stderr="", cmd="podman run app")
print(issue)  # [container] Container killed (OOM or SIGKILL) (exit 137)

# Validate deploy files locally
from fixop import check_unresolved_vars, check_placeholders
issues = check_unresolved_vars(["deploy/traefik.yml", "deploy/web.container"])
issues += check_placeholders(["deploy/config.yml"])
```

## Modules

| Module | Purpose |
|---|---|
| `ssh.py` | SSH transport + connectivity checks |
| `dns.py` | DNS resolution + resolv.conf + systemd-resolved |
| `firewall.py` | UFW forward policy + iptables NAT masquerade |
| `containers.py` | Podman/Docker: health, running status, disk, memory |
| `systemd.py` | Unit management, graceful restart, daemon-reload |
| `tls.py` | Certificate validation (Let's Encrypt, self-signed) |
| `ports.py` | Port conflict detection + resolution |
| `deploy.py` | Deploy artifact validation (unresolved vars, placeholders) |
| `health.py` | HTTP/TCP endpoint health checks |
| `classify.py` | Runtime error classification (exit codes, stderr patterns) |
| `cli.py` | Standalone CLI |

## Key Design Principles

- **Zero dependencies** — stdlib only (`subprocess`, `socket`, `ssl`, `pathlib`, `re`, `json`)
- **SSH via subprocess** — uses the `ssh` command, not paramiko (optional extra)
- **Taskfile-agnostic** — operates on infrastructure primitives, not Taskfile.yml format
- **Dispatch tables** — uses data-driven classification instead of if/elif chains

## License

Licensed under Apache-2.0.
## Author

Tom Sapletta
