---
id: pipeline
title: Pipeline phân tích (export start/end, gán tác giả, đếm LOC, báo cáo)
type: module
milestone: M5, M8
modules: [src/loc_counter/pipeline.py]
tests: [tests/test_pipeline.py]
spec_refs: ["3.1", "3.2", "3.3", "3.4", "3.5", "8.1", "8.2", "8.3", "10.2", "12", "15", "16"]
depends_on: [config, git_repo, snapshot, identity, attribution, builder, counter, report, classifier]
status: reviewed
---

# Pipeline phân tích

## 1. Mục đích & phạm vi
`pipeline` ghép các module đã có thành **một lần phân tích** (§13 M5): tìm C_START / C_END → export start → gán tác giả → export end (tất cả / theo user / xuất riêng) → đếm LOC trên nội dung zip → số liệu theo ngôn ngữ, file, user, tuần, kiểm tra chéo → báo cáo §12 trong thư mục kết quả. Dùng chung cho CLI `analyze` (spec `cli-analyze`) và màn hình Streamlit (M6).

`pipeline` **làm**: chọn tập account (D21, D40-N19), tên thư mục kết quả (D40-N10), dựng trong thư mục tạm rồi thay thế (D40-N13), `run.log` (D40-N12), tiến độ (D40-N16), xuất riêng (D40-N17), gộp + khử trùng cảnh báo có phạm vi (D40-N8, D31), `PATH_CONFLICT` cho start / `all` nguyên bản (A13), `WINDOWS_PATH` cho mọi export (D39), cảnh báo kiểm tra chéo, cảnh báo `IDENTITY`, dựng `ReportData` + gọi `report.write_reports` (ranh giới ở spec `report` mục 1).

Ngoài phạm vi:
- Phân tích tham số dòng lệnh, đọc token từ biến môi trường, `load_config`, `load_identities`, `make_period`, mở repo (`GitRepo.open`), chọn nhánh mặc định, stdout / mã thoát → spec `cli-analyze`.
- Hiển thị kết quả, khóa ô nhập, nút tải → M6 (dùng `AnalysisResult`, `prepare_period`).
- Tối ưu hiệu năng (đọc blob 2 lần, song song) → M7.

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | C_START / C_END theo first-parent; C_START rỗng → start không có file, LOC 0; không có commit trước end → lỗi "Không có dữ liệu trong khoảng thời gian" (từ `find_snapshots`) | §3.1 |
| R2 | Export start = source tại C_START sau bộ lọc §9 | §3.2 |
| R3 | Export end: "Tất cả user" = C_END; chọn user = C_START + thay đổi của user chọn, một bản gộp; "Xuất riêng từng user" → mỗi user một zip (mặc định tắt). "Tất cả" + loại bot dựng bằng builder (không có bot → C_END), tag `all` | §3.3, D21, D40-N17 |
| R4 | LOC của mỗi bản export đếm trên chính nội dung entry ghi vào zip | §3.4, D36 |
| R5 | Một `AccountResolver` dùng chung cho danh sách user và gán tác giả; account = author | §3.5, PLAN M5 |
| R6 | `loc_start`, `loc_end`, `loc_delta`, theo ngôn ngữ | §8.1 |
| R7 | Theo user: `added_code`, `deleted_code`, `net_code`, `commits` (không merge), `files_changed` | §8.2, D15, D40-N7 |
| R8 | Kiểm tra chéo `loc_start + Σ net_code ≈ loc_end` cho export chính và từng zip riêng; lệch > 0.5 % → cảnh báo kèm hai giá trị (không phải lỗi) | §8.3, D38, D40-N17 |
| R9 | Tiến độ theo bước (thứ tự thực): Export start → Gán tác giả → Export end → Đếm LOC → Tạo báo cáo | §10.2, D40-N16 |
| R10 | Thư mục `<out>/<repo>_<branch>_<start>_<end>_<user-tag>/` với đủ file §12 | §12, D40-N10 |
| R11 | Token không xuất hiện trong log, file đầu ra, cấu hình, manifest, exception | §10.2, §12, §15 |
| R12 | `logging` mức INFO, ghi `<out>/run.log`; lỗi Git: thông báo tiếng Việt + lệnh lỗi trong log | §15, D40-N12 |
| R13 | Tái lập: cùng repo, nhánh, kỳ, user, cấu hình → kết quả giống hệt (trừ `generated_at` trong manifest) | §15, D40-N14 |
| R14 | Cảnh báo gộp vào `warnings.csv` với phạm vi, sắp ổn định | §7.5, D40-N8, D31 |
| R15 | Bot hiện trong danh sách; tùy chọn loại trừ; chọn tường minh thắng `exclude_bots` | §16, D14, D40-N19 |

## 3. Giao diện

```python
RUN_LOG_NAME = "run.log"
TMP_PREFIX = ".loc-tmp-"          # thư mục tạm trong <out>
OLD_PREFIX = ".loc-old-"          # thư mục cũ đang chờ xóa
NAME_PART_MAX = 40                # độ dài tối đa <repo>, <branch> trong tên thư mục
WINDOWS_MAX_PATH = 259            # khi Windows chưa bật long path

class Step(StrEnum):
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
    branch: str                               # nhánh đã chọn (người gọi đã giải quyết nhánh mặc định)
    period: Period
    config: AppConfig
    out_root: Path                            # --out
    users: tuple[str, ...] | None = None      # None = "Tất cả user"; giá trị thô (--user / UI)
    exclude_bots: bool = False
    separate_users: bool = False
    attribution_mode: AttributionMode = "line"   # "last_commit": gán theo commit cuối của file (attribution 5.10)
    loc_end_mode: LocEndMode = "net_code"        # "added_code": LOC end = LOC start + Σ code thêm (report A15, A24)

@dataclass(frozen=True)
class PeriodContext:
    branch: str
    period: Period
    snapshots: Snapshots
    commits: tuple[LogCommit, ...]
    users: UsersResult                        # summarize_users(commits, resolver)
    # (A21) kết quả gán tác giả đã tính cho ctx này: FilterConfig → (weakref.ref(resolver),
    # PeriodAttribution); tối đa 1 phần tử; init=False (dataclasses.replace tạo memo rỗng mới),
    # không tham gia so sánh / repr; dựng theo vị trí 5 tham số vẫn hợp lệ
    attribution_memo: dict = field(default_factory=dict, init=False, compare=False, repr=False)

@dataclass(frozen=True)
class AnalysisResult:
    out_dir: Path                             # thư mục kết quả cuối
    data: ReportData
    snapshots: Snapshots
    period_users: tuple[UserSummary, ...]     # mọi account có commit trong kỳ (kể cả bot)
    start_zip: Path
    end_zips: tuple[Path, ...]                # cùng thứ tự data.exports[1:]
    report_files: tuple[Path, ...]            # thứ tự của report.write_reports
    generated_at: datetime

def make_resolver(source: str, identities: IdentityMap | None, token: str | None,
                  login_cache: Path | None = None) -> AccountResolver:
    """AccountResolver dùng chung; bật GitHub API khi nguồn là GitHub và có token."""

def prepare_period(repo: GitRepo, branch: str, period: Period,
                   resolver: AccountResolver) -> PeriodContext:
    """find_snapshots + log_commits + summarize_users (dùng trước khi bấm Phân tích ở UI)."""

def match_users(requested: Sequence[str], period_users: Sequence[UserSummary]) -> tuple[str, ...]:
    """Khớp user yêu cầu với account trong kỳ (D40-N19); trả tuple account đã sắp, không trùng."""

def result_dir_name(source: str, branch: str, period: Period, tag: str) -> str:
    """<repo>_<branch>_<start>_<end>_<user-tag> (D40-N10)."""

@contextmanager
def run_log(out_root: Path, secrets: Sequence[str | None] = ()) -> Iterator[Path]:
    """Ghi log package loc_counter (INFO) vào <out_root>/run.log trong khối with; che secret."""

def run_analysis(repo: GitRepo, request: AnalysisRequest, resolver: AccountResolver,
                 progress: ProgressCallback | None = None, *,
                 context: PeriodContext | None = None,
                 now: Callable[[], datetime] | None = None) -> AnalysisResult:
    """Chạy toàn bộ phân tích, ghi thư mục kết quả; trả dữ liệu cho CLI / UI."""
```

