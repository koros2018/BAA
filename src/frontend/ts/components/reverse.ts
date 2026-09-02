// ── P123 Step 11: 反向重构 + 原子函数库 + 案例库 ──────────
// 从 baa-ext.js 迁入

import { apiFetch, getApiBase } from '../core/api-client';
import { getActiveKeyValue } from '../core/key-manager';
import { formatTimeAgo } from './tools';
import { showToast } from '../core/toast';
import { escHtml } from '../core/utils';

interface Room { type: string; x: number; y: number; w: number; h: number; }
interface Corridor { w: number; h: number; }
interface Layout { rooms: Room[]; corridor: Corridor | null; }
interface Validation { all_pass?: boolean; fail_count?: number; }

// ── P56 反向重构 ──────────────────────────────────────────

export async function generateReverse(): Promise<void> {
  const result = document.getElementById('reverse-result');
  const err = document.getElementById('reverse-error');
  if (!result) return;
  const constraints = document.getElementById('reverse-constraints');
  const validation = document.getElementById('reverse-validation');
  const dxfPre = document.getElementById('reverse-dxf');
  result.classList.add('hidden');
  err?.classList.add('hidden');

  const body = {
    room_type: (document.getElementById('reverse-room-type') as HTMLInputElement | null)?.value || 'office',
    width_mm: parseInt((document.getElementById('reverse-width') as HTMLInputElement | null)?.value || '0') || 5000,
    height_mm: parseInt((document.getElementById('reverse-height') as HTMLInputElement | null)?.value || '0') || 4000,
    door_width_mm: parseInt((document.getElementById('reverse-door-width') as HTMLInputElement | null)?.value || '0') || null,
  };

  try {
    const resp = await fetch(getApiBase() + '/api/v1/reverse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (getActiveKeyValue() || '') },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.status !== 'ok') {
      (err as HTMLElement).textContent = '错误: ' + JSON.stringify(data);
      err!.classList.remove('hidden');
      return;
    }
    const c = data.constraints;
    if (constraints) {
      constraints.innerHTML = '<table class="w-full text-sm">' +
        '<tr><td class="py-1 text-gray-500">最小宽度</td><td class="py-1">' + c.min_width_mm + ' mm</td></tr>' +
        '<tr><td class="py-1 text-gray-500">最小高度</td><td class="py-1">' + c.min_height_mm + ' mm</td></tr>' +
        '<tr><td class="py-1 text-gray-500">最小门宽</td><td class="py-1">' + c.min_door_width_mm + ' mm</td></tr>' +
        '<tr><td class="py-1 text-gray-500">面积</td><td class="py-1">' + c.min_area_m2.toFixed(1) + ' m²</td></tr>' +
        (c.notes.length ? '<tr><td class="py-1 text-gray-500">规范约束</td><td class="py-1">' + c.notes.join('<br>') + '</td></tr>' : '') +
        '</table>';
    }
    const svgContainer = document.getElementById('reverse-svg');
    if (svgContainer && data.validation) {
      const singleLayout: Layout = {
        rooms: [{ type: body.room_type, x: 0, y: 0, w: body.width_mm, h: body.height_mm }],
        corridor: null,
      };
      svgContainer.innerHTML = renderLayoutSVG(singleLayout, data.validation);
      (window as any)._reverseSVGLayout = singleLayout;
      (window as any)._reverseSVGValidation = data.validation;
    }
    const v = data.validation || {};
    if (validation) {
      validation.innerHTML = '<span class="' + (v.all_pass ? 'text-green-600' : 'text-red-600') + '" font-bold>' +
        (v.all_pass ? '✅ 闭环验证通过' : '❌ ' + (v.fail_count || '?') + ' FAIL') + '</span>';
    }
    if (dxfPre) dxfPre.textContent = data.dxf;
    result.classList.remove('hidden');
  } catch (e: any) {
    if (err) { err.textContent = '请求失败: ' + e.message; err.classList.remove('hidden'); }
  }
}

