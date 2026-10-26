# Review: attribution (cập nhật M5 — sha theo dòng, `commit_stats`, D35) — 2026-10-24
Kết luận: **PASS_WITH_NOTES**
Spec: docs/specs/attribution.md (status: implemented)   Files: `src/loc_counter/attribution.py` (576 dòng), `tests/test_attribution.py` (1751 dòng); đối chiếu thêm `docs/specs/counter.md` (A8, 5.8), `docs/PLAN.md` (D35, Q40), `docs/specs/README.md`, `docs/test-reports/M5-attribution-20261024.md`, `docs/reviews/attribution-20261023-r3.md`

## Bằng chứng tự động
- ruff: `All checks passed!` (src, tests)
- pytest `tests/test_attribution.py`: **75 passed** / 0 failed (121 s). Toàn bộ `uv run pytest -q`: **512 passed** (293 s)
- coverage `loc_counter.attribution` (chỉ chạy test_attribution): **99 %** (395 stmt, thiếu `:131` — `_split_lines` khi đoạn cuối không có `\n`; báo cáo test ghi 100 % khi chạy toàn bộ package)
- Kiểm thử đột biến phần M5 (bản sao ngoài project `C:\Users\User\AppData\Local\Temp\claude\d--PJ-Tool\e20c51ec-5ddb-40ba-80fd-365b111b065b\scratchpad\mut\m1..m2`, đã xác nhận `loc_counter.attribution.__file__` trỏ tới bản đột biến):

| Mutant | Thay đổi | Test bắt được |
|---|---|---|
| m1 | `:531-532` sắp `commit_stats` theo `(account, sha)` thay cho `sha` | 9 test fail (TC-38, 41, 42) |
| m2 | `:513-515` ô `per_commit` không cộng `added_code`/`deleted_code` | 16/16 test M5 fail (bất biến 4b) |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 3 Giao diện | `FileAttribution.added_commit` / `deleted_commit` đặt cuối, mặc định rỗng chỉ đọc; `CommitLineStats` 6 trường; `PeriodAttribution.commit_stats = ()`, `commit()` | `:63-64`, `:84-93`, `:106`, `:116-118`; TC-43 | Đạt |
| 3 / counter A8 | Giao diện `CommitLineStats` khớp spec `counter` mục 3 | `counter.md:230-240` ↔ `:84-93` | Đạt |
| 5.4 bước 2 | blame xuôi → sha `b.sha` | `:341` (`added[b.line] = b.sha`) | Đạt |
| 5.4 bước 3 | D22 → sha của lần blame thứ hai | `:354`; TC-40 (TC-16) | Đạt |
| 5.5 | sha = `cand` (thường) hoặc kết quả `resolve_merge` (commit nhánh / chính merge) | `:377-386`; TC-39 (TC-11, 13, 14, 36) | Đạt |
| 5.7 (a) | `added_commit[u] = deleted_commit[x]` | `:414` (A11); TC-40 (TC-18) | Đạt |
| 5.7 (b) | `deleted_commit[o] = added_commit[n]` | `:422`; TC-40 (TC-17) | Đạt |
| 5.9 bước 1–2 | Cờ code theo phía mới / cũ; thiếu cờ → False + WARNING | `:485-493`, `:512`; TC-37 (c) | Đạt |
| 5.9 bước 4a | `commit_stats` cùng vòng lặp, cùng cờ; chỉ ô ≥ 1 dòng; `whole`/`skip`/`renamed_by`/`last_touch_by` không tạo ô; sắp theo sha | `:496-533` (một lần `_code_flags` mỗi phía, `per_commit` chỉ tạo khi đếm dòng, vòng `renamed_by`/`last_touch_by` chỉ gọi `bucket`); TC-38, 42 | Đạt |
| 5.9 bước 4b | Bất biến khóa/thứ tự, account khớp, Σ theo account = `UserLineStats` | Đúng theo cấu trúc: `added_by`/`deleted_by` suy ra từ `added`/`deleted` (sha) `:302-305`, cùng thứ tự; `_line_stats` cộng cùng hàng cho user và commit `:513-515`; `assert_commit_invariants` `tests:1500-1523` | Đạt |
| 5.9 bước 6 | 4 Mapping theo chỉ số tăng dần, bọc chỉ đọc | `:302-311` | Đạt |
| 8 Hiệu năng | Không thêm lệnh git, không phân loại lại | Không có lời gọi `repo.*` mới; `_code_flags` một lần mỗi phía | Đạt |
| 5.1–5.8 (M4) | Không đổi cách gán account | Logic M4 giữ nguyên, chỉ đổi giá trị trung gian từ account sang sha (account suy ra qua `self.accounts[sha]`); TC-01..37 pass không đổi kỳ vọng | Đạt |
| TC-38 | 4 ô, sha từng dòng, không có ô admin / alice late | `test_section14_commit_stats` `:1526-1549` | Đạt |
| TC-39 | sha qua merge (11, 13, 14, 36) | `test_commit_sha_through_merges` `:1552-1601` | Đạt |
| TC-40 | sha của dòng dời (16, 17, 18) | `test_commit_sha_of_moved_lines` `:1604-1632` | Đạt |
| TC-41 | Bất biến trên 15 repo, chạy 2 lần bằng nhau | `test_commit_invariants` (12 repo) + gọi trong TC-21, 22, 25, 33 | Một phần (Minor 1) |
| TC-42 | (a)–(e) | `test_commit_stats_no_cells_and_multi_email` `:1674-1731` | Một phần — (b) không dùng repo TC-24 (Minor 1) |
| TC-43 | Dựng theo vị trí 10 / 6 tham số | `test_positional_construction_compat` `:1734-1751` | Đạt |

