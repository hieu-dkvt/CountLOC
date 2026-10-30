# Review: loc-end-mode (diff chưa commit) — 2026-10-30
Kết luận: PASS_WITH_NOTES
Spec: docs/specs/report.md (R16, A15), docs/specs/pipeline.md (A24), docs/specs/cli-analyze.md (A20), docs/specs/screen-input.md (A19), docs/specs/screen-result.md (A10) — cả 5 đang `status: implemented`
Files: src/loc_counter/report.py, src/loc_counter/pipeline.py, src/loc_counter/cli.py, src/loc_counter/app.py; tests/test_report.py, tests/test_pipeline.py, tests/test_cli_analyze.py, tests/test_app_input.py, tests/test_app_result.py; README.md

## Bằng chứng tự động
- ruff: `uv run ruff check src tests` → All checks passed!
- pytest (5 file test trong phạm vi): 155 passed / 0 failed (260 s)
- coverage (cùng 5 file test): `report.py` 100 %, `pipeline.py` 99 % (dòng 264, 417 là code cũ, không thuộc thay đổi), `cli.py` 78 %, `app.py` 85 %. Phần thiếu của `cli.py` / `app.py` nằm ở lệnh `count` / `users` và panel định danh (test ở file khác, ngoài phạm vi). **Mọi dòng mới của diff đều được phủ.** Báo cáo test toàn bộ (`docs/test-reports/loc-end-mode-20261030.md`) ghi 784 passed, coverage 99 %.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| report R16/A15 | `LocEndMode`, `LOC_END_MODE_LABELS` đúng chuỗi | report.py:50-52; test_report.py:708 (so dict nhãn) | Đạt |
| report A15 | `ReportOptions.loc_end_mode="net_code"`, giá trị lạ → `ValueError` | report.py:117-121; test_report.py:708 (c) | Đạt |
| report A15 | `sum_added_code` / `sum_deleted_code` = tổng `user_rows` (tương đương `total_metrics(...).added_code/deleted_code`, đã đối chiếu counter.py:410) | report.py:159-167 | Đạt |
| report A15 | `reported_loc_end`: net → `loc_end`; added → `loc_start + sum_added_code`; `reported_loc_delta`; `loc_delta` giữ nghĩa cũ | report.py:169-178; TC-report-26 | Đạt |
| report 5.3 | Tong_quan: `Cách tính LOC end` sau `Cách gán tác giả`; LOC end/Chênh lệch theo reported; `LOC end đếm trên export` chỉ ở mode added, ngay sau `Chênh lệch`; `Tổng code thêm`/`xóa` sau `Commit`, trước `Tổng code ròng` | report.py:337-349; TC-report-02 (giá trị net), TC-report-26 (thứ tự + giá trị added) | Đạt |
| report 5.5 | manifest `totals` 7 key đúng thứ tự; `options.loc_end_mode`; `cross_check.loc_end` luôn đếm trên export | report.py:521-531; TC-report-15, TC-report-26 | Đạt |
| report A15 | Theo_ngon_ngu / Theo_file / Theo_user không đổi theo mode | report.py (không sửa); TC-report-26 so `rows` 3 sheet | Đạt |
| pipeline A24 | `AnalysisRequest.loc_end_mode="net_code"`; kiểm hợp lệ ở đầu `run_analysis` cạnh `attribution_mode` | pipeline.py:153, 487-488; TC-pipeline-41 (c) | Đạt |
| pipeline bước 19 | Log INFO `LOC end theo code thêm: a + b = c (đếm trên export: d)` chỉ ở mode added | pipeline.py:594-597; TC-pipeline-41 (đọc run.log cả hai mode) | Đạt |
| pipeline bước 22 | `ReportOptions(..., request.loc_end_mode)`; không đổi `loc_end` / `check` / `exports` | pipeline.py:623-624; TC-pipeline-41 (cross_check bằng nhau, SHA zip + CSV trùng) | Đạt |
| pipeline A24 | Memo A21 không khóa theo `loc_end_mode` | không đổi khóa memo; TC-pipeline-41 (`len(spy.calls) == 1`) | Đạt |
| cli A20 | `--loc-end net\|added`, mặc định `net`, giá trị lạ → mã 2, ánh xạ `net_code`/`added_code` | cli.py:40-45, 436-438, 466-467; TC-cli-analyze-27 (c) | Đạt |
| cli 4.1 | Bảng tổng 6 cột; dòng `Cách tính LOC end: … — LOC đếm trên export end: N` ngay trước bảng, sau `Cách gán tác giả:` | cli.py:333-346; TC-cli-analyze-01..04, 15, 16, 24, 27 | Đạt |
| cli 4.2 | `--json` → `manifest.totals.loc_end == 23` ở mode added | manifest đọc từ file; TC-cli-analyze-27 (b) | Đạt |
| screen-input A19 | Radio `loc_end_mode` ngay dưới `Cách gán tác giả`, 2 nhãn, mặc định lựa chọn đầu, `disabled=locked` | app.py:65, 484, 649-650; TC-screen-input-26 (a)(b); (d) phủ bởi TC-screen-input-15 (duyệt mọi `at.radio`) | Đạt |
| screen-input 5.6 | `build_request(loc_end_mode=…)`; `sig` có `attribution_mode`, `loc_end_mode` | app.py:212-223, 812-816, 998-1000; TC-screen-input-26 (c) | Đạt |
| screen-result A10 | 6 metric (LOC end / Chênh lệch theo reported, Code thêm, Code xóa); `loc_end_note` + `st.caption` chỉ mode added | app.py:286-291, 894-903; TC-screen-result-01, 15 | Đạt |
| screen-result R10 | Dòng kiểm tra chéo vẫn theo LOC đếm trên export | app.py:904-905 (không đổi); TC-screen-result-15 (c) | Đạt |
| README | Mô tả `--loc-end` | README.md | Đạt |

