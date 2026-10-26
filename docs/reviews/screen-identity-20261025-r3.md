# Review: screen-identity (lần 3, r3) — 2026-10-25
Kết luận: **PASS_WITH_NOTES**
Spec: docs/specs/screen-identity.md (status: approved; lịch sử đã ghi bản sửa theo r2)   Files: `src/loc_counter/app.py` (384–450 hàm thuần, 644–707 panel), `tests/test_app_identity.py`
Đối chiếu: `docs/reviews/screen-identity-20261025-r2.md` (FAIL: 1 Major, 3 Minor, 3 Nit)

## Bằng chứng tự động
- ruff `src tests`: `All checks passed!`
- pytest `tests/test_app_identity.py`: 18 passed / 0 failed (36 s); toàn bộ suite: 746 passed / 0 failed (8 phút 49 giây).
- coverage `loc_counter.app` (chỉ chạy test_app_identity): 69 % toàn file; panel (644–707) và hàm thuần (384–450) phủ 100 % dòng.
- Kiểm chứng thêm (thư mục tạm `scratchpad/rv3/`, nạp lại `tests/conftest.py`):
  - `test_probe3.py`: đóng rồi mở lại panel có sửa đổi chưa lưu → cùng key `identity_editor_1`, cùng id, Lưu disabled; bắt đầu phân tích (locked) → `proto.id` **đổi** (vì `disabled` đổi); file hỏng → không có phần tử `identity_editor_*`; xóa trống hàng không có quy tắc → "Đã lưu 1 thay đổi", tạo file `identities: []`.
  - `test_probe4.py`: caption k đúng theo kết quả thật (file `name: alice → al` + `x@y.z → xyz`; xóa trống alice → "giữ nguyên 1"); đường dẫn rỗng → nhãn `"Lưu vào "`, nút disabled.
  - `prop.py`: 20 000 tổ hợp ngẫu nhiên (base 0–3 quy tắc, 1–3 hàng, gán / xóa trống, khác hoa thường), thử mọi hoán vị hàng → **0** trường hợp kết quả phụ thuộc thứ tự (so quy tắc đã đưa email/tên về chữ thường; chỉ còn khác chữ hoa/thường của chuỗi được ghi, tương đương khi tra cứu).
  - Mã frontend Streamlit 1.66.1 (`static/js/index.Dlja0TUX.js`): phần tử dataframe được render `c(rh,{element:e,…},e.id||void 0)`, tức React `key` = id phần tử → id đổi thì component DataFrame được mount lại (trạng thái sửa mới); `WidgetStateManager.removeInactive` xóa giá trị của id không còn hiện sau mỗi lần chạy. Đây là cơ sở để coi `proto.id` đổi (đo được trong AppTest) là đủ cho A6. Chưa chạy trên trình duyệt thật.

