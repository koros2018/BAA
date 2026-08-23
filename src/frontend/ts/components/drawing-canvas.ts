// ── P123 Phase 2: DrawingCanvas 图纸可视化组件 ────────────
// 对应 baa-review.js renderViolationOverlay：审查结果实体网格可视化 + Tooltip
// 纯 TS，渲染到指定 <canvas> 元素

interface CircleData {
  x: number;
  y: number;
  r: number;
  type: string;
  color: string;
  severity: string;
  isViolated: boolean;
  hints: string[];
}

interface Violation {
  entity_type?: string;
  severity?: string;
  clause_id?: string;
  clause_title?: string;
}

interface Element {
  type?: string;
  entity_type?: string;
}

interface ReviewResult {
  details?: Violation[];
  corrections?: unknown[];
  elements?: Element[];
  rawResult?: { elements?: Element[] };
}

const ENTITY_COLORS: Record<string, string> = {
  staircase: '#ef4444',
  stair: '#ef4444',
  corridor: '#f97316',
  aisle: '#f97316',
  fire_door: '#ef4444',
  door: '#f59e0b',
  fire_lane: '#ef4444',
  road: '#ef4444',
  fire_zone: '#f97316',
  room: '#22c55e',
  exit: '#ef4444',
  exit_door: '#ef4444',
  fire_window: '#f97316',
  window: '#3b82f6',
  refuge_floor: '#ef4444',
  exit_sign: '#f59e0b',
  sign: '#f59e0b',
  sprinkler_system: '#f97316',
  fire_alarm: '#f97316',
  shaft: '#f59e0b',
  insulation: '#f97316',
  evacuation_lighting: '#f59e0b',
  wall: '#6b7280',
};

/**
 * 在 canvas 上渲染审查结果的实体网格可视化
 * @param canvas 目标 <canvas> 元素
 * @param result 审查结果数据
 * @param emptyElId 无数据时显示占位的元素 ID
 */
