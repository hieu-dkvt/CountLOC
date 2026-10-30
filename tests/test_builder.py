"""Test cho builder.py (spec docs/specs/builder.md, mục 9)."""

from __future__ import annotations

import dataclasses
import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from test_attribution import ALICE, BOB, JAN, VALUES, A, B, j, prepare

from loc_counter import builder, snapshot
from loc_counter.attribution import (
    FileAttribution,
    PeriodAttribution,
    SideInfo,
    attribute_period,
)
from loc_counter.builder import (
    BuiltFile,
    EndExportJob,
    UserExport,
    build_user_export,
    build_user_file,
    export_from_plan,
    find_path_conflicts,
    fix_missing_eol,
    plan_end_exports,
    split_lines_keepends,
    user_tag,
    write_user_export,
)
from loc_counter.classifier import LineClassifier
from loc_counter.config import FilterConfig
from loc_counter.counter import WarningKind, decode_text
from loc_counter.git_repo import DiffEntry, GitRepo, Hunk, LogCommit
from loc_counter.identity import AccountResolver, UserSummary, summarize_users
from loc_counter.snapshot import ExportPlan, Snapshots, plan_export

ADMIN = "admin@example.com"
BOM = b"\xef\xbb\xbf"
FULL = FilterConfig(export_mode="full")
PATH_CONFLICT = WarningKind.PATH_CONFLICT


# ---------- helper ----------
@dataclass
class BCtx:
    """Chuỗi chuẩn: snapshot → commit → attribution → plan_export(C_START)."""

    repo: GitRepo
    snaps: Snapshots
    commits: list[LogCommit]
    filters: FilterConfig
    attr: PeriodAttribution
    start_plan: ExportPlan

    def export(self, users: set[str], tag: str = "t",
               attr: PeriodAttribution | None = None) -> UserExport:
        return build_user_export(self.repo, attr or self.attr, self.start_plan, set(users),
                                 self.filters, tag)


def bprepare(src: Any, cache_root: Path, start: date = JAN[0], end: date = JAN[1],
             filters: FilterConfig | None = None) -> BCtx:
    ctx = prepare(src, cache_root, start, end)
    filters = filters or FilterConfig()
    attr = attribute_period(ctx.repo, ctx.snaps, ctx.commits, AccountResolver(), filters)
    start_plan = plan_export(ctx.repo, ctx.snaps.c_start.sha if ctx.snaps.c_start else None,
                             filters)
    return BCtx(ctx.repo, ctx.snaps, ctx.commits, filters, attr, start_plan)


def content_of(repo: GitRepo, f: BuiltFile) -> bytes:
    return f.data if f.data is not None else repo.read_blob(f.blob_sha)


def files_map(repo: GitRepo, exp: UserExport) -> dict[str, bytes]:
    return {f.path: content_of(repo, f) for f in exp.files}


def built(exp: UserExport, path: str) -> BuiltFile:
    found = [f for f in exp.files if f.path == path]
    assert len(found) == 1, f"không có {path} trong export"
    return found[0]


def loc_of(repo: GitRepo, files: tuple[BuiltFile, ...] | list[BuiltFile]) -> int:
    """LOC trên nội dung export (spec builder mục 9)."""
    classifier = LineClassifier()
    total = 0
    for f in files:
        if f.language is None:
            continue
        total += sum(classifier.classify(decode_text(content_of(repo, f)), f.path, f.cache_key))
    return total


def blob_at(ctx: BCtx, commit: str, path: str) -> str:
    out = ctx.repo.run(["rev-parse", f"{commit}:{path}"])
    return out.decode("ascii").strip()


def summary(account: str, is_bot: bool = False) -> UserSummary:
    return UserSummary(account, 1, 0, [], is_bot)


def short_sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]


# ---------- TC-01 .. TC-02: hàm thuần ----------
@pytest.mark.parametrize(("data", "expected"), [
    (b"", []),
    (b"a", [b"a"]),
    (b"a\r\nb", [b"a\r\n", b"b"]),
    (b"\n\n", [b"\n", b"\n"]),
    (b"a\rb\n", [b"a\rb\n"]),
])
def test_split_lines_keepends(data: bytes, expected: list[bytes]) -> None:
    """TC-builder-01: tách dòng theo git, giữ nguyên byte xuống dòng."""
    assert split_lines_keepends(data) == expected


BASE5 = [b"l0\n", b"l1\n", b"l2\n", b"l3\n", b"l4\n"]
FINAL6 = [b"l0\n", b"bob1\n", b"l2\n", b"alice3\n", b"l3\n", b"l4\n"]
HUNKS2 = [Hunk(1, 1, 1, 1), Hunk(3, 0, 3, 1)]
ADDED2 = {1: B, 3: A}
DELETED2 = {1: B}


@pytest.mark.parametrize(("users", "expected"), [
    ({A}, [b"l0\n", b"l1\n", b"l2\n", b"alice3\n", b"l3\n", b"l4\n"]),
    ({B}, [b"l0\n", b"bob1\n", b"l2\n", b"l3\n", b"l4\n"]),
    (set(), BASE5),
    ({A, B}, FINAL6),
], ids=["alice", "bob", "none", "alice+bob"])
def test_build_user_file_section73(users: set[str], expected: list[bytes]) -> None:
    """TC-builder-02: §7.3 — dòng ngoài hunk giữ; cũ mất khi user xóa; mới thêm khi user viết."""
    assert build_user_file(BASE5, FINAL6, HUNKS2, ADDED2, DELETED2, users) == expected


def test_build_user_file_missing_keys() -> None:
    """TC-builder-02: thiếu khóa trong added_by / deleted_by → dòng cũ giữ, dòng mới bỏ."""
    assert build_user_file(BASE5, FINAL6, HUNKS2, {}, {}, {A, B}) == BASE5


def test_build_user_file_old_before_new() -> None:
    """TC-builder-02: trong hunk dòng cũ (giữ) đứng trước dòng mới (thêm)."""
    out = build_user_file(BASE5, FINAL6, [Hunk(1, 1, 1, 1)], {1: B}, {1: A}, {B})
    assert out == [b"l0\n", b"l1\n", b"bob1\n", b"l2\n", b"l3\n", b"l4\n"]


