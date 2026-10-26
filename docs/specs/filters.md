---
id: filters
title: Bộ lọc file source
type: module
milestone: M1
modules: [src/loc_counter/filters.py]
tests: [tests/test_filters.py]
spec_refs: ["6.3", "7.5", "9", "15"]
depends_on: [config]
status: reviewed
---

# Bộ lọc file source

## 1. Mục đích & phạm vi
Quyết định một file có bị loại khỏi export/đếm hay không, dựa trên **đường dẫn** (thư mục, glob, test) và **nội dung** (kích thước, binary). Dùng chung cho đếm thư mục (M1), export snapshot (M2) và builder (M4).
Ngoài phạm vi: nhận diện ngôn ngữ (spec `classifier`).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Loại thư mục trong `exclude_dirs` | §9 |
| R2 | Loại file khớp `exclude_globs` | §9 |
| R3 | `include_tests: false` → bỏ `test/`, `tests/`, `*_test.*`, `*.spec.*`, `*.test.*` | §9 |
| R4 | `exclude_binary`, binary ghi cảnh báo | §9, §7.5, §15 |
| R5 | Bỏ file > `max_file_size_kb`, ghi cảnh báo | §6.3, §7.5 |
| R6 | Áp dụng cho cả export và đếm | §9 |

## 3. Giao diện
```python
class SkipReason(StrEnum):
    EXCLUDED_DIR = "excluded_dir"
    EXCLUDED_GLOB = "excluded_glob"
    TEST_FILE = "test_file"
    TOO_LARGE = "too_large"
    BINARY = "binary"

TEST_DIRS: frozenset[str] = frozenset({"test", "tests"})
TEST_GLOBS: tuple[str, ...] = ("*_test.*", "*.spec.*", "*.test.*")
BINARY_SNIFF_BYTES = 8000

def is_dir_excluded(dir_name: str, config: FilterConfig) -> bool:
    """True nếu thư mục (một thành phần tên) bị loại — dùng để cắt nhánh khi duyệt cây."""

def check_path(rel_path: str, config: FilterConfig) -> SkipReason | None:
    """Kiểm tra theo đường dẫn POSIX tương đối (vd. 'src/a/b.py')."""

def is_binary(data: bytes) -> bool:
    """True nếu BINARY_SNIFF_BYTES byte đầu chứa byte NUL (heuristic giống git)."""

def check_content(size_bytes: int, head: bytes, config: FilterConfig) -> SkipReason | None:
    """Kiểm tra kích thước rồi binary. head = các byte đầu file (≥ BINARY_SNIFF_BYTES nếu file đủ dài)."""
```

## 4. Dữ liệu vào / ra
- `rel_path`: đường dẫn POSIX tương đối, không có `./` đầu, phân tách `/` (Windows: người gọi chuyển trước).
- So khớp **phân biệt hoa thường** (giống git).

## 5. Luồng xử lý
`check_path(rel_path, config)` — trả lý do đầu tiên khớp theo thứ tự:
1. Tách `parts = rel_path.split("/")`; `dirs = parts[:-1]`, `name = parts[-1]`.
2. Có `d in dirs` thuộc `config.exclude_dirs` → `EXCLUDED_DIR`.
3. `name` khớp một pattern trong `exclude_globs` (`fnmatch.fnmatchcase`; pattern chứa `/` thì so với cả `rel_path`) → `EXCLUDED_GLOB`.
4. `config.include_tests is False` và (có `d in dirs` thuộc `TEST_DIRS` hoặc `name` khớp `TEST_GLOBS`) → `TEST_FILE`.
5. → `None`.

`check_content(size_bytes, head, config)`:
1. `size_bytes > config.max_file_size_kb * 1024` → `TOO_LARGE`.
2. `is_binary(head)` → `BINARY`.
3. → `None`.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Binary **luôn** bị loại khỏi phần **đếm** (không thể phân loại dòng). `exclude_binary` chỉ quyết định file binary có được đưa vào **export** ở `export_mode: full` hay không (dùng từ M2). `check_content` vẫn trả `BINARY`; người gọi quyết định theo ngữ cảnh.
- File rỗng: không binary, không quá lớn.
- `max_file_size_kb` so sánh lớn hơn **nghiêm ngặt** (đúng 1024 KB vẫn được đếm).
- Mã hóa: §15 nói "UTF-8 → latin-1 → lỗi thì coi là binary". Vì latin-1 giải mã được mọi chuỗi byte, phát hiện binary dựa trên byte NUL; việc giải mã thuộc spec `counter`.

## 7. Xử lý lỗi & thông báo
Module thuần, không I/O, không ném lỗi nghiệp vụ. Thông báo cảnh báo tương ứng `SkipReason` do `counter` tạo.

## 8. Bảo mật, hiệu năng, tái lập
- Hàm thuần, kết quả chỉ phụ thuộc input → tái lập.
- `is_binary` chỉ xem tối đa 8000 byte đầu.

## 9. Test cases
| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-filters-01 | Mọi thư mục mặc định bị loại, ở mọi độ sâu | `node_modules/a.js`, `src/vendor/x.go`, `a/b/__pycache__/c.py`, `.git/config`, `bin/x.cs`, `obj/y.cs` | `EXCLUDED_DIR` | unit |
| TC-filters-02 | Tên file trùng tên thư mục loại không bị loại | `src/build.py`, `src/dist` (file) | `None` | unit |
| TC-filters-03 | Mọi glob mặc định | `a.min.js`, `s.min.css`, `x.js.map`, `Cargo.lock`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `api.pb.go`, `model_generated.ts`, `Form1.designer.cs` | `EXCLUDED_GLOB` | unit |
| TC-filters-04 | Phân biệt hoa thường | `Node_Modules/a.js`, `A.MIN.JS` | `None` | unit |
| TC-filters-05 | include_tests=true giữ test | `tests/test_a.py`, `a_test.go`, `a.spec.ts` | `None` | unit |
| TC-filters-06 | include_tests=false loại test | `test/a.py`, `src/tests/b.py`, `a_test.go`, `a.spec.ts`, `a.test.js` | `TEST_FILE` | unit |
| TC-filters-07 | include_tests=false không loại nhầm | `src/testing/a.py`, `latest.py`, `contest.py` | `None` | unit |
| TC-filters-08 | Thứ tự ưu tiên lý do | `node_modules/a.min.js` | `EXCLUDED_DIR` | unit |
| TC-filters-09 | Kích thước | max 1 KB; size 1024 / 1025 | `None` / `TOO_LARGE` | unit |
| TC-filters-10 | Binary | `b"\x89PNG\x00.."`, `b"abc"`, `b""`, NUL ở byte 8001 | `BINARY`, `None`, `None`, `None` | unit |
| TC-filters-11 | Quá lớn ưu tiên hơn binary | binary + quá lớn | `TOO_LARGE` | unit |
| TC-filters-12 | `is_dir_excluded` | `node_modules`, `src` | `True`, `False` | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | So khớp phân biệt hoa thường (theo git), kể cả trên Windows | Giả định | Đã duyệt 2026-10-22 |
| A2 | Binary luôn không được đếm; `exclude_binary` chỉ ảnh hưởng export ở chế độ `full` | Giả định | Đã duyệt 2026-10-22 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-22 | Tạo mới | M1 |
