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