"""Test cho filters.py (spec docs/specs/filters.md)."""

import pytest

from loc_counter.config import FilterConfig
from loc_counter.filters import (
    SkipReason,
    check_content,
    check_path,
    is_binary,
    is_dir_excluded,
)

DEFAULT = FilterConfig()
NO_TESTS = FilterConfig(include_tests=False)


@pytest.mark.parametrize(
    "path",
    ["node_modules/a.js", "src/vendor/x.go", "a/b/__pycache__/c.py", ".git/config",
     "bin/x.cs", "obj/y.cs", "dist/a.js", "build/a.py", "out/a", "target/a.java",
     ".venv/a.py", "venv/a.py", "third_party/a.c"],
)
def test_excluded_dirs(path: str) -> None:
    """TC-filters-01: mọi thư mục mặc định bị loại, ở mọi độ sâu."""
    assert check_path(path, DEFAULT) is SkipReason.EXCLUDED_DIR


@pytest.mark.parametrize("path", ["src/build.py", "src/dist", "vendor"])
def test_file_named_like_excluded_dir(path: str) -> None:
    """TC-filters-02: tên file trùng tên thư mục loại thì không bị loại."""
    assert check_path(path, DEFAULT) is None


@pytest.mark.parametrize(
    "path",
    ["a.min.js", "web/s.min.css", "x.js.map", "Cargo.lock", "package-lock.json", "yarn.lock",
     "pnpm-lock.yaml", "api.pb.go", "model_generated.ts", "ui/Form1.designer.cs"],
)
def test_excluded_globs(path: str) -> None:
    """TC-filters-03: mọi glob mặc định."""
    assert check_path(path, DEFAULT) is SkipReason.EXCLUDED_GLOB


@pytest.mark.parametrize("path", ["Node_Modules/a.js", "A.MIN.JS"])
def test_case_sensitive(path: str) -> None:
    """TC-filters-04: so khớp phân biệt hoa thường."""
    assert check_path(path, DEFAULT) is None


@pytest.mark.parametrize("path", ["tests/test_a.py", "a_test.go", "a.spec.ts", "a.test.js"])
def test_include_tests_true_keeps_tests(path: str) -> None:
    """TC-filters-05: include_tests=true giữ file test."""
    assert check_path(path, DEFAULT) is None


@pytest.mark.parametrize(
    "path", ["test/a.py", "src/tests/b.py", "a_test.go", "a.spec.ts", "a.test.js"]
)
def test_include_tests_false_excludes(path: str) -> None:
    """TC-filters-06: include_tests=false loại file test."""
    assert check_path(path, NO_TESTS) is SkipReason.TEST_FILE


@pytest.mark.parametrize("path", ["src/testing/a.py", "latest.py", "contest.py", "test.py"])
def test_include_tests_false_no_false_positive(path: str) -> None:
    """TC-filters-07: include_tests=false không loại nhầm."""
    assert check_path(path, NO_TESTS) is None


def test_reason_priority() -> None:
    """TC-filters-08: lý do thư mục ưu tiên trước glob và test."""
    assert check_path("node_modules/a.min.js", NO_TESTS) is SkipReason.EXCLUDED_DIR
    assert check_path("tests/a.min.js", NO_TESTS) is SkipReason.EXCLUDED_GLOB


def test_size_limit() -> None:
    """TC-filters-09: đúng giới hạn vẫn được đếm, vượt thì TOO_LARGE."""
    cfg = FilterConfig(max_file_size_kb=1)
    assert check_content(1024, b"x", cfg) is None
    assert check_content(1025, b"x", cfg) is SkipReason.TOO_LARGE


def test_binary() -> None:
    """TC-filters-10: binary theo byte NUL trong 8000 byte đầu."""
    assert is_binary(b"\x89PNG\x00\x01")
    assert not is_binary(b"abc")
    assert not is_binary(b"")
    assert not is_binary(b"a" * 8000 + b"\x00")
    assert is_binary(b"a" * 7999 + b"\x00")
    assert check_content(6, b"\x89PNG\x00\x01", DEFAULT) is SkipReason.BINARY
    assert check_content(3, b"abc", DEFAULT) is None


def test_too_large_before_binary() -> None:
    """TC-filters-11: quá lớn ưu tiên hơn binary."""
    cfg = FilterConfig(max_file_size_kb=1)
    assert check_content(5000, b"\x00\x00", cfg) is SkipReason.TOO_LARGE


def test_is_dir_excluded() -> None:
    """TC-filters-12: kiểm tra một thành phần tên thư mục."""
    assert is_dir_excluded("node_modules", DEFAULT)
    assert not is_dir_excluded("src", DEFAULT)
