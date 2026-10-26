---
id: git_repo
title: Truy cập Git repository
type: module
milestone: M2, M3, M4
modules: [src/loc_counter/git_repo.py]
tests: [tests/test_git_repo.py]
spec_refs: ["3.1", "3.5", "4", "7.1", "7.2", "7.4", "10.2", "11", "15"]
depends_on: [config]
status: reviewed
---

# Truy cập Git repository

## 1. Mục đích & phạm vi
Lớp duy nhất gọi lệnh `git`. Mở repo (URL hoặc đường dẫn local) thành một bare clone trong thư mục cache, liệt kê nhánh, tìm commit theo thời điểm, đọc cây file và blob. Các module khác (`snapshot`, sau này `identity`, `attribution`) chỉ dùng API ở mục 3.
M3 bổ sung: liệt kê commit trong kỳ kèm identity gốc và identity sau `.mailmap` (`log_commits`).
M4 bổ sung các **lệnh nguyên thủy** cho `attribution` (§7.2, §7.4): ghép cặp file giữa C_START và C_END có nhận diện đổi tên (`diff_tree`), hunk giữa hai blob (`diff_hunks`), blame xuôi / ngược (`blame`), liệt kê commit chạm đường dẫn (`rev_list`, `first_commit_after`), kiểm tra đường dẫn tồn tại ở commit (`paths_exist`). Logic gán tác giả (chọn commit xóa, tách theo parent của merge — D23, blame lại khi dòng bị dời — D22, người đổi tên — D25) thuộc spec `attribution`, không nằm ở đây.
Không làm: GitHub API (`identity`), quy đổi thời điểm người dùng nhập (`snapshot`), dựng nội dung file (`builder`).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Gọi `git` qua `subprocess`, yêu cầu git ≥ 2.30 | §4 |
| R2 | Nguồn: đường dẫn local hoặc URL Git (GitHub HTTPS, token cho repo private) | §2 |
| R3 | Clone bare vào `~/.loc_counter/repos/<hash>`; đã có thì `git fetch --all --prune` (ở đây: fetch refspec tường minh, xem bước 5) | §10.2[1] |
| R4 | Repo local cũng clone bare vào cache | PLAN D12 |
| R5 | Liệt kê nhánh; nhánh mặc định của repo | §10.2[1] |
| R6 | `git rev-list -1 --first-parent --before="<ISO8601>" <branch>` | §3.1 |
| R7 | Đọc nhiều blob bằng `git cat-file --batch` | §4 |
| R8 | Token không có trong log, file cấu hình, báo cáo, message exception, config của repo cache; cache chỉ chứa dữ liệu repo | §10.2[1], §15, CLAUDE.md quy tắc 6 |
| R9 | Lỗi git → thông báo tiếng Việt dễ hiểu; lệnh lỗi ghi trong log chi tiết | §15 |
| R10 | Đọc blob dạng bytes để giữ nguyên kiểu xuống dòng | §15 |
| R11 | Commit "trong kỳ" = `C_START..C_END` (C_START rỗng → mọi commit tới C_END) | §3.1 |
| R12 | Tác giả = **author** (không phải committer); `.mailmap` của repo (tại C_END) | §3.5, PLAN D17 |
| R13 | Dòng thêm: `git blame -w -M -C --line-porcelain C_START..C_END -- <path_at_end>`; dòng boundary (`^`) không phải dòng thêm | §7.2 |
| R14 | Dòng xóa: `git blame -w --reverse --line-porcelain C_START..C_END -- <path_at_start>` → commit `L`; commit xóa = commit cũ nhất trong `git rev-list --ancestry-path --reverse L..C_END -- <path>` | §7.2 |
| R15 | Ghép cặp file đổi tên bằng `git diff -M` giữa C_START và C_END | §7.4 |
| R16 | Hunk §7.3 lấy từ diff của git, `-U0`, thuật toán Myers tường minh | PLAN D24 |
| R17 | Blame lại không `-M -C` cho dòng cần kiểm tra di chuyển; reverse blame riêng từng dòng tới parent của merge | PLAN D22, D23 |
| R18 | Rename limit lớn tường minh; git báo vượt giới hạn → báo cho người gọi để cảnh báo | PLAN D27 (Q24) |
| R19 | Quan hệ tổ tiên và merge-base giữa hai commit (phục vụ D23 trong `attribution`) | PLAN D29 (Q36) |

## 3. Giao diện
```python
MIN_GIT_VERSION: tuple[int, int] = (2, 30)
DEFAULT_CACHE_ROOT: Path  # Path.home() / ".loc_counter" / "repos"

class GitError(LocCounterError):
    """Lỗi khi chạy git. str(err) = thông báo tiếng Việt (đã che token)."""
    command: str        # lệnh đã che token, để ghi log
    returncode: int | None
    stderr: str         # đã che token

@dataclass(frozen=True)
class CommitInfo:
    sha: str                    # 40 ký tự hex
    short_sha: str              # 7 ký tự đầu
    committer_date: datetime    # aware, giữ offset gốc của commit
    author_name: str
    author_email: str
    subject: str

@dataclass(frozen=True)
class TreeEntry:
    path: str                   # POSIX, tương đối gốc repo
    mode: str                   # "100644", "100755", "120000" (symlink), "160000" (submodule)
    object_type: str            # "blob" | "commit"
    sha: str
    size: int | None            # None khi object_type == "commit"

def git_version() -> tuple[int, int, int]:
    """Phiên bản git trên PATH; ném GitError nếu không có git hoặc < MIN_GIT_VERSION."""

def mask_secrets(text: str, secrets: Iterable[str]) -> str:
    """Thay mọi secret (và dạng base64 trong header) bằng '***'."""

def normalize_source(source: str) -> tuple[str, bool]:
    """(nguồn chuẩn hóa, is_local). Ném GitError nếu URL chứa thông tin xác thực hoặc nguồn không hợp lệ."""

def cache_dir_for(source: str, cache_root: Path = DEFAULT_CACHE_ROOT) -> Path:
    """cache_root / sha1(nguồn chuẩn hóa)[:16]."""

class GitRepo:
    git_dir: Path
    source: str                 # nguồn chuẩn hóa, không chứa token

    @classmethod
    def open(cls, source: str, token: str | None = None,
             cache_root: Path = DEFAULT_CACHE_ROOT) -> GitRepo:
        """Clone bare vào cache hoặc fetch nếu đã có. Token chỉ giữ trong đối tượng."""

    def run(self, args: Sequence[str], *, stdin: bytes | None = None) -> bytes:
        """Chạy `git <global opts> <args>` trong git_dir, trả stdout bytes; lỗi → GitError."""

    def list_branches(self) -> list[str]:
        """Tên nhánh (refs/heads), sắp xếp tăng dần."""

    def default_branch(self) -> str | None:
        """Nhánh mặc định của nguồn (HEAD), None nếu không xác định / không còn tồn tại."""

    def resolve_branch(self, branch: str) -> str:
        """SHA đầu nhánh; ném GitError nếu nhánh không tồn tại."""

    def rev_before(self, branch: str, moment: datetime) -> str | None:
        """Commit cuối theo first-parent có committer date ≤ moment; None nếu không có."""

    def commit_info(self, sha: str) -> CommitInfo: ...

    def list_tree(self, commit_sha: str) -> list[TreeEntry]:
        """Mọi entry của cây (đệ quy), sắp xếp theo path (so sánh chuỗi Python)."""

    def read_blob(self, sha: str) -> bytes: ...

    def read_blobs(self, shas: Iterable[str]) -> Iterator[tuple[str, bytes]]:
        """Đọc nhiều blob qua một tiến trình `git cat-file --batch`, giữ thứ tự đầu vào.
        Generator: đóng sớm (`close()`) thì tiến trình git bị dừng ngay."""

    def log_commits(self, c_end: str, c_start: str | None = None,
                    mailmap_rev: str | None = None) -> list[LogCommit]:
        """Mọi commit trong c_start..c_end (c_start None → mọi commit tới c_end), thứ tự `git log`."""

@dataclass(frozen=True)
class LogCommit:
    sha: str
    parents: tuple[str, ...]    # > 1 → merge commit
    author_name: str            # %an (gốc)
    author_email: str           # %ae (gốc)
    mapped_name: str            # %aN (sau .mailmap)
    mapped_email: str           # %aE (sau .mailmap)
    author_date: datetime       # %aI, aware

    @property
    def is_merge(self) -> bool: ...

# ----- M4 -----
@dataclass(frozen=True)
class DiffEntry:
    """Một cặp file giữa hai commit (một bản ghi `diff-tree --raw`)."""
    status: str                 # "A" | "D" | "M" | "R" | "T" (chữ cái đầu của trạng thái git)
    old_path: str | None        # None khi status == "A"
    new_path: str | None        # None khi status == "D"
    old_mode: str | None        # None khi không có phía cũ
    new_mode: str | None
    old_sha: str | None         # SHA blob / gitlink; None khi không có phía cũ
    new_sha: str | None
    similarity: int | None      # status "R": % giống nhau (R083 → 83); còn lại None

    @property
    def path(self) -> str:
        """new_path nếu có, ngược lại old_path (khóa sắp xếp)."""

@dataclass(frozen=True)
class TreeDiff:
    entries: tuple[DiffEntry, ...]   # sắp xếp theo (path, old_path or "")
    rename_limit_hit: bool           # git báo bỏ qua nhận diện rename do quá nhiều file

@dataclass(frozen=True)
class Hunk:
    """Một hunk `-U0`; chỉ số 0-based, dạng nửa mở [start, start + count)."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int

@dataclass(frozen=True)
class BlameLine:
    line: int           # 0-based trong file được blame (forward: file tại `end`; reverse: file tại `since`)
    sha: str            # forward: commit đưa dòng vào; reverse: commit cuối cùng còn dòng (L)
    orig_line: int      # 0-based trong file tại `sha`
    filename: str       # đường dẫn của file tại `sha` (đã bỏ C-quote)
    boundary: bool      # dòng boundary (`^`)

class GitRepo:  # (tiếp)
    def diff_tree(self, c_start: str | None, c_end: str) -> TreeDiff:
        """Cặp file khác nhau giữa c_start và c_end, nhận diện rename; c_start None → mọi entry của c_end là "A"."""

    def diff_hunks(self, old_sha: str, new_sha: str) -> list[Hunk]:
        """Hunk `-U0` (Myers) giữa hai blob, thứ tự tăng dần; cùng SHA → []."""

    def blame(self, end: str, path: str, since: str | None = None, *, reverse: bool = False,
              detect_moves: bool = True,
              line_ranges: Sequence[tuple[int, int]] = ()) -> list[BlameLine]:
        """Blame `since..end` (since None → tới commit gốc) của `path`.
        Forward: path tại `end`, thêm `-M -C` khi detect_moves. Reverse (cần since): path tại `since`, không `-M -C`.
        line_ranges: các khoảng 0-based nửa mở; rỗng → cả file. Kết quả sắp theo `line`."""

    def rev_list(self, include: str, exclude: str | None = None, paths: Sequence[str] = (), *,
                 ancestry_path: bool = False, reverse: bool = False) -> list[str]:
        """SHA commit trong `exclude..include` (exclude None → mọi tổ tiên) chạm `paths`, thứ tự topo."""

    def first_commit_after(self, since: str, until: str, paths: Sequence[str]) -> str | None:
        """Commit cũ nhất trong `--ancestry-path since..until` chạm `paths`; None nếu không có."""

    def paths_exist(self, items: Sequence[tuple[str, str]]) -> list[bool]:
        """Với mỗi (commit, path): path có trong cây của commit không. Giữ thứ tự đầu vào."""

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """ancestor là tổ tiên (hoặc chính là) descendant (D29)."""

    def merge_bases(self, a: str, b: str) -> list[str]:
        """Mọi merge-base tốt nhất của a và b, sắp tăng dần; không có tổ tiên chung → [] (D29)."""
```

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `source` | str | — | URL `https://`, `http://`, `ssh://`, `git@host:path`, `file://`; hoặc đường dẫn thư mục tồn tại | §2 |
| `token` | str \| None | None | chỉ dùng với URL `http(s)://` | §2, §11 |
| `cache_root` | Path | `~/.loc_counter/repos` | | §10.2[1] |
| `moment` | datetime | — | phải có tzinfo | §3.1 |

