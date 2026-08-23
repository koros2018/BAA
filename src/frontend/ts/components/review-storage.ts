// ── P123 Step 2: ReviewStorage 审查结果存储 ─────────────
// 从 baa-review.js lines 1418-1463 迁入
// loadReviewResults / fallbackLoadReviewResults / refreshCompareDrawingSelect

import { getApiBase, getHeaders } from '../core/api-client';

export interface ReviewResult {
  id?: string;
  drawingName?: string;
  buildingType?: string;
  details?: Array<Record<string, unknown>>;
  summary?: Record<string, unknown>;
}

let _reviewResults: ReviewResult[] = [];

export function getReviewResults(): ReviewResult[] {
  return _reviewResults;
}

export function setReviewResults(r: ReviewResult[]): void {
  _reviewResults = r;
}

export async function loadReviewResults(): Promise<void> {
  const apiBase = getApiBase();
  const teamFilter = (document.getElementById('history-team-filter') as HTMLInputElement | null)?.value || '';
  const projFilter = (document.getElementById('history-project-filter') as HTMLInputElement | null)?.value || '';
  let params = 'limit=200';
  if (teamFilter) params += '&team_id=' + encodeURIComponent(teamFilter);
  if (projFilter) params += '&project_id=' + encodeURIComponent(projFilter);
  try {
    const r = await fetch(apiBase + '/review/history?' + params, {
      method: 'GET',
      headers: getHeaders(),
    });
    const data = (await r.json()) as Record<string, unknown>;
    if (data && data.items && (data.items as Array<ReviewResult>).length > 0) {
      _reviewResults = data.items as ReviewResult[];
      try { localStorage.setItem('baa_review_results', JSON.stringify(_reviewResults)); } catch (_e) {}
      return;
    }
    fallbackLoadReviewResults();
  } catch (_e) {
    fallbackLoadReviewResults();
  }
}

export function fallbackLoadReviewResults(): void {
  try {
    const stored = localStorage.getItem('baa_review_results');
    if (stored) _reviewResults = JSON.parse(stored);
  } catch (_e) {
    _reviewResults = [];
  }
}

export function refreshCompareDrawingSelect(): void {
  const select = document.getElementById('compare-drawing-select') as HTMLSelectElement | null;
  if (!select) return;
  select.innerHTML = '<option value="">— 选择已审查图纸 —</option>';
  _reviewResults.forEach((r) => {
    const opt = document.createElement('option');
    opt.value = r.id || '';
    opt.textContent =
      (r.drawingName || '') +
      ' (' +
      (r.buildingType === 'civil' ? '民用' : '工业') +
      ') - ' +
      ((r.details || []).length || 0) +
      '项违规';
    select.appendChild(opt);
  });
}