export function renderViolationOverlay(
  canvas: HTMLCanvasElement,
  result: ReviewResult,
  emptyElId?: string,
): void {
  const viols = result.details || [];
  const elements = result.elements || result.rawResult?.elements || [];

  const hasPosData = elements.length > 0 || viols.some((v) => v.entity_type);
  if (!hasPosData) {
    if (emptyElId) {
      const el = document.getElementById(emptyElId) as HTMLElement | null;
      if (el) {
        el.className =
          'absolute inset-0 flex items-center justify-center text-gray-400 text-sm';
        el.textContent = '无实体位置数据';
      }
    }
    canvas.style.display = 'none';
    return;
  }
  if (emptyElId) {
    const emptyEl = document.getElementById(emptyElId) as HTMLElement | null;
    if (emptyEl) emptyEl.className = 'hidden';
  }
  canvas.style.display = 'block';

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#f8f9fa';
  ctx.fillRect(0, 0, W, H);

  // 收集违规类型及严重度
  const violTypes: Record<string, string> = {};
  const violClauses: Record<string, string[]> = {};
  viols.forEach((v) => {
    const et = v.entity_type || 'unknown';
    const severity = v.severity || 'major';
    if (!violTypes[et] || violTypes[et] === 'major') violTypes[et] = severity;
    if (!violClauses[et]) violClauses[et] = [];
    violClauses[et].push(v.clause_id + ': ' + (v.clause_title || ''));
  });

  const allTypes = [
    ...new Set([
      ...viols.map((v) => v.entity_type || 'unknown'),
      ...elements.map((e) => e.type || e.entity_type || ''),
    ].filter(Boolean)),
  ];

  if (allTypes.length === 0) {
    ctx.fillStyle = '#999';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('无实体位置数据', W / 2, H / 2);
    return;
  }

  const cols = Math.min(4, Math.ceil(Math.sqrt(allTypes.length)));
  const rows = Math.ceil(allTypes.length / cols);
  const cellW = (W - 60) / cols;
  const cellH = (H - 60) / rows;
  const circles: CircleData[] = [];

  allTypes.forEach((t, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cx = 30 + col * cellW + cellW / 2;
    const cy = 30 + row * cellH + cellH / 2;
    const radius = Math.min(cellW, cellH) * 0.3;
    const color = ENTITY_COLORS[t] || '#6b7280';
    const severity = violTypes[t] || 'none';
    const isViolated = violTypes[t] !== undefined;
    const hints = violClauses[t] || [];

    // 圆圈
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.fillStyle = isViolated
      ? severity === 'critical'
        ? '#fecaca'
        : '#fed7aa'
      : '#dcfce7';
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = isViolated ? 3 : 1.5;
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = t.length > 12 ? t.slice(0, 10) + '..' : t;
    ctx.fillText(label, cx, cy);

    if (isViolated) {
      ctx.fillStyle = color;
      ctx.font = 'bold 8px sans-serif';
      ctx.fillText('✗', cx + radius + 8, cy - radius);
    }

    if (hints.length > 0) {
      ctx.fillStyle = '#6b7280';
      ctx.font = '7px sans-serif';
      ctx.textAlign = 'center';
      hints.slice(0, 2).forEach((h, hi) => {
        ctx.fillText(
          h.length > 20 ? h.slice(0, 18) + '..' : h,
          cx,
          cy + 12 + hi * 10,
        );
      });
    }

    circles.push({ x: cx, y: cy, r: radius, type: t, color, severity, isViolated, hints });
  });

  // Tooltip
  let tip = document.getElementById('compare-vis-tooltip') as HTMLElement | null;
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'compare-vis-tooltip';
    tip.className =
      'fixed hidden bg-black bg-opacity-90 text-white text-xs rounded-lg p-2 pointer-events-none z-50 max-w-xs shadow-lg';
    document.body.appendChild(tip);
  }

  // 清除旧监听器
  if ((canvas as unknown as Record<string, unknown>).__onMove) {
    canvas.removeEventListener(
      'mousemove',
      (canvas as unknown as Record<string, unknown>).__onMove as EventListener,
    );
  }
  if ((canvas as unknown as Record<string, unknown>).__onLeave) {
    canvas.removeEventListener(
      'mouseleave',
      (canvas as unknown as Record<string, unknown>).__onLeave as EventListener,
    );
  }

  (canvas as unknown as Record<string, unknown>).__circles = circles;
  (canvas as unknown as Record<string, unknown>).__tooltip = tip;

  const onMove = (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    let hit: CircleData | null = null;
    let hitDist = Infinity;
    for (const c of circles) {
      const d = Math.hypot(mx - c.x, my - c.y);
      if (d < c.r * 1.3 && d < hitDist) {
        hit = c;
        hitDist = d;
      }
    }
    if (!hit) {
      tip!.classList.add('hidden');
      return;
    }
    const sevText =
      hit.severity === 'critical' ? '严重' : hit.severity === 'major' ? '主要' : '轻微';
    const sevColor =
      hit.severity === 'critical' ? 'red' : hit.severity === 'major' ? 'orange' : 'yellow';
    let html =
      '<div class="font-medium mb-1">' +
      hit.type +
      (hit.isViolated ? ' ✗' : ' ✓') +
      '</div>';
    if (hit.isViolated) {
      html +=
        '<div class="mb-1"><span class="text-' +
        sevColor +
        '-400">● ' +
        sevText +
        '</span></div>';
      if (hit.hints.length > 0) {
        html +=
          '<div class="text-gray-300 text-[10px]">' +
          hit.hints.slice(0, 4).join('<br>') +
          '</div>';
        if (hit.hints.length > 4) {
          html +=
            '<div class="text-gray-500 text-[10px]">… 还有 ' +
            (hit.hints.length - 4) +
            ' 条</div>';
        }
      }
    } else {
      html += '<div class="text-gray-400 text-[10px]">无违规</div>';
    }
    tip!.innerHTML = html;
    tip!.style.left = e.clientX + 12 + 'px';
    tip!.style.top = e.clientY + 12 + 'px';
    tip!.classList.remove('hidden');
  };

  const onLeave = () => {
    tip!.classList.add('hidden');
  };

  (canvas as unknown as Record<string, unknown>).__onMove = onMove;
  (canvas as unknown as Record<string, unknown>).__onLeave = onLeave;
  canvas.addEventListener('mousemove', onMove);
  canvas.addEventListener('mouseleave', onLeave);
}

// 向后兼容
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).renderViolationOverlay =
    renderViolationOverlay;
}