// ── P123 Step 6: 结果分析组件 ────────────────────────
// 从 baa-analysis.js 迁入 (221 行)

import { escHtml } from '../core/utils';

function getReviewResults(): Array<Record<string, unknown>> {
  return ((window as unknown as Record<string, unknown>).reviewResults as Array<Record<string, unknown>>) || [];
}

function renderAnalysisTable(): void {
  const tbody = document.getElementById('analysis-table');
  if (!tbody) return;
  const reviewResults = getReviewResults();
  if (reviewResults.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-gray-300">暂无数据，请先审查图纸</td></tr>'; return;
  }
  tbody.innerHTML = [...reviewResults]
    .sort((a, b) => ((b.violationCount as number) || 0) - ((a.violationCount as number) || 0))
    .slice(0, 30)
    .map((h, i) => {
      const viols = (h.violationCount as number) || 0;
      const checks = (h.entityCount as number) || 1;
      const passRate = checks > 0 ? Math.round((1 - viols / checks) * 100) : 0;
      const bt = h.buildingType as string;
      const btLabel = bt === 'civil' ? '民用' : bt === 'industrial' ? '工业' : '--';
      const safeName = escHtml(h.drawingName as string);
      return `<tr class="border-b border-gray-50 text-sm">
        <td class="py-2 px-2">${i + 1}</td>
        <td class="py-2 px-2 truncate max-w-32" title="${safeName}">${safeName}</td>
        <td class="py-2 px-2 text-xs">${btLabel}</td>
        <td class="py-2 px-2 text-red-600">${viols}</td>
        <td class="py-2 px-2"><div class="flex items-center gap-2">
          <div class="w-20 bg-gray-200 rounded-full h-2"><div class="bg-${passRate > 80 ? 'green' : passRate > 50 ? 'yellow' : 'red'}-500 h-2 rounded-full" style="width:${Math.max(0, passRate)}%"></div></div>
          <span class="text-xs">${Math.max(0, passRate)}%</span></div></td>
        <td class="py-2 px-2 text-xs">${h.reviewedAt ? new Date(h.reviewedAt as string).toLocaleString('zh-CN') : '--'}</td></tr>`;
    }).join('');
}

function renderCategoryAnalysis(): void {
  const el = document.getElementById('category-analysis');
  if (!el) return;
  const reviewResults = getReviewResults();
  if (!reviewResults.length) { el.innerHTML = '<div class="text-gray-400 text-xs">审查图纸后自动统计</div>'; return; }

  const catStats: Record<string, { evac: number; corridor: number; dead_end: number; other: number }> = {};
  reviewResults.forEach((h) => {
    const name = h.drawingName as string || 'unknown';
    if (!catStats[name]) catStats[name] = { evac: 0, corridor: 0, dead_end: 0, other: 0 };
    (h.details as Array<Record<string, unknown>>)?.forEach((v) => {
      const fid = v.func_id as string || '';
      if (fid.startsWith('EVAC-')) catStats[name].evac++;
      else if (fid === 'DIM-004') catStats[name].corridor++;
      else if ((v.explanation as string || '').toLowerCase().includes('死胡同')) catStats[name].dead_end++;
      else catStats[name].other++;
    });
  });

  const names = Object.keys(catStats);
  if (!names.length) { el.innerHTML = '<div class="text-gray-400 text-xs">审查图纸后自动统计</div>'; return; }

  const totalEvac = names.reduce((s, n) => s + catStats[n].evac, 0);
  const totalCor = names.reduce((s, n) => s + catStats[n].corridor, 0);
  const totalDead = names.reduce((s, n) => s + catStats[n].dead_end, 0);
  const totalOther = names.reduce((s, n) => s + catStats[n].other, 0);

  let html = '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
    '<th class="pb-1 pr-2">图纸</th><th class="pb-1 pr-2">🚪疏散</th><th class="pb-1 pr-2">📏走廊</th><th class="pb-1 pr-2">🔒死胡同</th><th class="pb-1">其他</th></tr></thead><tbody>';
  names.forEach((name) => {
    const s = catStats[name];
    html += `<tr class="border-b border-gray-50">
      <td class="py-1 pr-2 truncate max-w-28" title="${name}">${name}</td>
      <td class="py-1 pr-2"><span class="${s.evac > 0 ? 'text-red-600 font-medium' : 'text-green-500'}">${s.evac}</span></td>
      <td class="py-1 pr-2"><span class="${s.corridor > 0 ? 'text-orange-600 font-medium' : 'text-green-500'}">${s.corridor}</span></td>
      <td class="py-1 pr-2"><span class="${s.dead_end > 0 ? 'text-yellow-600 font-medium' : 'text-green-500'}">${s.dead_end}</span></td>
      <td class="py-1">${s.other}</td></tr>`;
  });
  html += `<tr class="font-medium bg-gray-50"><td class="py-1 pr-2">合计</td><td class="py-1 pr-2">${totalEvac}</td><td class="py-1 pr-2">${totalCor}</td><td class="py-1 pr-2">${totalDead}</td><td class="py-1">${totalOther}</td></tr>`;
  html += '</tbody></table>';
  el.innerHTML = html;
}

