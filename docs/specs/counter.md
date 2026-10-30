---
id: counter
title: Đếm LOC và số liệu
type: module
milestone: M1, M4, M5
modules: [src/loc_counter/counter.py]
tests: [tests/test_counter.py, tests/test_counter_metrics.py]
spec_refs: ["3.3", "3.4", "6.3", "7.2", "7.3", "7.4", "7.5", "8.1", "8.2", "8.3", "9", "10.3", "12", "15", "16"]
depends_on: [config, filters, classifier, attribution, builder, identity]
status: reviewed
---

# Đếm LOC và số liệu

## 1. Mục đích & phạm vi
Đếm LOC của mọi file source trong một thư mục (thư mục export hoặc thư mục bất kỳ cho lệnh `count`), chia theo ngôn ngữ và theo file, kèm danh sách cảnh báo.
Phạm vi M1: đếm thư mục. M5 sẽ mở rộng spec này (số liệu theo user §8.2, kiểm tra chéo §8.3).
M4 bổ sung (cập nhật nhỏ): **danh mục loại cảnh báo** dùng chung cho cả chương trình (`WarningKind` là nơi định nghĩa duy nhất — PLAN F8, snapshot A5) gồm các loại do `snapshot`, `attribution`, `builder` phát ra (mục 5.2). `count_directory` **không đổi** hành vi (TC-01..15 giữ nguyên).
Ngoài phạm vi M4: cảnh báo kiểm tra chéo §8.3 (`CROSS_CHECK`, thêm ở M5 cùng §8.3); cột của `warnings.csv` và khử trùng cảnh báo (`report`/`pipeline` M5); F9 (giải nén export ra đĩa Windows — quyết định ở M5).

**M5 bổ sung** (mục 3.2, 5.3–5.9) — các phép tính số liệu thuần (không gọi git, không ghi file) mà `pipeline` dùng để dựng báo cáo:
- Đếm LOC của một bản export **từ chính nội dung các entry ghi vào zip** (`count_files`, `count_export` — PLAN D36, thay cho giải nén ra đĩa; F9).
- So sánh start ↔ end theo ngôn ngữ (§8.1) và theo file (§10.3 "Chi tiết theo file").
- Số liệu theo user §8.2 (`user_metrics`, dòng Tổng `total_metrics`), theo tuần (`weekly_metrics`, D35), kiểm tra chéo §8.3 (`cross_check`, D38).
- Thêm `WarningKind.CROSS_CHECK`, `IDENTITY`, `WINDOWS_PATH` (D39).

Ngoài phạm vi M5 của spec này: đọc blob (người gọi truyền hàm đọc); phát hiện tên không hợp lệ trên Windows và `PATH_CONFLICT` cho export start / `all` (spec `builder` cập nhật M5 / `pipeline`); chuyển cảnh báo GitHub API thành `LocWarning(IDENTITY)` (`pipeline`); định dạng bảng, cột, nhãn dòng Tổng trong xlsx/CSV (`report`); chọn tập account (`pipeline`). `count_directory` **không đổi** (TC-01..15 giữ nguyên).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | LOC = tổng dòng code của mọi file source trong thư mục | §3.4 |
| R2 | Chia theo ngôn ngữ (tên lexer Pygments) | §8.1 |
| R3 | Áp bộ lọc §9; bỏ file quá lớn, binary, không nhận diện ngôn ngữ và ghi cảnh báo | §6.3, §7.5, §9 |
| R4 | Đọc UTF-8, lỗi thì `latin-1`; vẫn lỗi coi là binary + cảnh báo | §15 |
| R5 | Cache phân loại; file ngoài Git dùng SHA-1 nội dung | §6.3 |
| R6 | Tái lập: cùng input cho cùng kết quả | §15 |
| R7 | Cảnh báo hunk chứa dòng của nhiều user | §7.5, PLAN D27 (Q32) |
| R8 | Cảnh báo dòng bị nhiều user sửa liên tiếp (gán cho người sửa cuối) | §7.5, §16, PLAN D26 |
| R9 | Cảnh báo các trường hợp gán tác giả / dựng file đặc biệt đã chốt: dòng bị dời (D22), dòng không xác định được tác giả (D24), không xác định được người đổi tên (D25), vượt rename limit (D27/Q24), dòng thiếu EOL được thêm EOL (D27/Q28) | §7.2–§7.4, PLAN D22, D24, D25, D27 |
| R10 | File bị bỏ khỏi export vì đường dẫn không an toàn phải có cảnh báo trong `warnings.csv` | PLAN F8, snapshot A5 |
| R11 | Đường dẫn xung đột (file/thư mục, chỉ khác hoa thường) trong export theo user phải có cảnh báo | PLAN D32 (Q38) |
| R12 | `loc_start` = LOC export start; `loc_end` = LOC export end; `loc_delta = loc_end − loc_start`; chia theo ngôn ngữ (tên lexer Pygments) | §8.1 |
| R13 | LOC luôn đếm trên chính bản export (khớp file người dùng tải về) → đếm từ nội dung entry của zip | §3.4, PLAN D36 |
| R14 | Chỉ đếm file source không quá `max_file_size_kb`; file source quá lớn ở `full` không đếm, không cảnh báo lại | §6.3, §9, D13, D40 (N4) |
| R15 | `added_code` / `deleted_code` (theo `classify_lines` tại C_END / C_START), `net_code = added_code − deleted_code` cho mỗi user | §8.2 |
| R16 | `commits` = số commit của user trong kỳ, không tính merge | §8.2, §16, D15 |
| R17 | `files_changed` = số file source user đã thay đổi | §8.2, D40 (N7) |
| R18 | Kiểm tra chéo: `loc_start + Σ net_code (user được tính) ≈ loc_end`; lệch > 0.5 % → cảnh báo kèm giá trị hai bên | §8.3, §7.5, D38 |
| R19 | Chi tiết theo file: đường dẫn, ngôn ngữ, LOC start, LOC end, chênh lệch | §10.3 |
| R20 | Code ròng theo tuần, mỗi user (biểu đồ §10.3, sheet `Theo_tuan` §12): tuần ISO theo author date, múi giờ đã chọn | §10.3, §12, D35 |
| R21 | Dòng **Tổng** của bảng theo user | §10.3, D40 (N18) |
| R22 | Tái lập: mọi danh sách sắp xếp ổn định | §15 |

## 3. Giao diện
```python
class WarningKind(StrEnum):
    # M1 — bỏ qua file khi đếm / export
    TOO_LARGE = "too_large"
    BINARY = "binary"
    UNKNOWN_LANGUAGE = "unknown_language"
    READ_ERROR = "read_error"
    # M4 — export, gán tác giả, dựng export end theo user (mục 5.2)
    UNSAFE_PATH = "unsafe_path"
    RENAME_LIMIT = "rename_limit"
    RENAME_UNRESOLVED = "rename_unresolved"
    UNATTRIBUTED = "unattributed"
    MOVED_LINES = "moved_lines"
    MULTI_USER_HUNK = "multi_user_hunk"
    SEQUENTIAL_EDIT = "sequential_edit"
    MISSING_EOL = "missing_eol"
    PATH_CONFLICT = "path_conflict"
    # M5 — kiểm tra chéo, định danh, tên file trên Windows (mục 5.2)
    CROSS_CHECK = "cross_check"
    IDENTITY = "identity"
    WINDOWS_PATH = "windows_path"

@dataclass(frozen=True)
class LocWarning:
    kind: WarningKind
    path: str           # POSIX tương đối; "" = cảnh báo cấp repo (vd. RENAME_LIMIT)
    message: str        # tiếng Việt

@dataclass(frozen=True)
class FileLoc:
    path: str           # POSIX tương đối với gốc
    language: str
    code_lines: int
    total_lines: int

@dataclass(frozen=True)
class LanguageLoc:
    language: str
    files: int
    code_lines: int

@dataclass
class CountResult:
    files: list[FileLoc]              # sắp xếp theo path
    warnings: list[LocWarning]        # sắp xếp theo (path, kind)
    @property
    def total_code(self) -> int: ...
    def by_language(self) -> list[LanguageLoc]:
        """Sắp xếp code_lines giảm dần, rồi tên ngôn ngữ tăng dần."""

def decode_text(data: bytes) -> str:
    """UTF-8 (bỏ BOM) → nếu lỗi thì latin-1."""

def count_directory(root: Path, filters: FilterConfig,
                    classifier: LineClassifier | None = None) -> CountResult:
    """Đếm LOC mọi file source dưới root."""
```

