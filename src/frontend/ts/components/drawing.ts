// ── P123 Step 4: Drawing 图纸管理组件 ──────────────────────
// 从 baa-admin.js 迁入 — 20 个函数（图纸上传/管理/批量审查/送审）

import { getApiBase, getHeaders, apiPost, apiPostFile } from '../core/api-client';
import { showToast } from '../core/toast';
import {
  getParsedDrawings,
  setParsedDrawings,
  setFileCache,
} from '../core/drawing-state';
import { escHtml } from '../core/utils';
import { loadDashboard } from './dashboard';

// ── 本地存储 ──────────────────────────────────────────────────
export function saveParsedDrawings(): void {
  try {
    localStorage.setItem('baa_parsed_drawings', JSON.stringify(getParsedDrawings()));
  } catch (_e) { /* ignore quota */ }
}

export function loadParsedDrawings(): void {
  try {
    const stored = localStorage.getItem('baa_parsed_drawings');
    if (stored) setParsedDrawings(JSON.parse(stored));
  } catch (_e) { setParsedDrawings([]); }
}

// ── 渲染 ──────────────────────────────────────────────────────
export function renderDrawingList(): void {
  const tbody = document.getElementById('drawing-list') as HTMLElement | null;
  if (!tbody) return;
  const list = getParsedDrawings();
  const countEl = document.getElementById('drawing-count') as HTMLElement | null;
  if (countEl) countEl.textContent = String(list.length);

  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">暂无记录，请上传图纸</td></tr>';
    return;
  }

  tbody.innerHTML = list
    .map((d, i) => {
      const yoloBadge = d.use_yolo ? '<span class="ml-1 px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">YOLO</span>' : '';
      const checked = d._selected ? 'checked' : '';
      const elements = d.elements as Array<Record<string, unknown>> | undefined;
      return (
        '<tr class="border-b border-gray-50 text-sm">' +
        '<td class="py-2 px-2"><input type="checkbox" class="drawing-select" data-idx="' + i + '" ' + checked + ' onchange="toggleDrawingSelect(' + i + ',this.checked)" /></td>' +
        '<td class="py-2 px-2 truncate max-w-32">' + escHtml(String(d.filename)) + yoloBadge + '</td>' +
        '<td class="py-2 px-2 text-xs">' + (d.building_type === 'civil' ? '民用' : '工业') + '</td>' +
        '<td class="py-2 px-2">' + (elements?.length || 0) + '</td>' +
        '<td class="py-2 px-2 text-xs max-w-40 truncate">' + (elements ? elements.map((e) => e.type).join(', ') : '') + '</td>' +
        '<td class="py-2 px-2 text-xs">' + new Date(String(d.parsedAt)).toLocaleTimeString() + '</td>' +
        '<td class="py-2 px-2">' +
        '<button onclick="sendToReview(' + i + ')" class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200 mr-1">送审</button>' +
        (d.file_id ? '<button onclick="downloadReviewPdf(\'' + escHtml(String(d.file_id)) + '\')" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200 mr-1" title="下载PDF报告">📄</button>' : '') +
        '<button onclick="deleteDrawing(' + i + ')" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200">🗑️</button></td></tr>'
      );
    })
    .join('');
  updateBatchButton();
}

export function toggleDrawingSelect(idx: number, checked: boolean): void {
  const list = getParsedDrawings();
  if (list[idx]) list[idx]._selected = checked;
  updateBatchButton();
}

export function selectAllDrawings(): void {
  getParsedDrawings().forEach((d) => (d._selected = true));
  renderDrawingList();
}

export function deselectAllDrawings(): void {
  getParsedDrawings().forEach((d) => (d._selected = false));
  renderDrawingList();
}

export function updateBatchButton(): void {
  const count = getParsedDrawings().filter((d) => d._selected).length;
  const btn = document.getElementById('batch-review-btn') as HTMLElement | null;
  const badge = document.getElementById('batch-count') as HTMLElement | null;
  if (btn) {
    btn.className = count > 0
      ? 'px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700'
      : 'px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 hidden';
  }
  if (badge) badge.textContent = String(count);
}

