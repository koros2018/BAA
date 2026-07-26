// ── 规范库 ──────────────────────────────────────────────
// SPEC_DATA 定义在 baa-core.js 中（先加载，所有文件均可访问）

async function loadSpecs() {
  try {
    const r = await fetch(API_BASE() + '/api/v1/specs', {headers: getHeaders()});
    const data = await r.json();
    if (data.status === 'ok') {
      SPEC_DATA = data.specs;
    }
  } catch(e) {
    console.warn('规范库加载失败', e);
  }
  renderSpecList();
  const specCount = document.getElementById('home-stats')?.querySelectorAll('.stat-card')[1]?.querySelector('.text-2xl');
  if (specCount) specCount.textContent = SPEC_DATA.length;
}

function renderSpecList() {
  const tbody = document.getElementById('spec-list');
  if (!tbody) return;
  const search = (document.getElementById('spec-search')?.value || '').toLowerCase();
  const levelFilter = document.getElementById('spec-filter-level')?.value || 'all';
  const catFilter = document.getElementById('spec-filter-cat')?.value || 'all';
  const stdFilter = document.getElementById('spec-filter-std')?.value || 'all';

  // 统计
  const total = SPEC_DATA.length;
  const l1 = SPEC_DATA.filter(s => (s.level || 'L1') === 'L1').length;
  const l2 = SPEC_DATA.filter(s => (s.level || 'L1') === 'L2').length;
  const l3 = SPEC_DATA.filter(s => (s.level || 'L1') === 'L3').length;
  const tc = document.getElementById('spec-total-count'); if (tc) tc.textContent = total;
  const l1c = document.getElementById('spec-l1-count'); if (l1c) l1c.textContent = l1;
  const l2c = document.getElementById('spec-l2-count'); if (l2c) l2c.textContent = l2;
  const l3c = document.getElementById('spec-l3-count'); if (l3c) l3c.textContent = l3;

  // 过滤
  let filtered = SPEC_DATA;
  if (levelFilter !== 'all') filtered = filtered.filter(s => (s.level || 'L1') === levelFilter);
  if (catFilter !== 'all') filtered = filtered.filter(s => (s.category || '') === catFilter);
  if (stdFilter !== 'all') {
    filtered = filtered.filter(s => {
      const std = s.standard || s.std || '';
      return std.toLowerCase().includes(stdFilter.toLowerCase());
    });
  }
  if (search) {
    filtered = filtered.filter(s =>
      (s.clause_id || '').toLowerCase().includes(search) ||
      (s.title || s.name || '').toLowerCase().includes(search) ||
      (s.text || s.description || '').toLowerCase().includes(search) ||
      (s.standard || s.std || '').toLowerCase().includes(search)
    );
  }
  const fcount = document.getElementById('spec-filter-count');
  if (fcount) fcount.textContent = filtered.length + ' 条' + (filtered.length < total ? ' / ' + total : '');

  tbody.innerHTML = '';
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">无匹配记录</td></tr>';
    return;
  }
  // P73 修复：规范库分类使用规范领域标签（fire_safety/evacuation/...），
  // 原子函数库使用判定方法标签（dim/dist/count/...），两套独立不混用
  const catLabels = {
    fire_safety:'防火安全', evacuation:'疏散', lighting:'照明', structure:'结构', hvac:'暖通'
  };
  const levelColors = {L1:'red',L2:'orange',L3:'green'};
  const stdAbbrev = {'GB 50016':'016','GB 50974':'974','GB 50763':'763','GB 50067':'067','GB 50116':'116','GB 50084':'084'};
  filtered.forEach((s, i) => {
    const title = s.title || s.name || '';
    const desc = s.text || s.description || '';
    const cat = s.category || '--';
    const target = s.target_entities || s.target || [];
    const level = s.level || 'L1';
    const std = s.standard || s.std || '';
    const stdShort = stdAbbrev[std] || (std ? std.slice(3, 6) : '--');
    tbody.innerHTML += '<tr class="border-b border-gray-50">' +
      '<td class="py-2 px-2 text-xs">' + (i + 1) + '</td>' +
      '<td class="py-2 px-2 font-mono text-xs">' + (s.clause_id || '') + '</td>' +
      '<td class="py-2 px-2 text-sm">' + title + '<br/><span class="text-xs text-gray-400">' + desc + '</span></td>' +
      '<td class="py-2 px-2 text-xs">' + (std ? '<span class="bg-blue-100 text-blue-700 px-1 rounded">' + stdShort + '</span>' : '') + '</td>' +
      '<td class="py-2 px-2"><span class="px-2 py-0.5 bg-' + (levelColors[level]||'gray') + '-100 text-' + (levelColors[level]||'gray') + '-700 rounded text-xs">' + level + '</span></td>' +
      '<td class="py-2 px-2 text-xs">' + (catLabels[cat] || cat) + '</td>' +
      '<td class="py-2 px-2 font-mono text-xs max-w-32 truncate">' + (Array.isArray(target) ? target.join(', ') : '') + '</td></tr>';
  });
}

