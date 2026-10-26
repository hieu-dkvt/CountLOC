---
id: builder
title: Dựng export end theo user
type: module
milestone: M4, M5
modules: [src/loc_counter/builder.py]
tests: [tests/test_builder.py]
spec_refs: ["3.3", "3.4", "3.5", "7.1", "7.3", "7.4", "7.5", "8.3", "9", "12", "14", "15", "16"]
depends_on: [attribution, snapshot, counter, identity, git_repo]
status: reviewed
---

# Dựng export end theo user

## 1. Mục đích & phạm vi
Từ kết quả `attribution` (một lần cho cả kỳ) và export start (`snapshot.plan_export(C_START)`), dựng **export end cho tập user được chọn** = source tại C_START + chỉ các thay đổi (thêm và xóa) của các user đó (§3.3), theo từng dòng (§7.3) và quy tắc cấp file (§7.4); đặt `user-tag`, lên danh sách các zip end cần ghi (gộp / xuất riêng / tất cả user, D21, Q29) và ghi zip qua `snapshot.write_entries`.
**Cập nhật M5** (mục 3, 5.2 bước 6, 5.7–5.9; A13–A17): tách `path_conflict_warnings(paths)` công khai (refactor giữ hành vi của `build_user_export`) và thêm `windows_path_issues` / `windows_path_warnings` (D39) để `pipeline` kiểm `PATH_CONFLICT` cho export start / `all` và `WINDOWS_PATH` cho mọi export (F9). `build_user_export`, `export_from_plan` **không đổi hành vi** (TC-01..24 giữ nguyên).

Ngoài phạm vi: đếm LOC, `loc_end`, kiểm tra chéo §8.3, thư mục kết quả `<out>/...`, khử trùng cảnh báo giữa các export (`pipeline` M5); chọn user / UI (M5, M6).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Export end (user được chọn) = source tại C_START + chỉ thay đổi (thêm và xóa) của các user chọn; nhiều user → một bản gộp; có tùy chọn xuất riêng (mặc định tắt) | §3.3, §16 |
| R2 | Export end (tất cả user) = toàn bộ C_END; "Tất cả" + "Loại trừ bot" có bot commit → dựng với mọi account không phải bot, tag `all` | §3.3, PLAN D21 |
| R3 | Không cherry-pick / rebase; dựng theo từng dòng | §7.1 |
| R4 | §7.3: dòng ngoài hunk giữ; dòng cũ chỉ mất nếu user chọn xóa; dòng mới chỉ thêm nếu user chọn viết; trong hunk dòng cũ trước dòng mới | §7.3, PLAN D24, D27 (Q32) |
| R5 | Quy tắc cấp file §7.4: không đổi → giữ; user chọn tạo → chỉ dòng của user; user khác tạo → không có (rỗng → không tạo file); nhiều người sửa → dòng start + thay đổi user chọn; user chọn xóa hết → không có; user khác xóa → giữ như start; đổi tên → tên theo người đổi tên | §7.4, PLAN D25, D30 |
| R6 | Bộ lọc §9 áp cho export, trên tên được chọn và nội dung đã dựng | §9, PLAN D25, snapshot R13 |
| R7 | Binary / quá lớn / đổi kiểu: theo cả file — người chạm cuối thuộc user chọn → bản C_END, ngược lại bản C_START | PLAN D27 (Q27), D31 |
| R8 | File mới 0 byte → bỏ; file không đổi → giữ; mode của C_START nếu đã có, ngược lại của C_END | PLAN D27 (Q31), D33 |
| R9 | Dòng thiếu EOL mà không phải dòng cuối → thêm EOL chiếm đa số + `MISSING_EOL` | §15, PLAN D27 (Q28) |
| R10 | Đường dẫn xung đột trong export → giữ cả hai + `PATH_CONFLICT` | PLAN D32 (Q38) |
| R11 | Tên zip `end_<YYYY-MM-DD>_<user-tag>.zip`; `user-tag` = `all`, tên một user, hoặc `multi-<n>users`; thêm `-<sha1(account)[:6]>` khi `safe_name` đổi chuỗi hoặc trùng; xuất riêng → thêm một zip mỗi user | §12, PLAN D11, D27 (Q29) |
| R12 | Giữ nguyên kiểu xuống dòng (CRLF, BOM) của dòng không đổi; tái lập (zip trùng byte với cùng input) | §15 |
| R13 | Ghi chú: export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được (README) | §7.5 |
| R14 | (M5) Export start / `all` (`plan_export`) cũng được kiểm đường dẫn xung đột khi giải nén (file/thư mục, chỉ khác hoa thường) → `PATH_CONFLICT`, cùng quy tắc và thông báo với export dựng bằng builder | F9, PLAN D32, A13 |
| R15 | (M5) Đường dẫn hợp lệ trong git nhưng không giải nén đúng trên Windows (tên thiết bị `CON`, `NUL.py`…; `.`/khoảng trắng cuối; ký tự `<>"\|?*`) → `WINDOWS_PATH`, chỉ cảnh báo, file vẫn được export và đếm | F9, §15, PLAN D39 (Q44) |

