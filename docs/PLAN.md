# Kế hoạch triển khai LOC Counter

Nguồn: [spec_count_LOC.md](../spec_count_LOC.md). Cập nhật bằng `/milestone-plan`.
Quy trình mỗi feature: `/feature-spec <id>` → duyệt → `/feature-implement <id>` (gồm `/feature-test`, `/feature-review`).

## 1. Tổng quan kiến trúc

```
CLI (cli.py) ─┐                         ┌─> report.py ─> xlsx / csv / json / manifest
              ├─> pipeline.py ──────────┤
UI (app.py) ──┘     │                   └─> counter.py ─> classifier.py (+ filters.py)
                    ├─> git_repo.py  (clone/fetch, rev-list, cat-file, diff, blame)
                    ├─> snapshot.py  (C_START, C_END, export start / end tất cả user)
                    ├─> identity.py  (tên, email → account key)
                    ├─> attribution.py (blame / reverse blame → added_by, deleted_by)
                    └─> builder.py   (export end theo user)
config.py: cấu hình + mặc định, dùng chung.
```

Thư mục project code: thư mục gốc repo (tương ứng `loc-counter/` mục 5). Package `loc_counter`, src layout.

## 2. Milestone và feature

Trạng thái: ⬜ chưa bắt đầu · 📝 spec draft · ✅ spec approved · 🔨 implemented · 🟢 reviewed

### M1 — Khởi tạo, classifier, `loc-counter count`
Việc không cần spec: `pyproject.toml`, `README.md` (khung), `config.example.yaml`, `.gitignore`, `src/loc_counter/__init__.py`, `tests/conftest.py` (khung).

| ID spec | Loại | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| `config` | module | config.py | §9, §3.1, §16 | — | 🟢 |
| `filters` | module | filters.py | §9 | config | 🟢 |
| `classifier` | module | classifier.py | §3.4, §6 | config | 🟢 |
| `counter` | module | counter.py (phần đếm thư mục) | §3.4, §8.1, §15 (encoding) | filters, classifier | 🟢 |
| `cli-count` | cli | cli.py | §11 | counter | 🟢 |

Tiêu chí hoàn thành: test classifier 9 ngôn ngữ (mandatory-tests mục A) pass; `loc-counter count` trên thư mục mẫu lệch ≤ 2% so với `cloc` (xem Q7).
**✅ M1 hoàn thành 2026-10-22** — 119 test pass, review PASS_WITH_NOTES (Minor đã sửa), tiêu chí cloc chấp nhận (D9). Báo cáo: [test-reports/M1-20261022.md](test-reports/M1-20261022.md), [reviews/M1-20261022.md](reviews/M1-20261022.md).

### M2 — Git, snapshot, export tất cả user
| ID spec | Loại | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| `git_repo` | module | git_repo.py | §4, §10.2[1], §15 | config | 🟢 |
| `snapshot` | module | snapshot.py | §3.1, §3.2, §3.3 (tất cả user), §12 (tên zip) | git_repo, filters | 🟢 |

Thứ tự: `git_repo` → `snapshot`. M2 chưa có lệnh CLI (`users` ở M3, `analyze` ở M5).

Phạm vi từng spec:
- `git_repo`: chạy lệnh git an toàn (list tham số, `-c core.quotepath=off`, che token trong log, lỗi tiếng Việt kèm lệnh trong log); kiểm tra git ≥ 2.30; mở repo (URL → bare clone vào `~/.loc_counter/repos/<sha1(URL đã bỏ thông tin xác thực)>`, đã có → fetch `+refs/heads/*:refs/heads/*` + prune; đường dẫn local → xem Q14); token qua biến môi trường của tiến trình git (`GIT_CONFIG_PARAMETERS` / `http.extraHeader`), không qua URL/argv/config; liệt kê nhánh + nhánh mặc định; `rev-list -1 --first-parent --before`; đọc thông tin commit (sha, committer date, tiêu đề); `ls-tree -r -z` (mode, sha, size, path); đọc blob dạng bytes. Phần `diff`/`blame` để M4 bổ sung vào spec này.
- `snapshot`: chuẩn hóa thời điểm (ngày + giờ tùy chọn + múi giờ → datetime có tz, kiểm `start < end`); tìm C_START/C_END; liệt kê file của snapshot sau bộ lọc §9 (`filters`, `classifier.detect_language`, `export_mode`, `exclude_binary`, kích thước) kèm cảnh báo; ghi zip tái lập (entry sắp xếp, timestamp cố định, nội dung blob nguyên byte); đặt tên zip §12; C_START rỗng → zip rỗng.

Việc không cần spec: `tests/conftest.py` — fixture `make_repo` dựng repo Git tạm với `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` cố định, `core.autocrlf=false`, không truy cập mạng; repo "remote" giả lập bằng đường dẫn `file://`.

Tiêu chí hoàn thành (mandatory-tests mục B):
- `uv run pytest tests/test_git_repo.py tests/test_snapshot.py -q` pass; toàn bộ `uv run pytest -q` pass; `uv run ruff check src tests` sạch.
- C_START/C_END đúng theo `Asia/Bangkok` với commit sát mốc 00:00:00 và 23:59:59 (cả hai phía), không nhập giờ, `start >= end`, không có commit trước start / trước end, first-parent bỏ qua commit của nhánh feature đã merge.
- Zip start / end (tất cả user) đúng danh sách file sau bộ lọc §9, nội dung từng file trùng byte với blob (giữ CRLF/LF), chạy 2 lần cho zip trùng SHA-256.
- Token giả trong test không xuất hiện trong log, message exception, `config` của repo cache.

**✅ M2 hoàn thành 2026-10-23** — 168 test pass (M2: 49), review lần 1 FAIL (3 Major đã sửa, spec duyệt lại), lần 2 PASS_WITH_NOTES. Báo cáo: [test-reports/M2-20261023.md](test-reports/M2-20261023.md), [reviews/M2-20261023.md](reviews/M2-20261023.md), [reviews/M2-20261023-r2.md](reviews/M2-20261023-r2.md).

Việc tồn đọng từ review M2 lần 2 (Minor) — xử lý khi cập nhật spec `git_repo` ở M3, cần người dùng duyệt:
| # | Vấn đề | Đề xuất |
|---|---|---|
| F1 | Token sai → git vẫn gọi `GIT_ASKPASS` (VS Code terminal có thể bật hộp thoại, treo) | ✅ Đã xử lý 2026-10-23 (M3, D20): Đặt `GIT_ASKPASS=""` (và `SSH_ASKPASS=""`) cho mọi lệnh git |
| F2 | Clone local dùng hardlink: `chmod` khi xóa cache hỏng đổi quyền file pack của repo nguồn | ✅ Đã xử lý 2026-10-23 (M3, D20): Clone local với `--no-hardlinks` (an toàn hơn, tốn đĩa hơn) |
| F3 | `write_zip` lỗi giữa chừng: tiến trình `cat-file` còn sống khi exception còn được giữ | ✅ Đã xử lý 2026-10-23 (M3, D20): Đóng generator `read_blobs` tường minh (`contextlib.closing`) |
| F4 | Không tạo được `cache_root` → `FileExistsError` tiếng Anh | ✅ Đã xử lý 2026-10-23 (M3, D20): Bọc `OSError` thành `GitError "Không tạo được thư mục cache"` |
| F5 | `i18n.logOutputEncoding` toàn cục làm hỏng tên tác giả | ✅ Đã xử lý 2026-10-23 (M3, D20): Thêm `-c i18n.logOutputEncoding=UTF-8` vào tùy chọn chung |
| F6 | Đường dẫn không an toàn chưa gồm `C:`, `:` , `.git.` (Windows) | ✅ Đã xử lý 2026-10-23 (M3, D20): Mở rộng quy tắc ở `snapshot` (và dùng chung cho `builder` M4) |
| F7 | `read_blobs` lỗi không ghi log, mất stderr | ✅ Đã xử lý 2026-10-23 (M3, D20): Log WARNING kèm stderr đã che token |
| F8 | (review M3) File có `:` trong tên (hợp lệ trên Linux) bị bỏ khỏi export chỉ với log, không có `LocWarning` → người dùng không thấy trong `warnings.csv` | ✅ Đã xử lý 2026-10-23: `WarningKind.UNSAFE_PATH` (spec `counter` M4), phát trong `snapshot.screen_entry` |
| F9 | (review M3, M4) Giải nén export ra đĩa Windows: hai đường dẫn chỉ khác hoa thường đè nhau; tên có `.`/khoảng trắng cuối (`a.py.` ≡ `a.py`); ký tự cấm `<>"|?*`; tên thiết bị (`CON`, `NUL.py`…) → LOC "đếm trên thư mục export" lệch git | Quyết định khi viết spec `counter`/`pipeline` M5 (đếm từ nội dung zip/blob thay vì giải nén ra đĩa). M4: export dựng bằng `builder` đã có `PATH_CONFLICT` (D32); `plan_export` (export start / `all`) chưa kiểm hai file chỉ khác hoa thường → làm ở M5. **M5: chốt D36 (đếm từ nội dung), D39 (`WINDOWS_PATH`), A13 (`PATH_CONFLICT` cho start / `all`)** |

### M3 — Identity, `loc-counter users`
| ID spec | Loại | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| `git_repo` (cập nhật) | module | git_repo.py | §3.1, §3.5, §15 | — | 🟢 |
| `snapshot` (cập nhật) | module | snapshot.py | §12, §15 | git_repo | 🟢 |
| `identity` | module | identity.py | §3.5, §16 | git_repo, config | 🟢 |
| `cli-users` | cli | cli.py | §11, §3.1, §10.2[3] | identity, snapshot | 🟢 |

Thứ tự: `git_repo` (cập nhật) → `snapshot` (cập nhật) → `identity` → `cli-users`.

Phạm vi:
- `git_repo` cập nhật: `log_commits(c_start, c_end, mailmap_rev)` — mọi commit trong `C_START..C_END` (C_START rỗng → mọi commit tới C_END), mỗi commit: sha, số parent, author name/email gốc (`%an`/`%ae`), sau `.mailmap` (`%aN`/`%aE`), author date; `.mailmap` lấy từ C_END (`-c mailmap.blob=<C_END>:.mailmap -c mailmap.file=`). Xử lý tồn đọng F1, F2, F4, F5, F7.
- `snapshot` cập nhật: F3 (đóng `read_blobs` khi lỗi), F6 (đường dẫn không an toàn kiểu Windows).
- `identity`: đọc/ghi `identities.yaml`; gộp (tên, email) → account key theo thứ tự §3.5 (identities.yaml > .mailmap > GitHub API > email; noreply → login); nhận diện bot; GitHub API qua `requests` (mock trong test) + cache email → login; danh sách user trong kỳ (account, số commit không tính merge, các identity, cờ bot), sắp xếp số commit giảm dần.
- `cli-users`: `loc-counter users --repo --branch --start --end [--start-time --end-time --tz --config --identities --token-env --exclude-bots --json]`; phần phân tích tham số thời gian/repo dùng chung với `analyze` (M5).

