# Review: attribution (R19 bộ nhớ đệm / làm nóng D23, R20 song song theo file) — 2026-10-29
Kết luận: **PASS_WITH_NOTES**
Spec: docs/specs/attribution.md (status: implemented)   Files: `src/loc_counter/attribution.py` (731 dòng, đọc toàn bộ), `tests/test_attribution.py` (2021 dòng; trọng tâm `:1769-2021`); đối chiếu thêm `src/loc_counter/git_repo.py` (`blame`, `_merge_ranges`, `_parse_blame`, `_exec`), `src/loc_counter/pipeline.py` (`run_log`, `_RUN_LOG_ID`), `docs/test-reports/attribution-perf-20261028.md`, `docs/test-reports/perf-parallel-20261029.md`, `git diff` của hai file trong phạm vi.

## Bằng chứng tự động
- ruff `src tests`: `All checks passed!`
- pytest `tests/test_attribution.py`: **83 passed** / 0 failed (226 s, cùng lượt với coverage)
- coverage `loc_counter.attribution`: **99 %** (508 stmt, thiếu `:135` — `_split_lines` khi đoạn cuối không có `\n`, có từ trước; `:272` — cache hit trong `_fill_blame`; `:385` — bỏ dòng khi gom ở `_warm_parent`). Hai dòng sau đúng là các nhánh của đường làm nóng mới (xem Minor 2).
- **Kiểm chứng trên repo thật** (script chỉ đọc `C:\Users\User\AppData\Local\Temp\claude\d--PJ-Tool\7049a189-ff7d-4513-8cff-3dc0e095469d\scratchpad\review_attr\verify_real.py`, mở trực tiếp `D:\PJ\deepseek-harness\deepseek-harness\.git`, nhánh `master`, kỳ 2026-09-03, `config.yaml` của project): 182 commit / 90 merge, 1 287 file, 247 file đi qua D23.
  - Bản tối ưu, 8 luồng: 202,5 s; 8 527 lệnh `_fill_blame` (6 932 lệnh nhiều dòng, 141 969 cặp (lệnh, dòng)).
  - Bất biến "blame nhiều `-L` == blame một dòng" và khóa `b.line`: **0 dòng thiếu** trong kết quả nhiều `-L`; so ngẫu nhiên 300 dòng (cả xuôi tới merge-base và ngược trên parent) với `repo.blame` một dòng: **0 khác**.
  - Bản **không tối ưu** (tắt 4 bộ nhớ đệm + `_warm_merge` rỗng, 1 luồng — như `disable_optimizations` của TC-46) trên 15 file đi qua D23 (3–10 lần `resolve_merge` mỗi file; 240 lệnh blame, 13,3 s) so với kết quả của bản tối ưu 8 luồng chạy cả kỳ: **0 `FileAttribution` khác**, cảnh báo của các file đó bằng nhau, 31 dòng xóa đã gán. (Lần thử đầu với 20 file D23 nặng nhất không chạy xong sau ~45 phút ở chế độ không tối ưu nên đã dừng — đúng là lý do của R19.)
- **Kịch bản bổ sung** (`...\scratchpad\review_attr\test_probe_equiv.py`, chạy với fixture của `tests/conftest.py`): (1) "mixed" — feat tách trước C_START, C_START thêm 3 dòng sinh sau merge-base, bob xóa v2, v3 trên feat, carol merge xóa luôn 3 dòng đó → cùng nhóm `(S, path, M)` có dòng boundary và dòng không boundary (phủ `:385`); (2) "nested" — như TC-36 nhưng bob xóa v2..v4 trong **hai** file (song song + 3 dòng hội tụ ở độ sâu 2). Bản tối ưu 4 luồng **bằng hoàn toàn** bản tắt tối ưu 1 luồng (`PeriodAttribution ==`); số lệnh blame 4 vs 9 và 18 vs 38. Kết quả đúng nghiệp vụ: extra → carol (merge tự xóa, D23), v2..v4 → bob.
- **Thăm dò TC-47 (a)** (`...\scratchpad\review_attr\test_probe_tc47.py`): số entry / số lần `resolve_merge` của từng repo: s14 2/0, tc11 1/2, tc14 1/2, tc16 2/0, tc17 1/0, tc36 1/5, tc44 1/5, many 6/13 (xem Minor 1).
- **Kiểm thử đột biến** (bản sao `...\scratchpad\review_attr\mut\<m>\loc_counter`, đã xác nhận `loc_counter.attribution.__file__` trỏ tới bản đột biến; chạy 16 test D23 / song song):

