/**
 * E2-T5：前端组件单测（jsdom 环境）
 *
 * 覆盖模块：
 * 1. drawing-state.ts — 纯状态管理（parsedDrawings / fileCache）
 * 2. toast.ts — DOM 操作（showToast、容器管理、类型图标）
 * 3. review-panel.ts — showDrawingReviewPanel DOM 切换
 * 4. utils.ts — 纯函数（formatDate / maskKey / escHtml / permissionBadge / uid / mergeDeep）
 *
 * 运行：node node_modules/vitest/vitest.mjs run
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  formatDate,
  maskKey,
  escHtml,
  permissionBadge,
  enabledBadge,
  uid,
  mergeDeep,
} from './utils';

// ── 辅助：清理 DOM ────────────────────────────────────────
function cleanBody(): void {
  document.body.innerHTML = '';
}

// ── drawing-state 测试 ────────────────────────────────────
// 使用 vi.mock 隔离模块缓存，确保每个测试独立

let drawState: typeof import('./drawing-state');

beforeAll(async () => {
  // 每次 beforeAll 前重置模块缓存
  vi.resetModules();
  drawState = await import('./drawing-state');
});

describe('drawing-state', () => {
  beforeEach(async () => {
    vi.resetModules();
    drawState = await import('./drawing-state');
  });

  it('getParsedDrawings 初始为空数组', async () => {
    const { getParsedDrawings } = await import('./drawing-state');
    expect(getParsedDrawings()).toEqual([]);
  });

  it('setParsedDrawings 设置后 getParsedDrawings 返回新值', async () => {
    const { setParsedDrawings, getParsedDrawings } = await import('./drawing-state');
    const drawings = [{ id: 'd1', name: 'test.dxf' }];
    setParsedDrawings(drawings);
    expect(getParsedDrawings()).toHaveLength(1);
    expect(getParsedDrawings()[0].id).toBe('d1');
  });

  it('setParsedDrawings 覆盖而非追加', async () => {
    const { setParsedDrawings, getParsedDrawings } = await import('./drawing-state');
    setParsedDrawings([{ id: 'a' }]);
    setParsedDrawings([{ id: 'b' }]);
    const result = getParsedDrawings();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('b');
  });

  it('setParsedDrawings 同步 window.parsedDrawings', async () => {
    const { setParsedDrawings } = await import('./drawing-state');
    setParsedDrawings([{ id: 'w1' }]);
    expect((window as Record<string, unknown>).parsedDrawings).toEqual([{ id: 'w1' }]);
  });

  it('getFileCache 初始为空对象', async () => {
    const { getFileCache } = await import('./drawing-state');
    expect(getFileCache()).toEqual({});
  });

  it('setFileCache 按 id 存储文件', async () => {
    const { setFileCache, getFileCache } = await import('./drawing-state');
    const fakeFile = new File(['content'], 'test.dxf', { type: 'application/dxf' });
    setFileCache('file-1', fakeFile);
    expect(getFileCache()['file-1']).toBe(fakeFile);
  });

  it('setFileCache 同步 window.fileCache', async () => {
    const { setFileCache } = await import('./drawing-state');
    const f = new File(['x'], 'a.dxf');
    setFileCache('k1', f);
    expect((window as Record<string, unknown>).fileCache).toHaveProperty('k1');
  });
});

// ── toast 组件测试 ────────────────────────────────────────
// vitest 默认会注入 jest 全局（clearAllTimers 等）

describe('toast', () => {
  beforeEach(cleanBody);

  afterEach(() => {
    // 清除定时器残留
    if (typeof globalThis.clearAllTimers === 'function') {
      try { globalThis.clearAllTimers(); } catch { /* jsdom may not support */ }
    }
  });

  it('showToast 创建 toast-container 并插入通知', async () => {
    const { showToast } = await import('./toast');
    showToast('test message', 'info', 100);

    const container = document.getElementById('toast-container');
    expect(container).not.toBeNull();
    expect(container?.className).toContain('toast-container');

    const toasts = container?.querySelectorAll('.toast');
    expect(toasts).toHaveLength(1);
    expect(toasts?.[0]?.textContent).toContain('test message');
  });

  it('showToast 不同类型有不同 CSS class', async () => {
    const { showToast } = await import('./toast');
    showToast('err', 'error', 100);
    expect(document.querySelector('.toast-error')).not.toBeNull();

    document.querySelector('#toast-container')?.remove();
    showToast('ok', 'success', 100);
    expect(document.querySelector('.toast-success')).not.toBeNull();

    document.querySelector('#toast-container')?.remove();
    showToast('wrn', 'warn', 100);
    expect(document.querySelector('.toast-warn')).not.toBeNull();
  });

  it('showToast 限制最多 5 条', async () => {
    const { showToast } = await import('./toast');
    for (let i = 0; i < 7; i++) {
      showToast(`msg-${i}`, 'info', 100);
    }
    const toasts = document.querySelectorAll('.toast');
    expect(toasts.length).toBeLessThanOrEqual(5);
  });

  it('showToast 空消息不创建元素', async () => {
    const { showToast } = await import('./toast');
    showToast('', 'info', 100);
    expect(document.getElementById('toast-container')).toBeNull();
  });

  it('showToast 非字符串消息不创建元素', async () => {
    const { showToast } = await import('./toast');
    (showToast as unknown as (m: unknown) => void)(123, 'info', 100);
    expect(document.getElementById('toast-container')).toBeNull();
  });

  it('showToast 挂载到 window.showToast', async () => {
    await import('./toast');
    expect(typeof (window as Record<string, unknown>).showToast).toBe('function');
  });
});

