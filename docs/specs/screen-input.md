---
id: screen-input
title: Màn hình nhập (repo, thời điểm, chọn user, tùy chọn nâng cao, nút Phân tích)
type: screen
milestone: M6
modules: [src/loc_counter/app.py]
tests: [tests/test_app_input.py]
spec_refs: ["3.1", "3.3", "3.5", "9", "10.1", "10.2", "12", "15", "16"]
depends_on: [config, git_repo, snapshot, identity, pipeline, cli-analyze]
status: reviewed
---

# Màn hình nhập

## 1. Mục đích & phạm vi
Khung ứng dụng Streamlit `src/loc_counter/app.py` (chạy bằng `uv run streamlit run src/loc_counter/app.py`) và phần **nhập** của §10.1: khối [1] Repository, [2] Thời điểm thống kê, [3] Chọn user (trừ bảng gộp account), tùy chọn nâng cao, thư mục đầu ra, nút **PHÂN TÍCH**, thanh tiến độ, khóa ô nhập khi chạy. Toàn bộ nghiệp vụ dùng API công khai của `pipeline` (`make_resolver`, `prepare_period`, `run_log`, `run_analysis(context=…)`) — UI không tự tính LOC.

Ngoài phạm vi:
- Hiển thị kết quả §10.3, nút tải → spec `screen-result` (hàm `render_result(result, stale)` do spec đó định nghĩa; trước khi có, màn hình chỉ hiện dòng "Phân tích xong").
- Nút "Quản lý gộp account" + bảng sửa account key → spec `screen-identity` (hàm `render_identity_panel(...)`); spec này chỉ có ô đường dẫn `identities.yaml` và việc nạp file.
- Hủy giữa chừng (pipeline A13), song song nhiều tiến trình (README).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Bố cục: tiêu đề "ĐẾM LOC SOURCE CODE"; khối [1] REPOSITORY, [2] THỜI ĐIỂM THỐNG KÊ, [3] CHỌN USER, "Tùy chọn nâng cao (bộ lọc file, docstring, test, chế độ export)", nút PHÂN TÍCH | §10.1 |
| R2 | Ô repo (URL hoặc đường dẫn local), ô GitHub token (tùy chọn, ẩn), nút "Tải repo" → clone bare vào `~/.loc_counter/repos/<hash>`, đã có thì fetch | §10.2 [1] |
| R3 | Token chỉ giữ trong session; không ghi log, file cấu hình, báo cáo | §10.2 [1], §12, §15 |
| R4 | Dropdown nhánh: nhánh của repo, mặc định nhánh mặc định; spinner khi tải; lỗi rõ ràng khi URL sai / không có quyền | §10.2 [1] |
| R5 | Hai date picker (web UI **không** có ô giờ và ô múi giờ — A17); mặc định start = ngày đầu tháng hiện tại, end = hôm nay; múi giờ `Asia/Bangkok` (hoặc theo file cấu hình đã nạp) | §10.2 [2], §3.1 |
| R6 | Đổi start / end / nhánh → tự tính lại C_START, C_END, hiển thị hash ngắn, ngày commit, tiêu đề commit | §10.2 [2] |
| R7 | `start < end`; sai → lỗi và vô hiệu hóa nút Phân tích | §10.2 [2], §3.1 |
| R8 | Radio "Tất cả user" (mặc định) / "Chọn user"; danh sách account đã gộp có commit trong kỳ, sắp số commit giảm dần, hiện số commit; cập nhật khi đổi thời điểm / nhánh | §10.2 [3] |
| R9 | "Chọn user": bắt buộc ≥ 1 user, có ô tìm kiếm | §10.2 [3] |
| R10 | Bot hiện trong danh sách; "Loại trừ bot" (mặc định tắt); "Xuất riêng từng user" (mặc định tắt) | §3.3, §3.5, §16 |
| R11 | Tùy chọn nâng cao: bộ lọc §9 với mặc định §9 | §9 |
| R12 | Bấm Phân tích: chạy pipeline, thanh tiến độ theo bước; khóa các ô nhập trong lúc chạy | §10.2 |
| R13 | Lỗi Git: thông báo tiếng Việt; log chi tiết vào `<out>/run.log` mức INFO | §15 |
| R14 | Tái lập: cùng tham số → cùng `AnalysisRequest` như CLI | §15 |

## 3. Giao diện

### 3.1 Bố cục
```
ĐẾM LOC SOURCE CODE                                                      (st.title)
[1] REPOSITORY                                                           (st.subheader)
  Repo (URL hoặc đường dẫn local): [______________________]   key repo_source
  GitHub token (tùy chọn, ẩn):     [••••••]                    key token (password)
  [ Tải repo ]                                                 key load_repo
  Nhánh: [ main ▼ ]                                            key branch
[2] THỜI ĐIỂM THỐNG KÊ
  Start: [2026-10-01]   End: [2026-10-25]                      keys start_date end_date
  → Snapshot start: a1b2c3d (2025-12-15 10:00)  "admin: app.py"
  → Snapshot end:   f9e8d7c (2026-01-08 10:00)  "bob del"
[3] CHỌN USER
  File identities: [identities.yaml]                           key identities_path
  (•) Tất cả user  ( ) Chọn user                               key user_mode
  Tìm user: [____]                       (chỉ khi Chọn user)    key user_query
  [x] alice (2 commit)  [ ] bob (2 commit) …                    key pick_<sha1(account)[:12]>
  Đã chọn 1 user
  [ ] Loại trừ bot   [ ] Xuất riêng từng user                  keys exclude_bots separate_users
  Cách gán tác giả: (•) Theo từng dòng  ( ) Theo commit cuối cùng   key attribution_mode
  Cách tính LOC end: (•) Theo code ròng  ( ) Theo code thêm         key loc_end_mode
  (khu vực của screen-identity)
▸ Tùy chọn nâng cao (bộ lọc file, docstring, test, chế độ export)   (st.expander)
  File cấu hình: [______] [ Nạp ]                              keys config_path load_config
  Thư mục loại trừ / Mẫu file loại trừ / Ngôn ngữ loại trừ / Loại file binary /
  Kích thước tối đa (KB) / Tính file test / Tính docstring / Chế độ export
Thư mục đầu ra: [output]                                       key out_dir
  (lý do chưa chạy được — st.info từng dòng)
                                         [ PHÂN TÍCH ]          key analyze
  ▓▓▓▓▓░░░ Bước 3/5: Export end…                               (st.progress)
  (lỗi lần chạy trước — st.error) | (kết quả — screen-result)
```

