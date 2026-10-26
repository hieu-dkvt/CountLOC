# Review: screen-identity — 2026-10-25
Kết luận: **FAIL**
Spec: docs/specs/screen-identity.md (status: approved)   Files: `src/loc_counter/app.py` (phần panel gộp account, dòng 384–437, 631–689), `tests/test_app_identity.py`

## Bằng chứng tự động
- ruff: `All checks passed!`
- pytest `tests/test_app_identity.py`: 11 passed / 0 failed; toàn bộ suite: 739 passed.
- coverage `loc_counter.app` (chỉ test_app_identity): 68 % toàn file; phần panel chỉ thiếu 658–659 (kỳ không có tác giả — không có test, xem Minor M4).
- Script kiểm chứng (AppTest, thư mục tạm `scratchpad/rv/test_probe.py`): tái hiện được 3 lỗi dưới đây.

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 3.2 / 5.1-1 | Nút `toggle_identities`, on_click, disabled khi locked | app.py:640-643; TC-10 | Đạt |
| 5.1-2 | container border, "**Gộp account**", success một lần | app.py:644-648; TC-02 | Đạt |
| 5.1-3 | identities_error → error + caption, không bảng | app.py:649-652; TC-07 | Đạt |
| 5.1-4 | ctx None → info; users rỗng → info | app.py:653-659; TC-11 / **không test users rỗng** | Đạt một phần |
| 5.1-5 | data_editor fixed, hide_index, disabled Tên/Email | app.py:661-664; TC-01 **không assert cột bị khóa** | Đạt một phần |
| 5.1-6 | changed_rows + caption "giữ nguyên k quy tắc" | app.py:665-673; TC-03 | Đạt (nhưng xem Major 1) |
| 5.1-7 | Nút Lưu disabled khi locked / chưa đổi / path rỗng | app.py:674-676; TC-01, TC-10 | Đạt |
| 5.2-1,2 | upsert theo email, khóa tên khi email rỗng, giữ phần name/email | app.py:414-436; TC-05, TC-06, TC-09 | Đạt |
| 5.2-3 | Xung đột trong cùng lần lưu → IdentityError | app.py:418-422; TC-06 | Đạt một phần (xem Minor M1) |
| 5.2-4 | `dict.fromkeys` bỏ trùng; save kiểm lại | app.py:437; TC-09 | Đạt |
| 5.3 | save → lỗi st.error / thành công message + pop editor + rerun | app.py:679-689; TC-02, TC-06, TC-08 | Đạt |
| §6 Ô rỗng | Ô rỗng = bỏ quy tắc | app.py:405 | **Không đạt** khi ô trả về None (Major 1) |
| §6 Chỉ hàng đổi | chỉ hàng đổi giá trị được ghi | app.py:401-408 | **Không đạt** khi dữ liệu bảng đổi mà state editor còn (Major 2) |
| TC-01 | bảng, cột không sửa được, Lưu disabled | test_table | Thiếu assert "cột Tên, Email không sửa được" |
| TC-02 | "danh sách user **chỉ còn** team (4 commit)" | test_merge | Chỉ assert có `team (4 commit)`, không assert alice/bob biến mất |
| TC-03 → TC-11 | | các test tương ứng | Đạt |

## Phát hiện

### [Major] Ô Account key bị xóa (giá trị None) được lưu thành account `"nan"` — `src/loc_counter/app.py:405`
- **Mô tả**: `identity_rows` tạo DataFrame từ list chuỗi; với pandas 3.1.0 (bản đang khóa trong venv) các cột có dtype `StringDtype(na_value=nan)`. Khi data_editor áp edit `None`, ô trở thành `NaN` (float), không phải `None`. Nhánh `... if after["Account key"] is not None else ""` không bắt được NaN → `str(nan) == "nan"` → được coi là account mới.
- **Kịch bản lỗi (đã kiểm chứng bằng AppTest)**: file `alice@example.com → alice`; mở panel; `identity_editor = {"edited_rows": {0: {"Account key": None}}}`; bấm Lưu → `Đã lưu 1 thay đổi…`, file thành `- email: alice@example.com / account: nan`. Nếu xóa trống cả hàng alice và bob (ý định: trả cả hai về gộp tự động) thì cả hai bị gộp vào **cùng account `nan`** → số liệu theo user sai.
- **Kích hoạt**: frontend Streamlit TextColumn gửi `e.data ?? null` (đọc `static/js/DataFrame.*.js`), và chính code đã giả định có None (nhánh `is not None`). Việc thao tác "xóa ô" trên trình duyệt thật gửi `null` hay `""` **chưa kiểm chứng trên trình duyệt**; nếu gửi `null` thì đây là Blocker (sai số liệu từ thao tác mà spec §6 mô tả là "bỏ quy tắc").
- **Đề xuất sửa**: dùng `pd.isna(value)` (hoặc `value is None or value != value`) → `""`; thêm test AppTest với `{"Account key": None}` cho TC-04.
- **Tham chiếu**: spec §6 "Ô rỗng", §3.4 `changed_rows`, TC-screen-identity-04.

