// P122: escHtml 在 baa-review.ts 加载时 baa-ext.js 可能尚未加载，本地定义兜底
// 用 export 函数供 ES module 导出，window 挂接供 onclick 调用
declare const escHtml: ((s: unknown) => string) | undefined;

export function _escHtml(str: unknown): string {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
// 确保全局 escHtml 可用
if (typeof escHtml !== 'function') {
  (window as unknown as { escHtml?: (s: unknown) => string }).escHtml = _escHtml;
}

// ── 全局依赖声明（不修改全局状态）──────────────────────────
declare const parsedDrawings: unknown[];
declare const reviewResults: unknown[];
declare const API_BASE: () => string;
declare const HEADERS: () => Record<string, string>;
declare const showToast: (msg: string, kind?: string) => void;
declare const renderProgress: (el: HTMLElement | null, text: string, pct: number) => void;
declare const renderThermalViolations: (v: unknown[]) => void;
declare const renderStructuralViolations: (v: unknown[]) => void;
declare const loadFeedbackStats: () => void;
declare const loadFeedbacks: () => void;
declare const renderStructuralThresholds: () => void;
declare const confirmCorrection: (reviewId: string, idx: number, accept: boolean) => void;
declare const auditAction: (itemId: string, action: string, clauseId: string) => void;

// 类型别名
type ReviewFinding = Record<string, unknown>;
type ReviewCorrection = Record<string, unknown>;
type ReviewResult = Record<string, unknown>;

// ── AI审图 ──────────────────────────────────────────────
export async function runReview() {
  const select = document.getElementById('review-drawing-select');
  const id = (select as HTMLSelectElement | null)?.value ?? '';
  if (!id) { showToast('请选择已解析的图纸', 'info'); return; }
  const drawing = parsedDrawings.find(d => d.id === id) as Record<string, unknown> | undefined;
  if (!drawing) { showToast('图纸数据不存在', 'info'); return; }
  const bt = drawing.building_type as string;

  const entities = (drawing.entities || drawing.raw?.entities) as unknown[] || [];
  if (entities.length === 0) { showToast('该图纸没有解析出实体数据，请重新上传解析', 'info'); return; }

  const loading = document.getElementById('review-loading');
  renderProgress(loading, '审查中', 30);

  try {
    const url = API_BASE() + '/review-from-data';
    const r = await fetch(url, {
      method: 'POST', headers: { ...HEADERS(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ entities: entities, building_type: bt }),
    });
    const result = (await r.json()) as ReviewResult;
    if (loading) loading.className = 'hidden';

    const summary = document.getElementById('review-summary');
    window._currentReviewResult = result;
    window._currentReviewEntities = entities;
    if (result.status === 'success') {
      const vs = (result.summary || {}) as Record<string, unknown>;
      const tc = (vs.confidence_tier_counts || { confirmed: 0, suspected: 0, needs_review: 0 }) as Record<string, number>;
      summary.innerHTML =
        '<div class="grid grid-cols-4 gap-2 mb-3">' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + (vs.violations || 0) + '</div><div class="text-xs text-gray-400">违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + tc.confirmed + '</div><div class="text-xs text-gray-400">✅ 确认违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + tc.suspected + '</div><div class="text-xs text-gray-400">🟡 疑似违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + tc.needs_review + '</div><div class="text-xs text-gray-400">🔴 建议复核</div></div>' +
        '</div>';

      if (result.summary?.entity_types || result.queue_info?.task_id || result.task_id) {
        const summaryExtras: string[] = [];
        if (result.summary?.entity_types) {
          const entityParts: string[] = [];
          for (const [type, count] of Object.entries(result.summary.entity_types)) {
            entityParts.push('<span class="px-2 py-0.5 bg-gray-100 rounded text-xs">' + escHtml(type) + ': ' + count + '</span>');
          }
          summaryExtras.push('<p class="text-xs text-gray-400 mb-2">构件分布:</p><div class="flex flex-wrap gap-1 mb-3">' + entityParts.join('') + '</div>');
        }
        const reviewId = (result.queue_info?.task_id || result.task_id || '') as string;
        if (reviewId) {
          const safeReviewId = escHtml(reviewId);
          summaryExtras.push(
            '<div class="mt-3 flex gap-2">' +
            '<button onclick="downloadReviewPdf(\'' + safeReviewId + '\')" class="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">📄 PDF报告</button>' +
            '<button onclick="downloadReviewExport(\'' + safeReviewId + '\', \'' + 'json' + '\')" class="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">📋 导出JSON</button>' +
            '<button onclick="downloadReviewExport(\'' + safeReviewId + '\', \'' + 'csv' + '\')" class="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">📊 导出CSV</button>' +
            '</div>'
          );
        }
        summary.innerHTML += summaryExtras.join('');
      }

      const details = document.getElementById('review-details');
      details.innerHTML = '';

      renderStructuredSummary(result.structured_summary || {}, result.summary || {});
      _initAuditItems(result);

      const severityCounts: Record<string, number> = {};
      ((result.findings || []) as ReviewFinding[]).filter(f => f.result === 'FAIL' && !f.is_duplicate).forEach(f => {
        const sev = f.severity || 'major';
        severityCounts[sev] = (severityCounts[sev] || 0) + 1;
      });
      const totalViols = Object.values(severityCounts).reduce((a, b) => a + b, 0);
      if (totalViols > 0) {
        const sevColors = { critical: 'bg-red-500', major: 'bg-orange-500', minor: 'bg-yellow-400' };
        const sevLabels = { critical: '严重', major: '主要', minor: '轻微' };
        const sevTextColors = { critical: 'text-red-700', major: 'text-orange-700', minor: 'text-yellow-700' };
        const sevGrid = ['critical', 'major', 'minor'].map(sev => {
          const count = severityCounts[sev] || 0;
          const pct = totalViols > 0 ? (count / totalViols * 100).toFixed(0) : 0;
          return '<div class="card p-2 text-center">' +
            '<div class="text-lg font-bold ' + (sevTextColors[sev] || 'text-gray-600') + '">' + count + '</div>' +
            '<div class="text-xs text-gray-400">' + (sevLabels[sev] || sev) + '</div>' +
            '<div class="w-full bg-gray-100 rounded-full h-1.5 mt-1"><div class="' + (sevColors[sev] || 'bg-gray-400') + ' h-1.5 rounded-full" style="width:' + pct + '%"></div></div>' +
            '</div>';
        });
        details.innerHTML += '<div class="grid grid-cols-3 gap-2 mb-3">' + sevGrid.join('') + '</div>';
      }

      let violations: ReviewFinding[] = [];
      if (Array.isArray(result.findings)) {
        violations = (result.findings as ReviewFinding[]).filter(f => f.result === 'FAIL' && !f.is_duplicate);
      } else {
        violations = (result.details || []) as ReviewFinding[];
      }

      window._reviewViolations = violations;
      window._reviewThermalViolations = violations.filter(f => f.func_id && String(f.func_id).startsWith('THERM-'));
      window._reviewStructuralViolations = violations.filter(f => f.func_id && String(f.func_id).startsWith('STR-'));
      window._reviewThermalSummary = null;
      renderThermalViolations(window._reviewThermalViolations);
      renderStructuralViolations(window._reviewStructuralViolations);
      window._reviewPageSize = 15;
      window._reviewPage = 1;
      window._reviewFilter = 'all';
      window._reviewSearch = '';

      window.renderViolationPage = renderViolationPage;

      // 清除上一次审查残留的汇总卡/热力图
      while (details.previousElementSibling &&
             (details.previousElementSibling.classList.contains('card') ||
              details.previousElementSibling.classList.contains('heatmap-wrap'))) {
        details.previousElementSibling.remove();
      }

      const thermalSummaryHtml = renderThermalSummary(violations);
      const summaryHtml = renderEvacCorridorSummary(violations) + renderStructuralSummary(violations) + thermalSummaryHtml;
      if (summaryHtml) {
        document.getElementById('review-details').insertAdjacentHTML('beforebegin', summaryHtml);
      }
      const heatHtml = renderViolationHeatmap(violations);
      if (heatHtml) {
        document.getElementById('review-details').insertAdjacentHTML('beforebegin', heatHtml);
      }

      if (violations.length > 0) {
        renderViolationPage();

        if (result.status === 'success') {
          const reviewResult = {
            id: 'review_' + Date.now(),
            drawingName: drawing.filename,
            buildingType: bt,
            reviewedAt: new Date().toISOString(),
            summary: result.summary || {},
            details: result.details || result.findings || [],
            corrections: result.corrections || [],
            elements: result.elements || [],
            rawResult: result,
            drawingEntry: drawing,
          };
          reviewResults.unshift(reviewResult);
          try { localStorage.setItem('baa_review_results', JSON.stringify(reviewResults.slice(0, 50))); } catch (_e) {}

          const corrPanel = document.getElementById('review-correction-panel');
          if (corrPanel) corrPanel.className = corrPanel.className.replace(/\bhidden\b/g, '').trim();

          const loadedCorrs = (result.corrections || []) as ReviewCorrection[];
          if (loadedCorrs.length > 0) {
            const resultsDiv = document.getElementById('correction-results');
            const sorted = loadedCorrs.slice().sort((a, b) => {
              const order = { high: 0, medium: 1, low: 2 };
              return (order[a.priority] ?? 3) - (order[b.priority] ?? 3);
            });
            let html = '<p class="mb-1 text-gray-500">共 ' + sorted.length + ' 条建议（规则引擎自动生成）</p>';
            for (const s of sorted) {
              const pColor = s.priority === 'high' ? 'red' : s.priority === 'medium' ? 'orange' : 'yellow';
              const pLabel = s.priority === 'high' ? '🔴 高' : s.priority === 'medium' ? '🟠 中' : '🟡 低';
              html += '<div class="p-1.5 bg-gray-50 rounded border-l-2 border-' + pColor + '-400 mb-1">';
              html += '<p class="font-medium"><span class="text-' + pColor + '-600">' + pLabel + '</span> [' + s.clause_id + '] ' + (s.description || s.clause_title || '') + '</p>';
              if (s.recommendation) html += '<p class="text-gray-600 mt-0.5">💡 ' + s.recommendation + '</p>';
              if (s.action) html += '<p class="text-xs text-gray-400 mt-0.5">操作: ' + s.action + ' · 实测: ' + (s.current_value != null ? Number(s.current_value).toFixed(2) : '-') + ' → 要求: ' + (s.required_value != null ? Number(s.required_value).toFixed(2) : '-') + '</p>';
              if (Object.keys(s.parameters || {}).length > 0) {
                html += '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(s.parameters) + '</p>';
              }
              html += '</div>';
            }
            resultsDiv.innerHTML = html;
          } else {
            const resultsDiv = document.getElementById('correction-results');
            resultsDiv.innerHTML = '<p class="text-gray-400">✅ 无违规，无需修正建议</p>';
          }
        }
      } else {
        renderViolationPage();
      }
    } else {
      summary.innerHTML = '<span class="text-red-500">' + (result.message || '审查失败') + '</span>';
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    if (loading) {
      loading.innerHTML = '❌ 审查失败: ' + msg;
      loading.className = 'mt-3 text-sm text-red-500';
    }
  }
}

// ── 违规分页渲染 ──────────────────────────────────────────
export function renderViolationPage() {
  const v = (window._reviewViolations || []) as ReviewFinding[];
  const pageSize = window._reviewPageSize || 15;
  const page = window._reviewPage || 1;
  const filter = window._reviewFilter || 'all';
  const search = (window._reviewSearch || '').toLowerCase();

  let filtered: ReviewFinding[] = v;
  if (filter === 'critical') filtered = filtered.filter(f => f.severity === 'critical');
  else if (filter === 'major') filtered = filtered.filter(f => f.severity === 'major');
  else if (filter === 'minor') filtered = filtered.filter(f => f.severity !== 'critical' && f.severity !== 'major');
  else if (filter !== 'all') filtered = filtered.filter(f => (f.clause_id || '') === filter);
  if (search) filtered = filtered.filter(f =>
    (f.clause_title || '').toLowerCase().includes(search) ||
    (f.clause_id || '').toLowerCase().includes(search) ||
    (f.entity_type || '').toLowerCase().includes(search)
  );

  const confFilter = window._reviewConfFilter || 'all';
  if (confFilter !== 'all') {
    filtered = filtered.filter(f => {
      const c = f.confidence != null ? f.confidence : 1.0;
      if (confFilter === 'high') return c >= 0.85;
      if (confFilter === 'medium') return c >= 0.6 && c < 0.85;
      if (confFilter === 'low') return c < 0.6;
      return true;
    });
  }
  if (confFilter !== 'all') {
    filtered.sort((a, b) => {
      const ca = a.confidence != null ? a.confidence : 1.0;
      const cb = b.confidence != null ? b.confidence : 1.0;
      return ca - cb;
    });
  }

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const start = (page - 1) * pageSize;
  const pageItems = filtered.slice(start, start + pageSize);

  const selVals = { all: '全部', critical: '严重', major: '主要', minor: '轻微' };
  let filterOpts = Object.entries(selVals).map(([k, v2]) => '<option value="' + k + '"' + (filter === k ? ' selected' : '') + '>' + v2 + '</option>').join('');
  const confSelVals = { all: '全部置信度', high: '确认违规(≥85%)', medium: '疑似违规(60-85%)', low: '建议复核(<60%)' };
  const confFilterOpts = Object.entries(confSelVals).map(([k, v2]) => '<option value="' + k + '"' + (confFilter === k ? ' selected' : '') + '>' + v2 + '</option>').join('');

  const clauseGroups: Record<string, number> = {};
  v.forEach(f => {
    const cid = f.clause_id || '未知';
    if (!clauseGroups[cid]) clauseGroups[cid] = 0;
    clauseGroups[cid]++;
  });
  const sortedClauses = Object.entries(clauseGroups).sort((a, b) => b[1] - a[1]);

  let html = '<div class="flex items-center justify-between mb-2">' +
    '<p class="font-medium text-red-600">违规详情 (' + filtered.length + '/' + v.length + '项)</p>' +
    '<div class="flex gap-1 text-xs">' +
    '<select id="violation-filter" onchange="window._reviewFilter=this.value; window._reviewPage=1; renderViolationPage()" class="border rounded px-1 py-0.5 text-xs">' + filterOpts + '</select>' +
    '<select id="violation-conf-filter" onchange="window._reviewConfFilter=this.value; window._reviewPage=1; renderViolationPage()" class="border rounded px-1 py-0.5 text-xs">' + confFilterOpts + '</select>' +
    '<input id="violation-search" placeholder="搜索..." class="border rounded px-1 py-0.5 text-xs w-20" value="' + (window._reviewSearch || '') + '" oninput="window._reviewSearch=this.value; window._reviewPage=1; renderViolationPage()" />' +
    '</div></div>' +
    '<div class="flex flex-wrap gap-1 mb-2">' +
    sortedClauses.slice(0, 12).map(([cid, cnt]) =>
      '<span class="px-2 py-0.5 rounded text-xs cursor-pointer ' + (filter === cid ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200') + '" onclick="window._reviewFilter=\'' + cid + '\'; window._reviewPage=1; renderViolationPage()">' + cid + ' (' + cnt + ')</span>'
    ).join('') +
    '</div>';

  if (pageItems.length === 0) {
    html += '<div class="text-xs text-gray-400 p-2">无匹配项</div>';
  } else {
    pageItems.forEach(f => {
      const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
      const sevLabel = f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微';
      const conf = f.confidence != null ? f.confidence : 1.0;
      const confPct = Math.round(conf * 100);
      const confColor = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'red';
      const confLabel = f.confidence_tier === 'confirmed' ? '确认违规' : f.confidence_tier === 'suspected' ? '疑似违规' : '建议复核';
      const corrKey = (f.clause_id || f.func_id || '').trim();
      const corrs = (window._currentReviewResult && window._currentReviewResult.corrections || [])
        .filter((c: ReviewCorrection) => c.clause_id === corrKey);
      const hasCorr = corrs.length > 0;

      html +=
        '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs mb-1.5">' +
        '<div class="flex justify-between items-start">' +
        '<div><span class="font-medium">' + (f.clause_title || '') + '</span> <span class="text-gray-400">(' + (f.func_id || f.clause_id || '') + ')</span></div>' +
        '<div class="flex gap-1">' +
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span>' +
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + confColor + '-100 text-' + confColor + '-700" title="置信度 ' + confPct + '%">' + confLabel + '</span>' +
        '<span class="text-' + sevColor + '-600 font-medium">' + (f.result || '') + '</span></div></div>' +
        '<span class="text-gray-500">' + (f.entity_type || '') + ' · 实测: ' + (f.extracted_value != null ? Number(f.extracted_value).toFixed(2) : '-') + ' · 要求: ' + (f.required_value != null ? Number(f.required_value).toFixed(2) : '-') + '</span><br/>' +
        '<div class="mt-1"><div class="w-full bg-gray-200 rounded-full h-1"><div class="' + confColor + '-500 h-1 rounded-full" style="width:' + confPct + '%"></div></div></div>' +
        '<span class="text-gray-400">' + (f.explanation || '') + '</span>';

      if (hasCorr) {
        const top = corrs[0] as ReviewCorrection;
        const pColor = top.priority === 'high' ? 'red' : top.priority === 'medium' ? 'orange' : 'yellow';
        const pLabel = top.priority === 'high' ? '🔴 高' : top.priority === 'medium' ? '🟠 中' : '🟡 低';
        html += '<details class="mt-1"><summary class="cursor-pointer text-purple-600 font-medium">💡 修正建议 (' + corrs.length + '条)</summary>';
        html += '<div class="mt-0.5 p-1 bg-' + pColor + '-50 rounded border-l-2 border-' + pColor + '-400">';
        html += '<p class="text-xs"><span class="text-' + pColor + '-600">' + pLabel + '</span> ' + top.recommendation + '</p>';
        if (Object.keys(top.parameters || {}).length > 0) {
          html += '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(top.parameters) + '</p>';
        }
        html += '</div></details>';
      }

      if (window._reviewAuditMapping) {
        const detailList = (window._reviewAuditDetailList || []) as ReviewFinding[];
        const auditMapping = window._reviewAuditMapping as { reviewId: string };
        const reviewId = auditMapping.reviewId;
        const fid = f.func_id || f.clause_id || '';
        const eid = f.entity_id || '';
        let auditItemId: string | null = null;
        for (let i = 0; i < detailList.length; i++) {
          const d = detailList[i];
          const dfid = d.func_id || d.clause_id || '';
          const deid = d.entity_id || '';
          if (dfid === fid && deid === eid) { auditItemId = reviewId + ':' + i; break; }
        }
        const auditState = (window._reviewAuditStates && window._reviewAuditStates[auditItemId]) || 'unreviewed';
        html += renderAuditButtons(auditItemId, auditState, fid);
      }
      html += '</div>';
    });
  }

  if (totalPages > 1) {
    html += '<div class="flex items-center justify-center gap-2 mt-3 text-xs">';
    html += '<button onclick="window._reviewPage=Math.max(1,' + (page - 1) + ');renderViolationPage()" class="px-2 py-1 border rounded hover:bg-gray-100" ' + (page <= 1 ? 'disabled' : '') + '>‹</button>';
    for (let p = Math.max(1, page - 2); p <= Math.min(totalPages, page + 2); p++) {
      html += '<button onclick="window._reviewPage=' + p + ';renderViolationPage()" class="px-2 py-1 border rounded ' + (p === page ? 'bg-blue-100 text-blue-700' : 'hover:bg-gray-100') + '">' + p + '</button>';
    }
    html += '<button onclick="window._reviewPage=Math.min(' + totalPages + ',' + (page + 1) + ');renderViolationPage()" class="px-2 py-1 border rounded hover:bg-gray-100" ' + (page >= totalPages ? 'disabled' : '') + '>›</button>';
    html += '<span class="text-gray-400">' + page + '/' + totalPages + '</span>';
    html += '</div>';
  }

  const target = document.getElementById('review-details');
  if (target) target.innerHTML = html;
}

// ── 热工材料参数 ──────────────────────────────────────────
export const climateNames: Record<string, string> = {
  severe_cold: '严寒', cold: '寒冷', hot_cold: '夏热冬冷', hot_warm: '夏热冬暖',
};

export const THERMAL_MATERIALS: Record<string, { name: string; lambda: number; density: number }> = {
  rockwool: { name: '岩棉板', lambda: 0.035, density: 800 },
  eps: { name: 'EPS聚苯板', lambda: 0.040, density: 20 },
  xps: { name: 'XPS挤塑板', lambda: 0.030, density: 35 },
  pu: { name: '聚氨酯', lambda: 0.024, density: 40 },
  aerogel: { name: '气凝胶', lambda: 0.012, density: 120 },
};

export const THERMAL_THRESHOLDS: Record<string, { exterior_wall: number; roof: number; ground_floor: number; exterior_window: number }> = {
  severe_cold: { exterior_wall: 0.45, roof: 0.35, ground_floor: 0.30, exterior_window: 2.0 },
  cold: { exterior_wall: 0.60, roof: 0.50, ground_floor: 0.45, exterior_window: 2.4 },
  hot_cold: { exterior_wall: 1.50, roof: 1.20, ground_floor: 0.60, exterior_window: 3.2 },
  hot_warm: { exterior_wall: 2.00, roof: 1.50, ground_floor: 0.80, exterior_window: 4.0 },
};

export const HI = 8.7;
export const HO = 23.0;

export const DEFAULT_THERMAL_THICKNESS: Record<string, number> = {
  exterior_wall: 50, roof: 60, ground_floor: 80, exterior_window: 30,
};

// ═══════════════════════════════════════════════════════════
// Part1: review 选项卡 + 批量审查 + 对比可视化
// Source: baa-review.js 行 698-997
// ═══════════════════════════════════════════════════════════

export function switchReviewTab(tab: string): void {
  document.getElementById('review-tab-single').className = tab === 'single'
    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-700'
    : 'px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600';
  document.getElementById('review-tab-batch').className = tab === 'batch'
    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-700'
    : 'px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600';
  document.getElementById('review-tab-multisheet').className = tab === 'multisheet'
    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-700'
    : 'px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600';
  document.getElementById('review-tab-feedback').className = tab === 'feedback'
    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-700'
    : 'px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600';
  document.getElementById('review-tab-thermal').className = tab === 'thermal'
    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-700'
    : 'px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600';
  document.getElementById('review-tab-structural').className = tab === 'structural'
    ? 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-700'
    : 'px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600';
  document.getElementById('review-panel-single').className = tab === 'single' ? '' : 'hidden';
  document.getElementById('review-panel-batch').className = tab === 'batch' ? '' : 'hidden';
  document.getElementById('review-panel-multisheet').className = tab === 'multisheet' ? '' : 'hidden';
  document.getElementById('review-panel-feedback').className = tab === 'feedback' ? '' : 'hidden';
  document.getElementById('review-panel-thermal').className = tab === 'thermal' ? '' : 'hidden';
  document.getElementById('review-panel-structural').className = tab === 'structural' ? '' : 'hidden';
  if (tab === 'feedback') {
    loadFeedbackStats();
    loadFeedbacks();
  }
  if (tab === 'structural') {
    renderStructuralThresholds();
    renderStructuralViolations((window as unknown as { _reviewStructuralViolations?: unknown[] })._reviewStructuralViolations || []);
  }
  if (tab === 'thermal') {
    renderThermalViolations((window as unknown as { _reviewThermalViolations?: unknown[] })._reviewThermalViolations || []);
  }
  (window as unknown as { switchReviewTab?: (t: string) => void }).switchReviewTab = switchReviewTab;
}

let batchFiles: File[] = [];

export function onBatchFilesSelected(e: Event): void {
  const target = e.target as HTMLInputElement;
  const files = Array.from(target.files || []);
  batchFiles = files;
  const list = document.getElementById('batch-file-list');
  if (files.length === 0) {
    list.textContent = '';
    return;
  }
  list.innerHTML = files.map(f => `<div>📄 ${f.name} (${(f.size/1024/1024).toFixed(2)}MB)</div>`).join('');
}

document.getElementById('batch-file-input')?.addEventListener('change', onBatchFilesSelected);

// ── P10 反馈申诉 ──────────────────────────────────────────
export async function runBatchReview(): Promise<void> {
  if (batchFiles.length === 0) {
    showToast('请先选择至少一个图纸文件', 'info');
    return;
  }

  const btn = document.getElementById('batch-review-start-btn') as HTMLButtonElement;
  const loading = document.getElementById('batch-review-loading');
  const summary = document.getElementById('batch-review-summary');
  const details = document.getElementById('batch-review-details');

  btn.disabled = true;
  loading.classList.remove('hidden');
  loading.textContent = '⏳ 正在批量审查...';
  summary.innerHTML = '';
  details.innerHTML = '';

  const formData = new FormData();
  batchFiles.forEach(f => formData.append('files', f));

  try {
    const r = await fetch(API_BASE() + '/batch-review', {
      method: 'POST',
      headers: getHeaders(),
      body: formData,
    });
    const resp = await r.json();

    if (!r.ok) {
      const err = resp.detail || resp;
      throw new Error((err as { message?: string }).message || '审查失败');
    }

    if (resp.status !== 'success') throw new Error(resp.message || '审查失败');

    const bs = resp.batch_summary;
    summary.innerHTML = `
      <div class="grid grid-cols-2 gap-2 mb-2">
        <div class="card p-2 text-xs">
          <p class="font-medium">📁 文件统计</p>
          <p>总数: ${bs.total_files} | ✅成功: ${bs.success_files} | ❌失败: ${bs.failed_files}</p>
        </div>
        <div class="card p-2 text-xs">
          <p class="font-medium">📊 审查统计</p>
          <p>实体: ${bs.total_entities} | 检查: ${bs.total_checks.toLocaleString()} | 违规: ${bs.total_violations}</p>
          <p>耗时: ${(bs.processing_time_ms/1000).toFixed(1)}s</p>
        </div>
      </div>
    `;

    // 跨文件交叉分析
    if (resp.cross_analysis && resp.cross_analysis.length > 0) {
      let crossHtml = '<div class="card p-2 text-xs mb-2">';
      crossHtml += '<p class="font-medium text-sm mb-1">🔗 跨文件违规交叉分析</p>';
      crossHtml += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
        '<th class="pb-1 pr-1">规范条款</th><th class="pb-1 pr-1">违规数</th><th class="pb-1 pr-1">涉及图纸</th></tr></thead><tbody>';
      resp.cross_analysis.slice(0, 8).forEach((c: { clause_id: string; violations: number; files: number; file_names: string[] }) => {
        crossHtml += '<tr class="border-b border-gray-50">' +
          '<td class="py-1 pr-1">' + c.clause_id + '</td>' +
          '<td class="py-1 pr-1">' + c.violations + '</td>' +
          '<td class="py-1 pr-1">' + c.files + ' 张</td>' +
          '<td class="py-1 text-gray-400 truncate max-w-20">' + c.file_names.join(', ') + '</td>' +
          '</tr>';
      });
      crossHtml += '</tbody></table></div>';
      details.innerHTML = crossHtml + details.innerHTML;
    }

    // ── 各文件违规详情（卡片式） ──
    let fileHtml = '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">';
    (resp.results || []).forEach((r: any) => {
      if (r.status === 'error') {
        fileHtml += '<div class="card p-2 text-xs border-l-2 border-red-500 bg-red-50">' +
          '<p class="font-medium text-red-600">❌ ' + escHtml(r.filename || '') + '</p>' +
          '<p class="text-gray-500">' + escHtml(r.message || '') + '</p></div>';
        return;
      }
      const s = r.summary;
      const isClean = s.violations === 0;
      const sevColor = isClean ? 'green' : (s.violations >= 20 ? 'red' : 'orange');
      const safeFilename = escHtml(r.filename || '');
      const total = s.total_checks || 0;
      const passRate = total > 0 ? Math.round((1 - s.violations / total) * 100) : 100;

      const sevCount = { critical: 0, major: 0, minor: 0 };
      (r.details || []).forEach((v: { severity?: string }) => {
        const sv = v.severity || 'major';
        if (sv in sevCount) sevCount[sv as keyof typeof sevCount]++;
      });

      let bar = '<div class="mt-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">' +
        '<div class="' + sevColor + '-500 h-full rounded-full" style="width:' + passRate + '%"></div></div>' +
        '<div class="flex justify-between text-[10px] text-gray-400 mt-0.5">' +
        '<span>通过率 ' + passRate + '%</span><span>检查 ' + total.toLocaleString() + '</span></div>';

      let badges = '';
      if (sevCount.critical > 0) badges += '<span class="px-1 rounded bg-red-100 text-red-700 text-[10px]">● ' + sevCount.critical + ' 严重</span>';
      if (sevCount.major > 0) badges += '<span class="px-1 rounded bg-orange-100 text-orange-700 text-[10px]">● ' + sevCount.major + ' 主要</span>';
      if (sevCount.minor > 0) badges += '<span class="px-1 rounded bg-yellow-100 text-yellow-700 text-[10px]">● ' + sevCount.minor + ' 轻微</span>';
      if (!badges) badges = '<span class="px-1 rounded bg-green-100 text-green-700 text-[10px]">✓ 无违规</span>';

      fileHtml += '<div class="card p-2 text-xs border-l-2 border-' + sevColor + '-500">' +
        '<div class="flex items-center justify-between mb-1">' +
        '<p class="font-medium truncate" title="' + safeFilename + '">' + safeFilename + '</p>' +
        '<span class="text-' + sevColor + '-600 font-medium text-sm">' + (isClean ? '✓' : s.violations) + '</span>' +
        '</div>' +
        '<p class="text-gray-500 text-[10px]">' + s.total_entities + ' 实体 · ' + (r.buildingType === 'civil' ? '民用' : '工业') + '</p>' +
        bar +
        '<div class="mt-1 flex flex-wrap gap-0.5">' + badges + '</div>' +
        (s.violation_by_clause ? '<p class="text-[10px] text-gray-400 mt-1">' +
          '主要: ' + Object.entries(s.violation_by_clause).slice(0, 3).map(([k, v]) => k + '(' + v + ')').join(', ') + '</p>' : '') +
        '</div>';
    });
    fileHtml += '</div>';
    details.innerHTML += fileHtml;

    loading.classList.add('hidden');
  } catch (err: unknown) {
    loading.textContent = '❌ ' + (err as Error).message;
    loading.className = 'mt-3 text-sm text-red-500';
  } finally {
    btn.disabled = false;
  }
}

// ── 审查结果对比 Diff ──────────────────────────────────────
let _diffResult: unknown = null;

// 监听文件选择
// 加载对比图纸可视化（违规叠加渲染）
// ── PDF 下载 ──────────────────────────────────────────────
// ── P91: 结构化导出 (JSON/CSV) ────────────────────────────
// ── JSON 导出 ──────────────────────────────────────────────
// ── 审查结果存储（localStorage + 后端持久化） ──────────
// reviewResults 全局变量由 baa-admin.js 定义（var reviewResults = []）
// 违规可视化渲染（SVG/Canvas叠加）
export function renderViolationOverlay(r: unknown): void {
  const canvas = document.getElementById('compare-overlay-canvas') as HTMLCanvasElement | null;
  const visEmpty = document.getElementById('compare-vis-empty');
  if (!canvas) return;

  const ri = r as { details?: { entity_type?: string; severity?: string; clause_id?: string; clause_title?: string }[]; corrections?: unknown[]; elements?: unknown[]; rawResult?: { elements?: unknown[] } };
  const viols = ri.details || [];
  const corrs = ri.corrections || [];
  const elements = ri.elements || ri.rawResult?.elements || [];

  // 没有位置数据时显示占位
  const hasPosData = elements.length > 0 || viols.some((v: { entity_type?: string }) => v.entity_type);
  if (!hasPosData) {
    visEmpty.className = 'absolute inset-0 flex items-center justify-center text-gray-400 text-sm';
    canvas.style.display = 'none';
    return;
  }
  visEmpty.className = 'hidden';
  canvas.style.display = 'block';

  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  // 背景
  ctx.fillStyle = '#f8f9fa';
  ctx.fillRect(0, 0, W, H);

  // 收集违规实体类型及其严重度
  const violTypes: Record<string, string> = {};
  const violClauses: Record<string, string[]> = {};
  viols.forEach((v: { entity_type?: string; severity?: string; clause_id?: string; clause_title?: string }) => {
    const et = v.entity_type || 'unknown';
    const severity = v.severity || 'major';
    if (!violTypes[et] || violTypes[et] === 'major') violTypes[et] = severity;
    if (!violClauses[et]) violClauses[et] = [];
    violClauses[et].push(v.clause_id + ': ' + (v.clause_title || ''));
  });

  // 实体类型 → 颜色/位置映射
  const entityColors: Record<string, string> = {
    'staircase': '#ef4444', 'stair': '#ef4444',
    'corridor': '#f97316', 'aisle': '#f97316',
    'fire_door': '#ef4444', 'door': '#f59e0b',
    'fire_lane': '#ef4444', 'road': '#ef4444',
    'fire_zone': '#f97316', 'room': '#22c55e',
    'exit': '#ef4444', 'exit_door': '#ef4444',
    'fire_window': '#f97316', 'window': '#3b82f6',
    'refuge_floor': '#ef4444',
    'exit_sign': '#f59e0b', 'sign': '#f59e0b',
    'sprinkler_system': '#f97316',
    'fire_alarm': '#f97316',
    'shaft': '#f59e0b',
    'insulation': '#f97316',
    'evacuation_lighting': '#f59e0b',
    'wall': '#6b7280',
  };

  const allTypes = [...new Set([...viols.map((v: { entity_type?: string }) => v.entity_type || 'unknown'), ...elements.map((e: { type?: string; entity_type?: string }) => e.type || e.entity_type || '')].filter(Boolean))];

  if (allTypes.length === 0) {
    ctx.fillStyle = '#999';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('无实体位置数据', W / 2, H / 2);
    return;
  }

  const cols = Math.min(4, Math.ceil(Math.sqrt(allTypes.length)));
  const rows = Math.ceil(allTypes.length / cols);
  const cellW = (W - 60) / cols;
  const cellH = (H - 60) / rows;

  type CircleData = {
    x: number; y: number; r: number; type: string; color: string;
    severity: string; isViolated: boolean; hints: string[];
  };
  const circles: CircleData[] = [];

  allTypes.forEach((t: string, i: number) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cx = 30 + col * cellW + cellW / 2;
    const cy = 30 + row * cellH + cellH / 2;
    const radius = Math.min(cellW, cellH) * 0.3;

    const color = entityColors[t] || '#6b7280';
    const severity = violTypes[t] || 'none';
    const isViolated = violTypes[t] !== undefined;

    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.fillStyle = isViolated ? (severity === 'critical' ? '#fecaca' : '#fed7aa') : '#dcfce7';
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = isViolated ? 3 : 1.5;
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = t.length > 12 ? t.slice(0, 10) + '..' : t;
    ctx.fillText(label, cx, cy);

    if (isViolated) {
      ctx.fillStyle = color;
      ctx.font = 'bold 8px sans-serif';
      ctx.fillText('✗', cx + radius + 8, cy - radius);
    }

    const hints = violClauses[t];
    if (hints && hints.length > 0) {
      ctx.fillStyle = '#6b7280';
      ctx.font = '7px sans-serif';
      ctx.textAlign = 'center';
      hints.slice(0, 2).forEach((h, hi) => {
        ctx.fillText(h.length > 20 ? h.slice(0, 18) + '..' : h, cx, cy + 12 + hi * 10);
      });
    }

    circles.push({
      x: cx, y: cy, r: radius,
      type: t, color: color,
      severity: severity,
      isViolated: isViolated,
      hints: hints || []
    });
  });

  // ── 鼠标悬停 Tooltip ──
  let tip = document.getElementById('compare-vis-tooltip');
  if (!tip) {
    const t = document.createElement('div');
    t.id = 'compare-vis-tooltip';
    t.className = 'fixed hidden bg-black bg-opacity-90 text-white text-xs rounded-lg p-2 pointer-events-none z-50 max-w-xs shadow-lg';
    document.body.appendChild(t);
    tip = t;
  }

  type CanvasExt = HTMLCanvasElement & {
    __circles?: CircleData[]; __tooltip?: HTMLElement;
    __onMove?: (e: MouseEvent) => void; __onLeave?: () => void;
  };
  const canvasExt = canvas as CanvasExt;
  canvasExt.__circles = circles;
  canvasExt.__tooltip = tip;

  if (canvasExt.__onMove) canvas.removeEventListener('mousemove', canvasExt.__onMove);
  if (canvasExt.__onLeave) canvas.removeEventListener('mouseleave', canvasExt.__onLeave);

  canvasExt.__onMove = function(e: MouseEvent) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    let hit: CircleData | null = null;
    let hitDist = Infinity;
    circles.forEach(c => {
      const d = Math.hypot(mx - c.x, my - c.y);
      if (d < c.r * 1.3 && d < hitDist) { hit = c; hitDist = d; }
    });
    if (!hit) { tip.classList.add('hidden'); return; }
    const sevText = hit.severity === 'critical' ? '严重' : hit.severity === 'major' ? '主要' : '轻微';
    let html = '<div class="font-medium mb-1">' + hit.type + (hit.isViolated ? ' ✗' : ' ✓') + '</div>';
    if (hit.isViolated) {
      html += '<div class="mb-1"><span class="text-' + (hit.severity === 'critical' ? 'red' : hit.severity === 'major' ? 'orange' : 'yellow') + '-400">● ' + sevText + '</span></div>';
      if (hit.hints.length > 0) {
        html += '<div class="text-gray-300 text-[10px]">' + hit.hints.slice(0, 4).join('<br>') + '</div>';
        if (hit.hints.length > 4) html += '<div class="text-gray-500 text-[10px]">… 还有 ' + (hit.hints.length - 4) + ' 条</div>';
      }
    } else {
      html += '<div class="text-gray-400 text-[10px]">无违规</div>';
    }
    tip.innerHTML = html;
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY + 12) + 'px';
    tip.classList.remove('hidden');
  };

  canvasExt.__onLeave = function() { tip.classList.add('hidden'); };

  canvas.addEventListener('mousemove', canvasExt.__onMove);
  canvas.addEventListener('mouseleave', canvasExt.__onLeave);
}

