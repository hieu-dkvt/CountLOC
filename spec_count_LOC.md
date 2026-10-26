# SPEC: Ứng dụng đếm LOC (Lines of Code) trên Git repository

> **Hướng dẫn cho AI agent (Claude Code)**
> - Đọc toàn bộ tài liệu này trước khi viết code.
> - Triển khai theo thứ tự các Milestone ở mục 13. Hoàn thành và chạy test của milestone hiện tại trước khi sang milestone tiếp theo.
> - Không tự ý thay đổi các định nghĩa ở mục 3 và thuật toán ở mục 6, 7. Nếu gặp điểm mơ hồ hoặc mâu thuẫn, dừng lại và hỏi người dùng.
> - Mọi giá trị mặc định ghi trong spec là bắt buộc, trừ khi người dùng yêu cầu khác.
> - Viết code có type hint, docstring ngắn, và unit test cho mọi module lõi.
> - Ngôn ngữ giao diện (UI) và báo cáo: **tiếng Việt**. Tên biến, hàm, file: **tiếng Anh**.

---

## 1. Mục tiêu

Xây dựng ứng dụng cho phép người dùng:

1. Chọn một Git repository và một nhánh.
2. Chỉ định **thời điểm start** và **thời điểm end** để thống kê.
3. Chọn **một, nhiều, hoặc tất cả user** (tác giả commit).
4. Xuất (export) toàn bộ source tại start và tại end theo quy tắc ở mục 3.
5. Đếm LOC **chỉ tính dòng code** (bỏ dòng comment và dòng trống) bằng cách tự phân tích nội dung file, **không** dùng số liệu `git --numstat` / `--shortstat`.
6. Xuất báo cáo LOC theo ngôn ngữ và theo user.

---

## 2. Phạm vi

### Trong phạm vi (MVP)
- Repo nguồn: đường dẫn repo local, hoặc URL Git (GitHub HTTPS, có hỗ trợ token cho repo private).
- Một nhánh mỗi lần phân tích.
- Giao diện web bằng Streamlit + giao diện dòng lệnh (CLI).
- Xuất file zip source, báo cáo Excel, CSV, JSON.

### Ngoài phạm vi (chưa làm)
- Nhiều repo trong một lần phân tích.
- Đăng nhập, phân quyền người dùng app.
- Lưu lịch sử báo cáo vào database.
- Lên lịch chạy tự động.

---

## 3. Định nghĩa (BẮT BUỘC)

### 3.1. Thời điểm và snapshot
- Người dùng nhập `start` và `end` dạng ngày (bắt buộc) và giờ (tùy chọn).
- Múi giờ mặc định: `Asia/Bangkok` (UTC+7). Cho phép đổi trong UI.
- Nếu không nhập giờ: `start` = `00:00:00` của ngày start, `end` = `23:59:59` của ngày end.
- Ràng buộc: `start < end`. Nếu sai, hiển thị lỗi và không chạy.
- **C_START** = commit cuối cùng trên nhánh (theo first-parent) có commit date ≤ `start`.
  ```bash
  git rev-list -1 --first-parent --before="<start ISO8601>" <branch>
  ```
- **C_END** = commit cuối cùng trên nhánh (theo first-parent) có commit date ≤ `end`.
- Nếu không có commit nào trước `start`: C_START = rỗng (snapshot start không có file, LOC = 0).
- Nếu không có commit nào trước `end`: báo lỗi "Không có dữ liệu trong khoảng thời gian".
- Commit "trong kỳ" = các commit nằm trong `C_START..C_END` (có trong C_END, không có trong C_START).

### 3.2. Export start
- Toàn bộ source của nhánh tại **C_START** (sau khi áp bộ lọc file ở mục 9).

### 3.3. Export end
| Lựa chọn user | Nội dung export end |
|---|---|
| **Tất cả user** | Toàn bộ source của nhánh tại **C_END** |
| **Một hoặc nhiều user** | Source tại C_START **+ chỉ các thay đổi (thêm và xóa) do các user được chọn thực hiện** trong kỳ. Thay đổi của user khác **không** có trong bản này |

