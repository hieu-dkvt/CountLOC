---
id: screen-result
title: Màn hình kết quả (số liệu, bảng, biểu đồ, cảnh báo, tải file)
type: screen
milestone: M6
modules: [src/loc_counter/app.py]
tests: [tests/test_app_result.py]
spec_refs: ["7.5", "8.1", "8.2", "8.3", "10.3", "12", "13", "15"]
depends_on: [screen-input, pipeline, report, counter]
status: reviewed
---

# Màn hình kết quả

## 1. Mục đích & phạm vi
Hiển thị `AnalysisResult` của lần phân tích gần nhất trong phiên (§10.3) ngay dưới nút PHÂN TÍCH của `screen-input`, và cho **tải mọi file** của thư mục kết quả (§12, §13 M6). Hàm vào: `render_result(result, stale, locked)` — `screen-input` gọi khi `session_state.result` khác None (thay dòng "Phân tích xong" tạm thời).

Ngoài phạm vi: tính số liệu (đã có trong `ReportData` — pipeline/report), sửa account (`screen-identity`).

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | Dòng đầu: Repo • Nhánh • Kỳ (múi giờ); dòng "User: …" | §10.3 |
| R2 | Bốn số: LOC start, LOC end, Chênh lệch (có dấu), Commit | §10.3, §8.1 |
| R3 | Bảng "Theo ngôn ngữ": Ngôn ngữ, LOC start, LOC end, Chênh lệch | §10.3 |
| R4 | Bảng "Theo user": User, Commit, Thêm, Xóa, Ròng, File thay đổi; "Tất cả user" có dòng **Tổng** | §10.3, §8.2 |
| R5 | Biểu đồ cột code ròng theo tuần, mỗi user một màu | §10.3 |
| R6 | "⚠ n cảnh báo (xem chi tiết)"; mục mở rộng "Cảnh báo" hiển thị nội dung `warnings.csv` | §10.3, §7.5 |
| R7 | Mục mở rộng "Chi tiết theo file": đường dẫn, ngôn ngữ, LOC start, LOC end, chênh lệch; có lọc và sắp xếp | §10.3 |
| R8 | Nút tải start.zip, end.zip, Excel, CSV, manifest — tải được **mọi file** §12 (cả zip riêng từng user, `warnings.csv`) | §10.3, §12, §13 |
| R9 | Ghi chú: bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được | §7.5 |
| R10 | Kiểm tra chéo lệch > 0.5 % chỉ là cảnh báo | §8.3 |

## 3. Giao diện

### 3.1 Bố cục (`st.container(border=True)` dưới nút PHÂN TÍCH)
```
KẾT QUẢ                                                                       (st.subheader)
(ⓘ Kết quả ứng với tham số của lần phân tích trước; bấm PHÂN TÍCH để cập nhật.)   khi stale
Repo: <source> • Nhánh: main • Kỳ: 2026-01-01 00:00 → 2026-01-31 23:59 (Asia/Bangkok, UTC+07:00)
User: Tất cả user [ (loại trừ bot)] [ • Xuất riêng từng user]
[LOC start 10] [LOC end 20] [Chênh lệch +10] [Commit 4]                       (4 × st.metric)
Kiểm tra chéo: 10 + (+10) = 20; LOC end 20; lệch 0.000 % (ngưỡng 0.5 %) → đạt   (success | warning)
Theo ngôn ngữ                     (st.dataframe, hide_index)
Theo user                         (st.dataframe) + Tổng (st.dataframe 1 dòng, tách riêng)
Code ròng theo tuần               (st.bar_chart x=Tuần, y=Code ròng, color=User, stack=False)
⚠ 2 cảnh báo (xem chi tiết)       (st.warning) | Không có cảnh báo. (st.caption)
▸ Cảnh báo                        (expander: dataframe + nút tải warnings.csv)
▸ Chi tiết theo file              (expander: ô lọc đường dẫn, multiselect ngôn ngữ, checkbox chỉ file thay đổi, dataframe)
Tải file
[Tải start_…zip] [Tải end_…_all.zip] … [Tải loc_report.xlsx]
Tải CSV: [loc_by_user.csv] [loc_by_language.csv] [loc_by_file.csv]   [Tải manifest.json]
Bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được.   (khi có bản dựng theo user)
Thư mục kết quả: <out_dir>        (st.caption)
```

