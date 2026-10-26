# Review: counter (M4: WarningKind) + snapshot (F8: UNSAFE_PATH) — 2026-10-23
Kết luận: **PASS**
Spec: docs/specs/counter.md (status: implemented), docs/specs/snapshot.md (status: implemented)
Files: src/loc_counter/counter.py, src/loc_counter/snapshot.py, tests/test_counter.py, tests/test_snapshot.py
Phạm vi: bản cập nhật M4 của `counter` (danh mục `WarningKind` §5.2, TC-16, 17) và bản F8 của `snapshot` (`screen_entry` phát `UNSAFE_PATH`, 5.3.3.2, 5.7, bảng 5.3, mục 7; sửa TC-21, 23, 25, 27). Đọc lại toàn bộ hai module và hai file test để tìm hồi quy.

## Bằng chứng tự động
- ruff (`uv run ruff check src tests`): `All checks passed!`
- pytest (`tests/test_counter.py tests/test_snapshot.py`): **132 passed**, 0 failed. Toàn bộ suite: **375 passed** (135 s).
- coverage: `counter.py` 98% (thiếu 113-114, 127: nhánh `onerror` không có `filename` và junction trên Python < 3.12, đã có từ M1); `snapshot.py` 100%.
- Kiểm chứng thủ công (script trong scratchpad, không ghi vào repo):
  - `str(WarningKind.UNSAFE_PATH) == "unsafe_path"`, nên `cli.py:91` (`str(w.kind)`) xuất đúng giá trị chuỗi cho loại mới; `sorted([UNSAFE_PATH, BINARY, RENAME_LIMIT])` sắp theo giá trị chuỗi.
  - `screen_entry("../x.py", "120000", ...)` (symlink) và `screen_entry("../sub", "160000", "commit", ...)` (submodule) → `keep=False`, không cảnh báo. Đúng thứ tự bước 5.7 (1 trước 2) và đúng bảng 5.3.
  - `is_unsafe_path`: `a/.git`, `x/.Git./y`, `C:x.py`, `""`, `a//b`, `/abs.py`, `a/b:` → True. `GIT~1/config`, `CON.py`, `a.py.`, `.. /x.py`, `.../x.py` → False (đúng định nghĩa đã duyệt; xem Ghi chú cho spec 3).
  - `ntpath.abspath` (GetFullPathNameW) với `C:\out\export` + `.. \x.py`, `a\.. \.. \evil.py`, `a\...\b.py` vẫn nằm trong thư mục đích. Các thành phần này không dẫn tới path traversal.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| counter §3, §5.2 | `WarningKind` đủ 12 loại, đúng tên và giá trị | counter.py:20-36; TC-16 `test_warning_kind_catalog` (so khớp đúng dict 12 cặp, giá trị không trùng, `[a-z_]+`, `WarningKind("unsafe_path") is UNSAFE_PATH`) | Đạt |
| counter §3 | `LocWarning.path` có thể là `""` (cấp repo) | counter.py:39-45 (docstring ghi rõ) | Đạt |
| counter §5.2 | `WarningKind` là danh mục duy nhất, module khác không tự định nghĩa | grep `src/`: chỉ `snapshot.py:18` import lại; chưa có `attribution.py`/`builder.py` | Đạt |
| counter §6 | Sắp xếp theo `(path, kind)` bằng giá trị chuỗi, `""` đứng đầu; 4 loại M1 giữ nguyên giá trị | counter.py:183, snapshot.py:232; TC-17, TC-03 (thứ tự theo path) | Đạt (Nit 1) |
| counter §5.1 | `count_directory` không đổi | counter.py:132-186 giống bản M1; TC-01..15 pass | Đạt |
| snapshot 5.3.3.2 / 5.7 bước 2 | Đường dẫn không an toàn → `keep=False`, một `UNSAFE_PATH` đúng thông báo, `path` là đường dẫn gốc, log WARNING `%r`; các trường còn lại như `_DROPPED`; kiểm tra trước §9 | snapshot.py:154-158; TC-25 `test_screen_entry_unsafe` (2 path × 2 chế độ × `exclude_binary`, kiểm cờ, thông báo, log) | Đạt |
| snapshot 5.3 (plan_export) | Cảnh báo của entry bị bỏ ở `screen_entry` được gộp vào `plan.warnings` | snapshot.py:215-217; TC-21 (`../evil.py`, `.GIT/evil.py`, đúng thứ tự, đúng thông báo), TC-23 (`plan.warnings == [UNSAFE_PATH a:b.py]`), TC-26 | Đạt (Nit 2) |
| snapshot 5.7 `select_content` | Bỏ ở `screen_entry` → `Selection(False, None, s.warnings)` (giữ `UNSAFE_PATH`) | snapshot.py:200-202; TC-27 (`C:/x.py` cả hai chế độ), `test_select_content_unsafe_logged` | Đạt |
| snapshot bảng 5.3 | Dòng "Đường dẫn không an toàn → bỏ ở mọi chế độ, UNSAFE_PATH + log" | TC-25, TC-27 | Đạt |
| snapshot mục 7 | Thông báo `Bỏ qua file có đường dẫn không an toàn (không đưa vào export)` | snapshot.py:157 trùng nguyên văn; `UNSAFE_MSG` trong test | Đạt |
| snapshot 5.4, 5.8, 5.9 | Không đổi trong lần này | snapshot.py:248-296; TC-15, 16, 19, 22, 24, 28-32 | Đạt |
| Truy vết TC | Docstring test bắt đầu bằng ID | counter TC-01..17, snapshot TC-01..32 đều có | Đạt |

## Phát hiện
Không có Blocker, Major hay Minor.