### 3.2 Thành phần
| Thành phần | Widget | Key session_state | Mặc định | Validate | Khi thay đổi |
|---|---|---|---|---|---|
| Repo | `text_input` | `repo_source` | `""` | `clean_source` ≠ rỗng mới bật "Tải repo" | khác nguồn đã tải → cảnh báo, repo coi như chưa tải (A11) |
| Token | `text_input(type="password", autocomplete="off")` | `token` | `""` | — | như trên |
| Tải repo | `button` | `load_repo` | — | disabled khi nguồn rỗng hoặc đang chạy | mở repo (5.2) |
| Nhánh | `selectbox(index=None, placeholder="Chọn nhánh")` | `branch` (+ bản sao `branch_value`, A15) | nhánh mặc định của repo (đặt khi tải) | phải chọn | tính lại kỳ |
| Start / End | `date_input(min_value=1970-01-01, max_value=2100-12-31, format="YYYY-MM-DD")` | `start_date`, `end_date` | `default_dates(now)` (A3) | `make_period` | tính lại kỳ |
| Giờ, múi giờ | *(không có widget — A17)* | `start_time`, `end_time` (luôn `None`), `tz` (state thuần) | `None`, `Asia/Bangkok` | `tz` thuộc `timezone_options()` (A14) | — |
| File identities | `text_input` | `identities_path` | `"identities.yaml"` | file có → `load_identities`; vắng → rỗng; rỗng ô → không dùng file; là thư mục → lỗi `Đường dẫn identities không phải file: <p>` | tính lại kỳ (map mới) |
| Chế độ user | `radio(["Tất cả user", "Chọn user"], horizontal=True)` | `user_mode` | `Tất cả user` | — | — |
| Tìm user | `text_input` | `user_query` | `""` | — | lọc danh sách (không tính lại kỳ) |
| User | `checkbox` mỗi account | `pick_<sha1(account)[:12]>` | theo `selected` | — | cập nhật `selected` (on_change) |
| Loại trừ bot | `checkbox` | `exclude_bots` | `False` | — | ẩn bot, bỏ bot khỏi `selected` |
| Xuất riêng | `checkbox` | `separate_users` | `False` | — | — |
| Cách gán tác giả | `radio` ngang, 2 lựa chọn `ATTRIBUTION_MODES` = ("Theo từng dòng (blame)", "Theo commit cuối cùng của file") | `attribution_mode` | lựa chọn đầu | — | đổi → `result` thành "cũ" (có trong `sig`) |
| Cách tính LOC end | `radio` ngang, 2 lựa chọn `LOC_END_MODES` = ("Theo code ròng (đếm trên export)", "Theo code thêm (LOC start + tổng code thêm)") | `loc_end_mode` | lựa chọn đầu | — | đổi → `result` thành "cũ" (có trong `sig`) (A19) |
| File cấu hình | `text_input` + `button("Nạp")` | `config_path`, `load_config` | `""` | `load_config`; `timezone` của file qua `canonical_timezone` (A14) | điền 8 ô nâng cao + `tz` (A6) |
| Thư mục loại trừ | `text_area` (mỗi dòng một mục) | `adv_exclude_dirs` | `DEFAULT_EXCLUDE_DIRS` | `form_config` | — |
| Mẫu file loại trừ | `text_area` | `adv_exclude_globs` | `DEFAULT_EXCLUDE_GLOBS` | `form_config` | — |
| Ngôn ngữ loại trừ | `text_area` | `adv_exclude_languages` | `DEFAULT_EXCLUDE_LANGUAGES` | `form_config` | — |
| Loại file binary | `checkbox` | `adv_exclude_binary` | `True` | — | — |
| Kích thước tối đa (KB) | `number_input(min_value=0, step=1)` | `adv_max_file_size_kb` | `1024` | `form_config` (≤ 0 → lỗi) | — |
| Tính file test | `checkbox` | `adv_include_tests` | `True` | — | — |
| Tính docstring | `checkbox` | `adv_count_docstrings` | `False` | — | — |
| Chế độ export | `radio(["source_only", "full"])` | `adv_export_mode` | `source_only` | — | — |
| Thư mục đầu ra | `text_input` | `out_dir` | `"output"` | không rỗng | — |
| PHÂN TÍCH | `button(type="primary", on_click=_request_run)` | `analyze` | — | disabled khi `analyze_blockers` khác rỗng hoặc đang chạy | 5.6 |

Trạng thái phi widget (`st.session_state`): `repo: GitRepo | None`, `loaded_with: tuple[str, str] | None` (nguồn đã làm sạch, token lúc tải), `repo_gen: int`, `branches: list[str]`, `repo_error: str | None`, `period_memo: dict` (tối đa 1 mục), `selected: set[str]`, `run_requested: bool`, `run_error: str | None`, `result: AnalysisResult | None`, `result_sig: tuple | None`. Khởi tạo một lần bằng `_init_state()` (chỉ đặt khóa chưa có).

### 3.3 Trạng thái màn hình
`idle` (chưa tải repo) → `loading` (đang mở repo — spinner) → `ready` (có repo + nhánh) → `computing` (đang `prepare_period` — spinner) → `ready` | `blocked` (có lý do chặn) → `running` (sau bấm Phân tích) → `done` (có `result`) | `error` (`run_error`).
- `running`: **mọi** widget của §3.2 và nút tải / lưu của `screen-result`, `screen-identity` có `disabled=True` (biến `locked = st.session_state.run_requested`, tính ở đầu script).
- `done`/`error` → rerun → widget bật lại; `result` / `run_error` giữ tới lần chạy sau.
- `blocked`: nút Phân tích disabled, các lý do hiện bằng `st.info`.

