# LOC Counter

Đếm LOC (chỉ dòng code, bỏ comment và dòng trống) trên Git repository giữa hai thời điểm, theo ngôn ngữ và theo user.
Spec đầy đủ: [spec_count_LOC.md](spec_count_LOC.md).

## Cài đặt
```bash
uv sync
```

## Đếm LOC một thư mục
```bash
uv run loc-counter count <thư-mục> [--config config.yaml]
```

## Liệt kê user có commit trong kỳ
```bash
uv run loc-counter users --repo <URL hoặc đường dẫn> --start 2026-01-01 --end 2026-01-31 \
  [--branch main] [--start-time HH:MM] [--end-time HH:MM] [--tz Asia/Bangkok] \
  [--identities identities.yaml] [--token-env GITHUB_TOKEN] [--exclude-bots] [--json]
```
- Repo (kể cả repo local) được clone dạng bare vào `~/.loc_counter/repos/`; lần sau chỉ fetch. Repo local của bạn không bị thay đổi.
- Không nhập giờ: start `00:00:00`, end `23:59:59`; nhập `HH:MM`: start `HH:MM:00`, end `HH:MM:59`.
- Token GitHub chỉ đọc từ biến môi trường (`--token-env`), chỉ dùng với URL `https://`, không bao giờ được ghi ra log hay file.
- URL repo không được chứa thông tin xác thực: URL `https://` có `user@` / `user:pass@` và URL khác (`ssh://`, `git://`, dạng scp `user:pass@host:path`…) có mật khẩu đều bị từ chối; `ssh://git@host/...`, `git@host:o/r.git` vẫn dùng được. URL clone mặc định của Azure DevOps (`https://org@dev.azure.com/...`) cần bỏ phần `org@`. Cú pháp `<transport>::<địa chỉ>` (`ext::`, `fd::`) không được hỗ trợ. Nếu trước đây (bản trước 2026-10-25) bạn từng nhập URL `ssh://user:pass@...`, hãy xóa thư mục `~/.loc_counter/repos/` vì cấu hình repo cache cũ có thể còn giữ mật khẩu.
- Số commit không tính merge commit; tác giả là **author** (không phải committer).

### Gộp account
Thứ tự ưu tiên: `identities.yaml` → `.mailmap` của repo (tại commit end) → GitHub API (repo trên github.com và có token; kết quả email → login được cache ở `~/.loc_counter/github_logins.json`) → email chữ thường. Email `12345+login@users.noreply.github.com` → `login`.
Xem mẫu [identities.example.yaml](identities.example.yaml). Bot (`[bot]`, `dependabot`, `renovate`, `github-actions`) vẫn hiện trong danh sách với nhãn `bot`; `--exclude-bots` ẩn chúng.

## Định nghĩa LOC
Một dòng là **dòng code** khi chứa ít nhất một token không phải comment và không phải khoảng trắng theo lexer Pygments của ngôn ngữ.
- Docstring Python (`String.Doc`) không tính, trừ khi `count_docstrings: true`.
- JSDoc / Javadoc (`/** ... */`) là comment theo Pygments nên **luôn không tính**, kể cả khi `count_docstrings: true`.
- Chỉ thị tiền xử lý (`#include`, `#define`, `#if`, `#region`…) **là code**; shebang `#!` không tính.
- File không có lexer, hoặc lexer thuộc `exclude_languages` (mặc định: `Text only`, `Markdown`, `reStructuredText`), không được đếm.
- Dòng được tách như git: theo `\n` (CRLF được chấp nhận); các ký tự như form feed không tạo dòng mới.
- Chuỗi nhiều dòng không phải docstring (vd. `SQL = """..."""`) là code. Vì vậy kết quả có thể cao hơn `cloc` với Python: `cloc` coi mọi chuỗi triple-quote là comment.

## Cấu hình
Sao chép [config.example.yaml](config.example.yaml) thành `config.yaml` rồi truyền `--config config.yaml`.

