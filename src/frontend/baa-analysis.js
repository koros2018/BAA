// P122 XSS 防护工具函数
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ── 结果分析 ──────────────────────────────────────────────
function renderAnalysisTable() {
  const tbody = document.getElementById('analysis-table');
  if (!tbody) return;
  if (reviewResults.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-gray-300">暂无数据，请先审查图纸</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  // 优先显示有违规的记录，再显示无违规的，确保违规可见
  const sorted = [...reviewResults].sort((a, b) => (b.violationCount || 0) - (a.violationCount || 0));
  sorted.slice(0, 30).forEach((h, i) => {
    const viols = h.violationCount || 0;
    const checks = h.entityCount || 1;
    const passRate = checks > 0 ? Math.round((1 - viols / checks) * 100) : 0;
    const btLabel = h.buildingType === 'civil' ? '民用' : h.buildingType === 'industrial' ? '工业' : '--';
    const safeDrawingName = escHtml(h.drawingName || '');
    tbody.innerHTML += '<tr class="border-b border-gray-50 text-sm">' +
      '<td class="py-2 px-2">' + (i + 1) + '</td>' +
      '<td class="py-2 px-2 truncate max-w-32" title="' + safeDrawingName + '">' + safeDrawingName + '</td>' +
      '<td class="py-2 px-2 text-xs">' + btLabel + '</td>' +
      '<td class="py-2 px-2 text-red-600">' + viols + '</td>' +
      '<td class="py-2 px-2"><div class="flex items-center gap-2"><div class="w-20 bg-gray-200 rounded-full h-2"><div class="bg-' + (passRate > 80 ? 'green' : passRate > 50 ? 'yellow' : 'red') + '-500 h-2 rounded-full" style="width:' + Math.max(0, passRate) + '%"></div></div><span class="text-xs">' + Math.max(0, passRate) + '%</span></div></td>' +
      '<td class="py-2 px-2 text-xs">' + (h.reviewedAt ? new Date(h.reviewedAt).toLocaleString('zh-CN') : '--') + '</td></tr>';
  });
}

// ── EVAC/走廊宽度分类统计（结果分析页）──
function renderCategoryAnalysis() {
  const el = document.getElementById('category-analysis');
  if (!el) return;
  loadReviewResults();
  
  // 按图纸统计各类违规
  const catStats = {};  // {drawingName: {evac: N, corridor: N, dead_end: N, other: N}}
  reviewResults.forEach(h => {
    const name = h.drawingName;
    if (!catStats[name]) catStats[name] = {evac:0, corridor:0, dead_end:0, other:0};
    (h.details || []).forEach(v => {
      const fid = v.func_id || '';
      if (fid.startsWith('EVAC-')) catStats[name].evac++;
      else if (fid === 'DIM-004') catStats[name].corridor++;
      else if (v.explanation && v.explanation.toLowerCase().includes('死胡同')) catStats[name].dead_end++;
      else catStats[name].other++;
    });
  });
  
  const names = Object.keys(catStats);
  if (names.length === 0) {
    el.innerHTML = '<div class="text-gray-400 text-xs">审查图纸后自动统计</div>';
    return;
  }
  
  const totalEvac = names.reduce((s, n) => s + catStats[n].evac, 0);
  const totalCorridor = names.reduce((s, n) => s + catStats[n].corridor, 0);
  const totalDeadEnd = names.reduce((s, n) => s + catStats[n].dead_end, 0);
  
  let html = '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
    '<th class="pb-1 pr-2">图纸</th><th class="pb-1 pr-2">🚪疏散路径</th><th class="pb-1 pr-2">📏走廊宽度</th><th class="pb-1 pr-2">🔒死胡同</th><th class="pb-1">其他</th></tr></thead><tbody>';
  
  names.forEach(name => {
    const s = catStats[name];
    html += '<tr class="border-b border-gray-50">' +
      '<td class="py-1 pr-2 truncate max-w-28" title="' + name + '">' + name + '</td>' +
      '<td class="py-1 pr-2"><span class="' + (s.evac > 0 ? 'text-red-600 font-medium' : 'text-green-500') + '">' + s.evac + '</span></td>' +
      '<td class="py-1 pr-2"><span class="' + (s.corridor > 0 ? 'text-orange-600 font-medium' : 'text-green-500') + '">' + s.corridor + '</span></td>' +
      '<td class="py-1 pr-2"><span class="' + (s.dead_end > 0 ? 'text-yellow-600 font-medium' : 'text-green-500') + '">' + s.dead_end + '</span></td>' +
      '<td class="py-1">' + s.other + '</td></tr>';
  });
  
  html += '<tr class="font-medium bg-gray-50"><td class="py-1 pr-2">合计</td>' +
    '<td class="py-1 pr-2">' + totalEvac + '</td>' +
    '<td class="py-1 pr-2">' + totalCorridor + '</td>' +
    '<td class="py-1 pr-2">' + totalDeadEnd + '</td>' +
    '<td class="py-1">' + names.reduce((s, n) => s + catStats[n].other, 0) + '</td></tr>';
  
  html += '</tbody></table>';
  el.innerHTML = html;
}

function loadAnalysis() {
  renderTrendBars();
  renderViolationDistBars();
  renderAnalysisTable();
  renderCategoryAnalysis();
}

function renderTrendBars() {
  const el = document.getElementById('trend-bars');
  if (!el) return;
  loadReviewResults();
  if (reviewResults.length === 0) { el.innerHTML = '<div class="text-gray-400">审查图纸后自动统计</div>'; return; }

  const recent = reviewResults.slice(0, 20).reverse();
  const maxV = Math.max(...recent.map(r => r.details?.length || 0), 1);
  const totalV = recent.reduce((s, r) => s + (r.details?.length || 0), 0);
  const avgV = Math.round(totalV / recent.length * 10) / 10;
  const cleanCount = recent.filter(r => (r.details?.length || 0) === 0).length;
  const maxDate = recent.length > 0 ? recent[recent.length - 1] : null;
  const minDate = recent.length > 0 ? recent[0] : null;
  const firstDate = minDate ? new Date(minDate.reviewedAt || minDate.createdAt || Date.now()).toLocaleDateString() : '--';
  const lastDate = maxDate ? new Date(maxDate.reviewedAt || maxDate.createdAt || Date.now()).toLocaleDateString() : '--';

  // 按类别统计违规分布（最近审查）
  const recentViolations = recent.reduce((acc, r) => {
    (r.details || []).forEach(v => {
      const cat = (v.func_id || '').split('-')[0] || 'other';
      if (!acc[cat]) acc[cat] = { count: 0, critical: 0, major: 0, minor: 0 };
      acc[cat].count++;
      const sev = v.severity || 'major';
      if (acc[cat][sev]) acc[cat][sev]++;
      else acc[cat].major++;
    });
    return acc;
  }, {});

  // 按日期分组（如果审查集中在几天）
  const dailyStats = {};
  recent.forEach(r => {
    const d = new Date(r.reviewedAt || r.createdAt || Date.now());
    const key = d.toLocaleDateString();
    if (!dailyStats[key]) dailyStats[key] = { count: 0, violations: 0, clean: 0 };
    dailyStats[key].count++;
    const v = r.details?.length || 0;
    dailyStats[key].violations += v;
    if (v === 0) dailyStats[key].clean++;
  });

  // 趋势图表（交互式柱状图 + 数据标签）
  let chartHtml = '';

  // 统计卡片
  chartHtml += '<div class="grid grid-cols-4 gap-1 mb-2 text-xs">' +
    '<div class="bg-blue-50 rounded p-1 text-center"><div class="text-blue-600 font-bold">' + recent.length + '</div><div class="text-gray-500 text-[10px]">审查次数</div></div>' +
    '<div class="bg-red-50 rounded p-1 text-center"><div class="text-red-600 font-bold">' + totalV + '</div><div class="text-gray-500 text-[10px]">违规总数</div></div>' +
    '<div class="bg-yellow-50 rounded p-1 text-center"><div class="text-yellow-600 font-bold">' + avgV + '</div><div class="text-gray-500 text-[10px]">平均违规/次</div></div>' +
    '<div class="bg-green-50 rounded p-1 text-center"><div class="text-green-600 font-bold">' + (recent.length - cleanCount) + '/' + recent.length + '</div><div class="text-gray-500 text-[10px]">有违规比率</div></div>' +
    '</div>';

  // 时间跨度
  chartHtml += '<div class="text-[10px] text-gray-400 mb-1 flex justify-between">' +
    '<span>📅 ' + firstDate + ' → ' + lastDate + '</span>' +
    '<span id="trend-max-v" class="text-gray-500">最大: ' + maxV + '</span>' +
    '</div>';

  // 柱状图区域（鼠标悬停显示详情）
  chartHtml += '<div id="trend-chart-area" class="relative mb-1">';
  chartHtml += '<div class="flex items-end gap-0.5 h-24 border-b border-gray-200 pb-0.5 overflow-x-auto">';
  recent.forEach((r, i) => {
    const v = r.details?.length || 0;
    const pct = Math.round(v / maxV * 100);
    const height = Math.max(1, Math.round(pct / 100 * 96));
    const color = v === 0 ? 'green' : v > maxV * 0.5 ? 'red' : 'orange';
    const name = r.drawingName.length > 10 ? r.drawingName.slice(0, 10) + '…' : r.drawingName;
    const timeStr = new Date(r.reviewedAt || r.createdAt || Date.now()).toLocaleDateString();
    const critCount = (r.details || []).filter(v => v.severity === 'critical').length;
    chartHtml += '<div class="flex-1 min-w-[24px] flex flex-col items-center cursor-pointer group" '
      + 'title="' + name + '\n违规: ' + v + '\n严重: ' + critCount + '\n时间: ' + timeStr + '">' +
      '<span class="text-[9px] text-' + color + '-600 mb-0.5 opacity-0 group-hover:opacity-100 transition-opacity">' + v + '</span>' +
      '<div class="w-full bg-' + color + '-500 rounded-t transition-all duration-200 group-hover:bg-' + color + '-700" style="height:' + height + 'px"></div>' +
      '<span class="text-[8px] text-gray-400 mt-0.5 rotate-45 origin-center whitespace-nowrap" title="' + name + '">' + name.slice(0, 4) + '</span>' +
      '</div>';
  });
  chartHtml += '</div></div>';

  // 类别分布（最近审查汇总）
  if (Object.keys(recentViolations).length > 0) {
    chartHtml += '<div class="mt-2 text-xs">' +
      '<span class="font-medium text-gray-500">类别分布</span>';
    const sortedCats = Object.entries(recentViolations).sort((a, b) => b[1].count - a[1].count);
    const catColors = {
      'EVAC': 'red', 'DIM': 'orange', 'DIST': 'yellow', 'COUNT': 'blue',
      'THERM': 'purple', 'STR': 'indigo', 'AREA': 'teal', 'LIGHT': 'cyan',
      'EXIST': 'lime', 'ATTR': 'pink', 'other': 'gray'
    };
    chartHtml += '<div class="flex flex-wrap gap-1 mt-1">';
    sortedCats.forEach(([cat, data]) => {
      const c = catColors[cat] || 'gray';
      chartHtml += '<span class="px-1 py-0.5 rounded bg-' + c + '-100 text-' + c + '-700 text-[10px]" '
        + 'title="违规: ' + data.count + ' | 严重: ' + data.critical + ' | 主要: ' + data.major + '">' +
        cat + ': ' + data.count + '</span>';
    });
    chartHtml += '</div></div>';
  }

  el.innerHTML = chartHtml;
}

function renderViolationDistBars() {
  const el = document.getElementById('violation-dist-bars');
  if (!el) return;
  loadReviewResults();
  if (reviewResults.length === 0) { el.innerHTML = '<div class="text-gray-400">审查图纸后自动统计</div>'; return; }
  const sev = {critical: 0, major: 0, minor: 0};
  reviewResults.forEach(r => (r.details || []).forEach(v => {
    if (v.severity === 'critical') sev.critical++;
    else if (v.severity === 'major') sev.major++;
    else sev.minor++;
  }));
  const total = sev.critical + sev.major + sev.minor || 1;
  el.innerHTML = [
    {label: '严重', key: 'critical', color: '#ef4444', count: sev.critical},
    {label: '主要', key: 'major', color: '#f97316', count: sev.major},
    {label: '轻微', key: 'minor', color: '#eab308', count: sev.minor},
  ].map(s =>
    '<div class="flex items-center gap-2"><span class="w-10 text-xs">' + s.label + '</span>' +
    '<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:' + (s.count/total*100) + '%;background:' + s.color + '"></div></div>' +
    '<span class="w-6 text-right text-xs">' + s.count + '</span></div>'
  ).join('');
}

