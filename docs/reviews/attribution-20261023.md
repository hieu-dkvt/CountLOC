# Review: attribution — 2026-10-23
Kết luận: **FAIL**
Spec: docs/specs/attribution.md (status: implemented)   Files: `src/loc_counter/attribution.py`, `tests/test_attribution.py` (đọc thêm `git_repo.py`, `snapshot.py`, `classifier.py`, `counter.py`, `tests/conftest.py`)

## Bằng chứng tự động
- ruff: `All checks passed!` (src, tests)
- pytest `tests/test_attribution.py`: **46 passed** / 0 failed (60.9 s)
- coverage `loc_counter.attribution`: **97 %** (365 stmt, thiếu 108, 176, 198, 201, 203, 214, 216, 240, 301, 434)
- Script kiểm chứng (thư mục tạm, không thuộc project): `C:\Users\User\AppData\Local\Temp\claude\d--PJ-Tool\cea15fb9-6e82-493f-a3be-ab22515249c0\scratchpad\rv\test_probe.py` (chạy bằng `uv run pytest <file> -s --rootdir <thư mục rv>`, dùng lại `conftest.py` của project), `...\scratchpad\bench.py`.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.1.1 | `by_sha`, `commit_accounts` qua `resolver.resolve` | `attribution.py:483-484`; TC-28 | Đạt |
| 5.1.2 | `diff_tree`, cảnh báo `RENAME_LIMIT` path `""` | `:487-492`; TC-27 | Đạt |
| 5.1.3 | Một lượt `read_blobs`, SHA bỏ trùng, bỏ symlink/gitlink | `:494-500` | Đạt |
| 5.2 | `SideInfo`, `skip` / `whole` / `lines`, `last_touch_by` + UNATTRIBUTED | `:155-164`, `:227-243`; TC-24, TC-25 | Đạt (nhánh UNATTRIBUTED `:240` không có test) |
| 5.3 | Hunk theo 3 trường hợp | `:267-274`; TC-02, 22, 23 | Đạt |
| 5.4 | Blame xuôi `-M -C`, boundary → blame lại không `-M -C` (D22) | `:276-305`; TC-16, 20 | Đạt (nhánh `:301` không có test) |
| 5.5 | Reverse blame, nhóm `(L, fn)`, `first_commit_after`, merge → D23 | `:307-332`; TC-11..14, 22, 33 | Đạt |
| 5.6 | `resolve_merge`, guard neo == P, `merge_bases`, đệ quy, `MAX_MERGE_DEPTH` | `:171-217`; TC-11..15 | Đạt về code; nhánh `:198`, `:201`, `:203`, `:214`, `:216` không có test (đệ quy đã kiểm chứng tay, xem Minor 3) |
| 5.7 | D28 (a) rồi (b) | `:334-365`; TC-17, 18 | Đúng chữ 5.7, **mâu thuẫn §6 / D22** (Major 1, 2) |
| 5.8 | `renamed_by` qua `rev_list` + `paths_exist` (gom 1 lần), RENAME_UNRESOLVED | `:367-389`; TC-05..09 | Đạt |
| 5.8 | UNATTRIBUTED / MOVED_LINES / MULTI_USER_HUNK / SEQUENTIAL_EDIT, định dạng khoảng | `:391-425`; TC-14, 16, 29, 33 | Đạt |
| 5.9.1–2 | `added_code` theo C_END, `deleted_code` theo C_START, cờ thiếu = False | `:428-472`; TC-01, 04, 22, 25, 26 | Đạt (nhánh WARNING `:434` không có test) |
| 5.9.3–4 | `files`, `users` (cả account 0 dòng) | `:439-472`; TC-02, 11 | Đạt |
| 5.9.5–6 | Thứ tự phát cảnh báo + sort ổn định `(path, kind)`; log INFO | `:486-513`; TC-29 | Đạt |
| §6 | Chỉ đổi khoảng trắng → giữ bản C_START, không gán, không cảnh báo | TC-20 chỉ kiểm khi không có dòng xóa cùng khóa | **Không đạt** trong kịch bản Major 1 |
| §7 | Bảng lỗi / thông báo | `:178`, `:240`, `:329`, `:385-388`, `:402`, `:405`, `:415`, `:421` | Đạt (thiếu DEBUG cho dòng mới — Nit 2) |
| TC-01..33 | Mỗi TC có test, docstring bắt đầu bằng ID | 33/33 TC có test; assertion theo giá trị cụ thể | Đạt |

## Phát hiện

