"""Tests for fixop.deploy module."""

from __future__ import annotations

import pytest

from fixop.deploy import (
    check_unresolved_vars,
    check_placeholders,
    check_files_exist,
    scan_deploy_dir,
)
from fixop.models import Category


class TestCheckUnresolvedVars:
    def test_clean_file(self, tmp_path):
        f = tmp_path / "clean.yml"
        f.write_text("server:\n  port: 8080\n  host: myhost.com\n")
        issues = check_unresolved_vars([str(f)])
        assert len(issues) == 0

    def test_unresolved_dollar_var(self, tmp_path):
        f = tmp_path / "broken.yml"
        f.write_text("image: ${REGISTRY}/app:${VERSION}\n")
        issues = check_unresolved_vars([str(f)])
        assert len(issues) == 2
        assert all(i.category == Category.DEPLOY for i in issues)
        vars_found = {i.message.split("$")[1].split("}")[0].strip("{") for i in issues}
        assert "REGISTRY" in vars_found
        assert "VERSION" in vars_found

    def test_unresolved_template_var(self, tmp_path):
        f = tmp_path / "tmpl.yml"
        f.write_text("domain: {{DOMAIN}}\n")
        issues = check_unresolved_vars([str(f)])
        assert len(issues) == 1
        assert "DOMAIN" in issues[0].message

    def test_skips_comments(self, tmp_path):
        f = tmp_path / "commented.yml"
        f.write_text("# image: ${REGISTRY}/app\n// also: ${SKIP}\n")
        issues = check_unresolved_vars([str(f)])
        assert len(issues) == 0

    def test_nonexistent_file(self):
        issues = check_unresolved_vars(["/nonexistent/file.yml"])
        assert len(issues) == 0


class TestCheckPlaceholders:
    def test_clean_file(self, tmp_path):
        f = tmp_path / "clean.yml"
        f.write_text("domain: myapp.production.com\nemail: admin@myapp.com\n")
        issues = check_placeholders([str(f)])
        assert len(issues) == 0

    def test_example_com(self, tmp_path):
        f = tmp_path / "placeholder.yml"
        f.write_text("domain: your-app.example.com\n")
        issues = check_placeholders([str(f)])
        assert len(issues) == 1

    def test_changeme(self, tmp_path):
        f = tmp_path / "secret.env"
        f.write_text("DB_PASSWORD=changeme\n")
        issues = check_placeholders([str(f)])
        assert len(issues) == 1

    def test_skips_comments(self, tmp_path):
        f = tmp_path / "commented.yml"
        f.write_text("# domain: example.com\n")
        issues = check_placeholders([str(f)])
        assert len(issues) == 0


class TestCheckFilesExist:
    def test_files_present(self, tmp_path):
        (tmp_path / "traefik.yml").write_text("x: 1")
        issues = check_files_exist(["traefik.yml"], base_dir=str(tmp_path))
        assert len(issues) == 0

    def test_files_missing(self, tmp_path):
        issues = check_files_exist(["*.container"], base_dir=str(tmp_path))
        assert len(issues) == 1
        assert issues[0].category == Category.DEPLOY


class TestScanDeployDir:
    def test_scan_with_issues(self, tmp_deploy_dir):
        issues = scan_deploy_dir(str(tmp_deploy_dir))
        # Should find unresolved vars in web.container and placeholders in config.yml
        assert len(issues) > 0
        categories = {i.category for i in issues}
        assert Category.DEPLOY in categories

    def test_nonexistent_dir(self):
        issues = scan_deploy_dir("/nonexistent/deploy")
        assert len(issues) == 0
