"""Test cho git_repo.py (spec docs/specs/git_repo.md)."""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import stat
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from loc_counter import git_repo
from loc_counter.git_repo import (
    BlameLine,
    DiffEntry,
    GitError,
    GitRepo,
    Hunk,
    TreeDiff,
    cache_dir_for,
    git_version,
    mask_secrets,
    normalize_source,
)

TOKEN = "ghp_SECRET123"
TOKEN_B64 = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
BKK = timezone(timedelta(hours=7))


@pytest.fixture(autouse=True)
def _clear_version_cache():
    git_version.cache_clear()
    yield
    git_version.cache_clear()


def _two_branch_repo(make_repo):
    src = make_repo()
    src.commit("init", "2026-01-01T10:00:00+07:00", files={"a.py": "x = 1\n"})
    src.checkout("feature/x", create=True)
    src.commit("feat", "2026-01-02T10:00:00+07:00", files={"b.py": "y = 2\n"})
    src.checkout("main")
    return src


def test_git_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-01: phiên bản git thật ≥ 2.30; git cũ / không có git → GitError."""
    assert git_version() >= (2, 30, 0)

    git_version.cache_clear()
    monkeypatch.setattr(
        git_repo.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, b"git version 2.29.0\n", b""),
    )
    with pytest.raises(GitError, match="quá cũ"):
        git_version()

    git_version.cache_clear()

    def missing(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(git_repo.subprocess, "run", missing)
    with pytest.raises(GitError, match="Không tìm thấy lệnh git"):
        git_version()


def test_normalize_source(tmp_path: Path) -> None:
    """TC-git_repo-02: chuẩn hóa URL / đường dẫn; từ chối credential trong URL."""
    assert normalize_source(" https://github.com/o/r/ ") == ("https://github.com/o/r", False)
    assert normalize_source("git@github.com:o/r.git") == ("git@github.com:o/r.git", False)
    for bad, secret in (("https://u:p4ss@github.com/o/r", "p4ss"),
                        ("https://tok999@github.com/o/r", "tok999")):
        with pytest.raises(GitError, match="thông tin xác thực") as exc:
            normalize_source(bad)
        assert secret not in str(exc.value)
    with pytest.raises(GitError, match="Chưa nhập repo"):
        normalize_source("   ")
    local = tmp_path / "repo"
    local.mkdir()
    assert normalize_source(str(local)) == (str(local.resolve()), True)
    with pytest.raises(GitError, match="Không tìm thấy repo"):
        normalize_source(str(tmp_path / "missing"))


def test_password_in_url(tmp_path: Path, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                         caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-54: mật khẩu trong URL / scp bị từ chối (cả khi chứa # ? /), không lộ."""
    caplog.set_level(logging.DEBUG, logger="loc_counter")
    messages: list[str] = []
    for bad in ("ssh://u:s3cret@h/o/r", "SSH://u:s3cret@h:22/o/r", "git://u:s3cret@h/o/r",
                "file://u:s3cret@h/o/r", "git+ssh://u:s3cret@h/o/r", "ftp://u:s3cret@h/o/r",
                "us:s3cret@h:o/r.git", "u~x:s3cret@h:o/r", "us:s3@cret@h:o/r",
                "ssh://u:s3#cret@h/o/r", "ssh://u:s3?cret@h/o/r", "ssh://u:s3/cret@h/o/r",
                "git://u:s3#cret@h/o/r", "https://u:s3#cret@github.com/o/r",
                "https://u:s3/cret@github.com/o/r"):
        with pytest.raises(GitError, match="thông tin xác thực") as exc:
            normalize_source(bad)
        messages.append(str(exc.value))
    for good in ("ssh://git@h/o/r", "ssh://git@h:22/o/r/", "ssh://h/o/r", "git+ssh://git@h/o/r",
                 "ssh+git://git@h/o/r", "git@h:o/r.git"):
        assert normalize_source(good) == (good.rstrip("/"), False)
    for local in (tmp_path / "u:s3cret@x", tmp_path / "a@b"):
        with pytest.raises(GitError, match=r"Không tìm thấy repo: \*\*\*@") as exc:
            normalize_source(str(local))
        messages.append(str(exc.value))

    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    for bad in ("ext::sh -c x", "fd::0", "FD::0,1"):
        with pytest.raises(GitError, match="Không hỗ trợ nguồn dạng") as exc:
            normalize_source(bad)
        assert "sh -c" not in str(exc.value)
    real_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir",
                        lambda self: self.name == "repo:2024" or real_is_dir(self))
    assert normalize_source("repo:2024") == (str(Path("repo:2024").resolve()), True)
    monkeypatch.setattr(Path, "is_dir", real_is_dir)

    monkeypatch.setattr(git_repo.subprocess, "run", spy)
    for source in ("ssh://u:s3cret@h/o/r", "file://u:s3#cret@h/o/r"):
        with pytest.raises(GitError, match="thông tin xác thực") as exc:
            GitRepo.open(source, cache_root=cache_root)
        messages.append(str(exc.value))
    assert all(cmd[1:] == ["--version"] for cmd in calls)
    for text in (*messages, caplog.text):
        assert "s3cret" not in text and "cret" not in text


def test_cache_dir_for(tmp_path: Path) -> None:
    """TC-git_repo-03: cùng nguồn → cùng thư mục, nguồn khác → khác; tên 16 hex."""
    a1 = cache_dir_for("https://github.com/o/r", tmp_path)
    a2 = cache_dir_for("https://github.com/o/r", tmp_path)
    b = cache_dir_for("https://github.com/o/other", tmp_path)
    assert a1 == a2 != b
    assert a1.parent == tmp_path
    assert len(a1.name) == 16 and all(c in "0123456789abcdef" for c in a1.name)


def test_clone_local(make_repo, cache_root: Path) -> None:
    """TC-git_repo-04: clone repo local vào cache dạng bare; nguồn không đổi."""
    src = _two_branch_repo(make_repo)
    refs_before = src.git("for-each-ref")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.git_dir.parent == cache_root
    assert repo.run(["rev-parse", "--is-bare-repository"]).strip() == b"true"
    assert repo.list_branches() == ["feature/x", "main"]
    assert repo.default_branch() == "main"
    assert repo.source == str(src.path.resolve())
    assert src.git("for-each-ref") == refs_before
    assert src.git("status", "--porcelain") == ""


def test_reopen_fetches(make_repo, cache_root: Path) -> None:
    """TC-git_repo-05: mở lại → fetch commit mới, prune nhánh đã xóa, thêm nhánh mới."""
    src = _two_branch_repo(make_repo)
    GitRepo.open(str(src.path), cache_root=cache_root)
    new_sha = src.commit("more", "2026-01-03T10:00:00+07:00", files={"c.py": "z = 3\n"})
    src.git("branch", "-D", "feature/x")
    src.git("branch", "dev")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.resolve_branch("main") == new_sha
    assert repo.list_branches() == ["dev", "main"]


def test_broken_cache_recloned(make_repo, cache_root: Path) -> None:
    """TC-git_repo-06: thư mục cache tồn tại nhưng không phải bare repo → clone lại."""
    src = _two_branch_repo(make_repo)
    dest = cache_dir_for(str(src.path.resolve()), cache_root)
    dest.mkdir(parents=True)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.git_dir == dest
    assert repo.list_branches() == ["feature/x", "main"]


def test_not_a_repo(tmp_path: Path, cache_root: Path) -> None:
    """TC-git_repo-07: thư mục không phải repo → GitError; không để lại thư mục tạm."""
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitError, match="Không phải Git repository"):
        GitRepo.open(str(plain), cache_root=cache_root)
    leftovers = list(cache_root.iterdir()) if cache_root.exists() else []
    assert leftovers == []


def test_resolve_branch_errors(make_repo, cache_root: Path) -> None:
    """TC-git_repo-08: nhánh không tồn tại / tên nguy hiểm → GitError."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    for name in ("nope", "--all", "a..b"):
        with pytest.raises(GitError, match="Không tìm thấy nhánh"):
            repo.resolve_branch(name)
    assert len(repo.resolve_branch("feature/x")) == 40


def test_rev_before_boundaries(make_repo, cache_root: Path) -> None:
    """TC-git_repo-09: mốc bao gồm commit bằng mốc; hiểu offset múi giờ."""
    src = make_repo()
    a = src.commit("A", "2026-01-01T00:00:00+07:00", files={"f.txt": "a\n"})
    b = src.commit("B", "2026-01-01T00:00:01+07:00", files={"f.txt": "b\n"})
    c = src.commit("C", "2026-01-31T23:59:59+07:00", files={"f.txt": "c\n"})
    src.commit("D", "2026-02-01T00:00:00+07:00", files={"f.txt": "d\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.rev_before("main", datetime(2025, 12, 31, 23, 59, 59, tzinfo=BKK)) is None
    assert repo.rev_before("main", datetime(2026, 1, 1, 0, 0, 0, tzinfo=BKK)) == a
    assert repo.rev_before("main", datetime(2026, 1, 31, 23, 59, 59, tzinfo=BKK)) == c
    assert repo.rev_before("main", datetime(2026, 1, 31, 16, 59, 58, tzinfo=UTC)) == b
    assert repo.rev_before("main", datetime(2026, 1, 31, 16, 59, 59, 999, tzinfo=UTC)) == c


def test_rev_before_first_parent(make_repo, cache_root: Path) -> None:
    """TC-git_repo-10: commit trên nhánh feature đã merge không được chọn."""
    src = make_repo()
    m1 = src.commit("M1", "2026-01-01T10:00:00+07:00", files={"a.py": "x = 1\n"})
    src.checkout("feat", create=True)
    src.commit("F", "2026-01-05T10:00:00+07:00", files={"b.py": "y = 1\n"})
    src.checkout("main")
    src.merge("feat", "M2", "2026-01-10T10:00:00+07:00")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.rev_before("main", datetime(2026, 1, 6, tzinfo=BKK)) == m1


def test_rev_before_requires_tz(make_repo, cache_root: Path) -> None:
    """TC-git_repo-11: datetime không có tzinfo → ValueError."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    with pytest.raises(ValueError):
        repo.rev_before("main", datetime(2026, 1, 1))


