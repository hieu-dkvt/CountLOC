---
id: cli-analyze
title: Lệnh CLI loc-counter analyze
type: cli
milestone: M5
modules: [src/loc_counter/cli.py]
tests: [tests/test_cli_analyze.py]
spec_refs: ["3.1", "3.3", "3.5", "8.3", "10.2", "10.3", "11", "12", "15", "16"]
depends_on: [config, git_repo, snapshot, identity, report, pipeline, cli-users]
status: reviewed
---

# Lệnh `loc-counter analyze`

## 1. Mục đích & phạm vi
Lệnh `analyze` (§11, §13 M5) chạy **một lần phân tích** đầy đủ từ dòng lệnh: phân tích tham số → mở repo → `pipeline.run_analysis` → in tóm tắt kết quả (theo §10.3) ra stdout, tiến độ ra stderr, mã thoát. Toàn bộ nghiệp vụ (C_START/C_END, export, gán tác giả, đếm LOC, báo cáo, thư mục kết quả, `run.log`, khớp `--user`) nằm ở spec `pipeline`; `cli-analyze` chỉ ghép tham số và trình bày.

`cli-analyze` **làm**: khai báo lệnh + tham số (§11), kiểm tra tham số trước việc nặng, đọc token từ biến môi trường, bọc `GitRepo.open` + phân tích trong `pipeline.run_log` (pipeline A1), chọn nhánh mặc định, gọi `make_resolver` / `run_analysis`, in tiến độ, in bảng / JSON, ánh xạ lỗi → mã thoát (D40-N22).

Ngoài phạm vi:
- Mọi tính toán và file đầu ra → `pipeline`, `report`.
- Lệnh `users`, `count` (đã có spec) — chỉ dùng lại hàm private chung trong `cli.py`.
- README (việc không cần spec của M5).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Cú pháp `loc-counter analyze --repo … --branch … --start … --end … [--start-time] [--end-time] [--tz] [--user …]… [--separate-users] [--exclude-bots] [--config] [--identities] [--token-env] --out …` | §11 |
| R2 | Bỏ `--user` = tất cả user; nhiều `--user` = chọn nhiều user (một bản gộp); `--separate-users` = mỗi user một zip | §3.3, §11 |
| R3 | Token chỉ đọc từ biến môi trường `--token-env`, không nhận qua tham số; không xuất hiện ở stdout / stderr / log / file đầu ra | §11, §12, §15 |
| R4 | Thời điểm: ngày bắt buộc, giờ tùy chọn, múi giờ mặc định `Asia/Bangkok`; `start < end` | §3.1 |
| R5 | Bot hiện trong danh sách, `--exclude-bots` loại khỏi "Tất cả"; chọn tường minh thắng `--exclude-bots` | §3.5, §16, D40-N19 |
| R6 | Thư mục kết quả và đủ file §12 trong `--out`; `run.log` tại `<out>/run.log` | §12, §15, D40-N12 |
| R7 | Tiến độ theo bước (thứ tự thực): Export start → Gán tác giả → Export end → Đếm LOC → Tạo báo cáo | §10.2, D40-N16 |
| R8 | Kết quả: Repo, nhánh, kỳ, user; LOC start / end / chênh lệch / commit; theo ngôn ngữ; theo user (+ dòng Tổng); số cảnh báo | §10.3 |
| R9 | Kiểm tra chéo lệch > 0.5 % chỉ là cảnh báo | §8.3, D38 |
| R10 | Mã thoát 0 (kể cả có cảnh báo / kiểm tra chéo lệch), 1 lỗi nghiệp vụ (thông báo tiếng Việt), 2 sai cú pháp; `--json` tùy chọn | D40-N22 |
| R11 | `--user` khớp chính xác, rồi `casefold` nếu duy nhất; không khớp → lỗi liệt kê user trong kỳ | D40-N19 (thực hiện ở `pipeline.match_users`) |
| R12 | Lỗi Git: thông báo tiếng Việt, lệnh lỗi trong log chi tiết | §15 |

## 3. Giao diện

```
loc-counter analyze --repo REPO --start YYYY-MM-DD --end YYYY-MM-DD --out DIR
                    [--branch BRANCH] [--start-time HH:MM] [--end-time HH:MM] [--tz TZ]
                    [--user ACCOUNT]... [--separate-users] [--exclude-bots]
                    [--config PATH] [--identities PATH] [--token-env NAME] [--json]
```

