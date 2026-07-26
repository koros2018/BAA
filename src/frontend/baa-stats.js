// ── P72: 统计仪表盘 ─────────────────────────────────────
// 优先从 /api/v1/stats 获取聚合数据，本地 reviewResults 作为 fallback
let statsCache = null;  // 缓存最近一次 stats API 响应

// loadReviewResults 的 Promise 封装（原函数在 baa-review.js 中，非 async）
function _loadReviewResultsAsync() {
  return new Promise((resolve) => {
    const r = loadReviewResults();
    if (r && typeof r.then === 'function') {
      r.then(resolve).catch(() => { resolve(); });
    } else {
      resolve();
    }
  });
}

async function loadStats(days = 30) {
  console.log('[baa-stats] loadStats called, days=' + days);
  try {
    const url = API_BASE() + '/api/v1/stats?days=' + days;
    console.log('[baa-stats] fetching', url);
    const r = await fetch(url, {headers: getHeaders()});
    console.log('[baa-stats] fetch response status', r.status, r.ok);
    if (r.ok) {
      const data = await r.json();
      console.log('[baa-stats] response data status:', data.status, 'trend:', data.trend?.length, 'overview:', data.overview?.total_reviews);
      if (data.status === 'ok') {
        statsCache = data;
        console.log('[baa-stats] statsCache set, overview:', statsCache.overview);
        return data;
      }
    }
  } catch (e) {
    console.warn('[baa-stats] stats API 不可用', e);
  }
  // Fallback: 从本地 reviewResults 推导
  await _loadReviewResultsAsync();
  console.warn('[baa-stats] falling back to local reviewResults, length:', reviewResults?.length);
  return null;
}

// ── 总览卡片 ─────────────────────────────────────────────
function renderOverviewCards() {
  const el = document.getElementById('overview-cards');
  if (!el) return;

  let overview = statsCache?.overview || {};
  if (!overview.total_reviews && reviewResults?.length) {
    // fallback: 从本地数据推导
    const totalV = reviewResults.reduce((s, r) => s + (r.details?.length || 0), 0);
    overview = {
      total_reviews: reviewResults.length,
      total_drawings: reviewResults.length,
      total_violations: totalV,
      avg_compliance_score: 0,
      avg_compliance_rate: reviewResults.length > 0 ? (reviewResults.filter(r => r.details?.length === 0).length / reviewResults.length) : 0,
      avg_processing_time_ms: 0,
    };
  }

  if (overview.total_reviews === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">暂无审查数据</div>';
    return;
  }

  const passRate = (overview.avg_compliance_rate || 0) * 100;
  el.innerHTML =
    '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;">' +
      '<div class="card p-3 text-center"><div class="text-2xl font-bold text-blue-600">' + overview.total_reviews + '</div><div class="text-xs text-gray-500 mt-1">审查次数</div></div>' +
      '<div class="card p-3 text-center"><div class="text-2xl font-bold text-red-600">' + overview.total_violations + '</div><div class="text-xs text-gray-500 mt-1">违规总数</div></div>' +
      '<div class="card p-3 text-center"><div class="text-2xl font-bold text-green-600">' + Math.round(passRate) + '%</div><div class="text-xs text-gray-500 mt-1">平均合规率</div></div>' +
      '<div class="card p-3 text-center"><div class="text-2xl font-bold text-yellow-600">' + (overview.avg_compliance_score || '--') + '</div><div class="text-xs text-gray-500 mt-1">平均得分</div></div>' +
      '<div class="card p-3 text-center"><div class="text-2xl font-bold text-purple-600">' + Math.round(overview.avg_processing_time_ms || 0) + 'ms</div><div class="text-xs text-gray-500 mt-1">平均耗时</div></div>' +
    '</div>';
}

