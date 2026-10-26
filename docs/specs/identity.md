---
id: identity
title: Gộp tác giả thành account, danh sách user trong kỳ
type: module
milestone: M3
modules: [src/loc_counter/identity.py]
tests: [tests/test_identity.py]
spec_refs: ["3.1", "3.5", "8.2", "10.2", "15", "16"]
depends_on: [config, git_repo, snapshot]
status: reviewed
---

# Gộp tác giả thành account, danh sách user trong kỳ

## 1. Mục đích & phạm vi
Quy một tác giả commit (tên, email) về **account key** theo thứ tự ưu tiên §3.5; nhận diện bot; đọc/ghi `identities.yaml`; tra GitHub API (có cache) khi được phép; liệt kê user có commit trong kỳ kèm số commit. Dùng cho lệnh `users` (M3), màn hình chọn user / gộp account (M6), gán tác giả (M4) và số liệu theo user (M5).
Ngoài phạm vi: lấy commit từ git (`git_repo.log_commits`), tìm C_START/C_END (`snapshot`), giao diện sửa bảng (M6).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Gộp nhiều cặp (tên, email) về một account key | §3.5 |
| R2 | Ưu tiên: 1 `identities.yaml` → 2 `.mailmap` → 3 GitHub API (`GET /repos/{owner}/{repo}/commits/{sha}` → `author.login`, chỉ khi repo trên GitHub và có token, cache email → login) → 4 email chữ thường | §3.5 |
| R3 | `12345+login@users.noreply.github.com` → `login` | §3.5 |
| R4 | Bot: tên chứa `[bot]`, `dependabot`, `renovate`, `github-actions`; hiện trong danh sách, có nhãn; tùy chọn loại trừ | §3.5, §16, PLAN D14 |
| R5 | Tác giả = author, không phải committer | §3.5 |
| R6 | Danh sách user: account có commit trong kỳ, sắp xếp số commit giảm dần, hiển thị số commit | §10.2[3] |
| R7 | Số commit không tính merge commit | §8.2, PLAN D15 |
| R8 | `identities.yaml` người dùng sửa được (UI M6) | §10.2 |
| R9 | `.mailmap` tại C_END; identity được `.mailmap` đổi → key từ email chuẩn | PLAN D17 |
| R10 | Key tự sinh chữ thường; key thủ công giữ nguyên; bot theo tên/email/key không phân biệt hoa thường | PLAN D19 |
| R11 | GitHub API: lỗi → dùng email + cảnh báo; hết quota → ngừng gọi; cache `~/.loc_counter/github_logins.json` không chứa token | PLAN D18 |
| R12 | Token không xuất hiện trong log, cache, cảnh báo, exception | §15 |