Việc không cần spec: `identities.example.yaml` (định dạng theo D16), cập nhật README (lệnh `users`, file identities).

Tiêu chí hoàn thành (mandatory-tests mục C):
- `uv run pytest -q` pass toàn bộ; `uv run ruff check src tests` sạch.
- Gộp nhiều email qua `identities.yaml`; `.mailmap`; noreply `12345+login@users.noreply.github.com` → `login`; noreply + email công ty cùng account (§14); mặc định email chữ thường; thứ tự ưu tiên; GitHub API mock + cache; bot; author chứ không phải committer.
- `uv run loc-counter users --repo <repo mẫu> --branch main --start 2026-01-01 --end 2026-01-31` in đúng danh sách trên repo mẫu §14 (alice, bob — không có admin vì commit trước kỳ).

**✅ M3 hoàn thành 2026-10-23** — 237 test pass, review lần 1 FAIL (2 Major đã sửa, spec duyệt lại), lần 2 PASS_WITH_NOTES (Minor/Nit đã sửa). Báo cáo: [test-reports/M3-20261023.md](test-reports/M3-20261023.md), [reviews/M3-20261023.md](reviews/M3-20261023.md), [reviews/M3-20261023-r2.md](reviews/M3-20261023-r2.md).

### M4 — Export end theo user
| ID spec | Loại | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| `git_repo` (cập nhật) | module | git_repo.py | §7.2, §7.4, §15 | — | 🟢 (gồm D29: `is_ancestor`, `merge_bases`) |
| `snapshot` (cập nhật) | module | snapshot.py | §9, §12, §15 | git_repo | 🟢 (gồm F8: cảnh báo `UNSAFE_PATH`) |
| `counter` (cập nhật nhỏ) | module | counter.py | §7.5 | — | 🟢 |
| `attribution` | module | attribution.py | §7.1, §7.2, §7.5, §8.2 (added/deleted), §16 | git_repo, identity, classifier | 🟢 |
| `builder` | module | builder.py | §3.3, §7.3, §7.4, §7.5, §12 (user-tag) | attribution, snapshot | 🟢 |

Thứ tự: `git_repo` → `snapshot` → `counter` → `attribution` → `builder`. M4 chưa có lệnh CLI (`analyze` ở M5).

**Tiến độ M4 (2026-10-23):** `git_repo`, `snapshot` 🟢 (369 test pass; review lần 1 FAIL → sửa, lần 2 PASS_WITH_NOTES; báo cáo [test-reports/M4-git_repo-snapshot-20261023.md](test-reports/M4-git_repo-snapshot-20261023.md), [reviews/git_repo-snapshot-20261023-r2.md](reviews/git_repo-snapshot-20261023-r2.md)). `counter` (danh mục `WarningKind` M4) + `snapshot` F8 (`UNSAFE_PATH`) 🟢 (375 test pass, review PASS; [test-reports/M4-counter-snapshot-20261023.md](test-reports/M4-counter-snapshot-20261023.md), [reviews/counter-snapshot-20261023.md](reviews/counter-snapshot-20261023.md)). `git_repo` D29 (`is_ancestor`, `merge_bases`) 🟢 (review PASS_WITH_NOTES, [reviews/git_repo-D29-20261023.md](reviews/git_repo-D29-20261023.md)). `attribution` 🟢 (436 test pass; review r1 FAIL → sửa D28 bước (0), r2 FAIL (test TC-36) → sửa, r3 PASS; [test-reports/M4-attribution-20261023.md](test-reports/M4-attribution-20261023.md), [reviews/attribution-20261023-r3.md](reviews/attribution-20261023-r3.md)). `builder` 🟢 (+ `counter` D32 `PATH_CONFLICT`; 495 test pass; review PASS_WITH_NOTES, Minor đã sửa; [test-reports/M4-builder-20261023.md](test-reports/M4-builder-20261023.md), [reviews/builder-20261023.md](reviews/builder-20261023.md)).

**✅ M4 hoàn thành 2026-10-23** — 495 test pass, ruff sạch, coverage 98 %; tiêu chí mandatory-tests mục D đạt (trừ kiểm tra chéo §8.3, thuộc `pipeline` M5). Báo cáo: [test-reports/M4-20261023.md](test-reports/M4-20261023.md). Quyết định chốt theo khuyến nghị khi người dùng ủy quyền: D32–D34. **Bước tiếp theo:** `/milestone-plan M5` (mang theo F9, A13 của `builder`, rủi ro mục 5).

Phạm vi từng spec (phân tích của `spec-analyst`, đã chạy thử trên git 2.55):
- `git_repo` cập nhật: `diff_tree(c_start, c_end)` (`diff-tree -r -z --raw -M`, C_START rỗng → mọi file là `A`; rename phải truyền cả hai đường dẫn); `diff_hunks` (`-p -U0`, Myers tường minh, chỉ đọc header `@@`); `blame(..., reverse, detect_moves, line_ranges)` với `--line-porcelain --root --no-ignore-revs-file`, bỏ C-quote `filename`; `first_commit_after` (`rev-list --ancestry-path --topo-order --reverse`, lấy **dòng đầu** — `-1 --reverse` trả commit mới nhất); `path_creator` (Q23). Kết quả không phụ thuộc cấu hình git toàn cục (`blame.showRoot`, `blame.ignoreRevsFile`, `diff.algorithm`, `color.ui`, `diff.noprefix`).
- `snapshot` cập nhật: tách `write_zip` → `write_entries` (entry tham chiếu blob hoặc nội dung bytes); tách logic lọc từng file của `plan_export` thành hàm công khai để builder áp lên tên/nội dung kết quả; F6/F8 dùng chung.
- `counter` cập nhật: thêm `WarningKind` cho M4 (`MULTI_USER_HUNK`, `SEQUENTIAL_EDIT`, `MOVED_LINES`, `UNATTRIBUTED`, `MISSING_EOL`, `UNSAFE_PATH` (F8), `RENAME_LIMIT`…).
- `attribution`: tính **một lần cho cả kỳ** (không phụ thuộc user chọn): mỗi cặp file từ `diff_tree` → hunk, `added_by`/`deleted_by` cho các dòng **trong hunk** (account lấy từ `log_commits` + `AccountResolver`, không lấy tên trong porcelain), `renamed_by`, `added_code`/`deleted_code` theo user (Q30), cảnh báo §7.5.
- `builder`: `split_lines_keepends` (bytes, giữ CRLF), `build_user_file` (§7.3, thêm tham số `hunks`), `build_user_export(attribution, start_plan, users)` → danh sách file (blob hoặc bytes) + cảnh báo, áp quy tắc cấp file §7.4; `user_tag`; ghi zip qua `snapshot.write_entries` (timestamp = committer date C_END). Không ghi zip trực tiếp, không đếm LOC (M5).

Việc không cần spec: fixture trong `tests/conftest.py` — `section14_repo(rename=…, empty_start=…)`, repo merge song song, repo dời khối trong file / sang file khác, repo đổi khoảng trắng / CRLF→LF / thiếu EOL, repo xóa rồi tạo lại, repo nhiều user cùng hunk / sửa liên tiếp, cấu hình git toàn cục "khó chịu". Cập nhật README: giới hạn của export end theo user (§7.5).

Tiêu chí hoàn thành (mandatory-tests mục D):
- `uv run pytest -q` pass toàn bộ; `uv run ruff check src tests` sạch.
- Repo mẫu §14: LOC trên nội dung export end — tất cả user 10→20, chỉ alice 10→13 (không có `util.py`, dòng bob xóa vẫn còn), chỉ bob 10→17, alice+bob 10→20 (nội dung `app.py` trùng byte với C_END); alice `added_code=5, deleted_code=2, net=+3`, bob `8/1/+7`.
- Rename trong kỳ không tính là xóa + thêm; noreply + email công ty gộp cùng account; start trước commit đầu → `loc_start = 0`; thêm block comment nhiều dòng không tăng LOC.
- Zip end theo user chạy 2 lần trùng SHA-256; giữ nguyên byte (CRLF/BOM) của dòng không đổi.

### M5 — Đếm, báo cáo, pipeline, `loc-counter analyze`
| ID spec | Loại | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| `counter` (mở rộng) | module | counter.py | §3.4, §8.1, §8.2, §8.3, §7.5 | classifier (kiểu attribution/identity chỉ dưới `TYPE_CHECKING`, D37); `weekly_metrics` cần `attribution.commit_stats` | 🟢 |
| `attribution` (cập nhật nhỏ) | module | attribution.py | §10.3, §12 (`Theo_tuan`) | git_repo | 🟢 |
| `builder` (cập nhật nhỏ) | module | builder.py | §7.4, F9 (A13, D39) | — | 🟢 |
| `report` | module | report.py | §12, §7.5, §10.3, §15 | counter, config | 🟢 |
| `pipeline` | module | pipeline.py | §3, §8, §10.2 (tiến độ), §12, §15 | tất cả module trên | 🟢 |
| `cli-analyze` | cli | cli.py | §11, §12 | pipeline | 🟢 |

Thứ tự: `counter` → `attribution` → `builder` → `report` → `pipeline` → `cli-analyze` (viết spec). Lập trình: `attribution` (cập nhật) trước phần `weekly_metrics` của `counter` (spec `counter` A8) — hoặc lập trình `counter` trừ TC-37 rồi hoàn tất sau `attribution`.