### 3.2 Thành phần
| Thành phần | Widget | Key | Mặc định | Hành vi |
|---|---|---|---|---|
| Lọc đường dẫn | `text_input` | `file_query` | `""` | casefold "chứa" trên đường dẫn và "Đổi tên từ" |
| Lọc ngôn ngữ | `multiselect` | `file_languages` | `[]` (= mọi ngôn ngữ) | giữ hàng có ngôn ngữ trong danh sách |
| Chỉ file có LOC thay đổi hoặc đổi tên | `checkbox` | `file_changed_only` | `False` | giữ hàng `Chênh lệch != 0` hoặc có "Đổi tên từ" (file sửa mà LOC không đổi bị ẩn — đúng nhãn, A8) |
| Nút tải | `download_button(data=<callable đọc file>, file_name, mime, on_click="ignore")` | `dl_<tên file>` | — | `disabled` khi `locked` hoặc file không còn (+ `st.caption("Không còn file: <tên>")`) |
| Chọn zip riêng | `selectbox` | `dl_separate_pick` | zip riêng đầu tiên | chỉ khi > 5 zip riêng: 1 selectbox + 1 nút `dl_separate` |

### 3.3 Trạng thái
`hidden` (`result is None`) → `shown` → `stale` (tham số đổi, `screen-input` A9) → `shown` sau lần phân tích mới. Khi `locked` (đang chạy phân tích mới) các nút tải và ô lọc `disabled`.

### 3.4 Hàm thuần (mức module, test bằng pytest thường)
```python
NOTE_USER_EXPORT = "Bản export end theo user dùng để kiểm tra và đếm LOC, có thể không build/chạy được."
STALE_NOTE = "Kết quả ứng với tham số của lần phân tích trước; bấm PHÂN TÍCH để cập nhật."
SEPARATE_SELECT_MIN = 6           # > 5 zip riêng → selectbox
MIME = {".zip": "application/zip",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv", ".json": "application/json"}

def signed(value: int) -> str:            # 0 → '0', 1234 → '+1,234', -5 → '-5'
def header_text(data: ReportData) -> str: # dòng Repo • Nhánh • Kỳ (A2)
def users_text(data: ReportData) -> str:  # 'User: …' như CLI cli-analyze 4.1
def cross_check_text(check: CrossCheck) -> str   # như CLI (A3)
def language_frame(data) -> pd.DataFrame  # cột Ngôn ngữ, LOC start, LOC end, Chênh lệch; sắp (-loc_end, -loc_start, ngôn ngữ)
def user_frame(data) -> pd.DataFrame      # cột User, Bot, Commit, Thêm, Xóa, Ròng, File thay đổi; sắp (-commit, account)
def total_frame(data) -> pd.DataFrame | None     # 1 dòng 'Tổng' (counter.total_metrics) khi ≥ 1 user
def weekly_frame(data) -> pd.DataFrame    # cột Tuần, Bắt đầu tuần, User, Code ròng (từ data.weeks, giữ thứ tự)
def file_frame(data) -> pd.DataFrame      # cột Đường dẫn, Đổi tên từ, Ngôn ngữ, LOC start, LOC end, Chênh lệch; sắp đường dẫn
def filter_files(frame, query: str, languages: Sequence[str], changed_only: bool) -> pd.DataFrame
def warnings_frame(data) -> pd.DataFrame  # cột Loại, Đường dẫn, Nội dung, Phạm vi ('; '); sắp (path, kind) như warnings.csv
def has_user_export(data) -> bool         # có ExportSummary end/separate với accounts khác None

@dataclass(frozen=True)
class DownloadItem:
    label: str; path: Path; mime: str; key: str; group: str   # group: 'zip' | 'report' | 'csv' | 'warnings' | 'manifest'

def download_items(result: AnalysisResult) -> list[DownloadItem]:
    """start zip, các end zip (thứ tự data.exports[1:]), xlsx, 3 CSV, warnings.csv, manifest — mọi file §12."""
```
Cột số là `int` (dataframe sắp xếp đúng); hiển thị bằng `column_config.NumberColumn(format="localized")`; cột "Chênh lệch", "Ròng" dùng `format="%+d"`.

