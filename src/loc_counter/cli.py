"""Giao diện dòng lệnh loc-counter (§11)."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sys
from datetime import date, time
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer

from loc_counter import git_repo, identity, pipeline
from loc_counter.config import LocCounterError, config_to_dict, load_config
from loc_counter.counter import CountResult, CrossCheck, count_directory, total_metrics
from loc_counter.git_repo import CommitInfo, GitRepo
from loc_counter.identity import UserSummary, list_period_users, load_identities
from loc_counter.pipeline import STEP_LABELS, AnalysisRequest, AnalysisResult, PipelineError, Step
from loc_counter.report import MANIFEST_NAME
from loc_counter.snapshot import Period, SnapshotError, Snapshots, find_snapshots, make_period

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  pretty_exceptions_show_locals=False)  # traceback không in biến (token)


def _ensure_utf8() -> None:
    """In được tiếng Việt trên console Windows và khi pipe."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def main() -> None:
    """Đếm LOC source code trên Git repository."""
    _ensure_utf8()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True,
                        format="%(levelname)s %(name)s: %(message)s")


def _fail(err: LocCounterError | OSError) -> typer.Exit:
    typer.echo(f"Lỗi: {err}", err=True)
    return typer.Exit(code=1)


def _format_table(headers: list[str], rows: list[list[str]], right: set[int]) -> list[str]:
    """Căn cột: cột trong `right` căn phải, còn lại căn trái."""
    widths = [max(len(r[i]) for r in [headers, *rows]) for i in range(len(headers))]
    lines = []
    for row in [headers, *rows]:
        cells = [c.rjust(w) if i in right else c.ljust(w)
                 for i, (c, w) in enumerate(zip(row, widths, strict=True))]
        lines.append("  ".join(cells).rstrip())
    return lines


def _print_table(root: Path, result: CountResult, by_file: bool) -> None:
    rows = [[lang.language, f"{lang.files:,}", f"{lang.code_lines:,}"]
            for lang in result.by_language()]
    rows.append(["TỔNG", f"{len(result.files):,}", f"{result.total_code:,}"])
    typer.echo(f"Thư mục: {root}")
    for line in _format_table(["Ngôn ngữ", "Số file", "LOC"], rows, right={1, 2}):
        typer.echo(line)
    if by_file:
        typer.echo("")
        file_rows = [[f.path, f.language, f"{f.code_lines:,}", f"{f.total_lines:,}"]
                     for f in result.files]
        for line in _format_table(["Đường dẫn", "Ngôn ngữ", "LOC", "Tổng dòng"],
                                  file_rows, right={2, 3}):
            typer.echo(line)
    if result.warnings:
        typer.echo(f"Cảnh báo: {len(result.warnings)} (dùng --json để xem chi tiết)")


def _print_json(root: Path, config: dict, result: CountResult) -> None:
    data = {
        "root": root.as_posix(),
        "config": config,
        "totals": {"files": len(result.files), "code_lines": result.total_code},
        "languages": [{"language": lang.language, "files": lang.files,
                       "code_lines": lang.code_lines} for lang in result.by_language()],
        "files": [{"path": f.path, "language": f.language, "code_lines": f.code_lines,
                   "total_lines": f.total_lines} for f in result.files],
        "warnings": [{"kind": str(w.kind), "path": w.path, "message": w.message}
                     for w in result.warnings],
    }
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@app.command("count")
def count_command(
    path: Annotated[Path, typer.Argument(help="Thư mục cần đếm")],
    config: Annotated[Path | None, typer.Option("--config", help="File config.yaml")] = None,
    by_file: Annotated[bool, typer.Option("--by-file", help="In chi tiết theo file")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="In kết quả dạng JSON")] = False,
) -> None:
    """Đếm LOC một thư mục bất kỳ."""
    try:
        cfg = load_config(config)
        result = count_directory(path, cfg.filters)
    except LocCounterError as err:
        raise _fail(err) from None
    root = path.resolve()
    if json_output:
        _print_json(root, config_to_dict(cfg), result)
    else:
        _print_table(root, result, by_file)


