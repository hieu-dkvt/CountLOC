# Review: attribution (lần 2) — 2026-10-23
Kết luận: **FAIL**
Spec: docs/specs/attribution.md (status: implemented)   Files: `src/loc_counter/attribution.py`, `tests/test_attribution.py` (đọc thêm `tests/conftest.py`, `docs/PLAN.md` D22/D28, báo cáo lần 1 `reviews/attribution-20261023.md`)

## Bằng chứng tự động
- ruff: `All checks passed!` (src, tests)
- pytest `tests/test_attribution.py`: **55 passed** / 0 failed (74 s)
- coverage `loc_counter.attribution`: **98 %** (379 stmt, thiếu `111, 195, 221, 223, 234, 236, 324-325`)
- Script kiểm chứng (ngoài project): `C:\Users\User\AppData\Local\Temp\claude\d--PJ-Tool\cea15fb9-6e82-493f-a3be-ab22515249c0\scratchpad\rv2\test_probe2.py` (spy `resolve_merge` ghi độ sâu, chạy bằng `uv run pytest <file> -s --rootdir <rv2>` với bản sao `conftest.py`), `...\scratchpad\bench.py` và `...\scratchpad\rv2\bench20k.py` (đo `_match_moves`).

## Trạng thái phát hiện của review lần 1
| Phát hiện lần 1 | Đã sửa? | Bằng chứng |
|---|---|---|
| Major 1 — D28 (a) gán dòng chỉ đổi thụt lề cho người xóa dòng trùng khóa | Đã sửa | Bước (0) `attribution.py:368-377`; TC-34 (`test_ws_only_not_matched_to_line_deleted_elsewhere`) dùng đúng kịch bản lần 1 và kiểm `added_by`, `deleted_by`, `added_code/deleted_code`, không `MOVED_LINES` |
| Major 2 — D28 (b) đánh dấu xóa dòng còn sống khi có dòng trùng dời vào | Đã sửa | `remaining_alive` sau bước (0) `:370-392`; TC-35 dùng đúng kịch bản lần 1 |
| Minor — ghép D28 bậc hai | Đã sửa | `_key_index` / `_take` `:120-131`; `bench.py` 4 000 × 4 000: 4,1 s → 0,0 s; 20 000 × 20 000: 0,1 s |
| Minor — thiếu test nhánh D23 / phòng thủ | **Sửa một phần** | TC-36, TC-37 (a)–(d) có test; nhưng **TC-36 không chạy tới đệ quy** (Major dưới đây); `:221, :223, :234, :324-325` vẫn chưa có test |
| Minor — commit vắng trong `by_sha` bị coi là người tạo path | Đã sửa | `:398-399` lọc theo `by_sha`; TC-37 (d) |
| Nit — dict có thể sửa trong dataclass frozen | Sửa một phần | `MappingProxyType` `:285-286`, `:541`; `hash()` vẫn lỗi (Nit dưới đây) |
| Nit — thiếu DEBUG dòng mới UNATTRIBUTED | Đã sửa | `:311`, `:324` |
| Nit — thiếu docstring method nội bộ | Đã sửa | `:173`, `:185`, `:210`, `:241` |
| Nit — `_split_lines` riêng | Chưa (để builder) | `:106-112` |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.1.1 | `by_sha`, `commit_accounts` qua `resolver.resolve` | `attribution.py:510-511`; TC-28 | Đạt |
| 5.1.2 | `diff_tree`, `RENAME_LIMIT` path `""` | `:514-519`; TC-27 | Đạt |
| 5.1.3 | Một lượt `read_blobs`, SHA bỏ trùng, bỏ symlink/gitlink | `:521-527` | Đạt |
| 5.2 | `SideInfo`, `skip`/`whole`/`lines`, `last_touch_by` + UNATTRIBUTED | `:172-182`, `:248-264`; TC-24, 25, 37(b) | Đạt |
| 5.3 | Hunk theo 3 trường hợp | `:289-296`; TC-02, 22, 23 | Đạt |
| 5.4 | Blame `-M -C`; boundary → blame lại không `-M -C` (D22); DEBUG | `:298-329`; TC-16, 20 | Đạt (nhánh `:324-325` không có test) |
| 5.5 | Reverse blame, nhóm `(L, fn)`, `first_commit_after`, merge → D23 | `:331-356`; TC-11..14, 22, 33 | Đạt |
| 5.6 | `resolve_merge`: guard neo == P, `merge_bases`, đệ quy, `MAX_MERGE_DEPTH` | `:190-237`; TC-11..15, 36, 37(a) | Code đạt (đệ quy kiểm chứng tay, độ sâu 2, kết quả đúng); **TC-36 không kiểm đệ quy** (Major) |
| 5.7 (0) | Cặp chỉ đổi khoảng trắng `U ↔ O`, không gán, chạy trước (a)/(b) | `:368-377`; TC-34, 35 | Đạt |
| 5.7 (a) | `U` còn lại ↔ `X` (dòng cũ có `deleted_by`) | `:379-385`; TC-18 | Đạt |
| 5.7 (b) | `O` còn lại ↔ `N` (D22) | `:387-392`; TC-17 | Đạt |
| 5.7 | Chỉ mục `key → hàng đợi tăng dần`, tuyến tính | `:120-131` | Đạt (đã đo) |
| 5.8 | `renamed_by`: chỉ commit thuộc kỳ, phần tử cuối, gom 1 lần `paths_exist` | `:394-416`; TC-05..09, 37(d) | Đạt |
| 5.8 | UNATTRIBUTED / MOVED_LINES / MULTI_USER_HUNK / SEQUENTIAL_EDIT | `:418-452`; TC-14, 16, 29, 33 | Đạt |
| 5.9.1–2 | `added_code` theo C_END, `deleted_code` theo C_START, cờ thiếu = False + WARNING | `:455-494`; TC-01, 04, 22, 25, 26, 37(c) | Đạt |
| 5.9.3–4 | `files` gồm cả file không phải source; `users` gồm account 0 dòng | `:495-499`; TC-02, 26, 36 | Đạt |
| 5.9.5–6 | Thứ tự phát + sort ổn định `(path, kind)`; log INFO | `:513-540`; TC-29 | Đạt |
| §6 | Chỉ đổi khoảng trắng → giữ bản C_START, không gán, không cảnh báo | TC-20, 34, 35 | Đạt |
| §7 | Bảng lỗi / thông báo, DEBUG từng dòng | `:197`, `:261`, `:311`, `:324`, `:353`, `:412-415`, `:429-452`, `:461` | Đạt |
| TC-01..37 | Mỗi TC có test, docstring bắt đầu bằng ID | 37/37 TC có test (TC-02 ×2, TC-15 ×2, TC-37 ×4) | Đạt trừ TC-36 (test không kiểm điều TC mô tả) |