### [Major] D28 (a) gán dòng chỉ đổi thụt lề cho người xóa một dòng trùng khóa ở chỗ khác — `src/loc_counter/attribution.py:343-354`
- **Mô tả**: Bước (a) lấy `U` = mọi dòng mới trong hunk vẫn boundary sau 2 lần blame — nhóm này gồm cả dòng **chỉ đổi khoảng trắng/EOL** (D22: “bỏ dòng mới, giữ dòng cũ, không cảnh báo”). `X` lấy từ dòng cũ có `deleted_by` của **mọi hunk trong file**. Chỉ cần một dòng khác có cùng khóa bỏ khoảng trắng (`pass`, `}`, `return`, `else:`, `break`, dòng trống…) bị xóa ở bất kỳ hunk nào, dòng chỉ đổi thụt lề sẽ bị gán cho người xóa đó. Đây đúng là thuật toán 5.7(a), nhưng trái quy tắc §6 của chính spec (“Chỉ đổi khoảng trắng… giữ bản C_START, không cảnh báo (D22). D28 không ghép vì dòng cũ không có người xóa”) và trái D22.
- **Kịch bản lỗi (đã chạy, `test_d28a_false_match`, `test_d28a_rebuild`)**: C_START `m.py` = `def g(): / do_g() / pass / "" / def f(): / work_one() / pass / z = 3`; alice xóa `pass` trong `g`; bob bọc thân `f` trong `if cond:` (thụt lề lại `work_one()`, `pass`).
  - Kết quả: `added_by = {4: bob, 6: alice}`, `moved = {6}`; alice `added_lines=1, added_code=1, deleted_code=1` → `net_code = 0` (đúng phải là −1). Cảnh báo sai `MOVED_LINES` (“dòng mới 7”) và `MULTI_USER_HUNK … alice, bob` cho hunk alice không chạm vào.
  - Export theo §7.3 của alice: `work_one()`, `pass`, **`        pass`** → thừa một dòng `pass` alice không viết. Export “mọi user” dựng bằng builder cũng thừa 1 dòng code so với C_END → kiểm chứng chéo §8.3 lệch (Σ net = +1, thực tế 0).
  - Trường hợp nặng hơn: một người đổi CRLF→LF cả file (mọi dòng mới thành `U`) cộng bất kỳ dòng nào bị xóa trong kỳ → mọi dòng mới trùng khóa với dòng bị xóa (đặc biệt dòng trống, dòng `}`) bị gán cho người xóa.
- **Đề xuất**: Không tự sửa code — spec 5.7 và D28 cần người dùng quyết định (CLAUDE.md quy tắc 2). Hướng đề xuất: trước bước (a), ghép mỗi `u ∈ U` với dòng cũ **còn sống** (`alive`) cùng khóa chưa dùng (đây là cặp “chỉ đổi khoảng trắng”, giữ nguyên D22: không gán); chỉ `u` không ghép được mới đưa vào (a). Cách này giữ được TC-18 (khối bị hoán chỗ không có dòng cũ còn sống trong hunk). Thêm TC cho kịch bản trên (và biến thể CRLF→LF + xóa dòng trống).
- **Tham chiếu**: spec `attribution` §5.7(a), §6 dòng 196; PLAN D22, D28; spec gốc §7.2, §8.2, §8.3.

### [Major] D28 (b) đánh dấu xóa một dòng còn sống khi có dòng trùng nội dung được dời từ file khác vào — `src/loc_counter/attribution.py:356-365`
- **Mô tả**: Bước (b) lấy `O` = dòng cũ còn sống trong hunk (gồm cả dòng chỉ đổi thụt lề) và `N` = dòng D22 (dời từ file khác vào). Một dòng còn sống bị gán `deleted_by` cho người dời nếu trùng khóa với dòng được dời vào, kể cả khi hai dòng không liên quan với nhau.
- **Kịch bản lỗi (đã chạy, `test_d28b_false_match`)**: C_START `a.py` và `b.py` cùng chứa dòng `result_total = compute_the_total_amount(orders, discount_rate)` (thụt 4 dấu cách). carol thụt lề lại dòng đó trong `a.py` (8 dấu cách). bob dời dòng đó từ `b.py` sang cuối `a.py`.
  - Kết quả: `a.py` `deleted_by = {1: bob}` (dòng của carol, vẫn còn ở C_END), `added_by = {4: bob}`; bob `deleted_lines=2, deleted_code=2` (đúng phải là 1).
  - Tái dựng “mọi user” theo §7.3: `a.py` **mất** dòng `result_total…` ở vị trí 2 so với C_END (thiếu 1 dòng code) → vỡ đúng điều bất biến mà D28/TC-19 nhằm bảo vệ.