# ----- phần dùng chung cho users / analyze -----

def _parse_date(text: str, option: str) -> date:
    """Ngày dạng YYYY-MM-DD; sai → LocCounterError."""
    try:
        if not _DATE_RE.fullmatch(text):
            raise ValueError(text)
        return date.fromisoformat(text)
    except ValueError:
        raise LocCounterError(
            f"Ngày không hợp lệ cho {option}: {text} (định dạng YYYY-MM-DD)") from None


def _parse_time(text: str | None, option: str) -> time | None:
    """Giờ dạng HH:MM (None nếu không nhập); sai → LocCounterError."""
    if text is None:
        return None
    try:
        if not _TIME_RE.fullmatch(text):
            raise ValueError(text)
        return time(int(text[:2]), int(text[3:]))
    except ValueError:
        raise LocCounterError(
            f"Giờ không hợp lệ cho {option}: {text} (định dạng HH:MM)") from None


def _read_token(token_env: str | None) -> str | None:
    """Token chỉ đọc từ biến môi trường (§11)."""
    if token_env is None:
        return None
    token = os.environ.get(token_env, "").strip()
    if not token:
        raise LocCounterError(f"Biến môi trường {token_env} chưa được đặt hoặc rỗng.")
    return token


def _open_repo(repo: str, token: str | None) -> GitRepo:
    """GitRepo.open với thư mục cache đọc tại thời điểm gọi."""
    return GitRepo.open(repo, token, cache_root=git_repo.DEFAULT_CACHE_ROOT)


def _resolve_branch(repo: GitRepo, branch: str | None) -> str:
    """Nhánh truyền vào, hoặc nhánh mặc định của repo."""
    if branch:
        return branch
    default = repo.default_branch()
    if default is None:
        raise LocCounterError("Không xác định được nhánh mặc định; hãy truyền --branch.")
    return default


def _parse_period_args(start: str, end: str, start_time: str | None,
                       end_time: str | None) -> tuple[date, date, time | None, time | None]:
    """Kiểm định dạng ngày/giờ (trước khi đọc config — spec cli-users 5.2)."""
    return (_parse_date(start, "--start"), _parse_date(end, "--end"),
            _parse_time(start_time, "--start-time"), _parse_time(end_time, "--end-time"))


# ----- users -----

def _commit_text(commit: CommitInfo, zone: ZoneInfo) -> str:
    when = commit.committer_date.astimezone(zone)
    return f"{commit.short_sha} {when:%Y-%m-%d %H:%M} {commit.subject}"


def _commit_json(commit: CommitInfo | None, zone: ZoneInfo) -> dict | None:
    if commit is None:
        return None
    return {"sha": commit.sha, "short_sha": commit.short_sha,
            "date": commit.committer_date.astimezone(zone).isoformat(),
            "subject": commit.subject}


def _emails(user: UserSummary) -> str:
    return ", ".join(dict.fromkeys(i.email for i in user.identities))


def _print_period_header(source: str, snaps: Snapshots, period: Period) -> None:
    """Dòng Repo, Nhánh/Kỳ, Snapshot start/end (dùng chung cho users và analyze)."""
    zone = ZoneInfo(period.timezone)
    typer.echo(f"Repo: {source}")
    typer.echo(f"Nhánh: {snaps.branch} • Kỳ: {period.start:%Y-%m-%d %H:%M:%S} → "
               f"{period.end:%Y-%m-%d %H:%M:%S} ({period.timezone})")
    start_text = (_commit_text(snaps.c_start, zone) if snaps.c_start
                  else "(không có commit trước start)")
    typer.echo(f"Snapshot start: {start_text}")
    typer.echo(f"Snapshot end:   {_commit_text(snaps.c_end, zone)}")