- Khi chọn nhiều user: tạo **một bản export gộp** (start + thay đổi của tất cả user được chọn).
- Tùy chọn trong UI: "Xuất riêng từng user" → mỗi user một file zip riêng (mặc định: tắt).

### 3.4. LOC (dòng code)
Một dòng được tính là **dòng code** khi và chỉ khi nó chứa ít nhất một token không phải comment và không phải khoảng trắng, theo lexer của ngôn ngữ tương ứng.

| Loại dòng | Ví dụ | Tính LOC? |
|---|---|---|
| Dòng trống hoặc chỉ khoảng trắng | `    ` | Không |
| Comment một dòng | `// note`, `# note`, `-- note` | Không |
| Dòng nằm trong block comment | `/* ... */`, `<!-- ... -->`, `''' ... '''` dùng làm comment | Không |
| Code kèm comment cuối dòng | `x = 1  # set` | **Có** |
| Code chứa ký tự giống comment trong chuỗi | `url = "http://a.com"` | **Có** |
| Docstring (Python), JSDoc | `"""Mô tả"""` | Theo cấu hình `count_docstrings` (mặc định: **Không**) |

- LOC của một bản export = tổng số dòng code của tất cả file source trong bản export đó.
- **LOC luôn được đếm trên chính thư mục export** (để khớp với file người dùng tải về).

### 3.5. User (account)
- Một user có thể có nhiều cặp (tên, email) trong Git. App phải gộp về một **account key**.
- Thứ tự ưu tiên xác định account:
  1. Bảng ánh xạ thủ công trong file `identities.yaml` (người dùng chỉnh được trong UI).
  2. `.mailmap` của repo nếu có.
  3. GitHub API: `GET /repos/{owner}/{repo}/commits/{sha}` → `author.login` (chỉ khi repo trên GitHub và có token; cache kết quả email → login).
  4. Mặc định: dùng email (chữ thường) làm account key.
- Email dạng `12345+login@users.noreply.github.com` → account key = `login`.
- Danh sách bot mặc định bị loại trừ khỏi danh sách user (vẫn tính vào "Tất cả" trừ khi bật tùy chọn "Loại trừ bot"): tên chứa `[bot]`, `dependabot`, `renovate`, `github-actions`.
- Tác giả commit = **author** (không phải committer).

---

## 4. Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.11+ |
| Quản lý project | `pyproject.toml` (dùng `uv` hoặc `pip`) |
| Làm việc với Git | Gọi lệnh `git` qua `subprocess` (yêu cầu git ≥ 2.30). Dùng `git cat-file --batch` khi đọc nhiều blob |
| Phân loại dòng code | `pygments` |
| Diff | `git diff` hoặc `difflib` |
| GitHub API | `requests` |
| Tổng hợp dữ liệu | `pandas` |
| Xuất Excel | `openpyxl` |
| CLI | `typer` |
| UI | `streamlit` |
| Cấu hình | `pyyaml` |
| Test | `pytest` |
| Song song | `concurrent.futures.ProcessPoolExecutor` |

---

## 5. Cấu trúc project

```
loc-counter/
├── pyproject.toml
├── README.md
├── config.example.yaml
├── identities.example.yaml
├── src/loc_counter/
│   ├── __init__.py
│   ├── config.py          # Đọc cấu hình, giá trị mặc định
│   ├── git_repo.py        # Clone/fetch, rev-list, cat-file, diff, blame
│   ├── snapshot.py        # Xác định C_START, C_END; export start/end (tất cả user)
│   ├── identity.py        # Gộp (tên, email) → account key
│   ├── filters.py         # Bộ lọc file source
│   ├── classifier.py      # Phân loại từng dòng: code hay không
│   ├── attribution.py     # Gán tác giả cho dòng thêm (blame) và dòng xóa (reverse blame)
│   ├── builder.py         # Dựng export end cho user được chọn
│   ├── counter.py         # Đếm LOC trên thư mục export
│   ├── report.py          # Báo cáo Excel, CSV, JSON, manifest
│   ├── pipeline.py        # Điều phối toàn bộ luồng xử lý
│   ├── cli.py             # Lệnh CLI
│   └── app.py             # Giao diện Streamlit
└── tests/
    ├── conftest.py        # Tạo repo Git mẫu để test
    ├── test_classifier.py
    ├── test_snapshot.py
    ├── test_identity.py
    ├── test_attribution.py
    ├── test_builder.py
    └── test_pipeline.py
```

