// ── P123 Phase 2: ReviewItem 单条违规卡片组件 ─────────────
// 对应 baa-review.js 中 renderViolationPage 内的违规条目渲染
// 含置信度条、修正建议折叠、P119 审核按钮
// 纯 TS，返回 HTML 字符串

import { escHtml } from '../core/utils';

export interface ReviewItemProps {
  // 违规数据
  funcId: string;
  clauseId: string;
  clauseTitle: string;
  severity: 'critical' | 'major' | 'minor' | string;
  confidence: number;
  confidenceTier?: 'confirmed' | 'suspected' | 'needs_review';
  entityType: string;
  extractedValue: number | null;
  requiredValue: number | null;
  explanation: string;
  result: string;
  entityId?: string;
  // 修正建议
  corrections?: Array<{
    recommendation: string;
    priority: 'high' | 'medium' | 'low';
    parameters?: Record<string, unknown>;
  }>;
  // P119 审核
  auditItemId?: string;
  auditState?: 'unreviewed' | 'confirmed' | 'dismissed' | 'pending';
}

const SEV_COLOR: Record<string, string> = {
  critical: 'red',
  major: 'orange',
  minor: 'yellow',
};
const SEV_LABEL: Record<string, string> = {
  critical: '严重',
  major: '主要',
  minor: '轻微',
};

function confColor(conf: number): string {
  if (conf >= 0.85) return 'green';
  if (conf >= 0.6) return 'yellow';
  return 'red';
}

function confLabel(conf: number): string {
  if (conf >= 0.85) return '高';
  if (conf >= 0.6) return '中';
  return '低';
}

/** 渲染单条违规卡片 HTML */
export function renderReviewItem(props: ReviewItemProps): string {
  const sevColor = SEV_COLOR[props.severity] || 'orange';
  const sevLabel = SEV_LABEL[props.severity] || props.severity;
  const conf = Math.max(0, Math.min(1, props.confidence));
  const confPct = Math.round(conf * 100);
  const cColor = confColor(conf);
  const cLabel = confLabel(conf);

  let html =
    '<div class="p-2 bg-' +
    sevColor +
    '-50 rounded text-xs mb-1.5">' +
    '<div class="flex justify-between items-start">' +
    '<div><span class="font-medium">' +
    escHtml(props.clauseTitle) +
    '</span> <span class="text-gray-400">(' +
    escHtml(props.funcId || props.clauseId) +
    ')</span></div>' +
    '<div class="flex gap-1">' +
    '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' +
    sevColor +
    '-100 text-' +
    sevColor +
    '-700">' +
    sevLabel +
    '</span>' +
    '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' +
    cColor +
    '-100 text-' +
    cColor +
    '-700" title="置信度 ' +
    confPct +
    '%">' +
    cLabel +
    '</span>' +
    '<span class="text-' +
    sevColor +
    '-600 font-medium">' +
    escHtml(props.result) +
    '</span></div></div>' +
    '<span class="text-gray-500">' +
    escHtml(props.entityType) +
    ' · 实测: ' +
    (props.extractedValue != null ? props.extractedValue.toFixed(2) : '-') +
    ' · 要求: ' +
    (props.requiredValue != null ? props.requiredValue.toFixed(2) : '-') +
    '</span><br/>' +
    '<div class="mt-1"><div class="w-full bg-gray-200 rounded-full h-1">' +
    '<div class="' +
    cColor +
    '-500 h-1 rounded-full" style="width:' +
    confPct +
    '%"></div></div></div>' +
    '<span class="text-gray-400">' +
    escHtml(props.explanation) +
    '</span>';

  // 修正建议
  if (props.corrections && props.corrections.length > 0) {
    const top = props.corrections[0];
    const pColor = top.priority === 'high' ? 'red' : top.priority === 'medium' ? 'orange' : 'yellow';
    const pLabel = top.priority === 'high' ? '🔴 高' : top.priority === 'medium' ? '🟠 中' : '🟡 低';
    html +=
      '<details class="mt-1"><summary class="cursor-pointer text-purple-600 font-medium">💡 修正建议 (' +
      props.corrections.length +
      '条)</summary>' +
      '<div class="mt-0.5 p-1 bg-' +
      pColor +
      '-50 rounded border-l-2 border-' +
      pColor +
      '-400">' +
      '<p class="text-xs"><span class="text-' +
      pColor +
      '-600">' +
      pLabel +
      '</span> ' +
      escHtml(top.recommendation) +
      '</p>' +
      (Object.keys(top.parameters || {}).length > 0
        ? '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(top.parameters) + '</p>'
        : '') +
      '</div></details>';
  }

  // P119 审核按钮
  if (props.auditItemId) {
    html += renderAuditButtons(props.auditItemId, props.auditState || 'unreviewed', props.clauseId);
  }

  html += '</div>';
  return html;
}

/** P119 审核按钮 HTML（从 baa-review.js 抽取） */
function renderAuditButtons(
  itemId: string,
  itemStatus: string,
  clauseId: string,
): string {
  const safeClause = escHtml(clauseId || '');
  let html = '<div class="flex gap-1 mt-1"><span class="text-[10px] text-gray-400">审核:</span>';

  switch (itemStatus) {
    case 'confirmed':
      html +=
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✅ 已确认</span>' +
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'dismiss\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-red-100 hover:text-red-700">↩ 驳回</button>';
      break;
    case 'dismissed':
      html +=
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">❌ 已驳回</span>' +
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'confirm\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700">↩ 确认</button>';
      break;
    case 'pending':
      html +=
        '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">⏳ 待核实</span>' +
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'confirm\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>' +
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'dismiss\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>';
      break;
    default:
      html +=
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'confirm\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>' +
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'dismiss\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>' +
        '<button onclick="auditAction(\'' +
        escHtml(itemId) +
        '\',\'pending\',\'' +
        safeClause +
        '\')" class="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200">⏳ 待核实</button>';
  }
  html += '</div>';
  return html;
}

// 向后兼容
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).renderReviewItem = renderReviewItem;
}