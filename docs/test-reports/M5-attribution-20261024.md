# Báo cáo test — attribution (cập nhật M5)

Ngày: 2026-10-24 · Phạm vi: `docs/specs/attribution.md` (TC-attribution-01..43; mới: TC-38..43 — sha theo dòng, `commit_stats`, D35)

## Kết quả
| Lệnh | Kết quả |
|---|---|
| `uv run pytest tests/test_attribution.py -q` | 75 passed (43 TC, có parametrize) |
| `uv run pytest -q --cov=loc_counter` (toàn bộ) | 512 passed, 0 fail, 0 skip (5 phút 02 giây) |
| `uv run ruff check src tests` | sạch |

Coverage `attribution.py`: **100 %** (395 câu lệnh). Toàn bộ package 98 %.

## Truy vết TC
43/43 TC trong spec có hàm test (docstring `TC-attribution-NN`), không có test mồ côi.

| TC | Hàm test | Kết quả |
|---|---|---|
| TC-38 | `test_section14_commit_stats` | Đạt — 4 ô: alice add 7/0/5/0, bob util 8/0/8/0, alice del 0/2/0/2, bob del 0/1/0/1 |
| TC-39 | `test_commit_sha_through_merges` | Đạt — TC-11 (không có ô merge), TC-13 (ô merge 0/1/0/1), TC-14 (dòng xung đột → sha merge), TC-36 (sha commit bob trên `feat2`) |
| TC-40 | `test_commit_sha_of_moved_lines` | Đạt — D22, D28 (b), D28 (a) (sha commit dời, không phải commit carol đổi thụt lề) |
| TC-41 | `test_commit_invariants` (12 repo) + `assert_commit_invariants` trong TC-21, 22, 25, 33 | Đạt — chạy 2 lần cho kết quả bằng nhau |
| TC-42 | `test_commit_stats_no_cells_and_multi_email` | Đạt |
| TC-43 | `test_positional_construction_compat` | Đạt — test `builder` (dựng `FileAttribution` theo vị trí) không đổi |

TC-01..37 (M4) vẫn pass, không đổi kỳ vọng.

## Test bắt buộc
Mục D (attribution) không đổi so với báo cáo M4 — vẫn đạt. Tiêu chí M5 (`analyze`, `Theo_tuan`) thuộc `counter` / `pipeline` / `cli-analyze`, chưa kiểm ở đây.

## Ghi chú
- Lỗi lần chạy đầu thuộc **test** (không phải code): gọi `make_repo()` nhiều lần trong một test dùng lại cùng thư mục `tmp_path/src` → đặt tên riêng cho từng repo (`make_repo("r11")`…); TC-42 (c)(d) dùng chung một repo §14 cho hai kỳ.
- Cách làm: bên trong `_Attributor`, dict tạm lưu `dòng → sha`; `added_by` / `deleted_by` suy ra từ `commit_accounts` khi tạo `FileAttribution` → bất biến 4b đúng theo cấu trúc.

## Lần 2 (sau review PASS_WITH_NOTES — reviews/attribution-20261024.md)
Sửa Minor (chỉ test): `assert_commit_invariants(result, rerun)` kiểm thêm chạy 2 lần; áp cho repo TC-21, 22, 24 (binary + quá lớn + `T` → `commit_stats == ()`), 25, 28 (committer khác author), 33. Thêm docstring `stats_tuple`.

| Lệnh | Kết quả |
|---|---|
| `uv run pytest tests/test_attribution.py -q` | 75 passed |
| `uv run ruff check src tests` | sạch |
