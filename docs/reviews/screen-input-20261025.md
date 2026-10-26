# Review: screen-input — 2026-10-25
Kết luận: **FAIL**
Spec: docs/specs/screen-input.md (status: approved)   Files: `src/loc_counter/app.py`, `tests/test_app_input.py` (+ fixture `make_app` trong `tests/conftest.py`)

## Bằng chứng tự động
- ruff: `All checks passed!`
- pytest `tests/test_app_input.py`: 29 passed / 0 failed (57.6 s); toàn bộ suite: 710 passed (6 min 27 s)
- coverage `loc_counter.app`: 98 % (328 stmt, thiếu 264-265, 303-304, 333, 340, 376, 437)
- Streamlit 1.66.1, CPython 3.14.7, Windows 11
- Script kiểm chứng (AppTest, ngoài repo): `scratchpad/rv/probe.py`, `probe2.py`, `probe3.py` — kết quả trích trong từng phát hiện.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.1.1 | `set_page_config`, `st.title` | app.py:473-477 / TC-01 | Đạt |
| 5.1.2 | `_init_state` mặc định mọi key (A3, `adv_*` = `config_form_values(AppConfig())`) | app.py:206-222 / TC-01, TC-13 | Đạt |
| 5.1.3 | `locked = run_requested` đầu script | app.py:476 | Đạt |
| 5.2.1 | `clean_source`; "Tải repo" disabled khi rỗng / locked | app.py:252-253 / TC-01, TC-02 | Đạt |
| 5.2.2 | Spinner, khóa `repo:<cache_dir>` có chờ, `GitRepo.open`, nhánh, nhánh mặc định; lỗi → `repo_error` | app.py:225-242 / TC-03, TC-04 | Đạt (list_branches/default_branch ngoài khóa — Nit) |
| 5.2.3-4 | `st.error(repo_error)`; nguồn/token đổi → warning, chặn (A11) | app.py:255-262 / TC-21 | Đạt (xem Minor M1 về mất nhánh khi đổi lại) |
| 5.2.5 | selectbox nhánh; không nhánh → `st.error`; `branch None` → chặn | app.py:263-267 | Đạt, **không có test** (264-265 chưa phủ) |
| 5.3.1-2 | 2 cột date/time, múi giờ; `make_period`, lỗi → `st.error` | app.py:270-293 / TC-06 | Đạt |
| 5.3.3 | identities: rỗng/vắng → map rỗng; hỏng → lỗi | app.py:296-304 | Đạt một phần (thư mục bị bỏ qua im lặng — Minor M3); **không có test** đường lỗi |
| 5.3.4 | Memo 1 mục theo `(repo_gen, branch, period, identity_map, bool(token))`, lỗi cũng memo (A4) | app.py:307-324 / TC-05, TC-16 | Đạt |
| 5.3.5 | Hai dòng snapshot bằng `st.text` **trong khối [2]** | app.py:487-492 / TC-03, TC-08 | **Không đạt vị trí** (Major J2) |
| 5.4.1-6 | identities ở đầu [3], radio, reconcile + `st.info`, "Không có user", Tất cả = chỉ đọc, Chọn user = tìm + checkbox + "Đã chọn N user", cảnh báo | app.py:336-368, 481-482 / TC-09, 10, 11, 23 | Đạt |
| 5.4.7 | `render_identity_panel` nếu có | — (chưa có screen-identity) | N/A |
| 5.5.1 | "Nạp" → `adv_*` + `tz`; lỗi → `config_load_error` | app.py:371-385 / TC-13 | **Không đạt** với tz ngoài `timezone_options()` (Major J1) |
| 5.5.2 | 8 widget; `form_config`; lỗi → `st.error` trong expander | app.py:388-416 / TC-13 | Đạt |
| 5.6.1-3 | `out_dir`, `analyze_blockers` → `st.info`, nút disabled, `run_error`, `st.success` | app.py:496-511 / TC-01, 09, 19, 22 | Đạt |
| 5.6.4 | Cờ trả trước (A13), progress, khóa `out:` không chờ, `run_log(secrets)`, dòng INFO, `build_request`, `run_analysis(context=ctx)`, bắt lỗi, `st.rerun` | app.py:425-468 / TC-14..19 | Đạt |
| §6 | Không fetch lại; cùng resolver; Loại trừ bot ẩn + bỏ chọn; C_START rỗng; kỳ không user | TC-16, 11, 08, 23 | Đạt |
| §7 | Thứ tự lý do chặn 1→8 | app.py:152-167 / TC-22 | Đạt |
| §8 | Token: chỉ session, không vào memo key/sig/log | app.py:311, 444, 506 / TC-20 | Đạt (xem Minor M4) |
| §8 R14 | Cùng tham số → cùng `AnalysisRequest` như CLI | app.py:170-176 | **Không đạt** khi config có tz không chuẩn (Major J1) |
| TC-01 | trạng thái ban đầu | `test_initial_state`, `test_time_inputs_default_none` | Đạt |
| TC-02 | hàm thuần | `test_pure_helpers` | Đạt |
| TC-03 | tải repo §14 | `test_load_repo` | Đạt (không kiểm vị trí dòng snapshot) |
| TC-04 | lỗi nguồn | `test_load_error` | Đạt một phần — chỉ kiểm `at.error` khác rỗng, không kiểm nội dung tiếng Việt (Minor M5) |
| TC-05 | memo | `test_period_memo` | Đạt |
| TC-06/07/08 | start>=end / không dữ liệu / C_START rỗng | test tương ứng | Đạt |
| TC-09/10/11/12 | chọn user / tìm / bot / filter | test tương ứng | Đạt |
| TC-13 | nâng cao | `test_advanced_options` | Đạt (không có ca tz không chuẩn) |
| TC-14 | tiến độ | `test_progress` | Đạt một phần — "sau rerun có dòng xong" không được assert (Minor M5) |
| TC-15 | khóa ô nhập | `test_inputs_locked_while_running` | Đạt |
| TC-16 | AnalysisRequest | `test_request` | Đạt |
| TC-17 | E2E | `test_end_to_end` ×4 | Đạt |
| TC-18 | khóa out_root | `test_out_root_lock` | Đạt một phần — "khóa nhả sau lỗi pipeline" chỉ kiểm sau lần chạy **thành công** (Minor M5) |
| TC-19 | lỗi pipeline / bất thường | `test_run_errors` | Đạt |
| TC-20 | token | `test_token_not_leaked` | Đạt |
| TC-21 | đổi token | `test_source_or_token_changed` | Đạt |
| TC-22 | blockers, out_root | `test_blockers_and_out_root` | Đạt |
| TC-23 | lựa chọn cũ khi đổi kỳ | `test_selection_dropped_when_period_changes` | Đạt |

