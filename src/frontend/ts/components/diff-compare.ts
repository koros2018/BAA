// ── P123 Step 2: Diff 对比组件 ──────────────────────────
// 从 baa-review.js lines 1068-1328 迁入
// _onDiffFileSelect / runDiffComparison / renderDiffResults
// renderDiffItemPanel / switchDiffTab / loadDiffVisualization / clearDiffResults

import { getApiBase, getReviewHeaders } from '../core/api-client';
import { showToast } from '../core/toast';
import { escHtml } from '../core/utils';
import { renderProgress } from '../core/skeleton';

let _diffResult: unknown = null;

export function _onDiffFileSelect(inputId: string, labelId: string): void {
  const input = document.getElementById(inputId) as HTMLInputElement | null;
  const label = document.getElementById(labelId) as HTMLElement | null;
  if (!input || !label) return;
  input.addEventListener('change', () => {
    label.textContent = input.files && input.files[0] ? input.files[0].name : '';
  });
}
_onDiffFileSelect('diff-file1', 'diff-file1-name');
_onDiffFileSelect('diff-file2', 'diff-file2-name');

export async function runDiffComparison(): Promise<void> {
  const file1 = (document.getElementById('diff-file1') as HTMLInputElement | null)?.files?.[0];
  const file2 = (document.getElementById('diff-file2') as HTMLInputElement | null)?.files?.[0];
  if (!file1 || !file2) { showToast('请选择两个版本的图纸文件', 'info'); return; }

  const bt = (document.getElementById('diff-building-type') as HTMLInputElement | null)?.value || '';
  const std = (document.getElementById('diff-standard') as HTMLInputElement | null)?.value || '';
  const loading = document.getElementById('diff-loading') as HTMLElement | null;
  if (loading) {
    loading.className = 'mt-3';
    renderProgress(loading, '审查并对比', 20);
  }

  try {
    const form = new FormData();
    form.append('file1', file1);
    form.append('file2', file2);

    const url = getApiBase() + '/review/compare?building_type=' + encodeURIComponent(bt) + '&standard=' + encodeURIComponent(std);
    const resp = await fetch(url, { method: 'POST', headers: getReviewHeaders(), body: form });
    const data = await resp.json();
    if (loading) loading.className = 'hidden';

    if (resp.status !== 200) {
      showToast('对比失败: ' + ((data as Record<string, unknown>).detail || JSON.stringify(data)), 'error');
      return;
    }
    _diffResult = data;
    renderDiffResults(data as DiffData);
  } catch (e) {
    if (loading) {
      loading.className = 'mt-3 text-sm text-red-500';
      loading.innerHTML = '❌ 请求失败: ' + (e as Error).message;
    }
  }
}

interface DiffData {
  summary?: Record<string, number>;
  items?: Array<Record<string, unknown>>;
  v1_file_id?: string;
  v2_file_id?: string;
}

export function renderDiffResults(data: DiffData): void {
  const s = data.summary || {};
  const empty = document.getElementById('diff-empty') as HTMLElement | null;
  const results = document.getElementById('diff-results') as HTMLElement | null;
  if (empty) empty.className = 'hidden';
  if (results) results.className = '';

  const summaryDiv = document.getElementById('diff-summary') as HTMLElement | null;
  const newC = s.new_violations || 0;
  const fixedC = s.fixed_violations || 0;
  const changedC = s.changed_violations || 0;
  const totalV1 = s.total_v1 || 0;
  const totalV2 = s.total_v2 || 0;

  if (summaryDiv) {
    summaryDiv.innerHTML =
      '<div class="card p-3 text-center"><div class="text-lg font-bold text-blue-600">' + totalV1 + ' → ' + totalV2 + '</div><div class="text-xs text-gray-400">违规数</div></div>' +
      '<div class="card p-3 text-center"><div class="text-lg font-bold text-green-600">' + newC + '</div><div class="text-xs text-gray-400">🆕 新增违规</div></div>' +
      '<div class="card p-3 text-center"><div class="text-lg font-bold text-emerald-600">' + fixedC + '</div><div class="text-xs text-gray-400">✅ 已修复</div></div>' +
      '<div class="card p-3 text-center"><div class="text-lg font-bold text-yellow-600">' + changedC + '</div><div class="text-xs text-gray-400">🔄 变化项</div></div>' +
      '<div class="card p-3 text-center"><div class="text-lg font-bold ' + (newC === 0 ? 'text-green-600' : 'text-red-600') + '">' + (newC === 0 ? '✓ 合格' : newC + '项') + '</div><div class="text-xs text-gray-400">综合评估</div></div>';
  }

  const items = data.items || [];
  const groups: Record<string, Array<Record<string, unknown>>> = { new: [], fixed: [], changed: [] };
  items.forEach((item) => {
    const t = String(item.diff_type || 'new');
    if (groups[t]) groups[t].push(item);
  });
  ['new', 'fixed', 'changed'].forEach((t) => renderDiffItemPanel(t, groups[t] || []));

  const rawEl = document.getElementById('diff-raw-json') as HTMLElement | null;
  if (rawEl) rawEl.textContent = JSON.stringify(data, null, 2);

  loadDiffVisualization(data);
  switchDiffTab('new');
}

