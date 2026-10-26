# Review: attribution (lần 3, xác nhận sửa theo r2) — 2026-10-23
Kết luận: **PASS**
Spec: docs/specs/attribution.md (status: implemented)   Files: `src/loc_counter/attribution.py` (không đổi kể từ r2, mtime 22:11 < r2 22:32), `tests/test_attribution.py`, `docs/PLAN.md` (D28, mục 5 Rủi ro), `docs/specs/README.md`, `docs/test-reports/M4-attribution-20261023.md`

## Bằng chứng tự động
- ruff: `All checks passed!` (src, tests)
- pytest `tests/test_attribution.py`: **58 passed** / 0 failed (74 s); toàn bộ `uv run pytest -q`: **436 passed** (201 s)
- coverage `loc_counter.attribution`: **99 %** (379 stmt, chỉ thiếu `111`: `_split_lines` với dòng cuối không có `\n`)
- Kiểm thử đột biến (mutation), bản sao ngoài project `C:\Users\User\AppData\Local\Temp\claude\d--PJ-Tool\cea15fb9-6e82-493f-a3be-ab22515249c0\scratchpad\rv3\m1..m8`, chạy bằng `PYTHONPATH=<mutant>/src uv run pytest <mutant>/tests/test_attribution.py --rootdir <mutant>` (đã xác nhận `loc_counter.attribution.__file__` trỏ tới bản đột biến):

| Mutant | Thay đổi | Test bắt được |
|---|---|---|
| m1 | `:236` đệ quy → `return c` | TC-36 fail (`(2, inner)` không có trong `depths`) |
| m2 | `:221` dòng sinh sau base → `_UNDETERMINED` | TC-37 (e) `test_defensive_parent_side_branches` fail |
| m3 | `:223` `fb` không phải tổ tiên → `_PRESENT` | TC-37 (e) fail |
| m4 | `:234` `first_commit_after` None → `_PRESENT` | TC-37 (e) fail |
| m5 | `:194` bỏ memo | TC-37 (e) `test_defensive_resolve_merge_memo` fail (TypeError) |
| m6 | `:325` bỏ `unattr_new.add` ở blame lần 2 | TC-37 (e) `test_defensive_second_blame_outside_period` fail |
| m7 | `:236` truyền `anchor` cũ thay cho `(r.sha, r.filename, r.orig_line)` | **sống** (xem Nit 1) |
| m8 | `:236` `depth + 1` → `depth` | TC-36 fail |

