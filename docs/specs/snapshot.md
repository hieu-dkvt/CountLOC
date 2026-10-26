---
id: snapshot
title: Thời điểm, snapshot C_START / C_END và export (tất cả user)
type: module
milestone: M2, M3, M4
modules: [src/loc_counter/snapshot.py]
tests: [tests/test_snapshot.py]
spec_refs: ["3.1", "3.2", "3.3", "7.4", "9", "12", "15"]
depends_on: [config, filters, classifier, counter, git_repo]
status: reviewed
---

# Thời điểm, snapshot C_START / C_END và export (tất cả user)

## 1. Mục đích & phạm vi
Quy đổi khoảng thời gian người dùng nhập thành hai mốc có múi giờ, tìm C_START / C_END trên nhánh, chọn tập file cần export theo bộ lọc §9 và ghi file zip tái lập được. Dùng cho export start (§3.2) và export end khi chọn **tất cả user** (§3.3 = toàn bộ C_END).
M4 bổ sung (phục vụ `builder`): quy tắc lọc **từng file** của `plan_export` thành hàm công khai (`screen_entry`, `finish_entry`, `select_content`) để áp lên tên và nội dung file đã dựng; ghi zip từ danh sách entry tham chiếu blob **hoặc** nội dung bytes (`write_entries`); timestamp zip dùng chung (`zip_timestamp`). Hành vi của `plan_export`, `write_zip`, `export_snapshot` **không đổi**.
Ngoài phạm vi: dựng nội dung export end theo user, `user-tag` theo account (`builder`, M4), đếm LOC (`counter`, M5 đếm trên thư mục giải nén / nội dung export), thư mục kết quả `<out>/...` (`pipeline`, M5), khử trùng cảnh báo giữa export start / end / builder (`pipeline`, M5, A3).
M4 (cập nhật theo spec `counter` M4, PLAN F8): file bị bỏ vì đường dẫn không an toàn có cảnh báo `UNSAFE_PATH` (A5) — sửa duy nhất ở `screen_entry` (5.7) nên áp cho cả `plan_export` và `select_content`.

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Nhập ngày start/end bắt buộc, giờ tùy chọn; múi giờ mặc định `Asia/Bangkok` | §3.1 |
| R2 | Không nhập giờ: start `00:00:00`, end `23:59:59`. Nhập `HH:MM`: start `HH:MM:00`, end `HH:MM:59` | §3.1, PLAN D10 |
| R3 | `start < end`, sai → lỗi, không chạy | §3.1 |
| R4 | C_START / C_END = commit cuối theo first-parent có commit date ≤ mốc | §3.1 |
| R5 | Không có commit trước start → C_START rỗng (snapshot start không có file) | §3.1 |
| R6 | Không có commit trước end → lỗi "Không có dữ liệu trong khoảng thời gian" | §3.1 |
| R7 | Export start = source tại C_START sau bộ lọc §9; export end (tất cả user) = source tại C_END | §3.2, §3.3 |
| R8 | Bộ lọc §9 áp cho export; `source_only` / `full` theo PLAN D13 | §9, D13 |
| R9 | Tên zip `start_<YYYY-MM-DD>_<shortsha>.zip`, `end_<YYYY-MM-DD>_<user-tag>.zip`; ngày = ngày người dùng nhập; C_START rỗng → `start_<date>_empty.zip` | §12, PLAN D11 |
| R10 | Giữ nguyên kiểu xuống dòng (ghi blob nguyên byte) | §15 |
| R11 | Tái lập: entry sắp xếp, timestamp cố định | §15 |
| R12 | Cảnh báo file bỏ qua do quá lớn, binary, không nhận diện được ngôn ngữ | §7.5 |
| R13 | Bộ lọc §9 áp cho cả export end theo user, trên **tên được chọn** của file đổi tên | §9, §7.4, PLAN D25 |
| R14 | Export end theo user cũng giữ nguyên byte, tái lập (entry sắp xếp, timestamp cố định) | §15 |
| R15 | File bị bỏ vì đường dẫn không an toàn có cảnh báo `UNSAFE_PATH` (người dùng thấy trong `warnings.csv`) | PLAN F8, spec `counter` 5.2 |

