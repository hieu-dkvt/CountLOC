"""Một lần phân tích: export start/end, gán tác giả, đếm LOC, báo cáo (§3, §8, §12, M5)."""

from __future__ import annotations

import contextvars
import dataclasses
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import weakref
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import StrEnum
from pathlib import Path
from secrets import token_hex
from time import sleep
from zoneinfo import ZoneInfo

from loc_counter.attribution import AttributionMode, PeriodAttribution, attribute_period
from loc_counter.builder import (
    UserExport,
    build_user_export,
    export_from_plan,
    path_conflict_warnings,
    plan_end_exports,
    windows_path_warnings,
    write_user_export,
)
from loc_counter.classifier import LineClassifier
from loc_counter.config import AppConfig, FilterConfig, LocCounterError
from loc_counter.counter import (
    CountResult,
    LocWarning,
    WarningKind,
    compare_files,
    compare_languages,
    count_export,
    cross_check,
    cross_check_warning,
    rename_map,
    user_metrics,
    weekly_metrics,
)
from loc_counter.git_repo import GitRepo, LogCommit, mask_secrets
from loc_counter.identity import (
    AccountResolver,
    GitHubLoginResolver,
    IdentityMap,
    UsersResult,
    UserSummary,
    github_repo_of,
    summarize_users,
)
from loc_counter.report import (
    FILE_CSV_NAME,
    LANGUAGE_CSV_NAME,
    MANIFEST_NAME,
    SCOPE_ATTRIBUTION,
    SCOPE_CROSS_CHECK,
    SCOPE_IDENTITY,
    SCOPE_START,
    USER_CSV_NAME,
    WARNINGS_CSV_NAME,
    XLSX_NAME,
    ExportSummary,
    ReportData,
    ReportOptions,
    ReportWarning,
    end_scope,
    write_reports,
)
from loc_counter.snapshot import (
    Period,
    SnapshotError,
    Snapshots,
    end_zip_name,
    find_snapshots,
    plan_export,
    safe_name,
    start_zip_name,
    write_zip,
    zip_timestamp,
)

logger = logging.getLogger(__name__)

RUN_LOG_NAME = "run.log"
_REPLACE_RETRIES = 10             # số lần thử os.replace khi Windows báo Access denied
TMP_PREFIX = ".loc-tmp-"        # thư mục tạm trong <out>
OLD_PREFIX = ".loc-old-"          # thư mục cũ đang chờ xóa
NAME_PART_MAX = 40                # độ dài tối đa <repo>, <branch> trong tên thư mục
WINDOWS_MAX_PATH = 259            # khi Windows chưa bật long path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_PACKAGE_LOGGER = "loc_counter"
_MANIFEST_KEYS = ("tool_version", "c_end", "exports")
_REPORT_NAMES = (XLSX_NAME, USER_CSV_NAME, LANGUAGE_CSV_NAME, FILE_CSV_NAME, WARNINGS_CSV_NAME,
                 MANIFEST_NAME)
_LIST_MAX = 20
_SOURCE_SPLIT_RE = re.compile(r"[/\\:]")
_LONG_PATHS_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"
_NAME_SAMPLE = "9" * 10 + "-" + "f" * 8  # <pid tối đa 10 chữ số>-<8 hex>

# level logger loc_counter dùng chung cả tiến trình: đếm số phiên run_log đang mở (A18)
_LEVEL_LOCK = threading.Lock()
_level_sessions = 0
_saved_level = logging.NOTSET
# mã phiên run_log; luồng con chạy qua contextvars.copy_context() mang theo (A22)
_RUN_LOG_ID: contextvars.ContextVar[str] = contextvars.ContextVar("loc_counter_run_log")


class Step(StrEnum):
    """Các bước tiến độ của một lần phân tích (§10.2)."""

    EXPORT_START = "export_start"
    ATTRIBUTION = "attribution"
    EXPORT_END = "export_end"
    COUNT = "count"
    REPORT = "report"


STEP_LABELS: Mapping[Step, str] = {
    Step.EXPORT_START: "Export start", Step.ATTRIBUTION: "Gán tác giả",
    Step.EXPORT_END: "Export end", Step.COUNT: "Đếm LOC", Step.REPORT: "Tạo báo cáo",
}
ProgressCallback = Callable[[Step, int, int], None]   # (bước, thứ tự 1-based, tổng = 5)