## Trạng thái phát hiện của review lần 2
| Phát hiện r2 | Đã sửa? | Bằng chứng |
|---|---|---|
| Major — TC-36 không chạy tới đệ quy D23 | **Đã sửa** | Fixture mới `tests/test_attribution.py:1193-1220` (bob xóa v2 trên `feat2` → dave merge vào `feat` → carol merge vào main, alice sửa v7 trước). Spy `resolve_merge` `:1238-1248` kiểm `(1, outer)` và `(2, inner)`. Coverage `:236` đã có; m1, m8 bị bắt |
| Minor — PLAN D28 chưa ghi bước (0) | **Đã sửa** | `docs/PLAN.md:225` có "(0) … cặp chỉ đổi khoảng trắng, không gán — sửa theo review attribution", đúng thứ tự (0) → (a) → (b) như spec 5.7 |
| Minor — nhánh phòng thủ `:221, :223, :234, :324-325` chưa có test | **Đã sửa** | TC-37 (e) `:1434-1480` dùng `FakeRepo`; spec TC-37 thêm (e) (`attribution.md:270`); m2–m6 bị bắt |
| Nit — `hash()` của dataclass frozen chứa `MappingProxyType` lỗi | Chưa | Source không đổi; giữ Nit (dưới) |
| Nit — `docs/specs/README.md:31` lệch trạng thái | **Đã sửa** | README ghi `implemented`, khớp spec |
| Nit — `_split_lines` riêng | Chưa (để builder) | `:104-111` |
| Ghi chú spec 1 — rủi ro D28 bước (0) chia lệch ±1 | **Đã ghi** | `docs/PLAN.md:241` (mục Rủi ro, theo dõi qua §8.3 ở M5) |
| Ghi chú spec 2 — §7.3 với dòng chỉ đổi khoảng trắng | **Đã ghi** | `docs/PLAN.md:242`, yêu cầu ghi vào spec `builder` |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.1–5.5 | Như r2 (code không đổi) | `attribution.py` không đổi; test cũ vẫn pass | Đạt |
| 5.6 bước 1 | `depth > MAX_MERGE_DEPTH` → UNDETERMINED + WARNING | `:196-199`; TC-15 | Đạt |
| 5.6 bước 2.1 | neo theo `is_ancestor` / `merge_bases`; `len != 1` → UNDETERMINED; `fb` không boundary → PRESENT; `fb` không là tổ tiên → UNDETERMINED | `:212-224`; TC-37 (a), (e) | Đạt |
| 5.6 bước 2.2–2.3 | neo == P → PRESENT; reverse blame `r.sha == P` → PRESENT | `:225-231`; TC-11..14 | Đạt |
| 5.6 bước 2.4 | `first_commit_after` None → UNDETERMINED; merge → đệ quy `depth + 1` với neo mới | `:232-237`; TC-36 (độ sâu 2), TC-37 (e) | Đạt (neo mới chưa được test phân biệt — Nit 1) |
| 5.6 memo | Theo `(S, path, j, M)` | `:192-195`, `:206`; TC-37 (e) | Đạt |
| 5.4 bước 3 | Blame lần 2 ra commit ngoài kỳ → UNATTRIBUTED + DEBUG | `:322-325`; TC-37 (e) | Đạt |
| 5.7 (0)/(a)/(b) | Thứ tự và khóa như spec; PLAN D28 khớp | `:368-392`; TC-17, 18, 34, 35; `PLAN.md:225` | Đạt |
| §9 TC-36 | v2 → bob, v7 → alice; carol, dave 0 dòng; spy độ sâu 1 (outer), 2 (inner) | `test_nested_merge` `:1223-1262` kiểm `deleted_by[2] == B`, `deleted_by[7] == A`, `added_by[6] == A`, C/D 0 dòng, `files == ()`, `depths` | Đạt |
| §9 TC-37 (a)–(e) | Mỗi nhánh có test, docstring bắt đầu bằng ID | `:1265`, `:1289`, `:1329`, `:1367`, `:1434`, `:1454`, `:1466` | Đạt |
| TC-01..37 | Truy vết docstring | 37/37 TC, 58 test | Đạt |
| §11 Lịch sử | Ghi lần sửa theo r2 | `attribution.md:296` ("chỉ đổi test") | Đạt |

## Phát hiện
Không có Blocker, Major hay Minor.

### [Nit] TC-36 không phân biệt neo truyền vào đệ quy — `tests/test_attribution.py:1238-1248` (code `src/loc_counter/attribution.py:236`)
- **Mô tả**: spy chỉ ghi `(depth, merge)`. Mutant m7 (đệ quy với `anchor` gốc `(C_START, app.py, 2)` thay cho `(r.sha, r.filename, r.orig_line)` như spec 5.6 bước 2.4) vẫn pass TC-36. Trong fixture này C_START là tổ tiên của mọi parent và file không đổi tên, nên hai neo cho cùng kết quả.
- **Kịch bản**: hai neo chỉ cho kết quả khác nhau khi `app.py` bị đổi tên trên nhánh trước merge trong, hoặc khi phải tìm neo qua merge-base. Chưa dựng repo kiểm chứng trường hợp này; code hiện tại đúng spec.
- **Đề xuất**: ghi thêm `anchor` trong `resolve_spy` và kiểm lần gọi `depth == 2` có `anchor[0] != ctx.snaps.c_start.sha` (neo là commit `r.sha` trên nhánh). Không bắt buộc.

