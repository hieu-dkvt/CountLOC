# Review: cli-analyze — 2026-10-25
Kết luận: PASS_WITH_NOTES
Spec: docs/specs/cli-analyze.md (status: approved — chưa chuyển `implemented`)   Files: src/loc_counter/cli.py (phần `analyze`, dòng 285–445, cùng các hàm dùng chung), tests/test_cli_analyze.py

## Bằng chứng tự động
- ruff: `uv run ruff check src tests` → All checks passed!
- pytest: `tests/test_cli_analyze.py` 25 passed (44 s); toàn bộ suite 681 passed (360 s), không hồi quy.
- coverage (`test_cli_analyze.py` + `test_cli_users.py` + `test_cli_count.py`, `--cov=loc_counter.cli`): 99 % — thiếu dòng 168 (`_resolve_branch`: không xác định được nhánh mặc định), 188 (`_commit_json(None)` của `users`), 333 (`Không có file source nào.`).
- Kiểm chứng thủ công (script tạm trong scratchpad, repo §14 dựng bằng `conftest.RepoBuilder`): `--user zz`, `--user ""`, `--identities <không có>`, `--branch --all`, `--start-time 8:30`, `--tz ""`, `--help`, lỗi bất thường `ValueError` có `--token-env` chạy bằng tiến trình thật (`cli.app()`), không qua `CliRunner`.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| §3 Giao diện | Tham số, mặc định, mã thoát 0/1/2/130 | cli.py:392–415 (`--help` hiển thị đủ 15 tùy chọn); TC-11 mã 2, TC-22 mã 1/130 | Đạt |
| 5.1 | `_ensure_utf8` + logging stderr qua callback `main` | cli.py:44–49 | Đạt |
| 5.2 | Kiểm tham số trước khi tạo `--out` (ngày/giờ → config → period → identities → token → users) | cli.py:418–423; TC-10 (6 ca, `<tmp>/new` không tồn tại); thử `--identities` không có → `--out` không tạo | Đạt |
| 5.3 | `run_log(out, secrets=(token,))` bọc open → branch → resolver → request → run_analysis | cli.py:424–433; TC-05, TC-22c, TC-23 | Đạt |
| 5.3.6 | Log `Lỗi: …` (logger `loc_counter.cli`) trước khi rời `with`, rồi ném tiếp | cli.py:434–436; TC-20 (`run.log` có ERROR), TC-22c | Đạt |
| 5.4 | `LocCounterError`/`OSError` → `_fail` mã 1; Ctrl+C → `Đã hủy phân tích.` mã 130 | cli.py:437–441; TC-22a/b | Đạt |
| 5.5 | Thành công → bảng / JSON | cli.py:442–445 | Đạt (xem Minor 2 về lỗi khi in JSON) |
| 4.1 Header | Repo, Nhánh/Kỳ, Snapshot (dùng chung `users`) | `_print_period_header` cli.py:198–207; TC-01, TC-15, TC-21 | Đạt |
| 4.1 `User:` | Tất cả user (+ loại trừ bot) / danh sách / ` • Xuất riêng từng user` | cli.py:310–316; TC-01, 02, 04, 14 | Đạt |
| 4.1 Bảng tổng | LOC start/end, `_signed(delta)`, Σ commit | cli.py:317–321; TC-01, 16, 24 | Đạt |
| 4.1 Theo ngôn ngữ | sắp `(-loc_end, -loc_start, language)`; rỗng → `Không có file source nào.` | cli.py:325–333 (cùng khóa với `report._sorted_languages`) | Đạt; nhánh rỗng chưa test |
| 4.1 Theo user | sắp `(-commits, account)`, cột Bot, dòng Tổng khi ≥ 1 dòng (A6), rỗng → thông báo | cli.py:337–350; TC-01, 14, 16, 19 | Đạt |
| 4.1 Kiểm tra chéo | định dạng `{:.3f}`, `{:g}`, `→ đạt` / `→ VƯỢT NGƯỠNG (xem warnings.csv)` | `_check_text` cli.py:297–302; TC-01, 17 | Đạt |
| 4.1 Bản export | mỗi `ExportSummary` một dòng; role `separate` thêm kiểm tra chéo | cli.py:354–362; TC-04, 15 | Đạt |
| 4.1 Cảnh báo / Thư mục | `Cảnh báo: n` (+ `(xem warnings.csv)`), đường dẫn tuyệt đối | cli.py:363–365; TC-01, 17, 24 | Đạt |
| 4.2 JSON | 6 key đúng thứ tự, `out_dir` POSIX, `files` sắp, `manifest` đọc lại, warnings sắp `(path, kind)` | cli.py:368–389; TC-06 | Đạt |
| 4.3 Tiến độ | `[i/5] <nhãn>…` ra stderr, cả khi `--json` | cli.py:287–289; TC-07 (2 biến thể) | Đạt |
| §6 | `--user` thô theo thứ tự nhập, `users=None` khi không có | cli.py:423; TC-23 | Đạt |
| §6 | Token không vào `AnalysisRequest` | TC-23 (`repr(req1)`), TC-13 | Đạt |
| §7 | Bảng lỗi (ngày, giờ, start ≥ end, tz, config, token, `--out` là file, repo, nhánh, không dữ liệu, `--user`) | TC-08, 09, 10, 12, 20, 22 | Đạt (ca `--out` không tạo được / `--identities` hỏng không có test CLI — có ở test pipeline / identity) |
| §8 | Token chỉ từ env; stdout tái lập, không tên thư mục tạm | TC-13, TC-18; chạy thử: stdout không chứa `.loc-tmp-*` | Đạt (xem Minor 3) |
| TC-01 … TC-24 | 24 TC | 24 hàm test, docstring bắt đầu đúng ID; TC-07 tham số hóa 2 biến thể | Đạt (TC-10 ca config assertion yếu — Minor 4) |