## Trạng thái phát hiện của review trước (r2)
| Phát hiện r2 | Trạng thái | Bằng chứng |
|---|---|---|
| Major — xóa state phía server không reset frontend | **Đã sửa** | key `identity_editor_<gen>` (app.py:675-681), tăng khi `sig` đổi và khi lưu thành công (app.py:706); `test_rows_change_drops_unsaved_edits` assert `proto.id` đổi ở cả hai thời điểm (test:254-262); React key = id phần tử (mã JS ở trên) |
| M1 — A8 khác khóa (gán theo tên + xóa trống có email cùng tên) | Đã sửa | app.py:423-424 (xóa trống chiếm khóa tên); `test_mixed_key_conflict` thử cả hai thứ tự; `prop.py` 0 trường hợp phụ thuộc thứ tự |
| M2 — caption k không trừ quy tắc tên bị A7 bỏ | Đã sửa (chưa có test hồi quy — xem Minor 2) | app.py:684-688; probe `CAP_A7` → 1 |
| M3 — A5 không test dtype thật / không có AppTest ô `None` | Đã sửa | `test_none_cell_via_apptest` (test:266-274) |
| Nit — import giữa thân hàm test | Còn | test:119, 231, 279, 288, 291 |
| Nit — TC-09 không có strip tên/email trong `apply_identity_edits` | Còn | test:145-163 |
| Nit — nhãn "Lưu vào " khi đường dẫn rỗng; `identity_panel` ngoài `_init_state` | Còn | app.py:691, 459-475 |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 3.2 / 5.1-1 | `toggle_identities`, on_click, disabled khi locked | app.py:653-656; TC-10 `test_locked` | Đạt |
| 5.1-2 | container border, "**Gộp account**", success một lần | app.py:657-661; TC-02 `test_merge` | Đạt |
| 5.1-3 | identities_error → error + caption, không bảng | app.py:662-665; TC-07 `test_broken_or_missing_file` | Đạt (code); assert "không bảng" vô hiệu — Minor 1 |
| 5.1-4 | ctx None / users rỗng → info | app.py:666-671; TC-11, TC-12 | Đạt |
| 5.1-5 / A6 | `sig` đổi → tăng `identity_editor_gen`; key `identity_editor_<gen>`; lưu thành công cũng tăng; fixed, hide_index, disabled Tên/Email (locked → toàn bảng) | app.py:674-681, 706; TC-12 `test_rows_change_drops_unsaved_edits`, `test_no_authors_and_locked_columns`, TC-10 | Đạt |
| 5.1-6 | caption k = số quy tắc còn nguyên trong `apply_identity_edits(...)`; xung đột → tổng | app.py:684-690; TC-03 (chỉ khi chưa sửa) | Đạt (thiếu test sau khi sửa — Minor 2) |
| 5.1-7 | Lưu disabled khi locked / chưa đổi / path rỗng | app.py:691-693; TC-01, TC-10, TC-12; probe đường dẫn rỗng | Đạt |
| 3.4 / A5 | None / NA = rỗng | app.py:401-403; `test_empty_cells_are_blank`, `test_none_cell_via_apptest` | Đạt |
| 5.2-2 | upsert theo email / tên; giữ phần còn lại (A3) | app.py:429-449; TC-05, TC-09 | Đạt |
| 5.2-2 / A7 | xóa trống bỏ cả quy tắc tên | app.py:433, 437-438; `test_clear_removes_name_rule` | Đạt |
| 5.2-3 / A8 | cùng khóa nhận hai giá trị (kể cả trống; hàng xóa trống có email chiếm cả khóa tên) → `IdentityError`, `(trống)` | app.py:419-429; TC-06, `test_assign_and_clear_same_key_conflict`, `test_mixed_key_conflict`; `prop.py` | Đạt |
| 5.2-4 | `dict.fromkeys`; `save_identities` kiểm lại | app.py:450; TC-06 | Đạt |
| 5.3 | lỗi → st.error, file giữ nguyên; thành công → message, gen mới, rerun | app.py:696-707; TC-02, TC-06, TC-08 | Đạt |
| §6 | chỉ hàng đổi; ô rỗng; giữ quy tắc ngoài kỳ; file chưa có; tái lập | `changed_rows`; TC-03, TC-04, TC-07; `save_identities` sắp xếp | Đạt |
| TC-01 … TC-11 | | test tương ứng (docstring bắt đầu bằng ID) | Đạt (TC-07 xem Minor 1) |
| TC-12 | 6 tình huống | `test_empty_cells_are_blank`, `test_rows_change_drops_unsaved_edits`, `test_assign_and_clear_same_key_conflict`, `test_clear_removes_name_rule`, `test_no_authors_and_locked_columns`, + `test_none_cell_via_apptest`, `test_mixed_key_conflict` | Đạt |

## Phát hiện

### [Minor] 1 — TC-07: assert "không vẽ bảng" luôn đúng sau khi đổi key — `tests/test_app_identity.py:172`
- **Mô tả**: `assert not [d for d in at.dataframe if d.key == "identity_editor"]` so với key cũ; key hiện là `identity_editor_<gen>` (probe: `KEYS ['identity_editor_1']`) nên danh sách luôn rỗng, kể cả khi panel vẫn vẽ bảng lúc file hỏng.
- **Kịch bản**: bỏ `return` ở app.py:665 → bảng hiện cạnh thông báo lỗi; TC-07 vẫn pass. (Code hiện tại đúng: probe file hỏng → `BROKEN KEYS []`.)
- **Đề xuất**: `assert not [d for d in at.dataframe if (d.key or "").startswith("identity_editor_")]` (hoặc dùng helper `editor` với `pytest.raises(StopIteration)`).
- **Tham chiếu**: spec 5.1-3, TC-screen-identity-07.

### [Minor] 2 — Không có test hồi quy cho caption k sau khi sửa (bản sửa M2 của r2) — `src/loc_counter/app.py:684-690`, `tests/test_app_identity.py:84-95`
- **Mô tả**: Lịch sử spec ghi "caption đếm quy tắc từ kết quả thật", code đã đúng (probe `CAP_A7` = 1, `CAP_2` = 2), nhưng TC-03 chỉ kiểm caption khi chưa sửa (k = mọi quy tắc). Nếu quay lại cách đếm cũ (chỉ trừ tên của hàng email rỗng) không test nào báo.
- **Đề xuất**: trong `test_clear_removes_name_rule` assert caption `giữ nguyên 0 quy tắc khác` sau `edit(at, {0: ""})`, trước khi Lưu; thêm trường hợp quy tắc email+name bị tách (k giảm 1).
- **Tham chiếu**: spec 5.1-6.

