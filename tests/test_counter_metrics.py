"""Test M5 cho counter.py (spec docs/specs/counter.md, mục 9 — TC-counter-18..44)."""

from __future__ import annotations

import logging
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_attribution import ALICE, BOB, CAROL, A, B, j, prepare

from loc_counter.attribution import (
    CommitLineStats,
    FileAttribution,
    PeriodAttribution,
    SideInfo,
    UserLineStats,
    attribute_period,
)
from loc_counter.builder import (
    BuiltFile,
    UserExport,
    build_user_export,
    export_from_plan,
    write_user_export,
)
from loc_counter.classifier import LineClassifier, content_sha1
from loc_counter.config import FilterConfig
from loc_counter.counter import (
    CROSS_CHECK_THRESHOLD_PERCENT,
    NO_PR_LABEL,
    ContentFile,
    CountResult,
    CrossCheck,
    FileLoc,
    FileRow,
    LanguageRow,
    LocWarning,
    PrRef,
    PrRow,
    UserMetrics,
    WarningKind,
    WeekRow,
    compare_files,
    compare_languages,
    count_directory,
    count_export,
    count_files,
    cross_check,
    cross_check_warning,
    is_countable,
    iso_week,
    pr_membership,
    pr_metrics,
    rename_map,
    total_metrics,
    user_metrics,
    weekly_metrics,
)
from loc_counter.git_repo import DiffEntry, GitRepo, LogCommit
from loc_counter.identity import AccountResolver, UserSummary, summarize_users
from loc_counter.snapshot import ExportPlan, Snapshots, plan_export

FILTERS = FilterConfig()
TZ = "Asia/Bangkok"
C = "carol@example.com"


# ---------- helper ----------
def cf(path: str, data: bytes, language: str | None = "Python", key: str | None = None
       ) -> ContentFile:
    """ContentFile với cache_key mặc định = content_sha1(data)."""
    return ContentFile(path, language, data, key or content_sha1(data))


@dataclass
class S14:
    """Repo §14 đã gán tác giả + các export start / end."""

    repo: GitRepo
    snaps: Snapshots
    commits: list[LogCommit]
    attr: PeriodAttribution
    summaries: list[UserSummary]
    start_plan: ExportPlan
    exports: dict[str, UserExport]   # start, all, alice, bob, alice+bob


def s14_ctx(section14_repo: Any, cache_root: Path) -> S14:
    ctx = prepare(section14_repo().src, cache_root)
    resolver = AccountResolver()
    attr = attribute_period(ctx.repo, ctx.snaps, ctx.commits, resolver, FILTERS)
    summaries = summarize_users(ctx.commits, resolver).users
    start_plan = plan_export(ctx.repo, ctx.snaps.c_start.sha, FILTERS)
    exports = {
        "start": export_from_plan(start_plan, "start"),
        "all": export_from_plan(plan_export(ctx.repo, ctx.snaps.c_end.sha, FILTERS)),
    }
    for tag, users in (("alice", {A}), ("bob", {B}), ("alice+bob", {A, B})):
        exports[tag] = build_user_export(ctx.repo, attr, start_plan, users, FILTERS, tag)
    return S14(ctx.repo, ctx.snaps, ctx.commits, attr, summaries, start_plan, exports)


class FakeReader:
    """read_blobs giả: ghi lại lời gọi, trả (sha, data) theo thứ tự đầu vào."""

    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.calls: list[list[str]] = []

    def __call__(self, shas: Any) -> Any:
        shas = list(shas)
        self.calls.append(shas)
        return ((s, self.blobs[s]) for s in shas)


def side(path: str, language: str | None = "Python", *, keep: bool = True,
         too_large: bool = False, binary: bool = False) -> SideInfo:
    return SideInfo(path, "100644", "0" * 40, 10, keep, language, binary, too_large, 1)


def fattr(path: str, granularity: str = "lines", *, old: SideInfo | None = None,
          new: SideInfo | None = None, added: dict[int, str] | None = None,
          deleted: dict[int, str] | None = None, renamed_by: str | None = None,
          last_touch_by: str | None = None, status: str = "M",
          old_path: str | None = None) -> FileAttribution:
    entry = DiffEntry(status, old_path or (path if old else None), path if new else None,
                      "100644" if old else None, "100644" if new else None,
                      "0" * 40 if old else None, "0" * 40 if new else None, None)
    return FileAttribution(entry, old, new, granularity, (), added or {}, deleted or {},
                           frozenset(), renamed_by, last_touch_by)


def log_commit(sha: str, email: str, when: str, merge: bool = False) -> LogCommit:
    parents = ("p" * 40, "q" * 40) if merge else ("p" * 40,)
    return LogCommit(sha, parents, email.split("@")[0], email, email.split("@")[0], email,
                     datetime.fromisoformat(when))


def sha(ch: str) -> str:
    return ch * 40


# ---------- TC-18 .. TC-23: count_files ----------
def test_count_files_basic() -> None:
    """TC-counter-18: count_files cơ bản + sắp xếp; file language None không đếm."""
    result = count_files([cf("b.py", b"x = 1\n# c\ny = 2\n"),
                          cf("a.js", b"let a = 1;\n", "JavaScript"),
                          cf("c.txt", b"text\n", None)], FILTERS)
    assert [f.path for f in result.files] == ["a.js", "b.py"]
    assert result.files[1] == FileLoc("b.py", "Python", 2, 3)
    assert result.total_code == 3
    assert result.warnings == []


