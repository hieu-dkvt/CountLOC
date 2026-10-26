---
id: report
title: Báo cáo Excel, CSV, warnings.csv, manifest
type: module
milestone: M5
modules: [src/loc_counter/report.py]
tests: [tests/test_report.py]
spec_refs: ["3.3", "3.4", "3.5", "7.5", "8.1", "8.2", "8.3", "9", "10.3", "12", "15", "16"]
depends_on: [counter, config]
status: reviewed
---

# Báo cáo Excel, CSV, warnings.csv, manifest

## 1. Mục đích & phạm vi
Ghi các file báo cáo của **một** lần phân tích vào thư mục kết quả (§12): `loc_report.xlsx` (6 sheet), `loc_by_user.csv`, `loc_by_language.csv`, `loc_by_file.csv`, `warnings.csv`, `manifest.json`. `report` nhận **dữ liệu đã tính sẵn** (`ReportData`) — không gọi git, không đếm LOC, không chọn user, không gộp cảnh báo; chỉ định dạng, sắp xếp ổn định, làm sạch văn bản và ghi file tái lập được.

Vị trí trong pipeline: `pipeline` → (`counter` tính số liệu) → `report.write_reports(out_dir, data)`.

**Ranh giới với `pipeline`** (thuộc spec `pipeline`, không thuộc spec này):
- Dựng `ReportData`: chọn tập account được tính (tất cả / bỏ bot / user chọn — D21), gọi `counter` (`count_export`, `compare_languages`, `rename_map`, `compare_files`, `user_metrics`, `weekly_metrics`, `cross_check`), lập `ExportSummary` cho từng zip đã ghi.
- **Gộp cảnh báo**: chuyển `LocWarning` của từng nguồn thành `ReportWarning` với phạm vi (`start`, `end:<tag>`, `gán tác giả`, `kiểm tra chéo`, `định danh`), khử trùng theo `(kind, path, message)` và gộp phạm vi (D40-N8, D31); chuyển cảnh báo GitHub API thành `IDENTITY`; gọi `path_conflict_warnings` / `windows_path_warnings` (spec `builder` 5.9); gọi `cross_check_warning` cho export chính và từng zip riêng.
- Tên thư mục kết quả `<repo>_<branch>_<start>_<end>_<user-tag>` (D40-N10), dựng trong thư mục tạm rồi thay thế, chỉ xóa thư mục cũ có `manifest.json` của tool (N13); ghi zip start / end; `run.log` (N12); tiến độ (N16); chọn `generated_at` (không truyền → `report` lấy giờ hiện tại).

Ngoài phạm vi: màn hình kết quả §10.3 (M6, dùng lại `ReportData`), stdout của `analyze` (spec `cli-analyze`), biểu đồ (UI M6 — sheet `Theo_tuan` chỉ có bảng dữ liệu).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | `loc_report.xlsx` có đúng các sheet `Tong_quan`, `Theo_ngon_ngu`, `Theo_user`, `Theo_file`, `Theo_tuan`, `Canh_bao` (đúng thứ tự) | §12 |
| R2 | `loc_by_user.csv`, `loc_by_language.csv`, `loc_by_file.csv` — UTF-8 có BOM để mở bằng Excel | §12, D40-N20 |
| R3 | `warnings.csv` — danh sách cảnh báo (hunk nhiều user, sửa liên tiếp, file bỏ qua, kiểm tra chéo…), cột `Loại`, `Đường dẫn`, `Nội dung`, `Phạm vi`, sắp ổn định `(path, kind)` | §7.5, D40-N8, D31 |
| R4 | `manifest.json` đủ key §12 theo đúng thứ tự (`tool_version`, `generated_at`, `repo`, `branch`, `timezone`, `start`, `end`, `c_start`, `c_end`, `users`, `all_users`, `config`, `totals`, `cross_check`) + `options`, `exports` | §12, D38, D40-N15, N17 |
| R5 | Số liệu chính `loc_start`, `loc_end`, `loc_delta`; theo ngôn ngữ (LOC start, LOC end, chênh lệch) | §8.1, §10.3 |
| R6 | Theo user: commit, thêm, xóa, ròng (code), file thay đổi; dòng **Tổng** (xlsx, không ở CSV); sắp commit giảm dần rồi account | §8.2, §10.3, D40-N18 |
| R7 | Theo file: đường dẫn, ngôn ngữ, LOC start, LOC end, chênh lệch (+ cột "Đổi tên từ") | §10.3, D40-N21 |
| R8 | Code ròng theo tuần, mỗi user (bảng dài; không có commit → chỉ tiêu đề) | §10.3, §12, D35 |
| R9 | Kiểm tra chéo: ghi giá trị hai bên, `diff_percent`, ngưỡng, kết quả | §8.3, §12, D38 |
| R10 | Không ghi token / thông tin xác thực vào bất kỳ file đầu ra nào | §10.2, §12, §15 |
| R11 | Tái lập: cùng input → xlsx / CSV trùng byte; `generated_at` chỉ ở manifest; xlsx chuẩn hóa theo committer date C_END | §15, D40-N14 |
| R12 | Báo cáo tiếng Việt (tên cột, nhãn, thông báo lỗi) | §0, CLAUDE.md |
| R13 | Ô văn bản không thành công thức, lọc ký tự điều khiển, cắt ô > 32.767 ký tự (xlsx); CSV thêm `'` trước ô văn bản bắt đầu `= + - @` | D40-R |
| R14 | Ghi chú "bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được" | §7.5 |
| R15 | Xuất riêng: số liệu chính theo export gộp / `all`; mỗi zip riêng có `loc` + kiểm tra chéo riêng trong `exports[]` | §3.3, D40-N17 |