## 3. Giao diện
```python
def split_lines_keepends(data: bytes) -> list[bytes]:
    """Tách dòng theo git (D8): sau mỗi b"\\n", giữ nguyên byte (CRLF, BOM)."""

def build_user_file(base_lines: Sequence[bytes], final_lines: Sequence[bytes],
                    hunks: Sequence[Hunk], added_by: Mapping[int, str],
                    deleted_by: Mapping[int, str], users: AbstractSet[str]) -> list[bytes]:
    """§7.3 trên bytes với hunk của git (dòng ngoài hunk luôn giữ)."""

def fix_missing_eol(lines: Sequence[bytes]) -> tuple[list[bytes], list[int]]:
    """Thêm EOL đa số cho dòng thiếu EOL không phải dòng cuối; trả (dòng mới, chỉ số đã sửa)."""

@dataclass(frozen=True)
class BuiltFile:
    path: str                 # POSIX, tên trong export
    mode: str                 # "100644" | "100755"
    language: str | None      # Selection.language — None: không đếm LOC
    blob_sha: str | None = None
    data: bytes | None = None # đúng một trong blob_sha / data
    def zip_entry(self) -> ZipEntry: ...
    @property
    def cache_key(self) -> str:
        """blob_sha, hoặc content_sha1(data) (khóa cache phân loại §6.3 cho M5)."""

@dataclass(frozen=True)
class UserExport:
    accounts: tuple[str, ...] | None   # sắp tăng dần; None = bản nguyên (C_END / plan)
    tag: str
    files: tuple[BuiltFile, ...]       # sắp theo path
    warnings: tuple[LocWarning, ...]   # sắp ổn định theo (path, kind)

def build_user_export(repo: GitRepo, attribution: PeriodAttribution, start_plan: ExportPlan,
                      users: AbstractSet[str], filters: FilterConfig, tag: str) -> UserExport: ...

def export_from_plan(plan: ExportPlan, tag: str = "all") -> UserExport:
    """Bản nguyên của một snapshot (export end tất cả user = plan_export(C_END))."""

def find_path_conflicts(paths: Iterable[str]) -> list[tuple[str, str]]:
    """Các cặp (p, q), p < q, xung đột khi giải nén: q bắt đầu bằng p + "/" (file ↔ thư mục,
    so không phân biệt hoa thường) hoặc p.casefold() == q.casefold(). Sắp tăng dần."""

def path_conflict_warnings(paths: Iterable[str], label: str = "") -> list[LocWarning]:
    """(M5) PATH_CONFLICT cho cả hai đường dẫn của mỗi cặp find_path_conflicts (5.7)."""

def windows_path_issues(path: str) -> list[str]:
    """(M5) Lý do (tiếng Việt) khiến đường dẫn không giải nén đúng trên Windows; [] = hợp lệ (5.8)."""

def windows_path_warnings(paths: Iterable[str]) -> list[LocWarning]:
    """(M5) Một WINDOWS_PATH cho mỗi đường dẫn có lý do, sắp theo path (5.8)."""

def user_tag(accounts: Collection[str], *, all_users: bool = False,
             taken: Collection[str] = ()) -> str: ...

@dataclass(frozen=True)
class EndExportJob:
    tag: str
    accounts: tuple[str, ...] | None   # None = dùng thẳng C_END (export_from_plan)

def plan_end_exports(selected: Collection[str] | None, period_users: Sequence[UserSummary],
                     exclude_bots: bool = False, separate: bool = False) -> list[EndExportJob]:
    """Danh sách zip end cần ghi theo D21 / Q29; selected None = "Tất cả user"."""

def write_user_export(repo: GitRepo, export: UserExport, zip_path: Path,
                      c_end: CommitInfo, timezone: str) -> Path:
    """write_entries(..., zip_timestamp(c_end, timezone)) (snapshot 5.8, 5.9)."""
```
`UserSummary` từ `identity` (`account`, `is_bot`). Tên zip: `snapshot.end_zip_name(period, tag)`.

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `users` | set[str] | — | account key (§3.5); rỗng → bản = export start (không thay đổi nào) | §3.3 |
| `start_plan` | ExportPlan | — | `start_plan.commit_sha == attribution.c_start` (cả hai None khi C_START rỗng) | §3.2 |
| `exclude_bots` | bool | `False` | §16 "tùy chọn loại trừ" | §16, D14 |
| `separate` | bool | `False` | "Xuất riêng từng user" mặc định tắt | §16 |

## 5. Luồng xử lý

### 5.1 `split_lines_keepends`, `build_user_file`, `fix_missing_eol`
- `split_lines_keepends(data)`: `parts = data.split(b"\n")`; mọi phần trừ phần cuối + `b"\n"`; phần cuối khác rỗng → thêm (không EOL). `\r` đơn là ký tự trong dòng (D8).
- `build_user_file`: duyệt `hunks` theo thứ tự; con trỏ `pos` trên `base_lines`:
  1. trước hunk: thêm `base_lines[pos:h.old_start]` (dòng không đổi), `pos = h.old_start`;
  2. dòng cũ `i ∈ [old_start, old_start + old_count)`: giữ khi `deleted_by.get(i) not in users`;
  3. dòng mới `k ∈ [new_start, new_start + new_count)`: thêm `final_lines[k]` khi `added_by.get(k) in users`;
  4. `pos = old_start + old_count`. Sau hunk cuối: thêm `base_lines[pos:]`.
  Kiểu dữ liệu là `bytes` (không phải `str` như mã giả §7.3) để giữ CRLF / BOM — không đổi thuật toán.
- `fix_missing_eol(lines)`: `crlf` = số dòng kết thúc `b"\r\n"`, `lf` = số dòng kết thúc `b"\n"` không có `\r` trước. `eol = b"\r\n"` khi `crlf > lf`, ngược lại `b"\n"` (hòa hoặc không có dòng nào → `\n`). Mỗi dòng **không phải dòng cuối** không kết thúc bằng `b"\n"` → nối `eol`, ghi chỉ số. Dòng cuối giữ nguyên.