def test_is_countable_and_size_limit() -> None:
    """TC-counter-19: is_countable; ngưỡng max_file_size_kb là <=; file quá lớn không cảnh báo."""
    filters = FilterConfig(max_file_size_kb=1)
    big = b"x = 1\n" + b"#" * (1025 - 7) + b"\n"
    ok = b"x = 1\n" + b"#" * (1024 - 7) + b"\n"
    assert (len(big), len(ok)) == (1025, 1024)
    assert is_countable("Python", 1024, filters)
    assert not is_countable("Python", 1025, filters)
    assert not is_countable(None, 0, filters)
    result = count_files([cf("big.py", big), cf("ok.py", ok)], filters)
    assert [f.path for f in result.files] == ["ok.py"]
    assert result.warnings == []


def test_count_files_encodings() -> None:
    """TC-counter-20: BOM / latin-1 / CRLF qua count_files — kết quả như TC-05."""
    result = count_files([
        cf("bom.py", b"\xef\xbb\xbf# c\nx = 1\n"),
        cf("latin.py", b'x = "\xe9"\n'),
        cf("crlf.py", b"# c\r\nx = 1\r\n\r\ny = 2\r\n"),
    ], FILTERS)
    by_path = {f.path: f for f in result.files}
    assert by_path["bom.py"].code_lines == 1
    assert by_path["latin.py"].code_lines == 1
    assert (by_path["crlf.py"].code_lines, by_path["crlf.py"].total_lines) == (2, 4)


def test_count_files_duplicate_path() -> None:
    """TC-counter-21: hai ContentFile cùng đường dẫn → ValueError."""
    with pytest.raises(ValueError, match="ContentFile trùng đường dẫn: a.py"):
        count_files([cf("a.py", b"x = 1\n"), cf("a.py", b"y = 2\n")], FILTERS)


def test_count_files_case_only_paths() -> None:
    """TC-counter-22: A.py và a.py (chỉ khác hoa thường) đều được đếm (D36)."""
    result = count_files([cf("A.py", b"x = 1\n"), cf("a.py", b"x = 1\ny = 2\n")], FILTERS)
    assert [(f.path, f.code_lines) for f in result.files] == [("A.py", 1), ("a.py", 2)]
    assert result.total_code == 3


def test_count_files_cache_key() -> None:
    """TC-counter-23: hai file khác tên, cùng cache_key, classifier chung → cache_hits == 1."""
    clf = LineClassifier()
    count_files([cf("a.py", b"x = 1\n", key="k1"), cf("b.py", b"x = 1\n", key="k1")],
                FILTERS, clf)
    assert (clf.cache_hits, clf.cache_misses) == (1, 1)


# ---------- TC-24 .. TC-26: count_export ----------
def test_count_export_reads_once() -> None:
    """TC-counter-24: đọc blob một lần, khử trùng sha, không đọc file non-source."""
    s1, s2 = sha("1"), sha("2")
    export = UserExport(None, "all", (
        BuiltFile("a.py", "100644", "Python", blob_sha=s1),
        BuiltFile("b.py", "100644", "Python", blob_sha=s1),
        BuiltFile("c.py", "100644", "Python", data=b"x = 1\ny = 2\n"),
        BuiltFile("d.png", "100644", None, blob_sha=s2),
    ), ())
    reader = FakeReader({s1: b"x = 1\n", s2: b"\x89PNG\x00"})
    result = count_export(export, reader, FILTERS)
    assert reader.calls == [[s1]]
    assert [(f.path, f.code_lines) for f in result.files] == [("a.py", 1), ("b.py", 1),
                                                              ("c.py", 2)]
    assert result.warnings == []
    # read_blobs trả iterator thường (không có close()) vẫn dùng được
    plain = count_export(export, lambda shas: iter([(s1, b"x = 1\n")]), FILTERS)
    assert plain.files == result.files


def test_count_export_closes_generator() -> None:
    """TC-counter-25: lỗi ở phần tử 2 → lỗi lan ra, generator đã đóng (cả lỗi phía người đọc).

    (a) generator tự ném lỗi; (b) phần tử 2 hỏng nên dict() ở count_export ném lỗi trong khi
    generator còn treo — chỉ đóng được nhờ contextlib.closing (giữ tham chiếu để GC không
    tự đóng thay).
    """
    export = UserExport(None, "all", (
        BuiltFile("a.py", "100644", "Python", blob_sha=sha("1")),
        BuiltFile("b.py", "100644", "Python", blob_sha=sha("2")),
    ), ())

    for consumer_side in (False, True):
        state = {"closed": False}
        alive: list[Any] = []

        def reader(shas: Any, consumer_side: bool = consumer_side,
                   state: dict[str, bool] = state, alive: list[Any] = alive) -> Any:
            def gen() -> Any:
                try:
                    items = list(shas)
                    yield items[0], b"x = 1\n"
                    if consumer_side:
                        yield "hỏng"  # dict() không tách được thành (sha, data)
                    raise RuntimeError("cat-file hỏng")
                finally:
                    state["closed"] = True
            g = gen()
            alive.append(g)
            return g

        error = ValueError if consumer_side else RuntimeError
        with pytest.raises(error):
            count_export(export, reader, FILTERS)
        assert state["closed"] is True, consumer_side
        assert alive


def test_count_export_empty() -> None:
    """TC-counter-26: export rỗng (C_START rỗng) → CountResult(), không gọi read_blobs."""
    reader = FakeReader({})
    assert count_export(UserExport(None, "x", (), ()), reader, FILTERS) == CountResult()
    assert reader.calls == []


