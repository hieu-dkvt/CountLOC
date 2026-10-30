# Luồng hoạt động của Claude Code: Agent, Subagent, Skill, Hook

Tài liệu giải thích các thành phần của Claude Code và cách chúng phối hợp, lấy ví dụ từ chính dự án LOC Counter (thư mục `.claude/`).

> Ghi chú: một số chi tiết (thứ tự ưu tiên chọn model, tên trường frontmatter) có thể thay đổi theo phiên bản Claude Code. Cần chắc chắn thì đối chiếu bằng `/agents`, `/help` hoặc tài liệu chính thức.

---

## 1. Bức tranh tổng thể

| Thành phần | Nó là gì | Nằm ở đâu | Ai kích hoạt |
|---|---|---|---|
| **CLAUDE.md** | Hướng dẫn nền, luôn được nạp vào đầu phiên | `CLAUDE.md` | Tự động |
| **Agent chính** | Phiên Claude đang chat với bạn | (chính phiên làm việc) | Bạn gõ prompt |
| **Skill** | Quy trình đóng gói thành prompt, nạp khi cần | `.claude/skills/<tên>/SKILL.md` | Bạn gõ `/tên` hoặc Claude tự chọn theo `description` |
| **Subagent** | Một phiên Claude khác, context và tool riêng | `.claude/agents/<tên>.md` | Agent chính giao việc (hoặc skill `context: fork`) |
| **Hook** | Lệnh do harness chạy ở một sự kiện, Claude không điều khiển | `.claude/settings.json` + script | Tự động theo sự kiện |
| **Permissions** | Danh sách lệnh được phép chạy không hỏi | `.claude/settings.json` | Tự động |

Điểm cần nhớ nhất:

- **Agent** và **subagent** cùng một loại thực thể. Gọi là subagent khi nó được agent khác giao việc.
- **Skill là hướng dẫn**, không phải người thực thi. Phiên nào nạp skill thì phiên đó làm theo.
- **Subagent là người thực thi** trong context riêng, chỉ trả về bản tóm tắt.
- **Hook là chốt chặn cứng** do chương trình bên ngoài chạy. Claude không thể "quên" hay bỏ qua.

---

## 2. Từng thành phần

### 2.1 CLAUDE.md
- Được nạp vào context ngay từ đầu phiên, mọi lần.
- Chứa bối cảnh dự án, quy tắc bắt buộc, quy trình, lệnh thường dùng.
- Là hướng dẫn **mềm**: Claude tuân theo vì đã đọc, nhưng không có gì ép buộc về mặt kỹ thuật.

### 2.2 Skill
```
.claude/skills/feature-test/
├── SKILL.md              ← bắt buộc: frontmatter + các bước
└── mandatory-tests.md    ← tài liệu phụ, đọc khi cần
```
Frontmatter thường dùng:
```yaml
---
name: feature-review
description: Khi nào dùng skill này   # Claude dựa vào đây để tự chọn
argument-hint: "<id> | M1..M7 | diff"
context: fork                          # tuỳ chọn: chạy tách biệt
agent: code-reviewer                   # tuỳ chọn: chạy bằng subagent nào
---
```
Cách hoạt động:
1. Đầu phiên, Claude chỉ thấy **tên + description** của mọi skill (rất nhẹ).
2. Khi bạn gõ `/tên` hoặc yêu cầu khớp description, nội dung `SKILL.md` mới được nạp.
3. `$ARGUMENTS` trong thân skill được thay bằng tham số bạn truyền.
4. Skill **không có model hay tool riêng** trừ khi chạy fork. Nó dùng model và tool của phiên đang nạp nó.

### 2.3 Subagent
```yaml
---
name: test-engineer
description: Khi nào giao việc cho agent này
tools: Read, Write, Edit, Glob, Grep, Bash   # bỏ trống = kế thừa tất cả
model: sonnet                                # tuỳ chọn; bỏ trống = kế thừa
---
System prompt của agent viết ở đây.
```
Cách hoạt động:
1. Agent chính gọi tool **Agent** kèm tên subagent và một prompt mô tả việc.
2. Subagent khởi động với **context trống**: chỉ có system prompt của nó, prompt được giao, và CLAUDE.md. Nó không thấy hội thoại trước đó của bạn.
3. Nó làm việc bằng các tool được phép (`tools:`).
4. Kết thúc, **chỉ bản tóm tắt cuối** quay về agent chính. Phần đọc file, suy luận trung gian không làm phình context chính.

Lý do dùng subagent: giữ context chính gọn, giới hạn quyền (ví dụ chỉ đọc), có góc nhìn độc lập, và chọn model riêng cho từng vai trò.

