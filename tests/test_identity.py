"""Test cho identity.py (spec docs/specs/identity.md)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from loc_counter import identity
from loc_counter.git_repo import GitRepo, LogCommit
from loc_counter.identity import (
    AccountResolver,
    GitHubLoginResolver,
    Identity,
    IdentityError,
    IdentityMap,
    IdentityRule,
    github_repo_of,
    is_bot_text,
    key_from_email,
    list_period_users,
    load_identities,
    save_identities,
    summarize_users,
)
from loc_counter.snapshot import find_snapshots, make_period

TOKEN = "ghp_SECRET123"
NL = chr(10)
BKK = timezone(timedelta(hours=7))
JAN = (date(2026, 1, 1), date(2026, 1, 31))


def _commit(sha_char: str, name: str, email: str, mapped: tuple[str, str] | None = None,
            parents: int = 1) -> LogCommit:
    mn, me = mapped or (name, email)
    return LogCommit(sha_char * 40, tuple("p" * 40 for _ in range(parents)), name, email,
                     mn, me, datetime(2026, 1, 2, tzinfo=BKK))


class FakeResponse:
    def __init__(self, status: int, payload: object = None) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        return self._payload


class FakeSession:
    """Session giả: trả lần lượt các phản hồi trong `responses` (hoặc ném exception)."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, headers: dict, timeout: float, auth=None) -> FakeResponse:  # noqa: ANN001
        request = SimpleNamespace(headers=dict(headers))
        if auth is not None:
            auth(request)
        self.calls.append((url, request.headers))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


def _resolver(tmp_path: Path, *responses: object) -> tuple[GitHubLoginResolver, FakeSession]:
    session = FakeSession(*responses)
    return GitHubLoginResolver("o", "r", TOKEN, cache_path=tmp_path / "logins.json",
                               session=session), session


# ---------- hàm thuần ----------

def test_key_from_email() -> None:
    """TC-identity-01: email chữ thường, noreply → login, email rỗng → tên."""
    assert key_from_email("Alice@Corp.COM") == "alice@corp.com"
    assert key_from_email("12345+Alice@users.noreply.github.com") == "alice"
    assert key_from_email("bob@users.noreply.github.com") == "bob"
    assert key_from_email("", "Bình") == "bình"
    assert key_from_email("", "") == "(không rõ)"


def test_is_bot_text() -> None:
    """TC-identity-02: nhận diện bot không phân biệt hoa thường."""
    for text in ("dependabot[bot]", "Renovate Bot", "github-actions",
                 "41898282+github-actions[bot]@users.noreply.github.com"):
        assert is_bot_text(text), text
    assert not is_bot_text("alice")


SAMPLE = """identities:
  - email: alice@corp.com
    account: alice
  - email: 12345+alice@users.noreply.github.com
    account: alice
  - name: "Alice N"
    account: alice
"""


def test_load_identities(tmp_path: Path) -> None:
    """TC-identity-03: đọc file hợp lệ (có BOM), tra theo email rồi theo tên."""
    path = tmp_path / "identities.yaml"
    path.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
    m = load_identities(path)
    assert m.lookup("x", "ALICE@corp.com") == "alice"
    assert m.lookup("x", "12345+alice@users.noreply.github.com") == "alice"
    assert m.lookup("alice n", "z@z") == "alice"
    assert m.lookup("nobody", "z@z") is None
    assert load_identities(None).lookup("a", "b") is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("identities: [\n  - email: a\n", "sai cú pháp YAML"),
        ("- email: a@b\n  account: a\n", 'phải có dạng "identities: [danh sách]"'),
        ("identities: []\nfoo: 1\n", "Key không hợp lệ trong identities.yaml: foo"),
        ("identities:\n  - email: a@b\n", "Mục 1 trong identities.yaml: cần account"),
        ("identities:\n  - account: a\n", "Mục 1 trong identities.yaml: cần email hoặc name"),
        ("identities:\n  - email: 5\n    account: a\n",
         "Mục 1 trong identities.yaml: email phải là chuỗi"),
        ("identities:\n  - email: a@b\n    account: a\n    x: 1\n",
         "Mục 1 trong identities.yaml: key không hợp lệ x"),
        ("identities:\n  - email: A@b\n    account: a\n  - email: a@B\n    account: b\n",
         "Email a@b được gán cho nhiều account: a, b"),
    ],
)
def test_load_identities_errors(tmp_path: Path, content: str, message: str) -> None:
    """TC-identity-04: lỗi file identities có thông báo tiếng Việt."""
    path = tmp_path / "identities.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(IdentityError) as exc:
        load_identities(path)
    assert message in str(exc.value)


