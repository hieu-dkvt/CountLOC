"""Đếm LOC (§3.4, §8.1); số liệu theo user / tuần và kiểm tra chéo (§8.2, §8.3)."""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from loc_counter.classifier import LineClassifier, content_sha1, detect_language
from loc_counter.config import FilterConfig, LocCounterError
from loc_counter.filters import check_path, is_binary, is_dir_excluded

if TYPE_CHECKING:  # D37: các module này import counter → chỉ import kiểu
    from loc_counter.attribution import PeriodAttribution, SideInfo
    from loc_counter.builder import UserExport
    from loc_counter.git_repo import LogCommit
    from loc_counter.identity import UserSummary

logger = logging.getLogger(__name__)


class WarningKind(StrEnum):
    """Danh mục loại cảnh báo dùng chung cho cả chương trình (spec counter 5.2)."""

    # M1 — bỏ qua file khi đếm / export
    TOO_LARGE = "too_large"
    BINARY = "binary"
    UNKNOWN_LANGUAGE = "unknown_language"
    READ_ERROR = "read_error"
    # M4 — export, gán tác giả, dựng export end theo user
    UNSAFE_PATH = "unsafe_path"
    RENAME_LIMIT = "rename_limit"
    RENAME_UNRESOLVED = "rename_unresolved"
    UNATTRIBUTED = "unattributed"
    MOVED_LINES = "moved_lines"
    MULTI_USER_HUNK = "multi_user_hunk"
    SEQUENTIAL_EDIT = "sequential_edit"
    MISSING_EOL = "missing_eol"
    PATH_CONFLICT = "path_conflict"
    # M5 — kiểm tra chéo, định danh, tên file trên Windows
    CROSS_CHECK = "cross_check"
    IDENTITY = "identity"
    WINDOWS_PATH = "windows_path"


@dataclass(frozen=True)
class LocWarning:
    """Một cảnh báo; message là tiếng Việt; path "" = cảnh báo cấp repo."""

    kind: WarningKind
    path: str
    message: str


@dataclass(frozen=True)
class FileLoc:
    """LOC của một file."""

    path: str
    language: str
    code_lines: int
    total_lines: int


@dataclass(frozen=True)
class LanguageLoc:
    """LOC gộp theo ngôn ngữ."""

    language: str
    files: int
    code_lines: int


@dataclass
class CountResult:
    """Kết quả đếm một thư mục."""

    files: list[FileLoc] = field(default_factory=list)
    warnings: list[LocWarning] = field(default_factory=list)

    @property
    def total_code(self) -> int:
        """Tổng số dòng code."""
        return sum(f.code_lines for f in self.files)

    def by_language(self) -> list[LanguageLoc]:
        """Sắp xếp code_lines giảm dần, rồi tên ngôn ngữ tăng dần."""
        files: dict[str, int] = defaultdict(int)
        code: dict[str, int] = defaultdict(int)
        for f in self.files:
            files[f.language] += 1
            code[f.language] += f.code_lines
        langs = sorted(files, key=lambda lang: (-code[lang], lang))
        return [LanguageLoc(lang, files[lang], code[lang]) for lang in langs]


