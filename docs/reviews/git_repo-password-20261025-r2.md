# Review: git_repo lần 2 (r2), kiểm lại các điểm của `reviews/git_repo-password-20261025.md` — 2026-10-25
Kết luận: **PASS_WITH_NOTES**
Spec: docs/specs/git_repo.md (status: implemented; mục 5.3 sửa theo review 2026-10-25)
Files: `src/loc_counter/git_repo.py` (`normalize_source` :196–221, `_is_scp_like` :224–228, `_URL_RE` :32, `_DRIVE_RE` :36), `tests/test_git_repo.py` (`test_normalize_source` :74, `test_password_in_url` :92–135), `README.md` (dòng 25)

Lưu ý: `Countloc/` có `.git` nhưng chưa có commit nào (`git status`: mọi file đều untracked), nên không lấy được diff. Phạm vi xác định theo mục "Lịch sử thay đổi" 2026-10-25 (dòng thứ 3 và 4) của spec và theo các phát hiện của review lần 1.

## Bằng chứng tự động
- ruff: `All checks passed!`
- pytest: `tests/test_git_repo.py` 84 passed (67 s). Các test khác có gọi `normalize_source` / `GitRepo.open`: `test_app_input.py`, `test_cli_users.py`, `test_cli_analyze.py`, `test_identity.py` 117 passed. Không chạy lại toàn bộ suite (khoảng 600 s); thay đổi chỉ nằm trong `normalize_source`.
- coverage `git_repo.py`: 97 %. Toàn bộ `normalize_source` và `_is_scp_like` (196–228) được phủ. Các dòng chưa phủ (187, 253–254, …) nằm ngoài phạm vi.
- Script kiểm chứng `scratchpad/probe_r2.py`: 43 input biên cho `normalize_source`. Kiểm thêm `git ls-remote "ext::…"` với cấu hình git sạch.

## Kiểm lại các phát hiện của review lần 1
| Phát hiện r1 | Trạng thái | Bằng chứng |
|---|---|---|
| Major: mật khẩu chứa `#` `?` `/` lọt qua `urlsplit` | **Đã sửa** | :207–211 lấy userinfo theo `@` cuối của phần sau `://`, không dùng `urlsplit`. Probe: `ssh://u:pa#ss@h/o/r`, `ssh://u:pa?ss@…`, `ssh://u:pa/ss@…`, `https://u:pa?ss@github.com/o/r`, `https://pa#ss@github.com/o/r` → cả 5 đều REJECT. Test TC-54 có 6 ca tương ứng |
| Minor: scp có `@`/`/`/`\` trong mật khẩu, user lạ, `git+ssh`/`ssh+git`/`ftp` rơi vào nhánh local và bị in lại | **Đã sửa** | `first~last:pw@h:o/r`, `ssh+git://u:pw@h/o/r`, `ftps://u:pw@h/r` → REJECT. `u:p@ss@h:o/r`, `u:pa/ss@h:o/r`, `u:pa\ss@h:o/r` → `Không tìm thấy repo: ***@h:o/r` (đã che, :219). `git+ssh://git@h/o/r`, `ssh+git://git@h/o/r` → nguồn từ xa hợp lệ |
| Minor: cache cũ giữ mật khẩu trong `remote.origin.url` | **Đã xử lý bằng tài liệu** | spec 5.3 b4; README dòng 25 hướng dẫn xóa `~/.loc_counter/repos/` |
| Nit: comment :209 sai nghĩa | **Đã sửa** | :209–210 |
| Nit: thứ tự kiểm trên POSIX | N/A | Không cần sửa. `_DRIVE_RE` nay áp trên mọi nền tảng, nên ca `u:…` có user một chữ cái luôn đi vào nhánh local và bị che |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 5.3 b1 | strip; rỗng → "Chưa nhập repo" | :201–203; TC-02 | Đạt |
| 5.3 b2(a) | scheme `^[A-Za-z][A-Za-z0-9+.-]+://` là nguồn từ xa | `_URL_RE` :32 (trùng regex spec), :204; TC-54 (`git+ssh`, `ssh+git`, `ftp`) | Đạt |
| 5.3 b2(b) | scp: có `:`, trước `:` đầu không có `/` `\`, không phải ổ `X:` | `_is_scp_like` :224–228; TC-54 (`git@h:o/r.git`, `us:…`, `u~x:…`) | Đạt theo chữ spec (xem Minor 1 và Minor 2) |
| 5.3 b2 URL | userinfo = phần trước `@` cuối của `rest`; http(s): có `@` → từ chối; scheme khác: userinfo có `:` → từ chối | :207–215; TC-02, TC-54 | Đạt |
| 5.3 b2 scp | phần trước `@` cuối có `:` → từ chối | :207–211 (`rest = text`); TC-54 `us:s3@cret@h:o/r` | Đạt |
| 5.3 b2 false positive | `ssh://git@h:22/o/r@v` bị từ chối nhầm | probe: REJECT | Đạt (đúng mô tả spec) |
| 5.3 b2 cuối | bỏ `/` cuối, giữ hoa/thường | :216; TC-54 `ssh://git@h:22/o/r/` | Đạt |
| 5.3 b3 | đường dẫn local; không tồn tại → che phần trước `@` cuối | :217–220; TC-54 `<tmp>/u:s3cret@x`, `<tmp>/a@b` | Đạt |
| 5.3 b4 | cache cũ: không tự dọn, README hướng dẫn | README:25 | Đạt |
| 5.4 b1–2 | `git_version()` rồi `normalize_source`, lỗi trước mọi lệnh git khác | :404–405; TC-54 spy (chỉ `--version`) | Đạt |
| Mục 7 | thông báo không lặp URL; WARNING không ghi URL | :213–215 | Đạt |
| TC-git_repo-54 | 15 ca từ chối, 6 ca hợp lệ, 2 ca local, 2 ca `open`; không chứa `s3cret`/`cret` trong thông báo và caplog | test_git_repo.py:92–135. Đã đối chiếu từng input trong spec dòng 451: đủ, đúng thứ tự | Đạt |
| TC-git_repo-02 | http(s) có userinfo bị từ chối, thông báo không chứa bí mật | test_git_repo.py:74–89 | Đạt |
| TC-screen-input-04 | thông báo lỗi nguồn trên UI | test_app_input.py:154–164 (pass) | Đạt |

