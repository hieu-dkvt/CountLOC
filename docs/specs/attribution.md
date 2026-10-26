---
id: attribution
title: Gán tác giả dòng thêm / xóa trong kỳ
type: module
milestone: M4, M5
modules: [src/loc_counter/attribution.py]
tests: [tests/test_attribution.py]
spec_refs: ["3.1", "3.3", "3.4", "3.5", "7.1", "7.2", "7.3", "7.4", "7.5", "8.2", "9", "10.3", "12", "14", "15", "16"]
depends_on: [git_repo, identity, classifier, counter, snapshot]
status: reviewed
---

# Gán tác giả dòng thêm / xóa trong kỳ

## 1. Mục đích & phạm vi
Tính **một lần cho cả kỳ** (không phụ thuộc user được chọn) ai đã thêm / xóa từng dòng trong các đoạn thay đổi (hunk) giữa C_START và C_END, ai đổi tên file, ai chạm cuối các file chỉ xử lý được theo cả file, cùng số liệu `added_code` / `deleted_code` theo user (§8.2) và cảnh báo §7.5. Kết quả là đầu vào của `builder` (dựng export end theo user, §7.3, §7.4) và của `pipeline`/`report` (M5).
**Cập nhật M5 (D35, spec `counter` A8):** mỗi dòng thêm / xóa đã gán còn mang **sha commit** (`added_commit`, `deleted_commit`), và kết quả có thống kê dòng theo commit `commit_stats` để `counter.weekly_metrics` chia code ròng theo tuần (sheet `Theo_tuan`, §10.3, §12). Không đổi cách gán account đã duyệt ở M4.
Ngoài phạm vi: dựng nội dung file và quy tắc cấp file §7.4 (`builder`), `commits` / `files_changed` / `net_code` cuối cùng và kiểm tra chéo §8.3 (M5), lọc user được chọn, ghi zip.

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Không cherry-pick / rebase; dựng theo từng dòng dựa trên so sánh file tại C_START và C_END | §7.1 |
| R2 | Dòng thêm: `git blame -w -M -C --line-porcelain C_START..C_END -- <path_at_end>`; commit trong kỳ → tác giả = author (đã gộp account); boundary → không phải dòng thêm | §7.2 |
| R3 | Dòng xóa: `git blame -w --reverse` → commit L; commit xóa = commit cũ nhất trong `rev-list --ancestry-path --reverse L..C_END -- <path>`; file bị xóa hoàn toàn → commit đã xóa file | §7.2 |
| R4 | C_START rỗng: mọi dòng của C_END là dòng thêm, không có dòng xóa | §7.2, §3.1 |
| R5 | Hunk từ diff của git `-U0` Myers; chỉ tra blame cho dòng trong hunk; dòng mới không có tác giả → bỏ + cảnh báo; dòng cũ reverse blame báo còn sống → giữ | §7.3, PLAN D24 |
| R6 | Dòng bị dời: boundary với `-w -M -C` nhưng không boundary với `-w` → gán theo lần blame thứ hai + `MOVED_LINES`; vẫn boundary → bỏ dòng mới, giữ dòng cũ, không cảnh báo | PLAN D22 |
| R7 | Dời khối trong cùng file: ghép theo nội dung (bỏ khoảng trắng) để không nhân đôi / mất khối | PLAN D28 (Q35) |
| R8 | Commit xóa ứng viên là merge M → tìm commit xóa bên từng parent (đệ quy); chỉ gán cho M khi dòng còn ở mọi parent | §16, PLAN D23 |
| R9 | Đổi tên: ghép cặp bằng `diff -M`; người đổi tên = author commit thật sự tạo đường dẫn cuối; không xác định → tên cũ + cảnh báo | §7.4, PLAN D25, D30, D31 |
| R10 | Tác giả = author (không phải committer), account theo §3.5 (`log_commits` + `AccountResolver`), không lấy tên trong porcelain | §3.5, PLAN M4 |
| R11 | `added_code` = dòng thêm của user là code theo phân loại file tại C_END; `deleted_code` = dòng xóa là code theo file tại C_START | §8.2, PLAN D27 (Q30) |
| R12 | Bộ lọc §9 áp cho cả export và đếm; rename: mỗi phía theo tên của phía đó | §9, PLAN D31 |
| R13 | Binary / quá lớn / đổi kiểu (`T`): xử lý theo cả file — commit cuối chạm file trong kỳ | PLAN D27 (Q27), D31 |
| R14 | Cảnh báo: hunk nhiều user; dòng bị nhiều user sửa liên tiếp (heuristic); vượt rename limit | §7.5, §16, PLAN D26, D27 |
| R15 | Tái lập: cùng input → cùng kết quả, kể cả thứ tự cảnh báo | §15, PLAN D31 (Q34) |
| R16 | Merge commit: dòng do giải quyết xung đột gán cho author merge; squash merge = commit thường | §16 |
| R17 | (M5) Mỗi dòng thêm / xóa đã gán lưu sha commit thêm / xóa nó, ở mọi bước gán (blame xuôi, blame lần 2 D22, reverse blame + `first_commit_after`, D23, D28 (a)(b)); account của dòng = account của commit đó | §10.3, §12, PLAN D35 (Q40) |
| R18 | (M5) Thống kê dòng / dòng code theo commit (`commit_stats`), cùng cờ code với thống kê theo user; Σ theo account = `UserLineStats` | §8.2, §10.3, §12, PLAN D35, spec `counter` A8 |

