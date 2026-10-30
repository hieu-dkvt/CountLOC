"""Test cho attribution.py (spec docs/specs/attribution.md, mục 9)."""

from __future__ import annotations

import contextlib
import inspect
import logging
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from loc_counter import attribution
from loc_counter.attribution import (
    MAX_MERGE_DEPTH,
    CommitLineStats,
    FileAttribution,
    PeriodAttribution,
    SideInfo,
    UserLineStats,
    attribute_period,
    count_lines,
)
from loc_counter.config import FilterConfig
from loc_counter.counter import WarningKind
from loc_counter.git_repo import BlameLine, DiffEntry, GitRepo, Hunk, LogCommit, TreeDiff
from loc_counter.identity import AccountResolver, IdentityMap, IdentityRule
from loc_counter.snapshot import Snapshots, find_snapshots, make_period

NL = "\n"
ALICE = ("alice", "alice@example.com")
BOB = ("bob", "bob@example.com")
CAROL = ("carol", "carol@example.com")
A, B, C = "alice@example.com", "bob@example.com", "carol@example.com"
ADMIN = "admin@example.com"
JAN = (date(2026, 1, 1), date(2026, 1, 31))

# Dòng dài (≥ 40 ký tự chữ-số) để git -M / -C nhận diện dòng bị dời (labkit lab_c).
LONG = [f"    result_value_{i} = compute_something_long({i}, factor={i * 3})" for i in range(12)]
VALUES = [f"value_number_{i} = {i}" for i in range(10)]

MULTI = WarningKind.MULTI_USER_HUNK
SEQ = WarningKind.SEQUENTIAL_EDIT
UNATTR = WarningKind.UNATTRIBUTED
MOVED = WarningKind.MOVED_LINES


def j(lines: list[str], nl: str = NL) -> str:
    """Nối dòng, mỗi dòng kết thúc bằng nl."""
    return nl.join(lines) + nl


def split_lines_bytes(data: bytes) -> list[bytes]:
    """Tách dòng theo git (D8): sau mỗi '\\n', giữ nguyên byte xuống dòng."""
    parts = data.split(b"\n")
    out = [p + b"\n" for p in parts[:-1]]
    if parts[-1]:
        out.append(parts[-1])
    return out


def ws_key(line: bytes) -> bytes:
    """Khóa ghép D28: bỏ mọi byte khoảng trắng ASCII (như blame -w)."""
    return bytes(ch for ch in line if ch not in b" \t\n\v\f\r")


@dataclass
class Ctx:
    """Repo đã mở + snapshot + commit trong kỳ."""

    repo: GitRepo
    snaps: Snapshots
    commits: list[LogCommit]

    def attribute(self, resolver: AccountResolver | None = None,
                  filters: FilterConfig | None = None,
                  commits: list[LogCommit] | None = None) -> PeriodAttribution:
        return attribute_period(self.repo, self.snaps,
                                self.commits if commits is None else commits,
                                resolver or AccountResolver(), filters or FilterConfig())


def prepare(src: Any, cache_root: Path, start: date = JAN[0], end: date = JAN[1]) -> Ctx:
    """Mở repo, tìm C_START/C_END trên main, lấy commit trong kỳ (cách gọi chuẩn của spec)."""
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    snaps = find_snapshots(repo, "main", make_period(start, end))
    commits = repo.log_commits(snaps.c_end.sha, snaps.c_start.sha if snaps.c_start else None,
                               mailmap_rev=snaps.c_end.sha)
    return Ctx(repo, snaps, commits)


_BLAME_SIG = inspect.signature(GitRepo.blame)


class BlameSpy:
    """Thay repo.blame, ghi lại tham số mọi lần gọi rồi gọi bản thật."""

    def __init__(self, repo: GitRepo) -> None:
        self.calls: list[dict[str, Any]] = []
        self._orig = repo.blame
        repo.blame = self  # type: ignore[method-assign]

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        bound = _BLAME_SIG.bind(None, *args, **kwargs)
        bound.apply_defaults()
        info = dict(bound.arguments)
        info.pop("self", None)
        self.calls.append(info)
        return self._orig(*args, **kwargs)


def file_of(result: PeriodAttribution, path: str) -> FileAttribution:
    fa = result.file(path)
    assert fa is not None, f"không có file {path}"
    return fa


def user_of(result: PeriodAttribution, account: str) -> UserLineStats:
    stats = result.user(account)
    assert stats is not None, f"không có user {account}"
    return stats


def hunk_tuples(fa: FileAttribution) -> list[tuple[int, int, int, int]]:
    return [(h.old_start, h.old_count, h.new_start, h.new_count) for h in fa.hunks]


def kinds(result: PeriodAttribution, path: str | None = None) -> list[WarningKind]:
    return [w.kind for w in result.warnings if path is None or w.path == path]


def new_hunk_lines(fa: FileAttribution) -> list[int]:
    return [i for h in fa.hunks for i in range(h.new_start, h.new_start + h.new_count)]


def old_hunk_lines(fa: FileAttribution) -> list[int]:
    return [i for h in fa.hunks for i in range(h.old_start, h.old_start + h.old_count)]


# ---------- dựng repo kịch bản ----------
def build_merge_parallel(src: Any, fork_before: bool = False) -> None:
    """TC-11/12 (labkit lab_b): bob xóa v2 trên feat, alice sửa v7 trên main, carol merge.

    x0 (admin, 2025-12-01) app.py = value_number_0..9; C_START (admin, 2025-12-15) chỉ sửa
    other.py; feat tách từ C_START (hoặc x0 nếu fork_before); alice 2026-01-05 trên main,
    bob 2026-01-06 trên feat, carol merge --no-ff 2026-01-07 (parent đầu = main).
    """
    x0 = src.commit("admin0", "2025-12-01T10:00:00+07:00", files={"app.py": j(VALUES)})
    cs = src.commit("admin1", "2025-12-15T10:00:00+07:00", files={"other.py": "o = 1\n"})
    src.git("branch", "feat", x0 if fork_before else cs)
    main = list(VALUES)
    main[7] = "value_number_7 = 77"
    src.commit("alice main", "2026-01-05T10:00:00+07:00", author=ALICE, files={"app.py": j(main)})
    src.checkout("feat")
    src.commit("bob feat", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"app.py": j([v for v in VALUES if v != VALUES[2]])})
    src.checkout("main")
    src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)


def build_merge_self_delete(src: Any) -> None:
    """TC-13 (labkit lab_c b6): alice sửa v1 (main), bob sửa v9 (feat), carol merge xóa v5.

    C_START (admin, 2025-12-15) app.py = value_number_0..9; hai parent của merge đều còn v5.
    """
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(VALUES)})
    src.git("branch", "feat")
    main = list(VALUES)
    main[1] = "value_number_1 = 11"
    src.commit("alice", "2026-01-05T10:00:00+07:00", author=ALICE, files={"app.py": j(main)})
    src.checkout("feat")
    feat = list(VALUES)
    feat[9] = "value_number_9 = 99"
    src.commit("bob", "2026-01-06T10:00:00+07:00", author=BOB, files={"app.py": j(feat)})
    src.checkout("main")
    src.git("merge", "--no-ff", "--no-commit", "feat", date="2026-01-07T10:00:00+07:00",
            author=CAROL)
    merged = list(VALUES)
    merged[1] = "value_number_1 = 11"
    merged[9] = "value_number_9 = 99"
    del merged[5]
    src.write("app.py", j(merged))
    src.git("commit", "-q", "-m", "carol merge", date="2026-01-07T10:00:00+07:00", author=CAROL)


def build_conflict(src: Any) -> None:
    """TC-14 (labkit lab_b b3): xung đột v5 — alice (main) 'alice', bob (feat) 'bob', carol 'carol'.

    C_START = admin1 (2025-12-15); feat tách từ C_START. alice 2026-01-05 sửa v5 + v7;
    bob 2026-01-06 xóa v2 + sửa v5; carol merge feat vào main 2026-01-07 (parent đầu = main),
    giải quyết v5 = 'carol'.
    """
    src.commit("admin0", "2025-12-01T10:00:00+07:00", files={"app.py": j(VALUES)})
    src.commit("admin1", "2025-12-15T10:00:00+07:00", files={"other.py": "o = 1\n"})
    src.git("branch", "feat")
    main = list(VALUES)
    main[7] = "value_number_7 = 77"
    main[5] = "value_number_5 = 'alice'"
    src.commit("alice main", "2026-01-05T10:00:00+07:00", author=ALICE, files={"app.py": j(main)})
    src.checkout("feat")
    feat = [v for v in VALUES if v != VALUES[2]]
    feat[feat.index(VALUES[5])] = "value_number_5 = 'bob'"
    src.commit("bob feat", "2026-01-06T10:00:00+07:00", author=BOB, files={"app.py": j(feat)})
    src.checkout("main")
    src.git("merge", "--no-ff", "--no-commit", "-X", "ours", "feat",
            date="2026-01-07T10:00:00+07:00", author=CAROL)
    resolved = [v for v in main if v != VALUES[2]]
    resolved[resolved.index("value_number_5 = 'alice'")] = "value_number_5 = 'carol'"
    src.write("app.py", j(resolved))
    src.git("commit", "-q", "-m", "carol merge", date="2026-01-07T10:00:00+07:00", author=CAROL)


def build_move_cross_file(src: Any) -> None:
    """TC-16 (labkit lab_c2): bob dời 2 dòng dài cuối a.py sang cuối b.py trong một commit."""
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"a.py": j(LONG), "b.py": j(["x = 1"])})
    src.commit("bob move", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"a.py": j(LONG[:10]), "b.py": j(["x = 1", *LONG[10:12]])})


BLOCK_FILE = LONG[:8]
MOVED_BLOCK = LONG[4:8] + LONG[:4]  # khối 4 dòng đầu dời xuống cuối file


def build_move_block(src: Any) -> None:
    """TC-17: a.py = 8 dòng dài; alice (2026-01-05) dời khối LONG[0:4] xuống cuối file.

    Đã kiểm chứng git 2.55: diff cả kỳ ra hunk (0,4,0,0), (8,0,4,4); reverse blame báo 4 dòng
    cũ "còn sống" còn blame -w (không -M) gán 4 dòng mới cho alice → nhánh D28 (b).
    """
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": j(BLOCK_FILE)})
    src.commit("alice move", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"a.py": j(MOVED_BLOCK)})


def reindent(line: str) -> str:
    return "\t" + line.lstrip(" ")


def build_move_block_ws(src: Any) -> None:
    """TC-18: như TC-17, rồi carol (2026-01-07) đổi thụt lề (4 dấu cách → tab) khối 4 dòng
    đầu file sau khi dời (LONG[4:8], khối bị hoán chỗ).

    Đã kiểm chứng git 2.55: diff cả kỳ ra hunk (0,0,0,4), (4,4,8,0); 4 dòng mới vẫn boundary sau
    cả blame -w -M -C lẫn blame -w; 4 dòng cũ có người xóa (alice) → nhánh D28 (a).
    """
    build_move_block(src)
    ws = [reindent(x) for x in MOVED_BLOCK[:4]] + MOVED_BLOCK[4:]
    src.commit("carol ws", "2026-01-07T10:00:00+07:00", author=CAROL, files={"a.py": j(ws)})


# ---------- TC-01 .. TC-03: repo mẫu §14 ----------
def test_section14_code_stats(section14_repo, cache_root: Path) -> None:
    """TC-attribution-01: §14 theo user — alice 5/2, bob 8/1; commit 'alice late' bị bỏ."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root)
    assert ctx.snaps.c_end.sha == s14.end_sha
    result = ctx.attribute()

    alice, bob = user_of(result, A), user_of(result, B)
    assert (alice.added_code, alice.deleted_code) == (5, 2)
    assert (bob.added_code, bob.deleted_code) == (8, 1)
    late = s14.src.git("rev-parse", "main")
    assert late != s14.end_sha
    assert late not in result.commit_accounts
    assert result.c_end == s14.end_sha
    assert len(result.commit_accounts) == 4
    assert all(i < 19 for i in file_of(result, "app.py").added_by)  # không có dòng late*


def test_section14_line_detail(section14_repo, cache_root: Path) -> None:
    """TC-attribution-02: §14 chi tiết hunk, added_by/deleted_by, users, không cảnh báo."""
    s14 = section14_repo()
    result = prepare(s14.src, cache_root).attribute()

    app = file_of(result, "app.py")
    assert app.entry.status == "M"
    assert app.granularity == "lines"
    assert hunk_tuples(app) == [(2, 2, 2, 0), (13, 1, 11, 0), (15, 0, 12, 7)]
    assert dict(app.deleted_by) == {2: A, 3: A, 13: B}
    assert dict(app.added_by) == {i: A for i in range(12, 19)}
    assert app.renamed_by is None
    assert app.last_touch_by is None

    util = file_of(result, "util.py")
    assert util.entry.status == "A"
    assert util.old is None
    assert hunk_tuples(util) == [(0, 0, 0, 8)]
    assert dict(util.added_by) == {i: B for i in range(8)}
    assert dict(util.deleted_by) == {}

    alice = user_of(result, A)
    assert (alice.added_lines, alice.deleted_lines) == (7, 2)
    assert alice.files == ("app.py",)
    bob = user_of(result, B)
    assert (bob.added_lines, bob.deleted_lines) == (8, 1)
    assert bob.files == ("app.py", "util.py")
    assert [u.account for u in result.users] == [A, B]
    assert result.warnings == ()


def test_section14_empty_start(section14_repo, cache_root: Path) -> None:
    """TC-attribution-03: C_START rỗng — mọi dòng là dòng thêm, không reverse blame."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root, start=date(2025, 12, 1))
    assert ctx.snaps.c_start is None
    spy = BlameSpy(ctx.repo)
    result = ctx.attribute()

    assert result.c_start is None
    assert {f.entry.status for f in result.files} == {"A"}
    for fa in result.files:
        assert fa.new is not None
        assert set(fa.added_by) == set(range(fa.new.line_count))
        assert dict(fa.deleted_by) == {}
    assert user_of(result, ADMIN).added_code == 7
    assert user_of(result, A).added_code == 5
    assert user_of(result, B).added_code == 8
    assert all(u.deleted_code == 0 for u in result.users)
    assert spy.calls
    assert not any(call["reverse"] for call in spy.calls)


