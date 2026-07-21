// ── 概览页 ──────────────────────────────────────────────
async function loadDashboard() {
  try {
    const health = await apiGet('/health');
    document.getElementById('version-info').textContent = health.version + ' · 引擎就绪';
    document.getElementById('health-status').textContent = JSON.stringify(health, null, 2);
    await loadReviewResults();
    const results = reviewResults;
    document.getElementById('home-stats').querySelectorAll('.stat-card')[0].querySelector('.text-2xl').textContent = results.length;
    document.getElementById('home-stats').querySelectorAll('.stat-card')[1].querySelector('.text-2xl').textContent = SPEC_DATA.length;
    if (results.length > 0) {
      const totalV = results.reduce((s, r) => s + (r.details?.length || 0), 0);
      const totalC = results.reduce((s, r) => s + (r.summary?.total_checks || 0), 0);
      const passRate = totalC > 0 ? Math.round((1 - totalV / totalC) * 100) + '%' : '--';
      document.getElementById('home-stats').querySelectorAll('.stat-card')[2].querySelector('.text-2xl').textContent = passRate;
      document.getElementById('home-stats').querySelectorAll('.stat-card')[3].querySelector('.text-2xl').textContent = results[0].drawingName;
    }
    renderRecentReviews();
    renderSpecFreqBars();
    renderViolationTypeBars();
  } catch (e) {
    document.getElementById('version-info').textContent = '⚠️ 服务未连接';
    document.getElementById('health-status').textContent = '连接失败: ' + e.message;
  }
}

function renderRecentReviews() {
  const el = document.getElementById('recent-reviews');
  if (!el) return;
  const results = reviewResults;
  if (results.length === 0) { el.innerHTML = '<div class="text-xs text-gray-400">暂无审查记录</div>'; return; }
  const recent = results.slice(0, 5);
  el.innerHTML = recent.map(r => {
    const v = r.details?.length || 0;
    const color = v === 0 ? 'green' : 'red';
    return '<div class="flex items-center justify-between py-1 border-b border-gray-50 last:border-0">' +
      '<span class="font-medium">' + r.drawingName + '</span>' +
      '<span class="text-' + color + '-600">' + v + ' 项违规</span></div>';
  }).join('');
}

function renderSpecFreqBars() {
  const el = document.getElementById('spec-freq-bars');
  if (!el || reviewResults.length === 0) return;
  const freq = {};
  reviewResults.forEach(r => (r.details || []).forEach(v => {
    const key = v.clause_id || '未知';
    freq[key] = (freq[key] || 0) + 1;
  }));
  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const maxVal = Math.max(...sorted.map(s => s[1]), 1);
  el.innerHTML = sorted.map(([k, v]) =>
    '<div class="flex items-center gap-2"><span class="w-24 truncate">' + k + '</span>' +
    '<div class="flex-1 bg-gray-100 rounded-full h-3"><div class="bg-blue-500 h-3 rounded-full" style="width:' + (v/maxVal*100) + '%"></div></div>' +
    '<span class="w-6 text-right">' + v + '</span></div>'
  ).join('');
}