### 3.4 Hàm thuần (mức module, không gọi `st.*`, test bằng pytest thường)
```python
SOURCE_QUOTES = "\"'"
USER_MODES = ("Tất cả user", "Chọn user")
DEFAULT_OUT_DIR = "output"
DEFAULT_IDENTITIES = "identities.yaml"

def clean_source(text: str) -> str:
    """Bỏ khoảng trắng và dấu nháy bao quanh (đường dẫn dán từ "Copy as path")."""

def default_dates(now: datetime) -> tuple[date, date]:
    """(ngày 1 của tháng, hôm nay) theo ngày của `now` (aware, múi giờ đang chọn)."""

def timezone_options() -> list[str]:
    """sorted(zoneinfo.available_timezones())."""

def timezone_label(name: str, at: datetime) -> str:
    """'Asia/Bangkok (UTC+07:00)' — độ lệch tại thời điểm `at`."""

def canonical_timezone(name: str) -> str | None:
    """Tên trong timezone_options() khớp chính xác, hoặc khớp casefold duy nhất; không có → None (A14)."""

def snapshot_text(commit: CommitInfo | None, timezone: str) -> str:
    """'a1b2c3d (2025-12-15 10:00)  "admin: app.py"' | '(không có commit trước start)'."""

def user_label(user: UserSummary) -> str:
    """'alice (2 commit)' [+ ' · bot'] [+ ' · <m> merge']."""

def filter_users(users: Sequence[UserSummary], query: str,
                 exclude_bots: bool) -> list[UserSummary]:
    """Giữ thứ tự; bỏ bot nếu exclude_bots; query casefold khớp account, tên hoặc email."""

def reconcile_selection(selected: Set[str], users: Sequence[UserSummary],
                        exclude_bots: bool) -> tuple[set[str], list[str]]:
    """(lựa chọn còn hợp lệ, account bị bỏ — sắp tăng dần)."""

def parse_lines(text: str) -> list[str]:
    """Mỗi dòng một mục; bỏ khoảng trắng hai đầu, bỏ dòng rỗng, bỏ trùng giữ thứ tự."""

def form_config(values: Mapping[str, Any], timezone: str) -> AppConfig:
    """8 giá trị nâng cao (key không có tiền tố adv_) + timezone → config_from_dict."""

def config_form_values(config: AppConfig) -> dict[str, Any]:
    """Ngược của form_config: giá trị điền vào widget (danh sách → chuỗi nhiều dòng)."""

def resolve_out_root(text: str) -> Path:
    """Path(text.strip()).expanduser().resolve(); rỗng → PipelineError."""

def analyze_blockers(*, repo_ready: bool, branch: str | None, period_error: str | None,
                     context_error: str | None, identities_error: str | None,
                     config_error: str | None, out_dir: str, user_mode: str,
                     selected_count: int) -> list[str]:
    """Lý do (tiếng Việt, theo thứ tự cố định của mục 7) khiến chưa chạy được; [] = chạy được."""

def build_request(*, branch: str, period: Period, config: AppConfig, out_root: Path,
                  user_mode: str, selected: Set[str], exclude_bots: bool,
                  separate_users: bool, attribution_mode: str = ATTRIBUTION_MODES[0],
                  loc_end_mode: str = LOC_END_MODES[0]) -> AnalysisRequest:
    """users = None khi 'Tất cả user', ngược lại tuple(sorted(selected))."""

def progress_text(step: Step, index: int, total: int) -> str:
    """'Bước 3/5: Export end…' (nhãn STEP_LABELS)."""

class LockRegistry:
    """Khóa theo tên dùng chung tiến trình: get(name) -> threading.Lock (tạo một lần, có khóa nội bộ)."""

LOCKS = LockRegistry()   # singleton tiến trình (A12)
```
**Registry khóa (A12):** script chạy dưới tên `__main__` và bị chạy lại mỗi rerun, nên biến toàn cục của nó không bền. `main()` lấy registry từ **module gói** `importlib.import_module("loc_counter.app").LOCKS` — module này nạp một lần mỗi tiến trình (`sys.modules`), khi nạp không chạy `main()`. Test dùng trực tiếp `loc_counter.app.LOCKS`.

Hàm có dùng Streamlit (trong `app.py`, không test riêng): `_init_state()`, `_render_repository(locked)`, `_render_period(locked)`, `_render_users(locked, ctx)`, `_render_advanced(locked)`, `_render_run(locked, …)`, `_request_run()`, `main()`. Cuối file: `if __name__ == "__main__": main()`.

**Gọi qua thuộc tính module** (để test monkeypatch được dưới AppTest — script chạy như module `__main__` riêng): `GitRepo.open`, `pipeline.make_resolver`, `pipeline.prepare_period`, `pipeline.run_log`, `pipeline.run_analysis`, `git_repo.DEFAULT_CACHE_ROOT`, `identity.DEFAULT_LOGIN_CACHE` (đọc lúc gọi).

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| ngày start / end | `date` | `default_dates(datetime.now(ZoneInfo("Asia/Bangkok")))` khi mở phiên | `start < end` sau khi ghép giờ | §10.2 [2], A3 |
| giờ | `time | None` | `None` | `HH:MM` (D10) | §3.1 |
| múi giờ | `str` | `Asia/Bangkok` (`config.DEFAULT_TIMEZONE`) | IANA | §3.1 |
| bộ lọc | `AppConfig` | `AppConfig()` (§9) | `config_from_dict` | §9 |
| thư mục đầu ra | `str` | `output` (tương đối CWD) | không rỗng | D41-N2 |
| identities | `str` | `identities.yaml` (tương đối CWD) | YAML D16 | D41-N5 |
| `AnalysisRequest` | — | xem `build_request` | `period` là đúng đối tượng trong `PeriodContext` | pipeline 5.6 bước 3 |

## 5. Luồng xử lý
Mỗi lần script chạy (`main()`):

### 5.1 Khởi tạo
1. `st.set_page_config(page_title="Đếm LOC", layout="wide")`; `st.title("ĐẾM LOC SOURCE CODE")`.
2. `_init_state()`: đặt mặc định cho mọi key của §3.2 / trạng thái chưa có (ngày theo A3, `adv_*` theo `config_form_values(AppConfig())`).
3. `locked = st.session_state.run_requested`.

