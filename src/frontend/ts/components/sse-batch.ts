// ── P123 Step 6: SSE 流式批量审查组件 ──────────────────
// 从 baa-sse-batch.js 迁入 (293 行)
// 后端 /batch-review-stream 推送实时进度事件

import { getApiBase, getHeaders } from '../core/api-client';
import { showToast } from '../core/toast';
import { escHtml } from '../core/utils';

interface BatchEvent {
  event?: string;
  index?: number;
  filename?: string;
  file_id?: string;
  entity_count?: number;
  violations?: number;
  score?: number;
  error_code?: string;
  message?: string;
  results?: BatchResult[];
  cross_analysis?: CrossAnalysis[];
  success_files?: number;
  failed_files?: number;
  total_entities?: number;
  total_violations?: number;
}

interface BatchResult {
  filename?: string;
  status?: string;
  message?: string;
  error_code?: string;
  summary?: Record<string, number>;
  details?: Array<{ severity?: string }>;
}

interface CrossAnalysis {
  clause_id?: string;
  violations?: number;
  files?: number;
}

interface FileState {
  filename?: string;
  status: string;
  stage: string;
  file_id?: string | null;
  violations?: number;
  score?: number;
  entity_count?: number;
  error_code?: string;
  error_message?: string;
}

function getBatchFiles(): File[] {
  return (window as unknown as Record<string, unknown>).batchFiles as File[];
}

async function runBatchReviewSSE(): Promise<void> {
  const batchFiles = getBatchFiles();
  if (batchFiles.length === 0) {
    showToast('请先选择至少一个图纸文件', 'info');
    return;
  }

  const btn = document.getElementById('batch-review-start-btn') as HTMLButtonElement | null;
  const loading = document.getElementById('batch-review-loading') as HTMLElement | null;
  const summary = document.getElementById('batch-review-summary') as HTMLElement | null;
  const details = document.getElementById('batch-review-details') as HTMLElement | null;
  const skel = document.getElementById('batch-review-skeleton') as HTMLElement | null;

  btn?.setAttribute('disabled', 'disabled');
  if (loading) {
    loading.classList.remove('hidden');
    loading.textContent = '⏳ 正在批量审查（实时进度）...';
    loading.className = 'mt-3 text-sm text-gray-500';
  }
  summary?.classList.add('hidden');
  details?.classList.add('hidden');
  skel?.classList.remove('hidden');

  const formData = new FormData();
  batchFiles.forEach((f) => formData.append('files', f));
  const totalFiles = batchFiles.length;
  const fileStates: Record<string | number, FileState> = {};

  try {
    const resp = await fetch(getApiBase() + '/batch-review-stream', {
      method: 'POST',
      headers: getHeaders(),
      body: formData,
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error((errData as { detail?: { message?: string } }).detail?.message || `审查请求失败 (${resp.status})`);
    }

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = (lines.pop() || '');

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        try {
          const evt = JSON.parse(data) as BatchEvent;
          handleBatchEvent(evt, totalFiles, fileStates, summary, details, loading);
        } catch {
          // 忽略非 JSON 数据行
        }
      }
    }
  } catch (err) {
    if (loading) {
      loading.textContent = `❌ ${(err as Error).message}`;
      loading.className = 'mt-3 text-sm text-red-500';
    }
  } finally {
    btn?.removeAttribute('disabled');
    skel?.classList.add('hidden');
    summary?.classList.remove('hidden');
    details?.classList.remove('hidden');
  }
}

