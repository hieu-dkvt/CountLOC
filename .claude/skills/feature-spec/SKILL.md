---
name: feature-spec
description: Tạo hoặc cập nhật spec xử lý cho một màn hình, lệnh CLI hay module của LOC Counter trong docs/specs/<id>.md — BẮT BUỘC trước khi lập trình. Dùng khi chuẩn bị code một chức năng/màn hình mới, khi hook spec-first chặn việc ghi code, hoặc khi cần đổi hành vi đã có spec.
argument-hint: "<id>  (vd. classifier, cli-count, screen-input)"
---

# Viết spec xử lý cho chức năng / màn hình

Tham số: `$ARGUMENTS` = id spec. Quy ước id và loại: xem `docs/specs/README.md`. Thiếu id → lấy feature kế tiếp chưa có spec trong `docs/PLAN.md` và xác nhận với người dùng.

## Bước 1 — Chuẩn bị
1. Đọc dòng của feature trong PLAN.md (file nguồn, mục spec gốc, phụ thuộc).
2. Đọc các mục spec gốc liên quan trong `spec_count_LOC.md` + luôn đọc mục 3, 9, 15, 16.
3. Đọc spec của các feature phụ thuộc (dùng đúng API công khai của chúng).
4. Spec đã tồn tại → đây là cập nhật: giữ nguyên phần đã duyệt, chỉ sửa phần cần đổi, ghi "Lịch sử thay đổi", đặt lại `status: draft`.
5. Phạm vi phức tạp (attribution, builder, pipeline, màn hình) → giao agent `spec-analyst` phân tích trước.

## Bước 2 — Viết spec
Tạo `docs/specs/<id>.md` từ [template.md](template.md). Yêu cầu:
- `modules:` liệt kê **chính xác** file nguồn (dạng `src/loc_counter/<file>.py`) — hook spec-first dựa vào trường này.
- **Luồng xử lý** đủ chi tiết để người khác code được mà không cần đoán: từng bước, lệnh git chính xác, cấu trúc dữ liệu, thứ tự sắp xếp.
- Màn hình (`type: screen`): phải có bố cục ASCII, bảng thành phần (widget, key `session_state`, mặc định, validate, hành vi khi đổi), trạng thái màn hình (idle/loading/running/done/error) và chuyển trạng thái, mọi thông báo tiếng Việt hiển thị.
- CLI (`type: cli`): cú pháp, tham số, mã thoát, đầu ra stdout.
- **Bảng test case** `TC-<id>-NN` phủ: luồng chính, mọi quy tắc nghiệp vụ, trường hợp biên, lỗi. Feature thuộc mục 6.4 hoặc 14 phải chứa đủ test bắt buộc trong `.claude/skills/feature-test/mandatory-tests.md`.
- Mọi yêu cầu trích từ spec gốc ghi số mục `[§x.y]`. Điều gì là suy luận/giả định → đưa vào mục "Câu hỏi mở / giả định".
- Không thay đổi định nghĩa mục 3 hay thuật toán mục 6, 7 của spec gốc.

## Bước 3 — Tự kiểm
- Mỗi yêu cầu trong các mục spec gốc được tham chiếu đều xuất hiện trong spec?
- Mỗi quy tắc nghiệp vụ / nhánh lỗi có ít nhất một TC?
- Giá trị mặc định khớp spec gốc?

## Bước 4 — Duyệt
1. Trình bày tóm tắt spec cho người dùng (mục đích, API/màn hình, luồng chính, số TC, câu hỏi mở) kèm link file.
2. Hỏi các câu hỏi mở bằng AskUserQuestion; cập nhật spec theo câu trả lời.
3. Chỉ khi người dùng **đồng ý rõ ràng** mới đổi `status: approved`. Không tự duyệt.
4. Cập nhật cột Trạng thái trong PLAN.md và bảng chỉ mục trong `docs/specs/README.md`.
5. Gợi ý bước tiếp: `/feature-implement <id>`.