export function renderDiffItemPanel(type: string, items: Array<Record<string, unknown>>): void {
  const el = document.getElementById('diff-items-' + type) as HTMLElement | null;
  if (!el) return;
  if (items.length === 0) {
    const labels: Record<string, string> = { new: '🆕 无新增违规', fixed: '✅ 无已修复项', changed: '🔄 无变化项' };
    el.innerHTML = '<div class="text-xs text-gray-400 py-4 text-center">' + (labels[type] || '无差异项') + '</div>';
    return;
  }
  const typeColors: Record<string, string> = { new: 'red', fixed: 'green', changed: 'yellow' };
  const tc = typeColors[type] || 'gray';

  let html = '<div class="flex items-center gap-2 mb-2"><span class="text-xs text-gray-500">共 ' + items.length + ' 项</span><span class="text-xs text-gray-400">|</span><span class="text-xs text-gray-400">严重: ' + items.filter((i) => i.severity === 'critical').length + '</span><span class="text-xs text-gray-400">|</span><span class="text-xs text-gray-400">一般: ' + items.filter((i) => i.severity === 'normal' || !i.severity).length + '</span></div>';

  html += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
    '<th class="pb-1 pr-2">条款</th><th class="pb-1 pr-2">实体</th><th class="pb-1 pr-2">类型</th>';

  if (type === 'new') html += '<th class="pb-1 pr-2">实测值</th><th class="pb-1 pr-2">要求值</th>';
  else if (type === 'fixed') html += '<th class="pb-1 pr-2">原实测值</th><th class="pb-1 pr-2">要求值</th>';
  else html += '<th class="pb-1 pr-2">旧值</th><th class="pb-1 pr-2">新值</th>';

  html += '<th class="pb-1">严重度</th></tr></thead><tbody>';

  items.forEach((item) => {
    const sev = String(item.severity || '');
    const sevColor = sev === 'critical' ? 'red' : sev === 'normal' ? 'orange' : 'gray';
    const sevLabel = sev === 'critical' ? '严重' : sev === 'normal' ? '一般' : '轻微';
    const oldV = item.old_value != null ? Number(item.old_value).toFixed(2) : '-';
    const newV = item.new_value != null ? Number(item.new_value).toFixed(2) : '-';
    const reqV = item.old_required != null ? item.old_required : item.new_required != null ? item.new_required : '-';

    html += '<tr class="border-b border-gray-50 hover:bg-gray-50">' +
      '<td class="py-1.5 pr-2"><span title="' + escHtml(String(item.clause_title || '')) + '" class="cursor-help">' + escHtml(String(item.clause_id || '')) + '</span></td>' +
      '<td class="py-1.5 pr-2 truncate max-w-20" title="' + escHtml(String(item.entity_id || '')) + '">' + escHtml(String(item.entity_type || '-')) + '</td>' +
      '<td class="py-1.5 pr-2">' + (item.entity_id ? escHtml(String(item.entity_id).slice(0, 16)) : '-') + '</td>';

    if (type === 'new') html += '<td class="py-1.5 pr-2 text-red-600">' + newV + '</td><td class="py-1.5 pr-2">' + reqV + '</td>';
    else if (type === 'fixed') html += '<td class="py-1.5 pr-2 text-green-600 line-through">' + oldV + '</td><td class="py-1.5 pr-2">' + reqV + '</td>';
    else html += '<td class="py-1.5 pr-2 text-gray-400">' + oldV + '</td><td class="py-1.5 pr-2 text-yellow-600">' + newV + '</td>';

    html += '<td class="py-1.5"><span class="px-1.5 py-0.5 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span></td></tr>';

    if (item.explanation) {
      html += '<tr class="border-b border-gray-50"><td colspan="7" class="pb-1.5 pl-4 text-gray-400 text-xs">💡 ' + escHtml(String(item.explanation).slice(0, 120)) + '</td></tr>';
    }
  });

  html += '</tbody></table>';
  el.innerHTML = html;
}

