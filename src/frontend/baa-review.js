// P122: escHtml 在 baa-review.js 加载时 baa-ext.js 尚未加载，本地定义兜底
if (typeof escHtml !== 'function') {
    function escHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
}

// ── 概览页 ──────────────────────────────────────────────
// ── 规范库（loadSpecs 在 baa-admin.js 中定义，会先加载数据再渲染） ──
// 此处不重复定义，由 baa-admin.js 的后加载版本覆盖

// ── AI审图 ──────────────────────────────────────────────
async function runReview() {
  const select = document.getElementById('review-drawing-select');
  const id = select.value;
  if (!id) { showToast('请选择已解析的图纸', 'info'); return; }
  const drawing = parsedDrawings.find(d => d.id === id);
  if (!drawing) { showToast('图纸数据不存在', 'info'); return; }
  const bt = drawing.building_type;

  // 用缓存的数据直接提交审查，不需要重新上传文件
  const entities = drawing.entities || drawing.raw?.entities || [];
  if (entities.length === 0) { showToast('该图纸没有解析出实体数据，请重新上传解析', 'info'); return; }

  const loading = document.getElementById('review-loading');
  renderProgress(loading, '审查中', 30);

  try {
    const url = API_BASE() + '/review-from-data';
    const r = await fetch(url, {
      method: 'POST', headers: {...HEADERS(), 'Content-Type': 'application/json'},
      body: JSON.stringify({entities: entities, building_type: bt}),
    });
    const result = await r.json();
    loading.className = 'hidden';

    const summary = document.getElementById('review-summary');
    // 保存最新审查结果，供修正建议生成复用
    window._currentReviewResult = result;
    window._currentReviewEntities = entities;
    if (result.status === 'success') {
      const vs = result.summary || {};
      // ── P61 置信度分级统计 ──────────────────────────────
      const tc = vs.confidence_tier_counts || {confirmed:0, suspected:0, needs_review:0};
      summary.innerHTML =
        '<div class="grid grid-cols-4 gap-2 mb-3">' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + (vs.violations || 0) + '</div><div class="text-xs text-gray-400">违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + tc.confirmed + '</div><div class="text-xs text-gray-400">✅ 确认违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + tc.suspected + '</div><div class="text-xs text-gray-400">🟡 疑似违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + tc.needs_review + '</div><div class="text-xs text-gray-400">🔴 建议复核</div></div>' +
        '</div>';

      if (result.summary?.entity_types || result.queue_info?.task_id || result.task_id) {
        const summaryExtras = [];
        if (result.summary?.entity_types) {
          const entityParts = [];
          for (const [type, count] of Object.entries(result.summary.entity_types)) {
            entityParts.push('<span class="px-2 py-0.5 bg-gray-100 rounded text-xs">' + escHtml(type) + ': ' + count + '</span>');
          }
          summaryExtras.push('<p class="text-xs text-gray-400 mb-2">构件分布:</p><div class="flex flex-wrap gap-1 mb-3">' + entityParts.join('') + '</div>');
        }
        const reviewId = result.queue_info?.task_id || result.task_id || '';
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

// ── P62: 结构化摘要卡片（违规 TOP-5 + 整改优先级 + 合规路径） ──
      renderStructuredSummary(result.structured_summary || {}, result.summary || {});

      // ── P119: 违规审核工作流 — 审查完成后自动初始化后端审计条目 ──
      _initAuditItems(result);

      // 统计面板：违规严重度分布
      const severityCounts = {};
      (result.findings || []).filter(f => f.result === 'FAIL' && !f.is_duplicate).forEach(f => {
        const sev = f.severity || 'major';
        severityCounts[sev] = (severityCounts[sev] || 0) + 1;
      });
      const totalViols = Object.values(severityCounts).reduce((a, b) => a + b, 0);
      if (totalViols > 0) {
        const sevColors = {critical: 'bg-red-500', major: 'bg-orange-500', minor: 'bg-yellow-400'};
        const sevLabels = {critical: '严重', major: '主要', minor: '轻微'};
        const sevTextColors = {critical: 'text-red-700', major: 'text-orange-700', minor: 'text-yellow-700'};
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

      // findings可能是数组或旧的ID列表
      let violations = [];
      if (Array.isArray(result.findings)) {
        violations = result.findings.filter(f => f.result === 'FAIL' && !f.is_duplicate);
      } else {
        violations = result.details || [];
      }

      // 存储到全局供分页使用
      window._reviewViolations = violations;
      window._reviewThermalViolations = violations.filter(f => f.func_id && f.func_id.startsWith('THERM-'));
      window._reviewStructuralViolations = violations.filter(f => f.func_id && f.func_id.startsWith('STR-'));
      window._reviewThermalSummary = null;
      // 渲染热工/结构违规列表
      renderThermalViolations(window._reviewThermalViolations);
      renderStructuralViolations(window._reviewStructuralViolations);
      window._reviewPageSize = 15;
      window._reviewPage = 1;
      window._reviewFilter = 'all';
      window._reviewSearch = '';

      // 提升到 window 作用域，供 HTML onclick/onchange 调用
      window.renderViolationPage = function () {
        const v = window._reviewViolations || [];
        const pageSize = window._reviewPageSize || 15;
        const page = window._reviewPage || 1;
        const filter = window._reviewFilter || 'all';
        const search = (window._reviewSearch || '').toLowerCase();

        let filtered = v;
        if (filter === 'critical') filtered = filtered.filter(f => f.severity === 'critical');
        else if (filter === 'major') filtered = filtered.filter(f => f.severity === 'major');
        else if (filter === 'minor') filtered = filtered.filter(f => f.severity !== 'critical' && f.severity !== 'major');
        else if (filter !== 'all') filtered = filtered.filter(f => (f.clause_id || '') === filter);
        if (search) filtered = filtered.filter(f =>
          (f.clause_title || '').toLowerCase().includes(search) ||
          (f.clause_id || '').toLowerCase().includes(search) ||
          (f.entity_type || '').toLowerCase().includes(search)
        );

        // ── 置信度过滤：筛出低置信度需要人工复核的违规 ──
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

        // ── 置信度排序（低置信度在前，优先人工复核）──
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

        const selVals = {all:'全部',critical:'严重',major:'主要',minor:'轻微'};
        let filterOpts = Object.entries(selVals).map(([k,v]) => '<option value="'+k+'"'+(filter===k?' selected':'')+'>'+v+'</option>').join('');

        // 置信度过滤下拉
        const confSelVals = {all:'全部置信度',high:'确认违规(≥85%)',medium:'疑似违规(60-85%)',low:'建议复核(<60%)'};
        const confFilterOpts = Object.entries(confSelVals).map(([k,v]) => '<option value="'+k+'"'+(confFilter===k?' selected':'')+'>'+v+'</option>').join('');

        // 按规范分组标签
        const clauseGroups = {};
        v.forEach(f => {
          const cid = f.clause_id || '未知';
          if (!clauseGroups[cid]) clauseGroups[cid] = 0;
          clauseGroups[cid]++;
        });
        const sortedClauses = Object.entries(clauseGroups).sort((a, b) => b[1] - a[1]);

        let html = '<div class="flex items-center justify-between mb-2">' +
          '<p class="font-medium text-red-600">违规详情 (' + filtered.length + '/' + v.length + '项)</p>' +
          '<div class="flex gap-1 text-xs">' +
          '<select id="violation-filter" onchange="window._reviewFilter=this.value; window._reviewPage=1; renderViolationPage()" class="border rounded px-1 py-0.5 text-xs">' +
          filterOpts +
          '</select>' +
          '<select id="violation-conf-filter" onchange="window._reviewConfFilter=this.value; window._reviewPage=1; renderViolationPage()" class="border rounded px-1 py-0.5 text-xs">' +
          confFilterOpts +
          '</select>' +
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
            // 置信度可视化（后端 detail 已传 confidence 字段）
            const conf = f.confidence != null ? f.confidence : 1.0;
            const confPct = Math.round(conf * 100);
            const confColor = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'red';
            const confLabel = f.confidence_tier === 'confirmed' ? '确认违规' : f.confidence_tier === 'suspected' ? '疑似违规' : '建议复核';
            // 修正建议：从 result.corrections 中按 clause_id 匹配
            // corrections 的 clause_id 是规范ID（如 GB50016-5.5.18），与 detail 的 clause_id 对齐
            const corrKey = (f.clause_id || f.func_id || '').trim();
            const corrs = (window._currentReviewResult && window._currentReviewResult.corrections || [])
              .filter(c => c.clause_id === corrKey);
            const hasCorr = corrs.length > 0;
            const uid = 'corr-' + (f.func_id || f.clause_id || 'x') + '-' + (f.entity_id || '') + '-' + Math.random().toString(36).slice(2, 6);

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
            // 修正建议内联折叠
            if (hasCorr) {
              const top = corrs[0];
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

            // ── P119: 违规审核按钮 ──
            if (window._reviewAuditMapping) {
              const detailList = window._reviewAuditDetailList || [];
              const reviewId = window._reviewAuditMapping.reviewId;
              const fid = f.func_id || f.clause_id || '';
              const eid = f.entity_id || '';
              let auditItemId = null;
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

        // 分页控件
        if (totalPages > 1) {
          html += '<div class="flex items-center justify-center gap-2 mt-3 text-xs">';
          html += '<button onclick="window._reviewPage=Math.max(1,' + (page-1) + ');renderViolationPage()" class="px-2 py-1 border rounded hover:bg-gray-100" ' + (page<=1?'disabled':'') + '>‹</button>';
          for (let p = Math.max(1, page-2); p <= Math.min(totalPages, page+2); p++) {
            html += '<button onclick="window._reviewPage=' + p + ';renderViolationPage()" class="px-2 py-1 border rounded ' + (p===page?'bg-blue-100 text-blue-700':'hover:bg-gray-100') + '">' + p + '</button>';
          }
          html += '<button onclick="window._reviewPage=Math.min(' + totalPages + ',' + (page+1) + ');renderViolationPage()" class="px-2 py-1 border rounded hover:bg-gray-100" ' + (page>=totalPages?'disabled':'') + '>›</button>';
          html += '<span class="text-gray-400">' + page + '/' + totalPages + '</span>';
          html += '</div>';
        }

        document.getElementById('review-details').innerHTML = html;
      }

      // ── P62: 结构化摘要卡片 ────────────────────────────
      function renderStructuredSummary(sSummary, summary) {
        if (!sSummary || !sSummary.top_violations) return;
        const sc = sSummary.priority_distribution || {P0: 0, P1: 0, P2: 0};
        const top = sSummary.top_violations || [];
        const actions = sSummary.compliance_actions || [];
        const score = (summary.score != null) ? summary.score : null;
        const totalViols = summary.violations || 0;

        let html = '';

        // ── 顶部行：合规评分 + 优先级分布 ──
        html += '<div class="card bg-gradient-to-r from-gray-50 to-white border border-gray-100 p-3 mb-3">';
        html += '<div class="flex items-center justify-between mb-2">';
        html += '<div class="flex items-center gap-2">';
        html += '<span class="text-xs text-gray-500 font-medium">📋 审查结构化摘要</span>';
        if (score !== null) {
          const scoreColor = score >= 80 ? 'text-green-600' : score >= 60 ? 'text-yellow-600' : 'text-red-600';
          html += '<span class="px-2 py-0.5 rounded text-xs bg-gray-100 ' + scoreColor + ' font-bold">合规评分 ' + score + '/100</span>';
        }
        html += '</div>';
        html += '<div class="flex gap-2 text-xs">';
        if (sc.P0 > 0) html += '<span class="px-2 py-0.5 rounded bg-red-100 text-red-700 font-bold">🔴 P0 立即整改 ' + sc.P0 + '</span>';
        if (sc.P1 > 0) html += '<span class="px-2 py-0.5 rounded bg-orange-100 text-orange-700 font-bold">🟠 P1 尽快整改 ' + sc.P1 + '</span>';
        if (sc.P2 > 0) html += '<span class="px-2 py-0.5 rounded bg-yellow-100 text-yellow-700 font-bold">🟡 P2 计划优化 ' + sc.P2 + '</span>';
        html += '</div>';
        html += '</div>';

        // ── TOP-5 违规核心问题 ──
        if (top.length > 0) {
          html += '<div class="border-t border-gray-100 pt-2 mb-2">';
          html += '<div class="text-xs text-gray-500 font-medium mb-1">🔍 TOP-5 核心问题（按整改优先级排序）</div>';
          html += '<div class="space-y-1">';
          top.forEach(v => {
            const pLabel = {P0: 'P0 立即整改', P1: 'P1 尽快整改', P2: 'P2 计划优化'}[v.priority] || v.priority;
            const pColor = {P0: 'bg-red-600 text-white', P1: 'bg-orange-500 text-white', P2: 'bg-yellow-500 text-gray-900'}[v.priority] || 'bg-gray-400 text-white';
            const confTierLabel = {confirmed: '✓确认违规', suspected: '?疑似违规', needs_review: '☐建议复核'}[v.confidence_tier] || '';
            const confTierColor = {confirmed: 'text-red-600', suspected: 'text-orange-600', needs_review: 'text-gray-500'}[v.confidence_tier] || 'text-gray-500';
            html += '<div class="flex items-start gap-2 py-1 border-b border-gray-50 last:border-0">';
            html += '<div class="w-5 text-center"><span class="text-lg font-bold text-gray-300">' + v.rank + '</span></div>';
            html += '<div class="flex-1 min-w-0">';
            html += '<div class="flex items-center gap-1.5 flex-wrap">';
            html += '<span class="px-1.5 py-0.5 rounded text-xs font-bold ' + pColor + '">' + pLabel + '</span>';
            html += '<span class="text-xs ' + confTierColor + '">' + confTierLabel + '</span>';
            html += '<span class="text-xs text-gray-400">置信度 ' + Math.round((v.confidence||0)*100) + '%</span>';
            html += '<span class="text-xs text-gray-500 font-medium ml-auto">' + (v.clause_id||'') + '</span>';
            html += '</div>';
            html += '<div class="text-sm">' + (v.clause_title||'') + '</div>';
            html += '<div class="text-xs text-gray-400 mt-0.5">💡 ' + (v.compliance_path||'') + '</div>';
            html += '</div>';
            html += '</div>';
          });
          html += '</div>';
          html += '</div>';
        }

        // ── 合规路径指引 ──
        if (actions.length > 0) {
          html += '<div class="border-t border-gray-100 pt-2">';
          html += '<div class="text-xs text-gray-500 font-medium mb-1">🛤️ 合规路径指引</div>';
          html += '<div class="space-y-1">';
          actions.forEach(a => {
            const pLabel = {P0: '🔴 立即整改', P1: '🟠 尽快整改', P2: '🟡 计划优化'}[a.priority] || a.priority;
            html += '<div class="flex items-start gap-2 py-0.5">';
            html += '<span class="text-xs text-gray-600 font-medium whitespace-nowrap">' + pLabel + '</span>';
            html += '<span class="text-xs text-gray-400">· ' + a.count + ' 项 ·</span>';
            html += '<span class="text-xs text-gray-600">' + (a.description||'') + '</span>';
            html += '</div>';
            a.action_paths.slice(0,2).forEach(p => {
              html += '<div class="text-xs text-gray-400 pl-4 mt-0.5">→ ' + p + '</div>';
            });
          });
          html += '</div>';
          html += '</div>';
        }

        html += '</div>';

        // 插入到 review-details 之前（与热力图等汇总卡并列）
        const target = document.getElementById('review-details');
        if (target) target.insertAdjacentHTML('beforebegin', html);
      }

      // ── 违规热力图（按 func_id 前缀分组） ──────────────
      function renderViolationHeatmap(violations) {
        if (violations.length === 0) return '';

        // 按 func_id 前缀分组（如 DIM-, EXIST-, STR-, THERM-, EVAC-）
        const groups = {};
        violations.forEach(f => {
          const fid = f.func_id || f.clause_id || 'UNKNOWN';
          const prefix = fid.split('-')[0];
          if (!groups[prefix]) groups[prefix] = { total: 0, confSum: 0, critical: 0, major: 0, minor: 0, items: [] };
          groups[prefix].total++;
          groups[prefix].confSum += (f.confidence != null ? f.confidence : 1.0);
          const sev = f.severity || 'minor';
          if (sev === 'critical') groups[prefix].critical++;
          else if (sev === 'major') groups[prefix].major++;
          else groups[prefix].minor++;
          groups[prefix].items.push(f);
        });

        // 前缀显示名
        const prefixNames = {
          'DIM': '尺寸', 'EXIST': '存在性', 'DIST': '距离', 'COUNT': '数量',
          'AREA': '面积', 'ATTR': '属性', 'LIGHT': '照明', 'THERM': '热工',
          'STR': '结构', 'EVAC': '疏散'
        };
        const sortedGroups = Object.entries(groups).sort((a, b) => b[1].total - a[1].total);

        let html = '<div class="card p-2 text-xs mb-3">';
        html += '<p class="font-medium text-sm mb-2 text-gray-600">🔥 违规热力图（按规范类型）</p>';
        html += '<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">';
        sortedGroups.forEach(([prefix, g]) => {
          const avgConf = g.total > 0 ? g.confSum / g.total : 1.0;
          const confPct = Math.round(avgConf * 100);
          const density = g.total; // 违规数代表密度
          // 颜色：高违规+低置信 = 深红，低违规+高置信 = 浅绿
          const heatColor = density >= 10 ? 'red' : density >= 5 ? 'orange' : density >= 2 ? 'yellow' : 'green';
          html += '<div class="bg-' + heatColor + '-50 rounded p-1.5 cursor-pointer' + (density >= 5 ? ' ring-1 ring-' + heatColor + '-300' : '') + '" onclick="window._reviewFilter=\'' + prefix + '\';window._reviewPage=1;renderViolationPage()">' +
            '<p class="font-medium text-' + heatColor + '-700">' + (prefixNames[prefix] || prefix) + '</p>' +
            '<p class="text-xs text-gray-500">' + g.total + ' 项</p>' +
            // 迷你柱状图
            '<div class="mt-1 bg-gray-200 rounded h-1.5 overflow-hidden">' +
            '<div class="' + heatColor + '-500 h-full rounded" style="width:' + Math.min(100, density * 8) + '%"></div>' +
            '</div>' +
            // 置信度条
            '<div class="mt-0.5 flex items-center gap-0.5"><span class="text-[9px] text-gray-400">置信</span>' +
            '<div class="flex-1 bg-gray-200 rounded h-1 overflow-hidden"><div class="' + (avgConf >= 0.85 ? 'green' : avgConf >= 0.6 ? 'yellow' : 'red') + '-500 h-full rounded" style="width:' + confPct + '%"></div></div></div>' +
            // 严重度分布
            '<div class="mt-0.5 text-[9px] text-gray-400'>
              + (g.critical > 0 ? '<span class="text-red-500">●' + g.critical + '</span> ' : '')
              + (g.major > 0 ? '<span class="text-orange-500">●' + g.major + '</span>' : '')
            + '</div>' +
            '</div>';
        });
        html += '</div></div>';
        return html;
      }

      // ── 结构荷载违规汇总表 ──
      function renderStructuralSummary(violations) {
        const strViols = violations.filter(f =>
          f.func_id && f.func_id.startsWith('STR-')
        );
        if (strViols.length === 0) return '';

        // 按 func_id 分组，计算平均置信度
        const funcGroups = {};
        strViols.forEach(f => {
          const fid = f.func_id || 'STR-?';
          if (!funcGroups[fid]) funcGroups[fid] = { count: 0, confSum: 0, viols: [] };
          funcGroups[fid].count++;
          funcGroups[fid].confSum += (f.confidence != null ? f.confidence : 1.0);
          funcGroups[fid].viols.push(f);
        });
        const sortedFuncs = Object.entries(funcGroups).sort((a, b) => {
          const avgA = a[1].confSum / a[1].count;
          const avgB = b[1].confSum / b[1].count;
          return avgA - avgB; // 低置信度在前，提醒优先复查
        });

        let html = '<div class="card p-2 text-xs mb-3">';
        html += '<p class="font-medium text-sm mb-2 text-purple-600">🏗️ 结构荷载违规 (' + strViols.length + '项)</p>';

        // ── 置信度迷你柱状图（按 func_id 分组，低置信度优先） ──
        html += '<div class="mb-2">';
        sortedFuncs.forEach(([fid, g]) => {
          const avgConf = g.confSum / g.count;
          const confPct = Math.round(avgConf * 100);
          const confColor = avgConf >= 0.85 ? 'green' : avgConf >= 0.6 ? 'yellow' : 'red';
          // 柱状高度用 100% 满，条宽代表置信度百分比
          html += '<div class="flex items-center gap-1 mb-0.5">' +
            '<span class="text-gray-500 w-16 text-[10px]">' + fid + '</span>' +
            '<div class="flex-1 bg-gray-200 rounded h-2 overflow-hidden">' +
            '<div class="' + confColor + '-500 h-full rounded" style="width:' + confPct + '%"></div>' +
            '</div>' +
            '<span class="text-' + confColor + '-600 text-[10px] w-6 text-right">' + confPct + '%</span>' +
            '<span class="text-gray-400 text-[10px] w-6 text-right">(' + g.count + ')</span>' +
            '</div>';
        });
        html += '</div>';

        // ── 明细表格 ──
        html += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
          '<th class="pb-1 pr-1">函数</th><th class="pb-1 pr-1">构件</th><th class="pb-1 pr-1">实测</th><th class="pb-1 pr-1">要求</th><th class="pb-1 pr-1">置信</th><th class="pb-1">严重</th></tr></thead><tbody>';
        strViols.slice(0, 10).forEach(f => {
          const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
          const conf = f.confidence != null ? f.confidence : 1.0;
          const confPct = Math.round(conf * 100);
          const confColor = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'red';
          html += '<tr class="border-b border-gray-50">' +
            '<td class="py-1 pr-1">' + (f.func_id || '') + '</td>' +
            '<td class="py-1 pr-1 truncate max-w-16" title="' + (f.entity_id || '') + '">' + (f.entity_type || '') + '</td>' +
            '<td class="py-1 pr-1">' + (f.extracted_value != null ? Number(f.extracted_value).toFixed(2) : '-') + '</td>' +
            '<td class="py-1 pr-1">' + (f.required_value != null ? Number(f.required_value).toFixed(2) : '-') + '</td>' +
            '<td class="py-1 pr-1"><div class="w-10 bg-gray-200 rounded-full h-1.5 overflow-hidden"><div class="' + confColor + '-500 h-full rounded-full" style="width:' + confPct + '%"></div></div></td>' +
            '<td class="py-1"><span class="px-1 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + (f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微') + '</span></td></tr>';
        });
        if (strViols.length > 10) html += '<tr><td colspan="6" class="pt-1 text-gray-400 text-center">… 还有 ' + (strViols.length - 10) + ' 项</td></tr>';
        html += '</tbody></table></div>';
        return html;
      }

      // ── 热工汇总表 ──
      function renderThermalSummary(violations) {
        const thermViols = violations.filter(f =>
          f.func_id && f.func_id.startsWith('THERM-')
        );
        if (thermViols.length === 0) return '';

        // 按 func_id 分组，计算平均置信度
        const funcGroups = {};
        thermViols.forEach(f => {
          const fid = f.func_id || 'THERM-?';
          if (!funcGroups[fid]) funcGroups[fid] = { count: 0, confSum: 0, viols: [] };
          funcGroups[fid].count++;
          funcGroups[fid].confSum += (f.confidence != null ? f.confidence : 1.0);
          funcGroups[fid].viols.push(f);
        });
        const sortedFuncs = Object.entries(funcGroups).sort((a, b) => {
          const avgA = a[1].confSum / a[1].count;
          const avgB = b[1].confSum / b[1].count;
          return avgA - avgB;
        });

        let html = '<div class="card p-2 text-xs mb-3">';
        html += '<p class="font-medium text-sm mb-2 text-orange-600">🌡️ 热工性能违规 (' + thermViols.length + '项)</p>';

        // ── 置信度迷你柱状图 ──
        html += '<div class="mb-2">';
        sortedFuncs.forEach(([fid, g]) => {
          const avgConf = g.confSum / g.count;
          const confPct = Math.round(avgConf * 100);
          const confColor = avgConf >= 0.85 ? 'green' : avgConf >= 0.6 ? 'yellow' : 'red';
          html += '<div class="flex items-center gap-1 mb-0.5">' +
            '<span class="text-gray-500 w-16 text-[10px]">' + fid + '</span>' +
            '<div class="flex-1 bg-gray-200 rounded h-2 overflow-hidden">' +
            '<div class="' + confColor + '-500 h-full rounded" style="width:' + confPct + '%"></div>' +
            '</div>' +
            '<span class="text-' + confColor + '-600 text-[10px] w-6 text-right">' + confPct + '%</span>' +
            '<span class="text-gray-400 text-[10px] w-6 text-right">(' + g.count + ')</span>' +
            '</div>';
        });
        html += '</div>';

        // ── 明细表格 ──
        html += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
          '<th class="pb-1 pr-1">函数</th><th class="pb-1 pr-1">条款</th><th class="pb-1 pr-1">实测</th><th class="pb-1 pr-1">要求</th><th class="pb-1 pr-1">置信</th><th class="pb-1">严重</th></tr></thead><tbody>';
        thermViols.slice(0, 10).forEach(f => {
          const sev = f.severity || 'major';
          const sevColor = sev === 'critical' ? 'red' : sev === 'major' ? 'orange' : 'yellow';
          const conf = f.confidence != null ? f.confidence : 1.0;
          const confPct = Math.round(conf * 100);
          const confColor = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'red';
          html += '<tr class="border-b border-gray-50">' +
            '<td class="py-1 pr-1">' + (f.func_id || '') + '</td>' +
            '<td class="py-1 pr-1 truncate max-w-20" title="' + (f.clause_title || '') + '">' + (f.clause_id || '') + '</td>' +
            '<td class="py-1 pr-1">' + (f.extracted_value != null ? Number(f.extracted_value).toFixed(3) : '-') + '</td>' +
            '<td class="py-1 pr-1">' + (f.required_value != null ? Number(f.required_value).toFixed(3) : '-') + '</td>' +
            '<td class="py-1 pr-1"><div class="w-10 bg-gray-200 rounded-full h-1.5 overflow-hidden"><div class="' + confColor + '-500 h-full rounded-full" style="width:' + confPct + '%"></div></div></td>' +
            '<td class="py-1"><span class="px-1 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + (sev === 'critical' ? '严重' : sev === 'major' ? '主要' : '轻微') + '</span></td></tr>';
        });
        if (thermViols.length > 10) html += '<tr><td colspan="6" class="pt-1 text-gray-400 text-center">… 还有 ' + (thermViols.length - 10) + ' 项</td></tr>';
        html += '</tbody></table></div>';
        return html;
      }

      // ── EVAC + 走廊宽度汇总表 ──
      function renderEvacCorridorSummary(violations) {
        const evacViols = violations.filter(f =>
          f.func_id && f.func_id.startsWith('EVAC-')
        );
        const dim4Viols = violations.filter(f =>
          f.func_id === 'DIM-004'
        );
        const deadEnds = violations.filter(f =>
          f.explanation && f.explanation.toLowerCase().includes('死胡同')
        );
        
        if (evacViols.length === 0 && dim4Viols.length === 0) return '';
        
        let html = '<div class="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">';
        
        if (evacViols.length > 0) {
          html += '<div class="card p-2 text-xs">';
          html += '<p class="font-medium text-sm mb-1 text-red-600">🚪 疏散路径违规 (' + evacViols.length + '项)</p>';
          html += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
            '<th class="pb-1 pr-1">类型</th><th class="pb-1 pr-1">实体</th><th class="pb-1 pr-1">实测</th><th class="pb-1 pr-1">要求</th><th class="pb-1 pr-1">置信</th><th class="pb-1">判定</th></tr></thead><tbody>';
          evacViols.slice(0, 10).forEach(f => {
            const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
            const conf = f.confidence != null ? f.confidence : 1.0;
            const confPct = Math.round(conf * 100);
            const confColor = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'red';
            html += '<tr class="border-b border-gray-50">' +
              '<td class="py-1 pr-1">' + (f.func_id || '') + '</td>' +
              '<td class="py-1 pr-1 truncate max-w-16" title="' + (f.entity_id || '') + '">' + (f.entity_type || '') + '</td>' +
              '<td class="py-1 pr-1">' + (f.extracted_value != null ? Number(f.extracted_value).toFixed(2) : '-') + '</td>' +
              '<td class="py-1 pr-1">' + (f.required_value != null ? f.required_value : '-') + '</td>' +
              '<td class="py-1 pr-1"><div class="w-10 bg-gray-200 rounded-full h-1.5 overflow-hidden"><div class="' + confColor + '-500 h-full rounded-full" style="width:' + confPct + '%"></div></div></td>' +
              '<td class="py-1"><span class="px-1 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + (f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微') + '</span></td></tr>';
          });
          if (evacViols.length > 10) html += '<tr><td colspan="6" class="pt-1 text-gray-400 text-center">… 还有 ' + (evacViols.length - 10) + ' 项</td></tr>';
          html += '</tbody></table></div>';
        }
        
        if (dim4Viols.length > 0) {
          html += '<div class="card p-2 text-xs">';
          html += '<p class="font-medium text-sm mb-1 text-orange-600">📏 走廊宽度违规 (' + dim4Viols.length + '项)</p>';
          html += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
            '<th class="pb-1 pr-1">走廊</th><th class="pb-1 pr-1">实测宽度</th><th class="pb-1 pr-1">要求</th><th class="pb-1">判定</th></tr></thead><tbody>';
          dim4Viols.slice(0, 10).forEach(f => {
            html += '<tr class="border-b border-gray-50">' +
              '<td class="py-1 pr-1 truncate max-w-16" title="' + (f.entity_id || '') + '">' + (f.entity_id || '').replace('CORRIDOR_', 'C') + '</td>' +
              '<td class="py-1 pr-1">' + (f.extracted_value != null ? Number(f.extracted_value).toFixed(3) + 'm' : '-') + '</td>' +
              '<td class="py-1 pr-1">≥' + (f.required_value || 1.1) + 'm</td>' +
              '<td class="py-1"><span class="px-1 rounded text-xs bg-orange-100 text-orange-700">违规</span></td></tr>';
          });
          if (dim4Viols.length > 10) html += '<tr><td colspan="4" class="pt-1 text-gray-400 text-center">… 还有 ' + (dim4Viols.length - 10) + ' 项</td></tr>';
          html += '</tbody></table></div>';
        }
        
        html += '</div>';
        return html;
      }

      // 清除上一次审查残留的汇总卡/热力图（避免多次审查累积重复卡）
      while (details.previousElementSibling &&
             (details.previousElementSibling.classList.contains('card') ||
              details.previousElementSibling.classList.contains('heatmap-wrap'))) {
        details.previousElementSibling.remove();
      }

      // 在渲染违规列表前插入汇总表（疏散/走廊/结构荷载/热工）+ 热力图
      const thermalSummaryHtml = renderThermalSummary(violations);
      const summaryHtml = renderEvacCorridorSummary(violations) + renderStructuralSummary(violations) + thermalSummaryHtml;
      if (summaryHtml) {
        document.getElementById('review-details').insertAdjacentHTML('beforebegin', summaryHtml);
      }

      // 热力图：按 func_id 前缀分组，柱状图展示违规密度
      const heatHtml = renderViolationHeatmap(violations);
      if (heatHtml) {
        document.getElementById('review-details').insertAdjacentHTML('beforebegin', heatHtml);
      }

      if (violations.length > 0) {
        renderViolationPage();

        // 保存审查结果到全局，供对比重构消费
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
          try { localStorage.setItem('baa_review_results', JSON.stringify(reviewResults.slice(0, 50))); } catch(e) {}
          // 审查结果已由后端 /review 自动保存到数据库

          // ── 审查完成后自动展开修正建议面板 ──
          const corrPanel = document.getElementById('review-correction-panel');
          if (corrPanel) corrPanel.className = corrPanel.className.replace(/\bhidden\b/g, '').trim();
          // 后端 /review-from-data 已自动生成 corrections，直接从 result 取
          const loadedCorrs = result.corrections || [];
          if (loadedCorrs.length > 0) {
            const resultsDiv = document.getElementById('correction-results');
            const sorted = loadedCorrs.slice().sort((a, b) => {
              const order = {high: 0, medium: 1, low: 2};
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
      }
    } else {
      summary.innerHTML = '<span class="text-red-500">' + (result.message || '审查失败') + '</span>';
    }
  } catch (e) {
    loading.innerHTML = '❌ 审查失败: ' + e.message;
    loading.className = 'mt-3 text-sm text-red-500';
  }
}

// ── 批量审查 ──────────────────────────────────────────────
function switchReviewTab(tab) {
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
    renderStructuralViolations(window._reviewStructuralViolations || []);
  }
  if (tab === 'thermal') {
    renderThermalViolations(window._reviewThermalViolations || []);
  }
}

let batchFiles = [];

function onBatchFilesSelected(e) {
  const files = Array.from(e.target.files);
  batchFiles = files;
  const list = document.getElementById('batch-file-list');
  if (files.length === 0) {
    list.textContent = '';
    return;
  }
  list.innerHTML = files.map(f => `<div>📄 ${f.name} (${(f.size/1024/1024).toFixed(2)}MB)</div>`).join('');
}

document.getElementById('batch-file-input').addEventListener('change', onBatchFilesSelected);

// ── P10 反馈申诉 ──────────────────────────────────────────
async function runBatchReview() {
  if (batchFiles.length === 0) {
    showToast('请先选择至少一个图纸文件', 'info');
    return;
  }

  const btn = document.getElementById('batch-review-start-btn');
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
      throw new Error(err.message || '审查失败');
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
      resp.cross_analysis.slice(0, 8).forEach(c => {
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
    resp.results.forEach(r => {
      if (r.status === 'error') {
        fileHtml += '<div class="card p-2 text-xs border-l-2 border-red-500 bg-red-50">' +
          '<p class="font-medium text-red-600">❌ ' + escHtml(r.filename || '') + '</p>' +
          '<p class="text-gray-500">' + escHtml(r.message || '') + '</p></div>';
        return;
      }
      const s = r.summary;
      const isClean = s.violations === 0;
      const sevColor = isClean ? 'green' : (s.violations >= 20 ? 'red' : 'orange');
      // P122 XSS: filename 来自后端，escHtml 转义
      const safeFilename = escHtml(r.filename || '');
      const total = s.total_checks || 0;
      const passRate = total > 0 ? Math.round((1 - s.violations / total) * 100) : 100;

      // 按严重度分组
      const sevCount = { critical: 0, major: 0, minor: 0 };
      (r.details || []).forEach(v => {
        const sv = v.severity || 'major';
        if (sv in sevCount) sevCount[sv]++;
      });

      // 顶部进度条（通过率）
      let bar = '<div class="mt-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">' +
        '<div class="' + sevColor + '-500 h-full rounded-full" style="width:' + passRate + '%"></div></div>' +
        '<div class="flex justify-between text-[10px] text-gray-400 mt-0.5">' +
        '<span>通过率 ' + passRate + '%</span><span>检查 ' + total.toLocaleString() + '</span></div>';

      // 严重度徽章
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
          '主要: ' + Object.entries(s.violation_by_clause).slice(0, 3).map(([k,v]) => k + '(' + v + ')').join(', ') + '</p>' : '') +
        '</div>';
    });
    fileHtml += '</div>';
    details.innerHTML += fileHtml;

    loading.classList.add('hidden');
  } catch (err) {
    loading.textContent = '❌ ' + err.message;
    loading.className = 'mt-3 text-sm text-red-500';
  } finally {
    btn.disabled = false;
  }
}

// ── 审查结果对比 Diff ──────────────────────────────────────
let _diffResult = null;

// 监听文件选择
// 加载对比图纸可视化（违规叠加渲染）
// ── PDF 下载 ──────────────────────────────────────────────
// ── P91: 结构化导出 (JSON/CSV) ────────────────────────────
// ── JSON 导出 ──────────────────────────────────────────────
// ── 审查结果存储（localStorage + 后端持久化） ──────────
let reviewResults = [];
// 违规可视化渲染（SVG/Canvas叠加）
function renderViolationOverlay(r) {
  const canvas = document.getElementById('compare-overlay-canvas');
  const visEmpty = document.getElementById('compare-vis-empty');
  if (!canvas) return;

  const viols = r.details || [];
  const corrs = r.corrections || [];
  const elements = r.elements || r.rawResult?.elements || [];
  
  // 没有位置数据时显示占位
  const hasPosData = elements.length > 0 || viols.some(v => v.entity_type);
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
  const violTypes = {};
  const violClauses = {};
  viols.forEach(v => {
    const et = v.entity_type || 'unknown';
    const severity = v.severity || 'major';
    if (!violTypes[et] || violTypes[et] === 'major') violTypes[et] = severity;
    if (!violClauses[et]) violClauses[et] = [];
    violClauses[et].push(v.clause_id + ': ' + (v.clause_title || ''));
  });

  // 实体类型 → 颜色/位置映射
  const entityColors = {
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

  // 布局：将实体类型分布在画布网格中
  const allTypes = [...new Set([...viols.map(v => v.entity_type || 'unknown'), ...elements.map(e => e.type || e.entity_type || '')].filter(Boolean))];
  
  if (allTypes.length === 0) {
    // 无类型信息，显示文本
    ctx.fillStyle = '#999';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('无实体位置数据', W/2, H/2);
    return;
  }

  // 网格分布可视化
  const cols = Math.min(4, Math.ceil(Math.sqrt(allTypes.length)));
  const rows = Math.ceil(allTypes.length / cols);
  const cellW = (W - 60) / cols;
  const cellH = (H - 60) / rows;

  // 收集每个圆圈的几何信息（用于悬停检测）
  const circles = [];

  allTypes.forEach((t, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cx = 30 + col * cellW + cellW / 2;
    const cy = 30 + row * cellH + cellH / 2;
    const radius = Math.min(cellW, cellH) * 0.3;

    const color = entityColors[t] || '#6b7280';
    const severity = violTypes[t] || 'none';
    const isViolated = violTypes[t] !== undefined;

    // 绘制圆圈
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.fillStyle = isViolated ? (severity === 'critical' ? '#fecaca' : '#fed7aa') : '#dcfce7';
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = isViolated ? 3 : 1.5;
    ctx.stroke();

    // 实体图标
    ctx.fillStyle = color;
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = t.length > 12 ? t.slice(0,10) + '..' : t;
    ctx.fillText(label, cx, cy);

    // 违规标记
    if (isViolated) {
      ctx.fillStyle = color;
      ctx.font = 'bold 8px sans-serif';
      ctx.fillText('✗', cx + radius + 8, cy - radius);
    }

    // 详情提示（画布内，保留原有）
    const hints = violClauses[t];
    if (hints && hints.length > 0) {
      ctx.fillStyle = '#6b7280';
      ctx.font = '7px sans-serif';
      ctx.textAlign = 'center';
      hints.slice(0, 2).forEach((h, hi) => {
        ctx.fillText(h.length > 20 ? h.slice(0,18) + '..' : h, cx, cy + 12 + hi * 10);
      });
    }

    // 记录几何信息供悬停检测
    circles.push({
      x: cx, y: cy, r: radius,
      type: t, color: color,
      severity: severity,
      isViolated: isViolated,
      hints: hints || []
    });
  });

  // ── 鼠标悬停 Tooltip ──
  const tip = document.getElementById('compare-vis-tooltip');
  if (!tip) {
    const t = document.createElement('div');
    t.id = 'compare-vis-tooltip';
    t.className = 'fixed hidden bg-black bg-opacity-90 text-white text-xs rounded-lg p-2 pointer-events-none z-50 max-w-xs shadow-lg';
    document.body.appendChild(t);
  }
  canvas.__circles = circles;
  canvas.__tooltip = tip;

  // 移除旧监听器避免重复绑定
  if (canvas.__onMove) canvas.removeEventListener('mousemove', canvas.__onMove);
  if (canvas.__onLeave) canvas.removeEventListener('mouseleave', canvas.__onLeave);

  canvas.__onMove = function(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    let hit = null;
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

  canvas.__onLeave = function() { tip.classList.add('hidden'); };

  canvas.addEventListener('mousemove', canvas.__onMove);
  canvas.addEventListener('mouseleave', canvas.__onLeave);
}

// 渲染修正后预览文本
function renderAfterPreview(r) {
  const div = document.getElementById('compare-after-preview');
  const corrs = r.corrections || [];
  const viols = r.details || [];

  if (corrs.length === 0 && viols.length === 0) {
    div.innerHTML = '<div class="text-gray-400">图纸合规，无需修正</div>';
    return;
  }

  // 按优先级分组
  const high = corrs.filter(c => c.priority === 'high');
  const medium = corrs.filter(c => c.priority === 'medium');
  const low = corrs.filter(c => c.priority === 'low');

  let html = '<div class="space-y-1.5">';
  
  html += '<div class="flex gap-3 text-xs mb-2">' +
    '<span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-red-500"></span>高优先级: ' + high.length + '</span>' +
    '<span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>中优先级: ' + medium.length + '</span>' +
    '<span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-gray-500"></span>低优先级: ' + low.length + '</span>' +
    '</div>';

  if (high.length > 0) {
    html += '<div class="font-medium text-red-700 text-xs mt-2">🔴 必须修复</div>';
    high.forEach(c => {
      html += '<div class="pl-3 border-l-2 border-red-400 mb-1">' +
        '<span class="font-medium">' + (c.action || '') + '</span>: ' + (c.recommendation || '') +
        (c.parameter ? ' <span class="text-gray-400">(参数: ' + c.parameter + ')</span>' : '') +
        '</div>';
    });
  }

  if (medium.length > 0) {
    html += '<div class="font-medium text-yellow-700 text-xs mt-2">🟡 建议整改</div>';
    medium.forEach(c => {
      html += '<div class="pl-3 border-l-2 border-yellow-400 mb-1">' +
        '<span class="font-medium">' + (c.action || '') + '</span>: ' + (c.recommendation || '') +
        '</div>';
    });
  }

  if (low.length > 0) {
    html += '<div class="font-medium text-gray-600 text-xs mt-2">⚪ 可优化</div>';
    low.forEach(c => {
      html += '<div class="pl-3 border-l-2 border-gray-400 mb-1">' +
        '<span class="font-medium">' + (c.action || '') + '</span>: ' + (c.recommendation || '') +
        '</div>';
    });
  }

  // 无修正建议但有违规 → 兜底描述
  if (corrs.length === 0 && viols.length > 0) {
    html += '<div class="text-yellow-700">' +
      '发现 ' + viols.length + ' 项违规，修正引擎未生成具体建议。请参照规范要求手动调整。' +
      '</div>';
  }

  html += '</div>';
  div.innerHTML = html;
}

function onCompareSelect() {
  const select = document.getElementById('compare-drawing-select');
  const id = select.value;
  const empty = document.getElementById('compare-empty');
  const content = document.getElementById('compare-content');
  
  if (!id) {
    empty.className = 'card text-center py-8 text-gray-300';
    content.className = 'hidden';
    return;
  }
  
  const r = reviewResults.find(x => x.id === id);
  if (!r) return;
  
  empty.className = 'hidden';
  content.className = '';
  
  // 概览摘要
  const summaryDiv = document.getElementById('compare-summary');
  const viols = r.details || [];
  const corrs = r.corrections || [];
  const totalChecks = r.summary?.total_checks || viols.length + 10;
  const passRate = totalChecks > 0 ? Math.round((1 - viols.length / totalChecks) * 100) : 0;
  const criticalCount = viols.filter(v => v.severity === 'critical').length;
  const majorCount = viols.filter(v => v.severity === 'major').length;
  const entityCount = r.rawResult?.elements?.length || r.elements?.length || 0;
  
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
  if (r.drawingEntry?.raw) {
    originalJson.textContent = JSON.stringify(r.drawingEntry.raw, null, 2);
  } else if (r.elements && r.elements.length > 0) {
    originalJson.textContent = JSON.stringify(r.elements, null, 2);
  } else {
    originalJson.textContent = JSON.stringify(r.rawResult, null, 2);
  }
  
  // 违规标注
  const violationsDiv = document.getElementById('compare-violations');
  violationsDiv.innerHTML = '';
  if (viols.length === 0) {
    violationsDiv.innerHTML = '<div class="text-xs text-green-600">✅ 图纸合规，无违规项</div>';
  } else {
    // 按严重度排序
    const severityOrder = {'critical': 0, 'major': 1, 'minor': 2};
    const sorted = [...viols].sort((a, b) => (severityOrder[a.severity] || 2) - (severityOrder[b.severity] || 2));
    
    // P122 XSS 防护：违规数据全部 escHtml 转义，innerHTML += → 拼接后统一赋值
    const parts = [];
    sorted.forEach(f => {
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
    // P122 XSS: 修正建议字段全部 escHtml 转义
    const parts = [];
    corrs.slice(0, 10).forEach((c, ci) => {
      const pColor = c.priority === 'high' ? 'red' : c.priority === 'medium' ? 'yellow' : 'gray';
      const pLabel = c.priority === 'high' ? '高优先级' : c.priority === 'medium' ? '中优先级' : '低优先级';
      const statusKey = 'corr_' + r.id + '_' + ci;
      const savedStatus = localStorage.getItem(statusKey);
      const accepted = savedStatus === 'accepted';
      const rejected = savedStatus === 'rejected';
      const statusBadge = accepted ? '<span class="text-green-600 text-xs">✅ 已确认</span>' : rejected ? '<span class="text-red-400 text-xs">❌ 已拒绝</span>' : '';
      const safeClauseTitle = escHtml(c.clause_title || '');
      const safeAction = escHtml(c.action || '');
      const safeRecommendation = escHtml(c.recommendation || '');
      const safeReviewId = escHtml(r.id || '');
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

/**
 * 审查完成后，从 findings/details 批量初始化后端审计条目
 * 后端返回 item_id 格式为 "{review_id}:{index}"，前端据此映射
 * 结果存入 window._reviewAuditMapping 供确认/驳回按钮使用
 */
async function _initAuditItems(result) {
  const reviewId = result.queue_info?.task_id || result.task_id || '';
  if (!reviewId) {
    return;  // 无 review_id 则不初始化审计
  }

  const details = (result.findings || []).filter(f => f.result === 'FAIL' && !f.is_duplicate);
  if (details.length === 0) {
    window._reviewAuditMapping = {};
    return;
  }

  try {
    const url = API_BASE() + '/api/v1/audit/items';
    const r = await fetch(url, {
      method: 'POST',
      headers: { ...HEADERS(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ review_id: reviewId, details: details }),
    });
    if (r.ok) {
      const resp = await r.json();
      // 后端 item_id = "{review_id}:{idx}"，按 FAIL 详情顺序映射
      const mapping = {};
      details.forEach((d, i) => {
        const fid = d.func_id || d.clause_id || '';
        const eid = d.entity_id || '';
        mapping[fid + ':' + eid + ':' + i] = reviewId + ':' + i;
      });
      window._reviewAuditMapping = { mapping, reviewId };
      window._reviewAuditDetailList = details;

      // 加载后端审计条目状态（供按钮正确显示已确认/已驳回等状态）
      _loadAuditItemStates(reviewId);
    }
  } catch (err) {
    console.warn('[P119] 审计条目初始化失败:', err.message);
  }
}

/**
 * 从后端加载审计条目状态，缓存到 window._reviewAuditStates
 */
async function _loadAuditItemStates(reviewId) {
  try {
    const url = API_BASE() + '/api/v1/audit/items?review_id=' + encodeURIComponent(reviewId);
    const r = await fetch(url, { headers: HEADERS() });
    if (r.ok) {
      const resp = await r.json();
      const states = {};
      (resp.items || []).forEach(item => { states[item.id] = item.status; });
      window._reviewAuditStates = states;
    }
  } catch (err) {
    console.warn('[P119] 审计状态加载失败:', err.message);
  }
}

/**
 * 渲染 P119 审核操作按钮（确认/驳回/待核实）
 * 根据后端 item 状态显示对应操作按钮
 *
 * @param {string} itemId  - 后端审计条目 ID
 * @param {string} itemStatus - 后端返回的 status
 * @param {string} clauseId - 条款 ID（用于 UI 展示）
 * @returns {string} HTML 按钮字符串
 */
function renderAuditButtons(itemId, itemStatus, clauseId) {
  if (!itemId) return '';

  const safeClause = escHtml(clauseId || '');
  let html = '<div class="flex gap-1 mt-1"><span class="text-[10px] text-gray-400">审核:</span>';

  switch (itemStatus) {
    case 'confirmed':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✅ 已确认</span>';
      html += '<button onclick="auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-red-100 hover:text-red-700">↩ 驳回</button>';
      break;
    case 'dismissed':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">❌ 已驳回</span>';
      html += '<button onclick="auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700">↩ 确认</button>';
      break;
    case 'pending':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">⏳ 待核实</span>';
      html += '<button onclick="auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>';
      html += '<button onclick="auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      break;
    default: // unreviewed
      html += '<button onclick="auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>';
      html += '<button onclick="auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      html += '<button onclick="auditAction(\'' + itemId + '\',\'pending\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200">⏳ 待核实</button>';
  }
  html += '</div>';
  return html;
}

/**
 * 发起 P119 审计操作（确认/驳回/待核实），调用后端 API 后刷新违规列表
 *
 * @param {string} itemId  - 后端审计条目 ID
 * @param {string} action  - 'confirm' | 'dismiss' | 'pending'
 * @param {string} clauseId - 条款 ID（仅用于日志/展示）
 */
async function auditAction(itemId, action, clauseId) {
  const safeAction = escHtml(action || '');
  try {
    let body = {};
    let method = 'POST';
    if (action === 'dismiss') {
      body = { reason: '人工驳回' };
    }
    const url = API_BASE() + '/api/v1/audit/items/' + encodeURIComponent(itemId) + '/' + safeAction;
    const r = await fetch(url, {
      method: method,
      headers: { ...HEADERS(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json();
      showToast('操作失败: ' + (err.detail || r.statusText), 'error');
      return;
    }
    showToast((action === 'confirm' ? '✅ 已确认违规' : action === 'dismiss' ? '❌ 已驳回（误报）' : '⏳ 已标记待核实') + ' ' + escHtml(clauseId || ''), 'info');
    // 刷新违规列表以反映状态变化
    renderViolationPage && renderViolationPage();
  } catch (err) {
    showToast('网络错误: ' + err.message, 'error');
  }
}

// ── P45 热工性能计算 ────────────────────────────────────────

// 气候带名称映射
const climateNames = { severe_cold:'严寒', cold:'寒冷', hot_cold:'夏热冬冷', hot_warm:'夏热冬暖' };

// 保温材料的导热系数（W/(m·K)）
const THERMAL_MATERIALS = {
  rockwool:  { name: '岩棉板',     lambda: 0.035, density: 800 },
  eps:       { name: 'EPS聚苯板', lambda: 0.040, density: 20  },
  xps:       { name: 'XPS挤塑板', lambda: 0.030, density: 35  },
  pu:        { name: '聚氨酯',    lambda: 0.024, density: 40  },
  aerogel:   { name: '气凝胶',    lambda: 0.012, density: 120 },
};

// 各气候带 GB55015-3.2.2 K 值阈值（W/(m²·K)）
const THERMAL_THRESHOLDS = {
  severe_cold: { exterior_wall: 0.45, roof: 0.35, ground_floor: 0.30, exterior_window: 2.0 },
  cold:        { exterior_wall: 0.60, roof: 0.50, ground_floor: 0.45, exterior_window: 2.4 },
  hot_cold:    { exterior_wall: 1.50, roof: 1.20, ground_floor: 0.60, exterior_window: 3.2 },
  hot_warm:    { exterior_wall: 2.00, roof: 1.50, ground_floor: 0.80, exterior_window: 4.0 },
};

// 内外表面传热系数（W/(m²·K)）
const HI = 8.7;   // 内表面
const HO = 23.0;  // 外表面

// 默认保温层厚度（mm）按构件类型
const DEFAULT_THERMAL_THICKNESS = {
  exterior_wall: 50,
  roof: 60,
  ground_floor: 80,
  exterior_window: 30,
};
// 计算传热系数 K 值：调用后端 /api/v1/review/thermal/k-value API
// 渲染热工违规列表（与 STR/EVAC 对齐：置信度+严重度+修正建议）
// 页面加载后渲染阈值表
// ── P45 多材料复合层计算 ─────────────────────────────────────

function renderMultiLayerEditor() {
  const container = document.getElementById('multi-layer-editor');
  if (!container) return;
  container.innerHTML = '';
  let html = '<div class="text-xs text-gray-500 mb-2">从上到下添加保温层/结构层</div>';
  html += '<div id="multi-layer-rows" class="space-y-2 mb-2"></div>';
  html += '<div class="flex gap-2 mb-3">';
  html += '<button onclick="addMultiLayerRow()" class="px-3 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700">+ 添加层</button>';
  html += '<button onclick="computeMultiLayerK()" class="px-3 py-1 bg-orange-600 text-white text-xs rounded hover:bg-orange-700">计算 K 值</button>';
  html += '</div>';
  container.innerHTML = html;
  // 初始化默认层：内外表面换热 + 保温层
  addMultiLayerRow('surface_inside', '内表面换热', 0.0, 'm²·K/W');
  addMultiLayerRow('insulation', '保温层', 0.05, 'm');
  addMultiLayerRow('structure', '结构层(混凝土)', 0.2, 'm');
  addMultiLayerRow('surface_outside', '外表面换热', 0.0, 'm²·K/W');
}

function addMultiLayerRow(type, name, thickness, unit) {
  const rows = document.getElementById('multi-layer-rows');
  if (!rows) return;
  const idx = rows.children.length;
  const defaultName = name || (type === 'surface_inside' ? '内表面换热' : type === 'surface_outside' ? '外表面换热' : '保温层');
  const defaultThick = thickness ?? (type === 'surface_inside' || type === 'surface_outside' ? 0 : 0.05);
  const defaultUnit = unit || (type === 'surface_inside' || type === 'surface_outside' ? 'm²·K/W' : 'm');
  const rowsHtml = '<div class="flex gap-2 items-center" data-idx="' + idx + '">' +
    '<select onchange="updateMultiLayerRow(' + idx + ',0,this.value)" class="text-xs border rounded px-1 py-0.5 flex-1">' +
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
    '<input type="number" step="0.01" value="' + defaultThick + '" onchange="updateMultiLayerRow(' + idx + ',1,this.value)" class="text-xs border rounded px-1 py-0.5 w-20" placeholder="厚度/热阻" />' +
    '<span class="text-xs text-gray-400 w-12">' + defaultUnit + '</span>' +
    '<button onclick="removeMultiLayerRow(' + idx + ')" class="px-1 text-red-500 text-xs hover:text-red-700">×</button>' +
    '</div>';
  rows.insertAdjacentHTML('beforeend', rowsHtml);
}

function removeMultiLayerRow(idx) {
  const rows = document.getElementById('multi-layer-rows');
  if (rows.children.length <= 1) return; // 至少保留1层
  rows.children[idx].remove();
}

function updateMultiLayerRow(idx, field, value) {
  // 仅触发重新计算，不存全局状态
}

function computeMultiLayerK() {
  const rows = document.getElementById('multi-layer-rows');
  if (!rows) return;
  const resultEl = document.getElementById('multi-layer-result');
  const materials = {
    eps: 0.040, xps: 0.030, rockwool: 0.035, pu: 0.024,
    concrete: 1.74, brick: 0.81, glass: 0.8, steel: 50,
    surface_inside: null, surface_outside: null,
  };

  let totalR = 0;
  const layerInfo = [];
  const climate = document.getElementById('thermal-climate').value || 'severe_cold';
  const compType = document.getElementById('thermal-comp-type').value || 'exterior_wall';

  for (const row of rows.children) {
    const selects = row.querySelectorAll('select');
    const inputs = row.querySelectorAll('input[type=number]');
    if (selects.length === 0 || inputs.length === 0) continue;
    const matType = selects[0].value;
    const value = parseFloat(inputs[0].value) || 0;

    if (matType === 'surface_inside') {
      // 内表面换热：R = 1/HI
      totalR += 1.0 / 8.7;
      layerInfo.push({ type: matType, R: 1/8.7 });
    } else if (matType === 'surface_outside') {
      // 外表面换热：R = 1/HO
      totalR += 1.0 / 23.0;
      layerInfo.push({ type: matType, R: 1/23.0 });
    } else {
      const lambda = materials[matType] || 0.04;
      const R = value / lambda;
      totalR += R;
      layerInfo.push({ type: matType, thickness: value, lambda, R });
    }
  }

  const K = 1.0 / totalR;
  const threshold = THERMAL_THRESHOLDS[climate][compType] || THERMAL_THRESHOLDS.severe_cold.exterior_wall;
  const passed = K <= threshold;

  // 渲染每层明细
  let detailHtml = '<table class="w-full border-collapse text-xs"><thead><tr class="bg-gray-100 border-b"><th class="py-1 text-left">层</th><th>厚度(m)</th><th>λ(W/m·K)</th><th>R(m²·K/W)</th></tr></thead><tbody>';
  layerInfo.forEach(l => {
    if (l.type === 'surface_inside') {
      detailHtml += '<tr><td>内表面换热</td><td>-</td><td>-</td><td>' + l.R.toFixed(4) + '</td></tr>';
    } else if (l.type === 'surface_outside') {
      detailHtml += '<tr><td>外表面换热</td><td>-</td><td>-</td><td>' + l.R.toFixed(4) + '</td></tr>';
    } else {
      detailHtml += '<tr><td>' + l.type + '</td><td>' + (l.thickness||'-') + '</td><td>' + (l.lambda||'-') + '</td><td>' + (l.R||'-').toFixed(4) + '</td></tr>';
    }
  });
  detailHtml += '</tbody></table>';

  const html = '<div class="mt-3 p-2 rounded ' + (passed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200') + ' border">' +
    '<p class="font-medium ' + (passed ? 'text-green-700' : 'text-red-700') + '">' +
    'K = ' + K.toFixed(4) + ' W/(m²·K) · R_total = ' + totalR.toFixed(4) + ' m²·K/W ' +
    (passed ? '✅ ≤ ' + threshold : '❌ > ' + threshold) + '</p>' +
    '<p class="text-xs text-gray-500">气候: ' + climateNames[climate] + ' · 构件: ' + compType + '</p>' +
    '</div>' + detailHtml;

  if (resultEl) {
    resultEl.innerHTML = html;
  }
}


// ── P46 结构荷载验算 ────────────────────────────────────────

// 各构件类型的结构参数（GB50009/GB50010/GB55008）
const STRUCTURAL_PARAMS = {
  floor_live:       { label: '楼面活荷载',       clause: 'GB50009-5.1.1',   unit: 'kN/㎡', threshold: { 住宅: 2.0, 办公: 2.5, 商业: 3.5, 图书馆: 4.0, 档案: 5.0, 车库: 2.5 },   op: '>=' },
  beam_reinforcement:{ label: '梁最小配筋率',     clause: 'GB50010-9.2.1',   unit: '%',     threshold: { 默认: 0.20 },                                                      op: '>=' },
  column_reinforcement:{label: '柱纵向配筋率下限',clause: 'GB50010-11.4.12', unit: '%',     threshold: { 抗震一级: 0.55, 抗震二级: 0.50, 抗震三级: 0.55, 抗震四级: 0.50 }, op: '>=' },
  foundation_depth:  { label: '基础最小埋深',     clause: 'GB50007-5.1.3',   unit: 'm',     threshold: { 默认: 0.50, 冻土区: 1.00 },                                       op: '>=' },
  slab_thickness:    { label: '楼板最小厚度',     clause: 'GB50010-9.1.2',   unit: 'mm',    threshold: { 默认: 80, 屋面板: 90 },                                          op: '>=' },
  beam_height:       { label: '梁高跨比',         clause: 'GB50010-9.2.3',   unit: '1/跨',  threshold: { 简支: 0.083, 连续: 0.067 },                                       op: '>=' },
  concrete_strength: { label: '混凝土最低强度等级',clause:'GB50010-4.1.2',   unit: 'MPa',   threshold: { 默认: 20, 预应力: 40 },                                          op: '>=' },
  seismic_grade:     { label: '抗震等级标注',     clause: 'GB55008-3.2.1',   unit: '有/无', threshold: { 必须: 1 },                                                        op: '==' },
  seismic_intensity: { label: '抗震设防烈度',     clause: 'GB55008-3.1.1',   unit: '度',    threshold: { 最小: 6 },                                                         op: '>=' },
  shear_wall_thickness:{label: '剪力墙最小厚度',  clause: 'GB55008-4.3.1',   unit: 'mm',    threshold: { 默认: 160, 框支层: 200 },                                         op: '>=' },
  pile_count:        { label: '柱下独立桩基数量', clause: 'GB55008-4.1.1',   unit: '根',    threshold: { 默认: 2, 条形桩基: 3 },                                          op: '>=' },
};
// 渲染结构违规列表（审查结果联动）
