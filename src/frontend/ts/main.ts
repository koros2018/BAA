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
import { testConnection as testConn } from './core/page-nav';
// P123 Phase 3: Hash 路由 + 状态管理
import { router } from './core/router';
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
  refreshTokenSelect,
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
import { renderViolationOverlay } from './components/drawing-canvas';
import { runBatchReview as runBatchReviewComponent } from './components/batch-queue';
// P123 Step 2: 组件迁移（baa-review.js → TS）
import { loadDashboard, renderRecentReviews, renderSpecFreqBars, renderViolationTypeBars } from './components/dashboard';
import { loadReviewResults, fallbackLoadReviewResults, refreshCompareDrawingSelect } from './components/review-storage';
import { downloadReviewPdf, downloadReviewExport, downloadReviewJSON } from './components/export';
import { loadFeedbackStats, loadFeedbacks, submitFeedback } from './components/feedback';
import { _onDiffFileSelect, runDiffComparison, renderDiffResults, renderDiffItemPanel, switchDiffTab, loadDiffVisualization, clearDiffResults } from './components/diff-compare';
import { onThermalCompTypeChange, renderThermalThresholds, computeThermalK, renderThermalViolations } from './components/thermal';
import { generateCorrectionSuggestions, confirmCorrection } from './components/correction';
import { renderStructuralThresholds, onStructuralCompTypeChange, computeStructuralCheck, renderStructuralViolations } from './components/structural';
import { loadSpecs, renderSpecList } from './components/specs';
// P123 Step 3: baa-admin.js Zoom + Collab 组件迁入 TS
import {
  zoomImage,
  zoomSet,
  zoomReset,
  zoomFit,
  zoomClose,
} from './components/zoom';
import {
  collabErrMsg,
  collabApi,
  closeCollabModal,
  setModalBody,
  showCollabLogin,
  showCollabRegister,
  collabLogin,
  collabRegister,
  collabLogout,
  collabEnterMain,
  updateUserStatus,
  collabRefresh,
  loadCollabStats,
  loadCollabTeams,
  showCreateTeamModal,
  createTeam,
  showTeamDetail,
  showProjectDetail,
  showCreateProjectModal,
  createProject,
  showCreateReviewSessionModal,
  createReviewSession,
  showReviewSessionDetail,
} from './components/collab';

// ── 初始化 API 客户端 ──────────────────────────────────────
// 注意：apiBase 不能调用 getApiBase()（会无限递归），直接读 DOM
initApiClient({
  apiBase: () =>
    (document.getElementById('api-base') as HTMLInputElement | null)?.value ||
    'http://localhost:8000',
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
w.refreshTokenSelect = refreshTokenSelect;

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

// P123 Step 2: 组件挂载（baa-review.js → TS）
w.loadDashboard = loadDashboard;
w.renderRecentReviews = renderRecentReviews;
w.renderSpecFreqBars = renderSpecFreqBars;
w.renderViolationTypeBars = renderViolationTypeBars;
w.loadReviewResults = loadReviewResults;
w.fallbackLoadReviewResults = fallbackLoadReviewResults;
w.refreshCompareDrawingSelect = refreshCompareDrawingSelect;
w.downloadReviewPdf = downloadReviewPdf;
w.downloadReviewExport = downloadReviewExport;
w.downloadReviewJSON = downloadReviewJSON;
w.loadFeedbackStats = loadFeedbackStats;
w.loadFeedbacks = loadFeedbacks;
w.submitFeedback = submitFeedback;
w._onDiffFileSelect = _onDiffFileSelect;
w.runDiffComparison = runDiffComparison;
w.renderDiffResults = renderDiffResults;
w.renderDiffItemPanel = renderDiffItemPanel;
w.switchDiffTab = switchDiffTab;
w.loadDiffVisualization = loadDiffVisualization;
w.clearDiffResults = clearDiffResults;
w.onThermalCompTypeChange = onThermalCompTypeChange;
w.renderThermalThresholds = renderThermalThresholds;
w.computeThermalK = computeThermalK;
w.renderThermalViolations = renderThermalViolations;
w.generateCorrectionSuggestions = generateCorrectionSuggestions;
w.confirmCorrection = confirmCorrection;
w.renderStructuralThresholds = renderStructuralThresholds;
w.onStructuralCompTypeChange = onStructuralCompTypeChange;
w.computeStructuralCheck = computeStructuralCheck;
w.renderStructuralViolations = renderStructuralViolations;

// P123 Step 3: baa-admin.js specs / zoom / collab 组件
w.loadSpecs = loadSpecs;
w.renderSpecList = renderSpecList;

w.zoomImage = zoomImage;
w.zoomSet = zoomSet;
w.zoomReset = zoomReset;
w.zoomFit = zoomFit;
w.zoomClose = zoomClose;

w.collabErrMsg = collabErrMsg;
w.collabApi = collabApi;
w.closeCollabModal = closeCollabModal;
w.setModalBody = setModalBody;
w.showCollabLogin = showCollabLogin;
w.showCollabRegister = showCollabRegister;
w.collabLogin = collabLogin;
w.collabRegister = collabRegister;
w.collabLogout = collabLogout;
w.collabEnterMain = collabEnterMain;
w.updateUserStatus = updateUserStatus;
w.collabRefresh = collabRefresh;
w.loadCollabStats = loadCollabStats;
w.loadCollabTeams = loadCollabTeams;
w.showCreateTeamModal = showCreateTeamModal;
w.createTeam = createTeam;
w.showTeamDetail = showTeamDetail;
w.showProjectDetail = showProjectDetail;
w.showCreateProjectModal = showCreateProjectModal;
w.createProject = createProject;
w.showCreateReviewSessionModal = showCreateReviewSessionModal;
w.createReviewSession = createReviewSession;
w.showReviewSessionDetail = showReviewSessionDetail;

w.testConnection = testConn;
w.router = router;

// SPEC_DATA 已在 spec-data.ts 中挂载到 window，此处不重复定义

w.importServerKey = importServerKey;
w.importSelectedKey = importSelectedKey;
w.closeImportKeyModal = closeImportKeyModal;

// P123 Phase 2: 组件挂载
w.openModal = openModal;
w.renderFilterBar = renderFilterBar;
w.renderReviewItem = renderReviewItem;
w.renderReviewTable = renderReviewTable;
w.renderViolationOverlay = renderViolationOverlay;
w.runBatchReviewComponent = runBatchReviewComponent;

// P123 Phase 3: router 已在构造函数中初始化 hash 路由 + popstate/hashchange 监听
// 不再需要旧的 sidebar onclick 监听（page-nav.ts 的 initNavigation 已由 router 替代）

console.log('[P123] Vite TS core modules loaded');