- **Đề xuất**: Cũng là lỗi ở spec. Chỉ cho dòng còn sống `o` nhận `deleted_by` khi không có dòng mới “chỉ đổi khoảng trắng” nào ghép được với nó (cùng ý với cách sửa Major 1: ghép cặp `alive ↔ U` trước, phần còn lại mới vào (a)/(b)). Thêm TC.
- **Tham chiếu**: spec `attribution` §5.7(b), §6; PLAN D28 (Q35); spec gốc §8.3.

### [Minor] Ghép D28 tốn O(|U|·|X|) và tính lại khóa ở mỗi lần so — `src/loc_counter/attribution.py:347-365`
- **Mô tả**: `next(x for x in removed if x not in used and _key(old_lines[x]) == key)` duyệt lại toàn bộ `removed` và gọi lại `translate` cho mỗi `u`.
- **Kịch bản**: đã đo (`bench.py`) file 8 000 dòng CRLF→LF, 4 000 dòng bị xóa, không dòng nào trùng khóa → **4,1 s** cho riêng `_match_moves`; tăng theo bình phương (khoảng 100 s với 20 000 × 20 000).
- **Đề xuất**: tính khóa trước và dùng `dict[key, deque[index]]` (vẫn lấy chỉ số nhỏ nhất chưa dùng → kết quả không đổi). Có thể để M7, nhưng nên ghi vào PLAN.
- **Tham chiếu**: spec `attribution` §8 (hiệu năng); spec gốc §15.

### [Minor] Thiếu test cho các nhánh D23 và nhánh phòng thủ — `tests/test_attribution.py`
- **Mô tả**: Các dòng không được test nào chạy tới: đệ quy merge lồng nhau `:216`, `c is None` `:214`, criss-cross `len(bases) != 1` `:198`, “dòng sinh sau base → PRESENT” `:201`, `:203`, `whole` không xác định người chạm cuối `:240`, blame lần 2 ra commit ngoài kỳ `:301`, số cờ ≠ số dòng `:434`. Spec không có TC riêng cho các nhánh này (nên coi là lỗ hổng ở spec), nhưng đệ quy D23 là một phần chính của thuật toán.
- **Kiểm chứng**: đã chạy tay `test_nested_merge` (dave xóa v3 trên `feat2` → bob merge `feat2` vào `feat` → carol merge `feat` vào main): kết quả đúng `deleted_by = {3: dave, 6: alice, 8: bob}`, chạy qua `:216`. Code hiện tại đúng, chỉ thiếu test để giữ lại hành vi.
- **Đề xuất**: thêm TC cho merge lồng nhau, criss-cross (`UNDETERMINED` → UNATTRIBUTED), và `whole` khi `commits` thiếu.
- **Tham chiếu**: spec `attribution` §5.6, §9; checklist mục 1.

### [Minor] Commit vắng trong `by_sha` bị coi là “tạo đường dẫn” — `src/loc_counter/attribution.py:375`, `:380-382`
- **Mô tả**: `parents = … if sha in self.by_sha else ()`, nên một commit có trong `rev_list` nhưng thiếu trong `commits` (vi phạm điều kiện đầu vào, như TC-33) được coi là không có parent, tức là “tạo” `new_path`. Vì lấy phần tử cuối, commit đó (có thể chỉ sửa file) đè lên người tạo thật → ra `RENAME_UNRESOLVED` dù đã xác định được người đổi tên.
- **Kịch bản** (suy từ code, chưa chạy): bob rename `a.py → b.py`, sau đó dave sửa `b.py`; truyền `commits` thiếu commit của dave → `renamed_by = None` + cảnh báo, thay vì `bob`.
- **Đề xuất**: bỏ qua (không coi là người tạo) các commit không có trong `by_sha`, hoặc lấy parent qua git. Chỉ ảnh hưởng nhánh phòng thủ.
- **Tham chiếu**: spec `attribution` §5.8 (`by_sha[X]`).

### [Nit] Dataclass `frozen` chứa `dict` có thể sửa — `src/loc_counter/attribution.py:54-55`, `:86`
- `added_by`, `deleted_by`, `commit_accounts` là `dict` → người gọi (builder) sửa được, `hash()` lỗi. Có thể bọc bằng `types.MappingProxyType`.