### [Nit] Helper test thiếu docstring, có dòng trống thừa, type hint lệch — `tests/test_attribution.py:1396`, `:1422-1424`
- `_attributor` không có docstring và có hai dòng trống ngay sau dòng `def` (ruff mặc định không bắt E303). `FakeRepo.__init__` khai báo `ancestors: set[tuple[str, str]] = frozenset()`, tức kiểu khai báo là `set` nhưng mặc định là `frozenset`; nên khai báo `AbstractSet[...]` hoặc dùng `None`.

### [Nit] `hash()` của `FileAttribution` / `PeriodAttribution` vẫn lỗi — `src/loc_counter/attribution.py:48-61`, `:81-90`
- Giữ nguyên như r2: `frozen=True` sinh `__hash__`, nhưng trường `MappingProxyType` không hash được. Nên đặt `__hash__ = None` tường minh hoặc ghi vào docstring.

### [Nit] `_split_lines` vẫn riêng và nhánh dòng cuối không EOL chưa có test — `src/loc_counter/attribution.py:104-111`
- Dòng `111` là dòng duy nhất chưa có test. Đây là trường hợp phổ biến (file không có `\n` cuối) nhưng khóa D28 bỏ `\n`, nên không ảnh hưởng ghép. Khi làm `builder`, nên dùng chung một hàm tách dòng (D8) và thêm test cho dòng cuối không EOL.

### [Nit] PLAN D28 bước (0) mô tả `U` chưa đủ chặt — `docs/PLAN.md:225`
- PLAN ghi "dòng mới chưa có tác giả", còn spec 5.7 ghi rõ "chưa có `added_by` **và không UNATTRIBUTED**". Spec là nguồn chi tiết và code theo spec, nên đây chỉ là lệch câu chữ.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Luồng 5.1–5.9 không đổi so với r2 (đã đạt); 37/37 TC có test và test kiểm đúng điều TC mô tả (TC-36 kiểm đệ quy thật, TC-37 (e) phủ hết nhánh phòng thủ, xác nhận bằng mutation m1–m6, m8) |
| 2. Nghiệp vụ dễ sai | Đạt | D23 đệ quy cho đúng kết quả §16 (carol, dave 0 dòng); boundary, commit xóa, `added_code`/`deleted_code` như r2 |
| 3. Bảo mật | Đạt | Không đổi; module không nhận token; `FakeRepo` không gọi git |
| 4. Lỗi & log | Đạt | WARNING vượt độ sâu, DEBUG UNATTRIBUTED blame lần 2 (`:324`) |
| 5. Tái lập & encoding | Đạt | Không đổi; TC-29 pass |
| 6. Windows | Đạt | Toàn bộ 436 test chạy trên Windows 11 |
| 7. Chất lượng code | Đạt (Nit) | ruff sạch; Nit helper test, `hash()` |
| 8. Hiệu năng | Đạt | Không đổi (D28 tuyến tính, đo ở r2) |
| 9. Streamlit | N/A | Module lõi, không có UI |

## Ghi chú cho spec
1. Lần sửa r2 đổi bảng TC (TC-36 thêm kỳ vọng spy, TC-37 thêm (e)) mà vẫn giữ `implemented`, không quay lại `draft`. Cách này hợp lệ theo `docs/specs/README.md:17`, vì quy tắc quay lại `draft` chỉ áp khi sửa **hành vi**, và lịch sử `:296` đã ghi "chỉ đổi test". Mục Lịch sử chưa có dòng "Test pass (58 test)" cho lần 3; báo cáo test `M4-attribution-20261023.md` (Lần 3) đã ghi. Nên thêm dòng đó, rồi chuyển `status: reviewed` theo kết luận này.
2. Rủi ro D28 bước (0) (chia lệch ±1 giữa user) và hệ quả §7.3 với dòng chỉ đổi khoảng trắng đã ghi ở PLAN mục 5. Cần chuyển hai điểm này vào spec `builder` khi viết, và thêm vào tiêu chí kiểm tra chéo §8.3 ở M5.
