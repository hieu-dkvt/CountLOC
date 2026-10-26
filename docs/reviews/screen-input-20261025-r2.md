# Review: screen-input (lần 2, r2) — 2026-10-25
Kết luận: **PASS_WITH_NOTES**
Spec: docs/specs/screen-input.md (status: approved — bản có A13–A16, TC-24, mục Lịch sử "Theo review …")   Files: `src/loc_counter/app.py`, `tests/test_app_input.py` (+ fixture `make_app` trong `tests/conftest.py`)
Đối chiếu với: [screen-input-20261025.md](screen-input-20261025.md) (lần 1, FAIL: Major J1, J2; Minor M1–M6; Nit N1–N3)

## Bằng chứng tự động
- ruff `src tests`: `All checks passed!`
- pytest `tests/test_app_input.py`: **33 passed** / 0 failed (75.5 s) — Streamlit 1.66.1, CPython 3.14.7, Windows 11
- coverage `loc_counter.app`: **97 %** (363 stmt, thiếu 305-309, 311, 318, 368, 420-422, 478)
- Script kiểm chứng (AppTest, ngoài repo): `C:\Users\User\AppData\Local\Temp\claude\d--PJ-Tool\c51e6e46-cbc8-49e8-ab4c-ee7a36ec2b9e\scratchpad\rv2\test_probe.py` — kết quả trích trong từng phát hiện.