**Tiến độ M5 (2026-10-24):** `attribution` (cập nhật D35: `added_commit`/`deleted_commit`, `commit_stats`) 🟢 — 512 test pass, coverage `attribution.py` 100 %, review PASS_WITH_NOTES (Minor test đã sửa); [test-reports/M5-attribution-20261024.md](test-reports/M5-attribution-20261024.md), [reviews/attribution-20261024.md](reviews/attribution-20261024.md). `counter` M5 có thể lập trình đủ, gồm `weekly_metrics` (TC-counter-37).
`counter` (M5) 🟢 — 545 test pass, coverage `counter.py` 99 %, review PASS_WITH_NOTES (Minor 1, 2, 3, 5 đã sửa); [test-reports/M5-counter-20261024.md](test-reports/M5-counter-20261024.md), [reviews/counter-20261024.md](reviews/counter-20261024.md).
`builder` (cập nhật M5: `path_conflict_warnings`, `windows_path_issues`, `windows_path_warnings` — A13, D39; `builder` cung cấp hàm, `pipeline` gọi cho mọi export, spec `builder` A14–A16) 🟢 — 587 test pass, coverage `builder.py` 100 %, review PASS_WITH_NOTES (Minor 1 + Nit đã sửa); [test-reports/M5-builder-20261024.md](test-reports/M5-builder-20261024.md), [reviews/builder-20261024.md](reviews/builder-20261024.md).
`report` (`ReportData`, `ReportWarning`, `ExportSummary`, `ReportOptions`; `write_xlsx` 6 sheet tái lập, `write_csv_reports`, `write_warnings_csv`, `build_manifest` / `write_manifest`, `write_reports`; spec A1–A13, ranh giới với `pipeline` ở mục 1) 🟢 — 612 test pass, coverage `report.py` 100 %, tái lập xlsx/CSV trùng SHA-256 (manifest bằng nhau khi bỏ `generated_at`), review PASS_WITH_NOTES (5 Minor + 5 Nit đã sửa, còn Nit 6); [test-reports/M5-report-20261024.md](test-reports/M5-report-20261024.md), [reviews/report-20261024.md](reviews/report-20261024.md).
`pipeline` spec ✅ approved 2026-10-24 ([specs/pipeline.md](specs/pipeline.md), A1–A17 chốt theo khuyến nghị, người dùng ủy quyền; 35 TC): `run_log` context manager do CLI/UI bọc cả `GitRepo.open`, `make_resolver`, `prepare_period` (API hai pha cho M6), `match_users` (D40-N19 đặt trong pipeline), `result_dir_name`, `run_analysis`; thay thư mục bằng đổi tên thư mục cũ (Windows), kiểm độ dài đường dẫn khi chưa bật long path. **Bước tiếp theo:** `/feature-implement pipeline` (song song có thể `/feature-spec cli-analyze`).
`pipeline` 🟢 (2026-10-25) — 656 test pass, coverage `pipeline.py` 99 %, 36 TC; review lần 1 FAIL (Major: level logger khi nhiều luồng; Minor: lỗi thư mục tạm / đổi tên chưa tiếng Việt, nhánh lỗi chưa test) → sửa spec (A18–A20, TC-36) + code; review r2 PASS_WITH_NOTES (Minor khôi phục thư mục cũ đã sửa; còn Nit 1, 2: ERROR in ra stderr khi chưa có handler, lỗi `_commit_dir` log hai lần); [test-reports/M5-pipeline-20261025.md](test-reports/M5-pipeline-20261025.md), [reviews/pipeline-20261025.md](reviews/pipeline-20261025.md), [reviews/pipeline-20261025-r2.md](reviews/pipeline-20261025-r2.md). Mở cho M6: Q46 (`run.log` khi nhiều phiên cùng `out_root`). README (lệnh `analyze`, `run.log`, thư mục `.loc-tmp-*`/`.loc-old-*` sót lại, trùng tên thư mục kết quả) làm cùng `cli-analyze`.
`cli-analyze` spec ✅ approved 2026-10-24 ([specs/cli-analyze.md](specs/cli-analyze.md), A1–A10 chốt theo khuyến nghị, người dùng ủy quyền; 24 TC): kiểm tham số trước `run_log` (sai tham số không tạo `--out`), `run_log` bọc `GitRepo.open` → `make_resolver` → `run_analysis`; tiến độ `[i/5]` ra stderr; stdout bảng theo §10.3 (dòng Tổng khi có user) hoặc `--json` (`manifest` đọc lại từ file); mã 0/1/2, Ctrl+C 130. Lập trình sau khi `pipeline` implemented: `/feature-implement cli-analyze`. **Bước tiếp theo:** `/feature-implement cli-analyze` (`pipeline` đã 🟢; `pipeline` tự log ERROR cho lỗi trước bước 9 — `SnapshotError` ở `prepare_period`, `PipelineError` qua `_error` — nên CLI không cần ghi bù theo A9).
`cli-analyze` 🟢 (2026-10-25) — 25 test (`tests/test_cli_analyze.py`), coverage `cli.py` 99 %; review PASS_WITH_NOTES, 4 Minor đã sửa (spec sửa trước: A9 không log lại `PipelineError`/`SnapshotError`, A11 lỗi đọc `manifest.json` khi `--json`, A12 `pretty_exceptions_show_locals=False`, test bổ sung); còn Nit (cột LOC của "Bản export" căn trái, `--tz ""` dùng múi giờ config); [reviews/cli-analyze-20261025.md](reviews/cli-analyze-20261025.md). README: mục `analyze`, kết quả, `run.log`, thư mục tạm sót lại, trùng tên thư mục, kiểm tra chéo, giải nén trên Windows. **M5 hoàn thành** — [test-reports/M5-20261025.md](test-reports/M5-20261025.md). **Bước tiếp theo:** `/milestone-plan M6` → xong 2026-10-25 (D41); tiếp: `/feature-spec screen-input`.
`screen-input` 🟢 (2026-10-25) — 33 test (`tests/test_app_input.py`, AppTest), coverage `app.py` 97 %; review lần 1 FAIL (Major: múi giờ từ config bị `selectbox` âm thầm đổi; dòng snapshot nằm sai khối) → sửa spec (A13–A16, TC-24) + code; r2 PASS_WITH_NOTES (Minor test đã bổ sung; còn Nit: traceback lỗi lạ ghi 2 lần trong `run.log`, nhãn/thứ tự ô nâng cao lệch nhẹ, spinner ở khối [3]); [reviews/screen-input-20261025.md](reviews/screen-input-20261025.md), [reviews/screen-input-20261025-r2.md](reviews/screen-input-20261025-r2.md). Lưu ý: phiên Claude khác (tool-e1) từng ghi đè tạm spec — đã nhắn dừng. Tiếp: `/feature-spec screen-result`.
`screen-result` 🟢 (2026-10-25) — 14 test (`tests/test_app_result.py`), toàn bộ 728 pass trước khi sửa review; review FAIL (Major: `pyproject.toml` còn `streamlit>=1.40` trong khi dùng `download_button(data=callable)`) → nâng `streamlit>=1.66` + `uv lock`; Minor (test lọc / khóa / tham số nút tải) đã sửa, A8 nhãn bộ lọc, A9 định dạng số; [reviews/screen-result-20261025.md](reviews/screen-result-20261025.md). Tiếp: `/feature-spec screen-identity`.
`screen-identity` 🟢 (2026-10-25) — 19 test (`tests/test_app_identity.py`); review FAIL (Major: ô xóa trống lưu thành `"nan"` — pandas 3 StringDtype; sửa đổi chưa lưu áp sang hàng khác khi bảng đổi) → A5–A8; r2 FAIL (Major: xóa state phía server không reset frontend `data_editor`) → key theo thế hệ `identity_editor_<gen>`; r3 PASS_WITH_NOTES (Minor test đã sửa; còn Nit: bấm Phân tích bỏ sửa đổi chưa lưu không báo, xóa trống hàng không có quy tắc vẫn tạo file `identities: []`; câu hỏi quy tắc trên email/tên đã qua `.mailmap` ghi Q48); [reviews/screen-identity-20261025.md](reviews/screen-identity-20261025.md), [r2](reviews/screen-identity-20261025-r2.md), [r3](reviews/screen-identity-20261025-r3.md). README mục Giao diện; `mandatory-tests.md` mục F. Tiếp: `/feature-test M6`.
**M6 hoàn thành (2026-10-25)** — 747 test pass, coverage `app.py` 98 %; kiểm tra khói `/_stcore/health` = ok; kiểm tra trên trình duyệt thật (Playwright) luồng §14 + tải file trùng SHA-256; [test-reports/M6-20261025.md](test-reports/M6-20261025.md). README: lệnh chạy UI với `--server.address localhost`. **Bước tiếp theo:** M7 (hiệu năng) — cần repo đo (~5.000 file, 2.000 commit trong kỳ) theo tiêu chí §13.
**Tồn đọng M1–M6 đã xử lý (2026-10-25):** (1) `git_repo` 5.3 từ chối mật khẩu trong URL mọi scheme + scp, userinfo theo `@` cuối (không dùng `urlsplit`), từ chối `<transport>::`, che thông báo đường dẫn local — TC-git_repo-54, review [FAIL](reviews/git_repo-password-20261025.md) → [r2 PASS_WITH_NOTES](reviews/git_repo-password-20261025-r2.md); (2) bảng F1–F7 đánh ✅; (3) TC-pipeline-37: lệch kiểm tra chéo `vendor/` và file→symlink (fixture `build_systematic_mismatch`). 750 test pass, coverage 99 %.

Phạm vi từng spec (phân tích của `spec-analyst` 2026-10-23, đã chạy thử kiểm tra chéo trên repo §14 bằng API hiện có: 10/20, 10/13, 10/17, 10/20 khớp):
- `counter` mở rộng: `ContentFile(path, language, data, cache_key)` + `count_files(...)` — đếm LOC từ **nội dung entry đưa vào zip** (D36), bỏ file `language=None` và file vượt `max_file_size_kb` (không cảnh báo lại, D40-N4); `compare_languages` → `LanguageRow`; `compare_files` → `FileRow` (khóa theo đường dẫn export end, cột "Đổi tên từ"); `user_metrics` → `UserMetrics(account, is_bot, commits, added_lines, deleted_lines, added_code, deleted_code, net_code, files_changed)` (định nghĩa `files_changed` D40-N7); `weekly_metrics` → `WeekRow` (D35); `cross_check` → `CrossCheck` + `cross_check_warning` (D38); thêm `WarningKind.CROSS_CHECK`, `IDENTITY`, `WINDOWS_PATH` (D39). Dùng một `LineClassifier` chung (cache theo blob SHA).
- `attribution` cập nhật: thêm `added_commit` / `deleted_commit` (sha) song song `added_by` / `deleted_by` ở mọi bước gán (blame, reverse blame, D23, D28 (a)(b)), và `PeriodAttribution.commit_stats: tuple[CommitLineStats(sha, account, added_lines, deleted_lines, added_code, deleted_code), …]` sắp theo sha, tính cùng chỗ với `UserLineStats` (bất biến Σ theo account bằng nhau) — phục vụ `Theo_tuan` (D35; spec `counter` A8).
- `builder` cập nhật: tách `path_conflict_warnings(paths)` công khai (refactor giữ hành vi) để `pipeline` kiểm `PATH_CONFLICT` cho export start và export `all` (A13).
- `report`: kiểu `ReportData`, `ReportWarning(kind, path, message, scopes)`, `ExportSummary`; `write_xlsx` (6 sheet đúng tên §12, chuẩn hóa tái lập — D40-N14), `write_csv_reports` (3 CSV), `write_warnings_csv`, `build_manifest` / `write_manifest`, `write_reports`. Định dạng theo D40-N8, N15, N18, N20, N21; chống chèn công thức, lọc ký tự điều khiển (D40-R).
- `pipeline`: `AnalysisRequest` (không chứa token), `Step` (tiến độ theo thứ tự thực, D40-N16), `AnalysisResult` (đủ dữ liệu cho màn hình §10.3 ở M6), `run_analysis(repo, request, resolver, progress)` — nhận `GitRepo` đã mở và **một** `AccountResolver` dùng chung cho `summarize_users` và `attribute_period`; tên thư mục kết quả (D40-N10), dựng thư mục tạm rồi thay thế (D40-N13), `run.log` (D40-N12), xuất riêng (D40-N17), gộp + sắp ổn định cảnh báo (D31), kiểm `PATH_CONFLICT` cho start / `all` (A13), cảnh báo `WINDOWS_PATH` (D39).
- `cli-analyze`: `loc-counter analyze` đủ tham số §11 (`--out` bắt buộc, `--branch` tùy chọn như `users`, `--json` tùy chọn); dùng lại phần phân tích kỳ/repo/token của `cli-users`; khớp `--user` (D40-N19); mã thoát + stdout (D40-N22).

