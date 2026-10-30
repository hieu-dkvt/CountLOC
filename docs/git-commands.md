# Các lệnh git LOC Counter sử dụng

Nguồn: [src/loc_counter/git_repo.py](../src/loc_counter/git_repo.py). Mọi lệnh chạy qua `subprocess` với danh sách tham số (không dùng `shell=True`).
Ứng dụng chỉ **đọc** repo, không có lệnh ghi (commit, checkout, push, merge...).

## 0. Lệnh chạy ở đâu: local hay remote?

Ứng dụng làm việc trên **bản sao bare cục bộ (cache)**, không làm việc trực tiếp trên repo gốc:

```
Nguồn (URL GitHub hoặc đường dẫn local)
        │   chỉ 3 lệnh chạm tới nguồn: clone / fetch / ls-remote
        ▼
Cache bare cục bộ: ~/.loc_counter/repos/<sha1(URL đã bỏ thông tin xác thực)>
        │   mọi lệnh còn lại chạy ở đây (--git-dir <cache>)
        ▼
Kết quả: zip export, báo cáo
```

| Nhóm | Chạy trên | Cần mạng? |
|---|---|---|
| `clone --bare`, `fetch`, `ls-remote` | Nguồn (remote) → ghi vào cache | Có, nếu nguồn là URL. Nếu nguồn là đường dẫn local thì chỉ đọc đĩa. |
| Mọi lệnh còn lại (mục 2–5) | Cache bare cục bộ | Không |

Hệ quả:
- Sau khi tải xong, phân tích chạy offline được.
- Không đụng repo gốc của người dùng. Repo local cũng được clone vào cache (với `--no-hardlinks` để không đổi quyền file của repo nguồn).
- Không đọc working tree. Nội dung file lấy từ object database (`cat-file`), nên CRLF/BOM được giữ nguyên.
- Cache chỉ có nhánh (`refs/heads/*`), không có tag (`--no-tags`).
- Token GitHub chỉ đi qua biến môi trường `GIT_CONFIG_PARAMETERS` của tiến trình git (header `Authorization`). Token không nằm trong URL, tham số dòng lệnh hay file `config` của cache.

Tuỳ chọn chung cho mọi lệnh: `-c core.quotepath=off` (giữ tên file Unicode), `-c core.autocrlf=false` (không đổi kiểu xuống dòng), `-c log.showSignature=false`, `-c i18n.logOutputEncoding=UTF-8` (tên tác giả không bị hỏng). Biến môi trường `GIT_ASKPASS` và `SSH_ASKPASS` đặt rỗng để git không bật hộp thoại hỏi mật khẩu.

## 1. Lấy repo về cache (chạm tới nguồn)

| Lệnh | Ý nghĩa |
|---|---|
| `git clone --bare --no-tags --origin origin [--no-hardlinks] -- <nguồn> <cache>` | Tạo bản sao chỉ chứa dữ liệu git (không có working tree). `--no-hardlinks` chỉ dùng với nguồn local. |
| `git fetch --prune --no-tags origin +refs/heads/*:refs/heads/*` | Cập nhật cache đã có từ nguồn và xoá nhánh đã bị xoá ở nguồn. |
| `git ls-remote --symref origin HEAD` | Hỏi nguồn nhánh mặc định là gì. |

Các lệnh phụ chạy trên cache để chuẩn bị và kiểm tra:

| Lệnh | Ý nghĩa |
|---|---|
| `git symbolic-ref HEAD <ref>` | Đặt nhánh mặc định của cache theo kết quả `ls-remote`. |
| `git config --get remote.origin.url` | Kiểm tra cache có đúng của nguồn đang nhập không. |
| `git rev-parse --is-bare-repository` | Kiểm tra cache còn hợp lệ không (hỏng thì clone lại). |
| `git --version` | Kiểm tra git ≥ 2.30. |

## 2. Tìm nhánh và mốc thời gian (C_START / C_END)

| Lệnh | Ý nghĩa |
|---|---|
| `git for-each-ref --format=%(refname:strip=2) refs/heads/` | Liệt kê nhánh để chọn. |
| `git symbolic-ref --quiet --short HEAD` | Nhánh mặc định của cache. |
| `git rev-parse --verify --quiet refs/heads/<nhánh>^{commit}` | Kiểm tra nhánh tồn tại. |
| `git rev-list -1 --first-parent --before=<thời điểm> refs/heads/<nhánh> --` | Commit cuối cùng trước một thời điểm, tức snapshot C_START hoặc C_END. `--first-parent` bỏ qua commit của nhánh feature đã merge. `--before` lọc theo committer date. |
| `git show -s --format=%H%x00%cI%x00%an%x00%ae%x00%s <sha> --` | Đọc sha, ngày commit, tác giả, tiêu đề của một commit. |

## 3. Đọc nội dung để export zip và đếm LOC

