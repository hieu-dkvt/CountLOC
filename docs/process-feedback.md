# Nhật ký phản hồi quy trình

Ghi lại các lỗi test cho thấy **skill, agent, spec hoặc CLAUDE.md thiếu/mơ hồ** (không phải bug code thuần). Dùng để quyết định khi nào cần cập nhật quy trình. Ghi bởi `/feature-test` (bước 5b).

## Quy tắc
- Mỗi lỗi một dòng. Không ghi bug code thuần.
- Cột **Thành phần thiếu** dùng đúng tên file đích, để đếm lặp lại (ví dụ `agents/test-engineer.md`).
- Một thành phần thiếu xuất hiện **từ 2 lần**, hoặc lỗi Blocker → AI đề xuất sửa cụ thể cho người dùng duyệt.
- AI **không tự sửa** `.claude/` hay `CLAUDE.md`. Người dùng duyệt → sửa → đổi Trạng thái thành `đã áp dụng` → chạy lại ca đã fail để kiểm chứng.

Trạng thái: `ghi nhận` → `đề xuất` (đã trình người dùng) → `đã áp dụng` | `từ chối`.

## Nhật ký

| Ngày | Feature / TC | Triệu chứng | Nguyên nhân gốc | Thành phần thiếu | Đề xuất sửa | Trạng thái |
|---|---|---|---|---|---|---|
| | | | | | | |

## Ví dụ một dòng (xoá khi có dữ liệu thật)

| Ngày | Feature / TC | Triệu chứng | Nguyên nhân gốc | Thành phần thiếu | Đề xuất sửa | Trạng thái |
|---|---|---|---|---|---|---|
| 2026-10-29 | classifier / TC-classifier-07 | Test fail với file CRLF | Fixture dùng `\n`, spec không nêu CRLF | `agents/test-engineer.md` | Thêm quy ước: mỗi test phân loại dòng phải có biến thể CRLF | ghi nhận |
