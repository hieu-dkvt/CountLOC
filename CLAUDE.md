# LOC Counter — hướng dẫn cho Claude Code

## Bối cảnh
- **Spec gốc (nguồn sự thật):** [spec_count_LOC.md](spec_count_LOC.md). Đọc phần liên quan trước mọi việc.
- **Thư mục gốc project:** thư mục chứa file này (tương ứng `loc-counter/` ở mục 5 của spec). Mọi lệnh `uv`, `pytest` chạy từ đây.
- **Kế hoạch & trạng thái:** [docs/PLAN.md](docs/PLAN.md) — milestone, danh sách feature, câu hỏi mở, rủi ro kỹ thuật.
- **Spec xử lý từng chức năng/màn hình:** `docs/specs/` (xem [README](docs/specs/README.md)).
- **Báo cáo review / test:** `docs/reviews/`, `docs/test-reports/`.
- Môi trường: Windows 11, git 2.55, **không có `python` trên PATH** → luôn dùng `uv` (`uv sync`, `uv run ...`). uv có sẵn CPython 3.14; project yêu cầu `>=3.11`.

## Quy tắc bắt buộc (từ spec gốc)
1. Triển khai theo thứ tự Milestone M1 → M7 (mục 13). Test của milestone hiện tại phải pass trước khi sang milestone kế.
2. **Không tự ý thay đổi** định nghĩa mục 3 và thuật toán mục 6, 7. Mơ hồ/mâu thuẫn → ghi vào mục "Câu hỏi mở" của PLAN.md và **hỏi người dùng**, không tự quyết.
3. Giá trị mặc định trong spec là bắt buộc.
4. Code có type hint, docstring ngắn (tiếng Việt), unit test cho mọi module lõi.
5. UI, thông báo lỗi, báo cáo: **tiếng Việt**. Tên biến/hàm/file: **tiếng Anh**.
6. Token GitHub **không bao giờ** xuất hiện trong log, file cấu hình, báo cáo, manifest, message exception, hay config của repo cache.
7. Chỉ dùng thư viện ở mục 4 (+ dev tool `pytest-cov`, `ruff`, và `tzdata` cho Windows). Cần thêm thư viện khác → hỏi người dùng.

## Quy trình làm việc (spec-first)
**Trước khi lập trình bất kỳ màn hình, chức năng hay module nào phải có spec xử lý** trong `docs/specs/` với `status: approved`.
Hook `.claude/hooks/require-spec.cjs` sẽ chặn mọi lần ghi `src/loc_counter/*.py` (trừ `__init__.py`) nếu chưa có spec được duyệt liệt kê file đó trong `modules:`.

| Bước | Skill | Kết quả |
|---|---|---|
| 1. Lập kế hoạch milestone | `/milestone-plan M<n>` | Cập nhật PLAN.md: feature, thứ tự, câu hỏi mở |
| 2. Viết spec xử lý | `/feature-spec <id>` | `docs/specs/<id>.md`, người dùng duyệt → `approved` |
| 3. Lập trình | `/feature-implement <id>` | Test (từ TC trong spec) + code, theo đúng spec |
| 4. Test | `/feature-test <id>\|M<n>\|all\|mandatory` | Chạy pytest, đối chiếu TC ↔ test, báo cáo |
| 5. Review | `/feature-review <id>` | Agent `code-reviewer` review độc lập, báo cáo PASS/FAIL |

Vòng đời spec: `draft` → `approved` (người dùng duyệt) → `implemented` (test pass) → `reviewed` (review PASS).
Thay đổi hành vi so với spec đã duyệt → **sửa spec trước** (ghi mục Lịch sử thay đổi), báo người dùng, rồi mới sửa code.

Agents: `spec-analyst` (phân tích spec gốc, tìm mơ hồ), `test-engineer` (viết test/fixture repo Git), `code-reviewer` (review độc lập, chỉ đọc + ghi báo cáo).

## Lệnh thường dùng (chạy ở thư mục gốc project)
```bash
uv sync                                   # cài dependency
uv run pytest -q                          # toàn bộ test
uv run pytest tests/test_classifier.py -q # một module
uv run pytest --cov=loc_counter --cov-report=term-missing
uv run ruff check src tests
uv run loc-counter count <dir>
uv run streamlit run src/loc_counter/app.py
```

## Quy ước code
- Gọi git qua `subprocess.run([...])` với list tham số, **không** `shell=True`; đọc blob dạng bytes (`git cat-file`) để giữ nguyên kiểu xuống dòng; dùng `-z` và `-c core.quotepath=off` khi cần đọc đường dẫn.
- Đường dẫn: `pathlib` trên đĩa, đường dẫn POSIX (`/`) bên trong zip và báo cáo.
- Kết quả tái lập được: sắp xếp ổn định mọi danh sách, timestamp cố định trong zip, timezone luôn tường minh (`zoneinfo`).
- Lỗi cho người dùng: exception có thông báo tiếng Việt; log chi tiết (kèm lệnh git, đã che token) bằng `logging`.
- Test: mỗi test case trong spec có ID `TC-<id>-NN`; docstring của hàm test **bắt đầu bằng ID đó** để truy vết. Repo Git mẫu tạo trong `tests/conftest.py`, ngày commit cố định, không truy cập mạng.
