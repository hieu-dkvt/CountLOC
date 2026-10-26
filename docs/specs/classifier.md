---
id: classifier
title: Bộ phân loại dòng code
type: module
milestone: M1
modules: [src/loc_counter/classifier.py]
tests: [tests/test_classifier.py]
spec_refs: ["3.4", "6"]
depends_on: [config]
status: reviewed
---

# Bộ phân loại dòng code

## 1. Mục đích & phạm vi
Xác định ngôn ngữ của file theo tên và phân loại từng dòng là code hay không theo định nghĩa §3.4 và thuật toán §6.2 (không thay đổi). Có cache theo blob SHA (§6.3).
Ngoài phạm vi: đọc file, giải mã, lọc kích thước/binary (spec `filters`, `counter`).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | `classify_lines(content, filename, count_docstrings=False) -> list[bool]` | §6.1 |
| R2 | Lexer từ `get_lexer_for_filename(filename)`; không có → không phải source | §6.2.1 |
| R3 | Tokenize **toàn bộ** file | §6.2.2 |
| R4 | Token `Comment.*` (trừ `Comment.Preproc`, `Comment.PreprocFile` — D7), token chỉ khoảng trắng, `String.Doc` (khi `count_docstrings=False`) không đánh dấu; còn lại → `is_code[line] = True` | §6.2.3, PLAN D7 |
| R5 | `len(result) == len(split_lines(content))` — dòng theo git (thay `splitlines()`) | §6.2.4, PLAN D8 |
| R6 | Cache theo Git blob SHA; file ngoài Git dùng SHA-1 của nội dung | §6.3 |
| R7 | Ngôn ngữ = tên lexer Pygments | §8.1 |
| R8 | Lexer thuộc `exclude_languages` → không phải source | PLAN D3 |
| R9 | JSDoc/Javadoc là `Comment.*` → luôn không tính | PLAN D4 |

## 3. Giao diện
```python
class NotSourceFileError(LocCounterError):
    """File không có lexer phù hợp."""

def detect_language(filename: str, exclude_languages: Iterable[str] = ()) -> str | None:
    """Tên lexer Pygments cho filename (chỉ dùng basename), None nếu không có hoặc bị loại."""

def split_lines(content: str) -> list[str]:
    """Tách dòng theo git: theo "\n", bỏ "\r" cuối mỗi dòng; không tạo dòng rỗng sau "\n" cuối file."""

def classify_lines(content: str, filename: str, count_docstrings: bool = False) -> list[bool]:
    """Trả về is_code[i] cho từng dòng i (0-based) của file. Ném NotSourceFileError nếu không có lexer."""

def content_sha1(content: bytes) -> str:
    """SHA-1 hex của nội dung (khóa cache cho file không đến từ Git)."""

class LineClassifier:
    """Phân loại có cache. Khóa cache = (sha, language, count_docstrings)."""
    def __init__(self, count_docstrings: bool = False) -> None: ...
    def classify(self, content: str, filename: str, sha: str) -> list[bool]: ...
    @property
    def cache_hits(self) -> int: ...
    @property
    def cache_misses(self) -> int: ...
```

## 4. Dữ liệu vào / ra
- `content`: chuỗi đã giải mã (counter lo giải mã, bỏ BOM).
- Kết quả: list bool, độ dài = `len(split_lines(content))` (file rỗng → `[]`). Dòng thứ i khớp dòng i+1 trong `git diff` / `git blame`.

## 5. Luồng xử lý
`detect_language(filename, exclude_languages)`:
1. `basename = PurePosixPath(filename.replace("\\", "/")).name`.
2. `get_lexer_for_filename(basename)` (lru_cache theo basename); `ClassNotFound` → `None`.
3. `lexer.name in exclude_languages` → `None`; ngược lại trả `lexer.name`.

`classify_lines(content, filename, count_docstrings)`:
1. `lexer = get_lexer_for_filename(basename, stripnl=False, stripall=False, ensurenl=True)`; `ClassNotFound` → `NotSourceFileError`.
   (`stripnl` mặc định `True` sẽ bỏ dòng trống đầu/cuối và làm lệch chỉ số dòng — đã kiểm chứng.)