| Mutant | Thay đổi | Test bắt được |
|---|---|---|
| mB | `_warm_merge` `:366` không bỏ dòng khỏi `pending` khi bên parent đã ≠ `PRESENT` → làm nóng cả parent mà cách tính tuần tự không tới (vi phạm "giữ thứ tự lười", 5.6a.3) | **Không** (16/16 pass) — Minor 3 |
| mC | `_attribute_entries` `:685` lấy kết quả theo `as_completed` | 2 fail (TC-47 a, b) |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 3 Giao diện | `ATTRIBUTION_WORKERS = min(8, os.cpu_count() or 1)`; không thêm API công khai | `:28`; `_attribute_entries`, cache, `_warm_*` đều private | Đạt |
| 5.1a.4 | `workers = min(ATTRIBUTION_WORKERS, len(entries))`; ≤ 1 → tuần tự; `ThreadPoolExecutor(thread_name_prefix="loc-attr")`; mỗi task một `copy_context().run` tạo ở luồng gọi | `:677-683` (hằng đọc lúc gọi → monkeypatch được); TC-47 (c) `:1995-2021` | Đạt |
| 5.1a.5 | Kết quả theo thứ tự nộp; lỗi của entry đầu tiên theo thứ tự; hủy task chưa chạy, chờ task đang chạy | `:684-689` (`f.result()` lần lượt; `cancel()`; `with` → `shutdown(wait=True)`); TC-47 (b) `:1967-1992`, mutant mC | Đạt |
| 5.1a.6 | Dùng chung `_Attributor`; cache/memo là `dict`, không lock; tính trùng khóa chỉ chạy git trùng | `:193-198`; mọi cache/memo chỉ thêm, không xóa; `GitRepo` không giữ trạng thái giữa lệnh (`git_repo.py:355-401`); `select_content`/`detect_language` chỉ dùng `lru_cache` | Đạt (xem Ghi chú spec 2) |
| 5.1a.7 | `_line_stats` tuần tự sau khi đủ kết quả | `:725` | Đạt |
| R20 log | Log luồng con vào `run.log` | context sao chép `:682` + filter `pipeline.py:307-308` đọc `_RUN_LOG_ID` lúc emit | Đạt |
| 5.6a.1 | Cache `is_ancestor` / `merge_bases` / `first_commit_after`; lỗi không ghi nhớ; áp dụng ở 5.5 bước 3 và 5.6 | `:219-244` (ghi sau khi gọi thành công); dùng ở `:319-337`, `:506`; TC-44 `:1824-1865` | Đạt |
| 5.6a.2 | Blame một dòng ghi nhớ theo `(S, path, base, j)` / `(P, neo.path, neo.commit, neo.j)` | `:246-259`, khóa `(end, path, since, line, reverse)`; gọi ở `:325`, `:334` | Đạt |
| 5.6a.3 | Làm nóng theo tầng: sau khi có `cand` của mọi nhóm, gom `(L, fn, cand)` merge → `_warm_merge(…, 1)`; dừng khi `depth > MAX_MERGE_DEPTH`/rỗng; bỏ dòng có memo; parent theo thứ tự, dừng khi `pending` rỗng; gom blame xuôi (a), ngược theo `(neo.path, neo.commit)` (b); dừng trước đệ quy, `nested` gộp mọi khóa (c); không gom dòng không cần blame | `:506-511`, `:344-370`, `:372-389`, `:261-283`. Tập (dòng, parent) được làm nóng đúng bằng tập mà `resolve_merge` tuần tự đi qua (lập luận: `resolve_merge` không bao giờ trả `PRESENT`, nên mọi kết quả ≠ `PRESENT` ở `_locate` đều dừng parent sau ở cả hai đường) | Đạt (test chưa khóa được tính lười — Minor 3) |
| 5.6a.3 lỗi | Lỗi git khi làm nóng ném lên | không có `try` nào trong `_warm_*` | Đạt |
| 5.6a.4 | Kết quả bằng bản không tối ưu | Lập luận: `_warm_*` chỉ nạp cache, `_locate` dùng chung; cache khóa theo `b.line` git trả. Repo thật: 0/300 khác, 0 thiếu; TC-46 `:1888-1920`; 2 kịch bản bổ sung | Đạt |
| 5.5 bước 3 | `cand` tính một lần mỗi nhóm `(L, fn)` | `:506` (trước đây gọi trong vòng lặp — cùng tập lệnh) | Đạt |
| 8 | Truy vấn thuần ≤ 1 lần mỗi `attribute_period`; blame không tỷ lệ theo số dòng | Đúng khi tuần tự (TC-44, 45); khi song song có thể trùng giữa luồng (5.1a.6) | Một phần (Ghi chú spec 1) |
| TC-44 | Kết quả đúng; spy không trùng tham số; `GitError` không ghi nhớ | `:1824-1865` — repo chỉ 1 entry nên chạy tuần tự (đúng với kỳ vọng "không trùng"); unit lỗi chỉ kiểm `is_ancestor` | Đạt (Nit 3) |
| TC-45 | Số blame n = 4 bằng n = 1; có lệnh D23 phủ ≥ 4 dòng | `:1868-1885` | Đạt |
| TC-46 | 7 repo: bản tắt cache + warm bằng bản tối ưu; bản tắt gọi blame nhiều hơn trên TC-44 | `:1801-1920` (`_NoStore` + `_warm_merge` rỗng — đúng là bản trước R19) | Đạt (độ phủ kịch bản: Minor 2) |
| TC-47 (a) | 8 repo, `ATTRIBUTION_WORKERS` 1 vs 4 bằng nhau | `:1942-1964` — 5/8 repo chỉ có 1 entry nên cả hai lần đều tuần tự | Một phần (Minor 1) |
| TC-47 (b) | File 2 và 4 lỗi → lỗi file 2 | `:1967-1992` (file 2 ngủ 0,3 s để lỗi file 4 xảy ra trước) | Đạt |
| TC-47 (c) | Luồng `loc-attr*`, đọc được `ContextVar` | `:1995-2021` | Đạt |