export function switchDiffTab(tab: string): void {
  ['new', 'fixed', 'changed'].forEach((t) => {
    const panel = document.getElementById('diff-items-' + t) as HTMLElement | null;
    if (panel) panel.className = 'diff-items-panel' + (t === tab ? '' : ' hidden');
  });
  document.querySelectorAll('.diff-tab-btn').forEach((btn) => {
    const isActive = (btn as HTMLElement).dataset.tab === tab;
    (btn as HTMLElement).className = 'diff-tab-btn px-3 py-1 rounded-lg font-medium ' + (isActive ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600');
  });
}

export function loadDiffVisualization(data: DiffData): void {
  const v1FileId = data.v1_file_id;
  const v2FileId = data.v2_file_id;
  const items = data.items || [];
  const v1El = document.getElementById('diff-vis-v1') as HTMLElement | null;
  const v2El = document.getElementById('diff-vis-v2') as HTMLElement | null;

  const makeUrl = (fileId?: string, isV1 = false) => {
    if (!fileId) return null;
    const filtered = items.filter((item) => (isV1 && item.diff_type === 'fixed') || (!isV1 && item.diff_type === 'new'));
    return getApiBase() + '/render/' + encodeURIComponent(fileId) + '/overlay?violations=' + encodeURIComponent(JSON.stringify(filtered.slice(0, 50).map((item) => ({
      entity_type: item.entity_type || 'unknown',
      severity: item.severity || 'major',
      clause_id: item.clause_id || '',
      x: 0, y: 0,
    }))));
  };

  const v1Url = makeUrl(v1FileId, true);
  const v2Url = makeUrl(v2FileId, false);

  if (v1El && v1Url) {
    v1El.innerHTML = '<img src="' + v1Url + '" class="w-full" alt="版本1图纸" style="max-height:400px" onerror="this.outerHTML=\'<div class=text-center py-8 text-gray-400 text-xs>⚠️ 图纸渲染失败</div>\'" />';
  } else if (v1El) {
    v1El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无渲染数据</div>';
  }

  if (v2El && v2Url) {
    v2El.innerHTML = '<img src="' + v2Url + '" class="w-full" alt="版本2图纸" style="max-height:400px" onerror="this.outerHTML=\'<div class=text-center py-8 text-gray-400 text-xs>⚠️ 图纸渲染失败</div>\'" />';
  } else if (v2El) {
    v2El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无渲染数据</div>';
  }
}

export function clearDiffResults(): void {
  const file1 = document.getElementById('diff-file1') as HTMLInputElement | null;
  const file2 = document.getElementById('diff-file2') as HTMLInputElement | null;
  if (file1) file1.value = '';
  if (file2) file2.value = '';
  const name1 = document.getElementById('diff-file1-name') as HTMLElement | null;
  const name2 = document.getElementById('diff-file2-name') as HTMLElement | null;
  if (name1) name1.textContent = '';
  if (name2) name2.textContent = '';
  const results = document.getElementById('diff-results') as HTMLElement | null;
  if (results) results.className = 'hidden';
  const empty = document.getElementById('diff-empty') as HTMLElement | null;
  if (empty) {
    empty.className = 'card text-center py-8 text-gray-300';
    empty.textContent = '上传两个版本的图纸后开始对比';
  }
  _diffResult = null;
}