### 5.2 `build_user_export(repo, attribution, start_plan, users, filters, tag)`
1. `start_plan.commit_sha != attribution.c_start` → `ValueError`.
2. `changed_old = {fa.entry.old_path for fa in attribution.files if old_path}`. Mỗi `f ∈ start_plan.files` có `f.path ∉ changed_old` → `BuiltFile(f.path, f.mode, f.language, blob_sha=f.blob_sha)` (file không đổi). Cảnh báo của `start_plan.warnings` có `path ∉ changed_old` được giữ.
3. Đọc một lượt `repo.read_blobs` mọi phía (mode khác `120000`, `160000`) của mọi `fa` (kể cả `skip` — cần nội dung để phát cảnh báo lọc, N7; SHA bỏ trùng).
4. Với mỗi `fa` theo thứ tự `attribution.files`:
   - **Tên được chọn** (`name`): status `R` → `new_path` nếu `fa.renamed_by in users`, ngược lại `old_path` (`renamed_by` None → tên cũ, D25); status khác → `fa.path`.
   - **`skip`**: không tạo file; giữ `select_content(side.path, side.mode, data(side)).warnings` với `side` = phía mới (phía cũ nếu không có phía mới) — đường dẫn là của chính phía đó, như `plan_export` sẽ phát (N7). Phía là symlink / gitlink → không cảnh báo.
   - **`whole`** (Q27, D33/N1): `side = fa.new if fa.last_touch_by in users else fa.old`; `side` None hoặc mode symlink/gitlink → không tạo file. Ngược lại `sel = select_content(name, side.mode, data(side), filters)`; `sel.keep` → `BuiltFile(name, side.mode, sel.language, blob_sha=side.sha)`; gom `sel.warnings`.
   - **`lines`**:
     1. `base = split(data(old))` nếu có phía cũ, ngược lại `[]`; `final = split(data(new))` tương tự.
     2. `out = build_user_file(base, final, fa.hunks, fa.added_by, fa.deleted_by, users)`; `out, fixed = fix_missing_eol(out)`. Khi file **được tạo** (sau bước 6) và `fixed` khác rỗng → `MISSING_EOL` (path = `name`): `Thêm xuống dòng cho dòng <khoảng> thiếu EOL ở giữa file đã dựng` (khoảng 1-based theo nội dung đã dựng, gộp liền kề). File bị bỏ (bước 4, 6) → không cảnh báo `MISSING_EOL`.
     3. `content = b"".join(out)`.
     4. Tồn tại: chỉ phía mới (`A`) và `content == b""` → không tạo (file người khác tạo / file mới 0 byte, §7.4, Q31). Chỉ phía cũ (`D`): `old.size == 0` → giữ bản start (`blob_sha = old.sha`, N2 — không biết ai xóa, LOC 0); ngược lại `content == b""` → không tạo (user chọn xóa hết). Có cả hai phía (`M`, `R`) → luôn tạo, kể cả rỗng (N4).
     5. `mode = old.mode` nếu có phía cũ, ngược lại `new.mode` (Q31).
     6. `sel = select_content(name, mode, content, filters)`; gom `sel.warnings`; `not sel.keep` → không tạo.
     7. Nội dung: `content == data(new)` → `blob_sha = new.sha`; ngược lại `content == data(old)` → `blob_sha = old.sha`; ngược lại `data = content`.
5. Trùng `path` chính xác giữa các `BuiltFile` → `ValueError` (lỗi lập trình — không xảy ra với `diff-tree -M`, xem A6).
6. `path_conflict_warnings(paths, tag)` (5.7; M5 tách từ bước này, cùng hành vi): mỗi cặp `(p, q)` của `find_path_conflicts(paths)` → `PATH_CONFLICT` cho **cả** `p` và `q`: `Đường dẫn xung đột với <đường dẫn kia> khi giải nén (file/thư mục trùng tên hoặc chỉ khác hoa thường); cả hai được giữ trong zip`. Không bỏ file nào (D32). `build_user_export` **không** phát `WINDOWS_PATH` (A16).
7. `files` sắp theo path; `warnings` = cảnh báo start giữ lại + cảnh báo lọc + `MISSING_EOL` + `PATH_CONFLICT`, sắp ổn định theo `(path, kind)`. `accounts = tuple(sorted(users))`. Log INFO số file / cảnh báo.

### 5.3 `export_from_plan(plan, tag)`
`UserExport(None, tag, tuple(BuiltFile(f.path, f.mode, f.language, blob_sha=f.blob_sha) for f in plan.files), tuple(plan.warnings))`. Không kiểm xung đột (cây git không thể có file và thư mục cùng tên; trùng hoa thường thuộc F9/M5).

### 5.4 `user_tag(accounts, all_users, taken)`
1. `all_users` → `"all"`. Bỏ trùng account; `len >= 2` → `f"multi-{len}users"`; `len == 0` → `ValueError`.
2. Một account `a`: `s = safe_name(a)`. Thêm hậu tố `-<sha1(a.encode("utf-8")).hexdigest()[:6]>` khi: `s != a`; hoặc `s.casefold()` trùng `t.casefold()` của một `t ∈ taken`; hoặc `s.casefold() == "all"`; hoặc `s` khớp `multi-\d+users` (không phân biệt hoa thường).

### 5.5 `plan_end_exports(selected, period_users, exclude_bots, separate)`
`pool` = account của `period_users` (bỏ bot khi `exclude_bots`), sắp tăng dần. `taken` = các tag đã phát (để `user_tag` thêm hậu tố khi trùng).
1. `selected is None` ("Tất cả user"):
   - `exclude_bots` và có bot trong `period_users` → `EndExportJob("all", tuple(pool))` (D21; `pool` rỗng → bản = export start);
   - ngược lại → `EndExportJob("all", None)` (C_END nguyên bản — **không** dựng bằng builder, vì bản dựng khác C_END ở dòng chỉ đổi khoảng trắng, PLAN mục 5);
   - `separate` → thêm một job cho mỗi account `a` của `pool`: `EndExportJob(user_tag([a], taken=taken), (a,))`.
2. `selected` khác None (sắp tăng dần, bỏ trùng; rỗng → `ValueError`):
   - 1 account → một job `user_tag([a])` (Q29: xuất riêng không tạo thêm file);
   - ≥ 2 account → job `multi-<n>users` với cả nhóm; `separate` → thêm một job mỗi account.
3. Thứ tự: job gộp / `all` trước, rồi job riêng theo account tăng dần.

