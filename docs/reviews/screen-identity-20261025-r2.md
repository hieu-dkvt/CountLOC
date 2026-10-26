# Review: screen-identity (lần 2, r2) — 2026-10-25
Kết luận: **FAIL**
Spec: docs/specs/screen-identity.md (status: approved, đã sửa A5–A8, TC-12)   Files: `src/loc_counter/app.py` (dòng 384–445 hàm thuần, 639–701 panel), `tests/test_app_identity.py`
Đối chiếu: `docs/reviews/screen-identity-20261025.md` (FAIL, 2 Major + 4 Minor + 2 Nit)

## Bằng chứng tự động
- ruff `src tests`: `All checks passed!`
- pytest `tests/test_app_identity.py`: 16 passed / 0 failed (45 s); toàn bộ suite: 744 passed / 0 failed.
- coverage `loc_counter.app` (chỉ test_app_identity): 69 % toàn file; phần panel (639–701) và hàm thuần (384–445) phủ 100 % dòng.
- Script kiểm chứng (AppTest, thư mục tạm `scratchpad/rv/test_probe.py`, `test_probe2.py`, nạp lại `tests/conftest.py`):
  - ô `None` qua `edited_rows` (dtype thật của bảng là `StringDtype(na_value=nan)`) → file `identities: []`, không còn `nan` (Major 1 cũ đã sửa);
  - `proto.id` của `identity_editor` **không đổi** khi đổi file identities làm đảo thứ tự hàng, và không đổi sau khi lưu;
  - gửi lại edit cũ sau khi đổi file (mô phỏng frontend) → Lưu bật lại, `other.yaml` thành `bob@example.com → team`;
  - thứ tự phụ thuộc giữa khóa tên và hàng xóa trống có email (xem Minor M1);
  - caption "giữ nguyên k quy tắc" sai khi xóa trống bỏ quy tắc tên (xem Minor M2).

## Trạng thái phát hiện của review trước
| Phát hiện cũ | Trạng thái | Bằng chứng |
|---|---|---|
| Major 1 — ô None lưu thành `"nan"` | **Đã sửa** | `_cell` (app.py:401-403) dùng `pd.isna`; AppTest probe với `{0: None, 1: None}` → `identities: []` |
| Major 2 — sửa đổi chưa lưu áp sang hàng khác | **Chỉ sửa ở phía server; chưa hết lỗi trên trình duyệt** | Xem Major mới dưới đây |
| M1 — gán + xóa trống cùng khóa phụ thuộc thứ tự | Đã sửa cho cùng khóa (A8) | `test_assign_and_clear_same_key_conflict`; còn trường hợp khác khóa (Minor M1 mới) |
| M2 — xóa trống hàng có account từ quy tắc tên | Đã sửa (A7) | `test_clear_removes_name_rule`; caption k sai (Minor M2 mới) |
| M3 — TC-01/TC-02 assert thiếu | Đã sửa (TC-01 khóa cột kiểm ở `test_no_authors_and_locked_columns`; TC-02 assert "chỉ còn") | test_app_identity.py:75, 262-266 |
| M4 — không test "Không có tác giả…" | Đã sửa | test_app_identity.py:267-270 |
| Nit — đếm k khi khóa tên chạm quy tắc email+name | Còn | app.py:679-683 |
| Nit — nhãn "Lưu vào " khi đường dẫn rỗng; `identity_panel` ngoài `_init_state` | Còn | app.py:686, 446-466 |