### 5.2 [1] Repository
1. `source = clean_source(repo_source)`; nút "Tải repo" disabled khi `not source or locked`.
2. Bấm "Tải repo": `with st.spinner("Đang tải repo…")`: khóa `LOCKS.get("repo:" + str(cache_dir_for(normalize_source(source)[0], git_repo.DEFAULT_CACHE_ROOT)))` (**có chờ**, D41-N4; `normalize_source` lỗi → `GitError` hiển thị như dưới); `repo = GitRepo.open(source, token or None, cache_root=git_repo.DEFAULT_CACHE_ROOT)`; `branches = repo.list_branches()`; `default = repo.default_branch()`.
   - Thành công: `repo`, `loaded_with = (source, token)`, `repo_gen += 1`, `branches`, `repo_error = None`, `period_memo = {}`; `st.session_state.branch = default if default in branches else None`.
   - `LocCounterError` / `OSError` → `repo = None`, `branches = []`, `repo_error = str(err)` (đã che token — `GitError`).
3. `repo_error` → `st.error(repo_error)`.
4. `repo_ready = repo is not None and loaded_with == (source, token)`; có repo nhưng khác → `st.warning("Nguồn hoặc token đã thay đổi; hãy bấm “Tải repo” lại.")`, coi như chưa có repo (A11).
5. `repo_ready`: `selectbox("Nhánh", branches, key="branch", index=None …)`; `branches` rỗng → `st.error("Repo không có nhánh nào.")`; `branch is None` → lý do chặn.

### 5.3 [2] Thời điểm thống kê
1. Hai cột: start (`date_input`, `time_input`), end (tương tự); `selectbox` múi giờ.
2. `period = snapshot.make_period(start_date, end_date, start_time, end_time, timezone=tz)`; `SnapshotError` → `period_error = str(err)`, `st.error(period_error)`.
3. Identities: `path = identities_path.strip()`; rỗng hoặc file không tồn tại → `identity_map = IdentityMap()`; có → `load_identities(Path(path))`, `IdentityError` → `identities_error`, `st.error` (ở khối [3]).
4. Khi `repo_ready and branch and period and identities_error is None`: `key = (repo_gen, branch, period, identity_map, bool(token))`; `period_memo.get(key)`; chưa có → `with st.spinner("Đang tính snapshot và danh sách user…")`: `resolver = pipeline.make_resolver(repo.source, identity_map, token or None, login_cache=identity.DEFAULT_LOGIN_CACHE)`; `ctx = pipeline.prepare_period(repo, branch, period, resolver)` → `period_memo = {key: (ctx, resolver, None)}`; `LocCounterError` → `period_memo = {key: (None, None, str(err))}` (A4).
5. Hai dòng snapshot và lỗi `prepare_period` vẽ vào **`st.container()` giữ chỗ tạo ngay dưới ô múi giờ trong khối [2]** (tính memo xảy ra sau khi đọc identities ở [3]): `ctx` → `st.text("→ Snapshot start: " + snapshot_text(ctx.snapshots.c_start, tz))`, `"→ Snapshot end:   " + snapshot_text(c_end, tz)` (`st.text`: tiêu đề commit không bị hiểu thành markdown); lỗi → `context_error`, `st.error`.
6. `ss.tz` không thuộc `timezone_options()` (vd. do nạp file) → thay bằng `canonical_timezone(ss.tz)` hoặc giữ nguyên và báo `st.error("Múi giờ không có trong danh sách: <x>")` + chặn (không để `selectbox` âm thầm chọn mục đầu).

### 5.4 [3] Chọn user
1. Ô `identities_path` (đặt ở đầu khối); radio `user_mode`; checkbox `exclude_bots`, `separate_users`.
2. `ctx` có: `users = ctx.users.users`; `selected, dropped = reconcile_selection(selected, users, exclude_bots)`; `dropped` → `st.info("Đã bỏ chọn user không còn trong danh sách: " + ", ".join(dropped))`.
3. Không có user → `st.info("Không có user nào có commit trong kỳ.")`.
4. "Tất cả user": liệt kê `user_label(u)` của `filter_users(users, "", exclude_bots)` (chỉ đọc, `st.caption` mỗi dòng hoặc một dòng nối `·`).
5. "Chọn user": `text_input` tìm; với mỗi `u` trong `filter_users(users, query, exclude_bots)`: `k = "pick_" + sha1(u.account)[:12]`; trước khi vẽ `st.session_state[k] = u.account in selected`; `checkbox(user_label(u), key=k, on_change=_toggle, args=(u.account, k))` — `_toggle` thêm / bỏ account trong `selected`. Dưới danh sách: `st.caption(f"Đã chọn {len(selected)} user")`. Lựa chọn bị ẩn bởi ô tìm vẫn giữ.
6. `ctx.users.warnings` → mỗi dòng `st.warning`.
7. Gọi `render_identity_panel(...)` nếu đã định nghĩa (spec `screen-identity`).

### 5.5 Tùy chọn nâng cao (`st.expander`, đóng mặc định)
1. Ô `config_path` + nút "Nạp" (`on_click=_load_config_file`): ô rỗng → xóa `config_load_error`, không làm gì; `load_config(Path(path))` → `tz = canonical_timezone(cfg.timezone)`; `None` → `config_load_error = "Múi giờ trong file cấu hình không có trong danh sách múi giờ: <x>"`, không ghi gì; ngược lại ghi `adv_*` = `config_form_values(cfg)` và `tz`; `ConfigError` → `config_load_error = str(err)` hiện `st.error` trong expander.
2. 8 widget §3.2; `config = form_config({...}, tz)`; `ConfigError` → `config_error = str(err)`, `st.error` trong expander.