# ---------- TC-04: block comment ----------
def test_block_comment_not_code(make_repo, cache_root: Path) -> None:
    """TC-attribution-04: docstring 5 dòng (.py) + /* */ 4 dòng (.js) → 9 dòng, 0 code."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"a.py": "x = 1\n", "b.js": "var x = 1;\n"})
    doc = ['"""Mô-đun ví dụ.', "", "Mô tả dòng ba.", "Mô tả dòng bốn.", '"""']
    block = ["/*", " * chú thích một", " * chú thích hai", " */"]
    src.commit("alice comments", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"a.py": j([*doc, "x = 1"]), "b.js": j([*block, "var x = 1;"])})
    result = prepare(src, cache_root).attribute()

    assert dict(file_of(result, "a.py").added_by) == {i: A for i in range(5)}
    assert dict(file_of(result, "b.js").added_by) == {i: A for i in range(4)}
    alice = user_of(result, A)
    assert alice.added_lines == 9
    assert alice.added_code == 0


# ---------- TC-05 .. TC-10: đổi tên ----------
def test_pure_rename(make_repo, cache_root: Path) -> None:
    """TC-attribution-05: bob git mv (không sửa) → R, không hunk, renamed_by bob, 0 code."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.git("mv", "old.py", "new.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    result = prepare(src, cache_root).attribute()

    assert len(result.files) == 1
    fa = result.files[0]
    assert fa.entry.status == "R"
    assert (fa.entry.old_path, fa.entry.new_path) == ("old.py", "new.py")
    assert fa.path == "new.py"
    assert fa.hunks == ()
    assert dict(fa.added_by) == {}
    assert dict(fa.deleted_by) == {}
    assert fa.renamed_by == B
    bob = user_of(result, B)
    assert bob.added_code == 0
    assert bob.deleted_code == 0
    assert (bob.added_lines, bob.deleted_lines) == (0, 0)
    assert bob.files == ("new.py",)
    assert result.warnings == ()


@pytest.mark.parametrize("order", ["mv_then_edit", "edit_then_mv"])
def test_rename_with_edit(make_repo, cache_root: Path, order: str) -> None:
    """TC-attribution-06: rename + alice thêm 1 dòng (cả hai thứ tự) → added_by {10: alice}."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    edited = j([*VALUES, "alice_line = 1"])
    if order == "mv_then_edit":
        src.git("mv", "old.py", "new.py")
        src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
        src.commit("alice edit", "2026-01-06T10:00:00+07:00", author=ALICE,
                   files={"new.py": edited})
    else:
        src.commit("alice edit", "2026-01-05T10:00:00+07:00", author=ALICE,
                   files={"old.py": edited})
        src.git("mv", "old.py", "new.py")
        src.commit("bob mv", "2026-01-06T10:00:00+07:00", author=BOB)
    result = prepare(src, cache_root).attribute()

    assert len(result.files) == 1
    fa = result.files[0]
    assert fa.entry.status == "R"
    assert dict(fa.added_by) == {10: A}
    assert dict(fa.deleted_by) == {}
    assert fa.renamed_by == B


def test_rename_chain(make_repo, cache_root: Path) -> None:
    """TC-attribution-07: bob a→b, alice b→c → R a→c, renamed_by alice."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": j(VALUES)})
    src.git("mv", "a.py", "b.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    src.git("mv", "b.py", "c.py")
    src.commit("alice mv", "2026-01-06T10:00:00+07:00", author=ALICE)
    result = prepare(src, cache_root).attribute()

    assert len(result.files) == 1
    fa = result.files[0]
    assert fa.entry.status == "R"
    assert (fa.entry.old_path, fa.entry.new_path) == ("a.py", "c.py")
    assert fa.renamed_by == A


def test_rename_via_merge_forked_before_start(make_repo, cache_root: Path) -> None:
    """TC-attribution-08: bob đổi tên trên feat (tách trước C_START), carol merge → bob (D30).

    labkit lab_d2: x0 admin old.py (2025-12-01); C_START admin z.py (2025-12-15); feat từ x0,
    bob mv old.py→new.py ngày 2025-12-10; alice sửa old.py trên main 2026-01-05; carol merge
    2026-01-07.
    """
    src = make_repo()
    x0 = src.commit("admin0", "2025-12-01T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.commit("admin1", "2025-12-15T10:00:00+07:00", files={"z.py": "z = 1\n"})
    src.git("branch", "feat", x0)
    src.commit("alice edit", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"old.py": j([*VALUES, "alice_line = 1"])})
    src.checkout("feat")
    src.git("mv", "old.py", "new.py")
    bob_mv = src.commit("bob mv", "2025-12-10T10:00:00+07:00", author=BOB)
    src.checkout("main")
    src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)
    result = prepare(src, cache_root).attribute()

    assert result.commit_accounts[bob_mv] == B
    fa = file_of(result, "new.py")
    assert fa.entry.status == "R"
    assert fa.entry.old_path == "old.py"
    assert fa.renamed_by == B
    assert fa.renamed_by != C


