# Review: git_repo + snapshot (M4), lần 2 — 2026-10-23
Kết luận: **PASS_WITH_NOTES**
Spec: docs/specs/git_repo.md (status: implemented), docs/specs/snapshot.md (status: implemented)
Files: src/loc_counter/git_repo.py, src/loc_counter/snapshot.py, tests/test_git_repo.py, tests/test_snapshot.py (+ tests/conftest.py)
Phạm vi: kiểm lại các phát hiện của reviews/git_repo-snapshot-20261023.md (Major 1, 2; Minor 1–3; Nit 1–2), phần spec sửa theo review (git_repo §5.1, §5.9, §5.16, §7, TC-37/44/47/49/50; snapshot §5.8, TC-32, A7), rồi đọc lại toàn bộ hai module và test để tìm hồi quy.

## Bằng chứng tự động
- ruff: `All checks passed!`
- pytest (`tests/test_git_repo.py tests/test_snapshot.py`): **190 passed**, 0 failed (96 s). Toàn bộ suite: **368 passed** (128 s).
- coverage: `git_repo.py` 97% (thiếu 186, 234-235, 261, 286-287, 420-422, 466, 501-502, 516, 519, **564-566**, 595-596); `snapshot.py` 100%. Các nhánh lỗi M4 mà lần 1 báo thiếu (:636, :699, :740, :781-792 cũ) giờ đã có test. Nhánh duy nhất của M4 còn thiếu là 564-566 (Minor 2).
- Kiểm chứng thủ công (script `scratchpad/r2/leak.py`, Popen giả):
  - `read_blobs` với tiến trình trả mã 128 ném GitError đúng, nhưng sau đó `stdout.closed == False` và `stderr.closed == False` (Minor 1).
  - `write_entries(repo, [])` và `write_entries` chỉ có entry `data` vẫn chạy 2 tiến trình `cat-file --batch` (Nit 1).

## Kiểm lại phát hiện lần 1
| Phát hiện lần 1 | Sửa | Kiểm chứng | Đạt |
|---|---|---|---|
| Major 1: `GIT_DIFF_OPTS` làm sai hunk `-U0` | `_env()` bỏ `GIT_DIFF_OPTS` và `GIT_EXTERNAL_DIFF` (git_repo.py:338-339); spec §5.1 bước 2 | `test_diff_hunks_ignores_diff_env` đặt `GIT_DIFF_OPTS=--unified=5`, so với `HUNK_CLEAN` (nếu không sửa, các hunk gần nhau bị gộp nên test sẽ fail), và kiểm env truyền cho git không chứa hai biến | Đạt |
| Major 2: gitlink trong `paths_exist` gây GitError | `<sha40> submodule` → True (:792-795); path có `\n`/`\r` tra bằng `rev-parse --verify --quiet` (:801-806) | `test_paths_exist_gitlinks`: gitlink trỏ tới commit có trong repo, gitlink trỏ tới commit không có, gitlink có `\n` trong tên, cùng lô với file thường và path missing → `[True, True, False, True, True, False, True]` | Đạt |
| Minor 1: path kết thúc `\r` | Path chứa `\r` không đưa vào batch (:781) | `test_paths_exist_newline_cr_path`: `cr.py\r` → True, `cr.py` → False, stdin của batch không có `\r`, không dùng `cat-file -e` | Đạt |
| Minor 2: đọc thiếu byte / không kiểm mã thoát | `len(data) != size` → GitError (:552-555); `write_entries` gọi `next(blobs, None)` (snapshot.py:273) | TC-git_repo-50 (`_ShortReadProcess`); TC-snapshot-32 (generator giả, kiểm `finished=True`, không còn zip/`.tmp`). Nếu bỏ `next(blobs, None)`, generator chỉ bị `close()` và TC-32 sẽ fail | Đạt (xem Minor 1, 2 mới) |
| Minor 3: nhánh lỗi M4 chưa test | TC-44 (truncated, khoảng rỗng), TC-47 (thiếu/thừa dòng, dòng lạ, `ambiguous`), TC-49 (meta thiếu trường, `R` thiếu path) | coverage | Đạt |
| Nit 1: TC-45 thiếu đối chứng | test_git_repo.py:1139 `rev_list(c4, f1, ["x.py"]) == [c3]` | — | Đạt |
| Nit 2: kiểu `dict` trong `_parse_blame` | Chưa sửa (git_repo.py:724) | — | Còn (Nit 3) |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| git_repo 5.1 bước 2 | Bỏ `GIT_DIFF_OPTS`, `GIT_EXTERNAL_DIFF` | git_repo.py:338-339; TC-37 (`test_diff_hunks_ignores_diff_env`) | Đạt |
| git_repo 5.9 | Đọc thiếu byte → WARNING + GitError `Không đọc được blob`; mã thoát ≠ 0 → GitError; đóng sớm → kill | :551-555, :560-571; TC-50 | Đạt. Nhánh mã ≠ 0 không có test (Minor 2), pipe không đóng khi ném lỗi (Minor 1) |
| git_repo 5.11–5.15 | Không đổi so với lần 1 | :603-772; TC-33..46, 48 | Đạt |
| git_repo 5.16 bước 1 | Batch chỉ gồm path không chứa `\n`/`\r` | :781-783; TC-47 | Đạt |
| git_repo 5.16 bước 2 | 3 trường + SHA → True; `<sha40> submodule` → True; ` missing` → False; khác hoặc sai số dòng → GitError | :787-800; TC-47 (4 tham số lỗi) | Đạt |
| git_repo 5.16 bước 3 | `rev-parse --verify --quiet <commit>:<path>`, `allow_fail`, mã 0 → True | :801-806; TC-47 kiểm argv | Đạt |
| git_repo 5.16 bước 4 | Giữ thứ tự; `[]` không chạy git | :779, :807; TC-47 spy | Đạt |
| git_repo 7 | Thêm dòng `read_blobs` đọc thiếu byte | :553-555 | Đạt |
| snapshot 5.8 bước 3 | Một generator `read_blobs`, `closing`, đọc tới hết bằng `next(blobs, None)`; lỗi → GitError, không tạo zip | snapshot.py:263-273; TC-30, TC-32 | Đạt (Nit 2: không kiểm giá trị trả về là `None`) |
| snapshot 5.3, 5.4, 5.7, 5.9 | Không đổi so với lần 1 | :148-233, :285-301; TC-01..31 | Đạt |
| TC git_repo-37, 44, 47, 49, 50 | Các ca mới thêm trong spec | test_git_repo.py:814, 1086-1112, 1197-1277, 1323-1349, 1380 | Đạt (assertion theo giá trị cụ thể) |
| TC snapshot-32 | Generator giả, lỗi ở bước kết thúc | test_snapshot.py:822 | Đạt |