// ── P57 原子函数库 ────────────────────────────────────────

export async function loadFunctions(): Promise<void> {
  try {
    const resp = await fetch(getApiBase() + '/api/v1/functions', {
      headers: { 'Authorization': 'Bearer ' + (getActiveKeyValue() || '') },
    });
    const data = await resp.json();
    if (data.status !== 'ok') return;
    const countEl = document.getElementById('func-count');
    if (countEl) countEl.textContent = '共 ' + data.count + ' 个函数';
    const categories = new Set();
    data.functions.forEach((f: any) => categories.add(f.category));
    const filter = document.getElementById('func-category-filter') as HTMLSelectElement | null;
    if (filter) {
      categories.forEach(cat => {
        const opt = document.createElement('option');
        (opt as HTMLOptionElement).value = String(cat);
        opt.textContent = String(cat);
        filter.appendChild(opt);
      });
    }
    (window as any)._allFuncs = data.functions;
    filterFunctions();
  } catch (e: any) {
    const el = document.getElementById('func-list');
    if (el) el.innerHTML = '<div class="text-center text-red-500 py-8">加载失败: ' + e.message + '</div>';
  }
}

export function filterFunctions(): void {
  const search = (document.getElementById('func-search') as HTMLInputElement | null)?.value.toLowerCase() || '';
  const category = (document.getElementById('func-category-filter') as HTMLSelectElement | null)?.value || '';
  const funcs = (window as any)._allFuncs || [];
  const list = document.getElementById('func-list');
  if (!list) return;
  const filtered = funcs.filter((f: any) => {
    if (category && f.category !== category) return false;
    if (search && !f.func_id.toLowerCase().includes(search) && !f.name.toLowerCase().includes(search)) return false;
    return true;
  });
  list.innerHTML = filtered.map((f: any) => {
    const catColors: Record<string, string> = { dim: 'blue', dist: 'green', count: 'purple', attr: 'orange', exist: 'red', area: 'teal', evac: 'pink', access: 'indigo' };
    const color = catColors[f.category] || 'gray';
    const fid = f.func_id;
    return '<div class="card p-3 hover:shadow-md transition cursor-pointer" onclick="toggleFuncDetail(&#39;' + fid + '&#39;)">' +
      '<div class="flex items-center justify-between"><div class="flex items-center gap-2">' +
      '<span class="text-xs font-mono bg-' + color + '-100 text-' + color + '-700 px-2 py-0.5 rounded">' + fid + '</span>' +
      '<span class="font-medium">' + f.name + '</span></div>' +
      '<span class="text-xs text-gray-400">' + f.clause_id + '</span></div>' +
      '<div class="text-sm text-gray-500 mt-1">' + f.description + '</div>' +
      '<div id="detail-' + fid + '" class="hidden mt-2 pt-2 border-t border-gray-100">' +
      '<div class="grid grid-cols-2 gap-2 text-sm">' +
      '<div><span class="text-gray-500">目标实体:</span> ' + (f.target_entities || []).join(', ') + '</div>' +
      '<div><span class="text-gray-500">运算符:</span> ' + f.operator + '</div>' +
      '<div><span class="text-gray-500">阈值:</span> <input class="input w-24 inline text-sm" value="' + f.threshold + '" id="th-' + fid + '" /></div>' +
      '<div><span class="text-gray-500">单位:</span> <input class="input w-20 inline text-sm" value="' + f.unit + '" id="unit-' + fid + '" /></div></div>' +
      '<button class="btn-primary text-xs mt-2" onclick="event.stopPropagation();updateFunction(&#39;' + fid + '&#39;)">保存修改</button>' +
      '</div></div>';
  }).join('');
}

export function toggleFuncDetail(funcId: string): void {
  document.getElementById('detail-' + funcId)?.classList.toggle('hidden');
}