def test_rename_unresolved_directory(make_repo, cache_root: Path) -> None:
    """TC-attribution-09: đổi tên tới x/y.py khi parent có thư mục x/y.py → RENAME_UNRESOLVED."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={
        "old.py": j(VALUES),
        "x/y.py/inner.py": j([f"inner_completely_different_{i} = 'zzz'" for i in range(6)]),
    })
    src.remove("x/y.py/inner.py")
    src.remove("old.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB, files={"x/y.py": j(VALUES)})
    result = prepare(src, cache_root).attribute()

    fa = file_of(result, "x/y.py")
    assert fa.entry.status == "R"
    assert fa.entry.old_path == "old.py"
    assert fa.renamed_by is None
    unresolved = [w for w in result.warnings if w.kind == WarningKind.RENAME_UNRESOLVED]
    assert len(unresolved) == 1
    assert unresolved[0].path == "x/y.py"
    assert unresolved[0].message == ("Không xác định được người đổi tên old.py → x/y.py; "
                                     "export dùng tên cũ")


def test_rename_low_similarity(make_repo, cache_root: Path) -> None:
    """TC-attribution-10: bob mv rồi sửa > 50% dòng → D + A; dòng chung không gán.

    labkit lab_d "rename-with-big-edit": commit mv thuần rồi commit sửa (cùng bob).
    """
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.git("mv", "old.py", "new.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    bob_lines = [f"bob_new_value_{i} = {i * 7}" for i in range(8)]
    src.commit("bob big edit", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"new.py": j(VALUES[:4] + bob_lines)})
    result = prepare(src, cache_root).attribute()

    assert [(f.entry.status, f.path) for f in result.files] == [("A", "new.py"),
                                                                 ("D", "old.py")]
    old, new = file_of(result, "old.py"), file_of(result, "new.py")
    assert hunk_tuples(old) == [(0, 10, 0, 0)]
    assert hunk_tuples(new) == [(0, 0, 0, 12)]
    for i in range(4):  # dòng chung VALUES[0:4]
        assert i not in old.deleted_by
        assert i not in new.added_by
    assert dict(new.added_by) == {i: B for i in range(4, 12)}
    assert dict(old.deleted_by) == {i: B for i in range(4, 10)}


# ---------- TC-11 .. TC-15: merge ----------
def assert_merge_parallel(result: PeriodAttribution) -> None:
    app = file_of(result, "app.py")
    assert hunk_tuples(app) == [(2, 1, 2, 0), (7, 1, 6, 1)]
    assert dict(app.deleted_by) == {2: B, 7: A}
    assert dict(app.added_by) == {6: A}
    carol = user_of(result, C)
    assert (carol.added_lines, carol.deleted_lines) == (0, 0)
    assert carol.files == ()
    assert result.warnings == ()


def test_merge_parallel(make_repo, cache_root: Path) -> None:
    """TC-attribution-11: merge song song — v2 → bob, v7 cũ/mới → alice, carol không có dòng."""
    src = make_repo()
    build_merge_parallel(src)
    assert_merge_parallel(prepare(src, cache_root).attribute())


def test_merge_parallel_fork_before_start(make_repo, cache_root: Path) -> None:
    """TC-attribution-12: như TC-11 nhưng feat tách trước C_START → v2 → bob, v7 → alice."""
    src = make_repo()
    build_merge_parallel(src, fork_before=True)
    ctx = prepare(src, cache_root)
    calls: list[tuple[str, str]] = []
    real = ctx.repo.merge_bases

    def spy(a: str, b: str) -> list[str]:
        calls.append((a, b))
        return real(a, b)

    ctx.repo.merge_bases = spy  # type: ignore[method-assign]
    result = ctx.attribute()

    assert_merge_parallel(result)
    assert calls, "D23 với nhánh tách trước C_START phải dùng merge_bases"


def test_merge_self_delete(make_repo, cache_root: Path) -> None:
    """TC-attribution-13: hai parent đều còn v5, merge (carol) xóa v5 → v5 → carol."""
    src = make_repo()
    build_merge_self_delete(src)
    result = prepare(src, cache_root).attribute()

    app = file_of(result, "app.py")
    assert app.deleted_by.get(5) == C
    assert app.deleted_by.get(1) == A
    assert app.deleted_by.get(9) == B
    assert user_of(result, C).deleted_lines == 1


def test_merge_conflict_resolution(make_repo, cache_root: Path) -> None:
    """TC-attribution-14: xung đột v5 — cũ → alice, mới → carol; SEQUENTIAL_EDIT + MULTI_USER."""
    src = make_repo()
    build_conflict(src)
    result = prepare(src, cache_root).attribute()

    app = file_of(result, "app.py")
    assert hunk_tuples(app) == [(2, 1, 2, 0), (5, 1, 4, 1), (7, 1, 6, 1)]
    assert app.deleted_by.get(5) == A
    assert app.added_by.get(4) == C
    assert app.deleted_by.get(2) == B
    assert kinds(result, "app.py") == [MULTI, SEQ]
    multi, seq = [w for w in result.warnings if w.path == "app.py"]
    assert multi.message.endswith(f"có thay đổi của nhiều user: {A}, {C}")
    assert re.fullmatch(rf"Dòng cũ 6(–6)? bị {A} xóa và {C} viết lại; "
                        r"chỉ gán được cho người sửa cuối", seq.message)


def test_merge_guard_parent_equals_anchor(make_repo, cache_root: Path) -> None:
    """TC-attribution-15: parent của merge == L → không blame với since == end, không GitError."""
    src = make_repo()
    build_merge_self_delete(src)
    ctx = prepare(src, cache_root)
    spy = BlameSpy(ctx.repo)
    result = ctx.attribute()

    assert file_of(result, "app.py").deleted_by.get(5) == C
    assert spy.calls
    assert not [c for c in spy.calls if c["since"] is not None and c["since"] == c["end"]]


def test_merge_depth_limit(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                           caplog: pytest.LogCaptureFixture) -> None:
    """TC-attribution-15: MAX_MERGE_DEPTH = 0 → dòng cũ giữ + UNATTRIBUTED, log WARNING."""
    assert MAX_MERGE_DEPTH == 64
    src = make_repo()
    build_merge_parallel(src)
    ctx = prepare(src, cache_root)
    monkeypatch.setattr(attribution, "MAX_MERGE_DEPTH", 0)
    caplog.set_level(logging.DEBUG)
    result = ctx.attribute()

    app = file_of(result, "app.py")
    assert 2 not in app.deleted_by  # v2: ứng viên là merge → vượt độ sâu → giữ
    unattr = [w for w in result.warnings if w.kind == UNATTR]
    assert [w.path for w in unattr] == ["app.py"]
    assert unattr[0].message.startswith("Không xác định được tác giả: ")
    assert re.search(r"dòng cũ (\d+(–\d+)?, )*3(\D|$)", unattr[0].message)
    assert any(r.levelno == logging.WARNING and r.name.startswith("loc_counter.attribution")
               for r in caplog.records)


# ---------- TC-16 .. TC-18: dòng bị dời ----------
def test_move_to_other_file(make_repo, cache_root: Path) -> None:
    """TC-attribution-16: bob dời 2 dòng dài a.py → b.py → b.py gán bob (moved), a.py xóa bob."""
    src = make_repo()
    build_move_cross_file(src)
    result = prepare(src, cache_root).attribute()

    b = file_of(result, "b.py")
    assert hunk_tuples(b) == [(1, 0, 1, 2)]
    assert dict(b.added_by) == {1: B, 2: B}
    assert b.moved == frozenset({1, 2})
    a = file_of(result, "a.py")
    assert hunk_tuples(a) == [(10, 2, 10, 0)]
    assert dict(a.deleted_by) == {10: B, 11: B}
    assert a.moved == frozenset()
    moved = [w for w in result.warnings if w.kind == MOVED]
    assert [(w.path, w.message) for w in moved] == [
        ("b.py", "Dòng bị dời được gán cho người dời: dòng mới 2–3")]
    assert kinds(result) == [MOVED]


def test_move_block_in_file(make_repo, cache_root: Path) -> None:
    """TC-attribution-17: alice dời khối 4 dòng xuống cuối → 4 mới + 4 cũ gán alice, MOVED_LINES."""
    src = make_repo()
    build_move_block(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    fa = file_of(result, "a.py")
    assert fa.granularity == "lines"
    assert hunk_tuples(fa) == [(0, 4, 0, 0), (8, 0, 4, 4)]
    # tiền điều kiện kịch bản D28 (b): reverse blame báo 4 dòng cũ "còn sống"
    ce = ctx.snaps.c_end.sha
    rev = ctx.repo.blame(ce, "a.py", ctx.snaps.c_start.sha, reverse=True, line_ranges=[(0, 4)])
    assert [b.sha for b in rev] == [ce] * 4
    # mọi dòng trong hunk đã gán (không nhân đôi khối)
    assert dict(fa.added_by) == {4: A, 5: A, 6: A, 7: A}
    assert dict(fa.deleted_by) == {0: A, 1: A, 2: A, 3: A}
    assert fa.moved == frozenset({4, 5, 6, 7})
    assert [(w.kind, w.message) for w in result.warnings] == [
        (MOVED, "Dòng bị dời được gán cho người dời: dòng mới 5–8")]


def test_move_block_then_reindent(make_repo, cache_root: Path) -> None:
    """TC-attribution-18: dời khối rồi carol đổi thụt lề → dòng mới vẫn được gán (D28 a)."""
    src = make_repo()
    build_move_block_ws(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    fa = file_of(result, "a.py")
    assert hunk_tuples(fa) == [(0, 0, 0, 4), (4, 4, 8, 0)]
    # tiền điều kiện kịch bản D28 (a): dòng mới vẫn boundary sau blame -w (không -M -C)
    cs, ce = ctx.snaps.c_start.sha, ctx.snaps.c_end.sha
    again = ctx.repo.blame(ce, "a.py", cs, detect_moves=False, line_ranges=[(0, 4)])
    assert all(b.boundary for b in again)

    new_lines = split_lines_bytes(ctx.repo.read_blob(fa.new.sha))
    old_lines = split_lines_bytes(ctx.repo.read_blob(fa.old.sha))
    block = [i for i, line in enumerate(new_lines) if line.startswith(b"\t")]
    assert block == [0, 1, 2, 3]
    used: set[int] = set()
    for i in block:
        assert i in fa.added_by, f"dòng mới {i + 1} của khối bị bỏ"
        assert i in fa.moved
        key = ws_key(new_lines[i])
        matches = [x for x in fa.deleted_by if x not in used and ws_key(old_lines[x]) == key]
        assert matches, f"không có dòng cũ cùng nội dung với dòng mới {i + 1}"
        used.add(matches[0])
        assert fa.added_by[i] == fa.deleted_by[matches[0]]
    assert dict(fa.added_by) == {0: A, 1: A, 2: A, 3: A}
    assert dict(fa.deleted_by) == {4: A, 5: A, 6: A, 7: A}
    assert [(w.kind, w.message) for w in result.warnings] == [
        (MOVED, "Dòng bị dời được gán cho người dời: dòng mới 1–4")]


# ---------- TC-19: tái dựng "mọi user" = C_END ----------
def rebuild_all_users(fa: FileAttribution, old_data: bytes, new_data: bytes,
                      users: set[str]) -> bytes:
    """Áp §7.3: dòng ngoài hunk giữ; trong hunk dòng cũ giữ nếu người xóa không thuộc users,
    dòng mới thêm nếu người thêm thuộc users."""
    old_lines, new_lines = split_lines_bytes(old_data), split_lines_bytes(new_data)
    out: list[bytes] = []
    pos = 0
    for h in fa.hunks:
        out += old_lines[pos:h.old_start]
        for i in range(h.old_start, h.old_start + h.old_count):
            if fa.deleted_by.get(i) not in users:
                out.append(old_lines[i])
        for k in range(h.new_start, h.new_start + h.new_count):
            if fa.added_by.get(k) in users:
                out.append(new_lines[k])
        pos = h.old_start + h.old_count
    out += old_lines[pos:]
    return b"".join(out)


DAVE = ("dave", "dave@example.com")
D = "dave@example.com"
WRAP_START = ["def g():", "    do_g()", "    pass", "", "def f():", "    work_one()", "    pass",
              "z = 3"]


def build_ws_vs_deleted_elsewhere(src: Any) -> None:
    """TC-34 (review Major 1): bob chỉ thụt lề `pass` của f(), alice xóa `pass` giống hệt của g().

    C_START (admin, 2025-12-15) m.py = WRAP_START; alice 2026-01-05 xóa `pass` trong g()
    (dòng cũ 2); bob 2026-01-06 bọc thân f() trong `if cond:` (thụt lề work_one() và `pass`).
    """
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"m.py": j(WRAP_START)})
    s1 = [line for i, line in enumerate(WRAP_START) if i != 2]
    src.commit("alice del pass in g", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"m.py": j(s1)})
    s2 = ["def g():", "    do_g()", "", "def f():", "    if cond:", "        work_one()",
          "        pass", "z = 3"]
    src.commit("bob wrap in if", "2026-01-06T10:00:00+07:00", author=BOB, files={"m.py": j(s2)})


LONG_Z = "result_total = compute_the_total_amount(orders, discount_rate)"


def build_ws_vs_moved_in(src: Any) -> None:
    """TC-35 (review Major 2): carol thụt lề dòng Z ở a.py; bob dời Z giống hệt b.py → a.py.

    C_START (admin, 2025-12-15): a.py, b.py đều có dòng Z (≥ 40 ký tự) thụt 4 dấu cách;
    carol 2026-01-05 thụt lại Z của a.py thành 8 dấu cách; bob 2026-01-06 dời Z của b.py
    xuống cuối a.py.
    """
    a = ["def run():", "    " + LONG_Z, "    other_call_here()", "x = 1"]
    b = ["def helper():", "    " + LONG_Z, "    return None"]
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": j(a), "b.py": j(b)})
    a2 = ["def run():", "        " + LONG_Z, "    other_call_here()", "x = 1"]
    src.commit("carol reindent", "2026-01-05T10:00:00+07:00", author=CAROL,
               files={"a.py": j(a2)})
    src.commit("bob move line", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"a.py": j([*a2, "    " + LONG_Z]),
                      "b.py": j(["def helper():", "    return None"])})


REBUILD_CASES = {
    "tc02_section14": None,
    "tc11_merge_parallel": build_merge_parallel,
    "tc14_conflict": build_conflict,
    "tc16_move_cross_file": build_move_cross_file,
    "tc17_move_block": build_move_block,
    "tc18_move_block_ws": build_move_block_ws,
    "tc34_ws_vs_deleted_elsewhere": build_ws_vs_deleted_elsewhere,
    "tc35_ws_vs_moved_in": build_ws_vs_moved_in,
}
# Kịch bản có dòng chỉ đổi khoảng trắng: D22 giữ bản C_START của dòng đó (như TC-20) →
# chỉ so đa tập dòng sau khi bỏ khoảng trắng (không mất, không nhân đôi dòng).
WS_ONLY_CASES = {"tc34_ws_vs_deleted_elsewhere", "tc35_ws_vs_moved_in"}


@pytest.mark.parametrize("case", list(REBUILD_CASES))
def test_rebuild_all_users_equals_end(make_repo, section14_repo, cache_root: Path,
                                     case: str) -> None:
    """TC-attribution-19: áp §7.3 với users = mọi account → trùng byte blob C_END.

    TC-34/35 (có dòng chỉ đổi khoảng trắng): đa tập dòng theo ws_key bằng C_END.
    """
    builder = REBUILD_CASES[case]
    if builder is None:
        src = section14_repo().src
    else:
        src = make_repo()
        builder(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()
    users = set(result.commit_accounts.values())
    checked = 0
    for fa in result.files:
        if fa.granularity != "lines" or fa.new is None:
            continue
        new_data = ctx.repo.read_blob(fa.new.sha)
        old_data = ctx.repo.read_blob(fa.old.sha) if fa.old is not None else b""
        rebuilt = rebuild_all_users(fa, old_data, new_data, users)
        if case in WS_ONLY_CASES:
            def keys(data: bytes) -> list[bytes]:
                return sorted(ws_key(line) for line in split_lines_bytes(data))
            assert keys(rebuilt) == keys(new_data), fa.path
        else:
            assert rebuilt == new_data, fa.path
        checked += 1
    assert checked >= 1


# ---------- TC-20 .. TC-23: khoảng trắng, tạo lại, xóa, file rỗng ----------
def test_whitespace_and_eol_only(make_repo, cache_root: Path) -> None:
    """TC-attribution-20: carol đổi thụt lề 1 dòng + CRLF→LF cả file → hunk có, không gán."""
    src = make_repo()
    code = ["def f():", "    return 1", "", "x = f()", "y = x + 1"]
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"ws.py": j(code, "\r\n")})
    changed = list(code)
    changed[1] = "        return 1"
    src.commit("carol ws", "2026-01-07T10:00:00+07:00", author=CAROL,
               files={"ws.py": j(changed)})
    result = prepare(src, cache_root).attribute()

    fa = file_of(result, "ws.py")
    assert fa.granularity == "lines"
    assert fa.hunks != ()
    assert dict(fa.added_by) == {}
    assert dict(fa.deleted_by) == {}
    assert fa.moved == frozenset()
    assert result.warnings == ()


def test_delete_then_recreate(make_repo, cache_root: Path) -> None:
    """TC-attribution-21: alice git rm, bob tạo lại 3/6 dòng như cũ → M; khác: cũ alice, mới bob."""
    src = make_repo()
    code = VALUES[:6]
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(code)})
    src.commit("alice rm", "2026-01-05T10:00:00+07:00", author=ALICE, remove=("app.py",))
    src.commit("bob recreate", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"app.py": j([*code[:3], "bob_line = 1"])})
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    assert len(result.files) == 1
    fa = result.files[0]
    assert fa.entry.status == "M"
    assert hunk_tuples(fa) == [(3, 3, 3, 1)]
    assert dict(fa.deleted_by) == {3: A, 4: A, 5: A}
    assert dict(fa.added_by) == {3: B}
    for i in range(3):  # dòng chung nằm ngoài hunk
        assert i not in old_hunk_lines(fa)
        assert i not in new_hunk_lines(fa)
    assert_commit_invariants(result, ctx.attribute)  # TC-41


def test_file_deleted(make_repo, cache_root: Path) -> None:
    """TC-attribution-22: alice git rm util.py → D, mọi dòng cũ → alice, deleted_code = 3."""
    src = make_repo()
    util = j(["# tiện ích", "", "u0 = 0", "u1 = 1", "u2 = 2"])
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"util.py": util, "main.py": "m = 1\n"})
    src.commit("alice rm", "2026-01-05T10:00:00+07:00", author=ALICE, remove=("util.py",))
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    fa = file_of(result, "util.py")
    assert fa.entry.status == "D"
    assert fa.new is None
    assert hunk_tuples(fa) == [(0, 5, 0, 0)]
    assert dict(fa.deleted_by) == {i: A for i in range(5)}
    assert dict(fa.added_by) == {}
    alice = user_of(result, A)
    assert alice.deleted_lines == 5
    assert alice.deleted_code == 3
    assert_commit_invariants(result, ctx.attribute)  # TC-41


def test_new_empty_file(make_repo, cache_root: Path) -> None:
    """TC-attribution-23: bob tạo x.py rỗng → 'lines', hunks == (), không thống kê."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": "a = 1\n"})
    src.commit("bob empty", "2026-01-05T10:00:00+07:00", author=BOB, files={"x.py": b""})
    result = prepare(src, cache_root).attribute()

    fa = file_of(result, "x.py")
    assert fa.entry.status == "A"
    assert fa.granularity == "lines"
    assert fa.hunks == ()
    assert dict(fa.added_by) == {}
    assert fa.new is not None and fa.new.line_count == 0 and fa.new.size == 0
    bob = user_of(result, B)
    assert (bob.added_lines, bob.deleted_lines, bob.added_code, bob.deleted_code) == (0, 0, 0, 0)
    assert bob.files == ()


# ---------- TC-24 .. TC-26: mức xử lý & bộ lọc ----------
def test_whole_file_granularity(make_repo, cache_root: Path) -> None:
    """TC-attribution-24: binary / quá lớn / T → 'whole', last_touch_by bob, không blame."""
    src = make_repo()
    big = j([f"big_value_{i:03d} = 'xxxxxxxxxxxxxxxxxxxxxxxx'" for i in range(40)])
    assert len(big) > 1024
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={
        "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00admin", "big.py": big, "link.txt": "target\n"})
    src.commit("alice edit", "2026-01-05T10:00:00+07:00", author=ALICE, files={
        "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00alice", "big.py": big + "alice = 1\n"})
    src.add_index_entry("120000", src.hash_blob(b"big.py"), "link.txt")
    src.commit("bob edit", "2026-01-06T10:00:00+07:00", author=BOB, files={
        "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00bob", "big.py": big + "bob = 2\n"})
    ctx = prepare(src, cache_root)
    spy = BlameSpy(ctx.repo)
    filters = FilterConfig(export_mode="full", exclude_binary=False, max_file_size_kb=1)
    result = ctx.attribute(filters=filters)

    statuses = {f.path: f.entry.status for f in result.files}
    assert statuses == {"big.py": "M", "link.txt": "T", "logo.png": "M"}
    for path in ("big.py", "link.txt", "logo.png"):
        fa = file_of(result, path)
        assert fa.granularity == "whole", path
        assert fa.last_touch_by == B, path
        assert fa.hunks == ()
        assert dict(fa.added_by) == {}
        assert dict(fa.deleted_by) == {}
    assert file_of(result, "logo.png").new.binary is True
    assert file_of(result, "big.py").new.too_large is True
    assert file_of(result, "link.txt").new.mode == "120000"
    assert spy.calls == []
    for account in (A, B):
        stats = user_of(result, account)
        assert (stats.added_lines, stats.deleted_lines) == (0, 0)
        assert (stats.added_code, stats.deleted_code) == (0, 0)
    assert user_of(result, B).files == ("big.py", "link.txt", "logo.png")
    assert result.warnings == ()
    assert result.commit_stats == ()  # TC-42 (b): file whole không tạo ô
    assert_commit_invariants(result, lambda: ctx.attribute(filters=filters))  # TC-41