## Phát hiện

### [Major] J1 — Múi giờ từ config.yaml không có trong `timezone_options()` bị Streamlit lặng lẽ đổi thành `Africa/Abidjan` (sai kỳ thống kê, lệch CLI) — `src/loc_counter/app.py:385`, `src/loc_counter/app.py:284`
- **Mô tả:** `_load_config_file` gán `ss.tz = cfg.timezone` không kiểm `cfg.timezone in timezone_options()` (spec §3.2 cột Validate của "Múi giờ": "thuộc `timezone_options()`"). `config_from_dict` chỉ kiểm `ZoneInfo(timezone)`; trên Windows, `tzdata` đọc file tài nguyên trên hệ thống file không phân biệt hoa thường nên `ZoneInfo("singapore")`, `ZoneInfo("utc")`, `"japan"`, `"hongkong"`… đều hợp lệ nhưng **không** có trong `available_timezones()`. Khi giá trị session của selectbox không thuộc options, Streamlit 1.66 bỏ giá trị đó và chọn phần tử đầu (`Africa/Abidjan`, UTC+00:00), không báo lỗi.
- **Kịch bản (đã kiểm chứng, `probe2.py`):** `config.yaml` = `timezone: singapore` → "Nạp" → widget `tz` = `Africa/Abidjan`, `at.error` rỗng, `PeriodContext.period` = `2026-01-01T00:00:00+00:00 … 2026-01-31T23:59:59+00:00`. Cùng file đó với CLI (`make_period(..., timezone="singapore")`) cho `2026-01-01T00:00:00+08:00`. → Biên kỳ lệch 8 giờ, C_START/C_END và số liệu có thể khác CLI mà người dùng không được cảnh báo (vi phạm R14 / §15 tái lập, §3.1 múi giờ). Với `timezone: utc` cũng ra `Africa/Abidjan` (cùng offset nhưng tên sai trong log/báo cáo).
- **Đề xuất:** trong `_load_config_file`: nếu `cfg.timezone not in timezone_options()` thì tìm tên chuẩn không phân biệt hoa thường (`{n.casefold(): n for n in options}`), không thấy → `config_load_error = f"Múi giờ {cfg.timezone} không có trong danh sách múi giờ IANA"` và không ghi đè widget. Thêm ca TC-13 với `timezone: singapore`. (Gốc rễ ở `config.config_from_dict` chấp nhận tên sai hoa thường trên Windows — xem "Ghi chú cho spec".)
- **Tham chiếu:** screen-input §3.2 (Múi giờ — Validate), R5, R14; spec gốc §3.1, §15.

