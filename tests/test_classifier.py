"""Test cho classifier.py (spec docs/specs/classifier.md, ma trận §6.4)."""

import pytest

from loc_counter.classifier import (
    LineClassifier,
    NotSourceFileError,
    classify_lines,
    content_sha1,
    detect_language,
    split_lines,
)
from loc_counter.config import DEFAULT_EXCLUDE_LANGUAGES

# Mỗi mẫu: danh sách (dòng, is_code). Phủ: dòng trống, comment một dòng, block comment
# nhiều dòng, code + comment cuối dòng, chuỗi chứa // hoặc #, docstring (nếu có).
PYTHON = [
    ('"""Module doc."""', False),
    ("", False),
    ("import os  # c", True),
    ("# note", False),
    ('x = "a # b"', True),
    ("'''", False),
    ("block", False),
    ("'''", False),
    ("def f():", True),
    ('    """Doc', False),
    ('    more."""', False),
    ("    return 1", True),
]
JAVASCRIPT = [
    ("/**", False),
    (" * JSDoc", False),
    (" */", False),
    ("const u = 'http://a.com'; // c", True),
    ("// note", False),
    ("/* a", False),
    (" b */", False),
    ("   ", False),
    ("let x = 1;", True),
]
TYPESCRIPT = [
    ("/** doc */", False),
    ('const u: string = "//x"; // c', True),
    ("// note", False),
    ("/* a", False),
    (" b */", False),
    ("", False),
    ("interface A { x: number }", True),
]
JAVA = [
    ("/** doc", False),
    (" */", False),
    ("class A { // c", True),
    ('  String s = "//x";', True),
    ("  // note", False),
    ("", False),
    ("  /* a", False),
    ("  b */", False),
    ("}", True),
]
CSHARP = [
    ("/// <summary>doc</summary>", False),
    ("class A { // c", True),
    ('  string s = "//x";', True),
    ("  // note", False),
    ("", False),
    ("  /* a", False),
    ("  b */", False),
    ("}", True),
]
GO = [
    ("// Package a", False),
    ("package a", True),
    ("/* a", False),
    (" b */", False),
    ('var s = "//x" // c', True),
    ("", False),
]
SQL = [
    ("-- note", False),
    ("SELECT '--x' FROM t; -- c", True),
    ("/* a", False),
    (" b */", False),
    ("", False),
    ("SELECT '#x', 1", True),
]
HTML = [
    ("<!-- a", False),
    (" b -->", False),
    ("<p>x</p> <!-- c -->", True),
    ('<a href="http://x">y</a>', True),
    ("", False),
]
CSS = [
    ("/* a", False),
    (" b */", False),
    ("a { color: red; } /* c */", True),
    ('a[href="//x"] {}', True),
    ("", False),
]


def _content(sample: list[tuple[str, bool]]) -> str:
    return "\n".join(line for line, _ in sample) + "\n"


def _expected(sample: list[tuple[str, bool]]) -> list[bool]:
    return [is_code for _, is_code in sample]


def _check(filename: str, sample: list[tuple[str, bool]]) -> None:
    assert classify_lines(_content(sample), filename) == _expected(sample)


def test_python() -> None:
    """TC-classifier-01: Python — trống, #, ''' block, code + # c, chuỗi chứa #, docstring."""
    _check("a.py", PYTHON)


def test_javascript() -> None:
    """TC-classifier-02: JavaScript — trống, //, /* */, code + //, chuỗi 'http://', JSDoc."""
    _check("a.js", JAVASCRIPT)


def test_typescript() -> None:
    """TC-classifier-03: TypeScript — như JS, có type annotation."""
    _check("a.ts", TYPESCRIPT)


def test_java() -> None:
    """TC-classifier-04: Java — trống, //, block, code + //, chuỗi "//x", Javadoc."""
    _check("A.java", JAVA)


def test_csharp() -> None:
    """TC-classifier-05: C# — trống, //, block, code + //, chuỗi "//x", /// doc."""
    _check("A.cs", CSHARP)


def test_go() -> None:
    """TC-classifier-06: Go — trống, //, block, code + //, chuỗi "//x"."""
    _check("a.go", GO)


def test_sql() -> None:
    """TC-classifier-07: SQL — trống, --, block, code + --, chuỗi '--x' và '#x'."""
    _check("a.sql", SQL)


def test_html() -> None:
    """TC-classifier-08: HTML — trống, <!-- --> nhiều dòng, thẻ + comment, href "http://"."""
    _check("a.html", HTML)


def test_css() -> None:
    """TC-classifier-09: CSS — trống, /* */ nhiều dòng, rule + comment, selector "//x"."""
    _check("a.css", CSS)


def test_count_docstrings_true() -> None:
    """TC-classifier-10: count_docstrings=True tính docstring Python, JSDoc vẫn không."""
    py = classify_lines(_content(PYTHON), "a.py", count_docstrings=True)
    assert py == [line.strip() != "" and not line.startswith("#") for line, _ in PYTHON]
    js = classify_lines(_content(JAVASCRIPT), "a.js", count_docstrings=True)
    assert js == _expected(JAVASCRIPT)


LINE_SEP = chr(0x2028)
NEL = chr(0x85)