## 5. Luồng xử lý

### 5.1 Chạy lệnh git (`_run_git`, dùng cho mọi lệnh)
1. Lệnh = `["git", "-c", "core.quotepath=off", "-c", "core.autocrlf=false", "-c", "log.showSignature=false", "-c", "i18n.logOutputEncoding=UTF-8", "--git-dir", str(git_dir), *args]` (bỏ `--git-dir` với `git_version`, `clone`). Các `-c` này giữ kết quả độc lập với cấu hình git toàn cục của người dùng.
2. Môi trường = `os.environ` + `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=""`, `SSH_ASKPASS=""` (không bật hộp thoại hỏi mật khẩu — kể cả askpass của VS Code), `LC_ALL=C` (thông báo lỗi tiếng Anh ổn định để phân loại); **bỏ** `GIT_DIFF_OPTS` (git cho nó ưu tiên hơn `-U` trên dòng lệnh → làm sai hunk `-U0`) và `GIT_EXTERNAL_DIFF` khỏi môi trường (M4, review). Có token (chỉ với nguồn `https://`): thêm vào `GIT_CONFIG_PARAMETERS` (nối sau giá trị sẵn có, cách nhau một khoảng trắng) hai mục định dạng cũ `'key=value'` (git ≥ 2.30 đọc được):
   - `'http.https://<host>/.extraheader=Authorization: Basic <base64("x-access-token:" + token)>'` — header chỉ gửi tới đúng host của nguồn;
   - `'credential.helper='` — tắt credential helper để token sai thất bại ngay, không bật hộp thoại Git Credential Manager.
   Token **không** nằm trong argv, URL hay file config.
3. `subprocess.run(cmd, input=stdin, capture_output=True, env=env, check=False)` — list tham số, không `shell=True`.
4. Log DEBUG: `mask_secrets(" ".join(cmd))`. Mã thoát ≠ 0 → log WARNING lệnh + stderr (đã che) và ném `GitError` với thông báo theo bảng mục 7 (phân loại bằng stderr).
5. Trả `stdout` (bytes).

`mask_secrets(text, secrets)`: với mỗi secret không rỗng, thay `secret`, `base64("x-access-token:" + secret)` bằng `***`.

### 5.2 `git_version()`
`git --version` → regex `(\d+)\.(\d+)\.(\d+)`. Không chạy được (`FileNotFoundError`) → GitError "chưa cài git". `< (2, 30)` → GitError "phiên bản git quá cũ". Kết quả cache (`functools.cache`).

### 5.3 `normalize_source(source)`
1. `s = source.strip()`; rỗng → GitError "Chưa nhập repo".
2. Cú pháp transport helper `<transport>::<địa chỉ>` (regex `^[A-Za-z0-9+.-]+::`, vd. `ext::…`, `fd::…`) → GitError "Không hỗ trợ nguồn dạng <transport>::<địa chỉ>. Hãy nhập URL hoặc đường dẫn local." (không lặp lại nguồn) — `ext` chạy lệnh tùy ý, `fd` đọc stdin có thể treo.
   Dạng scp (b) dưới đây mà `Path(s).expanduser()` là **thư mục có thật** → coi là đường dẫn local (bước 3), như `git clone` (vd. thư mục POSIX `repo:2024`).
   Nguồn từ xa khi (a) có scheme dạng URL `^[A-Za-z][A-Za-z0-9+.-]+://` (http, https, ssh, git, file, `git+ssh`, `ssh+git`, ftp(s)… — git tự quyết scheme có hỗ trợ hay không), hoặc (b) dạng scp theo quy tắc của git: có `:` và trước dấu `:` đầu tiên không có `/` hay `\`, và không phải tiền tố ổ đĩa `X:` (một chữ cái). Phần **userinfo** tìm **không dựa vào `urlsplit`** (vốn cắt netloc tại `/`, `?`, `#` nên bỏ sót mật khẩu chứa các ký tự này):
   - URL: `rest` = phần sau `://`; userinfo = `rest` trước dấu `@` **cuối cùng** (không có `@` → không có userinfo).
     - http(s): có `@` trong `rest` (`user:pass@`, `token@`, kể cả mật khẩu chứa `#`, `?`, `/`) → GitError "URL không được chứa thông tin xác thực" (không lặp lại URL trong thông báo).
     - Scheme khác: userinfo chứa `:` (mật khẩu, vd. `ssh://user:pass@host/o/r`, `ssh://u:pa/ss@h/o/r`) → cùng GitError. Chỉ tên user (`ssh://git@host/o/r`, `ssh://git@host:22/o/r`) hợp lệ — cổng nằm sau `@` nên không bị nhầm là mật khẩu.
   - scp: phần trước `@` cuối cùng chứa `:` (`user:pass@host:path`; git không có cú pháp mật khẩu cho scp, nhưng chuỗi như vậy vẫn bị từ chối để không lộ) → cùng GitError.
   - False positive chấp nhận được (từ chối nhầm, không lộ gì): đường dẫn trong repo chứa `@` sau phần có `:` (vd. `ssh://git@h:22/o/r@v`).
   - Bỏ `/` cuối; giữ nguyên phần còn lại (không đổi hoa/thường) → `(s, False)`.
3. Ngược lại coi là đường dẫn: `Path(s).expanduser().resolve()`; không phải thư mục → GitError "Không tìm thấy repo: <s>", trong đó nếu `s` có `@` thì phần trước `@` cuối cùng được che thành `***` (lưới an toàn cho biến thể lạ). → `(str(path), True)`.
4. Cache tạo bởi phiên bản cũ (trước 2026-10-25) từ URL có mật khẩu vẫn giữ mật khẩu trong `remote.origin.url` của cache; nguồn đó nay bị từ chối nên cache không được mở lại. Không tự dọn — README hướng dẫn xóa `~/.loc_counter/repos`.

`cache_dir_for`: `cache_root / hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]`.