def test_skip_and_side_filters(make_repo, cache_root: Path) -> None:
    """TC-attribution-25: README.md / symlink / submodule → 'skip'; rename src→vendor theo phía."""
    src = make_repo()
    a_py = [f"a_value_{i} = {i}" for i in range(10)]
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"README.md": "# Dự án\n", "src/a.py": j(a_py)})
    src.write("README.md", "# Dự án\n\nalice viết thêm\n")
    src.add_index_entry("120000", src.hash_blob(b"src/a.py"), "link.py")
    src.add_index_entry("160000", "1234567890abcdef1234567890abcdef12345678", "sub")
    src.commit("alice misc", "2026-01-05T10:00:00+07:00", author=ALICE)
    edited = list(a_py)
    edited[3] = "a_value_3 = 333"
    src.commit("bob vendor", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"vendor/a.py": j(edited)}, remove=("src/a.py",))
    ctx = prepare(src, cache_root)
    spy = BlameSpy(ctx.repo)
    result = ctx.attribute()

    for path in ("README.md", "link.py", "sub"):
        assert file_of(result, path).granularity == "skip", path
        assert dict(file_of(result, path).added_by) == {}
    assert not [c for c in spy.calls if c["path"] in ("README.md", "link.py", "sub")]

    fa = file_of(result, "vendor/a.py")
    assert fa.entry.status == "R"
    assert fa.old.keep is True
    assert fa.new.keep is False
    assert fa.granularity == "lines"
    assert dict(fa.deleted_by) == {3: B}
    assert dict(fa.added_by) == {3: B}
    bob = user_of(result, B)
    assert (bob.added_lines, bob.deleted_lines) == (1, 1)
    assert bob.deleted_code == 1
    assert bob.added_code == 0
    alice = user_of(result, A)
    assert (alice.added_lines, alice.added_code) == (0, 0)
    assert_commit_invariants(result, ctx.attribute)  # TC-41


def test_full_mode_non_source(make_repo, cache_root: Path) -> None:
    """TC-attribution-26: export_mode full, notes.txt alice sửa → 'lines', added_by có, 0 code."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"notes.txt": "ghi chú 1\n"})
    src.commit("alice notes", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"notes.txt": "ghi chú 1\nghi chú 2\n"})
    result = prepare(src, cache_root).attribute(filters=FilterConfig(export_mode="full"))

    fa = file_of(result, "notes.txt")
    assert fa.granularity == "lines"
    assert dict(fa.added_by) == {1: A}
    alice = user_of(result, A)
    assert alice.added_lines == 1
    assert alice.added_code == 0


# ---------- TC-27 .. TC-30 ----------
def test_rename_limit_warning(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-27: diff_tree báo rename_limit_hit → đúng 1 RENAME_LIMIT path '' đứng đầu."""
    src = make_repo()
    build_move_cross_file(src)  # có thêm cảnh báo MOVED_LINES cho b.py
    ctx = prepare(src, cache_root)
    real = ctx.repo.diff_tree

    def fake(c_start: str | None, c_end: str) -> TreeDiff:
        return TreeDiff(real(c_start, c_end).entries, True)

    monkeypatch.setattr(ctx.repo, "diff_tree", fake)
    result = ctx.attribute()

    limit = [w for w in result.warnings if w.kind == WarningKind.RENAME_LIMIT]
    assert len(limit) == 1
    assert limit[0].path == ""
    assert limit[0].message == ("Git bỏ qua nhận diện đổi tên do quá nhiều file; file đổi tên "
                                "có thể bị tính là xóa + thêm")
    assert result.warnings[0] == limit[0]
    assert len(result.warnings) >= 2


def test_account_from_log_not_porcelain(make_repo, cache_root: Path) -> None:
    """TC-attribution-28: alice 2 email (identities) → account 'alice', không theo committer."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(VALUES[:3])})
    ci = ("ci-bot", "ci@example.com")
    c1 = src.commit("alice noreply", "2026-01-05T10:00:00+07:00",
                    author=("Alice Nguyen", "12345+alice-gh@users.noreply.github.com"),
                    committer=ci, files={"app.py": j([*VALUES[:3], "alice_one = 1"])})
    c2 = src.commit("alice corp", "2026-01-06T10:00:00+07:00",
                    author=("A. Nguyen", "Alice@Corp.Example"), committer=ci,
                    files={"app.py": j([*VALUES[:3], "alice_one = 1", "alice_two = 2"])})
    c3 = src.commit("bob", "2026-01-07T10:00:00+07:00", author=BOB, committer=ci,
                    files={"b.py": "b = 1\n"})
    identities = IdentityMap((
        IdentityRule("alice", email="12345+alice-gh@users.noreply.github.com"),
        IdentityRule("alice", email="alice@corp.example"),
    ))
    ctx = prepare(src, cache_root)
    result = ctx.attribute(resolver=AccountResolver(identities))

    assert dict(result.commit_accounts) == {c1: "alice", c2: "alice", c3: B}
    assert dict(file_of(result, "app.py").added_by) == {3: "alice", 4: "alice"}
    assert dict(file_of(result, "b.py").added_by) == {0: B}
    assert [u.account for u in result.users] == ["alice", B]
    assert user_of(result, "alice").added_lines == 2
    assert result.user("ci@example.com") is None
    assert result.user("alice-gh") is None
    assert_commit_invariants(  # TC-41 (committer khác author)
        result, lambda: ctx.attribute(resolver=AccountResolver(identities)))


def build_two_hunks(src: Any) -> None:
    """TC-29: hunk 1 (dòng 3–4) alice xóa, bob viết; hunk 2 (dòng 10) bob xóa, carol viết.

    C_START (admin, 2025-12-15) app.py = 12 dòng value_number_0..11; alice 2026-01-05 xóa
    dòng 3–4; bob 2026-01-06 viết 2 dòng mới vào chỗ đó và xóa dòng 10; carol 2026-01-07
    viết 1 dòng mới vào chỗ dòng 10.
    """
    base = [f"value_number_{i} = {i}" for i in range(12)]
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(base)})
    v1 = base[:2] + base[4:]
    src.commit("alice del", "2026-01-05T10:00:00+07:00", author=ALICE, files={"app.py": j(v1)})
    v2 = base[:2] + ["bob_wrote_one = 'b1'", "bob_wrote_two = 'b2'"] + base[4:9] + base[10:]
    src.commit("bob", "2026-01-06T10:00:00+07:00", author=BOB, files={"app.py": j(v2)})
    v3 = v2[:9] + ["carol_wrote = 'c'"] + v2[9:]
    src.commit("carol", "2026-01-07T10:00:00+07:00", author=CAROL, files={"app.py": j(v3)})


def test_multi_user_hunk_order(make_repo, cache_root: Path) -> None:
    """TC-attribution-29: [MULTI h1, MULTI h2, SEQ h1, SEQ h2], 1-based, tái lập."""
    src = make_repo()
    build_two_hunks(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    fa = file_of(result, "app.py")
    assert hunk_tuples(fa) == [(2, 2, 2, 2), (9, 1, 9, 1)]
    assert dict(fa.deleted_by) == {2: A, 3: A, 9: B}
    assert dict(fa.added_by) == {2: B, 3: B, 9: C}
    assert kinds(result) == [MULTI, MULTI, SEQ, SEQ]
    m1, m2, s1, s2 = result.warnings
    assert {w.path for w in result.warnings} == {"app.py"}
    assert m1.message == f"Hunk dòng cũ 3–4 / dòng mới 3–4 có thay đổi của nhiều user: {A}, {B}"
    assert re.fullmatch(rf"Hunk dòng cũ 10(–10)? / dòng mới 10(–10)? có thay đổi của nhiều "
                        rf"user: {B}, {C}", m2.message)
    assert s1.message == (f"Dòng cũ 3–4 bị {A} xóa và {B} viết lại; "
                          "chỉ gán được cho người sửa cuối")
    assert re.fullmatch(rf"Dòng cũ 10(–10)? bị {B} xóa và {C} viết lại; "
                        r"chỉ gán được cho người sửa cuối", s2.message)

    again = ctx.attribute()
    assert again == result
    assert again.warnings == result.warnings
    assert list(again.file("app.py").added_by.items()) == list(fa.added_by.items())
    assert list(again.file("app.py").deleted_by.items()) == list(fa.deleted_by.items())


def test_hostile_global_git_config(section14_repo, cache_root: Path, tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-30: GIT_CONFIG_GLOBAL "khó chịu" → kết quả như TC-02."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root)
    clean = ctx.attribute()

    hostile = tmp_path / "hostile-attr.gitconfig"
    hostile.write_text("[diff]\n\talgorithm = patience\n\trenames = copies\n"
                       "[blame]\n\tignoreRevsFile = .nope\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    result = ctx.attribute()

    assert result == clean
    app = file_of(result, "app.py")
    assert hunk_tuples(app) == [(2, 2, 2, 0), (13, 1, 11, 0), (15, 0, 12, 7)]
    assert dict(app.deleted_by) == {2: A, 3: A, 13: B}
    assert dict(app.added_by) == {i: A for i in range(12, 19)}
    assert dict(file_of(result, "util.py").added_by) == {i: B for i in range(8)}
    assert result.warnings == ()


# ---------- TC-31 .. TC-33 ----------
def test_no_commit_in_period(section14_repo, cache_root: Path) -> None:
    """TC-attribution-31: C_START == C_END → files == (), users == (), không blame."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root, start=date(2026, 1, 20), end=date(2026, 1, 31))
    assert ctx.snaps.c_start is not None
    assert ctx.snaps.c_start.sha == ctx.snaps.c_end.sha == s14.end_sha
    assert ctx.commits == []
    spy = BlameSpy(ctx.repo)
    result = ctx.attribute()

    assert result.files == ()
    assert result.users == ()
    assert result.warnings == ()
    assert dict(result.commit_accounts) == {}
    assert spy.calls == []


@pytest.mark.parametrize(("data", "expected"), [
    (b"", 0), (b"a", 1), (b"a\n", 1), (b"a\nb", 2), (b"a\r\nb\r\n", 2), (b"\n\n", 2),
])
def test_count_lines(data: bytes, expected: int) -> None:
    """TC-attribution-32: count_lines theo git (D8)."""
    assert count_lines(data) == expected