# ---------- TC-27 .. TC-30: §14 ----------
def test_section14_count_from_entries_equals_zip_and_dir(section14_repo, cache_root: Path,
                                                        tmp_path: Path) -> None:
    """TC-counter-27: §14 — count_export = count_files trên entry zip = count_directory giải nén."""
    s = s14_ctx(section14_repo, cache_root)
    expected = {"start": 10, "all": 20, "alice": 13, "bob": 17, "alice+bob": 20}
    for tag, export in s.exports.items():
        from_entries = count_export(export, s.repo.read_blobs, FILTERS)
        assert from_entries.total_code == expected[tag], tag

        zip_path = write_user_export(s.repo, export, tmp_path / f"{tag}.zip", s.snaps.c_end, TZ)
        languages = {f.path: f.language for f in export.files}
        with zipfile.ZipFile(zip_path) as zf:
            entries = [cf(name, zf.read(name), languages[name]) for name in zf.namelist()
                       if not name.endswith("/")]
            out = tmp_path / f"x_{tag}"
            zf.extractall(out)
        from_zip = count_files(entries, FILTERS)
        assert from_zip.files == from_entries.files, tag
        out.mkdir(exist_ok=True)
        assert count_directory(out, FILTERS).files == from_entries.files, tag


def test_section14_user_metrics(section14_repo, cache_root: Path) -> None:
    """TC-counter-28: §14 — alice 2 commit 5/2/+3 app.py; bob 2 commit 8/1/+7 app.py, util.py."""
    s = s14_ctx(section14_repo, cache_root)
    rows = user_metrics(s.attr, s.summaries, [A, B])
    assert [r.account for r in rows] == [A, B]
    alice, bob = rows
    assert (alice.commits, alice.added_code, alice.deleted_code, alice.net_code) == (2, 5, 2, 3)
    assert alice.files == ("app.py",)
    assert alice.files_changed == 1
    assert (alice.added_lines, alice.deleted_lines) == (7, 2)
    assert (bob.commits, bob.added_code, bob.deleted_code, bob.net_code) == (2, 8, 1, 7)
    assert bob.files == ("app.py", "util.py")
    assert alice.is_bot is False and bob.is_bot is False


def test_section14_cross_check(section14_repo, cache_root: Path) -> None:
    """TC-counter-29: §14 — kiểm tra chéo đạt cả 4 trường hợp, diff 0.0, không cảnh báo."""
    s = s14_ctx(section14_repo, cache_root)
    loc = {tag: count_export(e, s.repo.read_blobs, FILTERS).total_code
           for tag, e in s.exports.items()}
    net = {r.account: r.net_code for r in user_metrics(s.attr, s.summaries, [A, B])}
    cases = {"all": [net[A], net[B]], "alice": [net[A]], "bob": [net[B]],
             "alice+bob": [net[A], net[B]]}
    for tag, nets in cases.items():
        check = cross_check(loc["start"], loc[tag], nets)
        assert check.ok, tag
        assert check.diff_percent == 0.0
        assert check.expected_loc_end == loc[tag]
        assert cross_check_warning(check, tag) is None
    assert (net[A], net[B]) == (3, 7)


def test_total_metrics(section14_repo, cache_root: Path) -> None:
    """TC-counter-30: dòng Tổng — cộng cột số, files_changed = số file khác nhau."""
    s = s14_ctx(section14_repo, cache_root)
    total = total_metrics(user_metrics(s.attr, s.summaries, [A, B]))
    assert total.account == ""
    assert total.is_bot is False
    assert (total.commits, total.added_code, total.deleted_code, total.net_code) == (4, 13, 3, 10)
    assert (total.added_lines, total.deleted_lines) == (15, 3)
    assert total.files_changed == 2
    empty = total_metrics([])
    assert empty == UserMetrics("", False, 0, 0, 0, 0, 0, ())
    assert (empty.net_code, empty.files_changed) == (0, 0)


# ---------- TC-31: files_changed ----------
def test_files_changed_rules(caplog: pytest.LogCaptureFixture) -> None:
    """TC-counter-31: files_changed loại whole/skip, non-source, too_large; rename thuần = 1."""
    u = "u@example.com"
    files = (
        fattr("a.py", old=side("a.py"), new=side("a.py"), added={0: u}),
        fattr("b.png", "whole", old=side("b.png", None, binary=True),
              new=side("b.png", None, binary=True), last_touch_by=u),
        fattr("c.txt", old=side("c.txt", None), new=side("c.txt", None), added={0: u}),
        fattr("d.py", old=side("old_d.py"), new=side("d.py"), renamed_by=u, status="R",
              old_path="old_d.py"),
        fattr("e.py", old=side("e.py"), new=side("e.py")),
        fattr("f.py", old=side("f.py"), deleted={0: u}, status="D"),
        fattr("g.py", old=side("g.py", too_large=True), new=side("g.py", None), deleted={0: u}),
    )
    attr = PeriodAttribution(sha("s"), sha("e"), files,
                             (UserLineStats(u, 2, 2, 1, 1, ("a.py",)),), {}, ())
    caplog.set_level(logging.WARNING)
    rows = user_metrics(attr, [UserSummary(u, 3, 0, [], False)], [u])
    assert len(rows) == 1
    assert rows[0].files == ("a.py", "d.py", "f.py")
    assert rows[0].files_changed == 3
    assert (rows[0].added_lines, rows[0].deleted_lines) == (2, 2)
    assert rows[0].commits == 3
    # account không có trong summaries → commits 0, is_bot False, log WARNING
    missing = user_metrics(attr, [], [u, u])
    assert len(missing) == 1
    assert (missing[0].commits, missing[0].is_bot) == (0, False)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---------- TC-32 .. TC-35: so sánh ----------