Không có trường / tham số chứa token trong `AnalysisRequest`, `PeriodContext`, `AnalysisResult` (TC-24); `PeriodContext.attribution_memo` chỉ giữ **weakref** tới resolver (không giữ token, A21). Token chỉ đi vào `make_resolver` (giữ trong `GitHubLoginResolver`) và `run_log(secrets=…)` (giữ trong formatter).

Cách gọi chuẩn (CLI, UI):
```python
repo = GitRepo.open(source, token, cache_root=git_repo.DEFAULT_CACHE_ROOT)
with run_log(out_root, secrets=(token,)):         # CLI bọc cả GitRepo.open để log lỗi clone/fetch
    resolver = make_resolver(repo.source, load_identities(path), token)
    result = run_analysis(repo, AnalysisRequest(...), resolver, progress)
```

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `request.users` | tuple[str] \| None | None ("Tất cả user") | `()` → lỗi "Chưa chọn user nào" | §3.3, §10.2 [3] |
| `request.exclude_bots` | bool | False | | §16 |
| `request.separate_users` | bool | False | | §3.3 |
| `request.attribution_mode` | `"line"` \| `"last_commit"` | `"line"` | khác → `ValueError` | yêu cầu 2026-10-30 |
| `request.loc_end_mode` | `"net_code"` \| `"added_code"` | `"net_code"` | khác → `ValueError` (kiểm ở đầu `run_analysis`, cùng chỗ `attribution_mode`) | yêu cầu 2026-10-30, A24 |
| `request.period.timezone` | str | `Asia/Bangkok` (từ `make_period`) | thắng `config.timezone` (A10) | §3.1 |
| `request.out_root` | Path | — (CLI bắt buộc `--out`) | chưa có → tạo; là file → lỗi | §11, §12 |
| `progress` | callback \| None | None | gọi lúc **bắt đầu** mỗi bước | §10.2 |
| `now` | callable \| None | `datetime.now(ZoneInfo(tz)).replace(microsecond=0)` | aware | D40-N14 |
| `login_cache` | Path \| None | None → `identity.DEFAULT_LOGIN_CACHE` (đọc lúc gọi) | | D18 |

Đầu ra trong `<out_root>/<result_dir_name>/`: `start_<date>_<sha7|empty>.zip`, `end_<date>_<tag>.zip` (+ zip riêng), `loc_report.xlsx`, `loc_by_user.csv`, `loc_by_language.csv`, `loc_by_file.csv`, `loc_by_pr.csv` (M8), `warnings.csv`, `manifest.json`. `run.log` ở `<out_root>/run.log` (ngoài thư mục kết quả).

## 5. Luồng xử lý

### 5.1 `make_resolver(source, identities, token, login_cache)`
`gh = github_repo_of(source)`; `github = GitHubLoginResolver(*gh, token, cache_path=login_cache)` khi `gh is not None and token`, ngược lại `None`; trả `AccountResolver(identities, github)`. (Giống phần bên trong `identity.list_period_users`.)

### 5.2 `prepare_period(repo, branch, period, resolver)`
1. `snaps = find_snapshots(repo, branch, period)` (không có commit trước end → `SnapshotError` của `snapshot`, giữ nguyên).
2. `commits = repo.log_commits(snaps.c_end.sha, snaps.c_start.sha if snaps.c_start else None, mailmap_rev=snaps.c_end.sha)` (D17).
3. `users = summarize_users(commits, resolver)`.
4. Log INFO `C_START=<sha|rỗng>, C_END=<sha>` và `<n> commit, <m> user trong kỳ`. Trả `PeriodContext(branch, period, snaps, tuple(commits), users)`.

### 5.3 `match_users(requested, period_users)` (D40-N19, A4)
1. `requested` rỗng → `PipelineError("Chưa chọn user nào.")`.
2. `period_users` rỗng → `PipelineError("Không có user nào có commit trong kỳ; không thể chọn user.")`.
3. `accounts = [u.account for u in period_users]` (thứ tự của `summarize_users`). Với mỗi `name` (bỏ khoảng trắng đầu/cuối):
   - có trong `accounts` (khớp chính xác) → chọn;
   - ngược lại, ứng viên = account có `casefold()` bằng `name.casefold()`: đúng 1 → chọn; ≥ 2 → `PipelineError("User '<name>' khớp nhiều account chỉ khác hoa thường: <a>, <b>. Hãy nhập chính xác.")`; 0 → `PipelineError("Không tìm thấy user '<name>' trong kỳ. User trong kỳ: <danh sách>")` — danh sách theo thứ tự `accounts`, tối đa 20 tên, còn lại ghi `… và <k> user khác`.
4. Trả `tuple(sorted(set(chosen)))`. Bot được chọn tường minh vẫn giữ dù `exclude_bots` (D40-N19).

### 5.4 `result_dir_name(source, branch, period, tag)` (D40-N10, A5, A6)
- `<repo>`: tách `source` theo `/`, `\`, `:`; bỏ đoạn rỗng ở cuối; lấy đoạn cuối, bỏ đuôi `.git` (không phân biệt hoa thường); kết quả rỗng → lấy đoạn trước đó (lặp lại); hết đoạn → `repo`. Rồi `part(…)`.
- `<branch>`: `part(branch)`.
- `part(s)`: `t = safe_name(s)`; `len(t) > NAME_PART_MAX` → `t[:33] + "-" + sha1(s.encode("utf-8", "surrogatepass")).hexdigest()[:6]` (đúng 40 ký tự).
- `<start>` = `period.start_date:%Y-%m-%d`, thêm `T%H%M` khi `period.start.time() != 00:00:00`; `<end>` = `period.end_date:%Y-%m-%d`, thêm `T%H%M` khi `period.end.time() != 23:59:59` (suy từ `Period`, mỗi phía xét riêng — A5).
- `<user-tag>` = `tag` (tag của job đầu tiên `plan_end_exports`, đã an toàn cho tên file).
- Ví dụ: `https://github.com/org/repo.git`, `main`, 2026-01-01..2026-01-31, `all` → `repo_main_2026-01-01_2026-01-31_all`; `feature/x` → `feature_x`; start 08:30 → `…_2026-01-01T0830_2026-01-31_…`.

### 5.5 `run_log(out_root, secrets)` (D40-N12, A1, A2, A16)
1. `out_root = Path(out_root).resolve()`; là file → `PipelineError("Thư mục đầu ra là một file: <out_root>")`; chưa có → `mkdir(parents=True)` (`OSError` → `PipelineError("Không tạo được thư mục đầu ra <out_root>: <lỗi>")`).
2. `handler = logging.FileHandler(out_root / RUN_LOG_NAME, mode="w", encoding="utf-8")` (`OSError` → `PipelineError("Không ghi được run.log: <lỗi>")`); level INFO; formatter `_MaskingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")` — `format()` gọi lớp cha rồi `git_repo.mask_secrets(text, secrets)` (che cả message lẫn traceback, che dạng base64 `x-access-token:<t>`; không sửa `LogRecord`).
3. Filter chỉ nhận record của **phiên** đã vào `with` (nhiều phiên Streamlit song song, A16): record của **luồng** đã vào `with` (`record.thread == threading.get_ident()`), **hoặc** record phát khi `ContextVar` `_RUN_LOG_ID` (module-level) bằng mã của phiên này (A22). Vào `with`: `token = _RUN_LOG_ID.set(<mã duy nhất của phiên>)`; `finally` theo thứ tự: gỡ handler, `close()`, khôi phục level (bước 5) **rồi mới** `_RUN_LOG_ID.reset(token)` bọc `suppress(ValueError)` — thoát `with` ở context khác (vd. generator bị đóng ở luồng khác) không được làm sót handler / khóa `run.log` / lệch bộ đếm level. Luồng con nhận context của phiên khi được chạy qua `contextvars.copy_context().run` (vd. `attribution` 5.1a); luồng tạo bằng `threading.Thread` thông thường không mang context → vẫn bị loại như cũ.
4. Gắn handler vào logger `loc_counter`. Level của logger (tài nguyên dùng chung cả tiến trình) chỉnh theo **đếm tham chiếu có khóa** (`_LEVEL_LOCK`, số phiên đang mở, level đã lưu — A18): phiên **đầu tiên** vào lưu `logger.level` rồi, nếu `logger.getEffectiveLevel() > INFO`, đặt `logger.setLevel(INFO)`; các phiên sau chỉ tăng bộ đếm. `yield out_root / RUN_LOG_NAME`.
5. `finally`: gỡ handler, `handler.close()` (Windows nhả khóa file ngay); giảm bộ đếm, phiên **cuối cùng** ra khôi phục level đã lưu.