Việc không cần spec:
- Fixture `tests/conftest.py`: repo §14 kèm `identities.yaml` gộp email → `alice` / `bob`; repo ca lệch kiểm tra chéo (đổi tên `.txt`→`.py`, đổi tên vào `vendor/`, file→symlink); repo có `A.py` / `a.py` (tạo bằng `update-index`); `GitRepo` với nguồn `https://github.com/org/repo` + token giả (không mạng, mock `requests`).
- README: lệnh `analyze`, danh sách file đầu ra, `run.log`, ý nghĩa và giới hạn kiểm tra chéo (D38, D40-N6), cảnh báo giải nén trên Windows (F9), CSV với locale dùng `;`, cảnh báo `MULTI_USER_HUNK` khi C_START rỗng (N23).
- Cập nhật `.claude/skills/feature-test/mandatory-tests.md` mục E: `run.log` ở `<out>/run.log`; so sánh tái lập loại `manifest.json` (chỉ khác `generated_at`) và `run.log`.

Tiêu chí hoàn thành (§13 + mandatory-tests mục E), chạy trong thư mục gốc repo:
1. `uv run pytest -q` pass toàn bộ; `uv run ruff check src tests` sạch; coverage `counter`, `report`, `pipeline` ≥ 90 % (`uv run pytest --cov=loc_counter --cov-report=term-missing`).
2. Repo §14 + `identities.yaml`: `uv run loc-counter analyze --repo <src> --branch main --start 2026-01-01 --end 2026-01-31 --out <tmp>` với: không `--user` → 10/20; `--user alice` → 10/13; `--user bob` → 10/17; `--user alice --user bob` (có và không `--separate-users`) → 10/20. alice `5/2/+3`, bob `8/1/+7`. `cross_check.diff_percent == 0`, không có cảnh báo `cross_check`. Thư mục `repo_main_2026-01-01_2026-01-31_{all|alice|bob|multi-2users}`.
3. Đủ file §12: `start_2026-01-01_<sha7>.zip`, `end_2026-01-31_<tag>.zip` (+ zip riêng), `loc_report.xlsx` với `sheetnames == [Tong_quan, Theo_ngon_ngu, Theo_user, Theo_file, Theo_tuan, Canh_bao]`, 3 CSV bắt đầu `EF BB BF`, `warnings.csv`, `manifest.json` đủ key §12; `<out>/run.log`.
4. Chạy 2 lần vào hai `--out` khác nhau → mọi file trong thư mục kết quả trùng SHA-256, trừ `manifest.json` (bằng nhau sau khi bỏ `generated_at`).
5. Ca lệch cố ý (đổi tên `.txt`→`.py`) → `warnings.csv` có `cross_check` kèm hai giá trị.
6. Token giả (và dạng base64 `x-access-token:<token>`) không xuất hiện trong thư mục kết quả, `run.log`, repo cache, `github_logins.json`.
7. LOC đếm từ nội dung entry = đếm từ đọc lại zip = `count_directory` trên thư mục giải nén (repo §14).
8. Lỗi → mã 1 + thông báo tiếng Việt (ngày sai, `--user` không có trong kỳ, không có dữ liệu); thiếu `--out` → mã 2.

### M6 — Giao diện Streamlit
| ID spec | Loại | File nguồn | Mục spec gốc | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| `screen-input` | screen | app.py | §10.1, §10.2 [1][2][3], nút Phân tích, tùy chọn nâng cao, thư mục đầu ra | pipeline, identity, config | 🟢 |
| `screen-result` | screen | app.py | §10.3, §12 (tải mọi file), §7.5 (ghi chú) | screen-input, pipeline, report | 🟢 |
| `screen-identity` | screen | app.py | §10.2 "Quản lý gộp account", §3.5, D16 | screen-input, identity | 🟢 |

Thứ tự: `screen-input` → `screen-result` → `screen-identity` (luồng đầu–cuối và tải file sớm nhất; gộp account sửa trạng thái của màn hình nhập). Cả 3 spec `modules: [src/loc_counter/app.py]` — không thêm module ngoài §5 (D41-N1).

Phân tích `spec-analyst` 2026-10-25 (streamlit 1.66.1, pandas 3.1.0 trong `uv.lock`; đã kiểm chứng V1–V14: AppTest có `download_button`, `data_editor` sửa qua `session_state`, `download_button(data=callable)`, `st.dialog` mất nút sau rerun, `RerunException`/`StopException` kế thừa `BaseException`, traceback Streamlit `show_locals=False`, `run_analysis` §14 ≈ 1,6 s → AppTest `default_timeout=60`). Quyết định ở D41.

Cấu trúc `app.py`: hàm thuần (không gọi `st.*`) ở mức module, test bằng pytest thường; giao diện trong `main()`, cuối file `if __name__ == "__main__": main()`; trạng thái chung tiến trình (khóa `out_root`, khóa cache repo) qua `@st.cache_resource` (biến toàn cục của script bị tạo lại mỗi rerun).

Tiêu chí hoàn thành M6 (chạy trong thư mục gốc repo):
1. `uv run pytest -q` pass toàn bộ; `uv run ruff check src tests` sạch; coverage `app.py` ≥ 85 % (`uv run pytest --cov=loc_counter --cov-report=term-missing`).
2. `uv run pytest tests/test_app_input.py tests/test_app_result.py tests/test_app_identity.py -q` pass, gồm E2E AppTest trên repo §14: tất cả 10/20, alice 10/13, bob 10/17, alice+bob có xuất riêng 10/20 với 3 zip end; alice `5/2/+3`, bob `8/1/+7`.
3. "Tải được mọi file": với mỗi E2E, tập tên file của `download_items(result)` = `os.listdir(out_dir)`, bytes khớp, AppTest có đủ nút tải tương ứng (không disabled).
4. Token (ô password) không có trong cây phần tử AppTest, `run.log`, thư mục kết quả, cache repo, `github_logins.json`.
5. Kiểm tra khói: `uv run streamlit run src/loc_counter/app.py --server.headless true --server.port 8599` chạy nền, `GET /_stcore/health` trả `ok`.
6. Kiểm tra tay (ghi test-report): mở trình duyệt, chạy luồng §14, bấm thật từng nút tải.

Việc không cần spec: README mục chạy UI (mặc định `./output`, `./identities.yaml`, nạp config tùy chọn; khóa `out_root` chỉ trong một tiến trình; không fetch lại khi bấm Phân tích; gợi ý `--browser.gatherUsageStats false`); fixture `app_test` + `AnalysisResult` thật trong `tests/conftest.py`; `mandatory-tests.md` mục F (M6).

### M7 — Hiệu năng
Cập nhật spec `classifier`, `git_repo`, `counter`, `attribution`, `pipeline` (mục 8 "Hiệu năng") trước khi tối ưu: cache blob SHA, `git cat-file --batch`, `ProcessPoolExecutor`.
Ghi chú từ review M3 (N6): `GitHubLoginResolver._save_cache` ghi lại cả file sau mỗi lần tra (O(n²)); email noreply vẫn gọi API dù suy ra được login; `requests.Session` không được đóng; `plan_export` đọc trọn blob lớn để kiểm binary.
Tiêu chí: repo ~5.000 file, 2.000 commit trong kỳ < 5 phút trên máy 8 nhân (cần người dùng cung cấp repo đo).

## 3. Câu hỏi mở
Cần người dùng trả lời trước khi viết spec của milestone tương ứng (spec gốc yêu cầu dừng lại hỏi khi mơ hồ).

