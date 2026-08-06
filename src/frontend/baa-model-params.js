/**
 * P93: 模型参数导出前端面板
 * 5 Tab: 原子函数 / 图层规则 / 施工图审查标准 / 样本 / 导出
 * 挂载在 page-model-params 上
 */

var MODEL_PARAMS_TABS = {
  functions: '原子函数参数',
  layer_rules: '图层规则',
  cd_items: '施工图审查标准',
  samples: '审查样本',
  export: '数据导出'
};

function switchModelParamTab(tab) {
  Object.keys(MODEL_PARAMS_TABS).forEach(function(t) {
    var btn = document.getElementById('mptab-' + t);
    var pane = document.getElementById('mp-' + t);
    if (btn) btn.classList.toggle('active-tab', t === tab);
    if (pane) pane.classList.toggle('hidden', t !== tab);
  });
  var skel = document.getElementById('mp-skeleton');
  var content = document.getElementById('mp-content');
  if (skel) skel.classList.remove('hidden');
  if (content) content.classList.add('hidden');

  if (tab === 'functions') loadModelFunctions();
  else if (tab === 'layer_rules') loadModelLayerRules();
  else if (tab === 'cd_items') loadModelCDItems();
  else if (tab === 'samples') loadModelSamples();
  else if (tab === 'export') {
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  }
}

async function loadModelFunctions() {
  var skel = document.getElementById('mp-skeleton');
  var content = document.getElementById('mp-content');
  var box = document.getElementById('mp-functions');
  try {
    var data = await apiGet('/api/v1/model-params/functions?limit=2000');
    var funcs = data.functions || [];
    if (funcs.length === 0) {
      box.innerHTML = '<p class="text-gray-400 text-sm">暂无数据</p>';
      return;
    }
    var cats = {};
    funcs.forEach(function(f) { cats[f.category || 'other'] = (cats[f.category || 'other'] || 0) + 1; });
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

    box.innerHTML =
      '<div class="flex gap-2 mb-2 flex-wrap">' + summary + '</div>' +
      '<div class="text-xs text-gray-400 mb-2">显示 ' + funcs.length + ' 个原子函数 (前 80 条)</div>' +
      '<div class="overflow-auto max-h-96">' +
      '<table class="w-full text-sm">' +
      '<thead class="bg-gray-50 text-xs text-gray-500"><tr>' +
      '<th class="py-1 px-2">#</th><th class="py-1 px-2">标题</th><th class="py-1 px-2">分类</th>' +
      '<th class="py-1 px-2">规范条款</th><th class="py-1 px-2">判定条件</th>' +
      '</tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>';

    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  } catch (e) {
    box.innerHTML = '<p class="text-red-400 text-sm">加载失败: ' + e.message + '</p>';
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  }
}

async function loadModelLayerRules() {
  var skel = document.getElementById('mp-skeleton');
  var content = document.getElementById('mp-content');
  var box = document.getElementById('mp-layer-rules');
  try {
    var data = await apiGet('/api/v1/model-params/layer-rules');
    var rules = data.rules || [];
    if (rules.length === 0) {
      box.innerHTML = '<p class="text-gray-400 text-sm">暂无数据</p>';
      return;
    }
    var lr = rules.filter(function(r) { return r.source === 'LAYER_RULES'; }).length;
    var sl = rules.filter(function(r) { return r.source === 'SHORT_LAYER_RULES'; }).length;
    var rows = rules.slice(0, 60).map(function(r) {
      var cls = r.source === 'SHORT_LAYER_RULES' ? 'badge-secondary' : 'badge-primary';
      return '<tr>' +
        '<td class="py-1 px-2 text-xs text-mono">' + (r.pattern || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs">' + (r.entity_type || '-') + '</td>' +
        '<td class="py-1 px-2 text-xs"><span class="badge badge-xs ' + cls + '">' + (r.source || '-') + '</span></td>' +
        '<td class="py-1 px-2 text-xs">' + (r.match_type || '-') + '</td>' +
      '</tr>';
    }).join('');

    box.innerHTML =
      '<div class="text-xs text-gray-400 mb-2">' + rules.length + ' 条 (LAYER_RULES: ' + lr + ' / SHORT: ' + sl + ') 前 60 条</div>' +
      '<div class="overflow-auto max-h-96">' +
      '<table class="w-full text-sm">' +
      '<thead class="bg-gray-50 text-xs text-gray-500"><tr>' +
      '<th class="py-1 px-2">关键字</th><th class="py-1 px-2">实体类型</th>' +
      '<th class="py-1 px-2">来源</th><th class="py-1 px-2">匹配方式</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>';

    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  } catch (e) {
    box.innerHTML = '<p class="text-red-400 text-sm">加载失败: ' + e.message + '</p>';
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  }
}

async function loadModelCDItems() {
  var skel = document.getElementById('mp-skeleton');
  var content = document.getElementById('mp-content');
  var box = document.getElementById('mp-cd-items');
  try {
    var data = await apiGet('/api/v1/model-params/cd-items');
    var items = data.items || [];
    if (items.length === 0) {
      box.innerHTML = '<p class="text-gray-400 text-sm">暂无数据</p>';
      return;
    }
    var lvl = { L1: 0, L2: 0, L3: 0 };
    items.forEach(function(i) { if (i.level in lvl) lvl[i.level]++; });
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

    box.innerHTML =
      '<div class="flex gap-3 mb-2 text-xs">' + lvls + '</div>' +
      '<div class="overflow-auto max-h-96">' +
      '<table class="w-full text-sm">' +
      '<thead class="bg-gray-50 text-xs text-gray-500"><tr>' +
      '<th class="py-1 px-2">编码</th><th class="py-1 px-2">审查项</th>' +
      '<th class="py-1 px-2">等级</th><th class="py-1 px-2">专业</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>';

    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  } catch (e) {
    box.innerHTML = '<p class="text-red-400 text-sm">加载失败: ' + e.message + '</p>';
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  }
}

async function loadModelSamples() {
  var skel = document.getElementById('mp-skeleton');
  var content = document.getElementById('mp-content');
  var box = document.getElementById('mp-samples');
  try {
    var data = await apiGet('/api/v1/model-params/samples?limit=20');
    var samples = data.samples || [];
    if (samples.length === 0) {
      box.innerHTML = '<p class="text-gray-400 text-sm">暂无样本数据（需有审查记录后自动生成）</p>';
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
    box.innerHTML =
      '<div class="text-xs text-gray-400 mb-2">共 ' + samples.length + ' 条（前 10 条）</div>' + cards;

    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  } catch (e) {
    box.innerHTML = '<p class="text-red-400 text-sm">加载失败: ' + e.message + '</p>';
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
  }
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