## 3. Giao diện
`report` chỉ import lúc chạy `config`, `counter`, `loc_counter.__version__` (và thư viện chuẩn, `openpyxl`); kiểu `Period` (`snapshot`), `CommitInfo` (`git_repo`) chỉ import dưới `TYPE_CHECKING` — `report` không gọi git (TC-24).

```python
XLSX_NAME = "loc_report.xlsx"
USER_CSV_NAME = "loc_by_user.csv"
LANGUAGE_CSV_NAME = "loc_by_language.csv"
FILE_CSV_NAME = "loc_by_file.csv"
WARNINGS_CSV_NAME = "warnings.csv"
MANIFEST_NAME = "manifest.json"
SHEET_NAMES = ("Tong_quan", "Theo_ngon_ngu", "Theo_user", "Theo_file", "Theo_tuan", "Canh_bao")
XLSX_MAX_CELL_CHARS = 32767

# Nhãn phạm vi cảnh báo (D40-N8) — pipeline dùng khi gộp
SCOPE_START = "start"
SCOPE_ATTRIBUTION = "gán tác giả"
SCOPE_CROSS_CHECK = "kiểm tra chéo"
SCOPE_IDENTITY = "định danh"
def end_scope(tag: str) -> str:
    """Phạm vi của export end: "end:<tag>"."""

class ReportError(LocCounterError):
    """Lỗi ghi báo cáo (thông báo tiếng Việt)."""

@dataclass(frozen=True)
class ReportWarning:
    kind: WarningKind
    path: str                    # "" = cấp repo
    message: str                 # tiếng Việt
    scopes: tuple[str, ...]      # đã gộp, theo thứ tự pipeline đưa vào

ExportRole = Literal["start", "end", "separate"]

@dataclass(frozen=True)
class ExportSummary:
    role: ExportRole             # start | end (export gộp / all) | separate (zip riêng từng user)
    file_name: str               # tên zip trong thư mục kết quả
    tag: str | None              # user-tag; None cho start
    accounts: tuple[str, ...] | None   # None = bản nguyên (C_START / C_END)
    files: int                   # số entry trong zip
    loc: int                     # LOC của zip (count_export)
    cross_check: CrossCheck | None = None   # None cho start

@dataclass(frozen=True)
class ReportOptions:
    selected_users: tuple[str, ...] | None = None   # None = "Tất cả user"
    exclude_bots: bool = False
    separate_users: bool = False

@dataclass(frozen=True)
class ReportData:
    repo: str                    # nguồn đã chuẩn hóa (GitRepo.source — không chứa thông tin xác thực)
    branch: str
    period: Period
    c_start: CommitInfo | None
    c_end: CommitInfo
    users: tuple[str, ...]       # account được tính
    all_users: bool
    config: AppConfig
    options: ReportOptions
    loc_start: int
    loc_end: int
    languages: tuple[LanguageRow, ...]
    user_rows: tuple[UserMetrics, ...]
    files: tuple[FileRow, ...]
    weeks: tuple[WeekRow, ...]
    cross_check: CrossCheck      # của export gộp / all
    warnings: tuple[ReportWarning, ...] = ()
    exports: tuple[ExportSummary, ...] = ()
    tool_version: str = __version__
    @property
    def loc_delta(self) -> int: ...          # loc_end - loc_start

def clean_text(value: str) -> str:
    """Thay surrogate lẻ bằng U+FFFD, bỏ ký tự điều khiển XML không cho phép (giữ \\t \\n \\r)."""

def write_xlsx(path: Path, data: ReportData) -> Path:
    """loc_report.xlsx 6 sheet, chuẩn hóa tái lập (D40-N14)."""

def write_csv_reports(out_dir: Path, data: ReportData) -> list[Path]:
    """loc_by_user.csv, loc_by_language.csv, loc_by_file.csv (thứ tự này)."""

def write_warnings_csv(path: Path, warnings: Sequence[ReportWarning]) -> Path:
    """warnings.csv (cột Loại, Đường dẫn, Nội dung, Phạm vi)."""

def build_manifest(data: ReportData, generated_at: datetime | None = None) -> dict[str, Any]:
    """Dict manifest theo thứ tự key §12 + options, exports (D40-N15)."""

def write_manifest(path: Path, manifest: Mapping[str, Any]) -> Path:
    """JSON indent=2, ensure_ascii=False, UTF-8 không BOM, LF, có newline cuối."""

def write_reports(out_dir: Path, data: ReportData,
                  generated_at: datetime | None = None) -> list[Path]:
    """Ghi đủ 6 file vào out_dir; manifest ghi cuối cùng. Trả đường dẫn theo thứ tự cố định."""
```

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `data.repo` | str | — | `GitRepo.source` (URL có thông tin xác thực đã bị `normalize_source` từ chối) | §12, §15 |
| `data.period` | `Period` | — | `start`, `end` aware; `timezone` IANA | §3.1 |
| `data.users` | tuple[str] | — | account được tính; manifest ghi `sorted` | D40-N15 |
| `data.cross_check` | `CrossCheck` | — | `cross_check.loc_start == loc_start`, `cross_check.loc_end == loc_end` | D38 |
| `data.tool_version` | str | `loc_counter.__version__` (`0.1.0`) | | §12 |
| `generated_at` | datetime \| None | None → `datetime.now(ZoneInfo(period.timezone))` bỏ micro giây | phải aware | §12, D40-N14 |
| `out_dir` | Path | — | phải tồn tại và là thư mục | §12 |

