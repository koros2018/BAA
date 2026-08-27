// ── P123 Step 7: 应用初始化组件 ────────────────────────
// 从 baa-admin.js 迁入（最后 45 行 DOMContentLoaded 初始化）

import { appState } from '../core/state';
import { initAdminToken } from '../core/admin-keys';
import { loadKeys as loadKeysFn, populateTokenSelect } from '../core/key-manager';
import { loadParsedDrawings, renderDrawingList, refreshReviewDrawingSelect } from './drawing';
import { loadReviewResults } from './review-storage';
import { loadDashboard } from './dashboard';
import { loadSpecs } from './specs';

// ── 全局共享状态（旧 JS 依赖） ──────────────────────────
declare global {
  var reviewResults: Array<Record<string, unknown>>;
  var SPEC_DATA: Array<Record<string, unknown>>;
}

if (!window.reviewResults) {
  window.reviewResults = [];
}

function renderEngineStatus(): void {
  const el = document.getElementById('engine-status');
  if (!el) return;
  try {
    const text = (document.getElementById('health-status') as HTMLElement | null)?.textContent || '{}';
    const health = JSON.parse(text) as { engine?: { func_registry?: string } };
    const specCount = (window.SPEC_DATA as unknown[])?.length || 0;
    const [funcCount = '340', funcCap = '390'] = (health.engine?.func_registry || '340/390').split('/');
    el.innerHTML =
      `<div class="flex justify-between"><span>原子函数</span><span>${funcCount}/${funcCap} 已注册</span></div>` +
      `<div class="flex justify-between"><span>规范库</span><span>${specCount}条 (L1~L3)</span></div>` +
      `<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>` +
      `<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配</span></div>`;
  } catch {
    el.innerHTML =
      `<div class="flex justify-between"><span>原子函数</span><span>340/390 已注册</span></div>` +
      `<div class="flex justify-between"><span>规范库</span><span>199条 (L1~L3)</span></div>` +
      `<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>` +
      `<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配 (90.8%)</span></div>`;
  }
}

export function initApp(): void {
  appState.loadApiBase();
  initAdminToken();
  loadKeysFn();
  populateTokenSelect();

  loadParsedDrawings();
  renderDrawingList();
  refreshReviewDrawingSelect();

  loadReviewResults();
  loadDashboard();
  loadSpecs();

  const apiBase = document.getElementById('api-base');
  apiBase?.addEventListener('change', () => appState.saveApiBase());

  renderEngineStatus();
}