# ---------- TC-03 .. TC-04: §14 ----------
def test_section14_per_user(section14_repo, cache_root: Path) -> None:
    """TC-builder-03: §14 — LOC start 10; alice 13, bob 17, alice+bob 20 (app.py = blob C_END)."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root)
    repo = ctx.repo
    assert loc_of(repo, export_from_plan(ctx.start_plan).files) == 10

    alice = ctx.export({A}, "alice")
    assert alice.accounts == (A,)
    assert alice.tag == "alice"
    assert [f.path for f in alice.files] == ["app.py"]
    assert loc_of(repo, alice.files) == 13

    bob = ctx.export({B}, "bob")
    assert [f.path for f in bob.files] == ["app.py", "util.py"]
    assert content_of(repo, built(bob, "util.py")) == s14.util.encode()
    assert loc_of(repo, bob.files) == 17

    both = ctx.export({A, B}, "multi-2users")
    assert both.accounts == (A, B)
    app = built(both, "app.py")
    assert app.blob_sha == blob_at(ctx, s14.end_sha, "app.py")
    assert app.data is None
    assert content_of(repo, app) == s14.app_end.encode()
    assert loc_of(repo, both.files) == 20

    end_plan = plan_export(repo, ctx.snaps.c_end.sha, ctx.filters)
    assert loc_of(repo, export_from_plan(end_plan).files) == 20


def test_section14_alice_content(section14_repo, cache_root: Path) -> None:
    """TC-builder-03: app.py của alice = start + 7 dòng alice − 2 dòng alice xóa (v9 còn)."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root)
    app = files_map(ctx.repo, ctx.export({A}))["app.py"].decode("utf-8").splitlines()
    assert "v0 = 0" not in app and "v1 = 1" not in app
    assert "v9 = 9" in app
    assert app[-7:] == ["# alice", "a1 = 1", "a2 = 2", "# alice 2", "a3 = 3", "a4 = 4", "a5 = 5"]
    assert len(app) == 20


def test_section14_empty_start(section14_repo, cache_root: Path) -> None:
    """TC-builder-04: C_START rỗng — start 0; alice 5, bob 8, alice+bob 13, admin+alice+bob 20."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root, start=date(2025, 12, 1))
    repo = ctx.repo
    assert ctx.start_plan.files == []
    assert loc_of(repo, export_from_plan(ctx.start_plan).files) == 0
    assert loc_of(repo, ctx.export({A}).files) == 5
    assert loc_of(repo, ctx.export({B}).files) == 8
    assert loc_of(repo, ctx.export({A, B}).files) == 13
    every = ctx.export({ADMIN, A, B})
    assert loc_of(repo, every.files) == 20
    assert content_of(repo, built(every, "app.py")) == s14.app_end.encode()


# ---------- TC-05 .. TC-08: quy tắc cấp file §7.4 ----------
def test_new_files(make_repo, cache_root: Path) -> None:
    """TC-builder-05: bob tạo util.py, alice tạo e.py 0 byte."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": "a = 1\n"})
    src.commit("bob util", "2026-01-05T10:00:00+07:00", author=BOB,
               files={"util.py": "u = 1\nv = 2\n"})
    src.commit("alice empty", "2026-01-06T10:00:00+07:00", author=ALICE, files={"e.py": b""})
    ctx = bprepare(src, cache_root)

    alice = ctx.export({A})
    assert [f.path for f in alice.files] == ["a.py"]
    bob = ctx.export({B})
    assert [f.path for f in bob.files] == ["a.py", "util.py"]
    util = built(bob, "util.py")
    assert util.blob_sha == blob_at(ctx, ctx.snaps.c_end.sha, "util.py")
    assert util.data is None


def test_deleted_files(make_repo, cache_root: Path) -> None:
    """TC-builder-06: alice xóa d1.py (+ zero.py 0 byte), bob xóa d2.py; zero.py luôn giữ (N2)."""
    src = make_repo()
    cs = src.commit("admin", "2025-12-15T10:00:00+07:00", files={
        "d1.py": "a = 1\nb = 2\n", "d2.py": "c = 3\n", "zero.py": b""})
    src.commit("alice rm", "2026-01-05T10:00:00+07:00", author=ALICE,
               remove=("d1.py", "zero.py"))
    src.commit("bob rm", "2026-01-06T10:00:00+07:00", author=BOB, remove=("d2.py",))
    ctx = bprepare(src, cache_root)

    alice = ctx.export({A})
    assert [f.path for f in alice.files] == ["d2.py", "zero.py"]
    assert built(alice, "d2.py").blob_sha == blob_at(ctx, cs, "d2.py")
    bob = ctx.export({B})
    assert [f.path for f in bob.files] == ["d1.py", "zero.py"]
    assert built(bob, "d1.py").blob_sha == blob_at(ctx, cs, "d1.py")
    for exp in (alice, bob):
        zero = built(exp, "zero.py")
        assert zero.blob_sha == blob_at(ctx, cs, "zero.py")
        assert content_of(ctx.repo, zero) == b""


def build_rename_then_add(src: Any) -> None:
    """TC-07: bob git mv old.py new.py (2026-01-05), alice thêm 1 dòng vào new.py (2026-01-06)."""
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": j(VALUES)})
    src.git("mv", "old.py", "new.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    src.commit("alice add", "2026-01-06T10:00:00+07:00", author=ALICE,
               files={"new.py": j([*VALUES, "alice_line = 1"])})


def test_rename_by_user(make_repo, cache_root: Path) -> None:
    """TC-builder-07: rename — tên theo người đổi tên, nội dung theo dòng của user chọn."""
    src = make_repo()
    build_rename_then_add(src)
    ctx = bprepare(src, cache_root)
    fa = ctx.attr.file("new.py")
    assert fa is not None and fa.entry.status == "R" and fa.renamed_by == B
    start_bytes = j(VALUES).encode()
    end_bytes = j([*VALUES, "alice_line = 1"]).encode()

    assert files_map(ctx.repo, ctx.export({A})) == {"old.py": end_bytes}
    assert files_map(ctx.repo, ctx.export({B})) == {"new.py": start_bytes}
    both = ctx.export({A, B})
    assert files_map(ctx.repo, both) == {"new.py": end_bytes}
    assert built(both, "new.py").blob_sha == fa.new.sha