## 3. Giao diện
```python
Granularity = Literal["lines", "whole", "skip"]

@dataclass(frozen=True)
class SideInfo:
    """Một phía (C_START hoặc C_END) của cặp file."""
    path: str
    mode: str                   # "100644" | "100755" | "120000" | "160000"
    sha: str
    size: int                   # len(blob); 0 với symlink / gitlink (không đọc)
    keep: bool                  # snapshot.select_content(...).keep (§9, D13); symlink/gitlink → False
    language: str | None        # Selection.language; None → không tính *_code
    binary: bool                # is_binary(blob[:BINARY_SNIFF_BYTES]); False với symlink/gitlink
    too_large: bool             # size > max_file_size_kb * 1024
    line_count: int             # số dòng theo git (D8); 0 với file 0 byte / symlink / gitlink

@dataclass(frozen=True)
class FileAttribution:
    entry: DiffEntry
    old: SideInfo | None        # None: không có phía C_START (A, hoặc C_START rỗng)
    new: SideInfo | None        # None: file bị xóa (D)
    granularity: Granularity
    hunks: tuple[Hunk, ...]               # rỗng khi granularity != "lines"
    added_by: Mapping[int, str]           # chỉ số dòng mới (0-based, trong hunk) → account; thiếu khóa = bỏ dòng
    deleted_by: Mapping[int, str]         # chỉ số dòng cũ (0-based, trong hunk) → account; thiếu khóa = giữ dòng
    moved: frozenset[int]                 # dòng mới được gán theo D22 / D28
    renamed_by: str | None                # chỉ status "R"; None = không xác định (RENAME_UNRESOLVED)
    last_touch_by: str | None             # chỉ granularity "whole": account commit mới nhất chạm file
    # (M5, D35) đặt cuối, mặc định rỗng (Mapping chỉ đọc) — chỗ dựng theo vị trí cũ vẫn hợp lệ:
    added_commit: Mapping[int, str] = <rỗng>    # cùng khóa, cùng thứ tự với added_by → sha commit thêm dòng
    deleted_commit: Mapping[int, str] = <rỗng>  # cùng khóa, cùng thứ tự với deleted_by → sha commit xóa dòng

    @property
    def path(self) -> str:
        """entry.path (đường dẫn tại C_END, file bị xóa → tại C_START)."""

@dataclass(frozen=True)
class UserLineStats:
    account: str
    added_lines: int
    deleted_lines: int
    added_code: int             # §8.2
    deleted_code: int           # §8.2
    files: tuple[str, ...]      # FileAttribution.path user có đóng góp, sắp tăng dần (M5: files_changed)

@dataclass(frozen=True)
class CommitLineStats:          # (M5, D35; đúng giao diện spec counter mục 3)
    sha: str
    account: str                # = commit_accounts[sha]
    added_lines: int
    deleted_lines: int
    added_code: int
    deleted_code: int

@dataclass(frozen=True)
class PeriodAttribution:
    c_start: str | None
    c_end: str
    files: tuple[FileAttribution, ...]    # theo thứ tự TreeDiff.entries
    users: tuple[UserLineStats, ...]      # mọi account có commit trong kỳ, sắp theo account
    commit_accounts: Mapping[str, str]    # sha commit trong kỳ → account
    warnings: tuple[LocWarning, ...]      # sắp ổn định theo (path, kind) — mục 5.9
    commit_stats: tuple[CommitLineStats, ...] = ()  # (M5) commit có ≥ 1 dòng đã gán, sắp theo sha (A10)

    def file(self, path: str) -> FileAttribution | None: ...
    def user(self, account: str) -> UserLineStats | None: ...
    def commit(self, sha: str) -> CommitLineStats | None: ...   # (M5) None: commit không có dòng nào

MAX_MERGE_DEPTH = 64

def attribute_period(repo: GitRepo, snapshots: Snapshots, commits: Sequence[LogCommit],
                     resolver: AccountResolver, filters: FilterConfig,
                     classifier: LineClassifier | None = None) -> PeriodAttribution:
    """Gán tác giả cho mọi dòng trong hunk giữa C_START và C_END (§7.2, D22–D31)."""

def count_lines(data: bytes) -> int:
    """Số dòng theo git (D8): số '\\n' + 1 nếu đoạn cuối không rỗng."""
```
`commits` = `repo.log_commits(c_end.sha, c_start.sha if c_start else None, mailmap_rev=c_end.sha)` (người gọi đã có từ `list_period_users` — truyền vào để account khớp danh sách user). `classifier` None → `LineClassifier(filters.count_docstrings)`.

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `snapshots` | Snapshots | — | `c_end` bắt buộc; `c_start` có thể None | §3.1 |
| `commits` | Sequence[LogCommit] | — | đúng tập commit `C_START..C_END` | §3.1, §3.5 |
| `filters` | FilterConfig | — | §9 (`export_mode`, `max_file_size_kb`, `exclude_binary`, `count_docstrings`…) | §9 |
| `MAX_MERGE_DEPTH` | int | 64 | giới hạn đệ quy D23 | giả định A3 |

## 5. Luồng xử lý
Ký hiệu: `cs = snapshots.c_start.sha` hoặc None, `ce = snapshots.c_end.sha`. Mọi chỉ số dòng 0-based, khoảng nửa mở; trong thông báo hiển thị 1-based.

### 5.1 Chuẩn bị
1. `by_sha = {c.sha: c for c in commits}`; `commit_accounts = {sha: resolver.resolve(c)}`. `account(sha)` = `commit_accounts.get(sha)` (None = không thuộc kỳ).
2. `td = repo.diff_tree(cs, ce)`. `td.rename_limit_hit` → cảnh báo `RENAME_LIMIT` path `""`: `Git bỏ qua nhận diện đổi tên do quá nhiều file; file đổi tên có thể bị tính là xóa + thêm`.
3. Đọc nội dung mọi phía blob (mode ≠ `120000`, `160000`) bằng **một** lượt `repo.read_blobs` (SHA bỏ trùng, theo thứ tự xuất hiện); giữ trong `dict sha → bytes` cho tới hết hàm.

### 5.2 Thông tin từng phía và mức xử lý
Với mỗi `entry` của `td.entries`, phía cũ có khi `entry.old_path` khác None, phía mới có khi `entry.new_path` khác None.
- Symlink / gitlink: `SideInfo(path, mode, sha, 0, keep=False, language=None, binary=False, too_large=False, line_count=0)` (không đọc blob).
- Blob: `sel = snapshot.select_content(path, mode, data, filters)`; `SideInfo(path, mode, sha, len(data), sel.keep, sel.language, is_binary(data[:BINARY_SNIFF_BYTES]), len(data) > max_file_size_kb*1024, count_lines(data))`. **Không** đưa `sel.warnings` vào kết quả (cảnh báo lọc file do `plan_export` / `builder` phát).
- `granularity`:
  1. không phía nào có `keep` → `"skip"` (không blame, không thống kê);
  2. status `T`, hoặc một phía có mặt là symlink/gitlink, `binary` hoặc `too_large` → `"whole"`;
  3. còn lại → `"lines"`.
- `"whole"`: `last_touch_by = account(rev_list(ce, cs, paths)[0])` với `paths` = `old_path`, `new_path` (bỏ None, bỏ trùng); danh sách rỗng hoặc commit không thuộc kỳ → `None` + `UNATTRIBUTED` `Không xác định được người thay đổi cuối của file`. Không có hunk, không thống kê dòng.

### 5.3 Hunk (D24)
Chỉ `granularity == "lines"`:
- có cả hai phía: `hunks = repo.diff_hunks(old.sha, new.sha)` (cùng SHA → `[]`);
- chỉ phía mới: `[Hunk(0, 0, 0, new.line_count)]` nếu `line_count > 0`, ngược lại `[]` (file mới 0 byte, Q31);
- chỉ phía cũ: `[Hunk(0, old.line_count, 0, 0)]` nếu `line_count > 0`, ngược lại `[]`.

