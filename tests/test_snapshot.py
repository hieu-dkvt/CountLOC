"""Test cho snapshot.py (spec docs/specs/snapshot.md)."""

from __future__ import annotations

import hashlib
import logging
import subprocess
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from loc_counter import git_repo as git_repo_module
from loc_counter.config import FilterConfig
from loc_counter.counter import WarningKind
from loc_counter.filters import BINARY_SNIFF_BYTES
from loc_counter.git_repo import CommitInfo, GitError, GitRepo
from loc_counter.snapshot import (
    ExportFile,
    ExportPlan,
    Period,
    Screening,
    Selection,
    SnapshotError,
    ZipEntry,
    end_zip_name,
    export_snapshot,
    find_snapshots,
    finish_entry,
    is_unsafe_path,
    make_period,
    plan_export,
    safe_name,
    screen_entry,
    select_content,
    start_zip_name,
    write_entries,
    write_zip,
    zip_timestamp,
)

BKK = ZoneInfo("Asia/Bangkok")
JAN = (date(2026, 1, 1), date(2026, 1, 31))


def _open(src, cache_root: Path) -> GitRepo:
    return GitRepo.open(str(src.path), cache_root=cache_root)


# ---------- make_period ----------

def test_period_default_times() -> None:
    """TC-snapshot-01: không nhập giờ → 00:00:00 / 23:59:59 theo Asia/Bangkok."""
    p = make_period(*JAN)
    assert p.start == datetime(2026, 1, 1, 0, 0, 0, tzinfo=BKK)
    assert p.end == datetime(2026, 1, 31, 23, 59, 59, tzinfo=BKK)
    assert p.start.isoformat() == "2026-01-01T00:00:00+07:00"
    assert p.end.isoformat() == "2026-01-31T23:59:59+07:00"
    assert (p.timezone, p.start_date, p.end_date) == ("Asia/Bangkok", *JAN)


def test_period_with_times() -> None:
    """TC-snapshot-02: giờ nhập HH:MM → start :00, end :59 (giây nhập bị bỏ)."""
    p = make_period(*JAN, start_time=time(8, 30, 12), end_time=time(17, 45, 12))
    assert p.start.time() == time(8, 30, 0)
    assert p.end.time() == time(17, 45, 59)


def test_period_start_not_before_end() -> None:
    """TC-snapshot-03: start >= end → SnapshotError."""
    d = date(2026, 1, 5)
    with pytest.raises(SnapshotError, match="phải trước end"):
        make_period(d, d, start_time=time(10, 0), end_time=time(9, 59))
    with pytest.raises(SnapshotError, match="phải trước end"):
        make_period(date(2026, 1, 6), d)
    # cùng phút: start 10:00:00 < end 10:00:59 → hợp lệ
    p = make_period(d, d, start_time=time(10, 0), end_time=time(10, 0))
    assert p.start < p.end


def test_period_timezone() -> None:
    """TC-snapshot-04: múi giờ UTC; múi giờ sai → SnapshotError."""
    p = make_period(*JAN, timezone="UTC")
    assert p.end.utcoffset() == timedelta(0)
    with pytest.raises(SnapshotError, match="Múi giờ không hợp lệ"):
        make_period(*JAN, timezone="Mars/Base")


# ---------- find_snapshots ----------

def test_c_start_boundary(make_repo, cache_root: Path) -> None:
    """TC-snapshot-05: commit đúng 00:00:00 ngày start là C_START."""
    src = make_repo()
    src.commit("X", "2025-12-31T23:59:59+07:00", files={"a.py": "x = 0\n"})
    y = src.commit("Y", "2026-01-01T00:00:00+07:00", files={"a.py": "x = 1\n"})
    src.commit("Z", "2026-01-01T00:00:01+07:00", files={"a.py": "x = 2\n"})
    snaps = find_snapshots(_open(src, cache_root), "main", make_period(*JAN))
    assert snaps.c_start is not None and snaps.c_start.sha == y


def test_c_end_boundary(make_repo, cache_root: Path) -> None:
    """TC-snapshot-06: commit đúng 23:59:59 ngày end là C_END, 00:00:00 hôm sau thì không."""
    src = make_repo()
    p_sha = src.commit("P", "2026-01-31T23:59:59+07:00", files={"a.py": "x = 1\n"})
    src.commit("Q", "2026-02-01T00:00:00+07:00", files={"a.py": "x = 2\n"})
    snaps = find_snapshots(_open(src, cache_root), "main", make_period(*JAN))
    assert snaps.c_end.sha == p_sha
    assert snaps.branch == "main"


