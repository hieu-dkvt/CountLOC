"""Test cho lệnh `loc-counter analyze` (spec docs/specs/cli-analyze.md)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import build_cross_check_mismatch
from typer.testing import CliRunner

from loc_counter import cli, git_repo, identity, pipeline
from loc_counter.cli import app
from loc_counter.counter import cross_check
from loc_counter.git_repo import GitError

runner = CliRunner()
JAN = ["--start", "2026-01-01", "--end", "2026-01-31"]
TOKEN = "ghp_SECRET123"
ALL_DIR = "repo_main_2026-01-01_2026-01-31_all"
BOT = "dependabot[bot]"
IDS_YAML = """identities:
  - email: alice@example.com
    account: alice
  - email: bob@example.com
    account: bob
"""
PROGRESS = ["[1/5] Export start…", "[2/5] Gán tác giả…", "[3/5] Export end…",
            "[4/5] Đếm LOC…", "[5/5] Tạo báo cáo…"]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Cache repo / login trong tmp_path; identities.yaml gộp alice, bob."""
    monkeypatch.setattr(git_repo, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(identity, "DEFAULT_LOGIN_CACHE", tmp_path / "logins.json")
    ids = tmp_path / "identities.yaml"
    ids.write_text(IDS_YAML, encoding="utf-8")
    return SimpleNamespace(ids=ids, out=tmp_path / "out", tmp=tmp_path)


@pytest.fixture
def repo14(section14_repo, env: SimpleNamespace) -> str:
    """Repo §14 tên `repo`."""
    return str(section14_repo(name="repo").src.path)


def invoke(*args: str):  # noqa: ANN201
    return runner.invoke(app, ["analyze", *args])


def base(repo: str, env: SimpleNamespace, *extra: str, out: Path | None = None) -> list[str]:
    return ["--repo", repo, "--branch", "main", *JAN, "--identities", str(env.ids),
            "--out", str(out or env.out), *extra]


def rows(output: str) -> list[list[str]]:
    return [line.split() for line in output.splitlines()]


def export_lines(output: str) -> list[str]:
    lines = output.splitlines()
    i = lines.index("Bản export:")
    j = next(k for k in range(i, len(lines)) if lines[k].startswith("Cảnh báo:"))
    return lines[i + 1:j]


def digests(path: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.iterdir())}


def manifest_of(path: Path) -> dict[str, Any]:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