## Phát hiện

### [Major] TC-36 không chạy tới đệ quy D23 — `tests/test_attribution.py:1193-1251` (nhánh code `src/loc_counter/attribution.py:236`)
- **Mô tả**: TC-36 được thêm để giữ hành vi **đệ quy** D23 (spec 5.6 bước 2.4, "`c` là merge → `resolve_merge(..., depth + 1)`"; spec TC-36 ghi "v2 → bob (qua 2 tầng merge)"). Coverage cho thấy dòng `:236`, nơi duy nhất gọi đệ quy, **không được test nào chạy tới**. Vì bob sửa v5 trên `feat` (`:1205-1208`), reverse blame của v2 trả `L = "bob feat"`. Khi đó `first_commit_after` trả thẳng merge **trong** (dave) ở tầng 1. Merge ngoài (carol) chỉ xuất hiện khi xử lý v7, cũng ở tầng 1. Assertion `shas["outer"] in found and shas["inner"] in found` (`:1249-1251`) thỏa vì hai dòng khác nhau, nên comment "kịch bản thật sự đi qua 2 tầng merge" là sai.
- **Kịch bản (đã chạy, `test_probe2.py::test_tc36_depth`)**: các lần gọi `resolve_merge` (depth, orig_line, merge → kết quả) là `[(1, 2, inner → bob_del), (1, 4, inner → …), (1, 6, outer → …)]`, **max depth = 1**. Nếu ai đó làm hỏng `_parent_side` ở `:235-236`, ví dụ trả `c` thay cho gọi đệ quy, TC-36 vẫn pass.
- **Đối chứng (đã chạy, `test_probe2.py::test_prev_nested`, kịch bản của review lần 1)**: dave xóa v3 trên `feat2`, bob merge `feat2` vào `feat`, carol merge `feat` vào main, alice sửa v6 trên main trước bob. Có lần gọi ở **depth 2** (`(2, 3, bob-merge → dave)`); kết quả đúng `deleted_by = {3: dave, 6: alice, 8: bob}`, không cảnh báo. Code đệ quy hiện tại đúng, chỉ thiếu test giữ hành vi.
- **Đề xuất**: đổi fixture TC-36 sang kịch bản ở đối chứng, hoặc bất kỳ kịch bản nào mà `first_commit_after` ở tầng 1 trả merge ngoài cho chính dòng bị xóa trong nhánh lồng. Thêm assertion trực tiếp: spy `_Attributor.resolve_merge`, kiểm có lần gọi `depth == 2` cho đúng dòng v2 với merge trong, rồi mới kiểm `deleted_by`. Sửa comment `:1249`.
- **Tham chiếu**: spec `attribution` 5.6 bước 2.4, §9 TC-36; PLAN D23; spec gốc §16.

