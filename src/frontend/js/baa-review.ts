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