def test_commit_info(make_repo, cache_root: Path) -> None:
    """TC-git_repo-12: thông tin commit Unicode, committer date aware."""
    src = make_repo()
    sha = src.commit("Sửa lỗi đăng nhập", "2026-01-02T08:30:00+07:00",
                     author=("Bình", "b@x.vn"), files={"a.py": "x = 1\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    info = repo.commit_info(sha)
    assert info.sha == sha and info.short_sha == sha[:7]
    assert info.subject == "Sửa lỗi đăng nhập"
    assert (info.author_name, info.author_email) == ("Bình", "b@x.vn")
    assert info.committer_date == datetime(2026, 1, 2, 8, 30, tzinfo=BKK)
    assert info.committer_date.utcoffset() == timedelta(hours=7)


def test_list_tree(make_repo, cache_root: Path) -> None:
    """TC-git_repo-13: path POSIX Unicode, mode/type, symlink, submodule, sắp xếp."""
    src = make_repo()
    src.write("src/a.py", "x = 1\n")
    src.write("thư mục/tệp ở đây.py", "y = 2\n")
    src.write("run.sh", "#!/bin/sh\necho hi\n", executable=True)
    src.add_index_entry("120000", src.hash_blob(b"src/a.py"), "link.py")
    first = src.commit("first", "2026-01-01T10:00:00+07:00")
    src.add_index_entry("160000", first, "sub")
    sha = src.commit("second", "2026-01-02T10:00:00+07:00")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    entries = repo.list_tree(sha)
    by_path = {e.path: e for e in entries}
    assert [e.path for e in entries] == sorted(by_path)
    assert set(by_path) == {"src/a.py", "thư mục/tệp ở đây.py", "run.sh", "link.py", "sub"}
    assert by_path["run.sh"].mode == "100755"
    assert by_path["src/a.py"].mode == "100644" and by_path["src/a.py"].size == 6
    assert by_path["link.py"].mode == "120000" and by_path["link.py"].object_type == "blob"
    assert by_path["sub"].object_type == "commit" and by_path["sub"].size is None
    assert by_path["sub"].sha == first


def test_read_blobs_bytes(make_repo, cache_root: Path) -> None:
    """TC-git_repo-14: blob đọc nguyên byte; read_blobs giữ thứ tự, cả SHA lặp."""
    contents = {
        "crlf.py": b"x = 1\r\ny = 2\r\n",
        "lf.py": b"x = 1\ny = 2\n",
        "bom.py": b"\xef\xbb\xbfx = 1\n",
        "bin.dat": b"\x00\x01\x02\xff" * 10,
        "empty.txt": b"",
    }
    src = make_repo()
    sha = src.commit("c", "2026-01-01T10:00:00+07:00", files=contents)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    entries = {e.path: e.sha for e in repo.list_tree(sha)}
    for path, data in contents.items():
        assert repo.read_blob(entries[path]) == data
    order = ["bin.dat", "crlf.py", "bin.dat", "empty.txt", "bom.py", "lf.py"]
    got = list(repo.read_blobs(entries[p] for p in order))
    assert [s for s, _ in got] == [entries[p] for p in order]
    assert [d for _, d in got] == [contents[p] for p in order]


def test_read_blobs_missing(make_repo, cache_root: Path) -> None:
    """TC-git_repo-15: SHA không tồn tại → GitError."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    with pytest.raises(GitError):
        list(repo.read_blobs(["0" * 40]))


def test_token_not_leaked_on_error(monkeypatch: pytest.MonkeyPatch, cache_root: Path,
                                   caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-16: token không có trong argv, exception, log; env có header base64."""
    calls: list[tuple[list[str], dict]] = []
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[1:] == ["--version"]:
            return real_run(cmd, *args, **kwargs)
        calls.append((list(cmd), dict(kwargs.get("env") or {})))
        stderr = (f"fatal: unable to access 'https://{TOKEN}@example.invalid/o/r/': "
                  f"The requested URL returned error: 403 (Authorization: Basic {TOKEN_B64})\n")
        return subprocess.CompletedProcess(cmd, 128, b"", stderr.encode())

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.pager=cat'")
    caplog.set_level(logging.DEBUG, logger="loc_counter")
    with pytest.raises(GitError, match="Không có quyền truy cập") as exc:
        GitRepo.open("https://example.invalid/o/r", token=TOKEN, cache_root=cache_root)
    err = exc.value
    assert calls
    for cmd, env in calls:
        assert all(TOKEN not in part and TOKEN_B64 not in part for part in cmd)
        params = env["GIT_CONFIG_PARAMETERS"]
        assert params.startswith("'core.pager=cat' ")
        assert ("'http.https://example.invalid/.extraheader=Authorization: Basic "
                f"{TOKEN_B64}'") in params
        assert "'credential.helper='" in params
        assert env["GIT_TERMINAL_PROMPT"] == "0"
    for text in (str(err), err.command, err.stderr, caplog.text):
        assert TOKEN not in text and TOKEN_B64 not in text
    leftovers = list(cache_root.iterdir()) if cache_root.exists() else []
    assert leftovers == []


def test_mask_secrets() -> None:
    """TC-git_repo-17: che token và dạng base64 của header."""
    text = f"url https://{TOKEN}@h/x header Basic {TOKEN_B64} end"
    masked = mask_secrets(text, [TOKEN])
    assert TOKEN not in masked and TOKEN_B64 not in masked
    assert masked.count("***") == 2
    assert mask_secrets("abc", ["", None]) == "abc"


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("fatal: Authentication failed for 'https://github.com/o/r/'", "Không có quyền truy cập"),
        ("remote: Repository not found.\nfatal: repository 'x' not found", "Không tìm thấy repo"),
        ("fatal: unable to access 'x': Could not resolve host: github.com",
         "Không kết nối được tới github.com"),
        ("fatal: something odd happened\nmore", "Lệnh git thất bại: fatal: something odd happened"),
    ],
)
def test_error_classification(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                              stderr: str, expected: str) -> None:
    """TC-git_repo-18: phân loại lỗi git thành thông báo tiếng Việt."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    monkeypatch.setattr(
        git_repo.subprocess, "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 128, b"", stderr.encode()),
    )
    with pytest.raises(GitError, match=expected):
        repo.run(["fetch", "origin"])


def test_empty_repo(make_repo, cache_root: Path) -> None:
    """TC-git_repo-19: repo chưa có commit → mở được, không có nhánh."""
    src = make_repo()
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.list_branches() == []
    assert repo.default_branch() is None


def test_token_not_in_cache_config(make_repo, cache_root: Path) -> None:
    """TC-git_repo-20: token không vào config repo cache, repr; kiểm tra config phát hiện rò rỉ."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), token=TOKEN, cache_root=cache_root)
    config_path = repo.git_dir / "config"
    config_text = config_path.read_text(encoding="utf-8")
    assert TOKEN not in config_text and TOKEN_B64 not in config_text
    assert TOKEN not in repr(repo)
    url = repo.run(["config", "--get", "remote.origin.url"]).decode().strip()
    assert url == str(src.path.resolve())

    remote = GitRepo(repo.git_dir, "https://example.invalid/o/r", TOKEN)
    assert TOKEN not in repr(remote)
    remote._check_no_token_in_config()
    config_path.write_text(config_text + f"[x]\n\tleak = {TOKEN}\n", encoding="utf-8")
    with pytest.raises(GitError, match="Lỗi bảo mật") as exc:
        remote._check_no_token_in_config()
    assert TOKEN not in str(exc.value)


def _make_readonly(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, stat.S_IREAD)


