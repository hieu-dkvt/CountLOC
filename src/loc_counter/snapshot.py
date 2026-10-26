"""Thời điểm, snapshot C_START / C_END, lọc file và ghi zip export (§3.1–§3.3, §9, §12)."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loc_counter.classifier import detect_language
from loc_counter.config import DEFAULT_TIMEZONE, FilterConfig, LocCounterError
from loc_counter.counter import LocWarning, WarningKind
from loc_counter.filters import BINARY_SNIFF_BYTES, check_path, is_binary
from loc_counter.git_repo import CommitInfo, GitRepo

logger = logging.getLogger(__name__)

_ZIP_EPOCH = datetime(1980, 1, 1)
_TIME_FMT = "%Y-%m-%d %H:%M:%S"


class SnapshotError(LocCounterError):
    """Lỗi nghiệp vụ về thời điểm / snapshot; thông báo tiếng Việt."""


@dataclass(frozen=True)
class Period:
    """Khoảng thời gian thống kê (hai mốc aware) và ngày người dùng nhập."""

    start: datetime
    end: datetime
    timezone: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class Snapshots:
    """C_START (có thể rỗng) và C_END trên nhánh."""

    branch: str
    c_start: CommitInfo | None
    c_end: CommitInfo


@dataclass(frozen=True)
class ExportFile:
    """Một file được đưa vào export."""

    path: str
    blob_sha: str
    mode: str
    size: int
    language: str | None


@dataclass
class ExportPlan:
    """Danh sách file export của một commit và cảnh báo."""

    commit_sha: str | None
    files: list[ExportFile] = field(default_factory=list)
    warnings: list[LocWarning] = field(default_factory=list)


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SnapshotError(f"Múi giờ không hợp lệ: {timezone}") from exc


def make_period(start_date: date, end_date: date,
                start_time: time | None = None, end_time: time | None = None,
                timezone: str = DEFAULT_TIMEZONE) -> Period:
    """Quy đổi ngày + giờ (tùy chọn) + múi giờ thành hai mốc (§3.1, D10)."""
    tz = _zone(timezone)
    start_clock = time(start_time.hour, start_time.minute, 0) if start_time else time(0, 0, 0)
    end_clock = time(end_time.hour, end_time.minute, 59) if end_time else time(23, 59, 59)
    start = datetime.combine(start_date, start_clock, tzinfo=tz)
    end = datetime.combine(end_date, end_clock, tzinfo=tz)
    if start >= end:
        raise SnapshotError(f"Thời điểm start ({start:{_TIME_FMT}}) "
                            f"phải trước end ({end:{_TIME_FMT}}).")
    return Period(start, end, timezone, start_date, end_date)


def find_snapshots(repo: GitRepo, branch: str, period: Period) -> Snapshots:
    """Tìm C_START, C_END theo first-parent (§3.1)."""
    repo.resolve_branch(branch)
    end_sha = repo.rev_before(branch, period.end)
    if end_sha is None:
        logger.info("Nhánh %s không có commit trước %s", branch, period.end.isoformat())
        raise SnapshotError(f"Không có dữ liệu trong khoảng thời gian: nhánh {branch} không có "
                            f"commit nào trước {period.end:{_TIME_FMT}}.")
    start_sha = repo.rev_before(branch, period.start)
    c_end = repo.commit_info(end_sha)
    c_start = repo.commit_info(start_sha) if start_sha else None
    start_text = (f"{c_start.short_sha} ({c_start.committer_date.isoformat()})"
                  if c_start else "rỗng")
    logger.info("C_START=%s, C_END=%s (%s)", start_text, c_end.short_sha,
                c_end.committer_date.isoformat())
    return Snapshots(branch, c_start, c_end)


def is_unsafe_path(path: str) -> bool:
    """Đường dẫn POSIX trong cây git có thể ghi ra ngoài thư mục đích / vào .git khi giải nén."""
    if "\\" in path:
        return True
    for part in path.split("/"):
        if part in ("", ".", "..") or ":" in part:
            return True
        if part.rstrip(". ").lower() == ".git":
            return True
    return False


@dataclass(frozen=True)
class Screening:
    """Kết quả lọc một file theo đường dẫn / mode / kích thước (chưa xem nội dung)."""

    keep: bool
    language: str | None
    unknown: bool
    excluded_language: bool
    too_large: bool
    warnings: tuple[LocWarning, ...]


@dataclass(frozen=True)
class Selection:
    """Quyết định cuối cho một file."""

    keep: bool
    language: str | None
    warnings: tuple[LocWarning, ...]


_DROPPED = Screening(False, None, False, False, False, ())


def screen_entry(path: str, mode: str, object_type: str, size: int,
                 filters: FilterConfig) -> Screening:
    """Lọc theo đường dẫn / mode / kích thước, chưa cần nội dung (bước 5.3.3)."""
    if object_type != "blob" or mode == "120000":
        logger.debug("Bỏ symlink/submodule %s", path)
        return _DROPPED
    if is_unsafe_path(path):
        logger.warning("Bỏ đường dẫn không an toàn: %r", path)
        warning = LocWarning(WarningKind.UNSAFE_PATH, path,
                             "Bỏ qua file có đường dẫn không an toàn (không đưa vào export)")
        return Screening(False, None, False, False, False, (warning,))
    if check_path(path, filters) is not None:
        return _DROPPED
    full = filters.export_mode == "full"
    unknown = detect_language(path) is None
    language = detect_language(path, filters.exclude_languages)
    excluded_language = language is None and not unknown
    too_large = size > filters.max_file_size_kb * 1024
    if not full and excluded_language:
        return _DROPPED
    warnings: tuple[LocWarning, ...] = ()
    if too_large and (language is not None or not full):
        warnings = (LocWarning(WarningKind.TOO_LARGE, path,
                               f"Bỏ qua file lớn hơn {filters.max_file_size_kb} KB "
                               f"({size / 1024:.1f} KB)"),)
        if not full:
            return Screening(False, language, unknown, excluded_language, too_large, warnings)
    return Screening(True, language, unknown, excluded_language, too_large, warnings)


def finish_entry(path: str, screening: Screening, head: bytes,
                 filters: FilterConfig) -> Selection:
    """Quyết định cuối theo nội dung (bước 5.3.4); head = các byte đầu của nội dung."""
    if not screening.keep:
        raise ValueError("finish_entry chỉ dùng cho file có screening.keep")
    full = filters.export_mode == "full"
    warnings = screening.warnings
    if is_binary(head[:BINARY_SNIFF_BYTES]):
        if not (screening.too_large and screening.language is not None):
            warnings += (LocWarning(WarningKind.BINARY, path, "Bỏ qua file binary"),)
        return Selection(full and not filters.exclude_binary, None, warnings)
    if screening.excluded_language or (screening.too_large and screening.language is None):
        return Selection(True, screening.language, warnings)
    if screening.unknown:
        warnings += (LocWarning(WarningKind.UNKNOWN_LANGUAGE, path,
                                "Bỏ qua file không nhận diện được ngôn ngữ"),)
        return Selection(full, None, warnings)
    return Selection(True, screening.language, warnings)


def select_content(path: str, mode: str, data: bytes, filters: FilterConfig) -> Selection:
    """screen_entry (size = len(data)) + finish_entry cho nội dung đã có trong bộ nhớ."""
    screening = screen_entry(path, mode, "blob", len(data), filters)
    if not screening.keep:
        return Selection(False, None, screening.warnings)
    return finish_entry(path, screening, data[:BINARY_SNIFF_BYTES], filters)


def plan_export(repo: GitRepo, commit_sha: str | None, filters: FilterConfig) -> ExportPlan:
    """Chọn file export của commit theo bộ lọc §9 và D13, kèm cảnh báo."""
    plan = ExportPlan(commit_sha)
    if commit_sha is None:
        return plan
    to_read: list[tuple[ExportFile, Screening]] = []
    for entry in repo.list_tree(commit_sha):
        size = entry.size or 0
        screening = screen_entry(entry.path, entry.mode, entry.object_type, size, filters)
        if not screening.keep:
            plan.warnings.extend(screening.warnings)
            continue
        to_read.append((ExportFile(entry.path, entry.sha, entry.mode, size, screening.language),
                        screening))

    shas = list(dict.fromkeys(item.blob_sha for item, _ in to_read))
    heads = {sha: data[:BINARY_SNIFF_BYTES]
             for sha, data in repo.read_blobs(shas)} if shas else {}
    for item, screening in to_read:
        selection = finish_entry(item.path, screening, heads[item.blob_sha], filters)
        plan.warnings.extend(selection.warnings)
        if selection.keep:
            plan.files.append(ExportFile(item.path, item.blob_sha, item.mode, item.size,
                                         selection.language))

    plan.files.sort(key=lambda f: f.path)
    plan.warnings.sort(key=lambda w: (w.path, w.kind))
    logger.info("Export %s: %d file, %d cảnh báo", commit_sha[:7], len(plan.files),
                len(plan.warnings))
    return plan


@dataclass(frozen=True)
class ZipEntry:
    """Một entry của zip: tham chiếu blob hoặc nội dung bytes (đúng một trong hai)."""

    path: str
    mode: str
    blob_sha: str | None = None
    data: bytes | None = None


def write_entries(repo: GitRepo, entries: Sequence[ZipEntry], zip_path: Path,
                  timestamp: datetime) -> Path:
    """Ghi zip tái lập: entry theo path, timestamp cố định, nội dung nguyên byte."""
    seen: set[str] = set()
    for entry in entries:
        if (entry.blob_sha is None) == (entry.data is None):
            raise ValueError(f"ZipEntry {entry.path!r} cần đúng một trong blob_sha / data")
        if entry.path in seen:
            raise ValueError(f"ZipEntry trùng đường dẫn: {entry.path!r}")
        seen.add(entry.path)
    ordered = sorted(entries, key=lambda e: e.path)
    zip_path = Path(zip_path)
    tmp = zip_path.with_name(zip_path.name + ".tmp")
    stamp = timestamp.replace(tzinfo=None)
    date_time = max(stamp, _ZIP_EPOCH).timetuple()[:6]
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        blobs = repo.read_blobs([e.blob_sha for e in ordered if e.blob_sha is not None])
        with contextlib.closing(blobs), zipfile.ZipFile(
                tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for entry in ordered:
                data = entry.data if entry.blob_sha is None else next(blobs)[1]
                info = zipfile.ZipInfo(entry.path, date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100755 if entry.mode == "100755" else 0o100644) << 16
                zf.writestr(info, data)
            if any(e.blob_sha is not None for e in ordered):
                next(blobs, None)  # cho read_blobs kết thúc bình thường → kiểm mã thoát cat-file
        os.replace(tmp, zip_path)
    except BaseException as exc:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            logger.error("Không ghi được %s: %s", zip_path, exc)
            raise SnapshotError(f"Không ghi được file {zip_path}: {exc}") from exc
        raise
    return zip_path


def write_zip(repo: GitRepo, plan: ExportPlan, zip_path: Path, timestamp: datetime) -> Path:
    """Ghi zip tái lập: entry theo thứ tự path, timestamp cố định, nội dung blob nguyên byte."""
    entries = [ZipEntry(f.path, f.mode, f.blob_sha) for f in plan.files]
    return write_entries(repo, entries, zip_path, timestamp)


def zip_timestamp(commit: CommitInfo | None, timezone: str) -> datetime:
    """Committer date của commit theo timezone; None → 1980-01-01 00:00:00."""
    return commit.committer_date.astimezone(_zone(timezone)) if commit else _ZIP_EPOCH


def export_snapshot(repo: GitRepo, commit: CommitInfo | None, filters: FilterConfig,
                    zip_path: Path, timezone: str) -> ExportPlan:
    """plan_export + write_zip; timestamp = committer date của commit quy đổi về timezone."""
    plan = plan_export(repo, commit.sha if commit else None, filters)
    write_zip(repo, plan, zip_path, zip_timestamp(commit, timezone))
    return plan


def safe_name(text: str) -> str:
    """Ký tự ngoài [A-Za-z0-9._-] → '_' (dùng cho tên nhánh, user-tag trong tên file)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", text) or "_"


def start_zip_name(period: Period, c_start: CommitInfo | None) -> str:
    """`start_<YYYY-MM-DD>_<shortsha>.zip`; C_START rỗng → `..._empty.zip` (§12, D11)."""
    suffix = c_start.short_sha if c_start else "empty"
    return f"start_{period.start_date:%Y-%m-%d}_{suffix}.zip"


def end_zip_name(period: Period, user_tag: str) -> str:
    """`end_<YYYY-MM-DD>_<user-tag>.zip` (§12, D11)."""
    return f"end_{period.end_date:%Y-%m-%d}_{safe_name(user_tag)}.zip"
