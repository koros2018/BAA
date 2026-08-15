/* ── P87: SSE 流式批量审查消费者 ─────────────────────────
 * 后端 /batch-review-stream 推送实时进度事件，前端逐事件渲染。
 *
 * 事件流：
 *   file.queued → file.parsing → file.semantic → file.checking
 *     → file.done | file.error → batch.done
 */
async function runBatchReviewSSE() {
  if (batchFiles.length === 0) {
    showToast('请先选择至少一个图纸文件', 'info');
    return;
  }

  const btn = document.getElementById('batch-review-start-btn');
  const loading = document.getElementById('batch-review-loading');
  const summary = document.getElementById('batch-review-summary');
  const details = document.getElementById('batch-review-details');
  const skel = document.getElementById('batch-review-skeleton');


  btn.disabled = true;
  loading.classList.remove('hidden');
  loading.textContent = '⏳ 正在批量审查（实时进度）...';
  loading.className = 'mt-3 text-sm text-gray-500';
  // 隐藏已有结果，显示骨架屏
  if (summary) summary.classList.add('hidden');
  if (details) details.classList.add('hidden');
  if (skel) skel.classList.remove('hidden');

  const formData = new FormData();
  batchFiles.forEach(f => formData.append('files', f));
  const totalFiles = batchFiles.length;
  const fileStates = {};

  try {
    const resp = await fetch(API_BASE() + '/batch-review-stream', {
      method: 'POST',
      headers: HEADERS(),
      body: formData,
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.detail?.message || '审查请求失败 (' + resp.status + ')');
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      // SSE 事件以空行分隔
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // 保留不完整行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        try {
          const evt = JSON.parse(data);
          handleBatchEvent(evt, totalFiles, fileStates, summary, details, loading);
        } catch (e) {
          // 忽略非 JSON 数据行
        }
      }
    }

  } catch (err) {
    if (loading) {
      loading.textContent = '❌ ' + err.message;
      loading.className = 'mt-3 text-sm text-red-500';
    }
  } finally {
    btn.disabled = false;
    if (skel) skel.classList.add('hidden');
    if (summary) summary.classList.remove('hidden');
    if (details) details.classList.remove('hidden');
  }
}

