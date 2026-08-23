// ── P123 Step 2: Structural 结构验算组件 ───────────────
// 从 baa-review.js lines 2347-2463 迁入
// renderStructuralThresholds / onStructuralCompTypeChange
// computeStructuralCheck / renderStructuralViolations

import { escHtml } from '../core/utils';

export const STRUCTURAL_PARAMS: Record<
  string,
  { label: string; op: string; threshold: Record<string, number>; unit: string; clause: string }
> = {
  floor_live: { label: '楼面活荷载', clause: 'GB50009-5.1.1', unit: 'kN/㎡', threshold: { 住宅: 2.0, 办公: 2.5, 商业: 3.5, 图书馆: 4.0, 档案: 5.0, 车库: 2.5 }, op: '>=' },
  beam_reinforcement: { label: '梁最小配筋率', clause: 'GB50010-9.2.1', unit: '%', threshold: { 默认: 0.20 }, op: '>=' },
  column_reinforcement: { label: '柱纵向配筋率下限', clause: 'GB50010-11.4.12', unit: '%', threshold: { 抗震一级: 0.55, 抗震二级: 0.50, 抗震三级: 0.55, 抗震四级: 0.50 }, op: '>=' },
  foundation_depth: { label: '基础最小埋深', clause: 'GB50007-5.1.3', unit: 'm', threshold: { 默认: 0.50, 冻土区: 1.00 }, op: '>=' },
  slab_thickness: { label: '楼板最小厚度', clause: 'GB50010-9.1.2', unit: 'mm', threshold: { 默认: 80, 屋面板: 90 }, op: '>=' },
  beam_height: { label: '梁高跨比', clause: 'GB50010-9.2.3', unit: '1/跨', threshold: { 简支: 0.083, 连续: 0.067 }, op: '>=' },
  concrete_strength: { label: '混凝土最低强度等级', clause: 'GB50010-4.1.2', unit: 'MPa', threshold: { 默认: 20, 预应力: 40 }, op: '>=' },
  seismic_grade: { label: '抗震等级标注', clause: 'GB55008-3.2.1', unit: '有/无', threshold: { 必须: 1 }, op: '==' },
  seismic_intensity: { label: '抗震设防烈度', clause: 'GB55008-3.1.1', unit: '度', threshold: { 最小: 6 }, op: '>=' },
  shear_wall_thickness: { label: '剪力墙最小厚度', clause: 'GB55008-4.3.1', unit: 'mm', threshold: { 默认: 160, 框支层: 200 }, op: '>=' },
  pile_count: { label: '柱下独立桩基数量', clause: 'GB55008-4.1.1', unit: '根', threshold: { 默认: 2, 条形桩基: 3 }, op: '>=' },
};