### 3.2 Bổ sung M5
`counter` **không import** `attribution`, `builder`, `identity`, `git_repo`, `snapshot` lúc chạy (các module đó import `counter`): kiểu của chúng chỉ import trong `if TYPE_CHECKING:` (file đã có `from __future__ import annotations`) — PLAN D37. Hàm chỉ đọc thuộc tính, nên test dùng được đối tượng thật hoặc đối tượng giả cùng thuộc tính.

```python
BlobReader = Callable[[Sequence[str]], Iterator[tuple[str, bytes]]]
# = GitRepo.read_blobs: generator (sha, data) theo thứ tự đầu vào, đóng sớm được

@dataclass(frozen=True)
class ContentFile:
    path: str               # POSIX, đường dẫn trong zip
    language: str | None    # None = không phải source (không đếm)
    data: bytes             # nội dung nguyên byte như trong zip
    cache_key: str          # blob sha hoặc content_sha1(data) (khóa cache §6.3)

def is_countable(language: str | None, size: int, filters: FilterConfig) -> bool:
    """File được đếm LOC: là source (language khác None) và size <= max_file_size_kb*1024."""

def count_files(files: Iterable[ContentFile], filters: FilterConfig,
                classifier: LineClassifier | None = None) -> CountResult:
    """Đếm LOC của một bản export từ nội dung entry (D36); không phát cảnh báo."""

def count_export(export: UserExport, read_blobs: BlobReader, filters: FilterConfig,
                 classifier: LineClassifier | None = None) -> CountResult:
    """Đọc nội dung file source của export (blob hoặc data) rồi gọi count_files."""

@dataclass(frozen=True)
class LanguageRow:
    language: str
    files_start: int
    loc_start: int
    files_end: int
    loc_end: int
    @property
    def delta(self) -> int: ...          # loc_end - loc_start

def compare_languages(start: CountResult, end: CountResult) -> list[LanguageRow]:
    """Hợp ngôn ngữ của hai phía; sắp (-loc_end, -loc_start, language)."""

@dataclass(frozen=True)
class FileRow:
    path: str                  # đường dẫn trong export end; file chỉ có ở start → đường dẫn start
    renamed_from: str | None   # đường dẫn ở start khi file được đổi tên trong export end
    language: str              # phía end, không có thì phía start
    loc_start: int
    loc_end: int
    @property
    def delta(self) -> int: ...

def rename_map(attribution: PeriodAttribution, end_paths: Collection[str]) -> dict[str, str]:
    """{đường dẫn mới: đường dẫn cũ} cho cặp đổi tên có tên mới nằm trong export end."""

def compare_files(start: CountResult, end: CountResult,
                  renames: Mapping[str, str] | None = None) -> list[FileRow]:
    """Ghép file start ↔ end theo đường dẫn (và theo renames); sắp theo path."""

@dataclass(frozen=True)
class UserMetrics:
    account: str               # "" ở dòng Tổng
    is_bot: bool
    commits: int               # không tính merge
    added_lines: int
    deleted_lines: int
    added_code: int
    deleted_code: int
    files: tuple[str, ...]     # file source đã thay đổi, sắp tăng dần
    @property
    def net_code(self) -> int: ...       # added_code - deleted_code
    @property
    def files_changed(self) -> int: ...  # len(files)

def user_metrics(attribution: PeriodAttribution, summaries: Sequence[UserSummary],
                 accounts: Collection[str]) -> list[UserMetrics]:
    """Số liệu §8.2 cho từng account; sắp (-commits, account)."""

def total_metrics(rows: Sequence[UserMetrics]) -> UserMetrics:
    """Dòng Tổng: cộng các cột số, files = hợp các tập file (không đếm trùng)."""

@dataclass(frozen=True)
class WeekRow:
    week: str                  # "YYYY-Www" (năm ISO), vd. "2026-W02"
    week_start: date           # thứ Hai của tuần ISO
    account: str
    commits: int
    added_code: int
    deleted_code: int
    @property
    def net_code(self) -> int: ...

def iso_week(moment: datetime, timezone: str) -> tuple[str, date]:
    """(nhãn tuần ISO, thứ Hai) của thời điểm aware, quy về múi giờ đã chọn."""

def weekly_metrics(attribution: PeriodAttribution, commits: Sequence[LogCommit],
                   accounts: Collection[str], timezone: str) -> list[WeekRow]:
    """Code ròng theo tuần ISO (author date) cho từng account (D35); sắp (week_start, account)."""

# ----- M8 (D43): theo PR -----
NO_PR_LABEL = "(Không thuộc PR)"

@dataclass(frozen=True)
class PrRef:
    number: int
    title: str
    merge_sha: str             # merge commit "Merge pull request #N" hoặc commit squash "(#N)"
    merged_at: datetime        # author date của merge_sha, aware

@dataclass(frozen=True)
class PrRow:
    pr: int | None             # None = nhóm "Không thuộc PR"
    title: str                 # "" khi pr là None
    merge_sha: str             # "" khi pr là None
    merged_at: datetime | None # quy về múi giờ đã chọn; None khi pr là None
    account: str
    commits: int               # commit không phải merge
    added_code: int
    deleted_code: int
    @property
    def net_code(self) -> int: ...

def pr_membership(commits: Sequence[LogCommit]) -> dict[str, PrRef]:
    """commit sha → PR chứa nó (chỉ commit thuộc một PR; commit khác không có khóa)."""

def pr_metrics(attribution: PeriodAttribution, commits: Sequence[LogCommit],
               accounts: Collection[str], timezone: str) -> list[PrRow]:
    """LOC theo (PR, account) (D43); sắp (PR tăng dần, account), nhóm không thuộc PR cuối."""

CROSS_CHECK_THRESHOLD_PERCENT = 0.5

@dataclass(frozen=True)
class CrossCheck:
    loc_start: int
    sum_net_code: int
    loc_end: int
    diff_percent: float        # đã làm tròn 3 chữ số
    threshold_percent: float
    ok: bool                   # độ lệch chưa làm tròn <= ngưỡng
    @property
    def expected_loc_end(self) -> int: ...   # loc_start + sum_net_code

def cross_check(loc_start: int, loc_end: int, net_codes: Iterable[int],
                threshold_percent: float = CROSS_CHECK_THRESHOLD_PERCENT) -> CrossCheck:
    """Kiểm tra chéo §8.3 (D38)."""

def cross_check_warning(check: CrossCheck, tag: str) -> LocWarning | None:
    """Cảnh báo CROSS_CHECK (path "") khi check.ok là False; ngược lại None."""
```

`weekly_metrics` cần thống kê dòng theo **commit** — trường `commit_stats` do bản cập nhật M5 của spec `attribution` bổ sung (D35, giả định A8):
```python
@dataclass(frozen=True)
class CommitLineStats:          # trong attribution.py
    sha: str
    account: str
    added_lines: int
    deleted_lines: int
    added_code: int
    deleted_code: int
# PeriodAttribution.commit_stats: tuple[CommitLineStats, ...]   # sắp theo sha
```

## 4. Dữ liệu vào / ra
- `root`: thư mục tồn tại. `classifier` None → tạo `LineClassifier(filters.count_docstrings)`.
- `path` trong kết quả: tương đối với `root`, phân tách `/`.