// 渲染修正后预览文本
export function renderAfterPreview(r: unknown): void {
  const div = document.getElementById('compare-after-preview');
  type Corr = { priority?: string; action?: string; recommendation?: string; parameter?: string };
  const ri = r as { corrections?: Corr[]; details?: unknown[] };
  const corrs = ri.corrections || [];
  const viols = ri.details || [];

  if (corrs.length === 0 && viols.length === 0) {
    div.innerHTML = '<div class="text-gray-400">图纸合规，无需修正</div>';
    return;
  }

  const high = corrs.filter((c: Corr) => c.priority === 'high');
  const medium = corrs.filter((c: Corr) => c.priority === 'medium');
  const low = corrs.filter((c: Corr) => c.priority === 'low');

  let html = '<div class="space-y-1.5">';

  html += '<div class="flex gap-3 text-xs mb-2">' +
    '<span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-red-500"></span>高优先级: ' + high.length + '</span>' +
    '<span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>中优先级: ' + medium.length + '</span>' +
    '<span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-gray-500"></span>低优先级: ' + low.length + '</span>' +
    '</div>';

  if (high.length > 0) {
    html += '<div class="font-medium text-red-700 text-xs mt-2">🔴 必须修复</div>';
    high.forEach((c: Corr) => {
      html += '<div class="pl-3 border-l-2 border-red-400 mb-1">' +
        '<span class="font-medium">' + (c.action || '') + '</span>: ' + (c.recommendation || '') +
        (c.parameter ? ' <span class="text-gray-400">(参数: ' + c.parameter + ')</span>' : '') +
        '</div>';
    });
  }

  if (medium.length > 0) {
    html += '<div class="font-medium text-yellow-700 text-xs mt-2">🟡 建议整改</div>';
    medium.forEach((c: Corr) => {
      html += '<div class="pl-3 border-l-2 border-yellow-400 mb-1">' +
        '<span class="font-medium">' + (c.action || '') + '</span>: ' + (c.recommendation || '') +
        '</div>';
    });
  }

  if (low.length > 0) {
    html += '<div class="font-medium text-gray-600 text-xs mt-2">⚪ 可优化</div>';
    low.forEach((c: Corr) => {
      html += '<div class="pl-3 border-l-2 border-gray-400 mb-1">' +
        '<span class="font-medium">' + (c.action || '') + '</span>: ' + (c.recommendation || '') +
        '</div>';
    });
  }

  if (corrs.length === 0 && viols.length > 0) {
    html += '<div class="text-yellow-700">' +
      '发现 ' + viols.length + ' 项违规，修正引擎未生成具体建议。请参照规范要求手动调整。' +
      '</div>';
  }

  html += '</div>';
  div.innerHTML = html;
}