// ── 图纸管理：上传解析 ──────────────────────────────
// 已解析图纸的全局存储
let parsedDrawings = [];
// 文件缓存（用于AI审图时重新上传）
let fileCache = {};

async function uploadDrawing() {
  const file = document.getElementById('file-input').files[0];
  if (!file) { showToast('请先选择图纸文件', 'info'); return; }
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext !== 'dxf') { showToast('仅支持 .dxf 格式。DWG 格式兼容性有限，请先用CAD转存为DXF。', 'warn'); return; }

  const bt = document.getElementById('drawing-bt').value;

  const progress = document.getElementById('upload-progress');
  progress.className = 'card mb-4 text-sm text-gray-500';
  progress.innerHTML = '⏳ 正在解析 ' + file.name + '...';

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
  progress.className = 'card mb-4 text-sm text-gray-500';
  progress.innerHTML = '⏳ 正在批量审查 ' + selected.length + ' 张图纸...';
  
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
  progress.innerHTML = '⏳ 正在解析 ' + file.name + '...';
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
  if (resetPage) historyPage = 0; // 搜索/筛选时重置到第一页
  const el = document.getElementById('history-list');
  if (!el) return;
  loadReviewResults();
  const search = (document.getElementById('history-search')?.value || '').toLowerCase();
  const filter = document.getElementById('history-filter')?.value || 'all';
  let filtered = reviewResults;
  if (filter === 'civil') filtered = filtered.filter(r => r.buildingType === 'civil');
  else if (filter === 'industrial') filtered = filtered.filter(r => r.buildingType === 'industrial');
  else if (filter === 'violations') filtered = filtered.filter(r => (r.violationCount || 0) > 0);
  else if (filter === 'clean') filtered = filtered.filter(r => (r.violationCount || 0) === 0);
  if (search) {
    filtered = filtered.filter(r =>
      r.drawingName.toLowerCase().includes(search) ||
      (r.details || []).some(v => (v.clause_id || '').toLowerCase().includes(search) || (v.clause_title || '').toLowerCase().includes(search))
    );
  }
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
    return '<div class="card p-3 hover:shadow-md transition-shadow">' +
      '<div class="flex items-center justify-between">' +
      '<div class="flex items-center gap-3 cursor-pointer flex-1" onclick="viewHistoryDetail(\'' + r.id + '\')">' +
      '<span class="text-' + color + '-500 text-lg">' + (viols === 0 ? '✅' : '🔴') + '</span>' +
      '<div><div class="font-medium text-sm">' + r.drawingName + '</div>' +
      '<div class="text-xs text-gray-400">' + btLabel + ' · ' + timeStr + '</div></div></div>' +
      '<div class="text-right mr-3">' +
      '<div class="text-sm font-bold text-' + color + '-600">' + viols + ' 项违规</div>' +
      '<div class="text-xs text-gray-400">💡 ' + (r.correctionCount || 0) + ' 条建议</div></div>' +
      '<button onclick="event.stopPropagation();deleteReviewRecord(\'' + r.id + '\')" class="px-2 py-0.5 text-xs text-red-400 hover:text-red-600" title="删除">🗑️</button>' +
      '</div></div>';
  }).join('') + renderPagination(totalPages);
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
    showToast('删除失败: ' + e.message, 'error');
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