def test_load_identities_missing(tmp_path: Path) -> None:
    """TC-identity-04: file không tồn tại."""
    with pytest.raises(IdentityError, match="Không tìm thấy file identities"):
        load_identities(tmp_path / "nope.yaml")


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """TC-identity-05: ghi rồi đọc lại cùng quy tắc; thứ tự cố định; ghi 2 lần trùng byte."""
    m = IdentityMap((
        IdentityRule("zed", email="z@x.vn"),
        IdentityRule("bình", name="Nguyễn Bình"),
        IdentityRule("an", email="an@x.vn", name="An"),
    ))
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    save_identities(a, m)
    save_identities(b, load_identities(a))
    assert a.read_bytes() == b.read_bytes()
    loaded = load_identities(a)
    assert set(loaded.rules) == set(m.rules)
    assert [r.account for r in loaded.rules] == ["an", "bình", "zed"]
    assert "Nguyễn Bình" in a.read_text(encoding="utf-8")


def test_github_repo_of(tmp_path: Path) -> None:
    """TC-identity-06: nhận diện repo GitHub từ URL."""
    assert github_repo_of("https://github.com/o/r") == ("o", "r")
    assert github_repo_of("https://github.com/o/r.git") == ("o", "r")
    assert github_repo_of("https://GitHub.com/o/r/") == ("o", "r")
    for other in ("https://gitlab.com/o/r", "git@github.com:o/r.git", "https://github.com/o",
                  str(tmp_path)):
        assert github_repo_of(other) is None, other


# ---------- resolver ----------

def test_priority_order(tmp_path: Path) -> None:
    """TC-identity-07: identities.yaml > .mailmap > GitHub API > email."""
    commit = _commit("a", "alice", "x@y.com", mapped=("Alice", "alice@corp.com"))
    manual = IdentityMap((IdentityRule("alice-manual", email="x@y.com"),))
    gh, _ = _resolver(tmp_path, FakeResponse(200, {"author": {"login": "Alice-GH"}}))
    assert AccountResolver(manual, gh).resolve(commit) == "alice-manual"
    assert AccountResolver(IdentityMap(), gh).resolve(commit) == "alice@corp.com"
    plain = _commit("b", "alice", "x@y.com")
    assert AccountResolver(IdentityMap(), gh).resolve(plain) == "alice-gh"
    gh_none, _ = _resolver(tmp_path / "n", FakeResponse(200, {"author": None}))
    assert AccountResolver(IdentityMap(), gh_none).resolve(plain) == "x@y.com"


