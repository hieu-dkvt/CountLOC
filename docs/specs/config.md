---
id: config
title: Cấu hình và giá trị mặc định
type: module
milestone: M1
modules: [src/loc_counter/config.py]
tests: [tests/test_config.py]
spec_refs: ["3.1", "9", "15", "16"]
depends_on: []
status: reviewed
---

# Cấu hình và giá trị mặc định

## 1. Mục đích & phạm vi
- Định nghĩa cấu trúc cấu hình dùng chung (bộ lọc file, timezone), giá trị mặc định bắt buộc, đọc/validate `config.yaml`, xuất cấu hình ra dict (cho `manifest.json`).
- Định nghĩa exception gốc `LocCounterError` (thông báo tiếng Việt) dùng chung cho mọi module.
- Ngoài phạm vi: `identities.yaml` (spec `identity`, M3); thư mục cache repo (spec `git_repo`, M2).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Mặc định bộ lọc đúng nguyên văn khối YAML §9 | §9 |
| R2 | Người dùng chỉnh được qua file `config.yaml` | §9 |
| R3 | Múi giờ mặc định `Asia/Bangkok` | §3.1 |
| R4 | Manifest chứa "toàn bộ cấu hình bộ lọc đã dùng" | §12 |
| R5 | Thêm `exclude_languages` mặc định `["Text only", "Markdown", "reStructuredText"]` | PLAN D3 |

## 3. Giao diện
```python
class LocCounterError(Exception):
    """Lỗi nghiệp vụ; str(err) là thông báo tiếng Việt cho người dùng."""

class ConfigError(LocCounterError): ...

ExportMode = Literal["source_only", "full"]

@dataclass(frozen=True)
class FilterConfig:
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS
    exclude_globs: tuple[str, ...] = DEFAULT_EXCLUDE_GLOBS
    exclude_binary: bool = True
    max_file_size_kb: int = 1024
    include_tests: bool = True
    count_docstrings: bool = False
    export_mode: ExportMode = "source_only"
    exclude_languages: tuple[str, ...] = DEFAULT_EXCLUDE_LANGUAGES

@dataclass(frozen=True)
class AppConfig:
    filters: FilterConfig = FilterConfig()
    timezone: str = "Asia/Bangkok"

def load_config(path: Path | None = None) -> AppConfig:
    """Đọc config.yaml; path None → toàn bộ mặc định."""

def config_from_dict(data: Mapping[str, Any]) -> AppConfig:
    """Validate dict (đã parse từ YAML) và dựng AppConfig."""

def config_to_dict(config: AppConfig) -> dict[str, Any]:
    """Dict phẳng, kiểu JSON-able (list thay tuple), key theo thứ tự cố định — dùng cho manifest."""
```

## 4. Dữ liệu vào / ra & giá trị mặc định
`config.yaml` là mapping **phẳng**, key giống §9, cộng `timezone`:

| Key | Kiểu | Mặc định |
|---|---|---|
| `exclude_dirs` | list[str] | `[node_modules, vendor, dist, build, out, target, .venv, venv, __pycache__, .git, third_party, bin, obj]` |
| `exclude_globs` | list[str] | `["*.min.js", "*.min.css", "*.map", "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "*.pb.go", "*_generated.*", "*.designer.cs"]` |
| `exclude_binary` | bool | `true` |
| `max_file_size_kb` | int > 0 | `1024` |
| `include_tests` | bool | `true` |
| `count_docstrings` | bool | `false` |
| `export_mode` | `source_only` \| `full` | `source_only` |
| `exclude_languages` | list[str] (tên lexer Pygments) | `["Text only", "Markdown", "reStructuredText"]` |
| `timezone` | str (tên IANA) | `Asia/Bangkok` |

Key nào có trong file thì **thay thế** hoàn toàn giá trị mặc định (list không gộp). Key vắng → mặc định.

## 5. Luồng xử lý
`load_config(path)`:
1. `path is None` → `AppConfig()`.
2. Không tồn tại → `ConfigError`.
3. Đọc UTF-8 (`utf-8-sig`, chấp nhận BOM), `yaml.safe_load`. Lỗi giải mã hoặc lỗi đọc file → `ConfigError`. Lỗi cú pháp → `ConfigError`. File rỗng (`None`) → `{}`.
4. Không phải mapping → `ConfigError`.
5. `config_from_dict(data)`.