export async function updateFunction(funcId: string): Promise<void> {
  const th = document.getElementById('th-' + funcId) as HTMLInputElement | null;
  const unit = document.getElementById('unit-' + funcId) as HTMLInputElement | null;
  if (!th || !unit) return;
  try {
    await apiFetch('/api/v1/functions/' + funcId + '/update', {
      method: 'POST',
      body: JSON.stringify({ threshold: parseFloat(th.value), unit: unit.value }),
    });
    showToast('更新成功', 'success');
  } catch (e: any) { showToast('更新失败: ' + e.message, 'error'); }
}

// ── P58 多房间布局 ────────────────────────────────────────

export function switchRevTab(tab: string): void {
  const singlePanel = document.getElementById('rev-single-panel');
  const multiPanel = document.getElementById('rev-multi-panel');
  const tabSingle = document.getElementById('rev-tab-single');
  const tabMulti = document.getElementById('rev-tab-multi');
  if (tab === 'multi') {
    singlePanel?.classList.add('hidden');
    multiPanel?.classList.remove('hidden');
    tabSingle?.classList.remove('bg-white', 'shadow-sm', 'font-medium');
    tabSingle?.classList.add('text-gray-600');
    tabMulti?.classList.add('bg-white', 'shadow-sm', 'font-medium');
    tabMulti?.classList.remove('text-gray-600');
    initMultiRooms();
  } else {
    singlePanel?.classList.remove('hidden');
    multiPanel?.classList.add('hidden');
    tabSingle?.classList.add('bg-white', 'shadow-sm', 'font-medium');
    tabSingle?.classList.remove('text-gray-600');
    tabMulti?.classList.remove('bg-white', 'shadow-sm', 'font-medium');
    tabMulti?.classList.add('text-gray-600');
  }
  document.getElementById('reverse-result')?.classList.add('hidden');
  document.getElementById('reverse-error')?.classList.add('hidden');
}

export function initMultiRooms(): void {
  const list = document.getElementById('multi-room-list');
  if (!list || list.children.length > 0) return;
  addMultiRoom('office', 5000, 4000, 900);
  addMultiRoom('equipment', 3000, 3000, 900);
  addMultiRoom('accessible_toilet', 2500, 2500, 900);
}

export function addMultiRoom(type: string, width: number, height: number, doorWidth: number | null): void {
  const list = document.getElementById('multi-room-list');
  if (!list) return;
  const div = document.createElement('div');
  div.className = 'multi-room-row flex items-center gap-2 mb-2 p-2 border rounded-lg bg-gray-50';
  div.innerHTML = '<select class="multi-room-type input text-sm w-28">' +
    ['office|办公室','stair|楼梯间','corridor|走廊','exit|安全出口','fire_lobby|前室','equipment|设备间','accessible_toilet|无障碍卫生间'].map(o => {
      const [v, l] = o.split('|');
      return '<option value="' + v + '" ' + (v === type ? 'selected' : '') + '>' + l + '</option>';
    }).join('') +
    '</select>' +
    '<input class="multi-room-width input text-sm w-20" value="' + width + '" placeholder="宽" />' +
    '<input class="multi-room-height input text-sm w-20" value="' + height + '" placeholder="高" />' +
    '<input class="multi-room-door-width input text-sm w-20" value="' + (doorWidth || '') + '" placeholder="门宽" />' +
    '<span class="text-xs text-gray-400 w-16">mm</span>' +
    '<button class="text-red-500 hover:text-red-700 text-sm" onclick="this.closest(\'.multi-room-row\').remove()">✕</button>';
  list.appendChild(div);
}