### 5.6 `run_analysis(repo, request, resolver, progress, context, now)`
Ký hiệu: `cfg = request.config`, `filters = cfg.filters`, `tz = request.period.timezone`, `step(s)` = gọi `progress(s, i, 5)` nếu có.

**Chuẩn bị (trước mọi việc nặng — thuộc bước 1 về tiến độ)**
1. `step(EXPORT_START)`.
2. `out_root = request.out_root.resolve()`; là file → `PipelineError`; chưa có → `mkdir(parents=True)`.
3. `ctx = context or prepare_period(repo, request.branch, request.period, resolver)`; `context` khác `request.branch` / `request.period` → `ValueError` (lỗi lập trình). `snaps`, `commits`, `summaries = ctx.users.users`.
4. `selected = None if request.users is None else match_users(request.users, summaries)`.
5. `jobs = plan_end_exports(selected, summaries, request.exclude_bots, request.separate_users)`; `main = jobs[0]`.
6. `counted` = `main.accounts` nếu khác None, ngược lại `tuple(sorted(u.account for u in summaries))` (tập account được tính — R3, D21).
7. `final = out_root / result_dir_name(repo.source, snaps.branch, request.period, main.tag)`; `_check_target(final)` (5.7).
8. Tên file: `start_name = start_zip_name(period, snaps.c_start)`, `end_names = [end_zip_name(period, j.tag) for j in jobs]`; `_check_path_lengths(out_root, final, [start_name, *end_names, *report names])` (5.8).
9. `tmp = out_root / f"{TMP_PREFIX}{os.getpid()}-{secrets.token_hex(4)}"`; `tmp.mkdir()` — `OSError` → `PipelineError("Không tạo được thư mục tạm trong <out_root>: <lỗi>")` (A19). Từ đây mọi lỗi → dọn (5.9).

**Bước 1 — Export start**
10. `start_plan = plan_export(repo, snaps.c_start.sha if snaps.c_start else None, filters)`; `write_zip(repo, start_plan, tmp / start_name, zip_timestamp(snaps.c_start, tz))`.
11. Cảnh báo phạm vi `start`: `start_plan.warnings` + `path_conflict_warnings(paths, "start")` + `windows_path_warnings(paths)` với `paths = [f.path for f in start_plan.files]`.

**Bước 2 — Gán tác giả**
12. `step(ATTRIBUTION)`; `classifier = LineClassifier(filters.count_docstrings)` (dùng chung đến hết); `attr` lấy từ `ctx.attribution_memo` (A21): có khóa `(filters, request.attribution_mode)` và weakref lưu kèm trỏ tới **đúng** (`is`) `resolver` của lần gọi này → dùng lại, log INFO `Dùng lại kết quả gán tác giả đã tính cho kỳ này`; ngược lại (kể cả weakref đã chết) `attr = attribute_period(repo, snaps, commits, resolver, filters, classifier, mode=request.attribution_mode)` rồi `ctx.attribution_memo.clear(); ctx.attribution_memo[(filters, request.attribution_mode)] = (weakref.ref(resolver), attr)`. Cảnh báo phạm vi `gán tác giả`: `attr.warnings`.

**Bước 3 — Export end**
13. `step(EXPORT_END)`. `end_plan = plan_export(repo, snaps.c_end.sha, filters)` chỉ khi có job `accounts is None` (tính một lần).
14. Với mỗi job theo thứ tự `jobs`:
    - `accounts is None` → `export = export_from_plan(end_plan, job.tag)`; cảnh báo phạm vi `end:<tag>` = `end_plan.warnings` + `path_conflict_warnings(paths, job.tag)` + `windows_path_warnings(paths)`.
    - ngược lại → `export = build_user_export(repo, attr, start_plan, set(job.accounts), filters, job.tag)`; cảnh báo `end:<tag>` = `export.warnings` (đã có `PATH_CONFLICT`) + `windows_path_warnings(paths)`.
    - `write_user_export(repo, export, tmp / end_zip_name(period, job.tag), snaps.c_end, tz)`.

**Bước 4 — Đếm LOC**
15. `step(COUNT)`. `start_count = count_export(export_from_plan(start_plan, "start"), repo.read_blobs, filters, classifier)`; với mỗi export end: `count_export(export, repo.read_blobs, filters, classifier)` (D36). Cảnh báo của `CountResult.warnings` (nếu có) gộp vào phạm vi của export tương ứng.
16. Export chính `main_export`, `main_count`:
    - `languages = compare_languages(start_count, main_count)`;
    - `files = compare_files(start_count, main_count, rename_map(attr, [f.path for f in main_export.files]))`;
    - `user_rows = user_metrics(attr, summaries, counted)`; `weeks = weekly_metrics(attr, commits, counted, tz)`; `pr_rows = pr_metrics(attr, commits, counted, tz)` (M8, D43);
    - `check = cross_check(start_count.total_code, main_count.total_code, [r.net_code for r in user_rows])`.
17. Mỗi job riêng (`jobs[1:]`, một account `a`): `check_i = cross_check(loc_start, loc_i, [row(a).net_code])` với `row(a)` lấy từ `user_rows` (A11).
18. Cảnh báo phạm vi `kiểm tra chéo`: `cross_check_warning(check, main.tag)` rồi `cross_check_warning(check_i, job.tag)` theo thứ tự job (bỏ `None`). Phạm vi `định danh`: mỗi chuỗi trong `getattr(resolver.github, "warnings", ())` (đọc **sau** bước 2) → `LocWarning(IDENTITY, "", msg)`.
19. Log INFO mỗi export theo thứ tự start → end theo `jobs`: `<file>: <n> file, LOC <loc>`; kiểm tra chéo của export chính rồi từng zip riêng (theo `jobs`): `<tag>: loc_start + Σ net = expected, loc_end, lệch %`. Mode `added_code` (A24): thêm một dòng INFO `LOC end theo code thêm: loc_start + Σ added_code = <n> (đếm trên export: <loc_end>)`.

**Bước 5 — Tạo báo cáo**
20. `step(REPORT)`. `warnings = _merge_warnings(...)` (5.10).
21. `exports = (ExportSummary("start", start_name, None, None, len(start_plan.files), loc_start), ExportSummary("end", end_names[0], main.tag, main.accounts, len(main_export.files), loc_end, check), *[ExportSummary("separate", …, check_i)])`.
22. `data = ReportData(repo=repo.source, branch=snaps.branch, period=period, c_start=snaps.c_start, c_end=snaps.c_end, users=counted, all_users=selected is None, config=dataclasses.replace(cfg, timezone=tz), options=ReportOptions(selected, request.exclude_bots, request.separate_users, request.attribution_mode, request.loc_end_mode), loc_start=…, loc_end=…, languages=tuple(languages), user_rows=tuple(user_rows), files=tuple(files), weeks=tuple(weeks), pr_rows=tuple(pr_rows), cross_check=check, warnings=warnings, exports=exports)`.
23. `generated_at = (now or default)()`; `report_files = write_reports(tmp, data, generated_at)`.
24. `_commit_dir(tmp, final)` (5.9). Log INFO `Kết quả: <final>`.
25. Trả `AnalysisResult(final, data, snaps, tuple(summaries), final / start_name, tuple(final / n for n in end_names), tuple(final / p.name for p in report_files), generated_at)`.

### 5.7 `_check_target(final)` — thư mục đích (D40-N13, A8)
- Không tồn tại → OK.
- Là file (hoặc không phải thư mục) → `PipelineError("Đã có file trùng tên thư mục kết quả: <final>")`.
- Là thư mục: là "thư mục kết quả của tool" khi `final / "manifest.json"` là file, `json.loads` (UTF-8) ra `dict` có đủ key `tool_version`, `c_end`, `exports`. Ngược lại → `PipelineError("Thư mục <final> đã tồn tại nhưng không phải kết quả của LOC Counter (thiếu hoặc hỏng manifest.json); hãy xóa hoặc chọn thư mục đầu ra khác.")`.
- Gọi ở bước 7 (trước việc nặng) và lặp lại ở `_commit_dir`.