## 3. Giao diện
```python
BOT_MARKERS: tuple[str, ...] = ("[bot]", "dependabot", "renovate", "github-actions")
DEFAULT_LOGIN_CACHE: Path   # Path.home() / ".loc_counter" / "github_logins.json"
GITHUB_API = "https://api.github.com"

class IdentityError(LocCounterError):
    """Lỗi đọc/ghi identities.yaml; thông báo tiếng Việt."""

@dataclass(frozen=True)
class IdentityRule:
    account: str
    email: str | None = None     # khớp không phân biệt hoa thường
    name: str | None = None      # khớp không phân biệt hoa thường

@dataclass(frozen=True)
class IdentityMap:
    rules: tuple[IdentityRule, ...] = ()
    def lookup(self, name: str, email: str) -> str | None:
        """Account theo email trước, rồi theo tên; None nếu không có."""
    def lookup_email(self, email: str) -> str | None: ...
    def lookup_name(self, name: str) -> str | None: ...

def load_identities(path: Path | None) -> IdentityMap: ...
def save_identities(path: Path, identity_map: IdentityMap) -> None: ...

def key_from_email(email: str, name: str = "") -> str:
    """noreply GitHub → login; còn lại email chữ thường; email rỗng → tên chữ thường."""

def is_bot_text(text: str) -> bool: ...

def github_repo_of(source: str) -> tuple[str, str] | None:
    """(owner, repo) nếu source là https://github.com/<owner>/<repo>[.git]."""

class GitHubLoginResolver:
    def __init__(self, owner: str, repo: str, token: str,
                 cache_path: Path | None = None, session: _Session | None = None,
                 timeout: float = 10.0) -> None: ...
    def login_for(self, email: str, sha: str) -> str | None: ...
    @property
    def warnings(self) -> list[str]: ...
    @property
    def requests_made(self) -> int: ...

@dataclass(frozen=True)
class Identity:
    name: str
    email: str

class AccountResolver:
    def __init__(self, identities: IdentityMap | None = None,
                 github: _LoginLookup | None = None) -> None: ...   # _LoginLookup: Protocol (login_for, warnings)
    def resolve(self, commit: LogCommit) -> str: ...

@dataclass
class UserSummary:
    account: str
    commits: int                     # không tính merge
    merge_commits: int
    identities: list[Identity]       # (tên, email) gốc, sắp xếp, không trùng
    is_bot: bool

@dataclass
class UsersResult:
    users: list[UserSummary]         # commits giảm dần, rồi account tăng dần
    warnings: list[str]              # tiếng Việt (GitHub API, ...)

def summarize_users(commits: Sequence[LogCommit], resolver: AccountResolver) -> UsersResult: ...

def list_period_users(repo: _RepoLike, snapshots: _SnapshotsLike, identities: IdentityMap | None = None,
                      token: str | None = None, login_cache: Path | None = None) -> UsersResult:
    """log_commits(C_END, C_START, mailmap_rev=C_END) → summarize; bật GitHub API khi được phép."""

```

## 4. Dữ liệu vào / ra & giá trị mặc định
`identities.yaml` (UTF-8, có thể có BOM):
```yaml
identities:
  - email: alice@corp.com
    account: alice
  - email: 12345+alice@users.noreply.github.com
    account: alice
  - name: "Alice N"          # dùng khi commit không khớp email nào
    account: alice
```
| Tên | Kiểu | Mặc định | Ràng buộc | Nguồn |
|---|---|---|---|---|
| `identities.yaml` | file | không có → không có quy tắc | mapping có key `identities` là list; mỗi mục có `account` (chuỗi không rỗng) và ít nhất một trong `email`, `name` | D16 |
| cache login | JSON | `~/.loc_counter/github_logins.json` | `{"version": 1, "logins": {email: login \| null}}` | D18 |
| timeout GitHub | float | 10 s | | D18 |

## 5. Luồng xử lý

### 5.1 `load_identities(path)`
1. `path is None` → `IdentityMap()`.
2. Không tồn tại → IdentityError "Không tìm thấy file identities". Đọc `utf-8-sig`; lỗi giải mã / đọc → IdentityError; `yaml.safe_load` lỗi → IdentityError (kèm dòng nếu có). File rỗng → `IdentityMap()`.
3. Gốc không phải mapping, hoặc `identities` không phải list (giá trị rỗng `identities:` = danh sách rỗng) → IdentityError. Key gốc khác `identities` → IdentityError liệt kê key lạ (sắp xếp).
4. Mỗi mục (đánh số từ 1): phải là mapping chỉ gồm `account`, `email`, `name`; `account` là chuỗi, `strip()` không rỗng; `email`/`name` nếu có là chuỗi không rỗng sau `strip()`; thiếu cả hai → IdentityError `Mục <n>: cần email hoặc name`.
5. Cùng email (chữ thường) gán cho hai account khác nhau → IdentityError `Email <e> được gán cho nhiều account: <a>, <b>`; tương tự với name. Trùng hoàn toàn → bỏ bản sau.
6. `IdentityMap(rules)` giữ thứ tự file. `lookup`: dict email chữ thường → account; nếu không, dict name chữ thường (`strip`) → account.

