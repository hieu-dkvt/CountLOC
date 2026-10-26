"""Test cho lệnh `loc-counter users` (spec docs/specs/cli-users.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from loc_counter import git_repo, identity
from loc_counter.cli import app

runner = CliRunner()
JAN = ["--start", "2026-01-01", "--end", "2026-01-31"]


@pytest.fixture
def repo_path(section14_repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Repo §14 + 1 commit bot; cache repo và cache login nằm trong tmp_path."""
    monkeypatch.setattr(git_repo, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(identity, "DEFAULT_LOGIN_CACHE", tmp_path / "logins.json")
    return str(section14_repo(bot=True).src.path)


def _invoke(*args: str):  # noqa: ANN202
    return runner.invoke(app, ["users", *args])


def _rows(output: str) -> list[list[str]]:
    return [line.split() for line in output.splitlines()]


def test_table(repo_path: str) -> None:
    """TC-cli-users-01: bảng user, dòng Repo/Nhánh/Snapshot, TỔNG."""
    result = _invoke("--repo", repo_path, "--branch", "main", *JAN)
    assert result.exit_code == 0, result.output
    out = result.stdout
    lines = out.splitlines()
    assert lines[0].startswith("Repo: ")
    assert lines[1] == ("Nhánh: main • Kỳ: 2026-01-01 00:00:00 → 2026-01-31 23:59:59 "
                        "(Asia/Bangkok)")
    assert lines[2].startswith("Snapshot start: ") and "2025-12-15 10:00 admin: app.py" in lines[2]
    assert lines[3].startswith("Snapshot end:   ") and "2026-01-08 10:00 bob del" in lines[3]
    rows = _rows(out)
    assert ["User", "Commit", "Merge", "Bot", "Email"] in rows
    assert ["alice@example.com", "2", "0", "alice@example.com"] in rows
    assert ["bob@example.com", "2", "0", "bob@example.com"] in rows
    assert ["dependabot[bot]", "1", "0", "bot",
            "49699333+dependabot[bot]@users.noreply.github.com"] in rows
    assert lines[-1] == "TỔNG: 3 user, 5 commit"
    assert "Cảnh báo" not in out


def test_json(repo_path: str) -> None:
    """TC-cli-users-02: --json đúng cấu trúc."""
    result = _invoke("--repo", repo_path, "--branch", "main", *JAN, "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert list(data) == ["repo", "branch", "timezone", "start", "end", "c_start", "c_end",
                          "users", "warnings"]
    assert data["branch"] == "main" and data["timezone"] == "Asia/Bangkok"
    assert data["start"] == "2026-01-01T00:00:00+07:00"
    assert data["end"] == "2026-01-31T23:59:59+07:00"
    assert len(data["c_start"]["short_sha"]) == 7
    assert data["c_start"]["date"] == "2025-12-15T10:00:00+07:00"
    assert data["c_end"]["subject"] == "bob del"
    assert data["users"][0] == {
        "account": "alice@example.com", "commits": 2, "merge_commits": 0, "is_bot": False,
        "identities": [{"name": "alice", "email": "alice@example.com"}]}
    assert [u["account"] for u in data["users"]] == ["alice@example.com", "bob@example.com",
                                                    "dependabot[bot]"]
    assert data["warnings"] == []


def test_exclude_bots(repo_path: str) -> None:
    """TC-cli-users-03: --exclude-bots ẩn bot, TỔNG giảm."""
    result = _invoke("--repo", repo_path, "--branch", "main", *JAN, "--exclude-bots")
    assert result.exit_code == 0, result.output
    assert "dependabot" not in result.stdout
    assert result.stdout.splitlines()[-1] == "TỔNG: 2 user, 4 commit"


def test_identities_file(repo_path: str, tmp_path: Path) -> None:
    """TC-cli-users-04: --identities gộp alice và bob thành team."""
    path = tmp_path / "identities.yaml"
    path.write_text("identities:\n  - email: alice@example.com\n    account: team\n"
                    "  - email: bob@example.com\n    account: team\n", encoding="utf-8")
    result = _invoke("--repo", repo_path, "--branch", "main", *JAN, "--identities", str(path))
    assert result.exit_code == 0, result.output
    rows = _rows(result.stdout)
    assert ["team", "4", "0", "alice@example.com,", "bob@example.com"] in rows
    assert result.stdout.splitlines()[-1] == "TỔNG: 2 user, 5 commit"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--start", "2026-13-01", "--end", "2026-01-31"],
         "Ngày không hợp lệ cho --start: 2026-13-01 (định dạng YYYY-MM-DD)"),
        (["--start", "01/01/2026", "--end", "2026-01-31"],
         "Ngày không hợp lệ cho --start: 01/01/2026 (định dạng YYYY-MM-DD)"),
        ([*JAN, "--end-time", "25:00"], "Giờ không hợp lệ cho --end-time: 25:00 (định dạng HH:MM)"),
        ([*JAN, "--start-time", "8:5"], "Giờ không hợp lệ cho --start-time: 8:5 (định dạng HH:MM)"),
    ],
)
def test_bad_date_time(tmp_path: Path, args: list[str], message: str) -> None:
    """TC-cli-users-05: ngày/giờ sai định dạng → mã 1, thông báo tiếng Việt."""
    result = _invoke("--repo", str(tmp_path), *args)
    assert result.exit_code == 1
    assert f"Lỗi: {message}" in result.stderr