function renderViolationTypeBars() {
  const el = document.getElementById('violation-type-bars');
  if (!el || reviewResults.length === 0) return;
  const freq = {};
  reviewResults.forEach(r => (r.details || []).forEach(v => {
    const key = v.severity === 'critical' ? '严重' : v.severity === 'major' ? '主要' : '轻微';
    freq[key] = (freq[key] || 0) + 1;
  }));
  const colors = {'严重': '#ef4444', '主要': '#f97316', '轻微': '#eab308'};
  const total = Object.values(freq).reduce((a, b) => a + b, 0) || 1;
  el.innerHTML = Object.entries(freq).map(([k, v]) =>
    '<div class="flex items-center gap-2"><span class="w-10">' + k + '</span>' +
    '<div class="flex-1 bg-gray-100 rounded-full h-3"><div class="h-3 rounded-full" style="width:' + (v/total*100) + '%;background:' + (colors[k] || '#6b7280') + '"></div></div>' +
    '<span class="w-6 text-right">' + v + '</span></div>'
  ).join('');
}

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
      summary.innerHTML =
        '<div class="grid grid-cols-4 gap-2 mb-3">' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + (vs.total_violations || 0) + '</div><div class="text-xs text-gray-400">违规</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold ' + (vs.critical > 0 ? 'text-red-600' : 'text-green-600') + '">' + (vs.critical || 0) + '</div><div class="text-xs text-gray-400">严重</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-gray-600">' + (vs.total_checks || 0) + '</div><div class="text-xs text-gray-400">总检查</div></div>' +
        '<div class="card p-2 text-center"><div class="text-lg font-bold text-gray-600">' + (result.elements?.length || 0) + '</div><div class="text-xs text-gray-400">构件</div></div>' +
        '</div>';

      if (result.summary?.entity_types) {
        summary.innerHTML += '<p class="text-xs text-gray-400 mb-2">构件分布:</p><div class="flex flex-wrap gap-1 mb-3">';
        for (const [type, count] of Object.entries(result.summary.entity_types)) {
          summary.innerHTML += '<span class="px-2 py-0.5 bg-gray-100 rounded text-xs">' + type + ': ' + count + '</span>';
        }
        summary.innerHTML += '</div>';
      }

      // PDF 下载按钮（仅当有 file_id 时可用）
      const pdfFileId = drawing.file_id;
      if (pdfFileId) {
        summary.innerHTML += '<div class="mt-3 flex gap-2">' +
          '<button onclick="downloadReviewPdf(\'' + pdfFileId + '\')" class="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">📄 PDF报告</button>' +
          '<button onclick="downloadReviewJSON()" class="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">📋 导出JSON</button>' +
          '</div>';
      }

      const details = document.getElementById('review-details');
      details.innerHTML = '';

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
        details.innerHTML += '<div class="grid grid-cols-3 gap-2 mb-3">';
        ['critical', 'major', 'minor'].forEach(sev => {
          const count = severityCounts[sev] || 0;
          const pct = totalViols > 0 ? (count / totalViols * 100).toFixed(0) : 0;
          details.innerHTML +=
            '<div class="card p-2 text-center">' +
            '<div class="text-lg font-bold ' + (sevTextColors[sev] || 'text-gray-600') + '">' + count + '</div>' +
            '<div class="text-xs text-gray-400">' + (sevLabels[sev] || sev) + '</div>' +
            '<div class="w-full bg-gray-100 rounded-full h-1.5 mt-1"><div class="' + (sevColors[sev] || 'bg-gray-400') + ' h-1.5 rounded-full" style="width:' + pct + '%"></div></div>' +
            '</div>';
        });
        details.innerHTML += '</div>';
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

        const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
        const start = (page - 1) * pageSize;
        const pageItems = filtered.slice(start, start + pageSize);

        const selVals = {all:'全部',critical:'严重',major:'主要',minor:'轻微'};
        let filterOpts = Object.entries(selVals).map(([k,v]) => '<option value="'+k+'"'+(filter===k?' selected':'')+'>'+v+'</option>').join('');

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
            const confLabel = conf >= 0.85 ? '高置信' : conf >= 0.6 ? '中置信' : '低置信';
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
              '<span class="text-gray-400">' + (f.explanation || '') + '</span>' +
              '</div>';
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
            '<th class="pb-1 pr-1">类型</th><th class="pb-1 pr-1">实体</th><th class="pb-1 pr-1">实测</th><th class="pb-1 pr-1">要求</th><th class="pb-1">判定</th></tr></thead><tbody>';
          evacViols.slice(0, 10).forEach(f => {
            const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
            html += '<tr class="border-b border-gray-50">' +
              '<td class="py-1 pr-1">' + (f.func_id || '') + '</td>' +
              '<td class="py-1 pr-1 truncate max-w-16" title="' + (f.entity_id || '') + '">' + (f.entity_type || '') + '</td>' +
              '<td class="py-1 pr-1">' + (f.extracted_value != null ? Number(f.extracted_value).toFixed(2) : '-') + '</td>' +
              '<td class="py-1 pr-1">' + (f.required_value != null ? f.required_value : '-') + '</td>' +
              '<td class="py-1"><span class="px-1 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + (f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微') + '</span></td></tr>';
          });
          if (evacViols.length > 10) html += '<tr><td colspan="5" class="pt-1 text-gray-400 text-center">… 还有 ' + (evacViols.length - 10) + ' 项</td></tr>';
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

      // 在渲染违规列表前插入汇总表（疏散/走廊/结构荷载）
      const summaryHtml = renderEvacCorridorSummary(violations) + renderStructuralSummary(violations);
      if (summaryHtml) {
        document.getElementById('review-details').insertAdjacentHTML('beforebegin', summaryHtml);
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
    renderThermalThresholds();
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

async function loadFeedbackStats() {
  const el = document.getElementById('fb-stats');
  if (!el) return;
  try {
    const data = await apiGet('/api/v1/feedbacks/stats');
    if (data.status !== 'success') throw new Error('加载失败');
    const s = data.stats;
    el.innerHTML = `
      <div class="grid grid-cols-2 gap-2">
        <div class="card p-2 text-xs">
          <p class="font-medium">📊 申诉统计</p>
          <p>总数: ${s.total}</p>
          <p>待审核: ${s.by_status.pending || 0}</p>
          <p>已接受: ${s.by_status.accepted || 0}</p>
          <p>已拒绝: ${s.by_status.rejected || 0}</p>
          <p>接受率: ${(s.accepted_rate * 100).toFixed(1)}%</p>
        </div>
        <div class="card p-2 text-xs">
          <p class="font-medium">📋 高频条款</p>
          ${Object.entries(s.by_clause || {}).slice(0, 5).map(([c, n]) =>
            `<p>${c}: ${n}条</p>`
          ).join('')}
        </div>
      </div>
    `;
  } catch (e) {
    el.textContent = '加载失败: ' + e.message;
  }
}

async function loadFeedbacks() {
  const el = document.getElementById('fb-list');
  if (!el) return;
  try {
    const data = await apiGet('/api/v1/feedbacks');
    if (data.status !== 'success') throw new Error('加载失败');
    if (data.feedbacks.length === 0) {
      el.innerHTML = '<p class="text-gray-400 text-center py-4">暂无申诉记录</p>';
      return;
    }
    el.innerHTML = data.feedbacks.map(fb => {
      const statusBadge = fb.status === 'accepted' ? 'bg-green-100 text-green-700'
        : fb.status === 'rejected' ? 'bg-red-100 text-red-700'
        : 'bg-yellow-100 text-yellow-700';
      const statusText = fb.status === 'accepted' ? '✅ 已接受'
        : fb.status === 'rejected' ? '❌ 已拒绝'
        : '⏳ 待审核';
      return `
        <div class="card p-2 text-xs">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-mono">${fb.feedback_id}</span>
            <span class="px-1.5 py-0.5 rounded text-xs ${statusBadge}">${statusText}</span>
          </div>
          <p class="font-medium">${fb.clause_id}</p>
          <p class="text-gray-500">${fb.reason || '无理由'}</p>
          ${fb.reviewed_by ? `<p class="text-gray-400">审核: ${fb.reviewed_by} - ${fb.review_comment || ''}</p>` : ''}
          <p class="text-gray-400 text-xs">${fb.created_at?.slice(0, 10)}</p>
        </div>
      `;
    }).join('');
  } catch (e) {
    el.innerHTML = '<p class="text-red-400 text-center py-4">加载失败: ' + e.message + '</p>';
  }
}

async function submitFeedback() {
  const taskId = document.getElementById('fb-task-id').value.trim();
  const clauseId = document.getElementById('fb-clause-id').value.trim();
  const entityId = document.getElementById('fb-entity-id').value.trim();
  const reason = document.getElementById('fb-reason').value.trim();
  const description = document.getElementById('fb-description').value.trim();
  const originalValue = document.getElementById('fb-original-value').value;
  const severity = document.getElementById('fb-severity').value;

  if (!taskId || !clauseId || !reason) {
    showToast('请填写任务 ID、规范条款和申诉理由', 'info');
    return;
  }

  try {
    const data = await apiFetch('/api/v1/feedbacks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        clause_id: clauseId,
        entity_id: entityId,
        entity_type: '',
        reason,
        description,
        original_value: originalValue ? parseFloat(originalValue) : null,
        severity,
      }),
    });

    if (!data.status) throw new Error('提交失败');
    showToast('申诉提交成功！ID: ' + data.feedback.feedback_id, 'success');
    document.getElementById('fb-task-id').value = '';
    document.getElementById('fb-clause-id').value = '';
    document.getElementById('fb-entity-id').value = '';
    document.getElementById('fb-reason').value = '';
    document.getElementById('fb-description').value = '';
    document.getElementById('fb-original-value').value = '';
    document.getElementById('fb-severity').value = '';
    loadFeedbackStats();
    loadFeedbacks();
  } catch (e) {
    showToast('提交失败: ' + e.message, 'error');
  }
}

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

    // 各文件违规详情
    let fileHtml = '<div class="card p-2 text-xs">';
    fileHtml += '<p class="font-medium text-sm mb-1">📋 各文件违规详情</p>';
    resp.results.forEach(r => {
      if (r.status === 'error') {
        fileHtml += `<div class="p-2 rounded bg-red-50 text-red-600 mb-1">❌ ${r.filename}: ${r.message}</div>`;
        return;
      }
      const s = r.summary;
      const sevColor = s.violations > 0 ? 'red' : 'green';
      fileHtml += `<div class="p-2 rounded bg-${sevColor}-50 mb-1">`;
      fileHtml += `<p class="font-medium">${r.filename} (${s.total_entities} 实体)</p>`;
      fileHtml += `<p class="text-xs">违规: <span class="text-${sevColor}-600 font-medium">${s.violations}</span> 项`;
      if (s.violation_by_clause) {
        const top = Object.entries(s.violation_by_clause).slice(0, 3);
        fileHtml += ' | 主要: ' + top.map(([k,v]) => `${k}(${v})`).join(', ');
      }
      fileHtml += '</p></div>';
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
function _onDiffFileSelect(inputId, labelId) {
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  if (!input || !label) return;
  input.addEventListener('change', function() {
    label.textContent = this.files && this.files[0] ? this.files[0].name : '';
  });
}
_onDiffFileSelect('diff-file1', 'diff-file1-name');
_onDiffFileSelect('diff-file2', 'diff-file2-name');

async function runDiffComparison() {
  const file1 = document.getElementById('diff-file1').files[0];
  const file2 = document.getElementById('diff-file2').files[0];
  if (!file1 || !file2) { showToast('请选择两个版本的图纸文件', 'info'); return; }

  const bt = document.getElementById('diff-building-type').value;
  const std = document.getElementById('diff-standard').value;
  const loading = document.getElementById('diff-loading');
  loading.className = 'mt-3';
  renderProgress(loading, '审查并对比', 20);

  try {
    const form = new FormData();
    form.append('file1', file1);
    form.append('file2', file2);

    const url = API_BASE() + '/review/compare?building_type=' + encodeURIComponent(bt) + '&standard=' + encodeURIComponent(std);
    const resp = await fetch(url, {
      method: 'POST',
      headers: HEADERS(),
      body: form,
    });
    const data = await resp.json();
    loading.className = 'hidden';

    if (resp.status !== 200) {
      showToast('对比失败: ' + (data.detail?.message || JSON.stringify(data)), 'error');
      return;
    }

    _diffResult = data;
    renderDiffResults(data);
  } catch (e) {
    loading.className = 'mt-3 text-sm text-red-500';
    loading.innerHTML = '❌ 请求失败: ' + e.message;
  }
}

function renderDiffResults(data) {
  const s = data.summary || {};
  const empty = document.getElementById('diff-empty');
  const results = document.getElementById('diff-results');
  empty.className = 'hidden';
  results.className = '';

  // 摘要卡片
  const summaryDiv = document.getElementById('diff-summary');
  const newC = s.new_violations || 0;
  const fixedC = s.fixed_violations || 0;
  const changedC = s.changed_violations || 0;
  const totalV1 = s.total_v1 || 0;
  const totalV2 = s.total_v2 || 0;

  summaryDiv.innerHTML = '' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-blue-600">' + totalV1 + ' → ' + totalV2 + '</div>' +
      '<div class="text-xs text-gray-400">违规数</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-green-600">' + newC + '</div>' +
      '<div class="text-xs text-gray-400">🆕 新增违规</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-emerald-600">' + fixedC + '</div>' +
      '<div class="text-xs text-gray-400">✅ 已修复</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold text-yellow-600">' + changedC + '</div>' +
      '<div class="text-xs text-gray-400">🔄 变化项</div>' +
    '</div>' +
    '<div class="card p-3 text-center">' +
      '<div class="text-lg font-bold ' + (newC === 0 ? 'text-green-600' : 'text-red-600') + '">' + (newC === 0 ? '✓ 合格' : newC + '项') + '</div>' +
      '<div class="text-xs text-gray-400">综合评估</div>' +
    '</div>';

  // 按 diff_type 分组渲染
  const items = data.items || [];
  const groups = { new: [], fixed: [], changed: [] };
  items.forEach(item => {
    const t = item.diff_type || 'new';
    if (groups[t]) groups[t].push(item);
  });

  ['new', 'fixed', 'changed'].forEach(type => {
    renderDiffItemPanel(type, groups[type] || []);
  });

  // 原始 JSON
  document.getElementById('diff-raw-json').textContent = JSON.stringify(data, null, 2);

  // 加载图纸可视化（违规叠加）
  loadDiffVisualization(data);

  // 默认选中新增tab
  switchDiffTab('new');
}

function renderDiffItemPanel(type, items) {
  const el = document.getElementById('diff-items-' + type);
  if (!el) return;
  if (items.length === 0) {
    const labels = { new: '🆕 无新增违规', fixed: '✅ 无已修复项', changed: '🔄 无变化项' };
    el.innerHTML = '<div class="text-xs text-gray-400 py-4 text-center">' + (labels[type] || '无差异项') + '</div>';
    return;
  }

  const typeLabels = { new: '新增', fixed: '修复', changed: '变化' };
  const typeColors = { new: 'red', fixed: 'green', changed: 'yellow' };
  const tc = typeColors[type] || 'gray';

  let html = '<div class="flex items-center gap-2 mb-2">' +
    '<span class="text-xs text-gray-500">共 ' + items.length + ' 项</span>' +
    '<span class="text-xs text-gray-400">|</span>' +
    '<span class="text-xs text-gray-400">严重: ' + items.filter(i => i.severity === 'critical').length + '</span>' +
    '<span class="text-xs text-gray-400">|</span>' +
    '<span class="text-xs text-gray-400">一般: ' + items.filter(i => i.severity === 'normal' || !i.severity).length + '</span>' +
    '</div>';

  html += '<table class="w-full text-xs">' +
    '<thead><tr class="text-left text-gray-400 border-b">' +
    '<th class="pb-1 pr-2">条款</th>' +
    '<th class="pb-1 pr-2">实体</th>' +
    '<th class="pb-1 pr-2">类型</th>';
  
  if (type === 'new') {
    html += '<th class="pb-1 pr-2">实测值</th><th class="pb-1 pr-2">要求值</th>';
  } else if (type === 'fixed') {
    html += '<th class="pb-1 pr-2">原实测值</th><th class="pb-1 pr-2">要求值</th>';
  } else {
    html += '<th class="pb-1 pr-2">旧值</th><th class="pb-1 pr-2">新值</th>';
  }
  
  html += '<th class="pb-1">严重度</th></tr></thead><tbody>';

  items.forEach(item => {
    const sevColor = item.severity === 'critical' ? 'red' : item.severity === 'normal' ? 'orange' : 'gray';
    const sevLabel = item.severity === 'critical' ? '严重' : item.severity === 'normal' ? '一般' : '轻微';
    const oldV = item.old_value != null ? Number(item.old_value).toFixed(2) : '-';
    const newV = item.new_value != null ? Number(item.new_value).toFixed(2) : '-';
    const reqV = item.old_required != null ? item.old_required : (item.new_required != null ? item.new_required : '-');

    html += '<tr class="border-b border-gray-50 hover:bg-gray-50">' +
      '<td class="py-1.5 pr-2"><span title="' + (item.clause_title || '') + '" class="cursor-help">' + (item.clause_id || '') + '</span></td>' +
      '<td class="py-1.5 pr-2 truncate max-w-20" title="' + (item.entity_id || '') + '">' + (item.entity_type || '-') + '</td>' +
      '<td class="py-1.5 pr-2">' + (item.entity_id ? item.entity_id.slice(0, 16) : '-') + '</td>';

    if (type === 'new') {
      html += '<td class="py-1.5 pr-2 text-red-600">' + newV + '</td><td class="py-1.5 pr-2">' + reqV + '</td>';
    } else if (type === 'fixed') {
      html += '<td class="py-1.5 pr-2 text-green-600 line-through">' + oldV + '</td><td class="py-1.5 pr-2">' + reqV + '</td>';
    } else {
      html += '<td class="py-1.5 pr-2 text-gray-400">' + oldV + '</td><td class="py-1.5 pr-2 text-yellow-600">' + newV + '</td>';
    }

    html += '<td class="py-1.5"><span class="px-1.5 py-0.5 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span></td></tr>';

    // 显示说明
    if (item.explanation) {
      html += '<tr class="border-b border-gray-50"><td colspan="7" class="pb-1.5 pl-4 text-gray-400 text-xs">💡 ' + item.explanation.slice(0, 120) + '</td></tr>';
    }
  });

  html += '</tbody></table>';
  el.innerHTML = html;
}

function switchDiffTab(tab) {
  ['new', 'fixed', 'changed'].forEach(t => {
    const panel = document.getElementById('diff-items-' + t);
    if (panel) panel.className = 'diff-items-panel' + (t === tab ? '' : ' hidden');
  });
  document.querySelectorAll('.diff-tab-btn').forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.className = 'diff-tab-btn px-3 py-1 rounded-lg font-medium ' +
      (isActive ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600');
  });
}

// 加载对比图纸可视化（违规叠加渲染）
function loadDiffVisualization(data) {
  const v1FileId = data.v1_file_id;
  const v2FileId = data.v2_file_id;
  const items = data.items || [];

  if (!v1FileId && !v2FileId) {
    document.getElementById('diff-vis-v1').innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无文件 ID，无法渲染</div>';
    document.getElementById('diff-vis-v2').innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无文件 ID，无法渲染</div>';
    return;
  }

  // 从 diff items 提取违规位置信息
  // entity_type 和 entity_id 提供位置线索，但无精确 x/y
  // 使用 overlay 端点，传入违规摘要信息
  const makeOverlayUrl = (fileId, label, isV1) => {
    if (!fileId) return null;
    // 按严重度分组统计
    const sevCounts = {};
    items.forEach(item => {
      if ((isV1 && item.diff_type === 'fixed') || (!isV1 && item.diff_type === 'new')) {
        const s = item.severity || 'major';
        if (!sevCounts[s]) sevCounts[s] = 0;
        sevCounts[s]++;
      }
    });
    return API_BASE() + '/render/' + encodeURIComponent(fileId) + '/overlay?violations=' +
      encodeURIComponent(JSON.stringify(items.slice(0, 50).map(item => ({
        entity_type: item.entity_type || 'unknown',
        severity: item.severity || 'major',
        clause_id: item.clause_id || '',
        x: 0, y: 0  // 后端会 fallback
      }))));
  };

  const v1Url = makeOverlayUrl(v1FileId, '版本1', true);
  const v2Url = makeOverlayUrl(v2FileId, '版本2', false);

  // 渲染 V1
  const v1El = document.getElementById('diff-vis-v1');
  if (v1Url) {
    v1El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">⏳ 加载图纸...</div>';
    v1El.innerHTML = '<img src="' + v1Url + '" class="w-full" alt="版本1图纸" style="max-height:400px" onerror="this.outerHTML=\'<div class=text-center py-8 text-gray-400 text-xs>⚠️ 图纸渲染失败</div>\'" />';
  } else {
    v1El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无渲染数据</div>';
  }

  // 渲染 V2
  const v2El = document.getElementById('diff-vis-v2');
  if (v2Url) {
    v2El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">⏳ 加载图纸...</div>';
    v2El.innerHTML = '<img src="' + v2Url + '" class="w-full" alt="版本2图纸" style="max-height:400px" onerror="this.outerHTML=\'<div class=text-center py-8 text-gray-400 text-xs>⚠️ 图纸渲染失败</div>\'" />';
  } else {
    v2El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无渲染数据</div>';
  }
}

function clearDiffResults() {
  document.getElementById('diff-file1').value = '';
  document.getElementById('diff-file2').value = '';
  document.getElementById('diff-file1-name').textContent = '';
  document.getElementById('diff-file2-name').textContent = '';
  document.getElementById('diff-results').className = 'hidden';
  document.getElementById('diff-empty').className = 'card text-center py-8 text-gray-300';
  document.getElementById('diff-empty').textContent = '上传两个版本的图纸后开始对比';
  _diffResult = null;
}

// ── PDF 下载 ──────────────────────────────────────────────
function downloadReviewPdf(fileId) {
  const url = API_BASE() + '/review/' + encodeURIComponent(fileId) + '/pdf';
  const key = getActiveKeyValue();
  const headers = key ? { 'Authorization': '***' + key } : {};

  // 用 fetch 触发下载（支持鉴权头）
  fetch(url, { headers })
    .then(resp => {
      if (!resp.ok) {
        return resp.json().then(d => { throw new Error(d.detail?.message || '下载失败 (' + resp.status + ')'); });
      }
      return resp.blob();
    })
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = '审查报告_' + fileId + '.pdf';
      a.click();
      URL.revokeObjectURL(a.href);
    })
    .catch(err => {
      showToast('❌ ' + err.message, 'error');
    });
}