### 5.4 `GitRepo.open(source, token, cache_root)`
1. `git_version()`.
2. `normalized, is_local = normalize_source(source)`; `is_local` → bỏ qua token. Có token mà nguồn không phải `https://` (vd. `http://`, `ssh://`, `git@...`) → GitError "Token chỉ dùng với URL https://" (không gửi token qua kênh không mã hóa / không phải HTTP).
3. `dest = cache_dir_for(normalized, cache_root)`.
4. `dest` tồn tại và `git --git-dir dest rev-parse --is-bare-repository` in `true` → **fetch** (bước 5).
   `dest` tồn tại nhưng không phải bare repo hợp lệ → xóa `dest` (log WARNING) rồi clone.
   **Xóa thư mục** (cache hỏng, thư mục tạm) dùng `_remove_tree`: `shutil.rmtree` với handler lỗi bỏ thuộc tính read-only (`os.chmod(p, stat.S_IWRITE)`) rồi xóa lại — git trên Windows tạo file pack/idx read-only. Sau đó thư mục vẫn còn → GitError "Không xóa được thư mục cache".
5. Fetch: `git fetch --prune --no-tags origin "+refs/heads/*:refs/heads/*"`.
6. Clone: clone vào `dest.with_name(dest.name + ".tmp-<pid>")`: `git clone --bare --no-tags --origin origin [--no-hardlinks] -- <nguồn> <tmp>` (`--origin origin` để không phụ thuộc `clone.defaultRemoteName`; repo local thêm `--no-hardlinks` để cache không chia sẻ file với repo của người dùng — xóa/chmod cache không ảnh hưởng repo nguồn, PLAN D20/F2), rồi `os.replace(tmp, dest)`. Lỗi (kể cả `OSError` của `os.replace`) → `_remove_tree(tmp)`, ném GitError (`OSError` → "Không ghi được thư mục cache"). `cache_root` tạo bằng `mkdir(parents=True, exist_ok=True)`; `OSError` → GitError "Không tạo được thư mục cache".
7. Sau clone/fetch: cập nhật nhánh mặc định: `git ls-remote --symref origin HEAD` → dòng `ref: refs/heads/<x>\tHEAD` → `git symbolic-ref HEAD refs/heads/<x>`. Không có dòng `ref:` → giữ nguyên HEAD.
8. Kiểm tra an toàn (cache có sẵn: trước khi fetch ở bước 5; clone mới: sau bước 6): `git config --get remote.origin.url` phải bằng nguồn chuẩn hóa, ngược lại GitError "Cấu hình repo cache không khớp nguồn" (không in URL). Có token → file `config` của `dest` không được chứa token / base64 của header, ngược lại GitError "Lỗi bảo mật: thông tin xác thực bị ghi vào cấu hình repo cache."

### 5.5 Nhánh
- `list_branches`: `git for-each-ref --format=%(refname:strip=2) refs/heads/` → tách dòng, bỏ rỗng, `sorted`.
- `default_branch`: `git symbolic-ref --quiet --short HEAD`; trả về khi tên nằm trong `list_branches()`, ngược lại `None`.
- `resolve_branch(branch)`: `git rev-parse --verify --quiet refs/heads/<branch>^{commit}`; mã ≠ 0 → GitError "Không tìm thấy nhánh". Tên chứa ký tự cấm (`..`, bắt đầu bằng `-`) → GitError cùng thông báo (chống chèn tham số).

### 5.6 `rev_before(branch, moment)`
1. `moment.tzinfo is None` → `ValueError` (lỗi lập trình).
2. `iso = moment.replace(microsecond=0).isoformat()` (vd. `2026-01-31T23:59:59+07:00`).
3. `git rev-list -1 --first-parent --before=<iso> refs/heads/<branch> --`.
4. stdout rỗng → `None`; ngược lại SHA.
Đã kiểm chứng (git 2.55): mốc bao gồm commit có committer date **bằng** `moment`; offset được hiểu đúng (`23:59:59+07:00` ≡ `16:59:59+00:00`).

### 5.7 `commit_info(sha)`
`git show -s --format=%H%x00%cI%x00%an%x00%ae%x00%s <sha> --` → tách `\0`, giải mã UTF-8 (`errors="replace"`); `committer_date = datetime.fromisoformat(%cI)`. Trường `%H` phải khớp `[0-9a-f]{40}`, ngược lại GitError "Không đọc được thông tin commit <sha>" (chặn mọi dòng thừa do cấu hình toàn cục).

### 5.8 `list_tree(commit_sha)`
1. `git ls-tree -r -l -z --full-tree <commit_sha>`.
2. Mỗi bản ghi (tách `\0`, bỏ rỗng): `"<mode> <type> <sha> <size>\t<path>"`; `size` = `-` → `None`. `path` giải mã UTF-8 (`errors="replace"`, log WARNING nếu có ký tự thay thế).
3. Chỉ giữ `type` ∈ {`blob`, `commit`}; sắp xếp theo `path`.

### 5.9 Đọc blob
- `read_blob(sha)`: `git cat-file blob <sha>` → bytes.
- `read_blobs(shas)`: một tiến trình `git cat-file --batch` (`Popen`, stdin/stdout nhị phân), ghi `<sha>\n` từng cái, đọc header `<sha> <type> <size>\n` rồi đúng `size` byte + `\n`; đọc được ít hơn `size` byte (tiến trình chết giữa chừng) → log WARNING, GitError `Không đọc được blob <sha> trong repo.` Header `<sha> missing` hoặc `type != blob` → GitError `Không tìm thấy blob <sha> trong repo.` Tiến trình thoát mã ≠ 0 → log WARNING lệnh + stderr (đã che token), GitError theo bảng mục 7. Generator bị đóng sớm / exception → `kill` tiến trình trong `finally`. Đóng stdin, chờ tiến trình kết thúc; mã ≠ 0 → GitError. Giữ thứ tự đầu vào.

### 5.10 `log_commits(c_end, c_start, mailmap_rev)`
1. Tùy chọn mailmap: `-c mailmap.file=` (tắt file toàn cục) và `-c mailmap.blob=<mailmap_rev>:.mailmap` (rỗng khi `mailmap_rev is None` → tắt `.mailmap`, kể cả `HEAD:.mailmap` mặc định của bare repo). Commit không có `.mailmap` → git bỏ qua, không lỗi (đã kiểm chứng).
2. `git <mailmap opts> log --no-color --format=%x1e%H%x00%P%x00%an%x00%ae%x00%aN%x00%aE%x00%aI <c_end> [^<c_start>] --`.
3. Tách bản ghi theo `\x1e`, bỏ rỗng; mỗi bản ghi `rstrip("\n")` rồi tách `\0` thành 7 trường; `parents = tuple(P.split())`; `author_date = datetime.fromisoformat(aI)`. Giải mã UTF-8 (`errors="replace"`). `%H` không khớp `[0-9a-f]{40}` → GitError.
4. Trả list theo thứ tự `git log` (mặc định: mới → cũ, tái lập với cùng repo).

### 5.11 Quy ước chung cho các lệnh M4
- Mọi tham số commit (`c_start`, `c_end`, `end`, `since`, `include`, `exclude`, commit trong `paths_exist`) và blob (`old_sha`, `new_sha`) phải khớp `[0-9a-f]{40}`, ngược lại `ValueError` (lỗi lập trình; chặn chèn tùy chọn vào argv). Không gọi git trong trường hợp đó.
- Tùy chọn diff cố định, thêm trước lệnh con của `diff`/`blame`: `-c diff.algorithm=myers -c diff.indentHeuristic=true` (ghi đè cấu hình toàn cục; blame dùng cùng bộ xdiff).
- Chỉ số dòng trả ra luôn **0-based**; khoảng dòng luôn nửa mở `[start, end)`. Một dòng = một đoạn kết thúc bằng `\n` hoặc đoạn cuối file không có `\n` (cách git đếm, PLAN D8).
- Đường dẫn trong output giải mã UTF-8 (`errors="replace"`, log WARNING khi có ký tự thay thế, như mục 5.8).

### 5.12 `diff_tree(c_start, c_end)`
1. `c_start is None` → `entries` = mỗi `TreeEntry` của `list_tree(c_end)` thành `DiffEntry("A", None, e.path, None, e.mode, None, e.sha, None)`; `rename_limit_hit = False`. Không chạy diff (không phụ thuộc id của empty tree).
2. Ngược lại: `git diff-tree -r -z --raw --no-abbrev -M -l0 <c_start> <c_end>` (`-l0` = không giới hạn số file khi nhận diện rename; plumbing không đọc `diff.renames`, `color.*`, `diff.noprefix`).
3. Tách stdout theo `\0`. Bản ghi bắt đầu bằng `:`: `:<old_mode> <new_mode> <old_sha> <new_sha> <status>`; tiếp theo là 1 đường dẫn, hoặc 2 (cũ, mới) khi status bắt đầu bằng `R` hoặc `C`.
   - mode `000000` → `None`; SHA toàn `0` → `None`.
   - `status[0]` là trạng thái; `R<nnn>` → `similarity = int(nnn)`.
   - `A`: chỉ `new_*`; `D`: chỉ `old_*`; `M`, `T`, `R`: cả hai. `C` không xuất hiện (không dùng `-C` ở đây); gặp trạng thái khác (`U`, `X`, `C`) → GitError "Không đọc được kết quả so sánh cây file".