def test_compare_languages() -> None:
    """TC-counter-32: hợp ngôn ngữ, sắp (-loc_end, -loc_start, language), bất biến tổng."""
    start = CountResult([FileLoc("a.py", "Python", 10, 12)])
    end = CountResult([FileLoc("a.py", "Python", 13, 15), FileLoc("b.js", "JavaScript", 13, 13),
                       FileLoc("c.css", "CSS", 0, 0)])
    rows = compare_languages(start, end)
    assert rows == [LanguageRow("Python", 1, 10, 1, 13), LanguageRow("JavaScript", 0, 0, 1, 13),
                    LanguageRow("CSS", 0, 0, 1, 0)]
    assert [r.delta for r in rows] == [3, 13, 0]
    assert sum(r.loc_start for r in rows) == start.total_code
    assert sum(r.loc_end for r in rows) == end.total_code
    assert compare_languages(CountResult(), CountResult()) == []


def test_compare_files_by_path() -> None:
    """TC-counter-33: ghép theo đường dẫn, file chỉ ở một phía; sắp theo path; Σ khớp."""
    start = CountResult([FileLoc("a.py", "Python", 3, 3), FileLoc("b.py", "Python", 2, 2)])
    end = CountResult([FileLoc("a.py", "Python", 4, 4), FileLoc("c.py", "Python", 1, 1)])
    rows = compare_files(start, end)
    assert rows == [FileRow("a.py", None, "Python", 3, 4), FileRow("b.py", None, "Python", 2, 0),
                    FileRow("c.py", None, "Python", 0, 1)]
    assert [r.delta for r in rows] == [1, -2, 1]
    assert sum(r.loc_start for r in rows) == start.total_code
    assert sum(r.loc_end for r in rows) == end.total_code


def build_rename_repo(src: Any) -> None:
    """TC-34/35: start old.py 3 dòng code; bob đổi tên → new.py rồi thêm 1 dòng; alice sửa z.py."""
    lines = [f"value_number_{i} = {i}" for i in range(3)]
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"old.py": j(lines), "z.py": "z = 1\n"})
    src.git("mv", "old.py", "new.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    src.commit("bob edit", "2026-01-06T10:00:00+07:00", author=BOB,
               files={"new.py": j([*lines, "value_number_9 = 9"])})
    src.commit("alice z", "2026-01-07T10:00:00+07:00", author=ALICE,
               files={"z.py": "z = 1\nz2 = 2\n"})


def rename_ctx(make_repo: Any, cache_root: Path) -> tuple[GitRepo, PeriodAttribution, ExportPlan]:
    src = make_repo()
    build_rename_repo(src)
    ctx = prepare(src, cache_root)
    attr = attribute_period(ctx.repo, ctx.snaps, ctx.commits, AccountResolver(), FILTERS)
    start_plan = plan_export(ctx.repo, ctx.snaps.c_start.sha, FILTERS)
    return ctx.repo, attr, start_plan


def test_rename_map_and_compare_files(make_repo, cache_root: Path) -> None:
    """TC-counter-34: export all có new.py → rename_map {new: old}, một dòng FileRow 3→4."""
    repo, attr, start_plan = rename_ctx(make_repo, cache_root)
    end = export_from_plan(plan_export(repo, attr.c_end, FILTERS))
    start_count = count_export(export_from_plan(start_plan, "start"), repo.read_blobs, FILTERS)
    end_count = count_export(end, repo.read_blobs, FILTERS)
    renames = rename_map(attr, [f.path for f in end.files])
    assert renames == {"new.py": "old.py"}
    rows = [r for r in compare_files(start_count, end_count, renames) if r.path != "z.py"]
    assert rows == [FileRow("new.py", "old.py", "Python", 3, 4)]


def test_rename_map_old_name_export(make_repo, cache_root: Path) -> None:
    """TC-counter-35: export của alice (không đổi tên) dùng tên cũ → rename_map {}, old.py 3→3."""
    repo, attr, start_plan = rename_ctx(make_repo, cache_root)
    end = build_user_export(repo, attr, start_plan, {A}, FILTERS, "alice")
    paths = [f.path for f in end.files]
    assert "old.py" in paths and "new.py" not in paths
    start_count = count_export(export_from_plan(start_plan, "start"), repo.read_blobs, FILTERS)
    end_count = count_export(end, repo.read_blobs, FILTERS)
    renames = rename_map(attr, paths)
    assert renames == {}
    rows = {r.path: r for r in compare_files(start_count, end_count, renames)}
    assert rows["old.py"] == FileRow("old.py", None, "Python", 3, 3)
    assert rows["z.py"] == FileRow("z.py", None, "Python", 1, 2)


# ---------- TC-36 .. TC-39: theo tuần ----------
def test_iso_week() -> None:
    """TC-counter-36: iso_week theo múi giờ đã chọn và năm ISO."""
    moment = datetime.fromisoformat("2026-01-05T05:00:00+07:00")
    assert iso_week(moment, "Asia/Bangkok") == ("2026-W02", date(2026, 1, 5))
    assert iso_week(moment, "UTC") == ("2026-W01", date(2025, 12, 29))
    assert iso_week(datetime.fromisoformat("2025-12-29T10:00:00+07:00"), "Asia/Bangkok") == (
        "2026-W01", date(2025, 12, 29))