// ── JSON 导出 ──────────────────────────────────────────────
function downloadReviewJSON() {
  const violations = window._reviewViolations || [];
  if (violations.length === 0) {
    showToast('没有可导出的审查结果', 'info');
    return;
  }
  const exportData = {
    exportTime: new Date().toISOString(),
    totalViolations: violations.length,
    violations: violations.map(v => ({
      entity_id: v.entity_id,
      entity_type: v.entity_type,
      clause_id: v.clause_id,
      clause_title: v.clause_title,
      severity: v.severity || 'major',
      result: v.result,
      extracted_value: v.extracted_value,
      required_value: v.required_value,
      difference: v.difference,
      explanation: v.explanation,
    })),
    violationByClause: {},
  };
  violations.forEach(v => {
    const cid = v.clause_id || 'unknown';
    exportData.violationByClause[cid] = (exportData.violationByClause[cid] || 0) + 1;
  });
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '审查结果_' + new Date().toISOString().slice(0,10) + '.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── 审查结果存储（localStorage + 后端持久化） ──────────
let reviewResults = [];

function loadReviewResults() {
  // 先尝试从后端 API 加载
  const apiBase = API_BASE();
  return fetch(apiBase + '/review/history?limit=200')
    .then(r => r.json())
    .then(data => {
      if (data && data.items && data.items.length > 0) {
        reviewResults = data.items;
        // 同时更新 localStorage 作为缓存
        try { localStorage.setItem('baa_review_results', JSON.stringify(reviewResults)); } catch(e) {}
        return;
      }
      // 后端无数据，回退到 localStorage
      fallbackLoadReviewResults();
      return Promise.resolve();
    })
    .catch(() => {
      // 后端不可用，回退到 localStorage
      fallbackLoadReviewResults();
    });
}

function fallbackLoadReviewResults() {
  try {
    const stored = localStorage.getItem('baa_review_results');
    if (stored) reviewResults = JSON.parse(stored);
  } catch(e) { reviewResults = []; }
}

function refreshCompareDrawingSelect() {
  const select = document.getElementById('compare-drawing-select');
  if (!select) { /* 对比页已改用 Diff 模式 */ return; }
  select.innerHTML = '<option value="">— 选择已审查图纸 —</option>';
  reviewResults.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r.id;
    opt.textContent = r.drawingName + ' (' + (r.buildingType === 'civil' ? '民用' : '工业') + ') - ' + (r.details?.length || 0) + '项违规';
    select.appendChild(opt);
  });
}

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

    // 详情提示
    const hints = violClauses[t];
    if (hints && hints.length > 0) {
      ctx.fillStyle = '#6b7280';
      ctx.font = '7px sans-serif';
      ctx.textAlign = 'center';
      hints.slice(0, 2).forEach((h, hi) => {
        ctx.fillText(h.length > 20 ? h.slice(0,18) + '..' : h, cx, cy + 12 + hi * 10);
      });
    }
  });
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
    
    sorted.forEach(f => {
      const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
      const sevLabel = f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微';
      violationsDiv.innerHTML +=
        '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs mb-1.5">' +
        '<div class="flex justify-between items-start">' +
        '<div><span class="font-medium">' + (f.clause_title || '') + '</span> <span class="text-gray-400">(' + (f.clause_id || '') + ')</span></div>' +
        '<div class="flex gap-1">' +
        '<span class="px-1 py-0.5 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span>' +
        '<span class="text-' + sevColor + '-600 font-medium">' + f.result + '</span></div></div>' +
        '<span class="text-gray-500">' + (f.entity_type || '') + ' · 实测: ' + (f.extracted_value || 0).toFixed(2) + ' · 要求: ' + (f.required_value || 0) + '</span><br/>' +
        '<span class="text-gray-400">' + (f.explanation || '') + '</span>' +
        '</div>';
    });
  }
  
  // 可视化叠加
  renderViolationOverlay(r);
  
  // 修正建议
  const corrDiv = document.getElementById('compare-corrections');
  corrDiv.innerHTML = '';
  if (corrs.length === 0) {
    corrDiv.innerHTML = '<div class="text-xs text-gray-400">无修正建议</div>';
  } else {
    corrs.slice(0, 10).forEach((c, ci) => {
      const pColor = c.priority === 'high' ? 'red' : c.priority === 'medium' ? 'yellow' : 'gray';
      const pLabel = c.priority === 'high' ? '高优先级' : c.priority === 'medium' ? '中优先级' : '低优先级';
      const statusKey = 'corr_' + r.id + '_' + ci;
      const savedStatus = localStorage.getItem(statusKey);
      const accepted = savedStatus === 'accepted';
      const rejected = savedStatus === 'rejected';
      const statusBadge = accepted ? '<span class="text-green-600 text-xs">✅ 已确认</span>' : rejected ? '<span class="text-red-400 text-xs">❌ 已拒绝</span>' : '';
      corrDiv.innerHTML +=
        '<div class="p-2 bg-green-50 rounded text-xs mb-1.5 ' + (rejected ? 'opacity-50' : '') + '">' +
        '<div class="flex justify-between items-start">' +
        '<div><span class="font-medium">' + (c.clause_title || '') + '</span> ' + statusBadge + '</div>' +
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + pColor + '-100 text-' + pColor + '-800">' + pLabel + '</span></div>' +
        '<div class="text-gray-500">操作: ' + (c.action || '') + '</div>' +
        '<div class="text-gray-700 mt-1">' + (c.recommendation || '') + '</div>' +
        '<div class="flex gap-1 mt-1.5">' +
        '<button onclick="confirmCorrection(\'' + r.id + '\',' + ci + ',true)" class="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs hover:bg-green-200 ' + (accepted ? 'opacity-50' : '') + '" ' + (accepted ? 'disabled' : '') + '>✅ 确认</button>' +
        '<button onclick="confirmCorrection(\'' + r.id + '\',' + ci + ',false)" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200 ' + (rejected ? 'opacity-50' : '') + '" ' + (rejected ? 'disabled' : '') + '>❌ 拒绝</button>' +
        '</div></div>';
    });
  }

  // 修正后预览
  renderAfterPreview(r);
}