def test_rename_unresolved_uses_old_name(make_repo, cache_root: Path) -> None:
    """TC-builder-07: renamed_by None (giả lập) → luôn dùng tên cũ (D25)."""
    src = make_repo()
    build_rename_then_add(src)
    ctx = bprepare(src, cache_root)
    attr = dataclasses.replace(ctx.attr, files=tuple(
        dataclasses.replace(fa, renamed_by=None) for fa in ctx.attr.files))
    end_bytes = j([*VALUES, "alice_line = 1"]).encode()
    assert files_map(ctx.repo, ctx.export({A, B}, attr=attr)) == {"old.py": end_bytes}
    assert files_map(ctx.repo, ctx.export({B}, attr=attr)) == {"old.py": j(VALUES).encode()}


def test_rename_into_filtered_dir(make_repo, cache_root: Path) -> None:
    """TC-builder-08: bob đổi src/a.py → vendor/a.py, alice sửa → bob không có file (N9)."""
    src = make_repo()
    a_py = [f"a_value_{i} = {i}" for i in range(10)]
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"src/a.py": j(a_py)})
    edited = j([*a_py, "alice_line = 1"])
    src.commit("alice edit", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"src/a.py": edited})
    src.commit("bob vendor", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"vendor/a.py": edited}, remove=("src/a.py",))
    ctx = bprepare(src, cache_root)
    fa = ctx.attr.file("vendor/a.py")
    assert fa is not None and fa.entry.status == "R" and fa.renamed_by == B

    assert ctx.export({B}).files == ()
    assert files_map(ctx.repo, ctx.export({A})) == {"src/a.py": edited.encode()}


# ---------- TC-09: whole ----------
def test_whole_files(make_repo, cache_root: Path) -> None:
    """TC-builder-09: binary / T theo cả file — người chạm cuối thuộc user chọn → bản C_END."""
    src = make_repo()
    src.add_index_entry("120000", src.hash_blob(b"target"), "link")
    logo0, old0 = b"\x89PNG\r\n\x1a\n\x00logo-start", b"GIF89a\x00\x01old-png-bytes"
    cs = src.commit("admin", "2025-12-15T10:00:00+07:00",
                    files={"logo.png": logo0, "old.png": old0})
    new1 = b"\x00\x00\x00\x0cjP  \r\n\x87\nalice-new-image"
    # Git for Windows (core.symlinks=false) giữ mode 120000 khi add lại → bỏ khỏi index trước
    src.git("rm", "-q", "--cached", "--", "link")
    src.write("link", "link là file\n")
    src.commit("alice", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"new.png": new1}, remove=("old.png",))
    logo1 = b"\x89PNG\r\n\x1a\n\x00logo-bob-version"
    ce = src.commit("bob", "2026-01-06T10:00:00+07:00", author=BOB, files={"logo.png": logo1})
    filters = FilterConfig(export_mode="full", exclude_binary=False)
    ctx = bprepare(src, cache_root, filters=filters)
    statuses = {fa.path: (fa.entry.status, fa.granularity) for fa in ctx.attr.files}
    assert statuses == {"link": ("T", "whole"), "logo.png": ("M", "whole"),
                        "new.png": ("A", "whole"), "old.png": ("D", "whole")}

    alice = ctx.export({A})
    assert [f.path for f in alice.files] == ["link", "logo.png", "new.png"]
    assert built(alice, "new.png").blob_sha == blob_at(ctx, ce, "new.png")
    assert built(alice, "logo.png").blob_sha == blob_at(ctx, cs, "logo.png")
    link = built(alice, "link")
    assert link.blob_sha == blob_at(ctx, ce, "link")
    assert link.mode == "100644"
    assert content_of(ctx.repo, link) == "link là file\n".encode()

    bob = ctx.export({B})
    assert [f.path for f in bob.files] == ["logo.png", "old.png"]
    assert built(bob, "logo.png").blob_sha == blob_at(ctx, ce, "logo.png")
    assert built(bob, "old.png").blob_sha == blob_at(ctx, cs, "old.png")


# ---------- TC-10 .. TC-11: EOL, byte ----------
@pytest.mark.parametrize(("lines", "expected", "fixed"), [
    ([b"a = 1\n", b"c = 3", b"d = 4\n"], [b"a = 1\n", b"c = 3\n", b"d = 4\n"], [1]),
    ([BOM + b"a\r\n", b"c", b"d\r\n"], [BOM + b"a\r\n", b"c\r\n", b"d\r\n"], [1]),
    ([b"a\r\n", b"b", b"c\n"], [b"a\r\n", b"b\n", b"c\n"], [1]),
    ([b"a", b"b", b"c"], [b"a\n", b"b\n", b"c"], [0, 1]),
    ([b"a\n", b"b"], [b"a\n", b"b"], []),
    ([], [], []),
], ids=["lf", "crlf_bom", "tie", "no_eol", "last_kept", "empty"])
def test_fix_missing_eol(lines: list[bytes], expected: list[bytes], fixed: list[int]) -> None:
    """TC-builder-10: EOL đa số (hòa / không có → \\n), dòng cuối giữ nguyên."""
    assert fix_missing_eol(lines) == (expected, fixed)


