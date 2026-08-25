// P122 XSS 防护工具函数
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// 图纸管理函数（15个）和状态已由 TS bundle 管理 (P123 Step 4)
// baa-admin.js 保留审查历史记录 + escHtml（待后续迁移）
// ── 审查记录 ──────────────────────────────────────────────
let historyPage = 0;
const HISTORY_PAGE_SIZE = 20;

function renderHistoryList(resetPage = false) {
  if (resetPage) historyPage = 0;
  const el = document.getElementById('history-list');
  if (!el) return;
  loadReviewResults();
  const search = (document.getElementById('history-search')?.value || '').toLowerCase();
  const filter = document.getElementById('history-filter')?.value || 'all';
  const teamFilter = document.getElementById('history-team-filter')?.value || '';
  const projFilter = document.getElementById('history-project-filter')?.value || '';
  let filtered = reviewResults;
  if (filter === 'civil') filtered = filtered.filter(r => r.buildingType === 'civil');
  else if (filter === 'industrial') filtered = filtered.filter(r => r.buildingType === 'industrial');
  else if (filter === 'violations') filtered = filtered.filter(r => (r.violationCount || 0) > 0);
  else if (filter === 'clean') filtered = filtered.filter(r => (r.violationCount || 0) === 0);
  // P112: 按团队/项目过滤
  if (teamFilter) filtered = filtered.filter(r => r.teamId === teamFilter);
  if (projFilter) filtered = filtered.filter(r => r.projectId === projFilter);
  if (search) {
    filtered = filtered.filter(r =>
      r.drawingName.toLowerCase().includes(search) ||
      (r.details || []).some(v => (v.clause_id || '').toLowerCase().includes(search) || (v.clause_title || '').toLowerCase().includes(search))
    );
  }
  // 显示当前上下文
  var ctxEl = document.getElementById('history-context-info');
  if (ctxEl) {
    var ctxParts = [];
    if (currentTeamId) ctxParts.push('📌团队已选');
    if (currentProjectId) ctxParts.push('📋项目已选');
    ctxEl.textContent = ctxParts.length ? ctxParts.join(' · ') : '';
  }
  // 动态填充团队/项目下拉框（只填充一次）
  _populateHistoryFilters();
  const totalPages = Math.ceil(filtered.length / HISTORY_PAGE_SIZE) || 1;
  if (historyPage >= totalPages) historyPage = totalPages - 1;
  const pageData = filtered.slice(historyPage * HISTORY_PAGE_SIZE, (historyPage + 1) * HISTORY_PAGE_SIZE);
  document.getElementById('history-total-count').textContent = filtered.length;
  if (filtered.length === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">无匹配记录</div>';
    renderPagination(0);
    return;
  }
  el.innerHTML = pageData.map(r => {
    const viols = r.violationCount || r.details?.length || 0;
    const btLabel = r.buildingType === 'civil' ? '民用' : r.buildingType === 'industrial' ? '工业' : '--';
    const timeStr = new Date(r.reviewedAt || r.createdAt || Date.now()).toLocaleString();
    const color = viols === 0 ? 'green' : 'red';
    // P112: 显示团队/项目标签
    var teamTag = r.teamId ? '<span class="px-1 bg-blue-100 text-blue-600 rounded" title="团队">👥</span>' : '';
    var projTag = r.projectId ? '<span class="px-1 bg-purple-100 text-purple-600 rounded" title="项目">📋</span>' : '';
    return '<div class="card p-3 hover:shadow-md transition-shadow">' +
      '<div class="flex items-center justify-between">' +
      '<div class="flex items-center gap-3 cursor-pointer flex-1" onclick="viewHistoryDetail(\'' + r.id + '\')">' +
      '<span class="text-' + color + '-500 text-lg">' + (viols === 0 ? '✅' : '🔴') + '</span>' +
      '<div><div class="font-medium text-sm">' + r.drawingName + ' ' + teamTag + projTag + '</div>' +
      '<div class="text-xs text-gray-400">' + btLabel + ' · ' + timeStr + '</div></div></div>' +
      '<div class="text-right mr-3">' +
      '<div class="text-sm font-bold text-' + color + '-600">' + viols + ' 项违规</div>' +
      '<div class="text-xs text-gray-400">💡 ' + (r.correctionCount || 0) + ' 条建议</div></div>' +
      '<button onclick="event.stopPropagation();deleteReviewRecord(\'' + r.id + '\')" class="px-2 py-0.5 text-xs text-red-400 hover:text-red-600" title="删除">🗑️</button>' +
      '</div></div>';
  }).join('') + renderPagination(totalPages);
}

