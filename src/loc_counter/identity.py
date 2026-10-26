"""Gộp tác giả (tên, email) thành account key; bot; identities.yaml; GitHub API (§3.5)."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests
import requests.auth
import yaml

from loc_counter.config import LocCounterError
from loc_counter.git_repo import LogCommit

logger = logging.getLogger(__name__)

BOT_MARKERS: tuple[str, ...] = ("[bot]", "dependabot", "renovate", "github-actions")
DEFAULT_LOGIN_CACHE: Path = Path.home() / ".loc_counter" / "github_logins.json"
GITHUB_API = "https://api.github.com"

_NOREPLY_RE = re.compile(r"^(?:\d+\+)?([^@+]+)@users\.noreply\.github\.com$")
_RULE_KEYS = ("account", "email", "name")
_CACHE_VERSION = 1


class IdentityError(LocCounterError):
    """Lỗi đọc/ghi identities.yaml; thông báo tiếng Việt."""


@dataclass(frozen=True)
class IdentityRule:
    """Một quy tắc ánh xạ thủ công: email hoặc tên → account."""

    account: str
    email: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class IdentityMap:
    """Bảng ánh xạ thủ công từ identities.yaml."""

    rules: tuple[IdentityRule, ...] = ()
    _by_email: dict[str, str] = field(default_factory=dict, compare=False, repr=False)
    _by_name: dict[str, str] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        for rule in self.rules:
            if rule.email:
                self._by_email.setdefault(rule.email.strip().lower(), rule.account)
            if rule.name:
                self._by_name.setdefault(rule.name.strip().lower(), rule.account)

    def lookup_email(self, email: str) -> str | None:
        """Account của email (không phân biệt hoa thường)."""
        return self._by_email.get(email.strip().lower())

    def lookup_name(self, name: str) -> str | None:
        """Account của tên (không phân biệt hoa thường)."""
        return self._by_name.get(name.strip().lower())

    def lookup(self, name: str, email: str) -> str | None:
        """Account theo email trước, rồi theo tên; None nếu không có."""
        return self.lookup_email(email) or self.lookup_name(name)


def _parse_rules(data: Any) -> tuple[IdentityRule, ...]:
    if data is None:
        return ()
    if not isinstance(data, dict):
        raise IdentityError('File identities phải có dạng "identities: [danh sách]"')
    entries = data.get("identities")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise IdentityError('File identities phải có dạng "identities: [danh sách]"')
    unknown = sorted(str(k) for k in data if k != "identities")
    if unknown:
        raise IdentityError(f"Key không hợp lệ trong identities.yaml: {', '.join(unknown)}")
    rules: list[IdentityRule] = []
    owners: dict[tuple[str, str], str] = {}
    for index, item in enumerate(entries, start=1):
        prefix = f"Mục {index} trong identities.yaml"
        if not isinstance(item, dict):
            raise IdentityError(f"{prefix}: phải là mapping (account, email, name)")
        bad = sorted(str(k) for k in item if k not in _RULE_KEYS)
        if bad:
            raise IdentityError(f"{prefix}: key không hợp lệ {', '.join(bad)}")
        values: dict[str, str | None] = {}
        for key in _RULE_KEYS:
            value = item.get(key)
            if value is not None and not isinstance(value, str):
                raise IdentityError(f"{prefix}: {key} phải là chuỗi")
            values[key] = value.strip() if isinstance(value, str) and value.strip() else None
        if values["account"] is None:
            raise IdentityError(f"{prefix}: cần account")
        if values["email"] is None and values["name"] is None:
            raise IdentityError(f"{prefix}: cần email hoặc name")
        rule = IdentityRule(values["account"], values["email"], values["name"])  # type: ignore[arg-type]
        for kind, label, value in (("email", "Email", rule.email), ("name", "Tên", rule.name)):
            if value is None:
                continue
            key = (kind, value.lower())
            previous = owners.setdefault(key, rule.account)
            if previous != rule.account:
                raise IdentityError(f"{label} {value.lower()} được gán cho nhiều account: "
                                    f"{previous}, {rule.account}")
        if rule not in rules:
            rules.append(rule)
    return tuple(rules)


def load_identities(path: Path | None) -> IdentityMap:
    """Đọc identities.yaml; path None → không có quy tắc."""
    if path is None:
        return IdentityMap()
    path = Path(path)
    if not path.is_file():
        raise IdentityError(f"Không tìm thấy file identities: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IdentityError(f"File identities phải là văn bản UTF-8: {path}") from exc
    except OSError as exc:
        raise IdentityError(f"Không đọc được file identities: {path} ({exc})") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (dòng {mark.line + 1})" if mark is not None else ""
        raise IdentityError(f"File identities sai cú pháp YAML: {path}{where}") from exc
    return IdentityMap(_parse_rules(data))


def save_identities(path: Path, identity_map: IdentityMap) -> None:
    """Ghi identities.yaml (thứ tự cố định, UTF-8)."""
    path = Path(path)
    rules = sorted(identity_map.rules, key=lambda r: (r.account, r.email or "", r.name or ""))
    items = []
    for rule in rules:
        item: dict[str, str] = {}
        if rule.email:
            item["email"] = rule.email
        if rule.name:
            item["name"] = rule.name
        item["account"] = rule.account
        items.append(item)
    _parse_rules({"identities": items})  # cùng kiểm tra như khi đọc; lỗi → không ghi file
    text = yaml.safe_dump({"identities": items}, allow_unicode=True, sort_keys=False)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError as exc:
        if tmp.parent.is_dir():
            tmp.unlink(missing_ok=True)
        logger.error("Không ghi được %s: %s", path, exc)
        raise IdentityError(f"Không ghi được file identities {path}: {exc}") from exc


def key_from_email(email: str, name: str = "") -> str:
    """noreply GitHub → login; còn lại email chữ thường; email rỗng → tên chữ thường."""
    e = email.strip().lower()
    match = _NOREPLY_RE.match(e)
    if match:
        return match[1]
    if not e:
        return name.strip().lower() or "(không rõ)"
    return e


def is_bot_text(text: str) -> bool:
    """Tên/email/key có dấu hiệu bot (§3.5)."""
    lowered = text.lower()
    return any(marker in lowered for marker in BOT_MARKERS)


def github_repo_of(source: str) -> tuple[str, str] | None:
    """(owner, repo) nếu source là https://github.com/<owner>/<repo>[.git]."""
    parts = urlsplit(source)
    if parts.scheme.lower() != "https" or parts.netloc.lower() != "github.com":
        return None
    segments = [s for s in parts.path.strip("/").split("/") if s]
    if len(segments) != 2:
        return None
    owner, repo = segments
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return (owner, repo) if owner and repo else None