## Phát hiện
Không có Blocker / Major.

### [Minor] `manifest.totals.loc_end` đổi nghĩa theo mode — `src/loc_counter/report.py:521`
- Mô tả: spec gốc §8.1 / §12 định nghĩa `totals.loc_end` = LOC của export end. Ở mode `added_code`, key này chứa `loc_start + Σ added_code`; LOC thật dời sang `totals.loc_end_export`. Code làm **đúng spec xử lý A15**, nhưng công cụ đọc manifest (script, so sánh giữa các lần chạy) phải kiểm `options.loc_end_mode` mới hiểu đúng `loc_end`.
- Kịch bản: hai lần chạy cùng kỳ, một lần `--loc-end added`; một script so `totals.loc_end` của hai manifest sẽ thấy 23 với 20 mà không có thay đổi code nào.
- Đề xuất: giữ như spec nếu người dùng chấp nhận; nếu không thì giữ `totals.loc_end` = LOC export và thêm key mới (ví dụ `loc_end_reported`). Xem "Ghi chú cho spec".
- Tham chiếu: report A15; spec gốc §8.1, §12; CLAUDE.md quy tắc 2.

### [Minor] Hai giá trị "LOC end" khác nhau trên cùng màn hình / sheet ở mode added — `src/loc_counter/app.py:894-905`, `src/loc_counter/report.py:340-349`
- Mô tả: metric `LOC end` = 23, ngay dưới là dòng `Kiểm tra chéo: … = 20; LOC end 20; …`. Tong_quan cũng có `LOC end` 23 cạnh `LOC end kỳ vọng` 20. Đã có caption / hàng `LOC end đếm trên export` để giải thích, nên chỉ là rủi ro hiểu nhầm, không sai spec.
- Đề xuất: (tùy người dùng) đổi chữ trong dòng kiểm tra chéo thành `LOC end (export) 20` khi mode added. Phải sửa spec trước (cli-analyze 4.1, screen-result A3).

### [Nit] Câu chữ chưa thống nhất: "LOC end đếm trên export" và "LOC đếm trên export end" — `src/loc_counter/report.py:344`, `src/loc_counter/cli.py:336-337`, `src/loc_counter/app.py:290`
- Tong_quan dùng `LOC end đếm trên export`, CLI và caption dùng `LOC đếm trên export end`. Cả hai đều đúng chữ trong spec tương ứng; nên chọn một cách viết khi sửa spec lần tới.

### [Nit] Pipeline tự cộng lại `added_code` thay vì dùng thuộc tính của `ReportData` — `src/loc_counter/pipeline.py:594-597`
- Dòng log tự tính `sum(r.added_code for r in user_rows)` và `loc_start + added`, trong khi `ReportData.sum_added_code` / `reported_loc_end` đã có (nhưng `data` được tạo sau, ở bước 22). Kết quả giống nhau; chỉ là công thức nằm ở hai nơi. Có thể chuyển dòng log xuống sau khi tạo `data` nếu thứ tự log cho phép (spec bước 19 đặt dòng log trước bước 5), nên giữ nguyên cũng được.

