"""Truy cập Git repository: clone/fetch vào cache, nhánh, commit, cây file, blob (§3.1, §4, §15)."""

from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

from loc_counter.config import LocCounterError

logger = logging.getLogger(__name__)

MIN_GIT_VERSION: tuple[int, int] = (2, 30)
DEFAULT_CACHE_ROOT: Path = Path.home() / ".loc_counter" / "repos"

_GLOBAL_OPTS = ("-c", "core.quotepath=off", "-c", "core.autocrlf=false",
                "-c", "log.showSignature=false", "-c", "i18n.logOutputEncoding=UTF-8")
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+://")
_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
_HTTPS_RE = re.compile(r"^https://", re.IGNORECASE)
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_TRANSPORT_RE = re.compile(r"^[A-Za-z0-9+.-]+::")
_BAD_BRANCH_CHARS = set(" ~^:?*[\\\t\n")

_AUTH_RE = re.compile(
    r"Authentication failed|could not read (Username|Password)|returned error: 40[13]"
    r"|Permission denied \(publickey",
    re.IGNORECASE,
)
_NOT_FOUND_RE = re.compile(r"Repository not found|returned error: 404", re.IGNORECASE)
_NOT_REPO_RE = re.compile(
    r"does not appear to be a git repository|not a git repository"
    r"|repository '.*' does not exist",
    re.IGNORECASE,
)
_HOST_RE = re.compile(r"(?:Could not resolve host|Failed to connect to):? ([^\s':]+)",
                      re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"timed out", re.IGNORECASE)

_DIFF_OPTS = ("-c", "diff.algorithm=myers", "-c", "diff.indentHeuristic=true")
_ZERO_SHA = "0" * 40
_RENAME_LIMIT_RE = re.compile(r"rename detection was skipped|renamelimit", re.IGNORECASE)
_HUNK_RE = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_BLAME_HEADER_RE = re.compile(rb"^([0-9a-f]{40}) (\d+) (\d+)(?: \d+)?$")
_BLAME_MAX_RANGES = 200
_C_ESCAPES = {"\\": 0x5C, '"': 0x22, "a": 0x07, "b": 0x08, "t": 0x09, "n": 0x0A,
              "v": 0x0B, "f": 0x0C, "r": 0x0D}


class GitError(LocCounterError):
    """Lỗi khi chạy git. str(err) = thông báo tiếng Việt (đã che token)."""

    def __init__(self, message: str, command: str = "", returncode: int | None = None,
                 stderr: str = "") -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class CommitInfo:
    """Thông tin một commit."""

    sha: str
    short_sha: str
    committer_date: datetime
    author_name: str
    author_email: str
    subject: str


@dataclass(frozen=True)
class TreeEntry:
    """Một entry trong cây file của commit."""

    path: str
    mode: str
    object_type: str
    sha: str
    size: int | None


@dataclass(frozen=True)
class LogCommit:
    """Một commit trong kỳ: author gốc và author sau .mailmap."""

    sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    mapped_name: str
    mapped_email: str
    author_date: datetime
    subject: str = ""
    body_title: str = ""

    @property
    def is_merge(self) -> bool:
        """Merge commit (nhiều hơn một parent)."""
        return len(self.parents) > 1


@dataclass(frozen=True)
class DiffEntry:
    """Một cặp file giữa hai commit (một bản ghi `diff-tree --raw`)."""

    status: str
    old_path: str | None
    new_path: str | None
    old_mode: str | None
    new_mode: str | None
    old_sha: str | None
    new_sha: str | None
    similarity: int | None

    @property
    def path(self) -> str:
        """new_path nếu có, ngược lại old_path (khóa sắp xếp)."""
        return self.new_path if self.new_path is not None else self.old_path or ""


@dataclass(frozen=True)
class TreeDiff:
    """Kết quả so sánh cây file giữa C_START và C_END."""

    entries: tuple[DiffEntry, ...]
    rename_limit_hit: bool


