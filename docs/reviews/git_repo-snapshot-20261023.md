# Review: git_repo + snapshot (M4) — 2026-10-23
Kết luận: **FAIL**
Spec: docs/specs/git_repo.md (status: implemented), docs/specs/snapshot.md (status: implemented)
Files: src/loc_counter/git_repo.py, src/loc_counter/snapshot.py, tests/test_git_repo.py, tests/test_snapshot.py (+ tests/conftest.py)
Trọng tâm: phần M4 (git_repo §5.11–5.16, TC-33..49; snapshot §5.7–5.9, TC-25..31). Phần M2/M3 được đọc lại toàn bộ, không thấy hồi quy.

## Bằng chứng tự động
- ruff: `All checks passed!`
- pytest (`tests/test_git_repo.py tests/test_snapshot.py`): **175 passed**, 0 failed (83 s)
- coverage: `git_repo.py` 95% (thiếu 186, 234-235, 261, 286-287, 418-420, 464, 499-500, 514, 517, 558-560, 589-590, 636, 699, 740, 781-783, 791-792); `snapshot.py` 100%
- Kiểm chứng thủ công (git 2.55.0.windows.5, script trong scratchpad): `GIT_DIFF_OPTS` làm sai `diff_hunks`; `cat-file --batch-check` trả `<sha> submodule` cho gitlink và bỏ `\r` cuối dòng; `diff-tree -l1` in cảnh báo rename limit, `-l0` nhận đủ rename.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| git_repo 5.11 | SHA 40 hex → ValueError, không gọi git | `_check_sha` git_repo.py:250; TC-48 `test_m4_invalid_sha` | Đạt |
| git_repo 5.11 | `-c diff.algorithm=myers -c diff.indentHeuristic=true` trước `diff`/`blame` | `_DIFF_OPTS` :53, dùng :662, :690; TC-37, TC-43 | Đạt (nhưng xem Major 1: biến môi trường) |
| git_repo 5.12 | `diff-tree -r -z --raw --no-abbrev -M -l0`; parse; `C`/`U`/`X` → GitError; rename limit qua stderr; sắp `(path, old_path)` | :597-655; TC-33, 34, 35, 49 | Đạt |
| git_repo 5.13 | `diff -U0 --inter-hunk-context=0 … --text --no-renames`, đổi 0-based | :657-675; TC-36, 37 | **Không đạt khi có `GIT_DIFF_OPTS`** (Major 1) |
| git_repo 5.14 | blame `--line-porcelain --root --no-ignore-revs-file --no-textconv -w`, `-M -C`/`--reverse`, `-L` gộp + lô 200, parse, bỏ C-quote | :677-741, `_merge_ranges` :291, `_unquote_c` :265; TC-38..44 | Đạt |
| git_repo 5.15 | `--literal-pathspecs rev-list --topo-order [--ancestry-path] [--reverse]`; `first_commit_after` lấy phần tử đầu | :743-766; TC-45, 46 | Đạt |
| git_repo 5.16 | `cat-file --batch-check`; path có `\n` → `cat-file -e`; `[]` không chạy git | :768-797; TC-47 | **Không đạt với gitlink** (Major 2), sai với path kết thúc `\r` (Minor 1) |
| git_repo 7 | Thông báo lỗi M4 tiếng Việt, log WARNING | `fail()` :623, :713, :781, :791; TC-44, 49 | Đạt |
| snapshot 5.7 | `screen_entry` / `finish_entry` / `select_content` tách nguyên văn bước 5.3.3–5.3.4 | snapshot.py:148-201; TC-25, 26, 27 | Đạt (đã đối chiếu từng dòng bảng 5.3) |
| snapshot 5.3 | `plan_export` gọi lại hai hàm, đọc blob một lượt, mỗi SHA một lần | :204-233; TC-26 | Đạt |
| snapshot 5.8 | `write_entries`: kiểm đầu vào trước khi tạo file, sắp theo path, `.tmp` + `os.replace`, một generator `read_blobs` đóng bằng `closing` | :246-281; TC-28, 29, 30 | Đạt (xem Minor 2) |
| snapshot 5.4 | `write_zip` = `write_entries` | :284-287; TC-28 `test_write_zip_same_as_write_entries`, TC-15/16/22/24 | Đạt |
| snapshot 5.9 | `zip_timestamp` | :290-292; TC-31 | Đạt |
| TC git_repo-33..49 | Có test, assertion theo giá trị cụ thể | 18 hàm test | Đạt (TC-45 thiếu một assertion — Nit 1) |
| TC snapshot-25..31 | Có test | 13 hàm/tham số hóa | Đạt |

