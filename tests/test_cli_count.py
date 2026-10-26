"""Test cho lệnh `loc-counter count` (spec docs/specs/cli-count.md)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from loc_counter.cli import app

runner = CliRunner()


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    """Thư mục mẫu: a.py 3 dòng code, b.js 2 dòng code."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_bytes(b"import os\nx = 1\n# c\ny = 2\n")
    (root / "b.js").write_bytes(b"let a = 1;\n// c\nlet b = 2;\n")
    return root


def _lines(output: str) -> list[list[str]]:
    return [line.split() for line in output.splitlines()]


def test_table(sample: Path) -> None:
    """TC-cli-count-01: bảng theo ngôn ngữ và dòng TỔNG."""
    result = runner.invoke(app, ["count", str(sample)])
    assert result.exit_code == 0, result.output
    rows = _lines(result.stdout)
    assert ["Python", "1", "3"] in rows
    assert ["JavaScript", "1", "2"] in rows
    assert ["TỔNG", "2", "5"] in rows
    assert "Cảnh báo" not in result.stdout


def test_json(sample: Path) -> None:
    """TC-cli-count-02: --json in JSON hợp lệ, có config."""
    result = runner.invoke(app, ["count", str(sample), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["totals"] == {"files": 2, "code_lines": 5}
    assert data["config"]["max_file_size_kb"] == 1024
    assert data["languages"][0] == {"language": "Python", "files": 1, "code_lines": 3}
    assert data["files"][1] == {"path": "b.js", "language": "JavaScript",
                                "code_lines": 2, "total_lines": 3}
    assert data["warnings"] == []
    assert data["root"] == sample.resolve().as_posix()


def test_by_file(sample: Path) -> None:
    """TC-cli-count-03: --by-file in thêm chi tiết từng file."""
    result = runner.invoke(app, ["count", str(sample), "--by-file"])
    assert result.exit_code == 0, result.output
    rows = _lines(result.stdout)
    assert ["a.py", "Python", "3", "4"] in rows
    assert ["b.js", "JavaScript", "2", "3"] in rows


def test_config_applied(sample: Path, tmp_path: Path) -> None:
    """TC-cli-count-04: --config được áp dụng."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text('exclude_globs: ["*.js"]\n', encoding="utf-8")
    result = runner.invoke(app, ["count", str(sample), "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert ["TỔNG", "1", "3"] in _lines(result.stdout)


def test_missing_dir(tmp_path: Path) -> None:
    """TC-cli-count-05: thư mục không tồn tại → mã 1, lỗi tiếng Việt ra stderr."""
    result = runner.invoke(app, ["count", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "Lỗi: Thư mục không tồn tại" in result.stderr
    assert "Traceback" not in result.output


def test_bad_config(sample: Path, tmp_path: Path) -> None:
    """TC-cli-count-06: config có key lạ → mã 1."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("foo: 1\n", encoding="utf-8")
    result = runner.invoke(app, ["count", str(sample), "--config", str(cfg)])
    assert result.exit_code == 1
    assert "Key cấu hình không hợp lệ" in result.stderr


def test_warnings(sample: Path) -> None:
    """TC-cli-count-07: số cảnh báo trong bảng, chi tiết trong JSON."""
    (sample / "LICENSE").write_bytes(b"MIT\n")
    table = runner.invoke(app, ["count", str(sample)])
    assert "Cảnh báo: 1" in table.stdout
    data = json.loads(runner.invoke(app, ["count", str(sample), "--json"]).stdout)
    assert data["warnings"][0]["kind"] == "unknown_language"
    assert data["warnings"][0]["path"] == "LICENSE"


def test_empty_dir(tmp_path: Path) -> None:
    """TC-cli-count-08: thư mục rỗng → TỔNG 0."""
    result = runner.invoke(app, ["count", str(tmp_path)])
    assert result.exit_code == 0
    assert ["TỔNG", "0", "0"] in _lines(result.stdout)


def test_thousands_separator(tmp_path: Path) -> None:
    """TC-cli-count-09: số có dấu phẩy ngăn cách hàng nghìn."""
    (tmp_path / "a.py").write_bytes(b"x = 1\n" * 1234)
    result = runner.invoke(app, ["count", str(tmp_path)])
    assert ["TỔNG", "1", "1,234"] in _lines(result.stdout)
