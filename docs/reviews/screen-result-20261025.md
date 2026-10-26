# Review: screen-result — 2026-10-25
Kết luận: **FAIL**
Spec: docs/specs/screen-result.md (status: approved)   Files: `src/loc_counter/app.py` (dòng 231–373, 675–790, 835–836), `tests/test_app_result.py`, `pyproject.toml` (theo spec §8 / A5)

## Bằng chứng tự động
- ruff: `uv run ruff check src tests` → All checks passed!
- pytest: `uv run pytest tests/test_app_result.py -q` → **14 passed** (45,8 s)
- coverage (`test_app_result.py` + `test_app_input.py`, `--cov=loc_counter.app`): `app.py` 532 stmt, **98 %**; dòng chưa chạy thuộc screen-result: **744** (`st.caption("Không có file source nào.")`); còn lại (464–470, 477, 579–581, 637) thuộc screen-input.
- Kiểm chứng thêm (script trong scratchpad):
  - Streamlit đang cài là 1.66.1 (`uv.lock`); `pyproject.toml:13` vẫn ghi `streamlit>=1.40`.
  - `multiselect file_languages` / `selectbox dl_separate_pick` khi danh sách lựa chọn đổi giữa hai kết quả: Streamlit 1.66.1 tự đặt lại (giá trị cũ → `[]` / lựa chọn đầu), **không** ném lỗi; `names.index(choice or names[0])` không gặp `ValueError`.
  - `filter_files` trên frame rỗng, với `İ` (casefold), với chuỗi giống regex `a.*` (`regex=False`): kết quả đúng.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 3.4 | Hằng `NOTE_USER_EXPORT`, `STALE_NOTE`, `SEPARATE_SELECT_MIN = 6`, `MIME` | app.py:232–238 | Đạt |
| 3.4 | Các hàm thuần `signed` … `download_items`, `DownloadItem` (đúng chữ ký, cột, thứ tự sắp xếp) | app.py:242–373 | Đạt |
| 3.4 | Cột số kiểu `int`; `NumberColumn(format="localized")`, "Chênh lệch"/"Ròng" `%+d` | app.py:675–683 | Đạt (xem Ghi chú cho spec) |
| 5.1 | `container(border=True)`, `subheader("KẾT QUẢ")`, stale → `st.info(STALE_NOTE)` | app.py:727–730; TC-12 | Đạt |
| 5.2 | `st.text(header_text)`, `st.text(users_text)` | app.py:731–732; TC-11 | Đạt |
| 5.3 | 4 `st.metric`; Commit = Σ `user_rows.commits` | app.py:733–737; TC-01, TC-04 | Đạt |
| 5.4 | Kiểm tra chéo `success` / `warning` | app.py:738–739; TC-07 | Đạt |
| 5.5 | Theo ngôn ngữ, rỗng → caption | app.py:741–746 | Đạt (nhánh rỗng không có test) |
| 5.6 | Theo user + Tổng vẽ riêng; rỗng → caption | app.py:747–754; TC-03, TC-04 | Đạt |
| 5.7 | `bar_chart(x="Tuần", y="Code ròng", color="User", stack=False)`; rỗng → caption | app.py:755–760; TC-05, TC-04 | Đạt |
| 5.8 | `st.warning(..., icon="⚠️")` / caption; expander "Cảnh báo" + nút `warnings.csv` | app.py:762–774; TC-07, TC-10 | Đạt |
| 5.9 | Expander "Chi tiết theo file": 3 ô lọc, dataframe, caption `n / m file` | app.py:775–785; TC-06 (unit), TC-14 | Đạt |
| 5.10 | Hàng start + end chính + xlsx; zip riêng ≤ 5 / > 5 (selectbox); "Tải CSV:" 3 nút + manifest; file mất → disabled + caption | app.py:686–721; TC-08, TC-09, TC-10 | Đạt |
| 5.11 | `has_user_export` → `NOTE_USER_EXPORT`; caption thư mục kết quả | app.py:788–790; TC-11 | Đạt |
| 5 (cuối) | `data=functools.partial(Path.read_bytes, path)`, `on_click="ignore"` | app.py:689–691 | Đạt |
| 3.2/3.3 | `locked` → nút tải, ô lọc, `dl_separate_pick` disabled | app.py:691, 708–709, 777–780; TC-14 | Đạt (test thiếu 2 widget) |
| 6 | Dòng Tổng khi ≥ 1 user (cả khi chọn user) | app.py:303–308; TC-03 | Đạt |
| 6 | Kỳ không có commit: Commit 0, kiểm tra chéo đạt | TC-04 | Đạt (test không kiểm "đạt") |
| 6 | Thứ tự bảng giống `report` | app.py:287, 299, 319, 341 so với report.py:154–171 | Đạt |
| 8 | Token: chỉ hiện `repo.source` chuẩn hóa | app.py:254 | Đạt |
| 8 | **Nâng `streamlit>=1.66` trong `pyproject.toml` (A5)** | pyproject.toml:13 vẫn `>=1.40` | **Không đạt** |
| TC-01 … TC-14 | Mỗi TC có test, docstring bắt đầu bằng ID | test_app_result.py | Đạt (một số assertion yếu, xem Phát hiện) |