### 5.8 `_check_path_lengths(out_root, final, names)` (A9)
Chỉ trên Windows (`os.name == "nt"`) khi long path chưa bật (`winreg` đọc `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled` ≠ 1; đọc lỗi → coi như chưa bật). Độ dài dự kiến = `max(len(str(d / (n + ".tmp"))) for d in (tmp_mẫu, final, old_mẫu) for n in names)` với `tmp_mẫu` / `old_mẫu` dùng độ dài tên tối đa (`TMP_PREFIX` / `OLD_PREFIX` + 10 chữ số pid + `-` + 8 hex). Vượt `WINDOWS_MAX_PATH` → `PipelineError("Đường dẫn kết quả quá dài (<n> ký tự, Windows giới hạn 259): <đường dẫn dài nhất>. Hãy chọn thư mục đầu ra ngắn hơn hoặc gộp account bằng identities.yaml.")`.

### 5.9 Thư mục tạm, thay thế, dọn khi lỗi (D40-N13, A7)
`_commit_dir(tmp, final)`:
1. `final` không tồn tại → `os.replace(tmp, final)` — `OSError` → `PipelineError("Không đổi tên thư mục tạm thành <final>: <lỗi>")` (A19).
2. Tồn tại → `_check_target(final)` lại; `old = out_root / f"{OLD_PREFIX}{pid}-{hex8}"`; `os.replace(final, old)` — `OSError` → `PipelineError("Không thay thế được thư mục kết quả cũ <final> (có file đang mở?): <lỗi>")`, thư mục cũ giữ nguyên; rồi `os.replace(tmp, final)` — **mọi** lỗi (kể cả `KeyboardInterrupt`) → cố `os.replace(old, final)` (khôi phục) — khôi phục lỗi → log ERROR `Không khôi phục được thư mục kết quả cũ; dữ liệu cũ nằm ở <old>: <lỗi>`; `OSError` → `PipelineError("Không thay thế được thư mục kết quả cũ <final>: <lỗi>")` (khôi phục lỗi → thêm `. Không khôi phục được; dữ liệu cũ nằm ở <old>`), exception khác ném lại nguyên; cuối cùng `shutil.rmtree(old)` — lỗi chỉ log WARNING `Không xóa được thư mục cũ <old>`.

Bao toàn bộ bước 9–24 trong `try … except BaseException`: `logger.exception("Phân tích thất bại: …")` (đã che token qua formatter của `run_log`), `shutil.rmtree(tmp, ignore_errors=True)`, ném lại nguyên exception (kể cả `KeyboardInterrupt`, lỗi từ callback `progress`). Lỗi trước bước 9 không tạo file nào trong `<out_root>` (ngoài `run.log` nếu đang trong `run_log`).

### 5.10 `_merge_warnings` — gộp cảnh báo (D40-N8, D31, A12)
Nguồn theo thứ tự cố định, mỗi nguồn giữ thứ tự module trả về:
1. `start` (bước 11);
2. `gán tác giả` (bước 12);
3. `end:<tag>` của từng job theo thứ tự `jobs` (bước 14, 15);
4. `kiểm tra chéo` (bước 18);
5. `định danh` (bước 18).

Khử trùng theo khóa `(kind, path, message)`: giữ vị trí lần đầu xuất hiện; `scopes` = các phạm vi khác nhau theo thứ tự xuất hiện (vd. file quá lớn không đổi → một dòng `start; end:all`). Nhãn phạm vi dùng hằng của `report` (`SCOPE_START`, `SCOPE_ATTRIBUTION`, `end_scope(tag)`, `SCOPE_CROSS_CHECK`, `SCOPE_IDENTITY`). `report` sắp ổn định `(path, kind)` khi ghi.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- **C_START rỗng:** `plan_export(None)` → plan rỗng; zip `start_<date>_empty.zip` không có entry, timestamp 1980-01-01; `loc_start = 0`; `log_commits(c_end, None)`; manifest `c_start: null`.
- **Không có commit trong kỳ** (C_START == C_END): `summaries = []`. "Tất cả user" → `counted = ()`, `user_rows = ()`, `loc_end == loc_start`, kiểm tra chéo đạt. Chọn user → lỗi "Không có user nào có commit trong kỳ…".
- **Tập account được tính** (`counted`, `ReportData.users`): "Tất cả" không loại bot → mọi account trong kỳ (kể cả chỉ có merge commit, D15); "Tất cả" + loại bot → account không phải bot (có bot → end dựng bằng builder; không có bot → C_END nguyên bản, D21); chỉ có bot + loại bot → `counted = ()`, end = bản start, tag `all`; chọn user → kết quả `match_users`.
- **Xuất riêng:** chỉ khi chọn ≥ 2 user, hoặc "Tất cả" (mỗi account của pool một zip) — theo `plan_end_exports`; 1 user + xuất riêng → một zip. Số liệu chính theo export gộp / `all` (D40-N17); zip riêng chỉ có `ExportSummary` + kiểm tra chéo riêng.
- **`all_users`** = `request.users is None`; `options.selected_users` = `selected` (đã sắp) hoặc None.
- **Múi giờ:** `period.timezone` là nguồn duy nhất (C_START/C_END, timestamp zip, tuần, `generated_at`); `ReportData.config.timezone` thay bằng `period.timezone` để manifest ghi đúng cấu hình đã dùng (A10).
- **Kiểm tra chéo lệch:** chỉ cảnh báo, không ném lỗi; mã thoát do `cli-analyze` quyết (0).
- **Hai thư mục kết quả trùng tên** (`feature/x` vs `feature_x`, hoặc chỉ khác hoa thường trên NTFS): lần chạy sau thay lần trước — chấp nhận, ghi README (A6).
- **Thư mục `.loc-tmp-*` / `.loc-old-*` sót lại** do tiến trình bị giết: không tự xóa (có thể của tiến trình khác), README hướng dẫn xóa tay.
- **`run.log`** nằm ngoài thư mục kết quả → không ảnh hưởng tái lập; ghi đè mỗi lần chạy.

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo (tiếng Việt) | Log |
|---|---|---|---|
| Không có commit trước end | `SnapshotError` (từ `find_snapshots`), không tạo thư mục | `Không có dữ liệu trong khoảng thời gian` (nguyên văn của `snapshot`) | ERROR |
| `request.users == ()` | `PipelineError` | `Chưa chọn user nào.` | ERROR |
| Chọn user khi kỳ không có user | `PipelineError` | `Không có user nào có commit trong kỳ; không thể chọn user.` | ERROR |
| User không có trong kỳ | `PipelineError` | `Không tìm thấy user '<x>' trong kỳ. User trong kỳ: …` | ERROR |
| User khớp nhiều account khác hoa thường | `PipelineError` | `User '<x>' khớp nhiều account chỉ khác hoa thường: …. Hãy nhập chính xác.` | ERROR |
| `<out>` là file / không tạo được | `PipelineError` | `Thư mục đầu ra là một file: <p>` / `Không tạo được thư mục đầu ra <p>: <lỗi>` | ERROR |
| Không mở được `run.log` | `PipelineError` | `Không ghi được run.log: <lỗi>` | — |
| Đích là file / thư mục không phải của tool | `PipelineError`, trước việc nặng | xem 5.7 | ERROR |
| Đường dẫn quá dài (Windows) | `PipelineError`, trước việc nặng | xem 5.8 | ERROR |
| Không đổi tên được thư mục cũ (file đang mở) | `PipelineError`, giữ thư mục cũ, xóa tạm | `Không thay thế được thư mục kết quả cũ <p> (có file đang mở?): <lỗi>` | ERROR |
| Không đưa được thư mục tạm vào chỗ thư mục cũ | `PipelineError` (`OSError`) hoặc ném lại nguyên; khôi phục thư mục cũ, xóa tạm | `Không thay thế được thư mục kết quả cũ <p>: <lỗi>` | ERROR |
| Không tạo được thư mục tạm | `PipelineError`, không có file mới trong `<out>` | `Không tạo được thư mục tạm trong <out>: <lỗi>` | ERROR |
| Không đổi tên được thư mục tạm thành đích (đích chưa có) | `PipelineError`, xóa tạm | `Không đổi tên thư mục tạm thành <p>: <lỗi>` | ERROR |
| Lỗi git / snapshot / ghi zip / báo cáo giữa chừng | ném lại nguyên exception (`GitError`, `SnapshotError`, `ReportError`…), xóa tạm | thông báo của module gây lỗi | `logger.exception` (đã che token) |
| `KeyboardInterrupt`, callback `progress` ném lỗi | ném lại, xóa tạm | — | `logger.exception` |
| Không xóa được thư mục cũ sau khi thay | tiếp tục, trả kết quả | — | WARNING |
| `context` không khớp request | `ValueError` (lỗi lập trình) | — | — |