class PipelineError(LocCounterError):
    """Lỗi của pipeline (thông báo tiếng Việt)."""


@dataclass(frozen=True)
class AnalysisRequest:
    """Yêu cầu phân tích (không chứa token)."""

    branch: str
    period: Period
    config: AppConfig
    out_root: Path
    users: tuple[str, ...] | None = None
    exclude_bots: bool = False
    separate_users: bool = False
    attribution_mode: AttributionMode = "line"


@dataclass(frozen=True)
class PeriodContext:
    """C_START / C_END, commit và user trong kỳ (dùng lại giữa UI và run_analysis)."""

    branch: str
    period: Period
    snapshots: Snapshots
    commits: tuple[LogCommit, ...]
    users: UsersResult
    # (FilterConfig, chế độ gán) → (weakref resolver, PeriodAttribution) đã tính; tối đa 1 phần tử.
    # init=False: replace() tạo memo rỗng mới; weakref: ctx không giữ resolver (token) — A21
    attribution_memo: dict[tuple[FilterConfig, str],
                           tuple[weakref.ref[AccountResolver], PeriodAttribution]] = (
        field(default_factory=dict, init=False, compare=False, repr=False))


@dataclass(frozen=True)
class AnalysisResult:
    """Kết quả một lần phân tích cho CLI / UI."""

    out_dir: Path
    data: ReportData
    snapshots: Snapshots
    period_users: tuple[UserSummary, ...]
    start_zip: Path
    end_zips: tuple[Path, ...]
    report_files: tuple[Path, ...]
    generated_at: datetime


def _error(message: str) -> PipelineError:
    """Log ERROR rồi trả PipelineError cùng thông báo."""
    logger.error("%s", message)
    return PipelineError(message)


# ---------- resolver, kỳ, chọn user ----------
def make_resolver(source: str, identities: IdentityMap | None, token: str | None,
                  login_cache: Path | None = None) -> AccountResolver:
    """AccountResolver dùng chung; bật GitHub API khi nguồn là GitHub và có token."""
    gh = github_repo_of(source)
    github = GitHubLoginResolver(*gh, token, cache_path=login_cache) if gh and token else None
    return AccountResolver(identities, github)


def prepare_period(repo: GitRepo, branch: str, period: Period,
                   resolver: AccountResolver) -> PeriodContext:
    """find_snapshots + log_commits + summarize_users (dùng trước khi bấm Phân tích ở UI)."""
    try:
        snaps = find_snapshots(repo, branch, period)
    except SnapshotError as exc:
        logger.error("%s", exc)
        raise
    c_start = snaps.c_start.sha if snaps.c_start else None
    commits = repo.log_commits(snaps.c_end.sha, c_start, mailmap_rev=snaps.c_end.sha)
    users = summarize_users(commits, resolver)
    logger.info("C_START=%s, C_END=%s", c_start or "rỗng", snaps.c_end.sha)
    logger.info("%d commit, %d user trong kỳ", len(commits), len(users.users))
    return PeriodContext(branch, period, snaps, tuple(commits), users)


def match_users(requested: Sequence[str], period_users: Sequence[UserSummary]) -> tuple[str, ...]:
    """Khớp user yêu cầu với account trong kỳ (D40-N19); trả tuple account đã sắp, không trùng."""
    if not requested:
        raise _error("Chưa chọn user nào.")
    if not period_users:
        raise _error("Không có user nào có commit trong kỳ; không thể chọn user.")
    accounts = [u.account for u in period_users]
    exact = set(accounts)
    chosen: set[str] = set()
    for raw in requested:
        name = raw.strip()
        if name in exact:
            chosen.add(name)
            continue
        folded = name.casefold()
        candidates = [a for a in accounts if a.casefold() == folded]
        if len(candidates) == 1:
            chosen.add(candidates[0])
        elif candidates:
            raise _error(f"User '{name}' khớp nhiều account chỉ khác hoa thường: "
                         f"{', '.join(candidates)}. Hãy nhập chính xác.")
        else:
            listed = ", ".join(accounts[:_LIST_MAX])
            if len(accounts) > _LIST_MAX:
                listed += f", … và {len(accounts) - _LIST_MAX} user khác"
            raise _error(f"Không tìm thấy user '{name}' trong kỳ. User trong kỳ: {listed}")
    return tuple(sorted(chosen))