4. `rename_limit_hit = True` khi stderr (mã thoát 0) chứa `rename detection was skipped` hoặc `diff.renameLimit` / `renamelimit` (không phân biệt hoa thường) → log WARNING.
5. Sắp xếp `entries` theo `(entry.path, entry.old_path or "")`.

### 5.13 `diff_hunks(old_sha, new_sha)`
1. `old_sha == new_sha` → `[]`.
2. `git -c diff.algorithm=myers -c diff.indentHeuristic=true diff -U0 --inter-hunk-context=0 --diff-algorithm=myers --indent-heuristic --no-color --no-ext-diff --no-textconv --text --no-renames <old_sha> <new_sha>` (diff hai blob; `--text` để file bị đánh dấu binary vẫn so theo dòng; các tùy chọn tường minh ghi đè `diff.context`, `diff.interHunkContext`, `color.diff`, `diff.external`, thuộc tính `-diff`/`diff=<driver>`).
3. Mỗi dòng stdout khớp `^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@` → một hunk (count thiếu = 1). Các dòng khác (header, `-`, `+`, `\ No newline at end of file`) bỏ qua.
4. Đổi sang 0-based: `old_start = a - 1 if b > 0 else a`, `new_start = c - 1 if d > 0 else c` (count 0 nghĩa là chèn/xóa **sau** dòng a/c 1-based).
5. Giữ thứ tự xuất hiện (tăng dần). So khớp trên dòng thô (gồm `\r`), không bỏ khoảng trắng.

### 5.14 `blame(end, path, since, reverse, detect_moves, line_ranges)`
1. `reverse and since is None` → `ValueError`.
2. Lệnh: `git -c diff.algorithm=myers -c diff.indentHeuristic=true blame --line-porcelain --root --no-ignore-revs-file --no-textconv -w`, thêm:
   - `-M -C` khi `not reverse and detect_moves`;
   - `--reverse` khi `reverse`;
   - `-L <s+1>,<e>` cho mỗi khoảng sau khi gộp (sắp xếp, gộp khoảng chồng/liền kề, bỏ khoảng rỗng);
   - phạm vi `<since>..<end>` (hoặc `<end>` khi `since is None`), rồi `-- <path>`.
   `--root`: commit gốc trong phạm vi không bị đánh boundary (kể cả repo có lịch sử không liên quan được merge). `--no-ignore-revs-file`: bỏ `blame.ignoreRevsFile` toàn cục (file không tồn tại làm blame lỗi).
3. Chia lô: tối đa `_BLAME_MAX_RANGES = 200` khoảng `-L` mỗi lệnh (giới hạn argv Windows); nối kết quả các lô.
4. Phân tích output (bytes, tách theo `\n`):
   - Dòng header khớp `^([0-9a-f]{40}) (\d+) (\d+)( \d+)?$` → bắt đầu một `BlameLine` với `sha`, `orig_line = int - 1`, `line = int - 1`.
   - Các dòng khóa sau header: `boundary` → `boundary = True`; `filename <tên>` → bỏ C-quote (dưới đây). Khóa khác bỏ qua (không dùng `author*` — account lấy từ `log_commits`).
   - Dòng bắt đầu bằng `\t` = nội dung → kết thúc bản ghi. Bản ghi thiếu `filename` hoặc header/thứ tự sai → GitError "Không đọc được kết quả git blame của <path>".
5. Bỏ C-quote: giá trị bắt đầu và kết thúc bằng `"` → bỏ hai dấu nháy, giải các escape `\\`, `\"`, `\a`, `\b`, `\t`, `\n`, `\v`, `\f`, `\r`, `\ooo` (byte bát phân) thành bytes rồi giải mã UTF-8.
6. Sắp xếp theo `line`. Với `line_ranges` rỗng, kết quả phủ đúng các dòng `0..n-1`.
Ý nghĩa (đã kiểm chứng trên git 2.55): forward — `boundary` = dòng có từ `since` hoặc trước. Reverse — dòng còn tới `end` có `sha == end` (không `boundary`); dòng mất ngay sau `since` có `boundary` (L = `since`); `filename` = đường dẫn tại L (theo được rename).

### 5.15 `rev_list(include, exclude, paths, ancestry_path, reverse)`
`git --literal-pathspecs rev-list --topo-order [--ancestry-path] [--reverse] <include> [^<exclude>] -- <paths...>` → mỗi dòng một SHA. `--literal-pathspecs`: tên file chứa `*`, `?`, `[`, `:(` không bị hiểu là pattern. Không truyền `paths` → không lọc đường dẫn. Đơn giản hóa lịch sử mặc định của git (commit TREESAME bị bỏ).

`first_commit_after(since, until, paths)` = `rev_list(until, since, paths, ancestry_path=True, reverse=True)`, lấy **phần tử đầu** (không dùng `-1 --reverse`: git áp `-1` trước `--reverse` nên trả commit mới nhất — đã kiểm chứng); rỗng → `None`.

### 5.16 `paths_exist(items)`
1. Một tiến trình `git cat-file --batch-check`, stdin = `<commit>:<path>\n` cho mỗi mục mà path **không** chứa `\n` hay `\r` (git đọc stdin theo dòng và bỏ `\r` trước `\n`).
2. Mỗi dòng output: 3 trường, trường đầu là SHA 40 hex → `True`; 2 trường `<sha40> submodule` (gitlink trỏ tới commit không có trong repo) → `True` — gitlink tính là **tồn tại** (đường dẫn có trong cây, như `list_tree`/`diff_tree`; người gọi lọc theo mode); dòng kết thúc bằng ` missing` → `False`; dạng khác hoặc sai số dòng → GitError "Không đọc được kết quả kiểm tra đường dẫn".
3. Path chứa `\n` hoặc `\r`: `git rev-parse --verify --quiet <commit>:<path>` riêng (`allow_fail`; mã 0 → `True`). Không dùng `cat-file -e`: lệnh này kiểm **object** tồn tại nên trả mã 1 với gitlink trỏ tới commit không có trong repo (đã kiểm chứng git 2.55); `rev-parse` chỉ phân giải entry trong cây.
4. Trả list cùng thứ tự đầu vào; `items` rỗng → `[]` (không chạy git).