### [Nit] Bắt đầu phân tích làm mất sửa đổi chưa lưu, không báo — `src/loc_counter/app.py:679-681`
- `disabled` đổi từ `["Tên","Email"]` sang `True` làm id phần tử đổi (probe `LOCK id same False`) → khi locked frontend mount bảng mới; sau khi chạy xong id quay lại nhưng trạng thái cũ đã bị `removeInactive` xóa. Hai phía nhất quán (không ghi sai), chỉ là sửa đổi biến mất. Spec 3.3 không nói; có thể chấp nhận hoặc ghi vào §6.

### [Nit] (còn từ r2) import giữa thân hàm test — `tests/test_app_identity.py:119, 231, 279, 288, 291`
### [Nit] (còn từ r2) TC-09 chưa có trường hợp strip tên / email trong `apply_identity_edits` — `tests/test_app_identity.py:145-163`
### [Nit] (còn từ r2) nhãn `"Lưu vào "` khi đường dẫn rỗng (probe xác nhận); `identity_panel`, `identity_editor_gen`, `identity_rows_sig` không có trong `_init_state` (dùng `ss.get`) — `src/loc_counter/app.py:691`, `:459-475`

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Đạt | Mọi bước 5.1–5.3 có trong code đúng thứ tự; chữ ký 3 hàm thuần đúng 3.4; TC-01…12 có test (Minor 1, 2 là độ mạnh assert) |
| 2. Nghiệp vụ dễ sai | Đạt | Panel chỉ ghi `identities.yaml` qua `save_identities`; ưu tiên gộp (identities > .mailmap > GitHub > email) nằm trong `identity`, không đổi; A8 không phụ thuộc thứ tự (prop.py) |
| 3. Bảo mật | Đạt | Không đụng token, không subprocess; file chỉ có tên / email / account |
| 4. Lỗi & log | Đạt | `IdentityError` tiếng Việt hiển thị bằng `st.error`; `save_identities` log + ghi tạm / `os.replace`; không nuốt lỗi (preview bắt `LocCounterError` chỉ để tính k, lỗi vẫn báo khi Lưu) |
| 5. Tái lập & encoding | Đạt | `identity_rows` theo thứ tự users; `save_identities` sắp xếp `(account, email, name)`, UTF-8, `\n` |
| 6. Windows | Đạt | `pathlib`; đường dẫn tương đối CWD; file tạm được dọn khi lỗi |
| 7. Chất lượng code | Đạt | ruff sạch; type hint + docstring tiếng Việt; không code chết |
| 8. Hiệu năng | N/A | Bảng dựng từ `ctx` đã memo, không gọi git |
| 9. Streamlit | Đạt | Bố cục, nhãn tiếng Việt, khóa khi chạy, AppTest đầy đủ; vòng đời state `data_editor` đã gắn với id phần tử |

## Ghi chú cho spec
1. **Văn bản cũ còn sót sau khi đổi sang key theo thế hệ**: 3.1 (sơ đồ: "key identity_editor"), 3.2 (cột Key `identity_editor`; "Trạng thái phi widget" thiếu `identity_editor_gen`, `identity_rows_sig`), 5.3 bước 3 ("xóa state `identity_editor`" — code tăng `identity_editor_gen`, đúng theo 5.1-5), §9 fixture (`at.session_state["identity_editor"]` — test dùng `identity_editor_<gen>`). Nên sửa cho thống nhất với 5.1-5.
2. **Xóa trống hàng không có quy tắc** (account tự động): được tính là 1 thay đổi, lưu "thành công" và tạo file `identities: []` dù không có gì thay đổi (probe `CLEAR_AUTO`). Đúng chữ của spec (5.3 đếm `len(changes)`), nhưng gây hiểu nhầm; cần quyết định có bỏ qua / báo "không có quy tắc để bỏ" hay giữ nguyên.
3. **(còn từ r2, chưa có quyết định)** quy tắc trên email / tên canonical của `.mailmap`: bảng hiển thị email / tên gốc, `resolve` còn tra `mapped_email` / `mapped_name`; xóa trống hàng có account đến từ quy tắc trên giá trị canonical không chạm quy tắc đó nhưng vẫn báo "Đã lưu". Cần ghi vào §6 (chấp nhận) hoặc xử lý.
4. Bắt đầu phân tích làm mất sửa đổi chưa lưu (Nit ở trên) — nếu chấp nhận, ghi vào 3.3 / §6.