// ── 上传 ──────────────────────────────────────────────────────
export async function uploadDrawing(): Promise<void> {
  const file = (document.getElementById('file-input') as HTMLInputElement | null)?.files?.[0];
  if (!file) { showToast('请先选择图纸文件', 'info'); return; }
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  if (ext !== 'dxf') {
    showToast('仅支持 .dxf 格式。DWG 格式兼容性有限，请先用CAD转存为DXF。', 'warn');
    return;
  }

  const bt = (document.getElementById('drawing-bt') as HTMLInputElement | null)?.value || '';
  const progress = document.getElementById('upload-progress') as HTMLElement | null;
  if (progress) {
    progress.className = 'card mb-4';
    progress.innerHTML =
      '<div class="review-progress"><div class="review-progress-text"><span>解析</span><span>0%</span></div>' +
      '<div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
  }

  try {
    const useYolo = (document.getElementById('use-yolo-checkbox') as HTMLInputElement | null)?.checked || false;
    const yoloDevice = (document.getElementById('yolo-device-select') as HTMLSelectElement | null)?.value || 'cpu';
    const result = await apiPostFile('/deconstruct', file, { building_type: bt, use_yolo: useYolo, yolo_device: yoloDevice }) as Record<string, unknown>;

    if (progress) progress.className = 'hidden';

    const fileId = String(result.file_id || 'drawing_' + Date.now());
    setFileCache(fileId, file);

    const entry: Record<string, unknown> = {
      id: fileId,
      filename: file.name,
      building_type: bt,
      parsedAt: new Date().toISOString(),
      elements: (result.elements as Array<Record<string, unknown>>) || [],
      entities: (result.entities as Array<Record<string, unknown>>) || [],
      findings_count: result.findings || 0,
      total_checks: result.total_checks || 0,
      file_id: fileId,
      raw: result,
      use_yolo: useYolo,
    };

    const list = getParsedDrawings();
    list.unshift(entry);
    setParsedDrawings(list);
    saveParsedDrawings();
    renderDrawingList();

    const preview = document.getElementById('drawing-preview') as HTMLElement | null;
    if (preview) preview.className = 'card';
    const jsonEl = document.getElementById('parse-result-json') as HTMLElement | null;
    if (jsonEl) jsonEl.textContent = JSON.stringify(result, null, 2);

    const renderImg = document.getElementById('drawing-render-img') as HTMLImageElement | null;
    const placeholder = document.getElementById('drawing-render-placeholder') as HTMLElement | null;
    if (renderImg) {
      renderImg.className = 'w-full';
      renderImg.src = getApiBase() + '/render/' + fileId;
    }
    if (placeholder) placeholder.className = 'hidden';

    refreshReviewDrawingSelect();
    loadDashboard();
  } catch (e) {
    if (progress) {
      progress.innerHTML = '❌ 解析失败: ' + String(e);
      progress.className = 'card mb-4 text-sm text-red-500';
    }
  }
}

export async function uploadAndReview(): Promise<void> {
  const file = (document.getElementById('file-input') as HTMLInputElement | null)?.files?.[0];
  if (!file) { showToast('请先选择图纸文件', 'info'); return; }
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  if (ext !== 'dxf' && ext !== 'dwg') {
    showToast('仅支持 .dxf 和 .dwg 格式', 'warn');
    return;
  }
  const bt = (document.getElementById('drawing-bt') as HTMLInputElement | null)?.value || '';
  const progress = document.getElementById('upload-progress') as HTMLElement | null;
  if (progress) {
    progress.className = 'card mb-4 text-sm text-gray-500';
    progress.innerHTML =
      '<div class="review-progress"><div class="review-progress-text"><span>解析</span><span>0%</span></div>' +
      '<div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
  }

  try {
    const useYolo = (document.getElementById('use-yolo-checkbox') as HTMLInputElement | null)?.checked || false;
    const yoloDevice = (document.getElementById('yolo-device-select') as HTMLSelectElement | null)?.value || 'cpu';
    const result = await apiPostFile('/deconstruct', file, { building_type: bt, use_yolo: useYolo, yolo_device: yoloDevice }) as Record<string, unknown>;

    if (progress) progress.className = 'hidden';

    const fileId = String(result.file_id || 'drawing_' + Date.now());
    setFileCache(fileId, file);

    const entry: Record<string, unknown> = {
      id: fileId,
      filename: file.name,
      building_type: bt,
      parsedAt: new Date().toISOString(),
      elements: (result.elements as Array<Record<string, unknown>>) || [],
      entities: (result.entities as Array<Record<string, unknown>>) || [],
      findings_count: result.findings || 0,
      total_checks: result.total_checks || 0,
      use_yolo: useYolo,
      file_id: fileId,
      raw: result,
    };
    const list = getParsedDrawings();
    list.unshift(entry);
    setParsedDrawings(list);
    saveParsedDrawings();
    renderDrawingList();
    refreshReviewDrawingSelect();
    loadDashboard();

    const preview = document.getElementById('drawing-preview') as HTMLElement | null;
    if (preview) {
      preview.className = 'card';
      const jsonEl = document.getElementById('parse-result-json') as HTMLElement | null;
      if (jsonEl) jsonEl.textContent = JSON.stringify(result, null, 2);
    }
  } catch (e) {
    if (progress) {
      progress.innerHTML = '❌ 解析失败: ' + String(e);
      progress.className = 'card mb-4 text-sm text-red-500';
    }
  }
}