## 8. Bảo mật, hiệu năng, tái lập
- **Token:** không có trong request / context / result; không truyền vào hàm nào của pipeline ngoài `make_resolver` và `run_log(secrets)`. `run.log` che token qua `_MaskingFormatter` (cả dạng base64); `GitError` đã che sẵn. `ReportData.repo = repo.source` (URL https có thông tin xác thực bị `normalize_source` từ chối). Mật khẩu trong `ssh://` / `git://` / `file://` / scp cũng bị từ chối (`git_repo` 5.3, 2026-10-25).
- **Hiệu năng (M5):** một `LineClassifier` chung (cache theo blob SHA) cho gán tác giả và mọi lần đếm; `plan_export(C_END)` một lần; mỗi zip đọc blob 2 lần (ghi + đếm) — chấp nhận, tối ưu ở M7. **(A21)** Bấm "Phân tích" lại với cùng `PeriodContext` (UI dùng lại qua `period_memo`), cùng bộ lọc và cùng resolver → không gán tác giả lại (kết quả không phụ thuộc user được chọn — attribution A1). CLI tạo `ctx` mới mỗi lần nên không dùng memo.
- **Tái lập:** thứ tự job theo `plan_end_exports`; cảnh báo theo 5.10 (tất định); zip start timestamp C_START, zip end C_END (theo `tz`); xlsx chuẩn hóa theo C_END (`report`); `generated_at` chỉ ở manifest; tên thư mục tạm không lọt vào file đầu ra; bảng do `report` sắp lại.
- **Windows:** `FileHandler` gỡ + đóng trong `finally`; `os.replace` không đè thư mục đã có → đổi tên thư mục cũ trước (5.9); kiểm độ dài đường dẫn (5.8); LOC đếm từ nội dung (D36) nên `A.py`/`a.py`, `CON.py` vẫn được đếm.