## Phát hiện

### [Minor] Thông báo lỗi nghiệp vụ in lặp 2–3 lần trên stderr — `src/loc_counter/cli.py:435`, `:53`
- Mô tả: callback `main` gắn handler stderr cho root logger (cli.py:48), nên mỗi lỗi vừa được `logger.error("Lỗi: %s")` (cli.py:435) vừa được `_fail` in (cli.py:53); thêm nữa pipeline cũng tự log ERROR (`_error`, `prepare_period`).
- Kịch bản (đã chạy): `analyze --repo <§14> --start 2026-01-01 --end 2026-01-31 --user zz --out <tmp>` → stderr có 3 dòng cùng nội dung:
  ```
  ERROR loc_counter.pipeline: Không tìm thấy user 'zz' trong kỳ. User trong kỳ: …
  ERROR loc_counter.cli: Lỗi: Không tìm thấy user 'zz' trong kỳ. User trong kỳ: …
  Lỗi: Không tìm thấy user 'zz' trong kỳ. User trong kỳ: …
  ```
  `--branch --all` → 2 dòng. `run.log` cũng có 2 dòng ERROR trùng.
- Đánh giá: code đúng chữ spec (5.3.6 + 4.3 — log stderr song song `run.log`), nhưng người dùng CLI thấy cùng một lỗi lặp lại; không sai số liệu.
- Đề xuất: (cần quyết định ở spec) hoặc gắn filter cho handler stderr bỏ qua record ERROR của `loc_counter.cli` (chỉ để `run.log` nhận), hoặc chỉ log bù khi lỗi chưa được pipeline log (ví dụ chỉ cho `GitError` / lỗi trước `run_analysis`). Tham chiếu: spec cli-analyze 5.3.6, A9, 4.3; PLAN dòng 148.