## Phát hiện

### [Major] Chưa nâng cận dưới Streamlit theo spec §8 / A5 — `pyproject.toml:13`
- **Mô tả:** Spec §8 ("Phiên bản") và A5 (đã chốt) yêu cầu đổi `streamlit>=1.40` thành `streamlit>=1.66`, vì `app.py:689–691` dùng `download_button(data=<callable>, on_click="ignore")`, hai tính năng mà Streamlit cũ không có. `pyproject.toml` vẫn ghi `"streamlit>=1.40"`, nên metadata của `uv.lock` cũng ghi `specifier = ">=1.40"` (uv.lock:469).
- **Kịch bản lỗi:** cài gói vào môi trường không dùng `uv.lock` (`pip install .`, hoặc `uv lock --upgrade-package streamlit` với ràng buộc khác, hoặc môi trường đã có Streamlit 1.4x). Resolver thấy 1.40–1.65 là hợp lệ. Khi đó màn hình kết quả hỏng ngay ở `_download` (app.py:689): Streamlit cũ báo lỗi kiểu `data` không hợp lệ, hoặc không nhận `on_click="ignore"`. Mọi lần phân tích xong đều crash ở luồng chính, dù test vẫn xanh trên máy dev (đang khóa 1.66.1).
- **Đề xuất sửa:** đổi thành `"streamlit>=1.66"` trong `pyproject.toml`, chạy `uv lock` (không đổi bản đang khóa), rồi chạy lại toàn bộ test.
- **Tham chiếu:** spec screen-result §8 "Phiên bản", §10 A5; CLAUDE.md quy tắc 3 (giá trị trong spec là bắt buộc); checklist 1 (đúng spec), 5 (tái lập).

### [Minor] TC-06: test `changed_only` không kiểm việc loại hàng — `tests/test_app_result.py:124-125`, `:134`
- **Mô tả:** cả hai hàng của §14 (`app.py` 10→12, `util.py` 0→8) đều có chênh lệch khác 0. Ở repo đổi tên, hàng duy nhất là hàng đổi tên, vốn được giữ lại. Không có ca nào trong đó `changed_only=True` phải **bỏ** một hàng.
- **Kịch bản lỗi:** nếu nhánh `if changed_only:` (app.py:334–335) bị xóa, hoặc điều kiện bị đổi thành luôn True, cả hai assertion vẫn đúng (2 hàng / 1 hàng). Test không phát hiện được.
- **Đề xuất sửa:** thêm vào frame một hàng `Chênh lệch == 0`, `Đổi tên từ == ""` (ví dụ dựng tay bằng `pd.DataFrame`, hoặc repo có file không đổi trong kỳ), rồi assert hàng đó bị loại.
- **Tham chiếu:** spec §3.2 (Chỉ file thay đổi), TC-screen-result-06; checklist 1 (test thật sự kiểm điều TC mô tả).

