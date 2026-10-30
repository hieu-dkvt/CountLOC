---
name: milestone-plan
description: Phân tích spec gốc LOC Counter và lập/cập nhật kế hoạch cho một milestone (M1–M7) trong docs/PLAN.md (câu hỏi mở và quyết định ở docs/DECISIONS.md) — chia feature, thứ tự, phụ thuộc, tiêu chí hoàn thành, câu hỏi mở. Dùng khi bắt đầu milestone mới, hoặc khi người dùng hỏi "làm gì tiếp", "lên plan", "trạng thái dự án".
argument-hint: "[M1..M7 | status]"
---

# Lập kế hoạch milestone

Tham số: `$ARGUMENTS` (vd. `M1`). Trống → milestone đầu tiên chưa hoàn thành trong PLAN.md. `status` → chỉ báo cáo trạng thái, không sửa file.

## Bước 1 — Thu thập trạng thái
1. Đọc `docs/PLAN.md` (milestone, bảng feature) và `docs/DECISIONS.md` (câu hỏi mở, quyết định đã chốt).
2. Đọc front matter mọi file `docs/specs/*.md` (id, milestone, status).
3. Nếu có code: `uv run pytest -q` trong thư mục gốc project để biết test đang pass/fail (bỏ qua nếu chưa có `pyproject.toml`).
4. Kiểm tra milestone trước đã đạt tiêu chí hoàn thành (mục 13 spec gốc). Nếu chưa → báo người dùng, đề xuất hoàn thành nó trước.

Với `status`: in bảng tóm tắt (milestone → feature → status spec → test) rồi dừng.

## Bước 2 — Phân tích phạm vi
Đọc các mục spec gốc liên quan đến milestone (bảng ở mục 13 + mục 5 cấu trúc + các mục chi tiết của từng module).
Nếu phạm vi lớn hoặc chưa được phân tích trong PLAN.md, giao cho agent `spec-analyst` phân tích phạm vi milestone và dùng kết quả của nó.

## Bước 3 — Cập nhật PLAN.md
Trong mục của milestone:
- Bảng feature: `ID spec | Loại (module/screen/cli) | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái`.
  - Mỗi màn hình, mỗi lệnh CLI, mỗi module là **một spec riêng** (quy ước tên ở `docs/specs/README.md`).
  - Thứ tự triển khai theo phụ thuộc.
- Tiêu chí hoàn thành (chép từ mục 13, cụ thể hóa thành lệnh kiểm tra được).
- Công việc không cần spec (khởi tạo `pyproject.toml`, README, file example) liệt kê riêng.
- Câu hỏi mở mới → thêm vào mục "Câu hỏi mở" của `docs/DECISIONS.md` (đánh số tiếp, ghi milestone bị ảnh hưởng, `BLOCKING` hay không).

## Bước 4 — Hỏi người dùng
Các câu hỏi `BLOCKING` của milestone này: hỏi bằng AskUserQuestion (tối đa 4 câu/lần, phương án đề xuất đặt đầu). Ghi câu trả lời vào `docs/DECISIONS.md` (mục "Quyết định đã chốt") và đánh dấu câu hỏi đã đóng.

## Bước 5 — Kết thúc
Tóm tắt cho người dùng: danh sách feature theo thứ tự, câu hỏi còn mở, bước tiếp theo (`/feature-spec <id đầu tiên>`).