### 5.6 Phân tích
1. `text_input` `out_dir`.
2. `blockers = analyze_blockers(...)`; mỗi lý do `st.info`; `st.button("PHÂN TÍCH", type="primary", disabled=bool(blockers) or locked, on_click=_request_run)` — `_request_run` đặt `run_requested = True`, `run_error = None`.
3. `run_error` → `st.error(run_error)`. `result` → `render_result(result, stale=result_sig != current_sig)` nếu `screen-result` đã có, ngược lại `st.success(f"Phân tích xong. Thư mục kết quả: {result.out_dir}")`.
4. **Cuối script**, nếu `run_requested` (lần chạy này đã vẽ mọi widget disabled):
```text
st.session_state.run_requested = False   # trả cờ TRƯỚC việc nặng (A13)
bar = st.progress(0.0, text="Đang chuẩn bị…")
try:
    if blockers: raise PipelineError(blockers[0])              # tham số đổi giữa hai lần chạy
    out_root = resolve_out_root(out_dir)
    lock = LOCKS.get("out:" + os.path.normcase(str(out_root)))   # Windows: không phân biệt hoa thường
    if not lock.acquire(blocking=False):
        raise PipelineError(f"Thư mục đầu ra {out_root} đang được một phiên phân tích khác sử dụng; "
                            "hãy chờ hoặc chọn thư mục khác.")
    try:
        with pipeline.run_log(out_root, secrets=(token or None,)):
            logger.info("Phân tích từ giao diện: nguồn %s, nhánh %s, kỳ %s → %s (%s), C_START=%s, "
                        "C_END=%s, user: %s", repo.source, branch, period.start, period.end, tz,
                        sha|"rỗng", c_end.sha, "tất cả" | ", ".join(sorted(selected)))
            request = build_request(...)
            try:
                result = pipeline.run_analysis(repo, request, resolver, progress=on_progress, context=ctx)
            except Exception as err:             # không phải LocCounterError/OSError: log TRONG run_log (che token)
                if not isinstance(err, LocCounterError | OSError): logger.exception("Lỗi không mong đợi khi phân tích")
                raise
        st.session_state.result, st.session_state.result_sig = result, current_sig
    finally:
        lock.release()
except (LocCounterError, OSError) as err:  st.session_state.run_error = str(err)
except Exception:                           run_error = "Lỗi không mong đợi khi phân tích; xem run.log hoặc log của ứng dụng." (đã log trong run_log)
st.rerun()        # chỉ khi không có BaseException khác (Rerun/Stop/KeyboardInterrupt ném tiếp — không bắt)
```
`on_progress(step, i, n)`: `bar.progress((i - 1) / n, text=progress_text(step, i, n))`. `current_sig = (repo_gen, branch, period, identity_map, config, out_root_text, user_mode, tuple(sorted(selected)), exclude_bots, separate_users, attribution_mode, loc_end_mode)` (A9, A18, A19).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- **Không fetch lại khi bấm Phân tích** (D41-N22): kết quả khớp snapshot đang hiển thị; muốn cập nhật bấm "Tải repo" lại.
- **Memo kỳ** chỉ giữ 1 mục; gõ ô tìm, bật/tắt checkbox user, đổi tùy chọn nâng cao **không** gọi lại `prepare_period` (khóa không đổi). Đổi identities (nội dung file) → `IdentityMap` khác → tính lại.
- **Cùng resolver** cho `prepare_period` và `run_analysis` (pipeline R5): lấy từ memo.
- **"Loại trừ bot"** trên UI ẩn bot và bỏ bot khỏi lựa chọn ("thấy gì chọn nấy" — D41-N18; khác CLI, nơi chọn tường minh thắng `--exclude-bots`). Ở chế độ "Tất cả user" truyền `exclude_bots` cho pipeline như CLI.
- **C_START rỗng** hợp lệ: "(không có commit trước start)". **Không có commit trước end**: lỗi `Không có dữ liệu trong khoảng thời gian…` (từ `snapshot`), chặn Phân tích.
- **Kỳ không có user** + "Tất cả user": chạy được (pipeline 6). + "Chọn user": chặn ("Chưa chọn user nào.").
- **Ngày mặc định** tính một lần lúc mở phiên theo múi giờ mặc định; đổi múi giờ sau đó không đổi ngày (A3).
- **Giờ 23:59** cho end ≡ không nhập (D10, `make_period`).
- **Đường dẫn tương đối** (`output`, `identities.yaml`, `config_path`) theo thư mục chạy `streamlit` (CWD).
- **Tham số đổi sau khi chạy**: `result` giữ, `stale=True` (screen-result hiện chú thích, D41-N23).

## 7. Xử lý lỗi & thông báo
Lý do chặn của `analyze_blockers` (theo thứ tự, mỗi lý do một `st.info`):
1. `Chưa tải repo.` (không `repo_ready`)
2. `Chưa chọn nhánh.`
3. `period_error` (nguyên văn `make_period`)
4. `identities_error`
5. `context_error` (nguyên văn `prepare_period`, vd. `Không có dữ liệu trong khoảng thời gian…`)
6. `config_error`
7. `Chưa nhập thư mục đầu ra.`
8. `Chưa chọn user nào.` (chế độ "Chọn user", 0 user)

| Tình huống | Hành vi | Thông báo (tiếng Việt) | Log |
|---|---|---|---|
| Nguồn sai / không có quyền / URL có credential | `st.error`, không có nhánh | thông báo `GitError` (đã che token) | `git_repo` WARNING (stderr) |
| Repo không có nhánh | `st.error` | `Repo không có nhánh nào.` | — |
| Không xác định nhánh mặc định | `selectbox` trống | lý do `Chưa chọn nhánh.` | — |
| Nguồn / token đổi sau khi tải | `st.warning`, chặn | `Nguồn hoặc token đã thay đổi; hãy bấm “Tải repo” lại.` | — |
| `start >= end`, múi giờ sai | `st.error`, chặn | thông báo `make_period` | — |
| Không có commit trước end | `st.error`, chặn | `Không có dữ liệu trong khoảng thời gian…` | — |
| identities hỏng | `st.error`, chặn | thông báo `IdentityError` | — |
| Cấu hình nâng cao sai (vd. KB = 0) | `st.error` trong expander, chặn | thông báo `ConfigError` (vd. `max_file_size_kb phải là số nguyên dương`) | — |
| Nạp config lỗi | `st.error` trong expander, widget giữ nguyên | thông báo `ConfigError` | — |
| `out_root` đang được phiên khác dùng | `run_error` | `Thư mục đầu ra <p> đang được một phiên phân tích khác sử dụng; hãy chờ hoặc chọn thư mục khác.` | — |
| Lỗi pipeline (`PipelineError`, `GitError`, `ReportError`…), `OSError` | `run_error` | thông báo của module | `run.log` (pipeline) |
| Lỗi không mong đợi (`Exception` khác) | `run_error` | `Lỗi không mong đợi khi phân tích; xem run.log hoặc log của ứng dụng.` | `logger.exception` trong `run_log` (che token) |
| Múi giờ (từ file cấu hình) không có trong danh sách | `st.error` trong expander, không nạp | `Múi giờ trong file cấu hình không có trong danh sách múi giờ: <x>` | — |
| Đường dẫn identities là thư mục | `st.error`, chặn | `Đường dẫn identities không phải file: <p>` | — |
| Rerun / Stop / mất kết nối giữa chừng | không bắt (BaseException) — pipeline dọn thư mục tạm | — | `run.log` ERROR (pipeline) |