Đầu ra (tên cố định, trong `out_dir`): `loc_report.xlsx`, `loc_by_user.csv`, `loc_by_language.csv`, `loc_by_file.csv`, `warnings.csv`, `manifest.json`.

## 5. Luồng xử lý

### 5.1 Chuẩn hóa dữ liệu (dùng chung)
- Thứ tự bảng (report tự sắp lại — idempotent với thứ tự của `counter`, A4): ngôn ngữ `(-loc_end, -loc_start, language)`; user `(-commits, account)`; file `path`; tuần `(week_start, account)`; cảnh báo sắp **ổn định** theo `(path, kind.value)` (cảnh báo cùng khóa giữ thứ tự đầu vào). Bảng export giữ thứ tự `data.exports`.
- `ReportData.__post_init__`: `cross_check.loc_start != loc_start` hoặc `cross_check.loc_end != loc_end` → `ValueError` (lỗi lập trình).
- `clean_text(s)`: (1) mọi ký tự surrogate `U+D800–U+DFFF` → `U+FFFD`; (2) bỏ ký tự `\x00–\x08`, `\x0b`, `\x0c`, `\x0e–\x1f` (đúng tập `openpyxl.cell.cell.ILLEGAL_CHARACTERS_RE`) và `U+FFFE`, `U+FFFF`. `\t`, `\n`, `\r` giữ nguyên.
- Ô văn bản xlsx: `clean_text`, rồi `"\r\n"` và `"\r"` đơn → `"\n"` (XML chuẩn hóa xuống dòng khi đọc — A12), rồi nếu dài hơn `XLSX_MAX_CELL_CHARS` → `s[:32766] + "…"` (đúng 32.767 ký tự); gán `cell.value = s` rồi `cell.data_type = "s"` (không bao giờ thành công thức, kể cả bắt đầu `=`). Chuỗi rỗng **sau khi làm sạch** (`path` cấp repo, `Đổi tên từ` trống, `Bot` của dòng Tổng, `User` của start, chuỗi chỉ có ký tự điều khiển) → ô trống (không ghi giá trị).
- Ô văn bản CSV: `clean_text`, rồi nếu ký tự đầu thuộc `= + - @ \t \r` → thêm tiền tố `'` (A6). Không cắt độ dài. Ô số (int / float) ghi thô (`-3`, không tiền tố, không dấu phân cách nghìn).
- Ô số xlsx: kiểu số; định dạng `#,##0` cho số lượng / LOC, `+#,##0;-#,##0;0` cho cột chênh lệch / ròng, `0.000` cho phần trăm.

### 5.2 Cột của từng bảng (dùng chung xlsx ↔ CSV, D40-N20)
| Bảng | Cột (theo thứ tự) | Nguồn |
|---|---|---|
| Theo ngôn ngữ | `Ngôn ngữ`, `Số file start`, `LOC start`, `Số file end`, `LOC end`, `Chênh lệch` | `LanguageRow` (`files_start`, `loc_start`, `files_end`, `loc_end`, `delta`) |
| Theo user | `User`, `Bot`, `Commit`, `Code thêm`, `Code xóa`, `Code ròng`, `File thay đổi`, `Dòng thêm`, `Dòng xóa` | `UserMetrics` (`account`, `is_bot` → `có`/`không`, `commits`, `added_code`, `deleted_code`, `net_code`, `files_changed`, `added_lines`, `deleted_lines`) |
| Theo file | `Đường dẫn`, `Đổi tên từ`, `Ngôn ngữ`, `LOC start`, `LOC end`, `Chênh lệch` | `FileRow` (`renamed_from` None → `""`) |
| Theo tuần (chỉ xlsx) | `Tuần`, `Ngày bắt đầu`, `User`, `Commit`, `Code thêm`, `Code xóa`, `Code ròng` | `WeekRow` (`week_start` → chuỗi `YYYY-MM-DD`) |
| Cảnh báo | `Loại`, `Đường dẫn`, `Nội dung`, `Phạm vi` | `ReportWarning` (`kind.value`, `path`, `message`, `"; ".join(scopes)`) |

`Code thêm` / `Code xóa` = `added_code` / `deleted_code` (§10.3 "Thêm", "Xóa"); `Dòng thêm` / `Dòng xóa` = mọi dòng (kể cả comment / trống) để tham khảo.