### [Major] Sửa đổi chưa lưu bị áp vào sai người khi dữ liệu bảng thay đổi — `src/loc_counter/app.py:661-665`
- **Mô tả**: `st.data_editor(key=..., num_rows="fixed")` của Streamlit 1.66 lấy identity widget theo *chữ ký schema + số hàng*, không theo giá trị (`data_editor.py:1414-1439`, "keeps edits alive across pure value changes"). `edited_rows` lưu theo **chỉ số hàng**. Khi `users` đổi (đổi kỳ, nhánh, repo, hoặc ô `identities_path`) mà số hàng giữ nguyên, các edit cũ vẫn còn và được áp vào hàng khác. Code chỉ xóa state `identity_editor` sau khi lưu thành công.
- **Kịch bản lỗi (đã kiểm chứng bằng AppTest)**: §14, không có file; mở panel (hàng 0 = alice, hàng 1 = bob); sửa hàng 0 → `team` (ý định gộp alice); đổi ô "File identities" sang `other.yaml` (chứa `alice@example.com → zed`) → thứ tự hàng thành bob, alice; edit vẫn ở hàng 0 → `changes = [(bob, bob@example.com, team)]`; bấm Lưu → `other.yaml` có `bob@example.com → team`, thông báo "Đã lưu 1 thay đổi". Cùng cơ chế với đổi Start/End/nhánh (chưa chạy riêng từng trường hợp).
- **Đề xuất sửa**: lưu dấu vân tay của `original` (vd. tuple các (tên, email)) trong session_state; khác lần trước → `ss.pop("identity_editor")` trước khi vẽ editor; hoặc đưa vân tay vào `key` của data_editor. Thêm TC: sửa chưa lưu rồi đổi kỳ → bảng về trạng thái gốc, Lưu disabled.
- **Tham chiếu**: spec §6 "Chỉ hàng đổi giá trị được ghi", §5.1 bước 5–6, §8 "Bảng dựng từ ctx đã memo".

### [Minor] M1 — Xóa trống và gán account cho cùng một email trong một lần lưu: kết quả phụ thuộc thứ tự hàng, không báo lỗi — `src/loc_counter/app.py:419-420`
- **Mô tả**: `if account and previous and previous != account` bỏ qua trường hợp một trong hai giá trị rỗng.
- **Kịch bản (đã kiểm chứng)**: hai hàng `Alice Nguyen` / `alice` cùng `alice@example.com`, file `→ x`. Sửa hàng 0 → `b`, hàng 1 → `""`: file thành `identities: []` (account `b` mất im lặng), thông báo "Đã lưu 2 thay đổi". Đảo thứ tự (`""` rồi `b`) → giữ `b`.
- **Đề xuất**: coi `""` cũng là một giá trị khi so khóa (báo lỗi "được gán cho nhiều account: b, (trống)") hoặc chốt quy tắc rõ trong spec 5.2-3.

### [Minor] M2 — Xóa trống hàng có account đến từ quy tắc theo tên không có tác dụng nhưng vẫn báo "Đã lưu" — `src/loc_counter/app.py:418-433`
- **Kịch bản (đã kiểm chứng)**: file `name: Alice N → alice`; hàng `(Alice N, alice@y, alice)`; xóa trống → `changes` có 1 phần tử, khóa email `alice@y` không chạm quy tắc tên → file không đổi, account vẫn `alice`, thông báo "Đã lưu 1 thay đổi". Code đúng chữ spec 5.2 (email trước), nhưng trái kỳ vọng §6 "để trống để bỏ quy tắc của dòng đó". Xem Ghi chú cho spec.

