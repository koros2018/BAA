// ── P123 Step 2: Correction AI 修正建议组件 ─────────────
// 从 baa-review.js lines 1849-1923 迁入
// generateCorrectionSuggestions / confirmCorrection

import { getApiBase, getReviewHeaders } from '../core/api-client';
import { showToast } from '../core/toast';

export async function generateCorrectionSuggestions(): Promise<void> {
  const result = (window as unknown as Record<string, unknown>)._currentReviewResult;
  const entities = (window as unknown as Record<string, unknown>)._currentReviewEntities;
  if (!result || !entities) {
    showToast('请先运行审查', 'info');
    return;
  }

  const rr = result as Record<string, unknown>;
  const findings = ((rr.findings as Array<Record<string, unknown>> || []) as Array<Record<string, unknown>>).filter((f) => f.result === 'FAIL' && !f.is_duplicate);
  if (findings.length === 0) {
    const el = document.getElementById('correction-results') as HTMLElement | null;
    if (el) el.innerHTML = '<div class="text-green-600">✅ 无违规，无需修正建议</div>';
    return;
  }

  const panel = document.getElementById('review-correction-panel') as HTMLElement | null;
  const loading = document.getElementById('correction-loading') as HTMLElement | null;
  const resultsDiv = document.getElementById('correction-results') as HTMLElement | null;
  const btn = document.getElementById('correction-generate-btn') as HTMLButtonElement | null;
  const modeSelect = document.getElementById('correction-mode-select') as HTMLSelectElement | null;

  if (panel) panel.className = panel.className.replace(/hidden/g, '').trim();
  if (loading) loading.className = '';
  if (resultsDiv) resultsDiv.innerHTML = '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '...';
  }

  try {
    const mode = modeSelect?.value || 'auto';
    const r = await fetch(getApiBase() + '/correction/suggestions', {
      method: 'POST',
      headers: { ...getReviewHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ findings, entities, mode }),
    });
    const data = (await r.json()) as Record<string, unknown>;
    if (loading) loading.className = 'hidden';

    const suggestions = data.suggestions as Array<Record<string, unknown>> | undefined;
    if (!suggestions || suggestions.length === 0) {
      if (resultsDiv) resultsDiv.innerHTML = '<div class="text-gray-500">未生成修正建议（规则引擎无匹配）</div>';
      return;
    }

    const priorityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
    const sorted = suggestions.slice().sort((a, b) => (priorityOrder[String(a.priority)] ?? 3) - (priorityOrder[String(b.priority)] ?? 3));

    let html = '<p class="mb-1 text-gray-500">共 ' + sorted.length + ' 条建议（' + mode + ' 模式）</p>';
    for (const s of sorted) {
      const pColor = String(s.priority) === 'high' ? 'red' : String(s.priority) === 'medium' ? 'orange' : 'yellow';
      const pLabel = String(s.priority) === 'high' ? '🔴 高' : String(s.priority) === 'medium' ? '🟠 中' : '🟡 低';
      html += '<div class="p-1.5 bg-gray-50 rounded border-l-2 border-' + pColor + '-400">';
      html += '<p class="font-medium"><span class="text-' + pColor + '-600">' + pLabel + '</span> [' + s.clause_id + '] ' + s.description + '</p>';
      html += '<p class="text-gray-600 mt-0.5">💡 ' + s.recommendation + '</p>';
      if (Object.keys((s.parameters || {}) as Record<string, unknown>).length > 0) {
        html += '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(s.parameters) + '</p>';
      }
      html += '</div>';
    }
    if (resultsDiv) resultsDiv.innerHTML = html;
  } catch (e) {
    if (loading) loading.className = 'hidden';
    if (resultsDiv) resultsDiv.innerHTML = '<div class="text-red-600">生成失败: ' + (e as Error).message + '</div>';
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '生成';
    }
  }
}

export function confirmCorrection(reviewId: string, corrIdx: number, accepted: boolean): void {
  const key = 'corr_' + reviewId + '_' + corrIdx;
  localStorage.setItem(key, accepted ? 'accepted' : 'rejected');
  const select = document.getElementById('compare-drawing-select') as HTMLSelectElement | null;
  if (select && select.value) {
    const fn = (window as unknown as Record<string, unknown>).onCompareSelect as (this: unknown) => unknown;
    if (typeof fn === 'function') fn();
  }
}