export function renderStructuralThresholds(): void {
  const el = document.getElementById('structural-thresholds') as HTMLElement | null;
  if (!el) return;
  let html = '<table class="w-full"><thead><tr class="text-gray-400 border-b">' +
    '<th class="text-left py-1">构件</th><th>要求</th><th>单位</th><th>规范</th></tr></thead><tbody>';
  for (const [_key, p] of Object.entries(STRUCTURAL_PARAMS)) {
    const threshText = Object.entries(p.threshold).map(([k, v]) => k + ':' + v).join(' / ');
    html +=
      '<tr class="border-b"><td class="py-1">' + escHtml(p.label) + '</td>' +
      '<td class="text-center">' + p.op + ' ' + threshText + '</td>' +
      '<td class="text-center">' + escHtml(p.unit) + '</td>' +
      '<td class="text-gray-500">' + escHtml(p.clause) + '</td></tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

export function onStructuralCompTypeChange(): void {
  const type = (document.getElementById('structural-comp-type') as HTMLSelectElement | null)?.value || '';
  const p = STRUCTURAL_PARAMS[type];
  if (!p) return;
  const firstKey = Object.keys(p.threshold)[0];
  const input = document.getElementById('structural-value') as HTMLInputElement | null;
  if (input && firstKey) input.value = String(p.threshold[firstKey]);
}

export async function computeStructuralCheck(): Promise<void> {
  const compType = (document.getElementById('structural-comp-type') as HTMLSelectElement | null)?.value || '';
  const value = parseFloat((document.getElementById('structural-value') as HTMLInputElement | null)?.value || '0');
  const note = (document.getElementById('structural-note') as HTMLInputElement | null)?.value || '';
  const resultDiv = document.getElementById('structural-result') as HTMLElement | null;

  if (isNaN(value)) {
    if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">输入值无效</span>';
    return;
  }
  const p = STRUCTURAL_PARAMS[compType];
  if (!p) return;

  let activeThreshold: number | null = null;
  let activeThresholdLabel = '';
  for (const [label, t] of Object.entries(p.threshold)) {
    if (note && note.includes(label)) {
      activeThreshold = t;
      activeThresholdLabel = label;
      break;
    }
  }
  if (activeThreshold === null) {
    const keys = Object.keys(p.threshold);
    activeThreshold = p.threshold[keys[0] || ''];
    activeThresholdLabel = keys[0] || '';
  }

  let passed = false;
  if (activeThreshold !== null) {
    if (p.op === '>=') passed = value >= activeThreshold;
    else if (p.op === '<=') passed = value <= activeThreshold;
    else if (p.op === '==') passed = value === activeThreshold;
    else if (p.op === '>') passed = value > activeThreshold;
    else if (p.op === '<') passed = value < activeThreshold;
    else passed = value === activeThreshold;
  }

  const sign = p.op === '>=' ? '≥' : p.op === '<=' ? '≤' : p.op === '==' ? '=' : p.op;
  let html = '<div class="mt-2 p-2 ' + (passed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200') + ' rounded">';
  html += '<p class="font-medium ' + (passed ? 'text-green-700' : 'text-red-700') + '">';
  html += escHtml(p.label) + ': ' + value + ' ' + p.unit + ' ' + (passed ? '✅ ' : '❌ ') + sign + ' ' + activeThreshold + ' ' + p.unit;
  html += '</p>';
  html += '<p class="text-xs text-gray-500">规范: ' + p.clause + ' · 适用条件: ' + escHtml(activeThresholdLabel) + '</p>';
  if (!passed) {
    html += '<p class="text-orange-600 text-xs mt-1">→ 当前值不满足规范要求，建议修正至 ' + sign + ' ' + activeThreshold + ' ' + p.unit + '</p>';
  }
  html += '</div>';
  if (resultDiv) resultDiv.innerHTML = html;
}

export function renderStructuralViolations(structuralViolations: Array<Record<string, unknown>>): void {
  const el = document.getElementById('structural-review-list') as HTMLElement | null;
  if (!el) return;
  if (!structuralViolations || structuralViolations.length === 0) {
    el.innerHTML = '<span class="text-gray-400">✅ 单图审查后自动展示结构违规项</span>';
    return;
  }
  let html = '';
  structuralViolations.forEach((f) => {
    const funcId = String(f.func_id || 'STR-xxx');
    const title = String(f.clause_title || f.description || '未知条款');
    const clauseId = String(f.clause_id || '');
    const actual = f.extracted_value ?? f.actual_value ?? '?';
    const required = f.required_value ?? f.threshold ?? '?';
    const isFail = f.result === 'FAIL';
    html += '<div class="p-1.5 rounded ' + (isFail ? 'bg-red-50 border-l-2 border-red-400' : 'bg-green-50 border-l-2 border-green-400') + ' mb-1">';
    html += '<p class="font-medium ' + (isFail ? 'text-red-700' : 'text-green-700') + '">' + escHtml(funcId) + '</p>';
    html += '<p class="text-gray-600">' + escHtml(title) + '</p>';
    html += '<p class="text-xs text-gray-500">实测: ' + (typeof actual === 'number' ? actual.toFixed(3) : escHtml(String(actual))) + ' · 要求: ' + (typeof required === 'number' ? required.toFixed(3) : escHtml(String(required))) + ' · [' + escHtml(clauseId) + ']</p>';
    html += '</div>';
  });
  el.innerHTML = html;
}