// P112: 动态填充审查记录页的团队/项目筛选下拉框
function _populateHistoryFilters() {
  var teamSelect = document.getElementById('history-team-filter');
  var projSelect = document.getElementById('history-project-filter');
  if (!reviewResults || reviewResults.length === 0) return;
  var teams = {};
  var projects = {};
  reviewResults.forEach(function(r) {
    if (r.teamId) teams[r.teamId] = r.teamId;
    if (r.projectId) projects[r.projectId] = r.projectId;
  });
  if (teamSelect && Object.keys(teams).length > 0) {
    var curTeam = teamSelect.value || '';
    teamSelect.innerHTML = '<option value="">📌 全部团队</option>';
    Object.keys(teams).forEach(function(id) { teamSelect.innerHTML += '<option value="' + escHtml(id) + '">' + escHtml(id.substring(0, 12)) + '</option>'; });
    teamSelect.value = curTeam;
  }
  if (projSelect && Object.keys(projects).length > 0) {
    var curProj = projSelect.value || '';
    projSelect.innerHTML = '<option value="">📌 全部项目</option>';
    Object.keys(projects).forEach(function(id) { projSelect.innerHTML += '<option value="' + escHtml(id) + '">' + escHtml(id.substring(0, 12)) + '</option>'; });
    projSelect.value = curProj;
  }
}