@dataclass(frozen=True)
class Hunk:
    """Một hunk `-U0`; chỉ số 0-based, dạng nửa mở [start, start + count)."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass(frozen=True)
class BlameLine:
    """Một dòng của kết quả blame (chỉ số 0-based)."""

    line: int
    sha: str
    orig_line: int
    filename: str
    boundary: bool


def _header_b64(token: str) -> str:
    return base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")


def mask_secrets(text: str, secrets: Iterable[str | None]) -> str:
    """Thay mọi secret (và dạng base64 trong header) bằng '***'."""
    for secret in secrets:
        if not secret:
            continue
        text = text.replace(_header_b64(secret), "***").replace(secret, "***")
    return text


@functools.cache
def git_version() -> tuple[int, int, int]:
    """Phiên bản git trên PATH; ném GitError nếu không có git hoặc < MIN_GIT_VERSION."""
    try:
        proc = subprocess.run(["git", "--version"], capture_output=True, check=False)
    except FileNotFoundError as exc:
        logger.error("Không chạy được git: %s", exc)
        raise GitError("Không tìm thấy lệnh git. Hãy cài Git ≥ 2.30 và thêm vào PATH.") from exc
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", proc.stdout.decode("utf-8", "replace"))
    if proc.returncode != 0 or match is None:
        raise GitError("Không xác định được phiên bản git. Hãy cài Git ≥ 2.30.")
    version = (int(match[1]), int(match[2]), int(match[3]))
    if version[:2] < MIN_GIT_VERSION:
        text = ".".join(map(str, version))
        logger.error("git %s quá cũ", text)
        raise GitError(f"Phiên bản git {text} quá cũ, cần ≥ 2.30.")
    return version


def normalize_source(source: str) -> tuple[str, bool]:
    """(nguồn chuẩn hóa, is_local). Ném GitError nếu URL chứa thông tin xác thực / không hợp lệ.

    http(s): mọi userinfo bị từ chối; scheme khác / scp: chỉ từ chối khi có mật khẩu.
    """
    text = source.strip()
    if not text:
        raise GitError("Chưa nhập repo (URL hoặc đường dẫn local).")
    if _TRANSPORT_RE.match(text):  # ext:: chạy lệnh tùy ý, fd:: đọc stdin
        raise GitError("Không hỗ trợ nguồn dạng <transport>::<địa chỉ>. "
                       "Hãy nhập URL hoặc đường dẫn local.")
    is_url = bool(_URL_RE.match(text))
    if is_url or (_is_scp_like(text) and not Path(text).expanduser().is_dir()):
        # Không dùng urlsplit: netloc bị cắt tại / ? # nên bỏ sót mật khẩu chứa các ký tự đó.
        rest = text.split("://", 1)[1] if is_url else text
        userinfo = rest.rpartition("@")[0]
        # http(s): mọi userinfo; scheme khác / scp: chỉ khi có mật khẩu (scp không có cú pháp
        # mật khẩu, nhưng chuỗi user:pass@host:path vẫn bị từ chối để không lộ)
        has_secret = "@" in rest if _HTTP_RE.match(text) else ":" in userinfo
        if has_secret:
            logger.warning("Từ chối URL repo chứa thông tin xác thực")
            raise GitError("URL repo không được chứa thông tin xác thực. "
                           "Hãy nhập token ở ô/biến môi trường riêng.")
        return text.rstrip("/"), False
    path = Path(text).expanduser().resolve()
    if not path.is_dir():
        shown = f"***@{text.rpartition('@')[2]}" if "@" in text else text
        raise GitError(f"Không tìm thấy repo: {shown}")
    return str(path), True


def _is_scp_like(text: str) -> bool:
    """Dạng scp `[user@]host:path` theo quy tắc git: có `:`, trước nó không có `/` `\\`,
    không phải ổ đĩa `X:`."""
    head, colon, _ = text.partition(":")
    return bool(colon) and "/" not in head and "\\" not in head and not _DRIVE_RE.match(text)


def cache_dir_for(source: str, cache_root: Path = DEFAULT_CACHE_ROOT) -> Path:
    """cache_root / sha1(nguồn chuẩn hóa)[:16]."""
    return Path(cache_root) / hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]


def _remove_tree(path: Path) -> None:
    """Xóa thư mục, kể cả file read-only (pack/idx của git trên Windows).

    Không xóa được → GitError.
    """

    def retry(func, target, _exc) -> None:  # noqa: ANN001
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if not path.exists():
        return
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=retry)
        else:  # pragma: no cover - Python 3.11
            shutil.rmtree(path, onerror=retry)
    except OSError as exc:
        logger.warning("Không xóa được %s: %s", path, exc)
    if path.exists():
        raise GitError(f"Không xóa được thư mục cache {path}. "
                       "Hãy đóng chương trình đang dùng nó rồi thử lại.")


def _parse_commit_date(text: str, sha: str) -> datetime:
    """Ngày ISO 8601 của git (%aI/%cI); header múi giờ hỏng → GitError."""
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        logger.warning("Ngày commit %s không hợp lệ: %r", sha, text)
        raise GitError(f"Không đọc được ngày của commit {sha}") from exc


def _check_sha(*shas: str) -> None:
    """Tham số commit/blob phải là SHA 40 hex (chặn chèn tùy chọn vào argv)."""
    for sha in shas:
        if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
            raise ValueError(f"SHA không hợp lệ: {sha!r}")


def _decode_path(raw: bytes, context: str) -> str:
    """Giải mã đường dẫn UTF-8; ký tự lỗi → log WARNING."""
    path = raw.decode("utf-8", "replace")
    if "�" in path:
        logger.warning("Đường dẫn không phải UTF-8 (%s): %r", context, raw)
    return path


def _unquote_c(value: bytes) -> bytes:
    """Bỏ C-quote của git (`"..."` với escape `\\n`, `\\"`, `\\ooo`…)."""
    if len(value) < 2 or not (value.startswith(b'"') and value.endswith(b'"')):
        return value
    text = value[1:-1].decode("latin-1")
    out = bytearray()
    i = 0
    while i < len(text):
        char = text[i]
        if char != "\\" or i + 1 >= len(text):
            out.append(ord(char))
            i += 1
            continue
        nxt = text[i + 1]
        if nxt in _C_ESCAPES:
            out.append(_C_ESCAPES[nxt])
            i += 2
        elif re.fullmatch(r"[0-7]{3}", text[i + 1:i + 4]):
            out.append(int(text[i + 1:i + 4], 8) & 0xFF)
            i += 4
        else:
            out.append(ord(nxt))
            i += 2
    return bytes(out)


def _merge_ranges(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sắp xếp, gộp khoảng nửa mở chồng / liền kề, bỏ khoảng rỗng."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(r for r in ranges if r[1] > r[0]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _classify_error(stderr: str, source: str) -> str:
    """Thông báo tiếng Việt theo nội dung stderr (đã che token)."""
    if _AUTH_RE.search(stderr):
        return f"Không có quyền truy cập repo {source}. Kiểm tra token hoặc quyền của tài khoản."
    if _NOT_FOUND_RE.search(stderr):
        return (f"Không tìm thấy repo {source} trên server "
                "(sai URL hoặc repo private cần token).")
    if _NOT_REPO_RE.search(stderr):
        return f"Không phải Git repository: {source}"
    host_match = _HOST_RE.search(stderr)
    if host_match or _TIMEOUT_RE.search(stderr):
        host = host_match[1] if host_match else (urlsplit(source).hostname or source)
        return f"Không kết nối được tới {host}. Kiểm tra mạng."
    first = next((line.strip() for line in stderr.splitlines() if line.strip()), "")
    return f"Lệnh git thất bại: {first}"


class GitRepo:
    """Bare clone của nguồn trong thư mục cache; mọi lệnh git đi qua đây."""

    def __init__(self, git_dir: Path, source: str, token: str | None = None) -> None:
        self.git_dir = Path(git_dir)
        self.source = source
        self._token = token if token and _HTTPS_RE.match(source) else None
        self._is_local = False

    def __repr__(self) -> str:
        return f"GitRepo(source={self.source!r}, git_dir={str(self.git_dir)!r})"

    # ----- chạy lệnh -----
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = ""
        env["SSH_ASKPASS"] = ""
        env["LC_ALL"] = "C"
        env.pop("GIT_DIFF_OPTS", None)  # ưu tiên hơn -U trên dòng lệnh → hỏng hunk -U0
        env.pop("GIT_EXTERNAL_DIFF", None)
        if self._token:
            host = urlsplit(self.source).netloc
            header = f"Authorization: Basic {_header_b64(self._token)}"
            params = f"'http.https://{host}/.extraheader={header}' 'credential.helper='"
            existing = env.get("GIT_CONFIG_PARAMETERS")
            env["GIT_CONFIG_PARAMETERS"] = f"{existing} {params}" if existing else params
        return env

    def _command(self, args: Sequence[str], with_git_dir: bool = True) -> list[str]:
        cmd = ["git", *_GLOBAL_OPTS]
        if with_git_dir:
            cmd += ["--git-dir", str(self.git_dir)]
        return cmd + list(args)

    def _mask(self, text: str) -> str:
        return mask_secrets(text, [self._token])

    def _exec(self, args: Sequence[str], *, stdin: bytes | None = None,
              with_git_dir: bool = True, allow_fail: bool = False,
              ) -> subprocess.CompletedProcess[bytes]:
        cmd = self._command(args, with_git_dir)
        shown = self._mask(" ".join(cmd))
        logger.debug("git: %s", shown)
        proc = subprocess.run(cmd, input=stdin, capture_output=True, env=self._env(),
                              check=False)
        if proc.returncode != 0 and not allow_fail:
            self._raise_failed(proc)
        return proc

    def _raise_failed(self, proc: subprocess.CompletedProcess[bytes]) -> NoReturn:
        """Log lệnh + stderr (đã che token) rồi ném GitError theo bảng lỗi mục 7."""
        shown = self._mask(" ".join(proc.args))
        stderr = self._mask(proc.stderr.decode("utf-8", "replace"))
        logger.warning("Lệnh git lỗi (mã %s): %s\n%s", proc.returncode, shown, stderr)
        raise GitError(_classify_error(stderr, self.source), shown, proc.returncode, stderr)

    def run(self, args: Sequence[str], *, stdin: bytes | None = None) -> bytes:
        """Chạy `git <global opts> <args>` trong git_dir, trả stdout bytes; lỗi → GitError."""
        return self._exec(args, stdin=stdin).stdout

    # ----- mở repo -----
    @classmethod
    def open(cls, source: str, token: str | None = None,
             cache_root: Path = DEFAULT_CACHE_ROOT) -> GitRepo:
        """Clone bare vào cache hoặc fetch nếu đã có. Token chỉ giữ trong đối tượng."""
        git_version()
        normalized, is_local = normalize_source(source)
        if token and not is_local and not _HTTPS_RE.match(normalized):
            raise GitError("Token chỉ dùng với URL https://.")
        dest = cache_dir_for(normalized, cache_root)
        repo = cls(dest, normalized, None if is_local else token)
        repo._is_local = is_local
        if dest.exists() and repo._is_bare_repo():
            repo._check_origin_url()
            logger.info("Cập nhật repo cache %s", dest)
            repo.run(["fetch", "--prune", "--no-tags", "origin", "+refs/heads/*:refs/heads/*"])
        else:
            if dest.exists():
                logger.warning("Thư mục cache hỏng, clone lại: %s", dest)
                _remove_tree(dest)
            repo._clone()
            repo._check_origin_url()
        repo._update_head()
        repo._check_no_token_in_config()
        return repo

    def _is_bare_repo(self) -> bool:
        proc = self._exec(["rev-parse", "--is-bare-repository"], allow_fail=True)
        return proc.returncode == 0 and proc.stdout.strip() == b"true"

    def _clone(self) -> None:
        try:
            self.git_dir.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Không tạo được %s: %s", self.git_dir.parent, exc)
            raise GitError(f"Không tạo được thư mục cache {self.git_dir.parent}: {exc}") from exc
        tmp = self.git_dir.with_name(f"{self.git_dir.name}.tmp-{os.getpid()}")
        _remove_tree(tmp)
        logger.info("Clone %s vào cache %s", self.source, self.git_dir)
        try:
            hardlinks = ["--no-hardlinks"] if self._is_local else []
            self._exec(["clone", "--bare", "--no-tags", "--origin", "origin", *hardlinks, "--",
                        self.source, str(tmp)], with_git_dir=False)
            try:
                os.replace(tmp, self.git_dir)
            except OSError as exc:
                logger.warning("Không đổi tên %s → %s: %s", tmp, self.git_dir, exc)
                raise GitError(f"Không ghi được thư mục cache {self.git_dir}: {exc}") from exc
        except BaseException:
            with contextlib.suppress(GitError):
                _remove_tree(tmp)
            raise

    def _update_head(self) -> None:
        out = self.run(["ls-remote", "--symref", "origin", "HEAD"]).decode("utf-8", "replace")
        for line in out.splitlines():
            if line.startswith("ref: ") and line.endswith("\tHEAD"):
                ref = line[len("ref: "):-len("\tHEAD")]
                if ref.startswith("refs/heads/"):
                    self.run(["symbolic-ref", "HEAD", ref])
                return

    def _check_origin_url(self) -> None:
        """remote.origin.url của cache phải đúng nguồn chuẩn hóa (bước 5.4.8)."""
        proc = self._exec(["config", "--get", "remote.origin.url"], allow_fail=True)
        url = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode != 0 or url != self.source:
            logger.warning("remote.origin.url của cache %s không khớp nguồn", self.git_dir)
            raise GitError("Cấu hình repo cache không khớp nguồn. "
                           f"Hãy xóa thư mục {self.git_dir} rồi thử lại.")

    def _check_no_token_in_config(self) -> None:
        """File config của cache không được chứa token (bước 5.4.8)."""
        if not self._token:
            return
        config = (self.git_dir / "config").read_text(encoding="utf-8", errors="replace")
        if self._mask(config) != config:
            logger.error("Phát hiện thông tin xác thực trong config của %s", self.git_dir)
            raise GitError("Lỗi bảo mật: thông tin xác thực bị ghi vào cấu hình repo cache.")

    # ----- nhánh -----
    def list_branches(self) -> list[str]:
        """Tên nhánh (refs/heads), sắp xếp tăng dần."""
        out = self.run(["for-each-ref", "--format=%(refname:strip=2)", "refs/heads/"])
        return sorted(line for line in out.decode("utf-8", "replace").splitlines() if line)

    def default_branch(self) -> str | None:
        """Nhánh mặc định của nguồn (HEAD), None nếu không xác định / không còn tồn tại."""
        proc = self._exec(["symbolic-ref", "--quiet", "--short", "HEAD"], allow_fail=True)
        name = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode != 0 or not name:
            return None
        return name if name in self.list_branches() else None

    @staticmethod
    def _check_branch_name(branch: str) -> None:
        if (not branch or branch.startswith("-") or ".." in branch
                or any(c in _BAD_BRANCH_CHARS for c in branch)):
            raise GitError(f"Không tìm thấy nhánh: {branch}")

    def resolve_branch(self, branch: str) -> str:
        """SHA đầu nhánh; ném GitError nếu nhánh không tồn tại."""
        self._check_branch_name(branch)
        proc = self._exec(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
                          allow_fail=True)
        if proc.returncode != 0:
            raise GitError(f"Không tìm thấy nhánh: {branch}")
        return proc.stdout.decode("ascii").strip()

    # ----- commit -----
    def rev_before(self, branch: str, moment: datetime) -> str | None:
        """Commit cuối theo first-parent có committer date ≤ moment; None nếu không có."""
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("moment phải có tzinfo")
        self._check_branch_name(branch)
        iso = moment.replace(microsecond=0).isoformat()
        out = self.run(["rev-list", "-1", "--first-parent", f"--before={iso}",
                        f"refs/heads/{branch}", "--"])
        sha = out.decode("ascii").strip()
        return sha or None

    def commit_info(self, sha: str) -> CommitInfo:
        """Thông tin commit (committer date aware, giữ offset gốc)."""
        out = self.run(["show", "-s", "--format=%H%x00%cI%x00%an%x00%ae%x00%s", sha, "--"])
        full, date, name, email, subject = out.decode("utf-8", "replace").rstrip("\n").split("\0")
        if not _SHA_RE.fullmatch(full):
            logger.warning("Kết quả git show không hợp lệ cho %s: %r", sha, full[:80])
            raise GitError(f"Không đọc được thông tin commit {sha}")
        return CommitInfo(full, full[:7], _parse_commit_date(date, full), name, email, subject)

    # ----- cây file và blob -----
    def list_tree(self, commit_sha: str) -> list[TreeEntry]:
        """Mọi entry của cây (đệ quy), sắp xếp theo path (so sánh chuỗi Python)."""
        out = self.run(["ls-tree", "-r", "-l", "-z", "--full-tree", commit_sha])
        entries: list[TreeEntry] = []
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, object_type, sha, size = meta.decode("ascii").split()
            if object_type not in ("blob", "commit"):
                continue
            path = raw_path.decode("utf-8", "replace")
            if "\ufffd" in path:
                logger.warning("Đường dẫn không phải UTF-8 trong commit %s: %r",
                               commit_sha, raw_path)
            entries.append(TreeEntry(path, mode, object_type, sha,
                                     None if size == "-" else int(size)))
        entries.sort(key=lambda e: e.path)
        return entries

    def read_blob(self, sha: str) -> bytes:
        """Nội dung blob nguyên byte."""
        return self.run(["cat-file", "blob", sha])

    def read_blobs(self, shas: Iterable[str]) -> Iterator[tuple[str, bytes]]:
        """Đọc nhiều blob qua một tiến trình `git cat-file --batch`, giữ thứ tự đầu vào.

        Generator: đóng sớm (`close()`) thì tiến trình git bị dừng ngay.
        """
        cmd = self._command(["cat-file", "--batch"])
        shown = self._mask(" ".join(cmd))
        logger.debug("git: %s", shown)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=self._env())
        assert proc.stdin is not None and proc.stdout is not None
        finished = False
        try:
            for sha in shas:
                proc.stdin.write(f"{sha}\n".encode("ascii"))
                proc.stdin.flush()
                header = proc.stdout.readline().decode("ascii", "replace").split()
                if len(header) != 3 or header[1] != "blob":
                    logger.warning("cat-file không có blob %s: %s (%s)", sha, " ".join(header),
                                   shown)
                    raise GitError(f"Không tìm thấy blob {sha} trong repo.", shown)
                data = proc.stdout.read(int(header[2]))
                if len(data) != int(header[2]):
                    logger.warning("cat-file trả thiếu byte cho blob %s (%d/%s): %s", sha,
                                   len(data), header[2], shown)
                    raise GitError(f"Không đọc được blob {sha} trong repo.", shown)
                proc.stdout.read(1)  # "\n" kết thúc
                yield sha, data
            finished = True
        finally:
            error: GitError | None = None
            if finished:
                proc.stdin.close()
                stderr = proc.stderr.read() if proc.stderr else b""
                if proc.wait() != 0:
                    text = self._mask(stderr.decode("utf-8", "replace"))
                    logger.warning("Lệnh git lỗi (mã %s): %s\n%s", proc.returncode, shown, text)
                    error = GitError(_classify_error(text, self.source), shown, proc.returncode,
                                     text)
            else:
                proc.kill()
                with contextlib.suppress(OSError):
                    proc.stdin.close()
                proc.wait()
            proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            if error is not None:
                raise error

    def log_commits(self, c_end: str, c_start: str | None = None,
                    mailmap_rev: str | None = None) -> list[LogCommit]:
        """Mọi commit trong c_start..c_end (c_start None → mọi commit tới c_end).

        Thứ tự như `git log` (mới → cũ).
        """
        blob = f"{mailmap_rev}:.mailmap" if mailmap_rev else ""
        args = ["-c", "mailmap.file=", "-c", f"mailmap.blob={blob}", "log", "--no-color",
                "--format=%x1e%H%x00%P%x00%an%x00%ae%x00%aN%x00%aE%x00%aI%x00%s%x00%b", c_end]
        if c_start:
            args.append(f"^{c_start}")
        args.append("--")
        out = self.run(args).decode("utf-8", "replace")
        commits: list[LogCommit] = []
        for record in out.split("\x1e"):
            if not record.strip():
                continue
            fields = record.rstrip("\n").split("\0")
            if len(fields) != 9 or not _SHA_RE.fullmatch(fields[0]):
                logger.warning("Kết quả git log không hợp lệ: %r", record[:80])
                raise GitError("Không đọc được danh sách commit trong kỳ.")
            sha, parents, an, ae, mn, me, date, subject, body = fields
            body_title = next((s for s in map(str.strip, body.splitlines()) if s), "")
            commits.append(LogCommit(sha, tuple(parents.split()), an, ae, mn, me,
                                     _parse_commit_date(date, sha), subject.strip(), body_title))
        return commits

    # ----- diff, blame (M4) -----
    def diff_tree(self, c_start: str | None, c_end: str) -> TreeDiff:
        """Cặp file khác nhau giữa c_start và c_end, nhận diện rename.

        c_start None → mọi entry của c_end là "A".
        """
        _check_sha(c_end)
        if c_start is None:
            entries = [DiffEntry("A", None, e.path, None, e.mode, None, e.sha, None)
                       for e in self.list_tree(c_end)]
            return TreeDiff(tuple(entries), False)
        _check_sha(c_start)
        proc = self._exec(["diff-tree", "-r", "-z", "--raw", "--no-abbrev", "-M", "-l0",
                           c_start, c_end])
        entries = self._parse_raw_diff(proc.stdout, c_end)
        stderr = self._mask(proc.stderr.decode("utf-8", "replace"))
        limited = bool(_RENAME_LIMIT_RE.search(stderr))
        if limited:
            logger.warning("git bỏ qua nhận diện đổi tên giữa %s và %s: %s",
                           c_start[:7], c_end[:7], stderr.strip())
        entries.sort(key=lambda e: (e.path, e.old_path or ""))
        return TreeDiff(tuple(entries), limited)

    @staticmethod
    def _parse_raw_diff(out: bytes, context: str) -> list[DiffEntry]:
        """Phân tích output `diff-tree -r -z --raw`."""

        def fail(record: bytes) -> GitError:
            logger.warning("Kết quả diff-tree không hợp lệ: %r", record[:80])
            return GitError("Không đọc được kết quả so sánh cây file.")

        fields = out.split(b"\0")
        if fields and fields[-1] == b"":
            fields.pop()
        entries: list[DiffEntry] = []
        i = 0
        while i < len(fields):
            meta = fields[i]
            parts = meta[1:].decode("ascii", "replace").split() if meta.startswith(b":") else []
            if len(parts) != 5:
                raise fail(meta)
            old_mode, new_mode, old_sha, new_sha, status = parts
            kind = status[0]
            count = 2 if kind in "RC" else 1
            if kind not in "ADMRT" or i + count >= len(fields):
                raise fail(meta)
            paths = [_decode_path(p, context) for p in fields[i + 1:i + 1 + count]]
            i += 1 + count
            similarity = int(status[1:]) if kind == "R" and status[1:].isdigit() else None
            old_path = None if kind == "A" else paths[0]
            new_path = None if kind == "D" else paths[-1]
            entries.append(DiffEntry(
                kind, old_path, new_path,
                None if old_mode == "000000" else old_mode,
                None if new_mode == "000000" else new_mode,
                None if old_sha == _ZERO_SHA else old_sha,
                None if new_sha == _ZERO_SHA else new_sha,
                similarity,
            ))
        return entries

    def diff_hunks(self, old_sha: str, new_sha: str) -> list[Hunk]:
        """Hunk `-U0` (Myers) giữa hai blob, thứ tự tăng dần; cùng SHA → []."""
        _check_sha(old_sha, new_sha)
        if old_sha == new_sha:
            return []
        out = self.run([*_DIFF_OPTS, "diff", "-U0", "--inter-hunk-context=0",
                        "--diff-algorithm=myers", "--indent-heuristic", "--no-color",
                        "--no-ext-diff", "--no-textconv", "--text", "--no-renames",
                        old_sha, new_sha])
        hunks: list[Hunk] = []
        for line in out.split(b"\n"):
            match = _HUNK_RE.match(line)
            if match is None:
                continue
            a, c = int(match[1]), int(match[3])
            b = 1 if match[2] is None else int(match[2])
            d = 1 if match[4] is None else int(match[4])
            hunks.append(Hunk(a - 1 if b > 0 else a, b, c - 1 if d > 0 else c, d))
        return hunks

    def blame(self, end: str, path: str, since: str | None = None, *, reverse: bool = False,
              detect_moves: bool = True,
              line_ranges: Sequence[tuple[int, int]] = ()) -> list[BlameLine]:
        """Blame `since..end` (since None → tới commit gốc) của `path`.

        Forward: path tại `end`, thêm `-M -C` khi detect_moves. Reverse (cần since): path tại
        `since`, không `-M -C`. line_ranges: khoảng 0-based nửa mở; rỗng → cả file.
        """
        if reverse and since is None:
            raise ValueError("blame --reverse cần since")
        _check_sha(end)
        if since is not None:
            _check_sha(since)
        args = [*_DIFF_OPTS, "blame", "--line-porcelain", "--root", "--no-ignore-revs-file",
                "--no-textconv", "-w"]
        if reverse:
            args.append("--reverse")
        elif detect_moves:
            args += ["-M", "-C"]
        target = [f"{since}..{end}" if since else end, "--", path]
        ranges = _merge_ranges(line_ranges)
        if line_ranges and not ranges:
            return []
        batches = ([ranges[i:i + _BLAME_MAX_RANGES]
                    for i in range(0, len(ranges), _BLAME_MAX_RANGES)] if ranges else [[]])
        lines: list[BlameLine] = []
        for batch in batches:
            opts = [item for s, e in batch for item in ("-L", f"{s + 1},{e}")]
            lines += self._parse_blame(self.run([*args, *opts, *target]), path)
        lines.sort(key=lambda b: b.line)
        return lines

    @staticmethod
    def _parse_blame(out: bytes, path: str) -> list[BlameLine]:
        """Phân tích output `blame --line-porcelain`."""

        def fail(line: bytes) -> GitError:
            logger.warning("Kết quả git blame không hợp lệ (%s): %r", path, line[:80])
            return GitError(f"Không đọc được kết quả git blame của {path}.")

        result: list[BlameLine] = []
        current: dict | None = None
        raw = out.split(b"\n")
        if raw and raw[-1] == b"":
            raw.pop()
        for line in raw:
            if current is None:
                match = _BLAME_HEADER_RE.match(line)
                if match is None:
                    raise fail(line)
                current = {"sha": match[1].decode("ascii"), "orig": int(match[2]) - 1,
                           "line": int(match[3]) - 1, "boundary": False, "filename": None}
            elif line.startswith(b"\t"):
                if current["filename"] is None:
                    raise fail(line)
                result.append(BlameLine(current["line"], current["sha"], current["orig"],
                                        current["filename"], current["boundary"]))
                current = None
            elif line == b"boundary":
                current["boundary"] = True
            elif line.startswith(b"filename "):
                current["filename"] = _decode_path(_unquote_c(line[len(b"filename "):]), path)
        if current is not None:
            raise fail(b"<missing content line>")
        return result

    def rev_list(self, include: str, exclude: str | None = None, paths: Sequence[str] = (), *,
                 ancestry_path: bool = False, reverse: bool = False) -> list[str]:
        """SHA commit trong `exclude..include` (exclude None → mọi tổ tiên) chạm `paths`.

        Thứ tự topo (mới → cũ; reverse → cũ → mới).
        """
        _check_sha(include)
        if exclude is not None:
            _check_sha(exclude)
        args = ["--literal-pathspecs", "rev-list", "--topo-order"]
        if ancestry_path:
            args.append("--ancestry-path")
        if reverse:
            args.append("--reverse")
        args.append(include)
        if exclude is not None:
            args.append(f"^{exclude}")
        out = self.run([*args, "--", *paths]).decode("ascii", "replace")
        return [line for line in out.split() if line]

    def first_commit_after(self, since: str, until: str, paths: Sequence[str]) -> str | None:
        """Commit cũ nhất trong `--ancestry-path since..until` chạm `paths`; None nếu không có."""
        commits = self.rev_list(until, since, paths, ancestry_path=True, reverse=True)
        return commits[0] if commits else None

    def paths_exist(self, items: Sequence[tuple[str, str]]) -> list[bool]:
        """Với mỗi (commit, path): path có trong cây của commit không. Giữ thứ tự đầu vào."""
        items = list(items)
        for commit, _ in items:
            _check_sha(commit)
        result: list[bool | None] = [None] * len(items)
        # cat-file đọc stdin theo dòng và bỏ "\r" trước "\n" → các path này tra riêng
        batch = [i for i, (_, path) in enumerate(items) if "\n" not in path and "\r" not in path]
        if batch:
            stdin = b"".join(f"{items[i][0]}:{items[i][1]}\n".encode() for i in batch)
            lines = self.run(["cat-file", "--batch-check"], stdin=stdin).split(b"\n")
            if lines and lines[-1] == b"":
                lines.pop()
            if len(lines) != len(batch):
                logger.warning("cat-file --batch-check trả %d dòng, cần %d", len(lines),
                               len(batch))
                raise GitError("Không đọc được kết quả kiểm tra đường dẫn.")
            for i, line in zip(batch, lines, strict=True):
                parts = line.split(b" ")
                is_sha = _SHA_RE.fullmatch(parts[0].decode("ascii", "replace")) is not None
                if is_sha and (len(parts) == 3 or parts[1:] == [b"submodule"]):
                    result[i] = True  # gitlink (submodule) tính là tồn tại
                elif line.endswith(b" missing"):
                    result[i] = False
                else:
                    logger.warning("Kết quả cat-file --batch-check lạ: %r", line[:80])
                    raise GitError("Không đọc được kết quả kiểm tra đường dẫn.")
        for i, (commit, path) in enumerate(items):
            if result[i] is None:
                # rev-parse chỉ phân giải entry; cat-file -e đòi object (gitlink sẽ sai)
                proc = self._exec(["rev-parse", "--verify", "--quiet", f"{commit}:{path}"],
                                  allow_fail=True)
                result[i] = proc.returncode == 0
        return [bool(r) for r in result]

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """ancestor là tổ tiên (hoặc chính là) descendant (D29)."""
        _check_sha(ancestor, descendant)
        proc = self._exec(["merge-base", "--is-ancestor", ancestor, descendant],
                          allow_fail=True)
        if proc.returncode not in (0, 1):
            self._raise_failed(proc)
        return proc.returncode == 0

    def merge_bases(self, a: str, b: str) -> list[str]:
        """Mọi merge-base tốt nhất của a và b, sắp tăng dần; không có tổ tiên chung → [] (D29)."""
        _check_sha(a, b)
        proc = self._exec(["merge-base", "--all", a, b], allow_fail=True)
        if proc.returncode == 1 and not proc.stdout.strip():
            return []
        if proc.returncode != 0:
            self._raise_failed(proc)
        bases: set[str] = set()
        for line in proc.stdout.decode("ascii", "replace").splitlines():
            if not _SHA_RE.fullmatch(line):
                logger.warning("Kết quả merge-base lạ: %r", line[:80])
                raise GitError("Không đọc được kết quả merge-base.")
            bases.add(line)
        return sorted(bases)