| # | Câu hỏi | Mục | Ảnh hưởng | Đề xuất | Trạng thái |
|---|---|---|---|---|---|
| Q1 | **File không phải code nhưng có lexer.** §6.2 coi mọi file có lexer Pygments là source. Đã kiểm: `.txt` → "Text only", `.md`, `.json`, `.yaml`, `.xml`, `.ini`, `.rst` đều có lexer → mọi dòng không trống sẽ bị tính là code. Có loại trừ không? | §6.2, §9 | M1 · BLOCKING | Thêm `exclude_languages` mặc định `[Text only, Markdown, reStructuredText]`, giữ JSON/YAML/XML; cấu hình được | Đã chốt → D3 |
| Q2 | **Bot trong danh sách user.** §3.5 nói bot "bị loại trừ khỏi danh sách user", §16 nói "Hiện trong danh sách; tùy chọn loại trừ". | §3.5, §16 | M3 · BLOCKING | Theo §16: hiện trong danh sách, có gắn nhãn bot; tùy chọn "Loại trừ bot" ẩn đi | Đã chốt → D14 |
| Q3 | **"Tất cả user" + "Loại trừ bot"**: export end là toàn bộ C_END (§3.3) hay C_START + thay đổi của mọi user không phải bot? | §3.3, §3.5 | M4 · BLOCKING | Coi như "chọn mọi user không phải bot" → dựng bằng builder | Đã chốt → D21 |
| Q4 | **JSDoc / Javadoc với `count_docstrings=true`.** Pygments trả `/** */` là `Comment.Multiline` → theo thuật toán §6.2 luôn không tính, dù §3.4 nói JSDoc "theo cấu hình". | §3.4, §6.2 | M1 | Giữ đúng thuật toán §6.2 (JSDoc luôn không tính), ghi rõ trong README | Đã chốt → D4 |
| Q5 | **Dòng được di chuyển/copy từ file khác** (blame `-M -C` trả commit cũ/boundary) nhưng diff coi là dòng thêm trong file mới: không gán cho ai → export theo user thiếu dòng, còn reverse blame vẫn gán phần xóa ở file cũ cho người di chuyển. | §7.2, §7.3 | M4 · BLOCKING | Dòng thêm có blame boundary → gán cho author của commit đưa dòng vào file này (blame không `-C` cho riêng dòng đó); ghi cảnh báo | Đã chốt → D22 (gộp Q21) |
| Q6 | **Sheet `Theo_tuan` / biểu đồ theo tuần**: tuần ISO (bắt đầu thứ Hai) theo múi giờ đã chọn? Ngày tính theo author date hay committer date của commit được gán dòng? | §10.3, §12 | M5 | Tuần ISO, theo author date, múi giờ đã chọn | Đã chốt → D35 |
| Q7 | **Tiêu chí M1 so với `cloc`**: máy hiện chưa cài `cloc`. Cài (winget/scoop/npm) hay chấp nhận bỏ tiêu chí này? | §13 | M1 | Cài `cloc` qua npm (`npx cloc`) chỉ dùng khi test thủ công | Đã chốt → D5 |
| Q8 | **Số commit hiển thị ở danh sách user (UI)** có loại merge commit như §8.2 không? | §8.2, §10.2 | M3 | Có, dùng cùng định nghĩa §8.2 | Đã chốt → D15 |
| Q9 | **Định dạng `<start>_<end>` trong tên thư mục kết quả**: chỉ ngày `YYYY-MM-DD`? | §12 | M5 | `YYYY-MM-DD`; thêm `THHMM` khi người dùng nhập giờ | Đã chốt → D40 (N10) |
| Q10 | **Chỉ thị tiền xử lý** (`#include`, `#region`…) là `Comment.Preproc` → theo §6.2 không tính code (phát hiện khi review M1) | §3.4, §6.2 | M1 | Tính là code | Đã chốt → D7 |
| Q11 | **Định nghĩa dòng**: `splitlines()` (§6.2.4) khác cách git đếm dòng (`\n`) → lệch chỉ số khi ghép blame/diff ở M4 | §6.2, §7 | M1, M4 | Dòng theo git | Đã chốt → D8 |
| Q12 | **Giây của giờ người dùng nhập.** §3.1 chỉ nói "không nhập giờ → end = 23:59:59". Khi nhập `--end-time 17:30` thì end là `17:30:00` hay `17:30:59`? (UI mặc định hiển thị `23:59`) | §3.1, §10.2 | M2 · BLOCKING | start `HH:MM:00`, end `HH:MM:59` (bao trọn phút đã nhập; `23:59` ≡ không nhập giờ) | Đã chốt → D10 |
| Q13 | **Ngày trong tên zip** `start_<YYYY-MM-DD>_<shortsha>.zip`, `end_<YYYY-MM-DD>_<user-tag>.zip`: ngày người dùng nhập hay ngày của commit snapshot? Tên zip start khi C_START rỗng? | §12 | M2 · BLOCKING | Ngày người dùng nhập (theo múi giờ đã chọn); C_START rỗng → `start_<date>_empty.zip` (zip không có file) | Đã chốt → D11 |
| Q14 | **Repo local**: §10.2 "clone bare vào thư mục cache" — áp dụng cả cho đường dẫn local, hay đọc trực tiếp repo local? | §2, §10.2 | M2 · BLOCKING | Clone bare vào cache cho cả local (git dùng hardlink nên nhanh; không đụng repo của người dùng; cùng một luồng xử lý). Nhánh = nhánh local (`refs/heads`) của repo nguồn | Đã chốt → D12 |
| Q15 | **File vượt `max_file_size_kb` và file non-source ở `export_mode: full`**: có đưa vào zip không? §9 nói bộ lọc "áp dụng cho cả export và đếm", nhưng `full` = "export mọi file" | §9 | M2 · BLOCKING | `source_only`: chỉ file source, bỏ file quá lớn (cảnh báo). `full`: mọi file qua bộ lọc thư mục/glob/test, kể cả quá lớn và non-source (binary theo `exclude_binary`); chỉ đếm file source không quá lớn | Đã chốt → D13 |
| Q16 | **Định dạng `identities.yaml`** — spec gốc chỉ nói "bảng ánh xạ thủ công" sửa được trong UI (tên, email, account key) | §3.5, §10.2 | M3 · BLOCKING | List `identities: [{email, account}, {name, account}]`; khớp email không phân biệt hoa thường, khớp tên khi không có mục theo email; áp cho identity gốc rồi identity sau `.mailmap` | Đã chốt → D16 |
| Q17 | **`.mailmap` ở phiên bản nào** (nhánh/commit nào) và kết quả `.mailmap` thành account key ra sao? | §3.5 | M3 · BLOCKING | `.mailmap` tại C_END; identity được `.mailmap` đổi → key = email chuẩn (áp quy tắc noreply, chữ thường), không gọi GitHub API | Đã chốt → D17 |
| Q18 | **GitHub API**: lưu cache ở đâu, lỗi mạng / hết quota xử lý thế nào? | §3.5 | M3 | Chỉ khi nguồn là `https://github.com/<owner>/<repo>` và có token; 1 request / email chưa xác định; lỗi → dùng email + cảnh báo; 403/429 hết quota → ngừng gọi; cache `~/.loc_counter/github_logins.json` (email → login hoặc null), không chứa token | Đã chốt → D18 |
| Q19 | **Hoa thường của account key; nhận diện bot theo gì?** | §3.5 | M3 | Key tự sinh (email, login noreply, login API) chữ thường; key trong `identities.yaml` giữ nguyên. Bot: tên hoặc email của bất kỳ identity nào (hoặc key) chứa `[bot]`, `dependabot`, `renovate`, `github-actions` (không phân biệt hoa thường) | Đã chốt → D19 |
| Q20 | **Dòng xóa bị gán cho người merge.** Đã tái hiện: bob xóa `v2` trên nhánh feature, alice sửa `v7` trên main, carol merge không xung đột → theo đúng §7.2 (`ancestry-path` từ L) cả hai dòng xóa thành của carol; mâu thuẫn §16 (merge chỉ nhận dòng giải quyết xung đột) | §7.2, §16 | M4 · BLOCKING | Khi ứng viên là merge M: reverse blame riêng dòng đó tới từng parent; dòng vắng ở parent nào thì tìm commit xóa bên nhánh đó (đệ quy). Chỉ gán cho M khi dòng còn ở mọi parent | Đã chốt → D23 |
| Q21 | **Mở rộng Q5 — dòng bị dời** (trong file ≥ 20 ký tự, sang file khác ≥ 40 ký tự): blame xuôi `-M -C` trả boundary nhưng reverse blame (không `-M -C`) báo đã xóa → dòng **mất khỏi mọi export dựng bằng builder**, lệch §8.3 | §7.2, §7.3 | M4 · BLOCKING | Dòng mới trong hunk là boundary với `-w -M -C` nhưng không boundary với `-w` → gán theo lần blame thứ hai (người dời) + cảnh báo `MOVED_LINES`; vẫn boundary với `-w` = chỉ đổi khoảng trắng/EOL → bỏ dòng mới, giữ dòng cũ, không cảnh báo | Đã chốt → D22 |
| Q22 | **Thuật toán diff §7.3**: `difflib` hay `git diff`? Diff và blame không khớp thì sao? | §4, §7.3 | M4 · BLOCKING | `git diff-tree -p -U0` (Myers, cùng xdiff với blame; số dòng theo D8). Chỉ tra blame cho dòng trong hunk; dòng ngoài hunk luôn giữ; dòng mới không có tác giả → bỏ (cảnh báo); dòng cũ reverse blame báo còn sống → giữ | Đã chốt → D24 |
| Q23 | **"Người đổi tên" là ai** (chuỗi a→b→c, rename trong merge, xóa + thêm ở 2 commit)? Tên mới bị bộ lọc loại? | §7.4 | M4 · BLOCKING | Author của commit tạo **đường dẫn cuối** (merge → author merge); áp bộ lọc §9 lên tên được chọn; không tìm được → tên cũ + cảnh báo | Đã chốt → D25 |
| Q24 | Rename kèm sửa nhiều (độ giống < 50%) → git coi là xóa + thêm; vượt `diff.renameLimit` → bỏ nhận diện rename | §7.4, §14 | M4 | Giữ ngưỡng mặc định của `-M`, đặt rename limit lớn tường minh, cảnh báo khi git báo vượt giới hạn | Đã chốt → D27 |
| Q25 | **Phát hiện "dòng bị nhiều user sửa liên tiếp"**: trường `previous` của porcelain không dùng được | §7.5, §16 | M4 · BLOCKING (phần cảnh báo) | M4: heuristic — dòng base bị user D xóa, hunk có dòng mới của user khác → cảnh báo. Cách chính xác (diff từng commit + blame) để M7 | Đã chốt → D26 |
| Q26 | File bị alice xóa rồi bob tạo lại cùng tên → diff ra `M`, export của alice vẫn còn file (chỉ dòng chung) | §7.4 | M4 | Giữ quy tắc theo dòng, ghi giả định | Đã chốt → D27 |
| Q27 | `export_mode: full`: file binary / quá lớn / đổi kiểu symlink↔file dựng thế nào | §7.4, §9, D13 | M4 | Text (≤ giới hạn) → theo dòng; binary/quá lớn → theo cả file (commit cuối chạm file trong kỳ là của user chọn → bản C_END, ngược lại bản C_START); symlink/submodule bỏ như snapshot | Đã chốt → D27 |
| Q28 | **Dòng cuối không có newline**: base `c = 3` (không EOL), bob thêm EOL, alice thêm `d = 4` → export alice thành `c = 3d = 4` | §7.3, §15 | M4 | Dòng phát ra thiếu EOL mà không phải dòng cuối → thêm EOL chiếm đa số của file + cảnh báo `MISSING_EOL` | Đã chốt → D27 |
| Q29 | `user-tag` / tên zip: `safe_name` làm trùng hoặc hỏng tên (Unicode, `a.b`/`a_b`); "Xuất riêng" + 1 user; "Tất cả user" + "Xuất riêng" | §3.3, §12 | M4 | Vẫn có bản gộp; thêm hậu tố `-<sha1(account)[:6]>` khi `safe_name` đổi chuỗi hoặc trùng; 1 user → một file; "Tất cả" + "Xuất riêng" → mỗi account trong kỳ một zip | Đã chốt → D27 |
| Q30 | Tiêu chí M4 = toàn bộ §14, gồm `added_code`/`deleted_code` (§8.2 đặt ở M5) | §13, §8.2 | M4 | `added_code`/`deleted_code` tính trong `attribution` (M4); `commits`/`files_changed` ở M5; test M4 đếm LOC trên nội dung export | Đã chốt → D27 |
| Q31 | File 0 byte do user tạo; đổi mode 644↔755; file không đổi nhưng rỗng | §7.4 | M4 | File không đổi → luôn giữ; file mới 0 byte → bỏ; mode lấy của C_START nếu đã có, ngược lại của C_END | Đã chốt → D27 |
| Q32 | "Hunk nhiều user" và thứ tự dòng: §7.3 đặt dòng cũ trước dòng mới → hunk `a→A` (alice), `b→B` (bob), export alice ra `[b, A]` | §7.3, §7.5 | M4 | Làm đúng §7.3; hunk nhiều user = ≥ 2 account trong dòng cũ bị xóa + dòng mới → cảnh báo kèm khoảng dòng và account | Đã chốt → D27 |
| Q33 | `paths_exist` trả `True` cho mọi entry trong cây, kể cả **thư mục** (review M4 r2). `attribution` §7.4 có thể gặp file bị thay bằng thư mục cùng tên: "tồn tại" nghĩa là entry bất kỳ hay chỉ blob + gitlink? | §7.4 | M4 (spec `attribution`) | Giữ `paths_exist` như hiện tại; `attribution` dùng mode từ `diff_tree`/`list_tree` khi cần phân biệt | Đã chốt → D31 |
| Q34 | **Thứ tự ổn định của cảnh báo** (review counter-snapshot): sắp `(path, kind)` chưa xác định thứ tự giữa nhiều cảnh báo cùng file + cùng loại (`MULTI_USER_HUNK`, `UNATTRIBUTED`…) | §15 (tái lập) | M4 (spec `attribution`, `builder`), M5 (`report`) | Module phát cảnh báo theo thứ tự xác định (theo số dòng tăng dần); `pipeline`/`report` M5 sắp `(path, kind, message)` | Đã chốt → D31 |
| Q35 | **Dời khối trong cùng file** (phân tích `attribution`, kiểm chứng git 2.55): blame xuôi, reverse blame và diff cả kỳ không đối xứng → khối bị nhân đôi (dòng cũ "còn sống" + dòng mới gán theo D22) hoặc mất (dòng mới boundary sau 2 lần blame + dòng cũ bị gán xóa) → bản "mọi user" khác C_END, lệch §8.3 | §7.2, §7.3, §8.3 | M4 · BLOCKING | Ghép theo nội dung trong file (chuẩn hóa như `-w`) + `MOVED_LINES` | Đã chốt → D28 |
| Q36 | D23 cần merge-base / quan hệ tổ tiên (reverse blame tới commit không phải hậu duệ của `since` không báo lỗi mà trả mọi dòng boundary) | §7.2 | M4 | Thêm `is_ancestor`, `merge_bases` vào `git_repo` | Đã chốt → D29 |
| Q37 | D25 khi đổi tên đi qua merge: người đổi tên là người merge hay người thật sự tạo đường dẫn? | §7.4 | M4 | Người thật sự tạo đường dẫn (path vắng ở mọi parent); merge chỉ tính khi tự tạo | Đã chốt → D30 |
| Q38 | **Xung đột file/thư mục trong export theo user** (phân tích `builder`): alice xóa `x`, bob tạo `x/z.py` → export bob có cả `x` (giữ như start) lẫn `x/z.py`; tương tự rename. Zip ghi được nhưng giải nén hỏng | §7.4, §3.4, F9 | M4 · BLOCKING | Giữ cả hai + cảnh báo `PATH_CONFLICT` (gồm đường dẫn chỉ khác hoa thường); M5 đếm từ nội dung, không giải nén | Đã chốt → D32 |
| Q39 | Các điểm nhỏ của `builder` (N1–N10): mode khi `whole`/`T`; file `D` 0 byte; rename giữa hai file rỗng; M/R dựng ra rỗng; EOL đa số khi hòa; BOM giữa file; cảnh báo lọc; `user_tag` trùng không phân biệt hoa thường; tên được chọn bị bộ lọc loại; "Tất cả" không loại bot | §7.3, §7.4, §12 | M4 | Theo đề xuất của phân tích `builder` (ghi trong spec `builder` mục 10) | Đã chốt → D33 |
| Q40 | **`Theo_tuan` cần commit của từng dòng** (phân tích M5, N1): `attribution` chỉ lưu account cho dòng thêm/xóa, không lưu commit → không chia code ròng theo tuần (§10.3, §12) | §10.3, §12 | M5 · BLOCKING | `attribution` thêm `added_commit`/`deleted_commit` (sha); tuần ISO theo author date của commit đó, múi giờ đã chọn (gộp Q6) | Đã chốt → D35 |
| Q41 | **"Đếm trên chính thư mục export" (§3.4) với F9**: giải nén trên Windows làm hỏng/đè file (hoa thường, `a.py.`, `CON`, `<>?*`) | §3.4, F9 | M5 · BLOCKING | Đếm từ chính danh sách entry ghi vào zip (cùng byte với file người dùng tải), không giải nén | Đã chốt → D36 |
| Q42 | **Import vòng**: §8.2/§8.3 trong `counter.py` cần kiểu của `attribution`/`identity`, trong khi hai module đó import `counter` | §5, §8 | M5 · BLOCKING (thiết kế) | Giữ §8.2/§8.3 trong `counter.py` (đúng §5); chỉ import kiểu dưới `TYPE_CHECKING`, nhận dữ liệu qua tham số | Đã chốt → D37 |
| Q43 | **`diff_percent`** (§12): mẫu số, đơn vị, `loc_end = 0` | §8.3, §12 | M5 | Phần trăm: `abs(expected − loc_end) / loc_end × 100`, so `> 0.5` trên giá trị chưa làm tròn, ghi làm tròn 3 chữ số; `loc_end = 0` → 0.0 nếu `expected = 0`, ngược lại 100.0 | Đã chốt → D38 |
| Q44 | Tên file không hợp lệ trên Windows (`CON`, `NUL.py`, `a.py.`, `<>"\|?*`) trong export (F9, N11) | F9, §15 | M5 | Thêm `WarningKind.WINDOWS_PATH` (chỉ cảnh báo, vẫn giữ file); thêm `CROSS_CHECK`, `IDENTITY` (cảnh báo GitHub API) | Đã chốt → D39 |
| Q45 | Các điểm nhỏ M5 (N4–N23 của phân tích `spec-analyst`): kích thước ở `full`, lệch hệ thống kiểm tra chéo, `files_changed`, cột `warnings.csv`, tên thư mục, `run.log`, thư mục đã tồn tại, tái lập xlsx, manifest, tiến độ, xuất riêng, dòng Tổng, `--user`, CSV, `Theo_file`, mã thoát, rủi ro xlsx/CSV | §8, §11, §12, §15 | M5 | Theo đề xuất (tóm tắt ở D40) | Đã chốt → D40 |
| Q46 | **`run.log` khi nhiều phiên cùng `out_root`** (review `pipeline` 2026-10-25): `<out>/run.log` tên cố định, mở `mode="w"` → hai phiên Streamlit cùng thư mục đầu ra ghi đè lẫn nhau (mất dòng, byte NUL) | §15, D40-N12 | M6 (spec `screen-*`) | Khóa `out_root` theo phiên (lỗi "Thư mục đầu ra đang được dùng bởi phiên khác") hoặc tên log theo phiên; M5 (CLI) chấp nhận, ghi README (spec `pipeline` A20) | Đã chốt → D41-N3 |
| Q47 | **Tên múi giờ khác hoa thường** (review `screen-input` r2): trên Windows `zoneinfo` (tzdata tra file không phân biệt hoa thường) chấp nhận `singapore`, `utc` — `config_from_dict` / `make_period` giữ nguyên tên nhập, UI quy về tên chuẩn (`canonical_timezone`, spec `screen-input` A14). Số liệu như nhau nhưng `Period.timezone`, manifest, log khác giữa CLI và UI | §3.1, §15 (tái lập) | M7 (không blocking) | Chuẩn hóa trong `config`/`snapshot` (tên chuẩn của `available_timezones()`, khớp casefold duy nhất) khi cập nhật spec ở M7 | Mở |
| Q48 | **Quy tắc gộp trên email / tên đã qua `.mailmap`** (review `screen-identity` r2): bảng gộp account hiển thị (tên, email) **gốc** của author; `AccountResolver` tra `identities.yaml` theo cả email gốc lẫn email sau `.mailmap`, nên quy tắc ghi theo email gốc vẫn áp dụng — nhưng nếu repo có `.mailmap` gộp nhiều email, người dùng có thể muốn một quy tắc cho email canonical | §3.5 | M7 / sau MVP (không blocking) | Giữ như hiện tại (quy tắc theo email gốc, đã đủ để gộp); cân nhắc thêm cột "Email sau .mailmap" khi có nhu cầu | Mở |