export function onCompareSelect(): void {
  const select = document.getElementById('compare-drawing-select') as HTMLSelectElement;
  const id = select.value;
  const empty = document.getElementById('compare-empty');
  const content = document.getElementById('compare-content');

  if (!id) {
    empty.className = 'card text-center py-8 text-gray-300';
    content.className = 'hidden';
    return;
  }

  const r = (reviewResults as Array<{ id?: string } & unknown>).find(x => x.id === id);
  if (!r) return;

  empty.className = 'hidden';
  content.className = '';

  const ri = r as {
    details?: { severity?: string; clause_title?: string; clause_id?: string; entity_type?: string;
      explanation?: string; result?: string; extracted_value?: number; required_value?: number }[];
    corrections?: { priority?: string; clause_title?: string; action?: string; recommendation?: string }[];
    summary?: { total_checks?: number };
    rawResult?: { elements?: unknown[] };
    elements?: unknown[];
    drawingEntry?: { raw?: unknown };
    id?: string;
  };
  const summaryDiv = document.getElementById('compare-summary');
  const viols = ri.details || [];
  const corrs = ri.corrections || [];
  const totalChecks = ri.summary?.total_checks || viols.length + 10;
  const passRate = totalChecks > 0 ? Math.round((1 - viols.length / totalChecks) * 100) : 0;
  const criticalCount = viols.filter((v: { severity?: string }) => v.severity === 'critical').length;
  const majorCount = viols.filter((v: { severity?: string }) => v.severity === 'major').length;
  const entityCount = ri.rawResult?.elements?.length || ri.elements?.length || 0;

  summaryDiv.innerHTML = '' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold ' + (passRate > 80 ? 'text-green-600' : passRate > 50 ? 'text-yellow-600' : 'text-red-600') + '">' + passRate + '%</div>' +
      '<div class="text-xs text-gray-400">合规率</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-red-600">' + viols.length + '</div>' +
      '<div class="text-xs text-gray-400">违规项 (严重' + criticalCount + ')</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-blue-600">' + corrs.length + '</div>' +
      '<div class="text-xs text-gray-400">修正建议</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-gray-600">' + entityCount + '</div>' +
      '<div class="text-xs text-gray-400">检测实体</div>' +
    '</div>';

  // 原始图纸解析JSON
  const originalJson = document.getElementById('compare-original-json');
  if (ri.drawingEntry?.raw) {
    originalJson.textContent = JSON.stringify(ri.drawingEntry.raw, null, 2);
  } else if (ri.elements && ri.elements.length > 0) {
    originalJson.textContent = JSON.stringify(ri.elements, null, 2);
  } else {
    originalJson.textContent = JSON.stringify(ri.rawResult, null, 2);
  }

  // 违规标注
  const violationsDiv = document.getElementById('compare-violations');
  violationsDiv.innerHTML = '';
  if (viols.length === 0) {
    violationsDiv.innerHTML = '<div class="text-xs text-green-600">✅ 图纸合规，无违规项</div>';
  } else {
    const severityOrder: Record<string, number> = { critical: 0, major: 1, minor: 2 };
    const sorted = [...viols].sort((a, b) => (severityOrder[a.severity || ''] || 2) - (severityOrder[b.severity || ''] || 2));

    // P122 XSS 防护：违规数据全部 escHtml 转义
    const parts: string[] = [];
    sorted.forEach((f: { severity?: string; clause_title?: string; clause_id?: string;
      entity_type?: string; explanation?: string; result?: string;
      extracted_value?: number; required_value?: number }) => {
      const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
      const sevLabel = f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微';
      const clauseTitle = escHtml(f.clause_title || '');
      const clauseId = escHtml(f.clause_id || '');
      const entityType = escHtml(f.entity_type || '');
      const explanation = escHtml(f.explanation || '');
      const result = escHtml(f.result || '');
      parts.push(
        '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs mb-1.5">' +
        '<div class="flex justify-between items-start">' +
        '<div><span class="font-medium">' + clauseTitle + '</span> <span class="text-gray-400">(' + clauseId + ')</span></div>' +
        '<div class="flex gap-1">' +
        '<span class="px-1 py-0.5 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span>' +
        '<span class="text-' + sevColor + '-600 font-medium">' + result + '</span></div></div>' +
        '<span class="text-gray-500">' + entityType + ' · 实测: ' + (f.extracted_value || 0).toFixed(2) + ' · 要求: ' + (f.required_value || 0) + '</span><br/>' +
        '<span class="text-gray-400">' + explanation + '</span>' +
        '</div>'
      );
    });
    violationsDiv.innerHTML = violationsDiv.innerHTML + parts.join('');
  }

  // 可视化叠加
  renderViolationOverlay(r);

  // 修正建议
  const corrDiv = document.getElementById('compare-corrections');
  corrDiv.innerHTML = '';
  if (corrs.length === 0) {
    corrDiv.innerHTML = '<div class="text-xs text-gray-400">无修正建议</div>';
  } else {
    const parts: string[] = [];
    corrs.slice(0, 10).forEach((c: { priority?: string; clause_title?: string; action?: string; recommendation?: string }, ci: number) => {
      const pColor = c.priority === 'high' ? 'red' : c.priority === 'medium' ? 'yellow' : 'gray';
      const pLabel = c.priority === 'high' ? '高优先级' : c.priority === 'medium' ? '中优先级' : '低优先级';
      const statusKey = 'corr_' + ri.id + '_' + ci;
      const savedStatus = localStorage.getItem(statusKey);
      const accepted = savedStatus === 'accepted';
      const rejected = savedStatus === 'rejected';
      const statusBadge = accepted ? '<span class="text-green-600 text-xs">✅ 已确认</span>' : rejected ? '<span class="text-red-400 text-xs">❌ 已拒绝</span>' : '';
      const safeClauseTitle = escHtml(c.clause_title || '');
      const safeAction = escHtml(c.action || '');
      const safeRecommendation = escHtml(c.recommendation || '');
      const safeReviewId = escHtml(ri.id || '');
      parts.push(
        '<div class="p-2 bg-green-50 rounded text-xs mb-1.5 ' + (rejected ? 'opacity-50' : '') + '">' +
        '<div class="flex justify-between items-start">' +
        '<div><span class="font-medium">' + safeClauseTitle + '</span> ' + statusBadge + '</div>' +
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + pColor + '-100 text-' + pColor + '-800">' + pLabel + '</span></div>' +
        '<div class="text-gray-500">操作: ' + safeAction + '</div>' +
        '<div class="text-gray-700 mt-1">' + safeRecommendation + '</div>' +
        '<div class="flex gap-1 mt-1.5">' +
        '<button onclick="confirmCorrection(\'' + safeReviewId + '\',' + ci + ',true)" class="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs hover:bg-green-200 ' + (accepted ? 'opacity-50' : '') + '" ' + (accepted ? 'disabled' : '') + '>✅ 确认</button>' +
        '<button onclick="confirmCorrection(\'' + safeReviewId + '\',' + ci + ',false)" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200 ' + (rejected ? 'opacity-50' : '') + '" ' + (rejected ? 'disabled' : '') + '>❌ 拒绝</button>' +
        '</div></div>'
      );
    });
    corrDiv.innerHTML = corrDiv.innerHTML + parts.join('');
  }

  // 修正后预览
  renderAfterPreview(r);
}