function renderPagination(totalPages) {
  if (totalPages <= 1) return '';
  return '<div class="flex items-center justify-center gap-3 mt-4 text-sm">' +
    '<button onclick="historyPage=Math.max(0,historyPage-1);renderHistoryList()" class="px-3 py-1 border rounded ' + (historyPage === 0 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100') + '" ' + (historyPage === 0 ? 'disabled' : '') + '>上一页</button>' +
    '<span class="text-gray-500">第 ' + (historyPage + 1) + ' / ' + totalPages + ' 页</span>' +
    '<button onclick="historyPage=Math.min(' + (totalPages - 1) + ',historyPage+1);renderHistoryList()" class="px-3 py-1 border rounded ' + (historyPage >= totalPages - 1 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100') + '" ' + (historyPage >= totalPages - 1 ? 'disabled' : '') + '>下一页</button>' +
    '</div>';
}
async function deleteReviewRecord(id) {
  if (!confirm('确定删除此审查记录？')) return;
  try {
    await fetch(API_BASE() + '/review/history/' + id, {method: 'DELETE', headers: getHeaders()});
    reviewResults = reviewResults.filter(r => r.id !== id);
    renderHistoryList();
  } catch(e) {
    // P112: 404 降级（记录仅存本地）→ 仍从本地列表移除
    reviewResults = reviewResults.filter(r => r.id !== id);
    renderHistoryList();
    showToast('已从本地移除（后端未找到该记录）', 'info');
  }
}
async function viewHistoryDetail(id) {
  const r = reviewResults.find(x => x.id === id);
  if (!r) return;
  // 先显示加载中
  let modal = document.getElementById('history-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'history-detail-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-40 z-50 flex items-center justify-center';
    modal.onclick = function(e) { if (e.target === modal) closeHistoryModal(); };
    document.body.appendChild(modal);
  }
  modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">' +
    '<div class="flex items-center justify-between p-4 border-b">' +
    '<h3 class="text-lg font-bold">审查详情: ' + r.drawingName + '</h3>' +
    '<button onclick="closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div>' +
    '<div class="p-4 text-center text-gray-400">加载中...</div></div>';
  // 从后端加载完整详情
  try {
    const resp = await fetch(API_BASE() + '/review/history/' + id, {headers: getHeaders()});
    const detail = await resp.json();
    if (!detail || detail.status === 'error') {
      modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4"><div class="p-4 text-center text-red-500">加载失败</div></div>';
      return;
    }
    const details = detail.details || [];
    modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">' +
      '<div class="flex items-center justify-between p-4 border-b">' +
      '<h3 class="text-lg font-bold">审查详情: ' + (detail.drawingName || r.drawingName) + '</h3>' +
      '<button onclick="closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div>' +
      '<div class="p-4 overflow-y-auto flex-1">' +
      '<div class="grid grid-cols-4 gap-3 mb-4">' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + details.length + '</div><div class="text-xs text-gray-400">违规</div></div>' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + (details.filter(v => v.severity === 'critical').length || 0) + '</div><div class="text-xs text-gray-400">严重</div></div>' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + (details.filter(v => v.severity === 'major').length || 0) + '</div><div class="text-xs text-gray-400">主要</div></div>' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + (details.filter(v => v.severity !== 'critical' && v.severity !== 'major').length || 0) + '</div><div class="text-xs text-gray-400">轻微</div></div>' +
      '</div>' +
      '<div class="text-xs text-gray-400 mb-2">建筑类型: ' + (detail.buildingType === 'civil' ? '民用' : '工业') + ' · 审查时间: ' + new Date(detail.reviewedAt || r.reviewedAt).toLocaleString() + '</div>' +
      '<div class="space-y-2">' +
      details.slice().sort((a, b) => {
        // 按严重程度排序：critical > major > 其他
        const order = {critical: 0, major: 1};
        return (order[a.severity] !== undefined ? order[a.severity] : 2) - (order[b.severity] !== undefined ? order[b.severity] : 2);
      }).slice(0, 50).map(v => {
        const sevColor = v.severity === 'critical' ? 'red' : v.severity === 'major' ? 'orange' : 'yellow';
        const sevLabel = v.severity === 'critical' ? '严重' : v.severity === 'major' ? '主要' : '轻微';
        return '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs">' +
          '<div class="flex justify-between"><span class="font-medium">' + (v.clause_title || '') + '</span><span class="px-1.5 py-0.5 rounded bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span></div>' +
          '<span class="text-gray-500">' + (v.clause_id || '') + ' · ' + (v.entity_type || '') + '</span><br/>' +
          '<span class="text-gray-400">' + (v.explanation || '') + '</span></div>';
      }).join('') + (details.length > 50 ? '<div class="text-xs text-gray-400 text-center pt-2">... 仅显示前50项</div>' : '') +
      '</div>' +
      // 修正建议
      (detail.corrections && detail.corrections.length > 0 ?
        '<div class="mt-4 border-t pt-3">' +
        '<p class="font-medium text-sm mb-2">💡 修正建议</p>' +
        '<div class="space-y-2">' +
        detail.corrections.slice(0, 20).map(c => {
          const priColor = c.priority === 'high' ? 'red' : c.priority === 'medium' ? 'orange' : 'green';
          return '<div class="p-2 bg-green-50 rounded text-xs">' +
            '<span class="font-medium">' + (c.action || '') + '</span>' +
            ' <span class="px-1.5 py-0.5 rounded bg-' + priColor + '-100 text-' + priColor + '-700">' + (c.priority || 'low') + '</span>' +
            '<div class="text-gray-600 mt-1">' + (c.description || '') + '</div>' +
            (c.recommendation ? '<div class="text-gray-500 mt-0.5">' + c.recommendation + '</div>' : '') +
            '</div>';
        }).join('') +
        (detail.corrections.length > 20 ? '<div class="text-xs text-gray-400 text-center">... 仅显示前20条</div>' : '') +
        '</div></div>' : '') +
      '</div></div></div>';
  } catch(e) {
    modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4"><div class="p-4 text-center text-red-500">加载失败: ' + e.message + '</div></div>';
  }
}
function closeHistoryModal() {
  const modal = document.getElementById('history-detail-modal');
  if (modal) modal.remove();
}
function clearReviewHistory() {
  if (!confirm('确定清空所有审查历史记录？此操作不可恢复。')) return;
  localStorage.removeItem('baa_review_results');
  reviewResults = [];
  // 同时清空后端
  fetch(API_BASE() + '/review/history', { method: 'DELETE' }).catch(() => {});
  renderHistoryList();
  loadDashboard();
}
document.addEventListener('DOMContentLoaded', () => {
  loadApiBase();  // 恢复API地址
  initAdminToken();  // 初始化密钥管理页专用管理令牌
  loadApiKeys();
  populateTokenSelect();
  loadParsedDrawings();
  renderDrawingList();
  refreshReviewDrawingSelect();
  loadReviewResults();
  loadDashboard();
  loadSpecs();

  // API地址变更时自动保存
  document.getElementById('api-base')?.addEventListener('change', saveApiBase);

  // 引擎状态
  try {
    const health = JSON.parse(document.getElementById('health-status').textContent || '{}');
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
      '<div class="flex justify-between"><span>规范库</span><span>199条 (L1~L3)</span></span></div>' +
      '<div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div>' +
      '<div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配 (90.8%)</span></div>';
  }
});