### 5.4 Dòng thêm (§7.2, D22, D24)
`R_new` = các khoảng `[h.new_start, h.new_start + h.new_count)` có `new_count > 0`. Rỗng → bỏ qua.
1. `fwd = repo.blame(ce, new.path, cs, line_ranges=R_new)` (`detect_moves=True`; `cs` None → `since=None`, có `--root` nên không có boundary).
2. Dòng không boundary: `a = account(b.sha)`; `a` khác None → `added_by[b.line] = a`, `added_commit[b.line] = b.sha`; None → dòng "không có tác giả" (UNATTRIBUTED, mục 5.8).
3. Dòng boundary (chỉ khi `cs` khác None): `again = repo.blame(ce, new.path, cs, detect_moves=False, line_ranges=[(i, i+1) ...])` cho đúng các dòng đó:
   - không boundary và thuộc kỳ → `added_by[i] = account(sha)`, `added_commit[i] = sha` (sha của lần blame thứ hai), `moved.add(i)`, `d22.add(i)`;
   - không boundary nhưng không thuộc kỳ → UNATTRIBUTED;
   - vẫn boundary → chưa gán (ứng viên ghép D28 bước a; không ghép được → bỏ dòng, **không** cảnh báo).

### 5.5 Dòng xóa (§7.2, D23, D24)
Chỉ khi `cs` khác None và có phía cũ. `R_old` = các khoảng `[h.old_start, h.old_start + h.old_count)` có `old_count > 0`.
1. `rev = repo.blame(ce, old.path, cs, reverse=True, line_ranges=R_old)`.
2. `b.sha == ce` → dòng **còn sống** → giữ (ứng viên ghép D28 bước b).
3. Ngược lại `L = b.sha`, `fn = b.filename` (đường dẫn tại L — reverse blame đã theo rename). Gom các dòng theo `(L, fn)`; mỗi nhóm `cand = repo.first_commit_after(L, ce, [fn])`.
   - `cand` None → giữ dòng + UNATTRIBUTED;
   - `cand` thuộc kỳ và không phải merge (`cand` không có trong `by_sha` → coi như không phải merge, rơi vào bước phòng thủ cuối: UNATTRIBUTED) → `deleted_by[b.line] = account(cand)`, `deleted_commit[b.line] = cand` (file bị xóa hoàn toàn: `cand` là commit xóa file);
   - `cand` là merge → `deleter = resolve_merge((L, fn, b.orig_line), cand, 1)` (5.6): commit → `deleted_by[b.line] = account(deleter)`, `deleted_commit[b.line] = deleter` (commit bên nhánh, hoặc chính merge khi dòng còn ở mọi parent); `UNDETERMINED` → giữ dòng + UNATTRIBUTED.
   - `account(...)` None (commit không thuộc kỳ — phòng thủ) → giữ dòng + UNATTRIBUTED.

### 5.6 Merge (D23) — `resolve_merge(anchor, M, depth) -> sha | UNDETERMINED`
`anchor = (S, path, j)`: dòng `j` của `path` tại commit S, S là tổ tiên của M, dòng vắng ở M. Memo theo `(S, path, j, M)`.
1. `depth > MAX_MERGE_DEPTH` → `UNDETERMINED` (log WARNING).
2. Với mỗi parent P của M **theo thứ tự `parents`**, tính `side(P)`:
   1. Tìm neo trên lịch sử của P:
      - `repo.is_ancestor(S, P)` → neo = `(S, path, j)`;
      - ngược lại `bases = repo.merge_bases(S, P)`; `len(bases) != 1` → `side = UNDETERMINED`. Với `base`: `fb = repo.blame(S, path, base, detect_moves=False, line_ranges=[(j, j+1)])[0]`; `fb.boundary == False` → dòng sinh sau base, P chưa từng có → `side = PRESENT`; ngược lại neo = `(fb.sha, fb.filename, fb.orig_line)`, `repo.is_ancestor(fb.sha, P)` sai → `UNDETERMINED`.
   2. neo.commit `== P` → `PRESENT` (không gọi blame với `since == end`: git báo `More than one commit to dig up from`).
   3. `r = repo.blame(P, neo.path, neo.commit, reverse=True, line_ranges=[(neo.j, neo.j+1)])[0]`; `r.sha == P` → `PRESENT`.
   4. Ngược lại `c = repo.first_commit_after(r.sha, P, [r.filename])`: None → `UNDETERMINED`; `c` không phải merge → `side = c`; `c` là merge → `side = resolve_merge((r.sha, r.filename, r.orig_line), c, depth + 1)`.
3. Duyệt `side(P)` theo thứ tự parent: gặp kết quả đầu tiên khác `PRESENT` → trả nó (commit xóa, hoặc `UNDETERMINED`). Mọi parent `PRESENT` → trả `M` (merge tự xóa / giải quyết xung đột, §16).
Có thể gom nhiều dòng cùng `(S, path, M)` vào một lệnh blame nhiều `-L` — kết quả phải như gọi từng dòng.

### 5.7 Ghép dời khối trong file (D28)
Chỉ `granularity == "lines"` có **cả hai phía**. `key(line) = bytes của dòng bỏ mọi byte trong b" \t\n\v\f\r"` (như `-w`). Dòng lấy từ blob theo D8 (tách sau mỗi `\n`).
Tập ban đầu (đều tăng dần): `U` = dòng mới trong hunk chưa có `added_by` và không UNATTRIBUTED (vẫn boundary sau 2 lần blame); `O` = dòng cũ trong hunk **còn sống** (5.5 bước 2); `X` = dòng cũ trong hunk có `deleted_by`; `N` = dòng của `d22` (5.4 bước 3).
- (0) **Cặp chỉ đổi khoảng trắng** (D22): mỗi `u ∈ U`: dòng `o` nhỏ nhất của `O` chưa dùng có `key(o) == key(u)` → bỏ `u` khỏi `U`, bỏ `o` khỏi `O`, **không gán** (dòng mới bị bỏ, dòng cũ được giữ như D22).
- (a) Mỗi `u` còn lại trong `U`: dòng `x` nhỏ nhất của `X` chưa dùng có `key(x) == key(u)` → `added_by[u] = deleted_by[x]`, `added_commit[u] = deleted_commit[x]` (commit đã dời khối), `moved.add(u)`, đánh dấu `x` đã dùng.
- (b) Mỗi `o` còn lại trong `O`: dòng `n` nhỏ nhất của `N` chưa dùng có `key(n) == key(o)` → `deleted_by[o] = added_by[n]`, `deleted_commit[o] = added_commit[n]`, đánh dấu `n` đã dùng.
Bước (0) chạy trước để dòng chỉ đổi khoảng trắng không bị ghép với dòng cùng nội dung ở chỗ khác (dòng bị xóa ở hunk khác, hoặc dòng dời từ file khác vào). Tra "nhỏ nhất chưa dùng" bằng chỉ mục `key → hàng đợi chỉ số tăng dần` (tuyến tính theo số dòng, kết quả như duyệt tuần tự).
Thứ tự: 5.4 → 5.5 → 5.7 → 5.8.