@pytest.mark.parametrize(("base", "bob_v", "alice_v", "alice_expected"), [
    (b"a = 1\nc = 3", b"a = 1\nc = 3\n", b"a = 1\nc = 3\nd = 4\n", b"a = 1\nc = 3\nd = 4\n"),
    (BOM + b"a = 1\r\nc = 3", BOM + b"a = 1\r\nc = 3\r\n", BOM + b"a = 1\r\nc = 3\r\nd = 4\r\n",
     BOM + b"a = 1\r\nc = 3\r\nd = 4\r\n"),
], ids=["lf", "crlf_bom"])
def test_missing_eol_export(make_repo, cache_root: Path, base: bytes, bob_v: bytes,
                            alice_v: bytes, alice_expected: bytes) -> None:
    """TC-builder-10: base thiếu EOL, bob thêm EOL, alice thêm d = 4 → MISSING_EOL cho alice."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"x.py": base})
    src.commit("bob eol", "2026-01-05T10:00:00+07:00", author=BOB, files={"x.py": bob_v})
    src.commit("alice d", "2026-01-06T10:00:00+07:00", author=ALICE, files={"x.py": alice_v})
    ctx = bprepare(src, cache_root)

    alice = ctx.export({A})
    assert files_map(ctx.repo, alice) == {"x.py": alice_expected}
    eol = [w for w in alice.warnings if w.kind == WarningKind.MISSING_EOL]
    assert [(w.path, w.message) for w in eol] == [
        ("x.py", "Thêm xuống dòng cho dòng 2 thiếu EOL ở giữa file đã dựng")]
    bob = ctx.export({B})
    assert files_map(ctx.repo, bob) == {"x.py": base}
    assert not [w for w in bob.warnings if w.kind == WarningKind.MISSING_EOL]


def test_keep_bytes_crlf_bom(make_repo, cache_root: Path) -> None:
    """TC-builder-11: CRLF + BOM — dòng không đổi giữ byte start, BOM ở byte 0."""
    src = make_repo()
    base = BOM + b"line_0 = 0\r\nline_1 = 1\r\nline_2 = 2\r\nline_3 = 3\r\nline_4 = 4\r\n"
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"c.py": base})
    v1 = base.replace(b"line_2 = 2\r\n", b"alice_2 = 22\r\n")
    src.commit("alice mid", "2026-01-05T10:00:00+07:00", author=ALICE, files={"c.py": v1})
    v2 = v1.replace(b"line_4 = 4\r\n", b"bob_4 = 44\r\n")
    src.commit("bob last", "2026-01-06T10:00:00+07:00", author=BOB, files={"c.py": v2})
    ctx = bprepare(src, cache_root)

    data = files_map(ctx.repo, ctx.export({A}))["c.py"]
    assert data == BOM + b"line_0 = 0\r\nline_1 = 1\r\nalice_2 = 22\r\nline_3 = 3\r\nline_4 = 4\r\n"
    assert data.startswith(BOM)
    assert data.count(BOM) == 1


# ---------- TC-12, TC-21: zip ----------
def test_zip_reproducible(section14_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-builder-12: ghi export alice hai lần (files đảo thứ tự) → SHA-256 bằng nhau."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root)
    exp = ctx.export({A}, "alice")
    z1 = write_user_export(ctx.repo, exp, tmp_path / "a" / "end.zip", ctx.snaps.c_end,
                           "Asia/Bangkok")
    reversed_exp = dataclasses.replace(exp, files=tuple(reversed(exp.files)))
    z2 = write_user_export(ctx.repo, reversed_exp, tmp_path / "b" / "end.zip", ctx.snaps.c_end,
                           "Asia/Bangkok")
    assert hashlib.sha256(z1.read_bytes()).digest() == hashlib.sha256(z2.read_bytes()).digest()
    with zipfile.ZipFile(z1) as zf:
        # C_END = "bob del" 2026-01-08T10:00:00+07:00
        assert {info.date_time for info in zf.infolist()} == {(2026, 1, 8, 10, 0, 0)}


def test_write_user_export(section14_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-builder-21: zip đúng files theo path, trùng byte, external_attr theo mode."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root)
    exp = ctx.export({A}, "alice")
    zip_path = tmp_path / "out" / "end_2026-01-31_alice.zip"
    assert write_user_export(ctx.repo, exp, zip_path, ctx.snaps.c_end, "Asia/Bangkok") == zip_path
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == [f.path for f in exp.files]
        for f in exp.files:
            assert zf.read(f.path) == content_of(ctx.repo, f)
            mode = 0o100755 if f.mode == "100755" else 0o100644
            assert zf.getinfo(f.path).external_attr >> 16 == mode


def test_builtfile_zip_entry_and_cache_key() -> None:
    """TC-builder-21: BuiltFile.zip_entry / cache_key (blob hoặc sha1 nội dung)."""
    sha = "a" * 40
    f1 = BuiltFile("x.py", "100755", "Python", blob_sha=sha)
    assert f1.zip_entry() == snapshot.ZipEntry("x.py", "100755", sha)
    assert f1.cache_key == sha
    f2 = BuiltFile("y.py", "100644", "Python", data=b"y = 1\n")
    assert f2.zip_entry() == snapshot.ZipEntry("y.py", "100644", None, b"y = 1\n")
    assert f2.cache_key == hashlib.sha1(b"y = 1\n").hexdigest()


# ---------- TC-13 .. TC-14: đường dẫn ----------
def conflict_message(other: str) -> str:
    return (f"Đường dẫn xung đột với {other} khi giải nén (file/thư mục trùng tên hoặc chỉ "
            "khác hoa thường); cả hai được giữ trong zip")


def test_path_conflict_file_dir(make_repo, cache_root: Path) -> None:
    """TC-builder-13: (a) alice git rm x, bob tạo x/z.py → bob có cả hai + PATH_CONFLICT."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"x": "k = 1\n", "keep.py": "z = 1\n"})
    src.commit("alice rm x", "2026-01-05T10:00:00+07:00", author=ALICE, remove=("x",))
    src.commit("bob x/z.py", "2026-01-06T10:00:00+07:00", author=BOB, files={"x/z.py": "q = 1\n"})
    ctx = bprepare(src, cache_root, filters=FULL)

    bob = ctx.export({B})
    assert [f.path for f in bob.files] == ["keep.py", "x", "x/z.py"]
    conflicts = [(w.path, w.message) for w in bob.warnings if w.kind == PATH_CONFLICT]
    assert conflicts == [("x", conflict_message("x/z.py")), ("x/z.py", conflict_message("x"))]
    alice = ctx.export({A})
    assert [f.path for f in alice.files] == ["keep.py"]
    assert not [w for w in alice.warnings if w.kind == PATH_CONFLICT]


