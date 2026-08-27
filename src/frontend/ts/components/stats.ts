// ── P123 Step 6: 统计仪表盘组件 ────────────────────────
import { getApiBase, getHeaders } from '../core/api-client';

type StatsCache = Record<string, unknown>;
type ReviewItem = Record<string, unknown>;

let statsCache: StatsCache | null = null;

function _getReviewResults(): ReviewItem[] {
  return ((window as unknown as Record<string, unknown>).reviewResults as ReviewItem[]) || [];
}

async function loadStats(days = 30): Promise<void> {
  try {
    const url = getApiBase() + `/api/v1/stats?days=${days}`;
    const r = await fetch(url, { headers: getHeaders() });
    if (r.ok) {
      const data = (await r.json()) as StatsCache;
      if (data.status === 'ok') { statsCache = data; return; }
    }
  } catch { /* fallback */ }
  statsCache = null;
}

function _arrLen(v: unknown): number {
  return Array.isArray(v) ? v.length : 0;
}

function renderOverviewCards(): void {
  const el = document.getElementById('overview-cards');
  if (!el) return;
  const overview = (statsCache?.overview as Record<string, unknown>) || {};
  const reviewResults = _getReviewResults();
  if (!overview.total_reviews && reviewResults.length) {
    const totalV = reviewResults.reduce((s, r) => s + ((r.details as unknown[]).length || 0), 0);
    Object.assign(overview, {
      total_reviews: reviewResults.length,
      total_violations: totalV,
      avg_compliance_rate: reviewResults.filter((r) => ((r.details as unknown[]).length || 0) === 0).length / reviewResults.length,
      avg_compliance_score: 0, avg_processing_time_ms: 0,
    });
  }
  if ((overview.total_reviews as number) === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">暂无审查数据</div>'; return;
  }
  const passRate = ((overview.avg_compliance_rate as number) || 0) * 100;
  el.innerHTML = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;">' +
    `<div class="card p-3 text-center"><div class="text-2xl font-bold text-blue-600">${overview.total_reviews}</div><div class="text-xs text-gray-500 mt-1">审查次数</div></div>` +
    `<div class="card p-3 text-center"><div class="text-2xl font-bold text-red-600">${overview.total_violations}</div><div class="text-xs text-gray-500 mt-1">违规总数</div></div>` +
    `<div class="card p-3 text-center"><div class="text-2xl font-bold text-green-600">${Math.round(passRate)}%</div><div class="text-xs text-gray-500 mt-1">平均合规率</div></div>` +
    `<div class="card p-3 text-center"><div class="text-2xl font-bold text-yellow-600">${overview.avg_compliance_score || '--'}</div><div class="text-xs text-gray-500 mt-1">平均得分</div></div>` +
    `<div class="card p-3 text-center"><div class="text-2xl font-bold text-purple-600">${Math.round(overview.avg_processing_time_ms as number || 0)}ms</div><div class="text-xs text-gray-500 mt-1">平均耗时</div></div>` +
  '</div>';
}

function renderTrendChart(): void {
  const el = document.getElementById('trend-chart');
  if (!el) return;
  const trend = (statsCache?.trend as Array<{ date: string; reviews: number; violations: number }>) || [];
  if (!trend.length) { el.innerHTML = '<div class="text-gray-400 text-sm">暂无趋势数据</div>'; return; }
  const maxH = Math.max(...trend.flatMap((t) => [t.violations, t.reviews]), 1);
  let bars = '<div style="flex:1;display:flex;align-items:flex-end;gap:4px;height:120px;border-bottom:1px solid #e5e7eb;padding-bottom:2px;">';
  trend.forEach((t) => {
    const hV = Math.round(t.violations / maxH * 115);
    const hR = Math.round(t.reviews / maxH * 115);
    const sd = t.date.length > 4 ? t.date.slice(5) : t.date;
    bars += `<div style="flex:1;min-width:30px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;">` +
      `<div style="display:flex;align-items:flex-end;gap:1px;">` +
      `<div style="background:#ef4444;border-radius:2px 2px 0 0;width:10px;height:${hV}px"></div>` +
      `<div style="background:#3b82f6;border-radius:2px 2px 0 0;width:10px;height:${hR}px"></div></div>` +
      `<span style="font-size:9px;color:#9ca3af;margin-top:2px;">${sd}</span></div>`;
  });
  bars += '</div>';
  el.innerHTML = bars +
    `<div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7280;margin-top:4px;">` +
    `<div><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:#ef4444;margin-right:4px;"></span>违规` +
    `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:#3b82f6;margin-left:16px;margin-right:4px;"></span>审查</div>` +
    `<span style="color:#9ca3af;">峰值: ${maxH}</span></div>`;
}