// ── AI 修正建议（P41） ───────────────────────────────────
// ── 修正建议交互 ──────────────────────────────────────────
// ── P119: 违规审核工作流 ──────────────────────────────────

(window as unknown as {
  switchReviewTab?: (t: string) => void;
  onBatchFilesSelected?: (e: Event) => void;
  runBatchReview?: () => Promise<void>;
  renderViolationOverlay?: (r: unknown) => void;
  renderAfterPreview?: (r: unknown) => void;
  onCompareSelect?: () => void;
}).switchReviewTab = switchReviewTab;
(window as unknown as {
  onBatchFilesSelected?: (e: Event) => void;
  runBatchReview?: () => Promise<void>;
  renderViolationOverlay?: (r: unknown) => void;
  renderAfterPreview?: (r: unknown) => void;
  onCompareSelect?: () => void;
}).onBatchFilesSelected = onBatchFilesSelected;
(window as unknown as {
  runBatchReview?: () => Promise<void>;
  renderViolationOverlay?: (r: unknown) => void;
  renderAfterPreview?: (r: unknown) => void;
  onCompareSelect?: () => void;
}).runBatchReview = runBatchReview;
(window as unknown as {
  renderViolationOverlay?: (r: unknown) => void;
  renderAfterPreview?: (r: unknown) => void;
  onCompareSelect?: () => void;
}).renderViolationOverlay = renderViolationOverlay;
(window as unknown as {
  renderAfterPreview?: (r: unknown) => void;
  onCompareSelect?: () => void;
}).renderAfterPreview = renderAfterPreview;
(window as unknown as {
  onCompareSelect?: () => void;
}).onCompareSelect = onCompareSelect;

