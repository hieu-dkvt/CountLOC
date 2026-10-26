"""Fixture dùng chung cho test LOC Counter."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple

import pytest

DEFAULT_AUTHOR = ("admin", "admin@example.com")
BOT_AUTHOR = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
NL = chr(10)


class RepoBuilder:
    """Dựng repo Git tạm với ngày commit cố định (không truy cập mạng)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")

    def _env(self, date: str | None = None, author: tuple[str, str] | None = None,
             committer: tuple[str, str] | None = None) -> dict:
        env = dict(os.environ)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        name, email = author or DEFAULT_AUTHOR
        c_name, c_email = committer or (name, email)
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME=c_name, GIT_COMMITTER_EMAIL=c_email)
        if date is not None:
            env["GIT_AUTHOR_DATE"] = date
            env["GIT_COMMITTER_DATE"] = date
        return env

    def git(self, *args: str, date: str | None = None, author: tuple[str, str] | None = None,
            stdin: bytes | None = None, committer: tuple[str, str] | None = None) -> str:
        """Chạy git trong repo, trả stdout (đã strip)."""
        proc = subprocess.run(
            ["git", *args], cwd=self.path, input=stdin, capture_output=True,
            env=self._env(date, author, committer), check=True,
        )
        return proc.stdout.decode("utf-8").strip()

    def write(self, rel: str, data: bytes | str, executable: bool = False) -> None:
        """Ghi file (bytes giữ nguyên) và git add."""
        path = self.path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        self.git("add", "--", rel)
        if executable:
            self.git("update-index", "--chmod=+x", "--", rel)

    def remove(self, rel: str) -> None:
        self.git("rm", "-q", "--", rel)

    def add_index_entry(self, mode: str, sha: str, rel: str) -> None:
        """Thêm entry đặc biệt (symlink 120000, submodule 160000) trực tiếp vào index."""
        self.git("update-index", "--add", "--cacheinfo", f"{mode},{sha},{rel}")

    def hash_blob(self, data: bytes) -> str:
        return self.git("hash-object", "-w", "--stdin", stdin=data)

    def commit(self, message: str, date: str, author: tuple[str, str] | None = None,
               files: Mapping[str, bytes | str] | None = None,
               remove: tuple[str, ...] = (), committer: tuple[str, str] | None = None) -> str:
        """Ghi files, xóa remove rồi commit với author/committer date = date. Trả SHA."""
        for rel, data in (files or {}).items():
            self.write(rel, data)
        for rel in remove:
            self.remove(rel)
        self.git("commit", "-q", "--allow-empty", "-m", message, date=date, author=author,
                 committer=committer)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def checkout(self, branch: str, create: bool = False) -> None:
        if create:
            self.git("checkout", "-q", "-b", branch)
        else:
            self.git("checkout", "-q", branch)

    def merge(self, branch: str, message: str, date: str,
              author: tuple[str, str] | None = None) -> str:
        """Merge --no-ff nhánh vào nhánh hiện tại."""
        self.git("merge", "-q", "--no-ff", "-m", message, branch, date=date, author=author)
        return self.head()


@pytest.fixture(autouse=True)
def _isolate_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mọi lệnh git trong test không đọc cấu hình toàn cục / hệ thống của máy."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., RepoBuilder]:
    """Factory tạo repo nguồn trong tmp_path/<name>."""

    def factory(name: str = "src") -> RepoBuilder:
        return RepoBuilder(tmp_path / name)

    return factory


class Section14(NamedTuple):
    """Repo mẫu §14 và nội dung mong đợi."""

    src: RepoBuilder
    app_start: str
    app_end: str
    util: str
    end_sha: str


