# Báo cáo test — tăng tốc gán tác giả: bỏ JSON/YAML, song song, dùng lại kết quả — 2026-10-29

Phạm vi: đề xuất tăng tốc 2026-10-28, người dùng chọn mục 1 và 2.
Spec: [attribution.md](../specs/attribution.md) (R20, 5.1a, TC-47), [pipeline.md](../specs/pipeline.md) (A21, A22, TC-38, 39).

## Thay đổi
| Mục | Nội dung | File |
|---|---|---|
| 1 | `config.yaml` (cục bộ, đã có trong `.gitignore`): `exclude_languages` thêm `JSON`, `YAML`. Mặc định trong code / spec giữ nguyên | `config.yaml` |
| 2a | Gán tác giả song song theo file (`ATTRIBUTION_WORKERS = min(8, cpu)`), ghép kết quả theo thứ tự `diff_tree`, lỗi theo thứ tự entry | `attribution.py` |
| 2b | `PeriodContext.attribution_memo`: bấm "Phân tích" lại cùng kỳ / bộ lọc / resolver → không gán tác giả lại | `pipeline.py` |
| 2c | `run_log` lọc theo luồng **hoặc** `ContextVar` phiên, để log của luồng con (lỗi git, vượt độ sâu merge) không bị mất khỏi `run.log` | `pipeline.py` |

## Kết quả test
- Toàn bộ suite: **761 passed**, 0 fail (571 s). `ruff check src tests`: sạch.
- Coverage: `attribution.py` 99 % (thiếu 272, 385 — như báo cáo trước), `pipeline.py` 99 % (thiếu 255, có từ trước).
- TDD: 6 test mới fail đúng lý do trước khi code (thiếu `ATTRIBUTION_WORKERS`; spy gọi 2 lần thay vì 1; `run.log` rỗng với log luồng con).

| TC | Test | Kết quả |
|---|---|---|
| TC-attribution-47 (a) | `test_parallel_equals_serial` — 8 repo, 1 luồng vs 4 luồng | pass, bằng nhau hoàn toàn |
| TC-attribution-47 (b) | `test_parallel_error_order` — file 2 lỗi chậm, file 4 lỗi trước | pass, ném lỗi file 2 |
| TC-attribution-47 (c) | `test_parallel_context_propagated` | pass |
| TC-pipeline-38 | `test_attribution_memo` | pass |
| TC-pipeline-39 | `test_run_log_worker_threads`, `test_run_log_attribution_workers` | pass |

## Đo trên repo thật (chạy hết cả kỳ)
Repo local `deepseek-harness` (15 210 commit), nhánh `master`, kỳ 2026-09-02..2026-09-04 (334 commit, 148 merge, 1 895 cặp file). Đo riêng `attribute_period`. Hai tiến trình đo cũ (PID 1596, 16720) vẫn chạy nền trong mọi lần đo.

| Cấu hình | Luồng | File gán tác giả | Thời gian |
|---|---|---|---|
| Trước mọi tối ưu (mặc định) | 1 | 1 409 | > 90 phút, không chạy xong |
| `config.yaml` | 1 | 671 | 11,8 phút |
| Mặc định | 8 | 1 409 | 6,8 phút |
| **`config.yaml`** | **8** | **671** | **4,0 phút** |

- Song song: 11,8 → 4,0 phút (≈ 2,9 lần) với cùng cấu hình; kết quả hai lần **trùng khớp** (40 316 dòng thêm, 6 937 dòng xóa, 338 cảnh báo).
- Bỏ JSON/YAML: 6,8 → 4,0 phút (≈ 1,7 lần) với 8 luồng; số file cần gán tác giả giảm 1 409 → 671.
- Dùng lại kết quả (2b): kiểm bằng TC-pipeline-38, chưa đo trên UI với repo thật. Lần bấm thứ hai bỏ hẳn bước gán tác giả; các bước export / đếm vẫn chạy.

## Còn lại
- ~~Chưa chạy `/feature-review`~~ → đã review và xử lý, xem mục "Bổ sung sau review"; hai spec ở `reviewed`.
- Suite chậm hơn so với trước khi tối ưu (thêm các test dựng nhiều repo mẫu).

## Bổ sung sau review (2026-10-29)
Review độc lập: [reviews/attribution-20261029.md](../reviews/attribution-20261029.md) và [reviews/pipeline-20261029.md](../reviews/pipeline-20261029.md), cả hai **PASS_WITH_NOTES** (không có Blocker / Major).

| Phát hiện | Xử lý |
|---|---|
| pipeline Minor 1: `run_log` reset `ContextVar` trước khi dọn → thoát ở context khác làm sót handler, khóa `run.log`, lệch bộ đếm level | Dọn trước, `reset` sau bọc `suppress(ValueError)`; TC-39 (e) |
| pipeline Minor 2 + ghi chú spec 1–2: memo là tham số `__init__` (`replace` dùng chung memo) và giữ resolver (chứa token) | `field(init=False)` + `weakref` tới resolver; TC-38 kiểm `replace`, weakref |
| pipeline Minor 3, Nit 1: TC-38 chưa so `ReportData`, TC-39 (d) chưa kiểm reset trong luồng phiên | Đã bổ sung |
| attribution ghi chú 2: memo `resolve_merge` lưu cả kết quả chạm `MAX_MERGE_DEPTH` → song song có thể không tái lập | Không ghi nhớ kết quả bị cắt độ sâu (A16); TC-48 (a) |
| attribution Minor 1: 5/8 repo của TC-47 (a) chỉ 1 entry (thực chất không chạy song song) | Mọi repo thêm file phụ, assert ≥ 2 entry; thêm 2 builder của reviewer |
| attribution Minor 2: TC-46 không phủ cache hit một phần, dòng sinh sau merge-base, hội tụ độ sâu 2 | Thêm `build_mixed_born_after_base`, `build_nested_multi`, `build_back_merge` vào TC-46 |
| attribution Minor 3: không test giữ thứ tự lười theo parent | TC-48 (b): số dòng blame trên parent thứ hai bằng bản không tối ưu |
| Nit: thiếu docstring, comprehension khó đọc, test lỗi chỉ phủ 1/4 cache | Đã sửa (test tham số hóa 4 hàm) |

Kết quả sau sửa: **768 passed**; coverage `attribution.py` 99 % (thiếu 1 dòng), `pipeline.py` 99 %. Repo thật (`config.yaml`, 8 luồng, không còn tiến trình đo cũ): **3,0 phút**, kết quả không đổi (40 316 dòng thêm, 6 937 dòng xóa, 338 cảnh báo).

## Mục 3 — giảm `MAX_MERGE_DEPTH`: đo và **không áp dụng**
Cùng repo / kỳ, `config.yaml`, 8 luồng (đo song song với agent review nên thời gian chỉ để so tương đối):

| `MAX_MERGE_DEPTH` | Thời gian | Dòng xóa gán được | Mất |
|---|---|---|---|
| 64 (giữ nguyên) | 207 s | 6 937 | — |
| 8 | 192 s | 1 620 | −77 % |
| 4 | 107 s | 1 064 | −85 % |
| 2 | 75 s | 348 | −95 % |

Phân bố độ sâu lớn nhất mỗi lần gọi tầng 1: > 5 300 / ~6 900 chạm độ sâu 9–23 (đỉnh ở 15 và 19). Giảm độ sâu làm sai `deleted_code` / `net_code` của user để đổi lấy rất ít thời gian → giữ 64. Ghi quyết định **D42** trong [DECISIONS.md](../DECISIONS.md).
