"""Test cho panel "Quản lý gộp account" của app.py (spec docs/specs/screen-identity.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import streamlit as st
import yaml
from test_app_input import analyze, load, pick_key, select_mode, values

from loc_counter import app, pipeline
from loc_counter.identity import Identity, IdentityMap, IdentityRule, UserSummary


def open_panel(at: Any) -> Any:
    at.button(key="toggle_identities").click().run()
    return at


def editor_key(at: Any) -> str:
    """Key hiện tại của bảng (theo thế hệ, A6)."""
    return f"identity_editor_{at.session_state['identity_editor_gen']}"


def edit(at: Any, changes: dict[int, str | None]) -> Any:
    at.session_state[editor_key(at)] = {
        "edited_rows": {i: {"Account key": v} for i, v in changes.items()},
        "added_rows": [], "deleted_rows": []}
    at.run()
    return at


def save(at: Any) -> Any:
    at.button(key="save_identities").click().run()
    return at


def editor(at: Any) -> Any:
    return next(d for d in at.dataframe if d.key and d.key.startswith("identity_editor_"))


def file_rules(path: Path) -> list[dict[str, str]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["identities"]


@pytest.fixture
def s14(section14_repo) -> Path:
    return section14_repo(name="repo").src.path


def summary(account: str, *ids: tuple[str, str]) -> UserSummary:
    return UserSummary(account, 1, 0, [Identity(n, e) for n, e in ids], False)


# ---------- TC-01 .. TC-04 ----------
def test_table(make_app, s14: Path) -> None:
    """TC-screen-identity-01: bảng (tên, email, account key); nút Lưu disabled khi chưa đổi."""
    at = open_panel(load(make_app(), s14))
    assert not at.exception
    frame = editor(at).value
    assert list(frame.columns) == ["Tên", "Email", "Account key"]
    assert frame.values.tolist() == [["alice", "alice@example.com", "alice@example.com"],
                                     ["bob", "bob@example.com", "bob@example.com"]]
    assert at.button(key="save_identities").disabled
    users = [summary("alice", ("alice", "alice@x"), ("Alice N", "alice@y")),
             summary("bob", ("bob", "bob@x"), ("alice", "alice@x"))]
    assert app.identity_rows(users).values.tolist() == [
        ["alice", "alice@x", "alice"], ["Alice N", "alice@y", "alice"], ["bob", "bob@x", "bob"]]


def test_merge(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-02: gộp alice, bob → team; danh sách user cập nhật ngay."""
    at = save(edit(open_panel(load(make_app(), s14)), {0: "team", 1: "team"}))
    assert not at.exception and not at.error
    assert sorted((r["email"], r["account"]) for r in file_rules(tmp_path / "identities.yaml")) == [
        ("alice@example.com", "team"), ("bob@example.com", "team")]
    assert [c for c in values(at.caption) if c.endswith(" commit)")] == ["team (4 commit)"]
    assert any(s.startswith("Đã lưu 2 thay đổi vào ") for s in values(at.success))


