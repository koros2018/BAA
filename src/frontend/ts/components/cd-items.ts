// ── P123 Step 6: 施工图审查深度标准组件 ──────────────────
// 从 baa-cd.js 迁入 (103 行)
// 加载 /api/v1/construction-review 列表 + 筛选 + 渲染表格

import { apiGet } from '../core/api-client';

const CD_MAJOR_LABELS: Record<string, string> = {
  arch: '建筑',
  struct: '结构',
  mech: '暖通',
  elec: '电气',
  plumb: '给排水',
};
const CD_LEVEL_COLORS: Record<string, string> = {
  L1: 'red',
  L2: 'orange',
  L3: 'green',
};
const CD_METHOD_LABELS: Record<string, string> = {
  auto: '自动',
  manual: '人工',
  ai: 'AI',
};
const CD_METHOD_ICONS: Record<string, string> = {
  auto: '\uD83E\uDD16',
  manual: '\uD83D\uDC64',
  ai: '\uD83E\uDD88',
};

interface CDItem {
  item_id: string;
  title: string;
  description?: string;
  standard_ref?: string;
  level?: string;
  major?: string;
  check_method?: string;
  func_id?: string;
}

async function loadCDItems(): Promise<void> {
  const search = ((document.getElementById('cd-search') as HTMLInputElement | null)?.value || '').toLowerCase();
  const level = (document.getElementById('cd-filter-level') as HTMLSelectElement | null)?.value || 'all';
  const major = (document.getElementById('cd-filter-major') as HTMLSelectElement | null)?.value || 'all';
  const method = (document.getElementById('cd-filter-method') as HTMLSelectElement | null)?.value || 'all';

  const skel = document.getElementById('cd-skeleton') as HTMLElement | null;
  const content = document.getElementById('cd-content') as HTMLElement | null;
  if (skel) skel.classList.remove('hidden');
  if (content) content.classList.add('hidden');

  const parts: string[] = [];
  if (level !== 'all') parts.push(`level=${encodeURIComponent(level)}`);
  if (major !== 'all') parts.push(`major=${encodeURIComponent(major)}`);
  if (method !== 'all') parts.push(`method=${encodeURIComponent(method)}`);
  const qs = parts.length ? `?${parts.join('&')}` : '';
  const path = `/api/v1/construction-review${qs}`;

  try {
    const data = await apiGet(path) as { summary?: { total?: number; L1?: number; L2?: number; L3?: number }; items?: any[] };
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');

    const items = (data.items as CDItem[]) || [];
    let filtered = items;
    if (search) {
      filtered = items.filter((i) =>
        i.item_id.toLowerCase().includes(search) ||
        i.title.toLowerCase().includes(search) ||
        (i.description || '').toLowerCase().includes(search) ||
        (i.standard_ref || '').toLowerCase().includes(search),
      );
    }

    const totalEl = document.getElementById('cd-total') as HTMLElement | null;
    const l1El = document.getElementById('cd-l1') as HTMLElement | null;
    const l2El = document.getElementById('cd-l2') as HTMLElement | null;
    const l3El = document.getElementById('cd-l3') as HTMLElement | null;
    if (totalEl) totalEl.textContent = String(data.summary?.total ?? items.length);
    if (l1El) l1El.textContent = String((data.summary as Record<string, number>).L1 ?? 0);
    if (l2El) l2El.textContent = String((data.summary as Record<string, number>).L2 ?? 0);
    if (l3El) l3El.textContent = String((data.summary as Record<string, number>).L3 ?? 0);

    const fc = document.getElementById('cd-filter-count') as HTMLElement | null;
    if (fc) fc.textContent = `${filtered.length} \u9879${filtered.length < items.length ? ' / ' + items.length : ''}`;

    const tbody = document.getElementById('cd-list') as HTMLElement | null;
    if (!tbody) return;

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-gray-300">\u65E0\u5339\u914D\u9879</td></tr>';
      return;
    }

    tbody.innerHTML = filtered
      .map((i, idx) => {
        const lv = i.level || 'L1';
        const majorLabel = CD_MAJOR_LABELS[i.major || ''] || i.major || '--';
        const methodLabel = CD_METHOD_LABELS[i.check_method || ''] || i.check_method || '--';
        const methodIcon = CD_METHOD_ICONS[i.check_method || ''] || '\u2014';
        const funcId = i.func_id || '<span class="text-gray-400">\u2014</span>';
        const color = CD_LEVEL_COLORS[lv] || 'gray';
        return `<tr class="border-b border-gray-50">
          <td class="py-2 px-2 text-xs">${idx + 1}</td>
          <td class="py-2 px-2 font-mono text-xs text-blue-600">${i.item_id}</td>
          <td class="py-2 px-2 text-sm">${i.title}<br/><span class="text-xs text-gray-400">${i.description || ''}</span></td>
          <td class="py-2 px-2 font-mono text-xs text-gray-500">${i.standard_ref || ''}</td>
          <td class="py-2 px-2"><span class="px-2 py-0.5 bg-${color}-100 text-${color}-700 rounded text-xs">${lv}</span></td>
          <td class="py-2 px-2 text-xs">${majorLabel}</td>
          <td class="py-2 px-2 text-xs">${methodIcon} ${methodLabel}</td>
          <td class="py-2 px-2 font-mono text-xs">${funcId}</td>
        </tr>`;
      })
      .join('');
  } catch (e) {
    if (skel) skel.classList.add('hidden');
    if (content) content.classList.remove('hidden');
    const tbody = document.getElementById('cd-list') as HTMLElement | null;
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" class="py-8 text-center text-red-400">\u52A0\u8F7D\u5931\u8D25: ${(e as Error).message}</td></tr>`;
    }
  }
}

// 监听 page-cd 页面激活，自动加载
document.addEventListener('DOMContentLoaded', () => {
  const page = document.getElementById('page-cd') as HTMLElement | null;
  if (!page) return;
  const observer = new MutationObserver(() => {
    if (!page.classList.contains('hidden')) loadCDItems();
  });
  observer.observe(page, { attributes: true, attributeFilter: ['class'] });
});

export { loadCDItems };