@pytest.mark.parametrize(
    ("content", "git_lines"),
    [
        ("\n\nx = 1\n\n\n", 5),
        ("x = 1\r\ny = 2\r\n", 2),
        ("x = 1\ry = 2\r", 1),
        ("x = 1\ny = 2", 2),
        ("x = 1\fy = 2\n", 1),
        (f"# a{LINE_SEP}b{NEL}c\n", 1),
        ("", 0),
        ("\n", 1),
    ],
)
def test_result_length(content: str, git_lines: int) -> None:
    """TC-classifier-11: len(kết quả) == số dòng theo git == len(split_lines(content))."""
    assert len(classify_lines(content, "a.py")) == git_lines == len(split_lines(content))


def test_crlf_and_no_trailing_newline() -> None:
    """TC-classifier-11: CRLF và file không có newline cuối đếm đúng dòng code."""
    assert classify_lines("# c\r\nx = 1\r\n\r\ny = 2", "a.py") == [False, True, False, True]
    assert classify_lines("", "a.py") == []


def test_leading_blank_lines_not_shifted() -> None:
    """TC-classifier-12: dòng trống đầu file không làm lệch chỉ số."""
    assert classify_lines("\n\nx = 1\n", "a.py") == [False, False, True]


@pytest.mark.parametrize("filename", ["LICENSE", "a.unknownext", "data.csv"])
def test_no_lexer(filename: str) -> None:
    """TC-classifier-13: không có lexer → None / NotSourceFileError."""
    assert detect_language(filename) is None
    with pytest.raises(NotSourceFileError, match="Không nhận diện được ngôn ngữ"):
        classify_lines("abc\n", filename)


def test_exclude_languages() -> None:
    """TC-classifier-14: exclude_languages mặc định loại Text/Markdown/RST, giữ JSON."""
    assert detect_language("a.txt", DEFAULT_EXCLUDE_LANGUAGES) is None
    assert detect_language("a.md", DEFAULT_EXCLUDE_LANGUAGES) is None
    assert detect_language("a.rst", DEFAULT_EXCLUDE_LANGUAGES) is None
    assert detect_language("a.json", DEFAULT_EXCLUDE_LANGUAGES) == "JSON"
    assert detect_language("a.txt") == "Text only"


def test_language_names() -> None:
    """TC-classifier-15: tên ngôn ngữ là tên lexer Pygments."""
    names = [detect_language(f"a{ext}") for ext in
             (".py", ".js", ".ts", ".java", ".cs", ".go", ".sql", ".html", ".css")]
    assert names == ["Python", "JavaScript", "TypeScript", "Java", "C#", "Go",
                     "Transact-SQL", "HTML", "CSS"]


def test_cache() -> None:
    """TC-classifier-16: cache theo (sha, ngôn ngữ, count_docstrings)."""
    clf = LineClassifier()
    content = _content(PYTHON)
    sha = content_sha1(content.encode())
    first = clf.classify(content, "a.py", sha)
    second = clf.classify(content, "b.py", sha)
    assert first == second == _expected(PYTHON)
    assert (clf.cache_hits, clf.cache_misses) == (1, 1)
    second[0] = True  # kết quả trả về là bản sao, không làm hỏng cache
    assert clf.classify(content, "a.py", sha) == _expected(PYTHON)
    clf.classify("x = 1\n", "a.js", sha)  # khác ngôn ngữ → miss
    assert clf.cache_misses == 2
    other = LineClassifier(count_docstrings=True)
    assert other.classify(content, "a.py", sha)[0] is True
    assert other.cache_misses == 1


def test_classifier_not_source() -> None:
    """TC-classifier-16: LineClassifier ném NotSourceFileError khi không có lexer."""
    with pytest.raises(NotSourceFileError):
        LineClassifier().classify("abc", "LICENSE", "x")


def test_content_sha1() -> None:
    """TC-classifier-17: SHA-1 hex của nội dung."""
    assert content_sha1(b"abc") == "a9993e364706816aba3e25717850c26c9cd0d89d"


def test_windows_path() -> None:
    """TC-classifier-18: đường dẫn Windows chỉ dùng basename."""
    assert detect_language("src\\a.py") == "Python"
    assert detect_language("src/sub/a.py") == "Python"
    assert classify_lines("x = 1\n", "src\\a.py") == [True]


def test_preprocessor_is_code() -> None:
    """TC-classifier-19: chỉ thị tiền xử lý là code (D7), shebang thì không."""
    cs = "#region A\n#if DEBUG\nint x = 1;\n#endif\n#endregion\n// c\n"
    assert classify_lines(cs, "a.cs") == [True, True, True, True, True, False]
    c = "#include <stdio.h>\n#define N 1\nint x;\n/* c */\n"
    assert classify_lines(c, "a.c") == [True, True, True, False]
    assert classify_lines("#!/usr/bin/env python\nx = 1\n", "a.py") == [False, True]


def test_split_lines_git_semantics() -> None:
    """TC-classifier-20: split_lines theo git (D8)."""
    assert split_lines("a\nb\n") == ["a", "b"]
    assert split_lines("a\r\nb") == ["a", "b"]
    assert split_lines("a\rb\n") == ["a\rb"]
    assert split_lines(f"a\fb{NEL}c{LINE_SEP}d\n") == [f"a\fb{NEL}c{LINE_SEP}d"]
    assert split_lines("\n") == [""]
    assert split_lines("") == []


def test_lone_cr_does_not_shift_lines() -> None:
    """TC-classifier-21: \r đơn trong dòng không làm lệch chỉ số dòng."""
    assert classify_lines("x = 1\r# c\ny = 2\n", "a.py") == [True, True]
    assert classify_lines("# c\rstill comment\nx = 1\n", "a.py") == [False, True]