### [Nit] Assertion của test hơi lỏng so với TC — `tests/test_cli_analyze.py:576`, `tests/test_pipeline.py:1211`, `tests/test_app_input.py:644`
- TC-cli-analyze-27 (b) yêu cầu dòng kiểm tra chéo "… đạt", nhưng test chỉ kiểm chuỗi con tới `lệch 0.000 %`, không kiểm phần `→ đạt`.
- TC-pipeline-41 (b) có nêu `Theo_ngon_ngu` / `Theo_file` trùng giữa hai mode; test pipeline chỉ so SHA của zip và CSV (`loc_by_language.csv` / `loc_by_file.csv` cùng nguồn dữ liệu). Ý này đã có ở TC-report-26.
- Docstring TC-screen-input-26 ghi "khóa", nhưng test không kiểm `disabled`. Ý (d) thực tế được phủ bởi TC-screen-input-15 (đã kiểm chứng: radio `loc_end_mode` vẽ ở app.py:649 không phụ thuộc `ctx`, nên có trong `at.radio`). Đề xuất: thêm `→ đạt` vào assertion CLI; với (d), ghi rõ trong docstring là phủ bởi TC-15.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Mọi bước / quy tắc / TC mới có code và test với giá trị cụ thể (bảng trên). API công khai mới (`LocEndMode`, `LOC_END_MODE_LABELS`, `ReportOptions.loc_end_mode`, 4 property, `AnalysisRequest.loc_end_mode`, `LocEndChoice`, `LOC_END_MODES`, `loc_end_note`, tham số `build_request`) đều có trong mục Giao diện của spec. Mode mặc định `net_code` giữ §3.4/§8.1. Không đụng lệnh git, classifier, attribution. |
| 2. Nghiệp vụ dễ sai | Đạt | `loc_end` vẫn đếm trên export; kiểm tra chéo §8.3 và `exports[].loc` không đổi (TC-pipeline-41 so `cross_check` + SHA zip/CSV). Tổng code thêm / xóa lấy cùng tập `user_rows` với `sum_net_code` (pipeline.py:574-576). |
| 3. Bảo mật | N/A | Diff không đụng token, URL, subprocess, zip. |
| 4. Lỗi & log | Đạt | Lỗi giá trị bằng tiếng Việt (`loc_end_mode không hợp lệ`), kiểm ở đầu `run_analysis` trước khi tạo thư mục kết quả; dòng log INFO mới dùng `logging`. |
| 5. Tái lập & encoding | Đạt | Thứ tự hàng Tong_quan và key `totals` cố định (có test thứ tự key); zip / CSV không phụ thuộc mode (có test SHA). |
| 6. Windows | N/A | Không có thay đổi về đường dẫn hay file. |
| 7. Chất lượng code | Đạt | Có type hint (`LocEndMode` Literal), docstring tiếng Việt, ruff sạch, không thêm thư viện, không có code chết. UI chỉ ánh xạ nhãn → mode; phép tính nằm ở `ReportData`. |
| 8. Hiệu năng | Đạt | Đổi chỉ cách tính LOC end thì dùng lại kết quả gán tác giả (memo A21). Vẫn phải export / đếm lại vì `sig` đổi; spec A19 chấp nhận điều này vì xlsx/manifest khác nhau. |
| 9. Streamlit | Đạt | Nhãn tiếng Việt; radio ngang, khóa khi chạy; thêm vào `sig` nên đổi mode sẽ báo kết quả cũ; có test AppTest. |

## Ghi chú cho spec
1. **Nghĩa của `totals.loc_end` và nhãn "LOC end" ở mode `added_code`** (report A15, ghi "Khuyến nghị (ủy quyền)"): spec gốc §8.1 / §12 coi `loc_end` là LOC của export end. A15 cho ghi đè nhãn / key này bằng `loc_start + Σ added_code` khi chọn mode added. Người dùng đã yêu cầu chức năng này, nhưng **cách thể hiện** (dùng lại key `loc_end`, hay giữ `loc_end` = LOC export và thêm key mới) vẫn là quyết định chạm định nghĩa §8.1 (CLAUDE.md quy tắc 2). Cần người dùng xác nhận rõ.
2. Mục A15 (report), A24 (pipeline), A20 (cli-analyze), A19 (screen-input), A10 (screen-result) ghi "ủy quyền 2026-10-23", còn các mục cùng đợt (A14, A23, A19 cli, A18) ghi "ủy quyền 2026-10-30". Nên thống nhất ngày cho dễ truy vết.
3. Thống nhất cách viết "LOC end đếm trên export" (Tong_quan) và "LOC đếm trên export end" (CLI, caption).
4. Sau khi review PASS: cập nhật 5 spec `implemented` → `reviewed` (và bảng trong docs/specs/README.md), ghi vào mục Lịch sử thay đổi.

## Xử lý sau review (2026-10-30)
| Phát hiện | Xử lý |
|---|---|
| Minor 1 — `totals.loc_end` đổi nghĩa theo mode | **Đã sửa** (chốt theo khuyến nghị, người dùng ủy quyền): `totals.loc_end` / `loc_delta` luôn là LOC đếm trên export (giữ nghĩa §8.1 / §12); bỏ `loc_end_export`; thêm `reported_loc_end` / `reported_loc_delta`. Spec report 5.5 / A15 / TC-26, pipeline TC-41, cli-analyze TC-27, README cập nhật |
| Minor 2 — hai giá trị "LOC end" trên cùng màn hình ở mode added | Giữ nguyên (đúng A10 / A15, đã có ghi chú cách tính ngay dưới metric) |
| Nit — cụm từ không thống nhất | **Đã sửa**: mọi nơi dùng `LOC end đếm trên export` (Tong_quan, CLI, màn hình) |
| Nit — log pipeline cộng lại tổng code thêm | Giữ nguyên (`ReportData` dựng sau bước log; tổng một dòng, cùng công thức) |
| Nit — assertion lỏng | **Đã sửa** TC-cli-analyze-27: kiểm đủ dòng `… (ngưỡng 0.5 %) → đạt`; ý "khóa khi chạy" của TC-screen-input-26 giữ phủ bởi TC-screen-input-15 (duyệt mọi `radio`) |
| Ghi chú spec 2 — ngày ủy quyền | Giữ 2026-10-23: đó là ngày người dùng ủy quyền "thực hiện theo recommend" (memory / PLAN); các mục khác ghi ngày áp dụng |