## 8. Bảo mật, hiệu năng, tái lập
- **Token:** chỉ trong state widget `token`, `loaded_with`, `GitRepo`, resolver (trong `session_state` của phiên — "chỉ giữ trong session", R3). Không vào `st.cache_*`, khóa memo (chỉ `bool(token)`), `current_sig`, log (logger.info không in token), thông báo. `run_log(secrets=(token,))`. Lỗi: chỉ hiện `str(err)` của `LocCounterError` (đã che); lỗi khác hiện thông báo chung (không in exception). Traceback Streamlit không in biến cục bộ (D41 V6).
- **Đa phiên:** khóa `out_root` không chờ (D41-N3), khóa cache repo có chờ (N4) — registry `LOCKS` của module gói (A12; thay cho `st.cache_resource` của D41-N1, cùng mục đích: bền qua rerun, chung mọi phiên). Không dùng `st.cache_data` cho dữ liệu repo (dùng chung mọi phiên).
- **Hiệu năng:** `prepare_period` chỉ khi khóa memo đổi; GitHub API (lần đầu mỗi email) chạy trong spinner. Phân tích chạy trên luồng script (A7).
- **Tái lập:** `build_request` cho cùng `AnalysisRequest` như CLI với cùng tham số (`users` đã sắp).
- **Windows:** đường dẫn qua `pathlib`; `clean_source` bỏ dấu nháy của "Copy as path".

