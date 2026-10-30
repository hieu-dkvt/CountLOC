"""Test cho màn hình nhập của app.py (spec docs/specs/screen-input.md)."""

from __future__ import annotations

import hashlib
import os
import threading
import zipfile
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import requests
import streamlit as st
from test_identity import FakeResponse, FakeSession

from loc_counter import app, pipeline
from loc_counter.config import AppConfig, FilterConfig
from loc_counter.git_repo import GitRepo
from loc_counter.identity import Identity, UserSummary
from loc_counter.pipeline import PipelineError, Step

JAN = (date(2026, 1, 1), date(2026, 1, 31))
BOT = "dependabot[bot]"
TOKEN = "ghp_SECRET123"
IDS_YAML = """identities:
  - email: alice@example.com
    account: alice
  - email: bob@example.com
    account: bob
"""


# ---------- helper ----------
def pick_key(account: str) -> str:
    return "pick_" + hashlib.sha1(account.encode("utf-8")).hexdigest()[:12]


def load(at: Any, src: Path | str, period: tuple[date, date] = JAN) -> Any:
    """Nhập nguồn + kỳ rồi bấm Tải repo."""
    at.run()
    at.text_input(key="repo_source").set_value(str(src))
    at.date_input(key="start_date").set_value(period[0])
    at.date_input(key="end_date").set_value(period[1])
    at.run()
    at.button(key="load_repo").click().run()
    return at


def set_period(at: Any, start: date, end: date) -> None:
    at.date_input(key="start_date").set_value(start)
    at.date_input(key="end_date").set_value(end)
    at.run()


def values(elements: Any) -> list[str]:
    return [str(e.value) for e in elements]


def all_texts(at: Any) -> list[str]:
    out: list[str] = []
    for kind in (at.title, at.subheader, at.markdown, at.text, at.caption, at.info, at.warning,
                 at.error, at.success, at.exception):
        out += values(kind)
    out += [str(t.value) for t in at.text_input if t.key != "token"]
    return out


def pick_boxes(at: Any) -> list[Any]:
    return [c for c in at.checkbox if c.key and c.key.startswith("pick_")]


def select_mode(at: Any, mode: str) -> None:
    at.radio(key="user_mode").set_value(mode).run()


def analyze(at: Any) -> Any:
    at.button(key="analyze").click().run()
    return at


@pytest.fixture
def s14(section14_repo) -> Path:
    return section14_repo(name="repo").src.path


@pytest.fixture
def with_ids(tmp_path: Path) -> Path:
    path = tmp_path / "identities.yaml"   # CWD = tmp_path → đường dẫn mặc định
    path.write_text(IDS_YAML, encoding="utf-8")
    return path


def summary(account: str, commits: int = 1, bot: bool = False, merges: int = 0,
            ids: tuple[tuple[str, str], ...] = ()) -> UserSummary:
    return UserSummary(account, commits, merges, [Identity(n, e) for n, e in ids], bot)


# ---------- TC-01, TC-02 ----------
def test_initial_state(make_app) -> None:
    """TC-screen-input-01: tiêu đề, khối, token ẩn, mặc định, nút disabled."""
    at = make_app().run()
    assert not at.exception
    assert at.title[0].value == "ĐẾM LOC SOURCE CODE"
    assert values(at.subheader) == ["[1] REPOSITORY", "[2] THỜI ĐIỂM THỐNG KÊ", "[3] CHỌN USER"]
    assert at.expander[0].label.startswith("Tùy chọn nâng cao")
    assert at.text_input(key="token").proto.type == at.text_input(key="token").proto.PASSWORD
    assert at.radio(key="user_mode").value == "Tất cả user"
    assert at.checkbox(key="exclude_bots").value is False
    assert at.checkbox(key="separate_users").value is False
    assert at.text_input(key="out_dir").value == "output"
    assert at.button(key="load_repo").disabled
    assert at.button(key="analyze").disabled
    assert "Chưa tải repo." in values(at.info)


