// ── P123 Step 2: Feedback 反馈申诉组件 ──────────────────
// 从 baa-review.js lines 826-891 迁入
// loadFeedbackStats / loadFeedbacks / submitFeedback

import { apiGet, apiFetch } from '../core/api-client';
import { showToast } from '../core/toast';
import { escHtml } from '../core/utils';

export async function loadFeedbackStats(): Promise<void> {
  const el = document.getElementById('fb-stats') as HTMLElement | null;
  if (!el) return;
  try {
    const data = (await apiGet('/api/v1/feedbacks/stats')) as Record<string, unknown>;
    if ((data.status as string) !== 'success') throw new Error('加载失败');
    const s = data.stats as Record<string, unknown>;
    const byClause = (s.by_clause || {}) as Record<string, unknown>;
    const topClauses = Object.entries(byClause)
      .slice(0, 5)
      .map(([c, n]) => '<p>' + escHtml(c) + ': ' + String(n) + '条</p>')
      .join('');
    const stats = s as {
      total?: number;
      by_status?: Record<string, number>;
      accepted_rate?: number;
    };
    el.innerHTML =
      '<div class="grid grid-cols-2 gap-2">' +
      '<div class="card p-2 text-xs">' +
      '<p class="font-medium">📊 申诉统计</p>' +
      '<p>总数: ' +
      stats.total +
      '</p><p>待审核: ' +
      (stats.by_status?.pending || 0) +
      '</p><p>已接受: ' +
      (stats.by_status?.accepted || 0) +
      '</p><p>已拒绝: ' +
      (stats.by_status?.rejected || 0) +
      '</p><p>接受率: ' +
      ((stats.accepted_rate || 0) * 100).toFixed(1) +
      '%</p></div>' +
      '<div class="card p-2 text-xs">' +
      '<p class="font-medium">📋 高频条款</p>' +
      topClauses +
      '</div></div>';
  } catch (e) {
    el.textContent = '加载失败: ' + (e as Error).message;
  }
}

export async function loadFeedbacks(): Promise<void> {
  const el = document.getElementById('fb-list') as HTMLElement | null;
  if (!el) return;
  try {
    const data = (await apiGet('/api/v1/feedbacks')) as Record<string, unknown>;
    if ((data.status as string) !== 'success') throw new Error('加载失败');
    const fbs = (data.feedbacks || []) as Array<Record<string, unknown>>;
    if (fbs.length === 0) {
      el.innerHTML = '<p class="text-gray-400 text-center py-4">暂无申诉记录</p>';
      return;
    }
    el.innerHTML = fbs
      .map((fb) => {
        const status = String(fb.status || '');
        const badge =
          status === 'accepted'
            ? 'bg-green-100 text-green-700'
            : status === 'rejected'
              ? 'bg-red-100 text-red-700'
              : 'bg-yellow-100 text-yellow-700';
        const stxt =
          status === 'accepted' ? '✅ 已接受' : status === 'rejected' ? '❌ 已拒绝' : '⏳ 待审核';
        const reviewed = fb.reviewed_by
          ? '<p class="text-gray-400">审核: ' +
            escHtml(String(fb.reviewed_by)) +
            ' - ' +
            escHtml(String(fb.review_comment || '')) +
            '</p>'
          : '';
        return (
          '<div class="card p-2 text-xs">' +
          '<div class="flex items-center gap-2 mb-1">' +
          '<span class="font-mono">' +
          escHtml(String(fb.feedback_id || '')) +
          '</span>' +
          '<span class="px-1.5 py-0.5 rounded text-xs ' +
          badge +
          '">' +
          stxt +
          '</span></div>' +
          '<p class="font-medium">' +
          escHtml(String(fb.clause_id || '')) +
          '</p>' +
          '<p class="text-gray-500">' +
          escHtml(String(fb.reason || '无理由')) +
          '</p>' +
          reviewed +
          '<p class="text-gray-400 text-xs">' +
          (String(fb.created_at || '').slice(0, 10)) +
          '</p></div>'
        );
      })
      .join('');
  } catch (e) {
    el.innerHTML = '<p class="text-red-400 text-center py-4">加载失败: ' + (e as Error).message + '</p>';
  }
}

export async function submitFeedback(): Promise<void> {
  const val = (id: string) => (document.getElementById(id) as HTMLInputElement | null)?.value?.trim() || '';
  const taskId = val('fb-task-id');
  const clauseId = val('fb-clause-id');
  const entityId = val('fb-entity-id');
  const reason = val('fb-reason');
  const description = val('fb-description');
  const originalValue = val('fb-original-value');
  const severity = val('fb-severity');

  if (!taskId || !clauseId || !reason) {
    showToast('请填写任务 ID、规范条款和申诉理由', 'info');
    return;
  }

  try {
    const data = (await apiFetch('/api/v1/feedbacks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        clause_id: clauseId,
        entity_id: entityId,
        entity_type: '',
        reason,
        description,
        original_value: originalValue ? parseFloat(originalValue) : null,
        severity,
      }),
    })) as Record<string, unknown>;

    if (!data.status) throw new Error('提交失败');
    const fb = data.feedback as Record<string, unknown> | undefined;
    showToast('申诉提交成功！ID: ' + (fb?.feedback_id || ''), 'success');
    ['fb-task-id', 'fb-clause-id', 'fb-entity-id', 'fb-reason', 'fb-description', 'fb-original-value', 'fb-severity'].forEach((id) => {
      const el = document.getElementById(id) as HTMLInputElement | null;
      if (el) el.value = '';
    });
    loadFeedbackStats();
    loadFeedbacks();
  } catch (e) {
    showToast('提交失败: ' + (e as Error).message, 'error');
  }
}