## 9. Test cases
Fixture: `section14_repo` (thêm tham số tên repo nguồn để thư mục là `repo_…`, + `identities.yaml` gộp `alice@example.com`→`alice`, `bob@example.com`→`bob`), kỳ 2026-01-01..2026-01-31 `Asia/Bangkok`; `cache_root`; `FakeSession` (`test_identity.py`); `GitRepo(bare, "https://github.com/org/repo", TOKEN)` không mạng (mẫu `test_git_repo.py`); repo ca lệch (đổi tên `.txt`→`.py`), repo có `A.py`/`a.py` (`add_index_entry`), repo có `CON.py`/`a.py.` (`core.protectNTFS=false`). Mặc định chạy trong `run_log(out_root)`.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-pipeline-01 | §14 tất cả user | `users=None` | `loc_start 10`, `loc_end 20`; alice `5/2/+3`, bob `8/1/+7`; `cross_check.diff_percent == 0`, `ok`; không cảnh báo `cross_check`; thư mục `repo_main_2026-01-01_2026-01-31_all`; `data.exports` = start + end (`accounts None`, tag `all`); `all_users True`, `users == ("alice","bob")` (admin không có commit trong kỳ) | integration |
| TC-pipeline-02 | Chỉ alice | `users=("alice",)` | 10/13; `end_2026-01-31_alice.zip` không có `util.py`; thư mục `…_alice`; `user_rows` chỉ alice; `all_users False`, `options.selected_users == ("alice",)` | integration |
| TC-pipeline-03 | Chỉ bob | `("bob",)` | 10/17; `app.py` trong zip không có thay đổi của alice | integration |
| TC-pipeline-04 | alice + bob | `("bob","alice")` | 10/20; tag `multi-2users`, thư mục `…_multi-2users`; `app.py`, `util.py` trong zip trùng byte với C_END; `selected_users == ("alice","bob")` | integration |
| TC-pipeline-05 | Xuất riêng | alice + bob, `separate_users=True`; biến thể 1 user | 3 zip end theo thứ tự `multi-2users`, `alice`, `bob`; `exports` role `end`, `separate`, `separate`; số liệu chính = bản gộp (10/20); zip riêng `loc` 13 / 17, kiểm tra chéo riêng đạt; `end_zips` cùng thứ tự; 1 user + xuất riêng → chỉ 1 zip end | integration |
| TC-pipeline-06 | "Tất cả" + bot | `section14_repo(bot=True)`: (a) không loại bot + xuất riêng; (b) `exclude_bots`; (c) repo không bot + `exclude_bots` | (a) có zip riêng của bot, `users` gồm bot; (b) không có zip bot, end dựng bằng builder (`accounts` = account không phải bot), `user_rows` không có bot, tag `all`, kiểm tra chéo đạt; (c) `exports[1].accounts is None` (C_END, D21) | integration |
| TC-pipeline-07 | Đủ file §12 | TC-01 | `start_2026-01-01_<sha7>.zip`, `end_2026-01-31_all.zip`; `sheetnames == [Tong_quan, Theo_ngon_ngu, Theo_user, Theo_file, Theo_tuan, Canh_bao]`; 3 CSV bắt đầu `EF BB BF`; `warnings.csv`; `manifest.json` đủ key §12; `<out>/run.log` tồn tại, không nằm trong thư mục kết quả; không còn `.loc-tmp-*` / `.loc-old-*` trong `<out>` | integration |
| TC-pipeline-08 | Tái lập | chạy 2 lần vào 2 `out_root` khác nhau, `now` khác nhau | mọi file trong thư mục kết quả trùng SHA-256 trừ `manifest.json`; manifest bằng nhau sau khi bỏ `generated_at` | integration |
| TC-pipeline-09 | Chạy lại cùng `out` | lần 1 rồi thêm file lạ vào thư mục kết quả, chạy lần 2 | thư mục bị thay hoàn toàn (file lạ biến mất), nội dung giống lần 1 trừ `generated_at`; không còn `.loc-old-*` | integration |
| TC-pipeline-10 | Đích không phải của tool | thư mục đích có sẵn: (a) không có manifest, (b) manifest hỏng JSON, (c) manifest thiếu `exports`; (d) đích là file | `PipelineError` tiếng Việt chứa đường dẫn; thư mục / file cũ nguyên vẹn; spy: `attribute_period`, `plan_export` không được gọi; không còn `.loc-tmp-*` | integration |
| TC-pipeline-11 | Thư mục cũ đang mở (Windows, `skipif` khác nt) | lần 1; mở một file trong thư mục kết quả; chạy lần 2 | `PipelineError` "Không thay thế được thư mục kết quả cũ…"; thư mục cũ còn đủ file; không còn `.loc-tmp-*` | integration |
| TC-pipeline-12 | Lỗi giữa chừng | monkeypatch `write_reports` ném `ReportError`; biến thể `KeyboardInterrupt` trong `build_user_export`; có thư mục kết quả cũ | exception ném lại đúng loại; thư mục cũ nguyên vẹn (không có đích mới); không còn `.loc-tmp-*`; `run.log` có dòng ERROR kèm traceback | integration |
| TC-pipeline-13 | `out_root` | chưa tồn tại (lồng 2 cấp); là file | tạo được và chạy xong; là file → `PipelineError` "Thư mục đầu ra là một file" (cả `run_log` và `run_analysis`) | integration |
| TC-pipeline-14 | C_START rỗng | start 2025-01-01 | `start_2025-01-01_empty.zip` không có entry; `loc_start 0`; manifest `c_start` null; `data.c_start is None`; kiểm tra chéo đạt; admin trong `users` | integration |
| TC-pipeline-15 | Không có commit trong kỳ | kỳ không chứa commit nào (sau commit trước start, trước commit trong kỳ đầu tiên) | "Tất cả": `users == ()`, `user_rows == ()`, `loc_end == loc_start`, kiểm tra chéo đạt, `Theo_tuan` chỉ tiêu đề; chọn alice → `PipelineError` "Không có user nào có commit trong kỳ" | integration |
| TC-pipeline-16 | `match_users` | `UserSummary` giả: `alice`, `Bob`, `x[bot]`; yêu cầu `ALICE`; `zz`; `bob` khi có cả `Bob` và `BOB`; `("alice","alice")`; `("Bob",)` khi có `Bob` và `bob`; `()`; 26 user + `zz` | casefold khớp → `("alice",)`; `zz` → lỗi liệt kê user theo thứ tự; mơ hồ → lỗi "khớp nhiều account"; trùng → một; khớp chính xác thắng casefold; `()` → "Chưa chọn user nào."; danh sách cắt 20 + `… và 6 user khác` | unit |
| TC-pipeline-17 | Bot chọn tường minh + `exclude_bots` | `section14_repo(bot=True)`, `users=(<bot>,)`, `exclude_bots=True` | bot được chọn, export dựng bằng builder cho bot | integration |
| TC-pipeline-18 | Không có dữ liệu trước end | kỳ 2020-01-01..2020-01-31 | `SnapshotError` "Không có dữ liệu trong khoảng thời gian"; `out_root` chỉ có `run.log` | integration |
| TC-pipeline-19 | Kiểm tra chéo lệch | repo ca lệch (đổi tên `.txt`→`.py` trong kỳ) | không ném lỗi; `warnings.csv` có hàng `cross_check` chứa hai giá trị, phạm vi `kiểm tra chéo`; manifest `cross_check.ok == false` | integration |
| TC-pipeline-20 | Gộp cảnh báo | repo có file source quá lớn (`max_file_size_kb` nhỏ) không đổi trong kỳ; (a) tất cả; (b) alice+bob xuất riêng | (a) đúng một `ReportWarning` cho file đó với `scopes == ("start", "end:all")`; (b) `scopes` gồm `start`, `end:multi-2users`, `end:alice`, `end:bob`; thứ tự `data.warnings` tất định (chạy 2 lần bằng nhau) | integration |
| TC-pipeline-21 | `IDENTITY` | `GitRepo` https + token giả; `make_resolver(..., login_cache=tmp)` với `FakeSession` trả 403; `run_analysis` | `data.warnings` có `identity`, path `""`, phạm vi `("định danh",)`; resolver được dùng (`requests_made ≥ 1`) | integration |
| TC-pipeline-22 | `PATH_CONFLICT` start / `all` (A13) | `A.py` + `a.py` (qua `add_index_entry`) trước start | `path_conflict` cho cả 2 path, phạm vi `start` và `end:all`; cả hai file trong zip và được đếm (`files` có cả hai) | integration |
| TC-pipeline-23 | `WINDOWS_PATH` (D39) | `CON.py`, `a.py.` trong repo; "Tất cả" và chọn user | có `windows_path` cho mỗi path ở mọi phạm vi export chứa file; file vẫn trong zip và được đếm | integration |
| TC-pipeline-24 | LOC đếm từ nội dung (D36, mục E) | §14, chọn alice và tất cả | `ExportSummary.loc` = đếm lại từ zip (đọc entry) = `count_directory` trên thư mục giải nén | integration |
| TC-pipeline-25 | Token không lộ (mục E) | như TC-21 + log một dòng chứa token và dạng base64 `x-access-token:<t>` trong `run_log(secrets=(TOKEN,))`; gây một `GitError` có token | không có token / base64 trong mọi file (kể cả nội dung đã giải nén các zip, xlsx giải nén) của thư mục kết quả, `run.log` (có `***`), `config` của repo cache, `github_logins.json`; `fields()` của `AnalysisRequest`, `PeriodContext`, `AnalysisResult` không có tên chứa `token`/`secret`/`auth`/`password` | integration |
| TC-pipeline-26 | Tiến độ | callback ghi các lần gọi; biến thể callback ném `RuntimeError` ở bước 3 | 5 lần gọi đúng thứ tự `EXPORT_START, ATTRIBUTION, EXPORT_END, COUNT, REPORT`, `(i, 5)` với i = 1..5; `STEP_LABELS` đúng 5 nhãn tiếng Việt; biến thể: `RuntimeError` ném lại, không còn `.loc-tmp-*`, không có thư mục đích | integration |
| TC-pipeline-27 | `run_log` | chạy 2 lần; root logger WARNING, logger `loc_counter` NOTSET; một luồng khác ghi log trong lúc `with`; biến thể hai luồng lồng thời gian (A vào, B vào, A ra, B ghi INFO, B ra — đồng bộ bằng `threading.Event`, hai `out_root` khác nhau) | chỉ còn log lần sau; UTF-8; có dòng INFO `C_START=`; không có dòng của luồng khác; sau `with`: handler đã gỡ, level logger `loc_counter` như cũ, xóa được `run.log` ngay (Windows); biến thể: `run.log` của B có dòng INFO ghi sau khi A ra, sau khi cả hai ra level logger là NOTSET | unit |
| TC-pipeline-28 | `result_dir_name` | nguồn `https://github.com/org/repo.git`, `git@github.com:org/Repo.GIT`, `file:///D:/x/r`, `D:\x\r\`, `/home/u/r/.git`; nhánh `feature/x`; repo / nhánh 50 ký tự; start 08:30, end 23:59 (≡ không giờ), end 17:30 | `repo`, `Repo`, `r`, `r`, `r`; `feature_x`; phần dài cắt đúng 40 ký tự `…-<6 hex>` = sha1 chuỗi gốc; `2026-01-01T0830_2026-01-31`; `…_2026-01-31T1730_…` | unit |
| TC-pipeline-29 | Resolver dùng chung | spy `summarize_users`, `attribute_period`; `FakeSession` đếm request | cùng một instance resolver; mỗi email tra API đúng một lần | integration |
| TC-pipeline-30 | `prepare_period` + `context` | gọi `prepare_period` rồi `run_analysis(context=ctx)`; biến thể `context` khác nhánh | không gọi lại `find_snapshots`/`log_commits` (spy); kết quả như TC-01; khác nhánh → `ValueError` | integration |
| TC-pipeline-31 | `AnalysisResult` | TC-05 | mọi đường dẫn tồn tại trong `out_dir`; `end_zips` cùng thứ tự `data.exports[1:]`; `report_files` đúng 7 tên (có `loc_by_pr.csv`); `period_users` đủ account; manifest khớp `data` (`totals`, `exports`) | integration |
| TC-pipeline-32 | Múi giờ trong config (A10) | `period` UTC, `config.timezone = Asia/Bangkok` | manifest `config.timezone == "UTC" == timezone`; timestamp entry zip theo UTC | integration |
| TC-pipeline-33 | Độ dài đường dẫn (A9) | monkeypatch hàm kiểm giới hạn → chưa bật; `out_root` dài ~230 ký tự; biến thể long path đã bật; đọc registry bằng `winreg` giả (`LongPathsEnabled` = 1, = 0, lỗi đọc) và `os.name` khác `nt` | `PipelineError` "Đường dẫn kết quả quá dài" trước `attribute_period` (spy), không tạo `.loc-tmp-*`; biến thể bật → không kiểm; registry: 1 → bật, 0 / lỗi → chưa bật; không phải `nt` → không áp giới hạn | unit |
| TC-pipeline-34 | Timestamp zip | TC-01 | entry zip start mang committer date C_START, zip end mang C_END theo `Asia/Bangkok` | integration |
| TC-pipeline-36 | Nhánh lỗi hệ thống tệp (mục 7) | monkeypatch: `mkdir` của `out_root` lỗi; `FileHandler` lỗi; `mkdir` thư mục tạm lỗi; `os.replace(tmp, final)` lỗi khi đích chưa có; có thư mục cũ và `os.replace(tmp, final)` lỗi (`OSError`, `KeyboardInterrupt`); `shutil.rmtree(old)` lỗi | `PipelineError` đúng thông báo mục 7 (lần lượt "Không tạo được thư mục đầu ra", "Không ghi được run.log", "Không tạo được thư mục tạm", "Không đổi tên thư mục tạm thành"); thư mục cũ được khôi phục nguyên vẹn (`OSError` → `PipelineError` "Không thay thế được thư mục kết quả cũ", `KeyboardInterrupt` ném lại nguyên); không còn `.loc-tmp-*`; rmtree lỗi → vẫn trả kết quả, log WARNING "Không xóa được thư mục cũ"; biến thể khôi phục `os.replace(old, final)` cũng lỗi → thông báo và log ERROR chứa đường dẫn `.loc-old-*`, dữ liệu cũ còn trong đó | unit |
| TC-pipeline-37 | Kiểm tra chéo lệch hệ thống: thư mục loại / symlink (D40-N6) | c0: `app.py`, `lib.py` (10 dòng code mỗi file); trong kỳ alice (a) `git mv lib.py vendor/lib.py`; (b) thay `lib.py` bằng symlink 120000 trỏ `app.py` | cả hai: không ném lỗi; `cross_check` = `(20, 0, 10)`, `ok` false, `diff_percent` 100.0; alice `net_code` 0; đúng một cảnh báo `cross_check` phạm vi `kiểm tra chéo`; manifest `cross_check.ok == false`; export end không có `vendor/lib.py` / `lib.py` | integration |
| TC-pipeline-38 | Dùng lại kết quả gán tác giả (A21) | repo §14; `ctx = prepare_period(...)`; spy `pipeline.attribute_period`; chạy `run_analysis(context=ctx)` lần lượt: (1) mọi user; (2) chọn `alice` (cùng filters, cùng resolver); (3) `count_docstrings` khác; (4) resolver mới (cùng filters như 3); mỗi lần `out_root` riêng | spy gọi ở (1), (3), (4) — **không** gọi ở (2); `run.log` của (2) có `Dùng lại kết quả gán tác giả đã tính cho kỳ này`, của (1), (3), (4) thì không; lần (2) bằng một lần chạy (2) với ctx mới: `ReportData` bằng nhau, mọi file kết quả trùng SHA-256 (kể cả manifest, cùng `now`); `len(ctx.attribution_memo) == 1`; `PeriodContext` 5 tham số vị trí vẫn dựng được, hai ctx khác memo vẫn bằng nhau; `dataclasses.replace(ctx)` có memo rỗng; memo không giữ tham chiếu mạnh tới resolver (resolver bị thu hồi → weakref chết → tính lại) | integration |
| TC-pipeline-39 | Log của luồng con vào `run.log` (A22) | trong `with run_log(...)`: (a) phát WARNING từ `ThreadPoolExecutor` với `contextvars.copy_context().run`; (b) phát WARNING từ `threading.Thread` thường; (c) chạy `attribute_period` trên repo TC-attribution-11 với `MAX_MERGE_DEPTH = 0`, `ATTRIBUTION_WORKERS = 4`; (d) hai phiên `run_log` lồng ở hai luồng khác nhau, mỗi phiên một luồng con có context | (a) có trong `run.log`; (b) không có; (c) `run.log` có `Vượt giới hạn đệ quy merge`; (d) mỗi `run.log` chỉ có log của phiên mình; sau `with`, `_RUN_LOG_ID` trở về như trước (ở luồng chính và trong từng luồng phiên); (e) `__enter__` trong một context, `__exit__` ở context khác → không ném lỗi, handler đã gỡ, level logger khôi phục, `run.log` xóa được | unit + integration |
| TC-pipeline-40 | Chế độ gán `last_commit` (A23) | repo §14 + identities: (a) `AnalysisRequest(attribution_mode="last_commit")`, tất cả user → 10/20, cross_check 0, `manifest.options.attribution_mode == "last_commit"`; (b) `--user alice` → 10/10, `--user bob` → 10/20; (c) spy `attribute_period` nhận `mode`; hai lần chạy cùng `ctx` khác mode → gọi lại (memo khóa theo mode); (d) `mode` lạ → `ValueError` | integration |
| TC-pipeline-41 | Cách tính LOC end (A24) | repo §14 + identities, tất cả user: (a) mặc định; (b) `AnalysisRequest(loc_end_mode="added_code")`; (c) giá trị lạ | (a) `data.options.loc_end_mode == "net_code"`, `reported_loc_end == 20`; (b) `data.loc_end == 20` (đếm trên export), `reported_loc_end == 23` (10 + 13), cross_check như (a) (`ok`, lệch 0); manifest `totals.loc_end == 20`, `reported_loc_end == 23`, `options.loc_end_mode == "added_code"`; zip, `Theo_ngon_ngu` / `Theo_file` / CSV trùng SHA-256 với (a); `run.log` có `LOC end theo code thêm`; spy `attribute_period` không bị gọi lại khi chỉ đổi mode này trên cùng `ctx`; (c) `ValueError`, chưa tạo thư mục kết quả | integration |
| TC-pipeline-42 | LOC theo PR (M8, D43) | repo: base trước kỳ; nhánh `feat` (bob thêm `b.py` 4 dòng, alice thêm `c.py` 2 dòng); main: alice thêm 3 dòng `app.py`; merge `Merge pull request #7 from o/feat` (body `Thêm b.py`, author carol); alice `Sửa lỗi (#9)` thêm 1 dòng; tất cả user | `data.pr_rows` = (7, alice, 1, 2, 0), (7, bob, 1, 4, 0), (9, alice, 1, 1, 0), (None, alice, 1, 3, 0); `report_files` có `loc_by_pr.csv`; sheet `Theo_PR` 5 hàng (tiêu đề + 4), hàng PR 7 có tiêu đề `Thêm b.py` và ngày `2026-01-06`; Σ theo PR của từng account = `user_rows` (commit, thêm, xóa); chạy 2 lần → `loc_by_pr.csv` trùng SHA-256 | integration |
| TC-pipeline-35 | `make_resolver` | nguồn GitHub + token; GitHub không token; nguồn local + token | `github` là `GitHubLoginResolver` (cache = `login_cache`); `None`; `None` | unit |

