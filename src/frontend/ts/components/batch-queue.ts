// ── P123 Phase 2: BatchQueue 批量审查队列组件 ──────────────
// 对应 baa-review.js runBatchReview()：同步 POST 批量审查
// 渲染文件卡片网格 + 跨文件交叉分析 + 文件统计

import { escHtml } from '../core/utils';
import { showToast } from '../core/toast';
import { getApiBase, getHeaders } from '../core/api-client';

export interface BatchFileResult {
  status: 'success' | 'error';
  filename?: string;
  message?: string;
  buildingType?: 'civil' | 'industrial';
  summary?: {
    violations?: number;
    total_checks?: number;
    total_entities?: number;
    violation_by_clause?: Record<string, number>;
  };
  details?: Array<Record<string, unknown>>;
}

export interface BatchSummary {
  total_files: number;
  success_files: number;
  failed_files: number;
  total_entities: number;
  total_checks: number;
  total_violations: number;
  processing_time_ms: number;
}

export interface CrossAnalysisItem {
  clause_id: string;
  violations: number;
  files: number;
  file_names?: string[];
}

export interface BatchResponse {
  status: string;
  batch_summary: BatchSummary;
  results: BatchFileResult[];
  cross_analysis?: CrossAnalysisItem[];
  message?: string;
  detail?: { message?: string };
}

export interface BatchQueueOptions {
  summaryElId?: string;
  detailsElId?: string;
  loadingElId?: string;
  btnElId?: string;
}

const DEFAULT_IDS = {
  summary: 'batch-review-summary',
  details: 'batch-review-details',
  loading: 'batch-review-loading',
  btn: 'batch-review-start-btn',
};

function getEl(id: string): HTMLElement | null {
  return document.getElementById(id) as HTMLElement | null;
}

/**
 * 执行批量审查（同步 POST）
 * @param files 文件列表（window.batchFiles）
 * @param options DOM 元素 ID 配置
 */
export async function runBatchReview(
  files: File[],
  options: BatchQueueOptions = {},
): Promise<void> {
  if (files.length === 0) {
    showToast('请先选择至少一个图纸文件', 'info');
    return;
  }

  const ids = { ...DEFAULT_IDS, ...options };
  const btn = getEl(ids.btn);
  const loading = getEl(ids.loading);
  const summary = getEl(ids.summary);
  const details = getEl(ids.details);

  btn?.setAttribute('disabled', 'true');
  loading?.classList.remove('hidden');
  loading!.textContent = '⏳ 正在批量审查...';
  if (summary) summary.innerHTML = '';
  if (details) details.innerHTML = '';

  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));

  try {
    const r = await fetch(getApiBase() + '/batch-review', {
      method: 'POST',
      headers: getHeaders(),
      body: formData,
    });
    const resp = (await r.json()) as BatchResponse;

    if (!r.ok) {
      throw new Error(resp.detail?.message || '审查请求失败');
    }
    if (resp.status !== 'success') {
      throw new Error(resp.message || '审查失败');
    }

    renderBatchSummary(resp.batch_summary, summary);
    renderBatchDetails(resp, details);

    if (loading) loading.classList.add('hidden');
  } catch (err) {
    if (loading) {
      loading.textContent = '❌ ' + (err as Error).message;
      loading.className = 'mt-3 text-sm text-red-500';
    }
  } finally {
    btn?.removeAttribute('disabled');
  }
}

/** 文件统计摘要卡片 */
function renderBatchSummary(bs: BatchSummary, summary: HTMLElement | null): void {
  if (!summary) return;
  const timeSec = (bs.processing_time_ms / 1000).toFixed(1);
  summary.innerHTML =
    '<div class="grid grid-cols-2 gap-2 mb-2">' +
    '<div class="card p-2 text-xs"><p class="font-medium">📁 文件统计</p>' +
    '<p>总数: ' +
    bs.total_files +
    ' | ✅成功: ' +
    bs.success_files +
    ' | ❌失败: ' +
    bs.failed_files +
    '</p></div>' +
    '<div class="card p-2 text-xs"><p class="font-medium">📊 审查统计</p>' +
    '<p>实体: ' +
    bs.total_entities +
    ' | 检查: ' +
    bs.total_checks.toLocaleString() +
    ' | 违规: ' +
    bs.total_violations +
    '</p>' +
    '<p>耗时: ' +
    timeSec +
    's</p></div></div>';
}