// ── P119 审计初始化 ────────────────────────────────────────

export async function _initAuditItems(result: any): Promise<void> {
  const reviewId = result.queue_info?.task_id || result.task_id || '';
  if (!reviewId) return;

  const details = ((result.findings || []) as any[]).filter(f => f.result === 'FAIL' && !f.is_duplicate);
  if (details.length === 0) {
    window._reviewAuditMapping = {};
    return;
  }

  try {
    const url = (window as any).API_BASE?.() + '/api/v1/audit/items';
    const r = await fetch(url, {
      method: 'POST',
      headers: { ...(window as any).HEADERS?.() || {}, 'Content-Type': 'application/json' },
      body: JSON.stringify({ review_id: reviewId, details }),
    });
    if (r.ok) {
      const resp = await r.json();
      const mapping: Record<string, string> = {};
      details.forEach((d: any, i: number) => {
        const fid = d.func_id || d.clause_id || '';
        const eid = d.entity_id || '';
        mapping[fid + ':' + eid + ':' + i] = reviewId + ':' + i;
      });
      window._reviewAuditMapping = { mapping, reviewId };
      window._reviewAuditDetailList = details;
      await _loadAuditItemStates(reviewId);
    }
  } catch (err) {
    console.warn('[P119] 审计条目初始化失败:', (err as Error).message);
  }
}