def test_path_conflict_rename(make_repo, cache_root: Path) -> None:
    """TC-builder-13: (b) alice mv x.py y.py, bob tạo x.py/z.py → bob có x.py và x.py/z.py."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"x.py": "k = 1\n"})
    src.git("mv", "x.py", "y.py")
    src.commit("alice mv", "2026-01-05T10:00:00+07:00", author=ALICE)
    src.commit("bob x.py/z.py", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"x.py/z.py": "q = 1\n"})
    ctx = bprepare(src, cache_root)

    bob = ctx.export({B})
    assert [f.path for f in bob.files] == ["x.py", "x.py/z.py"]
    conflicts = [(w.path, w.message) for w in bob.warnings if w.kind == PATH_CONFLICT]
    assert conflicts == [("x.py", conflict_message("x.py/z.py")),
                         ("x.py/z.py", conflict_message("x.py"))]
    assert [f.path for f in ctx.export({A}).files] == ["y.py"]


def test_find_path_conflicts() -> None:
    """TC-builder-13: (c) find_path_conflicts — file/thư mục và khác hoa thường."""
    assert find_path_conflicts(["A.py", "a.py", "b", "b/c", "bc"]) == [("A.py", "a.py"),
                                                                       ("b", "b/c")]


def test_duplicate_path_defensive(make_repo, cache_root: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-builder-14: PeriodAttribution giả có 2 entry A cùng new_path → ValueError."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": "a = 1\n"})
    src.commit("alice", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"x.py": "x = 1\n", "y.py": "y = 2\n"})
    ctx = bprepare(src, cache_root)
    ce = ctx.snaps.c_end.sha
    fakes = []
    for name in ("x.py", "y.py"):
        sha = blob_at(ctx, ce, name)
        entry = DiffEntry("A", None, "dup.py", None, "100644", None, sha, None)
        side = SideInfo("dup.py", "100644", sha, 6, True, "Python", False, False, 1)
        fakes.append(FileAttribution(entry, None, side, "lines", (Hunk(0, 0, 0, 1),), {0: A},
                                     {}, frozenset(), None, None))
    attr = dataclasses.replace(ctx.attr, files=tuple(fakes))
    calls: list[Any] = []
    monkeypatch.setattr(snapshot, "write_entries", lambda *a, **k: calls.append(a))
    if hasattr(builder, "write_entries"):
        monkeypatch.setattr(builder, "write_entries", lambda *a, **k: calls.append(a))

    with pytest.raises(ValueError):
        ctx.export({A}, attr=attr)
    assert calls == []


# ---------- TC-15 .. TC-16: tag và danh sách zip ----------
@pytest.mark.parametrize(("accounts", "kwargs", "expected"), [
    (["alice"], {}, "alice"),
    (["alice@example.com"], {}, f"alice_example.com-{short_sha1('alice@example.com')}"),
    (["a", "b"], {}, "multi-2users"),
    (["alice"], {"taken": ["Alice"]}, f"alice-{short_sha1('alice')}"),
    (["all"], {}, f"all-{short_sha1('all')}"),
    (["multi-2users"], {}, f"multi-2users-{short_sha1('multi-2users')}"),
    (["alice", "bob"], {"all_users": True}, "all"),
], ids=["plain", "email", "multi", "taken", "all", "multi_name", "all_users"])
def test_user_tag(accounts: list[str], kwargs: dict[str, Any], expected: str) -> None:
    """TC-builder-15: user_tag — tên, hậu tố sha1 khi safe_name đổi / trùng / tên dành riêng."""
    assert user_tag(accounts, **kwargs) == expected


def test_user_tag_empty() -> None:
    """TC-builder-15: user_tag([]) → ValueError."""
    with pytest.raises(ValueError):
        user_tag([])


PERIOD_USERS = [summary("alice"), summary("bob")]
PERIOD_USERS_BOT = [summary("alice"), summary("bob"), summary("dependabot[bot]", is_bot=True)]


@pytest.mark.parametrize(("selected", "users", "kwargs", "expected"), [
    (None, PERIOD_USERS, {}, [EndExportJob("all", None)]),
    (None, PERIOD_USERS_BOT, {"exclude_bots": True},
     [EndExportJob("all", ("alice", "bob"))]),
    (None, PERIOD_USERS, {"exclude_bots": True}, [EndExportJob("all", None)]),
    (None, PERIOD_USERS, {"separate": True},
     [EndExportJob("all", None), EndExportJob("alice", ("alice",)),
      EndExportJob("bob", ("bob",))]),
    (["alice"], PERIOD_USERS, {"separate": True}, [EndExportJob("alice", ("alice",))]),
    (["bob", "alice"], PERIOD_USERS, {"separate": True},
     [EndExportJob("multi-2users", ("alice", "bob")), EndExportJob("alice", ("alice",)),
      EndExportJob("bob", ("bob",))]),
], ids=["all", "all_exclude_bot", "all_exclude_no_bot", "all_separate", "one_separate",
        "two_separate"])
def test_plan_end_exports(selected: list[str] | None, users: list[UserSummary],
                          kwargs: dict[str, Any], expected: list[EndExportJob]) -> None:
    """TC-builder-16: plan_end_exports theo D21 / Q29."""
    assert plan_end_exports(selected, users, **kwargs) == expected


def test_plan_end_exports_empty_selection() -> None:
    """TC-builder-16: chọn rỗng → ValueError."""
    with pytest.raises(ValueError):
        plan_end_exports([], PERIOD_USERS)


# ---------- TC-17 .. TC-22 ----------
def test_exclude_bots(section14_repo, cache_root: Path) -> None:
    """TC-builder-17: 'Tất cả' + loại bot → dựng bằng builder, không có deps.txt; LOC 20."""
    s14 = section14_repo(bot=True)
    ctx = bprepare(s14.src, cache_root, filters=FULL)
    period_users = summarize_users(ctx.commits, AccountResolver()).users
    assert any(u.is_bot for u in period_users)

    jobs = plan_end_exports(None, period_users, exclude_bots=True)
    assert jobs == [EndExportJob("all", (A, B))]
    no_bot = ctx.export(set(jobs[0].accounts), jobs[0].tag)
    assert "deps.txt" not in [f.path for f in no_bot.files]
    assert loc_of(ctx.repo, no_bot.files) == 20

    assert plan_end_exports(None, period_users) == [EndExportJob("all", None)]
    end_plan = plan_export(ctx.repo, ctx.snaps.c_end.sha, FULL)
    every = export_from_plan(end_plan)
    assert every.accounts is None
    assert every.tag == "all"
    assert "deps.txt" in [f.path for f in every.files]
    assert loc_of(ctx.repo, every.files) == 20


def test_input_validation(section14_repo, cache_root: Path) -> None:
    """TC-builder-18: start_plan không khớp C_START → ValueError; users rỗng → export start."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root)
    wrong = plan_export(ctx.repo, ctx.snaps.c_end.sha, ctx.filters)
    with pytest.raises(ValueError):
        build_user_export(ctx.repo, ctx.attr, wrong, {A}, ctx.filters, "alice")

    empty = ctx.export(set())
    start = export_from_plan(ctx.start_plan)
    assert empty.files == start.files
    assert all(f.blob_sha is not None and f.data is None for f in empty.files)