## Trạng thái phát hiện lần 1
| # | Lần 1 | Sửa | Kiểm chứng | Trạng thái |
|---|---|---|---|---|
| J1 | Major — tz config ngoài `timezone_options()` → `Africa/Abidjan` | `canonical_timezone` (app.py:78-84), `_load_config_file` (app.py:418-425), chặn ở `_render_period` (app.py:303-318) | `test_canonical_timezone`: `timezone: singapore` → `tz == "Singapore"`, kỳ `+08:00` | **Đã sửa** |
| J2 | Major — dòng snapshot nằm trong khối [3] | `st.container()` giữ chỗ trong `_render_period` (app.py:316), vẽ ở app.py:534-540 | `test_review_fixes`: chỉ số `→ Snapshot` < chỉ số subheader `[3]` | **Đã sửa** |
| M1 | Minor — mất nhánh khi đổi/trả token | `branch_value` (app.py:259, 283-286) | `test_review_fixes` (main); probe: chọn `dev` → đổi token → trả lại → vẫn `dev`; Tải repo lại → `main` | **Đã sửa** |
| M2 | Minor — khóa `out:` phân biệt hoa thường | `os.path.normcase` (app.py:480) | test dùng cùng tên khóa | **Đã sửa** |
| M3 | Minor — identities là thư mục bị bỏ qua | app.py:332-335 | `test_review_fixes` | **Đã sửa** |
| M4 | Minor — `logger.exception` ngoài `run_log` | app.py:498-504 (trong `with run_log`) | `test_no_branches_and_lock_release`: `ERROR` + `Traceback` trong `run.log` | **Đã sửa** (xem Nit N4: log 2 lần) |
| M5 | Minor — test chưa đủ | `test_success_line`, `test_no_branches_and_lock_release`, `test_review_fixes` | TC-14 dòng xong, TC-18 nhả khóa sau lỗi, identities hỏng, không nhánh: đã có | **Phần lớn đã sửa** — còn Minor R1 |
| M6 | Minor — type hint `Any` | `MemoEntry`, `PeriodContext | None`, `AccountResolver | None` | đọc code | **Đã sửa** (còn `Any` cho container — chấp nhận) |
| N1 | Nit — lỗi nạp config cũ không xóa | app.py:410 | probe: lỗi YAML → ô rỗng + Nạp → `at.error == []` | **Đã sửa** (test chưa chứng minh — R1) |
| N2 | Nit — API ngoài §3.4 / chữ ký khác | — | `FORM_KEYS`, `EXPORT_MODES`, `MIN_DATE`, `MAX_DATE`, `MemoEntry` vẫn công khai; `_render_users(locked, ctx, identities_error)`, `_render_period` trả 3 phần tử | **Còn** (N2) |
| N3 | Nit — `list_branches`/`default_branch` ngoài khóa cache | — | app.py:249-252 | **Còn** (N3) |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.1 | page config, `_init_state` (có `branch_value`, `config_load_error`), `locked` | app.py:518-522, 223-239 / TC-01 | Đạt |
| 5.2.1-2 | `clean_source`, nút disabled, spinner, khóa `repo:` có chờ, `normalize_source` lỗi → hiển thị | app.py:242-259, 269-271 / TC-03, TC-04 | Đạt |
| 5.2.3-4 | `repo_error`; nguồn/token đổi → warning, chặn (A11) | app.py:272-279 / TC-21 | Đạt |
| 5.2.5 + A15 | selectbox nhánh; không nhánh → `Repo không có nhánh nào.`; `branch_value` | app.py:280-287 / TC-24 | Đạt (không truyền `index=None` nhưng `ss.branch` luôn được đặt trước — probe: nhánh mặc định `None` → value `None`, lý do `Chưa chọn nhánh.`) |
| 5.3.1-2 | date/time 2 cột, `make_period`, lỗi → `st.error` | app.py:293-326 / TC-06 | Đạt |
| 5.3.3 | identities rỗng/vắng/thư mục/hỏng | app.py:329-339 / TC-24 | Đạt |
| 5.3.4 | memo 1 mục, khóa `(repo_gen, branch, period, identity_map, bool(token))`, lỗi cũng memo (A4) | app.py:342-359 / TC-05 | Đạt |
| 5.3.5 | snapshot + lỗi `prepare_period` trong container của [2], `st.text` | app.py:316, 534-540 / TC-03, TC-08, TC-24 | Đạt |
| 5.3.6 + A14 | tz ngoài options → canonical hoặc lỗi + chặn | app.py:303-318 | Đạt về code; nhánh lỗi không có test (Nit N1) |
| 5.4 | radio, reconcile + info, không user, chỉ đọc / checkbox + tìm + "Đã chọn N", cảnh báo | app.py:371-403 / TC-09..11, TC-23 | Đạt |
| 5.4.7 | `render_identity_panel` | — | N/A (chưa có `screen-identity`) |
| 5.5.1 + A14 | Nạp: rỗng xóa lỗi; tz canonical / lỗi; `adv_*` + `tz` | app.py:406-425 / TC-13, TC-24 | Đạt (nhánh tz `None` 420-422 không test — khó đạt tới, vì `config_from_dict` đã từ chối tên không mở được) |
| 5.5.2 | 8 widget, `form_config`, lỗi trong expander | app.py:428-456 / TC-13 | Đạt (thứ tự/nhãn lệch nhẹ — Nit N5) |
| 5.6.1-3 | `out_dir`, blockers → `st.info`, nút, `run_error`, `st.success` | app.py:544-559 / TC-01, 09, 14, 19, 22 | Đạt |
| 5.6.4 + A13, A16 | cờ trả trước, progress, khóa `out:` normcase không chờ, `run_log(secrets)`, INFO, `build_request`, `logger.exception` trong `run_log`, nhả khóa, `st.rerun` | app.py:465-513 / TC-14..19, TC-24 | Đạt |
| §6 | không fetch lại; cùng resolver; Loại trừ bot; C_START rỗng; kỳ không user | TC-16, 11, 08, 23 | Đạt |
| §7 | thứ tự lý do 1→8 | app.py:169-184 / TC-22 | Đạt |
| §8 | token chỉ session; không vào memo key / sig / log / thông báo | app.py:346, 485, 554 / TC-20 | Đạt |
| TC-01..23 | | test tương ứng (33 test) | Đạt (TC-04 assertion yếu — R1) |
| TC-24 | canonical tz; config `singapore`; token đổi/trả; identities thư mục/hỏng; không nhánh; khóa nhả sau lỗi; traceback run.log; snapshot trong [2] | `test_canonical_timezone`, `test_review_fixes`, `test_no_branches_and_lock_release` | Đạt |

## Phát hiện