### 5.6 `write_user_export`
`snapshot.write_entries(repo, [f.zip_entry() for f in export.files], zip_path, snapshot.zip_timestamp(c_end, timezone))`. Timestamp = committer date C_END (cùng timestamp với zip end tất cả user).

### 5.7 `path_conflict_warnings(paths, label)` (M5, A13)
Tách nguyên văn từ 5.2 bước 6 (refactor giữ hành vi):
1. Với mỗi cặp `(p, q)` của `find_path_conflicts(paths)` theo thứ tự trả về: log WARNING `Đường dẫn xung đột trong export <label>: <p!r> ↔ <q!r>` (`label` rỗng → `Đường dẫn xung đột: <p!r> ↔ <q!r>`); thêm `LocWarning(PATH_CONFLICT, p, msg(q))` rồi `LocWarning(PATH_CONFLICT, q, msg(p))` với `msg(x) = "Đường dẫn xung đột với <x> khi giải nén (file/thư mục trùng tên hoặc chỉ khác hoa thường); cả hai được giữ trong zip"`.
2. Trả list theo đúng thứ tự trên (không sắp lại; người gọi sắp ổn định `(path, kind)` như 5.2 bước 7). Không có cặp → `[]`. `paths` có thể là iterator bất kỳ, phần tử trùng được bỏ (như `find_path_conflicts`).
`build_user_export` gọi `path_conflict_warnings(seen, tag)` → kết quả và log trùng hệt bản M4.