| Tham số | Bắt buộc | Mặc định | Ghi chú |
|---|---|---|---|
| `--repo` | có | — | URL hoặc đường dẫn local (như `users`) |
| `--start`, `--end` | có | — | `YYYY-MM-DD` |
| `--out` | có | — | thư mục đầu ra; chưa có → tạo (`run_log`) |
| `--branch` | không | nhánh mặc định của repo | như `users` (cli-users A1) |
| `--start-time`, `--end-time` | không | không nhập | `HH:MM` (D10) |
| `--tz` | không | `timezone` trong config (`Asia/Bangkok`) | |
| `--user` | không, lặp được | không truyền = "Tất cả user" | giá trị thô, khớp ở `match_users` |
| `--separate-users` | không | tắt | §3.3 |
| `--exclude-bots` | không | tắt | §16 |
| `--config` | không | mặc định §9 | |
| `--identities` | không | không có quy tắc | D16 |
| `--token-env` | không | không dùng token | tên biến môi trường |
| `--json` | không | tắt | stdout chỉ chứa JSON |

Mã thoát: **0** thành công (kể cả có cảnh báo, kiểm tra chéo lệch); **1** lỗi nghiệp vụ (`LocCounterError` — gồm `PipelineError`, `SnapshotError`, `GitError`, `ReportError`, `ConfigError`, `IdentityError` — và `OSError`): `Lỗi: <thông báo>` ra stderr; **2** sai cú pháp / thiếu tham số bắt buộc (typer); **130** Ctrl+C: `Đã hủy phân tích.` ra stderr (A5).

Thành phần trong `cli.py` (dùng lại hàm private của spec `cli-users`: `_parse_period_args`, `_read_token`, `_open_repo`, `_resolve_branch`, `_fail`, `_format_table`, `_commit_text`):
```python
@app.command("analyze")
def analyze_command(repo, start, end, out, branch=None, start_time=None, end_time=None,
                    tz=None, user: list[str] | None = None, separate_users=False,
                    exclude_bots=False, config=None, identities=None, token_env=None,
                    json_output=False) -> None:
    """Phân tích LOC trong kỳ, xuất zip + báo cáo vào --out."""

def _print_progress(step: Step, index: int, total: int) -> None:
    """In `[i/5] <nhãn>…` ra stderr (ProgressCallback)."""

def _signed(value: int) -> str:
    """Số có dấu + hàng nghìn: 0 → '0', 1234 → '+1,234', -5 → '-5'."""

def _print_analysis_table(result: AnalysisResult) -> None: ...
def _print_analysis_json(result: AnalysisResult) -> None: ...
```

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `users` truyền cho `AnalysisRequest` | tuple[str] \| None | None khi không có `--user` | `tuple(user)` nếu danh sách khác rỗng | §3.3, A3 |
| `period.timezone` | str | `--tz` or `cfg.timezone` (`Asia/Bangkok`) | IANA, sai → lỗi `make_period` | §3.1 |
| `login_cache` | Path | `identity.DEFAULT_LOGIN_CACHE` đọc lúc gọi | | D18 |
| `cache_root` | Path | `git_repo.DEFAULT_CACHE_ROOT` đọc lúc gọi (`_open_repo`) | | §10.2 [1] |

