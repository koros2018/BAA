/**
 * P92: 施工图审查深度标准前端面板
 * 加载 /api/v1/construction-review 列表 + 统计 + 渲染表格
 */

const CD_MAJOR_LABELS = {arch: '建筑', struct: '结构', mech: '暖通', elec: '电气', plumb: '给排水'};
const CD_LEVEL_COLORS = {L1: 'red', L2: 'orange', L3: 'green'};
const CD_METHOD_LABELS = {auto: '自动', manual: '人工', ai: 'AI'};
const CD_METHOD_ICONS = {auto: '🤖', manual: '👤', ai: '🧠'};

async function loadCDItems() {
  const search = (document.getElementById('cd-search')?.value || '').toLowerCase();
  const level = document.getElementById('cd-filter-level')?.value || 'all';
  const major = document.getElementById('cd-filter-major')?.value || 'all';
  const method = document.getElementById('cd-filter-method')?.value || 'all';

  // 显示骨架屏
  const skel = document.getElementById('cd-skeleton');
  const content = document.getElementById('cd-content');
  if (skel) skel.classList.remove('hidden');
  if (content) content.classList.add('hidden');

  const params = {};
  if (level !== 'all') params.level = level;
  if (major !== 'all') params.major = major;
  if (method !== 'all') params.method = method;

  const url = buildAPIUrl('/api/v1/construction-review', params);

  try {
    const data = await apiGet(url);
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');

    const items = data.items || [];
    let filtered = items;
    if (search) {
      filtered = items.filter(i =>
        i.item_id.toLowerCase().includes(search) ||
        i.title.toLowerCase().includes(search) ||
        i.description.toLowerCase().includes(search) ||
        (i.standard_ref || '').toLowerCase().includes(search)
      );
    }

    // 统计
    const totalEl = document.getElementById('cd-total');
    const l1El = document.getElementById('cd-l1');
    const l2El = document.getElementById('cd-l2');
    const l3El = document.getElementById('cd-l3');
    if (totalEl) totalEl.textContent = data.summary?.total || items.length;
    if (l1El) l1El.textContent = data.summary?.L1 || 0;
    if (l2El) l2El.textContent = data.summary?.L2 || 0;
    if (l3El) l3El.textContent = data.summary?.L3 || 0;

    // 过滤计数
    const fc = document.getElementById('cd-filter-count');
    if (fc) fc.textContent = filtered.length + ' 项' + (filtered.length < items.length ? ' / ' + items.length : '');

    // 渲染表格
    const tbody = document.getElementById('cd-list');
    if (!tbody) return;

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-gray-300">无匹配项</td></tr>';
      return;
    }

    let html = '';
    filtered.forEach((i, idx) => {
      const level = i.level || 'L1';
      const majorLabel = CD_MAJOR_LABELS[i.major] || i.major || '--';
      const methodLabel = CD_METHOD_LABELS[i.check_method] || i.check_method || '--';
      const methodIcon = CD_METHOD_ICONS[i.check_method] || '—';
      const funcId = i.func_id || '<span class="text-gray-400">—</span>';
      const color = CD_LEVEL_COLORS[level] || 'gray';
      html += '<tr class="border-b border-gray-50">' +
        '<td class="py-2 px-2 text-xs">' + (idx + 1) + '</td>' +
        '<td class="py-2 px-2 font-mono text-xs text-blue-600">' + i.item_id + '</td>' +
        '<td class="py-2 px-2 text-sm">' + i.title + '<br/><span class="text-xs text-gray-400">' + (i.description || '') + '</span></td>' +
        '<td class="py-2 px-2 font-mono text-xs text-gray-500">' + (i.standard_ref || '') + '</td>' +
        '<td class="py-2 px-2"><span class="px-2 py-0.5 bg-' + color + '-100 text-' + color + '-700 rounded text-xs">' + level + '</span></td>' +
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
      '<tr><td colspan="8" class="py-8 text-center text-red-400">加载失败: ' + e.message + '</td></tr>';
  }
}

// 初次进入施工图审查页时加载
document.addEventListener('DOMContentLoaded', function() {
  // 监听 page-cd 激活
  const observer = new MutationObserver(function() {
    const page = document.getElementById('page-cd');
    if (page && !page.classList.contains('hidden')) {
      loadCDItems();
    }
  });
  const contentEl = document.querySelector('#page-cd');
  if (contentEl) {
    observer.observe(contentEl, {attributes: true, attributeFilter: ['class']});
  }
});
