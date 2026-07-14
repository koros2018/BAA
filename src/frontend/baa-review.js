// ── 概览页 ──────────────────────────────────────────────
async function loadDashboard() {
  try {
    const health = await apiGet('/health');
    document.getElementById('version-info').textContent = health.version + ' · 引擎就绪';
    document.getElementById('health-status').textContent = JSON.stringify(health, null, 2);
    loadReviewResults();
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

// ── 规范库 ──────────────────────────────────────────────
const SPEC_DATA = [
  {clause_id:'GB50016-5.5.18', name:'疏散楼梯净宽判定', description:'疏散楼梯净宽度不应小于1.2m', category:'dim', target:['staircase','stair']},
  {clause_id:'GB50016-6.1.1', name:'防火分区面积判定', description:'防火分区面积不应大于2500㎡', category:'dim', target:['fire_zone','room','floor']},
  {clause_id:'GB50016-7.1.1', name:'消防车道宽度判定', description:'消防车道宽度不应小于4m', category:'dim', target:['fire_lane','road','driveway']},
  {clause_id:'GB50016-5.5.17', name:'疏散距离判定', description:'疏散距离不应大于30m', category:'dist', target:['room','floor','space']},
  {clause_id:'GB50016-5.5.8', name:'安全出口数量判定', description:'安全出口不应少于2个', category:'count', target:['floor','fire_zone']},
  {clause_id:'GB50016-6.5.1', name:'防火门等级判定', description:'防火门等级应为甲级', category:'attr', target:['fire_door','door']},
  {clause_id:'GB50016-5.5.18', name:'疏散走道宽度判定', description:'疏散走道净宽度不应小于1.1m', category:'dim', target:['corridor','aisle','passage']},
  {clause_id:'GB50016-7.4.1', name:'避难层面积判定', description:'避难层净面积不宜小于5㎡/人', category:'area', target:['refuge_floor','refuge_area','floor']},
  {clause_id:'GB50016-5.5.12', name:'楼梯间存在判定', description:'建筑应设置楼梯间', category:'exist', target:['staircase','stair']},
  {clause_id:'GB50016-7.2.4', name:'窗净面积判定', description:'消防窗净面积不应小于1.0㎡', category:'dim', target:['fire_window','window']},
  {clause_id:'GB50016-5.5.19', name:'疏散门净宽判定', description:'人员密集场所疏散门净宽不应小于1.4m', category:'dim', target:['exit_door','door']},
  {clause_id:'GB50016-6.5.3', name:'防火卷帘宽度判定', description:'防火分隔防火卷帘宽度不应大于10m', category:'dim', target:['fire_curtain','curtain']},
  {clause_id:'GB50016-6.6.1', name:'管道井封堵判定', description:'管道井应每层用不燃材料封堵', category:'exist', target:['shaft','pipe_shaft','cable_shaft']},
  {clause_id:'GB50016-5.5.24', name:'剪刀楼梯分隔判定', description:'剪刀楼梯梯段间应设置防火隔墙', category:'exist', target:['scissor_staircase','staircase']},
  {clause_id:'GB50016-10.3.1', name:'疏散指示标志判定', description:'疏散走道和安全出口应设疏散指示标志', category:'exist', target:['exit_sign','sign','corridor']},
  {clause_id:'GB50016-8.3.1', name:'自动灭火系统判定', description:'一类高层应设置自动灭火系统', category:'exist', target:['sprinkler_system','sprinkler','fire_system']},
  {clause_id:'GB50016-8.4.1', name:'火灾报警系统判定', description:'一类高层应设置火灾自动报警系统', category:'exist', target:['fire_alarm','alarm_system','fire_system']},
  {clause_id:'GB50016-6.7.1', name:'保温材料等级判定', description:'保温材料应选用A或B1级', category:'attr', target:['insulation','wall_insulation','roof_insulation']},
  {clause_id:'GB50016-10.1.5', name:'应急照明照度判定', description:'疏散照明照度不应低于1.0lx', category:'dim', target:['evacuation_lighting','light','lighting']},
  // L3 新增（11个）
  {clause_id:'GB50016-3.4.1', name:'防火间距判定', description:'厂房之间防火间距不应小于12m', category:'dist', target:['building','factory','warehouse']},
  {clause_id:'GB50016-9.2.1', name:'排烟窗面积判定', description:'排烟窗净面积不应小于房间面积2%', category:'dim', target:['smoke_exhaust_window','window','room']},
  {clause_id:'GB50016-7.3.1', name:'消防电梯判定', description:'一类高层公共建筑应设消防电梯', category:'exist', target:['fire_elevator','elevator']},
  {clause_id:'GB50016-7.3.5', name:'消防电梯前室面积判定', description:'消防电梯前室面积不应小于6㎡', category:'area', target:['elevator_lobby','lobby','room']},
  {clause_id:'GB50016-5.5.17', name:'袋形走道长度判定', description:'袋形走道长度不应大于20m', category:'dist', target:['corridor','aisle','passage']},
  {clause_id:'GB50016-5.5.18', name:'疏散出口宽度判定', description:'疏散出口净宽度不应小于0.9m', category:'dim', target:['exit','exit_door','door']},
  {clause_id:'GB50016-6.5.1', name:'防火窗等级判定', description:'防火窗耐火极限不应低于1.0h', category:'attr', target:['fire_window','window']},
  {clause_id:'GB50016-8.2.1', name:'消防水箱判定', description:'一类高层应设消防水箱', category:'exist', target:['water_tank','fire_system']},
  {clause_id:'GB50016-8.1.3', name:'消防水池判定', description:'市政供水不足时应设消防水池', category:'exist', target:['water_reservoir','fire_system']},
  {clause_id:'GB50016-7.2.4', name:'消防救援窗面积判定', description:'消防救援窗口净面积不应小于1.0㎡', category:'dim', target:['rescue_window','window']},
  {clause_id:'GB50016-8.5.1', name:'应急广播判定', description:'一类高层应设应急广播系统', category:'exist', target:['emergency_broadcast','speaker','fire_system']},
];

async function loadSpecs() {
  const tbody = document.getElementById('spec-list');
  tbody.innerHTML = '';
  SPEC_DATA.forEach((s, i) => {
    const catLabels = {dim:'尺寸',exist:'存在性',attr:'属性',dist:'距离',count:'数量',area:'面积'};
    tbody.innerHTML += '<tr class="border-b border-gray-50">' +
      '<td class="py-2 px-2 text-xs">' + (i + 1) + '</td>' +
      '<td class="py-2 px-2 font-mono text-xs">' + s.clause_id + '</td>' +
      '<td class="py-2 px-2 text-sm">' + s.name + '<br/><span class="text-xs text-gray-400">' + s.description + '</span></td>' +
      '<td class="py-2 px-2"><span class="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs">L1</span></td>' +
      '<td class="py-2 px-2 text-xs">' + (catLabels[s.category] || s.category) + '</td>' +
      '<td class="py-2 px-2 font-mono text-xs max-w-32 truncate">' + s.target.join(', ') + '</td></tr>';
  });
}

// ── AI审图 ──────────────────────────────────────────────
async function runReview() {
  const select = document.getElementById('review-drawing-select');
  const id = select.value;
  if (!id) { alert('请选择已解析的图纸'); return; }
  const drawing = parsedDrawings.find(d => d.id === id);
  if (!drawing) { alert('图纸数据不存在'); return; }
  const bt = drawing.building_type;

  // 用缓存的数据直接提交审查，不需要重新上传文件
  const entities = drawing.entities || drawing.raw?.entities || [];
  if (entities.length === 0) { alert('该图纸没有解析出实体数据，请重新上传解析'); return; }

  const loading = document.getElementById('review-loading');
  loading.className = 'mt-3 text-sm text-gray-500';
  loading.innerHTML = '⏳ 正在审查...';

  try {
    const url = API_BASE() + '/review-from-data';
    const r = await fetch(url, {
      method: 'POST', headers: {...HEADERS(), 'Content-Type': 'application/json'},
      body: JSON.stringify({entities: entities, building_type: bt}),
    });
    const result = await r.json();
    loading.className = 'hidden';

    const summary = document.getElementById('review-summary');
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
          '<button onclick="downloadReviewPdf(\'' + pdfFileId + '\')" class="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">📄 下载PDF报告</button>' +
          '</div>';
      }

      const details = document.getElementById('review-details');
      details.innerHTML = '';
      // findings可能是数组或旧的ID列表
      let violations = [];
      if (Array.isArray(result.findings)) {
        violations = result.findings.filter(f => f.result === 'FAIL' && !f.is_duplicate);
      } else {
        violations = result.details || [];
      }

      // 存储到全局供分页使用
      window._reviewViolations = violations;
      window._reviewPageSize = 15;
      window._reviewPage = 1;
      window._reviewFilter = 'all';
      window._reviewSearch = '';

      function renderViolationPage() {
        const v = window._reviewViolations || [];
        const pageSize = window._reviewPageSize || 15;
        const page = window._reviewPage || 1;
        const filter = window._reviewFilter || 'all';
        const search = (window._reviewSearch || '').toLowerCase();

        let filtered = v;
        if (filter === 'critical') filtered = filtered.filter(f => f.severity === 'critical');
        else if (filter === 'major') filtered = filtered.filter(f => f.severity === 'major');
        else if (filter === 'minor') filtered = filtered.filter(f => f.severity !== 'critical' && f.severity !== 'major');
        if (search) filtered = filtered.filter(f =>
          (f.clause_title || '').toLowerCase().includes(search) ||
          (f.clause_id || '').toLowerCase().includes(search) ||
          (f.entity_type || '').toLowerCase().includes(search)
        );

        const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
        const start = (page - 1) * pageSize;
        const pageItems = filtered.slice(start, start + pageSize);

        let html = '<div class="flex items-center justify-between mb-2">' +
          '<p class="font-medium text-red-600">违规详情 (' + filtered.length + '/' + v.length + '项)</p>' +
          '<div class="flex gap-1 text-xs">' +
          '<select id="violation-filter" onchange="window._reviewFilter=this.value; window._reviewPage=1; renderViolationPage()" class="border rounded px-1 py-0.5 text-xs">' +
          '<option value="all">全部</option>' +
          '<option value="critical">严重</option>' +
          '<option value="major">主要</option>' +
          '<option value="minor">轻微</option>' +
          '</select>' +
          '<input id="violation-search" placeholder="搜索..." class="border rounded px-1 py-0.5 text-xs w-20" oninput="window._reviewSearch=this.value; window._reviewPage=1; renderViolationPage()" />' +
          '</div></div>';

        if (pageItems.length === 0) {
          html += '<div class="text-xs text-gray-400 p-2">无匹配项</div>';
        } else {
          pageItems.forEach(f => {
            const sevColor = f.severity === 'critical' ? 'red' : f.severity === 'major' ? 'orange' : 'yellow';
            const sevLabel = f.severity === 'critical' ? '严重' : f.severity === 'major' ? '主要' : '轻微';
            html +=
              '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs mb-1.5">' +
              '<div class="flex justify-between items-start">' +
              '<div><span class="font-medium">' + (f.clause_title || '') + '</span> <span class="text-gray-400">(' + (f.clause_id || '') + ')</span></div>' +
              '<div class="flex gap-1">' +
              '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span>' +
              '<span class="text-' + sevColor + '-600 font-medium">' + (f.result || '') + '</span></div></div>' +
              '<span class="text-gray-500">' + (f.entity_type || '') + ' · 实测: ' + (f.extracted_value || 0).toFixed(2) + ' · 要求: ' + (f.required_value || 0) + '</span><br/>' +
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

      // 在渲染违规列表前插入汇总表
      const summaryHtml = renderEvacCorridorSummary(violations);
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
  document.getElementById('review-panel-single').className = tab === 'single' ? '' : 'hidden';
  document.getElementById('review-panel-batch').className = tab === 'batch' ? '' : 'hidden';
  document.getElementById('review-panel-feedback').className = tab === 'feedback' ? '' : 'hidden';
  if (tab === 'feedback') {
    loadFeedbackStats();
    loadFeedbacks();
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
    alert('请填写任务 ID、规范条款和申诉理由');
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
    alert('申诉提交成功！ID: ' + data.feedback.feedback_id);
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
    alert('提交失败: ' + e.message);
  }
}

async function runBatchReview() {
  if (batchFiles.length === 0) {
    alert('请先选择至少一个图纸文件');
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
  if (!file1 || !file2) { alert('请选择两个版本的图纸文件'); return; }

  const bt = document.getElementById('diff-building-type').value;
  const std = document.getElementById('diff-standard').value;
  const loading = document.getElementById('diff-loading');
  loading.className = 'mt-3 text-sm text-gray-500';
  loading.innerHTML = '⏳ 正在审查并对比...';

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
      alert('对比失败: ' + (data.detail?.message || JSON.stringify(data)));
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
      alert('❌ ' + err.message);
    });
}

// ── 旧的对比函数（保留给其他页面引用） ──────────────────
let reviewResults = [];

function loadReviewResults() {
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

// ── 修正建议交互 ──────────────────────────────────────────
function confirmCorrection(reviewId, corrIdx, accepted) {
  const key = 'corr_' + reviewId + '_' + corrIdx;
  localStorage.setItem(key, accepted ? 'accepted' : 'rejected');
  // 刷新对比页面的修正建议
  const select = document.getElementById('compare-drawing-select');
  if (select && select.value) onCompareSelect();
}

