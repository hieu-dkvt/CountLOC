"""Test cho màn hình kết quả của app.py (spec docs/specs/screen-result.md)."""

from __future__ import annotations

import dataclasses
import os
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
from conftest import build_cross_check_mismatch
from test_app_input import IDS_YAML, analyze, load, pick_key, select_mode, set_period, values

from loc_counter import app
from loc_counter.config import AppConfig
from loc_counter.git_repo import GitRepo
from loc_counter.identity import AccountResolver, IdentityMap, IdentityRule
from loc_counter.pipeline import AnalysisRequest, AnalysisResult, run_analysis, run_log
from loc_counter.snapshot import make_period

JAN = (date(2026, 1, 1), date(2026, 1, 31))
IDS = IdentityMap((IdentityRule("alice", email="alice@example.com"),
                   IdentityRule("bob", email="bob@example.com")))


def run(src: Any, tmp_path: Path, users: tuple[str, ...] | None = None, *,
        separate: bool = False, start: date = JAN[0], end: date = JAN[1],
        start_time: time | None = None, tz: str = "Asia/Bangkok",
        out: str = "out") -> AnalysisResult:
    """Chạy pipeline thật trên repo nguồn `src` (RepoBuilder)."""
    repo = GitRepo.open(str(src.path), cache_root=tmp_path / "cache")
    period = make_period(start, end, start_time, timezone=tz)
    request = AnalysisRequest("main", period, AppConfig(), tmp_path / out, users,
                              separate_users=separate)
    with run_log(tmp_path / out):
        return run_analysis(repo, request, AccountResolver(IDS))


@pytest.fixture
def s14(section14_repo) -> Any:
    return section14_repo(name="repo").src


@pytest.fixture
def with_ids(tmp_path: Path) -> Path:
    path = tmp_path / "identities.yaml"
    path.write_text(IDS_YAML, encoding="utf-8")
    return path


def rows(frame: Any) -> list[list[Any]]:
    return frame.values.tolist()


def downloads(at: Any) -> dict[str, Any]:
    return {d.key: d for d in at.get("download_button")}


# ---------- TC-01 .. TC-07 ----------
def test_metrics(make_app, s14: Any, with_ids: Path) -> None:
    """TC-screen-result-01: bốn số chính LOC start, LOC end, Chênh lệch, Commit."""
    at = analyze(load(make_app(), s14.path))
    assert not at.exception and not at.error
    assert "KẾT QUẢ" in values(at.subheader)
    assert [(m.label, m.value) for m in at.metric] == [
        ("LOC start", "10"), ("LOC end", "20"), ("Chênh lệch", "+10"), ("Commit", "4")]


def test_language_frame(s14: Any, tmp_path: Path) -> None:
    """TC-screen-result-02: Theo ngôn ngữ — cột và giá trị."""
    frame = app.language_frame(run(s14, tmp_path).data)
    assert list(frame.columns) == ["Ngôn ngữ", "LOC start", "LOC end", "Chênh lệch"]
    assert rows(frame) == [["Python", 10, 20, 10]]


def test_user_and_total(make_app, s14: Any, tmp_path: Path, with_ids: Path) -> None:
    """TC-screen-result-03: Theo user + Tổng (tất cả; chỉ alice); Tổng vẽ riêng."""
    data = run(s14, tmp_path).data
    frame = app.user_frame(data)
    assert list(frame.columns) == ["User", "Bot", "Commit", "Thêm", "Xóa", "Ròng", "File thay đổi"]
    assert rows(frame) == [["alice", "", 2, 5, 2, 3, 1], ["bob", "", 2, 8, 1, 7, 2]]
    assert rows(app.total_frame(data)) == [["Tổng", "", 4, 13, 3, 10, 2]]
    alice = run(s14, tmp_path, ("alice",), out="out_alice").data
    assert rows(app.user_frame(alice)) == [["alice", "", 2, 5, 2, 3, 1]]
    assert rows(app.total_frame(alice)) == [["Tổng", "", 2, 5, 2, 3, 1]]

    at = analyze(load(make_app(), s14.path))
    user_tables = [d.value for d in at.dataframe if "Ròng" in d.value.columns]
    assert [rows(t) for t in user_tables] == [rows(frame), [["Tổng", "", 4, 13, 3, 10, 2]]]