## Đối chiếu spec
| Mục | Yêu cầu | Code / test | Đạt |
|---|---|---|---|
| 3.2 / 5.1-1 | Nút `toggle_identities`, on_click, disabled khi locked | app.py:648-651; TC-10 | Đạt |
| 5.1-2 | container border, "**Gộp account**", success một lần | app.py:652-656; TC-02 | Đạt |
| 5.1-3 | identities_error → error + caption, không bảng | app.py:657-660; TC-07 | Đạt |
| 5.1-4 | ctx None → info; users rỗng → info | app.py:661-667; TC-11, TC-12 | Đạt |
| 5.1-5 | sig thay đổi → xóa state `identity_editor` (A6); data_editor fixed, hide_index, disabled Tên/Email | app.py:669-676; TC-12 `test_rows_change_drops_unsaved_edits`, `test_no_authors_and_locked_columns` | **Đạt trong AppTest, không đạt trên trình duyệt** (Major) |
| 5.1-6 | changed_rows + caption k | app.py:677-685; TC-03 | Đạt một phần (k sai khi A7 bỏ quy tắc tên — Minor M2) |
| 5.1-7 | Lưu disabled khi locked / chưa đổi / path rỗng | app.py:686-688; TC-01, TC-10, TC-12 | Đạt |
| 3.4 / A5 | None / NA = rỗng | app.py:401-413; TC-12 `test_empty_cells_are_blank` + probe | Đạt |
| 5.2-2 | upsert theo email / tên, giữ phần còn lại | app.py:428-444; TC-05, TC-09 | Đạt |
| 5.2-2 / A7 | xóa trống bỏ cả quy tắc tên của hàng | app.py:428, 432-433; TC-12 `test_clear_removes_name_rule` | Đạt |
| 5.2-3 / A8 | cùng khóa nhận hai giá trị (kể cả trống) → IdentityError, thông báo `(trống)` | app.py:423-427; TC-06, TC-12 | Đạt cho cùng khóa; còn phụ thuộc thứ tự giữa khóa email-xóa và khóa tên (Minor M1) |
| 5.2-4 | `dict.fromkeys`; save kiểm lại | app.py:445; TC-06, TC-09 | Đạt |
| 5.3 | save lỗi → st.error, file giữ nguyên; thành công → message, pop editor, rerun | app.py:691-701; TC-02, TC-06, TC-08 | Đạt (pop sau lưu có cùng hạn chế phía frontend — Major) |
| TC-01 → TC-11 | | test tương ứng | Đạt |
| TC-12 | 6 tình huống bổ sung | 4 test (`test_empty_cells_are_blank`, `test_assign_and_clear_same_key_conflict`, `test_clear_removes_name_rule`, `test_rows_change_drops_unsaved_edits`, `test_no_authors_and_locked_columns`) | Đủ tình huống; test A6 không mô phỏng được trình duyệt (Major) |

## Phát hiện

### [Major] Bản sửa A6 chỉ xóa state phía server; frontend vẫn giữ sửa đổi theo chỉ số hàng và gửi lại ở lần tương tác sau → sửa đổi vẫn bị áp sang người khác — `src/loc_counter/app.py:670-676`, `:700`
- **Mô tả**: `ss.pop("identity_editor")` chỉ xóa giá trị trong `SessionState` của server. Với `key` cố định và `num_rows="fixed"`, Streamlit 1.66 tính id phần tử theo chữ ký cấu trúc (`data_editor.py:1414-1439`, docstring dòng 1086-1093: *"preserves edits across reruns when the data's values change… Edits are matched by row position"*), nên id **không đổi** khi thứ tự / giá trị hàng đổi (đã kiểm chứng: `editor(at).proto.id` bằng nhau trước và sau khi đổi `identities_path`, và trước / sau khi Lưu). Phía frontend (`static/static/js/DataFrame.PZArLJF-.js`, hàm `Z_`): trạng thái sửa `J_` chỉ được tạo lại khi `originalNumRows` đổi (`xt(()=>{o.current=new J_(r)…},[r])`) hoặc khi form bị xóa; giá trị widget trong `WidgetStateManager` không bị server xóa (data_editor không hỗ trợ đặt giá trị từ server) và được gửi lại cùng mọi widget ở lần rerun kế tiếp. Lúc đó `sig` đã khớp → không pop nữa → edit cũ được áp theo chỉ số hàng.
- **Kịch bản lỗi** (§14, không file identities; `other.yaml` chứa `bob@example.com → aaa`):
  1. Mở panel, sửa hàng 0 (alice) → `team`, chưa lưu.
  2. Đổi ô "File identities" sang `other.yaml` → thứ tự hàng thành bob, alice. Server: Lưu disabled (test TC-12 chỉ kiểm tới đây). Trình duyệt: id không đổi → ô hàng 0 (giờ là bob) vẫn hiển thị `team`.
  3. Bất kỳ tương tác nào (vd. bấm vào ô khác, gõ ô tìm user) → frontend gửi lại `{"edited_rows": {0: {"Account key": "team"}}}` → `changes = [(bob, bob@example.com, team)]`, Lưu bật.
  4. Bấm Lưu → `other.yaml` thành `bob@example.com → team`, "Đã lưu 1 thay đổi" (đã tái hiện bước 3–4 bằng AppTest: gán lại state cũ sau khi đổi file).
  - Biến thể sau khi lưu thành công (TC-04): xóa trống alice, Lưu → file `[]`; tương tác kế tiếp gửi lại `{0: ""}` → bảng hiện ô trống, Lưu bật lại với "1 thay đổi" giả (probe `SAVE_ENABLED_AGAIN True`).