def test_commit_outside_period_defensive(section14_repo, cache_root: Path) -> None:
    """TC-attribution-33: thiếu commit của bob → dòng mới bob bỏ, dòng cũ giữ, UNATTRIBUTED."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root)
    without_bob = [c for c in ctx.commits if c.author_email != B]
    assert len(without_bob) == len(ctx.commits) - 2
    result = ctx.attribute(commits=without_bob)

    app = file_of(result, "app.py")
    assert 13 not in app.deleted_by  # v9 do bob xóa → giữ
    assert dict(app.deleted_by) == {2: A, 3: A}
    assert dict(app.added_by) == {i: A for i in range(12, 19)}
    util = file_of(result, "util.py")
    assert dict(util.added_by) == {}
    unattr = {w.path: w.message for w in result.warnings if w.kind == UNATTR}
    assert unattr == {
        "app.py": "Không xác định được tác giả: dòng cũ 14",
        "util.py": "Không xác định được tác giả: dòng mới 1–8",
    }
    assert result.user(B) is None
    assert [u.account for u in result.users] == [A]
    assert_commit_invariants(result, lambda: ctx.attribute(commits=without_bob))  # TC-41


def test_side_info_fields(section14_repo, cache_root: Path) -> None:
    """TC-attribution-02: SideInfo của app.py / util.py (keep, language, line_count, size)."""
    s14 = section14_repo()
    result = prepare(s14.src, cache_root).attribute()
    app = file_of(result, "app.py")
    assert isinstance(app.old, SideInfo)
    assert app.old.path == "app.py"
    assert app.old.mode == "100644"
    assert app.old.size == len(s14.app_start.encode("utf-8"))
    assert app.old.line_count == 15
    assert app.new.size == len(s14.app_end.encode("utf-8"))
    assert app.new.line_count == 19
    assert (app.new.keep, app.new.language, app.new.binary, app.new.too_large) == (
        True, "Python", False, False)
    util = file_of(result, "util.py")
    assert util.new.line_count == 8


# ---------- TC-34 .. TC-37 (sửa theo review) ----------
def test_ws_only_not_matched_to_line_deleted_elsewhere(make_repo, cache_root: Path) -> None:
    """TC-attribution-34: `pass` chỉ đổi thụt lề không ghép với `pass` alice xóa ở g() (D28 (0))."""
    src = make_repo()
    build_ws_vs_deleted_elsewhere(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    fa = file_of(result, "m.py")
    new_lines = split_lines_bytes(ctx.repo.read_blob(fa.new.sha))
    old_lines = split_lines_bytes(ctx.repo.read_blob(fa.old.sha))
    assert old_lines[2] == old_lines[6] == b"    pass\n"  # pass của g(), pass của f()
    assert new_lines[6] == b"        pass\n"  # pass của f() sau khi bob thụt lề
    assert 6 in new_hunk_lines(fa)
    assert 6 in old_hunk_lines(fa)
    assert 6 not in fa.added_by
    assert 6 not in fa.moved
    assert 6 not in fa.deleted_by
    assert fa.deleted_by.get(2) == A
    assert A not in fa.added_by.values()
    alice = user_of(result, A)
    assert (alice.added_code, alice.deleted_code) == (0, 1)
    assert (alice.added_lines, alice.deleted_lines) == (0, 1)
    assert MOVED not in kinds(result, "m.py")


def test_ws_only_not_matched_to_line_moved_in(make_repo, cache_root: Path) -> None:
    """TC-attribution-35: Z chỉ đổi thụt lề (carol) không ghép với Z bob dời từ b.py vào."""
    src = make_repo()
    build_ws_vs_moved_in(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()

    a = file_of(result, "a.py")
    new_lines = split_lines_bytes(ctx.repo.read_blob(a.new.sha))
    old_lines = split_lines_bytes(ctx.repo.read_blob(a.old.sha))
    z_old = old_lines.index(b"    " + LONG_Z.encode() + b"\n")
    z_moved = new_lines.index(b"    " + LONG_Z.encode() + b"\n")
    assert (z_old, z_moved) == (1, 4)
    assert z_old in old_hunk_lines(a)
    assert z_old not in a.deleted_by
    assert a.added_by.get(z_moved) == B
    assert z_moved in a.moved
    assert 1 not in a.added_by  # Z của carol (chỉ đổi thụt lề) bị bỏ, Z cũ được giữ
    b = file_of(result, "b.py")
    assert dict(b.deleted_by) == {1: B}
    bob = user_of(result, B)
    assert bob.deleted_code == 1
    assert bob.deleted_lines == 1
    assert bob.added_lines == 1
    carol = user_of(result, C)
    assert (carol.added_lines, carol.deleted_lines) == (0, 0)


def build_nested_merge(src: Any) -> dict[str, str]:
    """TC-36: merge lồng nhau — bob xóa v2 trên feat2 → dave merge feat2 vào feat → carol merge
    feat vào main; alice sửa v7 trên main.

    C_START (admin, 2025-12-15) app.py = value_number_0..9; feat, feat2 tách từ C_START.
    alice sửa v7 trên main 2026-01-04 (trước các commit của nhánh → D23 chạy tới độ sâu 2); bob
    2026-01-05 sửa v5 trên feat; bob 2026-01-06 xóa v2 trên feat2; dave merge feat2 vào feat
    2026-01-06; carol merge feat vào main 2026-01-07 (kịch bản của review r1, độ sâu 2).
    """
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(VALUES)})
    src.git("branch", "feat")
    src.git("branch", "feat2")
    main = list(VALUES)
    main[7] = "value_number_7 = 77"
    src.commit("alice main", "2026-01-04T10:00:00+07:00", author=ALICE,
               files={"app.py": j(main)})
    src.checkout("feat")
    feat = list(VALUES)
    feat[5] = "value_number_5 = 55"
    src.commit("bob feat", "2026-01-05T10:00:00+07:00", author=BOB, files={"app.py": j(feat)})
    src.checkout("feat2")
    bob_del = src.commit("bob del v2", "2026-01-06T09:00:00+07:00", author=BOB,
                         files={"app.py": j([v for v in VALUES if v != VALUES[2]])})
    src.checkout("feat")
    inner = src.merge("feat2", "dave merge feat2", "2026-01-06T12:00:00+07:00", author=DAVE)
    src.checkout("main")
    outer = src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)
    return {"bob_del": bob_del, "inner": inner, "outer": outer}


def test_nested_merge(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-36: merge lồng nhau (D23 đệ quy): v2 → bob, v7 → alice; carol, dave 0."""
    src = make_repo()
    shas = build_nested_merge(src)
    ctx = prepare(src, cache_root)
    assert ctx.snaps.c_end.sha == shas["outer"]
    found: list[str | None] = []
    real = ctx.repo.first_commit_after

    def spy(since: str, until: str, paths: Any) -> str | None:
        found.append(real(since, until, paths))
        return found[-1]

    ctx.repo.first_commit_after = spy  # type: ignore[method-assign]
    depths: list[tuple[int, str]] = []
    real_resolve = attribution._Attributor.resolve_merge

    def resolve_spy(self: Any, anchor: Any, merge: str, depth: int) -> str:
        depths.append((depth, merge))
        return real_resolve(self, anchor, merge, depth)

    monkeypatch.setattr(attribution._Attributor, "resolve_merge", resolve_spy)
    result = ctx.attribute()
    # đệ quy thật: merge ngoài ở độ sâu 1, merge trong ở độ sâu 2
    assert (1, shas["outer"]) in depths
    assert (2, shas["inner"]) in depths

    app = file_of(result, "app.py")
    assert app.deleted_by.get(2) == B
    assert app.deleted_by.get(7) == A
    assert app.added_by.get(6) == A
    for account in (C, D):
        assert account not in app.added_by.values()
        assert account not in app.deleted_by.values()
        stats = user_of(result, account)
        assert (stats.added_lines, stats.deleted_lines) == (0, 0)
        assert stats.files == ()
    # kịch bản thật sự đi qua 2 tầng merge: ứng viên là merge ngoài rồi merge trong
    assert shas["outer"] in found
    assert shas["inner"] in found


def test_defensive_merge_bases_ambiguous(make_repo, cache_root: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-37: (a) merge_bases trả 2 SHA (kịch bản TC-12) → v2 giữ + UNATTRIBUTED."""
    src = make_repo()
    build_merge_parallel(src, fork_before=True)
    ctx = prepare(src, cache_root)
    calls: list[tuple[str, str]] = []

    def two_bases(a: str, b: str) -> list[str]:
        calls.append((a, b))
        return sorted([a, b])

    monkeypatch.setattr(ctx.repo, "merge_bases", two_bases)
    result = ctx.attribute()

    app = file_of(result, "app.py")
    assert calls
    assert 2 not in app.deleted_by
    unattr = [w for w in result.warnings if w.kind == UNATTR]
    assert [w.path for w in unattr] == ["app.py"]
    assert re.fullmatch(r"Không xác định được tác giả: dòng cũ (\d+(–\d+)?, )*3(, .*)?",
                        unattr[0].message)


def test_defensive_whole_no_touch(make_repo, cache_root: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-37: (b) rev_list trả [] cho file whole → last_touch_by None + UNATTRIBUTED."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"logo.png": b"\x89PNG\r\n\x1a\n\x00\x00admin"})
    src.commit("alice logo", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"logo.png": b"\x89PNG\r\n\x1a\n\x00\x00alice"})
    ctx = prepare(src, cache_root)
    real = ctx.repo.rev_list

    def fake(include: str, exclude: str | None = None, paths: Any = (), **kw: Any) -> list[str]:
        if "logo.png" in list(paths):
            return []
        return real(include, exclude, paths, **kw)

    monkeypatch.setattr(ctx.repo, "rev_list", fake)
    result = ctx.attribute(filters=FilterConfig(export_mode="full", exclude_binary=False))

    fa = file_of(result, "logo.png")
    assert fa.granularity == "whole"
    assert fa.last_touch_by is None
    assert [(w.kind, w.path, w.message) for w in result.warnings] == [
        (UNATTR, "logo.png", "Không xác định được người thay đổi cuối của file")]
    assert user_of(result, A).files == ()


class ShortFlagsClassifier:
    """Classifier giả: chỉ trả cờ cho dòng đầu (True), thiếu cờ các dòng sau."""

    count_docstrings = False

    def __init__(self) -> None:
        self.calls: list[str] = []

    def classify(self, content: str, filename: str, sha: str) -> list[bool]:
        self.calls.append(filename)
        return [True]


def test_defensive_short_classifier_flags(make_repo, cache_root: Path,
                                          caplog: pytest.LogCaptureFixture) -> None:
    """TC-attribution-37: (c) classifier trả thiếu cờ → log WARNING, cờ thiếu = không phải code."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": "a = 1\n"})
    src.commit("alice x", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"x.py": "x1 = 1\nx2 = 2\nx3 = 3\n"})
    ctx = prepare(src, cache_root)
    fake = ShortFlagsClassifier()
    caplog.set_level(logging.DEBUG)
    result = attribute_period(ctx.repo, ctx.snaps, ctx.commits, AccountResolver(),
                              FilterConfig(), fake)  # type: ignore[arg-type]

    assert fake.calls == ["x.py"]
    assert dict(file_of(result, "x.py").added_by) == {0: A, 1: A, 2: A}
    alice = user_of(result, A)
    assert alice.added_lines == 3
    assert alice.added_code == 1
    assert any(r.levelno == logging.WARNING and r.name.startswith("loc_counter.attribution")
               for r in caplog.records)


def build_rename_recreated(src: Any) -> dict[str, str]:
    """TC-37 (d): bob mv old.py → new.py (tạo path), alice xóa new.py, dave tạo lại new.py.

    C_START (admin, 2025-12-15) old.py = value_number_0..9; bob 2026-01-05, alice 2026-01-06,
    dave 2026-01-07 (nội dung giống hệt → diff cả kỳ là R100 old.py → new.py).
    """
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.git("mv", "old.py", "new.py")
    bob_mv = src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    alice_rm = src.commit("alice rm", "2026-01-06T10:00:00+07:00", author=ALICE,
                          remove=("new.py",))
    dave_add = src.commit("dave re-add", "2026-01-07T10:00:00+07:00", author=DAVE,
                          files={"new.py": j(VALUES)})
    return {"bob_mv": bob_mv, "alice_rm": alice_rm, "dave_add": dave_add}


def test_defensive_rename_creator_outside_commits(make_repo, cache_root: Path) -> None:
    """TC-attribution-37: (d) commit tạo path cuối không có trong commits → lấy commit thuộc kỳ."""
    src = make_repo()
    shas = build_rename_recreated(src)
    ctx = prepare(src, cache_root)

    full = ctx.attribute()
    fa_full = file_of(full, "new.py")
    assert fa_full.entry.status == "R"
    assert fa_full.renamed_by == D  # lần tạo gần nhất (đủ commit)

    partial = [c for c in ctx.commits if c.sha != shas["dave_add"]]
    assert len(partial) == len(ctx.commits) - 1
    result = ctx.attribute(commits=partial)
    fa = file_of(result, "new.py")
    assert fa.entry.status == "R"
    assert fa.renamed_by == B
    assert WarningKind.RENAME_UNRESOLVED not in kinds(result)
    assert shas["dave_add"] not in result.commit_accounts


# ---------- TC-37 (e): nhánh phòng thủ D23 / blame lần 2 với repo giả ----------
def _sha(ch: str) -> str:
    return ch * 40