def test_bom_mid_file(make_repo, cache_root: Path) -> None:
    """TC-builder-19: BOM rơi vào dòng 2 khi dòng 0 cũ được giữ (N6) — đúng §7.3."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"b.py": BOM + b"# v0\nx = 1\n"})
    src.commit("alice v1", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"b.py": BOM + b"# v1\nx = 1\n"})
    src.commit("bob v2", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"b.py": BOM + b"# v2\nx = 1\n"})
    ctx = bprepare(src, cache_root)
    fa = ctx.attr.file("b.py")
    assert fa.deleted_by.get(0) == A
    assert fa.added_by.get(0) == B

    data = files_map(ctx.repo, ctx.export({B}))["b.py"]
    assert data == BOM + b"# v0\n" + BOM + b"# v2\nx = 1\n"


def test_no_commit_in_period(section14_repo, cache_root: Path) -> None:
    """TC-builder-20: C_START == C_END → export = start_plan (blob), không cảnh báo mới."""
    s14 = section14_repo()
    ctx = bprepare(s14.src, cache_root, start=date(2026, 1, 20))
    assert ctx.snaps.c_start.sha == ctx.snaps.c_end.sha
    assert ctx.attr.files == ()
    exp = ctx.export({A, B})
    start = export_from_plan(ctx.start_plan)
    assert exp.files == start.files
    assert all(f.blob_sha is not None for f in exp.files)
    assert exp.warnings == tuple(sorted(ctx.start_plan.warnings, key=lambda w: (w.path, w.kind)))


def test_filter_warnings(make_repo, cache_root: Path) -> None:
    """TC-builder-22: giữ BINARY logo.png của start_plan; big.py skip → TOO_LARGE như C_END."""
    src = make_repo()
    big = j([f"big_value_{i:03d} = 'xxxxxxxxxxxxxxxxxxxxxxxx'" for i in range(40)])
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"logo.png": b"\x89PNG\r\n\x1a\n\x00\x00logo", "big.py": big})
    src.commit("alice big", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"big.py": big + "alice_extra = 'more more more'\n" * 20})
    filters = FilterConfig(max_file_size_kb=1)
    ctx = bprepare(src, cache_root, filters=filters)
    assert ctx.attr.file("big.py").granularity == "skip"
    end_plan = plan_export(ctx.repo, ctx.snaps.c_end.sha, filters)

    exp = ctx.export({A})
    assert exp.files == ()
    start_binary = [w for w in ctx.start_plan.warnings if w.path == "logo.png"]
    assert [w.kind for w in start_binary] == [WarningKind.BINARY]
    end_big = [w for w in end_plan.warnings if w.path == "big.py"]
    assert [w.kind for w in end_big] == [WarningKind.TOO_LARGE]
    assert list(exp.warnings) == end_big + start_binary


# ---------- bổ sung theo review: TC-10 (bị lọc), TC-23, TC-24 ----------
def test_missing_eol_not_reported_when_filtered(make_repo, cache_root: Path) -> None:
    """TC-builder-10: alice đổi tên sang vendor/ (bị lọc) → không có file, không MISSING_EOL."""
    src = make_repo()
    head = [f"value_line_{i} = {i}" for i in range(6)]
    base = "\n".join([*head, "c = 3"])  # thiếu EOL cuối
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"x.py": base})
    src.commit("bob eol", "2026-01-05T10:00:00+07:00", author=BOB, files={"x.py": base + "\n"})
    (src.path / "vendor").mkdir(exist_ok=True)
    src.git("mv", "x.py", "vendor/x.py")
    src.commit("alice mv", "2026-01-06T10:00:00+07:00", author=ALICE)
    src.commit("alice d", "2026-01-07T10:00:00+07:00", author=ALICE,
               files={"vendor/x.py": base + "\nd = 4\n"})
    ctx = bprepare(src, cache_root)
    fa = ctx.attr.file("vendor/x.py")
    assert fa is not None and fa.entry.status == "R" and fa.renamed_by == A

    alice = ctx.export({A})
    assert alice.files == ()
    assert not [w for w in alice.warnings if w.kind == WarningKind.MISSING_EOL]


def test_skip_special_sides(make_repo, cache_root: Path) -> None:
    """TC-builder-23: symlink / submodule thay đổi → skip: không file, không cảnh báo, không đọc."""
    src = make_repo()
    src.add_index_entry("120000", src.hash_blob(b"target_a"), "link.py")
    src.add_index_entry("160000", "1" * 40, "sub")
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": "a = 1\n"})
    src.add_index_entry("120000", src.hash_blob(b"target_b"), "link.py")
    src.add_index_entry("160000", "2" * 40, "sub")
    src.commit("bob", "2026-01-05T10:00:00+07:00", author=BOB)
    ctx = bprepare(src, cache_root)
    special = {fa.path: fa.granularity for fa in ctx.attr.files}
    assert special == {"link.py": "skip", "sub": "skip"}
    requested: list[list[str]] = []
    real = ctx.repo.read_blobs

    def spy(shas):
        shas = list(shas)
        requested.append(shas)
        return real(shas)

    ctx.repo.read_blobs = spy  # type: ignore[method-assign]
    bob = ctx.export({B})
    assert [f.path for f in bob.files] == ["a.py"]
    assert bob.warnings == ()
    assert requested == []  # chỉ có phía symlink / gitlink → không đọc blob nào


def test_ranges_text_and_eol_indices() -> None:
    """TC-builder-24: khoảng 1-based gộp liền kề; fix_missing_eol sửa 2 dòng liền nhau."""
    assert builder._ranges_text([4, 1, 2, 7, 2]) == "2–3, 5, 8"
    out, fixed = fix_missing_eol([b"a", b"b", b"c\n"])
    assert out == [b"a\n", b"b\n", b"c\n"] and fixed == [0, 1]
    assert builder._ranges_text(fixed) == "1–2"


# ---------- TC-25 .. TC-30: kiểm đường dẫn khi giải nén (M5) ----------
WINDOWS_PATH = WarningKind.WINDOWS_PATH


def reserved_issue(part: str, stem: str) -> str:
    return f'"{part}" trùng tên thiết bị dành riêng của Windows ({stem})'


def chars_issue(part: str) -> str:
    return f'"{part}" chứa ký tự không hợp lệ trên Windows (<>"|?* hoặc ký tự điều khiển)'


def trailing_issue(part: str) -> str:
    return f'"{part}" kết thúc bằng dấu chấm hoặc khoảng trắng (Windows tự bỏ khi giải nén)'


def windows_message(*issues: str) -> str:
    return ("Đường dẫn có thể không giải nén đúng trên Windows: " + "; ".join(issues)
            + "; file vẫn được giữ trong zip và được đếm LOC")


def test_path_conflict_warnings(caplog: pytest.LogCaptureFixture) -> None:
    """TC-builder-25: path_conflict_warnings — cả hai path mỗi cặp, đúng thứ tự, log có label."""
    with caplog.at_level("WARNING", logger="loc_counter.builder"):
        got = builder.path_conflict_warnings(iter(["b/c", "A.py", "a.py", "b", "bc", "a.py"]),
                                             label="start")
    assert [(w.kind, w.path, w.message) for w in got] == [
        (PATH_CONFLICT, "A.py", conflict_message("a.py")),
        (PATH_CONFLICT, "a.py", conflict_message("A.py")),
        (PATH_CONFLICT, "b", conflict_message("b/c")),
        (PATH_CONFLICT, "b/c", conflict_message("b")),
    ]
    logged = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(logged) == 2 and all("start" in m for m in logged)
    assert builder.path_conflict_warnings([]) == []
    assert builder.path_conflict_warnings(["a.py", "b.py"]) == []
    caplog.clear()
    with caplog.at_level("WARNING", logger="loc_counter.builder"):
        builder.path_conflict_warnings(["x", "X"])
    assert [r.getMessage() for r in caplog.records] == ["Đường dẫn xung đột: 'X' ↔ 'x'"]


def test_built_file_requires_one_source() -> None:
    """TC-builder-31: BuiltFile cần đúng một trong blob_sha / data."""
    with pytest.raises(ValueError):
        BuiltFile("x.py", "100644", None)
    with pytest.raises(ValueError):
        BuiltFile("x.py", "100644", None, blob_sha="a" * 40, data=b"x")


def test_build_user_export_uses_path_conflict_warnings(make_repo, cache_root: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-builder-26: build_user_export gọi path_conflict_warnings 1 lần (giữ hành vi)."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"x": "k = 1\n", "keep.py": "z = 1\n"})
    src.commit("alice rm x", "2026-01-05T10:00:00+07:00", author=ALICE, remove=("x",))
    src.commit("bob x/z.py", "2026-01-06T10:00:00+07:00", author=BOB, files={"x/z.py": "q = 1\n"})
    ctx = bprepare(src, cache_root, filters=FULL)
    calls: list[tuple[set[str], str]] = []
    real = builder.path_conflict_warnings

    def spy(paths, label=""):
        paths = list(paths)
        calls.append((set(paths), label))
        return real(paths, label)

    monkeypatch.setattr(builder, "path_conflict_warnings", spy)
    bob = ctx.export({B}, tag="bob")
    assert calls == [({"keep.py", "x", "x/z.py"}, "bob")]
    monkeypatch.undo()
    expected = sorted(real([f.path for f in bob.files]), key=lambda w: (w.path, w.kind))
    assert [w for w in bob.warnings if w.kind == PATH_CONFLICT] == expected
    assert not [w for w in bob.warnings if w.kind == WINDOWS_PATH]


@pytest.mark.parametrize(("path", "part", "stem"), [
    ("CON", "CON", "CON"),
    ("con.py", "con.py", "CON"),
    ("NUL.tar.gz", "NUL.tar.gz", "NUL"),
    ("Aux .py", "Aux .py", "AUX"),
    ("src/com1/x.py", "com1", "COM1"),
    ("LPT9", "LPT9", "LPT9"),
    ("COM0.c", "COM0.c", "COM0"),
    ("com¹.py", "com¹.py", "COM¹"),
    ("LPT³", "LPT³", "LPT³"),
    ("prn.txt", "prn.txt", "PRN"),
])
def test_windows_path_issues_reserved(path: str, part: str, stem: str) -> None:
    """TC-builder-27: tên thiết bị dành riêng của Windows (mọi phần, có/không đuôi)."""
    assert builder.windows_path_issues(path) == [reserved_issue(part, stem)]


@pytest.mark.parametrize("path", [
    "CONSOLE.py", "COM10.py", "nul_.py", "connect.py", "src/null/x.py", "xcon.py", "lpt.py",
])
def test_windows_path_issues_not_reserved(path: str) -> None:
    """TC-builder-27: tên giống nhưng không phải tên thiết bị → hợp lệ."""
    assert builder.windows_path_issues(path) == []


@pytest.mark.parametrize("part", [
    "a<b.py", "a>b", 'a"b', "a|b", "a?b", "a*b", "a\x01b.py", "a\x1fb",
])
def test_windows_path_issues_chars(part: str) -> None:
    """TC-builder-28: ký tự cấm <>"|?* và ký tự điều khiển."""
    assert builder.windows_path_issues(part) == [chars_issue(part)]
    assert builder.windows_path_issues(f"src/{part}") == [chars_issue(part)]