### [Minor] `OSError` khi in kết quả JSON không được ánh xạ sang mã 1 — `src/loc_counter/cli.py:377-378`, `:442-443`
- Mô tả: `_print_analysis_json` đọc `out_dir.iterdir()` và `manifest.json` sau khi đã ra khỏi khối `try` (cli.py:442). Spec A5 / mục 7 yêu cầu `OSError` không được bọc → `Lỗi: <err>` mã 1 thay vì traceback.
- Kịch bản (suy luận, chưa tái hiện): chạy `--json`, ngay sau khi pipeline đổi tên thư mục kết quả thì phần mềm diệt virus / tiến trình khác khóa hoặc xóa `manifest.json` → `PermissionError`/`FileNotFoundError` → typer in traceback, mã 1, không có dòng `Lỗi: …`. Tỷ lệ xảy ra thấp.
- Đề xuất: bọc nhánh in JSON (hoặc cả bước 5) bằng `except OSError as err: raise _fail(err) from None`; hoặc ghi rõ trong spec mục 7 rằng bước in nằm ngoài ánh xạ lỗi. Tham chiếu: spec cli-analyze A5, mục 7 dòng "`OSError` không được module bọc".

### [Minor] Phòng thủ token: không tắt tường minh `pretty_exceptions_show_locals` của typer — `src/loc_counter/cli.py:32`
- Mô tả: `analyze_command` giữ token trong biến cục bộ `token` suốt thời gian chạy pipeline. Với exception ngoài `LocCounterError`/`OSError` (bug, `ValueError`, lỗi thư viện xlsx/zip…), typer in traceback qua rich. Bản typer đang khóa trong `uv.lock` (0.27.3) mặc định `pretty_exceptions_show_locals=False` → **không lộ** (đã kiểm: chạy tiến trình thật, `run_analysis` ném `ValueError`, `--token-env MYTOK` → stderr không chứa token). Nhưng `pyproject.toml` cho phép `typer>=0.12`; các bản typer cũ mặc định hiển thị biến cục bộ (chưa kiểm chứng chính xác phiên bản đổi mặc định).
- Kịch bản (đã kiểm chứng bằng cách bật `cli.app.pretty_exceptions_show_locals = True` để giả lập bản cũ): `run_analysis` ném `ValueError` → stderr có dòng `token = 'ghp_SECRET123'`, vi phạm quy tắc 6 CLAUDE.md / §15.
- Đề xuất: `typer.Typer(add_completion=False, no_args_is_help=True, pretty_exceptions_show_locals=False)` (có thể kèm test khẳng định thuộc tính này). Không cần đổi spec. Tham chiếu: §11, §15, spec cli-analyze §8 (Token).

### [Minor] Test chưa phủ / assertion yếu — `tests/test_cli_analyze.py:230`; `src/loc_counter/cli.py:333`, `:168`
- `TC-cli-analyze-10` ca `--config <file hỏng>` chỉ kiểm `"Lỗi: " in r.stderr` — đạt với bất kỳ lỗi nào (kể cả lỗi khác hoàn toàn); spec yêu cầu "thông báo của `ConfigError`". Đề xuất kiểm `"File cấu hình không đúng định dạng YAML"`.
- Nhánh `Không có file source nào.` (spec 4.1) và nhánh `Không xác định được nhánh mặc định; hãy truyền --branch.` (spec mục 7) không có test nào chạy qua (coverage báo dòng 333, 168). Spec không có TC riêng cho hai nhánh này → xem Ghi chú cho spec.

### [Nit] Cột `LOC` của khối "Bản export" căn trái — `src/loc_counter/cli.py:360-361`
- `right={1}` chỉ căn phải cột `<n> file`; cột `LOC <n>` là chuỗi có tiền tố nên số không thẳng hàng phải khi độ dài khác nhau (ví dụ `LOC 10` / `LOC 1,020`). Spec 4.1 nói chung "cột số căn phải" nhưng mẫu không đủ để kết luận. Đề xuất tách `LOC` và số thành hai cột, căn phải cột số.