## 4. Quyết định đã chốt
| # | Quyết định | Ngày |
|---|---|---|
| D1 | Code đặt trong `Countloc/` (không tạo thêm thư mục `loc-counter/`); package `loc-counter`, module `loc_counter` | 2026-10-22 |
| D2 | Dev dependency bổ sung: `pytest-cov`, `ruff`; runtime bổ sung `tzdata` (Windows không có dữ liệu múi giờ cho `zoneinfo`) | 2026-10-22 |
| D3 | Q1: thêm cấu hình `exclude_languages`, mặc định `["Text only", "Markdown", "reStructuredText"]` (tên lexer Pygments); JSON/YAML/XML vẫn đếm | 2026-10-22 |
| D4 | Q4: giữ đúng thuật toán §6.2 — JSDoc/Javadoc (`Comment.*`) luôn không tính; `count_docstrings` chỉ ảnh hưởng `String.Doc`. Ghi rõ trong README | 2026-10-22 |
| D5 | Q7: kiểm tiêu chí cloc của M1 bằng `npx cloc` (không cài vĩnh viễn) | 2026-10-22 |
| D7 | Q10: `Comment.Preproc`, `Comment.PreprocFile` (`#include`, `#define`, `#region`, `#if`…) **là code** — ngoại lệ của bước §6.2.3. `Comment.Hashbang` (`#!`) vẫn không tính | 2026-10-22 |
| D8 | Q11: định nghĩa dòng theo git — tách theo `\n`, bỏ `\r` cuối dòng; `\f`, `\x85`, `\u2028`, `\r` đơn là ký tự trong dòng. Thay cho `len(content.splitlines())` ở §6.2.4 | 2026-10-22 |
| D9 | Tiêu chí cloc M1 chấp nhận đạt: Python +3,15% do cloc coi mọi chuỗi triple-quote là comment (bỏ các dòng đó còn −0,30%); JS/CSS 0%, HTML −0,61% (xem test-reports/M1-20261022.md) | 2026-10-22 |
| D6 | Khởi tạo git repo trong `Countloc/`; Claude không tự commit khi chưa được yêu cầu | 2026-10-22 |
| D10 | Q12: giờ nhập dạng `HH:MM`; start → `HH:MM:00`, end → `HH:MM:59`. Không nhập giờ → `00:00:00` / `23:59:59` (§3.1) | 2026-10-23 (*) |
| D11 | Q13: ngày trong tên zip = ngày người dùng nhập (múi giờ đã chọn); C_START rỗng → `start_<date>_empty.zip` không chứa file | 2026-10-23 (*) |
| D12 | Q14: repo local cũng clone bare vào cache (`git clone --bare`; từ M3 thêm `--no-hardlinks` theo D20); nhánh = `refs/heads` của repo nguồn; mỗi lần mở thì fetch lại | 2026-10-23 (*) |
| D13 | Q15: `source_only` — chỉ file source (có lexer, không thuộc `exclude_languages`, không binary), bỏ file quá lớn + cảnh báo. `full` — mọi file qua bộ lọc thư mục/glob/test (binary theo `exclude_binary`, file quá lớn vẫn export); chỉ đếm file source không quá lớn | 2026-10-23 (*) |
| D14 | Q2: bot **hiện** trong danh sách user, gắn nhãn bot; tùy chọn "Loại trừ bot" (`--exclude-bots`) ẩn chúng (§16) | 2026-10-23 (*) |
| D15 | Q8: số commit của user = commit **không phải merge** trong `C_START..C_END` (§8.2); danh sách user gồm mọi account có commit trong kỳ, kể cả chỉ có merge commit (commit = 0) | 2026-10-23 (*) |
| D16 | Q16: `identities.yaml` = `identities:` list mục `{email, account}` hoặc `{name, account}` (xem `identities.example.yaml`). Tra quy tắc: email gốc → email sau `.mailmap` → tên gốc → tên sau `.mailmap` (email luôn thắng tên). `email: ''`/`name: ''` coi như không có; `identities:` để trống = danh sách rỗng | 2026-10-23 (*) |
| D17 | Q17: `.mailmap` tại C_END của nhánh phân tích; `mailmap.file` toàn cục bị tắt | 2026-10-23 (*) |
| D18 | Q18: GitHub API theo đề xuất Q18 | 2026-10-23 (*) |
| D19 | Q19: theo đề xuất Q19 | 2026-10-23 (*) |
| D20 | Tồn đọng review M2 F1–F7 làm theo đề xuất (F2: clone local `--no-hardlinks`) trong bản cập nhật spec `git_repo`, `snapshot` của M3 | 2026-10-23 (*) |
| D21 | Q3: "Tất cả user" + "Loại trừ bot" → dựng bằng builder với mọi account không phải bot; không có bot nào có commit trong kỳ → dùng thẳng C_END. `user-tag` vẫn là `all`; bot không hiện trong bảng theo user | 2026-10-23 |
| D22 | Q5/Q21: dòng mới trong hunk là boundary với `blame -w -M -C` nhưng không boundary với `blame -w` → gán theo lần blame thứ hai (người dời) + cảnh báo `MOVED_LINES`; vẫn boundary với `-w` (chỉ đổi khoảng trắng/EOL) → bỏ dòng mới, giữ dòng cũ, không cảnh báo | 2026-10-23 |
| D23 | Q20: commit xóa ứng viên là merge M → reverse blame riêng dòng đó tới từng parent, dòng vắng ở parent nào thì tìm commit xóa bên nhánh đó (đệ quy); chỉ gán cho M khi dòng còn ở mọi parent (giải quyết xung đột, §16) | 2026-10-23 |
| D24 | Q22: hunk §7.3 lấy từ `git diff-tree -p -U0` (Myers tường minh). Chỉ tra blame cho dòng trong hunk; dòng ngoài hunk luôn giữ; dòng mới không có tác giả → bỏ + cảnh báo; dòng cũ reverse blame báo còn sống → giữ | 2026-10-23 |
| D25 | Q23: người đổi tên = author của commit tạo đường dẫn cuối tại C_END (merge → author merge); bộ lọc §9 áp lên tên được chọn; không xác định được → tên cũ + cảnh báo | 2026-10-23 |
| D26 | Q25: M4 dùng heuristic (dòng base bị user D xóa, hunk có dòng mới của user khác → cảnh báo `SEQUENTIAL_EDIT`); phát hiện chính xác (diff từng commit + blame) để M7 | 2026-10-23 |
| D27 | Q24, Q26–Q32: theo đề xuất trong bảng câu hỏi mở | 2026-10-23 |
| D28 | Q35: trong một file (cả hai phía, theo dòng), sau bước blame: (0) dòng mới chưa có tác giả ghép 1–1 trước với dòng cũ còn sống cùng nội dung (cặp chỉ đổi khoảng trắng, không gán — sửa theo review attribution); (a) dòng mới trong hunk chưa có tác giả được ghép 1–1 với dòng cũ trong hunk đã có người xóa, cùng nội dung sau khi bỏ mọi khoảng trắng → nhận account người xóa; (b) dòng cũ trong hunk "còn sống" ghép 1–1 với dòng mới đã gán theo D22, cùng nội dung → `deleted_by` = account của dòng mới. Ghép theo thứ tự dòng tăng dần; có cảnh báo `MOVED_LINES` | 2026-10-23 |
| D29 | Q36: thêm `GitRepo.is_ancestor(a, b)` (`git merge-base --is-ancestor`) và `GitRepo.merge_bases(a, b)` (`git merge-base --all`) — cập nhật spec `git_repo` | 2026-10-23 |
| D30 | Q37: người đổi tên = author của commit **thật sự tạo** đường dẫn cuối (path vắng ở mọi parent), lần tạo gần nhất trong kỳ; merge chỉ được tính khi chính nó tạo path | 2026-10-23 |
| D31 | Q33: giữ `paths_exist` (thư mục trùng tên → không xác định người đổi tên → `RENAME_UNRESOLVED`, dùng tên cũ). Q34: cảnh báo phát theo thứ tự xác định (file theo `diff_tree`, rồi loại, rồi dòng tăng dần), M5 sắp ổn định theo `(path, kind)`. Dòng cũ không tìm được commit xóa → giữ + `UNATTRIBUTED`; rename: mỗi phía áp bộ lọc §9 theo tên của phía đó; phát cả `SEQUENTIAL_EDIT` và `MULTI_USER_HUNK`; status `T` → xử lý cả file theo người chạm cuối | 2026-10-23 |
| D32 | Q38: export theo user giữ mọi file kể cả khi đường dẫn xung đột (file `x` và thư mục `x/`, hoặc chỉ khác hoa thường) + cảnh báo `PATH_CONFLICT` (thêm vào `WarningKind`, spec `counter`); M5 đếm LOC từ nội dung zip/blob, không giải nén (một phần F9) | 2026-10-23 (*) |
| D33 | Q39: theo đề xuất N1–N10 của phân tích `builder` (spec `builder` A1–A10) | 2026-10-23 (*) |
| D34 | File bị user A sửa rồi user B xóa hết: dựng theo dòng §7.3 (như Q26/D27) — khớp §8.2/§8.3, không theo nghĩa đen §7.4 (spec `builder` A12) | 2026-10-23 (*) |
| D35 | Q6/Q40: `attribution` lưu thêm sha commit của mỗi dòng thêm/xóa. `Theo_tuan`: tuần ISO (thứ Hai, nhãn `YYYY-Www`) theo **author date** của commit, quy về múi giờ đã chọn; bảng dạng dài (tuần, account, commits, added_code, deleted_code, net_code), chỉ có dòng khác 0; commits theo tuần = commit không phải merge; tuần ngoài kỳ (nhánh tách sớm) vẫn giữ; không có commit → sheet chỉ có tiêu đề | 2026-10-23 (*) |
| D36 | Q41 (F9): LOC của mọi bản export đếm từ **chính nội dung các entry ghi vào zip** (blob hoặc bytes dựng bởi builder), dùng `language` của plan/builder + quy tắc kích thước D13 — tương đương "đếm trên thư mục export" mà không giải nén. Test xác nhận bằng nhau với đọc lại zip và `count_directory` trên thư mục giải nén | 2026-10-23 (*) |
| D37 | Q42: §8.1–§8.3 nằm trong `counter.py`; `counter` không import `attribution`/`identity`/`builder` lúc chạy (chỉ dưới `TYPE_CHECKING`) | 2026-10-23 (*) |
| D38 | Q43: `diff_percent` theo đề xuất Q43; manifest `cross_check` ghi thêm `loc_end`, `sum_net_code`, `threshold_percent` (0.5), `ok` | 2026-10-23 (*) |
| D39 | Q44: thêm `WarningKind.CROSS_CHECK`, `IDENTITY`, `WINDOWS_PATH` (spec `counter`); `WINDOWS_PATH` chỉ cảnh báo, file vẫn được export và đếm | 2026-10-23 (*) |
| D40 | Q9/Q45 — theo đề xuất của phân tích M5: **N4** `full` + file source quá lớn: không đếm, không cảnh báo lại. **N6** lệch hệ thống kiểm tra chéo (đổi tên non-source→source, vào thư mục bị loại, file↔symlink, binary↔text, vượt ngưỡng kích thước) giữ đúng §8.2/§8.3, chỉ cảnh báo + README. **N7** `files_changed` = số đường dẫn `FileAttribution` mà account có dòng thêm/xóa hoặc là `renamed_by`, có ít nhất một phía là source được đếm; loại file xử lý `whole`/`skip`; rename thuần = 1 file. **N8** `warnings.csv` cột `Loại`, `Đường dẫn`, `Nội dung`, `Phạm vi` (`start`, `end:<tag>`, `gán tác giả`, `kiểm tra chéo`, `định danh`; gộp phạm vi khi trùng `(kind, path, message)`), sắp ổn định `(path, kind)`. **N10/Q9** thư mục `<repo>_<branch>_<start>_<end>_<user-tag>`: ngày `YYYY-MM-DD`, thêm `THHMM` khi nhập giờ; `<repo>` = `safe_name` phần cuối nguồn (bỏ `.git`, áp cho URL https, scp, `file://`, đường dẫn Windows); `<repo>`/`<branch>` dài > 40 ký tự → cắt + `-<sha1[:6]>`; user-tag của export gộp/`all`. **N12** `run.log` tại `<out>/run.log`, ghi đè mỗi lần chạy, UTF-8, gỡ handler trong `finally`. **N13** dựng trong thư mục tạm rồi thay thế; chỉ xóa thư mục cũ có `manifest.json` của tool, ngược lại báo lỗi tiếng Việt. **N14** tái lập: `generated_at` chỉ ở manifest; xlsx chuẩn hóa (entry zip + `docProps/core.xml`) theo committer date C_END. **N15** manifest: thứ tự key như §12, `users` = account đã tính (sắp tăng dần), `c_start` null khi rỗng, `config = config_to_dict`, thêm `options` và `exports[]`, `indent=2`, `ensure_ascii=False`. **N16** tiến độ theo thứ tự thực: export start → gán tác giả → export end → đếm LOC → báo cáo. **N17** xuất riêng: số liệu chính theo export gộp/`all`; mỗi zip riêng có `loc_end` + kiểm tra chéo riêng trong `exports[]`. **N18** dòng Tổng ở xlsx/UI, không ở CSV; sắp commit giảm dần rồi account. **N19** `--user` khớp chính xác, rồi `casefold` nếu duy nhất; không khớp → lỗi liệt kê user trong kỳ; chọn tường minh thắng `--exclude-bots`. **N20** CSV bằng module `csv`: `utf-8-sig`, `,`, `\r\n`, số nguyên thô, tên cột tiếng Việt như xlsx. **N21** `Theo_file` khóa theo đường dẫn export end + cột "Đổi tên từ"; ngôn ngữ phía end, không có thì phía start. **N22** mã thoát 0 (kể cả có cảnh báo/lệch), 1 `LocCounterError`, 2 sai cú pháp; stdout bảng theo §10.3; `--json` tùy chọn. **R** xlsx: ô văn bản đặt kiểu chuỗi (không thành công thức), lọc ký tự điều khiển, cắt ô > 32.767 ký tự; CSV: thêm tiền tố `'` cho ô văn bản bắt đầu `= + - @` | 2026-10-23 (*) |
| D41 | M6 — theo khuyến nghị phân tích `spec-analyst` 2026-10-25: **N1** 3 spec chung `app.py`, hàm thuần + `main()`, trạng thái chung qua `st.cache_resource`. **N2** ô "Thư mục đầu ra" mặc định `./output` (CWD), `expanduser().resolve()` lúc chạy. **N3/Q46** khóa trong tiến trình theo `out_root` đã resolve, không chờ: bận → "Thư mục đầu ra <p> đang được một phiên phân tích khác sử dụng; hãy chờ hoặc chọn thư mục khác." (CLI song song tiến trình khác: README). **N4** khóa theo `cache_dir_for(source)` khi "Tải repo" (có chờ + spinner). **N5** ô đường dẫn `identities.yaml` mặc định `./identities.yaml`; chưa có → rỗng, lưu lần đầu tạo file; hỏng → lỗi + chặn Phân tích. **N6** mỗi hàng = một `Identity` trong kỳ; chỉ hàng đổi giá trị được ghi (upsert quy tắc `{email, account}` theo email chữ thường; email rỗng → `{name, account}`); ô rỗng → xóa quy tắc; quy tắc ngoài kỳ giữ nguyên; sau lưu nạp lại map, resolver mới, tính lại kỳ. **N7** tùy chọn nâng cao = 8 trường `FilterConfig` (mặc định §9) + ô đường dẫn config + nút "Nạp" điền widget; validate qua `config_from_dict`. **N8** tiến độ theo thứ tự thực (`STEP_LABELS`), `st.progress`. **N9** memo `PeriodContext` + resolver trong `session_state` theo khóa `(repo_gen, branch, Period, IdentityMap, github_on)`; không dùng `st.cache_data`; token không vào khóa. **N10** ngày mặc định theo múi giờ đang chọn khi mở phiên (start = ngày 1 tháng hiện tại, end = hôm nay); giờ `time_input(value=None, step=60)`; `min_value=1970-01-01`. **N11** múi giờ `sorted(available_timezones())`, nhãn kèm UTC±hh:mm. **N12** khóa ô nhập: `on_click` đặt `running`, rerun vẽ widget `disabled`, phân tích chạy cuối script trên luồng script, `finally` trả cờ; không bắt `BaseException`. **N13** mỗi file một nút tải (`data` callable đọc file khi bấm): start, từng end (> 5 → selectbox + 1 nút), Excel, 3 CSV, `warnings.csv`, manifest. **N14** `st.bar_chart` code ròng theo tuần, `color=User`, không xếp chồng. **N15** lọc file tường minh (đường dẫn chứa, ngôn ngữ, chỉ file thay đổi) + sắp xếp của `st.dataframe`, cột "Đổi tên từ". **N16** dòng Tổng khi ≥ 1 user, vẽ tách riêng. **N17** cảnh báo GitHub ở [3] trước khi chạy; sau khi chạy "⚠ n cảnh báo" + bảng + dòng kiểm tra chéo. **N18** chọn user bằng ô tìm kiếm + checkbox, lựa chọn trong `session_state`; "Loại trừ bot" ẩn và bỏ bot khỏi lựa chọn (khác CLI N19); account không còn trong kỳ → bỏ + `st.info`. **N19** `LocCounterError`/`OSError` → `st.error(str)`; lỗi khác → thông báo chung + `logger.exception`. **N20** token: `text_input(type="password")`, không vào cache/khóa memo, `run_log(secrets=(token,))`; đổi nguồn/token → vô hiệu repo, kỳ, kết quả. **N21** trong `run_log` app ghi một dòng INFO tóm tắt (nguồn, nhánh, kỳ, `C_START=`, `C_END=`, user). **N22** không fetch lại khi bấm Phân tích. **N23** kết quả cũ giữ kèm chú thích khi tham số đổi. **N24** dòng đầu kết quả `Repo • Nhánh • Kỳ (tz, UTC±hh:mm)`, dòng User như CLI, thư mục kết quả, ghi chú §7.5. **N25** không có nhánh mặc định → `selectbox(index=None)` + nhắc chọn. **N26** bỏ khoảng trắng và dấu `"` bao quanh nguồn. **N27** "Quản lý gộp account" là panel bật/tắt (không `st.dialog`). **N28** README gợi ý `--browser.gatherUsageStats false` | 2026-10-25 (*) |