def _print_users_table(source: str, snaps: Snapshots, period: Period,
                       users: list[UserSummary], warnings: list[str]) -> None:
    _print_period_header(source, snaps, period)
    if users:
        rows = [[u.account, f"{u.commits:,}", f"{u.merge_commits:,}", "bot" if u.is_bot else "",
                 _emails(u)] for u in users]
        for line in _format_table(["User", "Commit", "Merge", "Bot", "Email"], rows,
                                  right={1, 2}):
            typer.echo(line)
    else:
        typer.echo("Không có user nào có commit trong kỳ.")
    total = sum(u.commits for u in users)
    typer.echo(f"TỔNG: {len(users):,} user, {total:,} commit")
    for warning in warnings:
        typer.echo(f"Cảnh báo: {warning}")


def _print_users_json(source: str, snaps: Snapshots, period: Period,
                      users: list[UserSummary], warnings: list[str]) -> None:
    zone = ZoneInfo(period.timezone)
    data = {
        "repo": source,
        "branch": snaps.branch,
        "timezone": period.timezone,
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "c_start": _commit_json(snaps.c_start, zone),
        "c_end": _commit_json(snaps.c_end, zone),
        "users": [{"account": u.account, "commits": u.commits, "merge_commits": u.merge_commits,
                   "is_bot": u.is_bot,
                   "identities": [{"name": i.name, "email": i.email} for i in u.identities]}
                  for u in users],
        "warnings": warnings,
    }
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@app.command("users")
def users_command(
    repo: Annotated[str, typer.Option("--repo", help="URL hoặc đường dẫn repo local")],
    start: Annotated[str, typer.Option("--start", help="Ngày start YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--end", help="Ngày end YYYY-MM-DD")],
    branch: Annotated[str | None, typer.Option("--branch", help="Nhánh (mặc định: nhánh "
                                                "mặc định của repo)")] = None,
    start_time: Annotated[str | None, typer.Option("--start-time", help="Giờ start HH:MM")] = None,
    end_time: Annotated[str | None, typer.Option("--end-time", help="Giờ end HH:MM")] = None,
    tz: Annotated[str | None, typer.Option("--tz", help="Múi giờ IANA")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="File config.yaml")] = None,
    identities: Annotated[Path | None, typer.Option("--identities",
                                                    help="File identities.yaml")] = None,
    token_env: Annotated[str | None, typer.Option("--token-env",
                                                  help="Tên biến môi trường chứa token")] = None,
    exclude_bots: Annotated[bool, typer.Option("--exclude-bots", help="Ẩn user bot")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="In kết quả dạng JSON")] = False,
) -> None:
    """Liệt kê user (account đã gộp) có commit trong kỳ."""
    try:
        dates = _parse_period_args(start, end, start_time, end_time)
        cfg = load_config(config)
        period = make_period(*dates, timezone=tz or cfg.timezone)
        identity_map = load_identities(identities)
        token = _read_token(token_env)
        git = _open_repo(repo, token)
        snaps = find_snapshots(git, _resolve_branch(git, branch), period)
        result = list_period_users(git, snaps, identity_map, token,
                                   login_cache=identity.DEFAULT_LOGIN_CACHE)
    except LocCounterError as err:
        raise _fail(err) from None
    users = [u for u in result.users if not (exclude_bots and u.is_bot)]
    if json_output:
        _print_users_json(git.source, snaps, period, users, result.warnings)
    else:
        _print_users_table(git.source, snaps, period, users, result.warnings)


# ----- analyze -----

def _print_progress(step: Step, index: int, total: int) -> None:
    """In `[i/5] <nhãn>…` ra stderr (ProgressCallback)."""
    typer.echo(f"[{index}/{total}] {STEP_LABELS[step]}…", err=True)


def _signed(value: int) -> str:
    """Số có dấu + hàng nghìn: 0 → '0', 1234 → '+1,234', -5 → '-5'."""
    return f"{value:+,}" if value else "0"


def _check_text(check: CrossCheck) -> str:
    """Dòng kiểm tra chéo của export chính (spec cli-analyze 4.1)."""
    verdict = "đạt" if check.ok else "VƯỢT NGƯỠNG (xem warnings.csv)"
    return (f"Kiểm tra chéo: {check.loc_start:,} + ({_signed(check.sum_net_code)}) = "
            f"{check.expected_loc_end:,}; LOC end {check.loc_end:,}; lệch "
            f"{check.diff_percent:.3f} % (ngưỡng {check.threshold_percent:g} %) → {verdict}")