### 5.3 `write_xlsx(path, data)`
1. `Workbook()`; sheet đầu đổi tên `Tong_quan`; tạo tiếp 5 sheet theo `SHEET_NAMES`.
2. **Tong_quan** — bảng hai cột `Mục`, `Giá trị` (hàng 1 là tiêu đề), các hàng theo thứ tự:

   | Mục | Giá trị |
   |---|---|
   | `Repo` | `data.repo` |
   | `Nhánh` | `data.branch` |
   | `Múi giờ` | `period.timezone` |
   | `Start` | `period.start.isoformat()` |
   | `End` | `period.end.isoformat()` |
   | `C_START` | sha đầy đủ; rỗng → `(rỗng)` |
   | `Snapshot start` | `<short_sha> (<YYYY-MM-DD HH:MM> committer date theo múi giờ) "<subject>"`; rỗng → `Không có commit trước start (LOC start = 0)` |
   | `C_END` | sha đầy đủ |
   | `Snapshot end` | như `Snapshot start` cho C_END |
   | `User` | `all_users` → `Tất cả user` (thêm ` (loại trừ bot)` khi `options.exclude_bots`); ngược lại `", ".join(sorted(users))` |
   | `Số user được tính` | `len(users)` |
   | `LOC start` / `LOC end` / `Chênh lệch` | `loc_start` / `loc_end` / `loc_delta` (ba hàng) |
   | `Commit` | `total_metrics(user_rows).commits` |
   | `Tổng code ròng` | `cross_check.sum_net_code` |
   | `LOC end kỳ vọng` | `cross_check.expected_loc_end` |
   | `Lệch kiểm tra chéo (%)` | `cross_check.diff_percent` |
   | `Ngưỡng (%)` | `cross_check.threshold_percent` |
   | `Kiểm tra chéo` | `Đạt` / `Lệch quá ngưỡng` |
   | `Số cảnh báo` | `len(warnings)` |
   | `Phiên bản công cụ` | `tool_version` |
   | `Ghi chú` | chỉ khi có export `end`/`separate` với `accounts is not None`: `Bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được.` (§7.5) |

   Sau đó một hàng trống, rồi bảng export: tiêu đề `File export`, `Loại`, `User`, `Số file`, `LOC`, `LOC end kỳ vọng`, `Lệch (%)`, `Kiểm tra chéo`; mỗi `ExportSummary` theo thứ tự `data.exports` (pipeline đưa: start, end, rồi riêng theo account): `Loại` = `Start` / `End` / `End (riêng)`; `User` = `""` cho start, `Tất cả user` khi `tag == "all"` hoặc `accounts is None` (thêm ` (loại trừ bot)` khi `options.exclude_bots`, cùng nhãn với hàng `User`), ngược lại `", ".join(accounts)`; ba cột kiểm tra chéo trống (ô `None`) khi `cross_check is None`, ngược lại `expected_loc_end`, `diff_percent`, `Đạt`/`Lệch quá ngưỡng`.
3. **Theo_ngon_ngu**, **Theo_user**, **Theo_file**, **Theo_tuan**, **Canh_bao**: hàng 1 tiêu đề (mục 5.2), mỗi phần tử một hàng theo thứ tự 5.1. `Theo_user` thêm **dòng Tổng** cuối bảng, luôn có (A3): `User = "Tổng"`, `Bot = ""`, các cột số từ `counter.total_metrics(user_rows)` (`File thay đổi` = số file khác nhau). Bảng rỗng → chỉ tiêu đề (Theo_user vẫn có dòng Tổng toàn 0).
4. Trình bày (tất định): tiêu đề in đậm (cả tiêu đề bảng export của Tong_quan); `freeze_panes = "A2"` cho 5 sheet bảng; `auto_filter` trên vùng bảng (`A1:<cột cuối><hàng cuối dữ liệu>`, không gồm dòng Tổng); độ rộng cột = `min(60, max(10, độ dài lớn nhất của giá trị ô dạng chuỗi + 2))`.
5. Lưu vào `BytesIO`, rồi **chuẩn hóa** (D40-N14, rủi ro PLAN mục 5): `stamp = c_end.committer_date.astimezone(ZoneInfo(timezone))`; zip mới ghi lần lượt **đúng thứ tự** `infolist()` của bản openpyxl, mỗi entry `ZipInfo(name, date_time=max(stamp bỏ tz, 1980-01-01 00:00:00).timetuple()[:6])`, `compress_type = ZIP_DEFLATED`, `compresslevel = 6` (truyền cho từng `writestr`), `create_system = 3`, `external_attr = 0o100644 << 16`; nội dung giữ nguyên trừ `docProps/core.xml`: thay text của `<dcterms:created …>` và `<dcterms:modified …>` bằng `c_end.committer_date` quy về UTC dạng `YYYY-MM-DDTHH:MM:SSZ`.
6. Ghi `path.write_bytes(...)`; trả `path`.

### 5.4 `write_csv_reports(out_dir, data)`, `write_warnings_csv(path, warnings)`
- Dựng nội dung bằng `csv.writer(buf, delimiter=",", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)` trên `io.StringIO`; hàng 1 tiêu đề (5.2), rồi dữ liệu theo thứ tự 5.1; ghi `path.write_bytes(text.encode("utf-8-sig"))` (BOM `EF BB BF`, `\r\n` trên mọi OS).
- `loc_by_user.csv` (**không** có dòng Tổng, N18), `loc_by_language.csv`, `loc_by_file.csv`; trả `[user, language, file]`.
- `warnings.csv`: cảnh báo sắp ổn định 5.1; không có → chỉ tiêu đề.

