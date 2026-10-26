#!/usr/bin/env node
// PreToolUse hook (Write|Edit|MultiEdit): chặn ghi src/loc_counter/*.py khi chưa có
// spec xử lý đã được duyệt trong docs/specs/ liệt kê file đó ở trường `modules:`.
// Exit 2 + stderr => Claude Code chặn tool call và chuyển thông báo cho Claude.
'use strict';
const fs = require('fs');
const path = require('path');

const ALLOWED_STATUS = new Set(['approved', 'implemented', 'reviewed']);
const EXEMPT_FILES = new Set(['__init__.py']);
const SRC_MARKER = '/src/loc_counter/';

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

function parseFrontMatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return {};
  const fm = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = line.match(/^([A-Za-z_]+):\s*(.*?)\s*(#.*)?$/);
    if (kv) fm[kv[1]] = kv[2];
  }
  return fm;
}

function parseList(value) {
  if (!value) return [];
  return value
    .replace(/^\[|\]$/g, '')
    .split(',')
    .map((s) => s.trim().replace(/^["']|["']$/g, ''))
    .filter(Boolean);
}

function main() {
  let input;
  try {
    input = JSON.parse(readStdin() || '{}');
  } catch {
    return 0; // Không đọc được input: không chặn.
  }
  const filePath = input && input.tool_input && input.tool_input.file_path;
  if (!filePath) return 0;

  const norm = filePath.replace(/\\/g, '/');
  const idx = norm.lastIndexOf(SRC_MARKER);
  if (idx < 0) return 0;

  const rel = norm.slice(idx + 1); // src/loc_counter/<file>.py
  if (!rel.endsWith('.py') || EXEMPT_FILES.has(path.posix.basename(rel))) return 0;

  const specsDir = path.join(norm.slice(0, idx), 'docs', 'specs');
  const matches = [];
  if (fs.existsSync(specsDir)) {
    for (const name of fs.readdirSync(specsDir)) {
      if (!name.endsWith('.md') || name.startsWith('_') || name.toLowerCase() === 'readme.md') continue;
      const fm = parseFrontMatter(fs.readFileSync(path.join(specsDir, name), 'utf8'));
      if (parseList(fm.modules).includes(rel)) {
        matches.push({ name, status: (fm.status || '').toLowerCase() });
      }
    }
  }

  if (matches.some((m) => ALLOWED_STATUS.has(m.status))) return 0;

  const msg = matches.length === 0
    ? `[spec-first] Chưa có spec xử lý cho ${rel}. ` +
      `Hãy chạy /feature-spec <id> để tạo docs/specs/<id>.md (trường modules: phải chứa ${rel}) ` +
      `và để người dùng duyệt (status: approved) trước khi lập trình.`
    : `[spec-first] Spec cho ${rel} chưa được duyệt: ` +
      matches.map((m) => `${m.name} (status: ${m.status || 'trống'})`).join(', ') +
      `. Trình bày spec cho người dùng và chỉ đổi sang status: approved khi người dùng đồng ý.`;
  process.stderr.write(msg + '\n');
  return 2;
}

process.exit(main());
