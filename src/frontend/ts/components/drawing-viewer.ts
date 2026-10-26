// ── T-B6: 交互式图纸查看器（违规↔图元双向定位） ─────────────
// 加载 /render/{file_id}/interactive 渲染的 SVG（每图元带 data-eid=DXF handle 与
// data-bbox=DXF 坐标）。联动契约（T-B6 验证结论）：finding.entity_id ↔ SemanticEntity.id
// 为合成计数 ID（classify.py），非 DXF handle —— 违规→图元定位以 bbox IoU 回退为主，
// data-eid 直查保留为优先路径（未来 id 源切换为 handle 时零改动生效）。

import { getApiBase, getHeaders } from '../core/api-client';

interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

const FLASH_MS = 2200;
const IOU_MIN = 0.3;

function parseBBoxAttr(el: SVGElement): BBox | null {
  const raw = el.getAttribute('data-bbox') || '';
  const parts = raw.split(',').map(Number);
  if (parts.length !== 4 || parts.some((n) => !isFinite(n))) return null;
  const [x, y, width, height] = parts;
  return { x, y, width, height };
}

function iou(a: BBox, b: BBox): number {
  const ix = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
  const iy = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
  const inter = ix * iy;
  const union = a.width * a.height + b.width * b.height - inter;
  return union > 0 ? inter / union : 0;
}

function clearHighlights(): void {
  document.querySelectorAll('[data-locate-highlight]').forEach((el) => {
    const svg = el as SVGElement;
    const prev = svg.getAttribute('data-locate-prev-style');
    if (prev != null) {
      if (prev === '') svg.removeAttribute('style');
      else svg.setAttribute('style', prev);
      svg.removeAttribute('data-locate-prev-style');
    }
    svg.removeAttribute('data-locate-highlight');
  });
}

function highlightSvgElement(el: SVGElement): void {
  clearHighlights();
  el.setAttribute('data-locate-prev-style', el.getAttribute('style') || '');
  el.setAttribute('data-locate-highlight', '1');
  if (el.tagName.toLowerCase() === 'text') {
    el.setAttribute('style', 'fill:#ef4444 !important; stroke:#ef4444 !important; font-weight:bold;');
  } else {
    el.setAttribute('style', 'stroke:#ef4444 !important; stroke-width:2px !important;');
  }
  try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch { /* older engines */ }
}

function flashViolationCard(entityId: string): void {
  if (!entityId) return;
  let sel: string;
  try { sel = '[data-entity-id="' + CSS.escape(entityId) + '"]'; } catch { sel = '[data-entity-id="' + entityId.replace(/"/g, '') + '"]'; }
  const card = document.querySelector(sel);
  if (!card) return;
  const cls = ['ring-2', 'ring-blue-500', 'rounded'];
  cls.forEach((c) => card.classList.add(c));
  try { card.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch { /* noop */ }
  window.setTimeout(() => cls.forEach((c) => card.classList.remove(c)), FLASH_MS);
}

function findEntities(): Array<Record<string, unknown>> {
  const w = window as unknown as Record<string, unknown>;
  return ((w._currentReviewEntities as unknown) as Array<Record<string, unknown>>) || [];
}

function entityBBox(e: Record<string, unknown>): BBox | null {
  const b = e.bbox as BBox | undefined;
  if (!b || typeof b.x !== 'number' || typeof b.width !== 'number') return null;
  return b;
}

/** 渲染交互式图纸到指定容器（核心函数，审查成功后或按钮触发） */
export async function renderInteractiveDrawing(containerId: string, fileId: string): Promise<boolean> {
  const container = document.getElementById(containerId);
  if (!container || !fileId) return false;
  try {
    const r = await fetch(getApiBase() + '/render/' + encodeURIComponent(fileId) + '/interactive', { headers: getHeaders() });
    if (!r.ok) {
      container.innerHTML = '<div class="text-xs text-red-400 p-2">交互式图纸加载失败（HTTP ' + r.status + '）</div>';
      return false;
    }
    const svg = await r.text();
    container.innerHTML = svg;
    const svgEl = container.querySelector('svg');
    if (svgEl) {
      const svgItem = svgEl as SVGElement;
      svgItem.style.maxWidth = '100%';
      svgItem.style.height = 'auto';
      svgEl.querySelectorAll('[data-eid]').forEach((el) => {
        (el as SVGElement).addEventListener('click', (ev: Event) => {
          ev.stopPropagation();
          const item = ev.currentTarget as SVGElement;
          highlightSvgElement(item);
          // 图元 → 违规：bbox IoU 匹配语义实体后闪烁违规卡片
          const bbox = parseBBoxAttr(item);
          if (!bbox) return;
          let bestId = '';
          let bestScore = 0;
          for (const e of findEntities()) {
            const eb = entityBBox(e);
            if (!eb) continue;
            const score = iou(bbox, eb);
            if (score > bestScore) { bestScore = score; bestId = String(e.id || ''); }
          }
          if (bestScore > IOU_MIN) flashViolationCard(bestId);
        });
      });
    }
    return true;
  } catch {
    container.innerHTML = '<div class="text-xs text-red-400 p-2">交互式图纸加载异常</div>';
    return false;
  }
}

/** UI 入口：从图纸下拉框取当前 file_id 渲染 */
export async function loadInteractiveDrawing(): Promise<void> {
  const sel = document.getElementById('review-drawing-select') as HTMLSelectElement | null;
  const id = (sel?.value || '').trim();
  if (!id) {
    window.showToast?.('请先选择已解析的图纸', 'info');
    return;
  }
  await renderInteractiveDrawing('interactive-drawing-container', id);
}

/** 违规 → 图元定位：先按 data-eid 直查（handle 命中），否则 bbox IoU 回退 */
export function locateEntity(entityId: string): boolean {
  if (!entityId) return false;
  const containers = document.querySelectorAll('[data-interactive-drawing]');
  if (!containers.length) {
    window.showToast?.('请先载入交互式图纸', 'info');
    return false;
  }
  let target: SVGElement | null = null;
  let query = '';
  try { query = '[data-eid="' + CSS.escape(entityId) + '"]'; } catch { query = '[data-eid="' + entityId.replace(/"/g, '') + '"]'; }
  for (const c of Array.from(containers)) {
    const direct = c.querySelector(query);
    if (direct) { target = direct as SVGElement; break; }
  }
  if (!target) {
    const ent = findEntities().find((e) => String(e.id || '') === entityId);
    const bbox = ent ? entityBBox(ent) : null;
    if (bbox) {
      let bestScore = 0;
      for (const c of Array.from(containers)) {
        c.querySelectorAll('[data-bbox]').forEach((el) => {
          const bb = parseBBoxAttr(el as SVGElement);
          if (!bb) return;
          const score = iou(bbox, bb);
          if (score > bestScore) { bestScore = score; target = el as SVGElement; }
        });
      }
      if (bestScore <= IOU_MIN) target = null;
    }
  }
  if (!target) {
    window.showToast?.('未在图面定位到该实体', 'info');
    return false;
  }
  highlightSvgElement(target);
  // D2-T4 移动端：定位后滚动到视口中心
  const rect = (target as Element).getBoundingClientRect();
  if (rect.top < 0 || rect.bottom > window.innerHeight || rect.left < 0 || rect.right > window.innerWidth) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
  }
  return true;
}