### [Minor] M3 — Test TC-01, TC-02 chưa kiểm hết điều TC mô tả — `tests/test_app_identity.py:54-76`
- TC-01: không assert cột "Tên", "Email" bị khóa (vd. kiểm `column_config`/proto của editor).
- TC-02: không assert danh sách user **chỉ còn** `team (4 commit)` (alice/bob không còn trong caption).
- TC-09: không có trường hợp strip tên/email trong `apply_identity_edits` (chỉ strip account qua `changed_rows`).

### [Minor] M4 — Không có test cho nhánh "Không có tác giả nào có commit trong kỳ." — `src/loc_counter/app.py:657-659`
- Dòng 658–659 không được phủ; spec §7 liệt kê thông báo này. Không thuộc TC nào trong §9 → nên bổ sung TC.

### [Nit] Đếm "giữ nguyên k quy tắc" khi khóa tên chạm quy tắc có cả email + name — `src/loc_counter/app.py:667-671`
- Quy tắc `(acc, email, name)` bị chạm theo tên vẫn để lại phần email (5.2) nhưng không được tính vào `k`. Chỉ ảnh hưởng caption.

### [Nit] Nhãn nút "Lưu vào " khi đường dẫn rỗng; `identity_panel` không có trong `_init_state` — `src/loc_counter/app.py:674`, `:446-462`
- Nút đã disabled nên không sai hành vi; chỉ là nhãn cụt. `identity_panel` dùng `ss.get(..., False)` — chạy đúng nhưng lệch với cách khai báo mặc định tập trung.

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Không đạt | Major 1 (ô rỗng), Major 2 (chỉ hàng đổi); TC-01/02 assert thiếu |
| 2. Nghiệp vụ dễ sai | Một phần | Thứ tự ưu tiên identities.yaml giữ nguyên qua `AccountResolver`; lỗi ở tầng UI có thể ghi quy tắc sai vào identities.yaml |
| 3. Bảo mật | Đạt | Panel không đụng token; không subprocess |
| 4. Lỗi & log | Đạt | Lỗi tiếng Việt qua `IdentityError`; `save_identities` log khi ghi lỗi; M1 là trường hợp không báo |
| 5. Tái lập & encoding | Đạt | `save_identities` sắp xếp cố định, UTF-8, `\n`; `identity_rows` theo thứ tự users |
| 6. Windows | Đạt | `pathlib`; ghi tạm + `os.replace` |
| 7. Chất lượng code | Đạt | ruff sạch, type hint + docstring tiếng Việt; hàm thuần nằm trong app.py đúng spec 3.4 |
| 8. Hiệu năng | N/A | Bảng dựng từ ctx đã memo, không gọi git |
| 9. Streamlit | Một phần | Bố cục, nhãn, khóa khi chạy, AppTest có; state editor không được reset khi dữ liệu đổi (Major 2) |

## Ghi chú cho spec
1. **5.2 / §6 — hàng có email nhưng account đến từ quy tắc theo tên**: xóa trống hoặc sửa hàng đó chỉ tác động quy tắc email; quy tắc tên vẫn quyết định (khi xóa trống) → thao tác "không có tác dụng". Cần quyết định: (a) giữ như hiện tại, nhưng báo/khóa; (b) khi xóa trống mà không có quy tắc email nào bị chạm thì xóa quy tắc tên trùng tên hàng.
2. **5.2-3 — xung đột "xóa trống" với "gán account"** trên cùng khóa trong một lần lưu chưa được định nghĩa (M1).
3. **5.1-5 — vòng đời state `identity_editor`**: spec chỉ nói xóa sau khi lưu; cần thêm quy tắc reset khi tập hàng (tên, email) thay đổi (Major 2) và TC tương ứng.
4. **§7** có thông báo "Không có tác giả nào có commit trong kỳ." nhưng §9 không có TC.
