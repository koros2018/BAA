// ── P119: 违规审核工作流 ──────────────────────────────────
// 从 src/frontend/js/baa-review.ts 迁入 ts/components/audit.ts
// 审查完成后自动初始化审核条目，违规行内嵌审核按钮

declare const showToast: (msg: string, kind?: string) => void;
declare const renderViolationPage: (() => void) | undefined;

function _escHtml(str: unknown): string {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── P119 审计条目初始化 ─────────────────────────────────────

export async function _initAuditItems(result: any): Promise<void> {
  const reviewId = result.queue_info?.task_id || result.task_id || '';
  if (!reviewId) return;

  const details = ((result.findings || []) as any[]).filter(f => f.result === 'FAIL' && !f.is_duplicate);
  if (details.length === 0) {
    (window as any)._reviewAuditMapping = {};
    return;
  }

  try {
    const url = (window as any).API_BASE?.() + '/api/v1/audit/items';
    const r = await fetch(url, {
      method: 'POST',
      headers: { ...(window as any).HEADERS?.() || {}, 'Content-Type': 'application/json' },
      body: JSON.stringify({ review_id: reviewId, details }),
    });
    if (r.ok) {
      const mapping: Record<string, string> = {};
      details.forEach((d: any, i: number) => {
        const fid = d.func_id || d.clause_id || '';
        const eid = d.entity_id || '';
        mapping[fid + ':' + eid + ':' + i] = reviewId + ':' + i;
      });
      (window as any)._reviewAuditMapping = { mapping, reviewId };
      (window as any)._reviewAuditDetailList = details;
      await _loadAuditItemStates(reviewId);
    }
  } catch (err) {
    console.warn('[P119] 审计条目初始化失败:', (err as Error).message);
  }
}

export async function _loadAuditItemStates(reviewId: string): Promise<void> {
  try {
    const url = (window as any).API_BASE?.() + '/api/v1/audit/items?review_id=' + encodeURIComponent(reviewId);
    const r = await fetch(url, { headers: (window as any).HEADERS?.() || {} });
    if (r.ok) {
      const resp = await r.json();
      const states: Record<string, string> = {};
      (resp.items || []).forEach((item: any) => { states[item.id] = item.status; });
      (window as any)._reviewAuditStates = states;
    }
  } catch (err) {
    console.warn('[P119] 审计状态加载失败:', (err as Error).message);
  }
}

export function renderAuditButtons(itemId: string, itemStatus: string, clauseId: string): string {
  if (!itemId) return '';
  const safeClause = _escHtml(clauseId || '');
  let html = '<div class="flex gap-1 mt-1"><span class="text-[10px] text-gray-400">审核:</span>';

  switch (itemStatus) {
    case 'confirmed':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✅ 已确认</span>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-red-100 hover:text-red-700">↩ 驳回</button>';
      break;
    case 'dismissed':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">❌ 已驳回</span>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700">↩ 确认</button>';
      break;
    case 'pending':
      html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">⏳ 待核实</span>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      break;
    default:
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'confirm\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'dismiss\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      html += '<button onclick="window.auditAction(\'' + itemId + '\',\'pending\',\'' + safeClause + '\')" class="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200">⏳ 待核实</button>';
  }
  html += '</div>';
  return html;
}

export async function auditAction(itemId: string, action: string, clauseId: string): Promise<void> {
  const safeAction = _escHtml(action || '');
  try {
    const body = action === 'dismiss' ? { reason: '人工驳回' } : {};
    const url = (window as any).API_BASE?.() + '/api/v1/audit/items/' + encodeURIComponent(itemId) + '/' + safeAction;
    const r = await fetch(url, {
      method: 'POST',
      headers: { ...(window as any).HEADERS?.() || {}, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json();
      showToast?.('操作失败: ' + (err.detail || r.statusText), 'error');
      return;
    }
    showToast?.(
      (action === 'confirm' ? '✅ 已确认违规' : action === 'dismiss' ? '❌ 已驳回（误报）' : '⏳ 已标记待核实') + ' ' + _escHtml(clauseId || ''),
      'info',
    );
    renderViolationPage?.();
  } catch (err) {
    showToast?.('网络错误: ' + (err as Error).message, 'error');
  }
}

// ── P119 审核统计面板 ──────────────────────────────────────
// 顶部状态条：总条目 + 各状态计数（色块）
// 筛选下拉：全部 / 未审核 / 已确认 / 已驳回 / 待核实
// 整改通知单按钮：审核完成后生成 PDF

const STATUS_META = {
  all: { label: '全部', color: 'bg-gray-100 text-gray-700' },
  unreviewed: { label: '未审核', color: 'bg-gray-200 text-gray-800' },
  confirmed: { label: '已确认', color: 'bg-green-100 text-green-700' },
  dismissed: { label: '已驳回', color: 'bg-red-100 text-red-700' },
  pending: { label: '待核实', color: 'bg-yellow-100 text-yellow-700' },
} as const;

type AuditStatus = keyof typeof STATUS_META;

export function renderAuditStatsBar(reviewId: string, stats: {
  total: number; confirmed: number; dismissed: number; pending: number; unreviewed: number;
}): string {
  const safeId = _escHtml(reviewId);
  const { total, confirmed, dismissed, pending, unreviewed } = stats;

  let html = '<div id="audit-stats-bar" class="mb-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2.5 flex items-center gap-4 flex-wrap">';
  html += '<span class="text-xs font-semibold text-blue-800 mr-2">📋 审核进度</span>';

  // 进度文本
  const reviewed = confirmed + dismissed + pending;
  html += '<span class="text-xs text-blue-600">已审核 <b>' + reviewed + '</b> / <b>' + total + '</b></span>';

  // 状态色块
  if (unreviewed > 0) html += _statChip('⏳ ' + unreviewed + ' 未审核', 'bg-gray-200 text-gray-800');
  if (confirmed > 0) html += _statChip('✅ ' + confirmed + ' 确认', 'bg-green-100 text-green-700');
  if (dismissed > 0) html += _statChip('❌ ' + dismissed + ' 驳回', 'bg-red-100 text-red-700');
  if (pending > 0) html += _statChip('⏳ ' + pending + ' 待核实', 'bg-yellow-100 text-yellow-700');
  if (total === 0) html += '<span class="text-xs text-gray-500">暂无审核条目</span>';

  html += '</div>';

  // 筛选下拉
  html += '<div id="audit-filter-bar" class="mb-3 flex items-center gap-2">';
  html += '<select id="audit-status-filter" onchange="window._onAuditFilterChange(this.value,\'' + safeId + '\')" class="text-xs border rounded px-2 py-1">';
  (['all', 'unreviewed', 'confirmed', 'dismissed', 'pending'] as AuditStatus[]).forEach(k => {
    const m = STATUS_META[k];
    html += '<option value="' + k + '">' + m.label + '</option>';
  });
  html += '</select>';

  // 生成整改通知单按钮（仅 confirmed > 0 时显示）
  if (confirmed > 0) {
    html += '<button onclick="window.downloadCorrectionNotice(\'' + safeId + '\')" class="ml-auto px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700">📄 生成整改通知单</button>';
  }
  html += '</div>';

  return html;
}

function _statChip(text: string, css: string): string {
  return '<span class="px-2 py-0.5 rounded text-xs font-medium ' + css + '">' + text + '</span>';
}

export async function _loadAuditStats(reviewId: string): Promise<any> {
  try {
    const url = (window as any).API_BASE?.() + '/api/v1/audit/stats?review_id=' + encodeURIComponent(reviewId);
    const r = await fetch(url, { headers: (window as any).HEADERS?.() || {} });
    if (r.ok) {
      const resp = await r.json();
      (window as any)._auditStats = resp.stats;
      return resp.stats;
    }
  } catch (err) {
    console.warn('[P119] 审核统计加载失败:', (err as Error).message);
  }
  return null;
}

export async function _refreshAuditPanel(reviewId: string): Promise<void> {
  const stats = await _loadAuditStats(reviewId);
  if (!stats) return;

  const barEl = document.getElementById('audit-stats-bar');
  if (barEl) {
    barEl.outerHTML = renderAuditStatsBar(reviewId, stats);
  }
  // 刷新违规列表状态缓存
  await _loadAuditItemStates(reviewId);
  renderViolationPage?.();
}

export async function _onAuditFilterChange(status: string, reviewId: string): Promise<void> {
  // 触发违规列表重新加载（带 status 过滤）
  (window as any)._auditFilterStatus = status === 'all' ? '' : status;
  renderViolationPage?.();
}

export async function downloadCorrectionNotice(reviewId: string): Promise<void> {
  try {
    const url = (window as any).API_BASE?.() + '/api/v1/audit/export/pdf?review_id=' + encodeURIComponent(reviewId);
    const r = await fetch(url, { headers: (window as any).HEADERS?.() || {} });
    if (!r.ok) {
      showToast?.('生成失败: ' + r.statusText, 'error');
      return;
    }
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'correction-notice-' + _escHtml(reviewId) + '.pdf';
    a.click();
    URL.revokeObjectURL(a.href);
    showToast?.('✅ 整改通知单已下载', 'info');
  } catch (err) {
    showToast?.('网络错误: ' + (err as Error).message, 'error');
  }
}