class _Session(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float,
            auth: requests.auth.AuthBase) -> Any: ...


class _BearerAuth(requests.auth.AuthBase):
    """Header Bearer tường minh — `~/.netrc` không ghi đè được."""

    def __init__(self, token: str) -> None:
        self.__token = token

    def __repr__(self) -> str:
        return "_BearerAuth(***)"

    def __call__(self, request: Any) -> Any:
        request.headers["Authorization"] = f"Bearer {self.__token}"
        return request


class GitHubLoginResolver:
    """Tra login GitHub theo email qua API commit, có cache bền email → login."""

    def __init__(self, owner: str, repo: str, token: str, cache_path: Path | None = None,
                 session: _Session | None = None, timeout: float = 10.0) -> None:
        self._owner = owner
        self._repo = repo
        self.__token = token
        self._cache_path = Path(cache_path) if cache_path else DEFAULT_LOGIN_CACHE
        self._session: _Session = session or requests.Session()
        self._timeout = timeout
        self._cache = self._load_cache()
        self._disabled = False
        self._warnings: list[str] = []
        self._requests = 0

    def __repr__(self) -> str:
        return f"GitHubLoginResolver(owner={self._owner!r}, repo={self._repo!r})"

    @property
    def warnings(self) -> list[str]:
        """Cảnh báo tiếng Việt (không chứa token)."""
        return list(self._warnings)

    @property
    def requests_made(self) -> int:
        """Số request đã gửi tới GitHub API."""
        return self._requests

    def _load_cache(self) -> dict[str, str | None]:
        if not self._cache_path.is_file():
            return {}
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if data.get("version") != _CACHE_VERSION or not isinstance(data.get("logins"), dict):
                raise ValueError("sai phiên bản cache")
            return {str(k): (str(v) if v is not None else None)
                    for k, v in data["logins"].items()}
        except (OSError, ValueError, AttributeError) as exc:
            logger.warning("Bỏ qua cache login GitHub hỏng %s: %s", self._cache_path, exc)
            return {}

    def _save_cache(self) -> None:
        data = {"version": _CACHE_VERSION, "logins": self._cache}
        tmp = self._cache_path.with_name(self._cache_path.name + ".tmp")
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2),
                           encoding="utf-8")
            os.replace(tmp, self._cache_path)
        except OSError as exc:
            logger.warning("Không ghi được cache login GitHub %s: %s", self._cache_path, exc)
            if tmp.parent.is_dir():
                tmp.unlink(missing_ok=True)

    def _warn(self, message: str) -> None:
        if message not in self._warnings:
            self._warnings.append(message)
            logger.warning("%s", message)

    def login_for(self, email: str, sha: str) -> str | None:
        """Login GitHub (chữ thường) của tác giả commit; None nếu không xác định."""
        key = email.strip().lower()
        if key in self._cache:
            return self._cache[key]
        if self._disabled:
            return None
        url = f"{GITHUB_API}/repos/{self._owner}/{self._repo}/commits/{sha}"
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        self._requests += 1
        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout,
                                         auth=_BearerAuth(self.__token))
        except requests.RequestException as exc:
            self._disabled = True
            self._warn(f"Không gọi được GitHub API ({type(exc).__name__}); "
                       "dùng email làm account.")
            return None
        status = response.status_code
        if status == 200:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if not isinstance(payload, dict):
                self._disabled = True
                self._warn("GitHub API trả dữ liệu không hợp lệ; dùng email làm account.")
                return None
            author = payload.get("author")
            login = author.get("login") if isinstance(author, dict) else None
            value = login.lower() if isinstance(login, str) and login else None
            self._cache[key] = value
            self._save_cache()
            return value
        if status in (404, 422):
            logger.info("GitHub API %s cho commit %s; dùng email", status, sha[:7])
            return None
        self._disabled = True
        if status == 401:
            self._warn("GitHub API từ chối token (401); dùng email làm account.")
        elif status in (403, 429):
            self._warn(f"GitHub API hết lượt gọi hoặc bị chặn ({status}); "
                       "các email còn lại dùng email làm account.")
        else:
            self._warn(f"GitHub API lỗi {status}; dùng email làm account.")
        return None