## Phát hiện
Không có Blocker hay Major. Tương đương kết quả giữa đường làm nóng và đường tuần tự, khóa cache xuôi/ngược, `b.line` của blame ngược nhiều `-L`, thứ tự kết quả/lỗi khi song song, `MAX_MERGE_DEPTH` trong `_warm_merge` đều đúng (đã kiểm chứng ở trên). Các phát hiện dưới đây là về độ mạnh của test và chất lượng code.

### [Minor] 1. TC-47 (a): 5/8 repo không thực sự chạy song song — `tests/test_attribution.py:1945-1961`
- **Mô tả:** `_attribute_entries` dùng `workers = min(ATTRIBUTION_WORKERS, len(entries))`. Repo tc11, tc14, tc17, tc36, tc44 chỉ có **1 entry** (đã đo, xem "Thăm dò TC-47") → với `ATTRIBUTION_WORKERS = 4` vẫn đi nhánh tuần tự `:678-679`; phép so `parallel == serial` cho 5 repo này là so cùng một đường code với chính nó. Chỉ s14, tc16 (2 file, không qua D23) và `many` (6 file, 13 lần `resolve_merge`) chạy qua `ThreadPoolExecutor`; trong `many` các file có đường dẫn khác nhau nên chỉ chung khóa `is_ancestor`/`merge_bases`, không có memo/blame cache dùng chung. Báo cáo `perf-parallel-20261029.md` ghi "8 repo, 1 luồng vs 4 luồng" — dễ hiểu nhầm là 8 repo đều được kiểm song song.
- **Kịch bản lỗi:** một lỗi chỉ xuất hiện khi nhiều luồng cùng đi qua D23 trên các merge lồng nhau (vd. ghi memo dở dang, khóa cache phụ thuộc luồng) sẽ không bị TC-47 (a) bắt nếu nó không tái hiện trên `many`.
- **Đề xuất sửa:** thêm vào danh sách TC-47 (a) một repo nhiều file cùng đi qua merge lồng nhau (vd. kịch bản "nested" hai file `app.py`, `lib.py`, bob xóa v2..v4 trên `feat2` — `...\scratchpad\review_attr\test_probe_equiv.py:41-64`), và assert `len(entries) >= 2` cho mỗi repo trong vòng lặp (hoặc ghi rõ trong spec TC-47 rằng các repo 1 file chỉ để kiểm "không hỏng" nhánh tuần tự). Chỉ đổi test.
- **Tham chiếu:** spec 5.1a, R20, TC-47 (a); checklist 1 "test thật sự kiểm điều TC mô tả".