### 4.1 Bảng (mặc định), stdout
```
Repo: <repo.source>
Nhánh: main • Kỳ: 2026-01-01 00:00:00 → 2026-01-31 23:59:59 (Asia/Bangkok)
Snapshot start: a1b2c3d 2025-12-15 10:00 admin: app.py
Snapshot end:   f9e8d7c 2026-01-08 10:00 bob del
User: Tất cả user
LOC start  LOC end  Chênh lệch  Commit
       10       20         +10       4

Theo ngôn ngữ
Ngôn ngữ  LOC start  LOC end  Chênh lệch
Python           10       20         +10

Theo user
User   Bot  Commit  Thêm  Xóa  Ròng  File thay đổi
alice            2     5    2    +3              1
bob              2     8    1    +7              2
Tổng             4    13    3   +10              2

Kiểm tra chéo: 10 + (+10) = 20; LOC end 20; lệch 0.000 % (ngưỡng 0.5 %) → đạt
Bản export:
start_2026-01-01_a1b2c3d.zip  1 file  LOC 10
end_2026-01-31_all.zip        2 file  LOC 20
Cảnh báo: 0
Thư mục kết quả: <out_dir>
```
- Dòng Repo, Nhánh/Kỳ, Snapshot: **đúng định dạng của `users`** (`_commit_text`, ngày commit theo múi giờ kỳ; C_START rỗng → `Snapshot start: (không có commit trước start)`).
- Dòng `User:` — `all_users` → `Tất cả user`, thêm ` (loại trừ bot)` khi `options.exclude_bots`; ngược lại `", ".join(options.selected_users)`. Thêm ` • Xuất riêng từng user` khi `options.separate_users`.
- Bảng tổng: `LOC start` = `data.loc_start`, `LOC end` = `data.loc_end`, `Chênh lệch` = `_signed(data.loc_delta)`, `Commit` = `Σ r.commits` của `data.user_rows` (không tính merge, §8.2).
- `Theo ngôn ngữ`: sắp `(-loc_end, -loc_start, language)` (như `report`); cột `LOC start`, `LOC end`, `Chênh lệch` (`_signed(delta)`). Rỗng → dòng `Không có file source nào.` thay bảng.
- `Theo user`: sắp `(-commits, account)` (D40-N18); cột `User`, `Bot` (`bot` / rỗng), `Commit`, `Thêm` (`added_code`), `Xóa` (`deleted_code`), `Ròng` (`_signed(net_code)`), `File thay đổi` (`files_changed`); dòng `Tổng` = `counter.total_metrics(user_rows)` (cột Bot rỗng) khi có ≥ 1 dòng (A6). Rỗng → `Không có user nào có commit trong kỳ.` thay bảng, không có dòng Tổng.
- Cột số căn phải, số có dấu phẩy hàng nghìn (`f"{n:,}"`); dùng `_format_table`. Giữa các khối một dòng trống như mẫu.
- `Kiểm tra chéo` (của export chính, `data.cross_check`): `Kiểm tra chéo: {loc_start:,} + ({_signed(sum_net_code)}) = {expected_loc_end:,}; LOC end {loc_end:,}; lệch {diff_percent:.3f} % (ngưỡng {threshold_percent:g} %) → đạt` | `→ VƯỢT NGƯỠNG (xem warnings.csv)`.
- `Bản export`: mỗi `ExportSummary` trong `data.exports` theo thứ tự một dòng `<file_name>  <files:,> file  LOC <loc:,>`; với role `separate` thêm `  kiểm tra chéo: đạt` | `kiểm tra chéo: VƯỢT NGƯỠNG` (căn cột bằng `_format_table`, không tiêu đề — các dòng sau `Bản export:`).
- `Cảnh báo: <n>` (`n = len(data.warnings)`), thêm ` (xem warnings.csv)` khi `n > 0`.
- `Thư mục kết quả: <result.out_dir>` (đường dẫn tuyệt đối dạng hệ điều hành).

### 4.2 JSON (`--json`), stdout (`ensure_ascii=False`, `indent=2`)
```json
{
  "out_dir": "D:/out/repo_main_2026-01-01_2026-01-31_all",
  "files": ["end_2026-01-31_all.zip", "loc_by_file.csv", "…", "warnings.csv"],
  "manifest": { "…": "nội dung manifest.json đã ghi" },
  "languages": [{"language": "Python", "files_start": 1, "loc_start": 10,
                 "files_end": 2, "loc_end": 20, "delta": 10}],
  "users": [{"account": "alice", "is_bot": false, "commits": 2, "added_lines": 7,
             "deleted_lines": 2, "added_code": 5, "deleted_code": 2, "net_code": 3,
             "files_changed": 1}],
  "warnings": [{"kind": "large_file", "path": "big.py", "message": "…",
                "scopes": ["start", "end:all"]}]
}
```
- `out_dir` = `result.out_dir.as_posix()`; `files` = tên mọi file trong `out_dir`, sắp tăng dần.
- `manifest` = `json.loads((out_dir / report.MANIFEST_NAME).read_text("utf-8"))` — trùng khít file đã ghi (A4).
- `languages` / `users` cùng thứ tự với bảng 4.1 (không có dòng Tổng); `warnings` sắp ổn định `(path, kind)` (như `warnings.csv`), `kind = str(w.kind)`.
- Tiến độ và log vẫn ra stderr; stdout chỉ có JSON.

### 4.3 Tiến độ, stderr
`[1/5] Export start…`, `[2/5] Gán tác giả…`, `[3/5] Export end…`, `[4/5] Đếm LOC…`, `[5/5] Tạo báo cáo…` — nhãn từ `pipeline.STEP_LABELS`, in mỗi khi pipeline gọi callback (cả khi `--json`). Log INFO của `loc_counter` vẫn ra stderr (callback `main` của app) song song với `run.log`.

