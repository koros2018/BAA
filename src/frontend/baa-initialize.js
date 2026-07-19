// ── 初始化 ──────────────────────────────────────────────
// ── 审查记录 ──────────────────────────────────────────────
function renderHistoryList() {
  const el = document.getElementById('history-list');
  if (!el) return;
  loadReviewResults();
  const search = (document.getElementById('history-search')?.value || '').toLowerCase();
  const filter = document.getElementById('history-filter')?.value || 'all';
  let filtered = reviewResults;
  if (filter === 'civil') filtered = filtered.filter(r => r.buildingType === 'civil');
  else if (filter === 'industrial') filtered = filtered.filter(r => r.buildingType === 'industrial');
  else if (filter === 'violations') filtered = filtered.filter(r => (r.details?.length || 0) > 0);
  else if (filter === 'clean') filtered = filtered.filter(r => (r.details?.length || 0) === 0);
  if (search) {
    filtered = filtered.filter(r =>
      r.drawingName.toLowerCase().includes(search) ||
      (r.details || []).some(v => (v.clause_id || '').toLowerCase().includes(search) || (v.clause_title || '').toLowerCase().includes(search))
    );
  }
  document.getElementById('history-total-count').textContent = filtered.length;
  if (filtered.length === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">无匹配记录</div>';
    return;
  }
  el.innerHTML = filtered.map(r => {
    const viols = r.details?.length || 0;
    const btLabel = r.buildingType === 'civil' ? '民用' : r.buildingType === 'industrial' ? '工业' : '--';
    const criticalCount = (r.details || []).filter(v => v.severity === 'critical').length;
    const timeStr = new Date(r.reviewedAt).toLocaleString();
    const color = viols === 0 ? 'green' : criticalCount > 0 ? 'red' : 'orange';
    return '<div class="card p-3 cursor-pointer hover:shadow-md transition-shadow" onclick="viewHistoryDetail(\'' + r.id + '\')">' +
      '<div class="flex items-center justify-between">' +
      '<div class="flex items-center gap-3">' +
      '<span class="text-' + color + '-500 text-lg">' + (viols === 0 ? '✅' : criticalCount > 0 ? '🔴' : '🟡') + '</span>' +
      '<div><div class="font-medium text-sm">' + r.drawingName + '</div>' +
      '<div class="text-xs text-gray-400">' + btLabel + ' · ' + timeStr + '</div></div></div>' +
      '<div class="text-right"><div class="text-sm font-bold text-' + color + '-600">' + viols + ' 项</div>' +
      '<div class="text-xs text-gray-400">违规</div></div></div></div>';
  }).join('');
}
async function viewHistoryDetail(id) {
  const r = reviewResults.find(x => x.id === id);
  if (!r) return;
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
      details.slice(0, 50).map(v => {
        const sevColor = v.severity === 'critical' ? 'red' : v.severity === 'major' ? 'orange' : 'yellow';
        const sevLabel = v.severity === 'critical' ? '严重' : v.severity === 'major' ? '主要' : '轻微';
        return '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs">' +
          '<div class="flex justify-between"><span class="font-medium">' + (v.clause_title || '') + '</span><span class="px-1.5 py-0.5 rounded bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span></div>' +
          '<span class="text-gray-500">' + (v.clause_id || '') + ' · ' + (v.entity_type || '') + '</span><br/>' +
          '<span class="text-gray-400">' + (v.explanation || '') + '</span></div>';
      }).join('') + (details.length > 50 ? '<div class="text-xs text-gray-400 text-center pt-2">... 仅显示前50项</div>' : '') +
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
  fetch(API_BASE() + '/review/history', { method: 'DELETE' }).catch(() => {});
  renderHistoryList();
  loadDashboard();
}
document.addEventListener('DOMContentLoaded', () => {
  loadApiBase();  // 恢复API地址
  initAdminToken();  // 初始化密钥管理页专用管理令牌
  loadApiKeys();
  populateTokenSelect();

  // API地址变更时自动保存
  document.getElementById('api-base')?.addEventListener('change', saveApiBase);

  // 引擎状态（概览页用）
  try {
    const healthEl = document.getElementById('health-status');
    if (healthEl) {
      const health = JSON.parse(healthEl.textContent || '{}');
    }
  } catch(e) {}

  // 页面加载后异步加载规范库
  if (typeof loadSpecs === 'function') {
    loadSpecs();
  }

  // 引擎状态由 baa-admin.js 中的 initAdminToken 更新
});

// ── 预览缩放 ──────────────────────────────────────────────
function zoomImage(img) {
  if (!img || !img.src || img.style.display === 'none') return;
  let modal = document.getElementById('zoom-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'zoom-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-80 z-50 flex items-center justify-center cursor-zoom-out';
    modal.onclick = function() { modal.remove(); };
    document.body.appendChild(modal);
  }
  modal.innerHTML = '<img src="' + img.src + '" class="max-w-[95vw] max-h-[95vh] object-contain" />';
}

// P43 collab frontend
var collabToken = localStorage.getItem('baa_collab_token') || '';
var collabUser = {};
try { collabUser = JSON.parse(localStorage.getItem('baa_collab_user') || '{}'); } catch(e) {}