## Phát hiện

### [Major] 1. `diff_hunks` phụ thuộc biến môi trường `GIT_DIFF_OPTS` — hunk sai, `-U0` bị ghi đè — `src/loc_counter/git_repo.py:332-344` (`_env`), `:662-665` (`diff_hunks`)
- **Mô tả:** Theo tài liệu git, `GIT_DIFF_OPTS=--unified=N` "có ưu tiên cao hơn mọi `-U`/`--unified` truyền trên dòng lệnh". `_env()` sao chép nguyên `os.environ`, chỉ ghi đè `GIT_TERMINAL_PROMPT`, `GIT_ASKPASS`, `SSH_ASKPASS`, `LC_ALL`. Vì vậy `-U0` trong `diff_hunks` không còn đúng, hunk gồm cả dòng ngữ cảnh, và các hunk gần nhau bị gộp lại.
- **Kịch bản lỗi (đã chạy):** blob cũ `a\nb\nc\nd\ne\nf\ng\nh\n`, blob mới đổi dòng 2 và 7.
  - Môi trường sạch: `[Hunk(1,1,1,1), Hunk(6,1,6,1)]` (đúng).
  - `GIT_DIFF_OPTS=--unified=3`: `[Hunk(0,8,0,8)]`, tức cả 8 dòng bị coi là đã sửa. `attribution` (D24) sẽ tính 6 dòng không đổi thành dòng thêm/xóa, nên số liệu `added_*`/`deleted_*` bị sai.
- **Vì sao test không bắt được:** TC-37 chỉ thử cấu hình qua `GIT_CONFIG_GLOBAL`, không thử biến môi trường. Fixture cô lập trong conftest cũng không xóa `GIT_DIFF_OPTS`.
- **Đề xuất sửa:** trong `_env()`, xóa `GIT_DIFF_OPTS` (và để phòng xa cả `GIT_EXTERNAL_DIFF`, dù đã có `--no-ext-diff`). Ghi bước này vào spec git_repo §5.1 bước 2. Thêm vào TC-37 một ca `monkeypatch.setenv("GIT_DIFF_OPTS", "--unified=5")` với kết quả phải bằng `clean`.
- **Tham chiếu:** git_repo §5.13 ("Hunk `-U0`"), §8 ("không phụ thuộc cấu hình… toàn cục"), R16; PLAN D24; checklist 5 (tái lập).

### [Major] 2. `paths_exist` ném GitError khi path là submodule (gitlink) — `src/loc_counter/git_repo.py:784-792`
- **Mô tả:** Với gitlink trỏ tới commit không có trong repo (trường hợp thường gặp của submodule), git 2.55 trả `<sha> submodule`. Dòng này có 2 trường và không kết thúc bằng ` missing`, nên rơi vào nhánh `else` và ném `GitError("Không đọc được kết quả kiểm tra đường dẫn.")`. Cả loạt `paths_exist` thất bại, kể cả các path hợp lệ khác trong cùng lô.
- **Kịch bản lỗi (đã chạy):** cây có `160000 commit 1111…1111\tsub`. `printf '<K>:sub\n' | git cat-file --batch-check` cho `1111111111111111111111111111111111111111 submodule`, nên `paths_exist([(K, "a.py"), (K, "sub")])` ném GitError thay vì trả `[True, True]`. (Gitlink trỏ tới commit có trong repo thì trả `<sha> commit <size>`, tức True. Hai trường hợp không nhất quán.)
- **Tác động:** `diff_tree` trả gitlink như mọi entry (§6: "người gọi lọc theo mode"). Khi file bị thay bằng submodule cùng tên (status `T`, 100644 → 160000), `attribution` (§7.4) có thể cần hỏi "path cũ còn tồn tại ở C_END không" và sẽ làm cả lượt phân tích dừng ở luồng chính. Spec §5.16 không định nghĩa trường hợp gitlink (xem Ghi chú cho spec 1).
- **Đề xuất sửa:** dòng có 2 trường mà trường đầu là SHA 40 hex và trường thứ hai là `submodule` thì coi là `True` (path có trong cây), hoặc dùng `--batch-check='%(objectname) %(objecttype)'` rồi xử lý tường minh. Cập nhật §5.16 bước 2 và thêm ca gitlink (có/không có commit trong repo) vào TC-47.
- **Tham chiếu:** git_repo §5.16, §6; R14/R15 (§7.2, §7.4 spec gốc).

