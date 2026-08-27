// ── P123 Step 8: 多Sheet审查组件 ─────────────────────
import { getApiBase, getHeaders } from '../core/api-client';
import { escHtml } from '../core/utils';

const _msSheetData: Array<Record<string, unknown>> = [];

async function runMultiSheetReview(): Promise<void> {
  const fileInput = document.getElementById('ms-file-input') as HTMLInputElement | null;
  const file = fileInput?.files?.[0];
  if (!file) { (window as Record<string, unknown>).showToast('请先选择 DXF/DWG 文件', 'info'); return; }

  const btn = document.getElementById('ms-review-start-btn') as HTMLButtonElement | null;
  const loading = document.getElementById('ms-review-loading') as HTMLElement | null;
  const results = document.getElementById('ms-review-results') as HTMLElement | null;
  if (!btn || !loading || !results) return;

  btn.disabled = true;
  btn.textContent = '⏳ 审查中...';
  loading.classList.remove('hidden');
  results.classList.add('hidden');

  const buildingType = (document.getElementById('ms-building-type') as HTMLSelectElement | null)?.value || 'civil';
  const standard = (document.getElementById('ms-standard') as HTMLSelectElement | null)?.value || 'GB 50016-2014';
  const formData = new FormData();
  formData.append('file', file);

  try {
    const url = getApiBase() + `/review-multi-sheet?building_type=${encodeURIComponent(buildingType)}&standard=${encodeURIComponent(standard)}`;
    const r = await fetch(url, { method: 'POST', headers: getHeaders(), body: formData });
    const data = (await r.json()) as { status: string; sheets?: Array<Record<string, unknown>>; project_summary?: Record<string, unknown>; detail?: { message?: string }; message?: string };
    if (!r.ok || data.status !== 'success') {
      throw new Error(data.detail?.message || data.message || '审查失败');
    }
    _msSheetData.splice(0, _msSheetData.length, ...(data.sheets || []));
    renderMultiSheetResults(data);
    results.classList.remove('hidden');
    loading.classList.add('hidden');
    btn.textContent = '📑 重新审查';
    btn.disabled = false;
  } catch (e) {
    loading.classList.add('hidden');
    btn.textContent = '📑 开始多Sheet审查';
    btn.disabled = false;
    (window as Record<string, unknown>).showToast(`❌ 审查失败: ${(e as Error).message}`, 'error');
  }
}

function renderMultiSheetResults(data: Record<string, unknown>): void {
  const ps = (data.project_summary || {}) as Record<string, unknown>;
  const sheets = (data.sheets || []) as Array<{ name?: string; violation_count?: number }>;
  const summaryEl = document.getElementById('ms-project-summary');
  if (summaryEl) {
    const rate = ps.compliance_rate as number;
    const passRate = rate !== undefined ? (rate * 100).toFixed(1) : '--';
    const sev = (ps.violations_by_severity || {}) as Record<string, number>;
    summaryEl.innerHTML =
      '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;">' +
      `<div class="card p-3 text-center"><div class="text-2xl font-bold text-indigo-600">${ps.sheet_count || 0}</div><div class="text-xs text-gray-500 mt-1">Sheet 数量</div></div>` +
      `<div class="card p-3 text-center"><div class="text-2xl font-bold text-blue-600">${ps.total_entities || 0}</div><div class="text-xs text-gray-500 mt-1">总实体</div></div>` +
      `<div class="card p-3 text-center"><div class="text-2xl font-bold text-red-600">${ps.total_violations || 0}</div><div class="text-xs text-gray-500 mt-1">总违规</div></div>` +
      `<div class="card p-3 text-center"><div class="text-2xl font-bold ${parseFloat(passRate) > 80 ? 'text-green-600' : parseFloat(passRate) > 60 ? 'text-yellow-600' : 'text-red-600'}">${passRate}%</div><div class="text-xs text-gray-500 mt-1">合规率</div></div>` +
      '</div>' +
      '<div class="flex gap-4 text-xs text-gray-500">' +
      `<span>🔴 严重: ${sev.critical || 0}</span><span>🟠 主要: ${sev.major || 0}</span><span>🟡 轻微: ${sev.minor || 0}</span>` +
      `<span>⏱ ${ps.processing_time_ms || 0}ms</span></div>`;
  }
  const tabsEl = document.getElementById('ms-sheet-tabs');
  if (tabsEl) {
    tabsEl.innerHTML = sheets.map((s, i) => {
      const vc = s.violation_count || 0;
      const badge = vc > 0 ? `<span class="text-red-500"> (${vc})</span>` : '';
      return `<button class="px-3 py-1.5 rounded-lg font-medium ${i === 0 ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}" onclick="switchMultiSheetTab(${i})">${escHtml(s.name || 'Sheet ' + (i + 1))}${badge}</button>`;
    }).join('');
  }
  if (sheets.length > 0) renderMultiSheetTab(0);
}

function switchMultiSheetTab(index: number): void {
  document.querySelectorAll('#ms-sheet-tabs button').forEach((btn, i) => {
    btn.className = `px-3 py-1.5 rounded-lg font-medium ${i === index ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`;
  });
  renderMultiSheetTab(index);
}

function renderMultiSheetTab(index: number): void {
  const el = document.getElementById('ms-sheet-detail');
  if (!el) return;
  const sheet = _msSheetData[index];
  if (!sheet) { el.innerHTML = '<div class="text-gray-400">无效的 Sheet 索引</div>'; return; }
  const violations = (sheet.violations || []) as Array<Record<string, unknown>>;
  const vc = violations.length;
  if (vc === 0) { el.innerHTML = '<div class="text-center text-green-500 py-4">✅ 该 Sheet 无违规</div>'; return; }
  const order = { critical: 0, major: 1, minor: 2 };
  violations.sort((a, b) => (order[(a.severity as keyof typeof order) ?? 9]) - (order[(b.severity as keyof typeof order) ?? 9]));
  el.innerHTML = '<div class="text-xs space-y-2 max-h-96 overflow-y-auto">' + violations.map((v) => {
    const sev = v.severity as string;
    const label = sev === 'critical' ? '🔴 严重' : sev === 'major' ? '🟠 主要' : '🟡 轻微';
    const color = sev === 'critical' ? 'border-l-red-500' : sev === 'major' ? 'border-l-orange-400' : 'border-l-yellow-400';
    return `<div class="border rounded p-2 ${color}" style="border-left-width:3px;">` +
      `<div class="flex items-center justify-between"><span class="font-medium">${escHtml(v.clause_title as string || v.clause_id as string || '')}</span><span class="text-xs">${label}</span></div>` +
      `<div class="text-gray-500 mt-1">条款: <span class="font-mono">${escHtml(v.clause_id as string || '')}</span>${v.entity_type ? ' · 实体: ' + escHtml(v.entity_type as string) : ''}${v.extracted_value !== undefined ? ' · 实测: ' + v.extracted_value : ''}${v.required_value !== undefined ? ' · 要求: ' + v.required_value : ''}${v.difference !== undefined ? ' · 偏差: ' + v.difference : ''}</div>` +
      `<div class="mt-1 text-xs bg-blue-50 p-1 rounded">💡 ${escHtml(v.correction as string || '')}</div></div>`;
  }).join('') + '</div>';
}

export { runMultiSheetReview, switchMultiSheetTab, renderMultiSheetTab };