class FakeRepo:
    """Repo giả cho _Attributor: trả kết quả định sẵn, ghi lại lời gọi."""

    def __init__(self, *, ancestors: Iterable[tuple[str, str]] = (),
                 bases: list[str] | None = None, blames: list[list[Any]] | None = None,
                 first_after: str | None = None) -> None:
        self.ancestors = set(ancestors)
        self.bases = bases or []
        self.blames = list(blames or [])
        self.first_after = first_after
        self.calls: list[str] = []

    def is_ancestor(self, a: str, b: str) -> bool:
        self.calls.append("is_ancestor")
        return (a, b) in self.ancestors

    def merge_bases(self, a: str, b: str) -> list[str]:
        self.calls.append("merge_bases")
        return self.bases

    def blame(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append("blame")
        return self.blames.pop(0)

    def first_commit_after(self, since: str, until: str, paths: Any) -> str | None:
        self.calls.append("first_commit_after")
        return self.first_after


def _attributor(repo: FakeRepo, merge_parents: tuple[str, ...] = ()) -> Any:
    """_Attributor trên repo giả; merge_parents khác rỗng → thêm merge m vào by_sha."""
    when = datetime(2026, 1, 5, tzinfo=UTC)
    by_sha = {}
    if merge_parents:
        by_sha[_sha("m")] = LogCommit(_sha("m"), merge_parents, "carol", "c@x", "carol", "c@x",
                                      when)
    return attribution._Attributor(repo, _sha("s"), _sha("e"), by_sha, {_sha("m"): "carol"},
                                   FilterConfig(), {})


def test_defensive_parent_side_branches() -> None:
    """TC-attribution-37: (e) neo merge-base: dòng sinh sau base → PRESENT; fb không phải tổ
    tiên của parent → UNDETERMINED; first_commit_after None → UNDETERMINED."""

    anchor = (_sha("a"), "app.py", 3)
    parent = _sha("p")
    born_after = FakeRepo(bases=[_sha("b")],
                          blames=[[BlameLine(3, _sha("a"), 3, "app.py", False)]])
    assert attribution._Attributor._parent_side(
        _attributor(born_after), anchor, parent, 1) == attribution._PRESENT
    not_anc = FakeRepo(bases=[_sha("b")], blames=[[BlameLine(3, _sha("b"), 2, "app.py", True)]])
    assert attribution._Attributor._parent_side(
        _attributor(not_anc), anchor, parent, 1) == attribution._UNDETERMINED
    lost = FakeRepo(ancestors={(_sha("a"), parent)},
                    blames=[[BlameLine(3, _sha("q"), 3, "app.py", False)]], first_after=None)
    assert attribution._Attributor._parent_side(
        _attributor(lost), anchor, parent, 1) == attribution._UNDETERMINED
    assert lost.calls == ["is_ancestor", "blame", "first_commit_after"]


def test_defensive_resolve_merge_memo() -> None:
    """TC-attribution-37: (e) resolve_merge ghi nhớ theo (S, path, j, M): lần 2 không gọi git."""
    parent = _sha("p")
    repo = FakeRepo(ancestors={(_sha("a"), parent)})
    att = _attributor(repo, merge_parents=(parent,))
    att._parent_side = lambda anchor, p, depth: attribution._PRESENT  # type: ignore[method-assign]
    anchor = (_sha("a"), "app.py", 3)
    assert att.resolve_merge(anchor, _sha("m"), 1) == _sha("m")
    att._parent_side = None  # type: ignore[assignment]  # gọi lại sẽ lỗi nếu không dùng memo
    assert att.resolve_merge(anchor, _sha("m"), 1) == _sha("m")


def test_defensive_second_blame_outside_period() -> None:
    """TC-attribution-37: (e) dòng mới boundary, blame lần 2 trả commit ngoài kỳ → UNATTRIBUTED."""

    repo = FakeRepo(blames=[[BlameLine(0, _sha("s"), 0, "a.py", True)],
                            [BlameLine(0, _sha("z"), 0, "a.py", False)]])
    att = _attributor(repo)
    new = SideInfo("a.py", "100644", _sha("n"), 6, True, "Python", False, False, 1)
    added: dict[int, str] = {}
    moved: set[int] = set()
    d22: set[int] = set()
    unattr: set[int] = set()
    att._added_lines(new, [Hunk(0, 0, 0, 1)], added, moved, d22, unattr)
    assert added == {} and moved == set() and d22 == set()
    assert unattr == {0}


# ---------- TC-38 .. TC-43 (M5: sha theo dòng, commit_stats — D35) ----------
def sha_of(src: Any, subject: str) -> str:
    """SHA của commit duy nhất có tiêu đề subject (mọi nhánh)."""
    rows = [line.split(" ", 1) for line in src.git("log", "--all", "--format=%H %s").splitlines()]
    found = [sha for sha, subj in rows if subj == subject]
    assert len(found) == 1, f"không tìm thấy duy nhất commit '{subject}'"
    return found[0]


def stats_tuple(s: CommitLineStats) -> tuple[int, int, int, int]:
    """(added_lines, deleted_lines, added_code, deleted_code) của một ô commit_stats."""
    return (s.added_lines, s.deleted_lines, s.added_code, s.deleted_code)


def assert_commit_invariants(result: PeriodAttribution,
                             rerun: Callable[[], PeriodAttribution] | None = None) -> None:
    """Bất biến 5.9 bước 4b: sha cùng khóa với account; Σ commit_stats theo account = users.

    rerun: chạy lại attribute_period trên cùng input → kết quả và thứ tự sha phải trùng (TC-41).
    """
    if rerun is not None:
        again = rerun()
        assert again == result
        assert again.commit_stats == result.commit_stats
        for fa, fb in zip(result.files, again.files, strict=True):
            assert list(fa.added_commit.items()) == list(fb.added_commit.items())
            assert list(fa.deleted_commit.items()) == list(fb.deleted_commit.items())
    for fa in result.files:
        assert list(fa.added_commit) == list(fa.added_by), fa.path
        assert list(fa.deleted_commit) == list(fa.deleted_by), fa.path
        for i, sha in fa.added_commit.items():
            assert result.commit_accounts[sha] == fa.added_by[i], (fa.path, i)
        for i, sha in fa.deleted_commit.items():
            assert result.commit_accounts[sha] == fa.deleted_by[i], (fa.path, i)
    shas = [s.sha for s in result.commit_stats]
    assert shas == sorted(shas)
    assert len(set(shas)) == len(shas)
    totals: dict[str, list[int]] = {}
    for s in result.commit_stats:
        assert s.sha in result.commit_accounts
        assert s.account == result.commit_accounts[s.sha]
        assert s.added_lines + s.deleted_lines > 0, "không có ô toàn 0"
        row = totals.setdefault(s.account, [0, 0, 0, 0])
        for k, v in enumerate(stats_tuple(s)):
            row[k] += v
    for u in result.users:
        expected = [u.added_lines, u.deleted_lines, u.added_code, u.deleted_code]
        assert totals.get(u.account, [0, 0, 0, 0]) == expected, u.account
    assert set(totals) <= {u.account for u in result.users}


def test_section14_commit_stats(section14_repo, cache_root: Path) -> None:
    """TC-attribution-38: §14 — added_commit/deleted_commit theo dòng và commit_stats 4 ô."""
    s14 = section14_repo()
    result = prepare(s14.src, cache_root).attribute()
    add, util, dele, bdel = (sha_of(s14.src, s) for s in
                             ("alice add", "bob util", "alice del", "bob del"))

    app = file_of(result, "app.py")
    assert dict(app.added_commit) == {i: add for i in range(12, 19)}
    assert dict(app.deleted_commit) == {2: dele, 3: dele, 13: bdel}
    assert dict(file_of(result, "util.py").added_commit) == {i: util for i in range(8)}
    assert dict(file_of(result, "util.py").deleted_commit) == {}

    expected = {add: (A, (7, 0, 5, 0)), util: (B, (8, 0, 8, 0)),
                dele: (A, (0, 2, 0, 2)), bdel: (B, (0, 1, 0, 1))}
    assert [s.sha for s in result.commit_stats] == sorted(expected)
    for s in result.commit_stats:
        assert (s.account, stats_tuple(s)) == expected[s.sha]
    late = s14.src.git("rev-parse", "main")
    assert result.commit(late) is None
    assert result.commit(sha_of(s14.src, "admin: app.py")) is None
    stats = result.commit(bdel)
    assert stats is not None and stats.account == B
    assert_commit_invariants(result)


def test_commit_sha_through_merges(make_repo, cache_root: Path) -> None:
    """TC-attribution-39: sha qua merge (D23, §16) — kịch bản TC-11, 13, 14, 36."""
    # TC-11: merge song song không xung đột
    src = make_repo("r11")
    build_merge_parallel(src)
    result = prepare(src, cache_root / "11").attribute()
    alice, bob, merge = (sha_of(src, s) for s in ("alice main", "bob feat", "carol merge"))
    app = file_of(result, "app.py")
    assert dict(app.deleted_commit) == {2: bob, 7: alice}
    assert dict(app.added_commit) == {6: alice}
    assert result.commit(merge) is None
    assert_commit_invariants(result)

    # TC-13: merge tự xóa v5
    src = make_repo("r13")
    build_merge_self_delete(src)
    result = prepare(src, cache_root / "13").attribute()
    merge = sha_of(src, "carol merge")
    app = file_of(result, "app.py")
    assert app.deleted_commit.get(5) == merge
    assert app.deleted_commit.get(1) == sha_of(src, "alice")
    assert app.deleted_commit.get(9) == sha_of(src, "bob")
    stats = result.commit(merge)
    assert stats is not None and stats.account == C
    assert (stats.added_lines, stats.deleted_lines, stats.deleted_code) == (0, 1, 1)
    assert_commit_invariants(result)

    # TC-14: dòng giải quyết xung đột thuộc merge
    src = make_repo("r14")
    build_conflict(src)
    result = prepare(src, cache_root / "14").attribute()
    merge, alice = sha_of(src, "carol merge"), sha_of(src, "alice main")
    app = file_of(result, "app.py")
    assert app.added_commit.get(4) == merge
    assert app.deleted_commit.get(5) == alice
    assert app.deleted_commit.get(2) == sha_of(src, "bob feat")
    stats = result.commit(merge)
    assert stats is not None and stats.account == C and stats.added_lines == 1
    assert_commit_invariants(result)

    # TC-36: merge lồng nhau
    src = make_repo("r36")
    shas = build_nested_merge(src)
    result = prepare(src, cache_root / "36").attribute()
    app = file_of(result, "app.py")
    assert app.deleted_commit.get(2) == shas["bob_del"]
    assert app.deleted_commit.get(7) == sha_of(src, "alice main")
    assert result.commit(shas["inner"]) is None
    assert result.commit(shas["outer"]) is None
    assert_commit_invariants(result)


def test_commit_sha_of_moved_lines(make_repo, cache_root: Path) -> None:
    """TC-attribution-40: sha của dòng dời — D22 (TC-16), D28 (b) (TC-17), D28 (a) (TC-18)."""
    src = make_repo("r16")
    build_move_cross_file(src)
    result = prepare(src, cache_root / "16").attribute()
    move = sha_of(src, "bob move")
    assert dict(file_of(result, "b.py").added_commit) == {1: move, 2: move}
    assert dict(file_of(result, "a.py").deleted_commit) == {10: move, 11: move}
    assert_commit_invariants(result)

    src = make_repo("r17")
    build_move_block(src)
    result = prepare(src, cache_root / "17").attribute()
    move = sha_of(src, "alice move")
    fa = file_of(result, "a.py")
    assert dict(fa.added_commit) == {i: move for i in range(4, 8)}
    assert dict(fa.deleted_commit) == {i: move for i in range(4)}  # (b): sha của dòng mới D22
    assert_commit_invariants(result)

    src = make_repo("r18")
    build_move_block_ws(src)
    result = prepare(src, cache_root / "18").attribute()
    move = sha_of(src, "alice move")
    fa = file_of(result, "a.py")
    assert dict(fa.deleted_commit) == {i: move for i in range(4, 8)}
    # (a): dòng mới ghép nhận sha commit xóa dòng cũ (commit dời), không phải commit carol
    assert dict(fa.added_commit) == {i: move for i in range(4)}
    assert result.commit(sha_of(src, "carol ws")) is None
    assert_commit_invariants(result)


INVARIANT_CASES: dict[str, Any] = {
    "tc02_section14": None,
    "tc11_merge_parallel": build_merge_parallel,
    "tc12_fork_before": lambda src: build_merge_parallel(src, fork_before=True),
    "tc13_merge_self_delete": build_merge_self_delete,
    "tc14_conflict": build_conflict,
    "tc16_move_cross_file": build_move_cross_file,
    "tc17_move_block": build_move_block,
    "tc18_move_block_ws": build_move_block_ws,
    "tc29_two_hunks": build_two_hunks,
    "tc34_ws_vs_deleted_elsewhere": build_ws_vs_deleted_elsewhere,
    "tc35_ws_vs_moved_in": build_ws_vs_moved_in,
    "tc36_nested_merge": build_nested_merge,
}


@pytest.mark.parametrize("case", list(INVARIANT_CASES))
def test_commit_invariants(make_repo, section14_repo, cache_root: Path, case: str) -> None:
    """TC-attribution-41: bất biến 4b (sha ↔ account, Σ commit_stats = users), tái lập.

    Repo TC-21, 22, 24, 25, 28, 33 kiểm (cả chạy 2 lần) ngay trong test của chúng; TC-03, 05, 31
    trong TC-42.
    """
    builder = INVARIANT_CASES[case]
    if builder is None:
        src = section14_repo().src
    else:
        src = make_repo()
        builder(src)
    ctx = prepare(src, cache_root)
    result = ctx.attribute()
    assert result.commit_stats
    assert_commit_invariants(result, ctx.attribute)


def test_commit_stats_no_cells_and_multi_email(make_repo, section14_repo,
                                               cache_root: Path) -> None:
    """TC-attribution-42: không tạo ô (rename thuần, whole, không commit); C_START rỗng; 2 email."""
    # (a) rename thuần
    src = make_repo("ra")
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.git("mv", "old.py", "new.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    result = prepare(src, cache_root / "a").attribute()
    assert result.files[0].renamed_by == B
    assert result.commit_stats == ()
    assert_commit_invariants(result)

    # (b) file whole (binary); binary + quá lớn + đổi kiểu T kiểm thêm trong TC-24
    src = make_repo("rb")
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"logo.png": b"\x89PNG\r\n\x1a\n\x00\x00admin"})
    src.commit("alice logo", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"logo.png": b"\x89PNG\r\n\x1a\n\x00\x00alice"})
    filters = FilterConfig(export_mode="full", exclude_binary=False)
    result = prepare(src, cache_root / "b").attribute(filters=filters)
    assert file_of(result, "logo.png").granularity == "whole"
    assert file_of(result, "logo.png").last_touch_by == A
    assert result.commit_stats == ()
    assert_commit_invariants(result)

    # (c) không có commit trong kỳ
    s14 = section14_repo()
    result = prepare(s14.src, cache_root / "c", start=date(2026, 1, 20),
                     end=date(2026, 1, 31)).attribute()
    assert result.commit_stats == ()

    # (d) C_START rỗng (cùng repo §14): commit admin có ô (7 dòng code còn tại C_END)
    result = prepare(s14.src, cache_root / "d", start=date(2025, 12, 1)).attribute()
    admin = result.commit(sha_of(s14.src, "admin: app.py"))
    assert admin is not None and admin.account == ADMIN and admin.added_code == 7
    assert {s.account for s in result.commit_stats} == {ADMIN, A, B}
    assert all(s.deleted_lines == s.deleted_code == 0 for s in result.commit_stats)
    assert_commit_invariants(result)

    # (e) alice 2 email gộp qua identities → 2 ô, cùng account
    src = make_repo("re")
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(VALUES[:3])})
    c1 = src.commit("alice noreply", "2026-01-05T10:00:00+07:00",
                    author=("Alice Nguyen", "12345+alice-gh@users.noreply.github.com"),
                    files={"app.py": j([*VALUES[:3], "alice_one = 1"])})
    c2 = src.commit("alice corp", "2026-01-06T10:00:00+07:00",
                    author=("A. Nguyen", "Alice@Corp.Example"),
                    files={"app.py": j([*VALUES[:3], "alice_one = 1", "alice_two = 2"])})
    identities = IdentityMap((
        IdentityRule("alice", email="12345+alice-gh@users.noreply.github.com"),
        IdentityRule("alice", email="alice@corp.example"),
    ))
    result = prepare(src, cache_root / "e").attribute(resolver=AccountResolver(identities))
    assert dict(file_of(result, "app.py").added_commit) == {3: c1, 4: c2}
    assert [s.sha for s in result.commit_stats] == sorted([c1, c2])
    assert {s.account for s in result.commit_stats} == {"alice"}
    assert_commit_invariants(result)