- **Mức kiểm chứng**: server-side và id phần tử: đã kiểm chứng bằng AppTest; hành vi frontend: kiểm chứng bằng đọc mã JS đóng gói của Streamlit 1.66.1, **chưa chạy trên trình duyệt thật**.
- **Đề xuất sửa**: đổi id phần tử khi tập hàng đổi hoặc sau khi lưu, thay vì `pop` — vd. giữ `ss.identity_editor_gen` (tăng khi `sig` đổi và khi lưu thành công) và dùng `key=f"identity_editor_{gen}"`; hoặc đặt index có nghĩa (vd. chuỗi `Tên\x00Email`, vẫn `hide_index=True`) để chữ ký chứa giá trị index → đảo/đổi hàng sinh id mới (docstring Streamlit gợi ý cách này). Test: assert `editor(at).proto.id` khác trước/sau khi đổi file identities và sau khi Lưu (đây là đại lượng AppTest đo được thay cho trạng thái frontend).
- **Tham chiếu**: spec 5.1-5, A6, §6 "Chỉ hàng đổi giá trị được ghi", TC-screen-identity-12.

### [Minor] M1 — Còn phụ thuộc thứ tự hàng khi hàng xóa trống (có email) bỏ quy tắc tên mà hàng khác (email rỗng) vừa gán — `src/loc_counter/app.py:423-444`
- **Mô tả**: A8 chỉ so cùng một khóa (`("Email", e)` hoặc `("Tên", n)`), nhưng A7 cho hàng xóa trống có email chạm cả quy tắc theo **tên**. Hai hàng cùng tên, một có email, một email rỗng, không cùng khóa nên không báo xung đột.
- **Kịch bản (đã kiểm chứng)**: `apply_identity_edits(IdentityMap(), [("alice", "", "acc"), ("alice", "a@x", "")])` → `()` (account `acc` mất im lặng, vẫn "Đã lưu 2 thay đổi"); đảo thứ tự → `(IdentityRule("acc", None, "alice"),)`.
- **Đề xuất**: khi `drop_name` do xóa trống, ghi thêm `assigned[("Tên", name.lower())] = ""` (setdefault + so sánh như A8) để báo `Tên alice được gán cho nhiều account: acc, (trống)`; thêm vào TC-12.
- **Tham chiếu**: spec A8 ("không phụ thuộc thứ tự hàng"), 5.2-3.

### [Minor] M2 — Caption "giữ nguyên k quy tắc" không tính quy tắc tên bị A7 bỏ — `src/loc_counter/app.py:679-683`
- **Mô tả**: `names` chỉ gom tên của hàng email rỗng; hàng có email bị xóa trống cũng bỏ quy tắc theo tên (A7) nhưng không được trừ khỏi `k`.
- **Kịch bản (đã kiểm chứng)**: file `name: alice → al`; xóa trống hàng alice → caption "giữ nguyên 1 quy tắc khác trong file." trong khi bấm Lưu sẽ xóa đúng quy tắc đó (file `[]`).
- **Đề xuất**: tính `k` từ kết quả thật: `k = sum(1 for r in identity_map.rules if r in new_rules)` với `new_rules = apply_identity_edits(...)` (bắt `IdentityError` để hiển thị lỗi sớm), hoặc thêm tên của hàng có `account == ""` vào `names`. Cách đầu cũng sửa Nit cũ (quy tắc email+name bị chạm một phần).
- **Tham chiếu**: spec 5.1-6 (`k` = số quy tắc không bị `changes` chạm tới).