### 5.2 `save_identities(path, map)`
Kiểm tra trước khi ghi bằng cùng quy tắc 5.1.4–5.1.5 (email/tên gán nhiều account → IdentityError, không ghi file). Ghi `{"identities": [...]}` bằng `yaml.safe_dump(allow_unicode=True, sort_keys=False)`; mỗi mục theo thứ tự key `email`, `name`, `account` (bỏ key None); mục sắp xếp theo `(account, email or "", name or "")`. Ghi `path.tmp` rồi `os.replace`; `OSError` → IdentityError. Đọc lại bằng `load_identities` cho cùng `IdentityMap` (khác thứ tự).

### 5.3 `key_from_email(email, name)`
1. `e = email.strip().lower()`.
2. Khớp `^(?:\d+\+)?([^@+]+)@users\.noreply\.github\.com$` → nhóm 1 (login, chữ thường).
3. `e` rỗng → `name.strip().lower()`; vẫn rỗng → `"(không rõ)"`.
4. Còn lại → `e`.

### 5.4 `is_bot_text(text)`
`any(m in text.lower() for m in BOT_MARKERS)`.

### 5.5 `github_repo_of(source)`
`urlsplit(source)`: scheme `https`, host `github.com` (không phân biệt hoa thường, không có port), path `/<owner>/<repo>` (bỏ `/` cuối, bỏ hậu tố `.git`), đúng 2 thành phần → `(owner, repo)`; ngược lại `None`.