## Phát hiện

### [Minor] Thư mục local trên POSIX có `:` trước `/` đầu tiên (vd. `repo:2024`) nay bị coi là scp, nên không mở được — `src/loc_counter/git_repo.py:205`, `:228`
- **Mô tả:** `_is_scp_like("repo:2024")` trả True, nên `normalize_source` → `('repo:2024', False)` (đã kiểm chứng bằng probe). Trước r2, nhánh scp chỉ bắt `user@host:` nên chuỗi này là đường dẫn local. Git có thêm một quy tắc mà spec 5.3(b) không nói tới: `git clone` gọi `get_repo_path()` **trước**, nên đường dẫn đã tồn tại trên đĩa luôn là local, dù có `:`.
- **Kịch bản (POSIX, suy ra từ code; không tái hiện được trên Windows vì NTFS không cho tên chứa `:`):** người dùng nhập `repo:2024` khi đang đứng ở thư mục cha. `is_local=False` nên clone **không** có `--no-hardlinks`, trái D20/F2. Git clone thư mục local, rồi ghi `remote.origin.url` = đường dẫn tuyệt đối. `_check_origin_url` so với `"repo:2024"`, thấy khác, ném "Cấu hình repo cache không khớp nguồn. Hãy xóa thư mục … rồi thử lại." Xóa xong mở lại vẫn lỗi y như cũ, nên người dùng bị kẹt. Có thể đi vòng bằng `./repo:2024`.
- **Đề xuất:** trong `normalize_source`, nếu chuỗi khớp scp mà không có `://`, kiểm `Path(text).expanduser().is_dir()` trước, giống `get_repo_path` của git. Thư mục có thật thì coi là local. Sửa spec 5.3(b) trước, thêm một ca TC-54 (`skipif` trên Windows), hoặc ghi giới hạn này vào README.
- **Tham chiếu:** git_repo 5.3(b), 5.4 b6 (`--no-hardlinks`), PLAN D20.

### [Minor] Cú pháp remote helper `<transport>::<địa chỉ>` (vd. `ext::…`, `fd::…`) nay đi thẳng vào `git clone` — `src/loc_counter/git_repo.py:228`
- **Mô tả:** `ext::sh -c x` có head `ext` không chứa `/`, nên `_is_scp_like` trả True và `normalize_source` → `('ext::sh -c x', False)` (đã kiểm chứng). Trước r2, chuỗi này rơi vào nhánh local và bị từ chối. Đúng chữ spec 5.3(b), nhưng spec không nói gì về remote helper. Rủi ro hiện tại thấp: với cấu hình git mặc định, `git ls-remote "ext::sh -c echo% hi"` → `fatal: transport 'ext' not allowed` (đã kiểm chứng; máy này không đặt `protocol.ext.allow`). Rủi ro chỉ thành thật khi người dùng tự bật `protocol.ext.allow`/`GIT_ALLOW_PROTOCOL`, hoặc khi Streamlit nghe trên mạng: README:103 khuyên `localhost`, nhưng mặc định của Streamlit là mọi địa chỉ. `fd::0` (chính sách `user`, được phép mặc định) làm git đọc stdin của tiến trình (`subprocess.run` không đặt `stdin`), nên có thể treo.
- **Đề xuất:** có hai cách. (a) Thêm `-c protocol.ext.allow=never -c protocol.fd.allow=never` vào `_GLOBAL_OPTS`. (b) Ghi vào spec 5.3 rằng chuỗi có `::` trước `/` đầu tiên bị từ chối với thông báo "Nguồn repo không được hỗ trợ". Cần người dùng chọn (xem Ghi chú cho spec 1).
- **Tham chiếu:** git_repo 5.3(b), mục 8; checklist nhóm 3 (tham số người dùng thành lệnh git).