### [Major] J2 — Dòng "→ Snapshot start/end" (và lỗi `prepare_period`) hiển thị trong khối [3] CHỌN USER thay vì [2] THỜI ĐIỂM THỐNG KÊ — `src/loc_counter/app.py:481-492`
- **Mô tả:** `main()` vẽ `st.subheader("[3] CHỌN USER")` và ô "File identities" **trước** khi tính `ctx` rồi mới `st.text("→ Snapshot …")` / `st.error(context_error)`. Bố cục spec §3.1 và spec gốc §10.1 đặt hai dòng snapshot ngay dưới "Múi giờ" trong khối [2]; checklist mục 9 yêu cầu thứ tự thành phần đúng spec.
- **Kịch bản (đã kiểm chứng, `probe3.py` — thứ tự phần tử `at.main`):** `subheader [2] …` → `flex_container` → `selectbox Múi giờ` → `subheader [3] CHỌN USER` → `text_input File identities` → `text → Snapshot start: f23399a (2025-12-15 10:00) "admin: app.py"` → `text → Snapshot end: …` → `radio`. Người dùng thấy snapshot nằm dưới tiêu đề "CHỌN USER", sau ô identities; lỗi "Không có dữ liệu trong khoảng thời gian…" cũng hiện ở [3]. TC-03/TC-08 chỉ kiểm nội dung, không kiểm vị trí nên không phát hiện.
- **Đề xuất:** trong `_render_period` tạo `snap_box = st.container()` ngay sau selectbox múi giờ, trả về cho `main()`; sau khi có `ctx` thì `with snap_box: st.text(...)` / `st.error(context_error)`. Bổ sung assert thứ tự (chỉ số phần tử text snapshot nằm giữa subheader [2] và [3]) vào TC-03.
- **Tham chiếu:** screen-input §3.1, 5.3.5; spec gốc §10.1; checklist 9.

### [Minor] M1 — Đổi nguồn/token rồi trả lại như cũ làm mất nhánh đã chọn — `src/loc_counter/app.py:258-267`, `src/loc_counter/app.py:216`
- **Mô tả:** Khi repo không còn "ready", selectbox `branch` không được vẽ; Streamlit dọn state của widget không vẽ, `_init_state` đặt lại `branch = None`. Trả token/nguồn về như lúc tải → `repo_ready` đúng lại nhưng nhánh rỗng.
- **Kịch bản (đã kiểm chứng, `probe.py` ca A):** tải §14 (nhánh `main`) → token = `x` (warning đúng) → token = `""` → selectbox nhánh = `None`, `st.info("Chưa chọn nhánh.")`, PHÂN TÍCH disabled. Người dùng phải chọn lại nhánh dù repo không đổi. Không sai số liệu.
- **Đề xuất:** lưu nhánh trong một key phi widget (vd. `branch_value`) và đồng bộ qua `on_change`, hoặc vẫn vẽ selectbox (disabled) khi nguồn đổi để giữ state.
- **Tham chiếu:** 5.2.4 (A11).