def test_keep_other_rules(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-03: quy tắc ngoài kỳ và quy tắc theo tên được giữ."""
    path = tmp_path / "identities.yaml"
    path.write_text("identities:\n  - email: x@y.z\n    account: xyz\n"
                    "  - name: Alice N\n    account: alice\n", encoding="utf-8")
    at = open_panel(load(make_app(), s14))
    assert any("giữ nguyên 2 quy tắc khác" in c for c in values(at.caption))
    save(edit(at, {1: "b2"}))
    rules = file_rules(path)
    assert {"email": "x@y.z", "account": "xyz"} in rules
    assert {"name": "Alice N", "account": "alice"} in rules
    assert {"email": "bob@example.com", "account": "b2"} in rules


def test_remove_rule(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-04: xóa trống account key → bỏ quy tắc, account về tự động."""
    path = tmp_path / "identities.yaml"
    path.write_text("identities:\n  - email: alice@example.com\n    account: alice\n",
                    encoding="utf-8")
    at = open_panel(load(make_app(), s14))
    assert editor(at).value["Account key"].tolist()[0] == "alice"
    save(edit(at, {0: ""}))
    assert file_rules(path) == []
    assert "alice@example.com (2 commit)" in values(at.caption)


# ---------- TC-05, TC-06, TC-09: unit ----------
def test_empty_email_rule() -> None:
    """TC-screen-identity-05: email rỗng → quy tắc theo tên."""
    result = app.apply_identity_edits(IdentityMap(), [("Bình", "", "binh")])
    assert result.rules == (IdentityRule("binh", None, "Bình"),)


def test_conflict(make_app, make_repo, tmp_path: Path) -> None:
    """TC-screen-identity-06: một email hai account → IdentityError, file không đổi."""
    from loc_counter.identity import IdentityError, save_identities

    with pytest.raises(IdentityError, match="Email same@x được gán cho nhiều account: a, b"):
        app.apply_identity_edits(IdentityMap(), [("a", "same@x", "a"), ("A", "SAME@x", "b")])
    clash = app.apply_identity_edits(IdentityMap((IdentityRule("other", "bo@x", "Bo"),)),
                                     [("Bo", "", "new")])  # tên Bo → new, email bo@x → other
    assert clash.rules == (IdentityRule("other", "bo@x", None), IdentityRule("new", None, "Bo"))
    with pytest.raises(IdentityError, match="nhiều account"):  # save kiểm toàn bộ file
        save_identities(tmp_path / "c.yaml",
                        IdentityMap((*clash.rules, IdentityRule("third", "BO@x", None))))
    assert not (tmp_path / "c.yaml").exists()

    src = make_repo("two_names")
    src.commit("admin", "2025-12-15T10:00:00+07:00", files={"a.py": "a = 1\n"})
    for i, name in enumerate(("alice", "Alice Nguyen")):
        src.commit(f"c{i}", f"2026-01-0{i + 2}T10:00:00+07:00", author=(name, "alice@example.com"),
                   files={f"f{i}.py": f"v = {i}\n"})
    path = tmp_path / "identities.yaml"
    path.write_text("identities: []\n", encoding="utf-8")
    at = open_panel(load(make_app(), src.path))
    assert editor(at).value["Email"].tolist() == ["alice@example.com", "alice@example.com"]
    save(edit(at, {0: "a", 1: "b"}))
    assert any("nhiều account" in e for e in values(at.error))
    assert path.read_text(encoding="utf-8") == "identities: []\n"


def test_pure_functions() -> None:
    """TC-screen-identity-09: changed_rows, apply_identity_edits (upsert, xóa, email+name)."""
    original = pd.DataFrame([["a", "a@x", "a@x"], ["b", "b@x", "b@x"], ["c", "", "c"]],
                            columns=list(app.IDENTITY_COLUMNS))
    edited = original.copy()
    edited.loc[0, "Account key"] = "  team "
    edited.loc[1, "Account key"] = "b@x "
    edited.loc[2, "Account key"] = ""
    assert app.changed_rows(original, edited) == [("a", "a@x", "team"), ("c", "", "")]

    base = IdentityMap((IdentityRule("old", "A@X", None), IdentityRule("keep", "k@x", None),
                        IdentityRule("both", "b@x", "B Name"), IdentityRule("c", None, "c")))
    out = app.apply_identity_edits(base, [("a", "a@x", "team"), ("b", "b@x", "nb"),
                                          ("c", "", "")])
    assert out.rules == (IdentityRule("keep", "k@x", None),
                         IdentityRule("both", None, "B Name"),
                         IdentityRule("team", "a@x", None), IdentityRule("nb", "b@x", None))
    again = app.apply_identity_edits(out, [("a", "a@x", "team")])
    assert again.rules.count(IdentityRule("team", "a@x", None)) == 1


# ---------- TC-07, TC-08, TC-10, TC-11 ----------
def test_broken_or_missing_file(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-07: file hỏng → lỗi, không bảng; file vắng → lưu tạo file."""
    path = tmp_path / "identities.yaml"
    path.write_text("identities: [\n", encoding="utf-8")
    at = open_panel(load(make_app(), s14))
    assert not [d for d in at.dataframe if d.key and d.key.startswith("identity_editor_")]
    assert "Sửa file hoặc đổi đường dẫn rồi thử lại." in values(at.caption)
    assert at.button(key="analyze").disabled
    path.unlink()
    at.run()
    save(edit(at, {0: "alice"}))
    assert file_rules(path) == [{"email": "alice@example.com", "account": "alice"}]


def test_applies_immediately(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-identity-08: gộp alice → team khi đang chọn alice → bỏ chọn, tính lại kỳ."""
    calls: list[Any] = []
    orig = pipeline.prepare_period

    def spy(repo: Any, branch: str, period: Any, resolver: Any) -> Any:
        calls.append(resolver)
        return orig(repo, branch, period, resolver)

    monkeypatch.setattr(pipeline, "prepare_period", spy)
    at = load(make_app(), s14)
    select_mode(at, "Chọn user")
    at.checkbox(key=pick_key("alice@example.com")).check().run()
    before = len(calls)
    save(edit(open_panel(at), {0: "team"}))
    assert len(calls) == before + 1 and calls[-1] is not calls[before - 1]
    assert "Đã bỏ chọn user không còn trong danh sách: alice@example.com" in values(at.info)
    assert "team (2 commit)" in [c.label for c in at.checkbox if c.key.startswith("pick_")]


def test_locked(make_app, s14: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-screen-identity-10: đang chạy phân tích → nút và bảng bị khóa."""
    at = open_panel(load(make_app(), s14))
    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", lambda *a, **k: st.stop())
        analyze(at)
    assert at.button(key="toggle_identities").disabled
    assert at.button(key="save_identities").disabled
    assert editor(at).proto.disabled


def test_no_period_yet(make_app) -> None:
    """TC-screen-identity-11: chưa tải repo → thông báo cần tải repo."""
    at = open_panel(make_app().run())
    assert "Cần tải repo và chọn kỳ hợp lệ để có danh sách tác giả." in values(at.info)


# ---------- TC-12: bổ sung theo review ----------
def test_empty_cells_are_blank() -> None:
    """TC-screen-identity-12: ô None / NA (pandas StringDtype) = chuỗi rỗng, không phải 'nan'."""
    original = pd.DataFrame([["a", "a@x", "a@x"], ["b", "b@x", "b@x"]],
                            columns=list(app.IDENTITY_COLUMNS)).astype("string")
    edited = original.copy()
    edited.loc[0, "Account key"] = pd.NA
    edited.loc[1, "Account key"] = None
    assert app.changed_rows(original, edited) == [("a", "a@x", ""), ("b", "b@x", "")]


def test_assign_and_clear_same_key_conflict() -> None:
    """TC-screen-identity-12: cùng email vừa gán vừa xóa trống trong một lần lưu → xung đột."""
    from loc_counter.identity import IdentityError

    with pytest.raises(IdentityError, match=r"x@y được gán cho nhiều account: acc, \(trống\)"):
        app.apply_identity_edits(IdentityMap(), [("a", "x@y", "acc"), ("A", "X@y", "")])


def test_clear_removes_name_rule(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-12: xóa trống hàng có account từ quy tắc tên → account về tự động."""
    path = tmp_path / "identities.yaml"
    path.write_text("identities:\n  - name: alice\n    account: al\n", encoding="utf-8")
    at = open_panel(load(make_app(), s14))
    assert editor(at).value["Account key"].tolist()[0] == "al"
    save(edit(at, {0: ""}))
    assert file_rules(path) == []
    assert "alice@example.com (2 commit)" in values(at.caption)


def test_rows_change_drops_unsaved_edits(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-12: đổi file identities làm đảo thứ tự hàng → bỏ sửa đổi chưa lưu."""
    (tmp_path / "other.yaml").write_text(
        "identities:\n  - email: bob@example.com\n    account: aaa\n", encoding="utf-8")
    at = edit(open_panel(load(make_app(), s14)), {0: "team"})
    assert not at.button(key="save_identities").disabled
    first_id = editor(at).proto.id
    at.text_input(key="identities_path").set_value("other.yaml").run()
    assert editor(at).value["Account key"].tolist() == ["aaa", "alice@example.com"]
    assert editor(at).proto.id != first_id  # id phần tử đổi → frontend bỏ sửa đổi cũ
    assert at.button(key="save_identities").disabled
    assert file_rules(tmp_path / "other.yaml") == [{"email": "bob@example.com", "account": "aaa"}]
    before_save = editor(at).proto.id
    save(edit(at, {1: "x"}))
    assert editor(at).proto.id != before_save
    assert at.button(key="save_identities").disabled


def test_caption_counts_after_edit(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-12: caption 'giữ nguyên k quy tắc' đếm theo kết quả thật sau khi sửa."""
    (tmp_path / "identities.yaml").write_text(
        "identities:\n  - name: alice\n    account: al\n  - email: x@y.z\n    account: xyz\n",
        encoding="utf-8")
    at = open_panel(load(make_app(), s14))
    assert any("giữ nguyên 2 quy tắc khác" in c for c in values(at.caption))
    edit(at, {0: ""})  # xóa trống alice → bỏ cả quy tắc tên "alice" (A7)
    assert any("giữ nguyên 1 quy tắc khác" in c for c in values(at.caption))


def test_none_cell_via_apptest(make_app, s14: Path, tmp_path: Path) -> None:
    """TC-screen-identity-12: ô xóa trống gửi None trên bảng thật → bỏ quy tắc, không 'nan'."""
    path = tmp_path / "identities.yaml"
    path.write_text("identities:\n  - email: alice@example.com\n    account: alice\n",
                    encoding="utf-8")
    at = save(edit(open_panel(load(make_app(), s14)), {0: None}))
    assert file_rules(path) == []
    assert "nan" not in path.read_text(encoding="utf-8")
    assert "alice@example.com (2 commit)" in values(at.caption)


def test_mixed_key_conflict() -> None:
    """TC-screen-identity-12: hàng gán theo tên + hàng xóa trống có email cùng tên → xung đột."""
    from loc_counter.identity import IdentityError

    for changes in ([("A", "", "acc"), ("A", "a@x", "")], [("A", "a@x", ""), ("A", "", "acc")]):
        with pytest.raises(IdentityError, match=r"Tên a được gán cho nhiều account"):
            app.apply_identity_edits(IdentityMap(), changes)


def test_no_authors_and_locked_columns(make_app, s14: Path) -> None:
    """TC-screen-identity-12: kỳ không có tác giả; cột Tên, Email không sửa được."""
    from datetime import date

    at = open_panel(load(make_app(), s14))
    import json

    proto = editor(at).proto
    columns = json.loads(proto.columns)
    assert proto.disabled is False
    assert columns["Tên"]["disabled"] is True and columns["Email"]["disabled"] is True
    assert not columns.get("Account key", {}).get("disabled", False)
    at.date_input(key="start_date").set_value(date(2026, 1, 9))
    at.date_input(key="end_date").set_value(date(2026, 1, 20))
    at.run()
    assert "Không có tác giả nào có commit trong kỳ." in values(at.info)
