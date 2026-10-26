---
id: cli-users
title: Lệnh CLI loc-counter users
type: cli
milestone: M3
modules: [src/loc_counter/cli.py]
tests: [tests/test_cli_users.py]
spec_refs: ["3.1", "3.5", "10.2", "11", "15"]
depends_on: [config, git_repo, snapshot, identity]
status: reviewed
---

# Lệnh `loc-counter users`

## 1. Mục đích & phạm vi
Liệt kê user (account đã gộp) có commit trong kỳ trên một nhánh — tương đương danh sách ở khối [3] của màn hình (§10.2). Các hàm phân tích tham số repo/thời gian/token viết dùng chung để `analyze` (M5) dùng lại.
Ngoài phạm vi: export, đếm LOC (`analyze`, M5).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | `loc-counter users --repo <repo> --branch main --start ... --end ...` liệt kê user trong kỳ | §11 |
| R2 | Tham số thời gian như `analyze`: `--start-time`, `--end-time`, `--tz` | §11, §3.1 |
| R3 | Token chỉ đọc từ biến môi trường (`--token-env`), không nhận trực tiếp | §11 |
| R4 | `--identities identities.yaml`, `--config`, `--exclude-bots` | §11, §3.5 |
| R5 | Danh sách: sắp xếp số commit giảm dần, hiển thị số commit; bot có nhãn | §10.2[3], D14, D15 |
| R6 | Lỗi tiếng Việt; token không xuất hiện ở stdout/stderr | §15 |

## 3. Giao diện
```
loc-counter users --repo REPO [--branch BRANCH] --start YYYY-MM-DD --end YYYY-MM-DD
                  [--start-time HH:MM] [--end-time HH:MM] [--tz TZ]
                  [--config PATH] [--identities PATH] [--token-env NAME]
                  [--exclude-bots] [--json]
```
| Tham số | Bắt buộc | Mặc định | Ghi chú |
|---|---|---|---|
| `--repo` | có | — | URL hoặc đường dẫn local |
| `--branch` | không | nhánh mặc định của repo | không xác định được → lỗi |
| `--start`, `--end` | có | — | `YYYY-MM-DD` |
| `--start-time`, `--end-time` | không | không nhập | `HH:MM` (D10) |
| `--tz` | không | `timezone` trong config (`Asia/Bangkok`) | |
| `--config` | không | mặc định §9 | |
| `--identities` | không | không có quy tắc | D16 |
| `--token-env` | không | không dùng token | tên biến môi trường chứa token |
| `--exclude-bots` | không | tắt | ẩn user bot |
| `--json` | không | tắt | |

Mã thoát: 0 thành công; 1 lỗi nghiệp vụ (`LocCounterError`: `Lỗi: <thông báo>` ra stderr); 2 sai cú pháp (typer).

Hàm dùng chung trong `cli.py` (private, M5 dùng lại):
```python
def _parse_date(text: str, option: str) -> date: ...
def _parse_time(text: str | None, option: str) -> time | None: ...
def _read_token(token_env: str | None) -> str | None: ...
def _open_repo(repo: str, token: str | None) -> GitRepo:
    """GitRepo.open(..., cache_root=git_repo.DEFAULT_CACHE_ROOT) — đọc hằng tại thời điểm gọi."""
def _resolve_branch(repo: GitRepo, branch: str | None) -> str: ...
```

## 4. Đầu ra
**Bảng (mặc định)**, stdout:
```
Repo: <nguồn chuẩn hóa>
Nhánh: main • Kỳ: 2026-01-01 00:00:00 → 2026-01-31 23:59:59 (Asia/Bangkok)
Snapshot start: a1b2c3d 2025-12-15 10:00 admin: app.py
Snapshot end:   f9e8d7c 2026-01-08 10:00 bob del
User             Commit  Merge  Bot  Email
alice                 2      0       alice@example.com
bob                   2      0       bob@example.com
dependabot[bot]       1      0  bot  49699333+dependabot[bot]@users.noreply.github.com
TỔNG: 3 user, 5 commit
Cảnh báo: GitHub API hết lượt gọi ...
```
- Ngày commit snapshot theo múi giờ đã chọn, `%Y-%m-%d %H:%M`; C_START rỗng → `Snapshot start: (không có commit trước start)`.
- Cột Email: email gốc của các identity, không trùng, nối `, ` theo thứ tự `UserSummary.identities`.
- Số có dấu phẩy hàng nghìn. Bot: `bot` hoặc rỗng.
- Không có user → thay bảng bằng `Không có user nào có commit trong kỳ.`; vẫn in `TỔNG: 0 user, 0 commit`.
- Mỗi cảnh báo một dòng `Cảnh báo: <nội dung>`.