## 4. Dữ liệu vào / ra & giá trị mặc định
| Tên | Kiểu | Nguồn | Ghi chú |
|---|---|---|---|
| `result` | `AnalysisResult` | `session_state.result` (screen-input) | `out_dir`, `data`, `start_zip`, `end_zips`, `report_files` |
| `stale` | bool | `result_sig != current_sig` (screen-input A9) | |
| `locked` | bool | `run_requested` | |
| nhãn nút tải | str | `f"Tải {path.name}"` | |
| key nút tải | str | `f"dl_{path.name}"` | tên file trong một thư mục là duy nhất |

## 5. Luồng xử lý — `render_result(result, stale, locked)`
1. `data = result.data`; `with st.container(border=True)`: `st.subheader("KẾT QUẢ")`; `stale` → `st.info(STALE_NOTE)`.
2. `st.text(header_text(data))`, `st.text(users_text(data))`.
3. Bốn cột `st.metric`: `LOC start` = `f"{loc_start:,}"`, `LOC end`, `Chênh lệch` = `signed(loc_delta)`, `Commit` = `f"{Σ user_rows.commits:,}"` (không tính merge, §8.2).
4. `cross_check_text(data.cross_check)` → `st.success` khi `ok`, ngược lại `st.warning` (R10).
5. "Theo ngôn ngữ": `language_frame` rỗng → `st.caption("Không có file source nào.")`, ngược lại `st.dataframe(hide_index=True)`.
6. "Theo user": `user_frame` rỗng → `st.caption("Không có user nào có commit trong kỳ.")`; ngược lại dataframe + `total_frame` vẽ **riêng** (dataframe 1 dòng, không sắp lẫn) (D41-N16).
7. "Code ròng theo tuần": `weekly_frame` rỗng → `st.caption("Không có commit trong kỳ.")`; ngược lại `st.bar_chart(frame, x="Tuần", y="Code ròng", color="User", stack=False)`.
8. Cảnh báo: `n = len(data.warnings)`; `n > 0` → `st.warning(f"{n} cảnh báo (xem chi tiết)", icon="⚠️")` (Streamlit coi emoji đầu chuỗi là icon), ngược lại `st.caption("Không có cảnh báo.")`; `st.expander("Cảnh báo")`: `warnings_frame` (rỗng → caption) + nút tải `warnings.csv`.
9. `st.expander("Chi tiết theo file")`: ô lọc (3.2) → `filter_files(file_frame(data), …)` → `st.dataframe(hide_index=True)` + `st.caption(f"{len(filtered):,} / {len(all):,} file")`.
10. "Tải file": `items = download_items(result)`; zip start + zip end chính + xlsx một hàng cột; zip riêng: ≤ 5 → mỗi zip một nút; > 5 → selectbox `dl_separate_pick` + một nút `dl_separate`; "Tải CSV:" 3 nút; manifest. Mỗi nút: file không còn → `disabled` + `st.caption`.
11. `has_user_export(data)` → `st.caption(NOTE_USER_EXPORT)` (R9). Cuối: `st.caption(f"Thư mục kết quả: {result.out_dir}")`.

`data` của nút tải là callable `functools.partial(Path.read_bytes, path)` (đọc khi bấm, không giữ bytes trong bộ nhớ ở mỗi rerun — D41-N13); `on_click="ignore"` (không rerun).

## 6. Quy tắc nghiệp vụ & trường hợp biên
- **Dòng Tổng** khi có ≥ 1 user (cả khi chọn user) — thống nhất với CLI A6 và xlsx (D41-N16).
- **Kỳ không có commit**: bảng user và biểu đồ hiện thông báo rỗng; metric Commit `0`; kiểm tra chéo đạt.
- **Xuất riêng**: zip riêng có trong `download_items`; số liệu chính theo export gộp / `all` (pipeline D40-N17).
- **File bị xóa / di chuyển sau khi chạy**: nút disabled + "Không còn file: <tên>" (không lỗi).
- **Kết quả cũ** (stale): vẫn hiển thị đủ, có ghi chú (D41-N23).
- **Thứ tự** bảng như `report` (tái lập): ngôn ngữ (-loc_end, -loc_start, tên), user (-commit, account), file theo đường dẫn, cảnh báo (path, kind).