### [Minor] 1. `paths_exist` báo sai `False` với path kết thúc bằng `\r` — `src/loc_counter/git_repo.py:774-776`
- **Mô tả:** `cat-file --batch*` đọc stdin bằng `strbuf_getline`, hàm này bỏ `\r` trước `\n`. Path `cr.py\r` (hợp lệ trong git) vì vậy được tra thành `cr.py`.
- **Kịch bản (đã chạy):** cây có `cr.py\r`. Input `<K>:cr.py\r\n` cho `<K>:cr.py missing`, nên `paths_exist([(K, "cr.py\r")])` trả `[False]`, đáng lẽ `True`.
- **Đề xuất:** đưa path kết thúc bằng `\r` (hoặc chứa `\r`) vào nhánh `cat-file -e` riêng giống path chứa `\n`. Cập nhật §5.16 bước 1/3 và TC-47.
- **Tham chiếu:** git_repo §5.16.

### [Minor] 2. `write_entries` không bao giờ dùng hết generator `read_blobs`, nên không kiểm mã thoát và không phát hiện đọc thiếu byte — `src/loc_counter/snapshot.py:263-267`, `src/loc_counter/git_repo.py:549-551`
- **Mô tả:** `write_entries` gọi `next(blobs)` đúng N lần rồi `closing()` gọi `close()`. Generator đang dừng ở `yield` nên nhận `GeneratorExit`, `finished=False`, và tiến trình bị `kill()`. Nhánh "đóng stdin, chờ, mã ≠ 0 → GitError" (§5.9) vì thế không bao giờ chạy trong luồng ghi zip. Thêm vào đó `proc.stdout.read(size)` không kiểm `len(data) == size`: nếu `cat-file` chết giữa chừng ở blob cuối, nội dung bị cắt vẫn được ghi vào zip mà không có lỗi.
- **Kịch bản:** tiến trình `git cat-file --batch` bị dừng (antivirus, hết bộ nhớ) khi đang trả blob cuối. Zip có file thiếu byte, LOC đếm sai mà không có cảnh báo. Hiếm gặp, chưa tái hiện được bằng git thật (đã kiểm chứng bằng cách đọc luồng điều khiển).
- **Đề xuất:** trong `read_blobs`, kiểm `len(data) == int(header[2])`, nếu sai thì ném GitError. Tùy chọn: trong `write_entries`, sau vòng ghi thì gọi `next(blobs, None)` để generator kết thúc bình thường và kiểm mã thoát.
- **Tham chiếu:** git_repo §5.9; snapshot §5.8; checklist 4 (không nuốt lỗi im lặng).

### [Minor] 3. Nhánh xử lý lỗi M4 chưa có test — `src/loc_counter/git_repo.py:636, 699, 740, 781-783, 791-792`
- **Mô tả:** Coverage cho thấy chưa test các nhánh: bản ghi `diff-tree` sai định dạng (meta không đủ 5 trường hoặc thiếu đường dẫn, :636); `line_ranges` toàn khoảng rỗng thì trả `[]` mà không gọi git (:699); porcelain kết thúc giữa bản ghi (:740); `--batch-check` trả sai số dòng hoặc dòng lạ (:781-783, :791-792). Đây đều là các hàng trong bảng lỗi mục 7. Lỗi Major 2 nằm đúng ở nhánh :791 chưa được test.
- **Đề xuất:** thêm các tham số vào TC-44 / TC-47 / TC-49 (monkeypatch stdout). Thêm ca `line_ranges=[(3,3)]` với spy xác nhận không chạy git.
- **Tham chiếu:** git_repo §7, §9.

### [Nit] 1. TC-45 thiếu assertion đối chứng "không `ancestry_path` → `[c3]`" — `tests/test_git_repo.py:1090`
- Spec TC-45 ghi rõ `rev_list(c4, f1, ["x.py"])` (không `ancestry_path`) là `[c3]`. Test chỉ kiểm ca có `--ancestry-path` cho ra `[]`. Hiện ca này vẫn phát hiện được nếu thiếu cờ (vì kết quả sẽ là `[c3]`), nhưng nên có assertion tường minh để test tự mô tả đúng TC.