# ---------- tên thư mục kết quả ----------
def _name_part(text: str) -> str:
    """safe_name; dài hơn NAME_PART_MAX → 33 ký tự + '-' + sha1[:6] của chuỗi gốc."""
    safe = safe_name(text)
    if len(safe) <= NAME_PART_MAX:
        return safe
    digest = hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:6]
    return f"{safe[:NAME_PART_MAX - 7]}-{digest}"


def _repo_name(source: str) -> str:
    """Đoạn cuối khác rỗng của nguồn (tách / \\ :), bỏ đuôi .git; không có → 'repo'."""
    segments = _SOURCE_SPLIT_RE.split(source)
    while segments:
        last = segments.pop()
        name = last[:-4] if last.lower().endswith(".git") else last
        if name:
            return name
    return "repo"


def result_dir_name(source: str, branch: str, period: Period, tag: str) -> str:
    """<repo>_<branch>_<start>_<end>_<user-tag> (D40-N10)."""
    start = f"{period.start_date:%Y-%m-%d}"
    if period.start.time() != time(0, 0, 0):
        start += f"T{period.start:%H%M}"
    end = f"{period.end_date:%Y-%m-%d}"
    if period.end.time() != time(23, 59, 59):
        end += f"T{period.end:%H%M}"
    return f"{_name_part(_repo_name(source))}_{_name_part(branch)}_{start}_{end}_{tag}"