def _print_analysis_table(result: AnalysisResult) -> None:
    """Tóm tắt kết quả theo §10.3 ra stdout."""
    data = result.data
    opts = data.options
    _print_period_header(data.repo, result.snapshots, data.period)
    if data.all_users:
        who = "Tất cả user" + (" (loại trừ bot)" if opts.exclude_bots else "")
    else:
        who = ", ".join(opts.selected_users or ())
    if opts.separate_users:
        who += " • Xuất riêng từng user"
    typer.echo(f"User: {who}")
    commits = sum(r.commits for r in data.user_rows)
    for line in _format_table(["LOC start", "LOC end", "Chênh lệch", "Commit"],
                              [[f"{data.loc_start:,}", f"{data.loc_end:,}",
                                _signed(data.loc_delta), f"{commits:,}"]], right={0, 1, 2, 3}):
        typer.echo(line)

    typer.echo("")
    typer.echo("Theo ngôn ngữ")
    languages = sorted(data.languages, key=lambda r: (-r.loc_end, -r.loc_start, r.language))
    if languages:
        lang_rows = [[r.language, f"{r.loc_start:,}", f"{r.loc_end:,}", _signed(r.delta)]
                     for r in languages]
        for line in _format_table(["Ngôn ngữ", "LOC start", "LOC end", "Chênh lệch"],
                                  lang_rows, right={1, 2, 3}):
            typer.echo(line)
    else:
        typer.echo("Không có file source nào.")

    typer.echo("")
    typer.echo("Theo user")
    users = sorted(data.user_rows, key=lambda r: (-r.commits, r.account))
    if users:
        total = total_metrics(users)
        user_rows = [[r.account, "bot" if r.is_bot else "", f"{r.commits:,}",
                      f"{r.added_code:,}", f"{r.deleted_code:,}", _signed(r.net_code),
                      f"{r.files_changed:,}"] for r in users]
        user_rows.append(["Tổng", "", f"{total.commits:,}", f"{total.added_code:,}",
                          f"{total.deleted_code:,}", _signed(total.net_code),
                          f"{total.files_changed:,}"])
        for line in _format_table(["User", "Bot", "Commit", "Thêm", "Xóa", "Ròng",
                                   "File thay đổi"], user_rows, right={2, 3, 4, 5, 6}):
            typer.echo(line)
    else:
        typer.echo("Không có user nào có commit trong kỳ.")

    typer.echo("")
    typer.echo(_check_text(data.cross_check))
    typer.echo("Bản export:")
    export_rows = []
    for e in data.exports:
        note = ""
        if e.role == "separate" and e.cross_check is not None:
            note = "kiểm tra chéo: " + ("đạt" if e.cross_check.ok else "VƯỢT NGƯỠNG")
        export_rows.append([e.file_name, f"{e.files:,} file", f"LOC {e.loc:,}", note])
    for line in _format_table(export_rows[0], export_rows[1:], right={1}):
        typer.echo(line)
    count = len(data.warnings)
    typer.echo(f"Cảnh báo: {count}" + (" (xem warnings.csv)" if count else ""))
    typer.echo(f"Thư mục kết quả: {result.out_dir}")