### 2.4 Hook
Khai báo trong `settings.json`:
```json
"hooks": {
  "PreToolUse": [{
    "matcher": "Write|Edit|MultiEdit",
    "hooks": [{ "type": "command",
                "command": "node \"$CLAUDE_PROJECT_DIR/.claude/hooks/require-spec.cjs\"" }]
  }]
}
```
Cách hoạt động:
1. Claude quyết định gọi một tool, ví dụ `Write`.
2. **Trước khi tool chạy**, harness thấy `matcher` khớp nên chạy lệnh của hook.
3. Thông tin tool call (đường dẫn file, nội dung…) được truyền cho script qua **stdin dạng JSON**.
4. Script quyết định bằng **exit code**:
   - `0`: cho phép, tool chạy bình thường.
   - `2`: **chặn** tool call; nội dung `stderr` được chuyển cho Claude như lý do bị chặn.
5. Claude đọc lý do và điều chỉnh (ở dự án này: đi tạo spec trước).

Một số sự kiện hook phổ biến: `PreToolUse` (trước tool), `PostToolUse` (sau tool), `UserPromptSubmit` (khi bạn gửi prompt), `Stop` (khi Claude kết thúc lượt), `SessionStart` (đầu phiên).

---

## 3. Luồng khi bạn gõ một prompt

```
Bạn gõ prompt
   │
   ▼
[Hook UserPromptSubmit]  (nếu có cấu hình; dự án này không dùng)
   │
   ▼
Agent chính  ← đã có sẵn: CLAUDE.md, tên+description của skill/agent, tool
   │
   ├── Chọn skill?  → nạp SKILL.md vào phiên, làm theo các bước
   │
   ├── Giao việc?   → tool Agent → subagent chạy riêng → trả tóm tắt
   │
   └── Cần hành động (Read / Write / Bash / ...)
            │
            ▼
       [Hook PreToolUse]  ── exit 2 ──► BỊ CHẶN, lý do quay về Claude
            │ exit 0
            ▼
       Kiểm tra permissions (allow list / hỏi bạn)
            │
            ▼
       Tool chạy → kết quả quay về Claude
            │
            ▼
       [Hook PostToolUse] (nếu có)
            │
            ▼
       Claude tiếp tục vòng lặp cho đến khi xong → trả lời bạn
            │
            ▼
       [Hook Stop] (nếu có)
```

Lưu ý: bản thân subagent cũng chịu hook. Khi `test-engineer` gọi `Write`, hook `PreToolUse` vẫn chạy như với agent chính.

---

## 4. Ai được gọi ai

| Từ → Đến | Được không | Ví dụ |
|---|---|---|
| Phiên chính → skill | Được | `/feature-spec` |
| Phiên chính → subagent | Được | giao việc cho `spec-analyst` |
| Skill (inline) → subagent | Được | `feature-implement` → `test-engineer` |
| Skill (inline) → skill | Được | `feature-implement` → `/feature-test` → `/feature-review` |
| Skill `context: fork` → subagent khác | Không | skill đã chạy trong subagent rồi |
| Subagent → subagent | Không | subagent không có tool Agent, tránh đệ quy |
| Subagent → skill | Hạn chế | qua `skills:` (nạp sẵn nội dung) hoặc thêm tool `Skill` vào `tools:` |

Muốn nhiều tầng thì **agent chính phải điều phối**: gọi A, nhận kết quả, rồi gọi B.

**Inline và fork:**
- Inline (mặc định): skill chạy ngay trong phiên chính, thấy toàn bộ hội thoại, hỏi được bạn.
- Fork (`context: fork` + `agent:`): thân skill trở thành prompt giao cho subagent; phiên chính chỉ nhận kết quả.

---

## 5. Model của subagent

Thứ tự ưu tiên (cao → thấp):
1. Biến môi trường `CLAUDE_CODE_SUBAGENT_MODEL` (nếu đặt). Biến này chỉ chứa **một giá trị duy nhất** và áp cho **mọi** subagent, nên không dùng để chọn model riêng từng agent. Đặt nó thì mọi `model:` trong frontmatter bị bỏ qua.
2. Tham số `model` khi gọi tool Agent
3. Trường `model:` trong frontmatter của agent
4. Kế thừa model của phiên chính

Giá trị hợp lệ: alias (`opus`, `sonnet`, `haiku`, `fable`), `inherit`, hoặc model ID đầy đủ.
Skill không có model riêng; skill chạy fork thì dùng model của agent mà nó chỉ định.

---

## 6. Áp dụng vào dự án LOC Counter