def decode_text(data: bytes) -> str:
    """UTF-8 (bỏ BOM) → nếu lỗi thì latin-1."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _is_link(path: str) -> bool:
    """Symlink hoặc junction NTFS (os.path.isjunction có từ Python 3.12)."""
    isjunction = getattr(os.path, "isjunction", None)
    return os.path.islink(path) or (isjunction is not None and isjunction(path))


def _iter_files(
    root: Path, filters: FilterConfig, on_dir_error: Callable[[str, OSError], None]
) -> list[tuple[str, Path]]:
    """Liệt kê (rel_posix, path) theo thứ tự ổn định, cắt thư mục bị loại, bỏ symlink/junction."""

    def onerror(exc: OSError) -> None:
        target = Path(exc.filename) if exc.filename else root
        try:
            rel = target.relative_to(root).as_posix()
        except ValueError:
            rel = target.as_posix()
        on_dir_error(rel, exc)

    found: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if not is_dir_excluded(d, filters) and not _is_link(os.path.join(dirpath, d))
        )
        base = Path(dirpath)
        for name in sorted(filenames):
            path = base / name
            if path.is_symlink():
                continue
            found.append((path.relative_to(root).as_posix(), path))
    return found


def count_directory(
    root: Path, filters: FilterConfig, classifier: LineClassifier | None = None
) -> CountResult:
    """Đếm LOC mọi file source dưới root.

    classifier truyền vào quyết định count_docstrings (filters.count_docstrings chỉ dùng khi
    classifier là None).
    """
    root = Path(root)
    if not root.is_dir():
        raise LocCounterError(f"Thư mục không tồn tại: {root}")
    if classifier is None:
        classifier = LineClassifier(filters.count_docstrings)

    result = CountResult()

    def warn(kind: WarningKind, rel: str, message: str) -> None:
        result.warnings.append(LocWarning(kind, rel, message))

    def dir_error(rel: str, exc: OSError) -> None:
        warn(WarningKind.READ_ERROR, rel, f"Không đọc được thư mục: {exc.strerror or exc}")

    for rel, path in _iter_files(root, filters, dir_error):
        if check_path(rel, filters) is not None:
            continue
        unknown_language = detect_language(rel) is None
        language = detect_language(rel, filters.exclude_languages)
        if language is None and not unknown_language:
            continue  # ngôn ngữ bị loại theo cấu hình

        try:
            size = path.stat().st_size
            if size > filters.max_file_size_kb * 1024:
                warn(WarningKind.TOO_LARGE, rel,
                     f"Bỏ qua file lớn hơn {filters.max_file_size_kb} KB ({size / 1024:.1f} KB)")
                continue
            data = path.read_bytes()
        except OSError as exc:
            warn(WarningKind.READ_ERROR, rel, f"Không đọc được file: {exc}")
            continue
        if is_binary(data):
            warn(WarningKind.BINARY, rel, "Bỏ qua file binary")
            continue
        if language is None:
            warn(WarningKind.UNKNOWN_LANGUAGE, rel, "Bỏ qua file không nhận diện được ngôn ngữ")
            continue

        is_code = classifier.classify(decode_text(data), rel, content_sha1(data))
        result.files.append(FileLoc(rel, language, sum(is_code), len(is_code)))

    result.files.sort(key=lambda f: f.path)
    result.warnings.sort(key=lambda w: (w.path, w.kind))
    logger.info("Đếm %d file source, %d cảnh báo trong %s",
                len(result.files), len(result.warnings), root)
    return result


# ---------- M5: đếm từ nội dung entry (D36) ----------
BlobReader = Callable[[Sequence[str]], Iterator[tuple[str, bytes]]]


@dataclass(frozen=True)
class ContentFile:
    """Một entry của bản export: nội dung nguyên byte như trong zip."""

    path: str
    language: str | None
    data: bytes
    cache_key: str


def is_countable(language: str | None, size: int, filters: FilterConfig) -> bool:
    """File được đếm LOC: là source (language khác None) và size <= max_file_size_kb*1024."""
    return language is not None and size <= filters.max_file_size_kb * 1024


def count_files(files: Iterable[ContentFile], filters: FilterConfig,
                classifier: LineClassifier | None = None) -> CountResult:
    """Đếm LOC của một bản export từ nội dung entry (D36); không phát cảnh báo."""
    if classifier is None:
        classifier = LineClassifier(filters.count_docstrings)
    result = CountResult()
    seen: set[str] = set()
    for f in files:
        if f.path in seen:
            raise ValueError(f"ContentFile trùng đường dẫn: {f.path}")
        seen.add(f.path)
        if f.language is None or not is_countable(f.language, len(f.data), filters):
            continue
        is_code = classifier.classify(decode_text(f.data), f.path, f.cache_key)
        result.files.append(FileLoc(f.path, f.language, sum(is_code), len(is_code)))
    result.files.sort(key=lambda f: f.path)
    logger.debug("Đếm %d file source từ nội dung export", len(result.files))
    return result


def count_export(export: UserExport, read_blobs: BlobReader, filters: FilterConfig,
                 classifier: LineClassifier | None = None) -> CountResult:
    """Đọc nội dung file source của export (blob hoặc data) rồi gọi count_files."""
    wanted = [f for f in export.files if f.language is not None]
    shas = list(dict.fromkeys(f.blob_sha for f in wanted if f.blob_sha is not None))
    blobs: dict[str, bytes] = {}
    if shas:
        it = read_blobs(shas)
        try:
            blobs = dict(it)
        finally:  # đóng generator cả khi lỗi (F3); iterator thường không có close()
            close = getattr(it, "close", None)
            if close is not None:
                close()
    contents = [ContentFile(f.path, f.language,
                            f.data if f.data is not None else blobs[f.blob_sha or ""],
                            f.cache_key) for f in wanted]
    return count_files(contents, filters, classifier)


# ---------- M5: so sánh start ↔ end (§8.1, §10.3) ----------
@dataclass(frozen=True)
class LanguageRow:
    """LOC một ngôn ngữ ở export start và end."""

    language: str
    files_start: int
    loc_start: int
    files_end: int
    loc_end: int

    @property
    def delta(self) -> int:
        """loc_end - loc_start."""
        return self.loc_end - self.loc_start


def compare_languages(start: CountResult, end: CountResult) -> list[LanguageRow]:
    """Hợp ngôn ngữ của hai phía; sắp (-loc_end, -loc_start, language)."""
    s = {lang.language: lang for lang in start.by_language()}
    e = {lang.language: lang for lang in end.by_language()}
    rows = []
    for name in s.keys() | e.keys():
        a, b = s.get(name), e.get(name)
        rows.append(LanguageRow(name, a.files if a else 0, a.code_lines if a else 0,
                                b.files if b else 0, b.code_lines if b else 0))
    rows.sort(key=lambda r: (-r.loc_end, -r.loc_start, r.language))
    return rows


@dataclass(frozen=True)
class FileRow:
    """LOC một file ở export start và end (§10.3 "Chi tiết theo file")."""

    path: str
    renamed_from: str | None
    language: str
    loc_start: int
    loc_end: int

    @property
    def delta(self) -> int:
        """loc_end - loc_start."""
        return self.loc_end - self.loc_start


def rename_map(attribution: PeriodAttribution, end_paths: Collection[str]) -> dict[str, str]:
    """{đường dẫn mới: đường dẫn cũ} cho cặp đổi tên có tên mới nằm trong export end."""
    paths = set(end_paths)
    renames: dict[str, str] = {}
    for f in attribution.files:
        entry = f.entry
        if (entry.status.startswith("R") and entry.old_path is not None
                and entry.new_path is not None and entry.old_path != entry.new_path
                and entry.new_path in paths):
            renames[entry.new_path] = entry.old_path
    return renames


def compare_files(start: CountResult, end: CountResult,
                  renames: Mapping[str, str] | None = None) -> list[FileRow]:
    """Ghép file start ↔ end theo đường dẫn (và theo renames); sắp theo path."""
    sb = {f.path: f for f in start.files}
    eb = {f.path: f for f in end.files}
    renames = renames or {}
    used: set[str] = set()
    rows: list[FileRow] = []
    for p in sorted(eb):
        f = eb[p]
        src = renames.get(p)
        if p not in sb and src is not None and src in sb and src not in eb:
            used.add(src)
            rows.append(FileRow(p, src, f.language, sb[src].code_lines, f.code_lines))
        elif p in sb:
            used.add(p)
            rows.append(FileRow(p, None, f.language, sb[p].code_lines, f.code_lines))
        else:
            rows.append(FileRow(p, None, f.language, 0, f.code_lines))
    for q in sb:
        if q not in used:
            rows.append(FileRow(q, None, sb[q].language, sb[q].code_lines, 0))
    rows.sort(key=lambda r: r.path)
    return rows


# ---------- M5: số liệu theo user (§8.2) ----------
@dataclass(frozen=True)
class UserMetrics:
    """Số liệu §8.2 của một account; account "" = dòng Tổng."""

    account: str
    is_bot: bool
    commits: int
    added_lines: int
    deleted_lines: int
    added_code: int
    deleted_code: int
    files: tuple[str, ...]

    @property
    def net_code(self) -> int:
        """added_code - deleted_code."""
        return self.added_code - self.deleted_code

    @property
    def files_changed(self) -> int:
        """Số file source đã thay đổi."""
        return len(self.files)


def _counted_side(side: SideInfo | None) -> bool:
    """Phía là source được đếm (A9): keep, có ngôn ngữ, không quá lớn."""
    return (side is not None and side.keep and side.language is not None
            and not side.too_large)


def user_metrics(attribution: PeriodAttribution, summaries: Sequence[UserSummary],
                 accounts: Collection[str]) -> list[UserMetrics]:
    """Số liệu §8.2 cho từng account; sắp (-commits, account)."""
    by_summary = {u.account: u for u in summaries}
    stats = {u.account: u for u in attribution.users}
    changed: dict[str, set[str]] = defaultdict(set)  # account → file source đã thay đổi
    for f in attribution.files:
        if f.granularity not in ("lines", "last"):
            continue
        if not (_counted_side(f.old) or _counted_side(f.new)):
            continue
        touched = {*f.added_by.values(), *f.deleted_by.values()}
        if f.renamed_by is not None:
            touched.add(f.renamed_by)
        for account in touched:
            changed[account].add(f.path)
    rows: list[UserMetrics] = []
    for a in dict.fromkeys(accounts):
        summary = by_summary.get(a)
        if summary is None:
            logger.warning("Account %s không có trong danh sách user của kỳ", a)
        s = stats.get(a)
        files = sorted(changed.get(a, ()))
        rows.append(UserMetrics(
            a, summary.is_bot if summary else False, summary.commits if summary else 0,
            s.added_lines if s else 0, s.deleted_lines if s else 0,
            s.added_code if s else 0, s.deleted_code if s else 0, tuple(files)))
    rows.sort(key=lambda r: (-r.commits, r.account))
    return rows


def total_metrics(rows: Sequence[UserMetrics]) -> UserMetrics:
    """Dòng Tổng: cộng các cột số, files = hợp các tập file (không đếm trùng)."""
    return UserMetrics(
        "", False, sum(r.commits for r in rows), sum(r.added_lines for r in rows),
        sum(r.deleted_lines for r in rows), sum(r.added_code for r in rows),
        sum(r.deleted_code for r in rows), tuple(sorted({p for r in rows for p in r.files})))


# ---------- M5: theo tuần (D35) ----------
@dataclass(frozen=True)
class WeekRow:
    """Code ròng của một account trong một tuần ISO."""

    week: str
    week_start: date
    account: str
    commits: int
    added_code: int
    deleted_code: int

    @property
    def net_code(self) -> int:
        """added_code - deleted_code."""
        return self.added_code - self.deleted_code


def iso_week(moment: datetime, timezone: str) -> tuple[str, date]:
    """(nhãn tuần ISO, thứ Hai) của thời điểm aware, quy về múi giờ đã chọn."""
    year, week, _ = moment.astimezone(ZoneInfo(timezone)).isocalendar()
    return f"{year}-W{week:02d}", date.fromisocalendar(year, week, 1)


def weekly_metrics(attribution: PeriodAttribution, commits: Sequence[LogCommit],
                   accounts: Collection[str], timezone: str) -> list[WeekRow]:
    """Code ròng theo tuần ISO (author date) cho từng account (D35); sắp (week_start, account)."""
    wanted = set(accounts)
    by_sha = {c.sha: c for c in commits}
    acc = attribution.commit_accounts
    cells: dict[tuple[str, date, str], list[int]] = {}

    def cell(commit: LogCommit, account: str) -> list[int]:
        week, start = iso_week(commit.author_date, timezone)
        return cells.setdefault((week, start, account), [0, 0, 0])

    for c in commits:
        account = acc.get(c.sha)
        if not c.is_merge and account is not None and account in wanted:
            cell(c, account)[0] += 1
    for s in attribution.commit_stats:
        if s.account not in wanted:
            continue
        commit = by_sha.get(s.sha)
        if commit is None:
            logger.warning("Commit %s của commit_stats không có trong danh sách commit", s.sha)
            continue
        row = cell(commit, s.account)
        row[1] += s.added_code
        row[2] += s.deleted_code
    rows = [WeekRow(week, start, account, *values)
            for (week, start, account), values in cells.items() if any(values)]
    rows.sort(key=lambda r: (r.week_start, r.account))
    return rows


# ---------- M8: theo PR (D43) ----------
NO_PR_LABEL = "(Không thuộc PR)"
_MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+)\b")
_SQUASH_PR_RE = re.compile(r"\(#(\d+)\)\s*$")


@dataclass(frozen=True)
class PrRef:
    """Một PR nhận diện từ lịch sử git: merge commit "Merge pull request #N" hoặc squash "(#N)"."""

    number: int
    title: str
    merge_sha: str
    merged_at: datetime


@dataclass(frozen=True)
class PrRow:
    """LOC của một account trong một PR; pr None = nhóm "Không thuộc PR"."""

    pr: int | None
    title: str
    merge_sha: str
    merged_at: datetime | None
    account: str
    commits: int
    added_code: int
    deleted_code: int

    @property
    def net_code(self) -> int:
        """added_code - deleted_code."""
        return self.added_code - self.deleted_code


def _merge_pr_title(commit: LogCommit) -> str:
    """Tiêu đề PR của merge commit: dòng đầu body, rồi phần sau "from ", rồi subject."""
    if commit.body_title:
        return commit.body_title
    _, sep, rest = commit.subject.partition(" from ")
    return rest.strip() if sep and rest.strip() else commit.subject


def _ancestor_bits(commits: Sequence[LogCommit]) -> list[int]:
    """Bitset (theo chỉ số trong commits) của mỗi commit và mọi tổ tiên nằm trong commits."""
    index = {c.sha: i for i, c in enumerate(commits)}
    parents = [[index[p] for p in c.parents if p in index] for c in commits]
    anc = [0] * len(commits)
    state = [0] * len(commits)  # 0 chưa thăm, 1 đang trên đường đi DFS, 2 đã tính xong
    for root in range(len(commits)):
        if state[root]:
            continue
        state[root] = 1
        stack = [(root, iter(parents[root]))]
        while stack:
            i, todo = stack[-1]
            for p in todo:
                if state[p] == 0:  # state 1 = vòng (git không tạo ra): bỏ cạnh, không treo
                    state[p] = 1
                    stack.append((p, iter(parents[p])))
                    break
            else:
                bits = 1 << i
                for p in parents[i]:
                    if state[p] == 2:
                        bits |= anc[p]
                anc[i] = bits
                state[i] = 2
                stack.pop()
    return anc


def _bit_indexes(bits: int) -> Iterator[int]:
    """Chỉ số các bit 1 của bits, tăng dần."""
    while bits:
        low = bits & -bits
        yield low.bit_length() - 1
        bits ^= low


def pr_membership(commits: Sequence[LogCommit]) -> dict[str, PrRef]:
    """commit sha → PR chứa nó (D43); commit không thuộc PR nào không có khóa."""
    index = {c.sha: i for i, c in enumerate(commits)}
    merge_prs = [(i, c, int(m.group(1))) for i, c in enumerate(commits)
                 if c.is_merge and (m := _MERGE_PR_RE.match(c.subject))]
    result: dict[str, PrRef] = {}
    if merge_prs:
        anc = _ancestor_bits(commits)
        groups: list[tuple[int, str, PrRef, int]] = []
        for i, c, number in merge_prs:
            first = index.get(c.parents[0])
            others = 0
            for p in c.parents[1:]:
                if p in index:
                    others |= anc[index[p]]
            members = (others & ~(anc[first] if first is not None else 0)) | (1 << i)
            ref = PrRef(number, _merge_pr_title(c), c.sha, c.author_date)
            groups.append((members.bit_count(), c.sha, ref, members))
        for _, _, ref, members in sorted(groups, key=lambda g: g[:2]):  # PR trong cùng nhất trước
            for k in _bit_indexes(members):
                result.setdefault(commits[k].sha, ref)
    for c in commits:
        if c.sha in result:
            continue
        m = _SQUASH_PR_RE.search(c.subject)
        if m:
            title = c.subject[:m.start()].strip() or c.subject
            result[c.sha] = PrRef(int(m.group(1)), title, c.sha, c.author_date)
    return result


def pr_metrics(attribution: PeriodAttribution, commits: Sequence[LogCommit],
               accounts: Collection[str], timezone: str) -> list[PrRow]:
    """LOC theo (PR, account) (D43); sắp (PR tăng dần, account), nhóm không thuộc PR cuối."""
    wanted = set(accounts)
    membership = pr_membership(commits)
    canonical: dict[int, PrRef] = {}  # trùng số PR: lấy PR merge sớm nhất
    for ref in membership.values():
        cur = canonical.get(ref.number)
        if cur is None or (ref.merged_at, ref.merge_sha) < (cur.merged_at, cur.merge_sha):
            canonical[ref.number] = ref
    cells: dict[tuple[int | None, str], list[int]] = {}

    def cell(sha: str, account: str) -> list[int]:
        ref = membership.get(sha)
        return cells.setdefault((ref.number if ref else None, account), [0, 0, 0])

    acc = attribution.commit_accounts
    for c in commits:
        account = acc.get(c.sha)
        if not c.is_merge and account is not None and account in wanted:
            cell(c.sha, account)[0] += 1
    for s in attribution.commit_stats:
        if s.account in wanted:
            row = cell(s.sha, s.account)
            row[1] += s.added_code
            row[2] += s.deleted_code
    tz = ZoneInfo(timezone)
    rows: list[PrRow] = []
    for (number, account), values in cells.items():
        if not any(values):
            continue
        if number is None:
            rows.append(PrRow(None, "", "", None, account, *values))
        else:
            ref = canonical[number]
            rows.append(PrRow(number, ref.title, ref.merge_sha, ref.merged_at.astimezone(tz),
                              account, *values))
    rows.sort(key=lambda r: (r.pr is None, r.pr or 0, r.account))
    return rows


# ---------- M5: kiểm tra chéo (§8.3, D38) ----------
CROSS_CHECK_THRESHOLD_PERCENT = 0.5


@dataclass(frozen=True)
class CrossCheck:
    """Kết quả kiểm tra chéo loc_start + Σ net_code ≈ loc_end."""

    loc_start: int
    sum_net_code: int
    loc_end: int
    diff_percent: float
    threshold_percent: float
    ok: bool

    @property
    def expected_loc_end(self) -> int:
        """loc_start + sum_net_code."""
        return self.loc_start + self.sum_net_code


def cross_check(loc_start: int, loc_end: int, net_codes: Iterable[int],
                threshold_percent: float = CROSS_CHECK_THRESHOLD_PERCENT) -> CrossCheck:
    """Kiểm tra chéo §8.3 (D38)."""
    sum_net = sum(net_codes)
    expected = loc_start + sum_net
    # so ngưỡng trên giá trị chính xác (phân số) để "đúng bằng ngưỡng" luôn đạt (A11)
    if loc_end > 0:
        exact = Fraction(abs(expected - loc_end) * 100, loc_end)
    else:
        exact = Fraction(0 if expected == 0 else 100)
    return CrossCheck(loc_start, sum_net, loc_end, round(float(exact), 3), threshold_percent,
                      exact <= Fraction(str(threshold_percent)))


def cross_check_warning(check: CrossCheck, tag: str) -> LocWarning | None:
    """Cảnh báo CROSS_CHECK (path "") khi check.ok là False; ngược lại None."""
    if check.ok:
        return None
    return LocWarning(
        WarningKind.CROSS_CHECK, "",
        f"Kiểm tra chéo ({tag}): loc_start {check.loc_start} + tổng code ròng "
        f"{check.sum_net_code:+d} = {check.expected_loc_end}, loc_end = {check.loc_end}, "
        f"lệch {check.diff_percent:.3f}% (ngưỡng {check.threshold_percent}%)")