export async function generateMultiReverse(): Promise<void> {
  const result = document.getElementById('reverse-result');
  const err = document.getElementById('reverse-error');
  if (!result) return;
  const dxfPre = document.getElementById('reverse-dxf');
  const validationDiv = document.getElementById('reverse-validation');
  result.classList.add('hidden');
  err?.classList.add('hidden');
  const rooms: any[] = [];
  document.querySelectorAll('.multi-room-row').forEach(row => {
    rooms.push({
      room_type: (row.querySelector('.multi-room-type') as HTMLSelectElement | null)?.value || 'office',
      width_mm: parseInt((row.querySelector('.multi-room-width') as HTMLInputElement | null)?.value || '0') || 5000,
      height_mm: parseInt((row.querySelector('.multi-room-height') as HTMLInputElement | null)?.value || '0') || 4000,
      door_width_mm: parseInt((row.querySelector('.multi-room-door-width') as HTMLInputElement | null)?.value || '0') || null,
    });
  });
  if (rooms.length === 0) {
    rooms.push({ room_type: 'office', width_mm: 5000, height_mm: 4000 });
    rooms.push({ room_type: 'stair', width_mm: 3000, height_mm: 5000 });
  }
  try {
    const resp = await fetch(getApiBase() + '/api/v1/reverse/multi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (getActiveKeyValue() || '') },
      body: JSON.stringify({ rooms, validate: true }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') {
      (err as HTMLElement).textContent = '错误: ' + JSON.stringify(data);
      err!.classList.remove('hidden');
      return;
    }
    const svgContainer = document.getElementById('reverse-svg');
    if (svgContainer) {
      svgContainer.innerHTML = renderLayoutSVG(data.layout, data.validation);
      (window as any)._reverseSVGLayout = data.layout;
      (window as any)._reverseSVGValidation = data.validation;
    }
    const v = data.validation || {};
    if (validationDiv) {
      validationDiv.innerHTML = '<span class="' + (v.all_pass ? 'text-green-600' : 'text-gray-500') + ' font-bold">' +
        (v.all_pass ? '✅ 闭环验证通过' : '验证未开启') + '</span>';
    }
    if (dxfPre) dxfPre.textContent = data.dxf;
    result.classList.remove('hidden');
  } catch (e: any) {
    if (err) { err.textContent = '请求失败: ' + e.message; err.classList.remove('hidden'); }
  }
}

// ── P58 布局可视化 SVG ─────────────────────────────────────

export function renderLayoutSVG(layout: Layout, validation: Validation | null): string {
  const rooms = layout.rooms || [];
  const corridor = layout.corridor;
  if (!rooms.length && !corridor) return '<div class="text-center text-gray-400 py-8">无布局数据</div>';
  const SCALE = 0.1;
  const MARGIN = 40;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  rooms.forEach(r => {
    minX = Math.min(minX, r.x); minY = Math.min(minY, r.y);
    maxX = Math.max(maxX, r.x + r.w); maxY = Math.max(maxY, r.y + r.h);
  });
  if (corridor) {
    const ys = rooms.map(r => r.y + r.h).concat(rooms.map(r => r.y));
    const midY = Math.min(...ys);
    minX = Math.min(minX, 0); minY = Math.min(minY, midY - corridor.h);
    maxX = Math.max(maxX, corridor.w); maxY = Math.max(maxY, midY);
  }
  const svgW = (maxX - minX) * SCALE + MARGIN * 2;
  const svgH = (maxY - minY) * SCALE + MARGIN * 2;
  const colorMap: Record<string, string> = {
    office:'#dbeafe', stair:'#bfdbfe', corridor:'#e0f2fe', exit:'#bbf7d0',
    fire_lobby:'#fde68a', equipment:'#fed7aa', accessible_toilet:'#ddd6fe',
    bedroom:'#fce7f3', wc:'#f3e8ff', toilet:'#f3e8ff', hallway:'#ecfeff',
    kitchen:'#fef9c3', bathroom:'#e0e7ff'
  };
  const borderMap: Record<string, string> = {
    office:'#3b82f6', stair:'#2563eb', corridor:'#0891b2', exit:'#16a34a',
    fire_lobby:'#d97706', equipment:'#ea580c', accessible_toilet:'#7c3aed',
    bedroom:'#db2777', wc:'#8b5cf6', toilet:'#8b5cf6', hallway:'#06b6d4',
    kitchen:'#ca8a04', bathroom:'#6366f1'
  };
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgW} ${svgH}" style="width:100%;height:100%;display:block;background:#fafafa" font-family="system-ui,sans-serif">`;
  svg += `<defs><marker id="arrow-evac" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#ef4444" stroke="#ef4444" stroke-width="0.5"/></marker></defs>`;
  rooms.forEach(r => {
    const x = (r.x - minX) * SCALE + MARGIN;
    const y = (r.y - minY) * SCALE + MARGIN;
    const w = r.w * SCALE;
    const h = r.h * SCALE;
    const fill = colorMap[r.type] || '#e5e7eb';
    const stroke = borderMap[r.type] || '#6b7280';
    svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width="2" rx="2"/>`;
    const label = r.type.charAt(0).toUpperCase() + r.type.slice(1).replace(/_/g, ' ');
    const labelFontSize = Math.max(9, Math.min(14, Math.min(w, h) / 6));
    svg += `<text x="${x + w/2}" y="${y + h/2 - 4}" text-anchor="middle" font-size="${labelFontSize}" font-weight="600" fill="#1f2937">${label}</text>`;
    svg += `<text x="${x + w/2}" y="${y + h/2 + 10}" text-anchor="middle" font-size="8" fill="#6b7280">${r.w}x${r.h}mm</text>`;
  });
  if (corridor) {
    const ys = rooms.map(r => r.y + r.h).concat(rooms.map(r => r.y));
    const midY = Math.min(...ys);
    const cx = (0 - minX) * SCALE + MARGIN;
    const cy = (midY - corridor.h - minY) * SCALE + MARGIN;
    const cw = corridor.w * SCALE;
    const ch = corridor.h * SCALE;
    svg += `<rect x="${cx}" y="${cy}" width="${cw}" height="${ch}" fill="#e0f2fe" stroke="#0891b2" stroke-width="2" stroke-dasharray="6,4" rx="2"/>`;
    svg += `<text x="${cx + cw/2}" y="${cy + ch/2}" text-anchor="middle" font-size="11" font-weight="600" fill="#0e7490">CORRIDOR</text>`;
  }
  if (rooms.length > 1) {
    rooms.forEach(r => {
      const doorYRoom = r.y + r.h;
      const corridorTop = Math.min(...rooms.map(rr => rr.y + rr.h));
      const arrowStartX = (r.x + r.w / 2 - minX) * SCALE + MARGIN;
      const arrowStartY = (doorYRoom - minY) * SCALE + MARGIN + 4;
      const arrowEndX = arrowStartX;
      const arrowEndY = (corridorTop - minY) * SCALE + MARGIN - 4;
      if (arrowEndY > arrowStartY) {
        svg += `<line x1="${arrowStartX}" y1="${arrowStartY}" x2="${arrowEndX}" y2="${arrowEndY}" stroke="#ef4444" stroke-width="2" marker-end="url(#arrow-evac)"/>`;
      }
    });
    const corridorY2 = Math.min(...rooms.map(rr => rr.y + rr.h));
    const corrCX = (0 + (corridor ? corridor.w : 3000) / 2 - minX) * SCALE + MARGIN;
    const corrCY = (corridorY2 - minY) * SCALE + MARGIN;
    const exitX = (corridor ? corridor.w : 3000) * SCALE + MARGIN;
    if (exitX > corrCX) {
      svg += `<line x1="${corrCX}" y1="${corrCY}" x2="${exitX - 20}" y2="${corrCY}" stroke="#ef4444" stroke-width="2" marker-end="url(#arrow-evac)"/>`;
      svg += `<text x="${exitX - 15}" y="${corrCY - 8}" text-anchor="middle" font-size="10" fill="#dc2626" font-weight="700">出口</text>`;
    }
  }
  if (validation && (validation.fail_count ?? 0) > 0) {
    svg += `<text x="${svgW/2}" y="${svgH - 10}" text-anchor="middle" font-size="12" fill="#ef4444" font-weight="700">${validation.fail_count} 项违规</text>`;
  } else if (validation && validation.all_pass) {
    svg += `<text x="${svgW/2}" y="${svgH - 10}" text-anchor="middle" font-size="12" fill="#16a34a" font-weight="700">闭环验证通过</text>`;
  }
  const scaleLen = 2000 * SCALE;
  const scaleY = svgH - 25;
  svg += `<line x1="20" y1="${scaleY}" x2="${20 + scaleLen}" y2="${scaleY}" stroke="#374151" stroke-width="2"/>`;
  svg += `<line x1="20" y1="${scaleY - 4}" x2="20" y2="${scaleY + 4}" stroke="#374151" stroke-width="1.5"/>`;
  svg += `<line x1="${20 + scaleLen}" y1="${scaleY - 4}" x2="${20 + scaleLen}" y2="${scaleY + 4}" stroke="#374151" stroke-width="1.5"/>`;
  svg += `<text x="${20 + scaleLen/2}" y="${scaleY - 6}" text-anchor="middle" font-size="8" fill="#6b7280">2m</text>`;
  svg += '</svg>';
  return svg;
}

export function expandReverseSVG(): void {
  const layout = (window as any)._reverseSVGLayout;
  if (!layout) { showToast('先生成布局', 'info'); return; }
  const modal = document.createElement('div');
  modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4';
  modal.innerHTML = '<div class="bg-white rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">' +
    '<div class="flex items-center justify-between p-4 border-b"><h3 class="font-bold">布局可视化</h3>' +
    '<button onclick="this.closest(\'div.fixed\').remove()" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button></div>' +
    '<div class="flex-1 overflow-auto p-4">' + renderLayoutSVG(layout, (window as any)._reverseSVGValidation) + '</div></div>';
  document.body.appendChild(modal);
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
}

export function downloadReverseSVG(): void {
  const svgEl = document.querySelector('#reverse-svg svg');
  if (!svgEl) { showToast('先生成布局', 'info'); return; }
  const blob = new Blob([svgEl.outerHTML], { type: 'image/svg+xml' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'baa-layout.svg';
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── P68 行业案例库 ────────────────────────────────────────

let _casePage = 0;
const _casePageSize = 15;

export async function loadCaseStats(): Promise<void> {
  try {
    const r = await apiFetch('/api/v1/cases/stats') as any;
    if (r.status !== 'ok') return;
    const total = document.getElementById('case-total');
    const violations = document.getElementById('case-violations');
    const avgScore = document.getElementById('case-avg-score');
    const tagsCount = document.getElementById('case-tags-count');
    if (total) total.textContent = String(r.totalCases ?? '-');
    if (violations) violations.textContent = String(r.totalViolations ?? '-');
    if (avgScore) avgScore.textContent = String(r.avgScore ?? '-');
    if (tagsCount) tagsCount.textContent = String(r.topTags ? Object.keys(r.topTags).length : 0);
  } catch (e) { console.error('loadCaseStats failed:', e); }
}

export async function loadCases(page = 0): Promise<void> {
  _casePage = page;
  const q = (document.getElementById('case-search') as HTMLInputElement | null)?.value || '';
  const bt = (document.getElementById('case-filter-type') as HTMLSelectElement | null)?.value || '';
  const tag = (document.getElementById('case-filter-tag') as HTMLSelectElement | null)?.value || '';
  const listEl = document.getElementById('case-list');
  if (listEl) listEl.innerHTML = '<div class="text-center text-gray-400 py-8">加载中...</div>';
  try {
    let data: any;
    if (q) {
      data = await apiFetch(`/api/v1/cases/search?q=${encodeURIComponent(q)}`) as any;
    } else {
      const params = new URLSearchParams({ limit: String(_casePageSize), offset: String(page * _casePageSize) });
      if (bt) params.set('building_type', bt);
      if (tag) params.set('tag', tag);
      data = await apiFetch(`/api/v1/cases?${params}`) as any;
    }
    if (data.status !== 'ok') {
      if (listEl) listEl.innerHTML = '<div class="text-center text-gray-400 py-8">加载失败</div>';
      return;
    }
    const cases = data.cases || [];
    renderCaseList(cases, data.total ?? 0);
    renderCasePagination(data.total ?? 0, page);
  } catch (e: any) {
    console.error('loadCases failed:', e);
    if (listEl) listEl.innerHTML = '<div class="text-center text-red-400 py-8">加载失败: ' + e.message + '</div>';
  }
}

export function renderCaseList(cases: any[], total: number): void {
  const el = document.getElementById('case-list');
  if (!el) return;
  if (cases.length === 0) {
    el.innerHTML = '<div class="text-center text-gray-400 py-8">暂无案例数据</div>';
    return;
  }
  const tagColors: Record<string, string> = {
    '尺寸不合规': 'bg-red-100 text-red-700',
    '距离不合规': 'bg-orange-100 text-orange-700',
    '数量不合规': 'bg-yellow-100 text-yellow-700',
    '缺失设施': 'bg-red-100 text-red-700',
    '面积不合规': 'bg-blue-100 text-blue-700',
    '属性不合规': 'bg-gray-100 text-gray-700',
    '照明不合规': 'bg-yellow-100 text-yellow-700',
    '无障碍不合规': 'bg-green-100 text-green-700',
  };
  let html = '';
  for (const c of cases) {
    const score = c.score ?? 0;
    const scoreColor = score >= 80 ? 'text-green-600' : score >= 50 ? 'text-yellow-600' : 'text-red-600';
    const violations = c.violationCount ?? 0;
    const corrections = c.correctionCount ?? 0;
    const tagsHtml = (c.tags || []).slice(0, 4).map(
      (t: string) => `<span class="inline-block px-2 py-0.5 text-xs rounded-full ${tagColors[t] || 'bg-gray-100 text-gray-600'}">${escHtml(t)}</span>`
    ).join(' ');
    html += `<div class="card p-4 hover:bg-gray-50 cursor-pointer transition" onclick="openCaseDetail('${escHtml(c.caseId)}')">
      <div class="flex items-center justify-between mb-2">
        <div><h4 class="font-medium text-sm">${escHtml(c.drawingName)}</h4>
        <span class="text-xs text-gray-400">${escHtml(c.buildingType || 'civil')} · ${escHtml(c.standard || '')}</span></div>
        <div class="text-right"><span class="${scoreColor} font-bold text-lg">${score.toFixed(0)}</span><span class="text-xs text-gray-400 ml-1">分</span></div>
      </div>
      ${tagsHtml ? `<div class="flex flex-wrap gap-1 mb-2">${tagsHtml}</div>` : ''}
      <div class="flex gap-4 text-xs text-gray-400">
        <span>图元 ${c.entityCount ?? '-'}</span>
        <span class="${violations > 0 ? 'text-red-500' : 'text-green-500'}">违规 ${violations}</span>
        <span class="text-blue-500">修正 ${corrections}</span>
        <span>${formatTimeAgo(c.reviewedAt || '')}</span>
      </div></div>`;
  }
  el.innerHTML = html;
}

export function renderCasePagination(total: number, page: number): void {
  const el = document.getElementById('case-pagination');
  if (!el) return;
  const totalPages = Math.ceil(total / _casePageSize);
  if (totalPages <= 1) { el.innerHTML = ''; return; }
  let html = '';
  html += `<button onclick="loadCases(${page - 1})" ${page === 0 ? 'disabled' : ''} class="px-3 py-1 border rounded text-sm ${page === 0 ? 'opacity-40' : 'hover:bg-gray-100'}">← 上一页</button>`;
  html += `<span class="px-2 text-sm text-gray-500">第 ${page + 1} / ${totalPages} 页</span>`;
  html += `<button onclick="loadCases(${page + 1})" ${page + 1 >= totalPages ? 'disabled' : ''} class="px-3 py-1 border rounded text-sm ${page + 1 >= totalPages ? 'opacity-40' : 'hover:bg-gray-100'}">下一页 →</button>`;
  el.innerHTML = html;
}

export async function openCaseDetail(caseId: string): Promise<void> {
  const titleEl = document.getElementById('case-detail-title');
  const contentEl = document.getElementById('case-detail-content');
  const modal = document.getElementById('case-detail-modal');
  if (!modal || !titleEl || !contentEl) return;
  titleEl.textContent = '案例详情';
  contentEl.innerHTML = '<div class="text-center text-gray-400 py-8">加载中...</div>';
  modal.classList.remove('hidden');
  try {
    const data = await apiFetch(`/api/v1/cases/${caseId}`) as any;
    if (data.status !== 'ok') {
      contentEl.innerHTML = `<div class="text-center text-red-400 py-8">${escHtml(data.message || '加载失败')}</div>`;
      return;
    }
    const score = data.score ?? 0;
    const scoreColor = score >= 80 ? 'text-green-600' : score >= 50 ? 'text-yellow-600' : 'text-red-600';
    const tagsHtml = (data.tags || []).map((t: string) =>
      `<span class="inline-block px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700">${escHtml(t)}</span>`
    ).join(' ');
    let html = `<div class="mb-4">
      <h4 class="font-bold">${escHtml(data.drawingName)}</h4>
      <p class="text-xs text-gray-400">${escHtml(data.buildingType || 'civil')} · ${escHtml(data.standard || '')} · ${formatTimeAgo(data.reviewedAt || '')}</p>
      <div class="mt-2 flex gap-2 flex-wrap">${tagsHtml}</div></div>
      <div class="grid grid-cols-3 gap-3 mb-4">
        <div class="card p-3 text-center"><div class="${scoreColor} font-bold text-xl">${score.toFixed(0)}</div><div class="text-xs text-gray-500">审查得分</div></div>
        <div class="card p-3 text-center"><div class="font-bold text-xl text-red-500">${data.violationCount ?? '-'}</div><div class="text-xs text-gray-500">违规数</div></div>
        <div class="card p-3 text-center"><div class="font-bold text-xl text-blue-500">${data.correctionCount ?? '-'}</div><div class="text-xs text-gray-500">修正建议</div></div></div>
      <h5 class="font-medium mb-2">核心违规 TOP-5</h5><div class="space-y-2">`;
    for (const v of (data.topViolations || [])) {
      const tierColor = v.confidence_tier === '高' ? 'text-red-600' : v.confidence_tier === '中' ? 'text-yellow-600' : 'text-gray-400';
      html += `<div class="border rounded p-2 text-sm">
        <div class="font-medium">${escHtml(v.clause_title || v.clause_id)}</div>
        <div class="text-xs text-gray-400">${escHtml(v.entity_type || '')} · 条款 ${escHtml(v.clause_id || '')}</div>
        ${v.extracted_value !== undefined ? `<div class="text-xs">实测 ${v.extracted_value} · 要求 ${v.required_value} · 偏差 ${v.difference}</div>` : ''}
        ${v.confidence_tier ? `<span class="${tierColor} text-xs">${v.confidence_tier}置信</span>` : ''}</div>`;
    }
    if (!data.topViolations || data.topViolations.length === 0) {
      html += '<div class="text-center text-gray-400 text-sm py-4">无违规记录</div>';
    }
    html += '</div>';
    contentEl.innerHTML = html;
  } catch (e: any) {
    contentEl.innerHTML = `<div class="text-center text-red-400 py-8">加载失败: ${escHtml(e.message)}</div>`;
  }
}

export function closeCaseDetail(): void {
  const modal = document.getElementById('case-detail-modal');
  if (modal) modal.classList.add('hidden');
}

if (typeof document !== 'undefined') {
  document.addEventListener('click', function(e) {
    const modal = document.getElementById('case-detail-modal');
    if (modal && !modal.classList.contains('hidden') && e.target === modal) {
      closeCaseDetail();
    }
  });
  setTimeout(loadFunctions, 1000);
}