### Bản đồ thành phần
| Loại | Thành phần | Ghi chú |
|---|---|---|
| Agent chính | Phiên chat | Đọc `CLAUDE.md`, điều phối |
| Subagent | `spec-analyst` | Chỉ đọc; phân tích spec gốc, tìm mơ hồ |
| Subagent | `test-engineer` | Viết test, fixture repo Git |
| Subagent | `code-reviewer` | Đọc code; chỉ ghi báo cáo vào `docs/reviews/` |
| Skill | `milestone-plan` | Lập kế hoạch milestone |
| Skill | `feature-spec` | Viết spec xử lý (bắt buộc trước khi code) |
| Skill | `feature-implement` | Test trước, rồi code |
| Skill | `feature-test` | Chạy và đánh giá test |
| Skill | `feature-review` | Fork sang `code-reviewer` |
| Hook | `require-spec.cjs` | Chặn ghi code khi chưa có spec duyệt |

Mỗi subagent khai `model:` riêng trong frontmatter: `spec-analyst` và `code-reviewer` dùng `opus`, `test-engineer` dùng `sonnet`. Các giá trị này chỉ có hiệu lực khi không đặt `CLAUDE_CODE_SUBAGENT_MODEL`.

### Chuỗi spec-first
```
/milestone-plan M<n> ──(phạm vi lớn)──► spec-analyst
        │
        ▼
/feature-spec <id> ──(phức tạp)───────► spec-analyst
        │   ra docs/specs/<id>.md (draft) → BẠN DUYỆT → approved
        ▼
/feature-implement <id> ──(nhiều TC)──► test-engineer
        │   viết test → code → /feature-test → /feature-review
        ▼
/feature-test <id> ──(nhiều test)─────► test-engineer
        ▼
/feature-review <id>  =  fork thẳng vào code-reviewer
        ▼
Trạng thái spec: draft → approved → implemented → reviewed
```

### Chỗ nào quy định việc gọi agent
- **Cứng**: frontmatter `context: fork` + `agent: code-reviewer` trong `feature-review/SKILL.md`. Harness tự thi hành.
- **Mềm**: câu chữ trong thân skill như "nhiều TC → giao agent `test-engineer`" (`milestone-plan`, `feature-spec`, `feature-implement`, `feature-test`). Agent chính tự quyết có làm không.
- **Gián tiếp**: `feature-implement` gọi `/feature-test` rồi `/feature-review`, nên kéo theo `code-reviewer`.

### Hook `require-spec.cjs` làm gì, từng bước
1. Chỉ chạy với tool `Write`, `Edit`, `MultiEdit` (theo `matcher`).
2. Đọc JSON từ stdin, lấy `tool_input.file_path`.
3. Nếu đường dẫn không nằm trong `/src/loc_counter/`, hoặc không phải `.py`, hoặc là `__init__.py` → cho qua (exit 0).
4. Quét `docs/specs/*.md`, đọc frontmatter, tìm spec có `modules:` chứa file đang định ghi.
5. Có spec với `status` là `approved`, `implemented` hoặc `reviewed` → cho qua.
6. Ngược lại → ghi lý do ra stderr và **exit 2**: Claude nhận thông báo "Chưa có spec / spec chưa duyệt" rồi phải đi chạy `/feature-spec`.

Hai điểm đáng chú ý:
- Nếu hook không đọc được input, nó chọn **không chặn** (fail-open).
- Hook chỉ bảo vệ `Write/Edit/MultiEdit`. Ghi file bằng lệnh `Bash` (ví dụ `echo > file`) không đi qua matcher này.

### Hai tầng ràng buộc
| Loại | Cơ chế | Mức ràng buộc |
|---|---|---|
| Spec-first | Hook `require-spec.cjs` | **Cứng** (harness thi hành) |
| Review độc lập | `context: fork` + `agent:` | **Cứng** |
| Giao việc cho `spec-analyst` / `test-engineer` | Câu chữ trong SKILL.md | Mềm |
| Quy tắc trong CLAUDE.md (token, không đổi thuật toán…) | Văn bản | Mềm |

---

## 7. Gợi ý khi thiết kế

- Cần **chặn tuyệt đối** → dùng hook.
- Cần **quy trình nhiều bước** có thể hỏi người dùng → dùng skill chạy inline.
- Cần **góc nhìn độc lập**, giới hạn quyền, hoặc việc tốn nhiều context → dùng subagent (hoặc skill fork).
- Cần **nhiều tầng** → để agent chính điều phối, đừng mong subagent gọi subagent.
- Muốn tiết kiệm chi phí → gán `model: haiku/sonnet` cho agent làm việc khuôn mẫu, `opus` cho agent cần suy luận sâu.