### [Nit] 2. Kiểu và docstring helper private — `src/loc_counter/git_repo.py:718` (`current: dict | None`), `_env`, `_command`, `_mask`, `_exec`, `_clone`, `_update_head`, `_header_b64`
- Nên dùng `dict[str, object]` hoặc một dataclass nhỏ cho bản ghi blame. Các helper private chưa có docstring. Không bắt buộc theo spec.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Không đạt | Luồng xử lý và chữ ký API khớp mục 3 của cả hai spec; lệnh git đúng (`-w -M -C --line-porcelain`, `--reverse`, `--ancestry-path`, `diff-tree -M`). Sai ở môi trường `GIT_DIFF_OPTS` (Major 1) và gitlink trong `paths_exist` (Major 2). Mọi TC có test. |
| 2. Nghiệp vụ dễ sai | Đạt một phần | Boundary, `--root`, reverse blame theo rename, commit cũ nhất của `--ancestry-path` đều đúng và có test. Hunk sai khi có `GIT_DIFF_OPTS`. Chỉ số dòng 0-based nhất quán giữa `diff_hunks` và `blame`. Phần classifier/builder: N/A (ngoài phạm vi). |
| 3. Bảo mật | Đạt | Lệnh M4 đi qua `_exec`/`_mask`, stderr đã che token; không `shell=True`; tham số commit/blob kiểm 40 hex; path sau `--` hoặc gắn sau `<sha>:`; `is_unsafe_path` áp trong `screen_entry` nên `select_content` cũng được bảo vệ. `write_entries` không tự kiểm `is_unsafe_path` (dựa vào người gọi, đúng spec). |
| 4. Lỗi & log | Đạt một phần | Thông báo tiếng Việt, log WARNING kèm lệnh. Ngoại lệ: Minor 2 (đọc thiếu byte không phát hiện). |
| 5. Tái lập & encoding | Đạt một phần | Zip sắp theo path, timestamp cố định, POSIX, bytes gốc (TC-28). Kết quả `diff_hunks` phụ thuộc biến môi trường (Major 1). |
| 6. Windows | Đạt | `-L` chia lô 200 khoảng; `--git-dir str(Path)`; xóa `.tmp` khi lỗi; `ZipFile` đóng trước `os.replace`. |
| 7. Chất lượng code | Đạt | Type hint đủ cho API công khai; ruff sạch; không thư viện mới; ranh giới module đúng (`snapshot` không gọi git trực tiếp). Nit 2. |
| 8. Hiệu năng | Đạt (khuyến nghị) | `read_blobs`/`paths_exist` một tiến trình cho cả loạt, mỗi SHA đọc một lần. `plan_export` ở chế độ `full` đọc trọn blob lớn chỉ để lấy 8000 byte đầu (spec cho phép, để M7 xử lý). |
| 9. Streamlit | N/A | Không có màn hình trong phạm vi. |

## Ghi chú cho spec
1. **git_repo §5.16:** chưa định nghĩa kết quả cho gitlink (`<sha> submodule` trên git mới, `<sha> commit <n>` khi commit có trong repo) và cho path chứa `\r` (`cat-file` tự bỏ CR). Cần người dùng chốt: gitlink tính là "tồn tại" (đề xuất) hay `attribution` phải lọc trước khi gọi.
2. **git_repo §5.1 bước 2:** danh sách biến môi trường cần trung hòa nên thêm `GIT_DIFF_OPTS` (và `GIT_EXTERNAL_DIFF`). TC-37 nên có ca biến môi trường.
3. **snapshot `is_unsafe_path` (cho M5, khi giải nén ra đĩa để đếm LOC — §3.4 "LOC luôn đếm trên chính thư mục export"):** chưa xử lý các trường hợp trên Windows: tên khác nhau chỉ ở hoa/thường (`A.py` và `a.py`, giải nén sẽ ghi đè lẫn nhau, nên LOC sai); tên có dấu `.`/khoảng trắng cuối (`a.py.` trùng `a.py`); ký tự cấm `<>"|?*`; tên thiết bị (`CON`, `NUL.py`…). Cần quyết định trước M5: cảnh báo, đổi tên, hay đếm trên nội dung trong bộ nhớ. Không phải lỗi của bản M4 này.
4. **snapshot `make_period`:** spec chưa nói về múi giờ có DST (giờ không tồn tại hoặc lặp lại khi chuyển giờ). `Asia/Bangkok` mặc định không bị ảnh hưởng. Nên ghi một dòng giả định.
