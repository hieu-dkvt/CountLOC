"""Giao diện Streamlit của LOC Counter (§10): `uv run streamlit run src/loc_counter/app.py`."""

from __future__ import annotations

import functools
import hashlib
import importlib
import logging
import os
import threading
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import pandas as pd
import streamlit as st

from loc_counter import git_repo, identity, pipeline
from loc_counter.config import (
    DEFAULT_TIMEZONE,
    AppConfig,
    LocCounterError,
    config_from_dict,
    load_config,
)
from loc_counter.counter import CrossCheck, total_metrics
from loc_counter.git_repo import CommitInfo, GitRepo, cache_dir_for, normalize_source
from loc_counter.identity import (
    AccountResolver,
    IdentityError,
    IdentityMap,
    IdentityRule,
    UserSummary,
    load_identities,
    save_identities,
)
from loc_counter.pipeline import (
    STEP_LABELS,
    AnalysisRequest,
    AnalysisResult,
    PeriodContext,
    PipelineError,
    Step,
)
from loc_counter.report import (
    FILE_CSV_NAME,
    LANGUAGE_CSV_NAME,
    MANIFEST_NAME,
    USER_CSV_NAME,
    WARNINGS_CSV_NAME,
    XLSX_NAME,
    ReportData,
)
from loc_counter.snapshot import Period, make_period

logger = logging.getLogger("loc_counter.app")  # script chạy dưới tên __main__

SOURCE_QUOTES = "\"'"
USER_MODES = ("Tất cả user", "Chọn user")
ATTRIBUTION_MODES = ("Theo từng dòng (blame)", "Theo commit cuối cùng của file")
DEFAULT_OUT_DIR = "output"
DEFAULT_IDENTITIES = "identities.yaml"
FORM_KEYS = ("exclude_dirs", "exclude_globs", "exclude_languages", "exclude_binary",
             "max_file_size_kb", "include_tests", "count_docstrings", "export_mode")
EXPORT_MODES = ("source_only", "full")
MIN_DATE = date(1970, 1, 1)
MAX_DATE = date(2100, 12, 31)
MemoEntry = tuple[PeriodContext | None, AccountResolver | None, str | None]
_UNEXPECTED = "Lỗi không mong đợi khi phân tích; xem run.log hoặc log của ứng dụng."


# ---------- hàm thuần (không gọi st.*) ----------
def clean_source(text: str) -> str:
    """Bỏ khoảng trắng và dấu nháy bao quanh (đường dẫn dán từ "Copy as path")."""
    return text.strip().strip(SOURCE_QUOTES).strip()


def default_dates(now: datetime) -> tuple[date, date]:
    """(ngày 1 của tháng, hôm nay) theo ngày của `now` (aware, múi giờ đang chọn)."""
    today = now.date()
    return today.replace(day=1), today


def timezone_options() -> list[str]:
    """Mọi múi giờ IANA, sắp tăng dần."""
    return sorted(available_timezones())