## 5. Luồng xử lý
1. `_ensure_utf8` + logging stderr: callback `main` sẵn có.
2. **Kiểm tra tham số (trước khi tạo bất cứ gì trong `--out`, A2):** `dates = _parse_period_args(start, end, start_time, end_time)`; `cfg = load_config(config)`; `period = make_period(*dates, timezone=tz or cfg.timezone)`; `identity_map = load_identities(identities)`; `token = _read_token(token_env)`; `users = tuple(user) if user else None`.
3. `with pipeline.run_log(out, secrets=(token,)):` (lỗi `out` là file / không tạo được → `PipelineError`):
   1. `git = _open_repo(repo, token)`;
   2. `branch = _resolve_branch(git, branch)`;
   3. `resolver = pipeline.make_resolver(git.source, identity_map, token, login_cache=identity.DEFAULT_LOGIN_CACHE)`;
   4. `request = AnalysisRequest(branch=branch, period=period, config=cfg, out_root=out, users=users, exclude_bots=exclude_bots, separate_users=separate_users)`;
   5. `result = pipeline.run_analysis(git, request, resolver, progress=_print_progress)`;
   6. mọi `LocCounterError` / `OSError` ném ra trong khối `with` (3.1–3.5) **trừ** `PipelineError` và `SnapshotError` (pipeline đã tự log ERROR: `_error`, `prepare_period`, `logger.exception` từ bước 9 — spec `pipeline` mục 7) → `logger.error("Lỗi: %s", err)` (logger `loc_counter.cli`) **trước khi rời `with`** để `run.log` luôn có nguyên nhân (mở repo, nhánh, `GitError` trước bước 9 của pipeline); lỗi khác ném giữa chừng có thể có hai dòng ERROR (traceback của pipeline + dòng của CLI) — chấp nhận; rồi ném tiếp (A9).
4. Ngoài `with`: bắt `LocCounterError` / `OSError` từ bước 2–3 → `raise _fail(err)` (mã 1, `Lỗi: <str(err)>`); `KeyboardInterrupt` → stderr `Đã hủy phân tích.`, `typer.Exit(130)`.
5. Thành công: `--json` → `_print_analysis_json(result)`, ngược lại `_print_analysis_table(result)`; mã 0. Đọc lại `manifest.json` cho `--json` lỗi (`OSError`, JSON hỏng) → mã 1 `Lỗi: Không đọc được manifest.json: <lỗi>` (A11).

```text
parse/validate (no I/O in --out) ─► run_log(out) ─► open repo ─► branch ─► resolver
   ─► run_analysis(progress → stderr) ─► print table | JSON ─► exit 0
lỗi: LocCounterError/OSError → "Lỗi: …" exit 1; Ctrl+C → "Đã hủy phân tích." exit 130; typer → 2
```

## 6. Quy tắc nghiệp vụ & trường hợp biên
- **Không `--user`** → "Tất cả user" (`users=None`); CLI không thể tạo lựa chọn rỗng (lỗi "Chưa chọn user nào." chỉ xảy ra ở UI).
- **`--user` lặp lại / khác hoa thường / có khoảng trắng** → giao `match_users` (bỏ trùng, sắp, casefold duy nhất). Lỗi của `match_users` in nguyên văn.
- **`--separate-users` không kèm `--user`** → mỗi account của "Tất cả" một zip (theo `plan_end_exports`); một `--user` + `--separate-users` → một zip end.
- **`--exclude-bots`**: khác lệnh `users` (chỉ ẩn khỏi danh sách) — ở `analyze` nó đổi tập account được tính của "Tất cả" (D21); bot chọn tường minh qua `--user` vẫn được tính (D40-N19).
- **Kiểm tra chéo lệch / có cảnh báo** → mã 0; dòng `Kiểm tra chéo` báo `VƯỢT NGƯỠNG`.
- **Chạy lại cùng `--out` + cùng tham số** → thư mục kết quả cũ bị thay (pipeline 5.9); `run.log` bị ghi đè.
- **Đường dẫn `--out` tương đối** → pipeline `resolve()`; `Thư mục kết quả` in đường dẫn tuyệt đối.
- **Token** chỉ vào `_open_repo`, `make_resolver`, `run_log(secrets)`; không in, không đưa vào `AnalysisRequest`.
- **Không có commit trong kỳ** → bảng ngôn ngữ vẫn in (LOC start = end), `Theo user` in `Không có user nào có commit trong kỳ.`, `Commit 0`.