def test_positional_construction_compat() -> None:
    """TC-attribution-43: dựng theo vị trí như M4 → trường M5 mặc định rỗng, chỉ đọc."""
    sha = _sha("b")
    entry = DiffEntry("A", None, "x.py", None, "100644", None, sha, None)
    side = SideInfo("x.py", "100644", sha, 6, True, "Python", False, False, 1)
    fa = FileAttribution(entry, None, side, "lines", (Hunk(0, 0, 0, 1),), {0: A}, {},
                         frozenset(), None, None)
    assert dict(fa.added_commit) == {}
    assert dict(fa.deleted_commit) == {}
    with pytest.raises(TypeError):
        fa.added_commit[0] = sha  # type: ignore[index]
    pa = PeriodAttribution(None, sha, (fa,), (), {}, ())
    assert pa.commit_stats == ()
    assert pa.commit("x") is None
    stats = CommitLineStats(sha, A, 1, 0, 1, 0)
    pa2 = PeriodAttribution(None, sha, (fa,), (), {sha: A}, (), (stats,))
    assert pa2.commit(sha) == stats
    assert pa2.commit(_sha("c")) is None


# ---------- TC-44 .. TC-46: bộ nhớ đệm và gom blame cho D23 (R19, mục 5.6a) ----------
def build_merge_multi_delete(src: Any, n: int = 4, fork_before: bool = False) -> None:
    """TC-44..46: bob xóa n dòng liền kề (v2..) trên feat, alice sửa v8 trên main, carol merge.

    x0 (admin, 2025-12-01) app.py = value_number_0..9; C_START (admin, 2025-12-15) chỉ sửa
    other.py; feat tách từ C_START (hoặc x0 nếu fork_before); alice 2026-01-05 trên main, bob
    2026-01-06 trên feat, carol merge --no-ff 2026-01-07 (parent đầu = main).
    """
    x0 = src.commit("admin0", "2025-12-01T10:00:00+07:00", files={"app.py": j(VALUES)})
    cs = src.commit("admin1", "2025-12-15T10:00:00+07:00", files={"other.py": "o = 1\n"})
    src.git("branch", "feat", x0 if fork_before else cs)
    main = list(VALUES)
    main[8] = "value_number_8 = 88"
    src.commit("alice main", "2026-01-05T10:00:00+07:00", author=ALICE, files={"app.py": j(main)})
    src.checkout("feat")
    src.commit("bob feat", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"app.py": j(VALUES[:2] + VALUES[2 + n:])})
    src.checkout("main")
    src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)


def assert_multi_delete(result: PeriodAttribution, n: int) -> None:
    app = file_of(result, "app.py")
    assert hunk_tuples(app) == [(2, n, 2, 0), (8, 1, 8 - n, 1)]
    assert dict(app.deleted_by) == {**{2 + k: B for k in range(n)}, 8: A}
    assert dict(app.added_by) == {8 - n: A}
    carol = user_of(result, C)
    assert (carol.added_lines, carol.deleted_lines) == (0, 0)
    assert carol.files == ()
    assert result.warnings == ()


class _NoStore(dict):
    """dict không lưu gì: tắt bộ nhớ đệm để so với bản không tối ưu (TC-46)."""

    def __setitem__(self, key: Any, value: Any) -> None:
        pass


_CACHE_ATTRS = ("_anc_cache", "_bases_cache", "_fca_cache", "_blame_cache")


def disable_optimizations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tắt làm nóng gom blame và mọi bộ nhớ đệm của mục 5.6a (resolve_merge vẫn có memo cũ)."""
    orig_init = attribution._Attributor.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        orig_init(self, *args, **kwargs)
        for name in _CACHE_ATTRS:
            setattr(self, name, _NoStore())

    monkeypatch.setattr(attribution._Attributor, "__init__", init)
    monkeypatch.setattr(attribution._Attributor, "_warm_merge", lambda *a, **k: None)


@pytest.mark.parametrize("fork_before", [False, True])
def test_merge_pure_queries_cached(make_repo, cache_root: Path, fork_before: bool) -> None:
    """TC-attribution-44: is_ancestor / merge_bases / first_commit_after không lặp cùng tham số."""
    src = make_repo()
    build_merge_multi_delete(src, n=4, fork_before=fork_before)
    ctx = prepare(src, cache_root)
    seen: dict[str, list[Any]] = {"is_ancestor": [], "merge_bases": [], "first_commit_after": []}
    for name in seen:
        real = getattr(ctx.repo, name)

        def spy(*args: Any, _real: Any = real, _log: list[Any] = seen[name]) -> Any:
            _log.append(tuple(tuple(a) if isinstance(a, list) else a for a in args))
            return _real(*args)

        setattr(ctx.repo, name, spy)
    result = ctx.attribute()

    assert_multi_delete(result, 4)
    assert seen["is_ancestor"], "kịch bản phải đi qua D23"
    for name, calls in seen.items():
        assert len(calls) == len(set(calls)), f"{name} bị gọi lặp: {calls}"


def test_error_not_memoized() -> None:
    """TC-attribution-44: GitError không được ghi nhớ — lần gọi sau vẫn hỏi lại repo."""
    from loc_counter.git_repo import GitError

    class Flaky(FakeRepo):
        def is_ancestor(self, a: str, b: str) -> bool:
            self.calls.append("is_ancestor")
            if self.calls.count("is_ancestor") == 1:
                raise GitError("lỗi giả")
            return True

    anchor = (_sha("a"), "app.py", 3)
    parent = _sha("p")
    repo = Flaky(blames=[[BlameLine(3, _sha("p"), 3, "app.py", False)]])
    att = _attributor(repo)
    with pytest.raises(GitError):
        att._parent_side(anchor, parent, 1)
    assert att._parent_side(anchor, parent, 1) == attribution._PRESENT
    assert repo.calls.count("is_ancestor") == 2


def test_merge_blame_batched(make_repo, cache_root: Path) -> None:
    """TC-attribution-45: số lệnh blame không tỷ lệ theo số dòng xóa trong merge."""
    counts: dict[int, int] = {}
    d23_ranges: dict[int, list[int]] = {}
    for n in (1, 4):
        src = make_repo(f"src{n}")
        build_merge_multi_delete(src, n=n, fork_before=True)
        ctx = prepare(src, cache_root / f"n{n}")
        spy = BlameSpy(ctx.repo)
        result = ctx.attribute()
        assert_multi_delete(result, n)
        counts[n] = len(spy.calls)
        # blame của D23: không kết thúc ở C_END (xuôi tới L, ngược trên parent)
        d23_ranges[n] = [sum(e - s for s, e in c["line_ranges"])
                         for c in spy.calls if c["end"] != ctx.snaps.c_end.sha]
    assert counts[4] == counts[1], counts
    assert d23_ranges[4], "kịch bản phải đi qua D23"
    assert max(d23_ranges[4]) >= 4, d23_ranges


def test_optimizations_do_not_change_result(make_repo, cache_root: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-46: kết quả bằng nhau khi tắt bộ nhớ đệm + làm nóng; bản tắt gọi git nhiều."""
    builders: list[tuple[str, Callable[[Any], Any]]] = [
        ("tc11", build_merge_parallel),
        ("tc12", lambda s: build_merge_parallel(s, fork_before=True)),
        ("tc13", build_merge_self_delete),
        ("tc14", build_conflict),
        ("tc36", build_nested_merge),
        ("tc44a", lambda s: build_merge_multi_delete(s, n=4)),
        ("tc44b", lambda s: build_merge_multi_delete(s, n=4, fork_before=True)),
        ("mixed", lambda s: build_mixed_born_after_base(s)),
        ("nested_multi", lambda s: build_nested_multi(s)),
        ("back_merge", lambda s: build_back_merge(s)),
    ]
    fast: dict[str, PeriodAttribution] = {}
    fast_calls: dict[str, int] = {}
    ctxs: dict[str, Ctx] = {}
    for name, build in builders:
        src = make_repo(name)
        build(src)
        ctxs[name] = prepare(src, cache_root / name)
        spy = BlameSpy(ctxs[name].repo)
        fast[name] = ctxs[name].attribute()
        fast_calls[name] = len(spy.calls)

    with monkeypatch.context() as mp:
        disable_optimizations(mp)
        for name, _ in builders:
            ctx = ctxs[name]
            spy = BlameSpy(ctx.repo)
            slow = ctx.attribute()
            assert slow == fast[name], f"{name}: kết quả khác khi tắt tối ưu"
            assert len(spy.calls) >= fast_calls[name]
            if name in ("tc44a", "tc44b"):
                assert len(spy.calls) > fast_calls[name], name


# ---------- TC-47: song song theo file (R20, mục 5.1a) ----------
def build_many_files(src: Any) -> None:
    """TC-47: 6 file; alice sửa f0..f2 trên main, bob xóa dòng f3, f4 và sửa f5 trên feat, carol
    merge — nhiều cặp file để thật sự chạy song song, có dòng xóa đi qua merge (D23)."""
    files = {f"f{k}.py": j([f"{v}  # file {k}" for v in VALUES]) for k in range(6)}
    src.commit("admin", "2025-12-15T10:00:00+07:00", files=files)
    src.git("branch", "feat")
    main = {f"f{k}.py": j([f"{v}  # file {k}" for v in VALUES[:7]] + [f"alice_{k} = {k}"])
            for k in range(3)}
    src.commit("alice main", "2026-01-05T10:00:00+07:00", author=ALICE, files=main)
    src.checkout("feat")
    feat = {f"f{k}.py": j([f"{v}  # file {k}" for i, v in enumerate(VALUES) if i not in (2, 3)])
            for k in (3, 4)}
    feat["f5.py"] = j([f"{v}  # file 5" for v in VALUES] + ["bob_line = 5"])
    src.commit("bob feat", "2026-01-06T10:00:00+07:00", author=BOB, files=feat)
    src.checkout("main")
    src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)


