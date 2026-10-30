# Spec xử lý chức năng / màn hình

Mỗi màn hình, lệnh CLI và module có **một spec xử lý** ở thư mục này, tạo bằng `/feature-spec <id>` từ template `.claude/skills/feature-spec/template.md`.
Không lập trình file nào trong `src/loc_counter/` khi chưa có spec `approved` liệt kê file đó ở trường `modules:` (hook `require-spec.cjs` chặn).

## Quy ước id
| Loại | Mẫu id | Ví dụ | `modules:` |
|---|---|---|---|
| Module lõi | `<tên module>` | `classifier`, `snapshot` | `src/loc_counter/<tên>.py` |
| Lệnh CLI | `cli-<lệnh>` | `cli-count`, `cli-users`, `cli-analyze` | `src/loc_counter/cli.py` (+ module mới nếu có) |
| Màn hình | `screen-<tên>` | `screen-input`, `screen-identity`, `screen-result` | `src/loc_counter/app.py` |

Một file nguồn có thể thuộc nhiều spec (vd. `cli.py`, `app.py`, `counter.py`).

## Vòng đời
`draft` → `approved` (người dùng duyệt) → `implemented` (test pass) → `reviewed` (review PASS / PASS_WITH_NOTES).
Sửa hành vi sau khi duyệt → cập nhật spec, ghi "Lịch sử thay đổi", quay lại `draft` và xin duyệt lại.

## Chỉ mục
| ID | Loại | Milestone | Trạng thái |
|---|---|---|---|
| [config](config.md) | module | M1 | reviewed |
| [filters](filters.md) | module | M1 | reviewed |
| [classifier](classifier.md) | module | M1 | reviewed |
| [counter](counter.md) | module | M1, M4, M5, M8 | reviewed |
| [cli-count](cli-count.md) | cli | M1 | reviewed |
| [git_repo](git_repo.md) | module | M2, M3, M4, M8 | reviewed |
| [snapshot](snapshot.md) | module | M2, M3, M4 | reviewed |
| [identity](identity.md) | module | M3 | reviewed |
| [cli-users](cli-users.md) | cli | M3 | reviewed |
| [attribution](attribution.md) | module | M4, M5 | reviewed |
| [builder](builder.md) | module | M4, M5 | reviewed |
| [report](report.md) | module | M5, M8 | reviewed |
| [pipeline](pipeline.md) | module | M5, M8 | reviewed |
| [cli-analyze](cli-analyze.md) | cli | M5 | reviewed |
| [screen-input](screen-input.md) | screen | M6 | reviewed |
| [screen-result](screen-result.md) | screen | M6, M8 | reviewed |
| [screen-identity](screen-identity.md) | screen | M6 | reviewed |
