---
id: cli-count
title: Lệnh CLI loc-counter count
type: cli
milestone: M1
modules: [src/loc_counter/cli.py]
tests: [tests/test_cli_count.py]
spec_refs: ["11", "15"]
depends_on: [config, counter]
status: reviewed
---

# Lệnh `loc-counter count`

## 1. Mục đích & phạm vi
Đếm LOC một thư mục bất kỳ từ dòng lệnh, in bảng theo ngôn ngữ (tùy chọn theo file) hoặc JSON.
Spec này cũng định nghĩa **khung CLI** (`app` Typer có nhóm lệnh) mà `cli-users` (M3), `cli-analyze` (M5) bổ sung lệnh vào.

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | `loc-counter count <thư-mục>` đếm LOC một thư mục bất kỳ | §11 |
| R2 | Cấu hình qua `--config config.yaml` | §9, §11 |
| R3 | Thông báo lỗi tiếng Việt dễ hiểu | §15 |

## 3. Giao diện
```text
loc-counter count PATH [--config FILE] [--by-file] [--json]
```
| Tham số | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `PATH` | thư mục | bắt buộc | Thư mục cần đếm |
| `--config` | file | không có → mặc định | `config.yaml` |
| `--by-file` | cờ | tắt | In thêm bảng chi tiết theo file |
| `--json` | cờ | tắt | In JSON thay vì bảng |

Mã thoát: `0` thành công (kể cả có cảnh báo); `1` lỗi nghiệp vụ (`LocCounterError`); `2` lỗi cú pháp tham số (Typer).

```python
app: typer.Typer   # entry point loc-counter = "loc_counter.cli:app"

@app.callback()
def main() -> None:
    """Đếm LOC source code trên Git repository."""   # buộc Typer dùng chế độ nhóm lệnh

@app.command("count")
def count_command(path: Path, config: Path | None = None,
                  by_file: bool = False, json_output: bool = False) -> None: ...
```

## 4. Đầu ra
**Bảng (mặc định)**, stdout:
```
Thư mục: <path tuyệt đối>
Ngôn ngữ        Số file      LOC
Python               12    4,310
JavaScript            3      820
TỔNG                 15    5,130
Cảnh báo: 2 (dùng --json để xem chi tiết)
```
- Số có dấu phẩy ngăn cách hàng nghìn. Dòng ngôn ngữ theo thứ tự `CountResult.by_language()`.
- `--by-file`: thêm bảng `Đường dẫn | Ngôn ngữ | LOC | Tổng dòng` theo thứ tự path.
- Không có cảnh báo → không in dòng "Cảnh báo".

**JSON** (`--json`), stdout, UTF-8, `ensure_ascii=False`, indent 2:
```json
{
  "root": "<path tuyệt đối, POSIX>",
  "config": { "...": "config_to_dict(...)" },
  "totals": {"files": 15, "code_lines": 5130},
  "languages": [{"language": "Python", "files": 12, "code_lines": 4310}],
  "files": [{"path": "a.py", "language": "Python", "code_lines": 3, "total_lines": 5}],
  "warnings": [{"kind": "binary", "path": "img.png", "message": "Bỏ qua file binary"}]
}
```

## 5. Luồng xử lý
1. Cấu hình stdout/stderr UTF-8 (`reconfigure(encoding="utf-8", errors="replace")`) để in tiếng Việt khi chạy trên Windows hoặc khi pipe.
2. `cfg = load_config(config)`.
3. `result = count_directory(path, cfg.filters)`.
4. In theo `--json` hoặc bảng (mục 4).
5. `LocCounterError` ở bước 2–3 → in `Lỗi: <thông báo>` ra **stderr**, thoát mã 1.
6. Logging: `logging.basicConfig(level=INFO)` ra stderr; lệnh `count` không ghi `run.log` (thuộc `analyze`).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Thư mục không có file source → bảng chỉ có dòng `TỔNG 0 0`, mã thoát 0.
- Không in stack trace cho `LocCounterError`; lỗi khác (bug) để Python in traceback.

## 7. Xử lý lỗi & thông báo
| Tình huống | Mã thoát | stderr |
|---|---|---|
| PATH không tồn tại | 1 | `Lỗi: Thư mục không tồn tại: <path>` |
| Config lỗi | 1 | `Lỗi: <thông báo ConfigError>` |
| Thiếu PATH | 2 | thông báo của Typer |

## 8. Bảo mật, hiệu năng, tái lập
- JSON sắp xếp ổn định (theo thứ tự của `CountResult`) → tái lập.

## 9. Test cases
Dùng `typer.testing.CliRunner`.

| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-cli-count-01 | Bảng theo ngôn ngữ | thư mục mẫu (`a.py` 3 code, `b.js` 2 code) | mã 0; có dòng `Python`, `JavaScript`, `TỔNG ... 5` | cli |
| TC-cli-count-02 | `--json` | thư mục mẫu | JSON hợp lệ; `totals.code_lines == 5`; có `config` | cli |
| TC-cli-count-03 | `--by-file` | thư mục mẫu | có dòng `a.py` và `b.js` | cli |
| TC-cli-count-04 | `--config` áp dụng | config `exclude_globs: ["*.js"]` | tổng 3 | cli |
| TC-cli-count-05 | Thư mục không tồn tại | `missing/` | mã 1, stderr chứa `Thư mục không tồn tại` | cli |
| TC-cli-count-06 | Config lỗi | config có key lạ | mã 1, stderr chứa `Key cấu hình không hợp lệ` | cli |
| TC-cli-count-07 | Cảnh báo | thư mục có `LICENSE` | dòng `Cảnh báo: 1`; JSON có warning `unknown_language` | cli |
| TC-cli-count-08 | Thư mục rỗng | | mã 0, `TỔNG` = 0 | cli |
| TC-cli-count-09 | Số có dấu phẩy | file 1.234 dòng code | in `1,234` | cli |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | Thêm tùy chọn `--by-file`, `--json` ngoài cú pháp §11 (§11 chỉ ghi `count <thư-mục>`) | Đề xuất | Đã duyệt 2026-10-22 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-22 | Tạo mới | M1 |