def _build_section14(src: RepoBuilder, bot: bool) -> Section14:
    """Repo mẫu §14: admin trước start, alice/bob trong kỳ, alice sau end."""
    alice, bob = ("alice", "alice@example.com"), ("bob", "bob@example.com")
    code = [f"v{i} = {i}" for i in range(10)]
    app = ["# đầu file", "", *code[:5], "# giữa", "", *code[5:], "# cuối"]
    src.commit("admin: app.py", "2025-12-15T10:00:00+07:00",
               files={"app.py": NL.join(app) + NL})
    if bot:
        src.commit("chore: bump", "2026-01-04T10:00:00+07:00", author=BOT_AUTHOR,
                   files={"deps.txt": "lib==2" + NL})
    app2 = [*app, "# alice", "a1 = 1", "a2 = 2", "# alice 2", "a3 = 3", "a4 = 4", "a5 = 5"]
    src.commit("alice add", "2026-01-05T10:00:00+07:00", author=alice,
               files={"app.py": NL.join(app2) + NL})
    util = NL.join(f"u{i} = {i}" for i in range(8)) + NL
    src.commit("bob util", "2026-01-06T10:00:00+07:00", author=bob, files={"util.py": util})
    app3 = [line for line in app2 if line not in ("v0 = 0", "v1 = 1")]
    src.commit("alice del", "2026-01-07T10:00:00+07:00", author=alice,
               files={"app.py": NL.join(app3) + NL})
    app4 = [line for line in app3 if line != "v9 = 9"]
    end_sha = src.commit("bob del", "2026-01-08T10:00:00+07:00", author=bob,
                         files={"app.py": NL.join(app4) + NL})
    app5 = [*app4, *(f"late{i} = {i}" for i in range(100))]
    src.commit("alice late", "2026-02-10T10:00:00+07:00", author=alice,
               files={"app.py": NL.join(app5) + NL})
    return Section14(src, NL.join(app) + NL, NL.join(app4) + NL, util, end_sha)


@pytest.fixture
def section14_repo(make_repo) -> Callable[..., Section14]:
    """Factory repo mẫu §14 (mục 14 spec gốc); bot=True thêm 1 commit dependabot[bot] trong kỳ."""

    def factory(bot: bool = False, name: str = "src") -> Section14:
        return _build_section14(make_repo(name), bot)

    return factory


@pytest.fixture
def cache_root(tmp_path: Path) -> Path:
    """Thư mục cache repo riêng cho từng test (không đụng ~/.loc_counter)."""
    return tmp_path / "cache"


def build_cross_check_mismatch(src: RepoBuilder) -> RepoBuilder:
    """Repo ca lệch kiểm tra chéo: notes.txt (bị loại) đổi tên 100 % → notes.py trong kỳ."""
    body = NL.join(f"x{i} = {i}" for i in range(10)) + NL
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"app.py": body.replace("x", "a"), "notes.txt": body})
    src.commit("alice rename", "2026-01-05T10:00:00+07:00", author=("alice", "alice@example.com"),
               files={"notes.py": body}, remove=("notes.txt",))
    return src


def build_systematic_mismatch(src: RepoBuilder, kind: str) -> RepoBuilder:
    """Repo lệch kiểm tra chéo hệ thống (D40-N6): alice chuyển lib.py vào vendor/ hoặc thay
    lib.py bằng symlink trỏ app.py trong kỳ. kind: "vendor" | "symlink"."""
    body = NL.join(f"x{i} = {i}" for i in range(10)) + NL
    src.commit("admin", "2025-12-15T10:00:00+07:00",
               files={"app.py": body.replace("x", "a"), "lib.py": body})
    if kind == "vendor":
        (src.path / "vendor").mkdir()
        src.git("mv", "lib.py", "vendor/lib.py")
    else:
        src.remove("lib.py")
        src.add_index_entry("120000", src.hash_blob(b"app.py"), "lib.py")
    src.commit(f"alice {kind}", "2026-01-05T10:00:00+07:00", author=("alice", "alice@example.com"))
    return src


APP_PATH = Path(__file__).resolve().parents[1] / "src" / "loc_counter" / "app.py"


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], object]:
    """Factory AppTest cho app.py: cache repo / login trong tmp_path, CWD = tmp_path (M6)."""
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from loc_counter import git_repo, identity

    monkeypatch.setattr(git_repo, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(identity, "DEFAULT_LOGIN_CACHE", tmp_path / "logins.json")
    monkeypatch.chdir(tmp_path)
    st.cache_resource.clear()

    def factory() -> AppTest:
        return AppTest.from_file(str(APP_PATH), default_timeout=60)

    return factory
