/**
 * P93: 模型参数导出前端面板
 * 5 Tab: 原子函数 / 图层规则 / 施工图审查标准 / 样本 / 导出
 * 挂载在 page-model-params 上
 */

var MODEL_PARAMS_TABS = {
  functions: '原子函数参数',
  'layer-rules': '图层规则',
  'cd-items': '施工图审查标准',
  samples: '审查样本',
  export: '数据导出'
};

/**
 * 切换 tab：
 * - 所有 mptab-* 按钮：当前 tab 加 active-tab，其余移除
 * - 所有 mp-* 面板：当前 tab 移除 hidden，其余加 hidden
 * - 不操作 #mp-content（它是所有面板的公共父容器，不应被隐藏/显示）
 * - 不操作 #mp-skeleton（避免与异步加载打架）
 */
function switchModelParamTab(tab) {
  Object.keys(MODEL_PARAMS_TABS).forEach(function(t) {
    var btn = document.getElementById('mptab-' + t);
    var pane = document.getElementById('mp-' + t);
    if (btn) {
      if (t === tab) btn.classList.add('active-tab');
      else btn.classList.remove('active-tab');
    }
    if (pane) {
      if (t === tab) pane.classList.remove('hidden');
      else pane.classList.add('hidden');
    }
  });

  if (tab === 'functions') loadModelFunctions();
  else if (tab === 'layer-rules') loadModelLayerRules();
  else if (tab === 'cd-items') loadModelCDItems();
  else if (tab === 'samples') loadModelSamples();
  else if (tab === 'export') {
    // 无远程调用，直接显示导出按钮
  }
}

function _setOk(box, html) {
  if (box) {
    box.classList.remove('hidden');
    box.style.display = 'block';
    box.style.position = 'relative';
    box.style.zIndex = '10000';
    box.style.boxSizing = 'border-box';
    box.style.margin = '0';
    box.style.padding = '0';
    box.innerHTML = html;
    console.error('[P93-SETOK] id=' + box.id + ' classList=' + box.className + ' innerHTML length=' + box.innerHTML.length);
  }
}

function _setError(box, err) {
  var msg = (err && err.message) ? err.message : String(err);
  console.error('[P93] loader error:', msg);
  if (box) box.innerHTML = '<p class="text-red-400 text-sm">加载失败: ' + msg + '</p>';
}