M5:
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `filters.max_file_size_kb` | int | 1024 | ngưỡng của `is_countable` | §9 |
| `filters.count_docstrings` | bool | False | chỉ dùng khi `classifier` None | §3.4, §9 |
| `classifier` | LineClassifier \| None | None → `LineClassifier(filters.count_docstrings)` | `pipeline` truyền **một** classifier chung cho attribution và mọi lần đếm (cache theo blob sha) | §6.3 |
| `accounts` | Collection[str] | — | tập account được tính (pipeline chọn: tất cả / bỏ bot / user chọn) | §3.3, D21 |
| `timezone` | str | (`Period.timezone`, mặc định `Asia/Bangkok`) | tên IANA hợp lệ (đã kiểm ở `make_period`) | §3.1, D35 |
| `threshold_percent` | float | 0.5 | > 0 | §8.3 |

## 5. Luồng xử lý
### 5.1 `count_directory(root, filters, classifier)`
1. `root` không tồn tại hoặc không phải thư mục → `LocCounterError`.
2. Duyệt cây bằng `os.walk(root, followlinks=False, onerror=...)`; tại mỗi cấp: sắp xếp tên thư mục và file; **cắt** thư mục có `is_dir_excluded(name)`, thư mục symlink và **junction NTFS** (không đi vào). Thư mục con không liệt kê được (`onerror`) → cảnh báo `READ_ERROR` với `path` là đường dẫn tương đối của thư mục.
3. Với mỗi file (bỏ qua symlink):
   1. `rel = đường dẫn POSIX tương đối`.
   2. `check_path(rel, filters)` khác None → bỏ qua **không** cảnh báo (loại theo cấu hình).
   3. `language = detect_language(rel, filters.exclude_languages)`:
      - `None` và lexer thật sự không tồn tại → ghi nhận ứng viên `UNKNOWN_LANGUAGE` (chỉ cảnh báo nếu file không binary, xem bước 5).
      - `None` vì thuộc `exclude_languages` → bỏ qua không cảnh báo.
   4. `size = stat().st_size`; `size > max_file_size_kb*1024` → cảnh báo `TOO_LARGE`, bỏ qua.
   5. Đọc bytes (lỗi OS → cảnh báo `READ_ERROR`, bỏ qua). `is_binary(data)` → cảnh báo `BINARY`, bỏ qua. Nếu là ứng viên `UNKNOWN_LANGUAGE` → cảnh báo `UNKNOWN_LANGUAGE`, bỏ qua.
   6. `text = decode_text(data)`; `is_code = classifier.classify(text, rel, content_sha1(data))`.
   7. Thêm `FileLoc(rel, language, sum(is_code), len(is_code))`.
4. Sắp xếp `files` theo `path`, `warnings` theo `(path, kind)`; trả `CountResult`.

`decode_text(data)`: `data.decode("utf-8-sig")`; `UnicodeDecodeError` → `data.decode("latin-1")`.

### 5.2 Danh mục loại cảnh báo (M4)
`WarningKind` là danh mục **duy nhất**; module khác chỉ dùng lại, không tự định nghĩa loại cảnh báo. Giá trị chuỗi (cột "Giá trị") là định danh ổn định, sẽ ghi vào cột loại của `warnings.csv` (M5) — không đổi sau khi duyệt. Thông báo luôn tiếng Việt; nội dung chi tiết (khoảng dòng, account…) do spec của module phát ra quy định, `counter` không tạo các cảnh báo này.