### [Nit] `--tz ""` lặng lẽ dùng múi giờ của config — `src/loc_counter/cli.py:420`
- `tz or cfg.timezone` coi chuỗi rỗng như không nhập (đã chạy: mã 0, `Asia/Bangkok`). Chấp nhận được, nhưng khác `--start-time ""` (báo lỗi). Đề xuất `tz if tz is not None else cfg.timezone` để `make_period` báo `Múi giờ không hợp lệ:`; hoặc giữ nguyên và ghi vào spec.

### [Nit] Trạng thái spec chưa cập nhật — `docs/specs/cli-analyze.md:10`
- Test đã pass nhưng `status: approved` (README cũng `approved`); theo vòng đời phải là `implemented` trước khi review.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Mọi bước 5.1–5.5 có trong code đúng thứ tự; giao diện khớp mục 3 (chỉ thêm helper private `_check_text`); 24/24 TC có test. Assertion yếu ở TC-10 ca config (Minor 4). Lệnh git / thuật toán §6, §7: N/A — CLI không gọi git trực tiếp |
| 2. Nghiệp vụ dễ sai | N/A | CLI chỉ trình bày; số liệu lấy nguyên từ `ReportData` (Σ commit tính từ `user_rows`, sắp xếp cùng khóa với `report`) |
| 3. Bảo mật | Đạt, có ghi chú | Token chỉ từ env, vào `_open_repo`/`make_resolver`/`run_log`; TC-13 quét stdout, stderr, `run.log`, zip/xlsx giải nén, cache. `--branch --all` bị `git_repo` chặn. Minor 3: nên tắt `show_locals` tường minh |
| 4. Lỗi & log | Đạt, có ghi chú | Thông báo tiếng Việt; `run.log` luôn có nguyên nhân; không nuốt exception. Minor 1 (lặp thông báo), Minor 2 (OSError khi in JSON) |
| 5. Tái lập & encoding | Đạt | Bảng/JSON sắp ổn định; TC-18 trùng SHA-256 giữa hai `--out`; stdout không có tên thư mục tạm; `_ensure_utf8` |
| 6. Windows | Đạt | `pathlib`; `Thư mục kết quả` dạng OS, JSON dạng POSIX; `run.log` đóng sau `with` trước khi đọc `manifest.json` |
| 7. Chất lượng code | Đạt | Type hint + docstring tiếng Việt cho hàm mới; ruff sạch; không thư viện mới. (`_fail`, `_commit_text` thiếu docstring — có từ `cli-users`, ngoài phạm vi) |
| 8. Hiệu năng | N/A | CLI không thêm việc nặng; JSON đọc `manifest.json` một lần |
| 9. Streamlit | N/A | Không phải spec `screen-*` |

## Ghi chú cho spec
1. **A9 / 5.3.6 và PLAN dòng 148 mâu thuẫn:** PLAN ghi "pipeline tự log ERROR cho lỗi trước bước 9 … nên CLI không cần ghi bù theo A9", còn spec vẫn yêu cầu CLI log mọi lỗi. Code theo spec → ERROR trùng trong `run.log` và stderr (Minor 1). Cần người dùng chốt: giữ log bù cho mọi lỗi, chỉ log bù cho lỗi pipeline chưa log (`GitError` khi mở repo / nhánh, `OSError`), hay lọc handler stderr.
2. **Lỗi khi in kết quả** (sau `run_log`) chưa có trong bảng mục 7 — nên ghi rõ (Minor 2).
3. **TC thiếu** cho nhánh `Không có file source nào.` (ví dụ repo chỉ có file bị loại) và `Không xác định được nhánh mặc định` (repo HEAD trỏ nhánh không tồn tại, không `--branch`) — đề xuất thêm TC-25/TC-26.
4. `--tz ""`: nên quy định coi là không nhập hay báo lỗi (Nit).