## Phát hiện
Không có Blocker hay Major.

### [Minor] TC-41 / TC-42 (b) chạy trên tập repo hẹp hơn spec mô tả — `tests/test_attribution.py:1635-1671`, `:1687-1698`, `:981-1006`
- **Mô tả**:
  - TC-41 liệt kê repo TC-28 (alice 2 email **và committer khác author**). `test_account_from_log_not_porcelain` (`:981`) không gọi `assert_commit_invariants`; TC-42 (e) dựng repo riêng không có `committer=ci`. Repo TC-21, 22, 25, 33 chỉ kiểm bất biến một lần, không có bước "chạy 2 lần → bằng nhau" mà TC-41 yêu cầu.
  - TC-42 (b) ghi "TC-24 (`whole`)" (binary + `.py` quá lớn + đổi kiểu `T` sang symlink), nhưng test chỉ dựng một file binary `logo.png`. Hai nhánh `too_large` và `T` không được kiểm `commit_stats == ()`.
- **Kịch bản**: hiện chưa gây sai số. Tôi đã đọc code: mọi nhánh `whole` trả `_EMPTY` (`:283-284`) và `_line_stats` chỉ đếm khi `granularity == "lines"` (`:519`), nên too_large / `T` đi cùng đường với binary. Nếu sau này ai đó tách nhánh `T` hoặc too_large ra (ví dụ để đếm dòng cho file `.py` quá lớn), sẽ không có test nào báo lệch bất biến.
- **Đề xuất**: thêm `assert_commit_invariants(result)` và `assert result.commit_stats == ()` vào `test_whole_file_granularity` (TC-24); thêm `assert_commit_invariants` vào `test_account_from_log_not_porcelain`; hoặc ghi lại phạm vi thực tế vào cột Input của TC-41/42 trong spec.
- **Tham chiếu**: spec attribution §9 TC-41, TC-42; checklist 1 "test thật sự kiểm điều TC mô tả".

### [Nit] Trạng thái README lệch spec — `docs/specs/README.md:31`
- README ghi `approved (M5)`, front matter spec ghi `status: implemented` (Lịch sử 2026-10-24 "Test pass → implemented"). Cần cập nhật README.

### [Nit] Helper test thiếu docstring — `tests/test_attribution.py:1496`
- `stats_tuple` không có docstring (các helper mới khác đều có).

### [Nit] (giữ từ r3) `hash()` của dataclass frozen chứa `MappingProxyType` lỗi — `src/loc_counter/attribution.py:48-64`, `:96-106`
- `FileAttribution` / `PeriodAttribution` là `frozen=True` nên dataclass sinh `__hash__`, nhưng có trường `MappingProxyType` không hash được, nên `hash(fa)` raise `TypeError`. Hai trường M5 mới cũng là Mapping nên giữ nguyên tình trạng này. Hiện không có chỗ nào dùng làm khóa dict / phần tử set.

### [Nit] `PeriodAttribution.commit()` duyệt tuyến tính — `src/loc_counter/attribution.py:116-118`
- O(n) mỗi lần gọi. `counter.weekly_metrics` (spec counter 5.8) duyệt `commit_stats` trực tiếp nên không bị ảnh hưởng. Chỉ cần quan tâm nếu pipeline gọi `commit()` trong vòng lặp lớn (M7).

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt (trừ Minor 1) | Luồng 5.4 → 5.5 → 5.7 → 5.8 → 5.9 đúng thứ tự; API công khai đúng mục 3; không đổi định nghĩa §3, thuật toán §7 (account của mọi dòng như M4); lệnh git không đổi |
| 2. Nghiệp vụ dễ sai | Đạt | `added_code` theo C_END, `deleted_code` theo C_START (`:520-525`); boundary không phải dòng thêm; merge chỉ có ô khi giải quyết xung đột / tự xóa (TC-39). `_split_lines` riêng (Nit cũ, để builder) |
| 3. Bảo mật | Đạt | Không nhận token; không gọi subprocess trực tiếp; mọi git qua `GitRepo` |
| 4. Lỗi & log | Đạt | Không nuốt exception; WARNING khi thiếu cờ, vượt độ sâu; INFO tổng kết; không `print` |
| 5. Tái lập & encoding | Đạt | `commit_stats` sắp theo sha; dict theo chỉ số tăng dần; TC-41 chạy 2 lần bằng nhau; `decode_text` dùng chung |
| 6. Windows | Đạt | Không thao tác đường dẫn đĩa; toàn bộ test pass trên Windows 11 |
| 7. Chất lượng code | Đạt | Có type hint, docstring tiếng Việt; ruff sạch; không TODO, không code chết |
| 8. Hiệu năng | Đạt (M4/M5) | Không thêm lệnh git; phân loại mỗi phía một lần, có cache theo SHA của `LineClassifier`; song song để M7 |
| 9. Màn hình Streamlit | N/A | Module lõi, không có UI |

## Ghi chú cho spec
1. TC-41 / TC-42 (b): nên ghi đúng tập repo test thật sự dùng, hoặc bổ sung test như Minor 1. Người dùng quyết định.
2. A11 (D28 (a) nhận sha commit xóa dòng cũ): tuần ISO của dòng dời rồi đổi khoảng trắng (TC-18) tính theo commit dời (alice), không theo commit đổi thụt lề (carol). Cách này nhất quán với account đã gán ở M4 và đúng như A11 đã chốt. Ghi ở đây để biết khi đọc sheet `Theo_tuan`: sẽ không có dòng code nào trong tuần của carol cho khối này.
