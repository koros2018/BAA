// ── 结果分析 ──────────────────────────────────────────────
function renderAnalysisTable() {
  const tbody = document.getElementById('analysis-table');
  if (!tbody) return;
  loadReviewResults();
  if (reviewResults.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">暂无数据，请先审查图纸</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  reviewResults.forEach((h, i) => {
    const viols = h.details?.length || 0;
    const checks = h.summary?.total_checks || 0;
    const passRate = checks > 0 ? Math.round((1 - viols / checks) * 100) : 0;
    const btLabel = h.buildingType === 'civil' ? '民用' : h.buildingType === 'industrial' ? '工业' : '--';
    tbody.innerHTML += '<tr class="border-b border-gray-50 text-sm">' +
      '<td class="py-2 px-2">' + (i + 1) + '</td>' +
      '<td class="py-2 px-2 truncate max-w-32" title="' + h.drawingName + '">' + h.drawingName + '</td>' +
      '<td class="py-2 px-2 text-xs">' + btLabel + '</td>' +
      '<td class="py-2 px-2">' + checks + '</td>' +
      '<td class="py-2 px-2 text-red-600">' + viols + '</td>' +
      '<td class="py-2 px-2"><div class="flex items-center gap-2"><div class="w-20 bg-gray-200 rounded-full h-2"><div class="bg-' + (passRate > 80 ? 'green' : passRate > 50 ? 'yellow' : 'red') + '-500 h-2 rounded-full" style="width:' + passRate + '%"></div></div><span class="text-xs">' + passRate + '%</span></div></td>' +
      '<td class="py-2 px-2 text-xs">' + new Date(h.reviewedAt).toLocaleString() + '</td></tr>';
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
  const recent = reviewResults.slice(0, 10).reverse();
  const maxV = Math.max(...recent.map(r => r.details?.length || 0), 1);
  el.innerHTML = recent.map(r => {
    const v = r.details?.length || 0;
    const pct = Math.round(v / maxV * 100);
    const name = r.drawingName.length > 10 ? r.drawingName.slice(0, 10) + '…' : r.drawingName;
    return '<div class="flex items-center gap-2"><span class="w-20 truncate text-xs" title="' + r.drawingName + '">' + name + '</span>' +
      '<div class="flex-1 bg-gray-100 rounded-full h-4 relative"><div class="bg-' + (v > 0 ? 'red' : 'green') + '-500 h-4 rounded-full" style="width:' + pct + '%"></div></div>' +
      '<span class="w-6 text-right text-xs">' + v + '</span></div>';
  }).join('');
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

