// ── P123 Step 2: Thermal 热工计算组件 ────────────────────
// 从 baa-review.js lines 2060-2346 迁入
// onThermalCompTypeChange / renderThermalThresholds / computeThermalK
// renderThermalViolations / renderMultiLayerEditor / addMultiLayerRow
// removeMultiLayerRow / updateMultiLayerRow / computeMultiLayerK

import { getApiBase, getHeaders } from '../core/api-client';
import { escHtml } from '../core/utils';

// ── 热工常量 ──────────────────────────────────────────────
export const CLIMATE_NAMES: Record<string, string> = {
  severe_cold: '严寒',
  cold: '寒冷',
  hot_cold: '夏热冬冷',
  hot_warm: '夏热冬暖',
};

export const THERMAL_MATERIALS: Record<string, { name: string; lambda: number; density: number }> = {
  rockwool: { name: '岩棉板', lambda: 0.035, density: 800 },
  eps: { name: 'EPS聚苯板', lambda: 0.040, density: 20 },
  xps: { name: 'XPS挤塑板', lambda: 0.030, density: 35 },
  pu: { name: '聚氨酯', lambda: 0.024, density: 40 },
  aerogel: { name: '气凝胶', lambda: 0.012, density: 120 },
};

export const THERMAL_THRESHOLDS: Record<string, Record<string, number>> = {
  severe_cold: { exterior_wall: 0.45, roof: 0.35, ground_floor: 0.30, exterior_window: 2.0 },
  cold: { exterior_wall: 0.60, roof: 0.50, ground_floor: 0.45, exterior_window: 2.4 },
  hot_cold: { exterior_wall: 1.50, roof: 1.20, ground_floor: 0.60, exterior_window: 3.2 },
  hot_warm: { exterior_wall: 2.00, roof: 1.50, ground_floor: 0.80, exterior_window: 4.0 },
};

export const DEFAULT_THERMAL_THICKNESS: Record<string, number> = {
  exterior_wall: 50,
  roof: 60,
  ground_floor: 80,
  exterior_window: 30,
};

export function onThermalCompTypeChange(): void {
  const compType = (document.getElementById('thermal-comp-type') as HTMLSelectElement | null)?.value || '';
  const input = document.getElementById('thermal-thickness') as HTMLInputElement | null;
  if (input) input.value = String(DEFAULT_THERMAL_THICKNESS[compType] || 50);
}

