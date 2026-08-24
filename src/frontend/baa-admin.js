// P122 XSS 防护工具函数
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ── 规范库 ──────────────────────────────────────────────
// SPEC_DATA 定义在 baa-core.js 中（先加载，所有文件均可访问）
// ── 图纸管理：上传解析 ──────────────────────────────
// 已解析图纸的全局存储（挂载到 window，供 baa-core.js 访问）
let parsedDrawings = [];
window.parsedDrawings = parsedDrawings;
// 文件缓存（用于AI审图时重新上传）
let fileCache = {};

async function uploadDrawing() {
  const file = document.getElementById('file-input').files[0];
  if (!file) { showToast('请先选择图纸文件', 'info'); return; }
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext !== 'dxf') { showToast('仅支持 .dxf 格式。DWG 格式兼容性有限，请先用CAD转存为DXF。', 'warn'); return; }

  const bt = document.getElementById('drawing-bt').value;

  const progress = document.getElementById('upload-progress');
  progress.className = 'card mb-4';
  progress.innerHTML = '<div class="review-progress"><div class="review-progress-text"><span>解析</span><span>0%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';

  try {
    // Step 1: 调 /deconstruct 做纯解析（获取结构化JSON）
    const useYolo = document.getElementById('use-yolo-checkbox')?.checked || false;
    const yoloDevice = document.getElementById('yolo-device-select')?.value || 'cpu';
    const result = await apiPostFile('/deconstruct', file, {building_type: bt, use_yolo: useYolo, yolo_device: yoloDevice});
    progress.className = 'hidden';

    // 缓存文件（用于后续AI审图重新上传）
    const fileId = result.file_id || 'drawing_' + Date.now();
    fileCache[fileId] = file;

    // 存储解析结果
    const entry = {
      id: fileId,
      filename: file.name,
      building_type: bt,
      parsedAt: new Date().toISOString(),
      elements: result.elements || [],
      entities: result.entities || [],
      findings_count: result.findings || 0,
      total_checks: result.total_checks || 0,
      file_id: fileId,
      raw: result,
      use_yolo: useYolo,
    };
    parsedDrawings.unshift(entry);
    saveParsedDrawings();

    // 更新图纸列表
    renderDrawingList();

    // 显示解析预览
    const preview = document.getElementById('drawing-preview');
    preview.className = 'card';
    document.getElementById('parse-result-json').textContent =
      JSON.stringify(result, null, 2);

    // 渲染图纸
    const renderImg = document.getElementById('drawing-render-img');
    const placeholder = document.getElementById('drawing-render-placeholder');
    renderImg.className = 'w-full';
    renderImg.src = API_BASE() + '/render/' + fileId;
    placeholder.className = 'hidden';

    // 刷新AI审图的下拉
    refreshReviewDrawingSelect();
    loadDashboard();
  } catch (e) {
    progress.innerHTML = '❌ 解析失败: ' + e.message;
    progress.className = 'card mb-4 text-sm text-red-500';
  }
}

function saveParsedDrawings() {
  try {
    localStorage.setItem('baa_parsed_drawings', JSON.stringify(parsedDrawings));
  } catch (e) { /* ignore quota */ }
}

function loadParsedDrawings() {
  try {
    const stored = localStorage.getItem('baa_parsed_drawings');
    if (stored) parsedDrawings = JSON.parse(stored);
  } catch (e) { parsedDrawings = []; }
}

function renderDrawingList() {
  const tbody = document.getElementById('drawing-list');
  if (!tbody) return;
  const countEl = document.getElementById('drawing-count');
  if (countEl) countEl.textContent = parsedDrawings.length;
  
  if (parsedDrawings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">暂无记录，请上传图纸</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  parsedDrawings.forEach((d, i) => {
    const row = tbody.insertRow(-1);
    row.className = 'border-b border-gray-50 text-sm';
    const yoloBadge = d.use_yolo ? '<span class="ml-1 px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">YOLO</span>' : '';
    const checked = d._selected ? 'checked' : '';
    row.innerHTML =
      '<td class="py-2 px-2"><input type="checkbox" class="drawing-select" data-idx="' + i + '" ' + checked + ' onchange="toggleDrawingSelect(' + i + ',this.checked)" /></td>' +
      '<td class="py-2 px-2 truncate max-w-32">' + d.filename + yoloBadge + '</td>' +
      '<td class="py-2 px-2 text-xs">' + (d.building_type === 'civil' ? '民用' : '工业') + '</td>' +
      '<td class="py-2 px-2">' + (d.elements?.length || 0) + '</td>' +
      '<td class="py-2 px-2 text-xs max-w-40 truncate">' + (d.elements ? d.elements.map(e => e.type).join(', ') : '') + '</td>' +
      '<td class="py-2 px-2 text-xs">' + new Date(d.parsedAt).toLocaleTimeString() + '</td>' +
      '<td class="py-2 px-2">' +
      '<button onclick="sendToReview(' + i + ')" class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200 mr-1">送审</button>' +
      (d.file_id ? '<button onclick="downloadReviewPdf(\'' + d.file_id + '\')" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200 mr-1" title="下载PDF报告">📄</button>' : '') +
      '<button onclick="deleteDrawing(' + i + ')" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200">🗑️</button></td>';
  });
  updateBatchButton();
}

function toggleDrawingSelect(idx, checked) {
  if (parsedDrawings[idx]) parsedDrawings[idx]._selected = checked;
  updateBatchButton();
}

function selectAllDrawings() {
  parsedDrawings.forEach(d => d._selected = true);
  renderDrawingList();
}

function deselectAllDrawings() {
  parsedDrawings.forEach(d => d._selected = false);
  renderDrawingList();
}

