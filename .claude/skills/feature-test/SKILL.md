---
name: feature-test
description: Chạy và đánh giá test cho LOC Counter — theo feature, milestone, toàn bộ, hoặc kiểm tra danh sách test bắt buộc (spec mục 6.4, 14); đối chiếu test case trong spec với test thực tế, sinh test còn thiếu, chạy pytest + coverage, phân tích lỗi và ghi báo cáo. Dùng khi cần test, chạy test, kiểm tra một feature đã làm đúng chưa.
argument-hint: "[<id> | M1..M7 | all | mandatory] [--gen]"
---

# Test LOC Counter

Tham số: `$ARGUMENTS`
- `<id>`: test một feature (theo `docs/specs/<id>.md`).
- `M<n>`: mọi feature có `milestone: M<n>` + tiêu chí hoàn thành milestone (mục 13 spec gốc).
- `all` hoặc trống: toàn bộ test suite.
- `mandatory`: chỉ đối chiếu danh sách [mandatory-tests.md](mandatory-tests.md) với test hiện có.
- `--gen`: được phép viết test còn thiếu (mặc định chỉ báo thiếu; riêng khi được gọi từ `/feature-implement` thì luôn sinh).

Mọi lệnh chạy trong thư mục gốc project. Chưa có `.venv` → `uv sync` trước.

## Bước 1 — Xác định phạm vi
- Feature: đọc front matter (`tests:`, `modules:`) và bảng "Test cases" của spec.
- Milestone: gộp mọi spec của milestone + tiêu chí ở PLAN.md.

## Bước 2 — Truy vết TC ↔ test
Với mỗi `TC-<id>-NN` trong spec, tìm hàm test có docstring bắt đầu bằng ID đó (Grep pattern `"""TC-<id>-\d+` trong `tests/`, `-B 1` để lấy tên hàm).
Lập bảng: `TC | hàm test | có/thiếu`. Đồng thời liệt kê test có TC ID không tồn tại trong spec (test "mồ côi").
Feature thuộc mục 6.4/14 → đối chiếu thêm với [mandatory-tests.md](mandatory-tests.md).

## Bước 3 — Sinh test thiếu (nếu được phép)
Viết theo quy ước trong agent `test-engineer` (docstring có TC ID, giá trị kỳ vọng lấy từ spec, fixture Git có ngày cố định, không mạng). Nhiều test hoặc fixture phức tạp → giao agent `test-engineer`.

## Bước 4 — Chạy
```bash
uv run pytest <các file test trong phạm vi> -q --tb=short -p no:cacheprovider
uv run pytest <phạm vi> --cov=loc_counter --cov-report=term-missing -q
```
- Milestone M1: nếu có `cloc` trên máy, so sánh `uv run loc-counter count <thư mục mẫu>` với `cloc` (sai lệch ≤ 2%). Không có `cloc` → ghi rõ "chưa kiểm được tiêu chí cloc", không coi là pass.
- Milestone M5: chạy `loc-counter analyze` trên repo mẫu, kiểm đủ file đầu ra mục 12 và kiểm tra chéo mục 8.3.
- Milestone M7: đo thời gian trên repo lớn nếu người dùng cung cấp.
- Chạy lại lần 2 với cùng input để kiểm **tính tái lập** khi phạm vi có sinh file đầu ra (so sánh hash file, bỏ qua `generated_at`).

## Bước 5 — Phân tích lỗi
Với mỗi test fail, phân loại: **bug code** / **test sai** / **spec mơ hồ hoặc mâu thuẫn**.
- Không bao giờ sửa giá trị kỳ vọng để khớp code. Nghi giá trị kỳ vọng trong spec sai → hỏi người dùng.
- Khi gọi từ `/feature-implement`: sửa bug code rồi chạy lại. Gọi độc lập: báo cáo, đề xuất sửa, hỏi người dùng có sửa không.

## Bước 6 — Báo cáo
Ghi `docs/test-reports/<phạm vi>-<YYYYMMDD>.md` và tóm tắt cho người dùng:
- Tổng pass/fail/skip, coverage của các module trong phạm vi (mục tiêu ≥ 85% cho module lõi).
- Bảng truy vết TC (đủ / thiếu / fail).
- Danh sách test bắt buộc còn thiếu (nếu có).
- Tiêu chí milestone: đạt / chưa đạt / chưa kiểm được.