## 3. Giao diện
```python
class SnapshotError(LocCounterError):
    """Lỗi nghiệp vụ về thời điểm / snapshot; thông báo tiếng Việt."""

@dataclass(frozen=True)
class Period:
    start: datetime          # aware, múi giờ đã chọn
    end: datetime            # aware
    timezone: str            # tên IANA
    start_date: date         # ngày người dùng nhập (dùng đặt tên file)
    end_date: date

def make_period(start_date: date, end_date: date,
                start_time: time | None = None, end_time: time | None = None,
                timezone: str = DEFAULT_TIMEZONE) -> Period: ...

@dataclass(frozen=True)
class Snapshots:
    branch: str
    c_start: CommitInfo | None
    c_end: CommitInfo

def find_snapshots(repo: GitRepo, branch: str, period: Period) -> Snapshots: ...

@dataclass(frozen=True)
class ExportFile:
    path: str                # POSIX
    blob_sha: str
    mode: str                # "100644" | "100755"
    size: int
    language: str | None     # None: file không phải source (chỉ có ở export_mode full)

@dataclass
class ExportPlan:
    commit_sha: str | None
    files: list[ExportFile]          # sắp xếp theo path
    warnings: list[LocWarning]       # sắp xếp theo (path, kind)

def plan_export(repo: GitRepo, commit_sha: str | None, filters: FilterConfig) -> ExportPlan: ...

def write_zip(repo: GitRepo, plan: ExportPlan, zip_path: Path,
              timestamp: datetime) -> Path: ...

def export_snapshot(repo: GitRepo, commit: CommitInfo | None, filters: FilterConfig,
                    zip_path: Path, timezone: str) -> ExportPlan:
    """plan_export + write_zip; timestamp = committer date của commit quy đổi về timezone."""

def is_unsafe_path(path: str) -> bool:
    """Đường dẫn POSIX trong cây git có thể ghi ra ngoài thư mục đích / vào .git khi giải nén."""

def safe_name(text: str) -> str:
    """Ký tự ngoài [A-Za-z0-9._-] → '_' (dùng cho tên nhánh, user-tag trong tên file)."""

def start_zip_name(period: Period, c_start: CommitInfo | None) -> str: ...
def end_zip_name(period: Period, user_tag: str) -> str: ...

# ----- M4 -----
@dataclass(frozen=True)
class Screening:
    """Kết quả lọc một file theo đường dẫn / mode / kích thước (chưa xem nội dung)."""
    keep: bool                      # False → bỏ (không cần đọc nội dung)
    language: str | None            # tên lexer sau exclude_languages
    unknown: bool                   # không có lexer
    excluded_language: bool         # có lexer nhưng thuộc exclude_languages
    too_large: bool                 # size > max_file_size_kb * 1024
    warnings: tuple[LocWarning, ...]

@dataclass(frozen=True)
class Selection:
    """Quyết định cuối cho một file."""
    keep: bool
    language: str | None            # None: không đếm LOC (non-source / binary / quá lớn không phải source)
    warnings: tuple[LocWarning, ...]

def screen_entry(path: str, mode: str, object_type: str, size: int,
                 filters: FilterConfig) -> Screening: ...

def finish_entry(path: str, screening: Screening, head: bytes,
                 filters: FilterConfig) -> Selection:
    """head = tối đa BINARY_SNIFF_BYTES byte đầu của nội dung; chỉ gọi khi screening.keep."""

def select_content(path: str, mode: str, data: bytes, filters: FilterConfig) -> Selection:
    """screen_entry (size = len(data)) + finish_entry cho nội dung đã có trong bộ nhớ."""

@dataclass(frozen=True)
class ZipEntry:
    path: str                       # POSIX
    mode: str                       # "100644" | "100755"
    blob_sha: str | None = None     # đúng một trong blob_sha / data khác None
    data: bytes | None = None

def write_entries(repo: GitRepo, entries: Sequence[ZipEntry], zip_path: Path,
                  timestamp: datetime) -> Path: ...

def zip_timestamp(commit: CommitInfo | None, timezone: str) -> datetime:
    """Committer date của commit theo timezone; None → 1980-01-01 00:00:00."""
```
`LocWarning`, `WarningKind` dùng lại từ `counter` (cùng thông báo).

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `start_date`, `end_date` | date | — | bắt buộc | §3.1 |
| `start_time`, `end_time` | time \| None | None | chỉ dùng giờ, phút (bỏ giây) | §3.1, D10 |
| `timezone` | str | `Asia/Bangkok` | tên IANA hợp lệ (`zoneinfo` + `tzdata`) | §3.1 |
| `branch` | str | — | nhánh tồn tại trong repo | §3.1 |
| `user_tag` | str | — | M2 chỉ dùng `all` | §12 |

## 5. Luồng xử lý

### 5.1 `make_period`
1. `tz = ZoneInfo(timezone)`; lỗi (`ZoneInfoNotFoundError`, `ValueError`) → SnapshotError "Múi giờ không hợp lệ".
2. `start = datetime.combine(start_date, time(h, m, 0) if start_time else time(0, 0, 0), tzinfo=tz)`.
3. `end = datetime.combine(end_date, time(h, m, 59) if end_time else time(23, 59, 59), tzinfo=tz)`.
4. `start >= end` → SnapshotError "Thời điểm start phải trước end".
5. Trả `Period(start, end, timezone, start_date, end_date)`.

### 5.2 `find_snapshots`
1. `repo.resolve_branch(branch)` (nhánh không tồn tại → GitError từ `git_repo`).
2. `end_sha = repo.rev_before(branch, period.end)`; `None` → SnapshotError "Không có dữ liệu trong khoảng thời gian".
3. `start_sha = repo.rev_before(branch, period.start)` (có thể `None`).
4. Trả `Snapshots(branch, commit_info(start_sha) | None, commit_info(end_sha))`. Log INFO: hai SHA ngắn + ngày commit.