function updateBatchButton() {
  const count = parsedDrawings.filter(d => d._selected).length;
  const btn = document.getElementById('batch-review-btn');
  const badge = document.getElementById('batch-count');
  if (btn) {
    btn.className = count > 0
      ? 'px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700'
      : 'px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 hidden';
  }
  if (badge) badge.textContent = count;
}

async function batchReview() {
  const selected = parsedDrawings.filter(d => d._selected);
  if (selected.length === 0) { showToast('请先勾选要送审的图纸', 'info'); return; }
  
  const progress = document.getElementById('upload-progress');
  progress.className = 'card mb-4';
  progress.innerHTML = '<div class="review-progress"><div class="review-progress-text"><span>批量审查</span><span>0%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
  
  let totalViolations = 0;
  let results = [];
  
  for (const d of selected) {
    try {
      const r = await apiPost('/review-from-data', {
        entities: d.elements || [],
        building_type: d.building_type,
      });
      if (r.status === 'completed' || r.status === 'success') {
        const v = r.details?.length || 0;
        totalViolations += v;
        results.push({name: d.filename, violations: v, details: r.details});
      }
    } catch (e) {
      results.push({name: d.filename, violations: -1, error: e.message});
    }
  }
  
  progress.className = 'card mb-4 text-sm';
  let html = '✅ 批量审查完成 (' + selected.length + ' 张, 共 ' + totalViolations + ' 项违规)<br/><br/>';
  results.forEach(r => {
    if (r.error) {
      html += '<div class="text-red-500 text-xs">❌ ' + r.name + ': ' + r.error + '</div>';
    } else {
      const c = r.violations > 0 ? 'text-red-500' : 'text-green-600';
      html += '<div class="text-xs mb-1">' + r.name + ': <span class="' + c + '">' + r.violations + ' 项违规</span></div>';
    }
  });
  progress.innerHTML = html;
  
  // 切换到审图页面，加载第一张
  if (results.length > 0) {
    switchPage('review');
  }
}

async function uploadAndReview() {
  // 先执行上传+解析
  const file = document.getElementById('file-input').files[0];
  if (!file) { showToast('请先选择图纸文件', 'info'); return; }
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext !== 'dxf') { showToast('仅支持 .dxf 和 .dwg 格式', 'warn'); return; }
  const bt = document.getElementById('drawing-bt').value;
  const progress = document.getElementById('upload-progress');
  progress.className = 'card mb-4 text-sm text-gray-500';
  progress.innerHTML = '<div class="review-progress"><div class="review-progress-text"><span>解析</span><span>0%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
  try {
    const useYolo = document.getElementById('use-yolo-checkbox')?.checked || false;
    const yoloDevice = document.getElementById('yolo-device-select')?.value || 'cpu';
    const result = await apiPostFile('/deconstruct', file, {building_type: bt, use_yolo: useYolo, yolo_device: yoloDevice});
    progress.className = 'hidden';
    const fileId = result.file_id || 'drawing_' + Date.now();
    fileCache[fileId] = file;
    const entry = {
      id: fileId, filename: file.name, building_type: bt,
      parsedAt: new Date().toISOString(),
      elements: result.elements || [], entities: result.entities || [],
      findings_count: result.findings || 0, total_checks: result.total_checks || 0,
      use_yolo: useYolo,
      file_id: fileId, raw: result,
    };
    parsedDrawings.unshift(entry);
    saveParsedDrawings();
    renderDrawingList();
    refreshReviewDrawingSelect();
    loadDashboard();
    // 停留在图纸管理页面，显示解析预览
    const preview = document.getElementById('drawing-preview');
    if (preview) {
      preview.className = 'card';
      document.getElementById('parse-result-json').textContent =
        JSON.stringify(result, null, 2);
    }
  } catch (e) {
    progress.innerHTML = '❌ 解析失败: ' + e.message;
    progress.className = 'card mb-4 text-sm text-red-500';
  }
}

function deleteDrawing(idx) {
  const d = parsedDrawings[idx];
  if (!d) return;
  if (!confirm('确定删除图纸「' + d.filename + '」的解析记录？')) return;
  parsedDrawings.splice(idx, 1);
  saveParsedDrawings();
  renderDrawingList();
}

function sendToReview(idx) {
  const d = parsedDrawings[idx];
  if (!d) return;
  // 切换到AI审图页面并选中此图纸
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
  document.querySelector('[data-page="review"]').classList.add('active');
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById('page-review').classList.add('active');

  const select = document.getElementById('review-drawing-select');
  // 找到对应option并选中
  for (let i = 0; i < select.options.length; i++) {
    if (select.options[i].value === d.id) {
      select.selectedIndex = i;
      break;
    }
  }
  onReviewDrawingSelect();
}

function refreshReviewDrawingSelect() {
  const select = document.getElementById('review-drawing-select');
  if (!select) return;
  select.innerHTML = '<option value="">— 选择已解析图纸 —</option>';
  parsedDrawings.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.id;
    opt.textContent = d.filename + ' (' + (d.building_type === 'civil' ? '民用' : '工业') + ')';   
    select.appendChild(opt);
  });
}

function onReviewDrawingSelect() {
  const select = document.getElementById('review-drawing-select');
  const btn = document.getElementById('review-start-btn');
  const info = document.getElementById('review-drawing-info');
  const id = select.value;
  if (!id) {
    btn.disabled = true;
    info.textContent = '';
    return;
  }
  const d = parsedDrawings.find(p => p.id === id);
  if (!d) {
    btn.disabled = true;
    info.textContent = '';
    return;
  }
  btn.disabled = false;
  info.textContent = '实体: ' + (d.elements?.length || 0) + '个 · 已解析: ' + new Date(d.parsedAt).toLocaleString();
}

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

