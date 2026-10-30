"""Dựng export end theo user (§3.3, §7.3, §7.4, §12, PLAN D21–D33, D39)."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Collection, Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path

from loc_counter.attribution import FileAttribution, PeriodAttribution, SideInfo
from loc_counter.classifier import content_sha1
from loc_counter.config import FilterConfig
from loc_counter.counter import LocWarning, WarningKind
from loc_counter.git_repo import CommitInfo, GitRepo, Hunk
from loc_counter.identity import UserSummary
from loc_counter.snapshot import (
    ExportPlan,
    ZipEntry,
    safe_name,
    select_content,
    write_entries,
    zip_timestamp,
)

logger = logging.getLogger(__name__)

_SPECIAL_MODES = ("120000", "160000")
_MULTI_TAG = re.compile(r"multi-\d+users", re.IGNORECASE)
_WINDOWS_RESERVED = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"{dev}{n}" for dev in ("com", "lpt") for n in [*"0123456789", "¹", "²", "³"]])
_WINDOWS_BAD_CHARS = frozenset('<>"|?*') | {chr(c) for c in range(0x20)}


def split_lines_keepends(data: bytes) -> list[bytes]:
    """Tách dòng theo git (D8): sau mỗi b"\\n", giữ nguyên byte (CRLF, BOM)."""
    parts = data.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def build_user_file(base_lines: Sequence[bytes], final_lines: Sequence[bytes],
                    hunks: Sequence[Hunk], added_by: Mapping[int, str],
                    deleted_by: Mapping[int, str], users: Set[str]) -> list[bytes]:
    """§7.3 trên bytes với hunk của git (dòng ngoài hunk luôn giữ)."""
    result: list[bytes] = []
    pos = 0
    for h in hunks:
        result.extend(base_lines[pos:h.old_start])
        result.extend(base_lines[i] for i in range(h.old_start, h.old_start + h.old_count)
                      if deleted_by.get(i) not in users)
        result.extend(final_lines[k] for k in range(h.new_start, h.new_start + h.new_count)
                      if added_by.get(k) in users)
        pos = h.old_start + h.old_count
    result.extend(base_lines[pos:])
    return result


def fix_missing_eol(lines: Sequence[bytes]) -> tuple[list[bytes], list[int]]:
    """Thêm EOL đa số cho dòng thiếu EOL không phải dòng cuối; trả (dòng mới, chỉ số đã sửa)."""
    crlf = sum(1 for line in lines if line.endswith(b"\r\n"))
    lf = sum(1 for line in lines if line.endswith(b"\n") and not line.endswith(b"\r\n"))
    eol = b"\r\n" if crlf > lf else b"\n"
    fixed: list[int] = []
    out = list(lines)
    for i in range(len(out) - 1):
        if not out[i].endswith(b"\n"):
            out[i] += eol
            fixed.append(i)
    return out, fixed


@dataclass(frozen=True)
class BuiltFile:
    """Một file của export end theo user: tham chiếu blob hoặc nội dung đã dựng."""

    path: str
    mode: str
    language: str | None
    blob_sha: str | None = None
    data: bytes | None = None

    def __post_init__(self) -> None:
        if (self.blob_sha is None) == (self.data is None):
            raise ValueError(f"BuiltFile {self.path!r} cần đúng một trong blob_sha / data")

    def zip_entry(self) -> ZipEntry:
        """ZipEntry tương ứng cho snapshot.write_entries."""
        return ZipEntry(self.path, self.mode, self.blob_sha, self.data)

    @property
    def cache_key(self) -> str:
        """blob_sha, hoặc content_sha1(data) (khóa cache phân loại §6.3 cho M5)."""
        if self.blob_sha is not None:
            return self.blob_sha
        assert self.data is not None
        return content_sha1(self.data)


@dataclass(frozen=True)
class UserExport:
    """Export end của một tập user (hoặc bản nguyên của một snapshot)."""

    accounts: tuple[str, ...] | None
    tag: str
    files: tuple[BuiltFile, ...]
    warnings: tuple[LocWarning, ...]


@dataclass(frozen=True)
class EndExportJob:
    """Một zip end cần ghi; accounts None = dùng thẳng C_END."""

    tag: str
    accounts: tuple[str, ...] | None


def _ranges_text(indices: Iterable[int]) -> str:
    """Chỉ số 0-based → khoảng 1-based gộp liền kề, vd. '3–5, 9'."""
    ordered = sorted(set(indices))
    parts: list[str] = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1:
            j += 1
        first, last = ordered[i] + 1, ordered[j] + 1
        parts.append(str(first) if first == last else f"{first}–{last}")
        i = j + 1
    return ", ".join(parts)


def find_path_conflicts(paths: Iterable[str]) -> list[tuple[str, str]]:
    """Các cặp (p, q), p < q, xung đột khi giải nén: q nằm dưới thư mục p (không phân biệt
    hoa thường) hoặc p.casefold() == q.casefold(). Sắp tăng dần."""
    unique = sorted(set(paths))
    by_fold: dict[str, list[str]] = {}
    for p in unique:
        by_fold.setdefault(p.casefold(), []).append(p)
    pairs: set[tuple[str, str]] = set()
    for same in by_fold.values():
        pairs.update((a, b) for i, a in enumerate(same) for b in same[i + 1:])
    for q in unique:
        parts = q.split("/")
        for depth in range(1, len(parts)):
            prefix = "/".join(parts[:depth]).casefold()
            for p in by_fold.get(prefix, ()):
                pairs.add((min(p, q), max(p, q)))
    return sorted(pairs)


def path_conflict_warnings(paths: Iterable[str], label: str = "") -> list[LocWarning]:
    """PATH_CONFLICT cho cả hai đường dẫn của mỗi cặp find_path_conflicts (spec 5.7)."""
    warnings: list[LocWarning] = []
    for p, q in find_path_conflicts(paths):
        if label:
            logger.warning("Đường dẫn xung đột trong export %s: %r ↔ %r", label, p, q)
        else:
            logger.warning("Đường dẫn xung đột: %r ↔ %r", p, q)
        for path, other in ((p, q), (q, p)):
            warnings.append(LocWarning(
                WarningKind.PATH_CONFLICT, path,
                f"Đường dẫn xung đột với {other} khi giải nén (file/thư mục trùng tên hoặc chỉ "
                "khác hoa thường); cả hai được giữ trong zip"))
    return warnings


def windows_path_issues(path: str) -> list[str]:
    """Lý do (tiếng Việt) khiến đường dẫn không giải nén đúng trên Windows; [] = hợp lệ (5.8)."""
    issues: list[str] = []
    for part in path.split("/"):
        if part in ("", ".", ".."):
            continue  # thuộc UNSAFE_PATH, không có trong export
        stem = part.split(".", 1)[0].rstrip(" ")
        if stem.casefold() in _WINDOWS_RESERVED:
            issues.append(f'"{part}" trùng tên thiết bị dành riêng của Windows ({stem.upper()})')
        if any(ch in _WINDOWS_BAD_CHARS for ch in part):
            issues.append(f'"{part}" chứa ký tự không hợp lệ trên Windows '
                          '(<>"|?* hoặc ký tự điều khiển)')
        if part.endswith((".", " ")):
            issues.append(f'"{part}" kết thúc bằng dấu chấm hoặc khoảng trắng '
                          "(Windows tự bỏ khi giải nén)")
    return issues


def windows_path_warnings(paths: Iterable[str]) -> list[LocWarning]:
    """Một WINDOWS_PATH cho mỗi đường dẫn có lý do, sắp theo path; file vẫn giữ (5.8, D39)."""
    warnings: list[LocWarning] = []
    for path in sorted(set(paths)):
        issues = windows_path_issues(path)
        if not issues:
            continue
        logger.warning("Đường dẫn không hợp lệ trên Windows: %r", path)
        warnings.append(LocWarning(
            WarningKind.WINDOWS_PATH, path,
            "Đường dẫn có thể không giải nén đúng trên Windows: " + "; ".join(issues)
            + "; file vẫn được giữ trong zip và được đếm LOC"))
    return warnings


def _chosen_name(fa: FileAttribution, users: Set[str]) -> str:
    """Tên trong export: rename theo người đổi tên (D25), ngược lại path của entry."""
    entry = fa.entry
    if entry.status == "R" and entry.old_path is not None and entry.new_path is not None:
        return entry.new_path if fa.renamed_by in users else entry.old_path
    return fa.path


def _is_blob(side: SideInfo | None) -> bool:
    """Phía có mặt và là blob thường (không phải symlink / gitlink)."""
    return side is not None and side.mode not in _SPECIAL_MODES


def build_user_export(repo: GitRepo, attribution: PeriodAttribution, start_plan: ExportPlan,
                      users: Set[str], filters: FilterConfig, tag: str) -> UserExport:
    """Export end = C_START + thay đổi của users (§3.3, §7.3, §7.4)."""
    if start_plan.commit_sha != attribution.c_start:
        raise ValueError("start_plan không thuộc C_START của attribution")
    users = frozenset(users)
    changed_old = {fa.entry.old_path for fa in attribution.files if fa.entry.old_path}
    files: list[BuiltFile] = [BuiltFile(f.path, f.mode, f.language, blob_sha=f.blob_sha)
                              for f in start_plan.files if f.path not in changed_old]
    warnings: list[LocWarning] = [w for w in start_plan.warnings if w.path not in changed_old]

    shas = [side.sha for fa in attribution.files for side in (fa.old, fa.new) if _is_blob(side)]
    shas = list(dict.fromkeys(shas))
    blobs = dict(repo.read_blobs(shas)) if shas else {}

    for fa in attribution.files:
        built, file_warnings = _build_file(fa, users, filters, blobs)
        warnings.extend(file_warnings)
        if built is not None:
            files.append(built)

    seen: set[str] = set()
    for f in files:
        if f.path in seen:
            raise ValueError(f"Trùng đường dẫn trong export: {f.path!r}")
        seen.add(f.path)
    warnings.extend(path_conflict_warnings(seen, tag))

    files.sort(key=lambda f: f.path)
    warnings.sort(key=lambda w: (w.path, w.kind))
    logger.info("Export end %s: %d file, %d cảnh báo", tag, len(files), len(warnings))
    return UserExport(tuple(sorted(users)), tag, tuple(files), tuple(warnings))


def _build_file(fa: FileAttribution, users: frozenset[str], filters: FilterConfig,
                blobs: Mapping[str, bytes]) -> tuple[BuiltFile | None, list[LocWarning]]:
    """Dựng một cặp file theo granularity (5.2 bước 4)."""
    old, new = fa.old, fa.new
    name = _chosen_name(fa, users)

    if fa.granularity == "skip":
        side = new if new is not None else old
        if not _is_blob(side):
            return None, []
        assert side is not None
        sel = select_content(side.path, side.mode, blobs[side.sha], filters)
        return None, list(sel.warnings)

    if fa.granularity in ("whole", "last"):
        side = new if fa.last_touch_by in users else old
        if not _is_blob(side):
            return None, []
        assert side is not None
        sel = select_content(name, side.mode, blobs[side.sha], filters)
        built = BuiltFile(name, side.mode, sel.language, blob_sha=side.sha) if sel.keep else None
        return built, list(sel.warnings)

    old_data = blobs[old.sha] if old is not None else b""
    new_data = blobs[new.sha] if new is not None else b""
    out = build_user_file(split_lines_keepends(old_data), split_lines_keepends(new_data),
                          fa.hunks, fa.added_by, fa.deleted_by, users)
    out, fixed = fix_missing_eol(out)
    content = b"".join(out)

    if old is None and not content:
        return None, []  # file người khác tạo / file mới 0 byte (§7.4, Q31)
    if new is None:
        if old is not None and old.size == 0:
            content = old_data  # không biết ai xóa → giữ bản start (A2)
        elif not content:
            return None, []  # user chọn xóa hết
    mode = old.mode if old is not None else new.mode  # type: ignore[union-attr]
    sel = select_content(name, mode, content, filters)
    warnings = list(sel.warnings)
    if not sel.keep:
        return None, warnings
    if fixed:  # chỉ cảnh báo khi file có trong export
        warnings.append(LocWarning(
            WarningKind.MISSING_EOL, name,
            f"Thêm xuống dòng cho dòng {_ranges_text(fixed)} thiếu EOL ở giữa file đã dựng"))
    if new is not None and content == new_data:
        return BuiltFile(name, mode, sel.language, blob_sha=new.sha), warnings
    if old is not None and content == old_data:
        return BuiltFile(name, mode, sel.language, blob_sha=old.sha), warnings
    return BuiltFile(name, mode, sel.language, data=content), warnings


def export_from_plan(plan: ExportPlan, tag: str = "all") -> UserExport:
    """Bản nguyên của một snapshot (export end tất cả user = plan_export(C_END))."""
    files = tuple(BuiltFile(f.path, f.mode, f.language, blob_sha=f.blob_sha) for f in plan.files)
    return UserExport(None, tag, files, tuple(plan.warnings))


def user_tag(accounts: Collection[str], *, all_users: bool = False,
             taken: Collection[str] = ()) -> str:
    """`all`, tên một user (an toàn cho tên file), hoặc `multi-<n>users` (§12, Q29)."""
    if all_users:
        return "all"
    accounts = sorted(set(accounts))
    if len(accounts) >= 2:
        return f"multi-{len(accounts)}users"
    if not accounts:
        raise ValueError("user_tag cần ít nhất một account")
    account = accounts[0]
    tag = safe_name(account)
    folded = {t.casefold() for t in taken}
    if (tag != account or tag.casefold() in folded or tag.casefold() == "all"
            or _MULTI_TAG.fullmatch(tag)):
        tag = f"{tag}-{hashlib.sha1(account.encode('utf-8')).hexdigest()[:6]}"
    return tag


def plan_end_exports(selected: Collection[str] | None, period_users: Sequence[UserSummary],
                     exclude_bots: bool = False, separate: bool = False) -> list[EndExportJob]:
    """Danh sách zip end cần ghi theo D21 / Q29; selected None = "Tất cả user"."""
    pool = sorted({u.account for u in period_users if not (exclude_bots and u.is_bot)})
    jobs: list[EndExportJob] = []
    taken: list[str] = []

    def add(tag: str, accounts: tuple[str, ...] | None) -> None:
        jobs.append(EndExportJob(tag, accounts))
        taken.append(tag)

    if selected is None:
        has_bot = any(u.is_bot for u in period_users)
        add("all", tuple(pool) if exclude_bots and has_bot else None)
        singles = pool if separate else []
    else:
        chosen = sorted(set(selected))
        if not chosen:
            raise ValueError("Chưa chọn user nào")
        add(user_tag(chosen), tuple(chosen))
        singles = chosen if separate and len(chosen) >= 2 else []
    for account in singles:
        add(user_tag([account], taken=taken), (account,))
    return jobs


def write_user_export(repo: GitRepo, export: UserExport, zip_path: Path,
                      c_end: CommitInfo, timezone: str) -> Path:
    """Ghi zip export qua snapshot.write_entries, timestamp = committer date C_END."""
    return write_entries(repo, [f.zip_entry() for f in export.files], zip_path,
                         zip_timestamp(c_end, timezone))