### [Nit] Spec mục 4 và mục 7 chưa cập nhật theo 5.3 mới — `docs/specs/git_repo.md:208`, `:361`, `:362`
- Mục 4 (dòng 208) vẫn liệt kê `https/http/ssh/git@host:path/file`, chưa có scheme tổng quát (`git+ssh`, `ssh+git`, ftp(s)).
- Mục 7 (dòng 361) ghi "ssh/git/file hoặc scp có mật khẩu", nên là "scheme khác hoặc scp".
- Dòng 362 ghi `Không tìm thấy repo: <đường dẫn>` mà không nói phần trước `@` cuối bị che thành `***`.

### [Nit] "Theo quy tắc của git" chưa đúng hoàn toàn — `src/loc_counter/git_repo.py:225–228`
- Ở `url_is_local_not_ssh`, git chỉ xét `/` (không xét `\`), và chỉ loại tiền tố ổ đĩa `X:` trên Windows. Code (khớp spec) còn loại `\` và loại `X:` trên mọi nền tảng. Hệ quả trên POSIX: `h:o/r` (host một chữ cái) → "Không tìm thấy repo: h:o/r", còn git coi đó là ssh. Trên mọi nền tảng: `a\b:c` → local. Cả hai đều theo hướng an toàn (không lộ gì), chỉ nên sửa docstring/spec thành "gần quy tắc git, bảo thủ hơn".

### [Nit] userinfo mã hóa % không bị coi là mật khẩu — `src/loc_counter/git_repo.py:211`
- `ssh://u%3Apw@h/r` → chấp nhận (probe), nên chuỗi `u%3Apw` vào log/manifest. Git url-decode thành user `u:pw`, nhưng ssh không có mật khẩu trong URL, nên về ngữ nghĩa đây chỉ là tên user. Đã đúng spec; ghi nhận để người dùng biết.

### [Nit] PLAN chưa ghi lần sửa r2 — `docs/PLAN.md:322`
- Dòng rủi ro M5 vẫn chỉ mô tả bản sửa lần 1 (ssh/git/file/scp). Nên thêm: "r2: tìm userinfo theo `@` cuối, scheme tổng quát, che thông báo local".

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Mọi bullet 5.3 (b1–b4) có code. TC-54 khớp từng input trong spec. Không có API công khai mới (`_is_scp_like` là private) |
| 2. Nghiệp vụ dễ sai | N/A | Không chạm classifier/attribution/builder/snapshot |
| 3. Bảo mật | Đạt (có Minor 2) | Đã thử 43 input biên, không ca nào lộ mật khẩu vào thông báo/log. http(s) có `@` luôn bị từ chối, kể cả remote helper `https::…`/`http::…` (nhờ `:` trong userinfo). Remote helper `::` nay tới được `git clone` (Minor 2). `--` trước nguồn trong `clone` chặn chèn option |
| 4. Lỗi & log | Đạt | Thông báo tiếng Việt. WARNING "Từ chối URL…" không ghi URL. Input NUL / quá dài / `CON` / `<>\|?` → GitError, không crash (probe) |
| 5. Tái lập & encoding | N/A | |
| 6. Windows | Đạt | `C:\Users\me@corp\…`, `D:repo@v2:x`, UNC `\\srv\share\…`, `//srv/…` → local. `file:///C:/…` → URL. Lỗi local trên POSIX ở Minor 1 |
| 7. Chất lượng code | Đạt | type hint, docstring tiếng Việt, ruff sạch, comment :206 và :209 đúng nghĩa |
| 8. Hiệu năng | N/A | |
| 9. Streamlit | N/A (gián tiếp Đạt) | `app._load_repo` gọi `normalize_source` trước khi khóa cache, bắt `LocCounterError` rồi `st.error`. TC-screen-input-04 pass |

## Ghi chú cho spec
1. **Remote helper `<transport>::<địa chỉ>` (Minor 2):** cần chốt một trong hai: (a) chấp nhận và chặn `ext`/`fd` bằng `-c protocol.<x>.allow=never`; (b) từ chối `::` với thông báo rõ. Khuyến nghị (a), vì vẫn dùng được `https::`/`ssh::` hợp lệ và không đổi luồng 5.3.
2. **Đường dẫn local có `:` trên POSIX (Minor 1):** nên thêm vào 5.3(b) quy tắc "chuỗi dạng scp mà là thư mục có thật trên đĩa → local", giống `git clone`.
3. **`ftp://tok@host`, `ftps://tok@host` được chấp nhận** (git có `git-remote-ftp(s)` dựa trên curl, đã thấy trong `git --exec-path`). Theo 5.3 chỉ http(s) mới từ chối userinfo không có mật khẩu. Nếu muốn nhất quán với "token không bao giờ trong URL", có thể mở rộng quy tắc http(s) sang ftp(s). Người dùng quyết định.
4. **False positive hiện có (không đổi ở r2):** `https://org@dev.azure.com/org/p/_git/r`, dạng URL mà Azure DevOps hiển thị mặc định, bị từ chối; scp `git@h:o/r@v` cũng bị từ chối nhầm, tương tự ví dụ `ssh://git@h:22/o/r@v` mà spec đã ghi. Nên ghi thêm vào README: bỏ `org@` khỏi URL Azure.
