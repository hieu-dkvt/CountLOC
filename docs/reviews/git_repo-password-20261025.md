# Review: git_repo — từ chối mật khẩu trong URL ssh/git/file/scp (spec 5.3, TC-git_repo-54) + TC-pipeline-37 — 2026-10-25
Kết luận: **FAIL**
Spec: docs/specs/git_repo.md (status: implemented), docs/specs/pipeline.md (TC-37, chỉ test)
Files: `src/loc_counter/git_repo.py` (`normalize_source`, `_SCP_PASSWORD_RE`), `tests/test_git_repo.py` (`test_password_in_non_http_url`), `tests/test_pipeline.py` (`test_systematic_cross_check_mismatch`), `tests/conftest.py` (`build_systematic_mismatch`)

Lưu ý: `Countloc/` không phải repo git → không có diff; phạm vi xác định qua mục "Lịch sử thay đổi" 2026-10-25 của hai spec và PLAN (rủi ro M5, dòng 322).

## Bằng chứng tự động
- ruff: `All checks passed!`
- pytest: `tests/test_git_repo.py` 84 passed; `tests/test_pipeline.py -k "37 or cross"` 3 passed; toàn bộ 750 passed (599 s).
- coverage: `normalize_source` (git_repo.py:197–219) được phủ đủ bởi TC-02 + TC-54.
- Script kiểm chứng (thư mục tạm): `probe_ns.py` (22 input biên cho `normalize_source`), `probe_open.py` (`GitRepo.open` + handler log bắt toàn bộ `loc_counter`).

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.3 b1 | strip, rỗng → "Chưa nhập repo" | git_repo.py:202–204; TC-02 | Đạt |
| 5.3 b2 http(s) | mọi userinfo → GitError, không lặp URL | git_repo.py:207–208, 213; TC-02 | Đạt theo chữ spec (xem Major 1: `#`/`?`/`/` trong mật khẩu lọt qua) |
| 5.3 b2 ssh/git/file | phần trước `@` cuối của netloc chứa `:` → GitError; chỉ tên user / cổng hợp lệ | git_repo.py:206, 210; TC-54 | Đạt theo chữ spec; lọt với ký tự dành riêng (Major 1) |
| 5.3 b2 scp | regex `^[\w.+-]+:[^@/\\]*@[\w.-]+:` kiểm trước nhánh local | git_repo.py:37, 205, 210; TC-54 ca 5 | Đạt theo chữ spec; mật khẩu chứa `@`/`/`/`\` vẫn lọt vào "Không tìm thấy repo: …" (Minor 1) |
| 5.3 b2 cuối | bỏ `/` cuối, giữ hoa/thường | git_repo.py:215; TC-54 ca hợp lệ | Đạt |
| 5.3 b3 | đường dẫn local | git_repo.py:216–219; TC-02 | Đạt |
| 5.4 b1–2 | `git_version()` rồi `normalize_source`, lỗi trước khi chạy git khác | git_repo.py:395–396; TC-54 spy (chỉ cho phép `git --version`) | Đạt |
| Mục 7 | dòng lỗi "URL có credential…", log WARNING không ghi URL | git_repo.py:212–214 | Đạt |
| TC-git_repo-54 | 5 ca bị từ chối, thông báo + caplog không có `s3cret`; 3 ca hợp lệ; `open` không chạy git | test_git_repo.py:92–116 | Đạt |
| TC-pipeline-37 | vendor / symlink: `cross_check == (20, 0, 10)`, `ok` false, 100 %, alice `net_code` 0, đúng 1 cảnh báo phạm vi `kiểm tra chéo`, manifest `ok == false`, export end không có `vendor/lib.py`/`lib.py` | test_pipeline.py:510–523, conftest.py:179–192 | Đạt (assertion export end mạnh hơn TC: đúng `["app.py"]`) |
| pipeline mục bảo mật | cập nhật tài liệu | pipeline.md:288, 368 | Đạt |

## Phát hiện

### [Major] Mật khẩu chứa `#`, `?` hoặc `/` (chưa mã hóa %) vượt qua kiểm tra và lọt vào `run.log` / thông báo lỗi — `src/loc_counter/git_repo.py:206`, `:208`, `:210`
- **Mô tả:** userinfo lấy từ `urlsplit(text).netloc`. `urlsplit` cắt netloc tại ký tự đầu tiên trong `/?#`, nên khi mật khẩu có một trong các ký tự này thì phần chứa `@` rơi sang path/query/fragment: netloc không còn `@`, `has_secret` = False, nguồn được chấp nhận nguyên văn. Lỗi này lọt cả qua kiểm tra http(s) đã có từ trước.
- **Kịch bản lỗi (đã kiểm chứng bằng `probe_ns.py`):**
  - `normalize_source("ssh://u:pa#ss@h/o/r")` → `('ssh://u:pa#ss@h/o/r', False)` (đáng lẽ GitError).
  - Tương tự với `ssh://u:pa?ss@h/o/r`, `ssh://u:pa/ss@h/o/r`, `git://u:pa#ss@h/o/r`, `https://u:pa#ss@github.com/o/r`, `https://u:pa?ss@github.com/o/r`: đều bị CHẤP NHẬN.
  - `probe_open.py` với `GitRepo.open("file://u:pa#ss@h/o/r")`: log có `Clone file://u:pa#ss@h/o/r vào cache …` (INFO, git_repo.py:428), dòng DEBUG lệnh `git clone … -- file://u:pa#ss@h/o/r …`, dòng WARNING "Lệnh git lỗi …" kèm stderr `fatal: 'u:pa#ss@h/o/r' does not appear…`. Ngoài ra thông báo `GitError` hiển thị cho người dùng là `Không phải Git repository: file://u:pa#ss@h/o/r`. Nếu clone thành công, nguồn đó còn vào `manifest.repo` và `Tong_quan`. Đây chính là chỗ rò mà thay đổi 2026-10-25 muốn chặn.