### [Minor] R1 — Một vài assertion vẫn chưa kiểm đúng điều TC/sửa đổi mô tả — `tests/test_app_input.py:154-161`, `tests/test_app_input.py:592-597`, `tests/test_app_input.py:541-543`
- **TC-04** ("`st.error` tiếng Việt" cho cả hai input): `test_load_error` chỉ `assert at.error`; `test_success_line` chỉ kiểm ca `does-not-exist-dir` bằng tiền tố lỏng (`"Không" | "Đường dẫn" | "Repo" | "Nguồn"`). Ca `https://u:p@github.com/o/r` không có assertion nội dung. Probe xác nhận hành vi đúng (`URL repo không được chứa thông tin xác thực. Hãy nhập token ở ô/biến môi trường riêng.`) nhưng nếu thông báo bị thay bằng chuỗi tiếng Anh / chứa `u:p` thì test vẫn pass.
- **N1 (ô config rỗng xóa lỗi cũ)**: `test_canonical_timezone` bấm "Nạp" với ô rỗng sau một lần nạp **thành công** (không có lỗi trước đó) → assertion `not [... "File cấu hình" ...]` đúng cả khi chưa sửa. Probe: nạp `bad.yaml` (lỗi) → ô rỗng + Nạp → lỗi biến mất (hành vi đúng, test không chứng minh).
- `_toggle` nhánh bỏ chọn (app.py:368) không có test; probe: tick rồi bỏ tick alice → `selected == set()`, `Đã chọn 0 user` (đúng).
- **Đề xuất:** TC-04 assert chuỗi cụ thể cho từng input (vd. `"không được chứa thông tin xác thực"` và không chứa `u:p`); ca N1 nạp file hỏng trước khi bấm Nạp với ô rỗng; thêm bước bỏ tick vào TC-09 hoặc TC-10.
- **Tham chiếu:** §9 TC-04, TC-24; checklist 1 ("test thật sự kiểm điều TC mô tả").

### [Nit] N1 — Nhánh lỗi múi giờ ở `_render_period` (5.3.6) không có test và gần như không thể đạt tới — `src/loc_counter/app.py:304-311, 318`
- `ss.tz` chỉ được ghi bởi selectbox (giá trị trong options) và `_load_config_file` (đã qua `canonical_timezone`), nên `tz_error` không xảy ra qua UI. Không kiểm chứng được qua AppTest (gán `session_state["tz"] = "Mars/X"` làm AppTest lỗi `list.index` khi gửi lại giá trị selectbox). Chưa kiểm chứng: nếu nhánh này xảy ra, selectbox `tz` không được vẽ nên Streamlit có thể dọn state, rerun kế tiếp `_init_state` đặt lại `Asia/Bangkok` — trái ý "giữ nguyên và báo + chặn". Rủi ro thực tế thấp; ghi nhận để `screen-identity`/`screen-result` không ghi `ss.tz` trực tiếp mà không qua `canonical_timezone`.

### [Nit] N2 — API mức module ngoài §3.4 / chữ ký khác spec (còn từ lần 1) — `src/loc_counter/app.py:43-48, 290, 371`
- `FORM_KEYS`, `EXPORT_MODES`, `MIN_DATE`, `MAX_DATE`, `MemoEntry` công khai; `_render_users(locked, ctx, identities_error)` và `_render_period` trả `(period, lỗi, container)` khác §3.4 (`_render_users(locked, ctx)`, `_render_period(locked)`). Đề xuất thêm tiền tố `_` hoặc cập nhật §3.4.

### [Nit] N3 — `list_branches()` / `default_branch()` chạy ngoài khóa cache repo (còn từ lần 1) — `src/loc_counter/app.py:249-252`
- Rủi ro thấp (git cập nhật ref nguyên tử); đưa vào trong `with` cho đúng 5.2.2.

### [Nit] N4 — Lỗi bất thường trong thân `run_analysis` được ghi traceback **hai lần** trong `run.log` — `src/loc_counter/app.py:501-504`, `src/loc_counter/pipeline.py:577-578`
- Probe: `write_reports` giả ném `ValueError` → `run.log` có `ERROR … Phân tích thất bại: …` + traceback (pipeline) **và** `ERROR … Lỗi không mong đợi khi phân tích` + traceback (app); `log.count("Traceback") == 2`. Không sai, chỉ thừa. Lỗi ném **trước** khối `try` của pipeline (vd. `ValueError("context không khớp …")`, pipeline.py:458) chỉ app ghi — nên giữ log ở app; có thể dùng `logger.error(...)` không traceback khi đã có `__traceback__` được pipeline ghi, hoặc chấp nhận.

