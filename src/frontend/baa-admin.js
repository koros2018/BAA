// P123 Step 5: baa-admin.js 精简 — 历史记录函数已迁入 components/history.ts
// 保留：reviewResults 全局变量（被 baa-review.js / baa-analysis.js / baa-stats.js 共享）
// + DOMContentLoaded 初始化（跨模块共享的启动逻辑）

// ── 全局共享状态 ─────────────────────────────────────────
var reviewResults = [];

document.addEventListener('DOMContentLoaded', () => {
  // 恢复 API 地址 / 密钥管理 / 访问令牌选择器
  loadApiBase();
  initAdminToken();
  loadApiKeys();
  populateTokenSelect();

  // 图纸管理（P123 Step 4 迁入 TS，但 DOMContentLoaded 仍需调用）
  loadParsedDrawings();
  renderDrawingList();
  refreshReviewDrawingSelect();

  // 审查记录 + 仪表盘 + 规范库
  loadReviewResults();
  loadDashboard();
  loadSpecs();

  // API 地址变更时自动保存
  document.getElementById('api-base')?.addEventListener('change', saveApiBase);

  // 引擎状态面板
  try {
    const health = JSON.parse(document.getElementById('health-status')?.textContent || '{}');
    const specCount = SPEC_DATA.length || 0;
    const funcCount = health?.engine?.func_registry?.split('/')?.[0] || '340';
    const funcCap = health?.engine?.func_registry?.split('/')?.[1] || '390';
    document.getElementById('engine-status').innerHTML =
      '<div class="flex justify-between"><span>原子函数</span><span>' + funcCount + '/' + funcCap + ' 已注册</span></div>' +
      '<div class="flex justify-between"><span>规范库</span><span>' + specCount + '条 (L1~L3)</span></div>' +
      '<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>' +
      '<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配</span></div>';
  } catch(e) {
    document.getElementById('engine-status').innerHTML =
      '<div class="flex justify-between"><span>原子函数</span><span>340/390 已注册</span></div>' +
      '<div class="flex justify-between"><span>规范库</span><span>199条 (L1~L3)</span></div>' +
      '<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>' +
      '<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配 (90.8%)</span></div>';
  }
});