---
id: <id>
title: <Tên chức năng / màn hình>
type: module            # module | screen | cli
milestone: M1
modules: [src/loc_counter/<file>.py]
tests: [tests/test_<file>.py]
spec_refs: ["<mục spec gốc>", "..."]
depends_on: []
status: draft           # draft → approved → implemented → reviewed
---

# <Tên chức năng / màn hình>

## 1. Mục đích & phạm vi
- Làm gì, cho ai, nằm ở đâu trong pipeline.
- Ngoài phạm vi của spec này.

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | ... | §x.y |

## 3. Giao diện
<!-- module: chữ ký hàm/class công khai, kiểu dữ liệu, exception.
     screen: bố cục ASCII + bảng thành phần + trạng thái.
     cli: cú pháp lệnh, tham số, mã thoát, đầu ra. -->

```python
def example(arg: str) -> int:
    """Mô tả ngắn."""
```

### 3.x (chỉ cho screen) Thành phần
| Thành phần | Widget | Key session_state | Mặc định | Validate | Khi thay đổi |
|---|---|---|---|---|---|

### 3.y (chỉ cho screen) Trạng thái màn hình
`idle → loading → ready → running → done | error` — điều kiện chuyển, ô nhập nào bị khóa ở trạng thái nào.

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|

## 5. Luồng xử lý
1. ...
2. ...

```text
pseudo-code hoặc lệnh git chính xác
```

## 6. Quy tắc nghiệp vụ & trường hợp biên
- ...

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo cho người dùng (tiếng Việt) | Log |
|---|---|---|---|

## 8. Bảo mật, hiệu năng, tái lập
- Token: ...
- Hiệu năng: ...
- Tái lập (sắp xếp, timestamp, timezone): ...
- Windows (đường dẫn, CRLF, encoding): ...

## 9. Test cases
| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-<id>-01 | ... | ... | ... | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án đề xuất | Trạng thái |
|---|---|---|---|

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