// ── AI 修正建议（P41） ───────────────────────────────────
async function generateCorrectionSuggestions() {
  const result = window._currentReviewResult;
  const entities = window._currentReviewEntities;
  if (!result || !entities) {
    showToast('请先运行审查', 'info'); return;
  }

  const findings = (result.findings || []).filter(f => f.result === 'FAIL' && !f.is_duplicate);
  if (findings.length === 0) {
    document.getElementById('correction-results').innerHTML = '<div class="text-green-600">✅ 无违规，无需修正建议</div>';
    return;
  }

  const panel = document.getElementById('review-correction-panel');
  const loading = document.getElementById('correction-loading');
  const resultsDiv = document.getElementById('correction-results');
  const btn = document.getElementById('correction-generate-btn');
  const modeSelect = document.getElementById('correction-mode-select');

  panel.className = panel.className.replace(/hidden/g, '').trim();
  loading.className = '';
  resultsDiv.innerHTML = '';
  btn.disabled = true;
  btn.textContent = '...';

  try {
    const mode = modeSelect.value;
    const r = await fetch(API_BASE() + '/correction/suggestions', {
      method: 'POST',
      headers: {...HEADERS(), 'Content-Type': 'application/json'},
      body: JSON.stringify({findings: findings, entities: entities, mode: mode}),
    });
    const data = await r.json();
    loading.className = 'hidden';

    if (!data.suggestions || data.suggestions.length === 0) {
      resultsDiv.innerHTML = '<div class="text-gray-500">未生成修正建议（规则引擎无匹配）</div>';
      return;
    }

    // 按优先级排序
    const priorityOrder = {high: 0, medium: 1, low: 2};
    const sorted = data.suggestions.slice().sort((a, b) => (priorityOrder[a.priority] ?? 3) - (priorityOrder[b.priority] ?? 3));

    let html = '<p class="mb-1 text-gray-500">共 ' + sorted.length + ' 条建议（' + mode + ' 模式）</p>';
    for (const s of sorted) {
      const pColor = s.priority === 'high' ? 'red' : s.priority === 'medium' ? 'orange' : 'yellow';
      const pLabel = s.priority === 'high' ? '🔴 高' : s.priority === 'medium' ? '🟠 中' : '🟡 低';
      html += '<div class="p-1.5 bg-gray-50 rounded border-l-2 border-' + pColor + '-400">';
      html += '<p class="font-medium"><span class="text-' + pColor + '-600">' + pLabel + '</span> [' + s.clause_id + '] ' + s.description + '</p>';
      html += '<p class="text-gray-600 mt-0.5">💡 ' + s.recommendation + '</p>';
      if (Object.keys(s.parameters || {}).length > 0) {
        html += '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(s.parameters) + '</p>';
      }
      html += '</div>';
    }
    resultsDiv.innerHTML = html;
  } catch (e) {
    loading.className = 'hidden';
    resultsDiv.innerHTML = '<div class="text-red-600">生成失败: ' + (e.message || e) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = '生成';
  }
}

