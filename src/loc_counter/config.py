"""Cấu hình, giá trị mặc định và exception gốc của LOC Counter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


class LocCounterError(Exception):
    """Lỗi nghiệp vụ; str(err) là thông báo tiếng Việt cho người dùng."""


class ConfigError(LocCounterError):
    """Lỗi đọc hoặc validate cấu hình."""


ExportMode = Literal["source_only", "full"]

DEFAULT_EXCLUDE_DIRS: tuple[str, ...] = (
    "node_modules", "vendor", "dist", "build", "out", "target", ".venv", "venv",
    "__pycache__", ".git", "third_party", "bin", "obj",
)
DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    "*.min.js", "*.min.css", "*.map", "*.lock", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "*.pb.go", "*_generated.*", "*.designer.cs",
)
DEFAULT_EXCLUDE_LANGUAGES: tuple[str, ...] = ("Text only", "Markdown", "reStructuredText")
DEFAULT_TIMEZONE = "Asia/Bangkok"


@dataclass(frozen=True)
class FilterConfig:
    """Bộ lọc file dùng cho export và đếm (§9)."""

    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS
    exclude_globs: tuple[str, ...] = DEFAULT_EXCLUDE_GLOBS
    exclude_binary: bool = True
    max_file_size_kb: int = 1024
    include_tests: bool = True
    count_docstrings: bool = False
    export_mode: ExportMode = "source_only"
    exclude_languages: tuple[str, ...] = DEFAULT_EXCLUDE_LANGUAGES


@dataclass(frozen=True)
class AppConfig:
    """Toàn bộ cấu hình ứng dụng."""

    filters: FilterConfig = FilterConfig()
    timezone: str = DEFAULT_TIMEZONE


_LIST_KEYS = ("exclude_dirs", "exclude_globs", "exclude_languages")
_BOOL_KEYS = ("exclude_binary", "include_tests", "count_docstrings")
_FILTER_KEYS = tuple(f.name for f in fields(FilterConfig))
_ALL_KEYS = (*_FILTER_KEYS, "timezone")


def load_config(path: Path | None = None) -> AppConfig:
    """Đọc config.yaml; path None → toàn bộ mặc định."""
    if path is None:
        return AppConfig()
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Không tìm thấy file cấu hình: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"File cấu hình phải là văn bản UTF-8: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"Không đọc được file cấu hình: {path} ({exc})") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"File cấu hình không đúng định dạng YAML: {path} ({exc})") from exc
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise ConfigError("File cấu hình phải là danh sách key: value")
    return config_from_dict(data)


def config_from_dict(data: Mapping[str, Any]) -> AppConfig:
    """Validate dict (đã parse từ YAML) và dựng AppConfig."""
    unknown = sorted(str(k) for k in data if k not in _ALL_KEYS)
    if unknown:
        raise ConfigError(f"Key cấu hình không hợp lệ: {', '.join(unknown)}")

    filter_values: dict[str, Any] = {}
    for key in _LIST_KEYS:
        if key in data:
            value = data[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f'Giá trị của "{key}" phải là danh sách chuỗi')
            filter_values[key] = tuple(value)
    for key in _BOOL_KEYS:
        if key in data:
            if not isinstance(data[key], bool):
                raise ConfigError(f'Giá trị của "{key}" phải là true hoặc false')
            filter_values[key] = data[key]
    if "max_file_size_kb" in data:
        value = data["max_file_size_kb"]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError('Giá trị của "max_file_size_kb" phải là số nguyên')
        if value <= 0:
            raise ConfigError("max_file_size_kb phải là số nguyên dương")
        filter_values["max_file_size_kb"] = value
    if "export_mode" in data:
        if data["export_mode"] not in get_args(ExportMode):
            raise ConfigError('export_mode phải là "source_only" hoặc "full"')
        filter_values["export_mode"] = data["export_mode"]

    timezone = data.get("timezone", DEFAULT_TIMEZONE)
    if not isinstance(timezone, str):
        raise ConfigError('Giá trị của "timezone" phải là tên múi giờ (chuỗi)')
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"Múi giờ không hợp lệ: {timezone}") from exc

    return AppConfig(filters=FilterConfig(**filter_values), timezone=timezone)


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    """Dict phẳng, kiểu JSON-able, key theo thứ tự cố định — dùng cho manifest."""
    result: dict[str, Any] = {}
    for key in _FILTER_KEYS:
        value = getattr(config.filters, key)
        result[key] = list(value) if isinstance(value, tuple) else value
    result["timezone"] = config.timezone
    return result
