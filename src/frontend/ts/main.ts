// ── P123 Phase 1: Vite 入口 ──────────────────────────────
// 渐进式迁移第1步：将 baa-core.js 拆为模块化 TypeScript
// 此入口将所有模块函数挂载到 window，保持与旧 .js 文件兼容

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
import { appState } from './core/state';
import { initNavigation, testConnection as testConn } from './core/page-nav';
import {
  loadKeys,
  getActiveKeyValue,
  getKeys,
  setActiveKey,
  populateTokenSelect,
  switchApiKey,
  deleteCurrentApiKey,
  addApiKey,
  deleteApiKey,
  copyApiKey,
} from './core/key-manager';
import {
  initAdminToken,
  loadAdminKeys,
  openCreateKeyModal,
  closeCreateKeyModal,
  createAdminKey,
  copyCreatedKey,
  closeKeyCreatedModal,
  showKeyDetail,
  showDetailRawKey,
  copyDetailRawKey,
  copyKeyFromDetail,
  closeKeyDetailModal,
  confirmRevokeKey,
  confirmDeleteKey,
  revokeAdminKey,
} from './core/admin-keys';
import {
  showDrawingReviewPanel,
  switchDrawingTab,
  loadReviewContext,
  onReviewTeamSelect,
  onReviewProjectSelect,
} from './core/review-panel';
import { getSpecData, setSpecData } from './core/spec-data';
import {
  importServerKey,
  importSelectedKey,
  closeImportKeyModal,
} from './core/import-key';
// P123 Phase 2: 组件化 — Modal / FilterBar / ReviewItem / ReviewTable
import { openModal } from './components/modal';
import { renderFilterBar } from './components/filter-bar';
import { renderReviewItem } from './components/review-item';
import { renderReviewTable } from './components/review-table';

// ── 初始化 API 客户端 ──────────────────────────────────────
initApiClient({
  apiBase: () => getApiBase(),
  getActiveKeyValue,
  currentTeamId: () => appState.teamId,
  currentProjectId: () => appState.projectId,
});

// ── 初始化 admin token ────────────────────────────────────
initAdminToken();

// ── 向后兼容：所有旧全局函数挂载到 window ──────────────────
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

w.getCurrentTeamId = () => appState.teamId;
w.getCurrentProjectId = () => appState.projectId;
w.setCurrentTeamId = (id?: string) => appState.setTeamId(id || '');
w.setCurrentProjectId = (id?: string) => appState.setProjectId(id || '');
w.loadApiBase = () => appState.loadApiBase();
w.saveApiBase = () => appState.saveApiBase();

w.getApiKey = () => getActiveKeyValue();
w.getActiveKeyValue = getActiveKeyValue;
w.loadApiKeys = loadKeys;
w.saveApiKeys = () => {};
w.switchApiKey = switchApiKey;
w.deleteCurrentApiKey = deleteCurrentApiKey;
w.addApiKey = addApiKey;
w.deleteApiKey = deleteApiKey;
w.copyApiKey = copyApiKey;
w.populateTokenSelect = populateTokenSelect;

w.initAdminToken = initAdminToken;
w.loadAdminKeys = loadAdminKeys;
w.openCreateKeyModal = openCreateKeyModal;
w.closeCreateKeyModal = closeCreateKeyModal;
w.createAdminKey = createAdminKey;
w.copyCreatedKey = copyCreatedKey;
w.closeKeyCreatedModal = closeKeyCreatedModal;
w.showKeyDetail = showKeyDetail;
w.showDetailRawKey = showDetailRawKey;
w.copyDetailRawKey = copyDetailRawKey;
w.copyKeyFromDetail = copyKeyFromDetail;
w.closeKeyDetailModal = closeKeyDetailModal;
w.confirmRevokeKey = confirmRevokeKey;
w.confirmDeleteKey = confirmDeleteKey;
w.revokeAdminKey = revokeAdminKey;

w.showDrawingReviewPanel = showDrawingReviewPanel;
w.switchDrawingTab = switchDrawingTab;
w.loadReviewContext = loadReviewContext;
w.onReviewTeamSelect = onReviewTeamSelect;
w.onReviewProjectSelect = onReviewProjectSelect;

w.testConnection = testConn;

// SPEC_DATA 挂载到 window（baa-admin.js / baa-review.js 直接引用）
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'SPEC_DATA', {
    get: () => getSpecData(),
    set: (v: unknown) => setSpecData(v as Array<Record<string, unknown>>),
  });
}

w.importServerKey = importServerKey;
w.importSelectedKey = importSelectedKey;
w.closeImportKeyModal = closeImportKeyModal;

// P123 Phase 2: 组件挂载
w.openModal = openModal;
w.renderFilterBar = renderFilterBar;
w.renderReviewItem = renderReviewItem;
w.renderReviewTable = renderReviewTable;

// 页面加载完成时初始化导航
document.addEventListener('DOMContentLoaded', initNavigation);

console.log('[P123] Vite TS core modules loaded');