@pytest.mark.parametrize(("path", "part"), [
    ("a.py.", "a.py."), ("a.py ", "a.py "), ("dir./x.py", "dir."), ("dir /x.py", "dir "),
])
def test_windows_path_issues_trailing(path: str, part: str) -> None:
    """TC-builder-28: phần kết thúc bằng dấu chấm / khoảng trắng (cả thư mục)."""
    assert builder.windows_path_issues(path) == [trailing_issue(part)]


@pytest.mark.parametrize("path", [
    "src/ok.py", ".gitignore", "a.b/c.py", "ü.py", "a b.py", "a..b.py", "a/../b//./c.py",
])
def test_windows_path_issues_valid(path: str) -> None:
    """TC-builder-28: đường dẫn hợp lệ trên Windows → []."""
    assert builder.windows_path_issues(path) == []


def test_windows_path_issues_order() -> None:
    """TC-builder-28: nhiều lý do — theo phần từ trái sang phải, rồi theo quy tắc."""
    assert builder.windows_path_issues("CON./a?.py ") == [
        reserved_issue("CON.", "CON"), trailing_issue("CON."),
        chars_issue("a?.py "), trailing_issue("a?.py "),
    ]


def test_windows_path_warnings(caplog: pytest.LogCaptureFixture) -> None:
    """TC-builder-29: một WINDOWS_PATH mỗi path lỗi, bỏ trùng, sắp theo path, log WARNING."""
    with caplog.at_level("WARNING", logger="loc_counter.builder"):
        got = builder.windows_path_warnings(["b/NUL.py", "ok.py", "a.py.", "b/NUL.py"])
    assert [(w.kind, w.path, w.message) for w in got] == [
        (WINDOWS_PATH, "a.py.", windows_message(trailing_issue("a.py."))),
        (WINDOWS_PATH, "b/NUL.py", windows_message(reserved_issue("NUL.py", "NUL"))),
    ]
    logged = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(logged) == 2
    assert any("'a.py.'" in m for m in logged) and any("'b/NUL.py'" in m for m in logged)
    assert builder.windows_path_warnings([]) == []


