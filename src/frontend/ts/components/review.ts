// ── P119: AI审图主流程（从 js/baa-review.ts runReview 迁入）──
// 审查 API → 渲染 summary → 违规表格（含 audit 按钮）→ audit 统计面板
// 替代 js/baa-review.ts 中从未被加载的 runReview()

import { getParsedDrawings } from '../core/drawing-state';
import { renderReviewTable } from './review-table';
import { ReviewItemProps } from './review-item';
import { _initAuditItems, _refreshAuditPanel } from './audit';

// 类型别名
type ReviewFinding = Record<string, unknown>;

/**
 * 执行审查：从已解析图纸中提取实体 → 调用 /review-from-data → 渲染结果
 */
export async function runReview(): Promise<void> {
  const select = document.getElementById('review-drawing-select');
  const id = (select as HTMLSelectElement | null)?.value ?? '';
  if (!id) {
    (window as any).showToast?.('请选择已解析的图纸', 'info');
    return;
  }

  const drawings = getParsedDrawings();
  const drawing = drawings.find((d) => d.id === id) as Record<string, unknown> | undefined;
  if (!drawing) {
    (window as any).showToast?.('图纸数据不存在', 'info');
    return;
  }

  const bt = (drawing.building_type as string) || '';
  const entities = ((drawing.entities || drawing.raw?.entities) as unknown[]) || [];
  if (entities.length === 0) {
    (window as any).showToast?.('该图纸没有解析出实体数据，请重新上传解析', 'info');
    return;
  }

  // 显示进度
  const loading = document.getElementById('review-loading');
  if (loading) {
    loading.classList.remove('hidden');
    loading.textContent = '⏳ 正在审查...';
  }

  const btn = document.getElementById('review-start-btn') as HTMLButtonElement | null;
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ 审查中...';
  }

  try {
    const url = (window as any).API_BASE?.() + '/review-from-data';
    const r = await fetch(url, {
      method: 'POST',
      headers: { ...(window as any).HEADERS?.() || {}, 'Content-Type': 'application/json' },
      body: JSON.stringify({ entities, building_type: bt }),
    });
    const result = (await r.json()) as Record<string, unknown>;

    if (loading) loading.classList.add('hidden');
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔍 开始审查';
    }

    const summary = document.getElementById('review-summary');
    const details = document.getElementById('review-details');

    // 保存结果供后续导出/修正使用
    (window as any)._currentReviewResult = result;
    (window as any)._currentReviewEntities = entities;

    if (result.status === 'success') {
      renderReviewSummary(summary, result);
      renderReviewDetails(details, result);
      // P119: 初始化审核条目 + 刷新审核面板
      _initAuditItems(result).then(() => {
        const reviewId = (result.queue_info as any)?.task_id || result.task_id || '';
        if (reviewId) {
          _refreshAuditPanel(reviewId);
        }
      });
    } else {
      if (summary) {
        summary.innerHTML = '<span class="text-red-500">❌ 审查失败: ' +
          ((result.message as string) || '未知错误') + '</span>';
      }
    }
  } catch (err) {
    if (loading) loading.classList.add('hidden');
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔍 开始审查';
    }
    const msg = err instanceof Error ? err.message : String(err);
    const summary = document.getElementById('review-summary');
    if (summary) {
      summary.innerHTML = '<span class="text-red-500">❌ 审查失败: ' + msg + '</span>';
    }
  }
}

/** 渲染审查摘要卡片 */
function renderReviewSummary(container: HTMLElement | null, result: Record<string, unknown>): void {
  if (!container) return;
  const vs = (result.summary || {}) as Record<string, unknown>;
  const tc = (vs.confidence_tier_counts || { confirmed: 0, suspected: 0, needs_review: 0 }) as Record<string, number>;

  let html =
    '<div class="grid grid-cols-4 gap-2 mb-3">' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + (vs.violations || 0) + '</div><div class="text-xs text-gray-400">违规</div></div>' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + (tc.confirmed || 0) + '</div><div class="text-xs text-gray-400">✅ 确认违规</div></div>' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + (tc.suspected || 0) + '</div><div class="text-xs text-gray-400">🟡 疑似违规</div></div>' +
    '<div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + (tc.needs_review || 0) + '</div><div class="text-xs text-gray-400">🔴 建议复核</div></div>' +
    '</div>';

  // 实体类型分布 + 导出按钮
  const reviewId = (result.queue_info as any)?.task_id || result.task_id || '';
  if (result.summary?.entity_types || reviewId) {
    const extras: string[] = [];
    if (result.summary?.entity_types) {
      const parts: string[] = [];
      for (const [type, count] of Object.entries(result.summary.entity_types as Record<string, unknown>)) {
        parts.push('<span class="px-2 py-0.5 bg-gray-100 rounded text-xs">' + type + ': ' + count + '</span>');
      }
      extras.push('<p class="text-xs text-gray-400 mb-2">构件分布:</p><div class="flex flex-wrap gap-1 mb-3">' + parts.join('') + '</div>');
    }
    if (reviewId) {
      const safeId = (window as any)._escHtml?.(reviewId) || reviewId;
      extras.push(
        '<div class="mt-3 flex gap-2 flex-wrap">' +
        '<button onclick="window.downloadReviewPdf?.(\'' + safeId + '\')" class="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">📄 PDF报告</button>' +
        '<button onclick="window.downloadReviewExport?.(\'' + safeId + '\',\'json\')" class="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">📋 导出JSON</button>' +
        '<button onclick="window.downloadReviewExport?.(\'' + safeId + '\',\'csv\')" class="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">📊 导出CSV</button>' +
        '</div>'
      );
    }
    html += extras.join('');
  }

  container.innerHTML = html;
}

