// ── P123 Step 5: 审查历史记录组件 ────────────────────────
// 从 baa-admin.js 迁入 — 6 个函数（renderHistoryList / _populateHistoryFilters /
// renderPagination / deleteReviewRecord / viewHistoryDetail / closeHistoryModal /
// clearReviewHistory）+ escHtml 工具函数

import { getApiBase, getHeaders } from '../core/api-client';
import { showToast } from '../core/toast';
import { loadDashboard } from './dashboard';
import { loadReviewResults } from './review-storage';

// ── XSS 防护 ──────────────────────────────────────────────
export function escHtml(str: unknown): string {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── 页面状态 ──────────────────────────────────────────────
// historyPage 通过 window 暴露（main.ts getter/setter），以支持 onclick 内联脚本修改
const HISTORY_PAGE_SIZE = 20;
function _historyPage(): number {
  const w = window as unknown as Record<string, unknown>;
  return (w.historyPage as number) || 0;
}
function _setHistoryPage(v: number): void {
  const w = window as unknown as Record<string, unknown>;
  w.historyPage = v;
}

// 获取全局 reviewResults（与 baa-review.js / baa-analysis.js / baa-stats.js 共享）
function _getReviewResults(): Array<Record<string, unknown>> {
  const w = window as unknown as Record<string, unknown>;
  return (w.reviewResults as Array<Record<string, unknown>>) || [];
}

function _setReviewResults(r: Array<Record<string, unknown>>): void {
  const w = window as unknown as Record<string, unknown>;
  w.reviewResults = r;
}

// ── 渲染审查记录列表 ──────────────────────────────────────
export function renderHistoryList(resetPage = false): void {
  if (resetPage) _setHistoryPage(0);
  const el = document.getElementById('history-list');
  if (!el) return;
  loadReviewResults();
  const search = ((document.getElementById('history-search') as HTMLInputElement | null)?.value || '').toLowerCase();
  const filter = (document.getElementById('history-filter') as HTMLSelectElement | null)?.value || 'all';
  const teamFilter = (document.getElementById('history-team-filter') as HTMLSelectElement | null)?.value || '';
  const projFilter = (document.getElementById('history-project-filter') as HTMLSelectElement | null)?.value || '';
  let filtered = _getReviewResults();
  if (filter === 'civil') filtered = filtered.filter(r => r.buildingType === 'civil');
  else if (filter === 'industrial') filtered = filtered.filter(r => r.buildingType === 'industrial');
  else if (filter === 'violations') filtered = filtered.filter(r => (r.violationCount as number || 0) > 0);
  else if (filter === 'clean') filtered = filtered.filter(r => (r.violationCount as number || 0) === 0);

  if (teamFilter) filtered = filtered.filter(r => r.teamId === teamFilter);
  if (projFilter) filtered = filtered.filter(r => r.projectId === projFilter);
  if (search) {
    filtered = filtered.filter(r =>
      String(r.drawingName || '').toLowerCase().includes(search) ||
      ((r.details as Array<Record<string, unknown>>) || []).some(v =>
        String(v.clause_id || '').toLowerCase().includes(search) ||
        String(v.clause_title || '').toLowerCase().includes(search)
      )
    );
  }

  const ctxEl = document.getElementById('history-context-info');
  if (ctxEl) {
    const w = window as unknown as Record<string, unknown>;
    const ctxParts: string[] = [];
    if (w.currentTeamId) ctxParts.push('📌团队已选');
    if (w.currentProjectId) ctxParts.push('📋项目已选');
    ctxEl.textContent = ctxParts.length ? ctxParts.join(' · ') : '';
  }

  _populateHistoryFilters();
  const totalPages = Math.ceil(filtered.length / HISTORY_PAGE_SIZE) || 1;
  if (_historyPage() >= totalPages) _setHistoryPage(totalPages - 1);
  const pageData = filtered.slice(_historyPage() * HISTORY_PAGE_SIZE, (_historyPage() + 1) * HISTORY_PAGE_SIZE);

  const countEl = document.getElementById('history-total-count');
  if (countEl) countEl.textContent = String(filtered.length);

  if (filtered.length === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">无匹配记录</div>';
    renderPagination(0);
    return;
  }

  el.innerHTML = pageData.map(r => {
    const viols = (r.violationCount as number) || (r.details as Array<unknown>)?.length || 0;
    const btLabel = r.buildingType === 'civil' ? '民用' : r.buildingType === 'industrial' ? '工业' : '--';
    const timeStr = new Date(String(r.reviewedAt || r.createdAt || Date.now())).toLocaleString();
    const color = viols === 0 ? 'green' : 'red';
    const teamTag = r.teamId ? '<span class="px-1 bg-blue-100 text-blue-600 rounded" title="团队">👥</span>' : '';
    const projTag = r.projectId ? '<span class="px-1 bg-purple-100 text-purple-600 rounded" title="项目">📋</span>' : '';
    const id = escHtml(String(r.id || ''));
    const name = escHtml(String(r.drawingName || ''));
    return '<div class="card p-3 hover:shadow-md transition-shadow">' +
      '<div class="flex items-center justify-between">' +
      '<div class="flex items-center gap-3 cursor-pointer flex-1" onclick="window.viewHistoryDetail(\'' + id + '\')">' +
      '<span class="text-' + color + '-500 text-lg">' + (viols === 0 ? '✅' : '🔴') + '</span>' +
      '<div><div class="font-medium text-sm">' + name + ' ' + teamTag + projTag + '</div>' +
      '<div class="text-xs text-gray-400">' + btLabel + ' · ' + timeStr + '</div></div></div>' +
      '<div class="text-right mr-3">' +
      '<div class="text-sm font-bold text-' + color + '-600">' + viols + ' 项违规</div>' +
      '<div class="text-xs text-gray-400">💡 ' + (r.correctionCount || 0) + ' 条建议</div></div>' +
      '<button onclick="event.stopPropagation();window.deleteReviewRecord(\'' + id + '\')" class="px-2 py-0.5 text-xs text-red-400 hover:text-red-600" title="删除">🗑️</button>' +
      '</div></div>';
  }).join('') + renderPagination(totalPages);
}

// ── 动态填充筛选下拉框 ──────────────────────────────────
function _populateHistoryFilters(): void {
  const teamSelect = document.getElementById('history-team-filter') as HTMLSelectElement | null;
  const projSelect = document.getElementById('history-project-filter') as HTMLSelectElement | null;
  const results = _getReviewResults();
  if (!results || results.length === 0) return;

  const teams: Record<string, string> = {};
  const projects: Record<string, string> = {};
  results.forEach(r => {
    if (r.teamId) teams[String(r.teamId)] = String(r.teamId);
    if (r.projectId) projects[String(r.projectId)] = String(r.projectId);
  });

  if (teamSelect && Object.keys(teams).length > 0) {
    const curTeam = teamSelect.value || '';
    teamSelect.innerHTML = '<option value="">📌 全部团队</option>';
    Object.keys(teams).forEach(id => {
      teamSelect.innerHTML += '<option value="' + escHtml(id) + '">' + escHtml(id.substring(0, 12)) + '</option>';
    });
    teamSelect.value = curTeam;
  }

  if (projSelect && Object.keys(projects).length > 0) {
    const curProj = projSelect.value || '';
    projSelect.innerHTML = '<option value="">📌 全部项目</option>';
    Object.keys(projects).forEach(id => {
      projSelect.innerHTML += '<option value="' + escHtml(id) + '">' + escHtml(id.substring(0, 12)) + '</option>';
    });
    projSelect.value = curProj;
  }
}

// ── 分页 ──────────────────────────────────────────────────
export function renderPagination(totalPages: number): string {
  if (totalPages <= 1) return '';
  return '<div class="flex items-center justify-center gap-3 mt-4 text-sm">' +
    '<button onclick="window.historyPage=Math.max(0,window.historyPage-1);window.renderHistoryList()" class="px-3 py-1 border rounded ' + (_historyPage() === 0 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100') + '" ' + (_historyPage() === 0 ? 'disabled' : '') + '>上一页</button>' +
    '<span class="text-gray-500">第 ' + (_historyPage() + 1) + ' / ' + totalPages + ' 页</span>' +
    '<button onclick="window.historyPage=Math.min(' + (totalPages - 1) + ',window.historyPage+1);window.renderHistoryList()" class="px-3 py-1 border rounded ' + (_historyPage() >= totalPages - 1 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100') + '" ' + (_historyPage() >= totalPages - 1 ? 'disabled' : '') + '>下一页</button>' +
    '</div>';
}

// ── 删除记录 ──────────────────────────────────────────────
export async function deleteReviewRecord(id: string): Promise<void> {
  if (!confirm('确定删除此审查记录？')) return;
  try {
    await fetch(getApiBase() + '/review/history/' + id, { method: 'DELETE', headers: getHeaders() });
    const results = _getReviewResults().filter(r => r.id !== id);
    _setReviewResults(results);
    renderHistoryList();
  } catch (_e) {
    const results = _getReviewResults().filter(r => r.id !== id);
    _setReviewResults(results);
    renderHistoryList();
    showToast('已从本地移除（后端未找到该记录）', 'info');
  }
}

// ── 查看详情 ──────────────────────────────────────────────
export async function viewHistoryDetail(id: string): Promise<void> {
  const r = _getReviewResults().find(x => String(x.id) === id);
  if (!r) return;

  let modal = document.getElementById('history-detail-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'history-detail-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-40 z-50 flex items-center justify-center';
    modal.onclick = function (e) { if (e.target === modal) closeHistoryModal(); };
    document.body.appendChild(modal);
  }

  const name = escHtml(String(r.drawingName || ''));
  modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">' +
    '<div class="flex items-center justify-between p-4 border-b">' +
    '<h3 class="text-lg font-bold">审查详情: ' + name + '</h3>' +
    '<button onclick="window.closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div>' +
    '<div class="p-4 text-center text-gray-400">加载中...</div></div>';

  try {
    const resp = await fetch(getApiBase() + '/review/history/' + id, { headers: getHeaders() });
    const detail = (await resp.json()) as Record<string, unknown>;
    if (!detail || detail.status === 'error') {
      modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4"><div class="p-4 text-center text-red-500">加载失败</div></div>';
      return;
    }

    const details = (detail.details as Array<Record<string, unknown>>) || [];
    const detailName = escHtml(String(detail.drawingName || r.drawingName || ''));
    const btLabel = detail.buildingType === 'civil' ? '民用' : '工业';
    const reviewTime = new Date(String(detail.reviewedAt || r.reviewedAt)).toLocaleString();

    const criticalCount = details.filter(v => v.severity === 'critical').length || 0;
    const majorCount = details.filter(v => v.severity === 'major').length || 0;
    const minorCount = details.filter(v => v.severity !== 'critical' && v.severity !== 'major').length || 0;

    let dm = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">' +
      '<div class="flex items-center justify-between p-4 border-b">' +
      '<h3 class="text-lg font-bold">审查详情: ' + detailName + '</h3>' +
      '<button onclick="window.closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div>' +
      '<div class="p-4 overflow-y-auto flex-1">' +
      '<div class="grid grid-cols-4 gap-3 mb-4">' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + details.length + '</div><div class="text-xs text-gray-400">违规</div></div>' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + criticalCount + '</div><div class="text-xs text-gray-400">严重</div></div>' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + majorCount + '</div><div class="text-xs text-gray-400">主要</div></div>' +
      '<div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + minorCount + '</div><div class="text-xs text-gray-400">轻微</div></div>' +
      '</div>' +
      '<div class="text-xs text-gray-400 mb-2">建筑类型: ' + btLabel + ' · 审查时间: ' + reviewTime + '</div>' +
      '<div class="space-y-2">';

    details.slice().sort((a, b) => {
      const order: Record<string, number> = { critical: 0, major: 1 };
      return (order[String(a.severity)] !== undefined ? order[String(a.severity)] : 2) -
             (order[String(b.severity)] !== undefined ? order[String(b.severity)] : 2);
    }).slice(0, 50).forEach(v => {
      const sevColor = v.severity === 'critical' ? 'red' : v.severity === 'major' ? 'orange' : 'yellow';
      const sevLabel = v.severity === 'critical' ? '严重' : v.severity === 'major' ? '主要' : '轻微';
      dm += '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs">' +
        '<div class="flex justify-between"><span class="font-medium">' + escHtml(String(v.clause_title || '')) + '</span><span class="px-1.5 py-0.5 rounded bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span></div>' +
        '<span class="text-gray-500">' + escHtml(String(v.clause_id || '')) + ' · ' + escHtml(String(v.entity_type || '')) + '</span><br/>' +
        '<span class="text-gray-400">' + escHtml(String(v.explanation || '')) + '</span></div>';
    });
    dm += (details.length > 50 ? '<div class="text-xs text-gray-400 text-center pt-2">... 仅显示前50项</div>' : '') +
      '</div>';

    // 修正建议
    const corrections = (detail.corrections as Array<Record<string, unknown>>) || [];
    if (corrections.length > 0) {
      dm += '<div class="mt-4 border-t pt-3">' +
        '<p class="font-medium text-sm mb-2">💡 修正建议</p>' +
        '<div class="space-y-2">';
      corrections.slice(0, 20).forEach(c => {
        const priColor = c.priority === 'high' ? 'red' : c.priority === 'medium' ? 'orange' : 'green';
        dm += '<div class="p-2 bg-green-50 rounded text-xs">' +
          '<span class="font-medium">' + escHtml(String(c.action || '')) + '</span>' +
          ' <span class="px-1.5 py-0.5 rounded bg-' + priColor + '-100 text-' + priColor + '-700">' + (c.priority || 'low') + '</span>' +
          '<div class="text-gray-600 mt-1">' + escHtml(String(c.description || '')) + '</div>' +
          (c.recommendation ? '<div class="text-gray-500 mt-0.5">' + escHtml(String(c.recommendation)) + '</div>' : '') +          '</div>';
      });
      dm += (corrections.length > 20 ? '<div class="text-xs text-gray-400 text-center">... 仅显示前20条</div>' : '') +
        '</div></div>';
    }
    dm += '</div></div></div>';
    modal.innerHTML = dm;
  } catch (e) {
    modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4"><div class="p-4 text-center text-red-500">加载失败: ' + String(e) + '</div></div>';
  }
}

// ── 关闭详情弹窗 ──────────────────────────────────────────
export function closeHistoryModal(): void {
  const modal = document.getElementById('history-detail-modal');
  if (modal) modal.remove();
}

// ── 清空历史记录 ──────────────────────────────────────────
export function clearReviewHistory(): void {
  if (!confirm('确定清空所有审查历史记录？此操作不可恢复。')) return;
  localStorage.removeItem('baa_review_results');
  _setReviewResults([]);
  fetch(getApiBase() + '/review/history', { method: 'DELETE' }).catch(() => {});
  renderHistoryList();
  loadDashboard();
}