// ── 趋势图（按天聚合，双柱并列：违规数 vs 审查次数） ─────
function renderTrendChart() {
  const el = document.getElementById('trend-chart');
  console.log('[baa-stats] renderTrendChart, el:', el ? 'found' : 'null', 'statsCache:', statsCache ? 'set' : 'null');
  if (!el) return;

  let trend = statsCache?.trend || [];
  console.log('[baa-stats] renderTrendChart trend data:', trend.length, 'entries');
  if (trend.length > 0) console.log('[baa-stats] first trend entry:', JSON.stringify(trend[0]));
  if (!trend.length && reviewResults?.length) {
    const daily = {};
    reviewResults.slice(0, 30).reverse().forEach(r => {
      const d = new Date(r.reviewedAt || r.createdAt || Date.now());
      const key = d.toLocaleDateString('zh-CN');
      if (!daily[key]) daily[key] = {date: key, reviews: 0, violations: 0};
      daily[key].reviews++;
      daily[key].violations += r.violationCount || 0;
    });
    trend = Object.values(daily);
  }

  if (!trend.length) {
    el.innerHTML = '<div class="text-gray-400 text-sm">暂无趋势数据</div>';
    return;
  }

  const maxH = Math.max(...trend.flatMap(t => [t.violations, t.reviews]), 1);

  // Y 轴刻度（用内联样式避免 JIT 类名问题）
  let yAxis = '<div style="display:flex;flex-direction:column-reverse;justify-content:space-between;font-size:10px;color:#9ca3af;margin-right:4px;height:120px;flex-shrink:0;">';
  [0, 0.25, 0.5, 0.75, 1].forEach(pct => {
    yAxis += '<span style="line-height:1px;">' + Math.round(maxH * pct) + '</span>';
  });
  yAxis += '</div>';

  // 柱状图容器
  let bars = '<div style="flex:1;display:flex;align-items:flex-end;gap:4px;height:120px;border-bottom:1px solid #e5e7eb;padding-bottom:2px;overflow-x:auto;">';
  trend.forEach(t => {
    const v = t.violations;
    const r = t.reviews;
    const hV = Math.round(v / maxH * 115);
    const hR = Math.round(r / maxH * 115);
    const shortDate = t.date.length > 4 ? t.date.slice(5) : t.date;
    bars += '<div style="flex:1;min-width:30px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;" '
      + 'title="' + t.date + '\n审查: ' + r + '\n违规: ' + v + '">'
      + '<div style="display:flex;align-items:flex-end;gap:1px;">'
        + '<div style="background:#ef4444;border-radius:2px 2px 0 0;width:10px;height:' + hV + 'px"></div>'
        + '<div style="background:#3b82f6;border-radius:2px 2px 0 0;width:10px;height:' + hR + 'px"></div>'
      + '</div>'
      + '<span style="font-size:9px;color:#9ca3af;margin-top:2px;">' + shortDate + '</span>'
      + '</div>';
  });
  bars += '</div>';

  // 图例 + 峰值
  let legend = '<div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#6b7280;margin-top:4px;">'
    + '<div style="display:flex;gap:16px;">'
      + '<span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:#ef4444;margin-right:4px;"></span>违规</span>'
      + '<span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:#3b82f6;margin-right:4px;"></span>审查</span>'
    + '</div>'
    + '<span style="color:#9ca3af;">峰值: ' + maxH + '</span>'
  + '</div>';

  el.innerHTML = '<div style="display:flex;">' + yAxis + bars + '</div>' + legend;
}

// ── 违规分布（按严重度） ────────────────────────────────
function renderViolationDist() {
  const el = document.getElementById('violation-dist');
  if (!el) return;

  let dist = statsCache?.violation_distribution || {};
  if (!dist.critical && !dist.major && !dist.minor && reviewResults?.length) {
    dist = {critical: 0, major: 0, minor: 0};
    reviewResults.forEach(r => (r.details || []).forEach(v => {
      if (v.severity === 'critical') dist.critical++;
      else if (v.severity === 'major') dist.major++;
      else dist.minor++;
    }));
  }

  const total = dist.critical + dist.major + dist.minor || 1;
  const items = [
    {label: '严重', count: dist.critical || 0, color: '#ef4444'},
    {label: '主要', count: dist.major || 0, color: '#f97316'},
    {label: '轻微', count: dist.minor || 0, color: '#eab308'},
  ];

  el.innerHTML = items.map(s =>
    '<div class="flex items-center gap-2"><span class="w-10 text-xs">' + s.label + '</span>' +
    '<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:' + (s.count/total*100) + '%;background:' + s.color + '"></div></div>' +
    '<span class="w-6 text-right text-xs">' + s.count + '</span></div>'
  ).join('');
}

