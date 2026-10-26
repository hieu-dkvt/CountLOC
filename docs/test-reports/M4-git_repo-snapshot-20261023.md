# Báo cáo test — `git_repo` + `snapshot` (cập nhật M4) — 2026-10-23

Phạm vi: spec [git_repo](../specs/git_repo.md) (TC-git_repo-01..49, mới: 33..49), [snapshot](../specs/snapshot.md) (TC-snapshot-01..31, mới: 25..31). Môi trường: Windows 11, git 2.55, CPython 3.14 (uv).

## Kết quả
| Lệnh | Kết quả |
|---|---|
| `uv run pytest -q -p no:cacheprovider --cov=loc_counter --cov-report=term-missing` | **353 passed**, 0 fail, 0 skip (116 s) |
| `uv run ruff check src tests` | sạch |

Coverage: `git_repo.py` 95% (dòng thiếu: nhánh phòng thủ khi output git sai định dạng — `log_commits`, `cat-file --batch-check` trả số dòng/dòng lạ, porcelain thiếu dòng nội dung cuối, mã thoát ≠ 0 của `read_blobs`), `snapshot.py` 100%. Toàn package 97%.

Hồi quy: 237 test có từ M1–M3 vẫn pass sau khi tách `plan_export` → `screen_entry`/`finish_entry` và `write_zip` → `write_entries` (đã chạy riêng trước khi thêm test M4).

## Truy vết TC
| Spec | TC trong spec | Có test | Thiếu | Mồ côi |
|---|---|---|---|---|
| git_repo | 49 | 49 | 0 | 0 |
| snapshot | 31 | 31 | 0 | 0 |

Test M4 (do agent `test-engineer` viết, giá trị kỳ vọng kiểm chứng trên git 2.55):

| TC | Hàm test |
|---|---|
| git_repo-33 | `test_diff_tree_changes` |
| git_repo-34 | `test_diff_tree_empty_start` |
| git_repo-35 | `test_diff_tree_argv_and_rename_limit` |
| git_repo-36 | `test_diff_hunks_zero_based` |
| git_repo-37 | `test_diff_hunks_ignores_global_config` |
| git_repo-38 | `test_blame_forward_period` |
| git_repo-39 | `test_blame_root_not_boundary` |
| git_repo-40 | `test_blame_reverse_rename` |
| git_repo-41 | `test_blame_line_ranges_batches` |
| git_repo-42 | `test_blame_moved_lines` |
| git_repo-43 | `test_blame_ignores_global_config` |
| git_repo-44 | `test_blame_porcelain_parsing`, `test_blame_porcelain_malformed` |
| git_repo-45 | `test_rev_list_and_first_commit_after` |
| git_repo-46 | `test_rev_list_literal_pathspec` |
| git_repo-47 | `test_paths_exist`, `test_paths_exist_newline_path` |
| git_repo-48 | `test_m4_invalid_sha` |
| git_repo-49 | `test_m4_git_errors` |
| snapshot-25 | `test_screen_finish_table`, `test_screen_entry_excluded`, `test_screening_flags` |
| snapshot-26 | `test_plan_export_matches_screen_finish` |
| snapshot-27 | `test_select_content`, `test_select_content_unsafe_logged` |
| snapshot-28 | `test_write_entries_mixed`, `test_write_zip_same_as_write_entries` |
| snapshot-29 | `test_write_entries_invalid`, `test_write_entries_empty` |
| snapshot-30 | `test_write_entries_blob_error` |
| snapshot-31 | `test_zip_timestamp` |

## Tái lập
TC-snapshot-16 và TC-snapshot-28 ghi zip hai lần (TC-28 với thứ tự đầu vào khác nhau) → SHA-256 bằng nhau.

## Ghi chú
- TC-git_repo-45: ca "`ancestry_path` loại f1" trong spec luôn đúng (f1 không phải tổ tiên của c4); đã thay bằng ca thực sự kiểm `--ancestry-path` (`rev_list(c4, f1, …, ancestry_path=True) == []`). Spec đã cập nhật mô tả TC (chỉ đổi test, ghi Lịch sử thay đổi).
- Tên file `*.py`, `:(glob)x.py`, `tệp: x.py`, tên có `\n` được tạo trong index bằng `git -c core.protectNTFS=false update-index` / `git mktree` (Windows không tạo được trên đĩa).
- Mandatory-tests mục D (§14) thuộc `attribution`/`builder`, chưa trong phạm vi này.

## Lần 2 — sau khi sửa theo review (reviews/git_repo-snapshot-20261023.md)
| Lệnh | Kết quả |
|---|---|
| `uv run pytest -q -p no:cacheprovider --cov=loc_counter --cov-report=term-missing` | **368 passed**, 0 fail (127 s) |
| `uv run ruff check src tests` | sạch |

Coverage: `git_repo.py` 97%, `snapshot.py` 100%, toàn package 97%. Truy vết: git_repo 50/50 TC, snapshot 32/32 TC, không thiếu, không mồ côi.

Test thêm/sửa: TC-git_repo-37 `test_diff_hunks_ignores_diff_env` (`GIT_DIFF_OPTS`, `GIT_EXTERNAL_DIFF`); TC-44 ca porcelain bị cắt + `test_blame_only_empty_ranges`; TC-45 assertion đối chứng `[c3]`; TC-47 `test_paths_exist_newline_cr_path`, `test_paths_exist_gitlinks`, `test_paths_exist_bad_batch_output`; TC-49 `test_diff_tree_malformed`; TC-50 `test_read_blobs_short_read`; TC-snapshot-32 `test_write_entries_checks_cat_file_exit`.