## 7. Xử lý lỗi & thông báo
| Tình huống | Hành vi | Thông báo |
|---|---|---|
| Không có file source | caption | `Không có file source nào.` |
| Không có user | caption | `Không có user nào có commit trong kỳ.` |
| Không có tuần | caption | `Không có commit trong kỳ.` |
| Không có cảnh báo | caption | `Không có cảnh báo.` |
| File kết quả không còn | nút disabled + caption | `Không còn file: <tên>` |
| Kiểm tra chéo lệch | `st.warning` | `Kiểm tra chéo: … → VƯỢT NGƯỠNG (xem warnings.csv)` |
| Lỗi đọc file khi bấm tải | Streamlit báo lỗi tải (callable ném `OSError`) | (của Streamlit) |

## 8. Bảo mật, hiệu năng, tái lập
- **Token:** không có trong `ReportData` / `AnalysisResult` (pipeline TC-25); màn hình chỉ hiện `repo.source` chuẩn hóa.
- **Hiệu năng:** dataframe dựng mỗi rerun từ `ReportData` (≈ 5.000 file chấp nhận được); bytes file chỉ đọc khi bấm tải.
- **Tái lập:** cùng thứ tự với `report`; không hiển thị `generated_at` ngoài manifest.
- **Phiên bản:** `download_button(data=callable)` cần Streamlit mới → nâng cận dưới `streamlit>=1.66` trong `pyproject.toml` (bằng bản đang khóa trong `uv.lock`, A5).