@dataclass(frozen=True)
class Identity:
    """Một cặp (tên, email) author gốc."""

    name: str
    email: str


class _LoginLookup(Protocol):
    warnings: list[str]

    def login_for(self, email: str, sha: str) -> str | None: ...


class AccountResolver:
    """Quy commit về account key theo thứ tự §3.5."""

    def __init__(self, identities: IdentityMap | None = None,
                 github: _LoginLookup | None = None) -> None:
        self.identities = identities or IdentityMap()
        self.github = github
        self._memo: dict[tuple[str, str, str, str], str] = {}

    def resolve(self, commit: LogCommit) -> str:
        """Account key của author commit."""
        memo_key = (commit.author_name, commit.author_email, commit.mapped_name,
                    commit.mapped_email)
        cached = self._memo.get(memo_key)
        if cached is not None:
            return cached
        ids = self.identities
        account = (ids.lookup_email(commit.author_email) or ids.lookup_email(commit.mapped_email)
                   or ids.lookup_name(commit.author_name) or ids.lookup_name(commit.mapped_name))
        if account is None:
            mailmapped = ((commit.mapped_name, commit.mapped_email.lower())
                          != (commit.author_name, commit.author_email.lower()))
            if mailmapped:
                account = key_from_email(commit.mapped_email, commit.mapped_name)
            elif self.github is not None:
                account = self.github.login_for(commit.author_email, commit.sha)
        if account is None:
            account = key_from_email(commit.author_email, commit.author_name)
        self._memo[memo_key] = account
        return account


@dataclass
class UserSummary:
    """Một account trong kỳ."""

    account: str
    commits: int
    merge_commits: int
    identities: list[Identity]
    is_bot: bool


@dataclass
class UsersResult:
    """Danh sách user trong kỳ và cảnh báo."""

    users: list[UserSummary]
    warnings: list[str]


def summarize_users(commits: Sequence[LogCommit], resolver: AccountResolver) -> UsersResult:
    """Gộp commit theo account; sắp xếp số commit giảm dần, rồi account tăng dần."""
    counts: dict[str, list[int]] = {}
    identities: dict[str, set[Identity]] = {}
    for commit in commits:
        account = resolver.resolve(commit)
        stats = counts.setdefault(account, [0, 0])
        stats[1 if commit.is_merge else 0] += 1
        identities.setdefault(account, set()).add(Identity(commit.author_name, commit.author_email))
    users = []
    for account, (normal, merges) in counts.items():
        ids = sorted(identities[account], key=lambda i: (i.email.lower(), i.name, i.email))
        bot = is_bot_text(account) or any(is_bot_text(i.name) or is_bot_text(i.email)
                                          for i in ids)
        users.append(UserSummary(account, normal, merges, ids, bot))
    users.sort(key=lambda u: (-u.commits, u.account))
    warnings = list(resolver.github.warnings) if resolver.github is not None else []
    return UsersResult(users, warnings)


class _HasSha(Protocol):
    sha: str


class _SnapshotsLike(Protocol):
    c_start: _HasSha | None
    c_end: _HasSha


class _RepoLike(Protocol):
    source: str

    def log_commits(self, c_end: str, c_start: str | None = None,
                    mailmap_rev: str | None = None) -> list[LogCommit]: ...


def list_period_users(repo: _RepoLike, snapshots: _SnapshotsLike,
                      identities: IdentityMap | None = None, token: str | None = None,
                      login_cache: Path | None = None) -> UsersResult:
    """log_commits(C_END, C_START, mailmap_rev=C_END) → summarize; bật GitHub API khi được phép."""
    c_end = snapshots.c_end.sha
    c_start = snapshots.c_start.sha if snapshots.c_start else None
    commits = repo.log_commits(c_end, c_start, mailmap_rev=c_end)
    gh_repo = github_repo_of(repo.source)
    github = None
    if gh_repo is not None and token:
        github = GitHubLoginResolver(*gh_repo, token, cache_path=login_cache)
    result = summarize_users(commits, AccountResolver(identities, github))
    logger.info("%d user, %d commit trong kỳ; %d request GitHub API", len(result.users),
                len(commits), getattr(github, "requests_made", 0))
    return result