### 5.17 `is_ancestor(ancestor, descendant)`, `merge_bases(a, b)` (D29)
Hai tham số đều kiểm SHA theo 5.11 (`ValueError`, không chạy git).
- `is_ancestor`: `git merge-base --is-ancestor <ancestor> <descendant>` (chạy với `allow_fail`). Mã 0 → `True` (kể cả `ancestor == descendant`); mã 1 → `False`; mã khác → log WARNING lệnh + stderr và GitError theo bảng mục 7 (như 5.1 bước 4).
- `merge_bases`: `git merge-base --all <a> <b>` (`allow_fail`). Mã 0 → các dòng SHA 40 hex, bỏ trùng, **sắp tăng dần** (không phụ thuộc thứ tự in của git); dòng không phải SHA → GitError `Không đọc được kết quả merge-base.` Mã 1 với stdout rỗng (hai lịch sử không liên quan) → `[]`. Mã khác (kể cả mã 1 mà stdout khác rỗng) → GitError như trên.
Dùng trong `attribution` (D23): reverse blame `since..end` chỉ đúng khi `since` là tổ tiên của `end` — khi không phải, git **không báo lỗi** mà trả mọi dòng boundary (đã kiểm chứng git 2.55), nên người gọi phải kiểm `is_ancestor` trước.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Chỉ nhánh `refs/heads/*` (sau clone bare = nhánh local của nguồn). Không dùng tag, không dùng `refs/pull/*`.
- Nhánh có `/` (vd. `feature/x`) được hỗ trợ.
- Repo rỗng (chưa commit): clone thành công, `list_branches() == []`. Người gọi báo lỗi.
- Fetch xóa nhánh đã bị xóa ở nguồn (`--prune`).
- Thông tin xác thực **không bao giờ** được đặt trong URL; URL nhập có sẵn credential bị từ chối (tránh lưu vào `remote.origin.url`).
- Dữ liệu bytes của blob trả nguyên vẹn (CRLF, BOM, binary).
- `core.autocrlf=false` truyền qua `-c` để không bị cấu hình toàn cục của Windows can thiệp.
- M4: `diff_hunks` so khớp trên dòng thô (CRLF ≠ LF, khoảng trắng có nghĩa); `blame` luôn `-w` (theo §7.2). Hai bên có thể không khớp (dòng chỉ đổi khoảng trắng/EOL nằm trong hunk nhưng blame trả boundary / còn sống) — người gọi xử lý theo D24.
- `diff_tree` có gitlink (`160000`) và symlink (`120000`) như mọi entry; người gọi lọc theo mode.
- Đổi tên với độ giống < 50% (ngưỡng mặc định của `-M`) là `D` + `A` (PLAN D27/Q24).

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo cho người dùng (tiếng Việt) | Log |
|---|---|---|---|
| Không có git | GitError | `Không tìm thấy lệnh git. Hãy cài Git ≥ 2.30 và thêm vào PATH.` | ERROR |
| git cũ | GitError | `Phiên bản git <x.y.z> quá cũ, cần ≥ 2.30.` | ERROR |
| Nguồn rỗng | GitError | `Chưa nhập repo (URL hoặc đường dẫn local).` | — |
| URL có credential (http(s) có userinfo; ssh/git/file hoặc scp có mật khẩu) | GitError | `URL repo không được chứa thông tin xác thực. Hãy nhập token ở ô/biến môi trường riêng.` | WARNING (không ghi URL) |
| Đường dẫn không tồn tại | GitError | `Không tìm thấy repo: <đường dẫn>` | — |
| Không phải repo git (nguồn local; stderr `does not appear to be a git repository`, `not a git repository` hoặc `repository ... does not exist`) | GitError | `Không phải Git repository: <nguồn>` | WARNING + lệnh |
| Sai quyền / cần đăng nhập (`Authentication failed`, `could not read Username`, `403`, `401`) | GitError | `Không có quyền truy cập repo <nguồn>. Kiểm tra token hoặc quyền của tài khoản.` | WARNING + lệnh (che token) |
| Repo không tồn tại trên server (`Repository not found`, `404`) | GitError | `Không tìm thấy repo <nguồn> trên server (sai URL hoặc repo private cần token).` | WARNING |
| Lỗi mạng (`Could not resolve host`, `Failed to connect`, `timed out`) | GitError | `Không kết nối được tới <host>. Kiểm tra mạng.` | WARNING |
| Nhánh không tồn tại | GitError | `Không tìm thấy nhánh: <branch>` | — |
| Token với nguồn không phải `https://` | GitError | `Token chỉ dùng với URL https://.` | — |
| Không xóa được thư mục cache hỏng / thư mục tạm | GitError | `Không xóa được thư mục cache <đường dẫn>. Hãy đóng chương trình đang dùng nó rồi thử lại.` | WARNING + lỗi OS |
| `os.replace` / ghi cache lỗi | GitError | `Không ghi được thư mục cache <đường dẫn>: <lỗi>` | WARNING |
| `remote.origin.url` khác nguồn | GitError | `Cấu hình repo cache không khớp nguồn. Hãy xóa thư mục <đường dẫn> rồi thử lại.` | WARNING |
| Token bị ghi vào config cache | GitError | `Lỗi bảo mật: thông tin xác thực bị ghi vào cấu hình repo cache.` | ERROR |
| `%H` không phải SHA | GitError | `Không đọc được thông tin commit <sha>` | WARNING |
| Không tạo được `cache_root` | GitError | `Không tạo được thư mục cache <đường dẫn>: <lỗi>` | WARNING |
| Blob không tồn tại / không phải blob | GitError | `Không tìm thấy blob <sha> trong repo.` | WARNING lệnh + stderr |
| `read_blobs` đọc thiếu byte | GitError | `Không đọc được blob <sha> trong repo.` | WARNING lệnh |
| Ngày commit không đọc được (header múi giờ hỏng) | GitError | `Không đọc được ngày của commit <sha>` | WARNING |
| `git log` trả bản ghi sai định dạng | GitError | `Không đọc được danh sách commit trong kỳ.` | WARNING |
| `diff-tree` bản ghi sai định dạng / trạng thái lạ | GitError | `Không đọc được kết quả so sánh cây file.` | WARNING + bản ghi (≤ 80 ký tự) |
| Blame porcelain sai định dạng | GitError | `Không đọc được kết quả git blame của <path>.` | WARNING + dòng lỗi (≤ 80 ký tự) |
| `cat-file --batch-check` trả dòng lạ | GitError | `Không đọc được kết quả kiểm tra đường dẫn.` | WARNING |
| Vượt rename limit (stderr, mã 0) | `TreeDiff.rename_limit_hit = True` (không exception) | — (người gọi ghi cảnh báo) | WARNING |
| `merge-base --all` trả dòng không phải SHA | GitError | `Không đọc được kết quả merge-base.` | WARNING + dòng lỗi (≤ 80 ký tự) |
| SHA tham số không hợp lệ | `ValueError` (lỗi lập trình) | — | — |
| Lỗi git khác | GitError | `Lệnh git thất bại: <dòng stderr đầu tiên, đã che token>` | WARNING lệnh + stderr đầy đủ |

## 8. Bảo mật, hiệu năng, tái lập
- Token: chỉ trong thuộc tính private của `GitRepo` và biến môi trường của tiến trình con; `repr(GitRepo)` không chứa token; mọi chuỗi lệnh/stderr đưa vào log hoặc exception đi qua `mask_secrets`. Không ghi token vào `remote.origin.url`, `config`, file nào khác.
- Hiệu năng: `read_blobs` dùng một tiến trình cho cả loạt; `git_version` cache. M4: mỗi file thay đổi 1 `diff` + 1–2 `blame`; `paths_exist` một tiến trình cho cả loạt. Gom lệnh / chạy song song để M7. Clone local dùng `--no-hardlinks` (D20) — đổi tốc độ lấy an toàn cho repo nguồn.
- Tái lập: `list_branches`, `list_tree` sắp xếp; không phụ thuộc cấu hình git toàn cục (`core.quotepath`, `core.autocrlf`, `log.showSignature` ghi đè bằng `-c`; `--origin origin` khi clone). Test chạy cô lập: fixture autouse đặt `GIT_CONFIG_GLOBAL` = file rỗng, `GIT_CONFIG_NOSYSTEM=1`; TC riêng bật cấu hình "khó chịu".
- Lệnh mạng không có timeout (spec gốc không yêu cầu); có token thì credential helper bị tắt nên không treo ở hộp thoại.
- Windows: đường dẫn `--git-dir` dạng `str(Path)`; path trong cây luôn POSIX; tên file Unicode giải mã UTF-8 nhờ `core.quotepath=off` + `-z`.