// ── 修正建议交互 ──────────────────────────────────────────
function confirmCorrection(reviewId, corrIdx, accepted) {
  const key = 'corr_' + reviewId + '_' + corrIdx;
  localStorage.setItem(key, accepted ? 'accepted' : 'rejected');
  // 刷新对比页面的修正建议
  const select = document.getElementById('compare-drawing-select');
  if (select && select.value) onCompareSelect();
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

function onThermalCompTypeChange() {
  const compType = document.getElementById('thermal-comp-type').value;
  document.getElementById('thermal-thickness').value = DEFAULT_THERMAL_THICKNESS[compType] || 50;
}

function renderThermalThresholds() {
  const el = document.getElementById('thermal-thresholds');
  if (!el) return;
  let html = '<table class="w-full"><thead><tr class="text-gray-400 border-b">' +
    '<th class="text-left py-1">气候带</th><th>外墙</th><th>屋顶</th><th>地面</th><th>外窗</th></tr></thead><tbody>';
  const climateNames = { severe_cold:'严寒', cold:'寒冷', hot_cold:'夏热冬冷', hot_warm:'夏热冬暖' };
  for (const [key, thresholds] of Object.entries(THERMAL_THRESHOLDS)) {
    html += '<tr class="border-b"><td class="py-1">' + climateNames[key] + '</td>';
    for (const comp of ['exterior_wall','roof','ground_floor','exterior_window']) {
      html += '<td class="text-center">' + thresholds[comp].toFixed(2) + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

// 计算传热系数 K 值：调用后端 /api/v1/review/thermal/k-value API
async function computeThermalK() {
  const compType = document.getElementById('thermal-comp-type').value;
  const materialKey = document.getElementById('thermal-material').value;
  const thicknessMm = parseFloat(document.getElementById('thermal-thickness').value);
  const climate = document.getElementById('thermal-climate').value;
  const resultDiv = document.getElementById('thermal-result');

  if (isNaN(thicknessMm) || thicknessMm <= 0) {
    resultDiv.innerHTML = '<span class="text-red-600">厚度无效</span>';
    return;
  }

  resultDiv.innerHTML = '<span class="text-gray-400">⏳ 计算中...</span>';

  try {
    const data = await fetch(API_BASE() + '/api/v1/review/thermal/k-value', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compType, material: materialKey, thicknessMm, climate }),
    }).then(r => r.json());

    if (data.status !== 'success') {
      resultDiv.innerHTML = '<span class="text-red-600">后端返回异常</span>';
      return;
    }

    const pass = data.passed;
    let html = '';
    html += '<div class="mt-2 p-2 ' + (pass ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200') + ' rounded">';
    html += '<p class="font-medium ' + (pass ? 'text-green-700' : 'text-red-700') + '">';
    html += 'K = ' + data.K + ' W/(m²·K) ' + (pass ? '✅ ≤ ' : '❌ > ') + data.threshold;
    html += '</p>';
    html += '<p>材料: ' + data.material + ' (λ=' + data['lambda'] + ') · 厚度: ' + data.thicknessMm + 'mm · R=' + data.R + ' m²·K/W</p>';

    if (!pass) {
      html += '<p class="text-orange-600 mt-1">→ 改用当前材料需厚度 ≥ ' + data.requiredThicknessMm + 'mm（当前差 ' + data.additionalThicknessMm + 'mm）</p>';
    } else {
      const climateLabel = { severe_cold:'严寒', cold:'寒冷', hot_cold:'夏热冬冷', hot_warm:'夏热冬暖' }[data.climate] || data.climate;
      html += '<p class="text-gray-500 mt-1">→ 满足 GB55015-3.2.2 ' + climateLabel + ' 要求</p>';
    }
    html += '</div>';
    resultDiv.innerHTML = html;

    // 缓存最近结果到 localStorage 供热工审查结果面板引用
    try { localStorage.setItem('baa_last_thermal_result', JSON.stringify(data)); } catch(e) {}
  } catch (e) {
    resultDiv.innerHTML = '<span class="text-red-600">计算失败: ' + (e.message || e) + '</span>';
  }
}

// 渲染热工违规列表
function renderThermalViolations(thermalViolations) {
  const el = document.getElementById('thermal-review-list');
  if (!el) return;
  if (!thermalViolations || thermalViolations.length === 0) {
    el.innerHTML = '<span class="text-gray-400">✅ 单图审查后自动展示热工违规项</span>';
    return;
  }
  let html = '';
  const colorMap = { THERM: 'orange', EXIST: 'red' };
  thermalViolations.forEach(f => {
    const funcId = f.func_id || 'THERM-xxx';
    const title = f.clause_title || f.description || '未知条款';
    const clauseId = f.clause_id || '';
    const actual = f.extracted_value || f.actual_value || '?';
    const required = f.required_value || f.threshold || '?';
    const isFail = f.result === 'FAIL';
    html += '<div class="p-1.5 rounded ' + (isFail ? 'bg-red-50 border-l-2 border-red-400' : 'bg-green-50 border-l-2 border-green-400') + ' mb-1">';
    html += '<p class="font-medium ' + (isFail ? 'text-red-700' : 'text-green-700') + '">' + funcId + '</p>';
    html += '<p class="text-gray-600">' + title + '</p>';
    html += '<p class="text-xs text-gray-500">实测: ' + (typeof actual === 'number' ? actual.toFixed(3) : actual) + ' · 要求: ' + (typeof required === 'number' ? required.toFixed(3) : required) + ' · [' + clauseId + ']</p>';
    html += '</div>';
  });
  el.innerHTML = html;
}

// 页面加载后渲染阈值表
renderThermalThresholds();
renderMultiLayerEditor();

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

function renderStructuralThresholds() {
  const el = document.getElementById('structural-thresholds');
  if (!el) return;
  let html = '<table class="w-full"><thead><tr class="text-gray-400 border-b">' +
    '<th class="text-left py-1">构件</th><th>要求</th><th>单位</th><th>规范</th></tr></thead><tbody>';
  for (const [key, p] of Object.entries(STRUCTURAL_PARAMS)) {
    const threshText = Object.entries(p.threshold).map(([k, v]) => k + ':' + v).join(' / ');
    html += '<tr class="border-b"><td class="py-1">' + p.label + '</td>';
    html += '<td class="text-center">' + p.op + ' ' + threshText + '</td>';
    html += '<td class="text-center">' + p.unit + '</td>';
    html += '<td class="text-gray-500">' + p.clause + '</td></tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

function onStructuralCompTypeChange() {
  // 重置为默认值
  const type = document.getElementById('structural-comp-type').value;
  const p = STRUCTURAL_PARAMS[type];
  if (p) {
    const firstKey = Object.keys(p.threshold)[0];
    document.getElementById('structural-value').value = p.threshold[firstKey];
  }
}

async function computeStructuralCheck() {
  const compType = document.getElementById('structural-comp-type').value;
  const value = parseFloat(document.getElementById('structural-value').value);
  const note = document.getElementById('structural-note').value;
  const resultDiv = document.getElementById('structural-result');

  if (isNaN(value)) {
    resultDiv.innerHTML = '<span class="text-red-600">输入值无效</span>';
    return;
  }

  const p = STRUCTURAL_PARAMS[compType];
  if (!p) return;

  // 选择适用阈值：优先按备注匹配，否则取第一个
  let activeThreshold = null;
  let activeThresholdLabel = '';
  for (const [label, t] of Object.entries(p.threshold)) {
    if (note && note.includes(label)) {
      activeThreshold = t;
      activeThresholdLabel = label;
      break;
    }
  }
  if (activeThreshold === null) {
    const keys = Object.keys(p.threshold);
    activeThreshold = p.threshold[keys[0]];
    activeThresholdLabel = keys[0];
  }

  let passed;
  if (p.op === '>=') passed = value >= activeThreshold;
  else if (p.op === '<=') passed = value <= activeThreshold;
  else if (p.op === '==') passed = value === activeThreshold;
  else if (p.op === '>')  passed = value > activeThreshold;
  else if (p.op === '<')  passed = value < activeThreshold;
  else passed = value === activeThreshold;

  const sign = p.op === '>=' ? '≥' : p.op === '<=' ? '≤' : p.op === '==' ? '=' : p.op;

  let html = '<div class="mt-2 p-2 ' + (passed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200') + ' rounded">';
  html += '<p class="font-medium ' + (passed ? 'text-green-700' : 'text-red-700') + '">';
  html += p.label + ': ' + value + ' ' + p.unit + ' ' + (passed ? '✅ ' : '❌ ') + sign + ' ' + activeThreshold + ' ' + p.unit;
  html += '</p>';
  html += '<p class="text-xs text-gray-500">规范: ' + p.clause + ' · 适用条件: ' + activeThresholdLabel + '</p>';
  if (!passed) {
    html += '<p class="text-orange-600 text-xs mt-1">→ 当前值不满足规范要求，建议修正至 ' + sign + ' ' + activeThreshold + ' ' + p.unit + '</p>';
  }
  html += '</div>';
  resultDiv.innerHTML = html;
}

// 渲染结构违规列表（审查结果联动）
function renderStructuralViolations(structuralViolations) {
  const el = document.getElementById('structural-review-list');
  if (!el) return;
  if (!structuralViolations || structuralViolations.length === 0) {
    el.innerHTML = '<span class="text-gray-400">✅ 单图审查后自动展示结构违规项</span>';
    return;
  }
  let html = '';
  structuralViolations.forEach(f => {
    const funcId = f.func_id || 'STR-xxx';
    const title = f.clause_title || f.description || '未知条款';
    const clauseId = f.clause_id || '';
    const actual = f.extracted_value || f.actual_value || '?';
    const required = f.required_value || f.threshold || '?';
    const isFail = f.result === 'FAIL';
    html += '<div class="p-1.5 rounded ' + (isFail ? 'bg-red-50 border-l-2 border-red-400' : 'bg-green-50 border-l-2 border-green-400') + ' mb-1">';
    html += '<p class="font-medium ' + (isFail ? 'text-red-700' : 'text-green-700') + '">' + funcId + '</p>';
    html += '<p class="text-gray-600">' + title + '</p>';
    html += '<p class="text-xs text-gray-500">实测: ' + (typeof actual === 'number' ? actual.toFixed(3) : actual) + ' · 要求: ' + (typeof required === 'number' ? required.toFixed(3) : required) + ' · [' + clauseId + ']</p>';
    html += '</div>';
  });
  el.innerHTML = html;
}