### 5.8 `windows_path_issues(path)`, `windows_path_warnings(paths)` (M5, D39, A14–A16)
`windows_path_issues(path)`: tách `path.split("/")`; bỏ qua phần `""`, `"."`, `".."` (thuộc `UNSAFE_PATH`, không bao giờ có trong export). Với từng phần `part` từ trái sang phải, kiểm theo thứ tự và thêm lý do tương ứng:
1. **Tên thiết bị**: `stem = part.split(".", 1)[0].rstrip(" ")`; `stem.casefold()` thuộc `{con, prn, aux, nul, com0…com9, com¹, com², com³, lpt0…lpt9, lpt¹, lpt², lpt³}` → `"<part>" trùng tên thiết bị dành riêng của Windows (<STEM>)` với `<STEM> = stem.upper()`. Ví dụ `CON`, `nul.py`, `Aux.tar.gz`, `src/com1/x.py`; không phải: `CONSOLE.py`, `COM10.py`, `nul_.py`, `null/x.py`.
2. **Ký tự cấm**: phần chứa ký tự thuộc `<>"|?*` hoặc mã `< 0x20` → `"<part>" chứa ký tự không hợp lệ trên Windows (<>"|?* hoặc ký tự điều khiển)`. (`:` và `\` đã là `UNSAFE_PATH` — file bị bỏ khỏi export, không kiểm lại.)
3. **Cuối tên**: `part.endswith((".", " "))` → `"<part>" kết thúc bằng dấu chấm hoặc khoảng trắng (Windows tự bỏ khi giải nén)`.
Trả list lý do (có thể rỗng). Hàm thuần, không log.

`windows_path_warnings(paths)`: với mỗi `path` trong `sorted(set(paths))` có `issues = windows_path_issues(path)` khác rỗng → `LocWarning(WINDOWS_PATH, path, "Đường dẫn có thể không giải nén đúng trên Windows: " + "; ".join(issues) + "; file vẫn được giữ trong zip và được đếm LOC")`, log WARNING `Đường dẫn không hợp lệ trên Windows: <path!r>`. Trả list sắp theo path (mỗi path tối đa một cảnh báo). Không bỏ file nào.

### 5.9 Cách `pipeline` dùng (M5, tham khảo cho spec `pipeline`)
- Export start (`plan_export(C_START)`) và export end `all` dùng thẳng C_END (`export_from_plan`): cảnh báo = cảnh báo của plan + `path_conflict_warnings(paths)` + `windows_path_warnings(paths)` với `paths` = đường dẫn các file của export đó.
- Export dựng bằng builder (`build_user_export`, kể cả `all` loại bot và zip riêng): đã có `PATH_CONFLICT` từ 5.2 bước 6 → chỉ thêm `windows_path_warnings(paths)`.
- `pipeline` gộp, khử trùng và sắp ổn định cảnh báo giữa các export (D31, D40-N8). `export_from_plan` giữ nguyên (không tự kiểm, 5.3).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Repo §14: chỉ alice → `app.py` = start + 7 dòng alice − 2 dòng alice xóa (dòng bob xóa vẫn còn), không có `util.py`; chỉ bob → `app.py` không có thay đổi của alice, có `util.py`; alice + bob → `app.py` trùng byte C_END (dùng blob).
- C_START rỗng: `start_plan` rỗng, mọi file là `A`; mỗi user chỉ có dòng của mình (admin trong kỳ cũng là một user).
- Không có commit trong kỳ: `attribution.files` rỗng → export = export start (mọi entry dùng blob).
- Dòng chỉ đổi khoảng trắng / EOL giữ bản C_START (D22) ở mọi bản dựng; dòng cũ đứng trước dòng mới trong hunk → bản "mọi user" có thể khác C_END về thụt lề / thứ tự (không mất, không nhân đôi). Vì vậy "Tất cả" không loại bot dùng thẳng C_END.
- Tên được chọn bị bộ lọc loại (vd. rename `src/a.py` → `vendor/a.py` do user chọn) → file không có trong export dù user có dòng (N9, hệ quả D25; §8.3 có thể lệch).
- Rename giữa hai file rỗng do git ghép (N3): giữ theo quy tắc rename, LOC 0.
- BOM ở dòng 0 của phía mới có thể rơi vào giữa file khi dòng 0 cũ được giữ (N6): để nguyên, có thể lệch LOC nhỏ (§8.3).
- Bot là account bình thường; lọc bot chỉ qua `plan_end_exports(exclude_bots=True)`.
- Bản export end theo user có thể không build / chạy được (§7.5) — ghi trong README.

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo (tiếng Việt) | Log |
|---|---|---|---|
| `start_plan` không khớp C_START | `ValueError` (lỗi lập trình) | — | — |
| Trùng path chính xác | `ValueError` (lỗi lập trình) | — | — |
| `user_tag([])`, `selected` rỗng | `ValueError` | — | — |
| Dòng thiếu EOL ở giữa | `MISSING_EOL` | `Thêm xuống dòng cho dòng <khoảng> thiếu EOL ở giữa file đã dựng` | — |
| Đường dẫn xung đột | `PATH_CONFLICT` cho cả hai path | `Đường dẫn xung đột với <q> khi giải nén (file/thư mục trùng tên hoặc chỉ khác hoa thường); cả hai được giữ trong zip` | WARNING |
| Đường dẫn không hợp lệ trên Windows (M5) | `windows_path_warnings` → `WINDOWS_PATH` (file vẫn giữ) | `Đường dẫn có thể không giải nén đúng trên Windows: <lý do>; …; file vẫn được giữ trong zip và được đếm LOC` (lý do: mục 5.8) | WARNING |
| File bị bộ lọc loại | cảnh báo của `select_content` (như `snapshot`) | (như `snapshot` mục 7) | — |
| Lỗi git / ghi zip | `GitError` / `SnapshotError` lan ra | (từ module tương ứng) | — |

## 8. Bảo mật, hiệu năng, tái lập
- Không nhận token; mọi git qua `GitRepo`; zip qua `write_entries` (đường dẫn đã qua `is_unsafe_path` trong `select_content`).
- Hiệu năng: một lượt `read_blobs` cho mỗi lần dựng; nhiều export (xuất riêng) đọc lại blob mỗi lần — gom để M7.
- Tái lập: `files` sắp theo path; dùng blob khi nội dung trùng blob; `write_entries` sắp entry và cố định timestamp → cùng input cho zip trùng SHA-256.

## 9. Test cases
Fixture: `section14_repo`, `make_repo`, các hàm dựng repo trong `tests/test_attribution.py` (dùng lại được). Chuỗi chuẩn: `plan_export(C_START)`, `log_commits`, `attribute_period`, rồi `build_user_export`. LOC trên nội dung export = tổng `sum(LineClassifier().classify(decode_text(data), path, cache_key))` cho file có `language`.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-builder-01 | split_lines_keepends | `b""`, `b"a"`, `b"a\r\nb"`, `b"\n\n"`, `b"a\rb\n"` | `[]`, `[b"a"]`, `[b"a\r\n", b"b"]`, `[b"\n", b"\n"]`, `[b"a\rb\n"]` | unit |
| TC-builder-02 | §7.3 thuần | base 5 dòng, hunk `(1,1,1,1)` (cũ bob xóa, mới bob viết), hunk `(3,0,3,1)` (mới alice); users `{alice}` / `{bob}` / `{}` | dòng ngoài hunk giữ; `{alice}`: dòng 1 cũ giữ + dòng alice; `{bob}`: dòng bob thay dòng 1; `{}` = base; thiếu khóa → cũ giữ, mới bỏ; cũ đứng trước mới | unit |
| TC-builder-03 | §14 theo user (bắt buộc D) | `section14_repo()`, kỳ 2026-01 | LOC start 10; alice 13 (không có `util.py`), bob 17, alice+bob 20 và `app.py` dùng blob C_END; `export_from_plan(plan_export(C_END))` 20 | integration |
| TC-builder-04 | start trước commit đầu (bắt buộc D) | §14, kỳ 2025-12-01..2026-01-31 | `start_plan.files == []`, loc_start 0; alice 5, bob 8, alice+bob 13, admin+alice+bob 20 | integration |
| TC-builder-05 | §7.4 file mới | bob tạo `util.py`; alice tạo `e.py` 0 byte | alice: không có `util.py`, không có `e.py`; bob: có `util.py` (blob), không có `e.py` | integration |
| TC-builder-06 | §7.4 xóa | alice `git rm d1.py`, bob `git rm d2.py`; `zero.py` 0 byte bị xóa | alice: không có `d1.py`, `d2.py` = blob start; bob: ngược lại; `zero.py` giữ (N2) ở cả hai | integration |
| TC-builder-07 | §7.4 rename (bắt buộc D) | bob `git mv old.py new.py`, alice thêm dòng; `renamed_by` None (monkeypatch) | alice: `old.py` có dòng alice, không có `new.py`; bob: `new.py` không có dòng alice; alice+bob: `new.py` trùng byte C_END; None → tên cũ | integration |
| TC-builder-08 | Rename + bộ lọc (N9) | bob đổi `src/a.py` → `vendor/a.py`, alice sửa | bob: không có file nào; alice: `src/a.py` có dòng alice | integration |
| TC-builder-09 | whole (Q27, N1) | `FilterConfig(export_mode="full", exclude_binary=False)`: alice tạo `new.png`, bob sửa `logo.png`, alice xóa `old.png`; `T`: alice đổi `link` (symlink) thành file | alice: có `new.png` (blob C_END), `logo.png` = bản start, không có `old.png`, `link` là file bản C_END với mode C_END; bob: `logo.png` bản C_END, `old.png` bản start, không có `new.png`, không có `link` (symlink bị bỏ) | integration |
| TC-builder-10 | MISSING_EOL (Q28) | base `a = 1\nc = 3` (thiếu EOL); bob thêm EOL; alice thêm `d = 4`; biến thể CRLF + BOM; biến thể hòa 1 CRLF / 1 LF; biến thể alice đổi tên sang `vendor/x.py` (bị bộ lọc loại) | alice: `a = 1\nc = 3\nd = 4\n` + 1 `MISSING_EOL` path `x.py`; CRLF: `\r\n` được thêm, BOM ở byte 0; hòa: `\n`; bob: trùng bản start ; đổi tên vào `vendor/` → file không có, **không** `MISSING_EOL` | unit + integration |
| TC-builder-11 | Giữ byte (bắt buộc D) | file CRLF + BOM, alice sửa dòng giữa, bob sửa dòng cuối (để bản alice là nội dung tự dựng, không trùng blob) | export alice: mọi dòng không đổi trùng byte start, BOM ở byte 0, dòng alice giữ CRLF của C_END | integration |
| TC-builder-12 | Tái lập zip (bắt buộc D) | ghi export alice §14 hai lần (đầu vào `files` đảo thứ tự lần 2) | SHA-256 bằng nhau; `date_time` = committer date C_END theo `Asia/Bangkok` | integration |
| TC-builder-13 | Xung đột file/thư mục (D32) | `export_mode: full` (file `x` không đuôi): (a) alice `git rm x`, bob tạo `x/z.py`; (b) alice `mv x.py y.py`, bob tạo `x.py/z.py`; (c) `find_path_conflicts(["A.py", "a.py", "b", "b/c", "bc"])` | (a), (b) export bob có cả hai path + `PATH_CONFLICT` cho từng path; (c) `[("A.py","a.py"), ("b","b/c")]` | unit + integration |
| TC-builder-14 | Trùng path phòng thủ | `PeriodAttribution` giả: 2 entry `A` cùng `new_path` | `ValueError`, không gọi `write_entries` | unit |
| TC-builder-15 | user_tag | `{alice}`; `{alice@example.com}`; `{a, b}`; `alice` khi `taken=["Alice"]`; account `all`; account `multi-2users`; `[]` | `alice`; `alice_example.com-<6 hex>`; `multi-2users`; `alice-<6 hex>`; `all-<6 hex>`; `multi-2users-<6 hex>`; ValueError | unit |
| TC-builder-16 | plan_end_exports | Tất cả (không bot); Tất cả + loại bot có bot; Tất cả + loại bot không bot; Tất cả + xuất riêng; chọn 1 + xuất riêng; chọn 2 + xuất riêng; chọn rỗng | `[all/None]`; `[all/(non-bot…)]`; `[all/None]`; `[all/None, alice, bob]`; `[alice]`; `[multi-2users, alice, bob]`; ValueError | unit |
| TC-builder-17 | Loại trừ bot (D21) | `section14_repo(bot=True)`, `full` | job "all" + loại bot dựng bằng builder: không có `deps.txt`; không loại bot: `export_from_plan(C_END)` có `deps.txt`; LOC source cả hai = 20 | integration |
| TC-builder-18 | Kiểm tra đầu vào | `start_plan` của commit khác C_START; `users = set()` | ValueError; `users` rỗng → export = export start (mọi file blob start) | integration |
| TC-builder-19 | BOM giữa file (N6) | `b.py` dòng 0 = BOM + `# v0`; alice đổi dòng 0 thành BOM + `# v1`, sau đó bob đổi thành BOM + `# v2`; export `{bob}` | `deleted_by[0] == alice`, `added_by[0] == bob` → nội dung bắt đầu bằng BOM + `# v0` rồi BOM + `# v2` (BOM ở dòng 2, đúng §7.3); không exception | integration |
| TC-builder-20 | Không có commit trong kỳ | C_START == C_END | export = `start_plan` (mọi entry blob), không cảnh báo mới | integration |
| TC-builder-21 | write_user_export | export alice §14 | zip có đúng `files` (theo path), nội dung trùng byte; `external_attr` theo mode | integration |
| TC-builder-22 | Cảnh báo lọc và giữ cảnh báo start | `logo.png` binary không đổi + `big.py` (`max_file_size_kb=1`) do alice sửa; `source_only` | export alice giữ cảnh báo BINARY `logo.png` từ `start_plan`; `big.py` `skip` → cảnh báo TOO_LARGE như `plan_export(C_END)` | integration |
| TC-builder-23 | `skip` có phía symlink / gitlink | symlink `link.py` bị bob sửa đích; submodule `sub` đổi commit | không có file, không cảnh báo, không đọc blob của các phía đó (spy `read_blobs`) | integration |
| TC-builder-24 | Định dạng khoảng trong thông báo | `_ranges_text([4, 1, 2, 7, 2])`; `fix_missing_eol` sửa 2 dòng liền nhau (`[b"a", b"b", b"c
"]`) | `"2–3, 5, 8"`; chỉ số `[0, 1]`, thông báo builder `dòng 1–2` | unit |
| TC-builder-25 | (M5) `path_conflict_warnings` | `iter(["b/c", "A.py", "a.py", "b", "bc", "a.py"])`, `label="start"`; `[]`; `["a.py", "b.py"]` | đúng 4 cảnh báo theo thứ tự `A.py`(với `a.py`), `a.py`(với `A.py`), `b`(với `b/c`), `b/c`(với `b`), kind `PATH_CONFLICT`, thông báo đúng nguyên văn 5.7; log WARNING chứa `start`; `[]`, `[]` | unit |
| TC-builder-26 | (M5) Refactor giữ hành vi | ca TC-13 (a); spy `builder.path_conflict_warnings` | `build_user_export` gọi đúng 1 lần với tập path của export và `label == tag`; cảnh báo `PATH_CONFLICT` của export = `path_conflict_warnings([f.path for f in exp.files])` (cùng thứ tự sau sắp `(path, kind)`); TC-01..24 không đổi | integration |
| TC-builder-27 | (M5) `windows_path_issues` — tên thiết bị | `CON`, `con.py`, `NUL.tar.gz`, `Aux .py`, `src/com1/x.py`, `LPT9`, `COM0.c`, `com¹.py`, `LPT³`; không phải: `CONSOLE.py`, `COM10.py`, `nul_.py`, `connect.py`, `src/null/x.py`, `xcon.py` | nhóm đầu đúng 1 lý do `"<part>" trùng tên thiết bị dành riêng của Windows (<STEM>)` (vd. `"Aux .py" … (AUX)`, `"com1" … (COM1)`, `"com¹.py" … (COM¹)`); nhóm sau `[]` | unit |
| TC-builder-28 | (M5) `windows_path_issues` — ký tự, cuối tên, nhiều lý do | `a<b.py`, `a>b`, `a"b`, `a\|b`, `a?b`, `a*b`, `a\x01b.py`, `a\x1fb`; `a.py.`, `a.py `, `dir./x.py`, `dir /x.py`; hợp lệ: `src/ok.py`, `.gitignore`, `a.b/c.py`, `ü.py`, `a b.py`, `a..b.py`, `a/../b//./c.py` (phần `""`/`.`/`..` bỏ qua); `CON./a?.py ` | ký tự → lý do ký tự; cuối tên → lý do cuối tên (đúng phần); hợp lệ → `[]`; `CON./a?.py ` → đúng 4 lý do theo thứ tự (theo phần rồi theo quy tắc): tên thiết bị `CON.`, cuối tên `CON.`, ký tự `a?.py `, cuối tên `a?.py ` | unit |
| TC-builder-29 | (M5) `windows_path_warnings` | `["b/NUL.py", "ok.py", "a.py.", "b/NUL.py"]`; `[]` | 2 cảnh báo sắp theo path `a.py.`, `b/NUL.py`; kind `WINDOWS_PATH`; thông báo đúng nguyên văn 5.8; log WARNING; `[]` | unit |
| TC-builder-30 | (M5) Tích hợp start / `all` (A13, D39) | repo (`update-index --cacheinfo`, không cần file trên đĩa): C_START có `A.py`, `a.py`, `NUL.py`, `src/a.py.`, `ok.py`; alice sửa `NUL.py` trong kỳ; `export_mode: full` | `plan_export(C_START/C_END)` giữ cả 5 file, không `UNSAFE_PATH`; `export_from_plan` không có `PATH_CONFLICT`/`WINDOWS_PATH` (không đổi); `path_conflict_warnings(paths start)` → `A.py`, `a.py`; `windows_path_warnings(paths)` → `NUL.py`, `src/a.py.`; `build_user_export({alice})` có `PATH_CONFLICT` cho `A.py`/`a.py`, **không** có `WINDOWS_PATH`; `write_user_export` ghi được zip chứa `NUL.py` (nội dung C_END) và `src/a.py.` | integration |
| TC-builder-31 | `BuiltFile` phòng thủ | `BuiltFile("x.py", "100644", None)`; `BuiltFile("x.py", "100644", None, blob_sha="a" * 40, data=b"x")` | cả hai `ValueError` | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | (N1) `whole`: mode lấy từ phía cung cấp nội dung (file ↔ symlink do user chọn đổi → mode C_END); `lines` theo Q31 | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A2 | (N2) File `D` 0 byte: không biết ai xóa → giữ bản start (LOC 0) | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A3 | (N3) Git ghép rename giữa hai file rỗng: theo quy tắc rename, LOC 0 | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A4 | (N4) `M` / `R` dựng ra rỗng → vẫn tạo file 0 byte (file tồn tại ở cả hai mốc) | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A5 | (N5) EOL đa số đếm trên nội dung đã dựng; hòa hoặc không có dòng nào → `\n` | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A6 | Trùng path chính xác không xảy ra với `diff-tree -M` (không `-B`/`-C`) → chỉ kiểm phòng thủ (`ValueError`) | Giả định | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A7 | (N6) BOM rơi vào giữa file: để nguyên, ghi rủi ro (§8.3 cho lệch nhỏ) | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A8 | (N7) Builder giữ cảnh báo `start_plan` của file không đổi và phát cảnh báo `select_content` của file đổi (kể cả `skip`) — `UserExport` tự đủ như `ExportPlan`; M5 khử trùng | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A9 | (N8) `user_tag` xét trùng không phân biệt hoa thường; tag cá nhân trùng `all` / `multi-\d+users` → thêm hậu tố; account là email luôn có hậu tố | D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A10 | (N10) "Tất cả" không loại bot (hoặc không có bot) dùng thẳng C_END; chỉ khi loại bot có bot mới dựng bằng builder | D21, D33 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A11 | Chữ ký `build_user_export` thêm `repo`, `filters`, `tag` so với PLAN (cần đọc blob, gọi `select_content`) | Làm rõ | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A12 | File bị người này sửa rồi người khác xóa hết: dựng theo dòng (§7.3) như Q26 — export người sửa = start − dòng họ xóa (không có dòng mới của họ vì phía mới không tồn tại), export người xóa vẫn còn file với các dòng người khác đã xóa; khớp số liệu §8.2 / §8.3 thay cho nghĩa đen §7.4 | D34 | Đã chốt theo khuyến nghị 2026-10-23 (*) |
| A13 | `PATH_CONFLICT` chỉ kiểm ở export dựng bằng builder; export start / `all` (`plan_export`) có hai file chỉ khác hoa thường chưa được cảnh báo → xử lý cùng F9 ở M5. **M5:** `builder` cung cấp `path_conflict_warnings(paths)` công khai (5.7), `pipeline` gọi cho export start / `all` (5.9); `plan_export`, `export_from_plan` không đổi | Giả định → M5 | Đã chốt theo khuyến nghị 2026-10-23 (*); cập nhật M5 chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (**) |
| A14 | (M5) **Ai phát hiện tên không hợp lệ trên Windows (D39)**: `builder` cung cấp hàm thuần `windows_path_issues` / `windows_path_warnings` (cạnh `find_path_conflicts` — cùng nhóm "kiểm đường dẫn khi giải nén", test đơn vị được, không phụ thuộc git); `pipeline` chỉ gọi và gộp. Phương án khác (để `pipeline` tự viết quy tắc) bị loại: trộn quy tắc tên file vào phần điều phối, khó test riêng | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (**) |
| A15 | (M5) Quy tắc `WINDOWS_PATH`: tên thiết bị theo danh sách của Microsoft ("Naming Files, Paths, and Namespaces": `CON PRN AUX NUL COM0–9 COM¹²³ LPT0–9 LPT¹²³`, so không phân biệt hoa thường, trên phần trước dấu `.` đầu tiên sau khi bỏ khoảng trắng cuối — `NUL.tar.gz`, `AUX .py`); ký tự `<>"\|?*` **và ký tự điều khiển < 0x20** (mở rộng so với Q44 — cũng không tạo được trên NTFS); `.`/khoảng trắng cuối mỗi phần (cả thư mục). Không kiểm: độ dài > 260 ký tự (phụ thuộc thư mục giải nén), `:`/`\` (đã `UNSAFE_PATH`), trùng sau khi Windows bỏ `.` cuối (`a.py.` ≡ `a.py` — chỉ thấy qua lý do "cuối tên", không thêm `PATH_CONFLICT`, để giữ hành vi `find_path_conflicts`) . **Sửa theo review 2026-10-24:** trên Windows 11 (build 26300) phần lớn tên thiết bị **có đuôi** (`NUL.py`, `con.py`) tạo / giải nén được, chỉ tên trần (`CON` → `_CON`) và `.`/khoảng trắng cuối hỏng; vẫn giữ quy tắc (Windows cũ, công cụ giải nén khác) nhưng thông báo nói "**có thể** không giải nén đúng". `a.py.` và `a.py` cùng có trong export → giải nén trên Windows một file đè file kia, chỉ `a.py.` có cảnh báo (LOC không ảnh hưởng, D36) — ghi README | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (**) |
| A16 | (M5) `build_user_export` **không** tự phát `WINDOWS_PATH` (giữ hành vi M4, TC-01..24 không đổi); `pipeline` gọi `windows_path_warnings` thống nhất cho **mọi** export (start, `all`, gộp, riêng) — một điểm áp dụng duy nhất, không phát trùng | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (**) |
| A17 | (M5) Mỗi đường dẫn tối đa một cảnh báo `WINDOWS_PATH`, gom mọi lý do (theo phần từ trái sang phải, trong một phần theo thứ tự tên thiết bị → ký tự → cuối tên); `path_conflict_warnings` trả theo thứ tự cặp như M4 (không sắp lại) để kết quả `build_user_export` trùng hệt | Khuyến nghị | Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (**) |

(*) Người dùng ủy quyền chọn phương án khuyến nghị, không chờ xác nhận (2026-10-23).
(**) Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 (không chờ xác nhận).

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-23 | Tạo mới theo phân tích `spec-analyst` (prototype trên git 2.55: §14 đúng 4 trường hợp, zip tái lập) và quyết định D32, D33 | M4 |
| 2026-10-23 | Chốt theo khuyến nghị (người dùng ủy quyền không chờ xác nhận, 2026-10-23) → `approved` | Duyệt (ủy quyền) |
| 2026-10-23 | Làm rõ khi lập trình: bước 5.2.3 đọc cả blob của file `skip` (cần cho cảnh báo lọc N7) — không đổi hành vi | /feature-implement |
| 2026-10-23 | Làm rõ khi viết test (không đổi hành vi): bộ lọc TC-13, fixture TC-11, đường dẫn cảnh báo của file `skip`, `accounts` của job xuất riêng | /feature-implement (test-engineer) |
| 2026-10-23 | Test pass (TC-01..22, 56 test; toàn bộ 492) → `implemented` | /feature-test |
| 2026-10-23 | Sửa theo review (reviews/builder-20261023.md, PASS_WITH_NOTES): `MISSING_EOL` chỉ phát khi file có trong export (Minor 1); `user_tag` bỏ trùng (Nit); A12 (sửa rồi bị xóa, D34), A13 (`PATH_CONFLICT` vs `plan_export`, F9); TC-10 thêm ca bị lọc, TC-23, 24 (Minor 3). Chốt theo khuyến nghị (ủy quyền) | Review builder |
| 2026-10-23 | Test pass (TC-01..24, 59 test; toàn bộ 495); review PASS_WITH_NOTES (reviews/builder-20261023.md), Minor đã sửa → `reviewed` | /feature-review |
| 2026-10-24 | Cập nhật M5 (PLAN F9, A13, D39): R14, R15; API `path_conflict_warnings` (tách từ 5.2 bước 6, giữ hành vi), `windows_path_issues`, `windows_path_warnings` (5.7, 5.8); cách `pipeline` dùng (5.9); mục 7 thêm `WINDOWS_PATH`; TC-25..30; A13 cập nhật, A14–A17. Phần M4 đã duyệt giữ nguyên. Chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24 → `approved` | M5 (`/feature-spec builder`) |
| 2026-10-24 | Làm rõ khi viết test (không đổi hành vi): fixture TC-30 đặt `core.protectNTFS=false` cho repo nguồn (git for Windows từ chối `NUL.py`, `a.py.` trong index); TC-28 thêm ca `a/../b//./c.py` (phần `""`/`.`/`..` bỏ qua) | /feature-implement |
| 2026-10-24 | Test pass (TC-01..30, 100 test builder; toàn bộ 586) → `implemented` | /feature-test |
| 2026-10-24 | Sửa theo review (reviews/builder-20261024.md, PASS_WITH_NOTES): thông báo `WINDOWS_PATH` thành "có thể không giải nén đúng" (Minor 1, phương án (a) — chốt theo khuyến nghị, người dùng ủy quyền 2026-10-24); log `path_conflict_warnings` khi `label` rỗng (Nit); TC-31 `BuiltFile` phòng thủ (Nit); A15 ghi kết quả thử Windows 11 và rủi ro `a.py.`/`a.py` (README) | Review builder |
| 2026-10-24 | Test pass (TC-01..31, 101 test builder; toàn bộ 587), coverage `builder.py` 100 %; review PASS_WITH_NOTES (reviews/builder-20261024.md), Minor 1 + 2 Nit đã sửa → `reviewed` | /feature-review |