## 9. Test cases
Fixture (thêm vào `tests/conftest.py`): `make_app` — `AppTest.from_file(<src>/loc_counter/app.py, default_timeout=60)`, monkeypatch `git_repo.DEFAULT_CACHE_ROOT`, `identity.DEFAULT_LOGIN_CACHE` vào `tmp_path`, `monkeypatch.chdir(tmp_path)`; `section14_repo(name="repo")`; GitHub giả: monkeypatch `GitRepo.open` trả `GitRepo(<bare>, "https://github.com/org/repo", TOKEN)` + `FakeSession` (không mạng).

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-screen-input-01 | Trạng thái ban đầu | chạy app | tiêu đề; 4 khối; `token` là password; radio `Tất cả user`; 2 checkbox tắt; `out_dir == "output"`; "Tải repo" disabled; PHÂN TÍCH disabled, lý do `Chưa tải repo.` | AppTest |
| TC-screen-input-02 | `default_dates`, `clean_source`, `timezone_*`, `user_label`, `parse_lines` | `now` 2026-10-25 01:00+07; 2026-10-01; `' "D:\x\r" '`; `Asia/Bangkok`; user bot + merge | `(2026-10-01, 2026-10-25)`; `(2026-10-01, 2026-10-01)`; `D:\x\r`; `Asia/Bangkok (UTC+07:00)`, `UTC` có trong options; `dependabot[bot] (1 commit) · bot · 1 merge`; dòng rỗng/trùng bị bỏ | unit |
| TC-screen-input-03 | Tải repo §14 | đường dẫn local, kỳ 2026-01-01..31 | nhánh `main`; dòng snapshot start `… (2025-12-15 10:00)  "admin: app.py"`, end `… (2026-01-08 10:00)  "bob del"`; danh sách `alice@example.com (2 commit)`, `bob@example.com (2 commit)`; PHÂN TÍCH enabled | AppTest |
| TC-screen-input-04 | Lỗi nguồn | đường dẫn không tồn tại; `https://u:p@github.com/o/r` | `st.error` tiếng Việt; không có selectbox nhánh; chặn `Chưa tải repo.` | AppTest |
| TC-screen-input-05 | Tính lại kỳ / memo | spy `pipeline.prepare_period`; đổi end; gõ ô tìm; bật checkbox user | đổi end → gọi lại, snapshot cập nhật; gõ tìm / checkbox → không gọi lại | AppTest |
| TC-screen-input-06 | `start >= end` | end < start | `st.error` chứa `phải trước end`; PHÂN TÍCH disabled | AppTest |
| TC-screen-input-07 | Không có dữ liệu | kỳ 2020 | `Không có dữ liệu trong khoảng thời gian`; disabled | AppTest |
| TC-screen-input-08 | C_START rỗng | start 2025-01-01 | `(không có commit trước start)`; `admin@example.com` trong danh sách | AppTest |
| TC-screen-input-09 | Chọn user bắt buộc | "Chọn user", 0 chọn → tick alice | lý do `Chưa chọn user nào.` → hết, enabled | AppTest |
| TC-screen-input-10 | Tìm kiếm | tick alice, gõ `BOB` | chỉ checkbox bob hiện; `Đã chọn 1 user` (alice giữ) | AppTest |
| TC-screen-input-11 | Bot | `section14_repo(bot=True)`; tick bot; bật "Loại trừ bot" | nhãn `· bot`; bật → bot ẩn, `st.info` bỏ chọn bot, `Đã chọn 0 user` | AppTest |
| TC-screen-input-12 | `filter_users`, `reconcile_selection` | user giả | casefold theo account/tên/email; giữ thứ tự; account vắng / bot khi exclude bị bỏ, danh sách bỏ sắp tăng dần | unit |
| TC-screen-input-13 | Tùy chọn nâng cao | mặc định; `max_file_size_kb=0`; nạp config.yaml (`include_tests: false`, `timezone: UTC`); nạp file hỏng | `form_config(config_form_values(AppConfig()), "Asia/Bangkok") == AppConfig()`; KB 0 → `max_file_size_kb phải là số nguyên dương`, disabled; nạp → `adv_include_tests` False, `tz == "UTC"`; file hỏng → `st.error`, widget giữ nguyên | unit + AppTest |
| TC-screen-input-14 | Tiến độ | `progress_text`; spy bọc `pipeline.run_analysis` ghi các lần gọi `progress` | `progress_text(Step.REPORT, 5, 5) == "Bước 5/5: Tạo báo cáo…"`; callback của app được gọi đủ 5 bước `(Step, i, 5)` không lỗi; sau rerun có dòng xong | unit + AppTest |
| TC-screen-input-15 | Khóa ô nhập | `run_analysis` giả gọi `st.stop()` (`StopException`, như bấm Stop giữa chừng — AppTest không bắt `BaseException` tự định nghĩa) | cây phần tử của lần chạy đó: mọi widget §3.2 `disabled`; không có kết quả; `run_requested` False; `at.run()` lần sau → widget enabled | AppTest |
| TC-screen-input-16 | `AnalysisRequest` | spy `run_analysis`: (a) tất cả; (b) chọn bob, alice + exclude + separate | `users is None` / `("alice","bob")` (tên account theo identities); `out_root == (tmp_path/"output").resolve()`; `context` là ctx đang hiển thị, `resolver` cùng đối tượng với memo; `exclude_bots`, `separate_users` đúng; `build_request` unit | AppTest + unit |
| TC-screen-input-17 | E2E §14 | identities gộp alice/bob; (a) tất cả; (b) alice; (c) bob; (d) alice+bob xuất riêng | `result.data` 10/20, 10/13, 10/17, 10/20; (d) 3 zip end; `<out>/run.log` có dòng INFO `Phân tích từ giao diện:` chứa `C_START=`; không `.loc-tmp-*` | AppTest |
| TC-screen-input-18 | Khóa `out_root` (Q46) | giữ thủ công `loc_counter.app.LOCKS.get("out:<p>")` rồi bấm | `run_error` chứa `đang được một phiên phân tích khác sử dụng`; không có `.loc-tmp-*`; khóa nhả sau lỗi pipeline (lần sau chạy được); `LockRegistry.get` trả cùng đối tượng cho cùng tên, nhiều luồng an toàn | AppTest + unit |
| TC-screen-input-19 | Lỗi pipeline / bất thường | `run_analysis` giả ném `PipelineError("x")`; `ValueError("bí mật")` | `st.error("x")`; `Lỗi không mong đợi khi phân tích…`, không có `bí mật`; `run_requested` False | AppTest |
| TC-screen-input-20 | Token | nguồn GitHub giả, token `ghp_SECRET123`, `FakeSession` 403 (monkeypatch `requests.Session`); chạy tất cả | token không có trong mọi `value` / text / markdown / error của cây AppTest (trừ giá trị widget `token`), `run.log`, thư mục kết quả (kể cả giải nén zip/xlsx), cache, `github_logins.json` | AppTest |
| TC-screen-input-21 | Đổi nguồn / token sau khi tải | đổi `token` | `st.warning` `Nguồn hoặc token đã thay đổi…`; chặn `Chưa tải repo.` | AppTest |
| TC-screen-input-22 | `analyze_blockers`, `resolve_out_root` | tổ hợp | đúng thứ tự mục 7; `""` → `PipelineError`; `~/x` → mở rộng home, tuyệt đối | unit |
| TC-screen-input-24 | Bổ sung theo review | `canonical_timezone("singapore")`, `"utc"`, `"Mars/X"`; nạp config `timezone: singapore`; đổi token rồi trả lại; identities là thư mục / YAML hỏng; repo không có nhánh (monkeypatch `list_branches → []`); khóa `out_root` sau lỗi pipeline; lỗi `ValueError` → `run.log` có traceback | `Singapore`, `UTC`, `None`; `tz == "Singapore"`, kỳ `+08:00`; nhánh `main` được giữ; lỗi tương ứng + chặn; `Repo không có nhánh nào.`; `acquire(blocking=False)` được sau lỗi; dòng ERROR `Lỗi không mong đợi khi phân tích` + `Traceback` trong `run.log`; snapshot nằm trong khối [2] (trước subheader [3]) | unit + AppTest |
| TC-screen-input-25 | Chọn cách gán tác giả (A18) | AppTest: (a) mặc định lựa chọn đầu; `build_request` → `attribution_mode == "line"`; (b) chọn "Theo commit cuối cùng của file" → `"last_commit"`; (c) đổi sau khi có kết quả → kết quả báo cũ (`sig` đổi); (d) E2E repo §14 (tất cả user, `last_commit`) → LOC 10/20 | AppTest |
| TC-screen-input-26 | Chọn cách tính LOC end (A19) | AppTest: (a) mặc định lựa chọn đầu; `build_request` → `loc_end_mode == "net_code"`; (b) chọn `Theo code thêm (LOC start + tổng code thêm)` → `"added_code"`; (c) đổi sau khi có kết quả → kết quả báo cũ (`sig` đổi); (d) radio disabled khi `locked` | AppTest |
| TC-screen-input-23 | Lựa chọn cũ khi kỳ đổi | tick alice, đổi kỳ sang 2026-01-09..20 (không có user) | `st.info` `Đã bỏ chọn user không còn trong danh sách: alice`; `Không có user nào có commit trong kỳ.` | AppTest |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | Mọi quyết định D41 (N1–N28) áp dụng nguyên văn | PLAN D41 | Chốt (*) |
| A2 | Một file `app.py`: hàm thuần mức module + `main()`; `if __name__ == "__main__": main()` | D41-N1 | Chốt (*) |
| A3 | Ngày mặc định theo `Asia/Bangkok` lúc mở phiên (`datetime.now(ZoneInfo(DEFAULT_TIMEZONE))`) | D41-N10 | Chốt (*) |
| A4 | Lỗi `prepare_period` cũng được memo (không gọi lại mỗi rerun khi kỳ vẫn lỗi) | Khuyến nghị | Chốt (*) |
| A5 | Ô "Thư mục đầu ra" đặt ngay trên nút PHÂN TÍCH (§10.1 không có — D41-N2) | Khuyến nghị | Chốt (*) |
| A6 | Nạp config ghi đè 8 ô nâng cao và múi giờ; ô trống không nạp | D41-N7 | Chốt (*) |
| A7 | Phân tích chạy đồng bộ trên luồng script (không luồng nền) | D41-N12 | Chốt (*) |
| A8 | Ở chế độ "Tất cả user", danh sách user hiển thị chỉ để xem (không checkbox) | Khuyến nghị (§10.1 vẽ checkbox cho chế độ chọn) | Chốt (*) |
| A9 | `current_sig` so sánh tham số để đánh dấu kết quả cũ | D41-N23 | Chốt (*) |
| A10 | Ngôn ngữ loại trừ nhập bằng `text_area` (mỗi dòng một tên Pygments) thay cho `multiselect(accept_new_options)` — đơn giản, test được | Khuyến nghị | Chốt (*) |
| A11 | So nguồn đã làm sạch + token với lúc tải để phát hiện thay đổi | D41-N20 | Chốt (*) |
| A13 | `run_requested` đặt lại `False` **ngay đầu** bước chạy (trước `run_analysis`): Stop của Streamlit (`st.stop()` / người dùng bấm Stop) có thể kết thúc luồng script mà không chạy `finally` (đã kiểm chứng trên 1.66.1), cờ còn `True` sẽ làm lần rerun sau tự chạy lại phân tích | Kiểm chứng khi lập trình | Chốt (*) |
| A14 | Múi giờ chỉ nhận tên trong `timezone_options()`; tên khác hoa thường (Windows: `zoneinfo` chấp nhận `singapore`, `utc`) quy về tên chuẩn nếu khớp casefold duy nhất — tránh `selectbox` âm thầm chọn mục đầu (`Africa/Abidjan`), lệch với CLI (review 2026-10-25, Major) | Khuyến nghị review | Chốt (*) |
| A15 | Nhánh đã chọn giữ ở `branch_value` (Streamlit xóa state của widget không vẽ khi nguồn/token tạm khác) | Khuyến nghị review | Chốt (*) |
| A16 | Khóa `out_root` theo `os.path.normcase` (Windows không phân biệt hoa thường) | Khuyến nghị review | Chốt (*) |
| A12 | Registry khóa là `LOCKS` mức module của module gói `loc_counter.app` (script lấy qua `importlib`), thay `st.cache_resource` — singleton tiến trình, test truy cập được (dưới AppTest script là `__main__` riêng) | Khuyến nghị khi thiết kế test | Chốt (*) |