// ── 置信度分布 ────────────────────────────────────────────
function renderConfidenceDist() {
  const el = document.getElementById('confidence-dist');
  if (!el) return;

  let dist = statsCache?.confidence_distribution || {};
  if (!dist.confirmed && !dist.suspected && reviewResults?.length) {
    dist = {confirmed: 0, suspected: 0, needs_review: 0};
    reviewResults.forEach(r => (r.details || []).forEach(v => {
      const t = v.confidence_tier || 'suspected';
      if (t === 'confirmed') dist.confirmed++;
      else if (t === 'suspected') dist.suspected++;
      else if (t === 'needs_review') dist.needs_review++;
    }));
  }

  const total = dist.confirmed + dist.suspected + dist.needs_review || 1;
  const items = [
    {label: '确认', count: dist.confirmed || 0, color: '#22c55e'},
    {label: '疑似', count: dist.suspected || 0, color: '#f59e0b'},
    {label: '待复核', count: dist.needs_review || 0, color: '#ef4444'},
  ];

  el.innerHTML = items.map(s =>
    '<div class="flex items-center gap-2"><span class="w-10 text-xs">' + s.label + '</span>' +
    '<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:' + (s.count/total*100) + '%;background:' + s.color + '"></div></div>' +
    '<span class="w-6 text-right text-xs">' + s.count + '</span></div>'
  ).join('');
}

// ── 建筑类型分布 ─────────────────────────────────────────
function renderBuildingTypeDist() {
  const el = document.getElementById('building-type-dist');
  if (!el) return;

  let dist = statsCache?.building_type_distribution || {};
  if (!dist.civil && !dist.industrial && reviewResults?.length) {
    dist = {civil: 0, industrial: 0};
    reviewResults.forEach(r => {
      const bt = r.buildingType || 'civil';
      dist[bt] = (dist[bt] || 0) + 1;
    });
  }

  const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
  const items = [
    {label: '民用', count: dist.civil || 0, color: '#3b82f6'},
    {label: '工业', count: dist.industrial || 0, color: '#8b5cf6'},
  ];

  el.innerHTML = items.map(s =>
    '<div class="flex items-center gap-2"><span class="w-10 text-xs">' + s.label + '</span>' +
    '<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:' + (s.count/total*100) + '%;background:' + s.color + '"></div></div>' +
    '<span class="w-6 text-right text-xs">' + s.count + '</span></div>'
  ).join('');
}

// ── 实体类型 TOP-10 ─────────────────────────────────────
function renderEntityDist() {
  const el = document.getElementById('entity-dist');
  if (!el) return;

  let dist = statsCache?.entity_type_distribution || {};
  if (!Object.keys(dist).length && reviewResults?.length) {
    dist = {};
    reviewResults.forEach(r => (r.details || []).forEach(v => {
      const t = v.entity_type || v.type || 'unknown';
      dist[t] = (dist[t] || 0) + 1;
    }));
    // 按数量降序
    dist = Object.fromEntries(Object.entries(dist).sort((a, b) => b[1] - a[1]));
  }

  const items = Object.entries(dist).slice(0, 10);
  if (!items.length) {
    el.innerHTML = '<div class="text-gray-400 text-sm">暂无数据</div>';
    return;
  }

  const maxV = items[0][1];
  el.innerHTML = items.map(([type, count]) =>
    '<div class="flex items-center gap-2">' +
      '<span class="w-20 text-xs font-mono truncate" title="' + type + '">' + type + '</span>' +
      '<div class="flex-1 bg-gray-100 rounded-full h-3"><div class="h-3 rounded-full bg-blue-500" style="width:' + Math.round(count/maxV*100) + '%"></div></div>' +
      '<span class="text-xs">' + count + '</span>' +
    '</div>'
  ).join('');
}

