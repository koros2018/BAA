// ── P123 Phase 2: FilterBar 筛选栏组件 ────────────────────
// 统一状态/严重度/规范筛选控件，供 ReviewTable + P119 审核使用
// 渲染到指定 container，触发 change 事件时通过回调通知上层

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterBarOptions {
  // 状态筛选（审核工作流）
  statusOptions?: FilterOption[];
  // 严重度筛选
  severityOptions?: FilterOption[];
  // 规范条款筛选
  clauseOptions?: FilterOption[];
  // 当前选中值
  activeStatus?: string;
  activeSeverity?: string;
  activeClause?: string;
  // 回调
  onChange?: (status: string, severity: string, clause: string) => void;
  // 统计条（可选，配合 P119 审核统计）
  stats?: {
    total: number;
    confirmed: number;
    dismissed: number;
    pending: number;
    unreviewed: number;
  };
}

/** 默认审核状态选项 */
const DEFAULT_STATUS_OPTIONS: FilterOption[] = [
  { value: '', label: '📋 全部' },
  { value: 'unreviewed', label: '⚪ 未审核' },
  { value: 'confirmed', label: '✅ 已确认' },
  { value: 'dismissed', label: '❌ 已驳回' },
  { value: 'pending', label: '⏳ 待核实' },
];

const DEFAULT_SEVERITY_OPTIONS: FilterOption[] = [
  { value: '', label: '🚦 全部严重度' },
  { value: 'critical', label: '🔴 严重' },
  { value: 'major', label: '🟠 主要' },
  { value: 'minor', label: '🟡 轻微' },
];

/**
 * 渲染筛选栏
 * @param container 目标容器
 * @param options 配置
 */
export function renderFilterBar(container: HTMLElement, options: FilterBarOptions = {}): void {
  const statusOpts = options.statusOptions || DEFAULT_STATUS_OPTIONS;
  const severityOpts = options.severityOptions || DEFAULT_SEVERITY_OPTIONS;
  const clauseOpts = options.clauseOptions || [];
  const aStatus = options.activeStatus || '';
  const aSeverity = options.activeSeverity || '';
  const aClause = options.activeClause || '';

  const sel = 'px-2 py-1 rounded text-xs bg-blue-100 text-blue-700 border border-blue-200';
  const unsel = 'px-2 py-1 rounded text-xs bg-gray-100 text-gray-600 hover:bg-gray-200 border border-gray-200';

  let html =
    '<div class="flex flex-wrap items-center gap-2 mb-3 p-2 bg-gray-50 rounded-lg border">' +
    '<span class="text-xs text-gray-500 font-medium">筛选:</span>';

  // 统计条
  if (options.stats) {
    const s = options.stats;
    html +=
      '<span class="text-xs text-gray-400 mr-2">|</span>' +
      `<span class="text-xs text-gray-500">已审核 <strong class="text-blue-600">${s.total - s.unreviewed}</strong>/${s.total} | 确认 <span class="text-green-600">${s.confirmed}</span> | 驳回 <span class="text-red-600">${s.dismissed}</span> | 待核实 <span class="text-yellow-600">${s.pending}</span></span>`;
  }

  // 状态筛选
  if (statusOpts.length > 0) {
    html += '<span class="text-xs text-gray-400 ml-2">状态:</span>';
    for (const opt of statusOpts) {
      const cls = opt.value === aStatus ? sel : unsel;
      html += `<button data-filter-status="${opt.value}" class="${cls}">${opt.label}</button>`;
    }
  }

  // 严重度筛选
  if (severityOpts.length > 0) {
    html += '<span class="text-xs text-gray-400 ml-2">严重度:</span>';
    for (const opt of severityOpts) {
      const cls = opt.value === aSeverity ? sel : unsel;
      html += `<button data-filter-severity="${opt.value}" class="${cls}">${opt.label}</button>`;
    }
  }

  // 规范条款筛选
  if (clauseOpts.length > 0) {
    html += '<span class="text-xs text-gray-400 ml-2">规范:</span>';
    for (const opt of clauseOpts.slice(0, 15)) {
      const cls = opt.value === aClause ? sel : unsel;
      html += `<button data-filter-clause="${opt.value}" class="${cls}">${opt.label}</button>`;
    }
    if (clauseOpts.length > 15) {
      html += `<span class="text-xs text-gray-400">+${clauseOpts.length - 15}</span>`;
    }
  }

  // 清除按钮
  if (aStatus || aSeverity || aClause) {
    html += '<button data-filter-clear class="px-2 py-1 rounded text-xs bg-red-100 text-red-600 hover:bg-red-200 ml-auto">✕ 清除</button>';
  }

  html += '</div>';

  container.innerHTML = html;

  // 事件绑定
  container.querySelectorAll('[data-filter-status]').forEach((btn) => {
    (btn as HTMLElement).addEventListener('click', () => {
      options.onChange?.(
        (btn as HTMLElement).dataset.filterStatus || '',
        aSeverity,
        aClause,
      );
    });
  });
  container.querySelectorAll('[data-filter-severity]').forEach((btn) => {
    (btn as HTMLElement).addEventListener('click', () => {
      options.onChange?.(
        aStatus,
        (btn as HTMLElement).dataset.filterSeverity || '',
        aClause,
      );
    });
  });
  container.querySelectorAll('[data-filter-clause]').forEach((btn) => {
    (btn as HTMLElement).addEventListener('click', () => {
      options.onChange?.(
        aStatus,
        aSeverity,
        (btn as HTMLElement).dataset.filterClause || '',
      );
    });
  });
  const clearBtn = container.querySelector('[data-filter-clear]') as HTMLElement | null;
  clearBtn?.addEventListener('click', () => {
    options.onChange?.('', '', '');
  });
}

// 向后兼容
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).renderFilterBar = renderFilterBar;
}