def test_section14_weekly_metrics(section14_repo, cache_root: Path) -> None:
    """TC-counter-37: §14 — 2 dòng tuần 2026-W02; Σ theo tuần = user_metrics."""
    s = s14_ctx(section14_repo, cache_root)
    rows = weekly_metrics(s.attr, s.commits, [A, B], TZ)
    monday = date(2026, 1, 5)
    assert rows == [WeekRow("2026-W02", monday, A, 2, 5, 2),
                    WeekRow("2026-W02", monday, B, 2, 8, 1)]
    assert [r.net_code for r in rows] == [3, 7]
    for m in user_metrics(s.attr, s.summaries, [A, B]):
        mine = [r for r in rows if r.account == m.account]
        assert sum(r.added_code for r in mine) == m.added_code
        assert sum(r.deleted_code for r in mine) == m.deleted_code
        assert sum(r.commits for r in mine) == m.commits


def test_weekly_metrics_weeks_merge_filter() -> None:
    """TC-counter-38: nhiều tuần, merge carol góp code không góp commit, lọc account, ô 0."""
    a1, a2, a3, m, b1 = sha("1"), sha("2"), sha("3"), sha("4"), sha("5")
    commits = [
        log_commit(a1, A, "2026-01-06T10:00:00+07:00"),          # 2026-W02
        log_commit(a2, A, "2026-01-13T10:00:00+07:00"),          # 2026-W03
        log_commit(a3, A, "2026-01-20T10:00:00+07:00"),          # 2026-W04, không có dòng code
        log_commit(m, C, "2026-01-14T10:00:00+07:00", merge=True),
        log_commit(b1, B, "2026-01-06T10:00:00+07:00"),
    ]
    stats = (
        CommitLineStats(a1, A, 3, 1, 2, 1),
        CommitLineStats(a2, A, 1, 0, 1, 0),
        CommitLineStats(m, C, 1, 0, 1, 0),
        CommitLineStats(b1, B, 5, 0, 5, 0),
    )
    accounts = {a1: A, a2: A, a3: A, m: C, b1: B}
    attr = PeriodAttribution(sha("s"), sha("e"), (), (), accounts, (), stats)
    rows = weekly_metrics(attr, commits, [A, C], TZ)
    assert rows == [
        WeekRow("2026-W02", date(2026, 1, 5), A, 1, 2, 1),
        WeekRow("2026-W03", date(2026, 1, 12), A, 1, 1, 0),
        WeekRow("2026-W03", date(2026, 1, 12), C, 0, 1, 0),
        WeekRow("2026-W04", date(2026, 1, 19), A, 1, 0, 0),
    ]
    assert all(r.account != B for r in rows)


def test_weekly_metrics_unknown_commit(caplog: pytest.LogCaptureFixture) -> None:
    """TC-counter-39: commit_stats có sha không có trong commits → bỏ qua, log WARNING."""
    a1, ghost = sha("1"), sha("9")
    attr = PeriodAttribution(sha("s"), sha("e"), (), (), {a1: A, ghost: A}, (),
                             (CommitLineStats(a1, A, 1, 0, 1, 0),
                              CommitLineStats(ghost, A, 4, 0, 4, 0)))
    caplog.set_level(logging.WARNING)
    rows = weekly_metrics(attr, [log_commit(a1, A, "2026-01-06T10:00:00+07:00")], [A], TZ)
    assert rows == [WeekRow("2026-W02", date(2026, 1, 5), A, 1, 1, 0)]
    assert any(r.levelno == logging.WARNING and ghost in r.getMessage() for r in caplog.records)


# ---------- TC-40 .. TC-42: kiểm tra chéo ----------
@pytest.mark.parametrize(("loc_start", "loc_end", "nets", "diff", "ok", "expected"), [
    (10, 20, [3, 7], 0.0, True, 20),
    (100, 1000, [], 90.0, False, 100),
    (995, 1000, [], 0.5, True, 995),
    (994, 1000, [], 0.6, False, 994),
    (300, 300, [1], 0.333, True, 301),
    (0, 0, [], 0.0, True, 0),
    (5, 0, [], 100.0, False, 5),
])
def test_cross_check_formula(loc_start: int, loc_end: int, nets: list[int], diff: float,
                             ok: bool, expected: int) -> None:
    """TC-counter-40: cross_check — công thức, ngưỡng <= 0.5 %, làm tròn 3 chữ số, loc_end 0."""
    check = cross_check(loc_start, loc_end, nets)
    assert check.diff_percent == diff
    assert check.ok is ok
    assert check.expected_loc_end == expected
    assert check.sum_net_code == sum(nets)
    assert check.threshold_percent == CROSS_CHECK_THRESHOLD_PERCENT == 0.5
    assert (check.loc_start, check.loc_end) == (loc_start, loc_end)


def test_cross_check_warning() -> None:
    """TC-counter-41: cross_check_warning — tiếng Việt, đủ giá trị; check ok → None."""
    bad = cross_check(10, 20, [3])
    warning = cross_check_warning(bad, "alice")
    assert warning == LocWarning(
        WarningKind.CROSS_CHECK, "",
        "Kiểm tra chéo (alice): loc_start 10 + tổng code ròng +3 = 13, loc_end = 20, "
        "lệch 35.000% (ngưỡng 0.5%)")
    assert cross_check_warning(cross_check(10, 13, [3]), "alice") is None
    assert isinstance(bad, CrossCheck)


