// ── P123 Phase 1 Step 3: 规范数据全局状态模块 ────────────
// 从 baa-core.js 拆出 SPEC_DATA 全局变量
// 供 baa-admin.js (loadSpecs/stats) 和 baa-review.js (home-stats) 使用

let _specData: Array<Record<string, unknown>> = [];

export function getSpecData(): Array<Record<string, unknown>> {
  return _specData;
}

export function setSpecData(specs: Array<Record<string, unknown>>): void {
  _specData = specs;
}

// 向后兼容：挂载到 window
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'SPEC_DATA', {
    get: () => _specData,
    set: (v: Array<Record<string, unknown>>) => { _specData = v; },
  });
}