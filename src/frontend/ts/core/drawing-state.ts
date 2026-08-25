// ── P123 Step 4: 图纸/文件全局状态（替代 baa-admin.js 中的 var 泄漏）───
// parsedDrawings / fileCache 原本定义在 baa-admin.js，
// 旧代码中通过 window.parsedDrawings / window.fileCache 访问

declare global {
  interface Window {
    parsedDrawings?: Array<Record<string, unknown>>;
    fileCache?: Record<string, File>;
  }
}

let _parsedDrawings: Array<Record<string, unknown>> = [];
const _fileCache: Record<string, File> = {};

export function getParsedDrawings(): Array<Record<string, unknown>> {
  return _parsedDrawings;
}
export function setParsedDrawings(v: Array<Record<string, unknown>>): void {
  _parsedDrawings = v;
  if (typeof window !== 'undefined') window.parsedDrawings = v;
}
export function getFileCache(): Record<string, File> {
  return _fileCache;
}
export function setFileCache(id: string, file: File): void {
  _fileCache[id] = file;
  if (typeof window !== 'undefined') window.fileCache = _fileCache;
}