def timezone_label(name: str, at: datetime) -> str:
    """'Asia/Bangkok (UTC+07:00)' — độ lệch tại thời điểm `at`."""
    offset = at.astimezone(ZoneInfo(name)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    sign = "+" if minutes >= 0 else "-"
    hours, mins = divmod(abs(minutes), 60)
    return f"{name} (UTC{sign}{hours:02d}:{mins:02d})"


def canonical_timezone(name: str) -> str | None:
    """Tên trong timezone_options() khớp chính xác, hoặc khớp casefold duy nhất; không có → None."""
    options = timezone_options()
    if name in options:
        return name
    folded = [o for o in options if o.casefold() == name.casefold()]
    return folded[0] if len(folded) == 1 else None


def snapshot_text(commit: CommitInfo | None, timezone: str) -> str:
    """'a1b2c3d (2025-12-15 10:00)  "admin: app.py"' | '(không có commit trước start)'."""
    if commit is None:
        return "(không có commit trước start)"
    when = commit.committer_date.astimezone(ZoneInfo(timezone))
    return f'{commit.short_sha} ({when:%Y-%m-%d %H:%M})  "{commit.subject}"'


def user_label(user: UserSummary) -> str:
    """'alice (2 commit)' [+ ' · bot'] [+ ' · <m> merge']."""
    label = f"{user.account} ({user.commits:,} commit)"
    if user.is_bot:
        label += " · bot"
    if user.merge_commits:
        label += f" · {user.merge_commits:,} merge"
    return label


def filter_users(users: Sequence[UserSummary], query: str,
                 exclude_bots: bool) -> list[UserSummary]:
    """Giữ thứ tự; bỏ bot nếu exclude_bots; query casefold khớp account, tên hoặc email."""
    q = query.strip().casefold()

    def matches(u: UserSummary) -> bool:
        if not q or q in u.account.casefold():
            return True
        return any(q in i.name.casefold() or q in i.email.casefold() for i in u.identities)

    return [u for u in users if not (exclude_bots and u.is_bot) and matches(u)]


def reconcile_selection(selected: Set[str], users: Sequence[UserSummary],
                        exclude_bots: bool) -> tuple[set[str], list[str]]:
    """(lựa chọn còn hợp lệ, account bị bỏ — sắp tăng dần)."""
    valid = {u.account for u in users if not (exclude_bots and u.is_bot)}
    return set(selected) & valid, sorted(set(selected) - valid)


def parse_lines(text: str) -> list[str]:
    """Mỗi dòng một mục; bỏ khoảng trắng hai đầu, bỏ dòng rỗng, bỏ trùng giữ thứ tự."""
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def form_config(values: Mapping[str, Any], timezone: str) -> AppConfig:
    """8 giá trị nâng cao + timezone → config_from_dict (cùng validate với config.yaml)."""
    data: dict[str, Any] = {
        "exclude_dirs": parse_lines(values["exclude_dirs"]),
        "exclude_globs": parse_lines(values["exclude_globs"]),
        "exclude_languages": parse_lines(values["exclude_languages"]),
        "exclude_binary": bool(values["exclude_binary"]),
        "max_file_size_kb": int(values["max_file_size_kb"]),
        "include_tests": bool(values["include_tests"]),
        "count_docstrings": bool(values["count_docstrings"]),
        "export_mode": values["export_mode"],
        "timezone": timezone,
    }
    return config_from_dict(data)


def config_form_values(config: AppConfig) -> dict[str, Any]:
    """Ngược của form_config: giá trị điền vào widget (danh sách → chuỗi nhiều dòng)."""
    f = config.filters
    return {
        "exclude_dirs": "\n".join(f.exclude_dirs),
        "exclude_globs": "\n".join(f.exclude_globs),
        "exclude_languages": "\n".join(f.exclude_languages),
        "exclude_binary": f.exclude_binary,
        "max_file_size_kb": f.max_file_size_kb,
        "include_tests": f.include_tests,
        "count_docstrings": f.count_docstrings,
        "export_mode": f.export_mode,
    }


def resolve_out_root(text: str) -> Path:
    """Path(text).expanduser().resolve(); rỗng → PipelineError."""
    stripped = text.strip()
    if not stripped:
        raise PipelineError("Chưa nhập thư mục đầu ra.")
    return Path(stripped).expanduser().resolve()


def analyze_blockers(*, repo_ready: bool, branch: str | None, period_error: str | None,
                     context_error: str | None, identities_error: str | None,
                     config_error: str | None, out_dir: str, user_mode: str,
                     selected_count: int) -> list[str]:
    """Lý do (tiếng Việt, theo thứ tự cố định) khiến chưa chạy được; [] = chạy được."""
    reasons: list[str] = []
    if not repo_ready:
        reasons.append("Chưa tải repo.")
    if not branch:
        reasons.append("Chưa chọn nhánh.")
    reasons += [e for e in (period_error, identities_error, context_error, config_error) if e]
    if not out_dir.strip():
        reasons.append("Chưa nhập thư mục đầu ra.")
    if user_mode == USER_MODES[1] and selected_count == 0:
        reasons.append("Chưa chọn user nào.")
    return reasons


def build_request(*, branch: str, period: Period, config: AppConfig, out_root: Path,
                  user_mode: str, selected: Set[str], exclude_bots: bool,
                  separate_users: bool,
                  attribution_mode: str = ATTRIBUTION_MODES[0]) -> AnalysisRequest:
    """users = None khi 'Tất cả user', ngược lại tuple(sorted(selected))."""
    users = None if user_mode == USER_MODES[0] else tuple(sorted(selected))
    mode = "last_commit" if attribution_mode == ATTRIBUTION_MODES[1] else "line"
    return AnalysisRequest(branch=branch, period=period, config=config, out_root=out_root,
                           users=users, exclude_bots=exclude_bots, separate_users=separate_users,
                           attribution_mode=mode)


def progress_text(step: Step, index: int, total: int) -> str:
    """'Bước 3/5: Export end…' (nhãn STEP_LABELS)."""
    return f"Bước {index}/{total}: {STEP_LABELS[step]}…"


class LockRegistry:
    """Khóa theo tên dùng chung tiến trình (tạo một lần, có khóa nội bộ)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def get(self, name: str) -> threading.Lock:
        """Khóa của `name` (cùng tên → cùng đối tượng)."""
        with self._guard:
            return self._locks.setdefault(name, threading.Lock())


LOCKS = LockRegistry()  # singleton tiến trình — script lấy qua module gói (A12)


# ---------- hàm thuần của màn hình kết quả (spec screen-result) ----------
NOTE_USER_EXPORT = ("Bản export end theo user dùng để kiểm tra và đếm LOC, "
                    "có thể không build/chạy được.")
STALE_NOTE = "Kết quả ứng với tham số của lần phân tích trước; bấm PHÂN TÍCH để cập nhật."
SEPARATE_SELECT_MIN = 6
MIME = {".zip": "application/zip",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv", ".json": "application/json"}
_CSV_NAMES = (USER_CSV_NAME, LANGUAGE_CSV_NAME, FILE_CSV_NAME)


def signed(value: int) -> str:
    """Số có dấu + hàng nghìn: 0 → '0', 1234 → '+1,234', -5 → '-5'."""
    return f"{value:+,}" if value else "0"


def header_text(data: ReportData) -> str:
    """'Repo: … • Nhánh: … • Kỳ: YYYY-MM-DD HH:MM → … (<tz>, UTC±hh:mm)'."""
    period = data.period
    offset = period.start.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    sign = "+" if minutes >= 0 else "-"
    hours, mins = divmod(abs(minutes), 60)
    return (f"Repo: {data.repo} • Nhánh: {data.branch} • Kỳ: {period.start:%Y-%m-%d %H:%M} → "
            f"{period.end:%Y-%m-%d %H:%M} ({period.timezone}, UTC{sign}{hours:02d}:{mins:02d})")


def users_text(data: ReportData) -> str:
    """'User: …' như CLI (cli-analyze 4.1)."""
    opts = data.options
    if data.all_users:
        who = "Tất cả user" + (" (loại trừ bot)" if opts.exclude_bots else "")
    else:
        who = ", ".join(opts.selected_users or ())
    if opts.separate_users:
        who += " • Xuất riêng từng user"
    return f"User: {who}"


def cross_check_text(check: CrossCheck) -> str:
    """Dòng kiểm tra chéo, cùng định dạng với CLI."""
    verdict = "đạt" if check.ok else "VƯỢT NGƯỠNG (xem warnings.csv)"
    return (f"Kiểm tra chéo: {check.loc_start:,} + ({signed(check.sum_net_code)}) = "
            f"{check.expected_loc_end:,}; LOC end {check.loc_end:,}; lệch "
            f"{check.diff_percent:.3f} % (ngưỡng {check.threshold_percent:g} %) → {verdict}")


_LANGUAGE_COLUMNS = ["Ngôn ngữ", "LOC start", "LOC end", "Chênh lệch"]
_USER_COLUMNS = ["User", "Bot", "Commit", "Thêm", "Xóa", "Ròng", "File thay đổi"]
_WEEK_COLUMNS = ["Tuần", "Bắt đầu tuần", "User", "Code ròng"]
_FILE_COLUMNS = ["Đường dẫn", "Đổi tên từ", "Ngôn ngữ", "LOC start", "LOC end", "Chênh lệch"]
_WARNING_COLUMNS = ["Loại", "Đường dẫn", "Nội dung", "Phạm vi"]


def language_frame(data: ReportData) -> pd.DataFrame:
    """Theo ngôn ngữ; sắp (-loc_end, -loc_start, ngôn ngữ)."""
    langs = sorted(data.languages, key=lambda r: (-r.loc_end, -r.loc_start, r.language))
    return pd.DataFrame([[r.language, r.loc_start, r.loc_end, r.delta] for r in langs],
                        columns=_LANGUAGE_COLUMNS)


def _user_row(account: str, metrics: Any) -> list[Any]:
    return [account, "bot" if metrics.is_bot else "", metrics.commits, metrics.added_code,
            metrics.deleted_code, metrics.net_code, metrics.files_changed]


def user_frame(data: ReportData) -> pd.DataFrame:
    """Theo user; sắp (-commit, account)."""
    users = sorted(data.user_rows, key=lambda r: (-r.commits, r.account))
    return pd.DataFrame([_user_row(r.account, r) for r in users], columns=_USER_COLUMNS)


def total_frame(data: ReportData) -> pd.DataFrame | None:
    """Một dòng 'Tổng' khi có ≥ 1 user; ngược lại None."""
    if not data.user_rows:
        return None
    return pd.DataFrame([_user_row("Tổng", total_metrics(data.user_rows))],
                        columns=_USER_COLUMNS)


def weekly_frame(data: ReportData) -> pd.DataFrame:
    """Code ròng theo tuần ISO và user (giữ thứ tự của report)."""
    return pd.DataFrame([[w.week, w.week_start, w.account, w.net_code] for w in data.weeks],
                        columns=_WEEK_COLUMNS)


def file_frame(data: ReportData) -> pd.DataFrame:
    """Chi tiết theo file; sắp theo đường dẫn."""
    files = sorted(data.files, key=lambda r: r.path)
    return pd.DataFrame([[f.path, f.renamed_from or "", f.language, f.loc_start, f.loc_end,
                          f.delta] for f in files], columns=_FILE_COLUMNS)


def filter_files(frame: pd.DataFrame, query: str, languages: Sequence[str],
                 changed_only: bool) -> pd.DataFrame:
    """Lọc theo chuỗi (casefold, đường dẫn / đổi tên từ), ngôn ngữ, chỉ file thay đổi."""
    q = query.strip().casefold()
    keep = pd.Series(True, index=frame.index)
    if q:
        keep &= (frame["Đường dẫn"].str.casefold().str.contains(q, regex=False)
                 | frame["Đổi tên từ"].str.casefold().str.contains(q, regex=False))
    if languages:
        keep &= frame["Ngôn ngữ"].isin(list(languages))
    if changed_only:
        keep &= (frame["Chênh lệch"] != 0) | (frame["Đổi tên từ"] != "")
    return frame[keep].reset_index(drop=True)


def warnings_frame(data: ReportData) -> pd.DataFrame:
    """Cảnh báo như warnings.csv; sắp (path, kind)."""
    rows = sorted(data.warnings, key=lambda w: (w.path, w.kind.value))
    return pd.DataFrame([[str(w.kind), w.path, w.message, "; ".join(w.scopes)] for w in rows],
                        columns=_WARNING_COLUMNS)


def has_user_export(data: ReportData) -> bool:
    """Có bản export end dựng theo user (accounts khác None)."""
    return any(e.accounts is not None for e in data.exports if e.role != "start")


@dataclass(frozen=True)
class DownloadItem:
    """Một file có thể tải."""

    label: str
    path: Path
    mime: str
    key: str
    group: str  # zip | report | csv | warnings | manifest


def download_items(result: AnalysisResult) -> list[DownloadItem]:
    """start zip, các end zip, xlsx, 3 CSV, warnings.csv, manifest — mọi file §12."""
    def item(path: Path, group: str) -> DownloadItem:
        return DownloadItem(f"Tải {path.name}", path,
                            MIME.get(path.suffix, "application/octet-stream"),
                            f"dl_{path.name}", group)

    items = [item(result.start_zip, "zip"), *(item(p, "zip") for p in result.end_zips)]
    groups = {XLSX_NAME: "report", WARNINGS_CSV_NAME: "warnings", MANIFEST_NAME: "manifest"}
    for path in result.report_files:
        items.append(item(path, "csv" if path.name in _CSV_NAMES else groups[path.name]))
    return items


# ---------- hàm thuần của panel gộp account (spec screen-identity) ----------
IDENTITY_COLUMNS = ("Tên", "Email", "Account key")


def identity_rows(users: Sequence[UserSummary]) -> pd.DataFrame:
    """Mỗi Identity (tên, email gốc) một hàng theo thứ tự users; bỏ trùng; Account key = account."""
    seen: set[tuple[str, str]] = set()
    rows: list[list[str]] = []
    for user in users:
        for ident in user.identities:
            key = (ident.name, ident.email)
            if key not in seen:
                seen.add(key)
                rows.append([ident.name, ident.email, user.account])
    return pd.DataFrame(rows, columns=list(IDENTITY_COLUMNS))


def _cell(value: Any) -> str:
    """Giá trị ô dạng chuỗi đã strip; None / NA (pandas StringDtype) → '' (A5)."""
    return "" if value is None or pd.isna(value) else str(value).strip()


def changed_rows(original: pd.DataFrame, edited: pd.DataFrame) -> list[tuple[str, str, str]]:
    """[(tên, email, account mới đã strip)] cho hàng có Account key khác bản gốc (so sau strip)."""
    changes: list[tuple[str, str, str]] = []
    for (_, before), (_, after) in zip(original.iterrows(), edited.iterrows(), strict=True):
        new = _cell(after["Account key"])
        if new != _cell(before["Account key"]):
            changes.append((_cell(before["Tên"]), _cell(before["Email"]), new))
    return changes


def apply_identity_edits(base: IdentityMap,
                         changes: Sequence[tuple[str, str, str]]) -> IdentityMap:
    """Upsert quy tắc theo email (hoặc tên khi email rỗng); account rỗng = bỏ quy tắc (5.2)."""
    assigned: dict[tuple[str, str], str] = {}
    for name, email, account in changes:  # kiểm xung đột trước, không phụ thuộc thứ tự (A8)
        email, name = email.strip(), name.strip()
        keys = [("Email", email.lower())] if email else []
        if name and (not email or not account):  # xóa trống chiếm cả khóa tên (A7)
            keys.append(("Tên", name.lower()))
        for key in keys:
            previous = assigned.setdefault(key, account)
            if previous != account:
                raise IdentityError(f"{key[0]} {key[1]} được gán cho nhiều account: "
                                    f"{previous or '(trống)'}, {account or '(trống)'}")
    rules = list(base.rules)
    for name, email, account in changes:
        email, name = email.strip(), name.strip()
        drop_name = not email or not account  # xóa trống bỏ cả quy tắc theo tên (A7)
        kept: list[IdentityRule] = []
        for rule in rules:
            hit_email = bool(email and rule.email and rule.email.lower() == email.lower())
            hit_name = bool(drop_name and name and rule.name
                            and rule.name.lower() == name.lower())
            if not (hit_email or hit_name):
                kept.append(rule)
                continue
            rest_email = None if hit_email else rule.email
            rest_name = None if hit_name else rule.name
            if rest_email or rest_name:
                kept.append(IdentityRule(rule.account, rest_email, rest_name))
        rules = kept
        if account:
            rules.append(IdentityRule(account, email, None) if email
                         else IdentityRule(account, None, name))
    return IdentityMap(tuple(dict.fromkeys(rules)))


# ---------- giao diện ----------
def _registry() -> LockRegistry:
    """LOCKS của module gói loc_counter.app (bền qua rerun, chung mọi phiên)."""
    return importlib.import_module("loc_counter.app").LOCKS


def _init_state() -> None:
    """Đặt mặc định cho các key chưa có (một lần mỗi phiên)."""
    ss = st.session_state
    start, end = default_dates(datetime.now(ZoneInfo(DEFAULT_TIMEZONE)))
    defaults: dict[str, Any] = {
        "repo_source": "", "token": "", "start_date": start, "start_time": None,
        "end_date": end, "end_time": None, "tz": DEFAULT_TIMEZONE,
        "identities_path": DEFAULT_IDENTITIES, "user_mode": USER_MODES[0], "user_query": "",
        "exclude_bots": False, "separate_users": False, "config_path": "",
        "attribution_mode": ATTRIBUTION_MODES[0],
        "out_dir": DEFAULT_OUT_DIR, "repo": None, "loaded_with": None, "repo_gen": 0,
        "branches": [], "branch_value": None, "repo_error": None, "period_memo": {},
        "selected": set(), "run_requested": False, "run_error": None, "result": None,
        "result_sig": None, "config_load_error": None,
    }
    defaults.update({f"adv_{k}": v for k, v in config_form_values(AppConfig()).items()})
    for key, value in defaults.items():
        ss.setdefault(key, value)


def _load_repo(source: str, token: str) -> None:
    """Mở repo (clone/fetch) dưới khóa cache; cập nhật trạng thái phiên (5.2)."""
    ss = st.session_state
    try:
        with st.spinner("Đang tải repo…"):
            normalized, _ = normalize_source(source)
            key = "repo:" + str(cache_dir_for(normalized, git_repo.DEFAULT_CACHE_ROOT))
            with _registry().get(key):
                repo = GitRepo.open(source, token or None, cache_root=git_repo.DEFAULT_CACHE_ROOT)
            branches = repo.list_branches()
            default = repo.default_branch()
    except (LocCounterError, OSError) as err:
        ss.repo, ss.branches, ss.repo_error = None, [], str(err)
        return
    ss.repo, ss.loaded_with, ss.branches, ss.repo_error = repo, (source, token), branches, None
    ss.repo_gen += 1
    ss.period_memo = {}
    ss.branch = ss.branch_value = default if default in branches else None


def _render_repository(locked: bool) -> tuple[GitRepo | None, str | None, str]:
    """Khối [1]; trả (repo đã tải hợp lệ, nhánh, token)."""
    ss = st.session_state
    st.subheader("[1] REPOSITORY")
    st.text_input("Repo (URL hoặc đường dẫn local)", key="repo_source", disabled=locked)
    st.text_input("GitHub token (tùy chọn, ẩn)", key="token", type="password",
                  autocomplete="off", disabled=locked)
    source, token = clean_source(ss.repo_source), ss.token
    if st.button("Tải repo", key="load_repo", disabled=locked or not source):
        _load_repo(source, token)
    if ss.repo_error:
        st.error(ss.repo_error)
    repo = ss.repo
    if repo is not None and ss.loaded_with != (source, token):
        st.warning("Nguồn hoặc token đã thay đổi; hãy bấm “Tải repo” lại.")
        return None, None, token
    if repo is None:
        return None, None, token
    if not ss.branches:
        st.error("Repo không có nhánh nào.")
        return repo, None, token
    if "branch" not in ss:  # state widget bị xóa khi lần trước không vẽ (A15)
        ss.branch = ss.get("branch_value")
    st.selectbox("Nhánh", ss.branches, key="branch", placeholder="Chọn nhánh", disabled=locked)
    ss.branch_value = ss.branch
    return repo, ss.branch, token


def _render_period(locked: bool) -> tuple[Period | None, str | None, Any]:
    """Khối [2] (phần ô nhập); trả (period, lỗi, chỗ giữ cho dòng snapshot)."""
    ss = st.session_state
    st.subheader("[2] THỜI ĐIỂM THỐNG KÊ")
    left, right = st.columns(2)
    with left:
        st.date_input("Start", key="start_date", min_value=MIN_DATE, max_value=MAX_DATE,
                      format="YYYY-MM-DD", disabled=locked)
    with right:
        st.date_input("End", key="end_date", min_value=MIN_DATE, max_value=MAX_DATE,
                      format="YYYY-MM-DD", disabled=locked)
    tz_error = None
    if ss.tz not in timezone_options():  # không để selectbox âm thầm chọn mục đầu (A14)
        canonical = canonical_timezone(ss.tz)
        if canonical is None:
            tz_error = f"Múi giờ không có trong danh sách: {ss.tz}"
        else:
            ss.tz = canonical
    if tz_error:
        st.error(tz_error)
    placeholder = st.container()
    if tz_error:
        return None, tz_error, placeholder
    try:  # web UI chỉ chọn ngày: không nhập giờ (A17)
        return make_period(ss.start_date, ss.end_date, None, None,
                           timezone=ss.tz), None, placeholder
    except LocCounterError as err:
        st.error(str(err))
        return None, str(err), placeholder


def _load_identity_map() -> tuple[IdentityMap, str | None]:
    """identities.yaml theo ô đường dẫn: rỗng / vắng → map rỗng; hỏng → lỗi."""
    text = st.session_state.identities_path.strip()
    if not text or not Path(text).exists():
        return IdentityMap(), None
    if not Path(text).is_file():
        return IdentityMap(), f"Đường dẫn identities không phải file: {Path(text).resolve()}"
    try:
        return load_identities(Path(text)), None
    except LocCounterError as err:
        return IdentityMap(), str(err)


def _period_context(repo: GitRepo, branch: str, period: Period, identity_map: IdentityMap,
                    token: str) -> MemoEntry:
    """(PeriodContext, resolver, lỗi) từ memo; khóa đổi → prepare_period (5.3 bước 4)."""
    ss = st.session_state
    key = (ss.repo_gen, branch, period, identity_map, bool(token))
    cached = ss.period_memo.get(key)
    if cached is not None:
        return cached
    try:
        with st.spinner("Đang tính snapshot và danh sách user…"):
            resolver = pipeline.make_resolver(repo.source, identity_map, token or None,
                                              login_cache=identity.DEFAULT_LOGIN_CACHE)
            ctx = pipeline.prepare_period(repo, branch, period, resolver)
        entry: MemoEntry = (ctx, resolver, None)
    except (LocCounterError, OSError) as err:
        entry = (None, None, str(err))
    ss.period_memo = {key: entry}
    return entry


def _toggle(account: str, key: str) -> None:
    """on_change của checkbox user: cập nhật `selected`."""
    selected: set[str] = st.session_state.selected
    if st.session_state[key]:
        selected.add(account)
    else:
        selected.discard(account)


def _render_users(locked: bool, ctx: PeriodContext | None, identity_map: IdentityMap,
                  identities_error: str | None) -> None:
    """Khối [3] (5.4)."""
    ss = st.session_state
    if identities_error:
        st.error(identities_error)
    st.radio("Chế độ chọn user", USER_MODES, key="user_mode", horizontal=True,
             label_visibility="collapsed", disabled=locked)
    users: list[UserSummary] = ctx.users.users if ctx is not None else []
    if ctx is not None:
        ss.selected, dropped = reconcile_selection(ss.selected, users, ss.exclude_bots)
        if dropped:
            st.info("Đã bỏ chọn user không còn trong danh sách: " + ", ".join(dropped))
        if not users:
            st.info("Không có user nào có commit trong kỳ.")
    if ss.user_mode == USER_MODES[0]:
        for u in filter_users(users, "", ss.exclude_bots):
            st.caption(user_label(u))
    else:
        st.text_input("Tìm user", key="user_query", disabled=locked)
        for u in filter_users(users, ss.user_query, ss.exclude_bots):
            key = "pick_" + hashlib.sha1(u.account.encode("utf-8")).hexdigest()[:12]
            ss[key] = u.account in ss.selected
            st.checkbox(user_label(u), key=key, on_change=_toggle, args=(u.account, key),
                        disabled=locked)
        st.caption(f"Đã chọn {len(ss.selected)} user")
    left, right = st.columns(2)
    with left:
        st.checkbox("Loại trừ bot", key="exclude_bots", disabled=locked)
    with right:
        st.checkbox("Xuất riêng từng user", key="separate_users", disabled=locked)
    st.radio("Cách gán tác giả", ATTRIBUTION_MODES, key="attribution_mode", horizontal=True,
             disabled=locked)
    if ctx is not None:
        for warning in ctx.users.warnings:
            st.warning(warning)
    render_identity_panel(locked, ctx, identity_map, identities_error)


def _toggle_identity_panel() -> None:
    """on_click "Quản lý gộp account": mở / đóng panel."""
    st.session_state.identity_panel = not st.session_state.get("identity_panel", False)


def render_identity_panel(locked: bool, ctx: PeriodContext | None, identity_map: IdentityMap,
                          identities_error: str | None) -> None:
    """Panel gộp account (spec screen-identity 5.1)."""
    ss = st.session_state
    st.button("Quản lý gộp account", key="toggle_identities", on_click=_toggle_identity_panel,
              disabled=locked)
    if not ss.get("identity_panel", False):
        return
    with st.container(border=True):
        st.markdown("**Gộp account**")
        message = ss.pop("identity_message", None)
        if message:
            st.success(message)
        if identities_error:
            st.error(identities_error)
            st.caption("Sửa file hoặc đổi đường dẫn rồi thử lại.")
            return
        if ctx is None:
            st.info("Cần tải repo và chọn kỳ hợp lệ để có danh sách tác giả.")
            return
        users = ctx.users.users
        if not users:
            st.info("Không có tác giả nào có commit trong kỳ.")
            return
        st.caption("Sửa cột Account key rồi bấm Lưu; để trống để bỏ quy tắc của dòng đó.")
        original = identity_rows(users)
        sig = tuple(map(tuple, original.values.tolist()))
        if ss.get("identity_rows_sig") != sig:  # hàng đổi → key mới để frontend reset (A6)
            ss.identity_editor_gen = ss.get("identity_editor_gen", 0) + 1
            ss.identity_rows_sig = sig
        edited = st.data_editor(original, key=f"identity_editor_{ss.identity_editor_gen}",
                                hide_index=True, num_rows="fixed",
                                disabled=True if locked else ["Tên", "Email"])
        changes = changed_rows(original, edited)
        path_text = ss.identities_path.strip()
        try:
            preview = set(apply_identity_edits(identity_map, changes).rules)
            kept = sum(1 for r in identity_map.rules if r in preview)
        except LocCounterError:
            kept = len(identity_map.rules)
        st.caption(f"File: {path_text or '(chưa nhập)'} — giữ nguyên {kept} quy tắc khác "
                   "trong file.")
        if st.button(f"Lưu vào {path_text}", key="save_identities", type="primary",
                     disabled=locked or not changes or not path_text):
            _save_identity_edits(Path(path_text), identity_map, changes)


def _save_identity_edits(path: Path, identity_map: IdentityMap,
                         changes: Sequence[tuple[str, str, str]]) -> None:
    """Lưu quy tắc mới (5.3); lỗi → st.error, file giữ nguyên; thành công → rerun."""
    try:
        save_identities(path, apply_identity_edits(identity_map, changes))
    except LocCounterError as err:
        st.error(str(err))
        return
    ss = st.session_state
    ss.identity_message = f"Đã lưu {len(changes)} thay đổi vào {path.resolve()}."
    ss.identity_editor_gen = ss.get("identity_editor_gen", 0) + 1  # bảng mới, không giữ sửa đổi
    st.rerun()


def _load_config_file() -> None:
    """on_click "Nạp": điền 8 ô nâng cao + múi giờ từ file cấu hình (A6)."""
    ss = st.session_state
    text = ss.config_path.strip()
    ss.config_load_error = None
    if not text:
        return
    try:
        cfg = load_config(Path(text))
    except LocCounterError as err:
        ss.config_load_error = str(err)
        return
    tz = canonical_timezone(cfg.timezone)
    if tz is None:
        ss.config_load_error = ("Múi giờ trong file cấu hình không có trong danh sách múi giờ: "
                                f"{cfg.timezone}")
        return
    for key, value in config_form_values(cfg).items():
        ss[f"adv_{key}"] = value
    ss.tz = tz


def _render_advanced(locked: bool) -> tuple[AppConfig | None, str | None]:
    """Tùy chọn nâng cao (5.5); trả (config, lỗi)."""
    ss = st.session_state
    with st.expander("Tùy chọn nâng cao (bộ lọc file, docstring, test, chế độ export)"):
        left, right = st.columns([4, 1], vertical_alignment="bottom")
        with left:
            st.text_input("File cấu hình (tùy chọn)", key="config_path", disabled=locked)
        with right:
            st.button("Nạp", key="load_config", on_click=_load_config_file, disabled=locked)
        if ss.config_load_error:
            st.error(ss.config_load_error)
        st.text_area("Thư mục loại trừ (mỗi dòng một mục)", key="adv_exclude_dirs",
                     disabled=locked)
        st.text_area("Mẫu file loại trừ (mỗi dòng một mục)", key="adv_exclude_globs",
                     disabled=locked)
        st.text_area("Ngôn ngữ loại trừ (tên lexer Pygments, mỗi dòng một mục)",
                     key="adv_exclude_languages", disabled=locked)
        st.number_input("Kích thước tối đa (KB)", key="adv_max_file_size_kb", min_value=0,
                        step=1, disabled=locked)
        st.checkbox("Loại file binary", key="adv_exclude_binary", disabled=locked)
        st.checkbox("Tính file test", key="adv_include_tests", disabled=locked)
        st.checkbox("Tính docstring là code", key="adv_count_docstrings", disabled=locked)
        st.radio("Chế độ export", EXPORT_MODES, key="adv_export_mode", horizontal=True,
                 disabled=locked)
        try:
            return form_config({k: ss[f"adv_{k}"] for k in FORM_KEYS}, ss.tz), None
        except LocCounterError as err:
            st.error(str(err))
            return None, str(err)


def _request_run() -> None:
    """on_click PHÂN TÍCH: lần chạy kế tiếp khóa ô nhập rồi phân tích (5.6)."""
    st.session_state.run_requested = True
    st.session_state.run_error = None


def _run_analysis(repo: GitRepo | None, token: str, ctx: PeriodContext | None,
                  resolver: AccountResolver | None, config: AppConfig,
                  blockers: list[str], sig: tuple[Any, ...]) -> None:
    """Chạy pipeline ở cuối script (5.6 bước 4); lỗi → run_error."""
    ss = st.session_state
    ss.run_requested = False  # trả cờ trước việc nặng: Stop của Streamlit có thể bỏ qua finally
    bar = st.progress(0.0, text="Đang chuẩn bị…")

    def on_progress(step: Step, index: int, total: int) -> None:
        bar.progress((index - 1) / total, text=progress_text(step, index, total))

    try:
        if blockers or repo is None or ctx is None or resolver is None:
            raise PipelineError(blockers[0] if blockers else "Chưa tải repo.")
        out_root = resolve_out_root(ss.out_dir)
        lock = _registry().get("out:" + os.path.normcase(str(out_root)))  # A16
        if not lock.acquire(blocking=False):
            raise PipelineError(f"Thư mục đầu ra {out_root} đang được một phiên phân tích khác "
                                "sử dụng; hãy chờ hoặc chọn thư mục khác.")
        try:
            with pipeline.run_log(out_root, secrets=(token or None,)):
                snaps = ctx.snapshots
                who = ("tất cả" if ss.user_mode == USER_MODES[0]
                       else ", ".join(sorted(ss.selected)))
                logger.info("Phân tích từ giao diện: nguồn %s, nhánh %s, kỳ %s → %s (%s), "
                            "C_START=%s, C_END=%s, user: %s", repo.source, snaps.branch,
                            ctx.period.start.isoformat(), ctx.period.end.isoformat(),
                            ctx.period.timezone, snaps.c_start.sha if snaps.c_start else "rỗng",
                            snaps.c_end.sha, who)
                request = build_request(branch=ctx.branch, period=ctx.period, config=config,
                                        out_root=out_root, user_mode=ss.user_mode,
                                        selected=ss.selected, exclude_bots=ss.exclude_bots,
                                        separate_users=ss.separate_users,
                                        attribution_mode=ss.attribution_mode)
                try:
                    result = pipeline.run_analysis(repo, request, resolver,
                                                   progress=on_progress, context=ctx)
                except Exception as err:  # log trong run_log để traceback vào run.log, đã che token
                    if not isinstance(err, LocCounterError | OSError):
                        logger.exception("Lỗi không mong đợi khi phân tích")
                    raise
            bar.progress(1.0, text="Xong")
            ss.result, ss.result_sig = result, sig
        finally:
            lock.release()
    except (LocCounterError, OSError) as err:
        ss.run_error = str(err)
    except Exception:  # đã log (trong run_log) hoặc lỗi trước run_log — chỉ hiện thông báo chung
        ss.run_error = _UNEXPECTED
    st.rerun()


_INT = st.column_config.NumberColumn(format="localized")
_DELTA = st.column_config.NumberColumn(format="%+d")
_TABLE_CONFIG = {"LOC start": _INT, "LOC end": _INT, "Chênh lệch": _DELTA, "Commit": _INT,
                 "Thêm": _INT, "Xóa": _INT, "Ròng": _DELTA, "File thay đổi": _INT,
                 "Code ròng": _DELTA}


def _table(frame: pd.DataFrame) -> None:
    st.dataframe(frame, hide_index=True, column_config=_TABLE_CONFIG)


def _download(item: DownloadItem, locked: bool, key: str | None = None) -> None:
    """Nút tải đọc file khi bấm; file không còn → disabled + chú thích."""
    exists = item.path.is_file()
    st.download_button(item.label, data=functools.partial(Path.read_bytes, item.path),
                       file_name=item.path.name, mime=item.mime, key=key or item.key,
                       on_click="ignore", disabled=locked or not exists)
    if not exists:
        st.caption(f"Không còn file: {item.path.name}")


def _render_downloads(result: AnalysisResult, locked: bool) -> None:
    """Khối 'Tải file' (5 bước 10)."""
    items = download_items(result)
    zips = [i for i in items if i.group == "zip"]
    main_items = [*zips[:2], *(i for i in items if i.group == "report")]
    separate = zips[2:]
    st.markdown("**Tải file**")
    for column, item in zip(st.columns(len(main_items)), main_items, strict=True):
        with column:
            _download(item, locked)
    if len(separate) >= SEPARATE_SELECT_MIN:
        names = [i.path.name for i in separate]
        choice = st.selectbox("Zip riêng từng user", names, key="dl_separate_pick",
                              disabled=locked)
        _download(separate[names.index(choice or names[0])], locked, key="dl_separate")
    elif separate:
        for column, item in zip(st.columns(len(separate)), separate, strict=True):
            with column:
                _download(item, locked)
    st.markdown("Tải CSV:")
    csv_items = [i for i in items if i.group == "csv"]
    manifest = [i for i in items if i.group == "manifest"]
    for column, item in zip(st.columns(len(csv_items) + len(manifest)), [*csv_items, *manifest],
                            strict=True):
        with column:
            _download(item, locked)


def render_result(result: AnalysisResult, stale: bool, locked: bool) -> None:
    """Màn hình kết quả §10.3 (spec screen-result mục 5)."""
    data = result.data
    with st.container(border=True):
        st.subheader("KẾT QUẢ")
        if stale:
            st.info(STALE_NOTE)
        st.text(header_text(data))
        st.text(users_text(data))
        commits = sum(r.commits for r in data.user_rows)
        for column, (label, value) in zip(st.columns(4), (
                ("LOC start", f"{data.loc_start:,}"), ("LOC end", f"{data.loc_end:,}"),
                ("Chênh lệch", signed(data.loc_delta)), ("Commit", f"{commits:,}")), strict=True):
            column.metric(label, value)
        check = cross_check_text(data.cross_check)
        (st.success if data.cross_check.ok else st.warning)(check)

        st.markdown("**Theo ngôn ngữ**")
        languages = language_frame(data)
        if languages.empty:
            st.caption("Không có file source nào.")
        else:
            _table(languages)
        st.markdown("**Theo user**")
        users = user_frame(data)
        total = total_frame(data)
        if users.empty or total is None:
            st.caption("Không có user nào có commit trong kỳ.")
        else:
            _table(users)
            _table(total)
        st.markdown("**Code ròng theo tuần**")
        weeks = weekly_frame(data)
        if weeks.empty:
            st.caption("Không có commit trong kỳ.")
        else:
            st.bar_chart(weeks, x="Tuần", y="Code ròng", color="User", stack=False)

        count = len(data.warnings)
        if count:
            st.warning(f"{count} cảnh báo (xem chi tiết)", icon="⚠️")
        else:
            st.caption("Không có cảnh báo.")
        items = {i.group: i for i in download_items(result)}
        with st.expander("Cảnh báo"):
            frame = warnings_frame(data)
            if frame.empty:
                st.caption("Không có cảnh báo.")
            else:
                st.dataframe(frame, hide_index=True)
            _download(items["warnings"], locked)
        with st.expander("Chi tiết theo file"):
            files = file_frame(data)
            st.text_input("Lọc theo đường dẫn", key="file_query", disabled=locked)
            st.multiselect("Ngôn ngữ", sorted(set(files["Ngôn ngữ"])), key="file_languages",
                           disabled=locked)
            st.checkbox("Chỉ file có LOC thay đổi hoặc đổi tên", key="file_changed_only",
                        disabled=locked)
            ss = st.session_state
            shown = filter_files(files, ss.get("file_query", ""), ss.get("file_languages", []),
                                 ss.get("file_changed_only", False))
            _table(shown)
            st.caption(f"{len(shown):,} / {len(files):,} file")

        _render_downloads(result, locked)
        if has_user_export(data):
            st.caption(NOTE_USER_EXPORT)
        st.caption(f"Thư mục kết quả: {result.out_dir}")


def main() -> None:
    """Một lần chạy script (§10.1, §10.2)."""
    st.set_page_config(page_title="Đếm LOC", layout="wide")
    _init_state()
    ss = st.session_state
    locked: bool = ss.run_requested
    st.title("ĐẾM LOC SOURCE CODE")

    repo, branch, token = _render_repository(locked)
    period, period_error, snapshot_box = _render_period(locked)
    st.subheader("[3] CHỌN USER")
    st.text_input("File identities", key="identities_path", disabled=locked)
    identity_map, identities_error = _load_identity_map()
    ctx: PeriodContext | None = None
    resolver: AccountResolver | None = None
    context_error: str | None = None
    if repo is not None and branch and period is not None and identities_error is None:
        ctx, resolver, context_error = _period_context(repo, branch, period, identity_map, token)
    with snapshot_box:  # dòng snapshot nằm trong khối [2] (§10.1)
        if ctx is not None:
            tz = ctx.period.timezone
            st.text("→ Snapshot start: " + snapshot_text(ctx.snapshots.c_start, tz))
            st.text("→ Snapshot end:   " + snapshot_text(ctx.snapshots.c_end, tz))
        elif context_error:
            st.error(context_error)
    _render_users(locked, ctx, identity_map, identities_error)
    config, config_error = _render_advanced(locked)

    st.text_input("Thư mục đầu ra", key="out_dir", disabled=locked)
    blockers = analyze_blockers(
        repo_ready=repo is not None, branch=branch, period_error=period_error,
        context_error=context_error, identities_error=identities_error,
        config_error=config_error, out_dir=ss.out_dir, user_mode=ss.user_mode,
        selected_count=len(ss.selected))
    for reason in blockers:
        st.info(reason)
    st.button("PHÂN TÍCH", key="analyze", type="primary", on_click=_request_run,
              disabled=bool(blockers) or locked)
    sig = (ss.repo_gen, branch, period, identity_map, config, ss.out_dir, ss.user_mode,
           tuple(sorted(ss.selected)), ss.exclude_bots, ss.separate_users, ss.attribution_mode)
    if ss.run_error:
        st.error(ss.run_error)
    if ss.result is not None:
        render_result(ss.result, stale=ss.result_sig != sig, locked=locked)
    if locked:
        _run_analysis(repo, token, ctx, resolver, config or AppConfig(), blockers, sig)


if __name__ == "__main__":
    main()
