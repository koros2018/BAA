// ── P123 Step 2: Export 导出组件 ───────────────────────
// 从 baa-review.js lines 1330-1413 迁入
// downloadReviewPdf / downloadReviewExport / downloadReviewJSON

import { getApiBase, getHeaders } from '../core/api-client';
import { getActiveKeyValue } from '../core/key-manager';
import { showToast } from '../core/toast';

export function downloadReviewPdf(reviewId: string): void {
  const url = getApiBase() + '/api/v1/review/pdf?review_id=' + encodeURIComponent(reviewId);
  const key = getActiveKeyValue();
  const headers: Record<string, string> = {};
  if (key) headers['Authorization'] = 'Bearer ' + key;

  fetch(url, { headers })
    .then((resp) => {
      if (!resp.ok) {
        return resp.json().then((d) => {
          throw new Error((d as Record<string, unknown>).detail?.toString() || '下载失败 (' + resp.status + ')');
        });
      }
      return resp.blob();
    })
    .then((blob) => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = '审查报告_' + (reviewId || 'report') + '.pdf';
      a.click();
      URL.revokeObjectURL(a.href);
    })
    .catch((err) => {
      showToast('❌ ' + (err as Error).message, 'error');
    });
}

export function downloadReviewExport(reviewId: string, format: string): void {
  if (!reviewId) {
    showToast('没有可导出的审查结果', 'info');
    return;
  }
  const url = getApiBase() + '/review/export?review_id=' + encodeURIComponent(reviewId) + '&format=' + format;
  fetch(url, { method: 'GET', headers: getHeaders() })
    .then((resp) => {
      if (!resp.ok) return resp.json().then((d) => { throw new Error((d as Record<string, unknown>).detail?.toString() || resp.statusText); });
      return resp.blob();
    })
    .then((blob) => {
      const mime = format === 'csv' ? 'text/csv;charset=utf-8-sig' : 'application/json';
      const ext = format === 'csv' ? 'csv' : 'json';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([blob], { type: mime }));
      a.download = '审查结果_' + reviewId + '.' + ext;
      a.click();
      URL.revokeObjectURL(a.href);
      showToast('✅ 已导出 ' + format.toUpperCase() + ' 文件', 'success');
    })
    .catch((e) => {
      showToast('❌ 导出失败: ' + (e as Error).message, 'error');
    });
}

export function downloadReviewJSON(): void {
  const violations = (window as unknown as Record<string, unknown>)._reviewViolations as Array<Record<string, unknown>> || [];
  if (violations.length === 0) {
    showToast('没有可导出的审查结果', 'info');
    return;
  }
  const exportData = {
    exportTime: new Date().toISOString(),
    totalViolations: violations.length,
    violations: violations.map((v) => ({
      entity_id: v.entity_id,
      entity_type: v.entity_type,
      clause_id: v.clause_id,
      clause_title: v.clause_title,
      severity: v.severity || 'major',
      result: v.result,
      extracted_value: v.extracted_value,
      required_value: v.required_value,
      difference: v.difference,
      explanation: v.explanation,
    })),
    violationByClause: {} as Record<string, number>,
  };
  violations.forEach((v) => {
    const cid = String(v.clause_id || 'unknown');
    exportData.violationByClause[cid] = (exportData.violationByClause[cid] || 0) + 1;
  });
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '审查结果_' + new Date().toISOString().slice(0, 10) + '.json';
  a.click();
  URL.revokeObjectURL(a.href);
}