## 9. Test cases
Fixture `make_repo` (conftest): repo nguồn tạm, `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` cố định, `core.autocrlf=false`, `cache_root` = `tmp_path`. Không truy cập mạng.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-git_repo-01 | Phiên bản git | git trên máy; monkeypatch `subprocess.run` trả `git version 2.29.0` / ném `FileNotFoundError` | tuple ≥ (2,30); GitError "quá cũ"; GitError "Không tìm thấy lệnh git" | unit |
| TC-git_repo-02 | normalize_source | `" https://github.com/o/r/ "`, `git@github.com:o/r.git`, `https://u:p@github.com/o/r`, `https://tok@github.com/o/r`, `""`, thư mục tồn tại, thư mục không tồn tại | `("https://github.com/o/r", False)`; scp giữ nguyên; credential → GitError (thông báo không chứa `p`/`tok`); rỗng → GitError; local → đường dẫn tuyệt đối, True; không tồn tại → GitError | unit |
| TC-git_repo-03 | cache_dir_for | cùng nguồn 2 lần; 2 nguồn khác | cùng thư mục; khác thư mục; tên 16 ký tự hex | unit |
| TC-git_repo-04 | Clone repo local vào cache | repo nguồn 2 nhánh `main`, `feature/x` | `git_dir` nằm trong cache_root, là bare; `list_branches() == ["feature/x", "main"]`; `default_branch() == "main"`; repo nguồn không thay đổi | integration |
| TC-git_repo-05 | Mở lại → fetch | sau TC-04, thêm commit vào `main`, xóa `feature/x`, tạo `dev` ở nguồn; `open` lại | `resolve_branch("main")` = SHA mới; nhánh `feature/x` biến mất, có `dev` | integration |
| TC-git_repo-06 | Cache hỏng | `dest` tồn tại nhưng là thư mục rỗng | xóa và clone lại thành công | integration |
| TC-git_repo-07 | Không phải repo | thư mục rỗng (không có `.git`) | GitError `Không phải Git repository`; không còn thư mục `.tmp-*` trong cache | integration |
| TC-git_repo-08 | Nhánh không tồn tại / tên nguy hiểm | `resolve_branch("nope")`, `resolve_branch("--all")` | GitError `Không tìm thấy nhánh` | integration |
| TC-git_repo-09 | rev_before biên và múi giờ | commit A `2026-01-01T00:00:00+07:00`, B `…00:00:01+07:00`, C `2026-01-31T23:59:59+07:00`, D `2026-02-01T00:00:00+07:00` | `moment` = `2025-12-31T23:59:59+07:00` → None; `2026-01-01T00:00:00+07:00` → A; `2026-01-31T23:59:59+07:00` → C; `2026-01-31T16:59:58+00:00` → B | integration |
| TC-git_repo-10 | rev_before first-parent | `main`: M1 → nhánh feature commit F (ngày gần mốc hơn) → merge `--no-ff` M2 (sau mốc) | `moment` giữa F và M2 → M1 (không phải F) | integration |
| TC-git_repo-11 | rev_before không có tz | `datetime(2026,1,1)` | ValueError | unit |
| TC-git_repo-12 | commit_info | commit có tiêu đề tiếng Việt, author `Bình <b@x.vn>` | các trường đúng; `committer_date` aware, offset +07:00; `short_sha` 7 ký tự | integration |
| TC-git_repo-13 | list_tree | file `src/a.py`, `thư mục/tệp ở đây.py`, file thực thi, symlink, submodule (gitlink tạo bằng `update-index --cacheinfo 160000`) | path POSIX Unicode đúng; mode/type đúng; size của gitlink = None; sắp xếp theo path | integration |
| TC-git_repo-14 | read_blob / read_blobs giữ byte | blob CRLF, LF, BOM, binary có NUL, rỗng | bytes trùng nội dung commit; `read_blobs` trả đúng thứ tự, cả SHA lặp lại | integration |
| TC-git_repo-15 | read_blobs SHA không tồn tại | sha `0`*40 | GitError | integration |
| TC-git_repo-16 | Token không bị lộ khi lỗi | `GitRepo.open("https://example.invalid/o/r", token="ghp_SECRET123")`, monkeypatch `subprocess.run` ghi lại argv/env và trả mã 128 với stderr chứa token và base64 của header | token (và base64) không có trong argv, `str(GitError)`, `err.command`, `err.stderr`, log (caplog); `GIT_CONFIG_PARAMETERS` chứa `'http.https://example.invalid/.extraheader=Authorization: Basic <b64>'` và `'credential.helper='`, giữ giá trị sẵn có của biến; không còn thư mục trong cache | unit |
| TC-git_repo-20 | Token không vào repo cache | (a) nguồn local + token: token bị bỏ qua; (b) `GitRepo(git_dir_cache, "https://example.invalid/o/r", token)` trên cache đã clone | (a) config, `repr` không chứa token, `remote.origin.url` = nguồn chuẩn hóa; (b) kiểm tra config (bước 5.4.8) qua; ghi token vào config → GitError `Lỗi bảo mật`, thông báo không chứa token | integration |
| TC-git_repo-21 | Cache hỏng có file read-only | clone, `git gc` ở cache, đặt mọi file read-only, xóa `HEAD` của cache, `open` lại; monkeypatch `shutil.rmtree` không xóa gì | lần 1: clone lại thành công, không sót `.tmp-*`; lần 2 (không xóa được): GitError `Không xóa được thư mục cache` | integration |
| TC-git_repo-22 | Cấu hình git toàn cục "khó chịu" | `GIT_CONFIG_GLOBAL` có `log.showSignature=true`, `clone.defaultRemoteName=upstream`; commit có header `gpgsig` giả (tạo bằng `hash-object -t commit`) | `open` OK; `commit_info(sha).sha == sha`, `short_sha` đúng; `remote.origin.url` có | integration |
| TC-git_repo-23 | Token với nguồn không phải https | `open("http://h/o/r", token=...)`, `open("git@h:o/r", token=...)` | GitError `Token chỉ dùng với URL https://`, không chạy lệnh git mạng | unit |
| TC-git_repo-24 | `remote.origin.url` khác nguồn | đổi `remote.origin.url` trong cache rồi `open` lại | GitError `không khớp nguồn` | integration |
| TC-git_repo-25 | log_commits theo kỳ | repo: c0 (trước kỳ), c1 alice, nhánh feat c2 bob, merge M (committer khác author), c3; `log_commits(c3, c0)`; `log_commits(c3, None)` | (a) đúng {c1, c2, M, c3}, không có c0; `M.is_merge`, `parents` 2 phần tử; author (không phải committer); `author_date` aware. (b) có thêm c0 | integration |
| TC-git_repo-26 | `.mailmap` tại mailmap_rev | `.mailmap` thêm ở c1 (gộp `12345+alice@users.noreply.github.com` → `Alice <alice@corp.com>`), bị đổi sau end ở c9; `GIT_CONFIG_GLOBAL` có `mailmap.file` trỏ file gộp bob → `x@y` | `mailmap_rev=c3`: commit noreply có `mapped_email == alice@corp.com`, `author_email` giữ gốc; bob không bị đổi; `mailmap_rev=None`: `mapped_* == author_*` | integration |
| TC-git_repo-27 | Không bật askpass | monkeypatch `subprocess.run` ghi env | `GIT_ASKPASS == ""`, `SSH_ASKPASS == ""`, `GIT_TERMINAL_PROMPT == "0"` cho mọi lệnh | unit |
| TC-git_repo-28 | Clone local không hardlink | spy argv của `clone` với nguồn local và nguồn https giả | local có `--no-hardlinks`; https không có | unit |
| TC-git_repo-29 | Không tạo được cache_root | `cache_root` là đường dẫn dưới một **file** | GitError `Không tạo được thư mục cache` | integration |
| TC-git_repo-30 | `i18n.logOutputEncoding` toàn cục | `GIT_CONFIG_GLOBAL` có `i18n.logOutputEncoding=ISO-8859-1`; author `José Bình` | `commit_info` và `log_commits` trả đúng `José Bình` | integration |
| TC-git_repo-31 | read_blobs lỗi có log | SHA không tồn tại | GitError `Không tìm thấy blob`; caplog có WARNING | integration |
| TC-git_repo-32 | Commit có múi giờ hỏng | commit tạo bằng `hash-object --literally` với `author … 1767240000 +9959` | `commit_info` và `log_commits` ném GitError `Không đọc được ngày của commit` | integration |
| TC-git_repo-33 | diff_tree đổi tên / xóa / thêm / sửa | c1: `old.py` (5 dòng), `gone.py`, `keep.py`; c2: `git mv old.py new.py` + sửa 1 dòng, xóa `gone.py`, thêm `tệp mới.py`, sửa `keep.py` | `R` (`old.py`→`new.py`, similarity 1..100), `D gone.py` (new_* None), `A tệp mới.py` (old_* None), `M keep.py`; SHA 40 ký tự khớp `rev-parse <c>:<path>`; sắp theo path; `rename_limit_hit` False | integration |
| TC-git_repo-34 | diff_tree với C_START rỗng | `diff_tree(None, c)` trên cây có file thường, file thực thi, symlink, gitlink | mọi entry `A`, mode/SHA trùng `list_tree(c)`, cùng thứ tự | integration |
| TC-git_repo-35 | diff_tree: argv và rename limit | monkeypatch `subprocess.run` ghi argv, trả mã 0, stdout rỗng, stderr `warning: exhaustive rename detection was skipped due to too many files.` | argv có `-M`, `-l0`, `-z`, `--no-abbrev`; `rename_limit_hit` True; caplog WARNING | unit |
| TC-git_repo-36 | diff_hunks → chỉ số 0-based | blob base `a..e` (5 dòng); biến thể: chèn đầu, xóa dòng cuối, sửa dòng 2, thêm dòng cuối không EOL, CRLF→LF một dòng; cùng SHA | `[Hunk(0,0,0,1)]`; `[Hunk(4,1,4,0)]`; `[Hunk(1,1,1,1)]`; `[Hunk(5,0,5,1)]` (base có EOL) hoặc `[Hunk(4,1,4,2)]` (base thiếu EOL); dòng CRLF→LF là hunk; cùng SHA → `[]` | integration |
| TC-git_repo-37 | diff_hunks không phụ thuộc cấu hình | `GIT_CONFIG_GLOBAL`: `diff.algorithm=patience`, `diff.context=10`, `diff.interHunkContext=5`, `diff.indentHeuristic=false`, `color.diff=always`, `diff.external=không-tồn-tại`, `diff.noprefix=true`; blob có byte NUL (git coi là binary); biến môi trường `GIT_DIFF_OPTS=--unified=5`, `GIT_EXTERNAL_DIFF=không-tồn-tại` | kết quả bằng kết quả với cấu hình sạch; blob có NUL vẫn ra hunk theo dòng (không "Binary files differ"); env của lệnh git không có `GIT_DIFF_OPTS`, `GIT_EXTERNAL_DIFF` | integration |
| TC-git_repo-38 | blame forward theo kỳ | c0 (trước kỳ) 3 dòng; c1 (alice) thêm 2 dòng giữa; `blame(c1, "app.py", c0)` | 5 `BlameLine`, `line` 0..4; dòng của c0 `boundary` True; dòng mới `sha == c1`, `boundary` False; `filename == "app.py"` | integration |
| TC-git_repo-39 | `--root` | (a) `blame(c1, path, None)` trên repo 2 commit; (b) kỳ chứa merge `--allow-unrelated-histories` của nhánh có commit gốc riêng | (a) không dòng nào `boundary`, dòng của commit gốc có `sha` = commit gốc; (b) dòng từ commit gốc thứ hai không `boundary` | integration |
| TC-git_repo-40 | blame reverse qua rename | c0 `old.py` 4 dòng; c1 alice xóa dòng 2; c2 bob `git mv old.py new.py`; `blame(c2, "old.py", c0, reverse=True)` | dòng 0, 2, 3 `sha == c2`, `filename == "new.py"`; dòng 1 `boundary` True (L = c0), `filename == "old.py"`; `reverse=True` + `since=None` → ValueError | integration |
| TC-git_repo-41 | blame line_ranges, chia lô, detect_moves | file 10 dòng; `line_ranges=[(7,9),(1,2),(2,3)]`; monkeypatch `_BLAME_MAX_RANGES = 1`; spy argv | kết quả chỉ dòng 1, 2, 7, 8 (đã gộp `(1,3)`), sắp theo `line`, bằng kết quả không chia lô; argv có `-L 2,3` và `-L 8,9`; `detect_moves=False` → argv không có `-M`/`-C`; `reverse=True` → không có `-M`/`-C` | integration |
| TC-git_repo-42 | Dòng bị dời (tiền đề D22) | c0 `a.py` có khối 3 dòng dài (≥ 40 ký tự chữ-số); c1 alice dời khối xuống cuối file; c2 alice chuyển một khối khác sang `b.py` | `blame(c2, "a.py", c0)` (có `-M -C`): dòng dời `boundary` True; `detect_moves=False`: dòng dời `sha == c1` / `c2`, không boundary | integration |
| TC-git_repo-43 | blame không phụ thuộc cấu hình | `GIT_CONFIG_GLOBAL`: `blame.ignoreRevsFile=.nope`, `blame.showRoot=false`, `blame.markUnblamableLines=true`, `blame.coloring=highlightRecent`, `diff.algorithm=patience`, `diff.indentHeuristic=false`, `color.ui=always` | không lỗi; kết quả bằng cấu hình sạch | integration |
| TC-git_repo-44 | Phân tích porcelain, bỏ C-quote | monkeypatch output: header 4 trường rồi 3 trường; `filename "q\"t.py"`, `filename "a\tb.py"`, `filename "\303\251.py"`, `filename thư mục/tệp.py`; output thiếu `filename`; dòng nội dung không có header trước; output kết thúc giữa bản ghi (header không có dòng nội dung); `line_ranges=[(3,3)]` (chỉ khoảng rỗng) | `q"t.py`, `a<TAB>b.py`, `é.py`, giữ nguyên Unicode; thiếu `filename` / sai thứ tự / thiếu dòng nội dung → GitError `Không đọc được kết quả git blame`; khoảng rỗng → `[]`, không chạy git | unit |
| TC-git_repo-45 | rev_list / first_commit_after | lịch sử tuyến tính c0..c4, c1 và c3 chạm `x.py`, c2 chạm `y.py`; nhánh feat từ c1 có f1 chạm `x.py` (không merge) | `rev_list(c4, c0, ["x.py"])` = `[c3, c1]`; `reverse=True` → `[c1, c3]`; `first_commit_after(c0, c4, ["x.py"]) == c1` (không phải c3); `ancestry_path`: `rev_list(c4, f1, ["x.py"], ancestry_path=True) == []` và `first_commit_after(f1, c4, ["x.py"])` → None (không có `ancestry_path` → `[c3]`); `first_commit_after(c3, c4, ["x.py"])` → None; `exclude=None` gồm c0 nếu c0 chạm path | integration |
| TC-git_repo-46 | Pathspec literal | file `*.py`, `a.py`, `:(glob)x.py` cùng sửa ở các commit khác nhau | `rev_list(..., ["*.py"])` chỉ trả commit sửa file `*.py`; tương tự `:(glob)x.py` | integration |
| TC-git_repo-47 | paths_exist | (c1, `a.py`) có; (c0, `new.py`) không; (c1, `thư mục/tệp: x.py`) có; `[]`; path chứa `\n`, path kết thúc `\r` (cây tạo bằng `mktree`); gitlink trỏ tới commit không có trong repo và tới commit có trong repo, cùng lô với file thường; monkeypatch `--batch-check` trả thiếu dòng / dòng lạ | `[True, False, True]`; `[]` không chạy git; path có `\n`, `\r` đi qua `rev-parse --verify` và trả `True`; hai gitlink → `True`, file thường cùng lô vẫn đúng; thiếu dòng / dòng lạ → GitError `Không đọc được kết quả kiểm tra đường dẫn.` | integration |
| TC-git_repo-48 | Tham số SHA không hợp lệ | `blame("--output=x", "a.py")`, `diff_hunks("HEAD", sha)`, `rev_list("main")`, `paths_exist([("-p", "a")])`; spy `subprocess` | ValueError, không chạy git | unit |
| TC-git_repo-49 | Lỗi git ở lệnh M4 | `blame(c1, "khong-co.py")`; monkeypatch `diff-tree` trả bản ghi status `X`, bản ghi meta thiếu trường, bản ghi `R` thiếu đường dẫn thứ hai | GitError `Lệnh git thất bại: ...` (tiếng Việt, có caplog WARNING lệnh); 3 ca sau → GitError `Không đọc được kết quả so sánh cây file.` | integration |
| TC-git_repo-51 | read_blobs: `cat-file` thoát mã ≠ 0 | monkeypatch `Popen`: trả đủ blob, `wait()` = 1, stderr chứa token | GitError `Lệnh git thất bại: ...` (đã che token), `returncode == 1`; log WARNING không chứa token; stdin/stdout/stderr đã đóng trước khi ném lỗi | unit |
| TC-git_repo-50 | read_blobs đọc thiếu byte | monkeypatch `Popen`: header `<sha> blob 10` nhưng stdout chỉ còn 4 byte rồi EOF | GitError `Không đọc được blob <sha> trong repo.`; caplog WARNING; tiến trình bị dừng | unit |
| TC-git_repo-52 | is_ancestor | c0 → c1 → c2 trên `main`; nhánh `feat` từ c1 có f1; `ancestor == descendant` | `is_ancestor(c0, c2)` True; `(c2, c0)` False; `(f1, c2)` False; `(c1, c1)` True; SHA không hợp lệ → ValueError, không chạy git; monkeypatch mã thoát 128 → GitError, caplog WARNING | integration |
| TC-git_repo-53 | merge_bases | (a) `main` c0 → c1 → c2, `feat` từ c1 có f1: `merge_bases(c2, f1)`; (b) criss-cross: hai nhánh merge chéo nhau tạo 2 merge-base; (c) nhánh không liên quan (`commit-tree` không parent); (d) monkeypatch stdout `xyz` mã 0; (e) monkeypatch stdout `B
A
B` mã 0; mã 128; mã 1 với stdout khác rỗng | (a) `[c1]`; (b) 2 SHA sắp tăng dần, khớp tập `git merge-base --all`; (c) `[]`; (d) GitError `Không đọc được kết quả merge-base.`; (e) `[A, B]`; GitError `returncode == 128` (stderr đã che); GitError `returncode == 1` | integration + unit |
| TC-git_repo-54 | Mật khẩu trong URL / scp | `ssh://u:s3cret@h/o/r`, `SSH://u:s3cret@h:22/o/r`, `git://u:s3cret@h/o/r`, `file://u:s3cret@h/o/r`, `git+ssh://u:s3cret@h/o/r`, `ftp://u:s3cret@h/o/r`, `us:s3cret@h:o/r.git`, `u~x:s3cret@h:o/r`, `us:s3@cret@h:o/r` (user ≥ 2 ký tự: `X:` một chữ cái là ổ đĩa); mật khẩu chứa `#`, `?`, `/`: `ssh://u:s3#cret@h/o/r`, `ssh://u:s3?cret@h/o/r`, `ssh://u:s3/cret@h/o/r`, `git://u:s3#cret@h/o/r`, `https://u:s3#cret@github.com/o/r`, `https://u:s3/cret@github.com/o/r`; hợp lệ: `ssh://git@h/o/r`, `ssh://git@h:22/o/r/`, `ssh://h/o/r`, `git+ssh://git@h/o/r`, `ssh+git://git@h/o/r`, `git@h:o/r.git`; local không tồn tại `<tmp>/u:s3cret@x` và `<tmp>/a@b`; `GitRepo.open("ssh://u:s3cret@h/o/r")`, `GitRepo.open("file://u:s3#cret@h/o/r")`; `ext::sh -c x`, `fd::0`, `FD::0,1`; thư mục có thật tên dạng scp (monkeypatch `Path.is_dir` → True cho `repo:2024`, vì Windows không tạo được tên có `:`) | `::` → GitError `Không hỗ trợ nguồn dạng`, không chứa `sh -c`; `repo:2024` → `(đường dẫn tuyệt đối, True)`; ca có mật khẩu → GitError `thông tin xác thực`; hợp lệ → `(s.rstrip("/"), False)`; local → GitError `Không tìm thấy repo: ***@…` (phần trước `@` cuối bị che); mọi thông báo và caplog không chứa `s3cret` / `cret`; `open` ném GitError trước khi chạy lệnh git nào ngoài `--version` (spy `subprocess`) | unit |
| TC-git_repo-17 | mask_secrets | text chứa token và base64 của `x-access-token:<token>` | cả hai thành `***` | unit |
| TC-git_repo-18 | Phân loại lỗi git | monkeypatch stderr: `Authentication failed`, `Repository not found`, `Could not resolve host: github.com`, lỗi khác | đúng 4 thông báo tiếng Việt mục 7 | unit |
| TC-git_repo-19 | Repo rỗng | nguồn `git init` chưa commit | open OK, `list_branches() == []`, `default_branch()` None | integration |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án đề xuất | Trạng thái |
|---|---|---|---|
| A1 | Token GitHub gửi bằng header `Authorization: Basic base64("x-access-token:<token>")`, khóa theo host `http.https://<host>/.extraheader`, qua `GIT_CONFIG_PARAMETERS` định dạng `'key=value'` (git 2.30 đọc được; git 2.55 đã kiểm chứng). Hoạt động với PAT classic, fine-grained và token GitHub App | Giả định | Đã duyệt 2026-10-23 (sửa theo review M2) |
| A2 | Không có token: git có thể gọi credential helper của hệ thống (Git Credential Manager trên Windows) — người dùng tự xác thực bằng tài khoản của họ. Có token: tắt credential helper (`credential.helper=`) để thất bại nhanh. `GIT_TERMINAL_PROMPT=0` ngăn treo ở prompt dòng lệnh | Giả định | Đã duyệt 2026-10-23 (sửa theo review M2) |
| A3 | Đường dẫn file không phải UTF-8 trong git: giải mã với `errors="replace"` + log WARNING (hiếm) | Giả định | Đã duyệt 2026-10-23 |
| A4 | Không khóa (lock) thư mục cache khi hai tiến trình cùng mở một repo; clone qua thư mục tạm + `os.replace` để tránh cache dở dang | Giả định (dùng một người, một phiên) | Đã duyệt 2026-10-23 |
| A5 | `git fetch` dùng refspec tường minh `+refs/heads/*:refs/heads/*` thay `--all` (bare clone không cấu hình refspec fetch — đã kiểm chứng) | Giả định | Đã duyệt 2026-10-23 |
| A6 | Hunk lấy bằng `git diff` giữa **hai blob** (`diff_hunks(old_sha, new_sha)`) thay vì `git diff-tree -p -- <old> <new>` như ghi trong D24: cùng xdiff Myers `-U0`, nhưng không phụ thuộc pathspec (diff-tree với pathspec dễ ghép sai cặp khi đường dẫn cũ còn tồn tại ở C_END hoặc có bản sao) | Làm rõ cách thực hiện D24, không đổi thuật toán | Đã duyệt 2026-10-23 |
| A7 | Rename limit: `-l0` (không giới hạn) thay cho "số lớn"; vẫn dò stderr để báo `rename_limit_hit` (D27/Q24) | Giả định | Đã duyệt 2026-10-23 |
| A8 | Blame dùng `-c diff.algorithm=myers -c diff.indentHeuristic=true` thay vì tùy chọn `--diff-algorithm` (tùy chọn này của blame không chắc có ở git 2.30); git bỏ qua `-c` không dùng nên an toàn | Giả định | Đã duyệt 2026-10-23 |
| A9 | `rev_list` dùng đơn giản hóa lịch sử mặc định của git (bỏ commit TREESAME, merge TREESAME với một parent đi theo parent đó); không dùng `--full-history` | Giả định — `attribution` tự xử lý merge theo D23 | Đã duyệt 2026-10-23 |
| A10 | Repo dùng SHA-256 (`[0-9a-f]{64}`) không được hỗ trợ (kiểm `[0-9a-f]{40}`) | Giới hạn, ghi README | Đã duyệt 2026-10-23 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-23 | Tạo mới | M2 |
| 2026-10-23 | Bảng lỗi mục 7: thêm mẫu stderr `repository ... does not exist` (git 2.55 báo khi clone thư mục local không phải repo) — làm rõ, không đổi hành vi | Kiểm chứng khi lập trình |
| 2026-10-23 | TC-20 viết lại để thực sự kiểm bước 5.4.8 (nguồn local không gắn token nên cách monkeypatch cũ không chạm tới kiểm tra) — chỉ đổi test | /feature-test M2 |
| 2026-10-23 | Sửa theo review M2 (reviews/M2-20261023.md): xóa thư mục có file read-only (`_remove_tree`), bọc lỗi `os.replace`; `-c log.showSignature=false`, `clone --origin origin`, kiểm `%H`; token chỉ với https, header theo host, định dạng `'key=value'`, tắt credential helper; kiểm `remote.origin.url`; `read_blobs` kiểm type; test cô lập cấu hình toàn cục; thêm TC-21..24 | Review M2 FAIL (Major 1, 2; Minor M2, M3, M5, M6, M7) |
| 2026-10-23 | M3: thêm `LogCommit`, `log_commits` (commit trong kỳ, `.mailmap` tại mailmap_rev); xử lý tồn đọng review M2 F1 (`GIT_ASKPASS`/`SSH_ASKPASS` rỗng), F2 (`--no-hardlinks` cho nguồn local), F4 (lỗi tạo cache_root), F5 (`i18n.logOutputEncoding=UTF-8`), F7 (log lỗi `read_blobs`); TC-25..31 | PLAN M3, D17, D20 |
| 2026-10-23 | Sửa theo review M3: ngày commit hỏng → GitError; bảng lỗi thêm dòng `log_commits`; sửa câu "hardlink" ở mục 8 cho khớp D20; TC-32 | Review M3 (m1, N2, ghi chú 4) |
| 2026-10-23 | M4: thêm `DiffEntry`, `TreeDiff`, `Hunk`, `BlameLine`, `diff_tree`, `diff_hunks`, `blame`, `rev_list`, `first_commit_after`, `paths_exist` (mục 3, 5.11–5.16); R13–R18; bảng lỗi; TC-33..49; A6–A10. Trạng thái về `draft` | PLAN M4, D22–D25, D27 |
| 2026-10-23 | Người dùng duyệt bản M4 (A6–A10 đồng ý) → `approved` | Duyệt |
| 2026-10-23 | TC-45: thay ca "`ancestry_path` loại f1" (luôn đúng vì f1 không phải tổ tiên c4) bằng ca thực sự kiểm `--ancestry-path` — chỉ đổi test | /feature-test M4 |
| 2026-10-23 | Sửa theo review M4 (reviews/git_repo-snapshot-20261023.md): bỏ `GIT_DIFF_OPTS`, `GIT_EXTERNAL_DIFF` khỏi môi trường (5.1); `read_blobs` đọc thiếu byte → GitError (5.9, mục 7); `paths_exist`: gitlink tính là tồn tại, path chứa `\r` tra riêng, tra riêng bằng `rev-parse --verify` (5.16); TC-37, 44, 47, 49 thêm ca, TC-50. Trạng thái `implemented` → `approved` (người dùng duyệt gói sửa trước khi sửa code) | Review M4 FAIL (Major 1, 2; Minor 1–3)
| 2026-10-23 | Sửa theo review M4 lần 2 (reviews/git_repo-snapshot-20261023-r2.md): `read_blobs` đóng pipe trước khi ném lỗi mã thoát; TC-51 — không đổi hành vi, chỉ thêm test | Review M4 r2 (Minor 1, 2) |
| 2026-10-23 | M4 (D29, phục vụ `attribution` D23): `is_ancestor`, `merge_bases` (mục 3, 5.17), R19, bảng lỗi, TC-52, 53. Trạng thái về `draft` | PLAN D29 (Q36) |
| 2026-10-23 | Người dùng duyệt bản D29 → `approved` | Duyệt |
| 2026-10-23 | Test pass (TC-52, 53) → `implemented` | /feature-test |
| 2026-10-23 | Review D29 PASS_WITH_NOTES (reviews/git_repo-D29-20261023.md): TC-53 mô tả khớp test, thêm ca bỏ trùng/sắp xếp và mã lỗi; ghi rõ mã 1 + stdout khác rỗng → GitError (không đổi code) → `reviewed` | /feature-review |
| 2026-10-25 | 5.3: từ chối mật khẩu trong userinfo của `ssh://`, `git://`, `file://` và dạng scp `user:pass@host:path` (trước đây chỉ http(s)) — mật khẩu lọt vào `manifest.repo`, `Tong_quan`, `run.log` (PLAN rủi ro M5, phân tích `pipeline` N18); bảng lỗi mục 7; TC-54. Người dùng yêu cầu sửa ("Fix công việc tồn đọng") → `approved` | Tồn đọng M5 |
| 2026-10-25 | Test pass (TC-54, 84 test `test_git_repo.py`) → `implemented` | /feature-test |
| 2026-10-25 | Sửa theo review `reviews/git_repo-password-20261025.md`: 5.3 tìm userinfo theo `@` cuối sau `://` (không dùng `urlsplit`, áp cả http(s)); scheme URL tổng quát (`git+ssh`, `ssh+git`, ftp(s)) là nguồn từ xa; scp theo quy tắc git; thông báo "Không tìm thấy repo" che phần trước `@`; mục 4 cache cũ (README). TC-54 mở rộng. Chốt theo khuyến nghị, người dùng ủy quyền → `approved` | Review FAIL (Major 1, Minor 1–2, Nit) |
| 2026-10-25 | Test pass (TC-54 mở rộng, 84 test) → `implemented` | /feature-test |
| 2026-10-25 | Review r2 PASS_WITH_NOTES (`reviews/git_repo-password-20261025-r2.md`): 5.3 từ chối `<transport>::` (Minor 2); dạng scp là thư mục có thật → local (Minor 1); README ghi chú Azure DevOps `org@`. TC-54 thêm ca. Chốt theo khuyến nghị, người dùng ủy quyền | Review r2 Minor 1, 2, ghi chú 4 |
| 2026-10-25 | Toàn bộ 750 test pass, coverage 99 % → `reviewed` | /feature-test all |