### [Minor] PLAN D28 chưa ghi bước (0) — `docs/PLAN.md:225`
- **Mô tả**: Spec 5.7 (đã duyệt lại) có bước (0) "cặp chỉ đổi khoảng trắng", chạy trước (a)/(b). Quyết định D28 trong PLAN vẫn chỉ mô tả (a)/(b). Nguồn quyết định và spec xử lý lệch nhau. Ai đọc D28 để làm `builder` hay review sau có thể coi bước (0) là lệch quyết định.
- **Đề xuất**: cập nhật D28 (hoặc thêm D-mới) ghi bước (0), ngày duyệt, tham chiếu review lần 1.
- **Tham chiếu**: CLAUDE.md quy tắc 2; spec `attribution` §11.

### [Minor] Nhánh phòng thủ D23 / D22 còn chưa có test — `src/loc_counter/attribution.py:221`, `:223`, `:234`, `:324-325`
- **Mô tả**: "dòng sinh sau base → PRESENT" (`:221`), "`fb.sha` không là tổ tiên của P → UNDETERMINED" (`:223`), "`first_commit_after` None → UNDETERMINED" (`:234`), "blame lần 2 ra commit ngoài kỳ → UNATTRIBUTED" (`:324-325`). Không TC nào yêu cầu các nhánh này (lỗ hổng ở spec). Đây là các nhánh quyết định UNATTRIBUTED, tức ảnh hưởng số liệu.
- **Đề xuất**: thêm vào TC-37 (monkeypatch `is_ancestor`/`first_commit_after`, hoặc `commits` thiếu commit chỉ gặp ở blame lần 2).
- **Tham chiếu**: spec `attribution` 5.4 bước 3, 5.6; checklist mục 1.

### [Nit] `hash()` của `FileAttribution` / `PeriodAttribution` vẫn lỗi — `src/loc_counter/attribution.py:48-61`, `:81-90`
- Dataclass `frozen=True` sinh `__hash__` theo trường. `MappingProxyType` không hash được: đã chạy, ra `TypeError: unhashable type: 'dict'`. Nên đặt `eq=True, unsafe_hash=False` kèm `__hash__ = None` tường minh, hoặc ghi trong docstring là không dùng làm khóa dict / set.

### [Nit] `docs/specs/README.md:31` ghi `approved`, spec ghi `implemented`
- Cập nhật bảng trạng thái cho khớp vòng đời spec.