## Phát hiện

### [Minor] 1. `read_blobs` không đóng pipe khi `cat-file` thoát với mã ≠ 0 — `src/loc_counter/git_repo.py:563-566` (so với :572-574)
- **Mô tả:** Trong nhánh `finished`, `raise GitError(...)` ở :566 chạy trước `proc.stdout.close()` và `proc.stderr.close()` (:572-574), nên hai pipe chỉ được đóng khi GC thu gom (kèm `ResourceWarning`). Nhánh này chính là nhánh mà sửa đổi `next(blobs, None)` (snapshot.py:273) nay mới đi tới.
- **Kịch bản (đã chạy, Popen giả trả mã 128):** `list(repo.read_blobs([sha]))` ném `GitError("Lệnh git thất bại: fatal: boom")`, nhưng sau đó `p.stdout.closed == False` và `p.stderr.closed == False`. Trên Windows, handle pipe còn mở chừng nào traceback còn được giữ (ví dụ trong UI, khi hiển thị lỗi).
- **Đề xuất:** đưa phần đóng `stdout`/`stderr` vào `try/finally` lồng bên trong, hoặc tính lỗi trước rồi đóng pipe, sau đó mới `raise`.
- **Tham chiếu:** git_repo §5.9; checklist 6 ("không giữ handle file mở").

### [Minor] 2. Nhánh "mã thoát ≠ 0" của `read_blobs` thật chưa có test — `src/loc_counter/git_repo.py:564-566`
- **Mô tả:** TC-snapshot-32 dùng generator giả thay cho `read_blobs`, còn TC-git_repo-50 chỉ kiểm việc đọc thiếu byte. Vì vậy đoạn code thật kiểm `proc.wait() != 0`, che token trong stderr, log WARNING rồi ném GitError chưa có test nào chạy qua (coverage báo thiếu 564-566). Spec §9 cũng không có TC cho trường hợp này.
- **Đề xuất:** thêm vào spec một TC (hoặc thêm ca vào TC-50): `Popen` giả trả đủ blob, `wait()` trả 128, stderr chứa token. Kết quả mong đợi: GitError có thông báo theo bảng mục 7, stderr đã che token, có WARNING trong caplog, và pipe đã đóng (kiểm luôn Minor 1).
- **Tham chiếu:** git_repo §5.9, §7, §9.

### [Nit] 1. `write_entries` luôn chạy `git cat-file --batch`, kể cả khi không có entry blob — `src/loc_counter/snapshot.py:263, 273`
- Generator chỉ bắt đầu chạy ở lần `next` đầu tiên. Trước bản sửa, zip không có blob không chạy tiến trình nào. Nay `next(blobs, None)` khởi động tiến trình với danh sách rỗng. Điều này xảy ra ở zip start khi C_START rỗng và ở zip end của `builder` khi mọi entry là `data`. Đã kiểm chứng: 2 lời gọi `write_entries` không có blob tạo 2 tiến trình. Kết quả vẫn đúng, chỉ tốn một lần spawn mỗi zip. Có thể bỏ qua bước đọc tới hết khi danh sách SHA rỗng.