### 5.3 `plan_export(repo, commit_sha, filters)`
1. `commit_sha is None` → `ExportPlan(None, [], [])`.
2. `entries = repo.list_tree(commit_sha)` (đã sắp xếp).
3. Duyệt từng entry, xác định ứng viên:
   1. `object_type != "blob"` (submodule) hoặc `mode == "120000"` (symlink) → bỏ, không cảnh báo (log DEBUG).
   2. Đường dẫn không an toàn (hàm `is_unsafe_path`, dùng chung cho `builder` M4) — một thành phần: rỗng, `.`, `..`; bằng `.git` sau khi bỏ dấu `.`/khoảng trắng cuối (Windows tự cắt: `.git.`, `.git `) và không phân biệt hoa thường; chứa `:` (ổ đĩa `C:`, alternate data stream); hoặc đường dẫn chứa `\` → bỏ (cả `source_only` và `full`), cảnh báo `UNSAFE_PATH` `Bỏ qua file có đường dẫn không an toàn (không đưa vào export)` với `path` = đường dẫn gốc, đồng thời log WARNING (repo bất thường/độc hại; không đưa vào zip để tránh ghi ra ngoài thư mục khi giải nén). Kiểm tra này đứng **trước** bộ lọc §9 nên `node_modules/a:b.js` cũng có cảnh báo.
   3. `check_path(path, filters) is not None` → bỏ, không cảnh báo.
   4. `unknown = detect_language(path) is None`; `language = detect_language(path, filters.exclude_languages)`; `excluded_language = language is None and not unknown`.
   5. `source_only`:
      - `excluded_language` → bỏ, không cảnh báo.
      - `size > max_file_size_kb * 1024` → bỏ, cảnh báo `TOO_LARGE`.
      - còn lại → ứng viên cần đọc nội dung.
   6. `full`: **mọi** entry còn lại là ứng viên cần đọc nội dung (kể cả file quá lớn và ngôn ngữ bị loại) để kiểm binary theo `exclude_binary`. File source quá lớn: cảnh báo `TOO_LARGE`.
4. Đọc nội dung ứng viên bằng `repo.read_blobs` (một loạt, theo thứ tự path) và kiểm `is_binary(data)` (8000 byte đầu):
   - Binary: cảnh báo `BINARY` trừ khi đã có cảnh báo `TOO_LARGE` cho file đó; `source_only` → bỏ; `full` → giữ (`language=None`) nếu `not exclude_binary`, ngược lại bỏ.
   - Không binary, `full`, (`excluded_language` hoặc file quá lớn không phải source) → giữ, không cảnh báo (`language` = None, file source quá lớn giữ tên lexer).
   - Không binary và `unknown` (không quá lớn): cảnh báo `UNKNOWN_LANGUAGE`; `source_only` → bỏ; `full` → giữ (`language=None`).
   - Còn lại → giữ (`language` = tên lexer).
5. `files` sắp xếp theo path, `warnings` theo `(path, kind)`. Log INFO số file / số cảnh báo.

Thông báo cảnh báo giống `counter` ("Bỏ qua …") — nghĩa là **bỏ qua khi đếm LOC**; ở `full` file có thể vẫn nằm trong zip.

Bảng tóm tắt (sau bước lọc đường dẫn):

| Loại file | `source_only` | `full` | Cảnh báo |
|---|---|---|---|
| Source, ≤ giới hạn, text | export | export | — |
| Source, > giới hạn, text | bỏ | export | TOO_LARGE |
| Ngôn ngữ trong `exclude_languages`, text | bỏ | export | — |
| Không lexer, ≤ giới hạn, text | bỏ | export | UNKNOWN_LANGUAGE |
| Không lexer, > giới hạn, text | bỏ | export | TOO_LARGE chỉ ở `source_only` |
| Binary (mọi kích thước, mọi loại) | bỏ | export chỉ khi `exclude_binary=false` | BINARY (hoặc TOO_LARGE nếu đã cảnh báo quá lớn) |
| Symlink, submodule | bỏ | bỏ | — (log DEBUG) |
| Đường dẫn không an toàn (mọi loại file blob) | bỏ | bỏ | UNSAFE_PATH (+ log WARNING) |

### 5.4 `write_zip(repo, plan, zip_path, timestamp)`
1. `zip_path.parent.mkdir(parents=True, exist_ok=True)`; ghi vào `<zip_path>.tmp` rồi `os.replace` → không để lại zip dở. Mọi exception (kể cả `GitError` khi đọc blob) → xóa file tạm rồi ném tiếp; riêng `OSError` → SnapshotError.
2. `zipfile.ZipFile(tmp, "w", compression=ZIP_DEFLATED, compresslevel=6)`.
3. `date_time = max(timestamp, 1980-01-01 00:00:00).timetuple()[:6]` (bỏ tzinfo; zip không lưu múi giờ).
4. Với từng file theo thứ tự `plan.files` (nội dung lấy bằng `read_blobs` theo cùng thứ tự):
   Generator `read_blobs` được đóng tường minh (`contextlib.closing`) khi ghi xong hoặc khi có lỗi → tiến trình `git cat-file` dừng ngay, không phụ thuộc thời điểm thu gom exception.
   `info = ZipInfo(path, date_time)`; `info.compress_type = ZIP_DEFLATED`; `info.create_system = 3`; `info.external_attr = (0o100755 if mode == "100755" else 0o100644) << 16`; `zf.writestr(info, data)`.
5. Không có file (C_START rỗng) → zip hợp lệ, không có entry.
6. Trả `zip_path`.

### 5.5 Tên file
- `start_zip_name`: `f"start_{period.start_date:%Y-%m-%d}_{c_start.short_sha if c_start else 'empty'}.zip"`.
- `end_zip_name`: `f"end_{period.end_date:%Y-%m-%d}_{safe_name(user_tag)}.zip"`.
- `safe_name`: `re.sub(r"[^A-Za-z0-9._-]", "_", text)`; kết quả rỗng → `_`.

### 5.6 `export_snapshot`
`plan = plan_export(repo, commit.sha if commit else None, filters)`; `timestamp = zip_timestamp(commit, timezone)`; `write_zip(...)`; trả `plan`.

### 5.7 Lọc từng file (M4): `screen_entry`, `finish_entry`, `select_content`
Tách nguyên văn các bước 5.3.3 (lọc không cần nội dung) và 5.3.4 (lọc theo nội dung) thành hàm thuần (không gọi git); `plan_export` gọi lại hai hàm này nên kết quả **không đổi** (TC-01..24 giữ nguyên).
- `screen_entry(path, mode, object_type, size, filters)` — bước 5.3.3 cho một entry:
  1. `object_type != "blob"` hoặc `mode == "120000"` → `keep=False`, không cảnh báo (log DEBUG).
  2. `is_unsafe_path(path)` → `keep=False`, `warnings = (LocWarning(UNSAFE_PATH, path, "Bỏ qua file có đường dẫn không an toàn (không đưa vào export)"),)`, log WARNING (A5). Các trường còn lại của `Screening` như `_DROPPED` (`language=None`, cờ `False`).
  3. `check_path(path, filters) is not None` → `keep=False`.
  4. `unknown`, `language`, `excluded_language`, `too_large = size > max_file_size_kb * 1024` như bước 5.3.3.4.
  5. `source_only` + `excluded_language` → `keep=False`. `too_large` và (`language is not None` hoặc `source_only`) → cảnh báo `TOO_LARGE`; `source_only` → `keep=False`.
  6. Còn lại → `keep=True` (cần xem nội dung).
- `finish_entry(path, screening, head, filters)` — bước 5.3.4 với `binary = is_binary(head[:BINARY_SNIFF_BYTES])`; trả `Selection(keep, language, warnings)` gồm cả cảnh báo của `screening`:
  - binary: cảnh báo `BINARY` trừ khi đã có `TOO_LARGE` cho file source; giữ (`language=None`) chỉ khi `full` và `not exclude_binary`;
  - không binary, (`excluded_language` hoặc quá lớn không phải source) → giữ, `language = screening.language` (`None` với file không phải source);
  - không binary, `unknown` → cảnh báo `UNKNOWN_LANGUAGE`; giữ (`language=None`) chỉ khi `full`;
  - còn lại → giữ, `language = screening.language`.
  `screening.keep == False` → `ValueError` (lỗi lập trình).
- `select_content(path, mode, data, filters)`: `s = screen_entry(path, mode, "blob", len(data), filters)`; `s.keep == False` → `Selection(False, None, s.warnings)`; ngược lại `finish_entry(path, s, data[:BINARY_SNIFF_BYTES], filters)`. Dùng cho file `builder` dựng ra (nội dung trong bộ nhớ, tên = tên được chọn theo D25).
- `plan_export` (5.3) = `screen_entry` cho mọi entry của `list_tree`; các entry `keep` đọc đầu nội dung bằng `read_blobs` (một loạt, theo thứ tự path, mỗi blob một lần) rồi `finish_entry`. Cảnh báo gộp, sắp theo `(path, kind)` như cũ.

### 5.8 `write_entries(repo, entries, zip_path, timestamp)`
1. Kiểm tra trước khi tạo file: mỗi entry có đúng một trong `blob_sha` / `data` khác `None`, và không trùng `path` → ngược lại `ValueError` (lỗi lập trình), không tạo file.
2. `ordered = sorted(entries, key=path)` — thứ tự entry trong zip luôn theo path, không phụ thuộc thứ tự đầu vào.
3. Các bước còn lại giống 5.4 (file tạm `.tmp` + `os.replace`, `ZIP_DEFLATED` mức 6, `date_time`, `create_system = 3`, `external_attr` theo mode, dọn file tạm với mọi exception, `OSError` → SnapshotError):
   - entry có `blob_sha`: nội dung lấy tuần tự từ **một** generator `read_blobs([e.blob_sha for e in ordered if e.blob_sha])`, đóng tường minh bằng `contextlib.closing`; ghi xong mọi entry thì đọc tiếp generator tới hết (`next(blobs, None)` phải trả `None`) để `read_blobs` kết thúc bình thường và kiểm mã thoát của `git cat-file` (lỗi → GitError, zip không được tạo);
   - entry có `data`: ghi thẳng `data`.
4. `entries` rỗng → zip hợp lệ không có entry.
`write_zip(repo, plan, zip_path, timestamp)` = `write_entries(repo, [ZipEntry(f.path, f.mode, f.blob_sha) for f in plan.files], zip_path, timestamp)`.

### 5.9 `zip_timestamp(commit, timezone)`
`commit.committer_date.astimezone(_zone(timezone))` nếu có commit, ngược lại `datetime(1980, 1, 1)`. `builder` dùng với C_END cho zip end theo user (cùng timestamp với zip end tất cả user).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- "commit date" của §3.1 = **committer date** (cái `git rev-list --before` dùng). Fixture test đặt cả `GIT_AUTHOR_DATE` và `GIT_COMMITTER_DATE`.
- Mốc bao gồm commit có committer date **bằng** mốc (≤).
- First-parent: commit chỉ có trên nhánh feature đã merge không bao giờ là C_START/C_END.
- C_START có thể bằng C_END (không có commit trong kỳ) → hợp lệ, hai export giống nhau.
- Commit date không đơn điệu (rebase, đồng hồ lệch): `rev-list --before` vẫn trả commit **đầu tiên theo thứ tự duyệt** thỏa điều kiện; chấp nhận, không sắp xếp lại.
- Đường dẫn trong zip là đường dẫn POSIX tương đối gốc repo, không có thư mục bọc ngoài; tên Unicode được `zipfile` đặt cờ UTF-8.
- Nội dung là blob nguyên byte (CRLF, BOM giữ nguyên); không áp `.gitattributes`/eol/filter (LFS pointer được export như file text).
- `export_mode=full` vẫn bỏ symlink và submodule.

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo cho người dùng (tiếng Việt) | Log |
|---|---|---|---|
| Múi giờ sai | SnapshotError | `Múi giờ không hợp lệ: <tz>` | — |
| start ≥ end | SnapshotError | `Thời điểm start (<start>) phải trước end (<end>).` (định dạng `YYYY-MM-DD HH:MM:SS`) | — |
| Không có commit ≤ end | SnapshotError | `Không có dữ liệu trong khoảng thời gian: nhánh <branch> không có commit nào trước <end>.` | INFO |
| Nhánh không tồn tại | GitError (từ `git_repo`) | `Không tìm thấy nhánh: <branch>` | — |
| Lỗi ghi zip (`OSError`) | SnapshotError | `Không ghi được file <zip_path>: <lỗi>` | ERROR |
| File bị bỏ | cảnh báo trong `ExportPlan.warnings` | `Bỏ qua file lớn hơn <n> KB (<x> KB)`, `Bỏ qua file binary`, `Bỏ qua file không nhận diện được ngôn ngữ` (giống `counter`) | — |
| Đường dẫn không an toàn | cảnh báo `UNSAFE_PATH` trong `ExportPlan.warnings` / `Selection.warnings` | `Bỏ qua file có đường dẫn không an toàn (không đưa vào export)` | WARNING (`%r` đường dẫn) |

## 8. Bảo mật, hiệu năng, tái lập
- Token: module không nhận token; mọi git đi qua `GitRepo`.
- Hiệu năng: kích thước lấy từ `ls-tree -l` (không đọc blob để lọc size); đọc blob bằng một tiến trình `cat-file --batch` cho mỗi lượt (lọc binary, ghi zip). M7 có thể gộp hai lượt đọc.
- Tái lập: entry theo path tăng dần, `date_time` = committer date của snapshot (cố định với cùng input), `create_system=3`, quyền cố định, `compresslevel` cố định → cùng input cho zip trùng byte.
- Windows: không giải nén ra đĩa ở M2; đường dẫn zip luôn `/`.

## 9. Test cases
Fixture `make_repo` (conftest): repo tạm, ngày commit cố định (`+07:00`), `core.autocrlf=false`, mở bằng `GitRepo.open(path, cache_root=tmp_path / "cache")`.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-snapshot-01 | Không nhập giờ | 2026-01-01 → 2026-01-31, `Asia/Bangkok` | start `2026-01-01T00:00:00+07:00`, end `2026-01-31T23:59:59+07:00` | unit |
| TC-snapshot-02 | Nhập giờ (D10) | start_time 08:30, end_time 17:45 (kèm giây 12 bị bỏ) | `08:30:00`, `17:45:59` | unit |
| TC-snapshot-03 | start ≥ end | cùng ngày, start 10:00, end 09:59; start = end | SnapshotError `phải trước end` | unit |
| TC-snapshot-04 | Múi giờ khác / sai | `UTC`; `Mars/Base` | end có offset +00:00; SnapshotError `Múi giờ không hợp lệ` | unit |
| TC-snapshot-05 | Biên múi giờ C_START | commit `2025-12-31T23:59:59+07:00` (X), `2026-01-01T00:00:00+07:00` (Y), `2026-01-01T00:00:01+07:00` (Z); start 2026-01-01 | C_START = Y | integration |
| TC-snapshot-06 | Biên C_END | commit `2026-01-31T23:59:59+07:00` (P), `2026-02-01T00:00:00+07:00` (Q); end 2026-01-31 | C_END = P | integration |
| TC-snapshot-07 | Cùng commit, múi giờ khác | commit `2026-01-01T03:00:00+07:00` (= `2025-12-31T20:00Z`); start 2026-01-01, tz `UTC` vs `Asia/Bangkok` | UTC: C_START = commit đó; Bangkok: commit trước nó | integration |
| TC-snapshot-08 | Không có commit trước start | commit đầu tiên trong kỳ | `c_start is None`; `start_zip_name` = `start_<date>_empty.zip`; zip không có entry; `plan.files == []` | integration |
| TC-snapshot-09 | Không có commit trước end | mọi commit sau end | SnapshotError `Không có dữ liệu trong khoảng thời gian` | integration |
| TC-snapshot-10 | First-parent | merge `--no-ff` nhánh feature, commit feature F trước end, merge M sau end | C_END = commit main trước M (không phải F) | integration |
| TC-snapshot-11 | Nhánh không tồn tại | `branch="nope"` | GitError `Không tìm thấy nhánh` | integration |
| TC-snapshot-12 | plan_export `source_only` | cây: `src/a.py`, `src/b.min.js`, `node_modules/x.js`, `tests/t.py`, `README.md`, `data.json`, `logo.png` (binary), `LICENSE`, `big.py` (> giới hạn, `max_file_size_kb=1`), symlink `link.py`, submodule `sub` | files = `data.json`, `src/a.py`, `tests/t.py`; cảnh báo BINARY `logo.png`, UNKNOWN_LANGUAGE `LICENSE`, TOO_LARGE `big.py`; không cảnh báo cho file bị loại theo đường dẫn / `exclude_languages` / symlink / submodule | integration |
| TC-snapshot-13 | `include_tests=false` | như TC-12 | `tests/t.py` bị bỏ, không cảnh báo | integration |
| TC-snapshot-14 | plan_export `full` (D13) | như TC-12 + `notes.txt` (Text only, chứa NUL) + `big.png` (binary 3 KB > giới hạn), `exclude_binary=true` rồi `false` | `true`: thêm `README.md`, `LICENSE`, `big.py` (language None cho 2 file đầu, `Python` cho `big.py`); `logo.png`, `notes.txt`, `big.png` bị bỏ, có cảnh báo BINARY. `false`: có thêm 3 file binary (language None). Symlink, submodule, `node_modules` vẫn bỏ | integration |
| TC-snapshot-15 | Zip đúng nội dung, giữ byte | file CRLF, LF, BOM, không newline cuối, tên `thư mục/tệp.py`, file thực thi | entry đúng danh sách theo thứ tự path; `zf.read(p)` trùng byte với blob; tên Unicode đúng; `external_attr` 0o100755 cho file thực thi | integration |
| TC-snapshot-16 | Tái lập | `export_snapshot` 2 lần vào 2 đường dẫn | SHA-256 hai zip bằng nhau; `date_time` = committer date của commit theo tz | integration |
| TC-snapshot-17 | Export start/end tất cả user | repo §14 (5 commit, start/end bao các commit trong kỳ, 1 commit sau end) | zip start chỉ có `app.py` bản của admin; zip end có `app.py` + `util.py` bản C_END; commit sau end không có | integration |
| TC-snapshot-18 | Tên file | `start_zip_name` với c_start sha `a1b2c3d…`; `end_zip_name(period, "all")`; `safe_name("feature/x y")` | `start_2026-01-01_a1b2c3d.zip`; `end_2026-01-31_all.zip`; `feature_x_y` | unit |
| TC-snapshot-19 | Lỗi ghi zip | `zip_path` trỏ vào một file đang tồn tại dùng làm thư mục cha | SnapshotError `Không ghi được file`; không còn `.zip.tmp` | integration |
| TC-snapshot-20 | File không lexer vượt giới hạn | `huge.dat` (text, 2 KB, không lexer), `max_file_size_kb=1` | `source_only`: bỏ, cảnh báo TOO_LARGE, không đọc nội dung (spy `read_blobs`); `full`: export (language None), không cảnh báo | integration |
| TC-snapshot-21 | Đường dẫn không an toàn | cây tạo bằng `git mktree` có thư mục `..` và thư mục `.GIT` cùng chứa `evil.py`, cộng `ok.py` | không có trong `plan.files`, zip chỉ có `ok.py`; log WARNING; `plan.warnings` có `UNSAFE_PATH` cho `../evil.py` và `.GIT/evil.py` (sắp theo `(path, kind)`), thông báo đúng mục 7 | integration |
| TC-snapshot-22 | write_zip dọn file tạm khi đọc blob lỗi | plan có `blob_sha = "0"*40` | GitError lan ra; không còn `.tmp` | integration |
| TC-snapshot-23 | Đường dẫn không an toàn kiểu Windows | `is_unsafe_path` với `C:/evil.py`, `a:b.py`, `.git./x.py`, `.GIT /x.py`, `a\b.py`, `src/ok.py`, `src/.gitignore`, `a.b/c.py`; cây thật có `a:b.py` | 5 đầu → True; 3 sau → False; `a:b.py` không có trong plan, `plan.warnings == [UNSAFE_PATH a:b.py]` | unit + integration |
| TC-snapshot-25 | screen_entry + finish_entry theo từng dòng bảng 5.3 | unit, không git: mỗi dòng của bảng tóm tắt × `source_only`/`full` × `exclude_binary` true/false (head có/không NUL) | `keep`, `language`, kind cảnh báo đúng bảng; symlink / submodule / `node_modules/x.js` → `keep=False`, không cảnh báo; `../evil.py`, `node_modules/a:b.js` → `keep=False`, đúng một cảnh báo `UNSAFE_PATH` (mọi chế độ); `finish_entry` với `screening.keep=False` → ValueError | unit |
| TC-snapshot-26 | plan_export không đổi sau khi tách hàm | cây TC-12, TC-14 (`full`, `exclude_binary` true/false) | `plan.files`, `plan.warnings` bằng kết quả gọi `screen_entry`/`finish_entry` trực tiếp trên từng entry; spy `read_blobs`: gọi một lần, chỉ với SHA của entry `keep` | integration |
| TC-snapshot-27 | select_content cho file đã dựng | `src/a.py` 10 byte; `src/a.py` 2 KB (`max_file_size_kb=1`); `vendor/a.py` (tên mới bị bộ lọc loại); `logo.png` có NUL; `C:/x.py`; `LICENSE` | giữ (`Python`); `source_only` bỏ + TOO_LARGE, `full` giữ + TOO_LARGE; bỏ, không cảnh báo; BINARY; bỏ + UNSAFE_PATH (log WARNING) ở cả hai chế độ; `source_only` bỏ + UNKNOWN_LANGUAGE | unit |
| TC-snapshot-28 | write_entries trộn blob và data | entries không theo thứ tự: `z.py` (blob CRLF), `a/b.py` (data `b"x\r\ny"`, mode 100755), `m.py` (blob) | thứ tự entry trong zip `a/b.py`, `m.py`, `z.py`; nội dung trùng byte; `external_attr` 0o100755 cho `a/b.py`; ghi 2 lần với thứ tự đầu vào khác nhau → SHA-256 bằng nhau; `read_blobs` gọi một lần với `[m, z]` | integration |
| TC-snapshot-29 | write_entries kiểm tra đầu vào | entry có cả blob và data; entry không có cả hai; hai entry cùng path; `[]` | 3 ca đầu → ValueError, không tạo zip / `.tmp`; `[]` → zip hợp lệ, 0 entry | unit |
| TC-snapshot-30 | write_entries lỗi đọc blob | entry data + entry blob `"0"*40` | GitError lan ra; không còn `.tmp`; tiến trình `cat-file` đã kết thúc | integration |
| TC-snapshot-32 | write_entries kiểm mã thoát `cat-file` | spy `read_blobs` bằng generator giả: trả đủ blob rồi ném GitError ở bước kết thúc (mô phỏng mã thoát ≠ 0) | GitError lan ra; không có zip, không còn `.tmp`; generator được đọc tới hết (bước kết thúc có chạy) | unit |
| TC-snapshot-31 | zip_timestamp | commit `2026-01-31T16:59:59+00:00`, tz `Asia/Bangkok`; `None` | `2026-01-31 23:59:59+07:00`; `datetime(1980,1,1)` | unit |
| TC-snapshot-24 | write_zip lỗi giữa chừng dừng `cat-file` | 2 file; monkeypatch `ZipFile.writestr` ném `OSError` ở file thứ 2; spy `subprocess.Popen` trong `git_repo` | SnapshotError; ngay khi exception còn được giữ, tiến trình `cat-file` đã kết thúc (`poll() is not None`); không còn `.tmp` | integration |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án đề xuất | Trạng thái |
|---|---|---|---|
| A1 | Symlink, submodule và đường dẫn không an toàn (`..`, `.git`…) không được export (kể cả `full`). Symlink, submodule không có `LocWarning` (chỉ log) — chúng không phải nội dung source; đường dẫn không an toàn có `UNSAFE_PATH` từ M4 (A5). `WarningKind` thuộc spec `counter` | Giả định | Đã duyệt 2026-10-23 (mở rộng theo review M2); sửa phần đường dẫn không an toàn theo A5 — đã duyệt 2026-10-23 |
| A2 | Zip không có thư mục bọc ngoài; timestamp entry = committer date của snapshot theo múi giờ đã chọn (C_START rỗng → 1980-01-01) | Giả định | Đã duyệt 2026-10-23 |
| A3 | Cảnh báo của `plan_export` có thể trùng với cảnh báo khi `counter` đếm lại cùng file ở M5; `pipeline` (M5) chịu trách nhiệm gộp, khử trùng | Giả định, xử lý ở M5 | Đã duyệt 2026-10-23 |
| A4 | Không áp `.gitattributes` (eol, LFS smudge): export đúng byte đang lưu trong git | Giả định (§15 "giữ nguyên kiểu xuống dòng") | Đã duyệt 2026-10-23 |
| A5 | Đường dẫn không an toàn: `screen_entry` (5.7 bước 2) phát `UNSAFE_PATH` (định nghĩa ở spec `counter` 5.2) và vẫn log WARNING — một chỗ duy nhất cho cả export start/end và builder. Cùng một đường dẫn có ở C_START và C_END → hai cảnh báo giống nhau (ở hai plan); `pipeline` M5 khử trùng (A3) | Đã duyệt 2026-10-23 (hoãn tới bản `counter` M4); bản thực hiện — đã duyệt 2026-10-23 |
| A6 | `write_entries` luôn sắp entry theo path (kể cả khi người gọi truyền thứ tự khác) để tái lập; trùng path là lỗi lập trình (`builder` phải tự giải quyết trùng tên, vd. rename trùng đường dẫn) | Giả định | Đã duyệt 2026-10-23 |
| A7 | Múi giờ có DST: giờ không tồn tại / bị lặp khi chuyển giờ được `zoneinfo` xử lý theo `fold=0` (mặc định của `datetime.combine`), không báo lỗi. `Asia/Bangkok` (mặc định) không có DST | Giả định (chỉ ghi chú, không đổi code) | Đã duyệt 2026-10-23 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-23 | Tạo mới | M2 |
| 2026-10-23 | Thêm TC-20 phủ hàng "Không lexer, > giới hạn" của bảng 5.3 — chỉ thêm test | /feature-test M2 |
| 2026-10-23 | Sửa theo review M2: `full` đọc mọi ứng viên để kiểm binary (kể cả file quá lớn, ngôn ngữ bị loại) — giải quyết mâu thuẫn bảng 5.3 với D13; bỏ đường dẫn không an toàn; `write_zip` dọn file tạm với mọi exception; ghi rõ ý nghĩa thông báo "Bỏ qua"; sửa TC-14, TC-20, thêm TC-21, 22 | Review M2 FAIL (Major 3, S1, S2, S6, Minor M1, M4, M7) |
| 2026-10-23 | M3: tồn đọng review M2 F3 (đóng `read_blobs` tường minh trong `write_zip`), F6 (`is_unsafe_path` công khai, chặn `:`, `.git.`/`.git `); TC-23, 24 | PLAN D20 |
| 2026-10-23 | TC-23 thêm ca dấu gạch ngược (review M3 N5) — chỉ đổi test | Review M3 |
| 2026-10-23 | M4: tách lọc từng file thành `screen_entry`/`finish_entry`/`select_content` (5.7); `ZipEntry`, `write_entries` (5.8), `write_zip` gọi lại `write_entries`; `zip_timestamp` (5.9); R13, R14; TC-25..31; A5, A6. Trạng thái về `draft` | PLAN M4 (phục vụ `builder`) |
| 2026-10-23 | Người dùng duyệt bản M4 (A5, A6 đồng ý) → `approved` | Duyệt |
| 2026-10-23 | Sửa theo review M4 (reviews/git_repo-snapshot-20261023.md): `write_entries` đọc hết `read_blobs` để kiểm mã thoát `cat-file` (5.8); TC-32; A7 (DST). Trạng thái `implemented` → `approved` (người dùng duyệt gói sửa trước khi sửa code) | Review M4 (Minor 2, ghi chú spec 4) |
| 2026-10-23 | `write_entries` chỉ đọc tiếp `read_blobs` khi có entry blob (không chạy `cat-file` thừa) — không đổi hành vi | Review M4 r2 (Nit) |
| 2026-10-23 | Thực hiện A5 / PLAN F8: `screen_entry` phát cảnh báo `UNSAFE_PATH` (5.3.3.2, 5.7, bảng 5.3, mục 7); R15; sửa TC-21, 23, 25, 27; A1, A5. Trạng thái về `draft` | Spec `counter` M4 |
| 2026-10-23 | Người dùng duyệt bản F8 → `approved` | Duyệt |
| 2026-10-23 | Test pass (sửa TC-21, 23, 25, 27) → `implemented` | /feature-test |
| 2026-10-23 | Review PASS (reviews/counter-snapshot-20261023.md); TC-21: sửa mô tả input cho khớp test, test kiểm thêm nội dung zip (Nit) → `reviewed` | /feature-review |
