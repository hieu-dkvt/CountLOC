"""Phân loại từng dòng của file: dòng code hay không (§3.4, §6)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from functools import lru_cache
from pathlib import PurePosixPath

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_for_filename
from pygments.token import Token, _TokenType
from pygments.util import ClassNotFound

from loc_counter.config import LocCounterError

_PREPROC_TOKENS = (Token.Comment.Preproc, Token.Comment.PreprocFile)


class NotSourceFileError(LocCounterError):
    """File không có lexer phù hợp."""


def _basename(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).name


@lru_cache(maxsize=4096)
def _lexer_class(basename: str) -> type[Lexer] | None:
    """Lớp lexer Pygments cho basename, None nếu không có."""
    try:
        return type(get_lexer_for_filename(basename))
    except ClassNotFound:
        return None


def detect_language(filename: str, exclude_languages: Iterable[str] = ()) -> str | None:
    """Tên lexer Pygments cho filename (chỉ dùng basename), None nếu không có hoặc bị loại."""
    lexer_cls = _lexer_class(_basename(filename))
    if lexer_cls is None or lexer_cls.name in exclude_languages:
        return None
    return lexer_cls.name


def split_lines(content: str) -> list[str]:
    """Tách dòng theo git: theo "\\n", bỏ "\\r" cuối mỗi dòng.

    Không tạo dòng rỗng sau "\\n" cuối file.
    """
    if not content:
        return []
    parts = content.split("\n")
    if content.endswith("\n"):
        parts.pop()
    return [p[:-1] if p.endswith("\r") else p for p in parts]


def _is_comment(ttype: _TokenType) -> bool:
    """Comment.* là comment, trừ chỉ thị tiền xử lý (PLAN D7)."""
    return ttype in Token.Comment and not any(ttype in t for t in _PREPROC_TOKENS)


def classify_lines(content: str, filename: str, count_docstrings: bool = False) -> list[bool]:
    """Trả về is_code[i] cho từng dòng i (0-based, theo split_lines) của file.

    Ném NotSourceFileError nếu không có lexer.
    """
    lexer_cls = _lexer_class(_basename(filename))
    if lexer_cls is None:
        raise NotSourceFileError(f"Không nhận diện được ngôn ngữ của file: {filename}")
    lexer = lexer_cls(stripnl=False, stripall=False, ensurenl=True)

    lines = split_lines(content)
    n = len(lines)
    if n == 0:
        return []
    # Pygments đổi "\r" đơn thành "\n"; thay bằng khoảng trắng để chỉ số dòng không lệch.
    text = "\n".join(line.replace("\r", " ") for line in lines)

    is_code = [False] * n
    line = 0
    for ttype, value in lexer.get_tokens(text):
        for k, part in enumerate(value.split("\n")):
            if k > 0:
                line += 1
            if line >= n or not part.strip():
                continue
            if _is_comment(ttype):
                continue
            if ttype in Token.Literal.String.Doc and not count_docstrings:
                continue
            is_code[line] = True
    return is_code


def content_sha1(content: bytes) -> str:
    """SHA-1 hex của nội dung (khóa cache cho file không đến từ Git)."""
    return hashlib.sha1(content).hexdigest()


class LineClassifier:
    """Phân loại có cache. Khóa cache = (sha, language, count_docstrings)."""

    def __init__(self, count_docstrings: bool = False) -> None:
        self.count_docstrings = count_docstrings
        self._cache: dict[tuple[str, str, bool], list[bool]] = {}
        self._hits = 0
        self._misses = 0

    def classify(self, content: str, filename: str, sha: str) -> list[bool]:
        """Phân loại dòng, dùng lại kết quả nếu cùng sha và ngôn ngữ."""
        language = detect_language(filename)
        if language is None:
            raise NotSourceFileError(f"Không nhận diện được ngôn ngữ của file: {filename}")
        key = (sha, language, self.count_docstrings)
        cached = self._cache.get(key)
        if cached is not None:
            self._hits += 1
            return list(cached)
        self._misses += 1
        result = classify_lines(content, filename, self.count_docstrings)
        self._cache[key] = result
        return list(result)

    @property
    def cache_hits(self) -> int:
        """Số lần dùng lại kết quả từ cache."""
        return self._hits

    @property
    def cache_misses(self) -> int:
        """Số lần phải phân tích mới."""
        return self._misses