### [Nit] `_split_lines` vẫn riêng — `src/loc_counter/attribution.py:106-112`
- Như lần 1; `builder` nên dùng chung một hàm tách dòng bytes (D8) với attribution để chỉ số hunk khớp nhau.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Có lỗi | Luồng 5.1–5.9 đúng thứ tự (5.4 → 5.5 → 5.7 → 5.8); API khớp §3; `MAX_MERGE_DEPTH = 64`; lệnh git không đổi so với lần 1 (đã đạt). 37/37 TC có test, nhưng TC-36 không kiểm đệ quy (Major) |
| 2. Nghiệp vụ dễ sai | Đạt | Boundary không phải dòng thêm; commit xóa = cũ nhất theo `--ancestry-path`; xóa cả file; author qua `log_commits` + resolver; `added_code` theo C_END, `deleted_code` theo C_START; D22/D28 không còn mâu thuẫn §6 (TC-34, 35). Khóa `_WHITESPACE` khớp `isspace` của `-w` |
| 3. Bảo mật | Đạt | Không nhận token; mọi git qua `GitRepo`; thông báo không chứa lệnh/URL |
| 4. Lỗi & log | Đạt | `GitError` lan ra; WARNING vượt độ sâu / số cờ lệch; DEBUG từng dòng cũ và mới; INFO tổng kết |
| 5. Tái lập & encoding | Đạt | Chỉ mục D28 giữ thứ tự tăng dần (`sorted` trước `_key_index`) nên kết quả như duyệt tuần tự; dict sắp theo chỉ số; sort cảnh báo ổn định; TC-29 chạy 2 lần bằng nhau (`MappingProxyType` so sánh `==` đúng) |
| 6. Windows | Đạt | Không thao tác đường dẫn đĩa; blob từ object; test chạy trên Windows 11 |
| 7. Chất lượng code | Đạt (Nit) | ruff sạch; type hint đủ; docstring đủ; không thêm thư viện (`collections.deque`, `types` là stdlib) |
| 8. Hiệu năng | Đạt (khuyến nghị) | D28 tuyến tính (đo 20 000 × 20 000: 0,1 s); vẫn đọc trọn blob (ghi chú lần 1, để M7) |
| 9. Streamlit | N/A | Module lõi, không có UI |

## Ghi chú cho spec
1. **Bước (0) có thể "lấy" dòng cũ còn sống vốn là cặp của dòng D22** (chưa kiểm chứng trên repo thật, chỉ chạy tổng hợp bằng cách gọi thẳng `_match_moves`). Với `old = [K (x, P xóa), K' (o, còn sống)]`, `new = [K'' (u, boundary sau 2 lần blame), K (n, D22 → Q)]`, cả bốn cùng khóa: bước (0) ghép `u ↔ o`, nên (b) không còn `o` để ghép với `n`. Kết quả `added_by = {n: Q}`, `deleted_by = {x: P}`: P −1, Q +1. Nếu `u` thực chất là dòng P dời đi (mẫu TC-18) còn `o` là dòng Q dời (mẫu TC-17), kết quả mong muốn là P 0 / Q 0. Tổng net và đa tập dòng của bản "mọi user" vẫn đúng; chỉ số liệu chia giữa các user lệch ±1. Điều kiện xảy ra hiếm (trong cùng file, một khối dời + đổi thụt lề và một khối dời khác có dòng trùng khóa). Đề xuất: ghi vào PLAN như rủi ro đã biết của heuristic D28, chưa cần sửa.
2. TC-19 cho TC-34/35 chỉ so **đa tập** dòng theo khóa bỏ khoảng trắng, không so thứ tự. Chấp nhận được: builder §7.3 đặt dòng cũ được giữ trước dòng mới được thêm trong cùng hunk, nên với dòng chỉ đổi khoảng trắng thì thứ tự không trùng C_END được (vd. TC-34 cho ra `work_one()`, `pass`, `if cond:`). Nên ghi hệ quả này vào spec `builder` (bản export theo user có thể đảo thứ tự trong hunk).
3. Spec chưa có TC cho các nhánh `:221`, `:223`, `:234`, `:324-325` (xem Minor).