| A17 | Web UI chỉ chọn ngày: bỏ `time_input` và `selectbox` múi giờ. `start_time`/`end_time` luôn `None` (start 00:00:00, end 23:59:59); `tz` là state thuần, mặc định `Asia/Bangkok`, vẫn đổi được qua "Nạp" file cấu hình (A6, A14). CLI giữ `--start-time/--end-time/--tz` | Người dùng yêu cầu 2026-10-28 | Chốt |
| A18 | Chọn cách gán tác giả (yêu cầu 2026-10-30): `build_request` quy `ATTRIBUTION_MODES[1]` → `AnalysisRequest.attribution_mode="last_commit"`, lựa chọn đầu → `"line"`; `attribution_mode` thêm vào `sig` (5.6). Radio khóa khi đang chạy (`locked`). TC-screen-input-25 | Khuyến nghị (ủy quyền) |
| A19 | Chọn cách tính LOC end (yêu cầu 2026-10-30, report A15): radio `loc_end_mode` ngay dưới `Cách gán tác giả`; `build_request` quy `LOC_END_MODES[1]` → `AnalysisRequest.loc_end_mode="added_code"`, lựa chọn đầu → `"net_code"`; thêm vào `sig`; khóa khi `locked`. TC-screen-input-26 | Khuyến nghị (ủy quyền 2026-10-23) |

(*) Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-23 / 2026-10-25 ("làm theo khuyến nghị"); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-28 | A17: bỏ ô giờ và ô múi giờ khỏi web UI, chỉ chọn ngày; R5, bố cục 3.1, bảng 3.2, TC-01 (ô giờ), TC-24/config (đọc `tz` từ session state) chỉnh theo | Người dùng yêu cầu |
| 2026-10-25 | Theo review `reviews/screen-input-20261025.md` (FAIL): A14 `canonical_timezone`, snapshot vẽ trong khối [2] (container giữ chỗ), A15 `branch_value`, A16 `normcase`, identities là thư mục → lỗi, lỗi không mong đợi log trong `run_log`, ô config rỗng xóa lỗi cũ; TC-24. Chốt theo khuyến nghị | review Major 1, 2 + Minor |
| 2026-10-25 | Khi lập trình: A13 (trả cờ chạy trước việc nặng), TC-15 dùng `st.stop()`; `analyze_blockers` liệt kê độc lập từng lý do (mục 7). Chốt theo khuyến nghị | kiểm chứng AppTest |
| 2026-10-25 | Trước khi lập trình: A12 (`LOCKS` thay `st.cache_resource`), `progress_text`, dòng snapshot dùng `st.text`, TC-14/18/20 chỉnh theo. Chốt theo khuyến nghị | thiết kế test AppTest |
| 2026-10-25 | Tạo mới theo PLAN M6 + phân tích `spec-analyst` (D41). A1–A11 chốt theo khuyến nghị, người dùng ủy quyền → `approved` | M6 (`/feature-spec screen-input`) |
| 2026-10-30 | Radio `attribution_mode` ở khối [3] (A18, TC-25), `build_request` + `sig` thêm tham số | Người dùng yêu cầu lựa chọn "Gán tác giả cho commit cuối cùng" (thuật toán đơn giản). Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | Yêu cầu mới |
| 2026-10-30 | Test pass (mode last_commit: TC-attribution-49/50, builder-32, pipeline-40, screen-input-25, cli-analyze-26; toàn bộ 779 test, ruff sạch, coverage 99 %) → `implemented`; chưa review | /feature-test |
| 2026-10-30 | Radio `loc_end_mode` ở khối [3] (A19, TC-26), `build_request` + `sig` thêm tham số; ghi `attribution_mode` vào công thức `current_sig` (đã có từ A18) | Người dùng yêu cầu chọn cách tính LOC end theo code thêm hoặc code ròng. Chốt theo khuyến nghị, người dùng ủy quyền → `approved` |
| 2026-10-30 | Test pass (tổng code thêm / xóa + cách tính LOC end: TC-report-26, pipeline-41, cli-analyze-27, screen-input-26, screen-result-15; toàn bộ 784 test, ruff sạch, coverage 99 %) → `implemented`; chưa review | /feature-test |
| 2026-10-30 | Test pass sau sửa theo review (toàn bộ 784 test, ruff sạch, coverage 99 %). Review PASS_WITH_NOTES (`reviews/loc-end-mode-20261030.md`), Minor 1 + Nit đã sửa → `reviewed` | /feature-review |
