/**
 * E2-T5：DrawingViewer 相关组件单测（jsdom 环境）
 *
 * 测试目标：
 * 1. drawing-state.ts 纯状态管理函数
 * 2. toast.ts DOM 操作（需要 jsdom）
 * 3. review-panel.ts 基础 DOM 操作
 */
import { describe, it, expect, beforeEach } from 'vitest';

// ── drawing-state 测试 ────────────────────────────────────

describe('drawing-state', () => {
  // 每个测试前清除模块缓存，避免状态污染
  function resetState() {
    // 重新导入以重置模块级状态
    delete (globalThis as any).__baa_parsedDrawings;
    delete (globalThis as any).__baa_fileCache;
  }

  it('getParsedDrawings 初始为空数组', async () => {
    resetState();
    const { getParsedDrawings } = await import('./ts/core/drawing-state');
    expect(getParsedDrawings()).toEqual([]);
  });

  it('setParsedDrawings 设置后 getParsedDrawings 返回新值', async () => {
    resetState();
    const { setParsedDrawings, getParsedDrawings } = await import('./ts/core/drawing-state');
    const drawings = [{ id: 'd1', name: 'test.dxf' }];
    setParsedDrawings(drawings);
    expect(getParsedDrawings()).toHaveLength(1);
    expect(getParsedDrawings()[0].id).toBe('d1');
  });

  it('setParsedDrawings 覆盖而非追加', async () => {
    resetState();
    const { setParsedDrawings, getParsedDrawings } = await import('./ts/core/drawing-state');
    setParsedDrawings([{ id: 'a' }]);
    setParsedDrawings([{ id: 'b' }]);
    const result = getParsedDrawings();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('b');
  });

  it('getFileCache 初始为空对象', async () => {
    resetState();
    const { getFileCache } = await import('./ts/core/drawing-state');
    expect(getFileCache()).toEqual({});
  });

  it('setFileCache 按 id 存储文件', async () => {
    resetState();
    const { setFileCache, getFileCache } = await import('./ts/core/drawing-state');
    const fakeFile = new File(['content'], 'test.dxf', { type: 'application/dxf' });
    setFileCache('file-1', fakeFile);
    expect(getFileCache()['file-1']).toBe(fakeFile);
  });
});

// ── toast 组件测试（jsdom）─────────────────────────────────

describe('toast', { timeout: 5000 }, () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('showToast 创建 toast-container 并插入通知', async () => {
    const { showToast } = await import('./ts/core/toast');
    showToast('test message', 'info', 100);

    const container = document.getElementById('toast-container');
    expect(container).not.toBeNull();
    expect(container?.className).toContain('toast-container');

    const toasts = container?.querySelectorAll('.toast');
    expect(toasts).toHaveLength(1);
    expect(toasts?.[0]?.textContent).toContain('test message');
  });

  it('showToast 限制最多 5 条', async () => {
    const { showToast } = await import('./ts/core/toast');
    for (let i = 0; i < 7; i++) {
      showToast(`msg-${i}`, 'info', 100);
    }
    const container = document.getElementById('toast-container');
    const toasts = container?.querySelectorAll('.toast') || [];
    // 旧 toast 在 100ms 后移除，但新 toast 在 700ms 后移除
    // 峰值应 <= 5（容器最多 5 条，超出的会被移除）
    expect(toasts.length).toBeLessThanOrEqual(5);
  });

  it('showToast 不同类型有不同 icon', async () => {
    const { showToast } = await import('./ts/core/toast');
    showToast('error msg', 'error', 100);
    const toast = document.querySelector('.toast-error');
    expect(toast).not.toBeNull();
    expect(toast?.textContent).toContain('error msg');

    document.querySelector('#toast-container')?.remove();
    showToast('success msg', 'success', 100);
    const toast2 = document.querySelector('.toast-success');
    expect(toast2).not.toBeNull();
  });

  it('showToast 空消息不创建元素', async () => {
    const { showToast } = await import('./ts/core/toast');
    showToast('', 'info', 100);
    expect(document.getElementById('toast-container')).toBeNull();
  });

  it('showToast 非字符串消息不创建元素', async () => {
    const { showToast } = await import('./ts/core/toast');
    (showToast as any)(123, 'info', 100);
    expect(document.getElementById('toast-container')).toBeNull();
  });
});

// ── review-panel DOM 操作测试 ─────────────────────────────

describe('review-panel', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('showDrawingReviewPanel 切换 visibility', async () => {
    const panel = document.createElement('div');
    panel.id = 'drawing-review-panel';
    panel.style.display = 'block';
    document.body.appendChild(panel);

    const { showDrawingReviewPanel } = await import('./ts/core/review-panel');
    showDrawingReviewPanel(false);
    expect(panel.style.display).toBe('none');

    showDrawingReviewPanel(true);
    expect(panel.style.display).toBe('block');
  });

  it('showDrawingReviewPanel 找不到 panel 时不抛异常', async () => {
    const { showDrawingReviewPanel } = await import('./ts/core/review-panel');
    expect(() => showDrawingReviewPanel(true)).not.toThrow();
  });
});