### [Nit] 1. TC-counter-17 tự viết lại khóa sắp xếp trong test, không gọi code sản phẩm — `tests/test_counter.py:248-262`
- **Mô tả:** Test gọi `sorted(warnings, key=lambda w: (w.path, w.kind))` ngay trong test. Cách này chỉ kiểm cách `StrEnum` so sánh, không kiểm khóa sắp xếp thật ở `counter.py:183` hay `snapshot.py:232`. Test bám đúng câu chữ của TC ("sắp theo khóa (path, kind) của mục 5.1") nên không coi là thiếu test.
- **Kịch bản:** đổi `snapshot.py:232` thành `key=lambda w: (w.kind, w.path)` thì TC-17 vẫn pass. Riêng `counter.py:183` vẫn được TC-03 bảo vệ phần thứ tự theo path.
- **Đề xuất:** khi viết `report`/`pipeline` (M5), thêm một hàm sắp xếp dùng chung (ví dụ `sort_warnings`) và cho TC-17 gọi hàm đó.
- **Tham chiếu:** counter §6, TC-17.

### [Nit] 2. TC-snapshot-21 không kiểm vế "không có trong zip" — `tests/test_snapshot.py:283-303`
- **Mô tả:** Kết quả mong đợi của spec gồm "không có trong `plan.files`, **không có trong zip**". Test mới kiểm `plan.files` và chưa ghi zip. `write_zip` chỉ ghi `plan.files` (snapshot.py:290) nên vế zip đúng theo cách dựng, nhưng chưa có assertion trực tiếp.
- **Đề xuất:** thêm `export_snapshot(...)` và `zipfile.ZipFile(...).namelist() == ["ok.py"]`.
- **Tham chiếu:** snapshot TC-21.

### [Nit] 3. Tài liệu theo dõi chưa cập nhật — `docs/specs/README.md:25,28`, `docs/PLAN.md:72,111`
- **Mô tả:** README ghi trạng thái `approved (M4)` / `approved (F8)`, trong khi front matter của hai spec đã là `implemented`. Dòng F8 trong bảng tồn đọng của PLAN chưa ghi là đã xử lý. Đoạn "Tiến độ M4" vẫn ghi bước tiếp theo là `/feature-spec counter`.
- **Đề xuất:** cập nhật README, PLAN (F8 đã xử lý, bước tiếp theo là `attribution`) khi chuyển spec sang `reviewed`.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Mọi bước 5.2, 5.3.3.2, 5.7 có trong code, đúng thứ tự; API công khai khớp mục 3 (`CountResult` có `default_factory`, đã có từ M1, không ảnh hưởng); không động tới định nghĩa mục 3 hay thuật toán mục 6, 7 của spec gốc; 49/49 TC có test. |
| 2. Nghiệp vụ dễ sai | N/A phần lớn | Phạm vi không chạm classifier, attribution, builder hay identity. Phần snapshot liên quan (bảng 5.3) được TC-25 kiểm theo từng dòng. |
| 3. Bảo mật | Đạt | Không có token. Không ghi ra ngoài thư mục đích: đường dẫn không an toàn bị loại ở cả `plan_export` và `select_content`. Đã kiểm GetFullPathNameW với `.. `, `...`. |
| 4. Lỗi & log | Đạt | Cảnh báo nghiệp vụ đi vào `LocWarning`, kèm log WARNING `%r`; không nuốt exception. |
| 5. Tái lập & encoding | Đạt | `warnings` được sắp `(path, kind)` sau khi gộp; sort ổn định. Xem Ghi chú cho spec 2 cho M5. |
| 6. Windows | Đạt | Không đổi cách xử lý đường dẫn; quy tắc `:`, `\`, `.git.`/`.git ` giữ nguyên. |
| 7. Chất lượng code | Đạt | Có type hint và docstring tiếng Việt; ruff sạch; không có code chết. |
| 8. Hiệu năng | N/A | Không đổi; `plan_export` vẫn đọc blob bằng một lượt `read_blobs` (TC-26). |
| 9. Streamlit | N/A | Không có màn hình. |

## Ghi chú cho spec
1. **TC-snapshot-21 không thống nhất trong spec:** cột Input ghi "thư mục `.GIT` chứa `x.py`", còn cột Kết quả mong đợi ghi `.GIT/evil.py`. Test dùng `evil.py` cho cả hai thư mục. Nên sửa cột Input thành `evil.py`.
2. **Khóa `(path, kind)` chưa xác định thứ tự toàn phần:** `attribution` sẽ phát nhiều cảnh báo cùng `(path, kind)` (ví dụ `MULTI_USER_HUNK` theo từng hunk, `UNATTRIBUTED` theo khoảng dòng). Khi đó thứ tự trong `warnings.csv` phụ thuộc thứ tự phát ra (đã kiểm: sort ổn định nên giữ nguyên thứ tự chèn). Khi viết spec `attribution`/`report` (M5) cần chốt một trong hai cách: (a) mở rộng khóa thành `(path, kind, message)`, hoặc (b) yêu cầu module phát ra theo thứ tự xác định (ví dụ theo số dòng). Việc này cần người dùng quyết định.
3. **`is_unsafe_path` không chặn tên chỉ có nghĩa đặc biệt trên Windows** (`.. ` có khoảng trắng cuối, `...`, `GIT~1`, `CON.py`, `a.py.`): theo đúng định nghĩa đã duyệt. Kiểm chứng cho thấy các tên này không dẫn tới path traversal, chỉ có thể làm giải nén lỗi hoặc làm hai file trùng tên. Thuộc PLAN F9, quyết định ở M5.
