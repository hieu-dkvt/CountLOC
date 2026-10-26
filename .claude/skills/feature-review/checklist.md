# Checklist review LOC Counter

## 1. Đúng spec
- [ ] Mọi bước "Luồng xử lý" trong spec xử lý đều có trong code, đúng thứ tự.
- [ ] Chữ ký hàm/class công khai đúng mục "Giao diện"; không có API công khai ngoài spec.
- [ ] Giá trị mặc định khớp spec gốc (mục 3.1 timezone/giờ, mục 9 bộ lọc, mục 16).
- [ ] Không thay đổi định nghĩa mục 3, thuật toán mục 6 (classifier), mục 7 (attribution/builder).
- [ ] Lệnh git đúng như spec (`--first-parent`, `--before`, `-w -M -C --line-porcelain`, `--reverse`, `--ancestry-path`, `diff -M`).
- [ ] Mọi TC trong spec có test, và test thật sự kiểm điều TC mô tả (assertion theo giá trị cụ thể).

## 2. Nghiệp vụ dễ sai
- [ ] Classifier: tokenize cả file (không từng dòng); lexer tạo với `stripnl=False`; số phần tử kết quả == số dòng theo git (`split_lines`, PLAN D8) kể cả CRLF, `\r` đơn, dòng trống đầu/cuối, `\f`/`\v`; `Token.Comment.*` (trừ `Comment.Preproc`/`PreprocFile` — D7), khoảng trắng, `String.Doc` (khi `count_docstrings=False`) không đánh dấu.
- [ ] Mọi nơi đếm/ghép dòng (counter, attribution, builder) dùng cùng `split_lines` để chỉ số dòng khớp `git diff`/`git blame`.
- [ ] Snapshot: thời điểm chuyển sang ISO 8601 có offset; end không nhập giờ = 23:59:59; C_START rỗng xử lý riêng (không gọi `C_START..C_END`).
- [ ] Attribution: dòng boundary (`^`) không phải dòng thêm; commit xóa = commit cũ nhất trong `--ancestry-path`; file bị xóa hoàn toàn; tác giả = author; merge commit không tính vào số commit.
- [ ] Builder: đúng quy tắc cấp file §7.4 (tạo mới, xóa, rename theo người đổi tên); file rỗng → không tạo.
- [ ] Số liệu: `added_code` phân loại theo file tại C_END, `deleted_code` theo file tại C_START; LOC luôn đếm trên chính thư mục export.
- [ ] Identity: thứ tự ưu tiên identities.yaml > .mailmap > GitHub API > email; noreply → login; email chữ thường; bot.

## 3. Bảo mật
- [ ] Token không xuất hiện trong: log, exception message, `manifest.json`, báo cáo, `config.yaml`, `identities.yaml`, **config của bare repo cache** (không clone bằng URL chứa token; dùng header/askpass qua env).
- [ ] URL có credential được che khi log hoặc hiển thị.
- [ ] `subprocess` không dùng `shell=True`; tham số từ người dùng (nhánh, đường dẫn) không thể thành option git (dùng `--` / `--end-of-options` khi cần).
- [ ] Zip/export không ghi ra ngoài thư mục đích (path traversal từ tên file trong repo).

## 4. Lỗi & log
- [ ] Lỗi cho người dùng bằng tiếng Việt, dễ hiểu; lỗi git kèm lệnh (đã che token) trong log chi tiết.
- [ ] `logging` mức INFO mặc định, ghi `<out>/run.log`; không dùng `print` cho log.
- [ ] Không nuốt exception im lặng; cảnh báo nghiệp vụ đi vào `warnings.csv`.

## 5. Tái lập & encoding
- [ ] Mọi danh sách đầu ra sắp xếp ổn định (không phụ thuộc thứ tự set/dict/filesystem/process pool).
- [ ] Zip: thứ tự entry cố định, timestamp cố định, đường dẫn POSIX.
- [ ] Timezone tường minh (`zoneinfo` + `tzdata`), không dùng giờ máy ngầm định.
- [ ] Đọc UTF-8 → `latin-1` → coi binary + cảnh báo; export ghi bytes gốc, giữ nguyên kiểu xuống dòng.

## 6. Windows
- [ ] `pathlib` cho đường dẫn đĩa; không ghép chuỗi với `/` hoặc `\`.
- [ ] Không phụ thuộc `core.autocrlf` (đọc blob từ git object, không checkout).
- [ ] Đường dẫn Unicode/khoảng trắng (`-z`, `core.quotepath=off`).
- [ ] File tạm/thư mục tạm được dọn; không giữ handle file mở (Windows không xóa được file đang mở).

## 7. Chất lượng code
- [ ] Type hint đầy đủ cho hàm công khai; docstring ngắn tiếng Việt.
- [ ] Ranh giới module đúng mục 5 spec gốc (git chỉ gọi trong `git_repo.py`, UI không chứa nghiệp vụ, ...).
- [ ] Không thư viện ngoài mục 4 (trừ `tzdata`, dev tools) khi chưa được duyệt.
- [ ] Không code chết, không TODO không có ghi chú trong spec.
- [ ] `ruff check` sạch.

## 8. Hiệu năng (bắt buộc từ M7, khuyến nghị trước đó)
- [ ] Cache classifier theo blob SHA; không phân tích lại cùng blob.
- [ ] Đọc nhiều blob qua `git cat-file --batch`, không spawn một process mỗi file.
- [ ] Việc nặng CPU chạy `ProcessPoolExecutor`, kết quả gộp theo thứ tự xác định.

## 9. Màn hình Streamlit (spec `screen-*`)
- [ ] Bố cục, nhãn, thứ tự thành phần đúng spec màn hình và mục 10 spec gốc; nhãn tiếng Việt.
- [ ] Mặc định: start = ngày đầu tháng, end = hôm nay, timezone `Asia/Bangkok`, radio "Tất cả user".
- [ ] Validate: start < end, chọn ít nhất 1 user khi "Chọn user" → nút "Phân tích" bị vô hiệu kèm thông báo.
- [ ] Khóa ô nhập khi đang chạy; thanh tiến độ đủ 5 bước.
- [ ] Token chỉ trong `st.session_state`, ô nhập kiểu password, không echo.
- [ ] Nghiệp vụ nằm trong `pipeline`/module lõi, `app.py` chỉ gọi; có test `AppTest`.
- [ ] Ghi chú "bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được" hiển thị khi chọn user.