Phủ mandatory-tests: mục D (kiểm tra chéo §8.3) — TC-01..04, 19; mục E — TC-07, 08, 24, 25, 28 (+ tên thư mục / user-tag TC-01..05).

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | `run.log` gắn qua context manager `run_log(out_root, secrets)` do CLI / UI bọc **cả** `GitRepo.open` (để lỗi clone/fetch vào log, §15); `run_analysis` không tự gắn handler | Phân tích N1 (a) | Chốt (*) |
| A2 | Che token trong `run.log` bằng formatter gọi `git_repo.mask_secrets` (không thêm API công khai cho `GitRepo`) | N2 (a) | Chốt (*) |
| A3 | `make_resolver` công khai cho CLI / UI; cảnh báo `IDENTITY` lấy từ `resolver.github.warnings` sau gán tác giả | N3 | Chốt (*) |
| A4 | Khớp user (D40-N19) đặt trong pipeline (`match_users`) vì danh sách user trong kỳ chỉ có ở đây; CLI truyền giá trị thô, UI truyền account chính xác; bỏ khoảng trắng, bỏ trùng, sắp tăng dần | N4 | Chốt (*) |
| A5 | "Có nhập giờ" (D40-N10) suy từ `Period`: start ≠ 00:00:00 / end ≠ 23:59:59, từng phía (khớp D10: `23:59` ≡ không nhập) | N5 (a) | Chốt (*) |
| A6 | `<repo>` = đoạn cuối của nguồn (tách `/ \ :`, bỏ `.git`); cắt > 40 ký tự thành 33 + `-` + sha1[:6]; trùng tên thư mục do `safe_name` / hoa thường → chấp nhận, ghi README | N6 | Chốt (*) |
| A7 | Thay thế thư mục: kiểm đích sớm; dựng trong `<out>/.loc-tmp-<pid>-<hex8>`; đổi tên thư mục cũ thành `.loc-old-…` rồi `os.replace` (Windows không cho `os.replace` đè thư mục, `rmtree` khi có file mở xóa dở dang — đã thử) | N7 | Chốt (*) |
| A8 | "Thư mục kết quả của tool" = có `manifest.json` parse được thành dict có `tool_version`, `c_end`, `exports` | N8 | Chốt (*) |
| A9 | Kiểm độ dài đường dẫn trước việc nặng chỉ khi Windows chưa bật long path (máy hiện tại `LongPathsEnabled = 0`) | N9 (a) | Chốt (*) |
| A10 | `ReportData.config = replace(config, timezone=period.timezone)` — manifest ghi múi giờ thực dùng | N10 | Chốt (*) |
| A11 | Kiểm tra chéo zip riêng dùng `net_code` của account đó trong `user_rows` của export chính (cùng `user_metrics`) | Khuyến nghị | Chốt (*) |
| A12 | Thứ tự gộp cảnh báo: start → gán tác giả → end theo job → kiểm tra chéo → định danh; khử trùng `(kind, path, message)`, giữ lần đầu, gộp phạm vi | N11 | Chốt (*) |
| A13 | Tiến độ: `progress(step, i, 5)` lúc bắt đầu bước; phần chuẩn bị tính vào bước 1; không có API hủy ở M5 (callback ném lỗi = dừng + dọn) | N12 | Chốt (*) |
| A14 | API hai pha cho UI: `prepare_period` → `PeriodContext`, `run_analysis(context=…)` dùng lại (§10.2 [2][3] cần C_START/C_END và user trước khi bấm Phân tích) | N15 | Chốt (*) |
| A15 | `generated_at` tính một lần ở bước 5 (`now` tiêm được cho test), dùng cho manifest và `AnalysisResult` | N14 | Chốt (*) |
| A16 | `run_log` chỉ ghi record của luồng đã vào `with` (nhiều phiên Streamlit song song ở M6) | N19 | Chốt (*) |
| A17 | Exception mới `PipelineError(LocCounterError)` cho lỗi riêng của pipeline; lỗi của module khác ném nguyên | Khuyến nghị | Chốt (*) |
| A18 | Level logger `loc_counter` chỉnh theo đếm tham chiếu có khóa (phiên đầu vào đặt INFO, phiên cuối ra khôi phục) — tránh phiên ra trước làm mất log INFO của phiên còn lại (review 2026-10-25, Major) | Khuyến nghị review | Chốt (*) |
| A19 | Lỗi `mkdir` thư mục tạm và `os.replace(tmp, final)` (đích chưa có) → `PipelineError` tiếng Việt; lỗi bất kỳ giữa hai lần đổi tên → khôi phục thư mục cũ trước khi ném | Khuyến nghị review | Chốt (*) |
| A20 | Hai phiên cùng `out_root` cùng ghi một `run.log` (`mode="w"`) → file hỏng. M5 (CLI một phiên) chấp nhận, ghi README; cách xử lý cho nhiều phiên Streamlit quyết ở M6 (PLAN Q46) | Khuyến nghị review | Chốt cho M5 (*), mở cho M6 |