### [Nit] 2. Không kiểm giá trị trả về của `next(blobs, None)` — `src/loc_counter/snapshot.py:273`
- Spec §5.8 ghi "`next(blobs, None)` phải trả `None`". Code bỏ qua giá trị này. Với cách gọi hiện tại thì không thể có phần tử thừa, nhưng một assertion hoặc `ValueError` sẽ giữ đúng chữ của spec và bắt được lỗi lập trình nếu sau này đổi cách dựng danh sách SHA.

### [Nit] 3. (còn từ lần 1) `current: dict | None` và helper private thiếu docstring — `src/loc_counter/git_repo.py:724`, `_env`, `_command`, `_mask`, `_exec`, `_clone`, `_update_head`, `_header_b64`

### [Nit] 4. Spec git_repo có ký tự CR thô trong bảng lịch sử — `docs/specs/git_repo.md:457`
- Đoạn "path chứa `` tra riêng" thực ra chứa byte `\r` giữa hai dấu backtick (đã xem bằng `od -c`). Khi hiển thị, đoạn này thành code span rỗng, và file có dòng kết thúc lẫn lộn. Nên viết `` `\r` `` bằng ký tự thường. Dòng này cũng thiếu dấu `|` ở cuối.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Mọi bước 5.1/5.9/5.16 (git_repo) và 5.8 (snapshot) đã sửa đều khớp code. Chữ ký API công khai không đổi. Lệnh git đúng spec (`diff-tree -M -l0`, `diff -U0 …`, `blame --line-porcelain -w -M -C` / `--reverse`, `rev-list --ancestry-path --reverse`). Mọi TC có test với assertion cụ thể. |
| 2. Nghiệp vụ dễ sai | Đạt | Hunk nay không phụ thuộc môi trường. Boundary, `--root`, reverse blame theo rename, commit cũ nhất của `--ancestry-path` không đổi. Classifier, builder, attribution: N/A (ngoài phạm vi). |
| 3. Bảo mật | Đạt | `_env` vẫn che token. `rev-parse` nhận `<sha>:<path>` (bắt đầu bằng SHA đã kiểm 40 hex, nên không thể thành option). Không `shell=True`. Path trong `<rev>:<path>` là literal (git không phân tích hậu tố `^{}` sau dấu `:`). |
| 4. Lỗi & log | Đạt một phần | Thông báo tiếng Việt, có WARNING. Pipe không được đóng khi `cat-file` lỗi (Minor 1). |
| 5. Tái lập & encoding | Đạt | Zip sắp theo path, timestamp cố định, bytes gốc. Hunk độc lập với `GIT_DIFF_OPTS`. |
| 6. Windows | Đạt một phần | Biến môi trường trên Windows đã được Python viết hoa nên `pop("GIT_DIFF_OPTS")` có tác dụng. Handle pipe bị giữ khi lỗi (Minor 1). |
| 7. Chất lượng code | Đạt | ruff sạch, không có thư viện mới, ranh giới module đúng (`snapshot` không gọi git trực tiếp). Nit 3. |
| 8. Hiệu năng | Đạt (khuyến nghị) | `paths_exist`: mỗi path chứa `\n`/`\r` cần một tiến trình riêng (hiếm gặp). Có một lần spawn thừa cho zip không có blob (Nit 1). |
| 9. Streamlit | N/A | Không có màn hình trong phạm vi. |

## Ghi chú cho spec
1. **git_repo §5.16 — path là thư mục:** `paths_exist` trả `True` khi `<commit>:<path>` là **tree** (`cat-file` cho `<sha> tree <n>`, `rev-parse` cũng thành công). Khi `attribution` (§7.4) hỏi "file cũ còn tồn tại ở C_END không", trường hợp file `foo` được thay bằng thư mục `foo/` sẽ cho `True`. Cần chốt: "tồn tại" nghĩa là có entry bất kỳ (hiện tại), hay chỉ blob/gitlink. Nếu chỉ blob/gitlink thì sửa bước 2 thành: `tree` → `False`. Không phải lỗi so với spec hiện tại.
2. **git_repo §9:** thêm TC cho `read_blobs` khi tiến trình thoát mã ≠ 0 (xem Minor 2).
3. Ghi chú 3 của lần 1 (`is_unsafe_path` với các trường hợp đặc thù Windows trước M5) vẫn còn mở và nằm ngoài phạm vi bản sửa này.