### [Nit] Không log DEBUG cho dòng mới UNATTRIBUTED — `src/loc_counter/attribution.py:288-289`, `:300-301`
- Spec §7 ghi “DEBUG từng dòng” cho cả dòng mới lẫn dòng cũ; hiện chỉ dòng cũ có log (`:329`).

### [Nit] Thiếu docstring ở method nội bộ — `src/loc_counter/attribution.py:155`, `:166`, `:190`, `:220`
- `side`, `_is_merge`, `_parent_side`, `attribute_file` chưa có docstring (CLAUDE.md quy tắc 4).

### [Nit] `_split_lines` riêng, không dùng chung — `src/loc_counter/attribution.py:103-109`
- Ngữ nghĩa giống D8 và `classifier.split_lines` (bản bytes), nhưng test lặp lại một bản khác (`split_lines_bytes`). Builder (M4) nên dùng chung một hàm để khỏi lệch chỉ số.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Có lỗi | Luồng 5.1–5.9 đúng thứ tự, API khớp §3, mặc định `MAX_MERGE_DEPTH=64`. Lệnh git đúng §7.2 (`-w -M -C --line-porcelain`, `--reverse`, `--ancestry-path`, `diff -M`). Có 33/33 TC. Mâu thuẫn §6/D22 ↔ §5.7 (Major 1, 2) |
| 2. Nghiệp vụ dễ sai | Có lỗi | Boundary không phải dòng thêm; commit xóa = cũ nhất theo `--ancestry-path`; xóa cả file; author qua `log_commits` + resolver; `added_code` theo C_END, `deleted_code` theo C_START (D31 theo từng phía). D28 ghép sai (Major 1, 2) |
| 3. Bảo mật | Đạt | Không nhận token; mọi git qua `GitRepo` (list tham số, `--`, `--literal-pathspecs`); thông báo không chứa lệnh/URL |
| 4. Lỗi & log | Đạt (Nit) | `GitError` lan ra; WARNING cho vượt độ sâu và số cờ lệch; INFO tổng kết; thiếu DEBUG dòng mới |
| 5. Tái lập & encoding | Đạt | Thứ tự theo `diff_tree`, dict theo chỉ số tăng dần, sort cảnh báo ổn định; TC-29 chạy 2 lần cho kết quả bằng nhau; TC-30 cấu hình global gây nhiễu; `decode_text` UTF-8 → latin-1 |
| 6. Windows | Đạt | Không thao tác đường dẫn đĩa; đường dẫn POSIX từ git (`-z`); blob đọc từ object (không phụ thuộc autocrlf); test chạy trên Windows 11 |
| 7. Chất lượng code | Đạt (Nit) | ruff sạch; type hint đủ; không thêm thư viện; không TODO |
| 8. Hiệu năng | Khuyến nghị | Đọc blob qua `cat-file --batch`, classifier có cache; ghép D28 bậc hai (Minor); D23 gọi blame theo từng dòng (spec cho phép, để M7) |
| 9. Streamlit | N/A | Module lõi, không có UI |

## Ghi chú cho spec
1. **Mâu thuẫn D22 ↔ D28 (cần người dùng quyết định)**: §6 dòng 196 khẳng định “D28 không ghép vì dòng cũ không có người xóa”. Điều này sai: `X` (5.7a) gom dòng bị xóa của mọi hunk trong file, và `O` (5.7b) gồm cả dòng chỉ đổi khoảng trắng. Đề xuất: thêm bước (0) “ghép `U ↔ alive` cùng khóa = cặp chỉ đổi khoảng trắng, không gán”; chỉ phần còn lại mới đi vào (a)/(b). Thêm TC cho 2 kịch bản ở Major 1, 2. Cần kiểm lại TC-17/18/19 sau khi đổi.
2. Spec chưa có TC cho: merge lồng nhau (đệ quy D23), criss-cross (`len(bases) != 1`), `whole` không xác định người chạm cuối, số cờ phân loại ≠ số dòng.
3. `UserLineStats.files` gồm cả file không phải source (`notes.txt` ở chế độ `full`, binary `whole`), trong khi §8.2 định nghĩa `files_changed` = số file **source**. M5 cần lọc lại; nên ghi rõ trong spec `attribution` hoặc spec pipeline.
4. 5.1.3 đọc trọn mọi blob (kể cả binary/file quá lớn chỉ cần `size` và vài byte đầu) vào bộ nhớ trong suốt hàm → file asset vài trăm MB làm tốn RAM. Nên cân nhắc ở M7 (dùng kích thước từ `ls-tree -l` / `cat-file --batch-check`, chỉ đọc đầu blob cho `is_binary`).