// ── review-panel 测试 ─────────────────────────────────────

describe('review-panel', () => {
  beforeEach(cleanBody);

  it('showDrawingReviewPanel 切换 visibility', async () => {
    const panel = document.createElement('div');
    panel.id = 'drawing-review-panel';
    panel.classList.remove('hidden');
    document.body.appendChild(panel);

    const { showDrawingReviewPanel } = await import('./review-panel');
    showDrawingReviewPanel(false);
    expect(panel.classList.contains('hidden')).toBe(true);

    showDrawingReviewPanel(true);
    expect(panel.classList.contains('hidden')).toBe(false);
  });

  it('showDrawingReviewPanel 找不到 panel 时不抛异常', async () => {
    const { showDrawingReviewPanel } = await import('./review-panel');
    expect(() => showDrawingReviewPanel(true)).not.toThrow();
  });

  it('showDrawingReviewPanel 挂在 window', async () => {
    await import('./review-panel');
    expect(typeof (window as Record<string, unknown>).showDrawingReviewPanel).toBe('function');
  });
});

// ── utils 纯函数测试 ──────────────────────────────────────

describe('formatDate', () => {
  it('空值返回 "-"', () => {
    expect(formatDate(undefined)).toBe('-');
    expect(formatDate(null)).toBe('-');
  });

  it('秒级时间戳转中文日期', () => {
    const result = formatDate(1789154400);
    expect(result).toContain('2026');
    expect(result).not.toBe('-');
  });

  it('ISO 字符串转中文日期', () => {
    expect(formatDate('2026-09-10T10:00:00')).toContain('2026');
  });

  it('非法日期返回 "-"', () => {
    expect(formatDate('not-a-date')).toBe('-');
  });
});

describe('maskKey', () => {
  it('保留前后各4位，中间用 ... 连接', () => {
    expect(maskKey('abcdef1234567890')).toBe('abcd...7890');
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
    const input = '<script>"&\'</script>';
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
    expect(permissionBadge('admin')).toContain('bg-red-100');
    expect(permissionBadge('admin')).toContain('admin');
  });

  it('write 权限使用蓝色样式', () => {
    expect(permissionBadge('write')).toContain('bg-blue-100');
  });

  it('read 权限使用绿色样式', () => {
    expect(permissionBadge('read')).toContain('bg-green-100');
  });

  it('未知权限使用灰色兜底样式', () => {
    expect(permissionBadge('unknown-perm')).toContain('bg-gray-100');
  });

  it('权限名会被 HTML 转义（防 XSS）', () => {
    expect(permissionBadge('admin"><script>')).not.toContain('<script>');
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
    expect(uid().startsWith('id_')).toBe(true);
  });

  it('多次调用生成不同 ID', () => {
    const ids = Array.from({ length: 50 }, () => uid());
    expect(new Set(ids).size).toBeGreaterThan(1);
  });

  it('格式为 id_<时间戳>_<随机串>', () => {
    expect(uid()).toMatch(/^id_\d{13}_[a-z0-9]+$/);
  });
});

describe('mergeDeep', () => {
  it('浅层合并', () => {
    expect(mergeDeep({ a: 1 }, { b: 2 })).toEqual({ a: 1, b: 2 });
  });

  it('深层对象递归合并', () => {
    const out = mergeDeep({ a: { x: 1, y: 2 }, b: 3 }, { a: { y: 20, z: 30 } });
    expect(out).toEqual({ a: { x: 1, y: 20, z: 30 }, b: 3 });
  });

  it('source 值覆盖 target 同名值', () => {
    expect(mergeDeep({ a: 1 }, { a: 99 })).toEqual({ a: 99 });
  });

  it('数组不做递归，整体替换', () => {
    expect(mergeDeep({ list: [1, 2, 3] }, { list: [9] }).list).toEqual([9]);
  });

  it('不修改原 target 对象（返回新对象）', () => {
    const target = { a: { x: 1 } };
    mergeDeep(target, { a: { y: 2 } });
    expect(target.a).toEqual({ x: 1 });
  });

  it('空 source 返回 target 副本', () => {
    const target = { a: 1, b: 2 };
    const out = mergeDeep(target, {});
    expect(out).toEqual({ a: 1, b: 2 });
    expect(out).not.toBe(target);
  });
});