async function loadModelFunctions() {
  var box = document.getElementById('mp-functions');
  try {
    var data = await apiGet('/api/v1/model-params/functions?limit=2000');
    var funcs = data.data || data.functions || [];
    if (funcs.length === 0) {
      _setOk(box, '<p class="text-gray-400 text-sm">暂无数据</p>');
      return;
    }
    var cats = {};
    funcs.forEach(function(f) {
      var c = f.category || 'other';
      cats[c] = (cats[c] || 0) + 1;
    });
    var summary = Object.keys(cats).slice(0, 12).map(function(c) {
      return '<span class="badge badge-sm badge-secondary">' + c + ' ' + cats[c] + '</span>';
    }).join(' ');

    var rows = funcs.slice(0, 80).map(function(f) {
      return '<tr>' +
        '<td class="py-1 px-2 text-xs text-mono">' + (f.func_id || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs">' + (f.title || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs"><span class="badge badge-xs">' + (f.category || '-') + '</span></td>' +
        '<td class="py-1 px-2 text-xs text-mono">' + (f.clause_id || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs">' + (f.operator || '-') + ' ' + (f.threshold || '-') + '</td>' +
      '</tr>';
    }).join('');

    _setOk(box,
      '<div class="flex gap-2 mb-2 flex-wrap">' + summary + '</div>' +
      '<div class="text-xs text-gray-400 mb-2">显示 ' + funcs.length + ' 个原子函数（前 80 条）</div>' +
      '<div class="overflow-auto max-h-96">' +
      '<table class="w-full text-sm">' +
      '<thead class="bg-gray-50 text-xs text-gray-500"><tr>' +
      '<th class="py-1 px-2">#</th><th class="py-1 px-2">标题</th><th class="py-1 px-2">分类</th>' +
      '<th class="py-1 px-2">规范条款</th><th class="py-1 px-2">判定条件</th>' +
      '</tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>');
  } catch (e) { _setError(box, e); }
}

async function loadModelLayerRules() {
  var box = document.getElementById('mp-layer-rules');
  try {
    var data = await apiGet('/api/v1/model-params/layer-rules');
    console.error('[P93-LR] apiGet returned:', JSON.stringify(data).slice(0,100));
    var rules = data.data || data.rules || [];
    console.error('[P93-LR] rules length:', rules.length, 'rules[0]:', JSON.stringify(rules[0]).slice(0,100));
    if (rules.length === 0) {
      _setOk(box, '<p class="text-gray-400 text-sm">暂无数据</p>');
      return;
    }
    console.error('[P93-LR] step1: about to filter/slice/map');
    var lr = rules.filter(function(r) { return r.source === 'LAYER_RULES'; }).length;
    console.error('[P93-LR] step2: lr=' + lr);
    var sl = rules.filter(function(r) { return r.source === 'SHORT_LAYER_RULES'; }).length;
    console.error('[P93-LR] step3: sl=' + sl);
    var rows = rules.slice(0, 60).map(function(r) {
      var cls = r.source === 'SHORT_LAYER_RULES' ? 'badge-secondary' : 'badge-primary';
      return '<tr>' +
        '<td class="py-1 px-2 text-xs text-mono">' + (r.pattern || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs">' + (r.entity_type || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs"><span class="badge badge-xs ' + cls + '">' + (r.source || '-') + '</span></td>' +
        '<td class="py-1 px-2 text-xs">' + (r.match_type || '-') + '</td>' +
      '</tr>';
    }).join('');

    console.error('[P93-LR] step4: rows length=' + rows.length + ' rows[0]=' + rows[0].slice(0,80));
    _setOk(box,
      '<div style="background:#ffffff;padding:8px;border:1px solid #e5e7eb;margin:4px;position:relative;z-index:9999;max-height:400px;overflow:auto">' +
      '<div class="text-xs text-gray-400 mb-2">' + rules.length + ' 条（LAYER_RULES: ' + lr + ' / SHORT: ' + sl + '）前 60 条</div>' +
      '<table class="w-full text-sm">' +
      '<thead class="bg-gray-50 text-xs text-gray-500"><tr>' +
      '<th class="py-1 px-2">关键字</th><th class="py-1 px-2">实体类型</th>' +
      '<th class="py-1 px-2">来源</th><th class="py-1 px-2">匹配方式</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>');
  } catch (e) { _setError(box, e); }
}

async function loadModelCDItems() {
  var box = document.getElementById('mp-cd-items');
  try {
    var data = await apiGet('/api/v1/model-params/cd-items');
    console.error('[P93-CD] apiGet returned:', JSON.stringify(data).slice(0,100));
    var items = data.data || data.items || [];
    console.error('[P93-CD] items length:', items.length, 'items[0]:', JSON.stringify(items[0]).slice(0,100));
    if (items.length === 0) {
      _setOk(box, '<p class="text-gray-400 text-sm">暂无数据</p>');
      return;
    }
    console.error('[P93-CD] step1: about to compute lvl');
    var lvl = { L1: 0, L2: 0, L3: 0 };
    items.forEach(function(i) { if (i.level in lvl) lvl[i.level]++; });
    console.error('[P93-CD] step2: lvl=' + JSON.stringify(lvl));
    var lvls = Object.keys(lvl).map(function(k) {
      var cls = k === 'L1' ? 'text-red-500' : (k === 'L2' ? 'text-orange-500' : 'text-green-500');
      return '<span class="' + cls + '">' + k + ': ' + lvl[k] + '</span>';
    }).join(' ');
    var rows = items.slice(0, 50).map(function(i) {
      return '<tr>' +
        '<td class="py-1 px-2 text-xs text-mono">' + (i.item_id || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs">' + (i.title || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs"><span class="badge badge-xs">' + (i.level || '-') + '</span></td>' +
        '<td class="py-1 px-2 text-xs">' + (i.major || '-') + '</td>' +
      '</tr>';
    }).join('');

    console.error('[P93-CD] step3: rows length=' + rows.length + ' rows[0]=' + rows[0].slice(0,80));
    _setOk(box,
      '<div style="background:#ffffff;padding:8px;border:1px solid #e5e7eb;margin:4px;position:relative;z-index:9999;max-height:400px;overflow:auto">' +
      '<div class="flex gap-3 mb-2 text-xs">' + lvls + '</div>' +
      '<table class="w-full text-sm">' +
      '<thead class="bg-gray-50 text-xs text-gray-500"><tr>' +
      '<th class="py-1 px-2">编码</th><th class="py-1 px-2">审查项</th>' +
      '<th class="py-1 px-2">等级</th><th class="py-1 px-2">专业</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>');
  } catch (e) { _setError(box, e); }
}

async function loadModelSamples() {
  var box = document.getElementById('mp-samples');
  try {
    var data = await apiGet('/api/v1/model-params/samples?limit=20');
    var samples = data.data || data.samples || [];
    if (samples.length === 0) {
      _setOk(box, '<p class="text-yellow-500 text-sm">暂无样本数据（需有审查记录后自动生成）</p>');
      return;
    }
    var cards = samples.slice(0, 10).map(function(s) {
      return '<div class="card p-2 mb-2">' +
        '<div class="text-xs text-gray-400">' + (s.created_at || '-') + '</div>' +
        '<div class="text-sm font-medium">' + (s.title || s.func_id || '样本') + '</div>' +
        '<div class="text-xs text-mono">' + (s.func_id || '-') + ' | ' + (s.dxf_file || '-') + '</div>' +
        '<div class="text-xs text-gray-500 mt-1">' + (s.query ? s.query.slice(0, 200) : '') + '</div>' +
      '</div>';
    }).join('');
    _setOk(box, '<div class="text-xs text-gray-400 mb-2">共 ' + samples.length + ' 条（前 10 条）</div>' + cards);
  } catch (e) { _setError(box, e); }
}

async function downloadModelExport(format) {
  try {
    var url = API_BASE() + '/api/v1/model-params/export?format=' + encodeURIComponent(format);
    window.open(url, '_blank');
    showToast('已开始下载 ' + format + ' 格式');
  } catch (e) {
    showToast('下载失败: ' + e.message);
  }
}