### [Minor] M3 — Test A5 không dùng dtype thực tế của bảng, và không có AppTest với ô `None` — `tests/test_app_identity.py:214-221`
- `astype("string")` cho `StringDtype(na_value=pd.NA)`; bảng thật (pandas 3.1.0) là `StringDtype(na_value=nan)` — chính dtype gây lỗi `"nan"` ở review trước. Code hiện đúng cho cả hai (probe đã kiểm), nhưng test hồi quy không khóa trường hợp NaN. Đề xuất: thêm biến thể `pd.DataFrame(...)` mặc định (không `astype`) + gán `None`, hoặc AppTest `edit(at, {0: None})` trong TC-04.

### [Nit] `test_no_authors_and_locked_columns` import giữa thân hàm (`from datetime import date`, `import json`) — `tests/test_app_identity.py:257-260`
- Đưa lên đầu file.

### [Nit] TC-09 vẫn chưa có trường hợp strip tên / email trong `apply_identity_edits` — `tests/test_app_identity.py:140-158`

### [Nit] (còn từ review trước) nhãn "Lưu vào " khi đường dẫn rỗng; `identity_panel` không có trong `_init_state` — `src/loc_counter/app.py:686`, `:446-466`

## Checklist
| Nhóm | Kết quả | Ghi chú |
|---|---|---|
| 1. Đúng spec | Không đạt | A6 không hiệu lực trên trình duyệt (Major); A8 còn lỗ hổng khác khóa (M1); caption k (M2) |
| 2. Nghiệp vụ dễ sai | Một phần | Ưu tiên identities.yaml (email trước tên) giữ nguyên trong `AccountResolver.resolve`; lỗi UI có thể ghi quy tắc sai người vào identities.yaml |
| 3. Bảo mật | Đạt | Panel không đụng token, không subprocess |
| 4. Lỗi & log | Đạt | `IdentityError` tiếng Việt; `save_identities` log + ghi tạm/`os.replace`; M1 là trường hợp mất dữ liệu nhập không báo |
| 5. Tái lập & encoding | Đạt | `save_identities` sắp xếp cố định, UTF-8, `\n`; `identity_rows` theo thứ tự users |
| 6. Windows | Đạt | `pathlib`; file tạm được dọn khi lỗi |
| 7. Chất lượng code | Đạt | ruff sạch; type hint + docstring tiếng Việt; Nit import trong hàm test |
| 8. Hiệu năng | N/A | Bảng dựng từ ctx đã memo, không gọi git |
| 9. Streamlit | Một phần | Bố cục, nhãn, khóa khi chạy, AppTest đủ; vòng đời state data_editor phụ thuộc frontend (Major) |

## Ghi chú cho spec
1. **5.1-5 / A6 — cơ chế bỏ sửa đổi**: spec mô tả "xóa state `identity_editor`", nhưng với `st.data_editor` có `key` cố định việc này không đồng bộ được xuống frontend. Đề nghị spec quy định cơ chế đổi id phần tử (key theo thế hệ / index có nghĩa) cho cả hai thời điểm: tập hàng đổi và sau khi lưu thành công (5.3-3), kèm TC kiểm `proto.id` đổi.
2. **A8 mở rộng**: nêu rõ hàng xóa trống có email (A7 chạm quy tắc tên) cũng tham gia kiểm xung đột theo khóa tên.
3. **Quy tắc theo email/tên đã qua `.mailmap`**: bảng hiển thị email/tên gốc (`Identity(commit.author_name, commit.author_email)`), còn `resolve` cũng tra `mapped_email` / `mapped_name`. Nếu account của hàng đến từ quy tắc trên email/tên canonical của `.mailmap`, xóa trống hàng không chạm quy tắc đó → không có tác dụng nhưng vẫn báo "Đã lưu" (kiểm chứng bằng đọc code `identity.py:350-370`, `app.py:428-441`; chưa chạy). Cần quyết định: chấp nhận (ghi vào §6) hay xử lý.