`config_from_dict(data)`:
1. Key không thuộc bảng mục 4 → `ConfigError` liệt kê key lạ (sắp xếp).
2. Validate kiểu từng key (bool phải là bool YAML thật, không nhận `"true"` chuỗi; int không nhận bool; list phải là list các chuỗi).
3. `export_mode` ∉ {source_only, full} → lỗi. `max_file_size_kb <= 0` → lỗi.
4. `timezone`: kiểm `zoneinfo.ZoneInfo(name)`; lỗi → `ConfigError`.
5. List → tuple; dựng `FilterConfig`, `AppConfig`.

`config_to_dict(config)`: thứ tự key: `exclude_dirs, exclude_globs, exclude_binary, max_file_size_kb, include_tests, count_docstrings, export_mode, exclude_languages, timezone`.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Dataclass frozen → cấu hình bất biến, dùng an toàn giữa process (M7).
- Không chứa token hay thông tin xác thực (token không bao giờ đi qua config).

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception | Thông báo |
|---|---|---|
| File không tồn tại | ConfigError | `Không tìm thấy file cấu hình: <path>` |
| Không phải UTF-8 / lỗi đọc | ConfigError | `File cấu hình phải là văn bản UTF-8: <path>` / `Không đọc được file cấu hình: <path> (<lỗi>)` |
| YAML sai cú pháp | ConfigError | `File cấu hình không đúng định dạng YAML: <path> (<chi tiết>)` |
| Không phải mapping | ConfigError | `File cấu hình phải là danh sách key: value` |
| Key lạ | ConfigError | `Key cấu hình không hợp lệ: <k1>, <k2>` |
| Sai kiểu | ConfigError | `Giá trị của "<key>" phải là <kiểu mong đợi>` |
| export_mode sai | ConfigError | `export_mode phải là "source_only" hoặc "full"` |
| max_file_size_kb ≤ 0 | ConfigError | `max_file_size_kb phải là số nguyên dương` |
| timezone sai | ConfigError | `Múi giờ không hợp lệ: <tên>` |

## 8. Bảo mật, hiệu năng, tái lập
- `yaml.safe_load` (không `yaml.load`).
- `config_to_dict` có thứ tự key cố định → manifest tái lập.

## 9. Test cases
| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-config-01 | Mặc định đúng §9 + D3 | `load_config(None)` | Mọi trường bằng bảng mục 4 | unit |
| TC-config-02 | Ghi đè một phần | yaml `max_file_size_kb: 10`, `include_tests: false` | 2 trường đổi, còn lại mặc định | unit |
| TC-config-03 | List thay thế, không gộp | `exclude_dirs: [a]` | `exclude_dirs == ("a",)` | unit |
| TC-config-04 | Key lạ | `exclude_dir: [a]` | ConfigError chứa `exclude_dir` | unit |
| TC-config-05 | Sai kiểu bool / int / list | `exclude_binary: "yes"`, `max_file_size_kb: true`, `exclude_globs: "*.js"` | ConfigError | unit |
| TC-config-06 | export_mode sai | `export_mode: all` | ConfigError | unit |
| TC-config-07 | max_file_size_kb ≤ 0 | `0` | ConfigError | unit |
| TC-config-08 | timezone sai / hợp lệ | `Mars/Base` / `UTC` | lỗi / `timezone == "UTC"` | unit |
| TC-config-09 | File không tồn tại, YAML hỏng, không phải mapping, file rỗng | | 3 trường hợp lỗi; file rỗng → mặc định | unit |
| TC-config-10 | `config_to_dict` | mặc định | Dict có đúng 9 key theo thứ tự mục 5, list thay tuple, `json.dumps` được | unit |
| TC-config-11 | Encoding file cấu hình | file UTF-16; file UTF-8 có BOM | UTF-16 → ConfigError `UTF-8`; BOM → đọc bình thường | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | `LocCounterError` đặt trong `config.py` (không thêm module `errors.py` ngoài cấu trúc §5) | Giả định | Đã duyệt 2026-10-22 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-22 | Tạo mới | M1 |
| 2026-10-22 | Lỗi encoding/đọc file → ConfigError; chấp nhận BOM; thêm TC-config-11. Người dùng duyệt sửa theo review | Review M1 (Minor config.py:72) |