export async function _loadAuditItemStates(reviewId: string): Promise<void> {
  try {
    const url = (window as any).API_BASE?.() + '/api/v1/audit/items?review_id=' + encodeURIComponent(reviewId);
    const r = await fetch(url, { headers: (window as any).HEADERS?.() || {} });
    if (r.ok) {
      const resp = await r.json();
      const states: Record<string, string> = {};
      (resp.items || []).forEach((item: any) => { states[item.id] = item.status; });
      window._reviewAuditStates = states;
    }
  } catch (err) {
    console.warn('[P119] 审计状态加载失败:', (err as Error).message);
  }
}

export function renderAuditButtons(itemId: string, itemStatus: string, clauseId: string): string {
  if (!itemId) return '';
  const safeClause = (window._escHtml || _escHtml)(clauseId || '');
  let html = '<div class="flex gap-1 mt-1"><span class="text-[10px] text-gray-400">审核:</span>';

  switch (itemStatus) {
    case 'confirmed':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✅ 已确认</span>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-red-100 hover:text-red-700">↩ 驳回</button>';
      break;
    case 'dismissed':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">❌ 已驳回</span>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700">↩ 确认</button>';
      break;
    case 'pending':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">⏳ 待核实</span>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      break;
    default:
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'pending\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200">⏳ 待核实</button>';
  }
  html += '</div>';
  return html;
}