---

## 6. Bộ phân loại dòng (`classifier.py`)

### 6.1. Hàm chính
```python
def classify_lines(content: str, filename: str, count_docstrings: bool = False) -> list[bool]:
    """Trả về is_code[i] cho từng dòng i (0-based) của file."""
```

### 6.2. Thuật toán
1. Chọn lexer bằng `pygments.lexers.get_lexer_for_filename(filename)`. Nếu không tìm được → file không phải source, bỏ qua (không đếm).
2. Tokenize toàn bộ nội dung file (không tokenize từng dòng riêng lẻ, để nhận đúng block comment nhiều dòng).
3. Duyệt token, theo dõi số dòng. Với mỗi phần token trên một dòng:
   - Nếu token thuộc `Token.Comment.*` → không đánh dấu.
   - Nếu token chỉ là khoảng trắng → không đánh dấu.
   - Nếu token thuộc `Token.Literal.String.Doc` và `count_docstrings = False` → không đánh dấu.
   - Ngược lại → `is_code[line] = True`.
4. Số phần tử của kết quả phải bằng số dòng của file (`len(content.splitlines())`).

### 6.3. Hiệu năng
- Cache kết quả theo **Git blob SHA** (cùng nội dung chỉ phân tích một lần). Với file không đến từ Git, dùng SHA-1 của nội dung.
- Bỏ qua file lớn hơn `max_file_size_kb` (mặc định 1024 KB), ghi vào cảnh báo.

### 6.4. Test bắt buộc
Mỗi ngôn ngữ sau có ít nhất 1 test: Python, JavaScript, TypeScript, Java, C#, Go, SQL, HTML, CSS. Mỗi test phủ: dòng trống, comment một dòng, block comment nhiều dòng, code kèm comment cuối dòng, chuỗi chứa `//` hoặc `#`, docstring (nếu ngôn ngữ có).

---

## 7. Dựng export end cho user được chọn (`attribution.py`, `builder.py`)

### 7.1. Nguyên tắc
Không dùng cherry-pick / rebase (sẽ xung đột). Dựng theo **từng dòng** dựa trên so sánh file tại C_START và C_END.

### 7.2. Gán tác giả
- **Dòng thêm** (có trong file tại C_END, không có tại C_START):
  ```bash
  git blame -w -M -C --line-porcelain C_START..C_END -- <path_at_end>
  ```
  Dòng có commit thuộc kỳ → tác giả = author của commit đó (đã gộp account). Dòng boundary (`^`, thuộc C_START hoặc trước) → không phải dòng thêm.
- **Dòng xóa** (có trong file tại C_START, không có tại C_END):
  ```bash
  git blame -w --reverse --line-porcelain C_START..C_END -- <path_at_start>
  ```
  Kết quả cho mỗi dòng là commit `L` cuối cùng mà dòng còn tồn tại. Commit xóa dòng = commit cũ nhất trong `git rev-list --ancestry-path --reverse L..C_END -- <path>`. Tác giả xóa = author của commit đó. Nếu file bị xóa hoàn toàn, commit xóa = commit đã xóa file.
- Nếu C_START rỗng: mọi dòng của C_END là dòng thêm, không có dòng xóa.

### 7.3. Dựng nội dung từng file
```python
def build_user_file(base_lines, final_lines, added_by, deleted_by, users) -> list[str]:
    result = []
    for hunk in diff(base_lines, final_lines):
        if hunk.unchanged:
            result += hunk.lines
            continue
        # Dòng cũ: chỉ mất nếu user được chọn xóa
        result += [l for l in hunk.old_lines if deleted_by[l] not in users]
        # Dòng mới: chỉ thêm nếu user được chọn viết
        result += [l for l in hunk.new_lines if added_by[l] in users]
    return result
```

