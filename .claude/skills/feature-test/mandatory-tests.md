# Danh sách test bắt buộc (trích spec gốc)

Mỗi mục phải có ít nhất một hàm test tương ứng. Khi viết spec xử lý, gán TC ID cho từng mục và ghi ID vào cột cuối.

## A. Classifier — §6.4 (spec `classifier`)
Mỗi ngôn ngữ: Python, JavaScript, TypeScript, Java, C#, Go, SQL, HTML, CSS.
Mỗi ngôn ngữ phủ đủ các trường hợp (ô "—" nghĩa là ngôn ngữ không có khái niệm đó):

| Trường hợp | Py | JS | TS | Java | C# | Go | SQL | HTML | CSS |
|---|---|---|---|---|---|---|---|---|---|
| Dòng trống / chỉ khoảng trắng → không | x | x | x | x | x | x | x | x | x |
| Comment một dòng → không | `#` | `//` | `//` | `//` | `//` | `//` | `--` | — | — |
| Block comment nhiều dòng → không | `'''` comment | `/* */` | `/* */` | `/* */` | `/* */` | `/* */` | `/* */` | `<!-- -->` | `/* */` |
| Code + comment cuối dòng → có | x | x | x | x | x | x | x | x | x |
| Chuỗi chứa `//` hoặc `#` → có | x | x | x | x | x | x | x | x | x |
| Docstring / JSDoc theo `count_docstrings` | `"""` | JSDoc | JSDoc | Javadoc | `///` | — | — | — | — |

Thêm:
- `len(classify_lines(...))` == số dòng theo git (`split_lines`, PLAN D8) — gồm file có dòng trống đầu/cuối, CRLF, `\r` đơn, form feed, file không có newline cuối.
- Chỉ thị tiền xử lý (`Comment.Preproc`/`PreprocFile`) là code, shebang không (PLAN D7).
- File không nhận diện được lexer → bỏ qua, không đếm.
- File > `max_file_size_kb` → bỏ qua + cảnh báo.
- Cache theo blob SHA: cùng nội dung chỉ phân tích một lần.

## B. Snapshot — §3.1, M2 (spec `snapshot`)
- C_START/C_END đúng theo múi giờ `Asia/Bangkok` (commit sát mốc 00:00:00 và 23:59:59, cả hai phía).
- Không nhập giờ → start 00:00:00, end 23:59:59.
- `start >= end` → lỗi, không chạy.
- Không có commit trước start → C_START rỗng, loc_start = 0.
- Không có commit trước end → lỗi "Không có dữ liệu trong khoảng thời gian".
- Theo first-parent (commit trên nhánh feature đã merge không được chọn làm snapshot).
- Zip export start / end (tất cả user) đúng nội dung, áp bộ lọc mục 9, giữ nguyên kiểu xuống dòng.

## C. Identity — §3.5, M3 (spec `identity`)
- Nhiều email cùng người qua `identities.yaml`.
- `.mailmap` của repo.
- Email noreply `12345+login@users.noreply.github.com` → `login`.
- Email noreply GitHub + email công ty gộp về cùng account (§14).
- Mặc định: email chữ thường.
- Thứ tự ưu tiên identities.yaml > .mailmap > GitHub API > email.
- GitHub API được mock, cache email → login.
- Bot: `[bot]`, `dependabot`, `renovate`, `github-actions`.
- Tác giả = author, không phải committer.

## D. Tích hợp — §14 (specs `attribution`, `builder`, `pipeline`)
Repo mẫu trong `conftest.py`:
1. Trước start — `admin` tạo `app.py`: 10 dòng code, 3 dòng comment, 2 dòng trống.
2. Trong kỳ — `alice` thêm 5 dòng code + 2 dòng comment vào `app.py`.
3. Trong kỳ — `bob` tạo `util.py`: 8 dòng code.
4. Trong kỳ — `alice` xóa 2 dòng code gốc của `admin` trong `app.py`.
5. Trong kỳ — `bob` xóa 1 dòng code gốc khác của `admin` trong `app.py`.
6. Sau end — `alice` thêm 100 dòng code (không được tính).

| Trường hợp | loc_start | loc_end |
|---|---|---|
| Tất cả user | 10 | 20 |
| Chỉ alice | 10 | 13 (không có `util.py`; dòng bob xóa vẫn còn) |
| Chỉ bob | 10 | 17 (`app.py` không có thay đổi của alice) |
| alice + bob | 10 | 20 |

Theo user: alice `added_code=5, deleted_code=2, net=+3`; bob `added_code=8, deleted_code=1, net=+7`.

Thêm:
- Đổi tên file trong kỳ không bị tính là xóa + thêm.
- start trước commit đầu tiên → loc_start = 0.
- Block comment nhiều dòng được thêm vào → không tăng LOC.
- Quy tắc cấp file §7.4: file user khác tạo → không có; file user chọn xóa hoàn toàn → không có; file user khác xóa → giữ như start; rename theo người đổi tên.
- Kiểm tra chéo §8.3: lệch > 0.5% → có cảnh báo.

## E. Đầu ra — §12, M5 (specs `report`, `pipeline`, `cli-analyze`)
- Đủ file: `start_*.zip`, `end_*.zip`, `loc_report.xlsx` (6 sheet đúng tên), 3 CSV UTF-8 có BOM, `warnings.csv`, `manifest.json`; `run.log` ở `<out>/run.log` (ngoài thư mục kết quả).
- Tên thư mục kết quả và `user-tag` (`all`, tên user, `multi-<n>users`).
- Không có token trong bất kỳ file đầu ra / log nào (test bằng token giả và grep toàn bộ thư mục đầu ra + cache).
- Chạy hai lần cùng input → mọi file trong thư mục kết quả trùng SHA-256, trừ `manifest.json` (bằng nhau sau khi bỏ `generated_at`); `run.log` không so sánh.

## F. Giao diện — §10, §13 M6 (specs `screen-input`, `screen-result`, `screen-identity`)
- E2E AppTest trên repo §14: tất cả 10/20, alice 10/13, bob 10/17, alice+bob có xuất riêng 10/20 với 3 zip end.
- "Tải được mọi file": tập tên file của `download_items(result)` = `os.listdir(out_dir)`, bytes khớp; AppTest có đủ nút tải (không disabled).
- `start ≥ end`, "Chọn user" với 0 user, chưa tải repo → nút PHÂN TÍCH disabled kèm lý do tiếng Việt.
- Token (ô password) không có trong cây phần tử AppTest, `run.log`, thư mục kết quả, cache repo, `github_logins.json`.
- Trong lúc chạy phân tích mọi ô nhập / nút tải / nút lưu bị khóa; sau đó bật lại.
- Gộp account trên UI ghi `identities.yaml` và danh sách user cập nhật ngay.