2. `lines = split_lines(content)` (dòng theo git, D8); `n = len(lines)`; `n == 0` → `[]`.
3. `text = "\n".join(line.replace("\r", " ") for line in lines)` — Pygments đổi `\r` đơn thành `\n`, nên thay `\r` còn sót trong dòng bằng khoảng trắng để chỉ số dòng của lexer không lệch. Các ký tự `\f`, `\v`, `\x85`, ` `… giữ nguyên trong dòng.
4. `is_code = [False] * n`; `line = 0`.
5. Với mỗi `(ttype, value)` trong `lexer.get_tokens(text)`:
   - Tách `value.split("\n")`; phần thứ `k > 0` tăng `line += 1`.
   - Với mỗi phần `p`: bỏ qua nếu `line >= n`, hoặc `p.strip() == ""`, hoặc (`ttype in Token.Comment` và không thuộc `Comment.Preproc`/`Comment.PreprocFile` — D7), hoặc (`ttype in Token.Literal.String.Doc` và `not count_docstrings`); ngược lại `is_code[line] = True`.
6. Trả `is_code`.

`LineClassifier.classify(content, filename, sha)`:
1. `language = detect_language(filename)`; `None` → `NotSourceFileError`.
2. Khóa `(sha, language, count_docstrings)`: có trong cache → `hits += 1`, trả bản sao list.
3. Không có → `misses += 1`, gọi `classify_lines`, lưu, trả.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Token `Token.Error` (lexer không hiểu) không phải comment/khoảng trắng → tính là code.
- `String.Doc` của Python: mọi chuỗi triple-quote đứng đầu dòng (docstring, `'''...'''` dùng làm comment). Chuỗi triple-quote gán cho biến (`x = """..."""`) là code.
- `count_docstrings=True` chỉ ảnh hưởng `String.Doc`; JSDoc/Javadoc/`///` của C# là comment → luôn không tính (D4).
- Chỉ thị tiền xử lý (`#include`, `#define`, `#if`, `#region`, `#pragma`…) là `Comment.Preproc`/`Comment.PreprocFile` → **là code** (D7). Shebang `#!` (`Comment.Hashbang`) không tính.
- Tên ngôn ngữ thực tế của Pygments: `.sql` → `Transact-SQL`, `.cs` → `C#`, `.ts` → `TypeScript` (đã kiểm chứng trên Pygments 2.21).
- Cùng nội dung, khác tên file (khác lexer) → khóa cache khác.

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception | Thông báo |
|---|---|---|
| Không có lexer | NotSourceFileError | `Không nhận diện được ngôn ngữ của file: <filename>` |

## 8. Bảo mật, hiệu năng, tái lập
- `get_lexer_for_filename` khá chậm → `functools.lru_cache` cho bước tìm lớp lexer theo basename.
- Cache kết quả theo SHA trong bộ nhớ; M7 bổ sung chia sẻ giữa process.
- Thuần, tái lập.

## 9. Test cases
Ma trận bắt buộc §6.4 (mandatory-tests mục A). Mỗi ngôn ngữ có một mẫu nguồn trong test, kỳ vọng là list `is_code` chính xác cho từng dòng.

| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-classifier-01 | Python: trống, `#`, `'''` block, code + `# c`, chuỗi chứa `#`, docstring module/hàm | mẫu Python | dòng code đúng vị trí; docstring không tính | unit |
| TC-classifier-02 | JavaScript: trống, `//`, `/* */` nhiều dòng, code + `//`, chuỗi `'http://a'`, JSDoc | mẫu JS | như trên; JSDoc không tính | unit |
| TC-classifier-03 | TypeScript: như JS, có type annotation | mẫu TS | | unit |
| TC-classifier-04 | Java: trống, `//`, block, code + `//`, chuỗi `"//x"`, Javadoc | mẫu Java | | unit |
| TC-classifier-05 | C#: trống, `//`, block, code + `//`, chuỗi `"//x"`, `///` doc | mẫu C# | | unit |
| TC-classifier-06 | Go: trống, `//`, block, code + `//`, chuỗi `"//x"` | mẫu Go | | unit |
| TC-classifier-07 | SQL: trống, `--`, block, code + `--`, chuỗi `'--x'` | mẫu `.sql` | | unit |
| TC-classifier-08 | HTML: trống, `<!-- -->` nhiều dòng, thẻ + comment cuối dòng, thuộc tính `"http://x"` | mẫu HTML | | unit |
| TC-classifier-09 | CSS: trống, `/* */` nhiều dòng, rule + comment cuối, selector chứa `"//x"` | mẫu CSS | | unit |
| TC-classifier-10 | `count_docstrings=True` | mẫu Python, JS | docstring Python tính; JSDoc vẫn không | unit |
| TC-classifier-11 | Độ dài kết quả | dòng trống đầu/cuối, CRLF, `\r` đơn, không newline cuối, `\f`/`\x85`/U+2028 giữa dòng, chuỗi rỗng | `len == len(split_lines(content))` == số dòng theo git; `""` → `[]` | unit |
| TC-classifier-12 | Dòng trống đầu file không làm lệch | `"\n\nx = 1\n"` | `[F, F, T]` | unit |
| TC-classifier-13 | Không có lexer | `LICENSE`, `a.unknownext` | `detect_language` → None; `classify_lines` ném `NotSourceFileError` | unit |
| TC-classifier-14 | exclude_languages | `a.txt`, `a.md` với mặc định; `a.json` | None, None, `"JSON"` | unit |
| TC-classifier-15 | Tên ngôn ngữ | `.py .js .ts .java .cs .go .sql .html .css` | `Python, JavaScript, TypeScript, Java, C#, Go, Transact-SQL, HTML, CSS` | unit |
| TC-classifier-16 | Cache | classify 2 lần cùng sha → hits=1, misses=1; khác `count_docstrings` → miss | | unit |
| TC-classifier-17 | `content_sha1` | `b"abc"` | `a9993e36...` | unit |
| TC-classifier-18 | Đường dẫn Windows | `detect_language("src\\a.py")` | `Python` | unit |
| TC-classifier-19 | Chỉ thị tiền xử lý là code (D7) | C#: `#region`, `#if DEBUG`, `#endif`; C: `#include <x.h>`, `#define N 1`; Python shebang | các dòng chỉ thị → True; shebang → False | unit |
| TC-classifier-20 | `split_lines` theo git (D8) | `"a\nb\n"`, `"a\r\nb"`, `"a\rb\n"`, `"a\fb\x85c\u2028d\n"`, `"\n"`, `""` | `["a","b"]`, `["a","b"]`, `["a\rb"]`, 1 dòng, `[""]`, `[]` | unit |
| TC-classifier-21 | `\r` đơn trong dòng không làm lệch | `"x = 1\r# c\ny = 2\n"` | `[True, True]` (2 dòng) | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | Dòng theo git (D8): `\f`, `\v`, `\x85`, ` `, `\r` đơn là ký tự trong dòng, không tách dòng. Nếu lexer coi chúng là `Error` → dòng tính là code | Chấp nhận (rất hiếm) | Đã duyệt 2026-10-22 (D8) |
` đơn là ký tự trong dòng, không tách dòng. Nếu lexer coi chúng là `Error` → dòng tính là code | Chấp nhận (rất hiếm) | Đã duyệt 2026-10-22 (D8) |
| A2 | `detect_language` dùng `get_lexer_for_filename(basename)` không truyền nội dung → với đuôi mơ hồ (vd. `.h`), Pygments chọn theo độ ưu tiên cố định, tái lập được | Giả định | Đã duyệt 2026-10-22 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-22 | Tạo mới | M1 |
| 2026-10-22 | `Comment.Preproc`/`PreprocFile` là code; định nghĩa dòng theo git (`split_lines`) thay `splitlines()`; thêm TC-19..21. Người dùng duyệt qua quyết định D7, D8 | Review M1 (reviews/M1-20261022.md) |
| 2026-10-23 | Đồng bộ mục 5 (bước 2, 3, 5) và A1 với D7/D8 đã duyệt; không đổi hành vi (code đã theo D7/D8) | Khôi phục spec bị ghi đè 05:58 |