### 7.4. Quy tắc cấp file
| Trường hợp | Kết quả trong export end của user |
|---|---|
| File không đổi | Giữ nguyên |
| File được user chọn tạo mới | Có, chỉ chứa dòng của user chọn |
| File do user khác tạo mới | Không có (kết quả rỗng → không tạo file) |
| File nhiều người cùng sửa | Dòng start + thay đổi của user chọn |
| File bị user chọn xóa hoàn toàn | Không có |
| File bị user khác xóa | Giữ nguyên như start |
| File đổi tên | Dùng `git diff -M` giữa C_START và C_END để ghép cặp; tên file trong export theo người đổi tên (nếu user chọn đổi tên → tên mới, ngược lại → tên cũ) |

### 7.5. Cảnh báo (ghi vào `warnings.csv`)
- Đoạn thay đổi (hunk) chứa dòng của nhiều user khác nhau.
- Dòng bị nhiều user sửa liên tiếp trong kỳ (chỉ gán được cho người sửa cuối).
- File bỏ qua do quá lớn, binary, hoặc không nhận diện được ngôn ngữ.
- Chênh lệch kiểm tra chéo ở mục 8.3.

Ghi chú hiển thị trong UI và README: **bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được.**

---

## 8. Đếm LOC và số liệu

### 8.1. Số liệu chính (đếm trên thư mục export)
- `loc_start` = LOC của export start.
- `loc_end` = LOC của export end.
- `loc_delta` = `loc_end - loc_start`.
- Chia theo ngôn ngữ (tên lexer của Pygments).

### 8.2. Số liệu theo user (tính từ diff)
Với mỗi user trong kỳ:
- `added_code` = số dòng thêm do user, là dòng code theo `classify_lines(file tại C_END)`.
- `deleted_code` = số dòng xóa do user, là dòng code theo `classify_lines(file tại C_START)`.
- `net_code` = `added_code - deleted_code`.
- `commits` = số commit của user trong kỳ (không tính merge commit).
- `files_changed` = số file source user đã thay đổi.

### 8.3. Kiểm tra chéo
- Chọn tất cả user: `loc_start + Σ net_code (mọi user) ≈ loc_end`.
- Chọn user U: `loc_start + Σ net_code (user chọn) ≈ loc_end`.
- Nếu lệch > 0.5%, ghi cảnh báo kèm giá trị hai bên (lệch nhỏ có thể do phân loại comment phụ thuộc ngữ cảnh khi ghép dòng).

---

## 9. Bộ lọc file (`filters.py`)

Áp dụng cho cả export và đếm. Mặc định:

```yaml
exclude_dirs: [node_modules, vendor, dist, build, out, target, .venv, venv, __pycache__, .git, third_party, bin, obj]
exclude_globs: ["*.min.js", "*.min.css", "*.map", "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "*.pb.go", "*_generated.*", "*.designer.cs"]
exclude_binary: true
max_file_size_kb: 1024
include_tests: true         # false: bỏ test/, tests/, *_test.*, *.spec.*, *.test.*
count_docstrings: false
export_mode: source_only    # source_only | full (full: export mọi file, nhưng chỉ đếm file source)
```

Người dùng chỉnh được trong UI (mục "Tùy chọn nâng cao") và qua file `config.yaml`.

---

## 10. Màn hình (Streamlit, `app.py`)

### 10.1. Bố cục