// ── 预览缩放/平移 ────────────────────────────────────────
// 支持：鼠标滚轮缩放、拖拽平移、键盘快捷键
function zoomImage(img) {
  if (!img || !img.src || img.style.display === 'none') return;

  // 先移除旧的 viewer（如果有残留）
  var old = document.getElementById('zoom-viewer');
  if (old) old.remove();

  var viewer = document.createElement('div');
  viewer.id = 'zoom-viewer';
  viewer.className = 'fixed inset-0 z-50 bg-black bg-opacity-90 select-none';

  viewer.innerHTML =
    '<div class="absolute inset-0 flex items-center justify-center overflow-hidden" id="zoom-stage">' +
      '<img id="zoom-img" src="' + img.src + '" alt="" draggable="false" ' +
      'style="max-width:95vw;max-height:95vh;transition:transform .12s ease-out;cursor:grab" />' +
    '</div>' +
    '<div class="absolute top-3 left-3 flex gap-1 z-10" id="zoom-toolbar">' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomSet("+1)">＋</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomSet(-1)">－</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomReset()" title="重置">⟲</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomFit()" title="适应窗口">⊡</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomClose()" title="关闭">✕</button>' +
      '<span id="zoom-scale" class="bg-white bg-opacity-80 text-gray-700 px-2 py-1 rounded text-xs self-center ml-1">100%</span>' +
    '</div>' +
    '<div class="absolute bottom-3 right-3 bg-black bg-opacity-50 text-gray-300 text-xs px-2 py-1 rounded" id="zoom-hint">滚轮缩放 · 拖拽平移 · ←↑→↓ · 空格/ESC 关闭</div>';

  document.body.appendChild(viewer);

  var imgEl = document.getElementById('zoom-img');
  var stage = document.getElementById('zoom-stage');
  var scaleEl = document.getElementById('zoom-scale');

  var state = {
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    isDragging: false,
    lastX: 0,
    lastY: 0
  };
  // 暴露到全局，让工具栏按钮（zoomSet/zoomReset/zoomFit）可访问
  window.__zoomState = state;

  var apply = function() {
    var x = state.offsetX + (stage.clientWidth - stage.clientWidth * state.scale) / 2;
    var y = state.offsetY + (stage.clientHeight - stage.clientHeight * state.scale) / 2;
    imgEl.style.transform = 'translate(' + x.toFixed(1) + 'px, ' + y.toFixed(1) + 'px) scale(' + state.scale.toFixed(4) + ')';
    imgEl.style.transformOrigin = '0 0';
    scaleEl.textContent = Math.round(state.scale * 100) + '%';
  };

  // 拖拽平移
  imgEl.addEventListener('mousedown', function(e) {
    state.isDragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    imgEl.style.cursor = 'grabbing';
    e.preventDefault();
  });
  window.addEventListener('mousemove', function(e) {
    if (!state.isDragging) return;
    state.offsetX += e.clientX - state.lastX;
    state.offsetY += e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    apply();
  });
  window.addEventListener('mouseup', function() {
    state.isDragging = false;
    imgEl.style.cursor = 'grab';
  });

  // 滚轮缩放（以鼠标为中心）
  stage.addEventListener('wheel', function(e) {
    e.preventDefault();
    var delta = e.deltaY;
    var factor = delta < 0 ? 1.12 : 1 / 1.12;
    var newScale = Math.max(0.1, Math.min(20, state.scale * factor));

    var rect = stage.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;

    // 缩放前的中心偏移
    var oldCx = state.offsetX + (rect.width - rect.width * state.scale) / 2;
    var oldCy = state.offsetY + (rect.height - rect.height * state.scale) / 2;

    // 鼠标在 img 内的相对位置（缩放前）
    var relX = (mx - oldCx) / state.scale;
    var relY = (my - oldCy) / state.scale;

    // 缩放后保持鼠标在 img 同一点
    var newCx = mx - relX * newScale;
    var newCy = my - relY * newScale;

    state.offsetX = newCx - (rect.width - rect.width * newScale) / 2;
    state.offsetY = newCy - (rect.height - rect.height * newScale) / 2;
    state.scale = newScale;
    apply();
  }, { passive: false });

  // 点击关闭（点击黑色背景区域）
  viewer.addEventListener('click', function(e) {
    if (e.target === viewer || e.target === stage) zoomClose();
  });

  // 键盘快捷键
  window.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { zoomClose(); return; }
    if (e.key === ' ') { e.preventDefault(); zoomClose(); return; }
    if (e.key === '+' || e.key === '=') { zoomSet(1); return; }
    if (e.key === '-') { zoomSet(-1); return; }
    if (e.key === 'ArrowLeft') { state.offsetX += 30; apply(); e.preventDefault(); }
    if (e.key === 'ArrowRight') { state.offsetX -= 30; apply(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { state.offsetY += 30; apply(); e.preventDefault(); }
    if (e.key === 'ArrowDown') { state.offsetY -= 30; apply(); e.preventDefault(); }
  });

  apply();
}

function zoomSet(dir) {
  var state = window.__zoomState;
  if (!state) return;
  var imgEl = document.getElementById('zoom-img');
  var stage = document.getElementById('zoom-stage');
  if (!imgEl || !stage) return;
  var factor = dir > 0 ? 1.25 : 0.8;
  var newScale = Math.max(0.1, Math.min(20, state.scale * factor));
  var rect = stage.getBoundingClientRect();
  var oldCx = state.offsetX + (rect.width - rect.width * state.scale) / 2;
  var oldCy = state.offsetY + (rect.height - rect.height * state.scale) / 2;
  state.offsetX = oldCx - (rect.width - rect.width * newScale) / 2;
  state.offsetY = oldCy - (rect.height - rect.height * newScale) / 2;
  state.scale = newScale;
  var x = state.offsetX + (rect.width - rect.width * state.scale) / 2;
  var y = state.offsetY + (rect.height - rect.height * state.scale) / 2;
  imgEl.style.transform = 'translate(' + x.toFixed(1) + 'px, ' + y.toFixed(1) + 'px) scale(' + state.scale.toFixed(4) + ')';
  imgEl.style.transformOrigin = '0 0';
  var s = document.getElementById('zoom-scale');
  if (s) s.textContent = Math.round(state.scale * 100) + '%';
}

function zoomReset() {
  var state = window.__zoomState;
  var imgEl = document.getElementById('zoom-img');
  if (!state || !imgEl) return;
  state.scale = 1;
  state.offsetX = 0;
  state.offsetY = 0;
  imgEl.style.transform = 'none';
  var s = document.getElementById('zoom-scale');
  if (s) s.textContent = '100%';
}

function zoomFit() {
  zoomReset();
}

function zoomClose() {
  window.__zoomState = null;
  var el = document.getElementById('zoom-viewer');
  if (el) el.remove();
}

// P43 collab frontend
var collabToken = localStorage.getItem('baa_collab_token') || '';
var collabUser = {};
try { collabUser = JSON.parse(localStorage.getItem('baa_collab_user') || '{}'); } catch(e) {}

function collabApi(path, options) {
  options = options || {};
  var url = API_BASE() + path;
  var headers = {'Content-Type': 'application/json'};
  if (collabToken) headers['Authorization'] = 'Bearer ' + collabToken;
  if (options.headers) { for (var k in options.headers) headers[k] = options.headers[k]; }
  options.headers = headers;
  return fetch(url, options).then(function(r) { return r.json(); });
}

function closeCollabModal() { var el = document.getElementById('collab-modal-overlay'); if (el) el.style.display = 'none'; }
function setModalBody(html) { var el = document.getElementById('collab-modal-body'); if (el) { el.innerHTML = html; document.getElementById('collab-modal-overlay').style.display = 'flex'; } }

function showCollabLogin() {
  document.getElementById('collab-login-form').style.display = 'block';
  document.getElementById('collab-register-form').style.display = 'none';
  var btns = document.querySelectorAll('#collab-auth-tabs button');
  btns[0].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white';
  btns[1].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600';
}

function showCollabRegister() {
  document.getElementById('collab-login-form').style.display = 'none';
  document.getElementById('collab-register-form').style.display = 'block';
  var btns = document.querySelectorAll('#collab-auth-tabs button');
  btns[0].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600';
  btns[1].className = 'flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white';
}

function collabLogin() {
  var u = document.getElementById('collab-username').value.trim();
  var p = document.getElementById('collab-password').value;
  if (!u || !p) { document.getElementById('collab-auth-msg').textContent = '请输入用户名和密码'; return; }
  collabApi('/collab/auth/login', { method: 'POST', body: JSON.stringify({username: u, password: p}) }).then(function(d) {
    if (d.status === 'success') {
      collabToken = d.token; collabUser = d.user;
      localStorage.setItem('baa_collab_token', collabToken);
      localStorage.setItem('baa_collab_user', JSON.stringify(collabUser));
      document.getElementById('collab-auth-msg').textContent = '';
      collabEnterMain();
    } else { document.getElementById('collab-auth-msg').textContent = d.detail || '登录失败'; }
  });
}

function collabRegister() {
  var u = document.getElementById('collab-reg-username').value.trim();
  var p = document.getElementById('collab-reg-password').value;
  var e = document.getElementById('collab-reg-email').value.trim();
  var dn = document.getElementById('collab-reg-name').value.trim();
  if (!u || !p) { document.getElementById('collab-reg-msg').textContent = '用户名和密码不能为空'; return; }
  if (p.length < 6) { document.getElementById('collab-reg-msg').textContent = '密码至少6位'; return; }
  var body = {username: u, password: p};
  if (e) { body.email = e; body.display_name = dn; }
  collabApi('/collab/auth/register', { method: 'POST', body: JSON.stringify(body) }).then(function(d) {
    if (d.status === 'success') {
      document.getElementById('collab-reg-msg').textContent = '注册成功，请登录';
      document.getElementById('collab-reg-msg').style.color = '#059669';
      showCollabLogin();
      document.getElementById('collab-username').value = u;
    } else { document.getElementById('collab-reg-msg').textContent = d.detail || '注册失败'; }
  });
}

function collabLogout() {
  collabToken = ''; collabUser = {};
  localStorage.removeItem('baa_collab_token');
  localStorage.removeItem('baa_collab_user');
  document.getElementById('collab-main-section').style.display = 'none';
  document.getElementById('collab-login-section').style.display = 'block';
}

function collabEnterMain() {
  document.getElementById('collab-login-section').style.display = 'none';
  document.getElementById('collab-main-section').style.display = 'block';
  document.getElementById('collab-user-display').textContent = '👤 ' + (collabUser.display_name || collabUser.username);
  collabRefresh();
}

function collabRefresh() { loadCollabStats(); loadCollabTeams(); }

function loadCollabStats() {
  collabApi('/collab/stats').then(function(d) {
    if (d.status === 'success') {
      document.getElementById('cs-users').textContent = d.stats.users;
      document.getElementById('cs-teams').textContent = d.stats.teams;
      document.getElementById('cs-projects').textContent = d.stats.active_projects;
      document.getElementById('cs-sessions').textContent = d.stats.review_sessions;
    }
  });
}

function loadCollabTeams() {
  collabApi('/collab/teams').then(function(d) {
    var el = document.getElementById('collab-teams');
    if (d.status !== 'success') { el.innerHTML = '\u52a0\u8f7d\u5931\u8d25'; return; }
    if (!d.teams.length) { el.innerHTML = '\u6682\u65e0\u56e2\u961f'; return; }
    var h = '<table class="collab-table"><tr><th>\u540d\u79f0</th><th>\u6210\u5458</th><th>\u89d2\u8272</th><th>\u65f6\u95f4</th><th>\u64cd\u4f5c</th></tr>';
    for (var i = 0; i < d.teams.length; i++) {
      var t = d.teams[i];
      h += '<tr><td><strong>' + t.name + '</strong></td><td>' + t.member_count + '</td><td><span class="collab-badge collab-badge-' + t.my_role + '">' + t.my_role + '</span></td><td>' + new Date(t.created_at*1000).toLocaleDateString() + '</td><td><button class="text-blue-600 text-xs underline" onclick="showTeamDetail(&#39;' + t.id + '&#39;)">📋</button></td></tr>';
    }
    h += '</table>';
    el.innerHTML = h;
  });
}

function showCreateTeamModal() {
  setModalBody('<h3 class="text-lg font-bold mb-4">\u65b0\u5efa\u56e2\u961f</h3><input id="modal-team-name" class="input w-full mb-2" placeholder="\u56e2\u961f\u540d\u79f0" /><textarea id="modal-team-desc" class="input w-full mb-3" placeholder="\u63cf\u8ff0" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u53d6\u6d88</button><button class="modal-btn modal-btn-primary" onclick="createTeam()">\u521b\u5efa</button></div>');
}

function createTeam() {
  var name = document.getElementById('modal-team-name').value.trim();
  if (!name) return;
  var desc = document.getElementById('modal-team-desc').value.trim();
  collabApi('/collab/teams', { method: 'POST', body: JSON.stringify({name: name, description: desc}) }).then(function(d) {
    if (d.status === 'success') { closeCollabModal(); collabRefresh(); } else { showToast(d.detail || '\u521b\u5efa\u5931\u8d25', 'info'); }
  });
}

function showTeamDetail(teamId) {
  Promise.all([collabApi('/collab/teams/' + teamId), collabApi('/collab/teams/' + teamId + '/projects')]).then(function(r) {
    if (r[0].status !== 'success') return;
    var team = r[0].team, projects = r[1].projects || [];
    var mh = '<table class="collab-table"><tr><th>\u7528\u6237</th><th>\u89d2\u8272</th><th>\u65f6\u95f4</th></tr>';
    for (var i = 0; i < team.members.length; i++) {
      var m = team.members[i];
      mh += '<tr><td>' + (m.display_name || m.username) + '</td><td><span class="collab-badge collab-badge-' + m.role + '">' + m.role + '</span></td><td>' + new Date(m.joined_at*1000).toLocaleDateString() + '</td></tr>';
    }
    mh += '</table>';
    var ph = '';
    if (projects.length === 0) { ph = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u9879\u76ee</p>'; } else {
      ph = '<table class="collab-table"><tr><th>\u9879\u76ee</th><th>\u56fe\u7eb8</th><th>\u5ba1\u67e5</th><th>\u72b6\u6001</th><th>\u64cd\u4f5c</th></tr>';
      for (var i = 0; i < projects.length; i++) {
        var p = projects[i];
        ph += '<tr><td><strong>' + p.name + '</strong></td><td>' + p.file_count + '</td><td>' + p.review_count + '</td><td>' + p.status + '</td><td><button class="text-blue-600 text-xs underline" onclick="showProjectDetail(&#39;' + p.id + '&#39;)">📝</button></td></tr>';
      }
      ph += '</table>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">\u56e2\u961f: ' + team.name + '</h3><div class="mb-4"><h4 class="font-medium mb-2">\u6210\u5458 (' + team.members.length + ')</h4>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">\u9879\u76ee</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateProjectModal(&#39;' + teamId + '&#39;)">+ \u65b0\u5efa\u9879\u76ee</button></div>' + ph + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u5173\u95ed</button></div>');
  });
}

function showCreateProjectModal(teamId) {
  setModalBody('<h3 class="text-lg font-bold mb-4">\u65b0\u5efa\u9879\u76ee</h3><input id="modal-proj-name" class="input w-full mb-2" placeholder="\u9879\u76ee\u540d\u79f0" /><textarea id="modal-proj-desc" class="input w-full mb-2" placeholder="\u63cf\u8ff0" rows="2"></textarea><input id="modal-proj-type" class="input w-full mb-2" placeholder="\u5efa\u7b51\u7c7b\u578b" /><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showTeamDetail(&#39;' + teamId + '&#39;)">\u8fd4\u56de</button><button class="modal-btn modal-btn-primary" onclick="createProject(&#39;' + teamId + '&#39;)">\u521b\u5efa</button></div>');
}

function createProject(teamId) {
  var name = document.getElementById('modal-proj-name').value.trim();
  if (!name) return;
  var desc = document.getElementById('modal-proj-desc').value.trim();
  var btype = document.getElementById('modal-proj-type').value.trim();
  collabApi('/collab/projects', { method: 'POST', body: JSON.stringify({name: name, team_id: teamId, description: desc, building_type: btype}) }).then(function(d) {
    if (d.status === 'success') { showTeamDetail(teamId); } else { showToast(d.detail || '\u521b\u5efa\u5931\u8d25', 'info'); }
  });
}

function showProjectDetail(projectId) {
  Promise.all([collabApi('/collab/projects/' + projectId), collabApi('/collab/projects/' + projectId + '/review-sessions')]).then(function(r) {
    if (r[0].status !== 'success') return;
    var proj = r[0].project, sessions = r[1].review_sessions || [];
    var mh = '<table class="collab-table"><tr><th>\u7528\u6237</th><th>\u6743\u9650</th></tr>';
    for (var i = 0; i < proj.members.length; i++) {
      var m = proj.members[i];
      mh += '<tr><td>' + (m.display_name || m.username) + '</td><td><span class="collab-badge">' + m.permission + '</span></td></tr>';
    }
    mh += '</table>';
    var sh = '';
    if (sessions.length === 0) { sh = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u5ba1\u67e5\u4f1a\u8bdd</p>'; } else {
      sh = '<table class="collab-table"><tr><th>\u540d\u79f0</th><th>\u72b6\u6001</th><th>\u521b\u5efa\u4eba</th><th>\u65f6\u95f4</th><th>\u64cd\u4f5c</th></tr>';
      for (var i = 0; i < sessions.length; i++) {
        var s = sessions[i];
        sh += '<tr><td>' + s.name + '</td><td><span class="collab-badge collab-badge-' + s.status + '">' + s.status + '</span></td><td>' + (s.creator_name || '') + '</td><td>' + new Date(s.created_at*1000).toLocaleString() + '</td><td><button class="text-blue-600 text-xs underline" onclick="showReviewSessionDetail(&#39;' + s.id + '&#39;)">📝</button></td></tr>';
      }
      sh += '</table>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">\u9879\u76ee: ' + proj.name + '</h3><div class="mb-4"><h4 class="font-medium mb-2">\u6210\u5458</h4>' + mh + '</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">\u5ba1\u67e5\u4f1a\u8bdd</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateReviewSessionModal(&#39;' + projectId + '&#39;)">+ \u65b0\u5efa\u5ba1\u67e5</button></div>' + sh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u5173\u95ed</button></div>');
  });
}

function showCreateReviewSessionModal(projectId) {
  setModalBody('<h3 class="text-lg font-bold mb-4">\u65b0\u5efa\u5ba1\u67e5\u4f1a\u8bdd</h3><input id="modal-rs-name" class="input w-full mb-2" placeholder="\u540d\u79f0" /><textarea id="modal-rs-desc" class="input w-full mb-2" placeholder="\u63cf\u8ff0" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showProjectDetail(&#39;' + projectId + '&#39;)">\u8fd4\u56de</button><button class="modal-btn modal-btn-primary" onclick="createReviewSession(&#39;' + projectId + '&#39;)">\u521b\u5efa</button></div>');
}

function createReviewSession(projectId) {
  var name = document.getElementById('modal-rs-name').value.trim();
  if (!name) return;
  var desc = document.getElementById('modal-rs-desc').value.trim();
  collabApi('/collab/review-sessions', { method: 'POST', body: JSON.stringify({project_id: projectId, name: name, description: desc}) }).then(function(d) {
    if (d.status === 'success') { showProjectDetail(projectId); } else { showToast(d.detail || '\u521b\u5efa\u5931\u8d25', 'info'); }
  });
}

function showReviewSessionDetail(sessionId) {
  Promise.all([
    collabApi('/collab/review-sessions/' + sessionId),
    collabApi('/collab/review-sessions/' + sessionId + '/comments'),
    collabApi('/collab/review-sessions/' + sessionId + '/approval-flow')
  ]).then(function(r) {
    if (r[0].status !== 'success') return;
    var rs = r[0].review_session, comments = r[1].comments || [], flow = r[2].approval_flow;
    var statusBadge = '<span class="collab-badge collab-badge-' + rs.status + '">' + rs.status + '</span>';
    var ch = '';
    if (comments.length === 0) { ch = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u8bc4\u8bba</p>'; } else {
      for (var i = 0; i < comments.length; i++) {
        var c = comments[i];
        var icon = c.comment_type === 'issue' ? '\u26a0\ufe0f' : c.comment_type === 'suggestion' ? '\U0001f4a1' : c.comment_type === 'question' ? '\u2753' : '\u2705';
        ch += '<div class="comment-box comment-' + c.comment_type + '"><div class="flex justify-between items-start"><span class="font-medium text-sm">' + icon + ' ' + (c.author_name || '') + '</span><span class="text-xs text-gray-400">' + new Date(c.created_at*1000).toLocaleString() + '</span></div><p class="text-sm mt-1">' + c.content + '</p>';
        if (c.clause_ref) { ch += '<div class="text-xs text-gray-400 mt-1">\u2022 \u6761\u6b3e: ' + c.clause_ref + '</div>'; }
        if (c.entity_ref) { ch += '<div class="text-xs text-gray-400">\u2022 \u5b9e\u4f53: ' + c.entity_ref + '</div>'; }
        ch += '</div>';
      }
    }
    var fh = '';
    if (flow) {
      fh = '<table class="collab-table"><tr><th>\u5e8f\u53f7</th><th>\u5ba1\u6279\u4eba</th><th>\u72b6\u6001</th><th>\u610f\u89c1</th><th>\u65f6\u95f4</th></tr>';
      for (var i = 0; i < flow.steps.length; i++) {
        var st = flow.steps[i];
        var sb = '<span class="collab-badge collab-badge-' + st.status + '">' + st.status + '</span>';
        fh += '<tr><td>' + st.order + '</td><td>' + (st.reviewer_name || '') + '</td><td>' + sb + '</td><td>' + (st.comment || '') + '</td><td>' + (st.acted_at ? new Date(st.acted_at*1000).toLocaleString() : '') + '</td></tr>';
      }
      fh += '</table>';
    } else {
      fh = '<p class="text-sm text-gray-400 py-2">\u6682\u65e0\u5ba1\u6279\u6d41\u7a0b</p>';
    }
    setModalBody('<h3 class="text-lg font-bold mb-4">\u5ba1\u67e5\u4f1a\u8bdd: ' + rs.name + ' ' + statusBadge + '</h3><div class="mb-4"><h4 class="font-medium mb-2">\u8bc4\u8bba</h4>' + ch + '</div><div><h4 class="font-medium mb-2">\u5ba1\u6279\u6d41\u7a0b</h4>' + fh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">\u5173\u95ed</button></div>');
  });
}

// Auto-login if token exists
if (collabToken) {
  setTimeout(function() {
    var page = document.getElementById('page-collab');
    if (page && page.classList.contains('active')) {
      collabEnterMain();
    }
  }, 500);
}