def _print_analysis_json(result: AnalysisResult) -> None:
    """Kết quả dạng JSON ra stdout (spec cli-analyze 4.2)."""
    data = result.data
    out_dir = result.out_dir
    languages = sorted(data.languages, key=lambda r: (-r.loc_end, -r.loc_start, r.language))
    users = sorted(data.user_rows, key=lambda r: (-r.commits, r.account))
    warnings = sorted(data.warnings, key=lambda w: (w.path, w.kind.value))
    payload = {
        "out_dir": out_dir.as_posix(),
        "files": sorted(p.name for p in out_dir.iterdir()),
        "manifest": json.loads((out_dir / MANIFEST_NAME).read_text(encoding="utf-8")),
        "languages": [{"language": r.language, "files_start": r.files_start,
                       "loc_start": r.loc_start, "files_end": r.files_end,
                       "loc_end": r.loc_end, "delta": r.delta} for r in languages],
        "users": [{"account": r.account, "is_bot": r.is_bot, "commits": r.commits,
                   "added_lines": r.added_lines, "deleted_lines": r.deleted_lines,
                   "added_code": r.added_code, "deleted_code": r.deleted_code,
                   "net_code": r.net_code, "files_changed": r.files_changed} for r in users],
        "warnings": [{"kind": str(w.kind), "path": w.path, "message": w.message,
                      "scopes": list(w.scopes)} for w in warnings],
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("analyze")
def analyze_command(
    repo: Annotated[str, typer.Option("--repo", help="URL hoặc đường dẫn repo local")],
    start: Annotated[str, typer.Option("--start", help="Ngày start YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--end", help="Ngày end YYYY-MM-DD")],
    out: Annotated[Path, typer.Option("--out", help="Thư mục đầu ra")],
    branch: Annotated[str | None, typer.Option("--branch", help="Nhánh (mặc định: nhánh "
                                                "mặc định của repo)")] = None,
    start_time: Annotated[str | None, typer.Option("--start-time", help="Giờ start HH:MM")] = None,
    end_time: Annotated[str | None, typer.Option("--end-time", help="Giờ end HH:MM")] = None,
    tz: Annotated[str | None, typer.Option("--tz", help="Múi giờ IANA")] = None,
    user: Annotated[list[str] | None, typer.Option("--user", help="Account cần tính "
                                                   "(lặp được; bỏ trống = tất cả user)")] = None,
    separate_users: Annotated[bool, typer.Option("--separate-users",
                                                 help="Xuất riêng zip từng user")] = False,
    exclude_bots: Annotated[bool, typer.Option("--exclude-bots",
                                               help="Loại bot khỏi 'Tất cả user'")] = False,
    config: Annotated[Path | None, typer.Option("--config", help="File config.yaml")] = None,
    identities: Annotated[Path | None, typer.Option("--identities",
                                                    help="File identities.yaml")] = None,
    token_env: Annotated[str | None, typer.Option("--token-env",
                                                  help="Tên biến môi trường chứa token")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="In kết quả dạng JSON")] = False,
) -> None:
    """Phân tích LOC trong kỳ, xuất zip + báo cáo vào --out."""
    try:
        dates = _parse_period_args(start, end, start_time, end_time)
        cfg = load_config(config)
        period = make_period(*dates, timezone=tz or cfg.timezone)
        identity_map = load_identities(identities)
        token = _read_token(token_env)
        users = tuple(user) if user else None
        with pipeline.run_log(out, secrets=(token,)):
            try:
                git = _open_repo(repo, token)
                chosen = _resolve_branch(git, branch)
                resolver = pipeline.make_resolver(git.source, identity_map, token,
                                                  login_cache=identity.DEFAULT_LOGIN_CACHE)
                request = AnalysisRequest(branch=chosen, period=period, config=cfg, out_root=out,
                                          users=users, exclude_bots=exclude_bots,
                                          separate_users=separate_users)
                result = pipeline.run_analysis(git, request, resolver, progress=_print_progress)
            except (LocCounterError, OSError) as err:
                if not isinstance(err, PipelineError | SnapshotError):  # pipeline đã log (A9)
                    logger.error("Lỗi: %s", err)  # run.log luôn có nguyên nhân
                raise
    except (LocCounterError, OSError) as err:
        raise _fail(err) from None
    except KeyboardInterrupt:
        typer.echo("Đã hủy phân tích.", err=True)
        raise typer.Exit(code=130) from None
    if json_output:
        try:
            _print_analysis_json(result)
        except (OSError, ValueError) as err:
            raise _fail(LocCounterError(f"Không đọc được {MANIFEST_NAME}: {err}")) from None
    else:
        _print_analysis_table(result)