function renderViolationDist(): void {
  const el = document.getElementById('violation-dist');
  if (!el) return;
  const dist = (statsCache?.violation_distribution as Record<string, number>) || {};
  const total = dist.critical + dist.major + dist.minor || 1;
  const items = [
    { label: '严重', count: dist.critical || 0, color: '#ef4444' },
    { label: '主要', count: dist.major || 0, color: '#f97316' },
    { label: '轻微', count: dist.minor || 0, color: '#eab308' },
  ];
  el.innerHTML = items.map((s) =>
    `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span>` +
    `<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div>` +
    `<span class="w-6 text-right text-xs">${s.count}</span></div>`
  ).join('');
}

function renderConfidenceDist(): void {
  const el = document.getElementById('confidence-dist');
  if (!el) return;
  const dist = (statsCache?.confidence_distribution as Record<string, number>) || {};
  const total = dist.confirmed + dist.suspected + dist.needs_review || 1;
  const items = [
    { label: '确认', count: dist.confirmed || 0, color: '#22c55e' },
    { label: '疑似', count: dist.suspected || 0, color: '#f59e0b' },
    { label: '待复核', count: dist.needs_review || 0, color: '#ef4444' },
  ];
  el.innerHTML = items.map((s) =>
    `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span>` +
    `<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div>` +
    `<span class="w-6 text-right text-xs">${s.count}</span></div>`
  ).join('');
}

function renderBuildingTypeDist(): void {
  const el = document.getElementById('building-type-dist');
  if (!el) return;
  const dist = (statsCache?.building_type_distribution as Record<string, number>) || {};
  const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
  const items = [
    { label: '民用', count: dist.civil || 0, color: '#3b82f6' },
    { label: '工业', count: dist.industrial || 0, color: '#8b5cf6' },
  ];
  el.innerHTML = items.map((s) =>
    `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span>` +
    `<div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div>` +
    `<span class="w-6 text-right text-xs">${s.count}</span></div>`
  ).join('');
}

function renderEntityDist(): void {
  const el = document.getElementById('entity-dist');
  if (!el) return;
  const dist = (statsCache?.entity_type_distribution as Record<string, number>) || {};
  const items = Object.entries(dist).slice(0, 10);
  if (!items.length) { el.innerHTML = '<div class="text-gray-400 text-sm">暂无数据</div>'; return; }
  const maxV = items[0][1];
  el.innerHTML = items.map(([type, count]) =>
    `<div class="flex items-center gap-2"><span class="w-20 text-xs font-mono truncate">${type}</span>` +
    `<div class="flex-1 bg-gray-100 rounded-full h-3"><div class="h-3 rounded-full bg-blue-500" style="width:${Math.round(count / maxV * 100)}%"></div></div>` +
    `<span class="text-xs">${count}</span></div>`
  ).join('');
}

function renderTopViolations(): void {
  const el = document.getElementById('top-violations');
  if (!el) return;
  const top = (statsCache?.top_violations as Array<{ clause_id: string; title?: string; count: number }>) || [];
  if (!top.length) { el.innerHTML = '<div class="text-gray-400 text-sm">暂无数据</div>'; return; }
  el.innerHTML = '<table class="w-full text-sm"><thead><tr class="text-left text-gray-400 border-b">' +
    '<th class="pb-2 px-2">#</th><th class="pb-2 px-2">条款编号</th><th class="pb-2 px-2">条款标题</th><th class="pb-2 px-2 text-right">次数</th></tr></thead><tbody>' +
    top.map((v, i) => `<tr class="border-b border-gray-50"><td class="py-1 px-2 text-xs">${i + 1}</td>` +
      `<td class="py-1 px-2 font-mono text-xs">${v.clause_id}</td>` +
      `<td class="py-1 px-2 truncate max-w-64">${v.title || '--'}</td>` +
      `<td class="py-1 px-2 text-right text-sm font-medium text-red-600">${v.count}</td></tr>`).join('') +
    '</tbody></table>';
}

async function loadAnalysis(days = 30): Promise<void> {
  document.querySelectorAll('button[onclick^="loadAnalysis"]').forEach((btn) => {
    btn.classList.remove('bg-blue-100', 'hover:bg-blue-200');
    btn.classList.add('hover:bg-gray-100');
    const match = btn.getAttribute('onclick')?.match(/loadAnalysis\((\d*)\)/);
    if (match) {
      const btnDays = match[1] ? parseInt(match[1]) : 0;
      if (btnDays === days || (!match[1] && days === 30)) {
        btn.classList.remove('hover:bg-gray-100');
        btn.classList.add('bg-blue-100', 'hover:bg-blue-200');
      }
    }
  });
  await loadStats(days);
  renderOverviewCards();
  renderTrendChart();
  renderViolationDist();
  renderConfidenceDist();
  renderBuildingTypeDist();
  renderEntityDist();
  renderTopViolations();
}

export { loadAnalysis, renderOverviewCards };