def test_cross_check_systematic_mismatch(make_repo, cache_root: Path) -> None:
    """TC-counter-42: notes.txt (bị loại) đổi tên → notes.py → loc 0→5, Σ net 0 → CROSS_CHECK."""
    src = make_repo()
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"notes.txt": j(["x = 1"] * 5)})
    src.git("mv", "notes.txt", "notes.py")
    src.commit("bob mv", "2026-01-05T10:00:00+07:00", author=BOB)
    ctx = prepare(src, cache_root)
    resolver = AccountResolver()
    attr = attribute_period(ctx.repo, ctx.snaps, ctx.commits, resolver, FILTERS)
    summaries = summarize_users(ctx.commits, resolver).users
    start = count_export(export_from_plan(plan_export(ctx.repo, ctx.snaps.c_start.sha, FILTERS)),
                         ctx.repo.read_blobs, FILTERS)
    end = count_export(export_from_plan(plan_export(ctx.repo, ctx.snaps.c_end.sha, FILTERS)),
                       ctx.repo.read_blobs, FILTERS)
    rows = user_metrics(attr, summaries, [u.account for u in summaries])
    check = cross_check(start.total_code, end.total_code, [r.net_code for r in rows])
    assert (check.loc_start, check.loc_end, check.sum_net_code) == (0, 5, 0)
    assert check.ok is False
    assert check.diff_percent == 100.0
    warning = cross_check_warning(check, "all")
    assert warning is not None and warning.kind == WarningKind.CROSS_CHECK
    assert "loc_end = 5" in warning.message


# ---------- TC-43 .. TC-44 ----------
def test_m5_reproducible(section14_repo, cache_root: Path) -> None:
    """TC-counter-43: mọi hàm M5 gọi 2 lần trên §14 cho kết quả bằng nhau."""
    s = s14_ctx(section14_repo, cache_root)

    def run() -> tuple[Any, ...]:
        counts = {t: count_export(e, s.repo.read_blobs, FILTERS) for t, e in s.exports.items()}
        users = user_metrics(s.attr, s.summaries, [A, B])
        renames = rename_map(s.attr, [f.path for f in s.exports["all"].files])
        return (
            counts,
            compare_languages(counts["start"], counts["all"]),
            compare_files(counts["start"], counts["all"], renames),
            users,
            total_metrics(users),
            weekly_metrics(s.attr, s.commits, [A, B], TZ),
            cross_check(counts["start"].total_code, counts["all"].total_code,
                        [u.net_code for u in users]),
        )

    assert run() == run()


