// ── P123 Phase 1: 骨架屏模块 ──────────────────────────────
// 从 baa-core.js showSkeleton/hideSkeleton/renderSkeletonContainer/renderProgress 拆出

export function showSkeleton(skeletonId: string, targetId?: string): void {
  const skel = document.getElementById(skeletonId);
  if (!skel) return;
  skel.classList.remove('hidden');
  if (targetId) {
    const target = document.getElementById(targetId);
    if (target) target.classList.add('hidden');
  }
}

export function hideSkeleton(skeletonId: string, targetId?: string): void {
  const skel = document.getElementById(skeletonId);
  if (!skel) return;
  skel.classList.add('hidden');
  if (targetId) {
    const target = document.getElementById(targetId);
    if (target) target.classList.remove('hidden');
  }
}

export function renderSkeletonContainer(
  container: HTMLElement | null,
  rows = 3,
  className = 'skeleton-overlay',
): void {
  if (!container) return;
  const html = Array(rows)
    .fill(0)
    .map(
      () =>
        '<div class="skeleton skeleton-row mb-2"><span class="skeleton-text w-32"></span><span class="skeleton-text flex-1"></span></div>',
    )
    .join('');
  container.innerHTML = html;
  container.className = className;
  container.classList.remove('hidden');
}

export function renderProgress(
  el: HTMLElement | null,
  label = '处理中',
  pct = 0,
): void {
  if (!el) return;
  el.className = 'review-progress';
  el.innerHTML =
    `<div class="review-progress-text"><span>${label}</span><span>${pct}%</span></div>` +
    `<div class="review-progress-bar"><div class="review-progress-fill" style="width:${pct}%"></div></div>`;
}