def test_timezone_changes_snapshot(make_repo, cache_root: Path) -> None:
    """TC-snapshot-07: cùng commit, múi giờ khác → C_START khác."""
    src = make_repo()
    before = src.commit("before", "2025-12-30T10:00:00+07:00", files={"a.py": "x = 0\n"})
    target = src.commit("target", "2026-01-01T03:00:00+07:00", files={"a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    utc = find_snapshots(repo, "main", make_period(*JAN, timezone="UTC"))
    bkk = find_snapshots(repo, "main", make_period(*JAN))
    assert utc.c_start is not None and utc.c_start.sha == target
    assert bkk.c_start is not None and bkk.c_start.sha == before


def test_no_commit_before_start(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-08: không có commit trước start → C_START rỗng, zip start rỗng."""
    src = make_repo()
    src.commit("first", "2026-01-10T10:00:00+07:00", files={"a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    period = make_period(*JAN)
    snaps = find_snapshots(repo, "main", period)
    assert snaps.c_start is None
    name = start_zip_name(period, snaps.c_start)
    assert name == "start_2026-01-01_empty.zip"
    plan = export_snapshot(repo, snaps.c_start, FilterConfig(), tmp_path / name, "Asia/Bangkok")
    assert plan.files == [] and plan.commit_sha is None
    with zipfile.ZipFile(tmp_path / name) as zf:
        assert zf.namelist() == []


def test_no_commit_before_end(make_repo, cache_root: Path) -> None:
    """TC-snapshot-09: mọi commit sau end → lỗi không có dữ liệu."""
    src = make_repo()
    src.commit("late", "2026-03-01T10:00:00+07:00", files={"a.py": "x = 1\n"})
    with pytest.raises(SnapshotError, match="Không có dữ liệu trong khoảng thời gian"):
        find_snapshots(_open(src, cache_root), "main", make_period(*JAN))


def test_first_parent(make_repo, cache_root: Path) -> None:
    """TC-snapshot-10: commit feature trước end, merge sau end → C_END là commit main."""
    src = make_repo()
    m1 = src.commit("M1", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    src.checkout("feat", create=True)
    src.commit("F", "2026-01-20T10:00:00+07:00", files={"b.py": "y = 1\n"})
    src.checkout("main")
    src.merge("feat", "M2", "2026-02-05T10:00:00+07:00")
    snaps = find_snapshots(_open(src, cache_root), "main", make_period(*JAN))
    assert snaps.c_end.sha == m1


def test_unknown_branch(make_repo, cache_root: Path) -> None:
    """TC-snapshot-11: nhánh không tồn tại → GitError."""
    src = make_repo()
    src.commit("a", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    with pytest.raises(GitError, match="Không tìm thấy nhánh"):
        find_snapshots(_open(src, cache_root), "nope", make_period(*JAN))


# ---------- plan_export ----------

TREE = {
    "src/a.py": "x = 1\n",
    "src/b.min.js": "var a=1;\n",
    "node_modules/x.js": "var x = 1;\n",
    "tests/t.py": "assert True\n",
    "README.md": "# Tiêu đề\n",
    "data.json": '{"a": 1}\n',
    "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    "LICENSE": "MIT License\n",
    "big.py": "x = 1\n" * 300,
}
SMALL = FilterConfig(max_file_size_kb=1)


def _tree_repo(make_repo, cache_root: Path,
               extra: dict[str, bytes | str] | None = None) -> tuple[GitRepo, str]:
    src = make_repo()
    for rel, data in {**TREE, **(extra or {})}.items():
        src.write(rel, data)
    src.add_index_entry("120000", src.hash_blob(b"src/a.py"), "link.py")
    first = src.commit("first", "2026-01-02T10:00:00+07:00")
    src.add_index_entry("160000", first, "sub")
    sha = src.commit("second", "2026-01-03T10:00:00+07:00")
    return _open(src, cache_root), sha


def _warn_set(plan) -> set[tuple[str, WarningKind]]:
    return {(w.path, w.kind) for w in plan.warnings}


def test_plan_source_only(make_repo, cache_root: Path) -> None:
    """TC-snapshot-12: source_only — chỉ file source; cảnh báo binary/unknown/too_large."""
    repo, sha = _tree_repo(make_repo, cache_root)
    plan = plan_export(repo, sha, SMALL)
    assert plan.commit_sha == sha
    assert [f.path for f in plan.files] == ["data.json", "src/a.py", "tests/t.py"]
    assert {f.path: f.language for f in plan.files} == {
        "data.json": "JSON", "src/a.py": "Python", "tests/t.py": "Python"}
    assert _warn_set(plan) == {
        ("LICENSE", WarningKind.UNKNOWN_LANGUAGE),
        ("big.py", WarningKind.TOO_LARGE),
        ("logo.png", WarningKind.BINARY),
    }
    assert [w.path for w in plan.warnings] == sorted(w.path for w in plan.warnings)
    messages = {w.kind: w.message for w in plan.warnings}
    assert messages[WarningKind.BINARY] == "Bỏ qua file binary"
    assert messages[WarningKind.UNKNOWN_LANGUAGE] == "Bỏ qua file không nhận diện được ngôn ngữ"
    assert messages[WarningKind.TOO_LARGE].startswith("Bỏ qua file lớn hơn 1 KB")


def test_plan_exclude_tests(make_repo, cache_root: Path) -> None:
    """TC-snapshot-13: include_tests=false bỏ tests/t.py, không cảnh báo."""
    repo, sha = _tree_repo(make_repo, cache_root)
    plan = plan_export(repo, sha, FilterConfig(max_file_size_kb=1, include_tests=False))
    assert [f.path for f in plan.files] == ["data.json", "src/a.py"]
    assert "tests/t.py" not in {w.path for w in plan.warnings}


BINARY_EXTRA = {
    "notes.txt": b"abc" + bytes([0, 1, 2]) + b"binary",
    "big.png": b"PNG" + bytes(3000),
}


def test_plan_full_mode(make_repo, cache_root: Path) -> None:
    """TC-snapshot-14: full — thêm non-source và file quá lớn; binary theo exclude_binary."""
    repo, sha = _tree_repo(make_repo, cache_root, BINARY_EXTRA)
    plan = plan_export(repo, sha, FilterConfig(max_file_size_kb=1, export_mode="full"))
    langs = {f.path: f.language for f in plan.files}
    assert langs == {
        "LICENSE": None, "README.md": None, "big.py": "Python", "data.json": "JSON",
        "src/a.py": "Python", "tests/t.py": "Python",
    }
    assert [f.path for f in plan.files] == sorted(langs)
    warnings = _warn_set(plan)
    for binary in ("logo.png", "notes.txt", "big.png"):
        assert (binary, WarningKind.BINARY) in warnings
    assert ("big.py", WarningKind.TOO_LARGE) in warnings

    plan2 = plan_export(repo, sha, FilterConfig(max_file_size_kb=1, export_mode="full",
                                                exclude_binary=False))
    langs2 = {f.path: f.language for f in plan2.files}
    assert langs2 == {**langs, "logo.png": None, "notes.txt": None, "big.png": None}
    for excluded in ("link.py", "sub", "node_modules/x.js", "src/b.min.js"):
        assert excluded not in langs2


def test_plan_large_unknown(make_repo, cache_root: Path) -> None:
    """TC-snapshot-20: file không lexer > giới hạn — source_only cảnh báo; full export im lặng."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00",
                     files={"huge.dat": "abc\n" * 512, "a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    huge_sha = next(e.sha for e in repo.list_tree(sha) if e.path == "huge.dat")
    requested: list[str] = []
    real_read = repo.read_blobs

    def spy(shas):
        shas = list(shas)
        requested.extend(shas)
        return real_read(shas)

    repo.read_blobs = spy  # type: ignore[method-assign]
    plan = plan_export(repo, sha, SMALL)
    assert [f.path for f in plan.files] == ["a.py"]
    assert _warn_set(plan) == {("huge.dat", WarningKind.TOO_LARGE)}
    assert huge_sha not in requested
    full = plan_export(repo, sha, FilterConfig(max_file_size_kb=1, export_mode="full"))
    assert {f.path: f.language for f in full.files} == {"a.py": "Python", "huge.dat": None}
    assert full.warnings == []


def test_plan_unsafe_paths(make_repo, cache_root: Path,
                           caplog: pytest.LogCaptureFixture) -> None:
    """TC-snapshot-21: thư mục '..' và '.GIT' trong cây không vào plan / zip."""
    src = make_repo()
    tab, nl = chr(9), chr(10)
    blob = src.hash_blob(f"x = 1{nl}".encode())
    sub = src.git("mktree", stdin=f"100644 blob {blob}{tab}evil.py".encode())
    entries = [f"040000 tree {sub}{tab}..", f"040000 tree {sub}{tab}.GIT",
               f"100644 blob {blob}{tab}ok.py"]
    root = src.git("mktree", stdin=nl.join(entries).encode())
    commit = src.git("commit-tree", root, "-m", "evil", date="2026-01-02T10:00:00+07:00")
    src.git("update-ref", "refs/heads/main", commit)
    repo = _open(src, cache_root)
    assert {e.path for e in repo.list_tree(commit)} >= {"../evil.py", ".GIT/evil.py", "ok.py"}
    plan = plan_export(repo, commit, FilterConfig())
    assert [f.path for f in plan.files] == ["ok.py"]
    assert "không an toàn" in caplog.text
    assert [(w.path, w.kind, w.message) for w in plan.warnings] == [
        ("../evil.py", WarningKind.UNSAFE_PATH, UNSAFE_MSG),
        (".GIT/evil.py", WarningKind.UNSAFE_PATH, UNSAFE_MSG),
    ]
    zip_path = write_zip(repo, plan, cache_root.parent / "unsafe.zip",
                         datetime(2026, 1, 2, tzinfo=UTC))
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["ok.py"]


def test_write_zip_cleans_tmp_on_git_error(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-22: blob không tồn tại → GitError lan ra, không còn file .tmp."""
    src = make_repo()
    src.commit("c", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1" + chr(10)})
    repo = _open(src, cache_root)
    plan = ExportPlan("x", [ExportFile("a.py", "0" * 40, "100644", 6, "Python")], [])
    with pytest.raises(GitError):
        write_zip(repo, plan, tmp_path / "out" / "s.zip", datetime(2026, 1, 2, tzinfo=UTC))
    assert not list(tmp_path.rglob("*.tmp"))


# ---------- zip ----------

def test_zip_content_bytes(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-15: zip đúng danh sách, đúng byte, tên Unicode, quyền thực thi."""
    contents = {
        "crlf.py": b"x = 1\r\ny = 2\r\n",
        "lf.py": b"x = 1\ny = 2\n",
        "bom.py": b"\xef\xbb\xbfx = 1\n",
        "nonl.py": b"x = 1",
        "thư mục/tệp.py": "z = 'ă'\n".encode(),
    }
    src = make_repo()
    for rel, data in contents.items():
        src.write(rel, data)
    src.write("run.sh", "#!/bin/sh\necho hi\n", executable=True)
    sha = src.commit("c", "2026-01-02T10:00:00+07:00")
    repo = _open(src, cache_root)
    plan = plan_export(repo, sha, FilterConfig())
    out = write_zip(repo, plan, tmp_path / "out" / "x.zip", datetime(2026, 1, 2, 10, tzinfo=BKK))
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert names == sorted([*contents, "run.sh"])
        for rel, data in contents.items():
            assert zf.read(rel) == data
        assert zf.getinfo("run.sh").external_attr >> 16 == 0o100755
        assert zf.getinfo("lf.py").external_attr >> 16 == 0o100644
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_zip_reproducible(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-16: export 2 lần → zip trùng SHA-256; date_time = committer date theo tz."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:20:30+07:00",
                     files={"a.py": "x = 1\n", "b/c.js": "let a = 1;\n"})
    repo = _open(src, cache_root)
    commit = repo.commit_info(sha)
    digests = []
    for name in ("one.zip", "two.zip"):
        export_snapshot(repo, commit, FilterConfig(), tmp_path / name, "UTC")
        digests.append(hashlib.sha256((tmp_path / name).read_bytes()).hexdigest())
    assert digests[0] == digests[1]
    with zipfile.ZipFile(tmp_path / "one.zip") as zf:
        assert {i.date_time for i in zf.infolist()} == {(2026, 1, 2, 3, 20, 30)}


def test_export_all_users(section14_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-17: export start/end (tất cả user) trên repo §14."""
    src, app_start, app_end, util, end_sha = section14_repo()
    repo = _open(src, cache_root)
    period = make_period(*JAN)
    snaps = find_snapshots(repo, "main", period)
    assert snaps.c_end.sha == end_sha
    assert snaps.c_start is not None
    start_zip = tmp_path / start_zip_name(period, snaps.c_start)
    end_zip = tmp_path / end_zip_name(period, "all")
    export_snapshot(repo, snaps.c_start, FilterConfig(), start_zip, period.timezone)
    export_snapshot(repo, snaps.c_end, FilterConfig(), end_zip, period.timezone)
    with zipfile.ZipFile(start_zip) as zf:
        assert zf.namelist() == ["app.py"]
        assert zf.read("app.py").decode() == app_start
    with zipfile.ZipFile(end_zip) as zf:
        assert zf.namelist() == ["app.py", "util.py"]
        assert zf.read("app.py").decode() == app_end
        assert zf.read("util.py").decode() == util
        assert b"late0" not in zf.read("app.py")


def test_zip_names() -> None:
    """TC-snapshot-18: tên zip theo §12 / D11 và safe_name."""
    period = Period(datetime(2026, 1, 1, tzinfo=BKK), datetime(2026, 1, 31, 23, 59, 59,
                    tzinfo=BKK), "Asia/Bangkok", *JAN)

    class _Commit:
        short_sha = "a1b2c3d"

    assert start_zip_name(period, _Commit()) == "start_2026-01-01_a1b2c3d.zip"
    assert start_zip_name(period, None) == "start_2026-01-01_empty.zip"
    assert end_zip_name(period, "all") == "end_2026-01-31_all.zip"
    assert safe_name("feature/x y") == "feature_x_y"
    assert safe_name("Bình") == "B_nh"
    assert safe_name("") == "_"


def test_zip_write_error(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-19: không ghi được zip → SnapshotError, không để lại file tạm."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    plan = plan_export(repo, sha, FilterConfig())
    with pytest.raises(SnapshotError, match="Không ghi được file"):
        write_zip(repo, plan, blocker / "x.zip", datetime(2026, 1, 2, tzinfo=UTC))
    assert not list(tmp_path.rglob("*.tmp"))


def test_unsafe_paths_windows(make_repo, cache_root: Path) -> None:
    """TC-snapshot-23: đường dẫn kiểu Windows nguy hiểm (C:, ':', .git.) bị loại."""
    for bad in ("C:/evil.py", "a:b.py", ".git./x.py", ".GIT /x.py", "a" + chr(92) + "b.py"):
        assert is_unsafe_path(bad), bad
    for ok in ("src/ok.py", "src/.gitignore", "a.b/c.py"):
        assert not is_unsafe_path(ok), ok
    src = make_repo()
    tab = chr(9)
    blob = src.hash_blob(b"x = 1" + bytes([10]))
    root = src.git("mktree", stdin=chr(10).join(
        [f"100644 blob {blob}{tab}a:b.py", f"100644 blob {blob}{tab}ok.py"]).encode())
    commit = src.git("commit-tree", root, "-m", "colon", date="2026-01-02T10:00:00+07:00")
    src.git("update-ref", "refs/heads/main", commit)
    plan = plan_export(_open(src, cache_root), commit, FilterConfig())
    assert [f.path for f in plan.files] == ["ok.py"]
    assert [(w.path, w.kind) for w in plan.warnings] == [("a:b.py", WarningKind.UNSAFE_PATH)]


def test_write_zip_error_stops_cat_file(make_repo, cache_root: Path, tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-snapshot-24: ghi zip lỗi giữa chừng → tiến trình cat-file dừng ngay, không còn .tmp."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00",
                     files={"a.py": "x = 1" + chr(10), "b.py": "y = 2" + chr(10)})
    repo = _open(src, cache_root)
    plan = plan_export(repo, sha, FilterConfig())
    procs: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def spy_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(git_repo_module.subprocess, "Popen", spy_popen)
    real_writestr = zipfile.ZipFile.writestr
    calls = {"n": 0}

    def failing_writestr(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("đĩa đầy")
        return real_writestr(self, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "writestr", failing_writestr)
    with pytest.raises(SnapshotError, match="Không ghi được file") as excinfo:
        write_zip(repo, plan, tmp_path / "out" / "x.zip", datetime(2026, 1, 2, tzinfo=UTC))
    assert excinfo.value is not None  # exception vẫn được giữ
    assert procs and all(p.poll() is not None for p in procs)
    assert not list(tmp_path.rglob("*.tmp"))


# ---------- M4: lọc từng file, write_entries, zip_timestamp ----------

TEXT_HEAD = b"x = 1\n"
BIN_HEAD = b"x\x00y\n"
TOO, BIN, UNK = WarningKind.TOO_LARGE, WarningKind.BINARY, WarningKind.UNKNOWN_LANGUAGE
UNSAFE = WarningKind.UNSAFE_PATH
UNSAFE_MSG = "Bỏ qua file có đường dẫn không an toàn (không đưa vào export)"
_FIXED_MESSAGES = {BIN: "Bỏ qua file binary", UNK: "Bỏ qua file không nhận diện được ngôn ngữ",
                   UNSAFE: UNSAFE_MSG}

# Bảng tóm tắt 5.3 với max_file_size_kb=1 (giới hạn 1024 byte).
# (id, path, size, head, source_only, full + exclude_binary, full + giữ binary);
# mỗi kết quả = (keep, language khi keep, kinds cảnh báo theo thứ tự).
FILE_ROWS = [
    ("source-text", "src/a.py", 10, TEXT_HEAD,
     (True, "Python", ()), (True, "Python", ()), (True, "Python", ())),
    ("source-large-text", "big.py", 2048, TEXT_HEAD,
     (False, None, (TOO,)), (True, "Python", (TOO,)), (True, "Python", (TOO,))),
    ("excluded-language-text", "README.md", 10, TEXT_HEAD,
     (False, None, ()), (True, None, ()), (True, None, ())),
    ("unknown-text", "LICENSE", 10, TEXT_HEAD,
     (False, None, (UNK,)), (True, None, (UNK,)), (True, None, (UNK,))),
    ("unknown-large-text", "huge.dat", 2048, TEXT_HEAD,
     (False, None, (TOO,)), (True, None, ()), (True, None, ())),
    ("source-binary", "src/a.py", 10, BIN_HEAD,
     (False, None, (BIN,)), (False, None, (BIN,)), (True, None, (BIN,))),
    ("source-large-binary", "big.py", 2048, BIN_HEAD,
     (False, None, (TOO,)), (False, None, (TOO,)), (True, None, (TOO,))),
    ("excluded-language-binary", "notes.txt", 10, BIN_HEAD,
     (False, None, ()), (False, None, (BIN,)), (True, None, (BIN,))),
    ("unknown-binary", "logo.png", 10, BIN_HEAD,
     (False, None, (BIN,)), (False, None, (BIN,)), (True, None, (BIN,))),
    ("unknown-large-binary", "big.png", 3000, BIN_HEAD,
     (False, None, (TOO,)), (False, None, (BIN,)), (True, None, (BIN,))),
]


def _table_cases():
    for row_id, path, size, head, source_only, full_exclude, full_keep in FILE_ROWS:
        for exclude_binary in (True, False):
            yield pytest.param(path, size, head, "source_only", exclude_binary, source_only,
                               id=f"{row_id}-source_only-exclude_binary={exclude_binary}")
        yield pytest.param(path, size, head, "full", True, full_exclude,
                           id=f"{row_id}-full-exclude_binary=True")
        yield pytest.param(path, size, head, "full", False, full_keep,
                           id=f"{row_id}-full-exclude_binary=False")


def _decide(path: str, size: int, head: bytes, filters: FilterConfig):
    """screen_entry rồi (nếu keep) finish_entry → (keep, language, warnings)."""
    screening = screen_entry(path, "100644", "blob", size, filters)
    assert isinstance(screening, Screening)
    if not screening.keep:
        return False, None, tuple(screening.warnings)
    selection = finish_entry(path, screening, head, filters)
    assert isinstance(selection, Selection)
    assert set(screening.warnings) <= set(selection.warnings)
    return selection.keep, selection.language, tuple(selection.warnings)


def _check_messages(warnings, path: str, limit_kb: int = 1) -> None:
    for w in warnings:
        assert w.path == path
        if w.kind is TOO:
            assert w.message.startswith(f"Bỏ qua file lớn hơn {limit_kb} KB (")
        else:
            assert w.message == _FIXED_MESSAGES[w.kind]


@pytest.mark.parametrize(("path", "size", "head", "export_mode", "exclude_binary", "expected"),
                         list(_table_cases()))
def test_screen_finish_table(path: str, size: int, head: bytes, export_mode: str,
                             exclude_binary: bool, expected) -> None:
    """TC-snapshot-25: screen_entry + finish_entry đúng bảng 5.3 × chế độ × exclude_binary."""
    filters = FilterConfig(max_file_size_kb=1, export_mode=export_mode,
                           exclude_binary=exclude_binary)
    keep, language, warnings = _decide(path, size, head, filters)
    exp_keep, exp_language, exp_kinds = expected
    assert keep is exp_keep
    if keep:
        assert language == exp_language
    assert tuple(w.kind for w in warnings) == exp_kinds
    _check_messages(warnings, path)


@pytest.mark.parametrize("exclude_binary", [True, False])
@pytest.mark.parametrize("export_mode", ["source_only", "full"])
@pytest.mark.parametrize(
    ("path", "mode", "object_type"),
    [
        ("link.py", "120000", "blob"),
        ("sub", "160000", "commit"),
        ("node_modules/x.js", "100644", "blob"),
        ("src/b.min.js", "100644", "blob"),
    ],
    ids=["symlink", "submodule", "excluded-dir", "excluded-glob"],
)
def test_screen_entry_excluded(path: str, mode: str, object_type: str, export_mode: str,
                               exclude_binary: bool) -> None:
    """TC-snapshot-25: symlink / submodule / lọc đường dẫn → keep=False, không cảnh báo."""
    filters = FilterConfig(max_file_size_kb=1, export_mode=export_mode,
                           exclude_binary=exclude_binary)
    screening = screen_entry(path, mode, object_type, 10, filters)
    assert screening.keep is False
    assert tuple(screening.warnings) == ()
    with pytest.raises(ValueError):
        finish_entry(path, screening, TEXT_HEAD, filters)


@pytest.mark.parametrize("exclude_binary", [True, False])
@pytest.mark.parametrize("export_mode", ["source_only", "full"])
@pytest.mark.parametrize("path", ["../evil.py", "node_modules/a:b.js"],
                         ids=["dotdot", "colon-in-excluded-dir"])
def test_screen_entry_unsafe(path: str, export_mode: str, exclude_binary: bool,
                             caplog: pytest.LogCaptureFixture) -> None:
    """TC-snapshot-25: đường dẫn không an toàn → keep=False, đúng một cảnh báo UNSAFE_PATH."""
    caplog.set_level(logging.WARNING, logger="loc_counter")
    filters = FilterConfig(max_file_size_kb=1, export_mode=export_mode,
                           exclude_binary=exclude_binary)
    screening = screen_entry(path, "100644", "blob", 10, filters)
    assert screening.keep is False
    assert screening.language is None
    assert not (screening.unknown or screening.excluded_language or screening.too_large)
    assert tuple((w.kind, w.path) for w in screening.warnings) == ((UNSAFE, path),)
    _check_messages(screening.warnings, path)
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    with pytest.raises(ValueError):
        finish_entry(path, screening, TEXT_HEAD, filters)


def test_screening_flags() -> None:
    """TC-snapshot-25: Screening ghi đúng language / unknown / excluded_language / too_large."""
    full = FilterConfig(max_file_size_kb=1, export_mode="full")

    def flags(path: str, size: int):
        s = screen_entry(path, "100644", "blob", size, full)
        return s.keep, s.language, s.unknown, s.excluded_language, s.too_large

    assert flags("src/a.py", 1024) == (True, "Python", False, False, False)
    assert flags("src/a.py", 1025) == (True, "Python", False, False, True)
    assert flags("README.md", 10) == (True, None, False, True, False)
    assert flags("LICENSE", 10) == (True, None, True, False, False)
    assert flags("huge.dat", 2048) == (True, None, True, False, True)

    # finish_entry chỉ xét BINARY_SNIFF_BYTES byte đầu của head
    default = FilterConfig()
    screening = screen_entry("src/a.py", "100644", "blob", 10, default)
    late_nul = b"x" * BINARY_SNIFF_BYTES + b"\x00"
    early_nul = b"x" * (BINARY_SNIFF_BYTES - 1) + b"\x00"
    assert finish_entry("src/a.py", screening, late_nul, default) == Selection(True, "Python", ())
    early = finish_entry("src/a.py", screening, early_nul, default)
    assert early.keep is False and tuple(w.kind for w in early.warnings) == (BIN,)


def _expected_plan(repo: GitRepo, sha: str, filters: FilterConfig):
    """screen_entry/finish_entry trực tiếp trên từng entry → (files, warnings, SHA cần đọc)."""
    files: list[ExportFile] = []
    warnings = []
    to_read: list[str] = []
    for e in repo.list_tree(sha):
        screening = screen_entry(e.path, e.mode, e.object_type, e.size or 0, filters)
        if not screening.keep:
            warnings += screening.warnings
            continue
        to_read.append(e.sha)
        selection = finish_entry(e.path, screening, repo.read_blob(e.sha)[:BINARY_SNIFF_BYTES],
                                 filters)
        warnings += selection.warnings
        if selection.keep:
            files.append(ExportFile(e.path, e.sha, e.mode, e.size or 0, selection.language))
    return files, sorted(warnings, key=lambda w: (w.path, w.kind)), list(dict.fromkeys(to_read))


@pytest.mark.parametrize(
    ("extra", "filters"),
    [
        (None, SMALL),
        (BINARY_EXTRA, SMALL),
        (BINARY_EXTRA, FilterConfig(max_file_size_kb=1, export_mode="full")),
        (BINARY_EXTRA, FilterConfig(max_file_size_kb=1, export_mode="full", exclude_binary=False)),
    ],
    ids=["tc12-source_only", "tc14-source_only", "tc14-full-exclude_binary",
         "tc14-full-keep_binary"],
)
def test_plan_export_matches_screen_finish(make_repo, cache_root: Path, extra,
                                           filters: FilterConfig) -> None:
    """TC-snapshot-26: plan_export = screen_entry/finish_entry từng entry; read_blobs gọi 1 lần."""
    repo, sha = _tree_repo(make_repo, cache_root, extra)
    files, warnings, keep_shas = _expected_plan(repo, sha, filters)
    requested: list[list[str]] = []
    real_read = repo.read_blobs

    def spy(shas):
        shas = list(shas)
        requested.append(shas)
        return real_read(shas)

    repo.read_blobs = spy  # type: ignore[method-assign]
    plan = plan_export(repo, sha, filters)
    assert plan.files == files
    assert plan.warnings == warnings
    assert requested == [keep_shas]


SELECT_CASES = [
    ("src/a.py", b"x = 12345\n", "source_only", (True, "Python", ())),
    ("src/a.py", b"x = 12345\n", "full", (True, "Python", ())),
    ("src/a.py", b"x = 1\n" * 350, "source_only", (False, None, (TOO,))),
    ("src/a.py", b"x = 1\n" * 350, "full", (True, "Python", (TOO,))),
    ("vendor/a.py", b"x = 1\n", "source_only", (False, None, ())),
    ("vendor/a.py", b"x = 1\n", "full", (False, None, ())),
    ("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "source_only", (False, None, (BIN,))),
    ("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "full", (False, None, (BIN,))),
    ("C:/x.py", b"x = 1\n", "source_only", (False, None, (UNSAFE,))),
    ("C:/x.py", b"x = 1\n", "full", (False, None, (UNSAFE,))),
    ("LICENSE", b"MIT License\n", "source_only", (False, None, (UNK,))),
    ("LICENSE", b"MIT License\n", "full", (True, None, (UNK,))),
]


@pytest.mark.parametrize(("path", "data", "export_mode", "expected"), SELECT_CASES,
                         ids=[f"{p}-{len(d)}B-{m}" for p, d, m, _ in SELECT_CASES])
def test_select_content(path: str, data: bytes, export_mode: str, expected) -> None:
    """TC-snapshot-27: select_content lọc file đã dựng theo tên + nội dung trong bộ nhớ."""
    filters = FilterConfig(max_file_size_kb=1, export_mode=export_mode)
    selection = select_content(path, "100644", data, filters)
    assert isinstance(selection, Selection)
    exp_keep, exp_language, exp_kinds = expected
    assert selection.keep is exp_keep
    if selection.keep:
        assert selection.language == exp_language
    assert tuple(w.kind for w in selection.warnings) == exp_kinds
    _check_messages(selection.warnings, path)
    screening = screen_entry(path, "100644", "blob", len(data), filters)
    if not screening.keep:  # bị loại ngay ở bước lọc tên / kích thước
        assert selection == Selection(False, None, tuple(screening.warnings))


def test_select_content_unsafe_logged(caplog: pytest.LogCaptureFixture) -> None:
    """TC-snapshot-27: tên không an toàn `C:/x.py` → bỏ, cảnh báo UNSAFE_PATH, log WARNING."""
    caplog.set_level(logging.WARNING, logger="loc_counter")
    selection = select_content("C:/x.py", "100644", b"x = 1\n", FilterConfig())
    assert selection.keep is False
    assert [(w.kind, w.path, w.message) for w in selection.warnings] == [
        (UNSAFE, "C:/x.py", UNSAFE_MSG)]
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def _spy_read_blobs(repo: GitRepo) -> list[list[str]]:
    requested: list[list[str]] = []
    real_read = repo.read_blobs

    def spy(shas):
        shas = list(shas)
        requested.append(shas)
        return real_read(shas)

    repo.read_blobs = spy  # type: ignore[method-assign]
    return requested


def test_write_entries_mixed(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-28: trộn blob và data; zip theo path, đúng byte, tái lập; read_blobs 1 lần."""
    z_data, m_data = b"z = 1\r\nz = 2\r\n", b"m = 1\n"
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00", files={"z.py": z_data, "m.py": m_data})
    repo = _open(src, cache_root)
    blobs = {e.path: e.sha for e in repo.list_tree(sha)}
    entries = [
        ZipEntry("z.py", "100644", blob_sha=blobs["z.py"]),
        ZipEntry("a/b.py", "100755", data=b"x\r\ny"),
        ZipEntry("m.py", "100644", blob_sha=blobs["m.py"]),
    ]
    requested = _spy_read_blobs(repo)
    stamp = datetime(2026, 1, 2, 10, 20, 30, tzinfo=BKK)
    one = tmp_path / "out" / "one.zip"
    assert write_entries(repo, entries, one, stamp) == one
    with zipfile.ZipFile(one) as zf:
        assert zf.namelist() == ["a/b.py", "m.py", "z.py"]
        assert zf.read("a/b.py") == b"x\r\ny"
        assert zf.read("m.py") == m_data
        assert zf.read("z.py") == z_data
        assert zf.getinfo("a/b.py").external_attr >> 16 == 0o100755
        assert zf.getinfo("m.py").external_attr >> 16 == 0o100644
        assert zf.getinfo("z.py").external_attr >> 16 == 0o100644
        for info in zf.infolist():
            assert info.date_time == (2026, 1, 2, 10, 20, 30)
            assert info.compress_type == zipfile.ZIP_DEFLATED
            assert info.create_system == 3
    assert requested == [[blobs["m.py"], blobs["z.py"]]]

    requested.clear()
    two = tmp_path / "out" / "two.zip"
    write_entries(repo, [entries[2], entries[0], entries[1]], two, stamp)
    assert requested == [[blobs["m.py"], blobs["z.py"]]]
    assert hashlib.sha256(one.read_bytes()).digest() == hashlib.sha256(two.read_bytes()).digest()
    assert not list(tmp_path.rglob("*.tmp"))


def test_write_zip_same_as_write_entries(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-28: write_zip(plan) trùng byte với write_entries các entry blob của plan."""
    repo, sha = _tree_repo(make_repo, cache_root)
    plan = plan_export(repo, sha, FilterConfig())
    stamp = datetime(2026, 1, 3, 10, tzinfo=BKK)
    via_plan = write_zip(repo, plan, tmp_path / "plan.zip", stamp)
    via_entries = write_entries(repo, [ZipEntry(f.path, f.mode, f.blob_sha) for f in plan.files],
                                tmp_path / "entries.zip", stamp)
    assert via_plan.read_bytes() == via_entries.read_bytes()


@pytest.mark.parametrize(
    "make_entries",
    [
        lambda blob: [ZipEntry("a.py", "100644", blob_sha=blob, data=b"x = 1\n")],
        lambda blob: [ZipEntry("a.py", "100644")],
        lambda blob: [ZipEntry("a.py", "100644", blob_sha=blob),
                      ZipEntry("a.py", "100644", data=b"y = 2\n")],
    ],
    ids=["blob-and-data", "neither", "duplicate-path"],
)
def test_write_entries_invalid(make_repo, cache_root: Path, tmp_path: Path, make_entries) -> None:
    """TC-snapshot-29: có cả / không có blob và data, trùng path → ValueError, không tạo file."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    blob = repo.list_tree(sha)[0].sha
    entries = make_entries(blob)
    zip_path = tmp_path / "out" / "bad.zip"
    with pytest.raises(ValueError):
        write_entries(repo, entries, zip_path, datetime(2026, 1, 2, tzinfo=UTC))
    assert not zip_path.exists()
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.zip"))


def test_write_entries_empty(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-29: entries rỗng → zip hợp lệ, 0 entry."""
    src = make_repo()
    src.commit("c", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    zip_path = tmp_path / "out" / "empty.zip"
    assert write_entries(repo, [], zip_path, datetime(2026, 1, 2, tzinfo=UTC)) == zip_path
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == []
        assert zf.testzip() is None
    assert not list(tmp_path.rglob("*.tmp"))


def test_write_entries_blob_error(make_repo, cache_root: Path, tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-snapshot-30: blob không tồn tại → GitError lan ra, không còn .tmp, cat-file đã dừng."""
    src = make_repo()
    src.commit("c", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    repo = _open(src, cache_root)
    procs: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def spy_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(git_repo_module.subprocess, "Popen", spy_popen)
    entries = [ZipEntry("a.py", "100644", data=b"x = 1\n"),
               ZipEntry("b.py", "100644", blob_sha="0" * 40)]
    zip_path = tmp_path / "out" / "err.zip"
    with pytest.raises(GitError):
        write_entries(repo, entries, zip_path, datetime(2026, 1, 2, tzinfo=UTC))
    assert procs and all(p.poll() is not None for p in procs)
    assert not zip_path.exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_zip_timestamp() -> None:
    """TC-snapshot-31: committer date quy về timezone; không có commit → 1980-01-01 00:00:00."""
    commit = CommitInfo(sha="a" * 40, short_sha="aaaaaaa",
                        committer_date=datetime(2026, 1, 31, 16, 59, 59, tzinfo=UTC),
                        author_name="x", author_email="x@example.com", subject="s")
    stamp = zip_timestamp(commit, "Asia/Bangkok")
    assert stamp == datetime(2026, 1, 31, 23, 59, 59, tzinfo=BKK)
    assert stamp.utcoffset() == timedelta(hours=7)
    assert stamp.replace(tzinfo=None) == datetime(2026, 1, 31, 23, 59, 59)
    empty = zip_timestamp(None, "Asia/Bangkok")
    assert empty == datetime(1980, 1, 1)
    assert empty.tzinfo is None


def test_write_entries_checks_cat_file_exit(make_repo, cache_root: Path, tmp_path: Path) -> None:
    """TC-snapshot-32: read_blobs lỗi ở bước kết thúc (mã thoát cat-file) → GitError, không zip."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00",
                     files={"a.py": "x = 1\n", "b.py": "y = 2\n"})
    repo = _open(src, cache_root)
    blobs = {e.path: e.sha for e in repo.list_tree(sha)}
    contents = {blobs["a.py"]: b"x = 1\n", blobs["b.py"]: b"y = 2\n"}
    state = {"yielded": 0, "finished": False}

    def fake_read_blobs(shas):
        for blob in list(shas):
            state["yielded"] += 1
            yield blob, contents[blob]
        state["finished"] = True  # bước kết thúc: kiểm mã thoát của git cat-file
        raise GitError("Lệnh git thất bại: fatal: cat-file chết (giả lập)")

    repo.read_blobs = fake_read_blobs  # type: ignore[method-assign]
    entries = [ZipEntry("a.py", "100644", blob_sha=blobs["a.py"]),
               ZipEntry("b.py", "100644", blob_sha=blobs["b.py"]),
               ZipEntry("c.py", "100644", data=b"z = 3\n")]
    zip_path = tmp_path / "out" / "end.zip"
    with pytest.raises(GitError, match="cat-file chết"):
        write_entries(repo, entries, zip_path, datetime(2026, 1, 2, tzinfo=UTC))
    assert state == {"yielded": 2, "finished": True}
    assert not zip_path.exists()
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.zip"))