# ---------- run.log ----------
class _MaskingFormatter(logging.Formatter):
    """Formatter che secret (cả dạng base64 x-access-token) trong message lẫn traceback."""

    def __init__(self, fmt: str, secrets: Sequence[str | None]) -> None:
        super().__init__(fmt)
        self._secrets = tuple(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return mask_secrets(super().format(record), self._secrets)


def _prepare_out_root(out_root: Path) -> Path:
    """Resolve thư mục đầu ra; là file → lỗi; chưa có → tạo."""
    out_root = Path(out_root).resolve()
    if out_root.exists() and not out_root.is_dir():
        raise _error(f"Thư mục đầu ra là một file: {out_root}")
    if not out_root.exists():
        try:
            out_root.mkdir(parents=True)
        except OSError as exc:
            raise _error(f"Không tạo được thư mục đầu ra {out_root}: {exc}") from exc
    return out_root


@contextmanager
def run_log(out_root: Path, secrets: Sequence[str | None] = ()) -> Iterator[Path]:
    """Ghi log package loc_counter (INFO) vào <out_root>/run.log trong khối with; che secret."""
    root = _prepare_out_root(out_root)
    path = root / RUN_LOG_NAME
    try:
        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Không ghi được run.log: {exc}") from exc
    handler.setLevel(logging.INFO)
    handler.setFormatter(_MaskingFormatter(_LOG_FORMAT, secrets))
    thread_id = threading.get_ident()
    run_id = token_hex(8)
    handler.addFilter(lambda record: (record.thread == thread_id
                                      or _RUN_LOG_ID.get(None) == run_id))
    package = logging.getLogger(_PACKAGE_LOGGER)
    package.addHandler(handler)
    _acquire_level(package)
    run_token = _RUN_LOG_ID.set(run_id)
    try:
        yield path
    finally:
        package.removeHandler(handler)
        handler.close()
        _release_level(package)
        # thoát ở context khác (generator đóng ở luồng khác) → token không reset được; bỏ qua
        with suppress(ValueError):
            _RUN_LOG_ID.reset(run_token)


def _acquire_level(package: logging.Logger) -> None:
    """Phiên đầu tiên lưu level và đặt INFO nếu cần; phiên sau chỉ tăng bộ đếm (A18)."""
    global _level_sessions, _saved_level
    with _LEVEL_LOCK:
        if _level_sessions == 0:
            _saved_level = package.level
            if package.getEffectiveLevel() > logging.INFO:
                package.setLevel(logging.INFO)
        _level_sessions += 1


def _release_level(package: logging.Logger) -> None:
    """Phiên cuối cùng ra khôi phục level đã lưu (A18)."""
    global _level_sessions
    with _LEVEL_LOCK:
        _level_sessions -= 1
        if _level_sessions == 0:
            package.setLevel(_saved_level)


# ---------- thư mục đích, độ dài đường dẫn, thay thế ----------
def _is_tool_dir(path: Path) -> bool:
    """Có manifest.json là dict đủ key tool_version, c_end, exports (A8)."""
    manifest = path / MANIFEST_NAME
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and all(k in data for k in _MANIFEST_KEYS)


def _check_target(final: Path) -> None:
    """Đích chưa có, hoặc là thư mục kết quả của tool (D40-N13)."""
    if not os.path.lexists(final):
        return
    if not final.is_dir():
        raise _error(f"Đã có file trùng tên thư mục kết quả: {final}")
    if not _is_tool_dir(final):
        raise _error(f"Thư mục {final} đã tồn tại nhưng không phải kết quả của LOC Counter "
                     "(thiếu hoặc hỏng manifest.json); hãy xóa hoặc chọn thư mục đầu ra khác.")


def _long_paths_enabled() -> bool:
    """LongPathsEnabled = 1 trong registry; đọc lỗi → coi như chưa bật."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _LONG_PATHS_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
    except (ImportError, OSError):
        return False
    return value == 1


def _path_limit_applies() -> bool:
    """Windows chưa bật long path → giới hạn WINDOWS_MAX_PATH."""
    return os.name == "nt" and not _long_paths_enabled()


def _check_path_lengths(out_root: Path, final: Path, names: Sequence[str]) -> None:
    """Đường dẫn dự kiến (tạm, đích, cũ; kèm .tmp) không vượt 259 ký tự (A9)."""
    if not _path_limit_applies() or not names:
        return
    dirs = (out_root / f"{TMP_PREFIX}{_NAME_SAMPLE}", final,
            out_root / f"{OLD_PREFIX}{_NAME_SAMPLE}")
    longest = max((str(d / f"{n}.tmp") for d in dirs for n in names), key=len)
    if len(longest) > WINDOWS_MAX_PATH:
        raise _error(f"Đường dẫn kết quả quá dài ({len(longest)} ký tự, Windows giới hạn "
                     f"{WINDOWS_MAX_PATH}): {longest}. Hãy chọn thư mục đầu ra ngắn hơn hoặc "
                     "gộp account bằng identities.yaml.")


def _replace(src: Path, dst: Path) -> None:
    """os.replace; Windows báo PermissionError (WinError 5) thoáng qua khi antivirus/indexer
    đang giữ file trong thư mục → thử lại vài lần với thời gian chờ tăng dần."""
    delay = 0.05
    for _ in range(_REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt":
                raise
            sleep(delay)
            delay = min(delay * 2, 1.0)
    os.replace(src, dst)


def _commit_dir(tmp: Path, final: Path) -> None:
    """Đưa thư mục tạm thành thư mục kết quả; thư mục cũ đổi tên rồi xóa (A7)."""
    if not os.path.lexists(final):
        try:
            _replace(tmp, final)
        except OSError as exc:
            raise _error(f"Không đổi tên thư mục tạm thành {final}: {exc}") from exc
        return
    _check_target(final)
    old = final.parent / f"{OLD_PREFIX}{os.getpid()}-{token_hex(4)}"
    try:
        _replace(final, old)
    except OSError as exc:
        raise _error(f"Không thay thế được thư mục kết quả cũ {final} "
                     f"(có file đang mở?): {exc}") from exc
    try:
        _replace(tmp, final)
    except BaseException as exc:  # kể cả KeyboardInterrupt: đưa thư mục cũ về chỗ (A19)
        lost = ""
        try:
            os.replace(old, final)
        except OSError as restore_exc:
            logger.error("Không khôi phục được thư mục kết quả cũ; dữ liệu cũ nằm ở %s: %s",
                         old, restore_exc)
            lost = f". Không khôi phục được; dữ liệu cũ nằm ở {old}"
        if isinstance(exc, OSError):
            raise _error(f"Không thay thế được thư mục kết quả cũ {final}: {exc}{lost}") from exc
        raise
    try:
        shutil.rmtree(old)
    except OSError as exc:
        logger.warning("Không xóa được thư mục cũ %s: %s", old, exc)


# ---------- cảnh báo ----------
def _merge_warnings(items: Iterable[tuple[str, LocWarning]]) -> tuple[ReportWarning, ...]:
    """Khử trùng theo (kind, path, message), giữ lần đầu, gộp phạm vi theo thứ tự (A12)."""
    merged: dict[tuple[WarningKind, str, str], list[str]] = {}
    for scope, w in items:
        scopes = merged.setdefault((w.kind, w.path, w.message), [])
        if scope not in scopes:
            scopes.append(scope)
    return tuple(ReportWarning(kind, path, message, tuple(scopes))
                 for (kind, path, message), scopes in merged.items())


def _scoped(scope: str, warnings: Iterable[LocWarning]) -> list[tuple[str, LocWarning]]:
    """Gắn nhãn phạm vi cho từng cảnh báo."""
    return [(scope, w) for w in warnings]


# ---------- phân tích ----------
def run_analysis(repo: GitRepo, request: AnalysisRequest, resolver: AccountResolver,
                 progress: ProgressCallback | None = None, *,
                 context: PeriodContext | None = None,
                 now: Callable[[], datetime] | None = None) -> AnalysisResult:
    """Chạy toàn bộ phân tích, ghi thư mục kết quả; trả dữ liệu cho CLI / UI."""
    cfg = request.config
    filters = cfg.filters
    period = request.period
    tz = period.timezone
    order = list(Step)
    if request.attribution_mode not in ("line", "last_commit"):
        raise ValueError(f"attribution_mode không hợp lệ: {request.attribution_mode!r}")

    def step(s: Step) -> None:
        if progress is not None:
            progress(s, order.index(s) + 1, len(order))

    # Chuẩn bị (thuộc bước 1 về tiến độ)
    step(Step.EXPORT_START)
    out_root = _prepare_out_root(request.out_root)
    if context is not None and (context.branch != request.branch or context.period != period):
        raise ValueError("context không khớp nhánh / kỳ của request")
    ctx = context or prepare_period(repo, request.branch, period, resolver)
    snaps, commits, summaries = ctx.snapshots, ctx.commits, ctx.users.users
    selected = None if request.users is None else match_users(request.users, summaries)
    jobs = plan_end_exports(selected, summaries, request.exclude_bots, request.separate_users)
    main = jobs[0]
    counted = (main.accounts if main.accounts is not None
               else tuple(sorted(u.account for u in summaries)))
    final = out_root / result_dir_name(repo.source, snaps.branch, period, main.tag)
    _check_target(final)
    start_name = start_zip_name(period, snaps.c_start)
    end_names = [end_zip_name(period, j.tag) for j in jobs]
    _check_path_lengths(out_root, final, [start_name, *end_names, *_REPORT_NAMES])

    tmp = out_root / f"{TMP_PREFIX}{os.getpid()}-{token_hex(4)}"
    try:
        tmp.mkdir()
    except OSError as exc:
        raise _error(f"Không tạo được thư mục tạm trong {out_root}: {exc}") from exc
    try:
        # Bước 1 — Export start
        start_plan = plan_export(repo, snaps.c_start.sha if snaps.c_start else None, filters)
        write_zip(repo, start_plan, tmp / start_name, zip_timestamp(snaps.c_start, tz))
        start_paths = [f.path for f in start_plan.files]
        start_warnings = [*start_plan.warnings, *path_conflict_warnings(start_paths, "start"),
                          *windows_path_warnings(start_paths)]

        # Bước 2 — Gán tác giả
        step(Step.ATTRIBUTION)
        classifier = LineClassifier(filters.count_docstrings)
        memo_key = (filters, request.attribution_mode)
        memo = ctx.attribution_memo.get(memo_key)
        if memo is not None and memo[0]() is resolver:
            attr = memo[1]
            logger.info("Dùng lại kết quả gán tác giả đã tính cho kỳ này")
        else:
            attr = attribute_period(repo, snaps, commits, resolver, filters, classifier,
                                    mode=request.attribution_mode)
            ctx.attribution_memo.clear()
            ctx.attribution_memo[memo_key] = (weakref.ref(resolver), attr)

        # Bước 3 — Export end
        step(Step.EXPORT_END)
        end_plan = (plan_export(repo, snaps.c_end.sha, filters)
                    if any(j.accounts is None for j in jobs) else None)
        exports: list[UserExport] = []
        end_warnings: list[list[LocWarning]] = []
        for job, name in zip(jobs, end_names, strict=True):
            if job.accounts is None and end_plan is not None:
                export = export_from_plan(end_plan, job.tag)
                paths = [f.path for f in export.files]
                found = [*end_plan.warnings, *path_conflict_warnings(paths, job.tag),
                         *windows_path_warnings(paths)]
            else:
                export = build_user_export(repo, attr, start_plan, set(job.accounts or ()),
                                           filters, job.tag)
                found = [*export.warnings, *windows_path_warnings(f.path for f in export.files)]
            write_user_export(repo, export, tmp / name, snaps.c_end, tz)
            exports.append(export)
            end_warnings.append(found)

        # Bước 4 — Đếm LOC
        step(Step.COUNT)
        start_count = count_export(export_from_plan(start_plan, "start"), repo.read_blobs,
                                   filters, classifier)
        start_warnings += start_count.warnings
        counts: list[CountResult] = []
        for export, found in zip(exports, end_warnings, strict=True):
            result = count_export(export, repo.read_blobs, filters, classifier)
            found += result.warnings
            counts.append(result)
        main_export, main_count = exports[0], counts[0]
        loc_start, loc_end = start_count.total_code, main_count.total_code
        languages = compare_languages(start_count, main_count)
        files = compare_files(start_count, main_count,
                              rename_map(attr, [f.path for f in main_export.files]))
        user_rows = user_metrics(attr, summaries, counted)
        weeks = weekly_metrics(attr, commits, counted, tz)
        check = cross_check(loc_start, loc_end, [r.net_code for r in user_rows])
        net_by_account = {r.account: r.net_code for r in user_rows}
        separate_checks = [
            cross_check(loc_start, c.total_code, [net_by_account[a] for a in j.accounts or ()])
            for j, c in zip(jobs[1:], counts[1:], strict=True)]
        cross_warnings = [w for w in (cross_check_warning(check, main.tag),
                                      *(cross_check_warning(c, j.tag)
                                        for j, c in zip(jobs[1:], separate_checks, strict=True)))
                          if w is not None]
        github_warnings = getattr(resolver.github, "warnings", ())
        identity_warnings = [LocWarning(WarningKind.IDENTITY, "", msg) for msg in github_warnings]
        logger.info("%s: %d file, LOC %d", start_name, len(start_plan.files), loc_start)
        for name, export, result in zip(end_names, exports, counts, strict=True):
            logger.info("%s: %d file, LOC %d", name, len(export.files), result.total_code)
        for job, c in zip(jobs, [check, *separate_checks], strict=True):
            logger.info("Kiểm tra chéo %s: loc_start %d + Σ net %+d = %d, loc_end %d, "
                        "lệch %.3f%%", job.tag, c.loc_start, c.sum_net_code, c.expected_loc_end,
                        c.loc_end, c.diff_percent)

        # Bước 5 — Tạo báo cáo
        step(Step.REPORT)
        warnings = _merge_warnings([
            *_scoped(SCOPE_START, start_warnings),
            *_scoped(SCOPE_ATTRIBUTION, attr.warnings),
            *(item for job, found in zip(jobs, end_warnings, strict=True)
              for item in _scoped(end_scope(job.tag), found)),
            *_scoped(SCOPE_CROSS_CHECK, cross_warnings),
            *_scoped(SCOPE_IDENTITY, identity_warnings),
        ])
        summaries_out = [
            ExportSummary("start", start_name, None, None, len(start_plan.files), loc_start),
            ExportSummary("end", end_names[0], main.tag, main.accounts, len(main_export.files),
                          loc_end, check),
        ]
        summaries_out += [
            ExportSummary("separate", name, job.tag, job.accounts, len(export.files),
                          result.total_code, sep_check)
            for job, name, export, result, sep_check in zip(
                jobs[1:], end_names[1:], exports[1:], counts[1:], separate_checks, strict=True)]
        data = ReportData(
            repo=repo.source, branch=snaps.branch, period=period, c_start=snaps.c_start,
            c_end=snaps.c_end, users=counted, all_users=selected is None,
            config=dataclasses.replace(cfg, timezone=tz),
            options=ReportOptions(selected, request.exclude_bots, request.separate_users,
                                  request.attribution_mode),
            loc_start=loc_start, loc_end=loc_end, languages=tuple(languages),
            user_rows=tuple(user_rows), files=tuple(files), weeks=tuple(weeks),
            cross_check=check, warnings=warnings, exports=tuple(summaries_out))
        generated_at = (now or (lambda: datetime.now(ZoneInfo(tz)).replace(microsecond=0)))()
        report_files = write_reports(tmp, data, generated_at)
        _commit_dir(tmp, final)
        logger.info("Kết quả: %s", final)
    except BaseException as exc:
        logger.exception("Phân tích thất bại: %s", exc)
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    return AnalysisResult(final, data, snaps, tuple(summaries), final / start_name,
                          tuple(final / n for n in end_names),
                          tuple(final / p.name for p in report_files), generated_at)