### [Minor] M2 — Khóa `out:<out_root>` phân biệt hoa thường trên Windows khi thư mục chưa tồn tại — `src/loc_counter/app.py:439`
- **Mô tả:** `Path.resolve()` trên Windows chỉ chuẩn hóa hoa thường cho phần đã tồn tại (kiểm chứng: `resolve()` của `Output_new` ≠ `output_new` khi chưa có; `EXISTING` == `existing` khi đã có).
- **Kịch bản:** hai phiên, lần chạy đầu, một phiên nhập `Output`, phiên kia `output` → hai khóa khác nhau, hai phân tích chạy song song cùng một thư mục (cùng `run.log` mở `mode="w"`, cùng tên thư mục kết quả). Hiếm (đa phiên + lần đầu + khác hoa thường).
- **Đề xuất:** tên khóa dùng `os.path.normcase(str(out_root))`.
- **Tham chiếu:** §8 Đa phiên, D41-N3, checklist 6 (Windows).

### [Minor] M3 — `identities_path` trỏ tới thư mục bị bỏ qua im lặng — `src/loc_counter/app.py:299`
- **Mô tả / kịch bản (đã kiểm chứng, `probe.py` ca D):** ô = đường dẫn một thư mục → `Path.is_file()` False → map rỗng, không `st.error`, không chặn. Người dùng tưởng đã dùng file gộp account nhưng kết quả theo email.
- **Đề xuất:** chỉ coi là "vắng" khi `not path.exists()`; tồn tại mà không phải file → `identities_error` ("… không phải file").
- **Tham chiếu:** 5.3.3, D41-N5.

### [Minor] M4 — `logger.exception` của lỗi bất thường nằm ngoài `run_log`: traceback không vào `run.log`, in ra stderr không che token — `src/loc_counter/app.py:465-466`
- **Mô tả:** khối `except Exception` chạy sau khi `with pipeline.run_log(...)` đã đóng, nên handler có `_MaskingFormatter` đã gỡ; bản ghi đi tới `logging.lastResort` (stderr của streamlit) không che secret. Thông báo cho người dùng lại bảo "xem run.log". Với lỗi phát sinh trong `run_analysis`, pipeline đã tự `logger.exception` vào `run.log` (pipeline.py:578) nên run.log vẫn có; lỗi phát sinh ở `build_request` / logger.info của app thì không. Chưa kiểm chứng có đường nào đưa token vào message exception (khả năng thấp).
- **Đề xuất:** chuyển `except Exception` vào trong khối `with run_log` (hoặc che bằng `mask_secrets(..., (token,))` trước khi log).
- **Tham chiếu:** §7 bảng lỗi, §8 Token; CLAUDE.md quy tắc 6.

### [Minor] M5 — Test chưa kiểm hết điều TC mô tả; thiếu test cho vài nhánh §7 — `tests/test_app_input.py:153-160, 289-307, 391-416`
- TC-04: chỉ `assert at.error`, không kiểm thông báo tiếng Việt (vd. `Không tìm thấy repo`, `không được chứa thông tin xác thực`).
- TC-14: "sau rerun có dòng xong" không được assert (không test nào kiểm `st.success("Phân tích xong…")`).
- TC-18: "khóa nhả sau lỗi pipeline" — test chỉ chứng minh khóa nhả sau lần chạy **thành công**; không có ca `run_analysis` ném lỗi rồi kiểm `LOCKS.get("out:…").acquire(blocking=False)`.
- Không có test cho: identities hỏng (§7, app.py:303-304, 340), "Repo không có nhánh nào." (app.py:264-265), bỏ tick checkbox user (`_toggle` nhánh discard, app.py:333).
- **Đề xuất:** bổ sung assert/ca test tương ứng (có thể thêm TC mới vào spec cho identities hỏng).

### [Minor] M6 — Type hint `Any` cho `PeriodContext` / `AccountResolver` — `src/loc_counter/app.py:307-308, 336, 425`
- `_period_context` trả `tuple[Any, Any, str | None]`, `ctx: Any`, `resolver: Any` dù đã có `pipeline.PeriodContext` và `identity.AccountResolver`. Đề xuất dùng kiểu cụ thể (`PeriodContext | None`).

