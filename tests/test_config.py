"""Test cho config.py (spec docs/specs/config.md)."""

import json
from pathlib import Path

import pytest

from loc_counter.config import (
    AppConfig,
    ConfigError,
    FilterConfig,
    config_from_dict,
    config_to_dict,
    load_config,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults() -> None:
    """TC-config-01: mặc định đúng §9 và quyết định D3."""
    cfg = load_config(None)
    f = cfg.filters
    assert f.exclude_dirs == (
        "node_modules", "vendor", "dist", "build", "out", "target", ".venv", "venv",
        "__pycache__", ".git", "third_party", "bin", "obj",
    )
    assert f.exclude_globs == (
        "*.min.js", "*.min.css", "*.map", "*.lock", "package-lock.json", "yarn.lock",
        "pnpm-lock.yaml", "*.pb.go", "*_generated.*", "*.designer.cs",
    )
    assert f.exclude_binary is True
    assert f.max_file_size_kb == 1024
    assert f.include_tests is True
    assert f.count_docstrings is False
    assert f.export_mode == "source_only"
    assert f.exclude_languages == ("Text only", "Markdown", "reStructuredText")
    assert cfg.timezone == "Asia/Bangkok"
    assert cfg == AppConfig()


def test_partial_override(tmp_path: Path) -> None:
    """TC-config-02: chỉ ghi đè key có trong file."""
    cfg = load_config(_write(tmp_path, "max_file_size_kb: 10\ninclude_tests: false\n"))
    assert cfg.filters.max_file_size_kb == 10
    assert cfg.filters.include_tests is False
    assert cfg.filters.exclude_dirs == FilterConfig().exclude_dirs
    assert cfg.timezone == "Asia/Bangkok"


def test_list_replaces_default() -> None:
    """TC-config-03: list thay thế, không gộp với mặc định."""
    assert config_from_dict({"exclude_dirs": ["a"]}).filters.exclude_dirs == ("a",)


def test_unknown_key() -> None:
    """TC-config-04: key lạ bị báo lỗi, liệt kê tên key."""
    with pytest.raises(ConfigError, match="exclude_dir"):
        config_from_dict({"exclude_dir": ["a"]})


@pytest.mark.parametrize(
    "data",
    [
        {"exclude_binary": "yes"},
        {"max_file_size_kb": True},
        {"max_file_size_kb": "10"},
        {"exclude_globs": "*.js"},
        {"exclude_dirs": ["a", 1]},
        {"timezone": 7},
    ],
)
def test_wrong_types(data: dict) -> None:
    """TC-config-05: sai kiểu bool / int / list / str."""
    with pytest.raises(ConfigError, match="phải là"):
        config_from_dict(data)


def test_invalid_export_mode() -> None:
    """TC-config-06: export_mode ngoài source_only/full."""
    with pytest.raises(ConfigError, match="export_mode"):
        config_from_dict({"export_mode": "all"})
    assert config_from_dict({"export_mode": "full"}).filters.export_mode == "full"


@pytest.mark.parametrize("value", [0, -5])
def test_non_positive_max_size(value: int) -> None:
    """TC-config-07: max_file_size_kb phải dương."""
    with pytest.raises(ConfigError, match="max_file_size_kb"):
        config_from_dict({"max_file_size_kb": value})


def test_timezone() -> None:
    """TC-config-08: timezone sai báo lỗi, hợp lệ được nhận."""
    with pytest.raises(ConfigError, match="Mars/Base"):
        config_from_dict({"timezone": "Mars/Base"})
    assert config_from_dict({"timezone": "UTC"}).timezone == "UTC"


def test_file_errors_and_empty(tmp_path: Path) -> None:
    """TC-config-09: file không tồn tại, YAML hỏng, không phải mapping, file rỗng."""
    with pytest.raises(ConfigError, match="Không tìm thấy file cấu hình"):
        load_config(tmp_path / "missing.yaml")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(_write(tmp_path, "exclude_dirs: [a\n"))
    with pytest.raises(ConfigError, match="key: value"):
        load_config(_write(tmp_path, "- a\n- b\n"))
    assert load_config(_write(tmp_path, "")) == AppConfig()


def test_config_to_dict() -> None:
    """TC-config-10: dict có 9 key theo thứ tự cố định, list thay tuple, JSON được."""
    data = config_to_dict(AppConfig())
    assert list(data) == [
        "exclude_dirs", "exclude_globs", "exclude_binary", "max_file_size_kb",
        "include_tests", "count_docstrings", "export_mode", "exclude_languages", "timezone",
    ]
    assert isinstance(data["exclude_dirs"], list)
    assert json.loads(json.dumps(data)) == data
    assert config_from_dict(data) == AppConfig()


def test_config_encoding(tmp_path: Path) -> None:
    """TC-config-11: file UTF-16 báo lỗi tiếng Việt; UTF-8 có BOM đọc bình thường."""
    utf16 = tmp_path / "utf16.yaml"
    utf16.write_text("max_file_size_kb: 10\n", encoding="utf-16")
    with pytest.raises(ConfigError, match="UTF-8"):
        load_config(utf16)
    bom = tmp_path / "bom.yaml"
    bom.write_text("max_file_size_kb: 10\n", encoding="utf-8-sig")
    assert load_config(bom).filters.max_file_size_kb == 10