### [Nit] N5 — Thứ tự / nhãn widget nâng cao lệch nhẹ §3.1-3.2 — `src/loc_counter/app.py:443-449`
- §3.1: "… Loại file binary / Kích thước tối đa (KB) / Tính file test / Tính docstring …"; code vẽ "Kích thước tối đa (KB)" trước "Loại file binary"; nhãn "Tính docstring là code", "Ngôn ngữ loại trừ (tên lexer Pygments, …)" dài hơn spec. Không ảnh hưởng chức năng.

### [Nit] N6 — Spinner "Đang tính snapshot và danh sách user…" hiện trong khối [3] — `src/loc_counter/app.py:533`
- `_period_context` được gọi sau ô "File identities", nên spinner xuất hiện dưới tiêu đề [3] trong khi kết quả hiện ở [2]. Spec không quy định vị trí spinner; có thể bọc `with snapshot_box:` quanh lời gọi.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt (có ghi chú) | Mọi bước 5.1–5.6, A13–A16 có trong code; mọi TC-01..24 có test; R1 (assertion yếu), N2 (API/chữ ký) |
| 2. Nghiệp vụ dễ sai | Đạt | UI không tự tính LOC; snapshot/attribution qua `pipeline`; kỳ đúng múi giờ sau A14 (TC-24 `+08:00`); C_START rỗng, kỳ không user (TC-08, TC-23); E2E §14 10/20, 10/13, 10/17, 10/20 (TC-17) |
| 3. Bảo mật | Đạt | Token: password, chỉ session/`loaded_with`/GitRepo/resolver; không vào memo key, `sig`, log; `run_log(secrets)`; lỗi bất thường log trong `run_log` (che token); TC-20 quét cây phần tử, run.log, zip/xlsx, cache, `github_logins.json` |
| 4. Lỗi & log | Đạt (có ghi chú) | Thông báo tiếng Việt; INFO `Phân tích từ giao diện:` (TC-17); traceback vào `run.log` (TC-24); N4 log hai lần |
| 5. Tái lập & encoding | Đạt (có ghi chú) | `users` sắp; múi giờ tường minh, quy về tên IANA chuẩn; xem Ghi chú cho spec 1 (khác hoa thường với CLI) |
| 6. Windows | Đạt | `normcase` khóa `out:`; `canonical_timezone` cho tên tz không phân biệt hoa thường; `clean_source` bỏ nháy; `pathlib` |
| 7. Chất lượng code | Đạt (có ghi chú) | ruff sạch; type hint cụ thể; docstring tiếng Việt; không thư viện ngoài §4; N2, N3 |
| 8. Hiệu năng | N/A (M7) | `prepare_period` chỉ khi khóa memo đổi (TC-05) |
| 9. Màn hình Streamlit | Đạt | Bố cục [1][2][3] + expander + nút (TC-01, snapshot trong [2] — TC-24); mặc định ngày/tz/radio; validate start<end, ≥1 user; khóa ô nhập (TC-15); 5 bước tiến độ (TC-14); AppTest. Ghi chú §7.5 thuộc `screen-result` (N/A) |

## Ghi chú cho spec
1. **Vẫn chưa ghi vào PLAN** (Ghi chú 1 của review lần 1): `config.config_from_dict` trên Windows chấp nhận `timezone: singapore`. UI nay quy về `Singapore` (A14) còn CLI giữ `singapore` → cùng offset, cùng số liệu, nhưng `Period.timezone` / manifest / log khác chuỗi, nên R14 ("cùng `AnalysisRequest` như CLI") chỉ đúng khi tên tz đã chuẩn. Đề xuất ghi một câu hỏi mở trong PLAN: chuẩn hóa ở `config` (dùng chung `canonical_timezone`) hay chấp nhận.
2. §3.4 nên cập nhật chữ ký `_render_period` / `_render_users` theo hiện thực (container giữ chỗ, `identities_error`) hoặc ghi rõ hàm `_` không ràng buộc chữ ký.
3. TC-04 nên nêu chuỗi mong đợi cụ thể cho từng input để test truy vết được.
