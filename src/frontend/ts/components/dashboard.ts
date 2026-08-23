// ── P123 Step 2: Dashboard 概览页组件 ────────────────────
// 从 baa-review.js lines 13-86 迁入
// loadDashboard / renderRecentReviews / renderSpecFreqBars / renderViolationTypeBars

import { apiGet } from '../core/api-client';
import { escHtml } from '../core/utils';
import { getSpecData } from '../core/spec-data';
import { getReviewResults, loadReviewResults } from './review-storage';

export async function loadDashboard(): Promise<void> {
  try {
    const health = (await apiGet('/health')) as Record<string, unknown>;
    const verEl = document.getElementById('version-info') as HTMLElement | null;
    const hsEl = document.getElementById('health-status') as HTMLElement | null;
    if (verEl) verEl.textContent = String(health.version || '') + ' · 引擎就绪';
    if (hsEl) hsEl.textContent = JSON.stringify(health, null, 2);

    await loadReviewResults();
    const results = getReviewResults();

    const stats = document.getElementById('home-stats') as HTMLElement | null;
    if (stats) {
      const cards = stats.querySelectorAll('.stat-card');
      if (cards[0]) (cards[0].querySelector('.text-2xl') as HTMLElement).textContent = String(results.length);
      const specData = getSpecData() as Array<Record<string, unknown>>;
      if (cards[1]) (cards[1].querySelector('.text-2xl') as HTMLElement).textContent = String(specData.length);
      if (results.length > 0) {
        const totalV = results.reduce((s, r) => s + (Array.isArray(r.details) ? r.details.length : 0), 0);
        const totalC = results.reduce(
          (s, r) => s + ((typeof r.summary === 'object' && r.summary !== null ? Number((r.summary as Record<string, unknown>).total_checks || 0) : 0)),
          0,
        );
        const passRate = totalC > 0 ? Math.round((1 - totalV / totalC) * 100) + '%' : '--';
        (cards[2].querySelector('.text-2xl') as HTMLElement).textContent = passRate;
        (cards[3].querySelector('.text-2xl') as HTMLElement).textContent = String((results[0] as Record<string, unknown>).drawingName || '');
      }
    }

    renderRecentReviews();
    renderSpecFreqBars();
    renderViolationTypeBars();
  } catch (e) {
    const verEl = document.getElementById('version-info') as HTMLElement | null;
    const hsEl = document.getElementById('health-status') as HTMLElement | null;
    if (verEl) verEl.textContent = '⚠️ 服务未连接';
    if (hsEl) hsEl.textContent = '连接失败: ' + (e as Error).message;
  }
}

export function renderRecentReviews(): void {
  const el = document.getElementById('recent-reviews') as HTMLElement | null;
  if (!el) return;
  const results = getReviewResults();
  if (results.length === 0) {
    el.innerHTML = '<div class="text-xs text-gray-400">暂无审查记录</div>';
    return;
  }
  const recent = results.slice(0, 5);
  el.innerHTML = recent
    .map((r) => {
      const rr = r as Record<string, unknown>;
      const v = (rr.details as Array<unknown>)?.length || 0;
      const color = v === 0 ? 'green' : 'red';
      return (
        '<div class="flex items-center justify-between py-1 border-b border-gray-50 last:border-0">' +
        '<span class="font-medium">' +
        escHtml(String(rr.drawingName || '')) +
        '</span>' +
        '<span class="text-' +
        color +
        '-600">' +
        v +
        ' 项违规</span></div>'
      );
    })
    .join('');
}

export function renderSpecFreqBars(): void {
  const el = document.getElementById('spec-freq-bars') as HTMLElement | null;
  if (!el || getReviewResults().length === 0) return;
  const freq: Record<string, number> = {};
  getReviewResults().forEach((r) => {
    const rr = r as Record<string, unknown>;
    (rr.details as Array<Record<string, unknown>> || []).forEach((v) => {
      const key = String(v.clause_id || '未知');
      freq[key] = (freq[key] || 0) + 1;
    });
  });
  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const maxVal = Math.max(...sorted.map((s) => s[1]), 1);
  el.innerHTML = sorted
    .map(
      ([k, v]) =>
        '<div class="flex items-center gap-2"><span class="w-24 truncate">' +
        escHtml(k) +
        '</span>' +
        '<div class="flex-1 bg-gray-100 rounded-full h-3"><div class="bg-blue-500 h-3 rounded-full" style="width:' +
        (v / maxVal * 100) +
        '%"></div></div>' +
        '<span class="w-6 text-right">' +
        v +
        '</span></div>',
    )
    .join('');
}

export function renderViolationTypeBars(): void {
  const el = document.getElementById('violation-type-bars') as HTMLElement | null;
  if (!el || getReviewResults().length === 0) return;
  const freq: Record<string, number> = {};
  const labels: Record<string, string> = { critical: '严重', major: '主要', minor: '轻微' };
  getReviewResults().forEach((r) => {
    const rr = r as Record<string, unknown>;
    (rr.details as Array<Record<string, unknown>> || []).forEach((v) => {
      const key = labels[String(v.severity || 'major')] || '未知';
      freq[key] = (freq[key] || 0) + 1;
    });
  });
  const colors: Record<string, string> = { '严重': '#ef4444', '主要': '#f97316', '轻微': '#eab308' };
  const total = Object.values(freq).reduce((a, b) => a + b, 0) || 1;
  el.innerHTML = Object.entries(freq)
    .map(
      ([k, v]) =>
        '<div class="flex items-center gap-2"><span class="w-10">' +
        escHtml(k) +
        '</span>' +
        '<div class="flex-1 bg-gray-100 rounded-full h-3"><div class="h-3 rounded-full" style="width:' +
        (v / total * 100) +
        '%;background:' +
        (colors[k] || '#6b7280') +
        '"></div></div>' +
        '<span class="w-6 text-right">' +
        v +
        '</span></div>',
    )
    .join('');
}