def test_pure_helpers() -> None:
    """TC-screen-input-02: default_dates, clean_source, timezone_*, user_label, parse_lines."""
    bkk = timezone(timedelta(hours=7))
    assert app.default_dates(datetime(2026, 10, 25, 1, 0, tzinfo=bkk)) == (
        date(2026, 10, 1), date(2026, 10, 25))
    assert app.default_dates(datetime(2026, 10, 1, 9, 0, tzinfo=bkk)) == (
        date(2026, 10, 1), date(2026, 10, 1))
    assert app.clean_source(' "D:\\x\\r" ') == "D:\\x\\r"
    assert app.clean_source("  https://github.com/o/r  ") == "https://github.com/o/r"
    at = datetime(2026, 1, 1, tzinfo=UTC)
    assert app.timezone_label("Asia/Bangkok", at) == "Asia/Bangkok (UTC+07:00)"
    assert app.timezone_label("America/St_Johns", at) == "America/St_Johns (UTC-03:30)"
    options = app.timezone_options()
    assert "UTC" in options and "Asia/Bangkok" in options and options == sorted(options)
    label = app.user_label(summary(BOT, 1, bot=True, merges=1))
    assert label == f"{BOT} (1 commit) · bot · 1 merge"
    assert app.user_label(summary("alice", 1234)) == "alice (1,234 commit)"
    assert app.parse_lines(" a \n\n b\na\n  ") == ["a", "b"]


# ---------- TC-03 .. TC-08: repo, kỳ ----------
def test_load_repo(make_app, s14: Path) -> None:
    """TC-screen-input-03: tải repo §14 — nhánh main, snapshot, danh sách user, enabled."""
    at = load(make_app(), s14)
    assert not at.exception and not at.error
    assert at.selectbox(key="branch").value == "main"
    texts = values(at.text)
    start_tail = '(2025-12-15 10:00)  "admin: app.py"'
    assert any(t.startswith("→ Snapshot start: ") and t.endswith(start_tail) for t in texts)
    assert any(t.startswith("→ Snapshot end:   ") and t.endswith('(2026-01-08 10:00)  "bob del"')
               for t in texts)
    captions = values(at.caption)
    assert "alice@example.com (2 commit)" in captions and "bob@example.com (2 commit)" in captions
    assert not at.button(key="analyze").disabled


@pytest.mark.parametrize("source", ["does-not-exist-dir", "https://u:p@github.com/o/r"])
def test_load_error(make_app, source: str) -> None:
    """TC-screen-input-04: nguồn sai / URL có credential → lỗi, không có nhánh, chặn."""
    at = load(make_app(), source)
    assert at.error and not at.exception
    expected = ("URL repo không được chứa thông tin xác thực" if "@" in source
                else "Không tìm thấy repo: does-not-exist-dir")
    assert any(expected in e for e in values(at.error))
    assert not [s for s in at.selectbox if s.key == "branch"]
    assert "Chưa tải repo." in values(at.info)
    assert at.button(key="analyze").disabled