def test_broken_cache_readonly_files(make_repo, cache_root: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-21: cache hỏng có file read-only → clone lại; không xóa được → GitError."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    repo.run(["gc", "-q"])
    (repo.git_dir / "HEAD").unlink()
    _make_readonly(repo.git_dir)
    repo2 = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo2.list_branches() == ["feature/x", "main"]
    assert [p.name for p in cache_root.iterdir()] == [repo2.git_dir.name]

    (repo2.git_dir / "HEAD").unlink()
    monkeypatch.setattr(git_repo.shutil, "rmtree", lambda *a, **k: None)
    with pytest.raises(GitError, match="Không xóa được thư mục cache"):
        GitRepo.open(str(src.path), cache_root=cache_root)


def test_hostile_global_config(make_repo, cache_root: Path, tmp_path: Path,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-22: log.showSignature, clone.defaultRemoteName toàn cục không làm sai kết quả."""
    src = make_repo()
    src.commit("base", "2026-01-01T10:00:00+07:00", files={"a.py": "x = 1\n"})
    tree = src.git("rev-parse", "HEAD^{tree}")
    parent = src.head()
    raw = (f"tree {tree}\nparent {parent}\n"
           "author a <a@x> 1767240000 +0700\ncommitter a <a@x> 1767240000 +0700\n"
           "gpgsig -----BEGIN SSH SIGNATURE-----\n U1NIU0lHAAAAAQ==\n"
           " -----END SSH SIGNATURE-----\n\nsigned commit\n")
    signed = src.git("hash-object", "-t", "commit", "-w", "--stdin", stdin=raw.encode())
    src.git("update-ref", "refs/heads/main", signed)

    hostile = tmp_path / "hostile.gitconfig"
    hostile.write_text("[log]\n\tshowSignature = true\n[clone]\n\tdefaultRemoteName = upstream\n",
                       encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    info = repo.commit_info(signed)
    assert info.sha == signed and info.short_sha == signed[:7]
    assert info.subject == "signed commit"
    url = repo.run(["config", "--get", "remote.origin.url"]).decode().strip()
    assert url == str(src.path.resolve())
    assert repo.resolve_branch("main") == signed


def test_token_requires_https(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-23: token với nguồn không phải https → GitError, không chạy lệnh mạng."""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", spy)
    for source in ("http://h.example/o/r", "git@h.example:o/r.git"):
        with pytest.raises(GitError, match="Token chỉ dùng với URL https://"):
            GitRepo.open(source, token=TOKEN, cache_root=cache_root)
    assert all(cmd[1:] == ["--version"] for cmd in calls)


def test_origin_url_mismatch(make_repo, cache_root: Path) -> None:
    """TC-git_repo-24: remote.origin.url của cache khác nguồn → GitError."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    repo.run(["config", "remote.origin.url", str(cache_root / "elsewhere")])
    with pytest.raises(GitError, match="không khớp nguồn"):
        GitRepo.open(str(src.path), cache_root=cache_root)


ALICE = ("alice", "alice@example.com")
BOB = ("bob", "bob@example.com")


def test_log_commits_period(make_repo, cache_root: Path) -> None:
    """TC-git_repo-25: commit trong kỳ (gồm nhánh đã merge), merge, author không phải committer."""
    src = make_repo()
    c0 = src.commit("c0", "2025-12-20T10:00:00+07:00", files={"a.py": "x = 0\n"})
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", author=ALICE,
                    committer=("admin", "admin@example.com"), files={"a.py": "x = 1\n"})
    src.checkout("feat", create=True)
    c2 = src.commit("c2", "2026-01-03T10:00:00+07:00", author=BOB, files={"b.py": "y = 1\n"})
    src.checkout("main")
    m = src.merge("feat", "M", "2026-01-04T10:00:00+07:00", author=("carol", "carol@example.com"))
    c3 = src.commit("c3", "2026-01-05T10:00:00+07:00", author=ALICE, files={"a.py": "x = 3\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    commits = repo.log_commits(c3, c0)
    by_sha = {c.sha: c for c in commits}
    assert set(by_sha) == {c1, c2, m, c3}
    assert by_sha[m].is_merge and len(by_sha[m].parents) == 2
    assert not by_sha[c1].is_merge
    assert (by_sha[c1].author_name, by_sha[c1].author_email) == ALICE
    assert by_sha[c1].author_date == datetime(2026, 1, 2, 10, tzinfo=BKK)
    assert by_sha[c1].author_date.utcoffset() == timedelta(hours=7)
    assert (by_sha[m].author_name, by_sha[c2].author_name) == ("carol", "bob")

    all_commits = repo.log_commits(c3, None)
    assert {c.sha for c in all_commits} == {c0, c1, c2, m, c3}


def test_log_commits_subject_and_body_title(make_repo, cache_root: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-55: log_commits trả subject và body_title (M8, D43)."""
    src = make_repo()
    c1 = src.commit("Thêm login (#12)", "2026-01-02T10:00:00+07:00", files={"a.py": "x = 1\n"})
    c2 = src.commit("Merge pull request #7 from org/feat\n\nFix lỗi đăng nhập\n\nchi tiết",
                    "2026-01-03T10:00:00+07:00", files={"a.py": "x = 2\n"})
    c3 = src.commit("Tiêu đề", "2026-01-04T10:00:00+07:00", files={"a.py": "x = 3\n"})
    c4 = src.commit("Đổi tên ñ → é", "2026-01-05T10:00:00+07:00", files={"a.py": "x = 4\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    by_sha = {c.sha: c for c in repo.log_commits(c4, None)}
    assert (by_sha[c1].subject, by_sha[c1].body_title) == ("Thêm login (#12)", "")
    assert by_sha[c2].subject == "Merge pull request #7 from org/feat"
    assert by_sha[c2].body_title == "Fix lỗi đăng nhập"
    assert (by_sha[c3].subject, by_sha[c3].body_title) == ("Tiêu đề", "")
    assert by_sha[c4].subject == "Đổi tên ñ → é"
    assert by_sha[c1].author_date == datetime(2026, 1, 2, 10, tzinfo=BKK)  # trường cũ không đổi

    bad = f"\x1e{c1}\0\0a\0a@x\0a\0a@x\0{by_sha[c1].author_date.isoformat()}\0chỉ-7-trường"
    monkeypatch.setattr(repo, "run", lambda args, **kwargs: bad.encode())
    with pytest.raises(GitError, match="Không đọc được danh sách commit trong kỳ"):
        repo.log_commits(c4)


def test_log_commits_mailmap(make_repo, cache_root: Path, tmp_path: Path,
                             monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-26: .mailmap lấy tại mailmap_rev; mailmap.file toàn cục bị bỏ qua."""
    noreply = ("alice", "12345+alice@users.noreply.github.com")
    src = make_repo()
    src.commit("base", "2026-01-01T10:00:00+07:00", files={"a.py": "x = 0\n"})
    c1 = src.commit("alice", "2026-01-02T10:00:00+07:00", author=noreply, files={
        ".mailmap": "Alice <alice@corp.com> <12345+alice@users.noreply.github.com>\n",
        "a.py": "x = 1\n"})
    c2 = src.commit("bob", "2026-01-03T10:00:00+07:00", author=BOB, files={"b.py": "y = 1\n"})
    c9 = src.commit("later", "2026-02-01T10:00:00+07:00", files={
        ".mailmap": "Other <other@corp.com> <12345+alice@users.noreply.github.com>\n"})

    global_map = tmp_path / "global.mailmap"
    global_map.write_text("B <x@y> <bob@example.com>\n", encoding="utf-8")
    global_cfg = tmp_path / "global.gitconfig"
    global_cfg.write_text(f"[mailmap]\n\tfile = {global_map.as_posix()}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_cfg))
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    mapped = {c.sha: c for c in repo.log_commits(c2, None, mailmap_rev=c2)}
    assert (mapped[c1].mapped_name, mapped[c1].mapped_email) == ("Alice", "alice@corp.com")
    assert (mapped[c1].author_name, mapped[c1].author_email) == noreply
    assert (mapped[c2].mapped_name, mapped[c2].mapped_email) == BOB

    later = {c.sha: c for c in repo.log_commits(c9, None, mailmap_rev=c9)}
    assert later[c1].mapped_email == "other@corp.com"

    plain = repo.log_commits(c2, None, mailmap_rev=None)
    assert all((c.mapped_name, c.mapped_email) == (c.author_name, c.author_email) for c in plain)


def test_no_askpass(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-27: mọi lệnh git chạy với GIT_ASKPASS/SSH_ASKPASS rỗng, không prompt."""
    src = _two_branch_repo(make_repo)
    envs: list[dict] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        if cmd[1:] != ["--version"]:
            envs.append(dict(kwargs.get("env") or {}))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", spy)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    repo.list_branches()
    assert envs
    for env in envs:
        assert env["GIT_ASKPASS"] == "" and env["SSH_ASKPASS"] == ""
        assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_local_clone_no_hardlinks(make_repo, cache_root: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-28: clone nguồn local dùng --no-hardlinks; nguồn https thì không."""
    src = _two_branch_repo(make_repo)
    clones: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        if "clone" in cmd:
            clones.append(list(cmd))
            if any(part.startswith("https://") for part in cmd):
                return subprocess.CompletedProcess(cmd, 128, b"", b"fatal: odd\n")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", spy)
    GitRepo.open(str(src.path), cache_root=cache_root)
    with pytest.raises(GitError):
        GitRepo.open("https://example.invalid/o/r", cache_root=cache_root)
    assert "--no-hardlinks" in clones[0]
    assert "--no-hardlinks" not in clones[1]


def test_cache_root_not_creatable(make_repo, tmp_path: Path) -> None:
    """TC-git_repo-29: cache_root nằm dưới một file → GitError tiếng Việt."""
    src = _two_branch_repo(make_repo)
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(GitError, match="Không tạo được thư mục cache"):
        GitRepo.open(str(src.path), cache_root=blocker / "cache")


def test_log_output_encoding_override(make_repo, cache_root: Path, tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-30: i18n.logOutputEncoding toàn cục không làm hỏng tên tác giả."""
    src = make_repo()
    sha = src.commit("c", "2026-01-02T10:00:00+07:00", author=("José Bình", "jb@example.com"),
                     files={"a.py": "x = 1\n"})
    cfg = tmp_path / "enc.gitconfig"
    cfg.write_text("[i18n]\n\tlogOutputEncoding = ISO-8859-1\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.commit_info(sha).author_name == "José Bình"
    assert repo.log_commits(sha)[0].author_name == "José Bình"


def test_read_blobs_missing_logged(make_repo, cache_root: Path,
                                   caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-31: blob không tồn tại → GitError rõ ràng và có log WARNING."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    caplog.set_level(logging.WARNING, logger="loc_counter")
    with pytest.raises(GitError, match="Không tìm thấy blob"):
        list(repo.read_blobs(["0" * 40]))
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_bad_timezone_commit(make_repo, cache_root: Path) -> None:
    """TC-git_repo-32: commit có header múi giờ hỏng → GitError tiếng Việt."""
    src = make_repo()
    src.commit("base", "2026-01-01T10:00:00+07:00", files={"a.py": "x = 1\n"})
    tree = src.git("rev-parse", "HEAD^{tree}")
    raw = (f"tree {tree}\nparent {src.head()}\n"
           "author a <a@x> 1767240000 +9959\ncommitter a <a@x> 1767240000 +9959\n\nbad tz\n")
    bad = src.git("hash-object", "-t", "commit", "--literally", "-w", "--stdin",
                  stdin=raw.encode())
    src.git("update-ref", "refs/heads/main", bad)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    with pytest.raises(GitError, match="Không đọc được ngày của commit"):
        repo.commit_info(bad)
    with pytest.raises(GitError, match="Không đọc được ngày của commit"):
        repo.log_commits(bad)


# ---------- M4: diff_tree, diff_hunks, blame, rev_list, paths_exist ----------

def _raw_entry(src, rel: str, data: bytes, mode: str = "100644") -> str:
    """Thêm entry có tên không tạo được trên NTFS (`*`, `:`) thẳng vào index; trả SHA blob."""
    sha = src.hash_blob(data)
    src.git("-c", "core.protectNTFS=false", "update-index", "--add", "--cacheinfo",
            f"{mode},{sha},{rel}")
    return sha


def _spy_git(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Ghi argv của mọi tiến trình con (`subprocess.run` và `Popen`) rồi chạy thật."""
    calls: list[list[str]] = []
    real_run, real_popen = subprocess.run, subprocess.Popen
    inside_run = {"depth": 0}

    def spy_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        inside_run["depth"] += 1
        try:
            return real_run(cmd, *args, **kwargs)
        finally:
            inside_run["depth"] -= 1

    def spy_popen(cmd, *args, **kwargs):
        if not inside_run["depth"]:  # subprocess.run gọi Popen bên trong → không ghi trùng
            calls.append(list(cmd))
        return real_popen(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", spy_run)
    monkeypatch.setattr(git_repo.subprocess, "Popen", spy_popen)
    return calls


def _blame_cmds(calls: list[list[str]]) -> list[list[str]]:
    return [cmd for cmd in calls if "blame" in cmd]


def _l_args(cmd: list[str]) -> list[str]:
    """Các giá trị `-L` trong argv (chấp nhận `-L 2,3` hoặc `-L2,3`)."""
    values = []
    for i, part in enumerate(cmd):
        if part == "-L":
            values.append(cmd[i + 1])
        elif part.startswith("-L") and len(part) > 2:
            values.append(part[2:])
    return values


def _blob_at(src, commit: str, path: str) -> str:
    return src.git("rev-parse", f"{commit}:{path}")


def test_diff_tree_changes(make_repo, cache_root: Path) -> None:
    """TC-git_repo-33: diff_tree nhận diện R / D / A / M, SHA đúng, sắp theo path."""
    src = make_repo()
    old = "".join(f"value_{i} = compute_long_name({i}, {i * 2})\n" for i in range(5))
    c1 = src.commit("c1", "2026-01-01T10:00:00+07:00", files={
        "old.py": old, "gone.py": "removed_file = True\nprint('bye')\n", "keep.py": "keep = 1\n"})
    src.git("mv", "old.py", "new.py")
    new = old.replace("value_2 = compute_long_name(2, 4)", "value_2 = 222")
    c2 = src.commit("c2", "2026-01-02T10:00:00+07:00", author=ALICE, files={
        "new.py": new, "tệp mới.py": "fresh = 'mới'\n", "keep.py": "keep = 2\n"},
        remove=("gone.py",))
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    diff = repo.diff_tree(c1, c2)
    assert isinstance(diff, TreeDiff)
    assert diff.rename_limit_hit is False
    entries = list(diff.entries)
    assert all(isinstance(e, DiffEntry) for e in entries)
    assert [(e.status, e.old_path, e.new_path) for e in entries] == [
        ("D", "gone.py", None),
        ("M", "keep.py", "keep.py"),
        ("R", "old.py", "new.py"),
        ("A", None, "tệp mới.py"),
    ]
    assert [e.path for e in entries] == ["gone.py", "keep.py", "new.py", "tệp mới.py"]
    by_path = {e.path: e for e in entries}

    renamed = by_path["new.py"]
    assert isinstance(renamed.similarity, int) and 1 <= renamed.similarity <= 100
    assert (renamed.old_mode, renamed.new_mode) == ("100644", "100644")
    assert renamed.old_sha == _blob_at(src, c1, "old.py")
    assert renamed.new_sha == _blob_at(src, c2, "new.py")

    gone = by_path["gone.py"]
    assert (gone.new_path, gone.new_mode, gone.new_sha, gone.similarity) == (None, None, None, None)
    assert (gone.old_mode, gone.old_sha) == ("100644", _blob_at(src, c1, "gone.py"))

    added = by_path["tệp mới.py"]
    assert (added.old_path, added.old_mode, added.old_sha, added.similarity) == (
        None, None, None, None)
    assert (added.new_mode, added.new_sha) == ("100644", _blob_at(src, c2, "tệp mới.py"))

    modified = by_path["keep.py"]
    assert modified.similarity is None
    assert modified.old_sha == _blob_at(src, c1, "keep.py")
    assert modified.new_sha == _blob_at(src, c2, "keep.py")
    for e in entries:
        for sha in (e.old_sha, e.new_sha):
            assert sha is None or re.fullmatch(r"[0-9a-f]{40}", sha)


def test_diff_tree_empty_start(make_repo, cache_root: Path,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-34: c_start None → mọi entry là "A", trùng list_tree, không chạy diff."""
    src = make_repo()
    src.write("src/a.py", "x = 1\n")
    src.write("run.sh", "#!/bin/sh\necho hi\n", executable=True)
    src.add_index_entry("120000", src.hash_blob(b"src/a.py"), "link.py")
    first = src.commit("first", "2026-01-01T10:00:00+07:00")
    src.add_index_entry("160000", first, "sub")
    c = src.commit("second", "2026-01-02T10:00:00+07:00")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    tree = repo.list_tree(c)

    calls = _spy_git(monkeypatch)
    diff = repo.diff_tree(None, c)
    assert diff.rename_limit_hit is False
    assert [(e.status, e.old_path, e.new_path, e.old_mode, e.new_mode, e.old_sha, e.new_sha,
             e.similarity) for e in diff.entries] == [
        ("A", None, t.path, None, t.mode, None, t.sha, None) for t in tree]
    assert {e.new_mode for e in diff.entries} == {"100644", "100755", "120000", "160000"}
    assert not any("diff-tree" in cmd or "diff" in cmd for cmd in calls)


def test_diff_tree_argv_and_rename_limit(make_repo, cache_root: Path,
                                         monkeypatch: pytest.MonkeyPatch,
                                         caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-35: argv có -M -l0 -z --no-abbrev; stderr rename limit → cờ + WARNING."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    c_start, c_end = src.git("rev-parse", "main"), src.git("rev-parse", "feature/x")
    calls: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if "diff-tree" in cmd:
            calls.append(list(cmd))
            return subprocess.CompletedProcess(
                cmd, 0, b"",
                b"warning: exhaustive rename detection was skipped due to too many files.\n")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    caplog.set_level(logging.WARNING, logger="loc_counter")
    diff = repo.diff_tree(c_start, c_end)
    assert diff.rename_limit_hit is True
    assert list(diff.entries) == []
    assert len(calls) == 1
    cmd = calls[0]
    for option in ("-r", "-z", "--raw", "--no-abbrev", "-M", "-l0"):
        assert option in cmd, option
    assert cmd.index(c_start) < cmd.index(c_end)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_diff_hunks_zero_based(make_repo, cache_root: Path) -> None:
    """TC-git_repo-36: hunk -U0 đổi sang chỉ số 0-based nửa mở; cùng SHA → []."""
    base = b"a\nb\nc\nd\ne\n"
    files = {
        "base.txt": base,
        "ins_first.txt": b"x\na\nb\nc\nd\ne\n",
        "del_last.txt": b"a\nb\nc\nd\n",
        "mod_2.txt": b"a\nB\nc\nd\ne\n",
        "add_noeol.txt": b"a\nb\nc\nd\ne\nf",
        "base_noeol.txt": b"a\nb\nc\nd\ne",
        "crlf.txt": b"a\nb\r\nc\nd\ne\n",
    }
    src = make_repo()
    c = src.commit("blobs", "2026-01-01T10:00:00+07:00", files=files)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    sha = {name: _blob_at(src, c, name) for name in files}

    cases = [
        ("base.txt", "ins_first.txt", [Hunk(0, 0, 0, 1)]),
        ("base.txt", "del_last.txt", [Hunk(4, 1, 4, 0)]),
        ("base.txt", "mod_2.txt", [Hunk(1, 1, 1, 1)]),
        ("base.txt", "add_noeol.txt", [Hunk(5, 0, 5, 1)]),
        ("base_noeol.txt", "add_noeol.txt", [Hunk(4, 1, 4, 2)]),
        ("crlf.txt", "base.txt", [Hunk(1, 1, 1, 1)]),
        ("base.txt", "base.txt", []),
    ]
    for old, new, expected in cases:
        assert repo.diff_hunks(sha[old], sha[new]) == expected, (old, new)
    hunk = repo.diff_hunks(sha["base.txt"], sha["mod_2.txt"])[0]
    assert (hunk.old_start, hunk.old_count, hunk.new_start, hunk.new_count) == (1, 1, 1, 1)


HUNK_FILES = {
    # Myers và patience cho hunk khác nhau; hai hunk cuối cách nhau 1 dòng.
    "old.txt": b"b\nc\n}\nc\na\n{\n}\na\n",
    "new.txt": b"{\nb\nc\n}\nc\na\n}\n",
    "nul_old.dat": b"a\x00b\nc\nd\n",
    "nul_new.dat": b"a\x00b\nC\nd\nE\n",
}
HUNK_PAIRS = [("old.txt", "new.txt"), ("nul_old.dat", "nul_new.dat")]
HUNK_CLEAN = [
    [Hunk(0, 0, 0, 1), Hunk(5, 1, 6, 0), Hunk(7, 1, 7, 0)],
    [Hunk(1, 1, 1, 1), Hunk(3, 0, 3, 1)],
]


def _hunk_repo(make_repo, cache_root: Path) -> tuple[GitRepo, list[tuple[str, str]]]:
    """Repo chứa các blob của HUNK_FILES; trả repo và cặp SHA theo HUNK_PAIRS."""
    src = make_repo()
    c = src.commit("blobs", "2026-01-01T10:00:00+07:00", files=HUNK_FILES)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    sha = {name: _blob_at(src, c, name) for name in HUNK_FILES}
    return repo, [(sha[a], sha[b]) for a, b in HUNK_PAIRS]


def test_diff_hunks_ignores_global_config(make_repo, cache_root: Path, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-37: cấu hình diff toàn cục không đổi kết quả; blob có NUL vẫn ra hunk."""
    repo, pairs = _hunk_repo(make_repo, cache_root)
    clean = [repo.diff_hunks(a, b) for a, b in pairs]
    assert clean == HUNK_CLEAN

    hostile = tmp_path / "hostile-diff.gitconfig"
    hostile.write_text(
        "[diff]\n\talgorithm = patience\n\tcontext = 10\n\tinterHunkContext = 5\n"
        "\tindentHeuristic = false\n\texternal = không-tồn-tại\n\tnoprefix = true\n"
        "[color]\n\tdiff = always\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    assert [repo.diff_hunks(a, b) for a, b in pairs] == clean


def test_diff_hunks_ignores_diff_env(make_repo, cache_root: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-37: GIT_DIFF_OPTS / GIT_EXTERNAL_DIFF không đổi hunk, không truyền cho git."""
    repo, pairs = _hunk_repo(make_repo, cache_root)
    clean = [repo.diff_hunks(a, b) for a, b in pairs]
    assert clean == HUNK_CLEAN

    monkeypatch.setenv("GIT_DIFF_OPTS", "--unified=5")
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", "không-tồn-tại")
    envs: list[dict] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        envs.append(dict(kwargs.get("env") or os.environ))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", spy)
    assert [repo.diff_hunks(a, b) for a, b in pairs] == clean
    assert len(envs) == len(pairs)
    for env in envs:
        assert "GIT_DIFF_OPTS" not in env
        assert "GIT_EXTERNAL_DIFF" not in env


def test_blame_forward_period(make_repo, cache_root: Path) -> None:
    """TC-git_repo-38: blame since..end — dòng cũ boundary, dòng mới thuộc c1, line 0-based."""
    src = make_repo()
    c0 = src.commit("c0", "2025-12-20T10:00:00+07:00",
                    files={"app.py": "line_a = 1\nline_b = 2\nline_c = 3\n"})
    c1 = src.commit("c1", "2026-01-05T10:00:00+07:00", author=ALICE, files={
        "app.py": "line_a = 1\nline_b = 2\nnew_x = 10\nnew_y = 20\nline_c = 3\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    lines = repo.blame(c1, "app.py", c0)
    assert all(isinstance(bl, BlameLine) for bl in lines)
    assert [bl.line for bl in lines] == [0, 1, 2, 3, 4]
    assert [(bl.sha, bl.boundary, bl.orig_line) for bl in lines] == [
        (c0, True, 0), (c0, True, 1), (c1, False, 2), (c1, False, 3), (c0, True, 2)]
    assert {bl.filename for bl in lines} == {"app.py"}


def test_blame_root_not_boundary(make_repo, cache_root: Path) -> None:
    """TC-git_repo-39: --root — commit gốc (cả gốc thứ hai merge unrelated) không bị boundary."""
    src = make_repo()
    root = src.commit("root", "2026-01-01T10:00:00+07:00", files={"app.py": "r1 = 1\nr2 = 2\n"})
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", author=ALICE,
                    files={"app.py": "r1 = 1\nr2 = 2\nc1 = 3\n"})

    src.git("checkout", "-q", "--orphan", "other")
    src.git("rm", "-rq", "--cached", ".")
    (src.path / "app.py").unlink()
    root2 = src.commit("root2", "2026-01-03T10:00:00+07:00", author=BOB,
                       files={"b.py": "y = 1\ny = 2\n"})
    src.checkout("main")
    src.git("merge", "-q", "--no-ff", "--allow-unrelated-histories", "-m", "M", "other",
            date="2026-01-04T10:00:00+07:00")
    merge = src.head()
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    # (a) since None: không dòng nào boundary; dòng của commit gốc có sha = commit gốc
    lines = repo.blame(c1, "app.py", None)
    assert [(bl.sha, bl.boundary) for bl in lines] == [(root, False), (root, False), (c1, False)]

    # (b) kỳ c1..merge chứa commit gốc thứ hai (unrelated): dòng của nó không boundary
    other = repo.blame(merge, "b.py", c1)
    assert [(bl.sha, bl.boundary) for bl in other] == [(root2, False), (root2, False)]
    main_lines = repo.blame(merge, "app.py", c1)
    assert [bl.boundary for bl in main_lines] == [True, True, True]


def test_blame_reverse_rename(make_repo, cache_root: Path) -> None:
    """TC-git_repo-40: reverse blame theo rename; dòng mất ngay sau since → boundary (L = since)."""
    src = make_repo()
    c0 = src.commit("c0", "2025-12-20T10:00:00+07:00", files={
        "old.py": "line zero = 0\nline one = 1\nline two = 2\nline three = 3\n"})
    src.commit("c1", "2026-01-02T10:00:00+07:00", author=ALICE, files={
        "old.py": "line zero = 0\nline two = 2\nline three = 3\n"})
    src.git("mv", "old.py", "new.py")
    c2 = src.commit("c2", "2026-01-03T10:00:00+07:00", author=BOB)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    lines = repo.blame(c2, "old.py", c0, reverse=True)
    assert [bl.line for bl in lines] == [0, 1, 2, 3]
    by_line = {bl.line: bl for bl in lines}
    for i, orig in ((0, 0), (2, 1), (3, 2)):
        assert (by_line[i].sha, by_line[i].boundary, by_line[i].filename) == (c2, False, "new.py")
        assert by_line[i].orig_line == orig
    assert (by_line[1].sha, by_line[1].boundary, by_line[1].filename) == (c0, True, "old.py")
    assert by_line[1].orig_line == 1

    with pytest.raises(ValueError):
        repo.blame(c2, "old.py", None, reverse=True)


def test_blame_line_ranges_batches(make_repo, cache_root: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-41: line_ranges gộp + chia lô cho cùng kết quả; detect_moves/reverse bỏ -M -C."""
    base = [f"line_{i} = {i}" for i in range(10)]
    changed = list(base)
    changed[2] = "line_2 = 'two'"
    changed[8] = "line_8 = 'eight'"
    src = make_repo()
    c0 = src.commit("c0", "2025-12-20T10:00:00+07:00", files={"f.py": "\n".join(base) + "\n"})
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", author=ALICE,
                    files={"f.py": "\n".join(changed) + "\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    full = repo.blame(c1, "f.py", c0)
    assert [bl.line for bl in full] == list(range(10))
    expected = [bl for bl in full if bl.line in (1, 2, 7, 8)]
    ranges = [(7, 9), (1, 2), (2, 3)]

    calls = _spy_git(monkeypatch)
    single = repo.blame(c1, "f.py", c0, line_ranges=ranges)
    assert [bl.line for bl in single] == [1, 2, 7, 8]
    assert single == expected
    cmds = _blame_cmds(calls)
    assert len(cmds) == 1
    assert _l_args(cmds[0]) == ["2,3", "8,9"]
    assert "-M" in cmds[0] and "-C" in cmds[0] and "-w" in cmds[0]

    calls.clear()
    monkeypatch.setattr(git_repo, "_BLAME_MAX_RANGES", 1)
    batched = repo.blame(c1, "f.py", c0, line_ranges=ranges)
    assert batched == expected
    cmds = _blame_cmds(calls)
    assert len(cmds) == 2
    assert [_l_args(cmd) for cmd in cmds] == [["2,3"], ["8,9"]]

    calls.clear()
    no_moves = repo.blame(c1, "f.py", c0, detect_moves=False, line_ranges=ranges)
    assert [bl.line for bl in no_moves] == [1, 2, 7, 8]
    cmds = _blame_cmds(calls)
    assert cmds and all("-M" not in cmd and "-C" not in cmd for cmd in cmds)

    calls.clear()
    reverse = repo.blame(c1, "f.py", c0, reverse=True, line_ranges=ranges)
    assert [(bl.line, bl.sha, bl.boundary) for bl in reverse] == [
        (1, c1, False), (2, c0, True), (7, c1, False), (8, c0, True)]
    cmds = _blame_cmds(calls)
    assert cmds and all("--reverse" in cmd for cmd in cmds)
    assert all("-M" not in cmd and "-C" not in cmd for cmd in cmds)

    calls.clear()
    monkeypatch.setattr(git_repo, "_BLAME_MAX_RANGES", 200)
    only3 = repo.blame(c1, "f.py", c0, line_ranges=[(5, 5), (3, 4)])
    assert [bl.line for bl in only3] == [3]
    assert [_l_args(cmd) for cmd in _blame_cmds(calls)] == [["4,4"]]


BLOCK_MOVED = [
    "moved_alpha = compute_something_long(alpha_value, beta_value, 1)",
    "moved_bravo = compute_something_long(gamma_value, delta_value, 2)",
    "moved_charl = compute_something_long(epsil_value, zetaa_value, 3)",
]
BLOCK_OTHER = [
    "other_delta = transform_another_block(first_param, second_param, 4)",
    "other_echoo = transform_another_block(third_param, fourth_param, 5)",
    "other_foxtr = transform_another_block(fifth_param, sixth_paramx, 6)",
]
KEEP_LINES = ["keep_1 = 1", "keep_2 = 2", "keep_3 = 3", "keep_4 = 4"]


def _lines(*blocks: list[str]) -> str:
    return "".join(line + "\n" for block in blocks for line in block)


def test_blame_moved_lines(make_repo, cache_root: Path) -> None:
    """TC-git_repo-42: dòng dời (trong file / sang file khác) → -M -C cho boundary; tắt → c1/c2."""
    src = make_repo()
    c0 = src.commit("c0", "2025-12-20T10:00:00+07:00",
                    files={"a.py": _lines(BLOCK_MOVED, KEEP_LINES, BLOCK_OTHER)})
    c1 = src.commit("c1 dời khối", "2026-01-02T10:00:00+07:00", author=ALICE,
                    files={"a.py": _lines(KEEP_LINES, BLOCK_OTHER, BLOCK_MOVED)})
    c2 = src.commit("c2 chuyển khối", "2026-01-03T10:00:00+07:00", author=ALICE,
                    files={"a.py": _lines(KEEP_LINES, BLOCK_MOVED), "b.py": _lines(BLOCK_OTHER)})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    a_moves = repo.blame(c2, "a.py", c0)
    assert [bl.line for bl in a_moves] == list(range(7))
    assert all(bl.boundary and bl.sha == c0 for bl in a_moves)
    assert [bl.orig_line for bl in a_moves[4:]] == [0, 1, 2]
    a_plain = repo.blame(c2, "a.py", c0, detect_moves=False)
    assert [(bl.sha, bl.boundary) for bl in a_plain[4:]] == [(c1, False)] * 3
    assert all(bl.boundary for bl in a_plain[:4])

    b_moves = repo.blame(c2, "b.py", c0)
    assert [(bl.sha, bl.boundary, bl.filename) for bl in b_moves] == [(c0, True, "a.py")] * 3
    b_plain = repo.blame(c2, "b.py", c0, detect_moves=False)
    assert [(bl.sha, bl.boundary, bl.filename) for bl in b_plain] == [(c2, False, "b.py")] * 3


def test_blame_ignores_global_config(make_repo, cache_root: Path, tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-43: blame.* / diff.* / color.ui toàn cục không làm lỗi hay đổi kết quả blame."""
    src = make_repo()
    c0 = src.commit("c0", "2025-12-20T10:00:00+07:00",
                    files={"f.py": "b\nc\n}\nc\na\n{\n}\na\n"})
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", author=ALICE,
                    files={"f.py": "{\nb\nc\n}\nc\na\n}\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    def run_all() -> list[list[BlameLine]]:
        return [
            repo.blame(c1, "f.py", c0),
            repo.blame(c1, "f.py"),
            repo.blame(c1, "f.py", c0, detect_moves=False),
            repo.blame(c1, "f.py", c0, reverse=True),
        ]

    clean = run_all()
    # Myers: chỉ dòng "{" đầu là mới; phần còn lại có từ c0 (patience cho kết quả khác)
    assert [(bl.sha, bl.boundary) for bl in clean[0]] == [(c1, False)] + [(c0, True)] * 6
    assert not any(bl.boundary for bl in clean[1])

    hostile = tmp_path / "hostile-blame.gitconfig"
    hostile.write_text(
        "[blame]\n\tignoreRevsFile = .nope\n\tshowRoot = false\n\tmarkUnblamableLines = true\n"
        "\tcoloring = highlightRecent\n[diff]\n\talgorithm = patience\n"
        "\tindentHeuristic = false\n[color]\n\tui = always\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    assert run_all() == clean


SHA_A, SHA_B = "1" * 40, "2" * 40


def _porcelain(*records: tuple[str, list[str]]) -> bytes:
    """Ghép output `--line-porcelain` giả: (header, các dòng khóa); nội dung = TAB + code."""
    out: list[str] = []
    for i, (header, keys) in enumerate(records):
        out += [header, *keys, f"\tcode {i}"]
    return ("\n".join(out) + "\n").encode("utf-8")


def _fake_blame(monkeypatch: pytest.MonkeyPatch, stdout: bytes) -> None:
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if "blame" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout, b"")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)


def test_blame_porcelain_parsing(make_repo, cache_root: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-44: header 4/3 trường, bỏ C-quote filename, giữ Unicode, sắp theo line."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    stdout = _porcelain(
        (f"{SHA_A} 3 1 2", ["author x", "author-mail <x@y>", "summary s", 'filename "q\\"t.py"']),
        (f"{SHA_A} 4 2", ["author x", "boundary", 'filename "a\\tb.py"']),
        (f"{SHA_B} 2 4 1", ["author y", "filename thư mục/tệp.py"]),
        (f"{SHA_B} 1 3 1", ["author y", 'filename "\\303\\251.py"']),
    )
    _fake_blame(monkeypatch, stdout)
    lines = repo.blame("a" * 40, "x.py")
    assert lines == [
        BlameLine(line=0, sha=SHA_A, orig_line=2, filename='q"t.py', boundary=False),
        BlameLine(line=1, sha=SHA_A, orig_line=3, filename="a\tb.py", boundary=True),
        BlameLine(line=2, sha=SHA_B, orig_line=0, filename="é.py", boundary=False),
        BlameLine(line=3, sha=SHA_B, orig_line=1, filename="thư mục/tệp.py", boundary=False),
    ]


@pytest.mark.parametrize(
    "stdout",
    [
        _porcelain((f"{SHA_A} 1 1 1", ["author x", "summary s"])),  # thiếu filename
        b"\tcode without header\n",  # nội dung không có header trước
        _porcelain((f"{SHA_A} 1 1 1", ["filename a.py"])) + b"\tsecond content\n",
        f"{SHA_A} 1 1 1\nauthor x\nfilename a.py\n".encode(),  # hết output giữa bản ghi
        _porcelain((f"{SHA_A} 1 1 2", ["filename a.py"]))
        + f"{SHA_A} 2 2\nfilename a.py\n".encode(),  # bản ghi cuối không có dòng nội dung
    ],
    ids=["missing-filename", "content-first", "content-twice", "truncated-only",
         "truncated-last"],
)
def test_blame_porcelain_malformed(make_repo, cache_root: Path,
                                   monkeypatch: pytest.MonkeyPatch, stdout: bytes) -> None:
    """TC-git_repo-44: porcelain thiếu filename / sai thứ tự / thiếu nội dung → GitError."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    _fake_blame(monkeypatch, stdout)
    with pytest.raises(GitError, match="Không đọc được kết quả git blame của x.py"):
        repo.blame("a" * 40, "x.py")


def test_blame_only_empty_ranges(make_repo, cache_root: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-44: line_ranges chỉ gồm khoảng rỗng → [], không chạy git."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    sha = src.head()
    calls = _spy_git(monkeypatch)
    assert repo.blame(sha, "a.py", line_ranges=[(3, 3)]) == []
    assert repo.blame(sha, "a.py", line_ranges=[(0, 0), (2, 2)]) == []
    assert calls == []


def test_rev_list_and_first_commit_after(make_repo, cache_root: Path) -> None:
    """TC-git_repo-45: rev_list theo path, topo, reverse; first_commit_after = commit cũ nhất."""
    src = make_repo()
    c0 = src.commit("c0", "2026-01-01T10:00:00+07:00", files={"x.py": "x = 0\n"})
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", files={"x.py": "x = 1\n"})
    src.checkout("feat", create=True)
    f1 = src.commit("f1", "2026-01-02T12:00:00+07:00", author=BOB, files={"x.py": "x = f\n"})
    src.checkout("main")
    c2 = src.commit("c2", "2026-01-03T10:00:00+07:00", files={"y.py": "y = 2\n"})
    c3 = src.commit("c3", "2026-01-04T10:00:00+07:00", files={"x.py": "x = 3\n"})
    c4 = src.commit("c4", "2026-01-05T10:00:00+07:00", files={"z.py": "z = 4\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    assert repo.rev_list(c4, c0, ["x.py"]) == [c3, c1]
    assert repo.rev_list(c4, c0, ["x.py"], reverse=True) == [c1, c3]
    assert repo.rev_list(c4, c0, ["x.py"], ancestry_path=True) == [c3, c1]
    assert repo.rev_list(c4, c0) == [c4, c3, c2, c1]
    assert repo.rev_list(c4, None, ["x.py"]) == [c3, c1, c0]
    assert repo.first_commit_after(c0, c4, ["x.py"]) == c1
    assert repo.first_commit_after(c3, c4, ["x.py"]) is None
    for result in (repo.rev_list(c4, c0, ["x.py"], ancestry_path=True, reverse=True),
                   repo.rev_list(c4, None, ["x.py"])):
        assert f1 not in result
    # f1 không phải tổ tiên của c4 → không commit nào nằm trên đường f1..c4
    assert repo.rev_list(c4, f1, ["x.py"]) == [c3]  # không ancestry_path: chỉ loại tổ tiên f1
    assert repo.rev_list(c4, f1, ["x.py"], ancestry_path=True) == []
    assert repo.first_commit_after(f1, c4, ["x.py"]) is None


def test_rev_list_literal_pathspec(make_repo, cache_root: Path) -> None:
    """TC-git_repo-46: tên `*.py`, `:(glob)x.py` là đường dẫn literal, không phải pattern."""
    src = make_repo()
    _raw_entry(src, "*.py", b"star = 0\n")
    _raw_entry(src, ":(glob)x.py", b"glob = 0\n")
    k0 = src.commit("k0", "2026-01-01T10:00:00+07:00", files={"a.py": "a = 0\n", "x.py": "x = 0\n"})
    _raw_entry(src, "*.py", b"star = 1\n")
    k1 = src.commit("k1 sửa *.py", "2026-01-02T10:00:00+07:00")
    k2 = src.commit("k2 sửa a.py", "2026-01-03T10:00:00+07:00", files={"a.py": "a = 1\n"})
    _raw_entry(src, ":(glob)x.py", b"glob = 1\n")
    k3 = src.commit("k3 sửa :(glob)x.py", "2026-01-04T10:00:00+07:00")
    k4 = src.commit("k4 sửa x.py", "2026-01-05T10:00:00+07:00", files={"x.py": "x = 1\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    assert repo.rev_list(k4, k0, ["*.py"]) == [k1]
    assert repo.rev_list(k4, k0, [":(glob)x.py"]) == [k3]
    assert repo.rev_list(k4, None, ["*.py"]) == [k1, k0]
    assert repo.first_commit_after(k0, k4, ["*.py"]) == k1
    assert repo.first_commit_after(k0, k4, [":(glob)x.py"]) == k3
    assert repo.rev_list(k4, k0, ["a.py"]) == [k2]


def test_paths_exist(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-47: path có trong cây, giữ thứ tự, tên Unicode có `:`; `[]` không chạy git."""
    src = make_repo()
    c0 = src.commit("c0", "2026-01-01T10:00:00+07:00", files={"a.py": "a = 0\n"})
    _raw_entry(src, "thư mục/tệp: x.py", b"t = 1\n")
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", files={"new.py": "n = 1\n"})
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    assert repo.paths_exist([(c1, "a.py"), (c0, "new.py"), (c1, "thư mục/tệp: x.py")]) == [
        True, False, True]
    assert repo.paths_exist([(c0, "thư mục/tệp: x.py"), (c1, "new.py"), (c0, "a.py"),
                             (c1, "nope.py")]) == [False, True, True, False]

    calls = _spy_git(monkeypatch)
    assert repo.paths_exist([]) == []
    assert calls == []


MISSING_COMMIT = "1234567890" * 4  # gitlink trỏ tới commit không có trong repo


def _mktree_commit(src, entries: list[tuple[str, str, str, str]], parent: str, message: str,
                   date: str) -> str:
    """Commit có cây dựng bằng `mktree -z` (tên chứa \\n, \\r…); cập nhật main, trả SHA."""
    raw = "".join(f"{mode} {kind} {sha}\t{name}\0" for mode, kind, sha, name in entries)
    tree = src.git("mktree", "-z", "--missing", stdin=raw.encode())
    commit = src.git("commit-tree", tree, "-p", parent, "-m", message, date=date)
    src.git("update-ref", "refs/heads/main", commit)
    return commit


def test_paths_exist_newline_cr_path(make_repo, cache_root: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-47: path chứa LF / kết thúc CR không qua batch mà tra `rev-parse --verify`."""
    src = make_repo()
    base = src.commit("c0", "2026-01-01T10:00:00+07:00", files={"a.py": "a = 0\n"})
    blob = src.hash_blob(b"x = 1\n")
    c_nl = _mktree_commit(src, [("100644", "blob", blob, "a.py"),
                                ("100644", "blob", blob, "line\nbreak.py"),
                                ("100644", "blob", blob, "cr.py\r")],
                          base, "newline / CR path", "2026-01-02T10:00:00+07:00")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    inputs: list[tuple[list[str], bytes | None]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        inputs.append((list(cmd), kwargs.get("input")))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", spy)
    special = [(c_nl, "line\nbreak.py"), (c_nl, "nope\nx.py"), (base, "line\nbreak.py"),
               (c_nl, "cr.py\r"), (base, "cr.py\r"), (c_nl, "cr.py")]
    result = repo.paths_exist([(c_nl, "a.py"), *special[:3], (c_nl, "b.py"), *special[3:]])
    assert result == [True, True, False, False, False, True, False, False]

    verify = [cmd for cmd, _ in inputs if "rev-parse" in cmd and "--verify" in cmd
              and "--quiet" in cmd]
    expected = [f"{c}:{p}" for c, p in special if "\n" in p or "\r" in p]
    assert sorted(cmd[-1] for cmd in verify) == sorted(expected)
    assert not any("cat-file" in cmd and "-e" in cmd for cmd, _ in inputs)
    batch_stdin = b"".join(data or b"" for cmd, data in inputs if "--batch-check" in cmd)
    assert b"break.py" not in batch_stdin and b"\r" not in batch_stdin
    assert f"{c_nl}:cr.py\n".encode() in batch_stdin


def test_paths_exist_gitlinks(make_repo, cache_root: Path) -> None:
    """TC-git_repo-47: gitlink (commit có / không có trong repo) tính là tồn tại, cùng lô file."""
    src = make_repo()
    c0 = src.commit("c0", "2026-01-01T10:00:00+07:00", files={"a.py": "a = 0\n"})
    blob = src.hash_blob(b"a = 0\n")
    c1 = _mktree_commit(src, [("100644", "blob", blob, "a.py"),
                              ("160000", "commit", c0, "sub_in"),
                              ("160000", "commit", MISSING_COMMIT, "sub_missing"),
                              ("160000", "commit", MISSING_COMMIT, "sub\nnl")],
                        c0, "gitlinks", "2026-01-02T10:00:00+07:00")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    assert repo.paths_exist([(c1, "a.py"), (c1, "sub_missing"), (c1, "nope.py"),
                             (c1, "sub_in"), (c1, "sub\nnl"), (c0, "sub_in"),
                             (c0, "a.py")]) == [True, True, False, True, True, False, True]


@pytest.mark.parametrize(
    "lines",
    [
        ["{blob} blob 6"],  # thiếu dòng cho mục thứ hai
        ["{blob} blob 6", "kết quả lạ"],
        ["{blob} blob 6", "{commit}:b.py ambiguous"],
        ["{blob} blob 6", "{blob} blob 6", "{blob} blob 6"],  # thừa dòng
    ],
    ids=["missing-line", "garbage", "ambiguous", "extra-line"],
)
def test_paths_exist_bad_batch_output(make_repo, cache_root: Path,
                                      monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
    """TC-git_repo-47: `--batch-check` trả thiếu dòng / dòng lạ → GitError tiếng Việt."""
    src = make_repo()
    commit = src.commit("c0", "2026-01-01T10:00:00+07:00",
                        files={"a.py": "a = 0\n", "b.py": "b = 0\n"})
    blob = _blob_at(src, commit, "a.py")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    stdout = "".join(line.format(blob=blob, commit=commit) + "\n" for line in lines).encode()
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if "--batch-check" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout, b"")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    with pytest.raises(GitError, match=re.escape("Không đọc được kết quả kiểm tra đường dẫn.")):
        repo.paths_exist([(commit, "a.py"), (commit, "b.py")])


@pytest.mark.parametrize(
    "call",
    [
        lambda repo, sha: repo.blame("--output=x", "a.py"),
        lambda repo, sha: repo.blame(sha, "a.py", "HEAD~1"),
        lambda repo, sha: repo.diff_hunks("HEAD", sha),
        lambda repo, sha: repo.diff_hunks(sha, sha.upper()),
        lambda repo, sha: repo.rev_list("main"),
        lambda repo, sha: repo.rev_list(sha, "-p"),
        lambda repo, sha: repo.first_commit_after("main", sha, ["a.py"]),
        lambda repo, sha: repo.diff_tree("--output=x", sha),
        lambda repo, sha: repo.diff_tree(None, "main"),
        lambda repo, sha: repo.paths_exist([("-p", "a")]),
    ],
    ids=["blame-end", "blame-since", "hunks-old", "hunks-upper", "rev_list-include",
         "rev_list-exclude", "first_commit_after", "diff_tree-start", "diff_tree-end",
         "paths_exist"],
)
def test_m4_invalid_sha(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                        call) -> None:
    """TC-git_repo-48: tham số commit/blob không phải 40 hex → ValueError, không chạy git."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    sha = src.head()
    calls = _spy_git(monkeypatch)
    with pytest.raises(ValueError):
        call(repo, sha)
    assert calls == []


def test_m4_git_errors(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                       caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-49: blame path không có → GitError `Lệnh git thất bại` + WARNING lệnh."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    c1 = src.head()
    caplog.set_level(logging.WARNING, logger="loc_counter")
    with pytest.raises(GitError, match="^Lệnh git thất bại: "):
        repo.blame(c1, "khong-co.py")
    assert any(r.levelno == logging.WARNING and "blame" in r.getMessage()
               for r in caplog.records)


@pytest.mark.parametrize(
    "raw",
    [
        f":100644 100644 {SHA_A} {SHA_B} X\0a.py\0",  # trạng thái lạ
        f":100644 100644 {SHA_A} {SHA_B}\0a.py\0",  # meta thiếu trường status
        f":100644 {SHA_A} {SHA_B} M\0a.py\0",  # meta thiếu new_mode
        f":100644 100644 {SHA_A} {SHA_B} R090\0old.py\0",  # R thiếu đường dẫn mới
    ],
    ids=["status-X", "meta-no-status", "meta-short", "rename-one-path"],
)
def test_diff_tree_malformed(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                             raw: str) -> None:
    """TC-git_repo-49: diff-tree trả bản ghi sai định dạng → GitError tiếng Việt."""
    src = _two_branch_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    c_start, c_end = src.git("rev-parse", "main"), src.git("rev-parse", "feature/x")
    real_run = subprocess.run
    bad = raw.encode()

    def fake_run(cmd, *args, **kwargs):
        if "diff-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, bad, b"")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    with pytest.raises(GitError, match=re.escape("Không đọc được kết quả so sánh cây file.")):
        repo.diff_tree(c_start, c_end)


class _ShortReadProcess:
    """Tiến trình `cat-file --batch` giả: header báo 10 byte nhưng stdout chỉ còn 4 byte rồi EOF."""

    def __init__(self, sha: str) -> None:
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(f"{sha} blob 10\n".encode() + b"abcd")
        self.stderr = io.BytesIO(b"")
        self.returncode: int | None = None
        self.killed = False
        self.waited = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def terminate(self) -> None:
        self.kill()

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode


def test_read_blobs_short_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-50: cat-file trả thiếu byte → GitError, WARNING, tiến trình bị dừng."""
    sha = "ab" * 20
    procs: list[_ShortReadProcess] = []

    def fake_popen(cmd, *args, **kwargs):
        assert "cat-file" in cmd and "--batch" in cmd
        proc = _ShortReadProcess(sha)
        procs.append(proc)
        return proc

    monkeypatch.setattr(git_repo.subprocess, "Popen", fake_popen)
    caplog.set_level(logging.WARNING, logger="loc_counter")
    repo = GitRepo(tmp_path / "fake.git", "fake-source")
    with pytest.raises(GitError, match=re.escape(f"Không đọc được blob {sha} trong repo.")):
        list(repo.read_blobs([sha]))
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert len(procs) == 1
    assert procs[0].killed and procs[0].waited


class _FailingExitProcess(_ShortReadProcess):
    """Tiến trình `cat-file --batch` giả: trả đủ blob nhưng thoát mã 1 kèm stderr."""

    def __init__(self, sha: str) -> None:
        super().__init__(sha)
        self.stdout = io.BytesIO(f"{sha} blob 4\n".encode() + b"abcd\n")
        self.stderr = io.BytesIO(b"fatal: boom ghp_SECRET123\n")

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        self.returncode = 1
        return 1


def test_read_blobs_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                 caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-51: cat-file thoát mã ≠ 0 sau khi trả đủ blob → GitError, pipe đã đóng."""
    sha = "cd" * 20
    procs: list[_FailingExitProcess] = []

    def fake_popen(cmd, *args, **kwargs):
        procs.append(_FailingExitProcess(sha))
        return procs[-1]

    monkeypatch.setattr(git_repo.subprocess, "Popen", fake_popen)
    caplog.set_level(logging.WARNING, logger="loc_counter")
    repo = GitRepo(tmp_path / "fake.git", "https://example.invalid/o/r", token="ghp_SECRET123")
    with pytest.raises(GitError) as info:
        list(repo.read_blobs([sha]))
    assert str(info.value) == "Lệnh git thất bại: fatal: boom ***"
    assert info.value.returncode == 1
    assert "ghp_SECRET123" not in info.value.stderr
    assert "ghp_SECRET123" not in caplog.text
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    proc = procs[0]
    assert proc.waited and not proc.killed
    assert proc.stdin.closed and proc.stdout.closed and proc.stderr.closed


def _ancestry_repo(make_repo):
    """main: c0 → c1 → c2; feat (từ c1): f1."""
    src = make_repo()
    c0 = src.commit("c0", "2026-01-01T10:00:00+07:00", files={"a.py": "a = 0\n"})
    c1 = src.commit("c1", "2026-01-02T10:00:00+07:00", files={"a.py": "a = 1\n"})
    src.checkout("feat", create=True)
    f1 = src.commit("f1", "2026-01-02T12:00:00+07:00", author=BOB, files={"f.py": "f = 1\n"})
    src.checkout("main")
    c2 = src.commit("c2", "2026-01-03T10:00:00+07:00", files={"a.py": "a = 2\n"})
    return src, c0, c1, c2, f1


def test_is_ancestor(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch,
                     caplog: pytest.LogCaptureFixture) -> None:
    """TC-git_repo-52: is_ancestor đúng chiều, chính nó là tổ tiên; SHA sai → ValueError."""
    src, c0, c1, c2, f1 = _ancestry_repo(make_repo)
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    assert repo.is_ancestor(c0, c2) is True
    assert repo.is_ancestor(c2, c0) is False
    assert repo.is_ancestor(f1, c2) is False
    assert repo.is_ancestor(c1, f1) is True
    assert repo.is_ancestor(c1, c1) is True

    calls: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        if "merge-base" in cmd:
            return subprocess.CompletedProcess(cmd, 128, b"", b"fatal: odd\n")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    for bad in (("main", c2), (c0, "-p")):
        with pytest.raises(ValueError):
            repo.is_ancestor(*bad)
    assert calls == []
    caplog.set_level(logging.WARNING, logger="loc_counter")
    with pytest.raises(GitError, match="Lệnh git thất bại"):
        repo.is_ancestor(c0, c2)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_merge_bases(make_repo, cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-53: merge_bases — một base, criss-cross (2 base, sắp tăng), không liên quan."""
    src, c0, c1, c2, f1 = _ancestry_repo(make_repo)
    # criss-cross: x1 (từ c2) và y1 (từ c2) merge chéo nhau
    src.checkout("x", create=True)
    x1 = src.commit("x1", "2026-01-04T10:00:00+07:00", files={"x.py": "x = 1\n"})
    src.checkout("main")
    src.checkout("y", create=True)
    y1 = src.commit("y1", "2026-01-04T11:00:00+07:00", files={"y.py": "y = 1\n"})
    src.checkout("x")
    mx = src.merge("y", "mx", "2026-01-05T10:00:00+07:00")
    src.checkout("y")
    src.git("merge", "-q", "--no-ff", "-m", "my", x1, date="2026-01-05T11:00:00+07:00")
    my = src.head()
    # lịch sử không liên quan
    blob = src.hash_blob(b"o = 1\n")
    tree = src.git("mktree", stdin=f"100644 blob {blob}\to.py".encode())
    lonely = src.git("commit-tree", tree, "-m", "lonely", date="2026-01-06T10:00:00+07:00")
    src.git("update-ref", "refs/heads/lonely", lonely)
    src.checkout("main")
    repo = GitRepo.open(str(src.path), cache_root=cache_root)

    assert repo.merge_bases(c2, f1) == [c1]
    assert repo.merge_bases(mx, my) == sorted([x1, y1])
    expected = sorted(src.git("merge-base", "--all", mx, my).split())
    assert repo.merge_bases(mx, my) == expected
    assert repo.merge_bases(c2, lonely) == []
    with pytest.raises(ValueError):
        repo.merge_bases("HEAD", c2)

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if "merge-base" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"xyz\n", b"")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    with pytest.raises(GitError, match=re.escape("Không đọc được kết quả merge-base.")):
        repo.merge_bases(c2, f1)


def test_merge_bases_sorted_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-git_repo-53: merge_bases bỏ trùng + sắp tăng dần; mã thoát khác 0/1 → GitError."""
    a, b = "a" * 40, "b" * 40
    outputs = [(0, f"{b}\n{a}\n{b}\n".encode(), b""), (128, b"", b"fatal: bad object\n"),
               (1, f"{a}\n".encode(), b"")]

    def fake_run(cmd, *args, **kwargs):
        code, out, err = outputs.pop(0)
        return subprocess.CompletedProcess(cmd, code, out, err)

    monkeypatch.setattr(git_repo.subprocess, "run", fake_run)
    repo = GitRepo(tmp_path / "fake.git", str(tmp_path))
    assert repo.merge_bases(a, b) == [a, b]
    with pytest.raises(GitError) as info:
        repo.merge_bases(a, b)
    assert info.value.returncode == 128 and "bad object" in info.value.stderr
    with pytest.raises(GitError) as info:
        repo.merge_bases(a, b)
    assert info.value.returncode == 1