### 5.8 Đổi tên, cảnh báo theo file
- **`renamed_by`** (status `R`, D25/D30): `xs = repo.rev_list(ce, cs, [new_path], reverse=True)`; người tạo = các `X` **thuộc kỳ** (có trong `by_sha`; commit khác bị bỏ qua) mà `paths_exist([(X, new_path)])` đúng và với mọi parent `p` của `by_sha[X]`, `paths_exist([(p, new_path)])` sai (không có parent → tạo). Lấy **phần tử cuối** (lần tạo gần nhất). Có → `renamed_by = account(X)`; không có (hoặc không thuộc kỳ) → `None` + `RENAME_UNRESOLVED` (path = `new_path`): `Không xác định được người đổi tên <old_path> → <new_path>; export dùng tên cũ`. `paths_exist` tính cả thư mục là tồn tại (D31/Q33). Gom mọi `(commit, path)` cần tra vào một lần gọi `paths_exist`.
- **UNATTRIBUTED** (mỗi file tối đa một cảnh báo): `Không xác định được tác giả: dòng mới <khoảng>; dòng cũ <khoảng>` (chỉ phần có), khoảng 1-based gộp liền kề, vd. `3–5, 9`.
- **MOVED_LINES** (mỗi file tối đa một): `Dòng bị dời được gán cho người dời: dòng mới <khoảng>` theo `moved`.
- Với mỗi hunk có cả dòng cũ và dòng mới, sau 5.7: `D = {deleted_by[i]}` của dòng cũ, `A = {added_by[k]}` của dòng mới (bỏ dòng không có):
  - **MULTI_USER_HUNK** khi `|D ∪ A| ≥ 2` (Q32): `Hunk dòng cũ <a–b> / dòng mới <c–d> có thay đổi của nhiều user: <account1, account2…>` (account sắp tăng dần; khoảng 1 dòng ghi một số, vd. `10`; phía rỗng ghi `—`);
  - **SEQUENTIAL_EDIT** khi có `d ∈ D`, `x ∈ A`, `x ≠ d` (D26): `Dòng cũ <a–b> bị <d…> xóa và <x…> viết lại; chỉ gán được cho người sửa cuối` (`<d…>` = mọi account của D, `<x…>` = mọi account của A, sắp tăng dần, cách nhau `, `).
  Hunk chỉ có dòng mới hoặc chỉ dòng cũ nhưng nhiều account → chỉ MULTI_USER_HUNK.
- `path` của cảnh báo = `FileAttribution.path` (spec `counter` 5.2).

### 5.9 Thống kê và kết quả
1. `added_code`: phía mới `keep and language is not None` → `flags = classifier.classify(decode_text(data), new.path, new.sha)`; `len(flags) != new.line_count` → log WARNING, coi cờ thiếu là `False`. Mỗi `i` trong `added_by`: `added_lines += 1`, `added_code += flags[i]`. Phía không đủ điều kiện → chỉ `added_lines`.
2. `deleted_code`: như trên với phía cũ (nội dung tại C_START) và `deleted_by`.
3. `files` của user: `FileAttribution.path` mà account có trong `added_by`, `deleted_by`, `renamed_by` hoặc `last_touch_by` — gồm **cả file không phải source** (`full`, file `whole`); `files_changed` §8.2 (chỉ file source) do M5 lọc lại theo `SideInfo.language`.
4. `users`: mọi account trong `commit_accounts` (kể cả 0 dòng) ∪ account xuất hiện ở trên, sắp tăng dần.
4a. **(M5) `commit_stats`** — tính trong **cùng vòng lặp** với bước 1–2, cùng `flags` (phân loại mỗi phía một lần): mỗi `i` trong `added_by` cộng vào ô `added_commit[i]` (`added_lines += 1`, `added_code += flags[i]`); mỗi `i` trong `deleted_by` cộng vào ô `deleted_commit[i]` tương tự. `account` của ô = `commit_accounts[sha]`. Chỉ có ô cho commit có ≥ 1 dòng đã gán (A10); file `whole`, `skip`, `renamed_by`, `last_touch_by` không tạo ô. Sắp theo `sha` tăng dần (chuỗi hex). Commit merge có thể có ô (dòng giải quyết xung đột §16, merge tự xóa D23).
4b. **(M5) Bất biến** (test TC-38..40): với mọi `FileAttribution` — `added_commit.keys() == added_by.keys()` (cùng thứ tự), `commit_accounts[added_commit[i]] == added_by[i]`; tương tự `deleted_commit` / `deleted_by`. Với mọi account `a`: Σ `added_lines`, `deleted_lines`, `added_code`, `deleted_code` của các ô `commit_stats` có `account == a` bằng đúng trường tương ứng của `user(a)`.
5. Cảnh báo phát theo thứ tự: `RENAME_LIMIT`; rồi từng file theo `td.entries`: `RENAME_UNRESOLVED`, `UNATTRIBUTED`, `MOVED_LINES`, rồi theo hunk tăng dần `MULTI_USER_HUNK`, `SEQUENTIAL_EDIT`. Cuối cùng `sorted(..., key=(path, kind))` (**ổn định**, giữ thứ tự dòng trong cùng `(path, kind)`, D31/Q34).
6. `added_by`, `deleted_by`, `added_commit`, `deleted_commit` dựng theo chỉ số tăng dần (dict giữ thứ tự chèn), bọc chỉ đọc → tái lập. Log INFO: số file, số dòng thêm/xóa đã gán, số cảnh báo.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Dòng ngoài hunk không có trong `added_by` / `deleted_by` → builder luôn giữ (D24).
- Chỉ đổi khoảng trắng / EOL (CRLF→LF, thụt lề): hunk có, blame `-w` → dòng mới boundary, dòng cũ còn sống → giữ bản C_START, không cảnh báo (D22). D28 bước (0) ghép cặp này trước nên nó không bị ghép với dòng trùng nội dung ở hunk khác / dòng dời từ file khác (TC-34, 35).
- Rename 100% (cùng SHA) → không hunk, không thống kê dòng, chỉ `renamed_by` (§14 "rename không tính là xóa + thêm"). Rename có sửa → hunk giữa hai blob.
- Rename độ giống < 50% → `D` + `A` (git); reverse blame theo được rename nên dòng chung của phía cũ "còn sống" (giữ), dòng tương ứng phía mới boundary (bỏ) → tương đương "file không đổi tên".
- Chuỗi đổi tên a→b→c: người đổi tên = người tạo `c`.
- File bị xóa rồi tạo lại cùng tên → `M` (Q26): dòng chung giữ, phần khác gán theo blame.
- File mới 0 byte: không hunk, không thống kê (builder bỏ theo Q31).
- Commit trên nhánh tách trước C_START nhưng merge vào trong kỳ thuộc `C_START..C_END` (§3.1) và được gán dòng dù author date trước start.
- Squash merge = commit thường (§16). Merge commit không nhận dòng trừ khi dòng còn ở mọi parent (D23) hoặc blame xuôi trả chính merge (dòng giải quyết xung đột, §16).
- Bot là account bình thường ở đây; lọc bot là việc của builder / pipeline (D21).
- `SEQUENTIAL_EDIT` luôn đi kèm `MULTI_USER_HUNK` cho cùng hunk — phát cả hai (D31).
- **(M5) sha của dòng:** dòng thêm → commit blame trả (lần 1, hoặc lần 2 với D22); dòng xóa → commit xóa (5.5) hoặc kết quả `resolve_merge` (commit bên nhánh, hoặc chính merge); D28 (a)(b) → sha của dòng được ghép. Một account nhiều email → nhiều sha, cùng account. Dòng không gán (UNATTRIBUTED, bỏ dòng, giữ dòng) không có sha.
- **(M5) `commit_stats` không lọc bot / user:** chứa mọi commit có dòng; `weekly_metrics` lọc theo `accounts` (D21). Commit có author date ngoài kỳ (nhánh tách sớm) vẫn có ô (D35 "tuần ngoài kỳ vẫn giữ").

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo (tiếng Việt) | Log |
|---|---|---|---|
| Lỗi git (blame, diff, rev-list…) | `GitError` lan ra | (từ `git_repo`) | WARNING (từ `git_repo`) |
| Vượt rename limit | cảnh báo `RENAME_LIMIT` | `Git bỏ qua nhận diện đổi tên do quá nhiều file; file đổi tên có thể bị tính là xóa + thêm` | WARNING |
| Không xác định người đổi tên | `RENAME_UNRESOLVED` | `Không xác định được người đổi tên <cũ> → <mới>; export dùng tên cũ` | — |
| Dòng không xác định tác giả / người xóa | `UNATTRIBUTED` | `Không xác định được tác giả: dòng mới <…>; dòng cũ <…>` | DEBUG từng dòng |
| File whole không xác định người chạm cuối | `UNATTRIBUTED` | `Không xác định được người thay đổi cuối của file` | — |
| Dòng dời | `MOVED_LINES` | `Dòng bị dời được gán cho người dời: dòng mới <…>` | — |
| Hunk nhiều user | `MULTI_USER_HUNK` | `Hunk dòng cũ <…> / dòng mới <…> có thay đổi của nhiều user: <…>` | — |
| Sửa liên tiếp | `SEQUENTIAL_EDIT` | `Dòng cũ <…> bị <…> xóa và <…> viết lại; chỉ gán được cho người sửa cuối` | — |
| Vượt `MAX_MERGE_DEPTH` | dòng thành UNATTRIBUTED | (như trên) | WARNING |
| Số cờ phân loại ≠ số dòng | coi cờ thiếu là không phải code | — | WARNING |
Thông báo không chứa lệnh git, URL hay token.