### 5.6 `GitHubLoginResolver`
- Khởi tạo: đọc cache (`cache_path` hoặc `DEFAULT_LOGIN_CACHE`); không có / hỏng / sai `version` → cache rỗng + log WARNING (hỏng). `session` mặc định `requests.Session()`.
- `login_for(email, sha)`:
  1. `key = email.strip().lower()`; có trong cache (kể cả `null`) → trả giá trị cache, không gọi API.
  2. Resolver đã bị tắt (lỗi trước đó) → `None`.
  3. `GET {GITHUB_API}/repos/{owner}/{repo}/commits/{sha}` với `auth=` một lớp `requests.auth.AuthBase` đặt header `Authorization: Bearer <token>` (để `~/.netrc` không ghi đè), header `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `timeout`; `requests_made += 1`.
  4. 200 → đọc JSON; không đọc được hoặc không phải object → tắt, cảnh báo `GitHub API trả dữ liệu không hợp lệ; dùng email làm account.` Ngược lại `author = json.get("author")`; dict có `login` → `login.lower()`; ngược lại `None`. Lưu cache `key → giá trị`, ghi file (5.6.1). Trả giá trị.
  5. 401 → tắt resolver, cảnh báo `GitHub API từ chối token (401); dùng email làm account.` 403 hoặc 429 → tắt, cảnh báo `GitHub API hết lượt gọi hoặc bị chặn (<mã>); các email còn lại dùng email làm account.` 404/422 → không cache, `None` (không cảnh báo, log INFO). Mã khác → tắt, cảnh báo `GitHub API lỗi <mã>; dùng email làm account.`
  6. `requests.RequestException` → tắt, cảnh báo `Không gọi được GitHub API (<tên lỗi>); dùng email làm account.` (không in URL/headers).
  - Mỗi cảnh báo chỉ thêm một lần.
- 5.6.1 Ghi cache: `cache_path.parent.mkdir(parents=True, exist_ok=True)`; JSON `ensure_ascii=False`, `sort_keys=True`, indent 2; ghi tmp rồi `os.replace`; `OSError` → log WARNING, bỏ qua (không lỗi nghiệp vụ). Cache chỉ có email và login.

### 5.7 `AccountResolver.resolve(commit)` — thứ tự §3.5
Kết quả nhớ theo `(author_name, author_email, mapped_name, mapped_email)` (GitHub chỉ gọi 1 lần / email).
1. Theo D16 (email trước tên): `lookup_email(author_email)` → `lookup_email(mapped_email)` → `lookup_name(author_name)` → `lookup_name(mapped_name)`; kết quả đầu tiên khác None là account (giữ nguyên chữ).
2. `.mailmap` đã đổi identity (`(mapped_name, mapped_email.lower()) != (author_name, author_email.lower())`) → `key_from_email(mapped_email, mapped_name)`.
3. `github` không None → `login_for(author_email, commit.sha)`; có login → login.
4. `key_from_email(author_email, author_name)`.

### 5.8 `summarize_users(commits, resolver)`
1. Với mỗi commit: `account = resolver.resolve(c)`; `merge = c.is_merge`; cộng `commits` (không merge) hoặc `merge_commits`; thêm `Identity(author_name, author_email)` vào tập của account.
2. `is_bot = is_bot_text(account) or any(is_bot_text(i.name) or is_bot_text(i.email) for i in identities)`.
3. `identities` sắp xếp theo `(email.lower(), name, email)` (email gốc làm tiêu chí phụ để thứ tự không phụ thuộc hash seed — §15); users sắp xếp `(-commits, account)`.
4. `warnings` = `resolver.github.warnings` (nếu có).

### 5.9 `list_period_users(repo, snapshots, identities, token, login_cache)`
1. `commits = repo.log_commits(c_end.sha, c_start.sha if c_start else None, mailmap_rev=c_end.sha)`.
2. `gh = github_repo_of(repo.source)`; có `gh` và `token` → `GitHubLoginResolver(*gh, token, login_cache)`; ngược lại `None`.
3. `summarize_users(commits, AccountResolver(identities, github))`. Log INFO số user, số commit, số request API.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- Commit "trong kỳ" gồm cả commit trên nhánh đã merge vào (không chỉ first-parent) — đúng §3.1 `C_START..C_END`.
- Account chỉ có merge commit vẫn hiện (commit = 0) vì có thể được gán dòng giải quyết xung đột (§16).
- Committer không bao giờ được dùng.
- noreply dạng cũ `login@users.noreply.github.com` (không có số) cũng → `login`.
- Email so sánh không phân biệt hoa thường; tên khớp sau `strip()`, không phân biệt hoa thường.
- Kết quả tái lập: sắp xếp ổn định; cache GitHub chỉ làm nhanh, không đổi kết quả trừ khi GitHub đổi dữ liệu.

## 7. Xử lý lỗi & thông báo
| Tình huống | Exception / hành vi | Thông báo (tiếng Việt) | Log |
|---|---|---|---|
| File identities không tồn tại | IdentityError | `Không tìm thấy file identities: <path>` | — |
| Không đọc được / không phải UTF-8 | IdentityError | `File identities phải là văn bản UTF-8: <path>` / `Không đọc được file identities: <path> (<lỗi>)` | — |
| YAML lỗi | IdentityError | `File identities sai cú pháp YAML: <path> (dòng <n>)` | — |
| Cấu trúc sai | IdentityError | `File identities phải có dạng "identities: [danh sách]"` / `Key không hợp lệ trong identities.yaml: <k1, k2>` | — |
| Mục sai | IdentityError | `Mục <n> trong identities.yaml: <lý do>` (lý do: `cần account`, `cần email hoặc name`, `key không hợp lệ <k>`, `<field> phải là chuỗi`) | — |
| Email/tên gán nhiều account | IdentityError | `Email <e> được gán cho nhiều account: <a>, <b>` / `Tên <n> được gán cho nhiều account: <a>, <b>` | — |
| Ghi identities lỗi | IdentityError | `Không ghi được file identities <path>: <lỗi>` | ERROR |
| GitHub API lỗi | cảnh báo trong `UsersResult.warnings` | xem 5.6 | WARNING (không token) |
| Cache login hỏng / không ghi được | bỏ qua | — | WARNING |

## 8. Bảo mật, hiệu năng, tái lập
- Token: chỉ trong header request (thuộc tính private), không vào log/cảnh báo/cache/exception; `repr(GitHubLoginResolver)` không có token. Request chỉ tới `https://api.github.com`.
- Hiệu năng: tối đa 1 request / email chưa có trong cache; cache bền giữa các lần chạy.
- Tái lập: sắp xếp như 5.8; `save_identities` thứ tự cố định.