## 9. Test cases
Fixture: `analysis` (module scope) — dựng `section14_repo`-tương đương + identities gộp alice/bob, chạy `pipeline.run_analysis` thật cho các ca cần; AppTest E2E dùng `make_app` (conftest) + chuỗi thao tác của `test_app_input.py`.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-screen-result-01 | Số chính | AppTest §14 tất cả | `at.metric` nhãn `LOC start`, `LOC end`, `Chênh lệch`, `Commit` giá trị `10`, `20`, `+10`, `4` | AppTest |
| TC-screen-result-02 | Theo ngôn ngữ | `language_frame` §14 | 1 hàng `Python, 10, 20, 10`; cột đúng thứ tự | unit |
| TC-screen-result-03 | Theo user + Tổng | `user_frame`, `total_frame` §14 tất cả; chỉ alice | alice `2,5,2,3,1`, bob `2,8,1,7,2`, Tổng `4,13,3,10,2`; alice: 1 hàng + Tổng `2,5,2,3,1`; AppTest có 2 dataframe user (bảng + Tổng) | unit + AppTest |
| TC-screen-result-04 | Không có user | kỳ 2026-01-09..20 | `user_frame` rỗng, `total_frame is None`; caption `Không có user nào có commit trong kỳ.`, `Không có commit trong kỳ.`; Commit `0` | unit + AppTest |
| TC-screen-result-05 | Biểu đồ tuần | §14 | `weekly_frame` cột `Tuần, Bắt đầu tuần, User, Code ròng`, tổng `Code ròng` theo user = net (alice 3, bob 7); AppTest có phần tử biểu đồ | unit + AppTest |
| TC-screen-result-06 | Chi tiết theo file | `file_frame` + `filter_files` | 2 hàng `app.py`, `util.py`; lọc `UTIL` → 1; ngôn ngữ `["Python"]` → 2; `changed_only` → hàng có chênh lệch ≠ 0; repo đổi tên → cột `Đổi tên từ` | unit |
| TC-screen-result-07 | Cảnh báo + kiểm tra chéo | repo ca lệch (`build_cross_check_mismatch`) | `warnings_frame` có `cross_check`, phạm vi `kiểm tra chéo`; AppTest cảnh báo icon `⚠️` nội dung `1 cảnh báo (xem chi tiết)`, dòng kiểm tra chéo trong `st.warning` kết thúc `VƯỢT NGƯỠNG (xem warnings.csv)`; §14 → `Không có cảnh báo.` + `st.success` | unit + AppTest |
| TC-screen-result-08 | Tải mọi file (tiêu chí M6) | alice + bob xuất riêng | `{i.path.name for i in download_items(r)} == set(os.listdir(r.out_dir))` (10 file: 4 zip + 6 báo cáo); `i.path.read_bytes()` = bytes file; mime theo đuôi; nhóm `csv` có 3 mục; AppTest có đủ `download_button` (key `dl_<tên>`) và không disabled | unit + AppTest |
| TC-screen-result-09 | Nhiều zip riêng | `download_items` giả với 7 zip riêng (AnalysisResult dựng tay) | AppTest (hoặc hàm chia nhóm) → 1 selectbox `dl_separate_pick` 7 lựa chọn + 1 nút | unit + AppTest |
| TC-screen-result-10 | File không còn | xóa `warnings.csv` sau khi chạy rồi rerun | nút `dl_warnings.csv` disabled; caption `Không còn file: warnings.csv` | AppTest |
| TC-screen-result-11 | Dòng đầu / ghi chú | `header_text` §14 Bangkok; giờ start 08:30 tz UTC; chỉ alice | `Repo: … • Nhánh: main • Kỳ: 2026-01-01 00:00 → 2026-01-31 23:59 (Asia/Bangkok, UTC+07:00)`; `… 08:30 → … (UTC, UTC+00:00)`; alice → `has_user_export` True, caption `NOTE_USER_EXPORT`; tất cả → False | unit + AppTest |
| TC-screen-result-12 | Kết quả cũ | chạy rồi đổi end | `st.info(STALE_NOTE)`; số liệu cũ vẫn hiện | AppTest |
| TC-screen-result-13 | Định dạng | `signed(0/1234/-5)`, `users_text`, `cross_check_text` | `0`, `+1,234`, `-5`; `User: Tất cả user (loại trừ bot) • Xuất riêng từng user`; `User: alice, bob`; dòng kiểm tra chéo như CLI | unit |
| TC-screen-result-14 | Khóa khi chạy | `locked=True` (fake run như TC-screen-input-15) | mọi `download_button` và ô lọc file disabled | AppTest |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | Mọi quyết định D41 (N13–N17, N23, N24) áp dụng | PLAN D41 | Chốt (*) |
| A2 | Dòng đầu `Kỳ` dạng `YYYY-MM-DD HH:MM → … (<tz>, UTC±hh:mm)` (§10.3 ghi `(UTC+7)`; giữ tên múi giờ + độ lệch tại start) | D41-N24 | Chốt (*) |
| A3 | Dòng kiểm tra chéo dùng cùng định dạng với CLI (`cli-analyze` 4.1); viết lại trong `app.py` (không import hàm private của `cli`) | Khuyến nghị | Chốt (*) |
| A4 | CSV: một nút cho mỗi file (không gói zip — §12 không có file gói) dưới nhãn "Tải CSV:" | D41-N13 | Chốt (*) |
| A5 | Nâng `streamlit>=1.66` trong `pyproject.toml` (callable `data` cho `download_button`) — không thêm thư viện | Khuyến nghị | Chốt (*) |
| A6 | Cột Bot có trong bảng user (`bot` / rỗng) như CLI | D41-N16 | Chốt (*) |
| A7 | Ngưỡng > 5 zip riêng → selectbox | D41-N13 | Chốt (*) |
| A8 | Bộ lọc "chỉ file thay đổi" dựa trên LOC / đổi tên (dữ liệu `FileRow` không có cờ "có sửa"); nhãn ghi rõ `Chỉ file có LOC thay đổi hoặc đổi tên` | Khuyến nghị review | Chốt (*) |
| A9 | Định dạng số: metric `1,234` (chuỗi); bảng giữ cột số nguyên để sắp xếp đúng, hiển thị `localized` (theo trình duyệt) và `%+d` cho chênh lệch / ròng (0 hiện `+0`) — chấp nhận khác biệt nhỏ | Khuyến nghị review (giữ §3.4) | Chốt (*) |

(*) Chốt theo khuyến nghị, người dùng ủy quyền ("làm theo khuyến nghị", 2026-10-25); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-25 | Theo review `reviews/screen-result-20261025.md` (FAIL — Major `streamlit>=1.66` chưa nâng): nâng trong `pyproject.toml` + `uv lock`; A8 nhãn bộ lọc; A9 định dạng số; test TC-04, 06, 08, 14 chặt hơn. Chốt theo khuyến nghị | review Major + Minor |
| 2026-10-25 | Tạo mới theo PLAN M6 + D41. A1–A7 chốt theo khuyến nghị, người dùng ủy quyền → `approved` | M6 (`/feature-spec screen-result`) |