function handleBatchEvent(
  evt: BatchEvent,
  totalFiles: number,
  fileStates: Record<string | number, FileState>,
  summary: HTMLElement | null,
  details: HTMLElement | null,
  loading: HTMLElement | null,
): void {
  if (!evt?.event) return;

  switch (evt.event) {
    case 'file.queued': {
      const idx = String(evt.index ?? 0);
      fileStates[idx] = { filename: evt.filename, status: 'queued', stage: '排队中', file_id: null };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.parsing': {
      const idx = String(evt.index ?? 0);
      fileStates[idx] = { ...fileStates[idx], status: 'parsing', stage: '解析中', file_id: evt.file_id };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.semantic': {
      const idx = String(evt.index ?? 0);
      fileStates[idx] = { ...fileStates[idx], status: 'semantic', stage: '语义分析中' };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.checking': {
      const idx = String(evt.index ?? 0);
      fileStates[idx] = { ...fileStates[idx], status: 'checking', stage: `规则检查中 (${evt.entity_count || 0} 实体)` };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.done': {
      const idx = String(evt.index ?? 0);
      fileStates[idx] = {
        ...fileStates[idx],
        status: 'done',
        violations: evt.violations || 0,
        score: evt.score || 0,
        entity_count: evt.entity_count || 0,
        stage: '完成',
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.error': {
      const idx = String(evt.index ?? 0);
      fileStates[idx] = {
        ...fileStates[idx],
        status: 'error',
        error_code: evt.error_code,
        error_message: evt.message || evt.error_code || '审查失败',
        stage: '错误',
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'batch.done': {
      renderBatchResults(evt, totalFiles, summary, details, loading);
      break;
    }
  }
}

function updateLoadingProgress(
  loading: HTMLElement | null,
  fileStates: Record<string | number, FileState>,
  totalFiles: number,
): void {
  if (!loading) return;
  const stages = Object.values(fileStates);
  const done = stages.filter((s) => s.status === 'done' || s.status === 'error').length;
  const active = stages.length - done;
  const progress = totalFiles > 0 ? Math.round((done / totalFiles) * 100) : 0;

  let parts = [
    `⏳ 进度: ${done}/${totalFiles} (${progress}%)`,
  ];
  if (active > 0) {
    const stageList = stages.slice(0, active).map((s) => s.stage || '处理中');
    parts.push(` · ${stageList.join(', ')}`);
  }
  parts.push(' · <span class="text-blue-500">实时 SSE 推送</span>');

  loading.innerHTML = parts.join('') + `<div class="mt-2">${renderBatchProgressBar(done, totalFiles)}</div>`;
}

function renderBatchProgressBar(done: number, total: number): string {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return `<div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
    <div class="bg-blue-500 h-full rounded-full transition-all duration-300" style="width:${pct}%"></div></div>`;
}

function renderBatchResults(
  evt: BatchEvent,
  totalFiles: number,
  summary: HTMLElement | null,
  details: HTMLElement | null,
  loading: HTMLElement | null,
): void {
  const bs = evt;
  const results = evt.results || [];

  if (summary) {
    summary.innerHTML = `
      <div class="grid grid-cols-2 gap-2 mb-2">
        <div class="card p-2 text-xs">
          <p class="font-medium">📁 文件统计</p>
          <p>总数: ${totalFiles} | ✅成功: ${bs.success_files || 0} | ❌失败: ${bs.failed_files || 0}</p>
        </div>
        <div class="card p-2 text-xs">
          <p class="font-medium">📊 审查统计</p>
          <p>实体: ${bs.total_entities || 0} | 违规: ${bs.total_violations || 0}</p>
          <p class="text-blue-500">SSE 实时推送 · 逐文件流式完成</p>
        </div>
      </div>`;
  }

  if (evt.cross_analysis?.length && details) {
    let crossHtml =
      '<div class="card p-2 text-xs mb-2">' +
      '<p class="font-medium text-sm mb-1">🔗 跨文件违规交叉分析</p>' +
      '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
      '<th class="pb-1 pr-1">规范条款</th><th class="pb-1 pr-1">违规数</th><th class="pb-1 pr-1">涉及图纸</th></tr></thead><tbody>';
    evt.cross_analysis.slice(0, 8).forEach((c) => {
      crossHtml += `<tr class="border-b border-gray-50">
        <td class="py-1 pr-1">${escHtml(c.clause_id || '')}</td>
        <td class="py-1 pr-1">${c.violations || 0}</td>
        <td class="py-1 pr-1">${c.files || 0} 张</td></tr>`;
    });
    crossHtml += '</tbody></table></div>';
    details.innerHTML = crossHtml + (details.innerHTML || '');
  }

  if (results.length > 0 && details) {
    let fileHtml = '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2>';
    results.forEach((r) => {
      if (r.status === 'error') {
        fileHtml += `<div class="card p-2 text-xs border-l-2 border-red-500 bg-red-50">
          <p class="font-medium text-red-600">❌ ${escHtml(r.filename || '')}</p>
          <p class="text-gray-500">${escHtml(r.message || r.error_code || '审查失败')}</p></div>`;
        return;
      }
      const s = r.summary || {};
      const isClean = (s.violations || 0) === 0;
      const sevColor = isClean ? 'green' : (s.violations >= 20 ? 'red' : 'orange');
      const total = s.total_checks || 0;
      const passRate = total > 0 ? Math.round((1 - (s.violations || 0) / total) * 100) : 100;

      const sevCount = { critical: 0, major: 0, minor: 0 };
      (r.details || []).forEach((v) => {
        const sv = v.severity || 'major';
        if (sv === 'critical') sevCount.critical++;
        else if (sv === 'major') sevCount.major++;
        else sevCount.minor++;
      });

      const bar = `<div class="mt-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">
        <div class="${sevColor}-500 h-full rounded-full" style="width:${passRate}%"></div></div>
        <div class="flex justify-between text-[10px] text-gray-400 mt-0.5">
          <span>通过率 ${passRate}%</span><span>检查 ${total.toLocaleString()}</span></div>`;

      let badges = '';
      if (sevCount.critical > 0) badges += `<span class="px-1 rounded bg-red-100 text-red-700 text-[10px]">● ${sevCount.critical} 严重</span>`;
      if (sevCount.major > 0) badges += `<span class="px-1 rounded bg-orange-100 text-orange-700 text-[10px]">● ${sevCount.major} 主要</span>`;
      if (sevCount.minor > 0) badges += `<span class="px-1 rounded bg-yellow-100 text-yellow-700 text-[10px]">● ${sevCount.minor} 轻微</span>`;
      if (!badges) badges = '<span class="px-1 rounded bg-green-100 text-green-700 text-[10px]">✓ 无违规</span>';

      fileHtml += `<div class="card p-2 text-xs border-l-2 border-${sevColor}-500">
        <div class="flex items-center justify-between mb-1">
          <p class="font-medium truncate" title="${escHtml(r.filename || '')}">${escHtml(r.filename || '')}</p>
          <span class="text-${sevColor}-600 font-medium text-sm">${isClean ? '✓' : (s.violations || 0)}</span>
        </div>
        <p class="text-gray-500 text-[10px]">${s.total_entities || 0} 实体</p>
        ${bar}
        <div class="mt-1 flex flex-wrap gap-0.5">${badges}</div>
      </div>`;
    });
    fileHtml += '</div>';
    details.innerHTML += fileHtml;
  }

  if (loading) {
    loading.textContent = `✅ 批量审查完成 — ${evt.success_files || 0}/${totalFiles} 成功`;
    loading.className = 'mt-3 text-sm text-green-600';
  }
}

// 覆盖 window.runBatchReview 为 SSE 版本（加载顺序在 baa-review.js 之后）
(window as unknown as Record<string, unknown>).runBatchReview = runBatchReviewSSE;

export { runBatchReviewSSE };
