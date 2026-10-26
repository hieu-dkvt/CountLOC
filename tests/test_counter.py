"""Test cho counter.py (spec docs/specs/counter.md)."""

import contextlib
import os
import re
import sys
from pathlib import Path

import pytest

from loc_counter.classifier import LineClassifier
from loc_counter.config import FilterConfig, LocCounterError
from loc_counter.counter import (
    FileLoc,
    LanguageLoc,
    LocWarning,
    WarningKind,
    count_directory,
    decode_text,
)

DEFAULT = FilterConfig()


def _make(root: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


BASIC = {
    "a.py": b"import os\nx = 1\n# c\ny = 2\n",
    "b.js": b"let a = 1;\n// c\nlet b = 2;\n",
    "sub/c.py": b"z = 3\n",
}


def test_basic_count(tmp_path: Path) -> None:
    """TC-counter-01: đếm đa ngôn ngữ, chia theo ngôn ngữ, file sắp xếp theo path."""
    result = count_directory(_make(tmp_path, BASIC), DEFAULT)
    assert result.total_code == 6
    assert result.files == [
        FileLoc("a.py", "Python", 3, 4),
        FileLoc("b.js", "JavaScript", 2, 3),
        FileLoc("sub/c.py", "Python", 1, 1),
    ]
    assert result.by_language() == [
        LanguageLoc("Python", 2, 4),
        LanguageLoc("JavaScript", 1, 2),
    ]
    assert result.warnings == []


def test_configured_exclusions_silent(tmp_path: Path) -> None:
    """TC-counter-02: thư mục/glob/exclude_languages bị loại, không cảnh báo."""
    root = _make(tmp_path, {
        "node_modules/x.js": b"let a;\n",
        "a.min.js": b"let a;\n",
        "README.md": b"# Title\ntext\n",
        "notes.txt": b"hello\n",
        "keep.py": b"x = 1\n",
    })
    result = count_directory(root, DEFAULT)
    assert [f.path for f in result.files] == ["keep.py"]
    assert result.warnings == []


def test_warnings(tmp_path: Path) -> None:
    """TC-counter-03: cảnh báo binary, không nhận diện ngôn ngữ, quá lớn."""
    root = _make(tmp_path, {
        "img.png": b"\x89PNG\r\n\x00\x00data",
        "LICENSE": b"MIT\n",
        "big.py": b"x = 1\n" * 300,
        "ok.py": b"x = 1\n",
    })
    result = count_directory(root, FilterConfig(max_file_size_kb=1))
    assert [f.path for f in result.files] == ["ok.py"]
    assert [(w.path, w.kind) for w in result.warnings] == [
        ("LICENSE", WarningKind.UNKNOWN_LANGUAGE),
        ("big.py", WarningKind.TOO_LARGE),
        ("img.png", WarningKind.BINARY),
    ]
    assert all(w.message for w in result.warnings)
    assert "1 KB" in result.warnings[1].message


def test_exclude_tests(tmp_path: Path) -> None:
    """TC-counter-04: include_tests=false bỏ file test."""
    root = _make(tmp_path, {"tests/test_a.py": b"x = 1\n", "a.py": b"x = 1\n"})
    assert count_directory(root, DEFAULT).total_code == 2
    assert count_directory(root, FilterConfig(include_tests=False)).total_code == 1


def test_encodings(tmp_path: Path) -> None:
    """TC-counter-05: BOM UTF-8, latin-1, CRLF."""
    root = _make(tmp_path, {
        "bom.py": b"\xef\xbb\xbf# c\nx = 1\n",
        "latin.py": b'x = "\xe9"\n',
        "crlf.py": b"# c\r\nx = 1\r\n\r\ny = 2\r\n",
    })
    by_path = {f.path: f for f in count_directory(root, DEFAULT).files}
    assert by_path["bom.py"].code_lines == 1
    assert by_path["latin.py"].code_lines == 1
    assert (by_path["crlf.py"].code_lines, by_path["crlf.py"].total_lines) == (2, 4)
    assert decode_text(b"\xef\xbb\xbfa") == "a"
    assert decode_text(b"\xe9") == "é"


def test_empty_source_file(tmp_path: Path) -> None:
    """TC-counter-06: file rỗng có lexer vẫn được liệt kê với 0 dòng."""
    result = count_directory(_make(tmp_path, {"empty.py": b""}), DEFAULT)
    assert result.files == [FileLoc("empty.py", "Python", 0, 0)]


def test_by_language_order(tmp_path: Path) -> None:
    """TC-counter-07: LOC giảm dần, cùng LOC sắp theo tên."""
    root = _make(tmp_path, {
        "a.js": b"let a;\nlet b;\n",
        "a.go": b"package a\nvar x = 1\n",
        "a.py": b"x = 1\ny = 2\nz = 3\n",
    })
    assert [lang.language for lang in count_directory(root, DEFAULT).by_language()] == [
        "Python", "Go", "JavaScript",
    ]


def test_missing_root(tmp_path: Path) -> None:
    """TC-counter-08: thư mục không tồn tại."""
    with pytest.raises(LocCounterError, match="Thư mục không tồn tại"):
        count_directory(tmp_path / "missing", DEFAULT)
    (tmp_path / "f.py").write_bytes(b"x\n")
    with pytest.raises(LocCounterError):
        count_directory(tmp_path / "f.py", DEFAULT)


def test_cache_by_content(tmp_path: Path) -> None:
    """TC-counter-09: hai file cùng nội dung chỉ phân tích một lần."""
    root = _make(tmp_path, {"a.py": b"x = 1\n", "b.py": b"x = 1\n"})
    clf = LineClassifier()
    count_directory(root, DEFAULT, clf)
    assert (clf.cache_hits, clf.cache_misses) == (1, 1)


def test_reproducible(tmp_path: Path) -> None:
    """TC-counter-10: đếm hai lần cho kết quả giống hệt."""
    root = _make(tmp_path, {**BASIC, "LICENSE": b"x\n"})
    first, second = count_directory(root, DEFAULT), count_directory(root, DEFAULT)
    assert first.files == second.files
    assert first.warnings == second.warnings


def test_posix_paths(tmp_path: Path) -> None:
    """TC-counter-11: đường dẫn trong kết quả dùng '/'."""
    root = _make(tmp_path, {"sub/deep/c.py": b"x = 1\n"})
    assert count_directory(root, DEFAULT).files[0].path == "sub/deep/c.py"


def test_read_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-counter-12: lỗi đọc file → cảnh báo READ_ERROR, không đếm."""
    root = _make(tmp_path, {"a.py": b"x = 1\n", "b.py": b"y = 2\n"})
    original = Path.read_bytes

    def fake_read_bytes(self: Path) -> bytes:
        if self.name == "a.py":
            raise PermissionError(13, "Permission denied", str(self))
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)
    result = count_directory(root, DEFAULT)
    assert [f.path for f in result.files] == ["b.py"]
    assert [(w.path, w.kind) for w in result.warnings] == [("a.py", WarningKind.READ_ERROR)]


def _link_dir(link: Path, target: Path) -> None:
    """Junction trên Windows (không cần quyền admin), symlink nơi khác."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_links_not_followed(tmp_path: Path) -> None:
    """TC-counter-13: symlink/junction thư mục và symlink file không được theo."""
    root = _make(tmp_path, {"real/a.py": b"x = 1\n"})
    _link_dir(root / "link", root / "real")
    # Windows không có quyền tạo symlink file thì chỉ kiểm junction.
    with contextlib.suppress(OSError):
        (root / "file_link.py").symlink_to(root / "real" / "a.py")
    result = count_directory(root, DEFAULT)
    assert [f.path for f in result.files] == ["real/a.py"]
    assert result.total_code == 1


def test_unreadable_subdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-counter-14: thư mục con không liệt kê được → cảnh báo READ_ERROR."""
    root = _make(tmp_path, {"a.py": b"x = 1\n", "sub/b.py": b"y = 2\n"})
    real_walk = os.walk

    def fake_walk(top, onerror=None, followlinks=False):  # noqa: ANN001, ANN202
        for dirpath, dirnames, filenames in real_walk(top, followlinks=followlinks):
            if Path(dirpath).name == "sub":
                onerror(PermissionError(13, "Access is denied", dirpath))
                continue
            yield dirpath, dirnames, filenames

    monkeypatch.setattr("loc_counter.counter.os.walk", fake_walk)
    result = count_directory(root, DEFAULT)
    assert [f.path for f in result.files] == ["a.py"]
    assert [(w.path, w.kind) for w in result.warnings] == [("sub", WarningKind.READ_ERROR)]
    assert "Không đọc được thư mục" in result.warnings[0].message


def test_total_lines_git_semantics(tmp_path: Path) -> None:
    """TC-counter-15: tổng dòng theo git — form feed không tách dòng."""
    root = _make(tmp_path, {"a.py": b"a = 1\n\x0c\nb = 2\n"})
    assert count_directory(root, DEFAULT).files == [FileLoc("a.py", "Python", 2, 3)]


ALL_KINDS = {
    "TOO_LARGE": "too_large",
    "BINARY": "binary",
    "UNKNOWN_LANGUAGE": "unknown_language",
    "READ_ERROR": "read_error",
    "UNSAFE_PATH": "unsafe_path",
    "RENAME_LIMIT": "rename_limit",
    "RENAME_UNRESOLVED": "rename_unresolved",
    "UNATTRIBUTED": "unattributed",
    "MOVED_LINES": "moved_lines",
    "MULTI_USER_HUNK": "multi_user_hunk",
    "SEQUENTIAL_EDIT": "sequential_edit",
    "MISSING_EOL": "missing_eol",
    "PATH_CONFLICT": "path_conflict",
    "CROSS_CHECK": "cross_check",
    "IDENTITY": "identity",
    "WINDOWS_PATH": "windows_path",
}


def test_warning_kind_catalog() -> None:
    """TC-counter-16: WarningKind đủ 16 loại (M1 + M4 + M5), giá trị ổn định, không trùng."""
    assert {k.name: k.value for k in WarningKind} == ALL_KINDS
    values = [k.value for k in WarningKind]
    assert len(set(values)) == len(values)
    assert all(re.fullmatch(r"[a-z_]+", v) for v in values)
    assert WarningKind("unsafe_path") is WarningKind.UNSAFE_PATH


def test_warning_sort_with_m4_kinds() -> None:
    """TC-counter-17: sắp (path, kind) theo giá trị chuỗi; cảnh báo cấp repo (path "") đứng đầu."""
    warnings = [
        LocWarning(WarningKind.MISSING_EOL, "b.py", "m"),
        LocWarning(WarningKind.RENAME_LIMIT, "", "m"),
        LocWarning(WarningKind.BINARY, "b.py", "m"),
        LocWarning(WarningKind.UNSAFE_PATH, "a:b.py", "m"),
    ]
    ordered = sorted(warnings, key=lambda w: (w.path, w.kind))
    assert [(w.kind, w.path) for w in ordered] == [
        (WarningKind.RENAME_LIMIT, ""),
        (WarningKind.UNSAFE_PATH, "a:b.py"),
        (WarningKind.BINARY, "b.py"),
        (WarningKind.MISSING_EOL, "b.py"),
    ]