export function renderThermalThresholds(): void {
  const el = document.getElementById('thermal-thresholds') as HTMLElement | null;
  if (!el) return;
  let html = '<table class="w-full"><thead><tr class="text-gray-400 border-b">' +
    '<th class="text-left py-1">气候带</th><th>外墙</th><th>屋顶</th><th>地面</th><th>外窗</th></tr></thead><tbody>';
  for (const [key, thresholds] of Object.entries(THERMAL_THRESHOLDS)) {
    html += '<tr class="border-b"><td class="py-1">' + escHtml(CLIMATE_NAMES[key] || key) + '</td>';
    for (const comp of ['exterior_wall', 'roof', 'ground_floor', 'exterior_window']) {
      html += '<td class="text-center">' + thresholds[comp].toFixed(2) + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

export async function computeThermalK(): Promise<void> {
  const compType = (document.getElementById('thermal-comp-type') as HTMLSelectElement | null)?.value || '';
  const materialKey = (document.getElementById('thermal-material') as HTMLSelectElement | null)?.value || '';
  const thicknessMm = parseFloat((document.getElementById('thermal-thickness') as HTMLInputElement | null)?.value || '0');
  const climate = (document.getElementById('thermal-climate') as HTMLSelectElement | null)?.value || '';
  const resultDiv = document.getElementById('thermal-result') as HTMLElement | null;

  if (isNaN(thicknessMm) || thicknessMm <= 0) {
    if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">厚度无效</span>';
    return;
  }
  if (resultDiv) resultDiv.innerHTML = '<span class="text-gray-400">⏳ 计算中...</span>';

  try {
    const r = await fetch(getApiBase() + '/api/v1/review/thermal/k-value', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compType, material: materialKey, thicknessMm, climate }),
    });
    const data = (await r.json()) as Record<string, unknown>;

    if (data.status !== 'success') {
      if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">后端返回异常</span>';
      return;
    }

    const pass = Boolean(data.passed);
    let html = '<div class="mt-2 p-2 ' + (pass ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200') + ' rounded">';
    html += '<p class="font-medium ' + (pass ? 'text-green-700' : 'text-red-700') + '">';
    html += 'K = ' + data.K + ' W/(m²·K) ' + (pass ? '✅ ≤ ' : '❌ > ') + data.threshold;
    html += '</p>';
    html += '<p>材料: ' + data.material + ' (λ=' + data.lambda + ') · 厚度: ' + data.thicknessMm + 'mm · R=' + data.R + ' m²·K/W</p>';

    if (!pass) {
      html += '<p class="text-orange-600 mt-1">→ 改用当前材料需厚度 ≥ ' + data.requiredThicknessMm + 'mm（当前差 ' + data.additionalThicknessMm + 'mm）</p>';
    } else {
      const climateLabel = CLIMATE_NAMES[data.climate as string] || String(data.climate);
      html += '<p class="text-gray-500 mt-1">→ 满足 GB55015-3.2.2 ' + climateLabel + ' 要求</p>';
    }
    html += '</div>';
    if (resultDiv) resultDiv.innerHTML = html;

    try { localStorage.setItem('baa_last_thermal_result', JSON.stringify(data)); } catch (_e) {}
  } catch (e) {
    if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">计算失败: ' + (e as Error).message + '</span>';
  }
}

export function renderThermalViolations(thermalViolations: Array<Record<string, unknown>>): void {
  const el = document.getElementById('thermal-review-list') as HTMLElement | null;
  if (!el) return;
  if (!thermalViolations || thermalViolations.length === 0) {
    el.innerHTML = '<span class="text-gray-400">✅ 单图审查后自动展示热工违规项</span>';
    return;
  }
  let html = '<p class="font-medium text-sm mb-1 text-orange-600">🌡️ 热工违规 (' + thermalViolations.length + '项)</p>';

  const corrs = ((window as unknown as Record<string, unknown>)._currentReviewResult as Record<string, unknown> | undefined)?.corrections as Array<Record<string, unknown>> || [];

  thermalViolations.forEach((f) => {
    const funcId = String(f.func_id || 'THERM-xxx');
    const title = String(f.clause_title || f.description || '未知条款');
    const clauseId = String(f.clause_id || '');
    const actual = f.extracted_value ?? f.actual_value ?? '?';
    const required = f.required_value ?? f.threshold ?? '?';
    const sev = String(f.severity || 'major');
    const sevColor = sev === 'critical' ? 'red' : sev === 'major' ? 'orange' : 'yellow';
    const sevLabel = sev === 'critical' ? '严重' : sev === 'major' ? '主要' : '轻微';
    const conf = typeof f.confidence === 'number' ? f.confidence : 1.0;
    const confPct = Math.round(conf * 100);
    const confColor = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'red';

    const corrKey = String(f.clause_id || f.func_id || '').trim();
    const matchedCorrs = corrs.filter((c) => c.clause_id === corrKey);
    const hasCorr = matchedCorrs.length > 0;

    html += '<div class="p-1.5 rounded bg-' + sevColor + '-50 border-l-2 border-' + sevColor + '-400 mb-1">';
    html += '<div class="flex justify-between items-start"><p class="font-medium text-' + sevColor + '-700">' + escHtml(funcId) + '</p>' +
      '<div class="flex gap-1"><span class="px-1 rounded text-xs bg-' + sevColor + '-100 text-' + sevColor + '-700">' + sevLabel + '</span>' +
      '<span class="px-1 rounded text-xs bg-' + confColor + '-100 text-' + confColor + '-700" title="置信度 '+confPct+'%">' +
      (conf >= 0.85 ? '高' : conf >= 0.6 ? '中' : '低') + '</span></div></div>' +
      '<p class="text-xs text-gray-600">' + escHtml(title) + '</p>' +
      '<p class="text-xs text-gray-500">实测: ' + (typeof actual === 'number' ? actual.toFixed(3) : escHtml(String(actual))) + ' · 要求: ' + (typeof required === 'number' ? required.toFixed(3) : escHtml(String(required))) + ' · [' + escHtml(clauseId) + ']</p>' +
      '<div class="mt-1 bg-gray-200 rounded-full h-1 overflow-hidden"><div class="' + confColor + '-500 h-full rounded-full" style="width:' + confPct + '%"></div></div>';

    if (hasCorr) {
      const top = matchedCorrs[0];
      const pColor = String(top.priority) === 'high' ? 'red' : String(top.priority) === 'medium' ? 'orange' : 'yellow';
      const pLabel = String(top.priority) === 'high' ? '🔴 高' : String(top.priority) === 'medium' ? '🟠 中' : '🟡 低';
      html += '<details class="mt-0.5"><summary class="cursor-pointer text-purple-600 font-medium text-xs">💡 修正建议 (' + matchedCorrs.length + '条)</summary>' +
        '<div class="mt-0.5 p-1 bg-' + pColor + '-50 rounded border-l-2 border-' + pColor + '-400">' +
        '<p class="text-xs"><span class="text-' + pColor + '-600">' + pLabel + '</span> ' + escHtml(String(top.recommendation)) + '</p></div></details>';
    }
    html += '</div>';
  });
  el.innerHTML = html;
}