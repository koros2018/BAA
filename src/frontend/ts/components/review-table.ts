// ── P123 Phase 2: ReviewTable 违规列表表格组件 ─────────────
// 对应 baa-review.js 中 renderViolationPage 的表格 + 分页
// 纯 TS，渲染 HTML 到指定 container

import { escHtml } from '../core/utils';
import { ReviewItemProps, renderReviewItem } from './review-item';

export interface ReviewTableOptions {
  items: ReviewItemProps[];
  page?: number;
  pageSize?: number;
  // 筛选
  filterStatus?: string;
  filterSeverity?: string;
}

/** 渲染分页违规列表 */
export function renderReviewTable(
  container: HTMLElement,
  options: ReviewTableOptions,
): void {
  const { items, page: curPage = 1, pageSize = 20 } = options;
  const filtered = filterItems(items, options);
  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.max(1, Math.min(curPage, totalPages));
  const start = (page - 1) * pageSize;
  const end = Math.min(start + pageSize, total);
  const pageItems = filtered.slice(start, end);

  if (total === 0) {
    container.innerHTML =
      '<div class="text-center py-8 text-gray-400 text-sm">暂无违规数据</div>';
    return;
  }

  let html = '';
  for (const item of pageItems) {
    html += renderReviewItem(item);
  }

  // 分页控件
  if (totalPages > 1) {
    html += '<div class="flex items-center justify-center gap-2 mt-3 text-xs">';
    html +=
      '<button data-page="prev" class="px-2 py-1 border rounded hover:bg-gray-100"' +
      (page <= 1 ? ' disabled' : '') +
      '>‹</button>';
    const pageRangeStart = Math.max(1, page - 2);
    const pageRangeEnd = Math.min(totalPages, page + 2);
    for (let p = pageRangeStart; p <= pageRangeEnd; p++) {
      html +=
        '<button data-page="' +
        p +
        '" class="px-2 py-1 border rounded ' +
        (p === page ? 'bg-blue-100 text-blue-700' : 'hover:bg-gray-100') +
        '">' +
        p +
        '</button>';
    }
    html +=
      '<button data-page="next" class="px-2 py-1 border rounded hover:bg-gray-100"' +
      (page >= totalPages ? ' disabled' : '') +
      '>›</button>';
    html += '<span class="text-gray-400">' + page + '/' + totalPages + '</span>';
    html += '</div>';
  }

  html += `<div class="text-xs text-gray-400 text-right mt-1">共 ${total} 条违规</div>`;

  container.innerHTML = html;

  // 分页事件
  container.querySelectorAll('[data-page]').forEach((btn) => {
    (btn as HTMLElement).addEventListener('click', () => {
      const val = (btn as HTMLElement).dataset.page;
      if (!val || val === 'prev' || val === 'next') return;
      if (typeof window !== 'undefined') {
        const w = window as unknown as Record<string, unknown>;
        if (typeof w.renderViolationPage === 'function') {
          (w as unknown as Record<string, unknown>)['_reviewPage'] = parseInt(val, 10);
          (w.renderViolationPage as () => void)();
        }
      }
    });
  });
}

function filterItems(
  items: ReviewItemProps[],
  options: ReviewTableOptions,
): ReviewItemProps[] {
  let filtered = items;
  if (options.filterStatus) {
    filtered = filtered.filter((i) => i.auditState === options.filterStatus);
  }
  if (options.filterSeverity) {
    filtered = filtered.filter((i) => i.severity === options.filterSeverity);
  }
  return filtered;
}

// 向后兼容
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).renderReviewTable = renderReviewTable;
}