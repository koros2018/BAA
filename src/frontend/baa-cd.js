/**
 * P92: 施工图审查深度标准前端面板
 * 加载 /api/v1/construction-review 列表 + 统计 + 渲染表格
 */

const CD_MAJOR_LABELS = { arch: '建筑', struct: '结构', mech: '暖通', elec: '电气', plumb: '给排水' };
const CD_LEVEL_COLORS = { L1: 'red', L2: 'orange', L3: 'green' };
const CD_METHOD_LABELS = { auto: '自动', manual: '人工', ai: 'AI' };
const CD_METHOD_ICONS = { auto: '\uD83E\uDD16', manual: '\uD83D\uDC64', ai: '\uD83E\uDD88' };

async function loadCDItems() {
  var search = (document.getElementById('cd-search')?.value || '').toLowerCase();
  var level = document.getElementById('cd-filter-level')?.value || 'all';
  var major = document.getElementById('cd-filter-major')?.value || 'all';
  var method = document.getElementById('cd-filter-method')?.value || 'all';

  var skel = document.getElementById('cd-skeleton');
  var content = document.getElementById('cd-content');
  if (skel) skel.classList.remove('hidden');
  if (content) content.classList.add('hidden');

  // 拼接 query string
  var parts = [];
  if (level !== 'all') parts.push('level=' + encodeURIComponent(level));
  if (major !== 'all') parts.push('major=' + encodeURIComponent(major));
  if (method !== 'all') parts.push('method=' + encodeURIComponent(method));
  // apiGet 内部已经拼接 API_BASE()，这里只传相对路径
  var qs = parts.length ? '?' + parts.join('&') : '';
  var path = '/api/v1/construction-review' + qs;

  try {
    var data = await apiGet(path);
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');

    var items = data.items || [];
    var filtered = items;
    if (search) {
      filtered = items.filter(function(i) {
        return i.item_id.toLowerCase().includes(search) ||
          i.title.toLowerCase().includes(search) ||
          (i.description || '').toLowerCase().includes(search) ||
          (i.standard_ref || '').toLowerCase().includes(search);
      });
    }

    var totalEl = document.getElementById('cd-total');
    var l1El = document.getElementById('cd-l1');
    var l2El = document.getElementById('cd-l2');
    var l3El = document.getElementById('cd-l3');
    if (totalEl) totalEl.textContent = (data.summary?.total || items.length);
    if (l1El) l1El.textContent = (data.summary?.L1 || 0);
    if (l2El) l2El.textContent = (data.summary?.L2 || 0);
    if (l3El) l3El.textContent = (data.summary?.L3 || 0);

    var fc = document.getElementById('cd-filter-count');
    if (fc) fc.textContent = filtered.length + ' \u9879' + (filtered.length < items.length ? ' / ' + items.length : '');

    var tbody = document.getElementById('cd-list');
    if (!tbody) return;

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-gray-300">\u65E0\u5339\u914D\u9879</td></tr>';
      return;
    }

    var html = '';
    filtered.forEach(function(i, idx) {
      var lv = i.level || 'L1';
      var majorLabel = CD_MAJOR_LABELS[i.major] || i.major || '--';
      var methodLabel = CD_METHOD_LABELS[i.check_method] || i.check_method || '--';
      var methodIcon = CD_METHOD_ICONS[i.check_method] || '\u2014';
      var funcId = i.func_id || '<span class="text-gray-400">\u2014</span>';
      var color = CD_LEVEL_COLORS[lv] || 'gray';
      html += '<tr class="border-b border-gray-50">' +
        '<td class="py-2 px-2 text-xs">' + (idx + 1) + '</td>' +
        '<td class="py-2 px-2 font-mono text-xs text-blue-600">' + i.item_id + '</td>' +
        '<td class="py-2 px-2 text-sm">' + i.title + '<br/><span class="text-xs text-gray-400">' + (i.description || '') + '</span></td>' +
        '<td class="py-2 px-2 font-mono text-xs text-gray-500">' + (i.standard_ref || '') + '</td>' +
        '<td class="py-2 px-2"><span class="px-2 py-0.5 bg-' + color + '-100 text-' + color + '-700 rounded text-xs">' + lv + '</span></td>' +
        '<td class="py-2 px-2 text-xs">' + majorLabel + '</td>' +
        '<td class="py-2 px-2 text-xs">' + methodIcon + ' ' + methodLabel + '</td>' +
        '<td class="py-2 px-2 font-mono text-xs">' + funcId + '</td>' +
        '</tr>';
    });
    tbody.innerHTML = html;
  } catch (e) {
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
    document.getElementById('cd-list').innerHTML =
      '<tr><td colspan="8" class="py-8 text-center text-red-400">\u52A0\u8F7D\u5931\u8D25: ' + e.message + '</td></tr>';
  }
}

// 监听 page-cd 页面激活，自动加载
document.addEventListener('DOMContentLoaded', function() {
  var page = document.getElementById('page-cd');
  if (!page) return;
  var observer = new MutationObserver(function() {
    if (!page.classList.contains('hidden')) loadCDItems();
  });
  observer.observe(page, { attributes: true, attributeFilter: ['class'] });
});
