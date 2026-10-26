"""Gán tác giả dòng thêm / xóa trong kỳ (§7.2, §8.2, PLAN D22–D31)."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from loc_counter.classifier import LineClassifier
from loc_counter.config import FilterConfig
from loc_counter.counter import LocWarning, WarningKind, decode_text
from loc_counter.filters import BINARY_SNIFF_BYTES, is_binary
from loc_counter.git_repo import DiffEntry, GitRepo, Hunk, LogCommit
from loc_counter.identity import AccountResolver
from loc_counter.snapshot import Snapshots, select_content

logger = logging.getLogger(__name__)

Granularity = Literal["lines", "whole", "skip"]

MAX_MERGE_DEPTH = 64

_SPECIAL_MODES = ("120000", "160000")
_WHITESPACE = b" \t\n\v\f\r"
_PRESENT = "present"
_UNDETERMINED = "undetermined"
_EMPTY: Mapping[int, str] = MappingProxyType({})


@dataclass(frozen=True)
class SideInfo:
    """Một phía (C_START hoặc C_END) của cặp file."""

    path: str
    mode: str
    sha: str
    size: int
    keep: bool
    language: str | None
    binary: bool
    too_large: bool
    line_count: int


@dataclass(frozen=True)
class FileAttribution:
    """Tác giả các dòng trong hunk của một cặp file."""

    entry: DiffEntry
    old: SideInfo | None
    new: SideInfo | None
    granularity: Granularity
    hunks: tuple[Hunk, ...]
    added_by: Mapping[int, str]
    deleted_by: Mapping[int, str]
    moved: frozenset[int]
    renamed_by: str | None
    last_touch_by: str | None
    # M5 (D35): sha commit của từng dòng, cùng khóa và thứ tự với added_by / deleted_by
    added_commit: Mapping[int, str] = field(default_factory=lambda: _EMPTY)
    deleted_commit: Mapping[int, str] = field(default_factory=lambda: _EMPTY)

    @property
    def path(self) -> str:
        """entry.path (đường dẫn tại C_END, file bị xóa → tại C_START)."""
        return self.entry.path


@dataclass(frozen=True)
class UserLineStats:
    """Số dòng thêm / xóa của một account (§8.2)."""

    account: str
    added_lines: int
    deleted_lines: int
    added_code: int
    deleted_code: int
    files: tuple[str, ...]


@dataclass(frozen=True)
class CommitLineStats:
    """Số dòng thêm / xóa đã gán cho một commit (M5, D35 — phục vụ Theo_tuan)."""

    sha: str
    account: str
    added_lines: int
    deleted_lines: int
    added_code: int
    deleted_code: int


@dataclass(frozen=True)
class PeriodAttribution:
    """Kết quả gán tác giả cho cả kỳ."""

    c_start: str | None
    c_end: str
    files: tuple[FileAttribution, ...]
    users: tuple[UserLineStats, ...]
    commit_accounts: Mapping[str, str]
    warnings: tuple[LocWarning, ...]
    commit_stats: tuple[CommitLineStats, ...] = ()

    def file(self, path: str) -> FileAttribution | None:
        """FileAttribution theo path (C_END, hoặc C_START với file bị xóa)."""
        return next((f for f in self.files if f.path == path), None)

    def user(self, account: str) -> UserLineStats | None:
        """Thống kê của account."""
        return next((u for u in self.users if u.account == account), None)

    def commit(self, sha: str) -> CommitLineStats | None:
        """Thống kê dòng của commit; None khi commit không có dòng nào được gán."""
        return next((s for s in self.commit_stats if s.sha == sha), None)


def count_lines(data: bytes) -> int:
    """Số dòng theo git (D8): số '\\n' + 1 nếu đoạn cuối không rỗng."""
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _split_lines(data: bytes) -> list[bytes]:
    """Tách dòng theo git (D8), giữ ký tự xuống dòng."""
    parts = data.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _key(line: bytes) -> bytes:
    """Khóa ghép D28: bỏ mọi khoảng trắng ASCII (như blame -w)."""
    return line.translate(None, _WHITESPACE)


def _key_index(indices: Iterable[int], lines: Sequence[bytes]) -> dict[bytes, deque[int]]:
    """Chỉ mục khóa D28 → hàng đợi chỉ số (giữ thứ tự tăng dần của indices)."""
    index: dict[bytes, deque[int]] = {}
    for i in indices:
        index.setdefault(_key(lines[i]), deque()).append(i)
    return index


def _take(index: dict[bytes, deque[int]], key: bytes) -> int | None:
    """Lấy chỉ số nhỏ nhất chưa dùng có khóa key; None nếu hết."""
    queue = index.get(key)
    return queue.popleft() if queue else None


def _ranges_text(indices: Iterable[int]) -> str:
    """Chỉ số 0-based → khoảng 1-based gộp liền kề, vd. '3–5, 9'."""
    parts: list[str] = []
    ordered = sorted(set(indices))
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1:
            j += 1
        first, last = ordered[i] + 1, ordered[j] + 1
        parts.append(str(first) if first == last else f"{first}–{last}")
        i = j + 1
    return ", ".join(parts)


def _span(start: int, count: int) -> str:
    """Khoảng [start, start + count) dạng 1-based; rỗng → '—'."""
    if count == 0:
        return "—"
    return str(start + 1) if count == 1 else f"{start + 1}–{start + count}"


class _Attributor:
    """Trạng thái dùng chung khi gán tác giả cho một kỳ."""

    def __init__(self, repo: GitRepo, cs: str | None, ce: str,
                 by_sha: Mapping[str, LogCommit], accounts: Mapping[str, str],
                 filters: FilterConfig, blobs: Mapping[str, bytes]) -> None:
        self.repo = repo
        self.cs = cs
        self.ce = ce
        self.by_sha = by_sha
        self.accounts = accounts
        self.filters = filters
        self.blobs = blobs
        self._memo: dict[tuple[str, str, int, str], str] = {}

    # ----- thông tin từng phía (5.2) -----
    def side(self, path: str | None, mode: str | None, sha: str | None) -> SideInfo | None:
        """SideInfo của một phía (5.2); None khi phía đó không có."""
        if path is None or mode is None or sha is None:
            return None
        if mode in _SPECIAL_MODES:
            return SideInfo(path, mode, sha, 0, False, None, False, False, 0)
        data = self.blobs[sha]
        selection = select_content(path, mode, data, self.filters)
        return SideInfo(path, mode, sha, len(data), selection.keep, selection.language,
                        is_binary(data[:BINARY_SNIFF_BYTES]),
                        len(data) > self.filters.max_file_size_kb * 1024, count_lines(data))

    def _is_merge(self, sha: str) -> bool:
        """Commit thuộc kỳ và là merge."""
        commit = self.by_sha.get(sha)
        return commit is not None and commit.is_merge

    # ----- merge (5.6, D23) -----
    def resolve_merge(self, anchor: tuple[str, str, int], merge: str, depth: int) -> str:
        """Commit xóa dòng anchor bên các parent của merge; _UNDETERMINED nếu không xác định."""
        s, path, j = anchor
        memo_key = (s, path, j, merge)
        if memo_key in self._memo:
            return self._memo[memo_key]
        if depth > MAX_MERGE_DEPTH:
            logger.warning("Vượt giới hạn đệ quy merge (%d) cho %s dòng %d", MAX_MERGE_DEPTH,
                           path, j + 1)
            return _UNDETERMINED
        result = merge
        for parent in self.by_sha[merge].parents:
            side = self._parent_side(anchor, parent, depth)
            if side != _PRESENT:
                result = side
                break
        self._memo[memo_key] = result
        return result

    def _parent_side(self, anchor: tuple[str, str, int], parent: str, depth: int) -> str:
        """Kết quả bên một parent của merge: _PRESENT, _UNDETERMINED hoặc commit xóa."""
        s, path, j = anchor
        repo = self.repo
        if repo.is_ancestor(s, parent):
            neo = anchor
        else:
            bases = repo.merge_bases(s, parent)
            if len(bases) != 1:
                return _UNDETERMINED
            fb = repo.blame(s, path, bases[0], detect_moves=False, line_ranges=[(j, j + 1)])[0]
            if not fb.boundary:
                return _PRESENT  # dòng sinh sau base, phía parent chưa từng có
            if not repo.is_ancestor(fb.sha, parent):
                return _UNDETERMINED
            neo = (fb.sha, fb.filename, fb.orig_line)
        neo_commit, neo_path, neo_line = neo
        if neo_commit == parent:
            return _PRESENT
        r = repo.blame(parent, neo_path, neo_commit, reverse=True,
                       line_ranges=[(neo_line, neo_line + 1)])[0]
        if r.sha == parent:
            return _PRESENT
        c = repo.first_commit_after(r.sha, parent, [r.filename])
        if c is None:
            return _UNDETERMINED
        if self._is_merge(c):
            return self.resolve_merge((r.sha, r.filename, r.orig_line), c, depth + 1)
        return c

    # ----- một cặp file -----
    def attribute_file(self, entry: DiffEntry) -> tuple[FileAttribution, list[LocWarning]]:
        """Gán tác giả cho một cặp file (5.2–5.8); trả kết quả và cảnh báo theo thứ tự phát."""
        old = self.side(entry.old_path, entry.old_mode, entry.old_sha)
        new = self.side(entry.new_path, entry.new_mode, entry.new_sha)
        present = [s for s in (old, new) if s is not None]
        warnings: list[LocWarning] = []
        path = entry.path

        if not any(s.keep for s in present):
            return FileAttribution(entry, old, new, "skip", (), _EMPTY, _EMPTY, frozenset(), None,
                                   None), warnings

        renamed_by = self._renamed_by(entry, warnings) if entry.status == "R" else None

        whole = entry.status == "T" or any(
            s.mode in _SPECIAL_MODES or s.binary or s.too_large for s in present)
        if whole:
            paths = list(dict.fromkeys(p for p in (entry.old_path, entry.new_path) if p))
            touched = self.repo.rev_list(self.ce, self.cs, paths)
            last = self.accounts.get(touched[0]) if touched else None
            if last is None:
                warnings.append(LocWarning(WarningKind.UNATTRIBUTED, path,
                                           "Không xác định được người thay đổi cuối của file"))
            return FileAttribution(entry, old, new, "whole", (), _EMPTY, _EMPTY, frozenset(),
                                   renamed_by, last), warnings

        hunks = self._hunks(old, new)
        # added / deleted: chỉ số dòng → sha commit thêm / xóa; account suy ra ở cuối (5.9 bước 4b)
        added: dict[int, str] = {}
        moved: set[int] = set()
        d22: set[int] = set()
        unattr_new: set[int] = set()
        if new is not None:
            self._added_lines(new, hunks, added, moved, d22, unattr_new)
        deleted: dict[int, str] = {}
        alive: set[int] = set()
        unattr_old: set[int] = set()
        if old is not None and self.cs is not None:
            self._deleted_lines(old, hunks, deleted, alive, unattr_old)
        if old is not None and new is not None:
            self._match_moves(old, new, hunks, added, deleted, moved, d22, alive, unattr_new)

        added = dict(sorted(added.items()))
        deleted = dict(sorted(deleted.items()))
        added_by = {i: self.accounts[sha] for i, sha in added.items()}
        deleted_by = {i: self.accounts[sha] for i, sha in deleted.items()}
        self._line_warnings(path, hunks, added_by, deleted_by, moved, unattr_new, unattr_old,
                            warnings)
        return FileAttribution(entry, old, new, "lines", tuple(hunks),
                               MappingProxyType(added_by), MappingProxyType(deleted_by),
                               frozenset(moved), renamed_by, None, MappingProxyType(added),
                               MappingProxyType(deleted)), warnings

    def _hunks(self, old: SideInfo | None, new: SideInfo | None) -> list[Hunk]:
        """Hunk theo 5.3 (D24)."""
        if old is not None and new is not None:
            return self.repo.diff_hunks(old.sha, new.sha)
        if new is not None:
            return [Hunk(0, 0, 0, new.line_count)] if new.line_count else []
        assert old is not None
        return [Hunk(0, old.line_count, 0, 0)] if old.line_count else []

    def _added_lines(self, new: SideInfo, hunks: Sequence[Hunk], added: dict[int, str],
                     moved: set[int], d22: set[int], unattr_new: set[int]) -> None:
        """Dòng thêm (5.4): blame -M -C, boundary → blame lại không -M -C (D22).

        added: chỉ số dòng → sha commit thêm.
        """
        ranges = [(h.new_start, h.new_start + h.new_count) for h in hunks if h.new_count]
        if not ranges:
            return
        boundary: list[int] = []
        for b in self.repo.blame(self.ce, new.path, self.cs, line_ranges=ranges):
            if b.boundary:
                boundary.append(b.line)
                continue
            account = self.accounts.get(b.sha)
            if account is None:
                logger.debug("Không xác định tác giả %s dòng %d", new.path, b.line + 1)
                unattr_new.add(b.line)
            else:
                added[b.line] = b.sha
        if not boundary or self.cs is None:
            return
        again = self.repo.blame(self.ce, new.path, self.cs, detect_moves=False,
                                line_ranges=[(i, i + 1) for i in boundary])
        for b in again:
            if b.boundary:
                continue  # chỉ đổi khoảng trắng / EOL → ứng viên ghép D28 (a)
            account = self.accounts.get(b.sha)
            if account is None:
                logger.debug("Không xác định tác giả %s dòng %d", new.path, b.line + 1)
                unattr_new.add(b.line)
            else:
                added[b.line] = b.sha
                moved.add(b.line)
                d22.add(b.line)

    def _deleted_lines(self, old: SideInfo, hunks: Sequence[Hunk], deleted: dict[int, str],
                       alive: set[int], unattr_old: set[int]) -> None:
        """Dòng xóa (5.5): reverse blame → L → commit xóa; merge → D23.

        deleted: chỉ số dòng → sha commit xóa.
        """
        assert self.cs is not None
        ranges = [(h.old_start, h.old_start + h.old_count) for h in hunks if h.old_count]
        if not ranges:
            return
        groups: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for b in self.repo.blame(self.ce, old.path, self.cs, reverse=True, line_ranges=ranges):
            if b.sha == self.ce:
                alive.add(b.line)
            else:
                groups.setdefault((b.sha, b.filename), []).append((b.line, b.orig_line))
        for (last, filename), lines in groups.items():
            cand = self.repo.first_commit_after(last, self.ce, [filename])
            for line, orig_line in lines:
                deleter = cand
                if cand is not None and self._is_merge(cand):
                    deleter = self.resolve_merge((last, filename, orig_line), cand, 1)
                account = (self.accounts.get(deleter)
                           if deleter not in (None, _UNDETERMINED) else None)
                if account is None:
                    logger.debug("Không xác định người xóa %s dòng %d", old.path, line + 1)
                    unattr_old.add(line)
                else:
                    deleted[line] = deleter

    def _match_moves(self, old: SideInfo, new: SideInfo, hunks: Sequence[Hunk],
                     added: dict[int, str], deleted: dict[int, str], moved: set[int],
                     d22: set[int], alive: set[int], unattr_new: set[int]) -> None:
        """Ghép dời khối trong file theo nội dung (5.7, D28); sao chép sha của dòng được ghép."""
        old_lines = _split_lines(self.blobs[old.sha])
        new_lines = _split_lines(self.blobs[new.sha])
        new_in_hunks = [i for h in hunks for i in range(h.new_start, h.new_start + h.new_count)]
        old_in_hunks = [i for h in hunks for i in range(h.old_start, h.old_start + h.old_count)]
        unassigned = sorted(i for i in new_in_hunks if i not in added and i not in unattr_new)

        # (0) cặp chỉ đổi khoảng trắng: dòng mới chưa có tác giả ↔ dòng cũ còn sống, không gán
        alive_index = _key_index(sorted(alive), old_lines)
        remaining_alive = set(alive)
        still_unassigned: list[int] = []
        for u in unassigned:
            o = _take(alive_index, _key(new_lines[u]))
            if o is None:
                still_unassigned.append(u)
            else:
                remaining_alive.discard(o)

        # (a) dòng mới chưa có tác giả ↔ dòng cũ đã có người xóa
        removed_index = _key_index(sorted(i for i in old_in_hunks if i in deleted), old_lines)
        for u in still_unassigned:
            x = _take(removed_index, _key(new_lines[u]))
            if x is not None:
                added[u] = deleted[x]
                moved.add(u)

        # (b) dòng cũ còn sống ↔ dòng mới được gán theo D22
        d22_index = _key_index(sorted(d22), new_lines)
        for o in sorted(remaining_alive):
            n = _take(d22_index, _key(old_lines[o]))
            if n is not None:
                deleted[o] = added[n]

    def _renamed_by(self, entry: DiffEntry, warnings: list[LocWarning]) -> str | None:
        """Người đổi tên (5.8, D25/D30): author commit thật sự tạo đường dẫn cuối."""
        new_path = entry.new_path
        assert new_path is not None
        commits = [sha for sha in self.repo.rev_list(self.ce, self.cs, [new_path], reverse=True)
                   if sha in self.by_sha]  # commit ngoài kỳ bị bỏ qua
        items: list[tuple[str, str]] = []
        for sha in commits:
            items.append((sha, new_path))
            items.extend((p, new_path) for p in self.by_sha[sha].parents)
        exists = dict(zip(items, self.repo.paths_exist(items), strict=True)) if items else {}
        creator: str | None = None
        for sha in commits:
            parents = self.by_sha[sha].parents
            if exists[(sha, new_path)] and not any(exists[(p, new_path)] for p in parents):
                creator = sha
        account = self.accounts.get(creator) if creator else None
        if account is None:
            warnings.append(LocWarning(
                WarningKind.RENAME_UNRESOLVED, new_path,
                f"Không xác định được người đổi tên {entry.old_path} → {new_path}; "
                "export dùng tên cũ"))
        return account

    @staticmethod
    def _line_warnings(path: str, hunks: Sequence[Hunk], added: Mapping[int, str],
                       deleted: Mapping[int, str], moved: set[int], unattr_new: set[int],
                       unattr_old: set[int], warnings: list[LocWarning]) -> None:
        """UNATTRIBUTED, MOVED_LINES, rồi MULTI_USER_HUNK / SEQUENTIAL_EDIT theo hunk (5.8)."""
        if unattr_new or unattr_old:
            parts = []
            if unattr_new:
                parts.append(f"dòng mới {_ranges_text(unattr_new)}")
            if unattr_old:
                parts.append(f"dòng cũ {_ranges_text(unattr_old)}")
            warnings.append(LocWarning(WarningKind.UNATTRIBUTED, path,
                                       "Không xác định được tác giả: " + "; ".join(parts)))
        if moved:
            warnings.append(LocWarning(WarningKind.MOVED_LINES, path,
                                       "Dòng bị dời được gán cho người dời: dòng mới "
                                       + _ranges_text(moved)))
        for h in hunks:
            dels = {deleted[i] for i in range(h.old_start, h.old_start + h.old_count)
                    if i in deleted}
            adds = {added[k] for k in range(h.new_start, h.new_start + h.new_count)
                    if k in added}
            everyone = dels | adds
            if len(everyone) >= 2:
                warnings.append(LocWarning(
                    WarningKind.MULTI_USER_HUNK, path,
                    f"Hunk dòng cũ {_span(h.old_start, h.old_count)} / dòng mới "
                    f"{_span(h.new_start, h.new_count)} có thay đổi của nhiều user: "
                    + ", ".join(sorted(everyone))))
            if h.old_count and h.new_count and any(x != d for d in dels for x in adds):
                warnings.append(LocWarning(
                    WarningKind.SEQUENTIAL_EDIT, path,
                    f"Dòng cũ {_span(h.old_start, h.old_count)} bị {', '.join(sorted(dels))} "
                    f"xóa và {', '.join(sorted(adds))} viết lại; "
                    "chỉ gán được cho người sửa cuối"))


def _code_flags(side: SideInfo, data: bytes, classifier: LineClassifier) -> list[bool] | None:
    """Cờ code từng dòng của phía file source (keep + language); ngược lại None."""
    if not side.keep or side.language is None:
        return None
    flags = classifier.classify(decode_text(data), side.path, side.sha)
    if len(flags) != side.line_count:
        logger.warning("Số dòng phân loại (%d) khác số dòng git (%d): %s", len(flags),
                       side.line_count, side.path)
    return flags


def _line_stats(files: Sequence[FileAttribution], accounts: Mapping[str, str],
                blobs: Mapping[str, bytes], classifier: LineClassifier
                ) -> tuple[tuple[UserLineStats, ...], tuple[CommitLineStats, ...]]:
    """Thống kê dòng theo account và theo commit, dùng chung cờ code (5.9 bước 1–4a)."""
    stats: dict[str, list[int]] = {a: [0, 0, 0, 0] for a in accounts.values()}
    touched: dict[str, set[str]] = {a: set() for a in stats}
    per_commit: dict[str, list[int]] = {}

    def bucket(account: str) -> list[int]:
        touched.setdefault(account, set())
        return stats.setdefault(account, [0, 0, 0, 0])

    def count(f: FileAttribution, commits: Mapping[int, str], flags: list[bool] | None,
              col: int) -> None:
        for i, sha in commits.items():
            account = accounts[sha]
            is_code = flags is not None and i < len(flags) and flags[i]
            for row in (bucket(account), per_commit.setdefault(sha, [0, 0, 0, 0])):
                row[col] += 1
                row[col + 2] += is_code
            touched[account].add(f.path)

    for f in files:
        if f.granularity == "lines":
            new_flags = (_code_flags(f.new, blobs[f.new.sha], classifier)
                         if f.new is not None and f.added_commit else None)
            count(f, f.added_commit, new_flags, 0)
            old_flags = (_code_flags(f.old, blobs[f.old.sha], classifier)
                         if f.old is not None and f.deleted_commit else None)
            count(f, f.deleted_commit, old_flags, 1)
        for account in (f.renamed_by, f.last_touch_by):
            if account is not None:
                bucket(account)
                touched[account].add(f.path)
    users = tuple(UserLineStats(a, *stats[a], tuple(sorted(touched[a]))) for a in sorted(stats))
    commit_stats = tuple(CommitLineStats(sha, accounts[sha], *per_commit[sha])
                         for sha in sorted(per_commit))
    return users, commit_stats


def attribute_period(repo: GitRepo, snapshots: Snapshots, commits: Sequence[LogCommit],
                     resolver: AccountResolver, filters: FilterConfig,
                     classifier: LineClassifier | None = None) -> PeriodAttribution:
    """Gán tác giả cho mọi dòng trong hunk giữa C_START và C_END (§7.2, D22–D31)."""
    if classifier is None:
        classifier = LineClassifier(filters.count_docstrings)
    cs = snapshots.c_start.sha if snapshots.c_start else None
    ce = snapshots.c_end.sha
    by_sha = {c.sha: c for c in commits}
    accounts = {sha: resolver.resolve(c) for sha, c in by_sha.items()}

    warnings: list[LocWarning] = []
    tree_diff = repo.diff_tree(cs, ce)
    if tree_diff.rename_limit_hit:
        warnings.append(LocWarning(
            WarningKind.RENAME_LIMIT, "",
            "Git bỏ qua nhận diện đổi tên do quá nhiều file; "
            "file đổi tên có thể bị tính là xóa + thêm"))

    shas: list[str] = []
    for e in tree_diff.entries:
        for mode, sha in ((e.old_mode, e.old_sha), (e.new_mode, e.new_sha)):
            if sha is not None and mode not in _SPECIAL_MODES:
                shas.append(sha)
    shas = list(dict.fromkeys(shas))
    blobs = dict(repo.read_blobs(shas)) if shas else {}

    attributor = _Attributor(repo, cs, ce, by_sha, accounts, filters, blobs)
    files: list[FileAttribution] = []
    for entry in tree_diff.entries:
        file_attr, file_warnings = attributor.attribute_file(entry)
        files.append(file_attr)
        warnings.extend(file_warnings)

    users, commit_stats = _line_stats(files, accounts, blobs, classifier)
    warnings.sort(key=lambda w: (w.path, w.kind))
    logger.info("Gán tác giả: %d file, %d dòng thêm, %d dòng xóa, %d cảnh báo", len(files),
                sum(len(f.added_by) for f in files), sum(len(f.deleted_by) for f in files),
                len(warnings))
    return PeriodAttribution(cs, ce, tuple(files), users, MappingProxyType(accounts),
                             tuple(warnings), commit_stats)
