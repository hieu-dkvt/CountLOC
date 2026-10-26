# Báo cáo test — attribution (M4)

Ngày: 2026-10-23 · Phạm vi: `docs/specs/attribution.md` (TC-attribution-01..33)

## Kết quả
| Lệnh | Kết quả |
|---|---|
| `uv run pytest tests/test_attribution.py -q` | 46 passed (33 TC, có parametrize) |
| `uv run pytest -q` (toàn bộ) | 424 passed, 0 fail, 0 skip |
| `uv run ruff check src tests` | sạch |

Coverage `attribution.py`: 97 % (thiếu 108, 176, 198, 201, 203, 214, 216, 240, 301, 434 — nhánh phòng thủ: memo D23 trúng, criss-cross khi tìm neo, `fb` không phải tổ tiên của parent, `first_commit_after` None trong D23, merge lồng nhau, số cờ phân loại khác số dòng).

Kiểm chứng chéo: agent `test-engineer` viết một prototype độc lập theo spec (scratchpad `te_proto/attr_proto.py`) — cũng pass 46/46.

## Truy vết TC
33/33 TC có test, không có test mồ côi (bảng hàm ↔ TC: docstring `TC-attribution-NN` trong `tests/test_attribution.py`).

## Test bắt buộc (mandatory-tests mục D, phần thuộc attribution)
| Mục | Test | Kết quả |
|---|---|---|
| §14 theo user: alice 5/2/+3, bob 8/1/+7 | TC-01 | Đạt |
| Rename trong kỳ không tính là xóa + thêm | TC-05 | Đạt |
| start trước commit đầu → không có dòng xóa (loc_start = 0 kiểm ở builder/M5) | TC-03 | Đạt |
| Block comment nhiều dòng không tăng LOC | TC-04 | Đạt |
| Noreply + email công ty gộp cùng account | TC-28 | Đạt |
| LOC trên nội dung export (10→20/13/17/20), quy tắc cấp file §7.4, zip theo user | — | Thuộc `builder` (chưa làm) |

## Tái lập
TC-29 chạy `attribute_period` 2 lần, kết quả bằng nhau (kể cả thứ tự cảnh báo). TC-19: tái dựng §7.3 với mọi account trùng byte C_END trên 6 repo kịch bản.

## Ghi chú spec (đã làm rõ, không đổi hành vi)
Định dạng khoảng trong thông báo, danh sách account của `SEQUENTIAL_EDIT`, thứ tự kiểm `cand` ngoài kỳ, kịch bản fixture TC-10/17/18, bộ lọc TC-24 — ghi trong Lịch sử thay đổi của spec.

## Lần 2 (sau review FAIL — reviews/attribution-20261023.md)
| Lệnh | Kết quả |
|---|---|
| `uv run pytest tests/test_attribution.py -q` | 55 passed (TC-01..37) |
| `uv run pytest -q` (toàn bộ) | 433 passed |
| `uv run ruff check src tests` | sạch |

Coverage `attribution.py` 98 % (thiếu 111, 195, 221, 223, 234, 236, 324-325: memo D23 trúng, nhánh phòng thủ neo merge-base).
- TC-34, 35 tái hiện 2 Major của review: pass sau khi thêm bước (0) của D28; prototype không có bước (0) làm hai test này fail (kiểm chứng của `test-engineer`).
- TC-36 merge lồng nhau (spy xác nhận đi qua cả hai tầng merge), TC-37 (a)–(d) nhánh phòng thủ: pass.
- TC-19 với TC-34/35 so đa tập dòng bỏ khoảng trắng (D22 giữ bản C_START của dòng chỉ đổi khoảng trắng) — spec đã sửa kỳ vọng.

## Lần 3 (sau review r2 — reviews/attribution-20261023-r2.md)
`uv run pytest -q`: 436 passed; ruff sạch; coverage `attribution.py` 99 % (chỉ còn `_split_lines` nhánh dòng cuối không EOL, 111).
- TC-36: fixture mới chạy thật tới đệ quy D23 độ sâu 2 (spy `resolve_merge`: `(1, outer)`, `(2, inner)`).
- TC-37 (e): unit với repo giả cho neo merge-base, memo, blame lần 2 ngoài kỳ.
