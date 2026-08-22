// ── P123 Phase 1 Step 2: 侧边栏导航模块 ──────────────────
// 从 baa-core.js 拆出 sidebar 点击事件处理器和 testConnection
// 旧 .js 文件中通过 window 调用 loadDashboard/loadSpecs/loadAnalysis 等

import { apiGet } from './api-client';
import { showToast } from './toast';
import { appState } from './state';

type PageName =
  | 'home'
  | 'specs'
  | 'analysis'
  | 'history'
  | 'apikeys'
  | 'cases'
  | 'cd'
  | 'model-params'
  | 'collab';

/** 页面切换入口：由侧边栏 item 点击触发 */
export async function navigateTo(page: string): Promise<void> {
  document.querySelectorAll('.sidebar-item').forEach((i) => i.classList.remove('active'));
  document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));

  const item = document.querySelector(`.sidebar-item[data-page="${page}"]`) as HTMLElement | null;
  const target = document.getElementById(`page-${page}`) as HTMLElement | null;
  if (!target) { console.warn('Page not found:', page); return; }
  item?.classList.add('active');
  target.classList.add('active');

  try {
    if (page === 'home') {
      await call('loadDashboard');
    } else if (page === 'specs') {
      call('loadSpecs');
    } else if (page === 'analysis') {
      await call('loadAnalysis');
    } else if (page === 'history') {
      call('renderHistoryList');
    } else if (page === 'apikeys') {
      await call('loadAdminKeys');
    } else if (page === 'cases') {
      call('loadCaseStats');
      call('loadCases', 0);
    } else if (page === 'cd') {
      call('loadCDItems');
    } else if (page === 'model-params') {
      call('switchModelParamTab', 'functions');
    } else if (page === 'collab') {
      // 恢复协作登录态
      const token = (window as unknown as Record<string, unknown>).collabToken as string | undefined;
      if (token) {
        call('updateUserStatus', true);
        setTimeout(() => call('collabEnterMain'), 100);
      }
    }
  } catch (e) {
    console.error('页面加载错误:', e);
  }
}

function call(fn: string, ...args: unknown[]): unknown {
  const f = (window as unknown as Record<string, unknown>)[fn];
  if (typeof f === 'function') return f(...args);
  console.warn(`Function not found: ${fn}`);
  return undefined;
}

/** 测试后端连接 */
export async function testConnection(): Promise<void> {
  const el = document.getElementById('conn-status') as HTMLElement | null;
  if (!el) return;
  el.className = 'text-xs text-yellow-600';
  el.textContent = '连接中...';
  try {
    const data = (await apiGet('/health')) as Record<string, unknown>;
    el.className = 'text-xs text-green-600';
    el.textContent = `✅ 连接成功 | ${data.version} | 引擎: ${data.engine_status}`;
  } catch (e) {
    el.className = 'text-xs text-red-600';
    el.textContent = `❌ 连接失败: ${(e as Error).message}`;
  }
}

/** 初始化侧边栏导航（DOMContentLoaded 时调用一次） */
export function initNavigation(): void {
  document.querySelectorAll('.sidebar-item').forEach((item) => {
    const el = item as HTMLElement;
    el.addEventListener('click', async function (ev) {
      if (this.tagName === 'A') return;
      const page = this.dataset.page;
      if (page) await navigateTo(page);
    });
  });
}

/** 重置所有页面到默认（切换 team/project 时） */
export function resetAllPages(): void {
  document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
  const home = document.getElementById('page-home');
  home?.classList.add('active');
}

// ── 向后兼容 ──────────────────────────────────────────────
if (typeof window !== 'undefined') {
  window.navigateTo = navigateTo;
  window.testConnection = testConnection;
}