### 5.5 `build_manifest(data, generated_at)`
1. `generated_at` None → `datetime.now(ZoneInfo(period.timezone)).replace(microsecond=0)`; naive (`tzinfo is None` hoặc `utcoffset() is None`) → `ValueError`.
2. Trả dict (thứ tự key cố định):
```json
{
  "tool_version": "0.1.0",
  "generated_at": "<generated_at.isoformat(timespec='seconds')>",
  "repo": "<repo>", "branch": "<branch>", "timezone": "<period.timezone>",
  "start": "<period.start.isoformat()>", "end": "<period.end.isoformat()>",
  "c_start": "<sha>" | null, "c_end": "<sha>",
  "users": ["<sorted(users)>"], "all_users": true|false,
  "config": "<config_to_dict(config)>",
  "totals": {"loc_start": 0, "loc_end": 0, "loc_delta": 0},
  "cross_check": {"expected_loc_end": 0, "diff_percent": 0.0, "loc_end": 0,
                  "sum_net_code": 0, "threshold_percent": 0.5, "ok": true},
  "options": {"selected_users": ["…"] | null, "exclude_bots": false, "separate_users": false},
  "exports": [{"role": "start|end|separate", "file": "<file_name>", "tag": "<tag>" | null,
               "accounts": ["…"] | null, "files": 0, "loc": 0, "cross_check": {…} | null}]
}
```
`cross_check` của `exports[i]` cùng dạng 6 key như cấp gốc. `options.selected_users` giữ thứ tự đầu vào (pipeline đã sắp). `exports` giữ thứ tự `data.exports`.

### 5.6 `write_manifest(path, manifest)`
Mọi chuỗi (key và giá trị, đệ quy trong dict / list) có surrogate lẻ → thay bằng `U+FFFD` (A13; vd. tên nhánh / đường dẫn POSIX không phải UTF-8); `text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"`; `path.write_bytes(text.encode("utf-8"))` (LF trên mọi OS, không BOM).

### 5.7 `write_reports(out_dir, data, generated_at)`
1. `out_dir` không tồn tại hoặc không phải thư mục → `ReportError`.
2. Tính `manifest = build_manifest(data, generated_at)` **trước** khi ghi (lỗi `generated_at` không để lại file nào).
3. Ghi theo thứ tự: `write_xlsx` → `write_csv_reports` → `write_warnings_csv` → `write_manifest` (**cuối cùng**: có `manifest.json` = thư mục đã ghi xong — dùng cho N13 của pipeline).
4. Trả `[xlsx, loc_by_user, loc_by_language, loc_by_file, warnings, manifest]`. Log INFO `Đã ghi báo cáo vào <out_dir>`.

Mọi lần ghi file (5.3 bước 6, 5.4, 5.6) bọc `OSError` → `ReportError` (mục 7).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- **C_START rỗng:** `C_START = (rỗng)`, manifest `c_start: null`, `loc_start = 0` (pipeline đưa vào).
- **Không có commit trong kỳ:** `user_rows`, `weeks` rỗng → `Theo_user` chỉ tiêu đề + Tổng 0; `Theo_tuan` chỉ tiêu đề; CSV user chỉ tiêu đề.
- **Xuất riêng (N17):** số liệu chính (Tong_quan, totals, cross_check cấp gốc, các bảng) theo export gộp / `all`; mỗi zip riêng chỉ có hàng trong bảng export của Tong_quan và `exports[]`.
- **Bot:** `report` không lọc; `Bot = có` chỉ để hiển thị.
- **Số âm** (chênh lệch, ròng) là số, không phải văn bản → không bị thêm `'` ở CSV.
- **Đường dẫn chứa `,`, `"`, xuống dòng:** CSV quote theo `QUOTE_MINIMAL`; đọc lại bằng `csv` cho đúng giá trị.
- **Ô văn bản bắt đầu `=`** (vd. đường dẫn `=cmd.py`, account `=x`): xlsx là chuỗi; CSV có `'` ở đầu.
- **`generated_at`** chỉ có trong manifest; xlsx / CSV không chứa thời điểm chạy → trùng byte giữa hai lần chạy.

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo (tiếng Việt) | Log |
|---|---|---|---|
| `out_dir` không tồn tại / không phải thư mục | `ReportError` | `Thư mục kết quả không tồn tại hoặc không phải thư mục: <out_dir>` | ERROR |
| Lỗi ghi file (`OSError`: quyền, đĩa đầy, file đang mở trong Excel) | `ReportError` (giữ `__cause__`) | `Không ghi được file báo cáo <path>: <lỗi OS>` | ERROR |
| `generated_at` naive | `ValueError` (lỗi lập trình) | — | — |
| `cross_check` không khớp `loc_start` / `loc_end` | `ValueError` (lỗi lập trình) | — | — |

## 8. Bảo mật, hiệu năng, tái lập
- Token: `ReportData` không có trường token; `repo` là nguồn đã chuẩn hóa (URL chứa thông tin xác thực bị `git_repo.normalize_source` từ chối); `config_to_dict` không có trường bí mật. `report` không log nội dung ô.
- Hiệu năng: xlsx dựng trong bộ nhớ (một lần); `Theo_file` có thể vài nghìn hàng — chấp nhận ở M5 (`write_only` để M7 nếu cần).
- Tái lập: bảng sắp theo khóa 5.1; xlsx chuẩn hóa thời gian zip + `core.xml` theo committer date C_END (5.3 bước 5); CSV `\r\n`, manifest LF, JSON thứ tự key cố định; `generated_at` chỉ ở manifest.
- Windows: ghi bytes → không bị đổi `\n` thành `\r\n` ngoài ý muốn; UTF-8 tường minh (không phụ thuộc cp1252).