def test_github_cache(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """TC-identity-08: 1 request / email, cache bền, header đúng, token không bị lưu/log."""
    caplog.set_level(logging.DEBUG)
    gh, session = _resolver(tmp_path, FakeResponse(200, {"author": {"login": "Alice"}}),
                            FakeResponse(200, {"author": None}))
    assert gh.login_for("Alice@X.com", "1" * 40) == "alice"
    assert gh.login_for("alice@x.com", "2" * 40) == "alice"
    assert gh.login_for("ghost@x.com", "3" * 40) is None
    assert gh.requests_made == 2 and len(session.calls) == 2
    url, headers = session.calls[0]
    assert url == "https://api.github.com/repos/o/r/commits/" + "1" * 40
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Accept"] == "application/vnd.github+json"
    cache_text = (tmp_path / "logins.json").read_text(encoding="utf-8")
    assert json.loads(cache_text) == {"version": 1,
                                      "logins": {"alice@x.com": "alice", "ghost@x.com": None}}
    assert TOKEN not in cache_text and TOKEN not in caplog.text and TOKEN not in repr(gh)
    gh2, session2 = _resolver(tmp_path)
    assert gh2.login_for("alice@x.com", "1" * 40) == "alice"
    assert gh2.login_for("ghost@x.com", "1" * 40) is None
    assert session2.calls == [] and gh2.requests_made == 0


@pytest.mark.parametrize(
    ("first", "warning"),
    [
        (FakeResponse(401), "GitHub API từ chối token (401)"),
        (FakeResponse(403), "GitHub API hết lượt gọi hoặc bị chặn (403)"),
        (FakeResponse(429), "GitHub API hết lượt gọi hoặc bị chặn (429)"),
        (FakeResponse(500), "GitHub API lỗi 500"),
        (requests.ConnectionError("boom https://api.github.com"),
         "Không gọi được GitHub API (ConnectionError)"),
    ],
)
def test_github_errors_disable(tmp_path: Path, first: object, warning: str) -> None:
    """TC-identity-09: lỗi API → cảnh báo, tắt resolver, dùng email."""
    gh, session = _resolver(tmp_path, first)
    resolver = AccountResolver(IdentityMap(), gh)
    assert resolver.resolve(_commit("a", "a", "a@x.com")) == "a@x.com"
    assert resolver.resolve(_commit("b", "b", "b@x.com")) == "b@x.com"
    assert len(session.calls) == 1
    assert len(gh.warnings) == 1 and warning in gh.warnings[0]
    assert TOKEN not in gh.warnings[0]


def test_github_404_not_fatal(tmp_path: Path) -> None:
    """TC-identity-09: 404 → None, không cảnh báo, không tắt, không cache."""
    gh, session = _resolver(tmp_path, FakeResponse(404),
                            FakeResponse(200, {"author": {"login": "bob"}}))
    assert gh.login_for("a@x.com", "1" * 40) is None
    assert gh.login_for("b@x.com", "2" * 40) == "bob"
    assert gh.warnings == [] and len(session.calls) == 2
    assert "a@x.com" not in json.loads((tmp_path / "logins.json").read_text("utf-8"))["logins"]


class _StubRepo:
    def __init__(self, source: str, commits: list[LogCommit]) -> None:
        self.source = source
        self._commits = commits

    def log_commits(self, c_end, c_start=None, mailmap_rev=None):  # noqa: ANN001, ANN201
        return self._commits


class _StubSnapshots:
    class _C:
        sha = "e" * 40

    c_start = None
    c_end = _C()


def test_github_only_when_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-identity-10: chỉ tạo GitHub resolver với nguồn github.com + token."""
    created: list[tuple] = []

    class SpyResolver:
        def __init__(self, *args, **kwargs) -> None:
            created.append(args)
            self.warnings: list[str] = []

        def login_for(self, email: str, sha: str) -> None:
            return None

    monkeypatch.setattr(identity, "GitHubLoginResolver", SpyResolver)
    commits = [_commit("a", "a", "a@x.com")]
    cases = [(str(tmp_path), TOKEN), ("https://github.com/o/r", None),
             ("https://gitlab.com/o/r", TOKEN)]
    for source, token in cases:
        list_period_users(_StubRepo(source, commits), _StubSnapshots(), token=token,
                          login_cache=tmp_path / "c.json")
    assert created == []
    list_period_users(_StubRepo("https://github.com/o/r", commits), _StubSnapshots(),
                      token=TOKEN, login_cache=tmp_path / "c.json")
    assert created and created[0][:3] == ("o", "r", TOKEN)


# ---------- tích hợp với repo thật ----------

def _users(src, cache_root: Path, identities: IdentityMap | None = None,
           period=None):  # noqa: ANN001, ANN202
    repo = GitRepo.open(str(src.path), cache_root=cache_root)
    snaps = find_snapshots(repo, "main", period or make_period(*JAN))
    return list_period_users(repo, snaps, identities)


ALICE_CORP = ("alice", "alice@corp.com")
ALICE_NOREPLY = ("alice", "12345+alice@users.noreply.github.com")


def test_mailmap_merges(make_repo, cache_root: Path) -> None:
    """TC-identity-11: .mailmap gộp noreply vào email công ty."""
    src = make_repo()
    src.commit("base", "2025-12-01T10:00:00+07:00", files={"a.py": "x = 0" + NL})
    src.commit("a1", "2026-01-02T10:00:00+07:00", author=ALICE_CORP, files={"a.py": "x = 1" + NL})
    src.commit("a2", "2026-01-03T10:00:00+07:00", author=ALICE_NOREPLY, files={
        "a.py": "x = 2" + NL,
        ".mailmap": "Alice <alice@corp.com> <12345+alice@users.noreply.github.com>" + NL})
    result = _users(src, cache_root)
    assert [(u.account, u.commits) for u in result.users] == [("alice@corp.com", 2)]
    assert result.users[0].identities == [Identity(*ALICE_NOREPLY), Identity(*ALICE_CORP)]


def test_identities_merge_noreply_and_corp(make_repo, cache_root: Path) -> None:
    """TC-identity-12: noreply GitHub + email công ty gộp qua identities.yaml (§14)."""
    src = make_repo()
    src.commit("base", "2025-12-01T10:00:00+07:00", files={"a.py": "x = 0" + NL})
    src.commit("a1", "2026-01-02T10:00:00+07:00", author=ALICE_CORP, files={"a.py": "x = 1" + NL})
    src.commit("a2", "2026-01-03T10:00:00+07:00", author=ALICE_NOREPLY,
               files={"a.py": "x = 2" + NL})
    rules = IdentityMap((IdentityRule("alice", email="alice@corp.com"),
                         IdentityRule("alice", email="12345+alice@users.noreply.github.com")))
    result = _users(src, cache_root, rules)
    assert [(u.account, u.commits) for u in result.users] == [("alice", 2)]


def test_default_keys_not_merged(make_repo, cache_root: Path) -> None:
    """TC-identity-13: không quy tắc → noreply thành login, email chữ thường, không tự gộp."""
    src = make_repo()
    src.commit("base", "2025-12-01T10:00:00+07:00", files={"a.py": "x = 0" + NL})
    src.commit("b1", "2026-01-02T10:00:00+07:00", author=("Bob", "Bob@Corp.com"),
               files={"a.py": "x = 1" + NL})
    src.commit("b2", "2026-01-03T10:00:00+07:00",
               author=("bob", "999+bob@users.noreply.github.com"),
               files={"a.py": "x = 2" + NL})
    result = _users(src, cache_root)
    assert sorted(u.account for u in result.users) == ["bob", "bob@corp.com"]


def test_author_not_committer_and_merge(make_repo, cache_root: Path) -> None:
    """TC-identity-14: dùng author; merge commit không tính vào commits."""
    src = make_repo()
    src.commit("base", "2025-12-01T10:00:00+07:00", files={"a.py": "x = 0" + NL})
    src.commit("a1", "2026-01-02T10:00:00+07:00", author=("alice", "alice@x.com"),
               committer=("admin", "admin@example.com"), files={"a.py": "x = 1" + NL})
    src.checkout("feat", create=True)
    src.commit("f1", "2026-01-03T10:00:00+07:00", author=("alice", "alice@x.com"),
               files={"b.py": "y = 1" + NL})
    src.checkout("main")
    src.merge("feat", "merge", "2026-01-04T10:00:00+07:00", author=("bob", "bob@x.com"))
    result = _users(src, cache_root)
    stats = {u.account: (u.commits, u.merge_commits) for u in result.users}
    assert stats == {"alice@x.com": (2, 0), "bob@x.com": (0, 1)}
    assert [u.account for u in result.users] == ["alice@x.com", "bob@x.com"]


def test_section14_users_with_bot(section14_repo, cache_root: Path) -> None:
    """TC-identity-15: repo §14 + bot: alice 2, bob 2, dependabot[bot] 1 (bot); không có admin."""
    s14 = section14_repo(bot=True)
    result = _users(s14.src, cache_root)
    rows = [(u.account, u.commits, u.is_bot) for u in result.users]
    assert rows == [("alice@example.com", 2, False), ("bob@example.com", 2, False),
                    ("dependabot[bot]", 1, True)]
    assert result.warnings == []


def test_no_c_start(section14_repo, cache_root: Path) -> None:
    """TC-identity-16: C_START rỗng → đếm mọi commit tới C_END (có admin)."""
    s14 = section14_repo()
    result = _users(s14.src, cache_root, period=make_period(date(2025, 1, 1), JAN[1]))
    stats = {u.account: u.commits for u in result.users}
    assert stats == {"admin@example.com": 1, "alice@example.com": 2, "bob@example.com": 2}


def test_mailmap_after_end_ignored(make_repo, cache_root: Path) -> None:
    """TC-identity-17: .mailmap chỉ thêm sau end → không áp dụng."""
    src = make_repo()
    src.commit("base", "2025-12-01T10:00:00+07:00", files={"a.py": "x = 0" + NL})
    src.commit("a1", "2026-01-02T10:00:00+07:00", author=ALICE_NOREPLY,
               files={"a.py": "x = 1" + NL})
    src.commit("mm", "2026-02-02T10:00:00+07:00", files={
        ".mailmap": "Alice <alice@corp.com> <12345+alice@users.noreply.github.com>" + NL})
    result = _users(src, cache_root)
    assert [u.account for u in result.users] == ["alice"]


def test_summarize_sorting() -> None:
    """TC-identity-15: sắp xếp (-commits, account); identities không trùng, sắp xếp."""
    commits = [_commit("1", "b", "b@x.com"), _commit("2", "a", "a@x.com"),
               _commit("3", "B", "b@x.com"), _commit("4", "c", "c@x.com", parents=2)]
    result = summarize_users(commits, AccountResolver())
    assert [(u.account, u.commits, u.merge_commits) for u in result.users] == [
        ("b@x.com", 2, 0), ("a@x.com", 1, 0), ("c@x.com", 0, 1)]
    assert result.users[0].identities == [Identity("B", "b@x.com"), Identity("b", "b@x.com")]


def test_mapped_identity_rule_email_wins() -> None:
    """TC-identity-18: quy tắc email khớp identity sau .mailmap thắng quy tắc tên gốc."""
    commit = _commit("a", "alice", "12345+alice@users.noreply.github.com",
                     mapped=("Alice", "alice@corp.com"))
    rules = IdentityMap((IdentityRule("A", email="alice@corp.com"),
                         IdentityRule("B", name="alice")))
    assert AccountResolver(rules).resolve(commit) == "A"
    only_name = IdentityMap((IdentityRule("B", name="alice"),))
    assert AccountResolver(only_name).resolve(commit) == "B"


ORDER_SCRIPT = """
from datetime import datetime, timezone
from loc_counter.git_repo import LogCommit
from loc_counter.identity import AccountResolver, IdentityMap, IdentityRule, summarize_users
d = datetime(2026, 1, 2, tzinfo=timezone.utc)
commits = [LogCommit(c * 40, ("p" * 40,), "alice", e, "alice", e, d)
           for c, e in (("1", "alice@corp.com"), ("2", "Alice@Corp.com"))]
rules = IdentityMap((IdentityRule("alice", email="alice@corp.com"),))
users = summarize_users(commits, AccountResolver(rules)).users
print("|".join(i.email for i in users[0].identities))
"""


def test_identity_order_reproducible() -> None:
    """TC-identity-19: thứ tự identity không phụ thuộc PYTHONHASHSEED."""
    outputs = set()
    for seed in range(1, 7):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        proc = subprocess.run([sys.executable, "-c", ORDER_SCRIPT], capture_output=True,
                              text=True, env=env, check=True)
        outputs.add(proc.stdout.strip())
    assert outputs == {"Alice@Corp.com|alice@corp.com"}


def test_github_bad_200(tmp_path: Path) -> None:
    """TC-identity-20: 200 với body không phải JSON object → cảnh báo, tắt, dùng email."""
    html = requests.Response()
    html.status_code = 200
    html._content = b"<html>proxy login</html>"
    html.encoding = "utf-8"
    for body in (html, FakeResponse(200, [1, 2])):
        gh, session = _resolver(tmp_path / str(id(body)), body)
        resolver = AccountResolver(IdentityMap(), gh)
        assert resolver.resolve(_commit("a", "a", "a@x.com")) == "a@x.com"
        assert resolver.resolve(_commit("b", "b", "b@x.com")) == "b@x.com"
        assert len(session.calls) == 1
        assert gh.warnings == ["GitHub API trả dữ liệu không hợp lệ; dùng email làm account."]


class _CaptureAdapter(requests.adapters.BaseAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.headers: list[dict] = []

    def send(self, request, **kwargs):  # noqa: ANN001, ANN003, ANN201
        self.headers.append(dict(request.headers))
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"author": {"login": "Zed"}}'
        response.encoding = "utf-8"
        response.request = request
        response.url = request.url
        return response

    def close(self) -> None:
        pass


def test_empty_list_save_conflict_netrc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-identity-21: `identities:` rỗng; save kiểm xung đột; netrc không ghi đè Bearer."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("identities:" + NL, encoding="utf-8")
    assert load_identities(empty).rules == ()

    target = tmp_path / "conflict.yaml"
    bad = IdentityMap((IdentityRule("a", email="x@y.com"), IdentityRule("b", email="X@y.com")))
    with pytest.raises(IdentityError, match="được gán cho nhiều account"):
        save_identities(target, bad)
    assert not target.exists()

    netrc = tmp_path / "netrc"
    netrc.write_text("machine api.github.com login u password p" + NL, encoding="utf-8")
    monkeypatch.setenv("NETRC", str(netrc))
    session = requests.Session()
    adapter = _CaptureAdapter()
    session.mount("https://", adapter)
    gh = GitHubLoginResolver("o", "r", TOKEN, cache_path=tmp_path / "c.json", session=session)
    assert gh.login_for("z@x.com", "1" * 40) == "zed"
    assert adapter.headers[0]["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("identities: {}" + NL, 'phải có dạng "identities: [danh sách]"'),
        ("identities: false" + NL, 'phải có dạng "identities: [danh sách]"'),
        ("identities:" + NL + "  - x" + NL, "Mục 1 trong identities.yaml: phải là mapping"),
        ("identities: [" + NL + "  - email: a" + NL, "(dòng "),
    ],
)
def test_load_identities_more_errors(tmp_path: Path, content: str, message: str) -> None:
    """TC-identity-04: giá trị identities sai kiểu, mục không phải mapping, số dòng lỗi YAML."""
    path = tmp_path / "identities.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(IdentityError) as exc:
        load_identities(path)
    assert message in str(exc.value)


def test_load_identities_not_utf8(tmp_path: Path) -> None:
    """TC-identity-04: file không phải UTF-8 → thông báo rõ."""
    path = tmp_path / "identities.yaml"
    path.write_bytes(SAMPLE.encode("utf-16"))
    with pytest.raises(IdentityError, match="phải là văn bản UTF-8"):
        load_identities(path)


def test_github_cache_corrupt(tmp_path: Path) -> None:
    """TC-identity-08: file cache hỏng bị bỏ qua, vẫn gọi API và ghi lại cache hợp lệ."""
    (tmp_path / "logins.json").write_text("{not json", encoding="utf-8")
    gh, session = _resolver(tmp_path, FakeResponse(200, {"author": {"login": "Q"}}))
    assert gh.login_for("q@x.com", "1" * 40) == "q"
    assert len(session.calls) == 1
    data = json.loads((tmp_path / "logins.json").read_text(encoding="utf-8"))
    assert data == {"version": 1, "logins": {"q@x.com": "q"}}