## 8. Bảo mật, hiệu năng, tái lập
- Không nhận token; mọi git qua `GitRepo`.
- Hiệu năng M4: mỗi file "lines" 1 diff + 1–2 blame xuôi + 1 blame ngược + `first_commit_after` theo nhóm `(L, filename)`; D23 thêm blame cho từng parent. Blob giữ trong bộ nhớ trong một lần chạy. (M5) sha và `commit_stats` không thêm lệnh git nào, không phân loại lại (dùng chung cờ 5.9). Tối ưu (song song, cache) để M7.
- Tái lập: thứ tự file theo `diff_tree`; dict theo chỉ số tăng dần; lựa chọn "đầu tiên" theo thứ tự topo của git hoặc thứ tự `parents`; cảnh báo sắp ổn định (5.9); `users` sắp theo account. Không phụ thuộc cấu hình git toàn cục (nhờ `git_repo`).

## 9. Test cases
Fixture: `section14_repo` (conftest) và các repo nhỏ dựng trong `tests/conftest.py` / `tests/test_attribution.py` (ngày cố định, không mạng). `resolver = AccountResolver()` (không GitHub), `filters = FilterConfig()` trừ khi ghi khác. Hunk viết `(old_start, old_count, new_start, new_count)`.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-attribution-01 | §14 theo user (bắt buộc D) | `section14_repo()`, kỳ 2026-01-01..2026-01-31 | alice `added_code=5, deleted_code=2`; bob `added_code=8, deleted_code=1`; commit "alice late" không ảnh hưởng | integration |
| TC-attribution-02 | §14 chi tiết dòng | như TC-01 | `app.py`: hunks `[(2,2,2,0),(13,1,11,0),(15,0,12,7)]`; `deleted_by == {2: alice, 3: alice, 13: bob}`; `added_by` = 12..18 → alice; `util.py` (A): `added_by` 0..7 → bob; alice `added_lines=7, deleted_lines=2`; `users` = alice, bob (sắp tăng dần); không cảnh báo | integration |
| TC-attribution-03 | start trước commit đầu (bắt buộc D) | §14 với kỳ 2025-12-01..2026-01-31 (C_START rỗng) | mọi file `A`; mọi dòng C_END có `added_by`, `deleted_by` rỗng; `added_code`: admin 7 (v2..v8 còn tại C_END), alice 5, bob 8; mọi `deleted_code` 0; không gọi reverse blame (spy) | integration |
| TC-attribution-04 | Block comment nhiều dòng (bắt buộc D) | alice thêm docstring `"""…"""` 5 dòng vào `.py` và `/* … */` 4 dòng vào `.js` | `added_lines` 9, `added_code` 0 | integration |
| TC-attribution-05 | Rename không tính xóa + thêm (bắt buộc D) | bob `git mv old.py new.py` (không sửa) | 1 entry `R`, `hunks == ()`, `added_by`/`deleted_by` rỗng, `renamed_by == bob`, bob `added_code == deleted_code == 0` | integration |
| TC-attribution-06 | Rename + sửa, cả hai thứ tự | (a) bob mv rồi alice thêm 1 dòng; (b) alice thêm dòng rồi bob mv | `R`, `added_by == {10: alice}`, `renamed_by == bob` ở cả hai | integration |
| TC-attribution-07 | Chuỗi rename | bob a→b, alice b→c | `R` a→c, `renamed_by == alice` | integration |
| TC-attribution-08 | Rename qua merge, nhánh tách trước C_START (D30) | bob đổi tên trên `feat` (tách trước start), carol merge vào main trong kỳ | `renamed_by == bob` (không phải carol) | integration |
| TC-attribution-09 | RENAME_UNRESOLVED (Q33) | rename tới `x/y.py` mà parent của commit tạo có **thư mục** `x/y.py` | `renamed_by is None`; cảnh báo `RENAME_UNRESOLVED` path `x/y.py`, thông báo có tên cũ và mới | integration |
| TC-attribution-10 | Rename độ giống < 50% | bob `git mv` (commit 1) rồi sửa > 50% dòng (commit 2) | `D old.py` + `A new.py`; dòng chung: phía cũ không có `deleted_by`, phía mới không có `added_by`; dòng bob viết mới có `added_by` bob | integration |
| TC-attribution-11 | Merge song song (Q20/D23) | C_START: v1..v9; bob xóa v2 trên `feat`, alice sửa v7 trên main, carol merge không xung đột | v2 → bob, v7 cũ → alice, v7 mới → alice; carol không có dòng | integration |
| TC-attribution-12 | Như TC-11, `feat` tách trước C_START | như TC-11 | v2 → bob, v7 → alice (dùng `merge_bases`) | integration |
| TC-attribution-13 | Merge tự xóa dòng | hai parent đều còn v5, merge (carol) xóa v5 | v5 → carol | integration |
| TC-attribution-14 | Xung đột (§16) | alice sửa v5 trên main, bob sửa v5 trên `feat`, carol merge `feat` vào main (parent đầu = main) và giải quyết xung đột | v5 cũ → alice (commit đầu tiên của `first_commit_after` theo thứ tự topo — không qua D23 vì ứng viên không phải merge; đã kiểm chứng), v5 mới → carol; `SEQUENTIAL_EDIT` và `MULTI_USER_HUNK` cho hunk đó | integration |
| TC-attribution-15 | Guard `S == T` và giới hạn độ sâu | parent của merge == L (spy `blame`); monkeypatch `MAX_MERGE_DEPTH = 0` | không gọi blame với `since == end`, không GitError; độ sâu vượt → dòng cũ giữ + `UNATTRIBUTED`, log WARNING | integration |
| TC-attribution-16 | Dời sang file khác (D22) | bob dời 2 dòng ≥ 40 ký tự từ `a.py` sang `b.py` trong 1 commit | `b.py`: 2 dòng → bob, thuộc `moved`, cảnh báo `MOVED_LINES`; `a.py`: 2 dòng cũ → bob | integration |
| TC-attribution-17 | Dời khối trong file, dòng cũ "còn sống" (D28 b) | file 8 dòng dài: alice dời khối 4 dòng đầu xuống cuối (hoán đổi hai khối) — điều kiện tiên quyết: reverse blame báo 4 dòng cũ còn sống | 4 dòng mới → alice; 4 dòng cũ tương ứng `deleted_by` alice; mọi dòng trong hunk đã gán; `MOVED_LINES` | integration |
| TC-attribution-18 | Dời khối rồi đổi khoảng trắng (D28 a) | như TC-17, sau đó carol đổi thụt lề khối **bị hoán chỗ** (nay ở đầu file) — điều kiện tiên quyết: dòng mới của khối boundary sau 2 lần blame | dòng mới của khối có `added_by` (không bị bỏ), cùng account với `deleted_by` của dòng cũ ghép được; `MOVED_LINES` | integration |
| TC-attribution-19 | Tái dựng "mọi user" = C_END (§8.3, D21) | các repo TC-02, 11, 14, 16, 17, 18 (trùng byte) và TC-34, 35 (đa tập dòng bỏ khoảng trắng): áp §7.3 với `users` = mọi account (hàm trợ giúp trong test) | nội dung từng file `lines` trùng byte với blob C_END | integration |
| TC-attribution-20 | Chỉ đổi khoảng trắng / CRLF→LF | carol đổi thụt lề một dòng và CRLF→LF cả file | hunk có; `added_by`, `deleted_by` rỗng; không cảnh báo | integration |
| TC-attribution-21 | Xóa rồi tạo lại (Q26) | alice `git rm a.py`, bob tạo lại `a.py` với 3/6 dòng như cũ | 1 entry `M`; dòng khác nhau: cũ → alice, mới → bob; dòng chung ngoài hunk | integration |
| TC-attribution-22 | File bị xóa hoàn toàn | alice `git rm util.py` | `D`, mọi dòng cũ → alice; alice `deleted_code` = số dòng code của file | integration |
| TC-attribution-23 | File mới 0 byte (Q31) | bob tạo `x.py` rỗng | `granularity "lines"`, `hunks == ()`, không thống kê | integration |
| TC-attribution-24 | Binary / quá lớn / T (Q27, D31) | `FilterConfig(export_mode="full", exclude_binary=False, max_file_size_kb=1)`: alice rồi bob sửa `logo.png`; file `.py` > giới hạn; `T` file → symlink | `granularity "whole"`, `last_touch_by == bob` (người sửa cuối), không blame (spy), không thống kê | integration |
| TC-attribution-25 | skip và bộ lọc theo phía | `README.md` (source_only), symlink, submodule; rename `src/a.py` → `vendor/a.py` | 3 cái đầu `"skip"`, không blame; rename: phía cũ `keep`, phía mới không → `"lines"`, `deleted_code` theo phía cũ, `added_code` 0 (D31) | integration |
| TC-attribution-26 | `export_mode: full` file không phải source | `notes.txt` sửa bởi alice, `full` | `"lines"`, `added_by` có, `added_code == 0` | integration |
| TC-attribution-27 | RENAME_LIMIT | monkeypatch `diff_tree` trả `TreeDiff(..., rename_limit_hit=True)` | đúng 1 cảnh báo `RENAME_LIMIT` path `""`, đứng đầu danh sách | unit |
| TC-attribution-28 | Account theo log, không theo porcelain | alice commit bằng 2 email (noreply + công ty) gộp qua `identities.yaml`; committer khác author | mọi dòng của alice → cùng account `alice`; không phải committer; `commit_accounts` đúng | integration |
| TC-attribution-29 | MULTI_USER_HUNK + thứ tự cảnh báo (Q34) | hunk 1 (dòng 3–4): alice xóa, bob viết; hunk 2 (dòng 10): bob xóa, carol viết | cảnh báo `[MULTI_USER_HUNK h1, MULTI_USER_HUNK h2, SEQUENTIAL_EDIT h1, SEQUENTIAL_EDIT h2]` (sắp `(path, kind)` ổn định); thông báo 1-based, account sắp tăng dần; chạy 2 lần → kết quả bằng nhau | integration |
| TC-attribution-30 | Cấu hình git toàn cục "khó chịu" | `GIT_CONFIG_GLOBAL`: `diff.algorithm=patience`, `blame.ignoreRevsFile=.nope`, `diff.renames=copies` | kết quả TC-02 không đổi | integration |
| TC-attribution-31 | Không có commit trong kỳ | C_START == C_END | `files == ()`, `users == ()`, không cảnh báo, không gọi blame | integration |
| TC-attribution-32 | count_lines | `b""`, `b"a"`, `b"a\n"`, `b"a\nb"`, `b"a\r\nb\r\n"`, `b"\n\n"` | 0, 1, 1, 2, 2, 2 | unit |
| TC-attribution-34 | Chỉ đổi thụt lề + dòng trùng nội dung bị xóa ở hunk khác (review Major 1) | C_START: `f()` có `pass`, `g()` có `pass`; alice xóa `pass` trong `g()`; bob bọc thân `f()` trong `if cond:` (thụt lề `pass`) | dòng `pass` mới trong `f()` không có `added_by`; `pass` cũ của `f()` không có `deleted_by`; `pass` của `g()` → alice; alice `added_code=0, deleted_code=1`; không `MOVED_LINES` cho `pass`; TC-19: đa tập dòng (bỏ khoảng trắng) của bản tái dựng mọi user bằng C_END — không mất, không nhân đôi (dòng chỉ đổi khoảng trắng giữ bản C_START theo D22, như TC-20) | integration |
| TC-attribution-35 | Chỉ đổi thụt lề + dòng trùng nội dung dời từ file khác vào (review Major 2) | carol thụt lề lại dòng Z (≥ 40 ký tự) trong `a.py`; bob dời dòng giống hệt Z từ `b.py` sang `a.py` | dòng Z cũ của `a.py` không có `deleted_by`; dòng Z bob dời vào → bob (`moved`); bob `deleted_code=1` (chỉ ở `b.py`); TC-19: đa tập dòng (bỏ khoảng trắng) bằng C_END như TC-34 | integration |
| TC-attribution-36 | Merge lồng nhau (D23 đệ quy) | alice sửa v7 trên main (trước các commit nhánh); bob sửa v5 trên `feat`, bob xóa v2 trên `feat2` → dave merge `feat2` vào `feat` → carol merge `feat` vào main | v2 → bob, v7 → alice; carol, dave không có dòng; spy: `resolve_merge` được gọi với merge ngoài ở độ sâu 1 và merge trong ở độ sâu 2 | integration |
| TC-attribution-37 | Nhánh phòng thủ D23 / whole / phân loại | (a) monkeypatch `repo.merge_bases` trả 2 SHA cho kịch bản TC-12; (b) monkeypatch `repo.rev_list` trả `[]` cho file `whole`; (c) classifier giả trả thiếu cờ; (d) rename mà commit tạo path không có trong `commits` nhưng commit thuộc kỳ trước đó có tạo path; (e) repo giả cho `_parent_side`, `resolve_merge`, `_added_lines` | (a) v2 giữ + `UNATTRIBUTED`; (b) `last_touch_by is None` + `UNATTRIBUTED` `Không xác định được người thay đổi cuối của file`; (c) log WARNING, cờ thiếu coi là không phải code; (d) `renamed_by` = account của commit thuộc kỳ (commit ngoài kỳ bị bỏ qua); (e) unit với repo giả: neo merge-base — dòng sinh sau base → PRESENT, `fb` không phải tổ tiên của parent → UNDETERMINED, `first_commit_after` None → UNDETERMINED; memo `resolve_merge`; blame lần 2 trả commit ngoài kỳ → UNATTRIBUTED | unit + integration |
| TC-attribution-33 | Commit không thuộc kỳ (phòng thủ) | `commits` truyền thiếu commit của bob | dòng của bob: mới không gán, cũ giữ; `UNATTRIBUTED` cho từng file bị ảnh hưởng | integration |
| TC-attribution-38 | (M5) §14 — sha theo dòng và `commit_stats` | như TC-01 | `app.py`: `added_commit` 12..18 = sha "alice add", `deleted_commit == {2: "alice del", 3: "alice del", 13: "bob del"}`; `util.py`: `added_commit` 0..7 = "bob util"; `commit_stats` đúng 4 ô sắp theo sha: alice add `7/0/5/0`, bob util `8/0/8/0`, alice del `0/2/0/2`, bob del `0/1/0/1` (`added_lines/deleted_lines/added_code/deleted_code`); không có "alice late", không có ô của admin; `commit(sha "bob del").account == bob`, `commit(<sha không có dòng>) is None` | integration |
| TC-attribution-39 | (M5) sha qua merge (D23, §16) | repo TC-11, 13, 14, 36 | TC-11: `deleted_commit` v2 = commit bob trên `feat`, v7 cũ / mới = commit alice; không có ô của merge carol. TC-13: v5 → sha merge carol, có ô merge `0/1/…`. TC-14: v5 mới → `added_commit` = sha merge carol, v5 cũ → commit alice. TC-36: v2 → commit bob trên `feat2`; không có ô của dave, carol | integration |
| TC-attribution-40 | (M5) sha của dòng dời (D22, D28) | repo TC-16, 17, 18 | TC-16: dòng của `b.py` có `added_commit` = commit dời của bob (lần blame 2), dòng cũ `a.py` `deleted_commit` = cùng commit. TC-17: mỗi cặp ghép (b): `deleted_commit[o] == added_commit[n]` = commit dời của alice. TC-18: mỗi cặp ghép (a): `added_commit[u] == deleted_commit[x]` | integration |
| TC-attribution-41 | (M5) Bất biến 4b trên nhiều repo | kết quả `attribute_period` của các repo TC-02, 03, 11, 14, 16, 17, 18, 21, 22, 25, 28, 33, 34, 35, 36 (hàm trợ giúp trong test) | với mọi file: khóa / thứ tự `added_commit` = `added_by`, account khớp `commit_accounts`; tương tự phía xóa; Σ `commit_stats` theo account = `UserLineStats` (4 trường); `commit_stats` sắp theo sha, không có ô toàn 0, mọi sha thuộc `commit_accounts`; chạy 2 lần → bằng nhau | integration |
| TC-attribution-42 | (M5) Không tạo ô / nhiều email | (a) repo TC-05 (rename thuần); (b) TC-24 (`whole`); (c) TC-31 (không commit); (d) TC-03 (C_START rỗng); (e) TC-28 (alice 2 email) | (a)(b)(c) `commit_stats == ()`; (d) có ô cho commit admin (`added_code` 7), alice, bob, mọi `deleted_*` = 0; (e) hai ô sha khác nhau, cùng `account == "alice"`, tổng = `user("alice")` | integration |
| TC-attribution-43 | (M5) Tương thích dựng theo vị trí | `FileAttribution(...)` 10 tham số vị trí như `tests/test_builder.py`; `PeriodAttribution(...)` 6 tham số | `added_commit`, `deleted_commit` rỗng, chỉ đọc; `commit_stats == ()`; `commit("x") is None`; TC-01..37 và test `builder` không đổi | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | `attribute_period` nhận `commits` từ người gọi (không tự gọi `log_commits`) để account khớp danh sách user và không chạy git lại | Giả định | Đã duyệt 2026-10-23 |
| A2 | Attribution không phát lại cảnh báo lọc file (`TOO_LARGE`, `BINARY`, `UNKNOWN_LANGUAGE`, `UNSAFE_PATH`) — `plan_export` / `builder` đã phát | Giả định | Đã duyệt 2026-10-23 |
| A3 | Giới hạn đệ quy D23 `MAX_MERGE_DEPTH = 64`; vượt → UNATTRIBUTED. Nhiều merge-base (criss-cross) → bên parent đó `UNDETERMINED` | Giả định | Đã duyệt 2026-10-23 |
| A4 | `"whole"`: `last_touch_by` = commit mới nhất theo thứ tự topo của `rev_list` (đơn giản hóa lịch sử mặc định: merge chỉ xuất hiện khi khác mọi parent → khi đó là author merge, §16) | Giả định (cách thực hiện Q27) | Đã duyệt 2026-10-23 |
| A5 | `added_code`/`deleted_code` chỉ tính file `"lines"`; file `"whole"` (binary, quá lớn) không có số liệu dòng (không đếm LOC, khớp §6.3/§9) | Giả định | Đã duyệt 2026-10-23 |
| A6 | `users` gồm mọi account có commit trong kỳ (kể cả 0 dòng, chỉ merge) để M5 ghép với danh sách user | Giả định | Đã duyệt 2026-10-23 |
| A7 | Khóa ghép D28 = dòng bỏ mọi khoảng trắng ASCII (như `blame -w`), ghép 1–1 theo dòng tăng dần, gồm cả dòng trống | Cách thực hiện D28 | Đã duyệt 2026-10-23 |
| A8 | Hàm `path_creator` nêu trong PLAN M4 không có trong `git_repo` đã duyệt; D25/D30 thực hiện bằng `rev_list` + `paths_exist` trong attribution | Làm rõ | Đã duyệt 2026-10-23 |
| A9 | (M5) sha lưu thành hai Mapping riêng `added_commit` / `deleted_commit` cùng khóa với `added_by` / `deleted_by` (không đổi kiểu `added_by` thành cặp) — `builder` và test M4 không đổi; trường mới đặt cuối dataclass, mặc định rỗng | Cách thực hiện D35 | Chốt theo khuyến nghị 2026-10-24 (*) |
| A10 | (M5) `commit_stats` chỉ có commit có ≥ 1 dòng đã gán (không có ô toàn 0); số commit theo tuần lấy từ `commits` (spec `counter` 5.8), không từ đây | Giả định | Chốt theo khuyến nghị 2026-10-24 (*) |
| A11 | (M5) D28 (a): dòng mới ghép được nhận sha **commit xóa** dòng cũ tương ứng (commit đã dời khối), (b) dòng cũ nhận sha của dòng mới D22 — nhất quán với account đã gán ở M4 | Cách thực hiện D35 + D28 | Chốt theo khuyến nghị 2026-10-24 (*) |