## 9. Test cases
Fixture: dữ liệu giả dựng tay (`Period` từ `make_period`, `CommitInfo` có ngày cố định, `LanguageRow`, `UserMetrics`, `FileRow`, `WeekRow`, `CrossCheck` thật của `counter`), và repo §14 (`s14_ctx` của `tests/test_counter_metrics.py`) cho TC-23.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-report-01 | Tên file và sheet | `write_xlsx` dữ liệu mẫu; hằng số | `load_workbook(...).sheetnames == ["Tong_quan","Theo_ngon_ngu","Theo_user","Theo_file","Theo_tuan","Canh_bao"]`; hằng tên file đúng §12 | unit |
| TC-report-02 | Tong_quan | dữ liệu mẫu (2 user chọn, 1 zip riêng) | các hàng `Mục`/`Giá trị` đúng thứ tự và giá trị mục 5.3 bước 2 (LOC là số, `Snapshot start` đúng định dạng, `Kiểm tra chéo` = `Đạt`, có `Ghi chú` §7.5); bảng export 3 hàng (`Start`, `End`, `End (riêng)`), ô kiểm tra chéo của start trống | unit |
| TC-report-03 | Theo_ngon_ngu + định dạng số | 3 `LanguageRow` đưa vào **không** theo thứ tự | tiêu đề đúng 5.2; hàng sắp `(-loc_end, -loc_start, language)`; `Chênh lệch` là số âm/dương; `number_format` cột LOC `#,##0`, cột chênh lệch `+#,##0;-#,##0;0`; tiêu đề in đậm, `freeze_panes == "A2"`, `auto_filter.ref` đúng; độ rộng cột theo 5.3 bước 4 (cột ngắn = 10, cột có giá trị 70 ký tự = 60) | unit |
| TC-report-04 | Theo_user + dòng Tổng | 3 `UserMetrics` (một bot, hai user cùng một file) đưa vào lộn thứ tự | sắp `(-commits, account)`; `Bot` = `có`/`không`; dòng cuối `Tổng`, cột số = `total_metrics` (File thay đổi = số file khác nhau); `user_rows` rỗng → chỉ tiêu đề + Tổng 0 | unit |
| TC-report-05 | Theo_file | `FileRow` có đổi tên, file chỉ ở start (`gone.py` 6 → 0), file chỉ ở end, lộn thứ tự | sắp theo path; `Đổi tên từ` = đường dẫn cũ / ô trống; chênh lệch đúng (`gone.py` −6) | unit |
| TC-report-06 | Theo_tuan | 2 `WeekRow` lộn thứ tự; biến thể rỗng | sắp `(week_start, account)`; `Ngày bắt đầu` chuỗi `2026-01-05`; rỗng → chỉ tiêu đề | unit |
| TC-report-07 | Canh_bao | cảnh báo `("b.py", BINARY)`, `("", CROSS_CHECK)`, `("a.py", UNATTRIBUTED)` ×2 (thông báo khác, thứ tự đầu vào giữ), scopes 2 phần tử | thứ tự `""` → `a.py` (2 hàng đúng thứ tự vào) → `b.py`; `Loại` = giá trị chuỗi (`cross_check`); `Phạm vi` = `start; end:alice` | unit |
| TC-report-08 | Chống công thức xlsx | account `=1+2`, path `+x.py`, `-x.py`, `@x.py`, message `=HYPERLINK("http://a")` | `load_workbook`: giá trị đúng nguyên văn, `data_type == "s"` (không `f`) | unit |
| TC-report-09 | Ký tự điều khiển, surrogate, cắt dài | message `"a\x00b\x07c\x1bd\te\nf"`; path chứa `"\ud800"`; message 40.000 ký tự | `clean_text` → `"abcd\te\nf"`, `"\ufffd"`; xlsx lưu được (không `IllegalCharacterError`), ô dài đúng 32.767 ký tự, kết thúc `…`; CSV giữ đủ độ dài (không cắt); path `a\rb.py` / `c\r\nd.py` → xlsx `a\nb.py` / `c\nd.py`, CSV giữ nguyên `\r`; chuỗi chỉ có `\x00` → ô trống | unit |
| TC-report-10 | Tái lập xlsx | ghi 2 lần, giữa hai lần đồng hồ khác (`time.sleep` > 1 s) | SHA-256 bằng nhau; mọi entry `date_time` = committer date C_END theo `Asia/Bangkok`; tên entry đúng thứ tự như `infolist()` của bản openpyxl gốc (lưu `Workbook` vào `BytesIO` bằng spy); mọi entry `compress_type == ZIP_DEFLATED`, `create_system == 3`, `external_attr == 0o100644 << 16`; `core.xml` created = modified = C_END UTC `…Z`; `load_workbook` đọc được | unit |
| TC-report-11 | C_END trước 1980 | `committer_date = 1975-01-01` | `date_time == (1980,1,1,0,0,0)`; `core.xml` = `1975-01-01T…Z`; ghi được | unit |
| TC-report-12 | Định dạng CSV | `write_csv_reports`; đường dẫn chứa `,` và `"` | mỗi file bắt đầu `EF BB BF`; dòng kết thúc `\r\n`; tiêu đề tiếng Việt đúng 5.2; số thô (`-3`, `1500` không dấu phân cách); `loc_by_user.csv` không có `Tổng`; đọc lại bằng `csv` đúng giá trị; trả `[user, language, file]` | unit |
| TC-report-13 | Chống công thức CSV | ô văn bản bắt đầu `=`, `+`, `-`, `@`, `\t`, `\r`; `a=b.py`; số âm | 6 ô đầu có tiền tố `'`; `a=b.py` không; số âm không | unit |
| TC-report-14 | warnings.csv | cảnh báo của TC-07; biến thể rỗng | BOM, `\r\n`; tiêu đề `Loại,Đường dẫn,Nội dung,Phạm vi`; cùng thứ tự TC-07; rỗng → chỉ tiêu đề | unit |
| TC-report-15 | `build_manifest` | dữ liệu mẫu, `generated_at = 2026-10-22T20:52:00+07:00` | `list(keys)` đúng thứ tự §12 + `options`, `exports`; `users` sắp tăng dần; `config == config_to_dict(config)`; `totals`; `cross_check` 6 key đúng thứ tự và giá trị; `generated_at == "2026-10-22T20:52:00+07:00"` | unit |
| TC-report-16 | `exports[]` (N17) | start + end `multi-2users` + 2 zip riêng (một zip lệch) | start `cross_check is None`, `tag is None`, `accounts is None`; end = cross_check cấp gốc; zip riêng có `loc`, `accounts`, kiểm tra chéo riêng (`ok False` ở zip lệch); thứ tự giữ nguyên | unit |
| TC-report-17 | `write_manifest` | manifest có account `"bé@ví_dụ"` | bytes không BOM, không `\r`, kết thúc `\n`, indent 2, chứa nguyên văn `bé` (không `\u00e9`); `json.loads` bằng dict; `write_reports` với `branch = "b\udcff"` (surrogate lẻ) → không lỗi, manifest có `"b\ufffd"` | unit |
| TC-report-18 | `generated_at` mặc định / naive | None; `datetime(2026,1,1)` naive | chuỗi ISO có offset `+07:00`, không micro giây; naive → `ValueError` | unit |
| TC-report-19 | `write_reports` + tái lập | ghi vào 2 thư mục với `generated_at` khác nhau; spy thứ tự ghi | 6 file đúng tên; danh sách trả đúng thứ tự; `manifest.json` ghi sau cùng; mọi file trùng SHA-256 trừ manifest; manifest bằng nhau sau khi bỏ `generated_at` | unit |
| TC-report-20 | Lỗi thư mục / ghi file | `out_dir` không tồn tại; `out_dir` là file; `Path.write_bytes` ném `PermissionError` | `ReportError` tiếng Việt chứa đường dẫn (`Thư mục kết quả không tồn tại hoặc không phải thư mục`, `Không ghi được file báo cáo`), `__cause__` là `PermissionError`; `generated_at` naive → `ValueError`, không file nào được ghi | unit |
| TC-report-21 | Kiểm tính nhất quán `ReportData` | `cross_check.loc_start` ≠ `loc_start`; `loc_end` ≠ | `ValueError` | unit |
| TC-report-22 | Không có trường bí mật | `dataclasses.fields` của `ReportData`, `ReportOptions`, `ExportSummary`, `ReportWarning`; key manifest (đệ quy) | không tên nào chứa `token`, `password`, `secret`, `auth` | unit |
| TC-report-23 | §14 tích hợp (`all`) | `s14_ctx`; dựng `ReportData` như pipeline (start 10, end `all` 20, `user_metrics` mọi account, `weekly_metrics`, `cross_check`) → `write_reports` | xlsx: Tong_quan LOC start 10, LOC end 20, Chênh lệch 10, Commit 4; Theo_user alice `5/2/+3`, bob `8/1/+7`, Tổng `13/3/+10`; Theo_tuan 2 hàng `2026-W02`; manifest `totals`, `cross_check.diff_percent == 0.0`, `ok True`, `c_start` = sha C_START; chạy 2 lần trùng SHA-256 (trừ manifest) | integration |
| TC-report-24 | Không import module git (không gọi git) | tiến trình con `import loc_counter.report` rồi liệt kê `sys.modules` | không có `loc_counter.git_repo`, `.snapshot`, `.attribution`, `.builder`, `.identity`, `.pipeline` | unit |
| TC-report-25 | C_START rỗng, không commit, tất cả user không ghi chú | `c_start=None`, `user_rows=()`, `weeks=()`, export end `accounts None`; biến thể `exclude_bots=True` | Tong_quan `C_START = (rỗng)`, `Snapshot start = Không có commit trước start (LOC start = 0)`, `User = Tất cả user`, không có hàng `Ghi chú`; biến thể: `Tất cả user (loại trừ bot)` ở hàng `User` và ở cột `User` của bảng export; manifest `c_start` null | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | **Ranh giới report ↔ pipeline** (mục 1): `report` chỉ định dạng + ghi; dựng `ReportData`, gộp / khử trùng cảnh báo, tên thư mục, thư mục tạm, `run.log` thuộc `pipeline`. `report` cung cấp hằng nhãn phạm vi (`SCOPE_*`, `end_scope`) để hai bên dùng chung | Theo PLAN M5 "Phạm vi từng spec" | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A2 | **Bảng `Theo_tuan` không có CSV** — §12 chỉ liệt kê 3 CSV (user, ngôn ngữ, file); cảnh báo có `warnings.csv` riêng | Theo §12 | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A3 | **Dòng Tổng của `Theo_user` luôn có** (không chỉ khi "Tất cả user" như §10.3): khi chọn user, Tổng = Σ của user chọn, chính là vế trái của kiểm tra chéo §8.3; không ở CSV (N18) | Khuyến nghị (§10.3 bắt buộc khi "Tất cả", không cấm trường hợp khác) | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A4 | `report` tự sắp lại các bảng theo đúng khóa của `counter` (A10 của spec `counter`) và sắp **ổn định** cảnh báo `(path, kind)` — idempotent nếu pipeline đã sắp, bảo đảm tái lập kể cả khi người gọi đưa thứ tự khác | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A5 | Tên cột (mục 5.2): theo §10.3 (`User`, `Commit`, `Thêm`→`Code thêm`, `Xóa`→`Code xóa`, `Ròng`→`Code ròng`, `File thay đổi`; `Ngôn ngữ`, `LOC start`, `LOC end`, `Chênh lệch`; `Đường dẫn`…) + cột phụ (`Bot`, `Dòng thêm`/`Dòng xóa`, `Số file start/end`, `Đổi tên từ`); CSV cùng tên cột với xlsx (N20) | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A6 | Chống chèn công thức CSV: ngoài `= + - @` (D40-R) thêm `\t`, `\r` ở đầu ô (khuyến nghị OWASP "CSV Injection"); ký tự điều khiển cũng được lọc ở CSV (cùng `clean_text`) để xlsx và CSV cùng giá trị (trừ `\r`, A12) | Mở rộng nhỏ của D40-R | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A7 | Chuẩn hóa xlsx (N14): giờ entry zip = committer date C_END theo múi giờ đã chọn (như zip export, `snapshot.zip_timestamp`, kẹp ≥ 1980); `core.xml` created/modified = committer date C_END (UTC); `create_system = 3`, `external_attr` cố định — xlsx trùng byte giữa hai lần chạy trên cùng phiên bản openpyxl + zlib (khác phiên bản thư viện có thể khác byte — ngoài phạm vi §15) | Theo D40-N14, rủi ro PLAN mục 5 (đã thử openpyxl 3.1.5: giữa hai lần ghi chỉ `core.xml` và giờ entry khác nhau) | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A8 | `Ngày bắt đầu` (Theo_tuan) ghi chuỗi ISO `YYYY-MM-DD` thay vì ô ngày Excel (tránh phụ thuộc định dạng ngày theo locale; tái lập) | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A9 | `manifest.json` ghi **sau cùng** trong `write_reports` để sự có mặt của nó nghĩa là báo cáo đã ghi đủ (pipeline N13 nhận diện thư mục của tool bằng manifest) | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A10 | `exports[]` của manifest: `role` (`start` / `end` / `separate`), `file`, `tag`, `accounts`, `files`, `loc`, `cross_check` (6 key như cấp gốc, `null` cho start). `options` = `selected_users` (null = tất cả), `exclude_bots`, `separate_users` (N15) | Cụ thể hóa D40-N15, N17 | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A11 | Không dùng `pandas` cho báo cáo (CSV bằng module `csv` theo N20; xlsx bằng `openpyxl` trực tiếp để kiểm soát kiểu ô và chuẩn hóa) — không thêm thư viện nào | Theo D40-N20, rủi ro PLAN mục 5 | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A12 | (review Minor 2) `\r` trong ô xlsx: openpyxl ghi `\r` thô, trình đọc XML chuẩn hóa thành `\n` → đọc lại khác CSV. Chọn **chủ động đổi `\r\n` / `\r` → `\n` ở xlsx** (kết quả giống nhau với mọi trình đọc; Excel hiển thị xuống dòng như nhau). Loại phương án escape `_x000D_` vì openpyxl đọc lại không giải mã (Excel và openpyxl cho hai giá trị khác nhau). CSV giữ nguyên `\r` | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |
| A13 | (review Minor 1) Surrogate lẻ trong chuỗi của manifest (`branch`, `repo` trên POSIX, mẫu lọc trong `config.yaml`) làm `encode("utf-8")` lỗi → `write_manifest` thay bằng `U+FFFD` (cùng quy tắc `clean_text` cho xlsx / CSV), không bọc lỗi thành `ReportError` | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (*) |