- **Đề xuất sửa (sửa spec 5.3 trước, rồi code):** không dựa vào `urlsplit().netloc` để tìm userinfo. Lấy authority theo cách git làm: phần sau `://` tới `/` đầu tiên. Cách an toàn hơn là lấy tới `@` **cuối cùng** đứng trước `/` đầu tiên *sau* `@` đó. Một quy tắc bảo thủ: sau `scheme://`, nếu có `@` và trước `@` cuối của toàn chuỗi có `:` mà không có `/`, thì từ chối. Với http(s): `"@"` xuất hiện trước `/` đầu tiên của path *hoặc* trong phần bị `urlsplit` coi là fragment/query, thì từ chối. Thêm các input trên vào TC-54 (và TC-02 cho http(s)).
- **Tham chiếu:** git_repo 5.3 (bullet ssh/git/file, http(s)), mục 7; CLAUDE.md quy tắc 6; checklist nhóm 3 "URL có credential được che khi log hoặc hiển thị"; PLAN rủi ro M5 (dòng 322).

### [Minor] Mật khẩu kiểu scp có `@`, `/`, `\` hoặc user có ký tự ngoài `[\w.+-]` (và scheme `git+ssh://`, `ssh+git://`, `ftp://`) rơi vào nhánh đường dẫn local và bị in lại trong thông báo lỗi — `src/loc_counter/git_repo.py:37`, `:218`
- **Mô tả:** `_SCP_PASSWORD_RE` loại `@/\` khỏi mật khẩu và giới hạn user ở `[\w.+-]`. Input không khớp regex sẽ thành đường dẫn local, và `GitError(f"Không tìm thấy repo: {text}")` lặp lại nguyên chuỗi. Đây đúng là điều spec 5.3 muốn tránh ("để mật khẩu không lọt vào thông báo 'Không tìm thấy repo: …'").
- **Kịch bản (đã kiểm chứng):** `u:p@ss@h:o/r`, `u:pa/ss@h:o/r`, `u:pa\ss@h:o/r`, `first~last:pw@h:o/r`, `git+ssh://u:pw@h/o/r`, `ssh+git://u:pw@h/o/r`, `ftp://u:pw@h/r` → `GitError('Không tìm thấy repo: <chuỗi có mật khẩu>')`. Thông báo này hiện qua `st.error` / CLI. Log không bị (probe_open: `secret in log: False`).
- **Đề xuất:** ở nhánh local (git_repo.py:218), che userinfo trước khi đưa vào thông báo, ví dụ thay `^[^@]*:[^@]*@` → `***@`, hoặc không lặp lại chuỗi khi chuỗi chứa `@` và `:`. Mở rộng `_URL_RE` / ghi rõ trong spec cách xử lý `git+ssh`, `ssh+git`, `ftp(s)` (git hỗ trợ cả bốn).
- **Tham chiếu:** git_repo 5.3 bullet scp, 5.3 b3.