```
┌──────────────────────────── ĐẾM LOC SOURCE CODE ─────────────────────────────┐
│ [1] REPOSITORY                                                               │
│   Repo (URL hoặc đường dẫn local): [______________________________]          │
│   GitHub token (tùy chọn, ẩn):     [••••••••••]                              │
│   [ Tải repo ]                                                               │
│   Nhánh: [ main ▼ ]                                                          │
│                                                                              │
│ [2] THỜI ĐIỂM THỐNG KÊ                                                       │
│   Start: [2026-01-01] [00:00]     End: [2026-10-22] [23:59]                  │
│   Múi giờ: [Asia/Bangkok ▼]                                                  │
│   → Snapshot start: a1b2c3d (2025-12-30 18:20)  "Fix login bug"              │
│   → Snapshot end:   f9e8d7c (2026-10-21 17:05)  "Release 2.3"                │
│                                                                              │
│ [3] CHỌN USER                                                                │
│   (•) Tất cả user    ( ) Chọn user                                           │
│   [x] alice    (142 commit)                                                  │
│   [ ] bob      (96 commit)                                                   │
│   [x] carol    (51 commit)                                                   │
│   [ ] Loại trừ bot   [ ] Xuất riêng từng user                                │
│   [ Quản lý gộp account ]                                                    │
│                                                                              │
│ [▸] Tùy chọn nâng cao (bộ lọc file, docstring, test, chế độ export)          │
│                                                                              │
│                                              [ PHÂN TÍCH ]                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 10.2. Hành vi các thành phần

**[1] Repository**
- Nhập URL hoặc đường dẫn local. Bấm "Tải repo" → clone bare vào thư mục cache (`~/.loc_counter/repos/<hash>`), nếu đã có thì `git fetch --all --prune`.
- Token chỉ giữ trong session, **không** ghi ra log, file cấu hình hay báo cáo.
- Dropdown nhánh: liệt kê nhánh remote, mặc định là nhánh mặc định của repo.
- Hiển thị spinner khi đang tải; báo lỗi rõ ràng nếu URL sai hoặc không có quyền.

**[2] Thời điểm thống kê**
- Hai date picker (start, end) và hai time input (tùy chọn).
- Mặc định: start = ngày đầu tháng hiện tại, end = hôm nay.
- Khi thay đổi start/end/nhánh: tự động tính lại C_START, C_END và hiển thị hash ngắn, ngày commit, tiêu đề commit.
- Kiểm tra `start < end`; nếu sai, hiển thị lỗi và vô hiệu hóa nút "Phân tích".

**[3] Chọn user**
- Radio: "Tất cả user" (mặc định) hoặc "Chọn user".
- Danh sách user: các account (đã gộp) có commit trong kỳ, sắp xếp theo số commit giảm dần, hiển thị số commit. Danh sách cập nhật khi đổi thời điểm hoặc nhánh.
- Khi chọn "Chọn user": bắt buộc chọn ít nhất 1 user, có ô tìm kiếm.
- "Quản lý gộp account": bảng (tên, email, account key) cho phép sửa account key, lưu vào `identities.yaml`.

**Nút PHÂN TÍCH**
- Chạy pipeline, hiển thị thanh tiến độ theo bước: Export start → Export end → Gán tác giả → Đếm LOC → Tạo báo cáo.
- Trong lúc chạy, khóa các ô nhập.

### 10.3. Màn hình kết quả

```
┌────────────────────────────── KẾT QUẢ ───────────────────────────────────────┐
│ Repo: org/repo  •  Nhánh: main  •  Kỳ: 2026-01-01 → 2026-10-22 (UTC+7)       │
│ User: alice, carol                                                           │
│                                                                              │
│  LOC start        LOC end          Chênh lệch       Commit                   │
│  60,510           68,450           +7,940           193                      │
│                                                                              │
│ Theo ngôn ngữ                                                                │
│  Ngôn ngữ    LOC start   LOC end   Chênh lệch                                │
│  Python        42,310     47,100     +4,790                                  │
│  TypeScript    18,200     21,350     +3,150                                  │
│                                                                              │
│ Theo user                                                                    │
│  User    Commit   Thêm    Xóa     Ròng     File thay đổi                     │
│  alice     142    6,120   1,010   +5,110   210                               │
│  carol      51    3,000     170   +2,830    64                               │
│                                                                              │
│ [Biểu đồ cột: code ròng theo tuần, mỗi user một màu]                         │
│                                                                              │
│ ⚠ 12 cảnh báo (xem chi tiết)                                                 │
│                                                                              │
│ [Tải start.zip] [Tải end.zip] [Tải báo cáo Excel] [Tải CSV] [Tải manifest]   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- Khi chọn "Tất cả user": bảng "Theo user" hiển thị mọi user và dòng **Tổng**.
- Có mục mở rộng "Chi tiết theo file" (đường dẫn, ngôn ngữ, LOC start, LOC end, chênh lệch), có lọc và sắp xếp.
- Có mục mở rộng "Cảnh báo" hiển thị nội dung `warnings.csv`.