| A21 | Memo gán tác giả gắn vào `PeriodContext` (vòng đời theo memo kỳ của UI; mỗi memo gắn với đúng một ctx — `init=False` nên `replace` không chia sẻ memo), khóa `FilterConfig` (gồm `count_docstrings` → classifier) + đồng nhất resolver qua **weakref** (`ref() is resolver`: không trùng `id()` sau thu hồi, ctx không giữ token); giữ 1 phần tử | Khuyến nghị (đề xuất tăng tốc 2026-10-28 mục 2) | Chốt 2026-10-29 (**) |
| A22 | Lọc `run.log` theo luồng **hoặc** `ContextVar` của phiên, để log của luồng gán tác giả song song (attribution R20) không bị mất | Khuyến nghị | Chốt 2026-10-29 (**) |
| A23 | `attribution_mode` đi qua `AnalysisRequest` → `attribute_period(mode=…)` và `ReportOptions.attribution_mode` (manifest). Memo A21 khóa theo `(filters, mode)`: đổi chế độ thì tính lại. TC-pipeline-40 | Khuyến nghị (ủy quyền 2026-10-30) |
| A24 | `loc_end_mode` (report A15) đi qua `AnalysisRequest` → `ReportOptions.loc_end_mode`; pipeline **không** đổi `loc_end` / `check` / `exports` (vẫn đếm trên export) — `ReportData` tự suy ra `reported_loc_end`. Không ảnh hưởng gán tác giả nên memo A21 không khóa theo mode này. TC-pipeline-41 | Khuyến nghị (ủy quyền 2026-10-23) |

(**) Người dùng chọn "Làm 1,2" (2026-10-29); duyệt theo ủy quyền làm theo khuyến nghị.

(*) Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-23 ("trường hợp có hỏi xác nhận thì thực hiện theo recommend"); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-29 | `PeriodContext.attribution_memo` + 5.6 bước 12 dùng lại kết quả gán tác giả (A21); 5.5 bước 3 lọc `run.log` theo luồng hoặc `ContextVar` phiên (A22); mục 8; TC-38, 39. `reviewed` → `approved` | Đề xuất tăng tốc mục 2 (attribution R20 song song) |
| 2026-10-29 | Test pass (TC-38, 39; toàn bộ 761; coverage `pipeline.py` 99 %) → `implemented`; chưa review | /feature-test |
| 2026-10-29 | Sửa theo review `reviews/pipeline-20261029.md` (PASS_WITH_NOTES): memo `init=False` + weakref resolver (Minor 2, ghi chú spec 1–2); thứ tự `finally` của `run_log`, `reset` bọc `suppress(ValueError)` (Minor 1, ghi chú 5); TC-38 so `ReportData` + manifest + log (Minor 3); TC-39 (d)(e) (Nit 1, Minor 1). Không đổi kết quả. `implemented` → `approved` (duyệt theo ủy quyền làm theo khuyến nghị; người dùng yêu cầu chạy review và xử lý) | Review pipeline |
| 2026-10-29 | Test pass (50 test pipeline; toàn bộ 768; coverage 99 %). Review PASS_WITH_NOTES, mọi Minor + Nit 1 đã sửa → `reviewed` | /feature-test, /feature-review |
| 2026-10-25 | Theo review `reviews/pipeline-20261025.md`: 5.5 bước 4–5 đếm tham chiếu level logger (A18); 5.6 bước 9, 5.9 bọc lỗi thư mục tạm / đổi tên, khôi phục thư mục cũ với mọi lỗi giữa hai lần đổi tên (A19); 5.6 bước 19 thứ tự log + kiểm tra chéo từng zip riêng; mục 7 thêm 3 dòng; TC-16 sửa "25" → "26 user" (khớp "… và 6 user khác"); TC-27, TC-33 mở rộng; thêm TC-36; A20 (`run.log` dùng chung, PLAN Q46). Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | review FAIL (Major + Minor) |
| 2026-10-25 | Mục bảo mật: bỏ ghi chú tồn đọng `ssh://user:pass` (đã xử lý ở `git_repo` 5.3) — chỉ cập nhật tài liệu, không đổi hành vi pipeline | Tồn đọng M5 |
| 2026-10-25 | TC-37: ca lệch kiểm tra chéo vendor/ và file→symlink (fixture PLAN M5) — chỉ thêm test, không đổi hành vi | Tồn đọng M5 |
| 2026-10-25 | 5.9: khôi phục thư mục cũ lỗi → log ERROR + thông báo nêu đường dẫn `.loc-old-*`; TC-36 thêm biến thể. Chốt theo khuyến nghị, người dùng ủy quyền | review r2 Minor |
| 2026-10-24 | Tạo mới theo PLAN M5 (phạm vi `pipeline`, D11, D13, D21, D31, D35–D40) + phân tích `spec-analyst` (N1–N19, API thực tế các module; thử nghiệm `os.replace`/`rmtree` trên Windows, `LongPathsEnabled`). A1–A17 chốt theo khuyến nghị, người dùng ủy quyền → `approved` | M5 (`/feature-spec pipeline`) |
| 2026-10-30 | `AnalysisRequest.attribution_mode`, truyền vào `attribute_period` và `ReportOptions`, memo khóa theo `(filters, mode)` (A23, TC-40) | Người dùng yêu cầu lựa chọn "Gán tác giả cho commit cuối cùng" (thuật toán đơn giản). Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | Yêu cầu mới |
| 2026-10-30 | Test pass (mode last_commit: TC-attribution-49/50, builder-32, pipeline-40, screen-input-25, cli-analyze-26; toàn bộ 779 test, ruff sạch, coverage 99 %) → `implemented`; chưa review | /feature-test |
| 2026-10-30 | `AnalysisRequest.loc_end_mode` (`net_code` mặc định / `added_code`), kiểm hợp lệ, truyền vào `ReportOptions`, log INFO ở mode `added_code` (A24, TC-41) | Người dùng yêu cầu "LOC end cho chọn cách tính theo added code hoặc net code". Chốt theo khuyến nghị, người dùng ủy quyền → `approved` |
| 2026-10-30 | Test pass (tổng code thêm / xóa + cách tính LOC end: TC-report-26, pipeline-41, cli-analyze-27, screen-input-26, screen-result-15; toàn bộ 784 test, ruff sạch, coverage 99 %) → `implemented`; chưa review | /feature-test |
| 2026-10-30 | Theo review `reviews/loc-end-mode-20261030.md` (PASS_WITH_NOTES): TC-41 theo manifest mới (`totals.loc_end` = LOC đếm trên export, `reported_loc_end`) | /feature-review |
| 2026-10-30 | M8 (D43): bước 16 thêm `pr_rows = pr_metrics(attr, commits, counted, tz)`, bước 22 truyền `pr_rows` vào `ReportData`; danh sách file đầu ra (mục 1/5) thêm `loc_by_pr.csv` (7 tên trong `report_files`, kiểm độ dài đường dẫn); TC-31 cập nhật, TC-42. Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | PLAN M8, D43 |
| 2026-10-30 | Test pass sau sửa theo review (toàn bộ 784 test, ruff sạch, coverage 99 %). Review PASS_WITH_NOTES (`reviews/loc-end-mode-20261030.md`), Minor 1 + Nit đã sửa → `reviewed` | /feature-review |