(*) Người dùng ủy quyền "làm theo khuyến nghị không cần xác nhận lại" (2026-10-24); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-23 | Tạo mới theo phân tích `spec-analyst` (kiểm chứng git 2.55) và quyết định D28–D31 | M4 |
| 2026-10-23 | Người dùng duyệt (A1–A8) → `approved` | Duyệt |
| 2026-10-23 | Làm rõ khi viết test (không đổi hành vi): định dạng khoảng trong thông báo (một dòng → một số, phía rỗng `—`), danh sách account của `SEQUENTIAL_EDIT`; thứ tự kiểm `cand` ngoài kỳ (5.5); kịch bản fixture TC-10, 17, 18, bộ lọc TC-24, số file TC-33 | /feature-implement (test-engineer) |
| 2026-10-23 | Test pass (TC-01..33, 46 test) → `implemented` | /feature-test |
| 2026-10-23 | Sửa theo review (reviews/attribution-20261023.md, FAIL): D28 thêm bước (0) ghép cặp chỉ đổi khoảng trắng trước (a)/(b) và tra bằng chỉ mục theo khóa (Major 1, 2, Minor 1); `renamed_by` bỏ qua commit ngoài kỳ (Minor 3); `files` gồm cả file không phải source (ghi chú 3); TC-34..37 (Minor 2). Trạng thái `implemented` → `draft` | Review attribution FAIL |
| 2026-10-23 | Người dùng duyệt bản sửa theo review → `approved` | Duyệt |
| 2026-10-23 | TC-19 với TC-34/35: so đa tập dòng bỏ khoảng trắng thay vì trùng byte (dòng chỉ đổi khoảng trắng giữ bản C_START theo D22) — sửa kỳ vọng sai của spec, không đổi hành vi; chốt theo khuyến nghị (người dùng ủy quyền 2026-10-23) | /feature-test |
| 2026-10-23 | Test pass (TC-01..37, 55 test) → `implemented` | /feature-test |
| 2026-10-23 | Sửa theo review r2 (reviews/attribution-20261023-r2.md, FAIL do test): fixture TC-36 chạy thật tới độ sâu 2 (spy `resolve_merge`); TC-37 (e) unit cho nhánh phòng thủ D23 / blame lần 2 — chỉ đổi test | Review r2 (Major 1, Minor 2) |
| 2026-10-23 | Test pass (TC-01..37, 58 test); review r3 PASS (reviews/attribution-20261023-r3.md) → `reviewed` | /feature-review |
| 2026-10-24 | Cập nhật M5 (D35, spec `counter` A8): `FileAttribution.added_commit` / `deleted_commit`, `CommitLineStats`, `PeriodAttribution.commit_stats` + `commit()`; gán sha ở 5.4, 5.5, 5.7; 5.9 bước 4a, 4b; R17, R18; TC-38..43; A9–A11. Không đổi cách gán account M4. Trạng thái `reviewed` → `draft` | PLAN M5 |
| 2026-10-24 | Chốt A9–A11 theo khuyến nghị (người dùng ủy quyền) → `approved` | Duyệt |
| 2026-10-24 | Test pass (TC-01..43, 75 test; toàn bộ 512) → `implemented` | /feature-test |
| 2026-10-24 | Review PASS_WITH_NOTES (reviews/attribution-20261024.md); sửa Minor: TC-41 thêm repo TC-24, TC-28 và kiểm chạy 2 lần cho TC-21, 22, 24, 25, 28, 33 (chỉ đổi test) → `reviewed` | /feature-review |