def test_period_memo(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-05: đổi end → tính lại; gõ tìm / tick user → không tính lại."""
    calls: list[Any] = []
    orig = pipeline.prepare_period

    def spy(*a: Any, **k: Any) -> Any:
        calls.append(a)
        return orig(*a, **k)

    monkeypatch.setattr(pipeline, "prepare_period", spy)
    at = load(make_app(), s14)
    assert len(calls) == 1
    at.date_input(key="end_date").set_value(date(2026, 1, 6)).run()
    assert len(calls) == 2
    assert any(t.endswith('(2026-01-06 10:00)  "bob util"') for t in values(at.text))
    select_mode(at, "Chọn user")
    at.text_input(key="user_query").set_value("ali").run()
    at.checkbox(key=pick_key("alice@example.com")).check().run()
    assert len(calls) == 2


def test_start_after_end(make_app, s14: Path) -> None:
    """TC-screen-input-06: start >= end → lỗi, nút disabled."""
    at = load(make_app(), s14)
    set_period(at, date(2026, 2, 1), date(2026, 1, 1))
    assert any("phải trước end" in e for e in values(at.error))
    assert at.button(key="analyze").disabled


def test_no_data(make_app, s14: Path) -> None:
    """TC-screen-input-07: kỳ trước mọi commit → Không có dữ liệu, disabled."""
    at = load(make_app(), s14, (date(2020, 1, 1), date(2020, 1, 31)))
    assert any("Không có dữ liệu trong khoảng thời gian" in e for e in values(at.error))
    assert at.button(key="analyze").disabled


def test_empty_start(make_app, s14: Path) -> None:
    """TC-screen-input-08: C_START rỗng → (không có commit trước start), có admin."""
    at = load(make_app(), s14, (date(2025, 1, 1), JAN[1]))
    assert "→ Snapshot start: (không có commit trước start)" in values(at.text)
    assert "admin@example.com (1 commit)" in values(at.caption)
    assert not at.button(key="analyze").disabled


# ---------- TC-09 .. TC-12: chọn user ----------
def test_select_required(make_app, s14: Path) -> None:
    """TC-screen-input-09: Chọn user, 0 user → chặn; tick alice → chạy được."""
    at = load(make_app(), s14)
    select_mode(at, "Chọn user")
    assert "Chưa chọn user nào." in values(at.info)
    assert at.button(key="analyze").disabled
    at.checkbox(key=pick_key("alice@example.com")).check().run()
    assert "Chưa chọn user nào." not in values(at.info)
    assert not at.button(key="analyze").disabled


def test_search_keeps_selection(make_app, s14: Path) -> None:
    """TC-screen-input-10: tìm BOB chỉ hiện bob, lựa chọn alice vẫn giữ."""
    at = load(make_app(), s14)
    select_mode(at, "Chọn user")
    at.checkbox(key=pick_key("alice@example.com")).check().run()
    at.text_input(key="user_query").set_value("BOB").run()
    assert [c.label for c in pick_boxes(at)] == ["bob@example.com (2 commit)"]
    assert "Đã chọn 1 user" in values(at.caption)
    assert at.session_state["selected"] == {"alice@example.com"}


def test_bots(make_app, section14_repo) -> None:
    """TC-screen-input-11: bot có nhãn; Loại trừ bot → ẩn và bỏ khỏi lựa chọn."""
    at = load(make_app(), section14_repo(bot=True, name="repo").src.path)
    select_mode(at, "Chọn user")
    assert f"{BOT} (1 commit) · bot" in [c.label for c in pick_boxes(at)]
    at.checkbox(key=pick_key(BOT)).check().run()
    at.checkbox(key="exclude_bots").check().run()
    assert all(BOT not in c.label for c in pick_boxes(at))
    assert f"Đã bỏ chọn user không còn trong danh sách: {BOT}" in values(at.info)
    assert "Đã chọn 0 user" in values(at.caption)


def test_filter_and_reconcile() -> None:
    """TC-screen-input-12: filter_users casefold, thứ tự; reconcile_selection."""
    users = [summary("alice", 3, ids=(("Alice Nguyen", "alice@corp.com"),)),
             summary("Bob", 2, ids=(("Bob", "BOB@corp.com"),)),
             summary(BOT, 1, bot=True)]
    names = [u.account for u in app.filter_users(users, "", False)]
    assert names == ["alice", "Bob", BOT]
    assert [u.account for u in app.filter_users(users, "NGUYEN", False)] == ["alice"]
    assert [u.account for u in app.filter_users(users, "bob@", False)] == ["Bob"]
    assert [u.account for u in app.filter_users(users, "", True)] == ["alice", "Bob"]
    keep, dropped = app.reconcile_selection({"alice", "zed", BOT, "carol"}, users, True)
    assert keep == {"alice"} and dropped == ["carol", BOT, "zed"]
    assert app.reconcile_selection({"Bob"}, users, False) == ({"Bob"}, [])


# ---------- TC-13: tùy chọn nâng cao ----------
def test_advanced_options(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-input-13: form_config ↔ config_form_values; KB 0 lỗi; nạp config."""
    assert app.form_config(app.config_form_values(AppConfig()), "Asia/Bangkok") == AppConfig()
    custom = AppConfig(FilterConfig(max_file_size_kb=7, export_mode="full",
                                    exclude_dirs=("a", "b")), "UTC")
    assert app.form_config(app.config_form_values(custom), "UTC") == custom

    at = load(make_app(), s14)
    at.number_input(key="adv_max_file_size_kb").set_value(0).run()
    assert "max_file_size_kb phải là số nguyên dương" in values(at.error)
    assert at.button(key="analyze").disabled
    at.number_input(key="adv_max_file_size_kb").set_value(1024).run()
    assert not at.button(key="analyze").disabled

    cfg = tmp_path / "config.yaml"
    cfg.write_text("include_tests: false\ntimezone: UTC\nexclude_dirs: [x, y]\n", encoding="utf-8")
    at.text_input(key="config_path").set_value(str(cfg)).run()
    at.button(key="load_config").click().run()
    assert at.checkbox(key="adv_include_tests").value is False
    assert at.session_state["tz"] == "UTC"
    assert at.text_area(key="adv_exclude_dirs").value == "x\ny"

    bad = tmp_path / "bad.yaml"
    bad.write_text("filters: [\n", encoding="utf-8")
    at.text_input(key="config_path").set_value(str(bad)).run()
    at.button(key="load_config").click().run()
    assert any("File cấu hình" in e for e in values(at.error))
    assert at.checkbox(key="adv_include_tests").value is False


# ---------- TC-14 .. TC-19: phân tích ----------
def test_progress(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-14: progress_text; callback của app nhận đủ 5 bước."""
    assert app.progress_text(Step.REPORT, 5, 5) == "Bước 5/5: Tạo báo cáo…"
    assert app.progress_text(Step.EXPORT_END, 3, 5) == "Bước 3/5: Export end…"
    seen: list[tuple[Step, int, int]] = []
    orig = pipeline.run_analysis

    def spy(repo: Any, request: Any, resolver: Any, progress: Any = None, **k: Any) -> Any:
        def record(step: Step, i: int, n: int) -> None:
            seen.append((step, i, n))
            progress(step, i, n)
        return orig(repo, request, resolver, record, **k)

    monkeypatch.setattr(pipeline, "run_analysis", spy)
    at = analyze(load(make_app(), s14))
    assert not at.exception and not at.error
    assert seen == [(s, i, 5) for i, s in enumerate(Step, 1)]
    assert at.session_state["result"] is not None
    assert at.session_state["run_requested"] is False


def test_inputs_locked_while_running(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-15: lần chạy phân tích vẽ mọi widget disabled; sau đó bật lại."""
    def halt(*_a: Any, **_k: Any) -> Any:
        st.stop()  # StopException (BaseException) — như người dùng bấm Stop giữa chừng

    at = load(make_app(), s14)
    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", halt)
        analyze(at)
    assert not at.exception and at.session_state["result"] is None
    widgets = [*at.text_input, *at.date_input, *at.time_input, *at.selectbox, *at.radio,
               *at.checkbox, *at.text_area, *at.number_input, *at.button]
    assert widgets and all(w.disabled for w in widgets)
    assert at.session_state["run_requested"] is False
    at.run()
    assert not at.text_input(key="repo_source").disabled
    assert not at.button(key="analyze").disabled


def test_request(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch, with_ids: Path,
                 tmp_path: Path) -> None:
    """TC-screen-input-16: AnalysisRequest, context và resolver của memo."""
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    orig = pipeline.run_analysis

    def spy(*a: Any, **k: Any) -> Any:
        calls.append((a, k))
        return orig(*a, **k)

    monkeypatch.setattr(pipeline, "run_analysis", spy)
    at = analyze(load(make_app(), s14))
    (repo, req, resolver, *_), kw = calls[0]
    (ctx, memo_resolver, err), = at.session_state["period_memo"].values()
    assert err is None and kw["context"] is ctx and resolver is memo_resolver
    assert req.users is None and req.branch == "main" and req.period is ctx.period
    assert req.out_root == (tmp_path / "output").resolve()
    assert (req.exclude_bots, req.separate_users) == (False, False)

    select_mode(at, "Chọn user")
    at.checkbox(key=pick_key("bob")).check().run()
    at.checkbox(key=pick_key("alice")).check().run()
    at.checkbox(key="exclude_bots").check()
    at.checkbox(key="separate_users").check().run()
    analyze(at)
    req2 = calls[1][0][1]
    assert req2.users == ("alice", "bob")
    assert (req2.exclude_bots, req2.separate_users) == (True, True)

    built = app.build_request(branch="main", period=ctx.period, config=AppConfig(),
                              out_root=tmp_path, user_mode="Chọn user", selected={"b", "a"},
                              exclude_bots=False, separate_users=False)
    assert built.users == ("a", "b")
    assert app.build_request(branch="main", period=ctx.period, config=AppConfig(),
                             out_root=tmp_path, user_mode="Tất cả user", selected={"a"},
                             exclude_bots=False, separate_users=False).users is None


@pytest.mark.parametrize("case", ["all", "alice", "bob", "both_separate"])
def test_end_to_end(make_app, s14: Path, with_ids: Path, tmp_path: Path, case: str) -> None:
    """TC-screen-input-17: E2E §14 trên UI — 10/20, 10/13, 10/17, 10/20 + 3 zip end."""
    at = load(make_app(), s14)
    if case != "all":
        select_mode(at, "Chọn user")
        picks = {"alice": ["alice"], "bob": ["bob"], "both_separate": ["alice", "bob"]}
        for account in picks[case]:
            at.checkbox(key=pick_key(account)).check().run()
        if case == "both_separate":
            at.checkbox(key="separate_users").check().run()
    analyze(at)
    assert not at.exception and not at.error
    result = at.session_state["result"]
    expected = {"all": 20, "alice": 13, "bob": 17, "both_separate": 20}[case]
    assert (result.data.loc_start, result.data.loc_end) == (10, expected)
    if case == "both_separate":
        assert len(result.end_zips) == 3
    log = (tmp_path / "output" / "run.log").read_text(encoding="utf-8")
    assert any("Phân tích từ giao diện:" in line and "C_START=" in line
               for line in log.splitlines())
    assert not [p for p in (tmp_path / "output").iterdir() if p.name.startswith(".loc-tmp-")]


def test_out_root_lock(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-input-18: out_root đang bị phiên khác giữ → lỗi; nhả khóa thì chạy được."""
    reg = app.LockRegistry()
    assert reg.get("x") is reg.get("x") and reg.get("x") is not reg.get("y")
    got: list[Any] = []
    threads = [threading.Thread(target=lambda: got.append(reg.get("z"))) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(lock) for lock in got}) == 1

    out = (tmp_path / "output").resolve()
    lock = app.LOCKS.get("out:" + os.path.normcase(str(out)))
    assert lock.acquire(blocking=False)
    try:
        at = analyze(load(make_app(), s14))
        assert any("đang được một phiên phân tích khác sử dụng" in e for e in values(at.error))
        assert at.session_state["result"] is None
        assert not out.exists() or not [p for p in out.iterdir() if p.name.startswith(".loc-tmp-")]
    finally:
        lock.release()
    analyze(at)
    assert at.session_state["result"] is not None
    assert lock.acquire(blocking=False)
    lock.release()


@pytest.mark.parametrize("exc, shown, hidden", [
    (PipelineError("Lỗi pipeline giả"), "Lỗi pipeline giả", None),
    (ValueError("bí mật"), "Lỗi không mong đợi khi phân tích", "bí mật"),
])
def test_run_errors(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception,
                    shown: str, hidden: str | None) -> None:
    """TC-screen-input-19: lỗi pipeline hiện nguyên văn; lỗi khác hiện thông báo chung."""
    def boom(*_a: Any, **_k: Any) -> Any:
        raise exc

    monkeypatch.setattr(pipeline, "run_analysis", boom)
    at = analyze(load(make_app(), s14))
    assert not at.exception
    errors = values(at.error)
    assert any(shown in e for e in errors)
    if hidden:
        assert not any(hidden in t for t in all_texts(at))
    assert at.session_state["run_requested"] is False
    assert not at.button(key="analyze").disabled


# ---------- TC-20, TC-21: token ----------
def test_token_not_leaked(make_app, s14: Path, tmp_path: Path,
                          monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-20: token không có trong cây phần tử, run.log, kết quả, cache."""
    local = GitRepo.open(str(s14), cache_root=tmp_path / "cache")

    def fake_open(source: str, token: str | None = None, cache_root: Path | None = None) -> GitRepo:
        return GitRepo(local.git_dir, "https://github.com/org/repo", token)

    monkeypatch.setattr(GitRepo, "open", staticmethod(fake_open))
    monkeypatch.setattr(requests, "Session", lambda: FakeSession(*[FakeResponse(403)] * 5))
    at = make_app().run()
    at.text_input(key="repo_source").set_value("https://github.com/org/repo")
    at.text_input(key="token").set_value(TOKEN)
    at.date_input(key="start_date").set_value(JAN[0])
    at.date_input(key="end_date").set_value(JAN[1])
    at.run()
    at.button(key="load_repo").click().run()
    analyze(at)
    assert not at.exception
    assert at.session_state["result"] is not None
    assert not [t for t in all_texts(at) if TOKEN in t]
    for root in (tmp_path / "output", tmp_path / "cache"):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            blobs = [p.read_bytes()]
            if p.suffix in (".zip", ".xlsx"):
                with zipfile.ZipFile(p) as zf:
                    blobs += [zf.read(n) for n in zf.namelist()]
            assert not any(TOKEN.encode() in b for b in blobs), p
    logins = tmp_path / "logins.json"
    assert not logins.exists() or TOKEN not in logins.read_text(encoding="utf-8")


def test_source_or_token_changed(make_app, s14: Path) -> None:
    """TC-screen-input-21: đổi token sau khi tải → cảnh báo, coi như chưa tải."""
    at = load(make_app(), s14)
    at.text_input(key="token").set_value("khác").run()
    assert "Nguồn hoặc token đã thay đổi; hãy bấm “Tải repo” lại." in values(at.warning)
    assert "Chưa tải repo." in values(at.info)
    assert at.button(key="analyze").disabled


# ---------- TC-22, TC-23 ----------
def test_blockers_and_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-22: analyze_blockers theo thứ tự mục 7; resolve_out_root."""
    base = dict(repo_ready=True, branch="main", period_error=None, context_error=None,
                identities_error=None, config_error=None, out_dir="output",
                user_mode="Tất cả user", selected_count=0)
    assert app.analyze_blockers(**base) == []
    everything = dict(repo_ready=False, branch=None, period_error="P", context_error="C",
                      identities_error="I", config_error="K", out_dir="  ",
                      user_mode="Chọn user", selected_count=0)
    assert app.analyze_blockers(**everything) == [
        "Chưa tải repo.", "Chưa chọn nhánh.", "P", "I", "C", "K", "Chưa nhập thư mục đầu ra.",
        "Chưa chọn user nào."]
    assert app.analyze_blockers(**{**base, "user_mode": "Chọn user", "selected_count": 2}) == []
    with pytest.raises(PipelineError, match="Chưa nhập thư mục đầu ra"):
        app.resolve_out_root("  ")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert app.resolve_out_root("~/x") == (tmp_path / "x").resolve()
    assert app.resolve_out_root("rel").is_absolute()


def test_selection_dropped_when_period_changes(make_app, s14: Path) -> None:
    """TC-screen-input-23: alice đã chọn, đổi kỳ không còn alice → bỏ chọn + thông báo."""
    at = load(make_app(), s14)
    select_mode(at, "Chọn user")
    at.checkbox(key=pick_key("alice@example.com")).check().run()
    set_period(at, date(2026, 1, 9), date(2026, 1, 20))
    infos = values(at.info)
    assert "Đã bỏ chọn user không còn trong danh sách: alice@example.com" in infos
    assert "Không có user nào có commit trong kỳ." in infos
    assert at.session_state["selected"] == set()


def test_time_inputs_default_none(make_app) -> None:
    """TC-screen-input-01: web UI chỉ chọn ngày, không có ô giờ / múi giờ (A17)."""
    at = make_app().run()
    assert len(at.time_input) == 0
    assert not [s for s in at.selectbox if s.key == "tz"]
    assert at.session_state["start_time"] is None and at.session_state["tz"] == "Asia/Bangkok"


# ---------- TC-24: bổ sung theo review ----------
def test_canonical_timezone(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-input-24: múi giờ khác hoa thường quy về tên chuẩn; không có → lỗi."""
    assert app.canonical_timezone("singapore") == "Singapore"
    assert app.canonical_timezone("utc") == "UTC"
    assert app.canonical_timezone("Asia/Bangkok") == "Asia/Bangkok"
    assert app.canonical_timezone("Mars/X") is None
    at = load(make_app(), s14)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("timezone: singapore\n", encoding="utf-8")
    at.text_input(key="config_path").set_value(str(cfg)).run()
    at.button(key="load_config").click().run()
    assert at.session_state["tz"] == "Singapore"
    (ctx, _, err), = at.session_state["period_memo"].values()
    assert err is None and ctx.period.start.isoformat() == "2026-01-01T00:00:00+08:00"
    (tmp_path / "bad.yaml").write_text("filters: [\n", encoding="utf-8")
    at.text_input(key="config_path").set_value(str(tmp_path / "bad.yaml")).run()
    at.button(key="load_config").click().run()
    assert [e for e in values(at.error) if "File cấu hình" in e]
    at.text_input(key="config_path").set_value("").run()
    at.button(key="load_config").click().run()
    assert not [e for e in values(at.error) if "File cấu hình" in e]

    at.radio(key="user_mode").set_value("Chọn user").run()
    alice = pick_key("alice@example.com")
    at.checkbox(key=alice).check().run()
    assert at.session_state["selected"] == {"alice@example.com"}
    at.checkbox(key=alice).uncheck().run()
    assert at.session_state["selected"] == set()
    assert "Đã chọn 0 user" in values(at.caption)


def test_review_fixes(make_app, s14: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-24: nhánh giữ khi đổi/trả token; snapshot trong khối [2]; identities lỗi."""
    at = load(make_app(), s14)
    order = [type(e).__name__ + ":" + str(getattr(e, "value", "")) for e in at.main]
    texts = [i for i, e in enumerate(at.main)
             if str(getattr(e, "value", "")).startswith("→ Snapshot")]
    third = next(i for i, e in enumerate(at.main) if getattr(e, "value", "") == "[3] CHỌN USER")
    assert texts and max(texts) < third, order
    at.text_input(key="token").set_value("tạm").run()
    at.text_input(key="token").set_value("").run()
    assert at.selectbox(key="branch").value == "main"
    assert not at.button(key="analyze").disabled

    (tmp_path / "ids_dir").mkdir()
    at.text_input(key="identities_path").set_value("ids_dir").run()
    assert any("Đường dẫn identities không phải file" in e for e in values(at.error))
    assert at.button(key="analyze").disabled
    (tmp_path / "bad.yaml").write_text("identities: [\n", encoding="utf-8")
    at.text_input(key="identities_path").set_value("bad.yaml").run()
    assert at.error and at.button(key="analyze").disabled
    at.text_input(key="identities_path").set_value("identities.yaml").run()
    assert not at.button(key="analyze").disabled


def test_no_branches_and_lock_release(make_app, s14: Path, tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-input-24: repo không có nhánh; khóa out_root nhả sau lỗi; traceback vào run.log."""
    with monkeypatch.context() as m:
        m.setattr(GitRepo, "list_branches", lambda self: [])
        empty = load(make_app(), s14)
        assert "Repo không có nhánh nào." in values(empty.error)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise ValueError("lỗi lạ")

    at = load(make_app(), s14)
    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", boom)
        analyze(at)
    lock = app.LOCKS.get("out:" + os.path.normcase(str((tmp_path / "output").resolve())))
    assert lock.acquire(blocking=False)
    lock.release()
    log = (tmp_path / "output" / "run.log").read_text(encoding="utf-8")
    assert " ERROR " in log and "Lỗi không mong đợi khi phân tích" in log and "Traceback" in log


def test_success_line(make_app, s14: Path) -> None:
    """TC-screen-input-14: sau khi chạy xong hiện kết quả (screen-result); lỗi nguồn tiếng Việt."""
    at = analyze(load(make_app(), s14))
    assert "KẾT QUẢ" in values(at.subheader)
    assert any(c.startswith("Thư mục kết quả:") for c in values(at.caption))
    bad = load(make_app(), "does-not-exist-dir")
    assert any(e.startswith(("Không", "Đường dẫn", "Repo", "Nguồn")) for e in values(bad.error))


# ---------- TC-25: cách gán tác giả ----------
def test_attribution_mode_radio(make_app, s14: Path, with_ids: Path, tmp_path: Path) -> None:
    """TC-screen-input-25: radio chọn cách gán — mặc định, build_request, kết quả cũ, E2E."""
    modes = app.ATTRIBUTION_MODES
    assert app.build_request(branch="main", period=None, config=AppConfig(),  # type: ignore[arg-type]
                             out_root=tmp_path, user_mode="Tất cả user", selected=set(),
                             exclude_bots=False, separate_users=False).attribution_mode == "line"
    assert app.build_request(branch="main", period=None, config=AppConfig(),  # type: ignore[arg-type]
                             out_root=tmp_path, user_mode="Tất cả user", selected=set(),
                             exclude_bots=False, separate_users=False,
                             attribution_mode=modes[1]).attribution_mode == "last_commit"

    at = load(make_app(), s14)
    assert at.radio(key="attribution_mode").value == modes[0]
    analyze(at)
    assert at.session_state["result"].data.options.attribution_mode == "line"
    at.radio(key="attribution_mode").set_value(modes[1]).run()
    assert app.STALE_NOTE in values(at.info)
    analyze(at)
    assert not at.exception and not at.error
    result = at.session_state["result"]
    assert result.data.options.attribution_mode == "last_commit"
    assert (result.data.loc_start, result.data.loc_end) == (10, 20)
    assert app.STALE_NOTE not in values(at.info)


# ---------- TC-26: cách tính LOC end ----------
def test_loc_end_mode_radio(make_app, s14: Path, with_ids: Path, tmp_path: Path) -> None:
    """TC-screen-input-26: radio cách tính LOC end — mặc định, build_request, kết quả cũ, khóa."""
    modes = app.LOC_END_MODES
    assert modes == ("Theo code ròng (đếm trên export)",
                     "Theo code thêm (LOC start + tổng code thêm)")
    common: dict[str, Any] = dict(branch="main", period=None, config=AppConfig(),
                                  out_root=tmp_path, user_mode="Tất cả user", selected=set(),
                                  exclude_bots=False, separate_users=False)
    assert app.build_request(**common).loc_end_mode == "net_code"
    assert app.build_request(**common, loc_end_mode=modes[1]).loc_end_mode == "added_code"

    at = load(make_app(), s14)
    assert at.radio(key="loc_end_mode").value == modes[0]
    analyze(at)
    assert at.session_state["result"].data.options.loc_end_mode == "net_code"
    at.radio(key="loc_end_mode").set_value(modes[1]).run()
    assert app.STALE_NOTE in values(at.info)
    analyze(at)
    assert not at.exception and not at.error
    data = at.session_state["result"].data
    assert data.options.loc_end_mode == "added_code"
    assert (data.loc_end, data.reported_loc_end) == (20, 23)
    assert app.STALE_NOTE not in values(at.info)