| Lệnh | Ý nghĩa |
|---|---|
| `git ls-tree -r -l -z --full-tree <commit>` | Mọi file của một snapshot: mode, sha blob, kích thước, đường dẫn. |
| `git cat-file --batch` | Đọc nhiều blob qua một tiến trình, trả về bytes nguyên bản, giữ thứ tự đầu vào. |
| `git cat-file blob <sha>` | Đọc một blob lẻ. |
| `git cat-file --batch-check` | Kiểm tra hàng loạt `<commit>:<path>` có tồn tại không. Các path chứa `\n` hoặc `\r` được tra riêng bằng `git rev-parse --verify --quiet <commit>:<path>`. |

## 4. Danh sách user trong kỳ

| Lệnh | Ý nghĩa |
|---|---|
| `git -c mailmap.file= -c mailmap.blob=<C_END>:.mailmap log --no-color --format=%x1e%H%x00%P%x00%an%x00%ae%x00%aN%x00%aE%x00%aI C_END ^C_START --` | Mọi commit trong kỳ: sha, các parent (nhiều hơn một là merge), tên/email tác giả gốc (`%an`, `%ae`) và sau `.mailmap` (`%aN`, `%aE`), ngày author. `.mailmap` lấy từ C_END, không lấy từ working tree. |

## 5. Gán tác giả cho dòng thêm/xoá (§7.2 spec gốc)

| Lệnh | Ý nghĩa |
|---|---|
| `git diff-tree -r -z --raw --no-abbrev -M -l0 C_START C_END` | Danh sách file thêm, sửa, xoá, đổi tên giữa hai mốc. `-M` nhận diện đổi tên, `-l0` bỏ giới hạn số file khi dò rename. |
| `git diff -U0 --diff-algorithm=myers --indent-heuristic --no-color --no-ext-diff --no-textconv --text --no-renames <blob_cũ> <blob_mới>` | Chỉ đọc header `@@` để biết các khối dòng bị đổi (hunk). |
| `git blame --line-porcelain --root --no-ignore-revs-file --no-textconv -w -M -C -L a,b C_START..C_END -- <file>` | Blame xuôi: dòng thêm do commit nào, nên do ai. `-w` bỏ qua đổi khoảng trắng, `-M -C` phát hiện dòng bị dời hoặc copy. |
| `git blame ... -w -L a,b C_START..C_END -- <file>` (không `-M -C`) | Blame xuôi lần hai cho riêng dòng mà lần đầu trả về boundary (D22), và cho bước truy vết merge (D23). |
| `git blame --reverse ... -L a,b C_START..C_END -- <file>` | Blame ngược: dòng cũ biến mất ở commit nào. |
| `git --literal-pathspecs rev-list --topo-order --ancestry-path --reverse <since> ^<until> -- <path>` | Commit **đầu tiên** chạm file sau một mốc. Dùng để xác định người xoá dòng, kể cả qua merge. |
| `git --literal-pathspecs rev-list --topo-order C_END ^C_START -- <path>` | Commit chạm file trong kỳ (commit đầu tiên trong kết quả là commit cuối cùng chạm file). Dùng cho file binary, symlink, quá lớn không blame theo dòng được, và cho việc tìm người đổi tên file (`--reverse`). |
| `git merge-base --is-ancestor A B` | A có phải tổ tiên của B không (mã thoát 0/1). Cần khi truy vết dòng xoá qua merge. |
| `git merge-base --all A B` | Các điểm gặp nhau của hai nhánh, dùng cho cùng mục đích. |

Blame được chia lô khi có quá nhiều khoảng `-L` trong một lệnh.

## 6. Nhận xét về hiệu năng

Đo ngày 2026-10-29 trên repo `deepseek-harness`, kỳ 2026-08-21..2026-09-04 (2.152 commit, 614 merge):

| Loại lệnh | Số lần gọi | Thời gian cộng dồn | Mỗi lần |
|---|---|---|---|
| `rev-list --ancestry-path --reverse` | 23.437 | 1.041 s | 44 ms |
| `blame --reverse` | 20.342 | 874 s | 43 ms |
| `blame` xuôi (không `-M -C`) | 19.376 | 766 s | 40 ms |
| `blame` xuôi (`-M -C`) | 2.574 | 652 s | 253 ms |
| `diff` | 1.692 | 65 s | 38 ms |
| `merge-base --is-ancestor` | 1.756 | 64 s | 36 ms |
| `merge-base` | 647 | 23 s | 36 ms |

(Thời gian cộng dồn lớn hơn thời gian thực vì các luồng chạy song song.) Chi phí chủ yếu là khởi động tiến trình `git` trên Windows (~25–40 ms mỗi lệnh), không phải khối lượng dữ liệu. Các lệnh `blame` và `rev-list --ancestry-path` dày đặc nhất đến từ thuật toán D23 (dòng bị xoá qua merge commit phải được lần ngược qua từng parent). Chi tiết quyết định ở [DECISIONS.md](DECISIONS.md) (D42) và báo cáo [test-reports/perf-parallel-20261029.md](test-reports/perf-parallel-20261029.md).