/** 文件卡片网格 + 跨文件交叉分析 */
function renderBatchDetails(resp: BatchResponse, details: HTMLElement | null): void {
  if (!details) return;

  // 跨文件交叉分析
  let crossHtml = '';
  if (resp.cross_analysis && resp.cross_analysis.length > 0) {
    crossHtml =
      '<div class="card p-2 text-xs mb-2">' +
      '<p class="font-medium text-sm mb-1">🔗 跨文件违规交叉分析</p>' +
      '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
      '<th class="pb-1 pr-1">规范条款</th><th class="pb-1 pr-1">违规数</th>' +
      '<th class="pb-1 pr-1">涉及图纸</th><th class="pb-1 pr-1">文件</th></tr></thead><tbody>';
    resp.cross_analysis.slice(0, 8).forEach((c) => {
      crossHtml +=
        '<tr class="border-b border-gray-50">' +
        '<td class="py-1 pr-1">' +
        escHtml(c.clause_id) +
        '</td>' +
        '<td class="py-1 pr-1">' +
        c.violations +
        '</td>' +
        '<td class="py-1 pr-1">' +
        c.files +
        ' 张</td>' +
        '<td class="py-1 text-gray-400 truncate max-w-20">' +
        escHtml((c.file_names || []).join(', ')) +
        '</td></tr>';
    });
    crossHtml += '</tbody></table></div>';
  }

  // 文件卡片
  let fileHtml = '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">';
  resp.results.forEach((r) => {
    if (r.status === 'error') {
      fileHtml +=
        '<div class="card p-2 text-xs border-l-2 border-red-500 bg-red-50">' +
        '<p class="font-medium text-red-600">❌ ' +
        escHtml(r.filename || '') +
        '</p>' +
        '<p class="text-gray-500">' +
        escHtml(r.message || '') +
        '</p></div>';
      return;
    }
    const s = r.summary || {};
    const isClean = (s.violations || 0) === 0;
    const sevColor = isClean ? 'green' : (s.violations || 0) >= 20 ? 'red' : 'orange';
    const total = s.total_checks || 0;
    const passRate = total > 0 ? Math.round((1 - (s.violations || 0) / total) * 100) : 100;
    const sevCount = { critical: 0, major: 0, minor: 0 };
    (r.details || []).forEach((v) => {
      const sv = String(v.severity || 'major');
      if (sv in sevCount) (sevCount as Record<string, number>)[sv]++;
    });

    const bar =
      '<div class="mt-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">' +
      '<div class="' +
      sevColor +
      '-500 h-full rounded-full" style="width:' +
      passRate +
      '%"></div></div>' +
      '<div class="flex justify-between text-[10px] text-gray-400 mt-0.5">' +
      '<span>通过率 ' +
      passRate +
      '%</span><span>检查 ' +
      total.toLocaleString() +
      '</span></div>';

    let badges = '';
    if (sevCount.critical > 0)
      badges += '<span class="px-1 rounded bg-red-100 text-red-700 text-[10px]">● ' + sevCount.critical + ' 严重</span>';
    if (sevCount.major > 0)
      badges += '<span class="px-1 rounded bg-orange-100 text-orange-700 text-[10px]">● ' + sevCount.major + ' 主要</span>';
    if (sevCount.minor > 0)
      badges += '<span class="px-1 rounded bg-yellow-100 text-yellow-700 text-[10px]">● ' + sevCount.minor + ' 轻微</span>';
    if (!badges)
      badges = '<span class="px-1 rounded bg-green-100 text-green-700 text-[10px]">✓ 无违规</span>';

    const violByClause = s.violation_by_clause || {};
    const topClauses = Object.entries(violByClause).slice(0, 3);
    const clauseText =
      topClauses.length > 0
        ? '<p class="text-[10px] text-gray-400 mt-1">主要: ' +
          topClauses.map(([k, v]) => k + '(' + v + ')').join(', ') +
          '</p>'
        : '';

    fileHtml +=
      '<div class="card p-2 text-xs border-l-2 border-' +
      sevColor +
      '-500">' +
      '<div class="flex items-center justify-between mb-1">' +
      '<p class="font-medium truncate" title="' +
      escHtml(r.filename || '') +
      '">' +
      escHtml(r.filename || '') +
      '</p>' +
      '<span class="text-' +
      sevColor +
      '-600 font-medium text-sm">' +
      (isClean ? '✓' : (s.violations || 0)) +
      '</span></div>' +
      '<p class="text-gray-500 text-[10px]">' +
      (s.total_entities || 0) +
      ' 实体 · ' +
      (r.buildingType === 'civil' ? '民用' : '工业') +
      '</p>' +
      bar +
      '<div class="mt-1 flex flex-wrap gap-0.5">' +
      badges +
      '</div>' +
      clauseText +
      '</div>';
  });
  fileHtml += '</div>';

  details.innerHTML = crossHtml + fileHtml;
}

// 向后兼容：全局 window.runBatchReview 保留旧行为（baa-sse-batch.js 会覆盖为 SSE 版）
if (typeof window !== 'undefined') {
  const w = window as unknown as Record<string, unknown>;
  (w as unknown as Record<string, unknown>).runBatchReviewComponent = runBatchReview;
}