(*) Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (không chờ xác nhận); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-24 | Tạo mới theo PLAN M5 (phạm vi `report`, D35, D38, D40-N8, N14, N15, N17, N18, N20, N21, R) và thử nghiệm openpyxl 3.1.5 (tái lập, kiểu ô chuỗi); A1–A11. Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 → `approved` | M5 (`/feature-spec report`) |
| 2026-10-24 | Làm rõ khi lập trình (không đổi hành vi): chuỗi rỗng → ô xlsx trống (5.1) | /feature-implement |
| 2026-10-24 | Test pass (TC-01..25, 25 test report; toàn bộ 612), coverage `report.py` 100 % → `implemented` | /feature-test |
| 2026-10-24 | Sửa theo review (reviews/report-20261024.md, PASS_WITH_NOTES): surrogate trong manifest → U+FFFD (Minor 1, A13); `\r` ở xlsx → `\n` (Minor 2, A12); bỏ ô rỗng sau làm sạch (Nit 1); `compresslevel` từng entry (Nit 2); nhãn "loại trừ bot" ở bảng export, thông báo `out_dir` là file (ghi chú spec 3, 4); TC-03 (độ rộng cột), TC-05, TC-09, TC-10, TC-17, TC-20, TC-25 bổ sung (Minor 4, 5, Nit 4). Hằng / bảng cột nội bộ đổi tên `_…` (Minor 3, không thuộc API mục 3). Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 | /feature-review |
| 2026-10-24 | Test pass sau sửa (25 test report; toàn bộ 612), coverage `report.py` 100 %; review PASS_WITH_NOTES (reviews/report-20261024.md), Minor + Nit 1–5 đã sửa, Nit 6 ghi nhận → `reviewed` | /feature-review |