### [Minor] TC-14 chưa kiểm hết widget bị khóa — `tests/test_app_result.py:265-268`
- **Mô tả:** spec §3.2/§3.3 yêu cầu **mọi** ô lọc file disabled khi `locked`. Test chỉ kiểm `file_query` và `file_changed_only`, không kiểm `multiselect file_languages`, và không có ca kiểm `selectbox dl_separate_pick` (> 5 zip riêng) lúc locked. Code hiện đã đúng (app.py:708–709, 778–779), nhưng nếu sau này bỏ `disabled=locked` ở hai widget này thì test không bắt được.
- **Đề xuất sửa:** thêm `assert at.multiselect(key="file_languages").disabled`. Có thể thêm một ca locked có > 5 zip riêng (dùng cách của TC-09) để kiểm `dl_separate_pick` và `dl_separate`.
- **Tham chiếu:** TC-screen-result-14.

### [Minor] TC-08: assertion bytes là so một file với chính nó; chưa kiểm `data` của nút tải — `tests/test_app_result.py:163-165`
- **Mô tả:** `i.path` chính là `result.out_dir / i.path.name`, nên `i.path.read_bytes() == (result.out_dir / i.path.name).read_bytes()` luôn đúng. Phần AppTest chỉ kiểm key và cờ `disabled`, không kiểm callable `data` mà nút tải thực sự gọi (`functools.partial(Path.read_bytes, item.path)`), cũng không kiểm `file_name`/`mime` truyền cho nút. Assertion `i.mime == app.MIME[i.path.suffix]` dùng lại chính bảng của code, nên chỉ bắt được trường hợp đuôi file lạ.
- **Kịch bản lỗi:** nếu `_download` truyền nhầm `path` (ví dụ luôn truyền file đầu danh sách) hoặc nhầm `file_name`, toàn bộ test vẫn pass.
- **Đề xuất sửa:** so bytes với một nguồn độc lập (ví dụ `zipfile.ZipFile(i.path).namelist()` cho zip, `json.loads` cho manifest), và/hoặc monkeypatch `st.download_button` (hoặc đọc proto) để assert `file_name == path.name` và `data()` trả đúng bytes của file.
- **Tham chiếu:** TC-screen-result-08 (tiêu chí M6 "tải được mọi file").

### [Minor] TC-04 chưa kiểm "kiểm tra chéo đạt"; nhánh "Không có file source nào." chưa có test — `tests/test_app_result.py:93-103`, `src/loc_counter/app.py:744`
- **Mô tả:** spec §6 ("Kỳ không có commit … kiểm tra chéo đạt") không có assertion nào kiểm `st.success`. Thông báo `Không có file source nào.` (spec §7, dòng 1) không được test nào chạy tới (coverage: dòng 744).
- **Đề xuất sửa:** trong TC-04 thêm assert dòng `st.success` kết thúc bằng `→ đạt`. Thêm một ca nhỏ (repo chỉ có file bị loại, hoặc `ReportData` có `languages=()`) kiểm caption này.
- **Tham chiếu:** spec §6, §7.

### [Nit] Code trùng với CLI — `src/loc_counter/app.py:242-275`
- `signed`, `cross_check_text` và phần thân `users_text` là bản sao từng ký tự của `cli._signed`, `cli._check_text` và đoạn cli.py:311–317. A3 đã chấp nhận việc viết lại, nhưng nếu một bên đổi định dạng, hai bên sẽ lệch nhau mà không có test so sánh. Có thể thêm một test assert `app.cross_check_text(c) == cli._check_text(c)`, hoặc đưa hàm vào module lõi (`report`/`counter`) ở M7.

