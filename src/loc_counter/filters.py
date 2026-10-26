"""Bộ lọc file source theo đường dẫn và nội dung (§9)."""

from __future__ import annotations

from enum import StrEnum
from fnmatch import fnmatchcase

from loc_counter.config import FilterConfig


class SkipReason(StrEnum):
    """Lý do một file bị loại."""

    EXCLUDED_DIR = "excluded_dir"
    EXCLUDED_GLOB = "excluded_glob"
    TEST_FILE = "test_file"
    TOO_LARGE = "too_large"
    BINARY = "binary"


TEST_DIRS: frozenset[str] = frozenset({"test", "tests"})
TEST_GLOBS: tuple[str, ...] = ("*_test.*", "*.spec.*", "*.test.*")
BINARY_SNIFF_BYTES = 8000


def is_dir_excluded(dir_name: str, config: FilterConfig) -> bool:
    """True nếu thư mục (một thành phần tên) bị loại — dùng để cắt nhánh khi duyệt cây."""
    return dir_name in config.exclude_dirs


def _match_glob(rel_path: str, name: str, pattern: str) -> bool:
    """Pattern chứa '/' so với cả đường dẫn, ngược lại so với tên file."""
    return fnmatchcase(rel_path if "/" in pattern else name, pattern)


def check_path(rel_path: str, config: FilterConfig) -> SkipReason | None:
    """Kiểm tra theo đường dẫn POSIX tương đối (vd. 'src/a/b.py')."""
    parts = rel_path.split("/")
    dirs, name = parts[:-1], parts[-1]
    if any(d in config.exclude_dirs for d in dirs):
        return SkipReason.EXCLUDED_DIR
    if any(_match_glob(rel_path, name, p) for p in config.exclude_globs):
        return SkipReason.EXCLUDED_GLOB
    if not config.include_tests and (
        any(d in TEST_DIRS for d in dirs) or any(fnmatchcase(name, p) for p in TEST_GLOBS)
    ):
        return SkipReason.TEST_FILE
    return None


def is_binary(data: bytes) -> bool:
    """True nếu BINARY_SNIFF_BYTES byte đầu chứa byte NUL (heuristic giống git)."""
    return b"\x00" in data[:BINARY_SNIFF_BYTES]


def check_content(size_bytes: int, head: bytes, config: FilterConfig) -> SkipReason | None:
    """Kiểm tra kích thước rồi binary. head = các byte đầu file."""
    if size_bytes > config.max_file_size_kb * 1024:
        return SkipReason.TOO_LARGE
    if is_binary(head):
        return SkipReason.BINARY
    return None