/** 渲染违规详情（审计统计面板 + 严重级别分布 + 违规表格） */
function renderReviewDetails(container: HTMLElement | null, result: Record<string, unknown>): void {
  if (!container) return;

  const findings = (result.findings || []) as ReviewFinding[];
  const violations = findings.filter((f) => f.result === 'FAIL' && !f.is_duplicate);

  if (violations.length === 0) {
    container.innerHTML = '<div class="text-center py-8 text-green-400 text-sm">✅ 无违规，图纸合规</div>';
    return;
  }

  // 严重级别分布卡片
  const sevCounts: Record<string, number> = {};
  violations.forEach((f) => {
    const sev = (f.severity as string) || 'major';
    sevCounts[sev] = (sevCounts[sev] || 0) + 1;
  });
  const totalViols = Object.values(sevCounts).reduce((a, b) => a + b, 0);

  let html = '';
  if (totalViols > 0) {
    const sevColors: Record<string, string> = { critical: 'bg-red-500', major: 'bg-orange-500', minor: 'bg-yellow-400' };
    const sevLabels: Record<string, string> = { critical: '严重', major: '主要', minor: '轻微' };
    const sevTextColors: Record<string, string> = { critical: 'text-red-700', major: 'text-orange-700', minor: 'text-yellow-700' };
    const sevGrid = ['critical', 'major', 'minor'].map((sev) => {
      const count = sevCounts[sev] || 0;
      const pct = totalViols > 0 ? (count / totalViols * 100).toFixed(0) : 0;
      return '<div class="card p-2 text-center">' +
        '<div class="text-lg font-bold ' + (sevTextColors[sev] || 'text-gray-600') + '">' + count + '</div>' +
        '<div class="text-xs text-gray-400">' + (sevLabels[sev] || sev) + '</div>' +
        '<div class="w-full bg-gray-100 rounded-full h-1.5 mt-1"><div class="' + (sevColors[sev] || 'bg-gray-400') + ' h-1.5 rounded-full" style="width:' + pct + '%"></div></div>' +
        '</div>';
    });
    html += '<div class="grid grid-cols-3 gap-2 mb-3">' + sevGrid.join('') + '</div>';
  }

  // 违规表格容器
  html += '<div id="audit-stats-bar-container"></div>';
  html += '<div id="review-table-container"></div>';

  container.innerHTML = html;

  // 用 renderReviewTable 渲染违规列表
  const tableContainer = document.getElementById('review-table-container');
  if (tableContainer) {
    const items: ReviewItemProps[] = violations.map((f) => mapFindingToItem(f));
    renderReviewTable(tableContainer, { items });
  }
}

/** 将 API 返回的 finding 映射为 ReviewItemProps */
function mapFindingToItem(f: ReviewFinding): ReviewItemProps {
  const corrKey = ((f.clause_id || f.func_id || '') as string).trim();
  const corrections = ((window as any)._currentReviewResult?.corrections || []) as Array<Record<string, unknown>>;
  const matchingCorrections = corrections.filter((c) => (c.clause_id as string) === corrKey);

  // 查找 auditItemId（从 window._reviewAuditMapping 中匹配）
  let auditItemId: string | undefined;
  let auditState: ReviewItemProps['auditState'];
  const mapping = (window as any)._reviewAuditMapping as { mapping?: Record<string, string>; reviewId?: string } | undefined;
  if (mapping?.mapping) {
    const fid = (f.func_id || f.clause_id || '') as string;
    const eid = (f.entity_id || '') as string;
    const key = fid + ':' + eid;
    if (mapping.mapping[key]) {
      auditItemId = mapping.mapping[key];
      const states = (window as any)._reviewAuditStates as Record<string, string>;
      auditState = (states?.[auditItemId] || 'unreviewed') as ReviewItemProps['auditState'];
    }
  }

  return {
    funcId: (f.func_id as string) || '',
    clauseId: (f.clause_id as string) || '',
    clauseTitle: (f.clause_title as string) || '',
    severity: (f.severity as ReviewItemProps['severity']) || 'major',
    confidence: f.confidence != null ? (f.confidence as number) : 1.0,
    confidenceTier: (f.confidence_tier as ReviewItemProps['confidenceTier']) || undefined,
    entityType: (f.entity_type as string) || '',
    extractedValue: f.extracted_value != null ? (f.extracted_value as number) : null,
    requiredValue: f.required_value != null ? (f.required_value as number) : null,
    explanation: (f.explanation as string) || '',
    result: (f.result as string) || '',
    entityId: (f.entity_id as string) || '',
    corrections: matchingCorrections.map((c) => ({
      recommendation: (c.recommendation as string) || '',
      priority: (c.priority as 'high' | 'medium' | 'low') || 'medium',
      parameters: (c.parameters as Record<string, unknown>) || {},
    })),
    auditItemId,
    auditState: auditState || 'unreviewed',
  };
}