## Giới hạn của export end theo user
Export end khi chọn một hoặc vài user = source tại C_START + **chỉ** các dòng do các user đó thêm / xóa trong kỳ, dựng theo từng dòng (không cherry-pick / rebase).
- **Bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build / chạy được.**
- Dòng bị nhiều user sửa liên tiếp chỉ gán được cho người sửa cuối (có cảnh báo `sequential_edit`); hunk có thay đổi của nhiều user có cảnh báo `multi_user_hunk`.
- Dòng chỉ đổi khoảng trắng / kiểu xuống dòng (thụt lề, CRLF→LF) giữ bản C_START trong mọi bản dựng theo user. Vì vậy "Tất cả user" luôn dùng thẳng C_END; chỉ khi bật "Loại trừ bot" và có bot commit trong kỳ mới dựng bằng cách ghép dòng.
- Trong một đoạn thay đổi, dòng cũ được giữ đứng trước dòng mới được thêm → thứ tự dòng có thể khác bản gốc.
- Dòng bị dời (trong file hoặc sang file khác) được gán cho người dời (`moved_lines`).
- File đổi tên lấy tên mới chỉ khi người đổi tên nằm trong nhóm user được chọn; nếu tên được chọn bị bộ lọc loại, file không có trong export.
- File binary / quá lớn được xử lý theo cả file: người sửa cuối trong kỳ thuộc nhóm chọn → bản C_END, ngược lại bản C_START.
- Commit trên nhánh tách ra trước ngày start nhưng được merge vào trong kỳ vẫn tính là "trong kỳ".
- Đường dẫn xung đột khi giải nén (file và thư mục cùng tên, tên chỉ khác hoa thường) vẫn được giữ trong zip, có cảnh báo `path_conflict`.
- Tên hợp lệ trong git nhưng có thể không giải nén đúng trên Windows (tên thiết bị `CON`, `NUL.py`…; tên kết thúc bằng `.` hoặc khoảng trắng; ký tự `<>"|?*`) vẫn được giữ trong zip và đếm LOC, có cảnh báo `windows_path`. Nếu export có cả `a.py.` và `a.py`, giải nén trên Windows sẽ cho một file đè file kia (chỉ `a.py.` có cảnh báo); số LOC trong báo cáo không bị ảnh hưởng vì được đếm từ nội dung zip.

## Phân tích LOC trong kỳ
```bash
uv run loc-counter analyze --repo <URL hoặc đường dẫn> --start 2026-01-01 --end 2026-01-31 \
  --out ./out [--branch main] [--start-time HH:MM] [--end-time HH:MM] [--tz Asia/Bangkok] \
  [--user alice --user bob] [--separate-users] [--exclude-bots] [--attribution line|last-commit] \
  [--loc-end net|added] [--config config.yaml] [--identities identities.yaml] \
  [--token-env GITHUB_TOKEN] [--json]
```
- Không có `--user` = **Tất cả user** (export end = C_END). Nhiều `--user` = một bản gộp các user đó; `--separate-users` thêm một zip riêng cho từng user.
- `--user` khớp chính xác account, nếu không có thì khớp không phân biệt hoa thường (khi chỉ có đúng một account khớp). Bot được chọn tường minh vẫn được tính dù có `--exclude-bots`; `--exclude-bots` chỉ loại bot khỏi "Tất cả user".
- `--attribution` chọn cách gán tác giả (cũng là radio "Cách gán tác giả" ở giao diện web): `line` (mặc định) gán từng dòng thêm/xóa cho người viết/xóa dòng đó bằng `git blame`; `last-commit` đơn giản và nhanh hơn: **toàn bộ** thay đổi của một file trong kỳ (dòng thêm, dòng xóa) và bản C_END của file thuộc về **người sửa cuối cùng** file đó. Với `last-commit`, chọn user A chỉ có các file mà A sửa cuối; file người khác sửa cuối giữ bản C_START. Lựa chọn được ghi ở `manifest.json` (`options.attribution_mode`) và sheet `Tong_quan`.
- `--loc-end` chọn cách tính LOC end (cũng là radio "Cách tính LOC end" ở giao diện web): `net` (mặc định) đếm LOC trên bản export end, xấp xỉ LOC start + tổng code ròng (code thêm − code xóa); `added` báo LOC end = LOC start + **tổng code thêm** (không trừ code xóa — đo khối lượng code viết thêm). Với `added`, LOC đếm trên export vẫn được ghi (hàng `LOC end đếm trên export`; `manifest.json` giữ `totals.loc_end` là LOC đếm trên export, LOC end theo cách tính đã chọn ở `totals.reported_loc_end`) và kiểm tra chéo vẫn so với LOC đếm trên export; bảng theo ngôn ngữ / theo file luôn đếm trên export. Bảng tổng (stdout, sheet `Tong_quan`, `manifest.json` `totals`, màn hình kết quả) luôn có thêm tổng code thêm và tổng code xóa.
- Tiến độ (`[1/5] Export start…` … `[5/5] Tạo báo cáo…`) và log in ra stderr; stdout là bảng tóm tắt, hoặc JSON khi có `--json`.
- Mã thoát: `0` thành công (kể cả có cảnh báo hay kiểm tra chéo lệch), `1` lỗi (thông báo tiếng Việt), `2` sai tham số, `130` khi bấm Ctrl+C.