---

## 11. CLI (`cli.py`)

```bash
loc-counter analyze \
  --repo https://github.com/org/repo \
  --branch main \
  --start 2026-01-01 --end 2026-10-22 \
  [--start-time 00:00] [--end-time 23:59] \
  [--tz Asia/Bangkok] \
  [--user alice --user carol]          # bỏ qua = tất cả user
  [--separate-users] \
  [--exclude-bots] \
  [--config config.yaml] [--identities identities.yaml] \
  [--token-env GITHUB_TOKEN] \
  --out ./output

loc-counter users --repo <repo> --branch main --start ... --end ...   # liệt kê user trong kỳ
loc-counter count <thư-mục>                                           # đếm LOC một thư mục bất kỳ
```

Token chỉ đọc từ biến môi trường (`--token-env`), không nhận trực tiếp qua tham số dòng lệnh.

---

## 12. Đầu ra

Thư mục kết quả: `<out>/<repo>_<branch>_<start>_<end>_<user-tag>/`
(`user-tag` = `all`, tên một user, hoặc `multi-<n>users`)

| File | Nội dung |
|---|---|
| `start_<YYYY-MM-DD>_<shortsha>.zip` | Export start |
| `end_<YYYY-MM-DD>_<user-tag>.zip` | Export end (thêm `end_<date>_<user>.zip` cho từng user nếu bật xuất riêng) |
| `loc_report.xlsx` | Sheet: `Tong_quan`, `Theo_ngon_ngu`, `Theo_user`, `Theo_file`, `Theo_tuan`, `Canh_bao` |
| `loc_by_user.csv`, `loc_by_language.csv`, `loc_by_file.csv` | Dữ liệu dạng CSV (UTF-8 có BOM để mở bằng Excel) |
| `warnings.csv` | Danh sách cảnh báo |
| `manifest.json` | Xem bên dưới |

```json
{
  "tool_version": "0.1.0",
  "generated_at": "2026-10-22T20:52:00+07:00",
  "repo": "https://github.com/org/repo",
  "branch": "main",
  "timezone": "Asia/Bangkok",
  "start": "2026-01-01T00:00:00+07:00",
  "end": "2026-10-22T23:59:59+07:00",
  "c_start": "a1b2c3d...",
  "c_end": "f9e8d7c...",
  "users": ["alice", "carol"],
  "all_users": false,
  "config": { "...": "toàn bộ cấu hình bộ lọc đã dùng" },
  "totals": { "loc_start": 60510, "loc_end": 68450, "loc_delta": 7940 },
  "cross_check": { "expected_loc_end": 68452, "diff_percent": 0.003 }
}
```

Không ghi token hoặc thông tin xác thực vào bất kỳ file đầu ra nào.

---

## 13. Milestone triển khai

| # | Nội dung | Tiêu chí hoàn thành |
|---|---|---|
| M1 | Khởi tạo project, `config.py`, `filters.py`, `classifier.py`, lệnh `loc-counter count` | Test classifier cho 9 ngôn ngữ ở mục 6.4 đều pass. Đếm một thư mục mẫu, sai lệch so với `cloc` (nếu có cài) ≤ 2% |
| M2 | `git_repo.py`, `snapshot.py`: clone/fetch, tìm C_START/C_END, export start và export end (tất cả user) | Test với repo mẫu: đúng commit snapshot theo múi giờ, zip đúng nội dung |
| M3 | `identity.py`: gộp account, lệnh `loc-counter users` | Test gộp nhiều email, noreply GitHub, mailmap, file identities |
| M4 | `attribution.py`, `builder.py`: dựng export end theo user | Toàn bộ test ở mục 14 pass |
| M5 | `counter.py`, `report.py`, `pipeline.py`, lệnh `loc-counter analyze` | Xuất đủ file mục 12, kiểm tra chéo mục 8.3 đạt trên repo mẫu |
| M6 | `app.py`: giao diện Streamlit theo mục 10 | Chạy được toàn bộ luồng trên UI, tải được mọi file |
| M7 | Hiệu năng: cache blob, chạy song song, `git cat-file --batch` | Repo khoảng 5.000 file, 2.000 commit trong kỳ chạy dưới 5 phút trên máy 8 nhân |

