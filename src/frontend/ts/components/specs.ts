// ── P123 Step 3: Specs 规范库组件 ──────────────────────
// 从 baa-admin.js lines 14-109 迁入
// loadSpecs / renderSpecList

import { getApiBase, getHeaders } from '../core/api-client';
import { getSpecData, setSpecData } from '../core/spec-data';
import { escHtml } from '../core/utils';

export async function loadSpecs(): Promise<void> {
  try {
    const r = await fetch(getApiBase() + '/api/v1/specs', { headers: getHeaders() });
    const data = (await r.json()) as Record<string, unknown>;
    if (data.status === 'ok') {
      setSpecData(data.specs as Array<Record<string, unknown>>);
    }
  } catch (e) {
    console.warn('规范库加载失败', e);
  }
  renderSpecList();
  const statsEl = document.getElementById('home-stats') as HTMLElement | null;
  const specCount = statsEl?.querySelectorAll('.stat-card')[1]?.querySelector('.text-2xl') as HTMLElement | null;
  if (specCount) specCount.textContent = String((getSpecData() || []).length);
}

export function renderSpecList(_showAll = false): void {
  const tbody = document.getElementById('spec-list') as HTMLElement | null;
  if (!tbody) return;
  const search = (document.getElementById('spec-search') as HTMLInputElement | null)?.value || '';
  const levelFilter = (document.getElementById('spec-filter-level') as HTMLSelectElement | null)?.value || 'all';
  const catFilter = (document.getElementById('spec-filter-cat') as HTMLSelectElement | null)?.value || 'all';
  const stdFilter = (document.getElementById('spec-filter-std') as HTMLSelectElement | null)?.value || 'all';

  const specs = getSpecData() || [];
  const total = specs.length;
  const l1 = specs.filter((s) => String(s.level || 'L1') === 'L1').length;
  const l2 = specs.filter((s) => String(s.level || 'L1') === 'L2').length;
  const l3 = specs.filter((s) => String(s.level || 'L1') === 'L3').length;
  const tc = document.getElementById('spec-total-count') as HTMLElement | null;
  if (tc) tc.textContent = String(total);
  const l1c = document.getElementById('spec-l1-count') as HTMLElement | null;
  if (l1c) l1c.textContent = String(l1);
  const l2c = document.getElementById('spec-l2-count') as HTMLElement | null;
  if (l2c) l2c.textContent = String(l2);
  const l3c = document.getElementById('spec-l3-count') as HTMLElement | null;
  if (l3c) l3c.textContent = String(l3);

  let filtered = specs;
  if (levelFilter !== 'all') filtered = filtered.filter((s) => String(s.level || 'L1') === levelFilter);
  if (catFilter !== 'all') filtered = filtered.filter((s) => (s.category || '') === catFilter);
  if (stdFilter !== 'all') {
    filtered = filtered.filter((s) => {
      const std = String(s.standard || s.std || '');
      return std.toLowerCase().includes(stdFilter.toLowerCase());
    });
  }
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter((s) =>
      String(s.clause_id || '').toLowerCase().includes(q) ||
      String(s.title || s.name || '').toLowerCase().includes(q) ||
      String(s.text || s.description || '').toLowerCase().includes(q) ||
      String(s.standard || s.std || '').toLowerCase().includes(q),
    );
  }
  const fcount = document.getElementById('spec-filter-count') as HTMLElement | null;
  if (fcount) fcount.textContent = filtered.length + ' 条' + (filtered.length < total ? ' / ' + total : '');

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">无匹配记录</td></tr>';
    return;
  }

  const catLabels: Record<string, string> = { fire_safety: '防火安全', evacuation: '疏散', lighting: '照明', structure: '结构', hvac: '暖通' };
  const levelColors: Record<string, string> = { L1: 'red', L2: 'orange', L3: 'green' };
  const stdAbbrev: Record<string, string> = {
    'GB 50016-2014': '016', 'GB 50016-2018': '016', 'GB 50974-2014': '974',
    'GB 50763-2012': '763', 'GB 50067-2014': '067', 'GB 50116-2013': '116',
    'GB 50084-2017': '084', 'NFPA 101-2021': 'NFPA101', 'NFPA 5000-2021': 'NFPA5K',
  };

  tbody.innerHTML = filtered
    .map((s, i) => {
      const title = s.title || s.name || '';
      const desc = s.text || s.description || '';
      const cat = String(s.category || '--');
      const target = s.func_id || '--';
      const level = String(s.level || 'L1');
      const std = String(s.standard || s.std || '');
      const stdShort = stdAbbrev[std] || (std ? std.replace(/-/g, '').slice(0, 5) : '--');
      const targetStr = Array.isArray(target) ? target.join(', ') : String(target);
      return (
        '<tr class="border-b border-gray-50">' +
        '<td class="py-2 px-2 text-xs">' + (i + 1) + '</td>' +
        '<td class="py-2 px-2 font-mono text-xs">' + escHtml(String(s.clause_id || '')) + '</td>' +
        '<td class="py-2 px-2 text-sm">' + escHtml(String(title)) + '<br/><span class="text-xs text-gray-400">' + escHtml(String(desc)) + '</span></td>' +
        '<td class="py-2 px-2 text-xs">' + (std ? '<span class="bg-blue-100 text-blue-700 px-1 rounded">' + escHtml(stdShort) + '</span>' : '') + '</td>' +
        '<td class="py-2 px-2"><span class="px-2 py-0.5 bg-' + (levelColors[String(level)] || 'gray') + '-100 text-' + (levelColors[String(level)] || 'gray') + '-700 rounded text-xs">' + level + '</span></td>' +
        '<td class="py-2 px-2 text-xs">' + (catLabels[cat] || cat) + '</td>' +
        '<td class="py-2 px-2 font-mono text-xs max-w-32 truncate">' + escHtml(targetStr) + '</td></tr>'
      );
    })
    .join('');
}