---
id: screen-identity
title: Quản lý gộp account (bảng tên, email, account key → identities.yaml)
type: screen
milestone: M6
modules: [src/loc_counter/app.py]
tests: [tests/test_app_identity.py]
spec_refs: ["3.5", "10.2", "16"]
depends_on: [screen-input, identity]
status: reviewed
---

# Quản lý gộp account

## 1. Mục đích & phạm vi
Nút **"Quản lý gộp account"** ở khối [3] của `screen-input` mở một panel: bảng (tên, email, account key) của mọi tác giả có commit trong kỳ, cho sửa **account key** rồi lưu vào `identities.yaml` (đường dẫn ở ô `identities_path` của `screen-input`, mặc định `./identities.yaml`). Sau khi lưu, danh sách user được tính lại ngay (account đã gộp, §10.2 [3]).

Ngoài phạm vi: thứ tự ưu tiên gộp, đọc/ghi YAML (`identity` — `load_identities`, `save_identities`, D16); quy tắc theo tên do người dùng tự viết tay vẫn được giữ.

## 2. Yêu cầu từ spec gốc
| # | Yêu cầu | Mục |
|---|---|---|
| R1 | "Quản lý gộp account": bảng (tên, email, account key) cho phép sửa account key, lưu vào `identities.yaml` | §10.2 [3] |
| R2 | `identities.yaml` có ưu tiên cao nhất khi gộp; định dạng D16 (`email` hoặc `name` → `account`) | §3.5 |
| R3 | Danh sách user là account đã gộp → cập nhật sau khi lưu | §10.2 [3] |
| R4 | Khóa khi đang phân tích | §10.2 |

## 3. Giao diện

### 3.1 Bố cục (trong khối [3], sau checkbox "Loại trừ bot" / "Xuất riêng")
```
[ Quản lý gộp account ]                                   key toggle_identities (bật/tắt panel)
┌ Gộp account ─────────────────────────────────────────────────────────┐
│ Sửa cột Account key rồi bấm Lưu; để trống để bỏ quy tắc của dòng đó.  │
│ Tên      Email                 Account key                           │  st.data_editor key identity_editor
│ alice    alice@example.com     alice@example.com   (sửa được)        │
│ bob      bob@example.com       bob@example.com                       │
│ File: identities.yaml — giữ nguyên 2 quy tắc khác trong file.        │  (caption)
│ [ Lưu vào identities.yaml ]                               key save_identities │
│ ✔ Đã lưu 2 thay đổi vào D:\…\identities.yaml.                        │  (success, một lần)
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Thành phần
| Thành phần | Widget | Key | Mặc định | Validate | Khi thay đổi |
|---|---|---|---|---|---|
| Quản lý gộp account | `button(on_click=_toggle_identity_panel)` | `toggle_identities` | panel đóng (`identity_panel = False`) | disabled khi `locked` | đảo `identity_panel` |
| Bảng | `data_editor(hide_index=True, num_rows="fixed", disabled=["Tên", "Email"])` | `identity_editor_<gen>` (A6) | `identity_rows(users)` | — | chỉ cột "Account key" sửa được |
| Lưu | `button(type="primary")` | `save_identities` | — | disabled khi `locked`, chưa có thay đổi, đường dẫn rỗng hoặc file identities hỏng | 5.3 |

Trạng thái phi widget: `identity_panel: bool` (False), `identity_message: str | None` (thông báo thành công, hiện một lần).

### 3.3 Trạng thái
`closed` → (bấm nút) `open` → (`locked`) `open-disabled` → `open` | `closed`. Không có `ctx` (chưa tải repo / kỳ lỗi) → panel hiện `st.info("Cần tải repo và chọn kỳ hợp lệ để có danh sách tác giả.")`.

### 3.4 Hàm thuần
```python
IDENTITY_COLUMNS = ("Tên", "Email", "Account key")

def identity_rows(users: Sequence[UserSummary]) -> pd.DataFrame:
    """Mỗi Identity (tên, email gốc) của users một hàng; thứ tự users rồi identities; bỏ trùng (tên, email);
    Account key = account hiện tại của user."""

def changed_rows(original: pd.DataFrame, edited: pd.DataFrame) -> list[tuple[str, str, str]]:
    """[(tên, email, account_mới đã strip)] cho hàng có Account key khác bản gốc (so sau strip);
    ô trống / None / NA (pandas StringDtype) = chuỗi rỗng (A5)."""

def apply_identity_edits(base: IdentityMap, changes: Sequence[tuple[str, str, str]]) -> IdentityMap:
    """Upsert quy tắc theo D41-N6 (5.2); không ghi file."""
