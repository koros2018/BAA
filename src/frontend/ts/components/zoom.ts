// ── P123 Step 3: Zoom 图像缩放组件 ──────────────────────
// 从 baa-admin.js lines 542-705 迁入
// zoomImage / zoomSet / zoomReset / zoomFit / zoomClose

interface ZoomState {
  scale: number;
  offsetX: number;
  offsetY: number;
  isDragging: boolean;
  lastX: number;
  lastY: number;
}

declare global {
  interface Window {
    __zoomState?: ZoomState | null;
  }
}

export function zoomImage(img: HTMLImageElement | null): void {
  if (!img || !img.src || img.style.display === 'none') return;

  const old = document.getElementById('zoom-viewer');
  if (old) old.remove();

  const viewer = document.createElement('div');
  viewer.id = 'zoom-viewer';
  viewer.className = 'fixed inset-0 z-50 bg-black bg-opacity-90 select-none';
  viewer.innerHTML =
    '<div class="absolute inset-0 flex items-center justify-center overflow-hidden" id="zoom-stage">' +
      '<img id="zoom-img" src="' + img.src + '" alt="" draggable="false" ' +
      'style="max-width:95vw;max-height:95vh;transition:transform .12s ease-out;cursor:grab" />' +
    '</div>' +
    '<div class="absolute top-3 left-3 flex gap-1 z-10" id="zoom-toolbar">' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomSet(1)">＋</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomSet(-1)">－</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomReset()" title="重置">⟲</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomFit()" title="适应窗口">⊡</button>' +
      '<button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomClose()" title="关闭">✕</button>' +
      '<span id="zoom-scale" class="bg-white bg-opacity-80 text-gray-700 px-2 py-1 rounded text-xs self-center ml-1">100%</span>' +
    '</div>' +
    '<div class="absolute bottom-3 right-3 bg-black bg-opacity-50 text-gray-300 text-xs px-2 py-1 rounded" id="zoom-hint">滚轮缩放 · 拖拽平移 · ←↑→↓ · 空格/ESC 关闭</div>';

  document.body.appendChild(viewer);

  const imgEl = document.getElementById('zoom-img') as HTMLImageElement | null;
  const stage = document.getElementById('zoom-stage') as HTMLElement | null;
  const scaleEl = document.getElementById('zoom-scale') as HTMLElement | null;

  const state: ZoomState = { scale: 1, offsetX: 0, offsetY: 0, isDragging: false, lastX: 0, lastY: 0 };
  window.__zoomState = state;

  const apply = () => {
    if (!imgEl || !stage || !scaleEl) return;
    const x = state.offsetX + (stage.clientWidth - stage.clientWidth * state.scale) / 2;
    const y = state.offsetY + (stage.clientHeight - stage.clientHeight * state.scale) / 2;
    imgEl.style.transform = 'translate(' + x.toFixed(1) + 'px, ' + y.toFixed(1) + 'px) scale(' + state.scale.toFixed(4) + ')';
    imgEl.style.transformOrigin = '0 0';
    scaleEl.textContent = Math.round(state.scale * 100) + '%';
  };

  imgEl?.addEventListener('mousedown', (e) => {
    state.isDragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    imgEl!.style.cursor = 'grabbing';
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!state.isDragging) return;
    state.offsetX += e.clientX - state.lastX;
    state.offsetY += e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    apply();
  });
  window.addEventListener('mouseup', () => {
    state.isDragging = false;
    if (imgEl) imgEl.style.cursor = 'grab';
  });

  stage?.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY;
    const factor = delta < 0 ? 1.12 : 1 / 1.12;
    const newScale = Math.max(0.1, Math.min(20, state.scale * factor));

    const rect = stage!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const oldCx = state.offsetX + (rect.width - rect.width * state.scale) / 2;
    const oldCy = state.offsetY + (rect.height - rect.height * state.scale) / 2;
    const relX = (mx - oldCx) / state.scale;
    const relY = (my - oldCy) / state.scale;

    state.offsetX = mx - relX * newScale - (rect.width - rect.width * newScale) / 2;
    state.offsetY = my - relY * newScale - (rect.height - rect.height * newScale) / 2;
    state.scale = newScale;
    apply();
  }, { passive: false });

  viewer.addEventListener('click', (e) => {
    if (e.target === viewer || e.target === stage) zoomClose();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { zoomClose(); return; }
    if (e.key === ' ') { e.preventDefault(); zoomClose(); return; }
    if (e.key === '+' || e.key === '=') { zoomSet(1); return; }
    if (e.key === '-') { zoomSet(-1); return; }
    if (e.key === 'ArrowLeft') { state.offsetX += 30; apply(); e.preventDefault(); }
    if (e.key === 'ArrowRight') { state.offsetX -= 30; apply(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { state.offsetY += 30; apply(); e.preventDefault(); }
    if (e.key === 'ArrowDown') { state.offsetY -= 30; apply(); e.preventDefault(); }
  });

  apply();
}

export function zoomSet(dir: number): void {
  const state = window.__zoomState;
  if (!state) return;
  const imgEl = document.getElementById('zoom-img') as HTMLImageElement | null;
  const stage = document.getElementById('zoom-stage') as HTMLElement | null;
  if (!imgEl || !stage) return;
  const factor = dir > 0 ? 1.25 : 0.8;
  const newScale = Math.max(0.1, Math.min(20, state.scale * factor));
  const rect = stage.getBoundingClientRect();
  const oldCx = state.offsetX + (rect.width - rect.width * state.scale) / 2;
  const oldCy = state.offsetY + (rect.height - rect.height * state.scale) / 2;
  state.offsetX = oldCx - (rect.width - rect.width * newScale) / 2;
  state.offsetY = oldCy - (rect.height - rect.height * newScale) / 2;
  state.scale = newScale;
  const x = state.offsetX + (rect.width - rect.width * state.scale) / 2;
  const y = state.offsetY + (rect.height - rect.height * state.scale) / 2;
  imgEl.style.transform = 'translate(' + x.toFixed(1) + 'px, ' + y.toFixed(1) + 'px) scale(' + state.scale.toFixed(4) + ')';
  imgEl.style.transformOrigin = '0 0';
  const s = document.getElementById('zoom-scale') as HTMLElement | null;
  if (s) s.textContent = Math.round(state.scale * 100) + '%';
}

export function zoomReset(): void {
  const state = window.__zoomState;
  const imgEl = document.getElementById('zoom-img') as HTMLImageElement | null;
  if (!state || !imgEl) return;
  state.scale = 1;
  state.offsetX = 0;
  state.offsetY = 0;
  imgEl.style.transform = 'none';
  const s = document.getElementById('zoom-scale') as HTMLElement | null;
  if (s) s.textContent = '100%';
}

export function zoomFit(): void {
  zoomReset();
}

export function zoomClose(): void {
  window.__zoomState = null;
  const el = document.getElementById('zoom-viewer');
  if (el) el.remove();
}