def test_parallel_equals_serial(make_repo, section14_repo, cache_root: Path,
                                monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-47: (a) ATTRIBUTION_WORKERS = 1 và = 4 cho PeriodAttribution bằng nhau."""
    builders: list[tuple[str, Callable[[Any], Any]]] = [
        ("tc11", build_merge_parallel), ("tc14", build_conflict),
        ("tc16", build_move_cross_file), ("tc17", build_move_block),
        ("tc36", build_nested_merge), ("tc44", lambda s: build_merge_multi_delete(s, n=4)),
        ("mixed", build_mixed_born_after_base), ("nested_multi", build_nested_multi),
        ("many", build_many_files),
    ]
    ctxs = [prepare(section14_repo().src, cache_root / "s14")]
    for name, build in builders:
        src = make_repo(name)
        build(src)
        # thêm một file phụ đổi trong kỳ: mọi repo có ≥ 2 entry → thật sự chạy song song
        src.commit("alice extra", "2026-01-20T10:00:00+07:00", author=ALICE,
                   files={"zz_extra.py": "extra = 1\n"})
        ctxs.append(prepare(src, cache_root / name))
    for ctx in ctxs:
        entries = ctx.repo.diff_tree(ctx.snaps.c_start.sha if ctx.snaps.c_start else None,
                                     ctx.snaps.c_end.sha).entries
        assert len(entries) >= 2, ctx.repo.source
        monkeypatch.setattr(attribution, "ATTRIBUTION_WORKERS", 1)
        serial = ctx.attribute()
        monkeypatch.setattr(attribution, "ATTRIBUTION_WORKERS", 4)
        parallel = ctx.attribute()
        assert parallel == serial
    many = file_of(parallel, "f3.py")
    assert dict(many.deleted_by) == {2: B, 3: B}
    assert len(parallel.files) == 7  # f0..f5 + zz_extra.py


def test_parallel_error_order(make_repo, cache_root: Path,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-47: (b) file thứ 2 và thứ 4 lỗi → ném lỗi của file thứ 2 (thứ tự entries)."""
    import time as _time

    from loc_counter.git_repo import GitError

    src = make_repo()
    build_many_files(src)
    ctx = prepare(src, cache_root)
    entries = ctx.repo.diff_tree(ctx.snaps.c_start.sha, ctx.snaps.c_end.sha).entries
    second, fourth = entries[1], entries[3]
    real = ctx.repo.diff_hunks

    def fake(old_sha: str, new_sha: str) -> list[Hunk]:
        if new_sha == second.new_sha:
            _time.sleep(0.3)  # lỗi của file thứ 4 xảy ra trước về thời gian
            raise GitError(f"hỏng {second.path}")
        if new_sha == fourth.new_sha:
            raise GitError(f"hỏng {fourth.path}")
        return real(old_sha, new_sha)

    ctx.repo.diff_hunks = fake  # type: ignore[method-assign]
    monkeypatch.setattr(attribution, "ATTRIBUTION_WORKERS", 4)
    with pytest.raises(GitError, match=f"hỏng {re.escape(second.path)}$"):
        ctx.attribute()


def test_parallel_context_propagated(make_repo, cache_root: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-47: (c) task chạy ở luồng loc-attr* và thấy ContextVar của luồng gọi."""
    import contextvars
    import threading

    marker: contextvars.ContextVar[str] = contextvars.ContextVar("tc47_marker")
    src = make_repo()
    build_many_files(src)
    ctx = prepare(src, cache_root)
    seen: list[tuple[str | None, str]] = []
    real = ctx.repo.blame

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append((marker.get(None), threading.current_thread().name))
        return real(*args, **kwargs)

    ctx.repo.blame = spy  # type: ignore[method-assign]
    monkeypatch.setattr(attribution, "ATTRIBUTION_WORKERS", 4)
    token = marker.set("phiên-47")
    try:
        ctx.attribute()
    finally:
        marker.reset(token)
    assert seen
    assert {value for value, _ in seen} == {"phiên-47"}
    assert any(name.startswith("loc-attr") for _, name in seen)


# ---------- TC-48: memo không giữ kết quả bị cắt độ sâu; thứ tự lười; nhánh làm nóng ----------
EXTRA = [f"extra_line_number_{k} = {k}" for k in range(3)]


def build_mixed_born_after_base(src: Any) -> None:
    """TC-48 (c): feat tách từ x0; C_START thêm 3 dòng extra (sinh sau merge-base); bob xóa v2, v3
    trên feat; carol merge (tự giải quyết) xóa luôn 3 dòng extra; alice sửa v8 trên main."""
    src.commit("admin0", "2025-12-01T10:00:00+07:00", files={"app.py": j(VALUES)})
    src.git("branch", "feat")
    cs_lines = VALUES[:5] + EXTRA + VALUES[5:]
    src.commit("admin1", "2025-12-15T10:00:00+07:00", files={"app.py": j(cs_lines)})
    main = list(cs_lines)
    main[main.index(VALUES[8])] = "value_number_8 = 88"
    src.commit("alice main", "2026-01-05T10:00:00+07:00", author=ALICE, files={"app.py": j(main)})
    src.checkout("feat")
    src.commit("bob feat", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"app.py": j([v for v in VALUES if v not in (VALUES[2], VALUES[3])])})
    src.checkout("main")
    with contextlib.suppress(subprocess.CalledProcessError):  # xung đột: tự giải quyết bên dưới
        src.git("merge", "--no-ff", "--no-commit", "feat", date="2026-01-07T10:00:00+07:00",
                author=CAROL)
    src.write("app.py", j([v for v in main if v not in (VALUES[2], VALUES[3]) and v not in EXTRA]))
    src.git("add", "app.py")
    src.git("commit", "-q", "-m", "carol merge", date="2026-01-07T10:00:00+07:00", author=CAROL)


def build_nested_multi(src: Any) -> None:
    """TC-48 (c): như TC-36 nhưng bob xóa v2..v4 ở hai file app.py, lib.py (song song + nhiều dòng
    hội tụ ở độ sâu 2)."""
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"app.py": j(VALUES), "lib.py": j([f"lib_{v}" for v in VALUES])})
    src.git("branch", "feat")
    src.git("branch", "feat2")
    main = list(VALUES)
    main[6] = "value_number_6 = 66"
    src.commit("alice main", "2026-01-04T10:00:00+07:00", author=ALICE, files={"app.py": j(main)})
    src.checkout("feat")
    feat = list(VALUES)
    feat[9] = "value_number_9 = 99"
    src.commit("bob feat", "2026-01-05T10:00:00+07:00", author=BOB,
               files={"app.py": j(feat), "lib.py": j([f"lib_{v}" for v in feat])})
    src.checkout("feat2")
    keep = [v for i, v in enumerate(VALUES) if i not in (2, 3, 4)]
    src.commit("bob del", "2026-01-06T09:00:00+07:00", author=BOB,
               files={"app.py": j(keep), "lib.py": j([f"lib_{v}" for v in keep])})
    src.checkout("feat")
    src.merge("feat2", "dave merge feat2", "2026-01-06T12:00:00+07:00", author=DAVE)
    src.checkout("main")
    src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)


def build_back_merge(src: Any) -> dict[str, str]:
    """TC-48 (b): alice xóa v2 trên main, bob sửa v9 trên feat, carol merge feat vào main."""
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"app.py": j(VALUES)})
    src.git("branch", "feat")
    src.commit("alice del v2", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"app.py": j([v for v in VALUES if v != VALUES[2]])})
    src.checkout("feat")
    feat = list(VALUES)
    feat[9] = "value_number_9 = 99"
    feat_tip = src.commit("bob feat", "2026-01-06T10:00:00+07:00", author=BOB,
                          files={"app.py": j(feat)})
    src.checkout("main")
    merge = src.merge("feat", "carol merge", "2026-01-07T10:00:00+07:00", author=CAROL)
    return {"feat_tip": feat_tip, "merge": merge}


def test_depth_truncated_not_memoized(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-48: (a) kết quả chạm MAX_MERGE_DEPTH không vào memo; độ sâu lớn → tính lại."""
    p, q = _sha("p"), _sha("q")
    att = _attributor(FakeRepo(), merge_parents=(p,))
    when = datetime(2026, 1, 5, tzinfo=UTC)
    att.by_sha[_sha("n")] = LogCommit(_sha("n"), (q,), "dave", "d@x", "dave", "d@x", when)
    nested = (_sha("b"), "app.py", 1)
    att._locate = (  # type: ignore[method-assign]
        lambda anchor, parent: (nested, _sha("n")) if parent == p else _sha("x"))
    anchor = (_sha("a"), "app.py", 3)
    monkeypatch.setattr(attribution, "MAX_MERGE_DEPTH", 1)
    assert att.resolve_merge(anchor, _sha("m"), 1) == attribution._UNDETERMINED
    assert att._memo == {}
    monkeypatch.setattr(attribution, "MAX_MERGE_DEPTH", 64)
    assert att.resolve_merge(anchor, _sha("m"), 1) == _sha("x")
    assert att._memo[(*anchor, _sha("m"))] == _sha("x")


def test_lazy_parent_order(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-48: (b) dòng xóa ở parent đầu → không blame parent thứ hai (thứ tự lười)."""
    src = make_repo()
    shas = build_back_merge(src)
    ctx = prepare(src, cache_root)
    merges: list[str] = []
    real_resolve = attribution._Attributor.resolve_merge

    def resolve_spy(self: Any, anchor: Any, merge: str, depth: int) -> str:
        merges.append(merge)
        return real_resolve(self, anchor, merge, depth)

    monkeypatch.setattr(attribution._Attributor, "resolve_merge", resolve_spy)

    def feat_lines(spy: BlameSpy) -> int:
        """Tổng số dòng được blame trên parent thứ hai (đầu feat)."""
        return sum(e - s for c in spy.calls if c["end"] == shas["feat_tip"]
                   for s, e in c["line_ranges"])

    spy = BlameSpy(ctx.repo)
    result = ctx.attribute()
    fast_lines = feat_lines(spy)
    ctx.repo.blame = spy._orig  # type: ignore[method-assign]
    with monkeypatch.context() as mp:
        disable_optimizations(mp)
        slow_spy = BlameSpy(ctx.repo)
        ctx.attribute()
    app = file_of(result, "app.py")
    assert app.deleted_by.get(2) == A  # v2: có kết quả ngay ở parent đầu (main)
    assert app.deleted_by.get(9) == B  # v9: còn ở parent đầu → xét parent thứ hai
    assert shas["merge"] in merges, "kịch bản phải đi qua D23"
    assert fast_lines == feat_lines(slow_spy) > 0  # không làm nóng thừa v2 trên feat


@pytest.mark.parametrize("method", ["_is_ancestor", "_merge_bases", "_first_after",
                                    "_line_blame"])
def test_error_not_memoized_all(method: str) -> None:
    """TC-attribution-44: GitError không được ghi nhớ ở cả 4 truy vấn có bộ nhớ đệm."""
    from loc_counter.git_repo import GitError

    class Flaky(FakeRepo):
        def _once(self, value: Any) -> Any:
            self.calls.append("call")
            if self.calls.count("call") == 1:
                raise GitError("lỗi giả")
            return value

        def is_ancestor(self, a: str, b: str) -> bool:
            return self._once(True)

        def merge_bases(self, a: str, b: str) -> list[str]:
            return self._once([_sha("b")])

        def first_commit_after(self, since: str, until: str, paths: Any) -> str | None:
            return self._once(_sha("c"))

        def blame(self, *args: Any, **kwargs: Any) -> list[Any]:
            return self._once([BlameLine(3, _sha("p"), 3, "app.py", False)])

    repo = Flaky()
    att = _attributor(repo)
    args: dict[str, tuple[Any, ...]] = {
        "_is_ancestor": (_sha("a"), _sha("p")), "_merge_bases": (_sha("a"), _sha("p")),
        "_first_after": (_sha("a"), _sha("p"), ["app.py"]),
        "_line_blame": (_sha("p"), "app.py", _sha("a"), 3)}
    kwargs = {"reverse": True} if method == "_line_blame" else {}
    with pytest.raises(GitError):
        getattr(att, method)(*args[method], **kwargs)
    getattr(att, method)(*args[method], **kwargs)
    getattr(att, method)(*args[method], **kwargs)  # lần 3: lấy từ bộ nhớ đệm
    assert repo.calls.count("call") == 2


# ---------- TC-49 .. TC-50: mode last_commit (R21, mục 5.10) ----------
def attribute_last(ctx: Ctx, commits: list[LogCommit] | None = None,
                   filters: FilterConfig | None = None) -> PeriodAttribution:
    return attribute_period(ctx.repo, ctx.snaps, ctx.commits if commits is None else commits,
                            AccountResolver(), filters or FilterConfig(), mode="last_commit")


def test_last_commit_section14(section14_repo, cache_root: Path,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-49: §14 — app.py thuộc bob (người sửa cuối); không blame/merge-base."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root)

    def forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("mode last_commit không được gọi lệnh này")

    for name in ("blame", "merge_bases", "is_ancestor"):
        monkeypatch.setattr(ctx.repo, name, forbidden)
    result = attribute_last(ctx)

    app = file_of(result, "app.py")
    assert app.granularity == "last"
    assert app.last_touch_by == B
    assert hunk_tuples(app) == [(2, 2, 2, 0), (13, 1, 11, 0), (15, 0, 12, 7)]
    assert dict(app.added_by) == {i: B for i in range(12, 19)}
    assert dict(app.deleted_by) == {2: B, 3: B, 13: B}
    assert set(app.added_commit.values()) == set(app.deleted_commit.values()) != set()
    util = file_of(result, "util.py")
    assert util.granularity == "last" and util.last_touch_by == B
    assert dict(util.added_by) == {i: B for i in range(8)}

    alice, bob = user_of(result, A), user_of(result, B)
    assert (alice.added_code, alice.deleted_code, alice.added_lines, alice.files) == (0, 0, 0, ())
    assert (bob.added_code, bob.deleted_code) == (13, 3)
    assert (bob.added_lines, bob.deleted_lines) == (15, 3)
    assert bob.files == ("app.py", "util.py")
    assert result.warnings == ()
    assert sum(u.added_code - u.deleted_code for u in result.users) == 10  # 10 → 20


def test_last_commit_default_mode_unchanged(section14_repo, cache_root: Path) -> None:
    """TC-attribution-50 (e): mode mặc định = "line" — kết quả như attribute_period cũ."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root)
    assert ctx.attribute() == attribute_period(ctx.repo, ctx.snaps, ctx.commits,
                                               AccountResolver(), FilterConfig(), mode="line")
    with pytest.raises(ValueError, match="mode"):
        attribute_period(ctx.repo, ctx.snaps, ctx.commits, AccountResolver(), FilterConfig(),
                         mode="x")  # type: ignore[arg-type]


def test_last_commit_binary(make_repo, cache_root: Path) -> None:
    """TC-attribution-50 (a): file binary → "last", người sửa cuối, không có dòng."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"d.bin": b"\x00\x01\x02" * 10})
    src.commit("alice", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"d.bin": b"\x00\x01\x03" * 10})
    src.commit("bob", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"d.bin": b"\x00\x01\x04" * 10})
    full = FilterConfig(export_mode="full", exclude_binary=False)
    fa = file_of(attribute_last(prepare(src, cache_root), filters=full), "d.bin")
    assert fa.granularity == "last"
    assert fa.last_touch_by == B
    assert fa.hunks == ()
    assert dict(fa.added_by) == {} and dict(fa.deleted_by) == {}


def test_last_commit_rename(make_repo, cache_root: Path) -> None:
    """TC-attribution-50 (b): rename + sửa → renamed_by = người sửa cuối (alice)."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.git("mv", "old.py", "new.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    src.commit("alice edit", "2026-01-06T10:00:00+07:00", author=ALICE,
               files={"new.py": j([*VALUES, "alice_line = 1"])})
    result = attribute_last(prepare(src, cache_root))
    fa = result.files[0]
    assert fa.entry.status == "R" and fa.granularity == "last"
    assert fa.renamed_by == A and fa.last_touch_by == A
    assert dict(fa.added_by) == {10: A}
    assert result.warnings == ()


def test_last_commit_unknown_account(section14_repo, cache_root: Path) -> None:
    """TC-attribution-50 (c): commit cuối ngoài danh sách commit → UNATTRIBUTED."""
    s14 = section14_repo()
    result = attribute_last(prepare(s14.src, cache_root), commits=[])
    app = file_of(result, "app.py")
    assert app.last_touch_by is None
    assert dict(app.added_by) == {} and dict(app.deleted_by) == {}
    assert [(w.path, w.kind) for w in result.warnings] == [
        ("app.py", WarningKind.UNATTRIBUTED), ("util.py", WarningKind.UNATTRIBUTED)]


def test_last_commit_empty_start(section14_repo, cache_root: Path) -> None:
    """TC-attribution-50 (d): C_START rỗng — mọi dòng của file gán cho người sửa cuối."""
    s14 = section14_repo()
    result = attribute_last(prepare(s14.src, cache_root, start=date(2025, 12, 1)))
    app = file_of(result, "app.py")
    assert app.entry.status == "A"
    assert set(app.added_by.values()) == {B}
    assert dict(app.deleted_by) == {}
    assert user_of(result, B).added_code == 20


def test_last_commit_parallel_equals_serial(section14_repo, cache_root: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-attribution-50 (f): song song = tuần tự ở mode last_commit."""
    s14 = section14_repo()
    ctx = prepare(s14.src, cache_root)

    def digest(workers: int) -> list[Any]:
        monkeypatch.setattr(attribution, "ATTRIBUTION_WORKERS", workers)
        res = attribute_last(ctx)
        return [(f.path, f.granularity, dict(f.added_by), dict(f.deleted_by), f.last_touch_by)
                for f in res.files] + [res.users, res.commit_stats]

    assert digest(1) == digest(4)