## 7. Xử lý lỗi & thông báo
| Tình huống | Hành vi | Thông báo (stderr) | `--out` / `run.log` |
|---|---|---|---|
| Ngày / giờ sai định dạng | mã 1 | `Lỗi: Ngày không hợp lệ cho --start: <x> (định dạng YYYY-MM-DD)` / `Lỗi: Giờ không hợp lệ cho --start-time: <x> (định dạng HH:MM)` | không tạo |
| `start ≥ end`, `--tz` sai | mã 1 | thông báo của `make_period` | không tạo |
| Config / identities lỗi | mã 1 | thông báo của `ConfigError` / `IdentityError` | không tạo |
| Biến token không có / rỗng | mã 1 | `Lỗi: Biến môi trường <NAME> chưa được đặt hoặc rỗng.` | không tạo |
| `--out` là file / không tạo được | mã 1 | `Lỗi: Thư mục đầu ra là một file: <p>` / `Lỗi: Không tạo được thư mục đầu ra <p>: <lỗi>` | — |
| Lỗi mở repo (clone/fetch, URL có credential, không có quyền) | mã 1 | thông báo của `GitError` (đã che token) | `run.log` có ERROR + lệnh git |
| Không xác định được nhánh / nhánh không có | mã 1 | `Lỗi: Không xác định được nhánh mặc định; hãy truyền --branch.` / thông báo `snapshot` | `run.log` có ERROR |
| Không có dữ liệu trước end | mã 1 | `Lỗi: Không có dữ liệu trong khoảng thời gian` | chỉ `run.log` |
| `--user` không có / mơ hồ / kỳ không có user | mã 1 | thông báo `match_users` (pipeline mục 7) | chỉ `run.log` |
| Đích không phải của tool, đường dẫn quá dài, không thay được thư mục cũ | mã 1 | thông báo `PipelineError` (pipeline 5.7–5.9) | thư mục cũ nguyên vẹn |
| Lỗi git / ghi zip / báo cáo giữa chừng | mã 1 | thông báo của module | `run.log` có traceback (pipeline) |
| `OSError` không được module bọc | mã 1 | `Lỗi: <str(err)>` | `run.log` có traceback |
| Đọc lại `manifest.json` lỗi khi `--json` | mã 1 | `Lỗi: Không đọc được manifest.json: <lỗi>` | thư mục kết quả đã ghi đủ |
| Ctrl+C | mã 130 | `Đã hủy phân tích.` | thư mục tạm đã dọn (pipeline) |
| Thiếu `--repo` / `--start` / `--end` / `--out`, tham số lạ | mã 2 | thông báo typer | không tạo |

## 8. Bảo mật, hiệu năng, tái lập
- **Token:** chỉ đọc `os.environ[<--token-env>]`; không có tùy chọn nhận token trực tiếp; không in ở stdout/stderr (lỗi đã che bởi `git_repo`, log stderr dùng chung logger nhưng mọi message có token đều đã che tại nguồn — `GitError`; `run.log` che thêm bằng formatter). Nguồn in ra là `repo.source` chuẩn hóa.
- **Hiệu năng:** CLI không thêm việc nặng; JSON đọc lại `manifest.json` một lần.
- **Tái lập:** bảng / JSON sắp ổn định (như `report`); stdout không chứa `generated_at` ngoài `manifest` trong JSON; tên thư mục tạm không xuất hiện.
- **Traceback:** `typer.Typer(..., pretty_exceptions_show_locals=False)` — traceback lỗi lập trình (nếu có) không in biến cục bộ (token) với mọi phiên bản typer được phép (`>=0.12`) (A12).
- **Windows:** stdout/stderr UTF-8 (`_ensure_utf8`); `run.log` được nhả khóa sau `with` (pipeline 5.5) → chạy lại / xóa ngay được.

## 9. Test cases
Fixture: `section14_repo` (tham số `name="repo"` để thư mục là `repo_…`), `identities.yaml` gộp `alice@example.com`→`alice`, `bob@example.com`→`bob` (dùng chung với `test_pipeline.py`); kỳ `--start 2026-01-01 --end 2026-01-31` (múi giờ mặc định); monkeypatch `git_repo.DEFAULT_CACHE_ROOT`, `identity.DEFAULT_LOGIN_CACHE` vào `tmp_path`; `typer.testing.CliRunner` (tách stdout / stderr).

| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-cli-analyze-01 | Tất cả user (bảng) | `analyze --repo <src> --branch main --start 2026-01-01 --end 2026-01-31 --identities <yaml> --out <tmp>` | mã 0; dòng `Repo:`, `Nhánh: main • Kỳ: …`, `User: Tất cả user`; LOC `10`, `20`, `+10`, Commit `4`; `Theo user` alice `2 5 2 +3`, bob `2 8 1 +7`, dòng `Tổng 4 13 3 +10`; `Kiểm tra chéo: … → đạt`; `Thư mục kết quả: …repo_main_2026-01-01_2026-01-31_all` | integration |
| TC-cli-analyze-02 | `--user alice` | như 01 + `--user alice` | LOC 10 / 13; `User: alice`; `Theo user` chỉ alice; thư mục `…_alice`; dòng `end_2026-01-31_alice.zip` | integration |
| TC-cli-analyze-03 | `--user bob` | | LOC 10 / 17; thư mục `…_bob` | integration |
| TC-cli-analyze-04 | alice + bob, có / không `--separate-users` | `--user bob --user alice` (+ biến thể `--separate-users`) | LOC 10 / 20; thư mục `…_multi-2users`; `User: alice, bob` (+ ` • Xuất riêng từng user`); biến thể: `Bản export` có 4 dòng (start, `multi-2users`, `alice` LOC 13, `bob` LOC 17), hai dòng riêng `kiểm tra chéo: đạt` | integration |
| TC-cli-analyze-05 | Đủ file §12 + `run.log` (mục E) | TC-01 | thư mục kết quả có `start_2026-01-01_<sha7>.zip`, `end_2026-01-31_all.zip`, `loc_report.xlsx`, 3 CSV, `warnings.csv`, `manifest.json`; `<tmp>/run.log` tồn tại, có dòng INFO `C_START=`; không có `.loc-tmp-*` | integration |
| TC-cli-analyze-06 | `--json` | TC-01 + `--json` | stdout parse được JSON, chỉ chứa JSON; `manifest` == nội dung `manifest.json`; `out_dir` == thư mục kết quả (POSIX); `files` sắp tăng dần, đủ 8 tên; `users` thứ tự alice, bob, có `net_code`, `files_changed`; `languages[0].delta == 10`; `warnings` là list | integration |
| TC-cli-analyze-07 | Tiến độ | TC-01 (cả `--json`) | stderr chứa đúng thứ tự `[1/5] Export start…` … `[5/5] Tạo báo cáo…`; không có dòng tiến độ nào trong stdout | integration |
| TC-cli-analyze-08 | `--user` không có / casefold | `--user zz`; `--user ALICE` | `zz`: mã 1, `Lỗi: Không tìm thấy user 'zz' trong kỳ. User trong kỳ: alice, bob`, không có thư mục kết quả; `run.log` có **đúng một** dòng ERROR chứa thông báo đó; `ALICE`: mã 0, thư mục `…_alice` | integration |
| TC-cli-analyze-09 | Không có dữ liệu | `--start 2020-01-01 --end 2020-01-31` | mã 1, `Lỗi: Không có dữ liệu trong khoảng thời gian`; `<tmp>` chỉ có `run.log` (có dòng ERROR) | integration |
| TC-cli-analyze-10 | Tham số sai — không tạo `--out` | `--start 2026-13-01`; `--end-time 25:00`; `--start 2026-02-01 --end 2026-01-01`; `--tz Mars/X`; `--config <file hỏng>` (YAML sai cú pháp → `File cấu hình không đúng định dạng YAML`); `--token-env NOPE` — `--out <tmp>/new` | mã 1, thông báo đúng mục 7; `<tmp>/new` không tồn tại | unit |
| TC-cli-analyze-11 | Thiếu tham số bắt buộc | thiếu `--out`; thiếu `--repo` | mã 2 | unit |
| TC-cli-analyze-12 | `--out` là file | `--out <file có sẵn>` | mã 1, `Lỗi: Thư mục đầu ra là một file: …`; file nguyên vẹn | integration |
| TC-cli-analyze-13 | Token (mục E) | `--token-env MYTOK` với `MYTOK=ghp_SECRET123` trên repo local | mã 0; `ghp_SECRET123` không có trong stdout, stderr, `run.log`, mọi file của thư mục kết quả (kể cả nội dung đã giải nén zip/xlsx), thư mục cache | integration |
| TC-cli-analyze-14 | Bot | `section14_repo(bot=True)`: (a) không cờ; (b) `--exclude-bots`; (c) `--user "dependabot[bot]" --exclude-bots` | (a) `Theo user` có `dependabot[bot]` cột Bot `bot`; (b) không có bot, `User: Tất cả user (loại trừ bot)`, kiểm tra chéo đạt; (c) mã 0, `User: dependabot[bot]`, bot trong `Theo user` | integration |
| TC-cli-analyze-15 | C_START rỗng | `--start 2025-01-01 --end 2026-01-31` | `Snapshot start: (không có commit trước start)`; LOC start `0`; dòng `start_2025-01-01_empty.zip  0 file  LOC 0`; admin trong `Theo user` | integration |
| TC-cli-analyze-16 | Không có commit trong kỳ | `--start 2026-01-09 --end 2026-01-20` | mã 0; `Không có user nào có commit trong kỳ.`; không có dòng `Tổng`; Commit `0`; Chênh lệch `0`; kiểm tra chéo `đạt` | integration |
| TC-cli-analyze-17 | Kiểm tra chéo lệch | repo ca lệch (đổi tên `.txt`→`.py` trong kỳ, fixture của `test_pipeline.py`) | mã 0; `Kiểm tra chéo: … → VƯỢT NGƯỠNG (xem warnings.csv)`; `Cảnh báo: <n≥1> (xem warnings.csv)` | integration |
| TC-cli-analyze-18 | Chạy lại cùng `--out` + tái lập (mục E) | TC-01 hai lần vào cùng `<tmp>`; rồi một lần vào `<tmp2>` | cả ba mã 0; lần 2 thay thư mục (file lạ thêm sau lần 1 biến mất); mọi file của `<tmp>/…_all` và `<tmp2>/…_all` trùng SHA-256 trừ `manifest.json` (bằng nhau khi bỏ `generated_at`) | integration |
| TC-cli-analyze-19 | `--identities` gộp | file gộp `alice@example.com`, `bob@example.com` → `team` | `Theo user` một dòng `team` Commit 4, Ròng `+10`; không có dòng alice/bob | integration |
| TC-cli-analyze-20 | Nhánh | không `--branch` → dùng `main` (thư mục `repo_main_…`); `--branch nope`; không `--branch` + `default_branch()` trả None (monkeypatch) | lần 1 mã 0; lần 2 mã 1, `Lỗi: Không tìm thấy nhánh: nope`, `run.log` có ERROR; lần 3 mã 1, `Lỗi: Không xác định được nhánh mặc định; hãy truyền --branch.` | integration |
| TC-cli-analyze-21 | Giờ + múi giờ | `--start-time 08:30 --tz UTC` | dòng `Kỳ: 2026-01-01 08:30:00 → 2026-01-31 23:59:59 (UTC)`; thư mục `repo_main_2026-01-01T0830_2026-01-31_all`; `manifest.timezone == "UTC"` | integration |
| TC-cli-analyze-22 | Lỗi bất thường / Ctrl+C | monkeypatch `pipeline.run_analysis` ném (a) `OSError("đĩa đầy")`, (b) `KeyboardInterrupt`; (c) `_open_repo` ném `GitError`; (d) `--json`, `manifest.json` bị xóa sau `run_analysis` | (a) mã 1, `Lỗi: đĩa đầy`; (b) mã 130, `Đã hủy phân tích.`; (c) mã 1, `run.log` có dòng ERROR chứa thông báo; (d) mã 1, `Lỗi: Không đọc được manifest.json:`, không traceback; `app.pretty_exceptions_show_locals is False` | unit |
| TC-cli-analyze-23 | Tham số truyền cho pipeline | spy `make_resolver`, `run_analysis` | `login_cache == identity.DEFAULT_LOGIN_CACHE` (đã monkeypatch); `AnalysisRequest.users` = `None` khi không `--user`, `("bob","alice")` theo thứ tự nhập khi có; `exclude_bots`, `separate_users`, `out_root`, `branch` đúng; `progress` khác None; không trường nào của request chứa token | unit |
| TC-cli-analyze-24 | Định dạng số | `_signed(0)`, `_signed(1234)`, `_signed(-5)`; bảng có giá trị ≥ 1.000 (monkeypatch `run_analysis` trả `AnalysisResult` giả) | `"0"`, `"+1,234"`, `"-5"`; cột số căn phải, có dấu phẩy hàng nghìn; dòng `Cảnh báo: 0` khi không có cảnh báo; biến thể `languages` rỗng → dòng `Không có file source nào.` | unit |