(*) Chốt theo khuyến nghị của Claude — người dùng ủy quyền "thực hiện theo khuyến nghị" / "tiếp tục" / "làm theo khuyến nghị không cần hỏi" (M5) ngày 2026-10-23; có thể đổi lại.

## 5. Rủi ro / lưu ý kỹ thuật
- **Pygments `stripnl=True` mặc định** bỏ dòng trống đầu/cuối → lệch chỉ số dòng. Phải tạo lexer với `stripnl=False` (đã kiểm chứng). Pygments còn chuẩn hóa `\r\n`/`\r` → `\n`, trong khi `str.splitlines()` tách cả `\f`, `\v`, `\x1c`–`\x1e`, `\u2028`… → cần ánh xạ offset để kết quả có đúng `len(content.splitlines())` phần tử.
- **Token trong bare clone**: clone bằng URL `https://<token>@...` sẽ lưu token trong `config` của repo cache (vi phạm §15). Truyền token qua `-c http.extraHeader` / biến môi trường `GIT_ASKPASS`, không qua URL.
- **Bare clone** không tạo remote-tracking branch; dùng `--mirror` hoặc refspec `+refs/heads/*:refs/heads/*` để `fetch --all --prune` cập nhật nhánh.
- **C_START rỗng**: không dùng được `C_START..C_END` cho blame/rev-list → nhánh xử lý riêng.
- **`git rev-list --before`** lọc theo committer date; fixture test phải đặt cả `GIT_AUTHOR_DATE` và `GIT_COMMITTER_DATE`.
- **CRLF trên Windows**: đọc blob từ object database (`cat-file`), không checkout, để giữ nguyên kiểu xuống dòng.
- **M6 Streamlit** (phân tích 2026-10-25): `RerunException`/`StopException` ở lệnh `st.*` kế tiếp trong callback tiến độ ngắt phân tích (pipeline dọn tạm, `run.log` có ERROR — chấp nhận); `with run_log` phải mở/đóng trong cùng một lần chạy script (lọc theo luồng A16); mất kết nối thì phiên chạy tiếp tới bước kế mới dừng, vẫn giữ khóa `out_root`; Excel đang mở file kết quả → lỗi thay thư mục cũ; GitHub API trong `prepare_period` làm UI đứng (cần spinner); `st.cache_resource` dùng chung giữa các AppTest → clear trong fixture.
- **Tái lập**: zip với timestamp cố định và thứ tự entry sắp xếp; gộp kết quả `ProcessPoolExecutor` theo thứ tự xác định.
- **Python**: máy có CPython 3.14 (qua uv); `requires-python = ">=3.11"`, cần kiểm tra tương thích pandas/streamlit trên 3.14 khi `uv sync`.
- **D28 bước (0) (rủi ro đã biết, review attribution r2):** trong cùng file, khi có một khối bị dời rồi đổi thụt lề và một khối dời khác chứa dòng trùng nội dung, ghép theo nội dung có thể chia lệch ±1 dòng giữa hai user (chưa tái hiện trên repo thật). Theo dõi qua kiểm tra chéo §8.3 ở M5.
- **xlsx không tái lập mặc định (M5, đã kiểm chứng):** openpyxl ghi `dcterms:modified` = giờ hiện tại (đè cả giá trị đã đặt) và mọi entry zip mang giờ hiện tại → ghi lại zip với `date_time` cố định, giữ thứ tự entry, sửa `docProps/core.xml`; `load_workbook` vẫn đọc được.
- **openpyxl / pandas (M5):** chuỗi bắt đầu `=` thành công thức; ký tự điều khiển gây `IllegalCharacterError`; `DataFrame.to_csv` không đường dẫn bỏ `encoding` (mất BOM) và dùng `os.linesep` → ghi CSV bằng module `csv`.
- **Windows (M5):** `FileHandler` giữ khóa `run.log` (gỡ trong `finally`); console cp1252 (CLI đã có `_ensure_utf8`); đường dẫn > 260 ký tự với tag email + hash (giới hạn độ dài `<repo>`/`<branch>`, D40).
- **Fixture §14 dùng email làm account** (`alice@example.com`) → test `--user alice` cần `identities.yaml` gộp về `alice`.
- ✅ **`normalize_source` chưa từ chối `ssh://user:pass@host/...`** (phân tích `pipeline` N18): mật khẩu sẽ vào `manifest.repo`, `Tong_quan`, `run.log`. **Đã xử lý 2026-10-25:** spec `git_repo` 5.3 từ chối mật khẩu trong `ssh://` / `git://` / `file://` và dạng scp `user:pass@host:path` (TC-git_repo-54).
- **§7.3 và dòng chỉ đổi khoảng trắng:** bản dựng "mọi user" giữ bản C_START của dòng chỉ đổi khoảng trắng (D22) và đặt dòng cũ trước dòng mới trong hunk → có thể khác C_END về thụt lề / thứ tự (không mất, không nhân đôi dòng). Ghi vào spec `builder`; LOC thường không đổi (trừ khi thứ tự dòng làm đổi phân loại comment theo ngữ cảnh — §8.3 cho phép lệch nhỏ).