### [Minor] 2. TC-46 không phủ các nhánh khác biệt của đường làm nóng — `src/loc_counter/attribution.py:272`, `:385`; `tests/test_attribution.py:1891-1899`
- **Mô tả:** Coverage cho thấy `:272` (`_fill_blame` gặp một phần dòng đã có trong cache) và `:385` (`_warm_parent` bỏ dòng có `fb` không boundary / `fb.sha` không là tổ tiên của parent) **không test nào chạy tới**. Đây chính là chỗ đường gom có thể lệch đường tuần tự. Các repo của TC-46 đều có nhóm `(S, path, M)` "đồng nhất" (mọi dòng cùng boundary, cùng neo); không repo nào có nhiều dòng hội tụ ở độ sâu ≥ 2 — động lực chính của A13 (TC-36 chỉ 1 dòng).
- **Kịch bản lỗi:** nếu sau này `_warm_parent` đưa nhầm dòng không boundary vào lệnh blame ngược (hoặc lấy neo sai cho nhóm hỗn hợp), TC-46 vẫn pass. Reviewer đã chạy 2 kịch bản bổ sung ("mixed" phủ `:385`, "nested" 3 dòng hội tụ độ sâu 2, hai file song song): kết quả hiện tại **bằng nhau** — tức code đúng, chỉ thiếu test giữ hành vi.
- **Đề xuất sửa:** thêm hai builder `build_mixed_born_after_base`, `build_nested_multi` (`...\scratchpad\review_attr\test_probe_equiv.py:15-64`) vào danh sách TC-46 (và TC-47 a), kèm kỳ vọng nghiệp vụ: mixed → `deleted_by` v2, v3 = bob, 3 dòng extra = carol (D23 merge tự xóa), v8 = alice; nested → v2..v4 = bob ở cả hai file, carol/dave không có dòng. Chỉ đổi test (+ dòng TC trong spec).
- **Tham chiếu:** spec 5.6a.3, 5.6a.4, A13, TC-46.

### [Minor] 3. Không test nào giữ "thứ tự lười theo parent" của `_warm_merge` — `src/loc_counter/attribution.py:358-369`
- **Mô tả:** Spec 5.6a.3 yêu cầu "chỉ làm nóng cho parent mà cách tính tuần tự cũng sẽ tới". Code đúng (dòng rời `pending` ngay khi bên parent ≠ `PRESENT`), nhưng mutant mB (giữ dòng trong `pending` → làm nóng cả parent sau) **sống sót** toàn bộ 16 test D23/song song. Lý do: trong mọi fixture, dòng xóa luôn `PRESENT` ở parent đầu (parent đầu = nhánh chính chứa L), nên không có dòng nào dừng sớm ở parent 1.
- **Kịch bản lỗi:** hồi quy kiểu mB không đổi kết quả nhưng chạy thêm blame cho parent thừa (chậm hơn trên repo nhiều "back-merge" — merge `master` vào nhánh feature, parent đầu là nhánh feature), và có thể ném `GitError` mà bản tuần tự không gặp.
- **Đề xuất sửa:** thêm một kịch bản có dòng bị xóa **bên parent đầu** của merge (vd. bob xóa v2 trên `feat`, rồi `git merge main` từ `feat` để parent đầu là `feat`, sau đó fast-forward/merge vào main), dùng `BlameSpy` kiểm không có lệnh blame nào với `end` = parent thứ hai cho các dòng đó; hoặc so số lệnh blame bằng đúng bản không tối ưu cho phần blame một dòng (đếm theo `(end, since)`). Chỉ đổi test.
- **Tham chiếu:** spec 5.6a.3 ("giữ thứ tự lười"), R19.

### [Nit] 1. Thiếu docstring cho các hàm bọc cache — `src/loc_counter/attribution.py:219`, `:228`, `:237`
- `_is_ancestor`, `_merge_bases`, `_first_after` không có docstring (các hàm private khác trong class đều có). Đề xuất: một dòng tiếng Việt mỗi hàm, vd. "`repo.is_ancestor` có ghi nhớ (5.6a.1); lỗi không ghi nhớ."

### [Nit] 2. Comprehension khó đọc, gọi `_is_merge` hai lần — `src/loc_counter/attribution.py:507-517`
- `for cand in [cands[(last, filename)]]` là mẹo gán biến trong comprehension; `_is_merge(cand)` tính lại ở `:516`. Đề xuất: vòng `for` thường, hoặc dựng `merge_keys = {key for key, cand in cands.items() if cand is not None and self._is_merge(cand)}` rồi dùng lại ở vòng gán.