| Loại | Giá trị | Ý nghĩa | Phát ra bởi | `path` | Nguồn |
|---|---|---|---|---|---|
| `TOO_LARGE`, `BINARY`, `UNKNOWN_LANGUAGE`, `READ_ERROR` | (như M1) | Bỏ qua file khi đếm LOC (mục 5, 7) | `counter`, `snapshot` | đường dẫn file | §6.3, §7.5, §15 |
| `UNSAFE_PATH` | `unsafe_path` | File bị bỏ khỏi export vì đường dẫn không an toàn (`snapshot.is_unsafe_path`) | `snapshot.screen_entry` (dùng cho export start/end và `builder` qua `select_content`) | đường dẫn gốc trong cây git (có thể chứa `..`, `:`, `\`) | PLAN F8, snapshot A5 |
| `RENAME_LIMIT` | `rename_limit` | Git bỏ nhận diện rename do quá nhiều file (`TreeDiff.rename_limit_hit`) → file đổi tên có thể bị tính là xóa + thêm | `attribution` | `""` (cấp repo) | §7.4, PLAN D27 (Q24) |
| `RENAME_UNRESOLVED` | `rename_unresolved` | Không xác định được người đổi tên → export dùng tên cũ | `attribution` | đường dẫn tại C_END (tên mới) | §7.4, PLAN D25 |
| `UNATTRIBUTED` | `unattributed` | Dòng thêm / dòng xóa trong hunk không xác định được tác giả → dòng thêm bị bỏ, dòng cũ được giữ | `attribution` | đường dẫn tại C_END; file bị xóa → tại C_START | §7.2, PLAN D23, D24 |
| `MOVED_LINES` | `moved_lines` | Dòng bị dời (trong file / sang file khác) được gán cho người dời theo blame lần hai | `attribution` | đường dẫn tại C_END | §7.2, PLAN D22 |
| `MULTI_USER_HUNK` | `multi_user_hunk` | Một hunk có dòng của ≥ 2 account (dòng cũ bị xóa + dòng mới) | `attribution` | đường dẫn tại C_END; file bị xóa → tại C_START | §7.5, PLAN D27 (Q32) |
| `SEQUENTIAL_EDIT` | `sequential_edit` | Dòng bị nhiều user sửa liên tiếp trong kỳ, chỉ gán cho người sửa cuối (heuristic M4) | `attribution` | đường dẫn tại C_END | §7.5, §16, PLAN D26 |
| `MISSING_EOL` | `missing_eol` | Dòng thiếu xuống dòng nằm giữa file đã dựng → được thêm EOL chiếm đa số của file | `builder` | tên file trong export end theo user | §7.3, §15, PLAN D27 (Q28) |
| `PATH_CONFLICT` | `path_conflict` | Hai đường dẫn trong cùng một export xung đột khi giải nén: một là file, một là thư mục cùng tên (`x` và `x/z.py`), hoặc chỉ khác hoa thường — cả hai vẫn được giữ trong zip | `builder` | đường dẫn của từng file liên quan | PLAN D32 (Q38), F9 |

| `CROSS_CHECK` | `cross_check` | `loc_start + Σ net_code` lệch `loc_end` quá 0.5 % (mục 5.9) | `counter.cross_check_warning` (pipeline gọi cho export chính và từng zip riêng) | `""` | §8.3, §7.5, D38 |
| `IDENTITY` | `identity` | Cảnh báo khi xác định account (GitHub API lỗi / hết quota — `UsersResult.warnings`) | `pipeline` (chuyển chuỗi thành `LocWarning`) | `""` | §3.5, D18, D39 |
| `WINDOWS_PATH` | `windows_path` | Đường dẫn hợp lệ trong git nhưng không giải nén đúng trên Windows (tên thiết bị `CON`, `NUL.py`…; `.`/khoảng trắng cuối; ký tự `<>"\|?*`) — file vẫn được export và đếm | `builder` / `pipeline` (spec `builder` cập nhật M5) | đường dẫn file | F9, D39 |

### 5.3 `is_countable`, `count_files` (M5, D36)
`is_countable(language, size, filters)` = `language is not None and size <= filters.max_file_size_kb * 1024` (cùng ngưỡng với bước 5.1.3.4).

`count_files(files, filters, classifier)`:
1. `classifier` None → `LineClassifier(filters.count_docstrings)`.
2. Với mỗi `f` theo thứ tự đầu vào: đường dẫn đã gặp → `ValueError("ContentFile trùng đường dẫn: …")` (lỗi lập trình, như `write_entries`). `not is_countable(f.language, len(f.data), filters)` → bỏ qua, **không** cảnh báo (cảnh báo bỏ file đã phát khi lập plan / dựng export; D40-N4).
3. `is_code = classifier.classify(decode_text(f.data), f.path, f.cache_key)`; thêm `FileLoc(f.path, f.language, sum(is_code), len(is_code))`.
4. `files` sắp theo `path`; `warnings = []`. Log DEBUG số file.

Không kiểm lại binary / bộ lọc đường dẫn: `language` đã là kết quả của `snapshot.screen_entry` + `finish_entry` hoặc `select_content` (binary / không nhận diện → `None`). Nhờ vậy kết quả bằng `count_directory` trên thư mục giải nén zip với cùng `filters` (TC-27), trừ khi giải nén làm hỏng tên (F9).

### 5.4 `count_export(export, read_blobs, filters, classifier)`
1. `wanted` = các `BuiltFile` của `export.files` có `language is not None` (giữ thứ tự `export.files`).
2. `shas` = `blob_sha` khác None của `wanted`, khử trùng giữ thứ tự (`dict.fromkeys`). Có `shas` → đọc **một lần**: `it = read_blobs(shas)`; `blobs = dict(it)` trong `try`, `finally` gọi `it.close()` nếu có (đóng generator cả khi lỗi — F3; iterator thường không có `close()` vẫn dùng được). Không có `shas` → không gọi `read_blobs`. Thiếu sha trong kết quả → `KeyError` lan ra (lỗi lập trình / repo hỏng).
3. `ContentFile(f.path, f.language, f.data if f.data is not None else blobs[f.blob_sha], f.cache_key)` → `count_files`.
4. File không phải source không được đọc. File source quá lớn (`full`) vẫn được đọc rồi bị `count_files` bỏ (`BuiltFile` không mang kích thước; tối ưu ở M7).

### 5.5 `compare_languages(start, end)`
1. `s = {l.language: l for l in start.by_language()}`, `e` tương tự; ngôn ngữ = hợp hai tập.
2. Mỗi ngôn ngữ → `LanguageRow(lang, s.files|0, s.code_lines|0, e.files|0, e.code_lines|0)`.
3. Sắp `(-loc_end, -loc_start, language)`. Bất biến: `Σ loc_start == start.total_code`, `Σ loc_end == end.total_code`.

### 5.6 `rename_map`, `compare_files` (§10.3, D40-N21)
`rename_map(attribution, end_paths)`: mỗi `f` của `attribution.files` có `f.entry.status` bắt đầu bằng `"R"`, `old_path != new_path`, `new_path in end_paths` → `{new_path: old_path}`. (Export dùng tên cũ khi người đổi tên không được chọn — D25 — nên tên mới không có trong export và không sinh cặp.)

`compare_files(start, end, renames)`:
1. `sb = {f.path: f for f in start.files}`, `eb` tương tự; `used: set[str] = set()`; `renames` None → `{}`.
2. Mỗi `p` của `eb` theo path tăng dần: `src = renames.get(p)`; nếu `p not in sb` và `src in sb` và `src not in eb` → ghép `sb[src]`, `renamed_from = src`, `used.add(src)`; ngược lại nếu `p in sb` → ghép `sb[p]`, `used.add(p)`; ngược lại không có phía start (`loc_start = 0`).
3. Mỗi `q` của `sb` không thuộc `used` → `FileRow(q, None, sb[q].language, sb[q].code_lines, 0)`.
4. `language` = phía end nếu có, không thì phía start. Sắp kết quả theo `path`. Bất biến: `Σ loc_start == start.total_code`, `Σ loc_end == end.total_code`.

### 5.7 `user_metrics`, `total_metrics` (§8.2, D40-N7, N18)
`user_metrics(attribution, summaries, accounts)`:
1. `by_summary = {u.account: u for u in summaries}`; `stats = {u.account: u for u in attribution.users}`.
2. Với mỗi `a` trong `accounts` (khử trùng):
   - `commits = by_summary[a].commits` (không tính merge, D15); `is_bot = by_summary[a].is_bot`. `a` không có trong `summaries` → `commits = 0`, `is_bot = False`, log WARNING `Account %s không có trong danh sách user của kỳ` (người gọi dùng resolver khác).
   - `added_lines, deleted_lines, added_code, deleted_code` lấy từ `stats[a]` (không có → 0). Không phân loại lại.
   - `files` = các `f.path` (khử trùng, sắp tăng dần) của `attribution.files` thỏa **cả hai**:
     a. `f.granularity in ("lines", "last")` và (`a in f.added_by.values()` hoặc `a in f.deleted_by.values()` hoặc `f.renamed_by == a`);
     b. ít nhất một phía là source được đếm: `side is not None and side.keep and side.language is not None and not side.too_large`.
     (Mode `last_commit`: `"last"` có `added_by` / `deleted_by` nên tính như `"lines"`; file binary `"last"` không có dòng nào được gán nên không tính.) File `whole` / `skip` (binary, quá lớn, symlink…) không tính; rename thuần (100 %) = 1 file; user chỉ đổi khoảng trắng (không có dòng nào được gán) không tính.
3. Sắp `(-commits, account)`.

`total_metrics(rows)`: `UserMetrics("", False, Σcommits, Σadded_lines, Σdeleted_lines, Σadded_code, Σdeleted_code, files = sorted(hợp các rows.files))` — `files_changed` của dòng Tổng là số file **khác nhau** (hai user sửa cùng file tính 1). `rows` rỗng → mọi số 0.

### 5.8 `iso_week`, `weekly_metrics` (D35)
`iso_week(moment, timezone)`: `local = moment.astimezone(ZoneInfo(timezone))`; `y, w, _ = local.isocalendar()`; trả `(f"{y}-W{w:02d}", date.fromisocalendar(y, w, 1))`. Năm là **năm ISO** (2025-12-29 → `2026-W01`).

`weekly_metrics(attribution, commits, accounts, timezone)`:
1. `by_sha = {c.sha: c for c in commits}`; `acc = attribution.commit_accounts`.
2. Đếm commit: mỗi `c` trong `commits` **không phải merge** có `acc.get(c.sha) in accounts` → ô `(tuần của c.author_date, account)`: `commits += 1`.
3. Dòng code: mỗi `s` trong `attribution.commit_stats` có `s.account in accounts`: `c = by_sha.get(s.sha)`; không có → log WARNING, bỏ qua; ngược lại ô `(tuần của c.author_date, s.account)`: `added_code += s.added_code`, `deleted_code += s.deleted_code`. Merge commit có dòng giải quyết xung đột (§16) góp dòng code nhưng không góp `commits`.
4. Chỉ giữ ô có `commits`, `added_code` hoặc `deleted_code` khác 0 (bảng dạng dài, không điền 0). Tuần ngoài kỳ (commit nhánh tách trước start, merge trong kỳ — author date cũ) vẫn giữ.
5. Sắp `(week_start, account)`. Bất biến: với mỗi account, Σ theo tuần của `added_code` / `deleted_code` = `UserMetrics.added_code` / `deleted_code` (TC-37).

### 5.9 `cross_check`, `cross_check_warning` (§8.3, D38)
`cross_check(loc_start, loc_end, net_codes, threshold)`:
1. `sum_net = sum(net_codes)`; `expected = loc_start + sum_net`.
2. `raw = abs(expected - loc_end) / loc_end * 100` khi `loc_end > 0`; `loc_end == 0` → `0.0` nếu `expected == 0`, ngược lại `100.0`.
3. `CrossCheck(loc_start, sum_net, loc_end, round(raw, 3), threshold, ok = raw <= threshold)` — so trên giá trị **chính xác** (`Fraction(abs(expected − loc_end) × 100, loc_end) <= Fraction(str(threshold))`) để lệch đúng bằng ngưỡng luôn đạt (A11) với mọi ngưỡng.

`net_codes` do người gọi chọn: "Tất cả user" → `net_code` của mọi account được tính (đã bỏ bot khi `--exclude-bots`, D21); chọn user → của các user chọn (§8.3).

`cross_check_warning(check, tag)`: `check.ok` → `None`; ngược lại `LocWarning(CROSS_CHECK, "", f"Kiểm tra chéo ({tag}): loc_start {loc_start} + tổng code ròng {sum_net_code:+d} = {expected_loc_end}, loc_end = {loc_end}, lệch {diff_percent:.3f}% (ngưỡng {threshold_percent}%)")`.

### 5.10 `pr_membership`, `pr_metrics` (M8, D43)
Chỉ dùng dữ liệu đã có (`commits` = `log_commits`, `attribution.commit_stats`); không gọi git. Tập `commits` là đồ thị của kỳ: cha nằm ngoài `commits` (tổ tiên của C_START) bị bỏ qua.

`pr_membership(commits)`:
1. Nhận diện PR:
   - **Merge PR:** commit có ≥ 2 parent và `subject` khớp `^Merge pull request #(\d+)\b` → PR `N`, `title = body_title` (rỗng → phần sau `from ` của subject, vẫn rỗng → `subject`).
   - **Squash:** commit (bất kể số parent) có `subject` khớp `\(#(\d+)\)\s*$` và **không** phải merge PR → PR `N`, `title = subject` bỏ đuôi ` (#N)` và `strip()`. `Revert "… (#12)"` không khớp (kết thúc bằng `")`).
2. Thành viên của merge PR `M` = `anc(M.parents[1]) \ anc(M.parents[0])` ∪ `{M}`, trong đó `anc(x)` = x và mọi tổ tiên của x **nằm trong `commits`**. Cài đặt: duyệt đồ thị theo thứ tự tô-pô (cha trước con; không dựa vào thứ tự `git log`), `anc` là bitset `int` theo chỉ số commit. Merge ≥ 3 parent: lấy mọi parent từ thứ hai trở đi.
3. Gán: duyệt merge PR theo `(số thành viên, merge_sha)` tăng dần; mỗi thành viên **chưa được gán** nhận `PrRef(N, title, M.sha, M.author_date)` — PR lồng nhau: PR trong cùng nhất thắng (Q50). Sau đó mỗi commit squash **chưa được gán** nhận `PrRef` của chính nó. Commit còn lại không có khóa.
4. Hai PR trùng số `N` (hiếm: merge lại sau revert, repo gộp từ fork): `pr_metrics` gộp theo `N`, lấy `title`, `merge_sha`, `merged_at` của PR có `(merged_at, merge_sha)` nhỏ nhất.

`pr_metrics(attribution, commits, accounts, timezone)`:
1. `membership = pr_membership(commits)`; khóa PR của một sha = `ref.number` nếu có, ngược lại `None`.
2. Đếm commit: mỗi `c` trong `commits` **không phải merge** có `attribution.commit_accounts.get(c.sha) in accounts` → ô `(PR của c.sha, account)`: `commits += 1`.
3. Dòng code: mỗi `s` trong `attribution.commit_stats` có `s.account in accounts` → ô `(PR của s.sha, s.account)`: `added_code += s.added_code`, `deleted_code += s.deleted_code`. `s.sha` không có trong `commits` → vào nhóm không thuộc PR (khác `weekly_metrics`: ở đây không cần ngày nên không bỏ dòng, để giữ bất biến Σ). Dòng giải quyết xung đột của merge PR `M` được tính cho PR của `M`.
4. Chỉ giữ ô có `commits`, `added_code` hoặc `deleted_code` khác 0. `merged_at` = `ref.merged_at.astimezone(ZoneInfo(timezone))`.
5. Sắp: PR có số tăng dần (theo account tăng dần), nhóm `pr is None` cuối (theo account). Bất biến: với mỗi account, Σ `added_code` / `deleted_code` / `commits` trên mọi dòng = `UserMetrics` tương ứng (TC-52).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Thứ tự kiểm tra: đường dẫn → ngôn ngữ (theo tên) → kích thước → binary → (cảnh báo ngôn ngữ). Nhờ vậy ảnh `.png` báo là `BINARY`, còn `LICENSE` báo `UNKNOWN_LANGUAGE`.
- File thuộc `exclude_languages` (`.txt`, `.md`, `.rst`) không đếm và không cảnh báo (cấu hình chủ động).
- Binary nhận diện bằng byte NUL trong 8000 byte đầu (`filters.is_binary`). Vì latin-1 giải mã được mọi chuỗi byte, nhánh "giải mã lỗi → binary" của §15 được thực hiện bằng kiểm tra NUL này.
- BOM UTF-8 bị bỏ trước khi phân loại (tránh token lỗi ở dòng 1).
- File 0 byte có lexer → `FileLoc(code_lines=0, total_lines=0)` vẫn được liệt kê.
- Symlink (file hoặc thư mục) không được theo.
- Danh sách cảnh báo luôn sắp theo `(path, kind)`; `kind` là `StrEnum` nên so sánh theo **giá trị chuỗi**, cảnh báo cấp repo (`path == ""`) đứng đầu. Thêm loại mới không làm đổi thứ tự giữa các loại M1 với nhau.
- Thêm thành viên vào `WarningKind` không đổi giá trị chuỗi của các loại M1 (tương thích ngược với `snapshot` và test hiện có).

M5:
- **Đếm từ nội dung, không giải nén (D36):** hai file chỉ khác hoa thường (`A.py`, `a.py`) đều được đếm (giải nén trên Windows chỉ còn một — F9).
- **File source quá lớn ở `full`:** có trong zip, không đếm LOC, không cảnh báo lại (TOO_LARGE đã phát khi lập plan).
- **C_START rỗng:** export start rỗng → `CountResult()`; `compare_files` chỉ có phía end; `loc_start = 0`.
- **Chọn user:** `loc_end` đếm trên export dựng bằng builder; `Σ net_code` chỉ của user chọn (§8.3).
- **Kiểm tra chéo lệch hệ thống** (không phải lỗi, D40-N6): file đổi tên non-source → source hoặc ra/vào thư mục bị loại, file ↔ symlink, binary ↔ text, vượt ngưỡng kích thước — §8.2 không gán các thay đổi này nên lệch là đúng định nghĩa; chỉ cảnh báo, README giải thích.
- **Dòng Tổng** không cộng dồn `files_changed` mà lấy số file khác nhau.
- **Merge commit:** không tính vào `commits` (D15) nhưng dòng giải quyết xung đột vẫn vào `added_code` / `weekly_metrics` của author merge (§16).
- **Bot:** `user_metrics` / `weekly_metrics` không tự lọc bot; tập `accounts` do pipeline quyết định (D21). `is_bot` chỉ để hiển thị.

## 7. Xử lý lỗi & thông báo
| Tình huống | Hành vi | Thông báo |
|---|---|---|
| root không tồn tại / không phải thư mục | `LocCounterError` | `Thư mục không tồn tại: <root>` |
| File quá lớn | cảnh báo TOO_LARGE | `Bỏ qua file lớn hơn <n> KB (<kích thước> KB)` |
| Binary | cảnh báo BINARY | `Bỏ qua file binary` |
| Không nhận diện ngôn ngữ | cảnh báo UNKNOWN_LANGUAGE | `Bỏ qua file không nhận diện được ngôn ngữ` |
| Lỗi đọc file | cảnh báo READ_ERROR | `Không đọc được file: <lỗi OS>` |
| Không liệt kê được thư mục con | cảnh báo READ_ERROR | `Không đọc được thư mục: <lỗi OS>` |
| (M5) `ContentFile` trùng đường dẫn | `ValueError` (lỗi lập trình) | `ContentFile trùng đường dẫn: <path>` |
| (M5) `read_blobs` lỗi / thiếu sha | `GitError` / `KeyError` lan ra; generator đã đóng | (từ `git_repo`) |
| (M5) Commit của `commit_stats` không có trong `commits` | bỏ qua trong `weekly_metrics` | — (log WARNING) |
| (M5) Account không có trong `summaries` | `commits = 0`, `is_bot = False` | — (log WARNING) |
| (M5) Kiểm tra chéo lệch > ngưỡng | `LocWarning(CROSS_CHECK)` | `Kiểm tra chéo (<tag>): loc_start … lệch …% (ngưỡng 0.5%)` |

## 8. Bảo mật, hiệu năng, tái lập
- Duyệt và kết quả sắp xếp ổn định, không phụ thuộc thứ tự của filesystem.
- Chỉ đọc file đã qua lọc đường dẫn và kích thước.
- Song song hóa để dành cho M7.
- (M5) Không gọi git trực tiếp; đọc blob qua `read_blobs` truyền vào, mỗi export một lần `cat-file --batch`. Dùng chung một `LineClassifier` → blob trùng giữa start, end và attribution chỉ phân loại một lần (khóa = blob sha). File source quá lớn ở `full` vẫn bị đọc (M7).
- (M5) Dữ liệu trả về không chứa token / thông tin xác thực (chỉ đường dẫn, account, số).
- (M5) Tái lập: mọi danh sách sắp theo khóa ở mục 5.3–5.8; `iso_week` dùng múi giờ tường minh (`zoneinfo`).

## 9. Test cases
| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-counter-01 | Đếm cơ bản đa ngôn ngữ | `a.py` (3 code), `b.js` (2 code), `sub/c.py` (1 code) | total 6; Python: 2 file / 4; JavaScript: 1 / 2; files sắp xếp `a.py, b.js, sub/c.py` | unit |
| TC-counter-02 | Thư mục loại bị cắt, glob, exclude_languages, không cảnh báo | `node_modules/x.js`, `a.min.js`, `README.md`, `notes.txt` | không đếm, `warnings == []` | unit |
| TC-counter-03 | Cảnh báo binary / unknown / too_large | `img.png` (có NUL), `LICENSE`, `big.py` > max | 3 cảnh báo đúng kind, không đếm | unit |
| TC-counter-04 | include_tests=false | `tests/test_a.py` | không đếm | unit |
| TC-counter-05 | Encoding | UTF-8 BOM `# c\nx=1`, latin-1 `x = "é"` (byte 0xE9), CRLF | BOM: 1 code (dòng 1 không bị tính); latin-1: 1; CRLF đếm đúng | unit |
| TC-counter-06 | File rỗng có lexer | `empty.py` | FileLoc 0/0 | unit |
| TC-counter-07 | by_language sắp xếp | ngôn ngữ cùng LOC | giảm dần LOC, cùng LOC theo tên | unit |
| TC-counter-08 | root không tồn tại | | `LocCounterError` | unit |
| TC-counter-09 | Cache theo nội dung | 2 file `.py` nội dung giống nhau | `cache_hits == 1` | unit |
| TC-counter-10 | Tái lập | đếm 2 lần | kết quả bằng nhau | unit |
| TC-counter-11 | Đường dẫn POSIX trên Windows | `sub/c.py` | `path == "sub/c.py"` | unit |
| TC-counter-12 | Lỗi đọc file | `read_bytes` ném `OSError` | cảnh báo `READ_ERROR`, không đếm | unit |
| TC-counter-13 | Symlink / junction không được theo | `link` → `real/` (junction trên Windows, symlink nơi khác), file symlink | chỉ đếm `real/...` một lần | unit |
| TC-counter-14 | Thư mục con không đọc được | `os.walk` gọi `onerror` cho `sub` | cảnh báo `READ_ERROR` path `sub` | unit |
| TC-counter-15 | Tổng dòng theo git (D8) | file `"a = 1\n\x0c\nb = 2\n"` | `total_lines == 3`, `code_lines == 2` | unit |
| TC-counter-16 | Danh mục `WarningKind` đủ và ổn định (M4, cập nhật M5) | `{k.name: k.value for k in WarningKind}` | bằng đúng 16 cặp của mục 3 (4 loại M1 giữ giá trị cũ + 9 loại M4 + `CROSS_CHECK`, `IDENTITY`, `WINDOWS_PATH`); giá trị không trùng, đều là chữ thường `[a-z_]+`; `WarningKind("unsafe_path") is WarningKind.UNSAFE_PATH` | unit |
| TC-counter-17 | Sắp xếp cảnh báo với loại M4 và `path` rỗng | `[LocWarning(MISSING_EOL,"b.py",…), LocWarning(RENAME_LIMIT,"",…), LocWarning(BINARY,"b.py",…), LocWarning(UNSAFE_PATH,"a:b.py",…)]` sắp theo khóa `(path, kind)` của mục 5.1 | `RENAME_LIMIT ""` → `UNSAFE_PATH a:b.py` → `BINARY b.py` → `MISSING_EOL b.py` | unit |

M5 — file `tests/test_counter_metrics.py` (repo §14 = fixture `section14_repo`, kỳ 2026-01-01..2026-01-31, `Asia/Bangkok`; account là email `alice@example.com`, `bob@example.com`):
| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-counter-18 | `count_files` cơ bản + sắp xếp | `ContentFile` `b.py` (2 code), `a.js` (1 code), `c.txt` language None | files `a.js, b.py`; total 3; `warnings == []`; `c.txt` không đếm | unit |
| TC-counter-19 | `is_countable`, file quá lớn ở `full` | `max_file_size_kb=1`; `big.py` 1025 byte language `Python`; `ok.py` đúng 1024 byte | `big.py` không đếm, không cảnh báo; `ok.py` được đếm (ngưỡng ≤) | unit |
| TC-counter-20 | Encoding / CRLF / BOM qua `count_files` | dữ liệu của TC-05 dạng bytes | kết quả bằng TC-05 | unit |
| TC-counter-21 | Trùng đường dẫn | hai `ContentFile` cùng `a.py` | `ValueError` | unit |
| TC-counter-22 | Hai file chỉ khác hoa thường đều được đếm (D36) | `A.py` (1 code), `a.py` (2 code) | 2 FileLoc, total 3 | unit |
| TC-counter-23 | Cache theo `cache_key` | 2 file khác tên, cùng `cache_key`, classifier chung | `cache_hits == 1` | unit |
| TC-counter-24 | `count_export`: đọc blob một lần, khử trùng, bỏ non-source | `UserExport` giả: 2 file cùng blob sha, 1 file có `data`, 1 file language None; `read_blobs` giả ghi lại lời gọi | gọi đúng 1 lần với 1 sha; file language None không được đọc; file `data` được đếm | unit |
| TC-counter-25 | `count_export` đóng generator khi lỗi | `read_blobs` giả là generator, ghi cờ trong `finally`, test giữ tham chiếu tới generator: (a) generator ném lỗi ở phần tử 2; (b) phần tử 2 hỏng → `dict()` của `count_export` ném lỗi khi generator còn treo | lỗi lan ra; cờ `finally` đã đặt (generator đã đóng) ở cả hai | unit |
| TC-counter-26 | Export rỗng (C_START rỗng) | `UserExport(None, "x", (), ())` | `CountResult()`; `read_blobs` không được gọi | unit |
| TC-counter-27 | **§14 — D36: đếm từ entry = đọc lại zip = `count_directory` trên thư mục giải nén** | export start, `all`, alice, bob, alice+bob (builder); zip ghi bằng `write_user_export` / `write_zip` | mỗi export: `count_export` = `count_files` trên entry đọc lại từ zip = `count_directory(thư mục giải nén)` (cùng `files`); total: start 10, all 20, alice 13, bob 17, alice+bob 20 | integration |
| TC-counter-28 | §14 — số liệu theo user | `attribute_period` + `summarize_users` cùng resolver; `accounts` = mọi user | alice: commits 2, added_code 5, deleted_code 2, net +3, `files == ("app.py",)`; bob: commits 2, 8 / 1 / +7, `files == ("app.py", "util.py")`; thứ tự alice, bob (cùng 2 commit → theo account) | integration |
| TC-counter-29 | §14 — kiểm tra chéo đạt cả 4 trường hợp | start 10; all (20, net mọi user), alice (13, +3), bob (17, +7), alice+bob (20, +10) | `ok`, `diff_percent == 0.0`, `cross_check_warning(...) is None` | integration |
| TC-counter-30 | `total_metrics` | rows của TC-28 | commits 4, added_code 13, deleted_code 3, net +10, `files_changed == 2` (không phải 3), `account == ""`; `total_metrics([])` toàn 0 | unit |
| TC-counter-31 | `files_changed`: loại `whole`/`skip` và non-source; rename thuần = 1; chỉ đổi khoảng trắng = 0 | `PeriodAttribution` giả, user U: (a) `lines` source, U có dòng thêm; (b) `whole` binary, `last_touch_by=U`; (c) `lines`, hai phía `language None` (`full`), U có dòng; (d) rename 100 % `renamed_by=U`, không hunk; (e) `lines` source, U không có dòng nào được gán; (f) `lines`, file bị xóa (`new is None`), phía cũ source, U xóa dòng; (g) `lines`, phía cũ source `too_large`, phía mới `None`, U xóa dòng | `files == (a, d, f)` (sắp theo path) | unit |
| TC-counter-32 | `compare_languages`: hợp ngôn ngữ, sắp xếp, bất biến tổng | start: Python 1 file / 10; end: Python 13, JavaScript 13, CSS 1 file rỗng (0) | thứ tự `Python (10→13)`, `JavaScript (0→13)`, `CSS (0→0)` (khóa `(-loc_end, -loc_start, language)`); `delta` 3 / 13 / 0; Σ cột = total hai phía | unit |
| TC-counter-33 | `compare_files` theo đường dẫn, file chỉ ở một phía | start `a.py` 3, `b.py` 2; end `a.py` 4, `c.py` 1 | `a.py 3→4`, `b.py 2→0`, `c.py 0→1`; sắp theo path; Σ khớp total | unit |
| TC-counter-34 | `rename_map` + `compare_files` với đổi tên | `make_repo`: start `old.py` (3 code); trong kỳ U đổi tên → `new.py` và thêm 1 dòng code; export `all` | `rename_map == {"new.py": "old.py"}`; đúng một dòng `FileRow("new.py", "old.py", "Python", 3, 4)`, không có dòng `old.py` | integration |
| TC-counter-35 | `rename_map` khi export dùng tên cũ | như TC-34; export của user V (không phải người đổi tên) | `rename_map(...) == {}`; dòng `FileRow("old.py", None, "Python", 3, 3)` | integration |
| TC-counter-36 | `iso_week`: múi giờ và năm ISO | `2026-01-05T05:00+07:00` với `Asia/Bangkok` và `UTC`; `2025-12-29T10:00+07:00` với `Asia/Bangkok` | `("2026-W02", 2026-01-05)`; `("2026-W01", 2025-12-29)`; `("2026-W01", 2025-12-29)` | unit |
| TC-counter-37 | §14 — `weekly_metrics` | mọi account | đúng 2 dòng tuần `2026-W02`: alice commits 2, 5 / 2 / +3; bob commits 2, 8 / 1 / +7; Σ theo tuần = `user_metrics` | integration |
| TC-counter-38 | `weekly_metrics`: nhiều tuần, merge, lọc account, ô 0 | dữ liệu giả: alice 2 commit ở 2 tuần có dòng code + 1 commit tuần 3 không có dòng code; merge commit của carol (không có commit thường) có `commit_stats` added_code 1; bob không thuộc `accounts` | alice có dòng ở 3 tuần (tuần 3: commits 1, 0 / 0); carol: commits 0, added_code 1; không có dòng bob; sắp `(week_start, account)` | unit |
| TC-counter-39 | `weekly_metrics` bỏ `commit_stats` không có commit | `commit_stats` chứa sha không có trong `commits` | dòng đó bị bỏ; log WARNING (`caplog`) | unit |
| TC-counter-40 | `cross_check`: công thức và ngưỡng | (10, 20, [3, 7]); (100, 1000, []); (995, 1000, []); (994, 1000, []); (300→ expected 301, loc_end 300); `loc_end = 0` với expected 0 và 5 | 0.0 ok; 90.0 không ok; 0.5 ok (không lớn hơn ngưỡng); 0.6 không ok; 0.333 (làm tròn 3 chữ số) ok; 0.0 ok / 100.0 không ok; `expected_loc_end` đúng | unit |
| TC-counter-41 | `cross_check_warning` | check không ok, tag `alice`; check ok | `LocWarning(CROSS_CHECK, "", …)` tiếng Việt chứa `alice`, loc_start, giá trị kỳ vọng, loc_end, phần trăm; check ok → None | unit |
| TC-counter-42 | Kiểm tra chéo lệch có cảnh báo (mandatory-tests D) | `make_repo`: start có `notes.txt` (5 dòng `x = 1`, bị loại theo `exclude_languages`); trong kỳ đổi tên 100 % → `notes.py`; export `all` | `loc_start 0`, `loc_end 5`, Σ net 0 → `ok False`, `diff_percent 100.0`; có cảnh báo `CROSS_CHECK` | integration |
| TC-counter-43 | Tái lập | gọi mọi hàm M5 hai lần trên §14 | kết quả bằng nhau | integration |
| TC-counter-45 | `pr_membership`: merge PR | đồ thị giả: `m1` ← `m2` (main), `f1` ← `f2` (nhánh từ `m1`), `M` = merge(`m2`, `f2`) subject `Merge pull request #7 from o/feat`, `body_title` `Thêm X`; cha gốc `p0` ngoài `commits` | `f1`, `f2`, `M` → `PrRef(7, "Thêm X", M, M.author_date)`; `m1`, `m2` không có khóa; `body_title` rỗng → title = `o/feat`; subject lạ + body rỗng → title = subject | unit |
| TC-counter-46 | `pr_membership`: squash | commit `Thêm login (#12)`; `Revert "Thêm login (#12)"`; `fix (#12) typo`; `Thêm (#5)  ` (khoảng trắng cuối); commit `Merge branch 'x'` 2 parent (không PR) | chỉ commit 1 và 4 có khóa (số 12 và 5); title `Thêm login` / `Thêm`; merge không PR và commit nhánh của nó không có khóa | unit |
| TC-counter-47 | PR lồng nhau và squash trong merge PR | PR #1: merge `M1` vào `B2`; PR #2: merge `M2` (main ← `B2`) nên tập thành viên chứa cả commit của #1; commit `c` trong nhánh #2 có subject `x (#9)` | commit/`M1` của #1 → PR 1 (nhỏ hơn thắng); commit riêng của B2 và `M2` → PR 2; `c` → PR 2 (merge PR thắng squash) | unit |
| TC-counter-48 | `pr_membership`: thứ tự `git log` không tô-pô | cùng đồ thị TC-45 nhưng danh sách `commits` đảo thứ tự (cha trước con) và xáo trộn | cùng kết quả TC-45; đồ thị hỏng có vòng (commit là cha của chính nó, hai commit là cha của nhau) → không treo, bỏ cạnh vòng | unit |
| TC-counter-49 | `pr_metrics`: nhóm theo (PR, account) | PR #7 (merge) gồm alice 2 commit, bob 1 commit, merge của carol có `commit_stats` added_code 1; PR #12 squash của alice; 1 commit trực tiếp của alice; mọi account | dòng đúng số commit/added/deleted từng (PR, account); carol: commits 0, added 1 ở PR 7; sắp PR 7, PR 12, rồi nhóm `None`; `merged_at` quy về `Asia/Bangkok` (offset +7); `net_code` đúng | unit |
| TC-counter-50 | `pr_metrics`: lọc account, ô 0, sha lạ | `accounts` = [alice]; commit alice không có dòng code (chỉ commit); `commit_stats` của sha không có trong `commits` | bob không có dòng; ô chỉ-có-commit vẫn có (commits 1, 0/0); sha lạ vào nhóm `None`; ô toàn 0 bị bỏ | unit |
| TC-counter-51 | `pr_metrics`: không có PR nào | chỉ commit thường | mọi dòng `pr is None`; bằng Σ theo account của `user_metrics` | unit |
| TC-counter-52 | Tích hợp repo git thật: bất biến Σ | repo: `base` (trước kỳ); main: alice thêm 3 dòng; nhánh `feat` (từ base): bob thêm `b.py` 4 dòng + alice thêm 2 dòng; merge `--no-ff` với message `Merge pull request #7 from o/feat\n\nThêm b.py` (author carol); commit alice `Sửa lỗi (#9)` thêm 1 dòng; commit trực tiếp bob thêm 1 dòng | `pr_metrics`: PR 7 gồm alice (1 commit, 2 dòng) + bob (1 commit, 4 dòng); PR 9 alice 1 dòng; nhóm `None` gồm alice 3 dòng + bob 1 dòng; với mỗi account Σ theo `pr_metrics` = `user_metrics` (commits, added, deleted) | integration |
| TC-counter-53 | Tái lập và hiệu năng đồ thị | gọi `pr_metrics` hai lần; đồ thị 3000 commit tuyến tính + 300 merge PR (giả) | kết quả bằng nhau; chạy dưới 5 giây | unit |
| TC-counter-44 | Không import module phụ thuộc lúc chạy (D37) | tiến trình con: `import loc_counter.counter` rồi liệt kê `sys.modules` | không có `loc_counter.attribution`, `.builder`, `.identity`, `.git_repo`, `.snapshot` | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | File không nhận diện ngôn ngữ (vd. `LICENSE`, `.csv`, `.log`) được ghi cảnh báo theo §7.5 — có thể nhiều cảnh báo trên repo lớn | Theo đúng §7.5 | Đã duyệt 2026-10-22 |
| A2 | File thuộc `exclude_languages` không ghi cảnh báo | Giả định | Đã duyệt 2026-10-22 |
| A3 | `LocWarning` giữ nguyên 3 trường (`kind`, `path`, `message`); chi tiết như khoảng dòng, account đưa vào `message`. Nếu `warnings.csv` (M5) cần cột riêng thì mở rộng ở M5 | Giả định | Đã duyệt 2026-10-23 |
| A4 | Tách `RENAME_UNRESOLVED` (người đổi tên, D25) khỏi `UNATTRIBUTED` (tác giả dòng, D24) để người dùng lọc được trong `warnings.csv`; `RENAME_LIMIT` dùng `path = ""` | Giả định | Đã duyệt 2026-10-23 |
| A5 | Quy ước `path` của từng loại theo bảng 5.2 (C_END trước, file bị xóa thì C_START; `MISSING_EOL` theo tên trong export) | Giả định | Đã duyệt 2026-10-23 |
| A6 | (M5) Đếm từ nội dung entry thay cho "thư mục export" (§3.4) | Theo PLAN D36 | Chốt theo khuyến nghị 2026-10-24 (*) |
| A7 | (M5) Đặt §8.1–§8.3 trong `counter.py`, chỉ import kiểu dưới `TYPE_CHECKING` | Theo PLAN D37 | Chốt theo khuyến nghị 2026-10-24 (*) |
| A8 | (M5) `weekly_metrics` cần dòng code theo **commit**. Thay vì đọc sha từng dòng rồi phân loại lại, bản cập nhật M5 của `attribution` cung cấp `commit_stats: tuple[CommitLineStats, …]` tính cùng chỗ với `UserLineStats` (cùng cờ code) — cụ thể hóa D35. Bất biến: Σ `commit_stats` theo account = `UserLineStats`. **`attribution` (cập nhật) phải lập trình trước** `weekly_metrics` (TC-37) | Giả định — spec `attribution` cập nhật phải có trường này | Chốt theo khuyến nghị 2026-10-24 (*) |
| A9 | (M5) "Phía là source được đếm" trong `files_changed` = `keep and language is not None and not too_large` của `SideInfo` (D40-N7) | Giả định | Chốt theo khuyến nghị 2026-10-24 (*) |
| A10 | (M5) Thứ tự bảng: ngôn ngữ `(-loc_end, -loc_start, language)`; user `(-commits, account)` (như `summarize_users`); tuần `(week_start, account)`; file theo `path` | Giả định (§10.3 không quy định) | Chốt theo khuyến nghị 2026-10-24 (*) |
| A11 | (M5) Lệch **đúng bằng** 0.5 % vẫn đạt (§8.3: "lệch > 0.5 %" mới cảnh báo); so trên giá trị chưa làm tròn | Theo §8.3, D38 | Chốt theo khuyến nghị 2026-10-24 (*) |

(*) Người dùng ủy quyền chốt theo khuyến nghị ("làm theo khuyến nghị không cần hỏi", M5; ủy quyền chung 2026-10-23); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-22 | Tạo mới (phạm vi M1: đếm thư mục) | M1 |
| 2026-10-22 | Cảnh báo thư mục không đọc được; bỏ qua junction NTFS; thêm TC-12..15. Người dùng duyệt sửa theo review | Review M1 (Minor counter.py:90, :93) |
| 2026-10-23 | M4: danh mục `WarningKind` (mục 5.2) thêm `UNSAFE_PATH`, `RENAME_LIMIT`, `RENAME_UNRESOLVED`, `UNATTRIBUTED`, `MOVED_LINES`, `MULTI_USER_HUNK`, `SEQUENTIAL_EDIT`, `MISSING_EOL`; `path = ""` cho cảnh báo cấp repo; R7–R10, TC-16, 17, A3–A5. `count_directory` không đổi. Trạng thái về `draft` | PLAN M4, F8 |
| 2026-10-23 | Người dùng duyệt bản M4 (A3–A5) → `approved` | Duyệt |
| 2026-10-23 | Test pass (TC-01..17) → `implemented` | /feature-test |
| 2026-10-23 | Review PASS (reviews/counter-snapshot-20261023.md) → `reviewed` | /feature-review |
| 2026-10-23 | M4 (D32): thêm `PATH_CONFLICT` (mục 3, 5.2), R11; TC-16 thành 13 loại. Chốt theo khuyến nghị (người dùng ủy quyền 2026-10-23) → `approved` | PLAN D32 (phân tích `builder`) |
| 2026-10-23 | Test pass (TC-16 cập nhật 13 loại) → `reviewed` (thay đổi một dòng enum, không đổi luồng xử lý; được kiểm tiếp trong review `builder`) | /feature-test |
| 2026-10-24 | M5: đếm từ nội dung entry (`ContentFile`, `is_countable`, `count_files`, `count_export` — D36); so sánh theo ngôn ngữ / file (`compare_languages`, `rename_map`, `compare_files`); §8.2 (`user_metrics`, `total_metrics`); theo tuần (`iso_week`, `weekly_metrics` — D35, A8); §8.3 (`cross_check`, `cross_check_warning` — D38); `WarningKind` thêm `CROSS_CHECK`, `IDENTITY`, `WINDOWS_PATH` (D39); R12–R22, TC-16 (16 loại), TC-18..44, A6–A11. `count_directory` không đổi. Trạng thái về `draft` | PLAN M5 |
| 2026-10-24 | Chốt A6–A11 theo khuyến nghị (người dùng ủy quyền) → `approved` | Duyệt (*) |
| 2026-10-24 | Test pass (TC-01..44; 50 test counter, toàn bộ 545) → `implemented` | /feature-test |
| 2026-10-24 | Sửa theo review (reviews/counter-20261024.md, PASS_WITH_NOTES) — làm rõ, không đổi kết quả trên luồng chính: 5.4 đóng iterator khi có `close()` (Minor 2); 5.9 so ngưỡng bằng phân số chính xác (Minor 3); TC-25 thêm ca lỗi phía người đọc (Minor 1); `user_metrics` gom file một lượt (Minor 5). Minor 4 (`iso_week` nhận datetime naive) giữ nguyên: đầu vào luôn aware (`LogCommit.author_date`). Chốt theo khuyến nghị (người dùng ủy quyền) → `reviewed` | /feature-review |
| 2026-10-30 | 5.7: `files` tính cả `granularity == "last"` (spec `attribution` 5.10); không đổi với mode `line` | Người dùng yêu cầu lựa chọn "Gán tác giả cho commit cuối cùng" (thuật toán đơn giản). Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | Yêu cầu mới |
| 2026-10-30 | Test pass (mode last_commit: TC-attribution-49/50, builder-32, pipeline-40, screen-input-25, cli-analyze-26; toàn bộ 779 test, ruff sạch, coverage 99 %) → `implemented`; chưa review | /feature-test |
| 2026-10-30 | M8 (D43): thêm `PrRef`, `PrRow`, `NO_PR_LABEL`, `pr_membership`, `pr_metrics` (mục 3, 5.10); TC-45..53. Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | PLAN M8, D43 |