def test_no_runtime_import_of_dependents() -> None:
    """TC-counter-44: import counter không kéo attribution/builder/identity/git_repo/snapshot."""
    code = ("import sys, loc_counter.counter\n"
            "print(','.join(sorted(m for m in sys.modules if m.startswith('loc_counter'))))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True).stdout.strip().split(",")
    for name in ("attribution", "builder", "identity", "git_repo", "snapshot"):
        assert f"loc_counter.{name}" not in out, name
    assert "loc_counter.counter" in out


# ---------- TC-45 .. TC-53: theo PR (M8, D43) ----------
def lc(ch: str, parents: tuple[str, ...] = (), subject: str = "", body_title: str = "",
       email: str = A, when: str = "2026-01-06T10:00:00+07:00") -> LogCommit:
    """LogCommit giả có parent và subject; sha = ch * 40."""
    name = email.split("@")[0]
    return LogCommit(sha(ch), tuple(parents), name, email, name, email,
                     datetime.fromisoformat(when), subject, body_title)


def _graph_pr7(**merge_kwargs: Any) -> list[LogCommit]:
    """m1←m2 (main), f1←f2 (nhánh từ m1), M = merge(m2, f2) 'Merge pull request #7'."""
    return [
        lc("1", (sha("0"),)),
        lc("2", (sha("1"),)),
        lc("3", (sha("1"),)),
        lc("4", (sha("3"),)),
        lc("5", (sha("2"), sha("4")), **{"subject": "Merge pull request #7 from o/feat",
                                         "body_title": "Thêm X", **merge_kwargs}),
    ]


def test_pr_membership_merge_pr() -> None:
    """TC-counter-45: thành viên merge PR = M^2 trừ M^1 và M; title lấy từ body, 'from', subject."""
    commits = _graph_pr7()
    ref = PrRef(7, "Thêm X", sha("5"), commits[-1].author_date)
    assert pr_membership(commits) == {sha("3"): ref, sha("4"): ref, sha("5"): ref}

    no_body = pr_membership(_graph_pr7(body_title=""))
    assert no_body[sha("5")].title == "o/feat"
    odd = pr_membership(_graph_pr7(subject="Merge pull request #7", body_title=""))
    assert odd[sha("5")].title == "Merge pull request #7"


def test_pr_membership_squash() -> None:
    """TC-counter-46: squash '(#N)' ở cuối subject; Revert/giữa subject không khớp."""
    commits = [
        lc("1", (sha("0"),), "Thêm login (#12)"),
        lc("2", (sha("1"),), 'Revert "Thêm login (#12)"'),
        lc("3", (sha("2"),), "fix (#12) typo"),
        lc("4", (sha("3"),), "Thêm (#5)  "),
        lc("5", (sha("0"),), "Việc trên nhánh"),
        lc("6", (sha("4"), sha("5")), "Merge branch 'x'"),
    ]
    got = pr_membership(commits)
    assert set(got) == {sha("1"), sha("4")}
    assert (got[sha("1")].number, got[sha("1")].title) == (12, "Thêm login")
    assert (got[sha("4")].number, got[sha("4")].title) == (5, "Thêm")
    assert got[sha("1")].merge_sha == sha("1")


def test_pr_membership_nested_and_squash_inside_merge() -> None:
    """TC-counter-47: PR lồng nhau → PR trong cùng nhất; squash trong merge PR → merge PR thắng."""
    commits = [
        lc("1", (sha("0"),)),                                   # m1
        lc("2", (sha("1"),)),                                   # b1 (nhánh B2)
        lc("3", (sha("2"),)),                                   # g1 (PR #1)
        lc("4", (sha("3"),)),                                   # g2
        lc("5", (sha("2"), sha("4")), "Merge pull request #1 from o/a", "Một"),   # M1
        lc("6", (sha("5"),)),                                   # b2
        lc("7", (sha("6"),), "x (#9)"),                         # c — squash trong PR #2
        lc("8", (sha("1"),)),                                   # m2 (main)
        lc("9", (sha("8"), sha("7")), "Merge pull request #2 from o/b", "Hai"),   # M2
    ]
    got = pr_membership(commits)
    assert {s: r.number for s, r in got.items()} == {
        sha("3"): 1, sha("4"): 1, sha("5"): 1,
        sha("2"): 2, sha("6"): 2, sha("7"): 2, sha("9"): 2}
    assert sha("1") not in got and sha("8") not in got


def test_pr_membership_ignores_log_order() -> None:
    """TC-counter-48: kết quả không phụ thuộc thứ tự danh sách commit (cha trước con)."""
    commits = _graph_pr7()
    expected = pr_membership(commits)
    assert pr_membership(list(reversed(commits))) == expected
    shuffled = [commits[i] for i in (3, 0, 4, 2, 1)]
    assert pr_membership(shuffled) == expected

    # dữ liệu hỏng có vòng (git không tạo ra): không treo, bỏ cạnh vòng
    loop = [lc("1", (sha("2"),)), lc("2", (sha("1"),)),
            lc("3", (sha("3"), sha("2")), "Merge pull request #1 from o/x", "Một")]
    assert set(pr_membership(loop)) == {sha("3")}


def test_pr_metrics_groups_by_pr_and_account() -> None:
    """TC-counter-49: nhóm (PR, account); merge carol góp dòng xung đột; quy về múi giờ đã chọn."""
    commits = [
        lc("1", (sha("0"),), email=A),                                       # d1 trực tiếp
        lc("2", (sha("1"),), email=A),                                       # f1
        lc("3", (sha("2"),), email=B),                                       # f2
        lc("4", (sha("3"),), email=A),                                       # f3
        lc("5", (sha("1"),), email=A),                                       # d2 trực tiếp
        lc("6", (sha("5"), sha("4")), "Merge pull request #7 from o/f", "Tính năng X",
           email=C, when="2026-01-10T01:00:00+00:00"),                      # M
        lc("7", (sha("6"),), "Sửa lỗi (#12)", email=A),                      # squash
    ]
    stats = (
        CommitLineStats(sha("1"), A, 5, 0, 4, 0),
        CommitLineStats(sha("2"), A, 3, 1, 2, 1),
        CommitLineStats(sha("3"), B, 4, 0, 4, 0),
        CommitLineStats(sha("4"), A, 1, 0, 1, 0),
        CommitLineStats(sha("6"), C, 1, 0, 1, 0),
        CommitLineStats(sha("7"), A, 2, 1, 2, 1),
    )
    accounts = {sha(ch): e for ch, e in zip("1234567", (A, A, B, A, A, C, A), strict=True)}
    attr = PeriodAttribution(sha("s"), sha("e"), (), (), accounts, (), stats)

    rows = pr_metrics(attr, commits, [A, B, C], TZ)
    merged = datetime.fromisoformat("2026-01-10T08:00:00+07:00")
    assert rows == [
        PrRow(7, "Tính năng X", sha("6"), merged, A, 2, 3, 1),
        PrRow(7, "Tính năng X", sha("6"), merged, B, 1, 4, 0),
        PrRow(7, "Tính năng X", sha("6"), merged, C, 0, 1, 0),
        PrRow(12, "Sửa lỗi", sha("7"), commits[-1].author_date, A, 1, 2, 1),
        PrRow(None, "", "", None, A, 2, 4, 0),
    ]
    assert rows[0].merged_at.utcoffset() == timedelta(hours=7)
    assert [r.net_code for r in rows] == [2, 4, 1, 1, 4]
    assert NO_PR_LABEL == "(Không thuộc PR)"


def test_pr_metrics_filter_zero_cells_unknown_sha() -> None:
    """TC-counter-50: lọc account, giữ ô chỉ-có-commit, bỏ ô toàn 0, sha lạ → nhóm không PR."""
    ghost = sha("9")
    commits = [
        lc("1", (sha("0"),), "Việc nhỏ (#3)", email=A),                      # squash: chỉ có commit
        lc("2", (sha("0"),), email=B),                                       # bob trong PR 8
        lc("3", (sha("0"), sha("2")), "Merge pull request #8 from o/g", "Tám", email=A),
    ]
    stats = (
        CommitLineStats(sha("1"), A, 0, 0, 0, 0),
        CommitLineStats(sha("2"), B, 6, 0, 6, 0),
        CommitLineStats(sha("3"), A, 0, 0, 0, 0),       # merge của alice, toàn 0 → ô (8, A) bị bỏ
        CommitLineStats(ghost, A, 4, 0, 4, 0),
    )
    accounts = {sha("1"): A, sha("2"): B, sha("3"): A, ghost: A}
    attr = PeriodAttribution(sha("s"), sha("e"), (), (), accounts, (), stats)

    rows = pr_metrics(attr, commits, [A], TZ)
    assert [(r.pr, r.account, r.commits, r.added_code, r.deleted_code) for r in rows] == [
        (3, A, 1, 0, 0), (None, A, 0, 4, 0)]
    assert all(r.account != B for r in rows)


def test_pr_metrics_without_any_pr() -> None:
    """TC-counter-51: không có PR → mọi dòng là nhóm không thuộc PR, Σ khớp."""
    commits = [lc("1", (sha("0"),), email=A), lc("2", (sha("1"),), email=B)]
    stats = (CommitLineStats(sha("1"), A, 3, 0, 3, 0), CommitLineStats(sha("2"), B, 2, 1, 2, 1))
    attr = PeriodAttribution(sha("s"), sha("e"), (), (), {sha("1"): A, sha("2"): B}, (), stats)
    rows = pr_metrics(attr, commits, [A, B], TZ)
    assert [(r.pr, r.account, r.commits, r.added_code, r.deleted_code) for r in rows] == [
        (None, A, 1, 3, 0), (None, B, 1, 2, 1)]


def test_pr_metrics_real_git(make_repo, cache_root: Path) -> None:
    """TC-counter-52: repo git thật — merge PR, squash, trực tiếp; Σ theo PR = user_metrics."""
    src = make_repo()
    base = src.commit("base", "2025-12-20T10:00:00+07:00", files={"app.py": "x0 = 0\n"})
    src.git("checkout", "-q", "-b", "feat", base)
    src.commit("bob b", "2026-01-03T10:00:00+07:00", author=BOB,
               files={"b.py": j(["b1 = 1", "b2 = 2", "b3 = 3", "b4 = 4"])})
    src.commit("alice c", "2026-01-04T10:00:00+07:00", author=ALICE,
               files={"c.py": j(["c1 = 1", "c2 = 2"])})
    src.checkout("main")
    src.commit("alice main", "2026-01-05T10:00:00+07:00", author=ALICE,
               files={"app.py": j(["x0 = 0", "a1 = 1", "a2 = 2", "a3 = 3"])})
    merge = src.merge("feat", "Merge pull request #7 from o/feat\n\nThêm b.py",
                      "2026-01-06T10:00:00+07:00", author=CAROL)
    squash = src.commit("Sửa lỗi (#9)", "2026-01-07T10:00:00+07:00", author=ALICE,
                        files={"d.py": "d1 = 1\n"})
    src.commit("bob direct", "2026-01-08T10:00:00+07:00", author=BOB, files={"e.py": "e1 = 1\n"})

    ctx = prepare(src, cache_root)
    attr = ctx.attribute()
    rows = pr_metrics(attr, ctx.commits, [A, B, C], TZ)
    assert [(r.pr, r.account, r.commits, r.added_code, r.deleted_code) for r in rows] == [
        (7, A, 1, 2, 0), (7, B, 1, 4, 0), (9, A, 1, 1, 0), (None, A, 1, 3, 0), (None, B, 1, 1, 0)]
    pr7 = rows[0]
    assert (pr7.title, pr7.merge_sha) == ("Thêm b.py", merge)
    assert pr7.merged_at == datetime.fromisoformat("2026-01-06T10:00:00+07:00")
    assert rows[2].merge_sha == squash and rows[2].title == "Sửa lỗi"

    summaries = summarize_users(ctx.commits, AccountResolver()).users
    for m in user_metrics(attr, summaries, [A, B, C]):
        mine = [r for r in rows if r.account == m.account]
        assert sum(r.commits for r in mine) == m.commits
        assert sum(r.added_code for r in mine) == m.added_code
        assert sum(r.deleted_code for r in mine) == m.deleted_code


def test_pr_metrics_deterministic_and_fast() -> None:
    """TC-counter-53: tái lập; đồ thị 3000 commit + 300 merge PR chạy dưới 5 giây."""
    import time

    when = datetime.fromisoformat("2026-01-06T10:00:00+07:00")
    commits: list[LogCommit] = []
    prev = sha("d")
    main: list[str] = []
    for k in range(3000):
        s = f"{k:040x}"
        commits.append(LogCommit(s, (prev,), "a", A, "a", A, when))
        main.append(s)
        prev = s
    for i in range(300):
        f, m = f"f{i:039x}", f"e{i:039x}"
        commits.append(LogCommit(f, (main[10 * i],), "b", B, "b", B, when))
        commits.append(LogCommit(m, (main[10 * i + 5], f), "c", C, "c", C, when,
                                 f"Merge pull request #{i + 1} from o/b{i}", f"PR {i + 1}"))
    main_set = set(main)
    stats = tuple(CommitLineStats(c.sha, A if c.sha in main_set else B, 1, 0, 1, 0)
                  for c in commits if not c.is_merge)
    accounts = {c.sha: (A if c.sha in main_set else B if c.sha[0] == "f" else C) for c in commits}
    attr = PeriodAttribution(sha("s"), sha("e"), (), (), accounts, (), stats)

    started = time.perf_counter()
    first = pr_metrics(attr, commits, [A, B, C], TZ)
    assert time.perf_counter() - started < 5
    assert first == pr_metrics(attr, commits, [A, B, C], TZ)
    assert sum(1 for r in first if r.pr is not None and r.account == B) == 300
