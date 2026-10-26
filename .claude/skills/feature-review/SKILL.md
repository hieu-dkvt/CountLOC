---
name: feature-review
description: Review độc lập phần đã lập trình của LOC Counter (một feature theo id, một milestone, hoặc thay đổi chưa commit) — đối chiếu code với spec xử lý và spec gốc theo checklist, ghi báo cáo vào docs/reviews/ với kết luận PASS / PASS_WITH_NOTES / FAIL. Dùng sau khi code xong một feature hoặc khi người dùng yêu cầu review.
argument-hint: "<id> | M1..M7 | diff"
context: fork
agent: code-reviewer
---

# Review phần đã lập trình

Phạm vi review: `$ARGUMENTS`
- `<id>`: feature có spec `docs/specs/<id>.md` — review mọi file trong `modules:` và `tests:`.
- `M<n>`: mọi spec có `milestone: M<n>`, thêm phần tích hợp giữa các module.
- `diff`: các thay đổi chưa commit (`git status` / `git diff`); tìm spec tương ứng qua trường `modules:`. Không phải repo git → báo lại và dừng.

## Quy trình
1. **Ngữ cảnh**: đọc spec xử lý, các mục `spec_refs` trong `spec_count_LOC.md`, `CLAUDE.md`, và [checklist.md](checklist.md).
2. **Bằng chứng tự động** (trong thư mục gốc project):
   ```bash
   uv run ruff check src tests
   uv run pytest <tests của phạm vi> -q --tb=short
   uv run pytest <tests của phạm vi> --cov=loc_counter --cov-report=term-missing -q
   ```
3. **Đối chiếu spec**: lập bảng `Bước luồng xử lý / Quy tắc / TC → vị trí code / test → Đạt?`.
4. **Checklist**: đi qua từng nhóm trong [checklist.md](checklist.md); với nhóm không áp dụng ghi "N/A" và lý do.
5. **Kiểm chứng** mọi nghi vấn trước khi ghi (đọc thêm code, chạy script nhỏ trong thư mục tạm). Phát hiện không kiểm chứng được → ghi rõ "chưa kiểm chứng".
6. **Ghi báo cáo** `docs/reviews/<phạm vi>-<YYYYMMDD>.md` theo mẫu dưới.

## Mẫu báo cáo
```markdown
# Review: <phạm vi> — <YYYY-MM-DD>
Kết luận: PASS | PASS_WITH_NOTES | FAIL
Spec: docs/specs/<id>.md (status: ...)   Files: ...

## Bằng chứng tự động
- ruff: ...   - pytest: x passed / y failed   - coverage: ...

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |

## Phát hiện
### [Blocker|Major|Minor|Nit] <tiêu đề> — `file:line`
- Mô tả / Kịch bản lỗi / Đề xuất sửa / Tham chiếu spec

## Checklist
| Nhóm | Kết quả | Ghi chú |

## Ghi chú cho spec
(Điểm spec xử lý thiếu hoặc mơ hồ phát hiện khi review — cần người dùng quyết định)
```

Câu trả lời cuối: đường dẫn báo cáo, kết luận, danh sách Blocker/Major (mỗi dòng: mức độ, `file:line`, tóm tắt).
