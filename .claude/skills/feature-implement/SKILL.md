---
name: feature-implement
description: Lập trình một chức năng/màn hình/module của LOC Counter theo spec xử lý đã duyệt trong docs/specs/<id>.md — viết test từ bảng TC trước, code đúng spec, chạy /feature-test và /feature-review, cập nhật trạng thái. Dùng khi người dùng yêu cầu code, implement, lập trình một feature.
argument-hint: "<id>"
---

# Lập trình feature theo spec

Tham số: `$ARGUMENTS` = id spec.

## Bước 0 — Cổng spec-first
1. Mở `docs/specs/<id>.md`.
   - Không tồn tại → **dừng**, chạy `/feature-spec <id>`.
   - `status: draft` → **dừng**, trình bày spec và xin người dùng duyệt (qua `/feature-spec <id>`, bước Duyệt).
2. Câu hỏi mở trong spec còn trạng thái "mở" → hỏi người dùng trước.
3. Các spec trong `depends_on` phải ở `implemented` hoặc `reviewed`. Nếu chưa → báo người dùng.

## Bước 1 — Chuẩn bị
- Đọc spec xử lý, các mục spec gốc trong `spec_refs`, API của các module phụ thuộc.
- Chưa có `pyproject.toml` → khởi tạo project theo mục 4, 5 spec gốc trước (package `loc-counter`, src layout `src/loc_counter`, `requires-python = ">=3.11"`, entry point `loc-counter = "loc_counter.cli:app"`, dependency mục 4 + `tzdata`, dev: `pytest`, `pytest-cov`, `ruff`), rồi `uv sync`.

## Bước 2 — Test trước (TDD)
- Viết test cho mọi TC trong spec vào file ở trường `tests:`. Docstring mỗi hàm test bắt đầu bằng `TC-<id>-NN`.
- Nhiều TC hoặc cần fixture repo Git phức tạp → giao agent `test-engineer`.
- Chạy test, xác nhận chúng fail vì chưa có code (không phải lỗi cú pháp test).

## Bước 3 — Code
- Chỉ ghi vào các file trong `modules:`; hook spec-first sẽ chặn file khác trong `src/loc_counter/`.
- Làm đúng từng bước "Luồng xử lý", đúng chữ ký ở mục "Giao diện", đúng bảng lỗi/thông báo.
- Không thêm hành vi, tham số, thư viện ngoài spec. Phát hiện spec thiếu/sai → **dừng**, cập nhật spec (`/feature-spec <id>`), xin duyệt lại, rồi mới code tiếp.
- Tuân thủ quy ước code trong `CLAUDE.md` (type hint, docstring tiếng Việt, subprocess không shell, token, tái lập, Windows).

## Bước 4 — Test
Chạy `/feature-test <id>`. Lặp sửa code đến khi pass hết. Không sửa giá trị kỳ vọng của test để khớp code.
Pass → đổi spec sang `status: implemented`.

## Bước 5 — Review
Chạy `/feature-review <id>`.
- Sửa mọi Blocker/Major; sửa Minor nếu đơn giản. Chạy lại `/feature-test <id>`.
- Có Blocker → chạy lại `/feature-review <id>` sau khi sửa.
- Kết luận PASS/PASS_WITH_NOTES → đổi spec sang `status: reviewed`.

## Bước 6 — Kết thúc
- Cập nhật cột Trạng thái trong `docs/PLAN.md` và `docs/specs/README.md`.
- Báo người dùng: file đã tạo/sửa, kết quả test (số pass/fail), kết luận review, vấn đề còn lại, feature kế tiếp.