export async function auditAction(itemId: string, action: string, clauseId: string): Promise<void> {
  const safeAction = (window._escHtml || _escHtml)(action || '');
  try {
    const body = action === 'dismiss' ? { reason: '人工驳回' } : {};
    const url = (window as any).API_BASE?.() + '/api/v1/audit/items/' + encodeURIComponent(itemId) + '/' + safeAction;
    const r = await fetch(url, {
      method: 'POST',
      headers: { ...(window as any).HEADERS?.() || {}, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json();
      showToast?.('操作失败: ' + (err.detail || r.statusText), 'error');
      return;
    }
    showToast?.((action === 'confirm' ? '✅ 已确认违规' : action === 'dismiss' ? '❌ 已驳回（误报）' : '⏳ 已标记待核实') + ' ' + (window._escHtml || _escHtml)(clauseId || ''), 'info');
    renderViolationPage?.();
  } catch (err) {
    showToast?.('网络错误: ' + (err as Error).message, 'error');
  }
}

// ── P45 多层热工编辑器 ────────────────────────────────────────

export function renderMultiLayerEditor(): void {
  const container = document.getElementById('multi-layer-editor');
  if (!container) return;
  container.innerHTML = '';
  let html = '<div class="text-xs text-gray-500 mb-2">从上到下添加保温层/结构层</div>';
  html += '<div id="multi-layer-rows" class="space-y-2 mb-2"></div>';
  html += '<div class="flex gap-2 mb-3">';
  html += '<button onclick="window.addMultiLayerRow()" class="px-3 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700">+ 添加层</button>';
  html += '<button onclick="window.computeMultiLayerK()" class="px-3 py-1 bg-orange-600 text-white text-xs rounded hover:bg-orange-700">计算 K 值</button>';
  html += '</div>';
  container.innerHTML = html;
  window.addMultiLayerRow('surface_inside', '内表面换热', 0.0, 'm²·K/W');
  window.addMultiLayerRow('insulation', '保温层', 0.05, 'm');
  window.addMultiLayerRow('structure', '结构层(混凝土)', 0.2, 'm');
  window.addMultiLayerRow('surface_outside', '外表面换热', 0.0, 'm²·K/W');
}

export function addMultiLayerRow(type?: string, name?: string, thickness?: number, unit?: string): void {
  const rows = document.getElementById('multi-layer-rows');
  if (!rows) return;
  const idx = rows.children.length;
  const defaultName = name || (type === 'surface_inside' ? '内表面换热' : type === 'surface_outside' ? '外表面换热' : '保温层');
  const defaultThick = thickness ?? (type === 'surface_inside' || type === 'surface_outside' ? 0 : 0.05);
  const defaultUnit = unit || (type === 'surface_inside' || type === 'surface_outside' ? 'm²·K/W' : 'm');
  const rowsHtml = '<div class="flex gap-2 items-center" data-idx="' + idx + '">' +
    '<select onchange="window.updateMultiLayerRow(' + idx + ',0,this.value)" class="text-xs border rounded px-1 py-0.5 flex-1">' +
    '<option value="surface_inside" ' + (type==='surface_inside'?'selected':'') + '>内表面换热</option>' +
    '<option value="surface_outside" ' + (type==='surface_outside'?'selected':'') + '>外表面换热</option>' +
    '<option value="eps" ' + (type==='eps'?'selected':'') + '>EPS聚苯板(λ=0.040)</option>' +
    '<option value="xps" ' + (type==='xps'?'selected':'') + '>XPS挤塑板(λ=0.030)</option>' +
    '<option value="rockwool" ' + (type==='rockwool'?'selected':'') + '>岩棉板(λ=0.035)</option>' +
    '<option value="pu" ' + (type==='pu'?'selected':'') + '>聚氨酯(λ=0.024)</option>' +
    '<option value="concrete" ' + (type==='concrete'?'selected':'') + '>混凝土(λ=1.74)</option>' +
    '<option value="brick" ' + (type==='brick'?'selected':'') + '>砖(λ=0.81)</option>' +
    '<option value="glass" ' + (type==='glass'?'selected':'') + '>玻璃(λ=0.8)</option>' +
    '<option value="steel" ' + (type==='steel'?'selected':'') + '>钢材(λ=50)</option>' +
    '</select>' +
    '<input type="number" step="0.01" value="' + defaultThick + '" onchange="window.updateMultiLayerRow(' + idx + ',1,this.value)" class="text-xs border rounded px-1 py-0.5 w-20" placeholder="厚度/热阻" />' +
    '<span class="text-xs text-gray-400 w-12">' + defaultUnit + '</span>' +
    '<button onclick="window.removeMultiLayerRow(' + idx + ')" class="px-1 text-red-500 text-xs hover:text-red-700">×</button>' +
    '</div>';
  rows.insertAdjacentHTML('beforeend', rowsHtml);
}

export function removeMultiLayerRow(idx: number): void {
  const rows = document.getElementById('multi-layer-rows');
  if (rows && rows.children.length > 1) {
    rows.children[idx].remove();
  }
}

export function updateMultiLayerRow(_idx: number, _field: number, _value: string): void {}

export function computeMultiLayerK(): void {
  const rows = document.getElementById('multi-layer-rows');
  if (!rows) return;
  const resultEl = document.getElementById('multi-layer-result');
  const materials: Record<string, number | null> = {
    eps: 0.040, xps: 0.030, rockwool: 0.035, pu: 0.024,
    concrete: 1.74, brick: 0.81, glass: 0.8, steel: 50,
    surface_inside: null, surface_outside: null,
  };

  let totalR = 0;
  const layerInfo: Array<{ type: string; thickness?: number; lambda?: number; R: number }> = [];
  const climate = (document.getElementById('thermal-climate') as HTMLSelectElement)?.value || 'severe_cold';
  const compType = (document.getElementById('thermal-comp-type') as HTMLSelectElement)?.value || 'exterior_wall';

  for (const row of rows.children) {
    const selects = row.querySelectorAll('select');
    const inputs = row.querySelectorAll('input[type=number]');
    if (selects.length === 0 || inputs.length === 0) continue;
    const matType = selects[0].value;
    const value = parseFloat(inputs[0].value) || 0;

    if (matType === 'surface_inside') {
      totalR += 1.0 / HI;
      layerInfo.push({ type: matType, R: 1/HI });
    } else if (matType === 'surface_outside') {
      totalR += 1.0 / HO;
      layerInfo.push({ type: matType, R: 1/HO });
    } else {
      const lambda = materials[matType] || 0.04;
      const R = value / lambda;
      totalR += R;
      layerInfo.push({ type: matType, thickness: value, lambda, R });
    }
  }

  const K = 1.0 / totalR;
  const threshold = THERMAL_THRESHOLDS[climate]?.[compType as keyof typeof THERMAL_THRESHOLDS["severe_cold"]] || THERMAL_THRESHOLDS.severe_cold.exterior_wall;
  const passed = K <= threshold;

  let detailHtml = '<table class="w-full border-collapse text-xs"><thead><tr class="bg-gray-100 border-b"><th class="py-1 text-left">层</th><th>厚度(m)</th><th>λ(W/m·K)</th><th>R(m²·K/W)</th></tr></thead><tbody>';
  layerInfo.forEach(l => {
    if (l.type === 'surface_inside') {
      detailHtml += '<tr><td>内表面换热</td><td>-</td><td>-</td><td>' + l.R.toFixed(4) + '</td></tr>';
    } else if (l.type === 'surface_outside') {
      detailHtml += '<tr><td>外表面换热</td><td>-</td><td>-</td><td>' + l.R.toFixed(4) + '</td></tr>';
    } else {
      detailHtml += '<tr><td>' + l.type + '</td><td>' + (l.thickness||'-') + '</td><td>' + (l.lambda||'-') + '</td><td>' + (l.R||0).toFixed(4) + '</td></tr>';
    }
  });
  detailHtml += '</tbody></table>';

  const html = '<div class="mt-3 p-2 rounded ' + (passed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200') + ' border">' +
    '<p class="font-medium ' + (passed ? 'text-green-700' : 'text-red-700') + '">' +
    'K = ' + K.toFixed(4) + ' W/(m²·K) · R_total = ' + totalR.toFixed(4) + ' m²·K/W ' +
    (passed ? '✅ ≤ ' + threshold : '❌ > ' + threshold) + '</p>' +
    '<p class="text-xs text-gray-500">气候: ' + climateNames[climate] + ' · 构件: ' + compType + '</p>' +
    '</div>' + detailHtml;

  if (resultEl) resultEl.innerHTML = html;
}

// ── P46 结构参数 ─────────────────────────────────────────────

export const STRUCTURAL_PARAMS: Record<string, { label: string; clause: string; unit: string; threshold: Record<string, number>; op: string }> = {
  floor_live: { label: '楼面活荷载', clause: 'GB50009-5.1.1', unit: 'kN/㎡', threshold: { '住宅': 2.0, '办公': 2.5, '商业': 3.5, '图书馆': 4.0, '档案': 5.0, '车库': 2.5 }, op: '>=' },
  beam_reinforcement: { label: '梁最小配筋率', clause: 'GB50010-9.2.1', unit: '%', threshold: { '默认': 0.20 }, op: '>=' },
  column_reinforcement: { label: '柱纵向配筋率下限', clause: 'GB50010-11.4.12', unit: '%', threshold: { '抗震一级': 0.55, '抗震二级': 0.50, '抗震三级': 0.55, '抗震四级': 0.50 }, op: '>=' },
  foundation_depth: { label: '基础最小埋深', clause: 'GB50007-5.1.3', unit: 'm', threshold: { '默认': 0.50, '冻土区': 1.00 }, op: '>=' },
  slab_thickness: { label: '楼板最小厚度', clause: 'GB50010-9.1.2', unit: 'mm', threshold: { '默认': 80, '屋面板': 90 }, op: '>=' },
  beam_height: { label: '梁高跨比', clause: 'GB50010-9.2.3', unit: '1/跨', threshold: { '简支': 0.083, '连续': 0.067 }, op: '>=' },
  concrete_strength: { label: '混凝土最低强度等级', clause: 'GB50010-4.1.2', unit: 'MPa', threshold: { '默认': 20, '预应力': 40 }, op: '>=' },
  seismic_grade: { label: '抗震等级标注', clause: 'GB55008-3.2.1', unit: '有/无', threshold: { '必须': 1 }, op: '==' },
  seismic_intensity: { label: '抗震设防烈度', clause: 'GB55008-3.1.1', unit: '度', threshold: { '最小': 6 }, op: '>=' },
  shear_wall_thickness: { label: '剪力墙最小厚度', clause: 'GB55008-4.3.1', unit: 'mm', threshold: { '默认': 160, '框支层': 200 }, op: '>=' },
  pile_count: { label: '柱下独立桩基数量', clause: 'GB55008-4.1.1', unit: '根', threshold: { '默认': 2, '条形桩基': 3 }, op: '>=' },
};

// ── window 挂载 ──────────────────────────────────────────────

(window as any)._initAuditItems = _initAuditItems;
(window as any).renderAuditButtons = renderAuditButtons;
(window as any).auditAction = auditAction;
(window as any).renderMultiLayerEditor = renderMultiLayerEditor;
(window as any).addMultiLayerRow = addMultiLayerRow;
(window as any).removeMultiLayerRow = removeMultiLayerRow;
(window as any).updateMultiLayerRow = updateMultiLayerRow;
(window as any).computeMultiLayerK = computeMultiLayerK;