def test_start_not_before_end(tmp_path: Path) -> None:
    """TC-cli-users-06: start ≥ end → mã 1."""
    result = _invoke("--repo", str(tmp_path), "--start", "2026-02-01", "--end", "2026-01-01")
    assert result.exit_code == 1
    assert "phải trước end" in result.stderr


def test_token_env(repo_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-users-07: biến token thiếu → lỗi; có token → không bị in ra."""
    monkeypatch.delenv("NOPE", raising=False)
    result = _invoke("--repo", repo_path, *JAN, "--token-env", "NOPE")
    assert result.exit_code == 1
    assert "Biến môi trường NOPE chưa được đặt hoặc rỗng." in result.stderr
    monkeypatch.setenv("MYTOK", "ghp_SECRET")
    result = _invoke("--repo", repo_path, *JAN, "--token-env", "MYTOK")
    assert result.exit_code == 0, result.output
    assert "ghp_SECRET" not in result.stdout and "ghp_SECRET" not in result.stderr


def test_no_data(repo_path: str) -> None:
    """TC-cli-users-08: không có commit trước end → mã 1."""
    result = _invoke("--repo", repo_path, "--start", "2020-01-01", "--end", "2020-01-31")
    assert result.exit_code == 1
    assert "Không có dữ liệu trong khoảng thời gian" in result.stderr


def test_branch(repo_path: str) -> None:
    """TC-cli-users-09: nhánh sai → lỗi; không truyền --branch → nhánh mặc định."""
    result = _invoke("--repo", repo_path, "--branch", "nope", *JAN)
    assert result.exit_code == 1
    assert "Không tìm thấy nhánh: nope" in result.stderr
    result = _invoke("--repo", repo_path, *JAN)
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[1].startswith("Nhánh: main ")


def test_no_c_start(repo_path: str) -> None:
    """TC-cli-users-10: C_START rỗng → dòng Snapshot start đặc biệt; có admin."""
    result = _invoke("--repo", repo_path, "--start", "2025-01-01", "--end", "2026-01-31")
    assert result.exit_code == 0, result.output
    assert "Snapshot start: (không có commit trước start)" in result.stdout
    assert any(row[:2] == ["admin@example.com", "1"] for row in _rows(result.stdout))


def test_missing_repo() -> None:
    """TC-cli-users-11: thiếu --repo → mã 2."""
    result = _invoke(*JAN)
    assert result.exit_code == 2


def test_no_users(repo_path: str) -> None:
    """TC-cli-users-12: kỳ không có commit → thông báo, TỔNG 0."""
    result = _invoke("--repo", repo_path, "--start", "2026-01-09", "--end", "2026-01-20")
    assert result.exit_code == 0, result.output
    assert "Không có user nào có commit trong kỳ." in result.stdout
    assert result.stdout.splitlines()[-1] == "TỔNG: 0 user, 0 commit"
    assert "User" not in _rows(result.stdout)[4]


def test_time_and_timezone(repo_path: str) -> None:
    """TC-cli-users-13: giờ nhập + múi giờ UTC hiển thị đúng kỳ."""
    result = _invoke("--repo", repo_path, *JAN, "--start-time", "10:00", "--end-time", "10:00",
                     "--tz", "UTC")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[1].endswith(
        "Kỳ: 2026-01-01 10:00:00 → 2026-01-31 10:00:59 (UTC)")


def test_warning_after_total(repo_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-users-14: dòng cảnh báo in sau dòng TỔNG; JSON có warnings."""
    from loc_counter import cli

    real = cli.list_period_users

    def with_warning(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        result = real(*args, **kwargs)
        result.warnings.append("GitHub API lỗi 500; dùng email làm account.")
        return result

    monkeypatch.setattr(cli, "list_period_users", with_warning)
    result = _invoke("--repo", repo_path, *JAN)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[-2] == "TỔNG: 3 user, 5 commit"
    assert lines[-1] == "Cảnh báo: GitHub API lỗi 500; dùng email làm account."
    data = json.loads(_invoke("--repo", repo_path, *JAN, "--json").stdout)
    assert data["warnings"] == ["GitHub API lỗi 500; dùng email làm account."]


def test_time_trailing_newline_and_order(tmp_path: Path) -> None:
    """TC-cli-users-05: giờ có ký tự xuống dòng cuối bị từ chối; lỗi ngày báo trước lỗi config."""
    result = _invoke("--repo", str(tmp_path), *JAN, "--start-time", "08:30" + chr(10))
    assert result.exit_code == 1
    assert "Giờ không hợp lệ cho --start-time" in result.stderr
    result = _invoke("--repo", str(tmp_path), "--start", "2026-1-1", "--end", "2026-01-31",
                     "--config", str(tmp_path / "missing.yaml"))
    assert result.exit_code == 1
    assert "Ngày không hợp lệ cho --start" in result.stderr