def test_no_users(make_app, s14: Any, tmp_path: Path) -> None:
    """TC-screen-result-04: kỳ không có commit — bảng user / biểu đồ rỗng, Commit 0."""
    data = run(s14, tmp_path, start=date(2026, 1, 9), end=date(2026, 1, 20)).data
    assert app.user_frame(data).empty and app.total_frame(data) is None
    assert app.weekly_frame(data).empty
    at = load(make_app(), s14.path, (date(2026, 1, 9), date(2026, 1, 20)))
    analyze(at)
    captions = values(at.caption)
    assert "Không có user nào có commit trong kỳ." in captions
    assert "Không có commit trong kỳ." in captions
    assert ("Commit", "0") in [(m.label, m.value) for m in at.metric]
    assert any(t.startswith("Kiểm tra chéo:") and t.endswith("→ đạt") for t in values(at.success))


def test_weekly(make_app, s14: Any, tmp_path: Path, with_ids: Path) -> None:
    """TC-screen-result-05: weekly_frame và biểu đồ."""
    frame = app.weekly_frame(run(s14, tmp_path).data)
    assert list(frame.columns) == ["Tuần", "Bắt đầu tuần", "User", "Code ròng"]
    assert frame.groupby("User")["Code ròng"].sum().to_dict() == {"alice": 3, "bob": 7}
    at = analyze(load(make_app(), s14.path))
    assert at.get("vega_lite_chart")


def test_file_frame(s14: Any, tmp_path: Path, make_repo) -> None:
    """TC-screen-result-06: Chi tiết theo file, lọc, cột Đổi tên từ."""
    frame = app.file_frame(run(s14, tmp_path).data)
    assert list(frame.columns) == ["Đường dẫn", "Đổi tên từ", "Ngôn ngữ", "LOC start", "LOC end",
                                   "Chênh lệch"]
    assert frame["Đường dẫn"].tolist() == ["app.py", "util.py"]
    assert app.filter_files(frame, "UTIL", [], False)["Đường dẫn"].tolist() == ["util.py"]
    assert len(app.filter_files(frame, "", ["Python"], False)) == 2
    assert len(app.filter_files(frame, "", ["Go"], False)) == 0
    changed = app.filter_files(frame, "", [], True)
    assert (changed["Chênh lệch"] != 0).all() and len(changed) == 2

    src = make_repo("ren")
    body = "".join(f"r{i} = {i}\n" for i in range(5))
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"old.py": body})
    src.commit("alice mv", "2026-01-05T10:00:00+07:00", author=("alice", "alice@example.com"),
               files={"new.py": body}, remove=("old.py",))
    renamed = app.file_frame(run(src, tmp_path, out="out_ren").data)
    assert rows(renamed) == [["new.py", "old.py", "Python", 5, 5, 0]]
    assert len(app.filter_files(renamed, "", [], True)) == 1
    assert len(app.filter_files(renamed, "OLD", [], False)) == 1

    mixed = app.file_frame(run(src, tmp_path, out="out_ren").data).iloc[0:0]
    mixed.loc[0] = ["a.py", "", "Python", 1, 3, 2]
    mixed.loc[1] = ["same.py", "", "Python", 4, 4, 0]
    assert app.filter_files(mixed, "", [], True)["Đường dẫn"].tolist() == ["a.py"]