---

## 14. Test tích hợp bắt buộc (repo mẫu tạo trong `conftest.py`)

Tạo repo Git tạm bằng script với các commit có `GIT_AUTHOR_DATE` và `GIT_COMMITTER_DATE` cố định:

1. **Trước start** — `admin` tạo `app.py` gồm 10 dòng code, 3 dòng comment, 2 dòng trống.
2. **Trong kỳ** — `alice` thêm 5 dòng code và 2 dòng comment vào `app.py`.
3. **Trong kỳ** — `bob` tạo `util.py` gồm 8 dòng code.
4. **Trong kỳ** — `alice` xóa 2 dòng code gốc của `admin` trong `app.py`.
5. **Trong kỳ** — `bob` xóa 1 dòng code gốc khác của `admin` trong `app.py`.
6. **Sau end** — `alice` thêm 100 dòng code (không được tính).

Kết quả mong đợi:

| Trường hợp | loc_start | loc_end | Ghi chú |
|---|---|---|---|
| Tất cả user | 10 | 20 | 10 + 5 − 2 + 8 − 1 |
| Chỉ alice | 10 | 13 | 10 + 5 − 2; không có `util.py`; dòng bob xóa vẫn còn |
| Chỉ bob | 10 | 17 | 10 + 8 − 1; `app.py` không có thay đổi của alice |
| alice + bob | 10 | 20 | Bằng trường hợp tất cả user |

Số liệu theo user mong đợi: alice `added_code=5, deleted_code=2, net=+3`; bob `added_code=8, deleted_code=1, net=+7`.

Thêm test:
- Đổi tên file trong kỳ (rename) không bị tính là xóa + thêm.
- Một email noreply GitHub và một email công ty được gộp về cùng account.
- start trước commit đầu tiên → loc_start = 0.
- Block comment nhiều dòng được thêm vào: không tăng LOC.

---

## 15. Yêu cầu phi chức năng

- **Bảo mật:** token không ghi log, không lưu file; thư mục cache chỉ chứa dữ liệu repo.
- **Lỗi:** mọi lỗi Git hiển thị thông báo tiếng Việt dễ hiểu, kèm lệnh lỗi trong log chi tiết.
- **Log:** dùng `logging`, mức INFO mặc định, ghi ra `<out>/run.log`.
- **Tái lập:** cùng repo, nhánh, thời điểm, user và cấu hình phải cho ra kết quả giống hệt nhau.
- **Mã hóa:** đọc file với UTF-8, lỗi giải mã thì thử `latin-1`; nếu vẫn lỗi coi là binary và ghi cảnh báo. Giữ nguyên kiểu xuống dòng của file gốc khi export.
- **README:** hướng dẫn cài đặt, chạy CLI, chạy UI (`streamlit run src/loc_counter/app.py`), giải thích định nghĩa LOC và giới hạn của export end theo user.

---

## 16. Quyết định mặc định (có thể thay đổi sau)

| Vấn đề | Mặc định |
|---|---|
| Chọn nhiều user | Một bản export gộp; có tùy chọn xuất riêng từng user |
| Dòng bị nhiều người sửa liên tiếp | Gán cho người sửa cuối, ghi cảnh báo |
| Squash merge | Tính cho author của commit squash (thường là người tạo PR) |
| Merge commit | Không tính vào số commit; dòng do giải quyết xung đột gán cho author của merge commit |
| Docstring / JSDoc | Không tính là code |
| Code test | Có tính, có tùy chọn loại bỏ |
| Bot | Hiện trong danh sách; tùy chọn loại trừ |