## 9. Test cases
Fixture: `RepoBuilder` (commit có author ≠ committer), `GitRepo.open(cache_root=tmp)`; GitHub API giả bằng `session` giả (không mạng).

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-identity-01 | key_from_email | `Alice@Corp.COM`, `12345+Alice@users.noreply.github.com`, `bob@users.noreply.github.com`, `""` + tên `Bình`, `""` + `""` | `alice@corp.com`, `alice`, `bob`, `bình`, `(không rõ)` | unit |
| TC-identity-02 | is_bot_text | `dependabot[bot]`, `Renovate Bot`, `github-actions`, `41898282+github-actions[bot]@users.noreply.github.com`, `alice` | True ×4, False | unit |
| TC-identity-03 | load_identities hợp lệ | file mẫu mục 4 (có BOM) | `lookup("x", "ALICE@corp.com") == "alice"`; noreply → `alice`; `lookup("alice n", "z@z")` → `alice`; không khớp → None | unit |
| TC-identity-04 | load_identities lỗi | không tồn tại; YAML sai; gốc là list; key lạ `foo`; mục thiếu account; mục thiếu email/name; `email: 5`; email trùng 2 account | đúng thông báo mục 7 | unit |
| TC-identity-05 | save/load vòng | map 3 quy tắc, tên tiếng Việt | file UTF-8 đọc lại cùng tập quy tắc; thứ tự mục sắp xếp; ghi 2 lần trùng byte | unit |
| TC-identity-06 | github_repo_of | `https://github.com/o/r`, `…/o/r.git`, `https://GitHub.com/o/r/`, `https://gitlab.com/o/r`, `git@github.com:o/r.git`, `https://github.com/o`, đường dẫn local | `(o, r)` ×3, None ×4 | unit |
| TC-identity-07 | Thứ tự ưu tiên | commit có identities khớp + mailmap đổi + API có login → identities; bỏ identities → mailmap; bỏ mailmap → API; API None → email | `alice-manual`, `alice@corp.com`, `alice-gh`, `x@y.com` | unit |
| TC-identity-08 | GitHub API + cache | session giả: 200 `{"author": {"login": "Alice"}}`; 200 `{"author": null}`; 2 commit cùng email | login `alice`; `null` → email; mỗi email 1 request; file cache có `{"version":1,"logins":{...}}`; resolver mới cùng cache → 0 request; token không có trong file cache, log | unit |
| TC-identity-09 | GitHub API lỗi | 401; 403; 429; 500; `ConnectionError`; 404 | 401/403/429/500/ConnectionError: cảnh báo đúng, resolver tắt (request sau = 0), kết quả = email; 404: None, không cảnh báo, không tắt | unit |
| TC-identity-10 | Không gọi API khi không đủ điều kiện | nguồn local + token; nguồn github không token; nguồn gitlab + token | `list_period_users` không tạo resolver (session giả không được gọi) | integration |
| TC-identity-11 | `.mailmap` gộp (mandatory C) | repo: alice commit bằng `alice@corp.com` và `12345+alice@users.noreply.github.com`; `.mailmap` map noreply → corp tại C_END | một account `alice@corp.com`, commits = 2, 2 identity | integration |
| TC-identity-12 | noreply + email công ty qua identities (§14) | không mailmap; identities `{email: alice@corp.com, account: alice}`, `{email: 12345+alice@…, account: alice}` | một account `alice`, commits = 2 | integration |
| TC-identity-13 | Không có quy tắc: noreply → login, email chữ thường | commit `Bob@Corp.com` và `999+bob@users.noreply.github.com` | 2 account `bob@corp.com`, `bob` (không tự gộp) | integration |
| TC-identity-14 | Author, không phải committer; merge | commit author alice / committer admin; merge commit author bob | admin không có trong danh sách; bob commits = 0, merge_commits = 1 | integration |
| TC-identity-15 | Danh sách trong kỳ, sắp xếp, bot | repo §14 + 1 commit `dependabot[bot]` trong kỳ + 1 commit admin trước kỳ | users = alice(2), bob(2), dependabot[bot](1, is_bot) theo `(-commits, account)`; admin không có | integration |
| TC-identity-16 | C_START rỗng | mọi commit trong kỳ (không có commit trước start) | đếm đủ mọi commit tới C_END | integration |
| TC-identity-17 | `.mailmap` sau end không áp dụng | `.mailmap` chỉ được thêm sau end | identity không bị đổi | integration |
| TC-identity-18 | Quy tắc khớp identity sau `.mailmap`; email thắng tên | `.mailmap` noreply → `alice@corp.com`; quy tắc `{email: alice@corp.com, account: A}` và `{name: alice, account: B}` | commit noreply → `A` (email sau mailmap thắng tên gốc) | unit |
| TC-identity-19 | Thứ tự identity tái lập | identity `(alice, Alice@Corp.com)` và `(alice, alice@corp.com)` chạy với `PYTHONHASHSEED` 1..6 (tiến trình con) | cùng một thứ tự mọi lần: `Alice@Corp.com` trước | unit |
| TC-identity-20 | Phản hồi 200 hỏng | body HTML (`requests.Response` thật, `json()` ném `JSONDecodeError`); body là list | cảnh báo `dữ liệu không hợp lệ`, resolver tắt, kết quả = email, không ném exception | unit |
| TC-identity-21 | `identities:` rỗng; save kiểm xung đột; netrc không ghi đè | file chỉ có `identities:`; `save_identities` với 2 quy tắc cùng email khác account; session thật + `NETRC` có `machine api.github.com` (chặn gửi bằng adapter giả) | map rỗng; IdentityError và không tạo file; header gửi đi là `Bearer <token>` | unit |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án đề xuất | Trạng thái |
|---|---|---|---|
| A1 | Theo đúng thứ tự §3.5, identity đã được `.mailmap` đổi thì **không** gọi GitHub API (key = email chuẩn). Hai email của cùng người, một qua mailmap, một qua API, có thể thành 2 account → người dùng gộp bằng `identities.yaml` | Giả định (đúng chữ §3.5) | Đã duyệt 2026-10-23 |
| A2 | GitHub API dùng SHA của commit **gặp đầu tiên** (mới nhất) của email đó trong kỳ | Giả định | Đã duyệt 2026-10-23 |
| A3 | Cache login dùng chung cho mọi repo GitHub (login của một email không phụ thuộc repo) | Giả định | Đã duyệt 2026-10-23 |
| A4 | Không tự gộp theo tên khi không có quy tắc (tên trùng giữa người khác nhau là phổ biến) | Giả định | Đã duyệt 2026-10-23 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-23 | Tạo mới | M3 |
| 2026-10-23 | Sửa theo review M3 (reviews/M3-20261023.md): khóa sắp xếp identity thêm email gốc (Major M1); 200 không phải JSON object → tắt + cảnh báo (Major M2); `save_identities` kiểm xung đột; `identities:` rỗng hợp lệ; tra quy tắc email trước tên cho cả identity gốc và sau mailmap (D16); `auth=` Bearer chống netrc; chữ ký mục 3 theo code; TC-18..21 | Review M3 FAIL |