def test_warnings(make_app, make_repo, s14: Any, tmp_path: Path) -> None:
    """TC-screen-result-07: cảnh báo kiểm tra chéo; §14 không có cảnh báo."""
    src = build_cross_check_mismatch(make_repo("mis"))
    data = run(src, tmp_path, out="out_mis").data
    frame = app.warnings_frame(data)
    assert list(frame.columns) == ["Loại", "Đường dẫn", "Nội dung", "Phạm vi"]
    assert ["cross_check", "", "kiểm tra chéo"] in [[r[0], r[1], r[3]] for r in rows(frame)]

    at = analyze(load(make_app(), src.path))
    assert [(w.icon, w.value) for w in at.warning if "cảnh báo (xem" in w.value] == [
        ("⚠️", "1 cảnh báo (xem chi tiết)")]
    assert any(w.startswith("Kiểm tra chéo:") and w.endswith("VƯỢT NGƯỠNG (xem warnings.csv)")
               for w in values(at.warning))
    ok = analyze(load(make_app(), s14.path))
    assert "Không có cảnh báo." in values(ok.caption)
    assert any(s.startswith("Kiểm tra chéo:") and s.endswith("→ đạt") for s in values(ok.success))


# ---------- TC-08 .. TC-10: tải file ----------
def test_download_all_files(make_app, s14: Any, tmp_path: Path, with_ids: Path,
                            monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-result-08: download_items = mọi file của thư mục kết quả; AppTest đủ nút."""
    import streamlit as st

    calls: list[dict[str, Any]] = []
    orig = st.download_button

    def spy(label: str, data: Any, **kwargs: Any) -> Any:
        if kwargs.get("key", "").startswith("dl_") and not kwargs.get("disabled"):
            calls.append({"data": data, **kwargs})
        return orig(label, data, **kwargs)

    monkeypatch.setattr(st, "download_button", spy)
    result = run(s14, tmp_path, ("alice", "bob"), separate=True)
    items = app.download_items(result)
    assert {i.path.name for i in items} == set(os.listdir(result.out_dir))
    assert len(items) == 10
    for i in items:
        assert i.path.read_bytes() == (result.out_dir / i.path.name).read_bytes()
        assert i.mime == app.MIME[i.path.suffix] and i.key == f"dl_{i.path.name}"
    assert [i.path.name for i in items if i.group == "csv"] == [
        "loc_by_user.csv", "loc_by_language.csv", "loc_by_file.csv"]

    at = load(make_app(), s14.path)
    select_mode(at, "Chọn user")
    at.checkbox(key=pick_key("alice")).check().run()
    at.checkbox(key=pick_key("bob")).check().run()
    at.checkbox(key="separate_users").check().run()
    analyze(at)
    shown = at.session_state["result"]
    buttons = downloads(at)
    for call in calls:
        path = shown.out_dir / call["file_name"]
        assert call["data"]() == path.read_bytes()
        assert call["mime"] == app.MIME[path.suffix] and call["on_click"] == "ignore"
    assert {c["file_name"] for c in calls} == set(os.listdir(shown.out_dir))
    assert set(buttons) == {f"dl_{name}" for name in os.listdir(shown.out_dir)}
    assert not any(b.proto.disabled for b in buttons.values())


def test_many_separate_zips(make_app, s14: Any, tmp_path: Path) -> None:
    """TC-screen-result-09: > 5 zip riêng → một selectbox + một nút."""
    result = run(s14, tmp_path)
    extra = []
    for i in range(7):
        path = result.out_dir / f"end_2026-01-31_u{i}.zip"
        path.write_bytes(b"PK")
        extra.append(path)
    fake = dataclasses.replace(result, end_zips=(*result.end_zips, *extra))
    at = make_app()
    at.session_state["result"] = fake
    at.run()
    pick = at.selectbox(key="dl_separate_pick")
    assert len(pick.options) == 7
    keys = set(downloads(at))
    assert "dl_separate" in keys and not any(k.startswith("dl_end_2026-01-31_u") for k in keys)


def test_missing_file(make_app, s14: Any, with_ids: Path) -> None:
    """TC-screen-result-10: file kết quả bị xóa → nút disabled + chú thích."""
    at = analyze(load(make_app(), s14.path))
    (at.session_state["result"].out_dir / "warnings.csv").unlink()
    at.run()
    assert downloads(at)["dl_warnings.csv"].proto.disabled
    assert "Không còn file: warnings.csv" in values(at.caption)


# ---------- TC-11 .. TC-14 ----------
def test_header_and_note(make_app, s14: Any, tmp_path: Path, with_ids: Path) -> None:
    """TC-screen-result-11: dòng đầu, múi giờ + độ lệch, ghi chú export theo user."""
    data = run(s14, tmp_path).data
    assert app.header_text(data) == (
        f"Repo: {data.repo} • Nhánh: main • Kỳ: 2026-01-01 00:00 → 2026-01-31 23:59 "
        "(Asia/Bangkok, UTC+07:00)")
    assert app.has_user_export(data) is False
    timed = run(s14, tmp_path, start_time=time(8, 30), tz="UTC", out="out_utc").data
    assert app.header_text(timed).endswith(
        "Kỳ: 2026-01-01 08:30 → 2026-01-31 23:59 (UTC, UTC+00:00)")
    assert app.has_user_export(run(s14, tmp_path, ("alice",), out="out_a").data) is True

    at = load(make_app(), s14.path)
    select_mode(at, "Chọn user")
    at.checkbox(key=pick_key("alice")).check().run()
    analyze(at)
    assert app.NOTE_USER_EXPORT in values(at.caption)
    assert any(t.startswith("Repo: ") and "• Kỳ: 2026-01-01 00:00 → " in t for t in values(at.text))
    assert "User: alice" in values(at.text)


def test_stale_result(make_app, s14: Any, with_ids: Path) -> None:
    """TC-screen-result-12: đổi tham số sau khi chạy → ghi chú kết quả cũ, số liệu vẫn hiện."""
    at = analyze(load(make_app(), s14.path))
    assert app.STALE_NOTE not in values(at.info)
    set_period(at, JAN[0], date(2026, 1, 6))
    assert app.STALE_NOTE in values(at.info)
    assert ("LOC end", "20") in [(m.label, m.value) for m in at.metric]


def test_formatting(s14: Any, tmp_path: Path) -> None:
    """TC-screen-result-13: signed, users_text, cross_check_text."""
    assert (app.signed(0), app.signed(1234), app.signed(-5)) == ("0", "+1,234", "-5")
    data = run(s14, tmp_path).data
    assert app.users_text(data) == "User: Tất cả user"
    opts = dataclasses.replace(data.options, exclude_bots=True, separate_users=True)
    assert app.users_text(dataclasses.replace(data, options=opts)) == (
        "User: Tất cả user (loại trừ bot) • Xuất riêng từng user")
    chosen = dataclasses.replace(data, all_users=False, options=dataclasses.replace(
        data.options, selected_users=("alice", "bob")))
    assert app.users_text(chosen) == "User: alice, bob"
    assert app.cross_check_text(data.cross_check) == (
        "Kiểm tra chéo: 10 + (+10) = 20; LOC end 20; lệch 0.000 % (ngưỡng 0.5 %) → đạt")


def test_locked_downloads(make_app, s14: Any, with_ids: Path,
                          monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-result-14: đang chạy phân tích mới → nút tải và ô lọc file disabled."""
    import streamlit as st

    from loc_counter import pipeline

    at = analyze(load(make_app(), s14.path))
    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", lambda *a, **k: st.stop())
        analyze(at)
    buttons = downloads(at)
    assert buttons and all(b.proto.disabled for b in buttons.values())
    assert at.text_input(key="file_query").disabled
    assert at.checkbox(key="file_changed_only").disabled
    assert at.multiselect(key="file_languages").disabled