// ── TOP 违规条款 ──────────────────────────────────────────
function renderTopViolations() {
  const el = document.getElementById('top-violations');
  if (!el) return;

  let top = statsCache?.top_violations || [];
  if (!top.length && reviewResults?.length) {
    const counter = {};
    reviewResults.forEach(r => (r.details || []).forEach(v => {
      const cid = v.clause_id || '';
      if (!cid) return;
      if (!counter[cid]) counter[cid] = {clause_id: cid, title: v.clause_title || cid, count: 0};
      counter[cid].count++;
    }));
    top = Object.values(counter).sort((a, b) => b.count - a.count).slice(0, 10);
  }

  if (!top.length) {
    el.innerHTML = '<div class="text-gray-400 text-sm">暂无数据</div>';
    return;
  }

  el.innerHTML = '<table class="w-full text-sm">' +
    '<thead><tr class="text-left text-gray-400 border-b">' +
      '<th class="pb-2 px-2">#</th>' +
      '<th class="pb-2 px-2">条款编号</th>' +
      '<th class="pb-2 px-2">条款标题</th>' +
      '<th class="pb-2 px-2 text-right">次数</th>' +
    '</tr></thead><tbody>' +
    top.map((v, i) =>
      '<tr class="border-b border-gray-50">' +
        '<td class="py-1 px-2 text-xs">' + (i + 1) + '</td>' +
        '<td class="py-1 px-2 font-mono text-xs">' + v.clause_id + '</td>' +
        '<td class="py-1 px-2 truncate max-w-64" title="' + (v.title || '') + '">' + (v.title || '--') + '</td>' +
        '<td class="py-1 px-2 text-right text-sm font-medium text-red-600">' + v.count + '</td>' +
      '</tr>'
    ).join('') +
    '</tbody></table>';
}

// ── 主入口 ───────────────────────────────────────────────
async function loadAnalysis(days = 30) {
  console.log('[baa-stats] loadAnalysis called, days=' + days);
  // 高亮当前选中的按钮
  document.querySelectorAll('button[onclick^="loadAnalysis"]').forEach(btn => {
    btn.classList.remove('bg-blue-100', 'hover:bg-blue-200');
    btn.classList.add('hover:bg-gray-100');
    const match = btn.getAttribute('onclick').match(/loadAnalysis\((\d*)\)/);
    if (match) {
      const btnDays = match[1] ? parseInt(match[1]) : 0;
      if (btnDays === days || (!match[1] && days === 30)) {
        btn.classList.remove('hover:bg-gray-100');
        btn.classList.add('bg-blue-100', 'hover:bg-blue-200');
      }
    }
  });
  await loadStats(days);
  console.log('[baa-stats] after loadStats, statsCache:', statsCache ? 'set' : 'null');
  // 确保 reviewResults 可用（兼容 async 和 .then 两种模式）
  await _loadReviewResultsAsync();
  console.log('[baa-stats] after loadReviewResults, reviewResults length:', reviewResults?.length);

  renderOverviewCards();
  renderTrendChart();
  renderViolationDist();
  renderConfidenceDist();
  renderBuildingTypeDist();
  renderEntityDist();
  renderTopViolations();
  // 安全调用详情表（可能不存在于 baa-analysis.js 中）
  try { if (typeof renderAnalysisTable === 'function') renderAnalysisTable(); } catch(e) {}
  try { if (typeof renderCategoryAnalysis === 'function') renderCategoryAnalysis(); } catch(e) {}
  console.log('[baa-stats] loadAnalysis complete');
}