# ---------- TC-01 .. TC-07: §14 ----------
def test_all_users_table(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-01: tất cả user — bảng tổng, theo user, kiểm tra chéo, thư mục."""
    r = invoke(*base(repo14, env))
    assert r.exit_code == 0, r.output
    lines = r.stdout.splitlines()
    assert lines[0].startswith("Repo: ")
    assert lines[1] == ("Nhánh: main • Kỳ: 2026-01-01 00:00:00 → 2026-01-31 23:59:59 "
                        "(Asia/Bangkok)")
    assert lines[2].startswith("Snapshot start: ") and "2025-12-15 10:00 admin: app.py" in lines[2]
    assert lines[3].startswith("Snapshot end:   ") and "2026-01-08 10:00 bob del" in lines[3]
    assert lines[4] == "User: Tất cả user"
    table = rows(r.stdout)
    assert ["10", "20", "+10", "4"] in table
    assert ["Python", "10", "20", "+10"] in table
    assert ["alice", "2", "5", "2", "+3", "1"] in table
    assert ["bob", "2", "8", "1", "+7", "2"] in table
    assert ["Tổng", "4", "13", "3", "+10", "2"] in table
    assert ("Kiểm tra chéo: 10 + (+10) = 20; LOC end 20; lệch 0.000 % (ngưỡng 0.5 %) → đạt"
            in lines)
    assert "Cảnh báo: 0" in lines
    assert lines[-1] == f"Thư mục kết quả: {(env.out / ALL_DIR).resolve()}"


def test_only_alice(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-02: --user alice — 10/13, chỉ alice, thư mục …_alice."""
    r = invoke(*base(repo14, env, "--user", "alice"))
    assert r.exit_code == 0, r.output
    table = rows(r.stdout)
    assert ["10", "13", "+3", "2"] in table
    assert "User: alice" in r.stdout.splitlines()
    assert not [row for row in table if row and row[0] == "bob"]
    assert ["alice", "2", "5", "2", "+3", "1"] in table
    assert (env.out / "repo_main_2026-01-01_2026-01-31_alice").is_dir()
    assert any(line.startswith("end_2026-01-31_alice.zip") for line in export_lines(r.stdout))


def test_only_bob(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-03: --user bob — 10/17, thư mục …_bob."""
    r = invoke(*base(repo14, env, "--user", "bob"))
    assert r.exit_code == 0, r.output
    assert ["10", "17", "+7", "2"] in rows(r.stdout)
    assert (env.out / "repo_main_2026-01-01_2026-01-31_bob").is_dir()


def test_alice_and_bob(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-04: alice + bob, có / không --separate-users."""
    r = invoke(*base(repo14, env, "--user", "bob", "--user", "alice"))
    assert r.exit_code == 0, r.output
    assert ["10", "20", "+10", "4"] in rows(r.stdout)
    assert "User: alice, bob" in r.stdout.splitlines()
    assert (env.out / "repo_main_2026-01-01_2026-01-31_multi-2users").is_dir()
    assert len(export_lines(r.stdout)) == 2

    s = invoke(*base(repo14, env, "--user", "bob", "--user", "alice", "--separate-users"))
    assert s.exit_code == 0, s.output
    assert "User: alice, bob • Xuất riêng từng user" in s.stdout.splitlines()
    ex = export_lines(s.stdout)
    assert len(ex) == 4
    assert ex[0].startswith("start_") and ex[1].startswith("end_2026-01-31_multi-2users.zip")
    assert ex[2].startswith("end_2026-01-31_alice.zip") and "LOC 13" in ex[2]
    assert ex[3].startswith("end_2026-01-31_bob.zip") and "LOC 17" in ex[3]
    assert all(line.endswith("kiểm tra chéo: đạt") for line in ex[2:])
    assert "kiểm tra chéo" not in ex[0] + ex[1]


def test_output_files_and_run_log(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-05: đủ file §12, run.log có INFO C_START=, không sót thư mục tạm."""
    r = invoke(*base(repo14, env))
    assert r.exit_code == 0, r.output
    result_dir = env.out / ALL_DIR
    names = sorted(p.name for p in result_dir.iterdir())
    starts = [n for n in names if n.startswith("start_2026-01-01_")]
    assert len(starts) == 1 and len(starts[0]) == len("start_2026-01-01_") + 7 + len(".zip")
    assert sorted(set(names) - set(starts)) == sorted([
        "end_2026-01-31_all.zip", "loc_report.xlsx", "loc_by_user.csv", "loc_by_language.csv",
        "loc_by_file.csv", "warnings.csv", "manifest.json"])
    log = (env.out / "run.log").read_text(encoding="utf-8")
    assert any(" INFO " in line and "C_START=" in line for line in log.splitlines())
    assert not [p for p in env.out.iterdir() if p.name.startswith((".loc-tmp-", ".loc-old-"))]


def test_json(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-06: --json — stdout chỉ JSON, manifest trùng file, thứ tự ổn định."""
    r = invoke(*base(repo14, env, "--json"))
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert list(data) == ["out_dir", "files", "manifest", "languages", "users", "warnings"]
    result_dir = (env.out / ALL_DIR).resolve()
    assert data["out_dir"] == result_dir.as_posix()
    assert data["manifest"] == manifest_of(result_dir)
    assert data["files"] == sorted(p.name for p in result_dir.iterdir())
    assert len(data["files"]) == 8
    assert [u["account"] for u in data["users"]] == ["alice", "bob"]
    assert data["users"][0]["net_code"] == 3 and data["users"][1]["files_changed"] == 2
    assert data["languages"][0]["delta"] == 10
    assert data["warnings"] == []


@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_progress_to_stderr(repo14: str, env: SimpleNamespace, extra: tuple[str, ...]) -> None:
    """TC-cli-analyze-07: tiến độ 5 bước ra stderr đúng thứ tự, không có trong stdout."""
    r = invoke(*base(repo14, env, *extra))
    assert r.exit_code == 0, r.output
    found = [line for line in r.stderr.splitlines() if line.startswith("[")]
    assert found == PROGRESS
    assert "[1/5]" not in r.stdout


# ---------- TC-08 .. TC-12: lỗi ----------
def test_user_not_found_and_casefold(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-08: --user zz → mã 1 liệt kê user; --user ALICE → khớp alice."""
    r = invoke(*base(repo14, env, "--user", "zz"))
    assert r.exit_code == 1
    message = "Không tìm thấy user 'zz' trong kỳ. User trong kỳ: alice, bob"
    assert f"Lỗi: {message}" in r.stderr
    assert sorted(p.name for p in env.out.iterdir()) == ["run.log"]
    log = (env.out / "run.log").read_text(encoding="utf-8").splitlines()
    assert len([line for line in log if " ERROR " in line and message in line]) == 1

    ok = invoke(*base(repo14, env, "--user", "ALICE"))
    assert ok.exit_code == 0, ok.output
    assert (env.out / "repo_main_2026-01-01_2026-01-31_alice").is_dir()


def test_no_data(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-09: không có commit trước end → mã 1, chỉ có run.log (có ERROR)."""
    args = base(repo14, env)
    args[args.index("2026-01-01")] = "2020-01-01"
    args[args.index("2026-01-31")] = "2020-01-31"
    r = invoke(*args)
    assert r.exit_code == 1
    assert "Lỗi: Không có dữ liệu trong khoảng thời gian" in r.stderr
    assert sorted(p.name for p in env.out.iterdir()) == ["run.log"]
    assert " ERROR " in (env.out / "run.log").read_text(encoding="utf-8")


def test_bad_arguments_create_nothing(repo14: str, env: SimpleNamespace,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-10: tham số sai → mã 1, thông báo mục 7, không tạo --out."""
    monkeypatch.delenv("NOPE", raising=False)
    bad_config = env.tmp / "bad.yaml"
    bad_config.write_text("filters: [\n", encoding="utf-8")
    out = env.tmp / "new"
    common = ["--repo", repo14, "--branch", "main", "--out", str(out)]
    cases = [
        (["--start", "2026-13-01", "--end", "2026-01-31"],
         "Lỗi: Ngày không hợp lệ cho --start: 2026-13-01 (định dạng YYYY-MM-DD)"),
        ([*JAN, "--end-time", "25:00"],
         "Lỗi: Giờ không hợp lệ cho --end-time: 25:00 (định dạng HH:MM)"),
        (["--start", "2026-02-01", "--end", "2026-01-01"], "phải trước end"),
        ([*JAN, "--tz", "Mars/X"], "Múi giờ không hợp lệ: Mars/X"),
        ([*JAN, "--config", str(bad_config)], "Lỗi: File cấu hình không đúng định dạng YAML"),
        ([*JAN, "--token-env", "NOPE"],
         "Lỗi: Biến môi trường NOPE chưa được đặt hoặc rỗng."),
    ]
    for extra, message in cases:
        r = invoke(*common, *extra)
        assert r.exit_code == 1, (extra, r.output)
        assert message in r.stderr, (extra, r.stderr)
        assert not out.exists(), extra


def test_missing_required(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-11: thiếu --out / --repo → mã 2."""
    assert invoke("--repo", repo14, *JAN).exit_code == 2
    assert invoke(*JAN, "--out", str(env.out)).exit_code == 2


def test_out_is_file(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-12: --out là file → mã 1, file nguyên vẹn."""
    target = env.tmp / "out.txt"
    target.write_text("giữ nguyên", encoding="utf-8")
    r = invoke(*base(repo14, env, out=target))
    assert r.exit_code == 1
    assert f"Lỗi: Thư mục đầu ra là một file: {target.resolve()}" in r.stderr
    assert target.read_text(encoding="utf-8") == "giữ nguyên"


# ---------- TC-13: token ----------
def _all_bytes(root: Path) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        data = p.read_bytes()
        out.append((str(p), data))
        if p.suffix in (".zip", ".xlsx"):
            with zipfile.ZipFile(p) as zf:
                out += [(f"{p}!{n}", zf.read(n)) for n in zf.namelist()]
    return out


def test_token_not_leaked(repo14: str, env: SimpleNamespace,
                          monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-13: token không có trong stdout, stderr, run.log, kết quả, cache."""
    monkeypatch.setenv("MYTOK", TOKEN)
    r = invoke(*base(repo14, env, "--token-env", "MYTOK"))
    assert r.exit_code == 0, r.output
    assert TOKEN not in r.stdout and TOKEN not in r.stderr
    for name, data in _all_bytes(env.out) + _all_bytes(env.tmp / "cache"):
        assert TOKEN.encode() not in data, name


# ---------- TC-14 .. TC-21: trường hợp nghiệp vụ ----------
def test_bots(section14_repo, env: SimpleNamespace) -> None:
    """TC-cli-analyze-14: bot hiện mặc định; --exclude-bots loại; chọn tường minh thắng."""
    repo = str(section14_repo(bot=True, name="repo").src.path)
    a = invoke(*base(repo, env))
    assert a.exit_code == 0, a.output
    assert [BOT, "bot", "1", "0", "0", "0", "0"] in rows(a.stdout)

    b = invoke(*base(repo, env, "--exclude-bots"))
    assert b.exit_code == 0, b.output
    assert "User: Tất cả user (loại trừ bot)" in b.stdout.splitlines()
    assert BOT not in b.stdout
    assert any(line.startswith("Kiểm tra chéo:") and line.endswith("→ đạt")
               for line in b.stdout.splitlines())

    c = invoke(*base(repo, env, "--user", BOT, "--exclude-bots"))
    assert c.exit_code == 0, c.output
    assert f"User: {BOT}" in c.stdout.splitlines()
    assert [row for row in rows(c.stdout) if row[:2] == [BOT, "bot"]]


def test_empty_start(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-15: C_START rỗng — LOC start 0, zip start rỗng, admin trong Theo user."""
    args = base(repo14, env)
    args[args.index("2026-01-01")] = "2025-01-01"
    r = invoke(*args)
    assert r.exit_code == 0, r.output
    assert "Snapshot start: (không có commit trước start)" in r.stdout.splitlines()
    table = rows(r.stdout)
    assert ["0", "20", "+20", "5"] in table
    assert ["start_2025-01-01_empty.zip", "0", "file", "LOC", "0"] in table
    assert [row for row in table if row and row[0] == "admin@example.com"]


def test_no_commit_in_period(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-16: kỳ không có commit — không có user, không dòng Tổng, đạt."""
    args = base(repo14, env)
    args[args.index("2026-01-01")] = "2026-01-09"
    args[args.index("2026-01-31")] = "2026-01-20"
    r = invoke(*args)
    assert r.exit_code == 0, r.output
    lines = r.stdout.splitlines()
    assert "Không có user nào có commit trong kỳ." in lines
    assert not [row for row in rows(r.stdout) if row and row[0] == "Tổng"]
    assert ["20", "20", "0", "0"] in rows(r.stdout)
    assert any(line.startswith("Kiểm tra chéo:") and line.endswith("→ đạt") for line in lines)


def test_cross_check_mismatch(make_repo, env: SimpleNamespace) -> None:
    """TC-cli-analyze-17: kiểm tra chéo lệch → mã 0, VƯỢT NGƯỠNG, số cảnh báo ≥ 1."""
    src = build_cross_check_mismatch(make_repo("repo"))
    r = invoke(*base(str(src.path), env))
    assert r.exit_code == 0, r.output
    lines = r.stdout.splitlines()
    check = next(line for line in lines if line.startswith("Kiểm tra chéo:"))
    assert check.endswith("→ VƯỢT NGƯỠNG (xem warnings.csv)")
    warn = next(line for line in lines if line.startswith("Cảnh báo:"))
    count = int(warn.split()[2])
    assert count >= 1 and warn == f"Cảnh báo: {count} (xem warnings.csv)"


def test_rerun_and_reproducible(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-18: chạy lại cùng --out thay thư mục; hai --out trùng SHA-256."""
    assert invoke(*base(repo14, env)).exit_code == 0
    first = env.out / ALL_DIR
    (first / "stray.txt").write_text("x", encoding="utf-8")
    assert invoke(*base(repo14, env)).exit_code == 0
    assert not (first / "stray.txt").exists()
    out2 = env.tmp / "out2"
    assert invoke(*base(repo14, env, out=out2)).exit_code == 0
    d1, d2 = digests(first), digests(out2 / ALL_DIR)
    assert d1.keys() == d2.keys()
    assert {k: v for k, v in d1.items() if k != "manifest.json"} == {
        k: v for k, v in d2.items() if k != "manifest.json"}
    m1, m2 = manifest_of(first), manifest_of(out2 / ALL_DIR)
    m1.pop("generated_at")
    m2.pop("generated_at")
    assert m1 == m2


def test_identities_merge(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-19: identities gộp alice, bob → team."""
    env.ids.write_text(IDS_YAML.replace("account: alice", "account: team")
                       .replace("account: bob", "account: team"), encoding="utf-8")
    r = invoke(*base(repo14, env))
    assert r.exit_code == 0, r.output
    table = rows(r.stdout)
    assert ["team", "4", "13", "3", "+10", "2"] in table
    assert not [row for row in table if row and row[0] in ("alice", "bob")]


def test_branch(repo14: str, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-20: không --branch → main; --branch nope / không có nhánh mặc định → mã 1."""
    args = base(repo14, env)
    del args[2:4]
    r = invoke(*args)
    assert r.exit_code == 0, r.output
    assert (env.out / ALL_DIR).is_dir()

    bad = invoke(*args, "--branch", "nope")
    assert bad.exit_code == 1
    assert "Lỗi: Không tìm thấy nhánh: nope" in bad.stderr
    assert " ERROR " in (env.out / "run.log").read_text(encoding="utf-8")

    monkeypatch.setattr(git_repo.GitRepo, "default_branch", lambda self: None)
    none = invoke(*args)
    assert none.exit_code == 1
    assert "Lỗi: Không xác định được nhánh mặc định; hãy truyền --branch." in none.stderr


def test_time_and_timezone(repo14: str, env: SimpleNamespace) -> None:
    """TC-cli-analyze-21: --start-time 08:30 --tz UTC → dòng Kỳ, thư mục, manifest."""
    r = invoke(*base(repo14, env, "--start-time", "08:30", "--tz", "UTC"))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines()[1] == ("Nhánh: main • Kỳ: 2026-01-01 08:30:00 → "
                                        "2026-01-31 23:59:59 (UTC)")
    result_dir = env.out / "repo_main_2026-01-01T0830_2026-01-31_all"
    assert manifest_of(result_dir)["timezone"] == "UTC"


# ---------- TC-22 .. TC-24: unit ----------
def test_unexpected_errors(repo14: str, env: SimpleNamespace,
                           monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-22: OSError → mã 1; Ctrl+C → 130; GitError khi mở repo → run.log có ERROR."""
    def raise_(exc: BaseException) -> Any:
        def fn(*_a: Any, **_k: Any) -> Any:
            raise exc
        return fn

    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", raise_(OSError("đĩa đầy")))
        r = invoke(*base(repo14, env))
    assert r.exit_code == 1 and "Lỗi: đĩa đầy" in r.stderr

    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", raise_(KeyboardInterrupt()))
        r = invoke(*base(repo14, env))
    assert r.exit_code == 130 and "Đã hủy phân tích." in r.stderr

    with monkeypatch.context() as m:
        m.setattr(cli, "_open_repo", raise_(GitError("Không có quyền truy cập repo giả")))
        r = invoke(*base(repo14, env))
    assert r.exit_code == 1 and "Lỗi: Không có quyền truy cập repo giả" in r.stderr
    log = (env.out / "run.log").read_text(encoding="utf-8")
    assert any(" ERROR " in line and "Không có quyền truy cập repo giả" in line
               for line in log.splitlines())

    orig = pipeline.run_analysis

    def drop_manifest(*a: Any, **k: Any) -> Any:
        res = orig(*a, **k)
        (res.out_dir / "manifest.json").unlink()
        return res

    with monkeypatch.context() as m:
        m.setattr(pipeline, "run_analysis", drop_manifest)
        r = invoke(*base(repo14, env, "--json"))
    assert r.exit_code == 1 and "Lỗi: Không đọc được manifest.json:" in r.stderr
    assert "Traceback" not in r.output
    assert app.pretty_exceptions_show_locals is False


def test_arguments_to_pipeline(repo14: str, env: SimpleNamespace,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-23: tham số truyền cho make_resolver / run_analysis."""
    calls: dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]] = {"res": [], "run": []}
    orig_res, orig_run = pipeline.make_resolver, pipeline.run_analysis

    def spy_res(*a: Any, **k: Any) -> Any:
        calls["res"].append((a, k))
        return orig_res(*a, **k)

    def spy_run(*a: Any, **k: Any) -> Any:
        calls["run"].append((a, k))
        return orig_run(*a, **k)

    monkeypatch.setattr(pipeline, "make_resolver", spy_res)
    monkeypatch.setattr(pipeline, "run_analysis", spy_run)
    monkeypatch.setenv("MYTOK", TOKEN)
    assert invoke(*base(repo14, env, "--token-env", "MYTOK")).exit_code == 0
    assert invoke(*base(repo14, env, "--user", "bob", "--user", "alice", "--exclude-bots",
                        "--separate-users")).exit_code == 0

    assert calls["res"][0][1]["login_cache"] == identity.DEFAULT_LOGIN_CACHE
    (args1, kw1), (args2, kw2) = calls["run"]
    req1, req2 = args1[1], args2[1]
    assert req1.users is None and req2.users == ("bob", "alice")
    assert (req1.exclude_bots, req1.separate_users) == (False, False)
    assert (req2.exclude_bots, req2.separate_users) == (True, True)
    assert req1.out_root == env.out and req1.branch == "main"
    assert kw1["progress"] is not None
    assert TOKEN not in repr(req1)


def test_number_format(repo14: str, env: SimpleNamespace,
                       monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-24: _signed; số ≥ 1.000 có dấu phẩy, căn phải; Cảnh báo: 0."""
    assert cli._signed(0) == "0"
    assert cli._signed(1234) == "+1,234"
    assert cli._signed(-5) == "-5"

    orig = pipeline.run_analysis

    def bigger(*a: Any, **k: Any) -> Any:
        res = orig(*a, **k)
        d = res.data
        users = tuple(dataclasses.replace(u, added_code=u.added_code + 1000)
                      if u.account == "alice" else u for u in d.user_rows)
        langs = tuple(dataclasses.replace(lang, loc_end=lang.loc_end + 1000)
                      for lang in d.languages)
        check = cross_check(d.loc_start, d.loc_end + 1000, [u.net_code for u in users])
        data = dataclasses.replace(d, loc_end=d.loc_end + 1000, user_rows=users,
                                   languages=langs, cross_check=check)
        return dataclasses.replace(res, data=data)

    monkeypatch.setattr(pipeline, "run_analysis", bigger)
    r = invoke(*base(repo14, env))
    assert r.exit_code == 0, r.output
    lines = r.stdout.splitlines()
    table = rows(r.stdout)
    assert ["10", "1,020", "+1,010", "4"] in table
    assert ["Python", "10", "1,020", "+1,010"] in table
    assert ["alice", "2", "1,005", "2", "+1,003", "1"] in table
    assert ["Tổng", "4", "1,013", "3", "+1,010", "2"] in table
    header = next(i for i, line in enumerate(lines) if line.startswith("LOC start"))
    head, row = lines[header], lines[header + 1]
    assert head.index("LOC end") + len("LOC end") == row.index("1,020") + len("1,020")
    assert "Cảnh báo: 0" in lines

    def no_languages(*a: Any, **k: Any) -> Any:
        res = orig(*a, **k)
        return dataclasses.replace(res, data=dataclasses.replace(res.data, languages=()))

    monkeypatch.setattr(pipeline, "run_analysis", no_languages)
    empty = invoke(*base(repo14, env))
    assert empty.exit_code == 0, empty.output
    lines = empty.stdout.splitlines()
    assert lines[lines.index("Theo ngôn ngữ") + 1] == "Không có file source nào."


def test_attribution_option(repo14: str, env: SimpleNamespace,
                            monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-cli-analyze-26: --attribution line | last-commit."""
    modes: list[str] = []
    orig_run = pipeline.run_analysis

    def spy_run(*a: Any, **k: Any) -> Any:
        modes.append(a[1].attribution_mode)
        return orig_run(*a, **k)

    monkeypatch.setattr(pipeline, "run_analysis", spy_run)
    plain = invoke(*base(repo14, env))
    assert plain.exit_code == 0 and "Cách gán tác giả:" not in plain.output
    last = invoke(*base(repo14, env, "--attribution", "last-commit", out=env.tmp / "out2"))
    assert last.exit_code == 0
    assert "Cách gán tác giả: Theo commit cuối cùng của file" in last.output
    assert modes == ["line", "last_commit"]
    assert manifest_of(env.tmp / "out2" / ALL_DIR)["options"]["attribution_mode"] == "last_commit"
    bad = invoke(*base(repo14, env, "--attribution", "x", out=env.tmp / "out3"))
    assert bad.exit_code == 2 and not (env.tmp / "out3").exists()
