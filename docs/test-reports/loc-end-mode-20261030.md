# Báo cáo test — tổng code thêm / xóa + cách tính LOC end (2026-10-30)

Phạm vi: `all` (toàn bộ test suite) sau thay đổi theo yêu cầu người dùng "Báo cáo số liệu thống kê xuất thêm added_code, deleted_code. LOC end cho chọn cách tính theo added code hoặc net code".
Spec liên quan: `report` (R16, A15), `pipeline` (A24), `cli-analyze` (A20), `screen-input` (A19), `screen-result` (A10).

## Kết quả
| Mục | Kết quả |
|---|---|
| `uv run pytest -q --cov=loc_counter` | **784 passed**, 0 fail, 0 skip (635 s) |
| Coverage tổng | 99 % (`report.py` 100 %, `pipeline.py` 99 %, `cli.py` 99 %, `app.py` 98 %) |
| `uv run ruff check src tests` | sạch (đã sửa 1 lỗi thứ tự import `I001` ở `pipeline.py`, chạy lại test pipeline liên quan: pass) |

## Truy vết TC mới
| TC | Hàm test | Trạng thái |
|---|---|---|
| TC-report-26 | `tests/test_report.py::test_loc_end_mode` | pass |
| TC-pipeline-41 | `tests/test_pipeline.py::test_loc_end_mode` | pass |
| TC-cli-analyze-27 | `tests/test_cli_analyze.py::test_loc_end_option` | pass |
| TC-screen-input-26 | `tests/test_app_input.py::test_loc_end_mode_radio` | pass (ý (d) "khóa khi chạy" phủ bởi TC-screen-input-15 — duyệt mọi `radio`) |
| TC-screen-result-15 | `tests/test_app_result.py::test_loc_end_mode` | pass |

Mọi `TC-<id>-NN` trong 5 spec đều có hàm test; không có test mồ côi.

## Test cũ cập nhật theo spec mới (không đổi giá trị kỳ vọng của số liệu cũ)
- TC-report-02, 15, 23, 25: thêm hàng `Cách tính LOC end`, `Tổng code thêm`, `Tổng code xóa` ở `Tong_quan`; `totals` thêm 4 key; `options.loc_end_mode`; chỉ số hàng / ô dịch theo.
- TC-pipeline-31: `totals` thêm 4 key.
- TC-cli-analyze-01..04, 15, 16, 24: bảng tổng thêm cột `Code thêm`, `Code xóa`.
- TC-screen-result-01: 6 metric.

## Tái lập
TC-pipeline-41 so SHA-256 giữa mode `net_code` và `added_code`: zip start/end, 3 CSV, `warnings.csv` trùng byte; chỉ xlsx và manifest khác (đúng spec). Các test tái lập cũ (TC-report-10, 19, 23; pipeline) vẫn pass.

## Phản hồi quy trình
Không có lỗi do spec / test / quy trình — không ghi thêm vào `docs/process-feedback.md`.

## Chạy lại sau sửa theo review
`totals.loc_end` giữ nghĩa LOC đếm trên export, thêm `reported_loc_end` / `reported_loc_delta`; thống nhất cụm từ; chuẩn hóa xuống dòng LF. `uv run pytest --cov` → **784 passed** (571 s), coverage 99 % (`report.py` 100 %); ruff sạch.
