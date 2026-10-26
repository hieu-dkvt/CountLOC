# Báo cáo test — counter (M4: WarningKind) + snapshot (F8: UNSAFE_PATH)

Ngày: 2026-10-23 · Phạm vi: `docs/specs/counter.md` (bản M4), `docs/specs/snapshot.md` (bản F8)

## Kết quả
| Lệnh | Kết quả |
|---|---|
| `uv run pytest tests/test_counter.py tests/test_snapshot.py -q` | 132 passed |
| `uv run pytest -q` (toàn bộ) | 375 passed, 0 fail, 0 skip |
| `uv run ruff check src tests` | sạch |

Coverage: `counter.py` 98 % (thiếu 113-114, 127: nhánh `onerror` không có `filename`, junction trên Python < 3.12 — có từ M1), `snapshot.py` 100 %.

## Truy vết TC
- `counter`: 17/17 TC có test, không có test mồ côi. Mới: TC-16 `test_warning_kind_catalog`, TC-17 `test_warning_sort_with_m4_kinds`.
- `snapshot`: 32/32 TC có test, không có test mồ côi. Đã sửa theo bản F8:
  - TC-21 `test_plan_unsafe_paths`: `plan.warnings` = `UNSAFE_PATH` cho `../evil.py`, `.GIT/evil.py` (đúng thứ tự, đúng thông báo).
  - TC-23 `test_unsafe_paths_windows`: `plan.warnings == [UNSAFE_PATH a:b.py]`.
  - TC-25: bỏ ca `dotdot` khỏi `test_screen_entry_excluded` (không cảnh báo); thêm `test_screen_entry_unsafe` (`../evil.py`, `node_modules/a:b.js` × 2 chế độ × `exclude_binary`): `keep=False`, đúng một `UNSAFE_PATH`, log WARNING.
  - TC-27: `C:/x.py` → `(False, None, (UNSAFE_PATH,))` ở cả hai chế độ; `test_select_content_unsafe_logged` kiểm thông báo.

## Test bắt buộc
Phạm vi không thuộc §6.4 / §14 — không áp dụng. Tiêu chí M4 (mandatory-tests mục D) kiểm khi xong `attribution` + `builder`.

## Tái lập
Không thay đổi luồng ghi zip; TC-snapshot-16, 28 (SHA-256 hai lần ghi bằng nhau) vẫn pass.