Phủ mandatory-tests mục E (đủ file, `run.log`, tên thư mục / user-tag, token, tái lập): TC-01..05, 13, 18; tiêu chí M5 số 2 (`analyze` trên repo §14): TC-01..04; số 8 (mã lỗi): TC-08..11.

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | `--branch` không bắt buộc (như `users`, cli-users A1); `--json` tùy chọn | PLAN M5, D40-N22 | Chốt (*) |
| A2 | Kiểm tra tham số rẻ (ngày, giờ, config, `--tz`, identities, token) **trước** `run_log` → sai tham số không tạo `--out` / `run.log`; từ `GitRepo.open` trở đi nằm trong `run_log` (pipeline A1) để lỗi clone/fetch vào `run.log` (§15) | Khuyến nghị | Chốt (*) |
| A3 | Không truyền `--user` → `users=None`; CLI truyền giá trị thô theo thứ tự nhập, `match_users` chuẩn hóa | pipeline A4 | Chốt (*) |
| A4 | `--json`: `{out_dir, files, manifest, languages, users, warnings}`; `manifest` đọc lại từ file đã ghi (khớp tuyệt đối) | Khuyến nghị | Chốt (*) |
| A5 | Ctrl+C → mã 130 + `Đã hủy phân tích.`; `OSError` không được bọc → mã 1 `Lỗi: <err>` (thay vì traceback) | Khuyến nghị | Chốt (*) |
| A6 | Dòng `Tổng` của `Theo user` in khi có ≥ 1 dòng (cả khi chọn user) — thống nhất với xlsx (`report` luôn có dòng Tổng); §10.3 chỉ bắt buộc khi "Tất cả" | Khuyến nghị | Chốt (*) |
| A7 | Dòng `Kỳ` dùng định dạng đầy đủ `%Y-%m-%d %H:%M:%S` + tên múi giờ như `users` (thay vì `2026-01-01 → … (UTC+7)` của §10.3) để thấy giờ đã nhập | Khuyến nghị | Chốt (*) |
| A8 | Tiến độ in ra **stderr** (`[i/5] <nhãn>…`) để stdout sạch cho `--json` / pipe | Khuyến nghị | Chốt (*) |
| A9 | Lỗi nghiệp vụ trong `run_log` mà pipeline **chưa** log (mở repo, nhánh, `GitError` trước bước 9, `OSError`…) được CLI log một dòng ERROR để `run.log` luôn có nguyên nhân; `PipelineError`, `SnapshotError` pipeline đã log ERROR → CLI không log lại (tránh lặp 2–3 dòng, review 2026-10-25) | Khuyến nghị (sửa theo review) | Chốt (*) |
| A11 | `--json` đọc lại `manifest.json` lỗi → mã 1 `Lỗi: Không đọc được manifest.json: …` thay vì traceback (theo A5) | Khuyến nghị review | Chốt (*) |
| A12 | `pretty_exceptions_show_locals=False` tường minh: typer cũ (mặc định bật) in biến cục bộ trong traceback → lộ token | Khuyến nghị review | Chốt (*) |
| A10 | Cảnh báo chỉ in số lượng (+ trỏ `warnings.csv`); chi tiết trong `--json` | Khuyến nghị, theo §10.3 "⚠ 12 cảnh báo" | Chốt (*) |

(*) Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-23 ("trường hợp có hỏi xác nhận thì thực hiện theo recommend"); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-25 | Theo review `reviews/cli-analyze-20261025.md`: 5.3.6 / A9 không log lại `PipelineError`, `SnapshotError`; 5.5 + A11 lỗi đọc `manifest.json` khi `--json`; mục 8 + A12 `pretty_exceptions_show_locals=False`; TC-08, 10, 20, 22, 24 thêm biến thể. Chốt theo khuyến nghị, người dùng ủy quyền | review PASS_WITH_NOTES (Minor 1–4) |
| 2026-10-24 | Tạo mới theo PLAN M5 (phạm vi `cli-analyze`, D40-N19, N22) và API spec `pipeline` mục 3. A1–A10 chốt theo khuyến nghị, người dùng ủy quyền → `approved` | M5 (`/feature-spec cli-analyze`) |
