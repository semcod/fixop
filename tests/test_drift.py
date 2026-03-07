"""Tests for fixop.drift — file drift detection between README and disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from fixop.drift import check_file_drift, check_untracked_files, _extract_blocks
from fixop.models import Severity


class TestExtractBlocks:
    def test_new_format(self):
        text = '''# Project

```yaml markpact:file path=deploy/traefik.yml
entryPoints:
  web:
    address: ":80"
```
'''
        blocks = _extract_blocks(text)
        assert "deploy/traefik.yml" in blocks
        assert 'address: ":80"' in blocks["deploy/traefik.yml"]

    def test_old_format(self):
        text = '''```markpact:file path=main.py
print("hello")
```
'''
        blocks = _extract_blocks(text)
        assert "main.py" in blocks
        assert blocks["main.py"] == 'print("hello")'

    def test_template_meta_ignored(self):
        text = '''```yaml markpact:file path=.env template=true
KEY=${ask:API Key}
```
'''
        blocks = _extract_blocks(text)
        assert ".env" in blocks

    def test_multiple_blocks(self):
        text = '''```yaml markpact:file path=a.yml
a: 1
```

Some text

```yaml markpact:file path=b.yml
b: 2
```
'''
        blocks = _extract_blocks(text)
        assert len(blocks) == 2


class TestCheckFileDrift:
    def test_no_drift(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=config.yml
key: value
```
''')
        target = tmp_path / "sandbox"
        target.mkdir()
        (target / "config.yml").write_text("key: value\n")

        issues = check_file_drift(readme, target)
        assert len(issues) == 0

    def test_drifted_file(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=config.yml
key: original
```
''')
        target = tmp_path / "sandbox"
        target.mkdir()
        (target / "config.yml").write_text("key: modified\n")

        issues = check_file_drift(readme, target)
        assert len(issues) == 1
        assert "drifted" in issues[0].message.lower()
        assert issues[0].severity == Severity.WARNING

    def test_missing_file(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=missing.yml
key: value
```
''')
        target = tmp_path / "sandbox"
        target.mkdir()

        issues = check_file_drift(readme, target)
        assert len(issues) == 1
        assert "missing" in issues[0].message.lower()

    def test_missing_readme(self, tmp_path):
        issues = check_file_drift(tmp_path / "nonexistent.md", tmp_path)
        assert len(issues) == 1
        assert "not found" in issues[0].message.lower()

    def test_no_blocks(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Just a README\n\nNo markpact blocks here.\n")
        issues = check_file_drift(readme, tmp_path)
        assert len(issues) == 0

    def test_ignore_whitespace(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=config.yml
key: value   
extra: data  
```
''')
        target = tmp_path / "sandbox"
        target.mkdir()
        (target / "config.yml").write_text("key: value\nextra: data\n")

        # Without ignore_whitespace, trailing spaces cause drift
        issues = check_file_drift(readme, target, ignore_whitespace=False)
        assert len(issues) == 1

        # With ignore_whitespace, trailing spaces are ignored
        issues = check_file_drift(readme, target, ignore_whitespace=True)
        assert len(issues) == 0

    def test_nested_paths(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=deploy/sub/config.yml
nested: true
```
''')
        target = tmp_path / "sandbox"
        (target / "deploy" / "sub").mkdir(parents=True)
        (target / "deploy" / "sub" / "config.yml").write_text("nested: true\n")

        issues = check_file_drift(readme, target)
        assert len(issues) == 0


class TestCheckUntrackedFiles:
    def test_all_tracked(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=config.yml
key: value
```
''')
        target = tmp_path / "sandbox"
        target.mkdir()
        (target / "config.yml").write_text("key: value\n")

        issues = check_untracked_files(readme, target)
        assert len(issues) == 0

    def test_untracked_file(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text('''```yaml markpact:file path=config.yml
key: value
```
''')
        target = tmp_path / "sandbox"
        target.mkdir()
        (target / "config.yml").write_text("key: value\n")
        (target / "extra.txt").write_text("untracked\n")

        issues = check_untracked_files(readme, target)
        assert len(issues) == 1
        assert "extra.txt" in issues[0].message

    def test_excludes_venv(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# No blocks\n")
        target = tmp_path / "sandbox"
        venv = target / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "stuff.py").write_text("x = 1\n")

        issues = check_untracked_files(readme, target)
        assert len(issues) == 0

    def test_missing_dir(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# No blocks\n")
        issues = check_untracked_files(readme, tmp_path / "nonexistent")
        assert len(issues) == 0
