import { describe, it, expect } from 'vitest';
import {
  formatDate,
  maskKey,
  escHtml,
  permissionBadge,
  enabledBadge,
  uid,
  mergeDeep,
} from './utils';

// ── P126: 前端纯函数单测 ────────────────────────────────────────
// utils.ts 是 P123 Phase 1 拆出的纯函数模块（无 DOM 依赖），
// 是前端单测的第一切入点。

describe('formatDate', () => {
  it('空值返回 "-"', () => {
    expect(formatDate(undefined)).toBe('-');
    expect(formatDate(null)).toBe('-');
  });

  it('秒级时间戳转中文日期', () => {
    // 2026-09-10 10:00:00 UTC = 1789154400 s
    const result = formatDate(1789154400);
    expect(result).toContain('2026');
    expect(result).not.toBe('-');
  });

  it('ISO 字符串转中文日期', () => {
    const result = formatDate('2026-09-10T10:00:00');
    expect(result).toContain('2026');
    expect(result).not.toBe('-');
  });

  it('非法日期返回 "-"', () => {
    expect(formatDate('not-a-date')).toBe('-');
  });
});

describe('maskKey', () => {
  it('保留前后各4位，中间用 ... 连接', () => {
    const k = 'abcdef1234567890';
    expect(maskKey(k)).toBe('abcd...7890');
  });

  it('短密钥（<=8位）原样返回', () => {
    expect(maskKey('short1')).toBe('short1');
    expect(maskKey('12345678')).toBe('12345678');
  });

  it('空值返回空字符串', () => {
    expect(maskKey('')).toBe('');
  });
});

describe('escHtml', () => {
  it('转义 5 个危险字符', () => {
    const input = `<script>"&'</script>`;
    const out = escHtml(input);
    expect(out).not.toContain('<');
    expect(out).not.toContain('>');
    expect(out).toContain('&lt;');
    expect(out).toContain('&gt;');
    expect(out).toContain('&amp;');
    expect(out).toContain('&quot;');
    expect(out).toContain('&#39;');
  });

  it('安全文本原样返回', () => {
    expect(escHtml('hello world')).toBe('hello world');
  });

  it('null/undefined 转空字符串', () => {
    expect(escHtml(null)).toBe('');
    expect(escHtml(undefined)).toBe('');
  });

  it('数字类型转字符串后转义', () => {
    expect(escHtml(42)).toBe('42');
  });
});

describe('permissionBadge', () => {
  it('admin 权限使用红色样式', () => {
    const html = permissionBadge('admin');
    expect(html).toContain('bg-red-100');
    expect(html).toContain('admin');
  });

  it('write 权限使用蓝色样式', () => {
    const html = permissionBadge('write');
    expect(html).toContain('bg-blue-100');
  });

  it('read 权限使用绿色样式', () => {
    const html = permissionBadge('read');
    expect(html).toContain('bg-green-100');
  });

  it('未知权限使用灰色兜底样式', () => {
    const html = permissionBadge('unknown-perm');
    expect(html).toContain('bg-gray-100');
  });

  it('权限名会被 HTML 转义（防 XSS）', () => {
    const html = permissionBadge('admin"><script>');
    expect(html).not.toContain('<script>');
  });
});

describe('enabledBadge', () => {
  it('启用状态显示绿色 ✓', () => {
    const html = enabledBadge(true);
    expect(html).toContain('bg-green-100');
    expect(html).toContain('✓');
    expect(html).toContain('启用');
  });

  it('禁用状态显示红色 ✗', () => {
    const html = enabledBadge(false);
    expect(html).toContain('bg-red-100');
    expect(html).toContain('✗');
    expect(html).toContain('已禁用');
  });
});

describe('uid', () => {
  it('生成 id_ 前缀', () => {
    const id = uid();
    expect(id.startsWith('id_')).toBe(true);
  });

  it('多次调用生成不同 ID', () => {
    const ids = new Set(Array.from({ length: 50 }, () => uid()));
    expect(ids.size).toBeGreaterThan(1);
  });

  it('格式为 id_<时间戳>_<随机串>', () => {
    const id = uid();
    // id_ + 13位时间戳 + _ + 6位随机
    expect(id).toMatch(/^id_\d{13}_[a-z0-9]+$/);
  });
});

describe('mergeDeep', () => {
  it('浅层合并', () => {
    expect(mergeDeep({ a: 1 }, { b: 2 })).toEqual({ a: 1, b: 2 });
  });

  it('深层对象递归合并', () => {
    const target = { a: { x: 1, y: 2 }, b: 3 };
    const source = { a: { y: 20, z: 30 } };
    const out = mergeDeep(target, source);
    expect(out).toEqual({ a: { x: 1, y: 20, z: 30 }, b: 3 });
  });

  it('source 值覆盖 target 同名值', () => {
    expect(mergeDeep({ a: 1 }, { a: 99 })).toEqual({ a: 99 });
  });

  it('数组不做递归，整体替换', () => {
    const out = mergeDeep({ list: [1, 2, 3] }, { list: [9] });
    expect(out.list).toEqual([9]);
  });

  it('不修改原 target 对象（返回新对象）', () => {
    const target = { a: { x: 1 } };
    mergeDeep(target, { a: { y: 2 } });
    expect(target.a).toEqual({ x: 1 }); // 原对象未被污染
  });

  it('空 source 返回 target 副本', () => {
    const target = { a: 1, b: 2 };
    const out = mergeDeep(target, {});
    expect(out).toEqual({ a: 1, b: 2 });
    expect(out).not.toBe(target);
  });
});