/* ── P87: SSE 事件处理 ─────────────────────────────── */
function handleBatchEvent(evt, totalFiles, fileStates, summary, details, loading) {
  if (!evt || !evt.event) return;

  switch (evt.event) {
    case 'file.queued': {
      const idx = evt.index;
      fileStates[idx] = {
        filename: evt.filename,
        status: 'queued',
        stage: '排队中',
        file_id: null,
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.parsing': {
      fileStates[evt.index] = {
        ...fileStates[evt.index],
        status: 'parsing',
        stage: '解析中',
        file_id: evt.file_id,
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.semantic': {
      fileStates[evt.index] = {
        ...fileStates[evt.index],
        status: 'semantic',
        stage: '语义分析中',
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.checking': {
      fileStates[evt.index] = {
        ...fileStates[evt.index],
        status: 'checking',
        stage: '规则检查中 (' + (evt.entity_count || 0) + ' 实体)',
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.done': {
      fileStates[evt.index] = {
        ...fileStates[evt.index],
        status: 'done',
        violations: evt.violations || 0,
        score: evt.score || 0,
        entity_count: evt.entity_count || 0,
        stage: '完成',
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'file.error': {
      fileStates[evt.index] = {
        ...fileStates[evt.index],
        status: 'error',
        error_code: evt.error_code,
        error_message: evt.message || evt.error_code || '审查失败',
        stage: '错误',
      };
      updateLoadingProgress(loading, fileStates, totalFiles);
      break;
    }
    case 'batch.done': {
      renderBatchResults(evt, totalFiles, summary, details, loading, fileStates);
      break;
    }
  }
}

/* ── P87: 进度更新 ─────────────────────────────────── */
function updateLoadingProgress(loading, fileStates, totalFiles) {
  if (!loading) return;
  const stages = Object.values(fileStates);
  const done = stages.filter(s => s.status === 'done' || s.status === 'error').length;
  const active = stages.length - done;
  const progress = totalFiles > 0 ? Math.round((done / totalFiles) * 100) : 0;

  let parts = [];
  parts.push('⏳ 进度: ' + done + '/' + totalFiles + ' (' + progress + '%)');
  if (active > 0) {
    parts.push(' · ' + Array.from({ length: active }, (_, i) => {
      const stage = Object.values(fileStates)[i].stage || '处理中';
      return stage;
    }).join(', '));
  }
  parts.push(' · <span class="text-blue-500">实时 SSE 推送</span>');

  loading.innerHTML = parts.join('') + '<div class="mt-2">' + renderBatchProgressBar(done, totalFiles) + '</div>';
}

function renderBatchProgressBar(done, total) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return '<div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">' +
    '<div class="bg-blue-500 h-full rounded-full transition-all duration-300" style="width:' + pct + '%"></div></div>';
}

/* ── P87: 渲染最终结果 ─────────────────────────────── */
function renderBatchResults(evt, totalFiles, summary, details, loading, fileStates) {
  const bs = evt;
  const results = evt.results || [];
  const startTime = Date.now();

  if (summary) {
    const fail = bs.failed_files || 0;
    const succ = bs.success_files || 0;
    summary.innerHTML = `
      <div class="grid grid-cols-2 gap-2 mb-2">
        <div class="card p-2 text-xs">
          <p class="font-medium">📁 文件统计</p>
          <p>总数: ${totalFiles} | ✅成功: ${succ} | ❌失败: ${fail}</p>
        </div>
        <div class="card p-2 text-xs">
          <p class="font-medium">📊 审查统计</p>
          <p>实体: ${bs.total_entities || 0} | 违规: ${bs.total_violations || 0}</p>
          <p class="text-blue-500">SSE 实时推送 · 逐文件流式完成</p>
        </div>
      </div>
    `;
  }

  // 跨文件交叉分析
  if (evt.cross_analysis && evt.cross_analysis.length > 0 && details) {
    let crossHtml = '<div class="card p-2 text-xs mb-2">' +
      '<p class="font-medium text-sm mb-1">🔗 跨文件违规交叉分析</p>' +
      '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b">' +
      '<th class="pb-1 pr-1">规范条款</th><th class="pb-1 pr-1">违规数</th><th class="pb-1 pr-1">涉及图纸</th></tr></thead><tbody>';
    evt.cross_analysis.slice(0, 8).forEach(c => {
      crossHtml += '<tr class="border-b border-gray-50">' +
        '<td class="py-1 pr-1">' + c.clause_id + '</td>' +
        '<td class="py-1 pr-1">' + c.violations + '</td>' +
        '<td class="py-1 pr-1">' + c.files + ' 张</td>' +
        '</tr>';
    });
    crossHtml += '</tbody></table></div>';
    details.innerHTML = crossHtml + (details.innerHTML || '');
  }

  // 文件卡片
  if (results.length > 0 && details) {
    let fileHtml = '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">';
    results.forEach(r => {
      if (r.status === 'error') {
        fileHtml += '<div class="card p-2 text-xs border-l-2 border-red-500 bg-red-50">' +
          '<p class="font-medium text-red-600">❌ ' + escapeHtml(r.filename) + '</p>' +
          '<p class="text-gray-500">' + escapeHtml(r.message || r.error_code || '审查失败') + '</p></div>';
        return;
      }
      const s = r.summary || {};
      const isClean = (s.violations || 0) === 0;
      const sevColor = isClean ? 'green' : (s.violations >= 20 ? 'red' : 'orange');
      const total = s.total_checks || 0;
      const passRate = total > 0 ? Math.round((1 - s.violations / total) * 100) : 100;

      const sevCount = { critical: 0, major: 0, minor: 0 };
      (r.details || []).forEach(v => {
        const sv = v.severity || 'major';
        if (sv in sevCount) sevCount[sv]++;
      });

      let bar = '<div class="mt-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">' +
        '<div class="' + sevColor + '-500 h-full rounded-full" style="width:' + passRate + '%"></div></div>' +
        '<div class="flex justify-between text-[10px] text-gray-400 mt-0.5">' +
        '<span>通过率 ' + passRate + '%</span><span>检查 ' + total.toLocaleString() + '</span></div>';

      let badges = '';
      if (sevCount.critical > 0) badges += '<span class="px-1 rounded bg-red-100 text-red-700 text-[10px]">● ' + sevCount.critical + ' 严重</span>';
      if (sevCount.major > 0) badges += '<span class="px-1 rounded bg-orange-100 text-orange-700 text-[10px]">● ' + sevCount.major + ' 主要</span>';
      if (sevCount.minor > 0) badges += '<span class="px-1 rounded bg-yellow-100 text-yellow-700 text-[10px]">● ' + sevCount.minor + ' 轻微</span>';
      if (!badges) badges = '<span class="px-1 rounded bg-green-100 text-green-700 text-[10px]">✓ 无违规</span>';

      fileHtml += '<div class="card p-2 text-xs border-l-2 border-' + sevColor + '-500">' +
        '<div class="flex items-center justify-between mb-1">' +
        '<p class="font-medium truncate" title="' + escapeHtml(r.filename) + '">' + escapeHtml(r.filename) + '</p>' +
        '<span class="text-' + sevColor + '-600 font-medium text-sm">' + (isClean ? '✓' : s.violations) + '</span>' +
        '</div>' +
        '<p class="text-gray-500 text-[10px]">' + (s.total_entities || 0) + ' 实体</p>' +
        bar +
        '<div class="mt-1 flex flex-wrap gap-0.5">' + badges + '</div>' +
        '</div>';
    });
    fileHtml += '</div>';
    details.innerHTML += fileHtml;
  }

  // 完成
  if (loading) {
    loading.textContent = '✅ 批量审查完成 — ' + (evt.success_files || 0) + '/' + totalFiles + ' 成功';
    loading.className = 'mt-3 text-sm text-green-600';
  }
}

function escapeHtml(s) {
  if (typeof s !== 'string') return s;
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ── 全局覆盖：runBatchReview → SSE 版本 ──────────────────
 * baa-review.js 中已有 runBatchReview() 使用同步 POST。
 * 此处覆盖为 SSE 流式版本（加载顺序在 baa-review.js 之后）。
 * 在非严格模式下，全局 function 声明可被重新赋值。
 */
window.runBatchReview = function() {
  return runBatchReviewSSE();
};