### Kết quả
Mỗi lần chạy ghi thư mục `<out>/<repo>_<nhánh>_<start>_<end>_<user-tag>/` (ngày `YYYY-MM-DD`, thêm `THHMM` khi có nhập giờ; user-tag `all`, tên user, hoặc `multi-<n>users`):

| File | Nội dung |
|---|---|
| `start_<ngày>_<sha7>.zip` | source tại C_START sau bộ lọc (`..._empty.zip` khi không có commit trước start) |
| `end_<ngày>_<user-tag>.zip` | export end (và zip riêng từng user nếu `--separate-users`) |
| `loc_report.xlsx` | sheet `Tong_quan`, `Theo_ngon_ngu`, `Theo_user`, `Theo_file`, `Theo_tuan`, `Theo_PR`, `Canh_bao` |
| `loc_by_user.csv`, `loc_by_language.csv`, `loc_by_file.csv`, `loc_by_pr.csv` | UTF-8 có BOM, phân cách `,` |
| `warnings.csv` | mọi cảnh báo, kèm phạm vi (`start`, `end:<tag>`, `gán tác giả`, `kiểm tra chéo`, `định danh`) |
| `manifest.json` | tham số, commit C_START / C_END, cấu hình đã dùng, tổng LOC, kiểm tra chéo, danh sách zip |

- `run.log` (log chi tiết mức INFO, token đã che) ghi ở `<out>/run.log`, **ngoài** thư mục kết quả, và bị ghi đè mỗi lần chạy. Không chạy song song hai lần phân tích với cùng `--out` (hai lần chạy cùng ghi một `run.log`).
- Chạy lại với cùng tham số và cùng `--out` sẽ **thay toàn bộ** thư mục kết quả cũ. Tool chỉ thay thư mục có `manifest.json` của chính nó; thư mục khác trùng tên → báo lỗi, không xóa gì.
- Hai nhánh có tên chỉ khác nhau ở ký tự đặc biệt (`feature/x` và `feature_x`) hoặc ở hoa thường (trên Windows) cho cùng tên thư mục kết quả: lần chạy sau thay lần chạy trước.
- Thư mục `.loc-tmp-*` / `.loc-old-*` trong `<out>` là thư mục làm việc tạm. Nếu tiến trình bị dừng đột ngột (tắt máy, kill), chúng có thể còn sót lại: hãy xóa tay khi không còn lần chạy nào đang dùng `--out` đó.
- Cùng repo, nhánh, kỳ, user và cấu hình → mọi file trong thư mục kết quả giống hệt nhau từng byte, trừ `generated_at` trong `manifest.json`.
- Excel với locale dùng `;` làm phân cách (vd. tiếng Việt, Đức) có thể mở CSV thành một cột: dùng `Data → From Text/CSV` và chọn phân cách `,`, hoặc mở `loc_report.xlsx`.
- Trên Windows chưa bật long path, đường dẫn kết quả dài hơn 259 ký tự bị từ chối trước khi phân tích: chọn `--out` ngắn hơn.

### LOC theo PR của từng user
Sheet `Theo_PR` và `loc_by_pr.csv` thống kê **commit, code thêm, code xóa, code ròng** theo từng cặp (PR, user); màn hình kết quả có mục "Theo PR của từng user". Cùng định nghĩa với bảng theo user (§8.2): với mỗi user, tổng các dòng PR = số liệu ở `Theo_user`.
- **PR được nhận diện từ lịch sử git**, không gọi GitHub API: (1) merge commit `Merge pull request #N from …` — PR gồm các commit của nhánh được merge và chính merge commit (tiêu đề = dòng đầu của nội dung merge commit); (2) commit squash có đuôi `(#N)` ở tiêu đề (`Thêm login (#12)`) — PR là chính commit đó; (3) commit còn lại (push thẳng, rebase-merge không có `#N`, merge kiểu GitLab…) thuộc nhóm **"(Không thuộc PR)"**.
- PR chỉ được tính khi merge / squash commit nằm trong kỳ. PR lồng nhau (PR vào nhánh, nhánh vào PR khác) → commit thuộc PR trong cùng nhất. Ngày merge = author date của merge / squash commit theo múi giờ đã chọn.
- Dòng do merge commit giải quyết xung đột được tính cho PR của merge đó (§16); dòng xóa tính cho PR chứa commit đã xóa dòng.