// ── 批量审查 ─────────────────────────────────────────────────
export async function batchReview(): Promise<void> {
  const selected = getParsedDrawings().filter((d) => d._selected);
  if (selected.length === 0) { showToast('请先勾选要送审的图纸', 'info'); return; }

  const progress = document.getElementById('upload-progress') as HTMLElement | null;
  if (progress) {
    progress.className = 'card mb-4';
    progress.innerHTML =
      '<div class="review-progress"><div class="review-progress-text"><span>批量审查</span><span>0%</span></div>' +
      '<div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
  }

  let totalViolations = 0;
  const results: Array<Record<string, unknown>> = [];

  for (const d of selected) {
    try {
    const r = (await apiPost('/review-from-data', {
      entities: d.elements || [],
      building_type: d.building_type,
    })) as Record<string, unknown>;
    if (r.status === 'completed' || r.status === 'success') {
        const v = (r.details as Array<unknown>)?.length || 0;
        totalViolations += v;
        results.push({ name: d.filename, violations: v, details: r.details });
      }
    } catch (e) {
      results.push({ name: d.filename, violations: -1, error: String(e) });
    }
  }

  if (progress) {
    progress.className = 'card mb-4 text-sm';
    let html = '✅ 批量审查完成 (' + selected.length + ' 张, 共 ' + totalViolations + ' 项违规)<br/><br/>';
    for (const r of results) {
      if (r.error) {
        html += '<div class="text-red-500 text-xs">❌ ' + escHtml(String(r.name)) + ': ' + escHtml(String(r.error)) + '</div>';
      } else {
        const c = Number(r.violations) > 0 ? 'text-red-500' : 'text-green-600';
        html += '<div class="text-xs mb-1">' + escHtml(String(r.name)) + ': <span class="' + c + '">' + r.violations + ' 项违规</span></div>';
      }
    }
    progress.innerHTML = html;
  }

  if (results.length > 0) {
    const fn = (window as unknown as Record<string, unknown>).switchPage as (page: string) => void | undefined;
    fn?.('review');
  }
}

// ── 删除/送审 ─────────────────────────────────────────────────
export function deleteDrawing(idx: number): void {
  const list = getParsedDrawings();
  const d = list[idx];
  if (!d) return;
  if (!confirm('确定删除图纸「' + d.filename + '」的解析记录？')) return;
  list.splice(idx, 1);
  setParsedDrawings(list);
  saveParsedDrawings();
  renderDrawingList();
}

export function sendToReview(idx: number): void {
  const d = getParsedDrawings()[idx];
  if (!d) return;
  document.querySelectorAll('.sidebar-item').forEach((el) => el.classList.remove('active'));
  const target = document.querySelector('[data-page="review"]');
  if (target) target.classList.add('active');
  document.querySelectorAll('.page').forEach((el) => el.classList.remove('active'));
  const page = document.getElementById('page-review');
  if (page) page.classList.add('active');

  const select = document.getElementById('review-drawing-select') as HTMLSelectElement | null;
  if (!select) return;
  for (let i = 0; i < select.options.length; i++) {
    if (select.options[i].value === String(d.id)) { select.selectedIndex = i; break; }
  }
  onReviewDrawingSelect();
}

// ── 下拉刷新 ─────────────────────────────────────────────────
export function refreshReviewDrawingSelect(): void {
  const select = document.getElementById('review-drawing-select') as HTMLSelectElement | null;
  if (!select) return;
  select.innerHTML = '<option value="">— 选择已解析图纸 —</option>';
  getParsedDrawings().forEach((d) => {
    const opt = document.createElement('option');
    opt.value = String(d.id);
    opt.textContent = d.filename + ' (' + (d.building_type === 'civil' ? '民用' : '工业') + ')';
    select.appendChild(opt);
  });
}

export function onReviewDrawingSelect(): void {
  const select = document.getElementById('review-drawing-select') as HTMLSelectElement | null;
  const btn = document.getElementById('review-start-btn') as HTMLButtonElement | null;
  const info = document.getElementById('review-drawing-info') as HTMLElement | null;
  const id = select?.value || '';
  if (!id || !btn || !info) { btn && (btn.disabled = true); info && (info.textContent = ''); return; }
  const d = getParsedDrawings().find((p) => p.id === id);
  if (!d) { btn.disabled = true; info.textContent = ''; return; }
  btn.disabled = false;
  info.textContent = '实体: ' + ((d.elements as Array<unknown>)?.length || 0) + '个 · 已解析: ' + new Date(String(d.parsedAt)).toLocaleString();
}
