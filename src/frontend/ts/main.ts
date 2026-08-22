// ── P123 Phase 1: Vite 入口 ──────────────────────────────
// 渐进式迁移第1步：将 baa-core.js 拆为模块化 TypeScript
// 此入口将所有模块函数挂载到 window，保持与旧 .js 文件兼容
// index.html 加载此 bundle 替代 baa-core.js

import {
  formatDate,
  maskKey,
  escHtml,
  permissionBadge,
  enabledBadge,
  uid,
  mergeDeep,
} from './core/utils';
import { showToast } from './core/toast';
import {
  showSkeleton,
  hideSkeleton,
  renderSkeletonContainer,
  renderProgress,
} from './core/skeleton';
import {
  initApiClient,
  setAdminToken,
  getApiBase,
  getReviewHeaders,
  getHeaders,
  getAdminHeaders,
  apiGet,
  apiPostJSON,
  apiPostFile,
  apiFetch,
  adminGet,
  adminPost,
  adminDelete,
} from './core/api-client';

// ── 初始化 API 客户端 ──────────────────────────────────────
initApiClient({
  apiBase: () => getApiBase(),
  getActiveKeyValue: () => {
    try {
      const stored = localStorage.getItem('baa_api_keys');
      const keys: Array<{ id: string; key: string }> = stored ? JSON.parse(stored) : [];
      const activeKey = localStorage.getItem('baa_active_key') || '';
      const k = keys.find((x) => x.id === activeKey);
      return k ? k.key : '';
    } catch {
      return '';
    }
  },
  currentTeamId: () => localStorage.getItem('baa_team_id') || '',
  currentProjectId: () => localStorage.getItem('baa_project_id') || '',
});

// 初始化 admin token
(async () => {
  try {
    const r = await fetch(getApiBase() + '/admin/bootstrap-key');
    if (r.ok) {
      const d = await r.json();
      if (d.status === 'success' && d.admin_key) setAdminToken(d.admin_key);
    }
  } catch {
    /* dev mode: no admin token needed */
  }
})();

// ── 向后兼容：所有旧全局函数挂载到 window ──────────────────
// Vite 模块构建后，函数不再自动暴露到全局，需手动挂载。
const w = window as unknown as Record<string, unknown>;

w.formatDate = formatDate;
w.maskKey = maskKey;
w.escHtml = escHtml;
w.permissionBadge = permissionBadge;
w.enabledBadge = enabledBadge;
w.uid = uid;
w.mergeDeep = mergeDeep;

w.showToast = showToast;

w.showSkeleton = showSkeleton;
w.hideSkeleton = hideSkeleton;
w.renderSkeletonContainer = renderSkeletonContainer;
w.renderProgress = renderProgress;

w.HEADERS = getReviewHeaders;
w.getHeaders = getHeaders;
w.adminHeaders = getAdminHeaders;
w.API_BASE = getApiBase;
w.apiGet = apiGet;
w.apiPostJSON = apiPostJSON;
w.apiPostFile = apiPostFile;
w.apiFetch = apiFetch;
w.adminGet = adminGet;
w.adminPost = adminPost;
w.adminDelete = adminDelete;

w.apiPost = async (path: string, body: unknown) => apiPostJSON(path, body);

console.log('[P123] Vite TS core modules loaded');