### Kiểm tra chéo
`loc_start + Σ code ròng của các user được tính ≈ loc_end`. Lệch quá 0.5 % (so với `loc_end`) → cảnh báo `cross_check` (không phải lỗi). Lệch là **đúng theo định nghĩa** khi trong kỳ có thay đổi không được gán cho dòng nào, ví dụ:
- đổi tên file không phải source thành source (`notes.txt` → `notes.py`) hoặc chuyển file vào / ra thư mục bị loại (`vendor/`, `node_modules/`…);
- file ↔ symlink, binary ↔ text, file vượt / xuống dưới ngưỡng `max_file_size_kb`.

Khi C_START rỗng (start trước commit đầu tiên), mọi dòng đều là dòng thêm trong kỳ; file có nhiều người cùng sửa thường có cảnh báo `multi_user_hunk` — đây là bình thường.

### Giải nén zip trên Windows
LOC luôn được đếm từ chính nội dung ghi vào zip, nên không phụ thuộc vào việc giải nén. Khi giải nén trên Windows, các file có cảnh báo `path_conflict` (tên chỉ khác hoa thường, file và thư mục cùng tên) hoặc `windows_path` (`CON`, `NUL.py`, tên kết thúc bằng `.`…) có thể bị đè hoặc không giải nén được.

## Giao diện (Streamlit)
```bash
uv run streamlit run src/loc_counter/app.py --server.address localhost --browser.gatherUsageStats false
```
Mở trình duyệt tại `http://localhost:8501`. **Nên giữ `--server.address localhost`**: mặc định Streamlit nghe trên mọi địa chỉ mạng, khi đó máy khác trong mạng có thể mở giao diện, đọc repo local và dùng thư mục đầu ra của bạn.

1. **[1] Repository** — nhập URL hoặc đường dẫn local (dấu nháy bao quanh khi dán "Copy as path" được bỏ tự động), token GitHub nếu cần (ô ẩn, chỉ giữ trong phiên), bấm **Tải repo** rồi chọn nhánh. Đổi nguồn hoặc token sau khi tải → phải bấm Tải repo lại.
2. **[2] Thời điểm thống kê** — mặc định từ ngày 1 của tháng hiện tại đến hôm nay (theo `Asia/Bangkok`); giờ để trống = không nhập giờ. Snapshot start / end hiện ngay khi đổi ngày, giờ, múi giờ hoặc nhánh.
3. **[3] Chọn user** — "Tất cả user" hoặc "Chọn user" (ô tìm theo account, tên, email). Ở giao diện, **"Loại trừ bot" ẩn bot và bỏ bot khỏi lựa chọn** (khác CLI, nơi bot chọn tường minh vẫn được tính).
   - **Quản lý gộp account**: sửa cột *Account key* rồi bấm Lưu → ghi vào file ở ô "File identities" (mặc định `./identities.yaml`, chưa có thì được tạo). Để trống một ô = bỏ quy tắc của dòng đó (account quay về cách gộp tự động). Quy tắc khác trong file được giữ nguyên. Đổi file / kỳ / nhánh khi chưa lưu sẽ bỏ các sửa đổi chưa lưu.
4. **Tùy chọn nâng cao** — 8 bộ lọc của §9 (mặc định như `config.example.yaml`); ô "File cấu hình" + **Nạp** điền các ô từ một `config.yaml` (cả múi giờ).
5. **Thư mục đầu ra** (mặc định `./output`, tương đối thư mục chạy lệnh) → **PHÂN TÍCH**. Trong lúc chạy mọi ô bị khóa và có thanh tiến độ 5 bước.

Kết quả: bốn số chính, kiểm tra chéo, bảng theo ngôn ngữ / user (+ dòng Tổng), biểu đồ code ròng theo tuần, cảnh báo, chi tiết theo file (lọc theo đường dẫn, ngôn ngữ, chỉ file có LOC thay đổi hoặc đổi tên) và **nút tải cho mọi file** của thư mục kết quả (zip start / end / riêng từng user, Excel, 3 CSV, `warnings.csv`, `manifest.json`). Đổi tham số sau khi chạy → kết quả cũ vẫn hiện kèm ghi chú.

Lưu ý:
- Bấm PHÂN TÍCH **không fetch lại** repo: kết quả khớp snapshot đang hiển thị; muốn lấy commit mới hãy bấm Tải repo lại.
- Hai phiên trình duyệt cùng một tiến trình Streamlit không thể dùng chung một thư mục đầu ra cùng lúc (phiên sau báo "đang được một phiên phân tích khác sử dụng"). Khóa này **không** chặn CLI `analyze` chạy song song ở tiến trình khác với cùng `--out` — đừng làm vậy (hai bên ghi đè `run.log` và thư mục kết quả của nhau).
- Bấm Stop của Streamlit giữa lúc phân tích: thư mục tạm được dọn, `run.log` có dòng lỗi; thư mục kết quả cũ (nếu có) giữ nguyên.