### [Nit] Helper private không có docstring — `src/loc_counter/app.py:292`, `:682`
- `_user_row`, `_table` không có docstring (CLAUDE.md quy tắc 4 chỉ yêu cầu docstring ngắn; hai hàm này là private).

### [Nit] Test import chéo giữa các file test — `tests/test_app_result.py:13`
- `from test_app_input import ...` làm hai file test phụ thuộc nhau. Các helper `analyze`, `load`, `pick_key`, `select_mode`, `set_period`, `values`, `IDS_YAML` nên chuyển sang `conftest.py` hoặc một module helper riêng.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | **Không đạt** | Luồng 5.1–5.11 đủ và đúng thứ tự; API công khai khớp §3.4, không có API ngoài spec. Lệch: chưa nâng `streamlit>=1.66` (Major). Mục 3/6/7 spec gốc không bị đụng. Mọi TC có test; TC-06/08/14 có assertion yếu (Minor). |
| 2. Nghiệp vụ dễ sai | Đạt | Màn hình chỉ đọc `ReportData`, không tính lại số liệu; Commit = Σ `user_rows.commits` (không tính merge), giống CLI; Tổng dùng `counter.total_metrics`. |
| 3. Bảo mật | Đạt | Chỉ hiện `data.repo` (= `repo.source` chuẩn hóa) và `out_dir`; không có token trong `ReportData`/`AnalysisResult`. Không gọi subprocess. |
| 4. Lỗi & log | Đạt | File mất → disabled + caption, không ném lỗi; lỗi đọc khi bấm tải do Streamlit báo (spec §7). |
| 5. Tái lập & encoding | Đạt | Thứ tự bảng trùng `report._sorted_*`; `download_items` theo thứ tự cố định; không hiện `generated_at`. Riêng ràng buộc phiên bản phụ thuộc: xem Major. |
| 6. Windows | Đạt | `pathlib` + `Path.read_bytes` (đóng handle ngay); key `dl_<tên file>` không phụ thuộc dấu phân cách đường dẫn. |
| 7. Chất lượng code | Đạt (có Nit) | Type hint đầy đủ; ruff sạch; không thêm thư viện; không có code chết. |
| 8. Hiệu năng | N/A | Màn hình không đếm LOC. Bytes chỉ đọc khi bấm tải (callable), dataframe dựng mỗi rerun (spec §8 chấp nhận). |
| 9. Màn hình Streamlit | Đạt | Nhãn tiếng Việt; bố cục theo §3.1; khóa widget khi `locked`; nghiệp vụ nằm trong pipeline/report; có AppTest; ghi chú §7.5 hiện khi có bản export end dựng theo user (cả "Tất cả user" + loại bot khi repo có bot, và xuất riêng). |

## Ghi chú cho spec
1. **Định dạng số không thống nhất:** metric dùng `f"{x:,}"`/`signed` (dấu phẩy, `0` không có dấu). Dataframe dùng `format="localized"` (dấu phân cách theo locale trình duyệt, ví dụ `1.234` với vi-VN) và `"%+d"` (không có dấu hàng nghìn, `0` thành `+0`, `1234` thành `+1234`). Cùng một số sẽ hiện khác nhau giữa metric, bảng và CLI. Cần người dùng quyết định có giữ như spec §3.4 hay thống nhất một định dạng.
2. **"Chỉ file thay đổi"** (§3.2) dựa trên `Chênh lệch != 0` hoặc có `Đổi tên từ`. File bị sửa nhưng số LOC không đổi (sửa một dòng, hoặc thêm và xóa cùng số dòng) sẽ bị ẩn. Nên ghi rõ trong spec hoặc nhãn là "LOC thay đổi".
3. Spec có `status: approved` trong khi code và test đã xong. Theo vòng đời trong CLAUDE.md, cần chạy `/feature-test screen-result` để chuyển sang `implemented` sau khi sửa Major.