**JSON** (`--json`, `ensure_ascii=False`, indent 2):
```json
{
  "repo": "<nguồn chuẩn hóa>", "branch": "main", "timezone": "Asia/Bangkok",
  "start": "2026-01-01T00:00:00+07:00", "end": "2026-01-31T23:59:59+07:00",
  "c_start": {"sha": "...", "short_sha": "a1b2c3d", "date": "2025-12-15T10:00:00+07:00", "subject": "..."},
  "c_end": {"sha": "...", "short_sha": "...", "date": "...", "subject": "..."},
  "users": [{"account": "alice", "commits": 2, "merge_commits": 0, "is_bot": false,
             "identities": [{"name": "alice", "email": "alice@example.com"}]}],
  "warnings": []
}
```
`c_start` = `null` khi rỗng; `date` theo múi giờ đã chọn.

## 5. Luồng xử lý
1. Như `count`: stdout/stderr UTF-8, logging INFO ra stderr (callback chung).
2. `start_date = _parse_date(start, "--start")`, tương tự `--end`; `_parse_time` cho giờ. Định dạng sai → LocCounterError.
3. `cfg = load_config(config)`; `tz = tz or cfg.timezone`; `period = make_period(start_date, end_date, start_time, end_time, tz)`.
4. `identities = load_identities(identities_path)`.
5. `token = _read_token(token_env)`: `None` → None; biến không có hoặc rỗng → LocCounterError.
6. `repo = _open_repo(repo, token)`; `branch = _resolve_branch(repo, branch)` (None → `repo.default_branch()`; vẫn None → LocCounterError).
7. `snaps = find_snapshots(repo, branch, period)`.
8. `result = list_period_users(repo, snaps, identities, token, login_cache=identity.DEFAULT_LOGIN_CACHE)` (đọc hằng tại thời điểm gọi).
9. `--exclude-bots` → bỏ user `is_bot`.
10. In bảng hoặc JSON (mục 4). Mọi `LocCounterError` ở bước 2–8 → `Lỗi: ...` stderr, mã 1.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- `TỔNG` commit = tổng cột Commit (không tính merge) của các user đang hiển thị.
- Token không bao giờ được in; nguồn in ra là nguồn chuẩn hóa (URL có credential đã bị `git_repo` từ chối).
- `--tz` sai → lỗi của `make_period`.

## 7. Xử lý lỗi & thông báo
| Tình huống | Hành vi | Thông báo |
|---|---|---|
| Ngày sai định dạng | mã 1 | `Ngày không hợp lệ cho --start: <x> (định dạng YYYY-MM-DD)` |
| Giờ sai định dạng | mã 1 | `Giờ không hợp lệ cho --start-time: <x> (định dạng HH:MM)` |
| Biến token không có / rỗng | mã 1 | `Biến môi trường <NAME> chưa được đặt hoặc rỗng.` |
| Không xác định được nhánh | mã 1 | `Không xác định được nhánh mặc định; hãy truyền --branch.` |
| Lỗi từ config / identities / git_repo / snapshot | mã 1 | thông báo của exception |
| Thiếu tham số bắt buộc | mã 2 | thông báo của typer |

## 8. Bảo mật, hiệu năng, tái lập
- Token chỉ qua biến môi trường; không có trong stdout/stderr/log.
- Kết quả tái lập: thứ tự user theo `identity`; JSON key thứ tự cố định.
- Windows: stdout UTF-8 (tên, email tiếng Việt).