### [Minor] Cache cũ tạo trước bản sửa vẫn giữ mật khẩu trong `remote.origin.url` — `src/loc_counter/git_repo.py:452–458`
- **Mô tả:** nếu trước 2026-10-25 người dùng từng mở `ssh://u:pass@host/o/r`, thì thư mục cache `~/.loc_counter/repos/<hash>` vẫn còn `config` chứa mật khẩu. Bản sửa chặn ở đầu vào nên không mở lại cache đó được, nhưng cũng không dọn hay cảnh báo. Đã kiểm chứng bằng cách đọc code; chưa tái hiện trên đĩa thật. Mức Minor vì công cụ chưa phát hành (M7 chưa xong), nên ít khả năng có cache cũ.
- **Đề xuất:** ghi vào README / PLAN là cần xóa cache cũ, hoặc chấp nhận và ghi chú trong spec.

### [Nit] Comment sai nghĩa — `src/loc_counter/git_repo.py:209`
- `# ssh/git/file: chỉ tên user hợp lệ; scp không có cú pháp mật khẩu`, trong khi cùng dòng lệnh kế tiếp lại kiểm `_SCP_PASSWORD_RE`. Nên sửa thành "scp: git không hỗ trợ mật khẩu, nhưng chuỗi `user:pass@host:path` vẫn bị từ chối để không lộ".

### [Nit] TC-54 không khóa thứ tự kiểm so với nhánh local trên POSIX
- Ca `u:s3cret@h:o/r.git` trên Windows là đường dẫn ổ `u:`, trên POSIX là đường dẫn tương đối. Test vẫn đủ: nếu regex không khớp thì thông báo sẽ là "Không tìm thấy repo", không khớp `thông tin xác thực`. Không cần sửa, chỉ ghi nhận.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt (theo chữ) | Mọi bullet 5.3 có code + TC; quy tắc spec chưa đủ chặt (Major 1, Minor 1) |
| 2. Nghiệp vụ dễ sai | N/A (git_repo); Đạt (TC-pipeline-37) | Thay đổi không chạm classifier/attribution/builder; TC-37 kiểm đúng giá trị cụ thể, phân biệt được symlink với xóa file (net_code 0 thay vì −10) |
| 3. Bảo mật | **Không đạt** | Mật khẩu có `#?/` lọt vào run.log, thông báo lỗi và có thể cả manifest (Major); thông báo "Không tìm thấy repo" lặp lại mật khẩu (Minor) |
| 4. Lỗi & log | Đạt | Thông báo tiếng Việt; WARNING không ghi URL |
| 5. Tái lập & encoding | N/A | Không đổi |
| 6. Windows | Đạt | Kiểm scp trước `Path()` tránh nhầm ổ đĩa `u:`; `C:\Users\me@corp\repo` không bị nhận nhầm |
| 7. Chất lượng code | Đạt (có Nit) | type hint, docstring tiếng Việt; ruff sạch |
| 8. Hiệu năng | N/A | |
| 9. Streamlit | N/A | `app._load_repo` bắt `LocCounterError` → `st.error`, hành vi mới hiển thị đúng |

## Ghi chú cho spec
1. **5.3 (cần người dùng quyết định trước khi sửa code):** định nghĩa "netloc" trong spec đang ngầm hiểu theo `urlsplit`, nên không bắt được mật khẩu có `#`, `?`, `/` chưa mã hóa. Cần chốt quy tắc tìm userinfo không phụ thuộc vào cách `urlsplit` cắt chuỗi (xem đề xuất ở Major), áp dụng cho cả http(s). Bổ sung TC cho các input ở Major 1.
2. **5.3 b3:** nên quy định thông báo "Không tìm thấy repo: …" che userinfo (hoặc không lặp lại nguồn), để phủ mọi biến thể scp/scheme lạ mà regex không bắt được.
3. **Scheme `git+ssh://`, `ssh+git://`, `ftp(s)://`:** spec chưa nói gì. Hiện chúng bị coi là đường dẫn local, kể cả khi không có mật khẩu (`git+ssh://git@h/o/r` → "Không tìm thấy repo"). Cần chốt: hỗ trợ hay từ chối với thông báo rõ.
4. False positive (không cần sửa): chuỗi local tương đối dạng `D:repo@v2:x` bị coi là scp có mật khẩu. Tên như vậy không hợp lệ trên Windows; trên POSIX rất hiếm.
