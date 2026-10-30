# Báo cáo test — attribution (tối ưu hiệu năng D23, R19) — 2026-10-28

Spec: [attribution.md](../specs/attribution.md) (5.6a, TC-44..46). Code: `src/loc_counter/attribution.py`.

## Kết quả
- Toàn bộ suite: **755 passed**, 0 fail, 0 skip (473 s). `ruff check src tests`: sạch.
- `tests/test_attribution.py`: **80 passed** (75 test cũ TC-01..43 không đổi + 5 test mới).
- Coverage `attribution.py`: **99 %** (mục tiêu ≥ 85 %); chưa phủ dòng 268 (dùng lại kết quả blame đã nạp trong `_fill_blame`) và 381 (bỏ qua dòng không cần blame trong `_warm_parent`) — nhánh phòng thủ mới, không ảnh hưởng kết quả.

## Truy vết TC
| TC | Test | Kết quả |
|---|---|---|
| TC-attribution-44 | `test_merge_pure_queries_cached[False/True]`, `test_error_not_memoized` | pass |
| TC-attribution-45 | `test_merge_blame_batched` | pass |
| TC-attribution-46 | `test_optimizations_do_not_change_result` (7 repo: TC-11, 12, 13, 14, 36, 44 ×2) | pass — kết quả bằng nhau khi tắt tối ưu |

TDD: trước khi code, TC-44/45/46 fail đúng lý do (`is_ancestor` 14 lần gọi / 5 cặp khác nhau; 10 lệnh blame so với 4; thiếu `_warm_merge`).

## Đo hiệu năng thật (không thuộc suite)
Repo local `deepseek-harness` (15 210 commit, 9 080 file), nhánh `master`, kỳ 2026-09-02..2026-09-04 (334 commit, 148 merge, 1 895 cặp file). Ngân sách đo 240 s, script đo ở thư mục scratchpad (không nằm trong repo). Hai tiến trình đo cũ vẫn chạy nền trong cả hai lần đo, nên số tuyệt đối bị lệch như nhau.

| | Trước | Bản 1 (chỉ cache) | Bản cuối (cache + làm nóng theo tầng) |
|---|---|---|---|
| File xử lý trong 240 s | 319 | 342 | **561** |
| File `lines` (có blame) | 107 | 126 | **264** |
| File chậm nhất | 16,3 s | 29,9 s | **4,9 s** |
| Lệnh git / file `lines` | ~116 | ~85 | **~40** |
| `merge-base --is-ancestor` | 4 222 | 263 | 353 |

File chậm nhất dao động giữa các lần đo vì tranh chấp CPU; cột "Lệnh git / file `lines`" và "File `lines`" đáng tin hơn.

Phát hiện: nhóm dòng xóa tầng 1 nhỏ (2–3 dòng) nhưng `resolve_merge` đệ quy sâu gấp ~10 lần (139 lần tầng 1 → 1 467 lần sâu hơn); bản 1 (chỉ gom tầng 1) gần như không giảm blame, nên spec được sửa sang làm nóng theo tầng (lịch sử spec 2026-10-28).

## Còn lại / chưa đạt
- Chưa đo được thời gian chạy hết cả kỳ (ước tính ~14 phút từ mẫu thiên về file `skip`, **không đáng tin**). Phần lớn thời gian còn lại là số lệnh git tuần tự (~20 ms/lệnh trên Windows): `blame` ngược/xuôi ~3 000 lần mỗi loại và `rev-list --ancestry-path` ~3 200 lần.
- Hướng tiếp theo (chưa làm, cần spec): chạy song song các file bằng thread (mỗi lệnh git là một tiến trình riêng nên hưởng lợi nhiều).
- Chưa chạy `/feature-review attribution`.