def test_start_and_all_exports_path_checks(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-builder-30: start / all — plan không tự cảnh báo; hàm M5 phát hai loại cảnh báo."""
    src = make_repo()
    src.git("config", "core.protectNTFS", "false")  # cho phép tên kiểu NUL.py trong index
    for path, data in (("A.py", b"A = 1\n"), ("a.py", b"a = 1\n"), ("NUL.py", b"n = 1\n"),
                       ("src/a.py.", b"d = 1\n")):
        src.add_index_entry("100644", src.hash_blob(data), path)
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"ok.py": "ok = 1\n"})
    src.add_index_entry("100644", src.hash_blob(b"n = 1\nn2 = 2\n"), "NUL.py")
    src.commit("alice NUL.py", "2026-01-05T10:00:00+07:00", author=ALICE)
    ctx = bprepare(src, cache_root, filters=FULL)
    paths = ["A.py", "NUL.py", "a.py", "ok.py", "src/a.py."]

    start_plan = ctx.start_plan
    end_plan = plan_export(ctx.repo, ctx.snaps.c_end.sha, FULL)
    for plan in (start_plan, end_plan):
        assert sorted(f.path for f in plan.files) == paths
        assert not [w for w in plan.warnings if w.kind == WarningKind.UNSAFE_PATH]
    everything = export_from_plan(end_plan)
    assert not [w for w in everything.warnings if w.kind in (PATH_CONFLICT, WINDOWS_PATH)]

    start_paths = [f.path for f in start_plan.files]
    assert [(w.path, w.message) for w in builder.path_conflict_warnings(start_paths)] == [
        ("A.py", conflict_message("a.py")), ("a.py", conflict_message("A.py"))]
    assert [(w.kind, w.path) for w in builder.windows_path_warnings(start_paths)] == [
        (WINDOWS_PATH, "NUL.py"), (WINDOWS_PATH, "src/a.py.")]

    alice = ctx.export({A}, tag="alice")
    assert sorted(f.path for f in alice.files) == paths
    assert [w.path for w in alice.warnings if w.kind == PATH_CONFLICT] == ["A.py", "a.py"]
    assert not [w for w in alice.warnings if w.kind == WINDOWS_PATH]
    assert files_map(ctx.repo, alice)["NUL.py"] == b"n = 1\nn2 = 2\n"

    zip_path = write_user_export(ctx.repo, alice, tmp_path / "alice.zip", ctx.snaps.c_end,
                                 "Asia/Bangkok")
    with zipfile.ZipFile(zip_path) as zf:
        assert sorted(zf.namelist()) == paths
        assert zf.read("NUL.py") == b"n = 1\nn2 = 2\n"
        assert zf.read("src/a.py.") == b"d = 1\n"


# ---------- TC-32: mode last_commit ----------
def test_last_commit_export(section14_repo, cache_root: Path) -> None:
    """TC-builder-32: export theo người sửa cuối — alice 10 (app.py bản start), bob 20."""
    s14 = section14_repo()
    base = bprepare(s14.src, cache_root)
    attr = attribute_period(base.repo, base.snaps, base.commits, AccountResolver(),
                            base.filters, mode="last_commit")
    repo = base.repo

    alice = base.export({A}, "alice", attr)
    assert [f.path for f in alice.files] == ["app.py"]
    assert built(alice, "app.py").blob_sha == blob_at(base, base.snaps.c_start.sha, "app.py")
    assert loc_of(repo, alice.files) == 10

    bob = base.export({B}, "bob", attr)
    assert [f.path for f in bob.files] == ["app.py", "util.py"]
    assert content_of(repo, built(bob, "app.py")) == s14.app_end.encode()
    assert loc_of(repo, bob.files) == 20

    both = base.export({A, B}, "multi-2users", attr)
    assert files_map(repo, both) == files_map(repo, bob)
    assert loc_of(repo, both.files) == 20
    assert files_map(repo, base.export({B}, "bob", attr)) == files_map(repo, bob)