### [Nit] 3. Unit "GitError không ghi nhớ" chỉ kiểm `is_ancestor` — `tests/test_attribution.py:1847-1865`
- Spec TC-44 nêu chung cho cả bộ nhớ đệm; `_merge_bases`, `_first_after`, `_line_blame` cùng mẫu nhưng không có test. Rủi ro thấp (code cùng một khuôn); có thể tham số hóa test cho 4 hàm.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt (trừ Minor 1–3 về test) | Luồng 5.1a, 5.6a đủ bước, đúng thứ tự; không API công khai mới ngoài `ATTRIBUTION_WORKERS`; lệnh git không đổi (`blame -w`, `--reverse`, `-L` nhiều khoảng qua `git_repo`); thuật toán §7 / D23 không đổi |
| 2. Nghiệp vụ dễ sai | Đạt | D23: dòng còn ở mọi parent → merge (kịch bản "mixed" kiểm thêm); commit xóa qua merge lồng nhau ("nested"); thứ tự `cand` không đổi |
| 3. Bảo mật | Đạt | Không nhận token; mọi git qua `GitRepo` (`subprocess.run` list, không `shell`); log từ luồng con đi qua `_MaskingFormatter` của pipeline |
| 4. Lỗi & log | Đạt | `GitError` lan ra theo thứ tự entry; WARNING vượt độ sâu vẫn vào `run.log` nhờ `copy_context` (TC-47 c, TC-pipeline-39); không nuốt exception (`except BaseException` chỉ hủy rồi `raise`) |
| 5. Tái lập & encoding | Đạt | `files`/cảnh báo theo thứ tự `td.entries` (mutant mC bị bắt); cache chỉ nạp, không đổi kết quả (repo thật 0/300 khác); xem Ghi chú spec 2 cho trường hợp lý thuyết gần `MAX_MERGE_DEPTH` |
| 6. Windows | Đạt | Thread + `subprocess.run(capture_output)` an toàn trên Windows; không file tạm |
| 7. Chất lượng code | Đạt (Nit 1–2) | ruff sạch; type hint đủ; không code chết (`_line_blame`, `_parent_side` vẫn dùng) |
| 8. Hiệu năng | Đạt | Truy vấn thuần có cache; blame D23 gom theo tầng; bộ nhớ: cache `BlameLine` theo số truy vấn (tối đa vài chục nghìn mục trên repo thật), sống trong một lần `attribute_period`; ≤ 8 tiến trình git đồng thời |
| 9. Màn hình Streamlit | N/A | Không phải spec màn hình |

## Ghi chú cho spec
1. **Mục 8 mâu thuẫn nhẹ với 5.1a.6:** mục 8 ghi "mỗi truy vấn thuần theo cặp commit chạy tối đa một lần mỗi lần `attribute_period`", nhưng 5.1a.6 cho phép hai luồng cùng tính một khóa (chạy git trùng). Đề xuất sửa mục 8 thành "tối đa một lần mỗi luồng / khi chạy tuần tự" và ghi rõ TC-44 dùng repo 1 file nên chạy tuần tự.
2. **5.1a.6 "kết quả như nhau (truy vấn thuần)" chưa chặt với memo `resolve_merge`:** khóa memo `(S, path, j, M)` không chứa `depth`, trong khi kết quả có thể phụ thuộc `depth` khi chuỗi merge chạm `MAX_MERGE_DEPTH` (nhánh sâu bị cắt thành `UNDETERMINED` rồi được ghi nhớ). Khi tuần tự, thứ tự tính cố định nên vẫn tái lập; khi song song, nếu **hai file khác nhau** cùng đi tới một khóa ở hai độ sâu khác nhau gần giới hạn 64, kết quả phụ thuộc luồng nào tính trước. Điều kiện cần (> 64 merge lồng nhau + hai entry hội tụ cùng neo) gần như không xảy ra thực tế; **chưa kiểm chứng bằng kịch bản**, chỉ suy luận từ code `:286-303`. Cần người dùng quyết định: chấp nhận và ghi vào A3/A14, hoặc chỉ ghi memo khi kết quả không bị cắt bởi độ sâu.
3. TC-47 (a): spec liệt kê repo TC-11, 14, 17, 36, 44 — đều 1 file nên không kiểm được song song (Minor 1). Đề xuất sửa danh sách repo của TC-47 (a) và TC-46 theo Minor 1, 2.