### [Nit] N1 — Lỗi nạp config cũ không bị xóa khi bấm "Nạp" với ô trống — `src/loc_counter/app.py:375-376`
- Ô trống → `return` sớm, `config_load_error` cũ vẫn hiển thị. Đặt `config_load_error = None` trước `return`.

### [Nit] N2 — API mức module ngoài §3.4 / chữ ký khác spec — `src/loc_counter/app.py:36-40, 336`
- `FORM_KEYS`, `EXPORT_MODES`, `MIN_DATE`, `MAX_DATE` công khai (không có trong §3.4); `_render_users(locked, ctx, identities_error)` khác `_render_users(locked, ctx)`. Đổi tên có `_` hoặc cập nhật spec.

### [Nit] N3 — `list_branches()` / `default_branch()` chạy ngoài khóa cache repo — `src/loc_counter/app.py:232-235`
- Phiên khác có thể fetch cùng cache trong lúc đọc ref. Git cập nhật ref nguyên tử nên rủi ro thấp; có thể đưa hai lệnh vào trong `with` cho đúng ý 5.2.2.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Không đạt | J1 (validate tz §3.2), J2 (bố cục §3.1); API/chữ ký lệch nhỏ (N2); TC-04/14/18 kiểm chưa đủ (M5) |
| 2. Nghiệp vụ dễ sai | Đạt | UI không tự tính LOC; snapshot/attribution qua `pipeline` (C_START rỗng, kỳ không user đúng). Ngoại lệ: kỳ sai múi giờ ở J1 |
| 3. Bảo mật | Đạt (có ghi chú) | Token chỉ trong session/`loaded_with`/GitRepo/resolver; không vào memo key, `sig`, log; `run_log(secrets)`; TC-20 pass. M4: log ngoài run_log không che |
| 4. Lỗi & log | Đạt (có ghi chú) | Thông báo tiếng Việt; dòng INFO "Phân tích từ giao diện" trong run.log (TC-17); M4 |
| 5. Tái lập & encoding | Không đạt | `users` sắp xếp; nhưng J1 làm UI khác CLI với cùng config |
| 6. Windows | Không đạt | J1 là lỗi riêng Windows (tzdata không phân biệt hoa thường); M2 hoa thường đường dẫn; `clean_source` bỏ nháy "Copy as path" đạt |
| 7. Chất lượng code | Đạt (có ghi chú) | ruff sạch; docstring tiếng Việt đủ; M6 type hint `Any`; không thư viện ngoài §4 |
| 8. Hiệu năng | N/A (M7) | `prepare_period` chỉ khi khóa memo đổi (TC-05). `timezone_label` ×598 lần/rerun ≈ 130 ms lần đầu, sau đó nhỏ |
| 9. Màn hình Streamlit | Không đạt | J2 vị trí snapshot; mặc định (ngày, tz, radio), validate start<end, ≥1 user, khóa ô nhập, 5 bước tiến độ, token password, AppTest: đạt. Ghi chú §7.5 thuộc `screen-result` (N/A) |

## Ghi chú cho spec
1. **`config.config_from_dict` chấp nhận tên múi giờ sai hoa thường trên Windows** (`ZoneInfo("singapore")` hợp lệ nhờ hệ thống file không phân biệt hoa thường). Đây là vấn đề của spec/module `config` (ngoài phạm vi review này) nhưng là gốc của J1 và còn làm `period.timezone`/báo cáo ghi tên không chuẩn (`singapore`) ở cả CLI. Cần người dùng quyết định: (a) `config` chuẩn hóa về tên IANA chuẩn hoặc báo lỗi khi `timezone not in available_timezones()`, hay (b) chỉ UI xử lý.
2. Spec §5.3/§5.4 có mâu thuẫn ngầm: dòng snapshot thuộc khối [2] nhưng phụ thuộc `identity_map` nhập ở khối [3]. Nên ghi rõ cách hiện thực (placeholder `st.container()` trong [2]).
3. §9 không có TC cho các dòng §7 "identities hỏng" và "Repo không có nhánh" — đề xuất thêm TC.
4. Hành vi giữ nhánh khi nguồn/token đổi rồi trả lại (M1) chưa được spec nêu — đề xuất ghi rõ "giữ nhánh đã chọn".