```

## 4. Dữ liệu vào / ra
| Tên | Kiểu | Nguồn | Ghi chú |
|---|---|---|---|
| `users` | `list[UserSummary]` | `ctx.users.users` (screen-input) | gồm cả bot |
| `identity_map` | `IdentityMap` | file ở `identities_path` (screen-input 5.3 bước 3) | rỗng khi file chưa có |
| đường dẫn lưu | `Path` | `identities_path.strip()` (tương đối CWD) | chưa có → tạo khi lưu |

## 5. Luồng xử lý

### 5.1 Vẽ (`render_identity_panel(locked, ctx, identity_map, identities_error)` — `screen-input` gọi ở cuối 5.4)
1. `st.button("Quản lý gộp account", key="toggle_identities", on_click=_toggle_identity_panel, disabled=locked)`; `identity_panel` False → dừng.
2. `with st.container(border=True)`: `st.markdown("**Gộp account**")`. `identity_message` → `st.success(...)` rồi xóa (hiện một lần).
3. `identities_error` → `st.error(identities_error)` + caption "Sửa file hoặc đổi đường dẫn rồi thử lại."; không vẽ bảng.
4. `ctx is None` → `st.info(...)` (3.3), dừng. `users` rỗng → `st.info("Không có tác giả nào có commit trong kỳ.")`, dừng.
5. `original = identity_rows(users)`; `sig = tuple(map(tuple, original.values.tolist()))`; `sig != identity_rows_sig` → tăng `identity_editor_gen` và lưu `identity_rows_sig = sig` (A6 — `data_editor` lưu sửa đổi theo **chỉ số hàng**, và frontend chỉ reset khi id phần tử đổi: key cố định giữ nguyên id nên phải đổi key); `edited = st.data_editor(original, key=f"identity_editor_{identity_editor_gen}", …, disabled=locked or ["Tên", "Email"])`. Lưu thành công cũng tăng `identity_editor_gen`.
6. `changes = changed_rows(original, edited)`; caption `File: <path> — giữ nguyên <k> quy tắc khác trong file.` (`k` = số quy tắc của `identity_map` còn nguyên trong `apply_identity_edits(identity_map, changes)`; xung đột → `k` = tổng số quy tắc).
7. `st.button(f"Lưu vào {path_text}", key="save_identities", type="primary", disabled=locked or not changes or not path_text)`; bấm → 5.3.

### 5.2 `apply_identity_edits(base, changes)`
1. `rules = list(base.rules)`.
2. Với mỗi `(name, email, account)` theo thứ tự `changes`:
   - `email.strip()` khác rỗng → **khóa email** `e = email.strip().lower()`: với mỗi quy tắc có `rule.email.lower() == e`: có `name` → thay bằng `IdentityRule(rule.account, None, rule.name)` (giữ phần theo tên), không có → bỏ. Rồi nếu `account` khác rỗng → thêm `IdentityRule(account, email.strip(), None)`.
   - email rỗng → **khóa tên** tương tự với `rule.name.lower() == name.strip().lower()` (giữ phần email nếu có); `account` khác rỗng → thêm `IdentityRule(account, None, name.strip())`.
   - `account` rỗng (xóa trống) → bỏ thêm cả phần **theo tên** của hàng (quy tắc có `rule.name.lower() == name.lower()`; giữ phần email nếu có) để account thật sự quay về tự động (A7).
3. Trong cùng một lần lưu, một khóa (email chữ thường / tên chữ thường) nhận hai giá trị khác nhau — hai account khác nhau, **hoặc** một account và một ô trống (A8; hàng xóa trống có email chiếm cả khóa email lẫn khóa tên của nó vì A7 bỏ cả quy tắc tên) → `IdentityError("Email <e> được gán cho nhiều account: <a>, <b>")` (hoặc `Tên …`) — cùng định dạng thông báo của `identity`; không ghi file.
4. Trả `IdentityMap(tuple(dict.fromkeys(rules)))` (bỏ trùng, giữ thứ tự); `save_identities` kiểm lại toàn bộ (xung đột với quy tắc khác trong file).

### 5.3 Lưu
1. `path = Path(identities_path.strip())`; `new_map = apply_identity_edits(identity_map, changes)`.
2. `save_identities(path, new_map)` — `IdentityError` (xung đột, không ghi được) → `st.error(str(err))`, file giữ nguyên.
3. Thành công: `identity_message = f"Đã lưu {len(changes)} thay đổi vào {path.resolve()}."`; tăng `identity_editor_gen` (bảng mới); `st.rerun()` → lần chạy sau `screen-input` đọc lại file → `IdentityMap` mới → khóa memo đổi → `prepare_period` với resolver mới (account đã gộp); `reconcile_selection` bỏ account không còn (vd. alice gộp thành `team`) kèm `st.info`.

## 6. Quy tắc nghiệp vụ & trường hợp biên
- **Chỉ hàng đổi giá trị** được ghi; hàng giữ nguyên account hiển thị không tạo quy tắc mới (không "đóng băng" account tự động).
- **Ô rỗng** = bỏ quy tắc theo email (hoặc tên) của hàng đó → account quay về cách gộp tự động (`.mailmap`, GitHub, email).
- **Quy tắc không có hàng tương ứng** (tác giả ngoài kỳ, quy tắc theo tên viết tay) giữ nguyên.
- **File chưa có**: bảng dùng được; lưu lần đầu tạo file (thư mục cha phải tồn tại — lỗi do `save_identities` báo).
- **Bot**: có hàng như user khác; gộp bot vào account thường làm account đó mất nhãn bot nếu không còn dấu hiệu bot (theo `identity`).
- **Tái lập**: `save_identities` ghi thứ tự cố định `(account, email, name)`.

## 7. Xử lý lỗi & thông báo
| Tình huống | Hành vi | Thông báo |
|---|---|---|
| File identities hỏng | panel không vẽ bảng | thông báo `IdentityError` + `Sửa file hoặc đổi đường dẫn rồi thử lại.` |
| Chưa có repo / kỳ lỗi | info | `Cần tải repo và chọn kỳ hợp lệ để có danh sách tác giả.` |
| Kỳ không có tác giả | info | `Không có tác giả nào có commit trong kỳ.` |
| Xung đột khi lưu / không ghi được | `st.error`, file giữ nguyên | thông báo `IdentityError` (vd. `Email alice@example.com được gán cho nhiều account: a, b`) |
| Lưu xong | `st.success` (một lần) | `Đã lưu <n> thay đổi vào <path>.` |

## 8. Bảo mật, hiệu năng, tái lập
- Không liên quan token; file chỉ chứa tên / email / account (người dùng tự chọn đường dẫn).
- Bảng dựng từ `ctx` đã memo — không gọi git.
- Ghi file qua `save_identities` (ghi tạm rồi `os.replace`).

## 9. Test cases
Fixture: `make_app`, helper `load` / `analyze` / `pick_key` của `test_app_input.py`; sửa bảng bằng `at.session_state[f"identity_editor_{gen}"] = {"edited_rows": {i: {"Account key": v}}, "added_rows": [], "deleted_rows": []}` rồi `at.run()`.

| ID | Mô tả | Input / fixture | Kết quả mong đợi | Loại |
|---|---|---|---|---|
| TC-screen-identity-01 | Bảng | §14, không có file identities; mở panel | 2 hàng `(alice, alice@example.com, alice@example.com)`, `(bob, bob@example.com, bob@example.com)`; cột Tên, Email không sửa được; nút Lưu disabled (chưa đổi) | AppTest + unit |
| TC-screen-identity-02 | Gộp | sửa 2 hàng thành `team` rồi Lưu | file có 2 quy tắc email → `team`; danh sách user chỉ còn `team (4 commit)`; `st.success` `Đã lưu 2 thay đổi vào …` | AppTest |
| TC-screen-identity-03 | Giữ quy tắc ngoài kỳ | file có `x@y.z → xyz` và quy tắc theo tên `Alice N → alice`; sửa bob → `b2` | sau lưu file còn `x@y.z`, `Alice N`; thêm `bob@example.com → b2`; caption `giữ nguyên 2 quy tắc khác` | AppTest |
| TC-screen-identity-04 | Xóa quy tắc | file `alice@example.com → alice`; xóa trống ô hàng alice, Lưu | quy tắc bị xóa; account về `alice@example.com` | AppTest |
| TC-screen-identity-05 | Email rỗng | `apply_identity_edits` với `("Bình", "", "binh")` | quy tắc `IdentityRule("binh", None, "Bình")` | unit |
| TC-screen-identity-06 | Xung đột | hai hàng cùng email (identity khác tên) sửa thành `a`, `b` | `IdentityError` hiển thị; file không đổi | unit + AppTest |
| TC-screen-identity-07 | File hỏng / chưa có | YAML sai; file vắng | hỏng → lỗi trong panel, không bảng, PHÂN TÍCH disabled (screen-input); vắng → bảng dùng được, Lưu tạo file | AppTest |
| TC-screen-identity-08 | Áp dụng ngay | "Chọn user" tick alice; gộp alice → `team`, Lưu | `st.info` bỏ chọn `alice`; `prepare_period` được gọi lại (spy) với resolver mới; checkbox `team (2 commit)` | AppTest |
| TC-screen-identity-09 | `apply_identity_edits`, `changed_rows`, `identity_rows` | tổ hợp: upsert, xóa, quy tắc có cả email + name (giữ phần name), bỏ trùng; strip; identity trùng ở hai user | đúng 5.2; thứ tự ổn định | unit |
| TC-screen-identity-10 | Khóa khi chạy | như TC-screen-input-15, panel mở | `toggle_identities`, `save_identities` disabled; data_editor disabled | AppTest |
| TC-screen-identity-12 | Bổ sung theo review | `changed_rows` với ô `None` / `pd.NA`; sửa hàng 0 chưa lưu rồi đổi file identities làm đảo thứ tự hàng; gán `a` + xóa trống cùng email; xóa trống hàng có account từ quy tắc tên; kỳ không có tác giả; cột Tên / Email bị khóa | rỗng (không `"nan"`); sửa đổi bị bỏ, Lưu disabled; `IdentityError` `… (trống)`; quy tắc tên bị bỏ, account về tự động; `Không có tác giả nào có commit trong kỳ.`; cấu hình cột disabled | unit + AppTest |
| TC-screen-identity-11 | Chưa có kỳ | mở panel trước khi tải repo | `Cần tải repo và chọn kỳ hợp lệ để có danh sách tác giả.` | AppTest |

## 10. Câu hỏi mở / giả định
| # | Nội dung | Phương án | Trạng thái |
|---|---|---|---|
| A1 | Ánh xạ hàng ↔ quy tắc theo D41-N6 (email trước, tên khi email rỗng; chỉ hàng đổi; ô rỗng xóa; giữ quy tắc ngoài kỳ) | D41-N6 | Chốt (*) |
| A2 | Panel bật/tắt bằng nút (không `st.dialog`) | D41-N27 | Chốt (*) |
| A3 | Quy tắc có cả email và name bị chạm theo email → giữ phần name (không mất ánh xạ viết tay) | Khuyến nghị | Chốt (*) |
| A4 | Không có ô đường dẫn riêng — dùng `identities_path` của `screen-input` | D41-N5 | Chốt (*) |
| A5 | Ô trống từ trình duyệt có thể là `None` / NA (pandas 3 `StringDtype`) → coi là chuỗi rỗng (review 2026-10-25, Major: từng lưu thành `"nan"`) | Khuyến nghị review | Chốt (*) |
| A6 | Tập hàng của bảng đổi (đổi file identities, kỳ, nhánh, repo) → bỏ sửa đổi chưa lưu (review Major: sửa đổi bị áp sang hàng khác cùng chỉ số) | Khuyến nghị review | Chốt (*) |
| A7 | Xóa trống ô → bỏ cả quy tắc theo email và theo tên của hàng (account đến từ quy tắc tên cũng quay về tự động) | Khuyến nghị review | Chốt (*) |
| A8 | Cùng khóa vừa được gán vừa bị xóa trống trong một lần lưu → lỗi xung đột (không phụ thuộc thứ tự hàng); thông báo ghi `(trống)` | Khuyến nghị review | Chốt (*) |

(*) Chốt theo khuyến nghị, người dùng ủy quyền ("làm theo khuyến nghị", 2026-10-25); có thể đổi lại.

## 11. Lịch sử thay đổi
| Ngày | Thay đổi | Lý do |
|---|---|---|
| 2026-10-25 | Theo review r2 (FAIL — Major: xóa state phía server không reset frontend): A6 đổi sang key theo thế hệ `identity_editor_<gen>`; A8 hàng xóa trống chiếm cả khóa tên; caption đếm quy tắc từ kết quả thật; test ô `None` qua AppTest. Chốt theo khuyến nghị | review r2 Major + Minor |
| 2026-10-25 | Theo review `reviews/screen-identity-20261025.md` (FAIL): A5 (NA → rỗng), A6 (bỏ sửa đổi khi tập hàng đổi), A7 (xóa trống bỏ cả quy tắc tên), A8 (gán + xóa cùng khóa → xung đột); TC-12. Chốt theo khuyến nghị | review Major 1, 2 + Minor |
| 2026-10-25 | Khi lập trình: 5.2 bước 3 — xung đột trong cùng lần lưu báo ngay ở `apply_identity_edits` (upsert theo email sẽ âm thầm giữ hàng sau). Chốt theo khuyến nghị | kiểm chứng TC-06 |
| 2026-10-25 | Tạo mới theo PLAN M6 + D41. A1–A4 chốt theo khuyến nghị, người dùng ủy quyền → `approved` | M6 (`/feature-spec screen-identity`) |