function renderTrendBars(): void {
  const el = document.getElementById('trend-bars');
  if (!el) return;
  const reviewResults = getReviewResults();
  if (!reviewResults.length) { el.innerHTML = '<div class="text-gray-400">审查图纸后自动统计</div>'; return; }
  const recent = reviewResults.slice(0, 20).reverse();
  const maxV = Math.max(...recent.map((r) => ((r.details as unknown[]).length || 0)), 1);
  const totalV = recent.reduce((s, r) => s + ((r.details as unknown[]).length || 0), 0);
  const avgV = Math.round(totalV / recent.length * 10) / 10;
  const cleanCount = recent.filter((r) => ((r.details as unknown[]).length || 0) === 0).length;
  const firstD = new Date(recent[0]?.reviewedAt as string || Date.now()).toLocaleDateString();
  const lastD = new Date(recent[recent.length - 1]?.reviewedAt as string || Date.now()).toLocaleDateString();

  let chart = '<div class="grid grid-cols-4 gap-1 mb-2 text-xs">' +
    `<div class="bg-blue-50 rounded p-1 text-center"><div class="text-blue-600 font-bold">${recent.length}</div><div class="text-gray-500 text-[10px]">审查次数</div></div>` +
    `<div class="bg-red-50 rounded p-1 text-center"><div class="text-red-600 font-bold">${totalV}</div><div class="text-gray-500 text-[10px]">违规总数</div></div>` +
    `<div class="bg-yellow-50 rounded p-1 text-center"><div class="text-yellow-600 font-bold">${avgV}</div><div class="text-gray-500 text-[10px]">平均违规/次</div></div>` +
    `<div class="bg-green-50 rounded p-1 text-center"><div class="text-green-600 font-bold">${recent.length - cleanCount}/${recent.length}</div><div class="text-gray-500 text-[10px]">有违规比率</div></div>` +
  '</div>' +
  `<div class="text-[10px] text-gray-400 mb-1"><span>📅 ${firstD} → ${lastD}</span><span>最大: ${maxV}</span></div>`;

  chart += '<div class="flex items-end gap-0.5 h-24 border-b border-gray-200 pb-0.5 overflow-x-auto">';
  recent.forEach((r) => {
    const v = (r.details as unknown[]).length || 0;
    const pct = Math.round(v / maxV * 100);
    const height = Math.max(1, Math.round(pct / 100 * 96));
    const color = v === 0 ? 'green' : v > maxV * 0.5 ? 'red' : 'orange';
    const name = (r.drawingName as string || '').slice(0, 10);
    chart += `<div class="flex-1 min-w-[24px] flex flex-col items-center">` +
      `<div class="w-full bg-${color}-500 rounded-t" style="height:${height}px"></div>` +
      `<span class="text-[8px] text-gray-400 mt-0.5" title="${name}">${name.slice(0, 4)}</span></div>`;
  });
  chart += '</div>';
  el.innerHTML = chart;
}

function renderViolationDistBars(): void {
  const el = document.getElementById('violation-dist-bars');
  if (!el) return;
  const reviewResults = getReviewResults();
  if (!reviewResults.length) { el.innerHTML = '<div class="text-gray-400">审查图纸后自动统计</div>'; return; }
  const sev = { critical: 0, major: 0, minor: 0 };
  reviewResults.forEach((r) => (r.details as Array<{ severity?: string }>)?.forEach((v) => {
    if (v.severity === 'critical') sev.critical++;
    else if (v.severity === 'major') sev.major++;
    else sev.minor++;
  }));
  const total = sev.critical + sev.major + sev.minor || 1;
  el.innerHTML = [
    { label: '严重', count: sev.critical, color: '#ef4444' },
    { label: '主要', count: sev.major, color: '#f97316' },
    { label: '轻微', count: sev.minor, color: '#eab308' },
  ].map((s) =>
    `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span>` +
    `<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div>` +
    `<span class="w-6 text-right text-xs">${s.count}</span></div>`
  ).join('');
}

// loadAnalysis 已定义在 stats.ts，analysis.ts 仅提供子渲染函数
export { renderAnalysisTable, renderCategoryAnalysis, renderTrendBars, renderViolationDistBars };