## 9. Test cases
Fixture: repo §14 (`section14_repo` trong conftest, dùng chung với snapshot/M4) + commit `dependabot[bot]` trong kỳ; monkeypatch `git_repo.DEFAULT_CACHE_ROOT`, `identity.DEFAULT_LOGIN_CACHE` vào `tmp_path`; `typer.testing.CliRunner`.

| ID | Mô tả | Input | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-cli-users-01 | Bảng | `users --repo <src> --branch main --start 2026-01-01 --end 2026-01-31` | mã 0; dòng Repo/Nhánh/Snapshot đúng; bảng alice 2, bob 2, dependabot[bot] 1 `bot`; `TỔNG: 3 user, 5 commit` | integration |
| TC-cli-users-02 | JSON | như 01 + `--json` | JSON đúng cấu trúc mục 4; `c_start.short_sha` 7 ký tự; `start` có `+07:00` | integration |
| TC-cli-users-03 | `--exclude-bots` | như 01 | không có dependabot; `TỔNG: 2 user, 4 commit` | integration |
| TC-cli-users-04 | `--identities` | file gộp `alice@example.com` và `bob@example.com` → `team` | 1 user `team` 4 commit (+ bot) | integration |
| TC-cli-users-05 | Ngày/giờ sai | `--start 2026-13-01`; `--start 01/01/2026`; `--end-time 25:00`; `--start-time 8:5` | mã 1, đúng thông báo mục 7 | unit |
| TC-cli-users-06 | start ≥ end | `--start 2026-02-01 --end 2026-01-01` | mã 1, `phải trước end` | unit |
| TC-cli-users-07 | Token | `--token-env NOPE` (không đặt) → mã 1; `--token-env MYTOK` với `MYTOK=ghp_SECRET` trên repo local | lỗi đúng; lần 2 mã 0 và `ghp_SECRET` không có trong stdout/stderr | integration |
| TC-cli-users-08 | Không có dữ liệu | `--start 2020-01-01 --end 2020-01-31` | mã 1, `Không có dữ liệu trong khoảng thời gian` | integration |
| TC-cli-users-09 | Nhánh | `--branch nope` → mã 1 `Không tìm thấy nhánh`; không truyền `--branch` → dùng `main` | | integration |
| TC-cli-users-10 | C_START rỗng | `--start 2025-01-01 --end 2026-01-31` (trước commit đầu) | `Snapshot start: (không có commit trước start)`; admin có trong danh sách | integration |
| TC-cli-users-11 | Thiếu `--repo` | `users --start ... --end ...` | mã 2 | unit |
| TC-cli-users-12 | Không có user | kỳ không có commit (C_START = C_END): `--start 2026-01-09 --end 2026-01-20` | `Không có user nào có commit trong kỳ.`; `TỔNG: 0 user, 0 commit` | integration |
| TC-cli-users-13 | Giờ + múi giờ | `--start-time 10:00 --end-time 10:00 --tz UTC` trên ngày có commit lúc 10:00+07 | dòng Kỳ hiển thị `… 10:00:00 → … 10:00:59 (UTC)` | integration |
| TC-cli-users-14 | Cảnh báo in sau TỔNG | `list_period_users` trả 1 cảnh báo (monkeypatch) | dòng `TỔNG` rồi `Cảnh báo: …` (mục 4); JSON có `warnings` | integration |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án đề xuất | Trạng thái |
|---|---|---|---|
| A1 | `--branch` không bắt buộc (mặc định nhánh mặc định của repo, giống UI §10.2) dù ví dụ §11 luôn truyền | Giả định | Đã duyệt 2026-10-23 |
| A2 | Cột Merge hiển thị số merge commit để giải thích user có Commit = 0 | Giả định | Đã duyệt 2026-10-23 |

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-23 | Tạo mới | M3 |
| 2026-10-23 | TC-14: thứ tự dòng cảnh báo theo mục 4 (review M3 m2) — code sai, spec giữ nguyên | Review M3 |
