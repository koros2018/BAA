// ── P123 Step 6: 模型参数导出组件 ──────────────────────
// 从 baa-model-params.js 迁入 (190 行)
// 5 Tab: 原子函数 / 图层规则 / 施工图审查标准 / 样本 / 导出

import { apiGet, getApiBase } from '../core/api-client';
import { showToast } from '../core/toast';
import { escHtml } from '../core/utils';

const MODEL_PARAMS_TABS: Record<string, string> = {
  'functions': '原子函数参数',
  'layer-rules': '图层规则',
  'cd-items': '施工图审查标准',
  'samples': '审查样本',
  'export': '数据导出',
};

let _mpLoading = false;

function _mpSetHTML(box: HTMLElement | null, html: string): void {
  if (!box) { _mpLoading = false; return; }
  box.classList.remove('hidden');
  box.style.display = 'block';
  box.style.overflow = 'auto';
  box.style.maxHeight = '480px';
  box.innerHTML = html;
  _mpLoading = false;
}

function _mpSetError(box: HTMLElement | null, err: unknown): void {
  const msg = err instanceof Error ? err.message : String(err);
  _mpSetHTML(box, `<p class="text-red-400 text-sm">\u52A0\u8F7D\u5931\u8D25: ${escHtml(msg)}</p>`);
}

function _mpSafe(s: unknown): string {
  return String(s === null || s === undefined ? '-' : s);
}

async function _mpLoadFunctions(): Promise<void> {
  const box = document.getElementById('mp-functions') as HTMLElement | null;
  try {
    const data = await apiGet('/api/v1/model-params/functions?limit=2000') as Record<string, unknown>;
    const funcs = (data.data as Array<Record<string, unknown>>) || (data.functions as Array<Record<string, unknown>>) || [];
    if (funcs.length === 0) { _mpSetHTML(box, '<p class="text-gray-400 text-sm">\u65E0\u6570\u636E</p>'); return; }

    const cats: Record<string, number> = {};
    funcs.forEach((f) => { const c = (f.category as string) || 'other'; cats[c] = (cats[c] || 0) + 1; });
    const summary = Object.keys(cats).slice(0, 12).map((c) =>
      `<span class="badge badge-sm badge-secondary">${escHtml(c)} ${cats[c]}</span>`,
    ).join(' ');

    const rows = funcs.slice(0, 80).map((f) =>
      `<tr><td class="py-1 px-2 text-xs text-mono">${escHtml(f.func_id as string)}</td>` +
      `<td class="py-1 px-2 text-xs">${escHtml(f.title as string)}</td>` +
      `<td class="py-1 px-2 text-xs"><span class="badge badge-xs">${escHtml(f.category as string)}</span></td>` +
      `<td class="py-1 px-2 text-xs text-mono">${escHtml(f.clause_id as string)}</td>` +
      `<td class="py-1 px-2 text-xs">${escHtml(f.operator as string)} ${escHtml(f.threshold as string)}</td></tr>`,
    ).join('');

    _mpSetHTML(box,
      `<div class="flex gap-2 mb-2 flex-wrap">${summary}</div>` +
      `<div class="text-xs text-gray-400 mb-2">\u663E\u793A ${funcs.length} \u4E2A\u539F\u5B50\u51FD\u6570\uff08\u524D 80 \u6761\uff09</div>` +
      `<div class="overflow-auto">` +
      `<table class="w-full text-sm">` +
      `<thead class="bg-gray-50 text-xs text-gray-500"><tr>` +
      `<th class="py-1 px-2">#</th><th class="py-1 px-2">\u6807\u9898</th><th class="py-1 px-2">\u5206\u7C7B</th>` +
      `<th class="py-1 px-2">\u89C4\u8303\u6761\u6B3E</th><th class="py-1 px-2">\u5224\u5B9A\u6761\u4EF6</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div>`,
    );
  } catch (e) { _mpSetError(box, e); }
}

async function _mpLoadLayerRules(): Promise<void> {
  const box = document.getElementById('mp-layer-rules') as HTMLElement | null;
  try {
    const data = await apiGet('/api/v1/model-params/layer-rules') as Record<string, unknown>;
    const rules = (data.data as Array<Record<string, unknown>>) || (data.rules as Array<Record<string, unknown>>) || [];
    if (rules.length === 0) { _mpSetHTML(box, '<p class="text-gray-400 text-sm">\u65E0\u6570\u636E</p>'); return; }

    const lr = rules.filter((r) => r.source === 'LAYER_RULES').length;
    const sl = rules.filter((r) => r.source === 'SHORT_LAYER_RULES').length;

    const rows = rules.slice(0, 60).map((r) => {
      const cls = r.source === 'SHORT_LAYER_RULES' ? 'badge-secondary' : 'badge-primary';
      return `<tr><td class="py-1 px-2 text-xs text-mono">${escHtml(r.pattern as string)}</td>` +
        `<td class="py-1 px-2 text-xs">${escHtml(r.entity_type as string)}</td>` +
        `<td class="py-1 px-2 text-xs"><span class="badge badge-xs ${cls}">${escHtml(r.source as string)}</span></td>` +
        `<td class="py-1 px-2 text-xs">${escHtml(r.match_type as string)}</td></tr>`;
    }).join('');

    _mpSetHTML(box,
      `<div class="text-xs text-gray-400 mb-2">${rules.length} \u6761\uff08LAYER_RULES: ${lr} / SHORT: ${sl}\uff09\u524D 60 \u6761</div>` +
      `<div class="overflow-auto">` +
      `<table class="w-full text-sm">` +
      `<thead class="bg-gray-50 text-xs text-gray-500"><tr>` +
      `<th class="py-1 px-2">\u5173\u952E\u5B57</th><th class="py-1 px-2">\u5B9E\u4F53\u7C7B\u578B</th>` +
      `<th class="py-1 px-2">\u6765\u6E90</th><th class="py-1 px-2">\u5339\u914D\u65B9\u5F0F</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div>`,
    );
  } catch (e) { _mpSetError(box, e); }
}

async function _mpLoadCDItems(): Promise<void> {
  const box = document.getElementById('mp-cd-items') as HTMLElement | null;
  try {
    const data = await apiGet('/api/v1/model-params/cd-items') as Record<string, unknown>;
    const items = (data.data as Array<Record<string, unknown>>) || (data.items as Array<Record<string, unknown>>) || [];
    if (items.length === 0) { _mpSetHTML(box, '<p class="text-gray-400 text-sm">\u65E0\u6570\u636E</p>'); return; }

    const lvl: Record<string, number> = { L1: 0, L2: 0, L3: 0 };
    items.forEach((i) => { if (i.level && lvl[i.level as keyof typeof lvl] !== undefined) lvl[i.level as keyof typeof lvl]++; });
    const lvls = Object.keys(lvl).map((k) => {
      const cls = k === 'L1' ? 'text-red-500' : k === 'L2' ? 'text-orange-500' : 'text-green-500';
      return `<span class="${cls}">${k}: ${lvl[k]}</span>`;
    }).join(' ');

    const rows = items.slice(0, 50).map((i) =>
      `<tr><td class="py-1 px-2 text-xs text-mono">${escHtml(i.item_id as string)}</td>` +
      `<td class="py-1 px-2 text-xs">${escHtml(i.title as string)}</td>` +
      `<td class="py-1 px-2 text-xs"><span class="badge badge-xs">${escHtml(i.level as string)}</span></td>` +
      `<td class="py-1 px-2 text-xs">${escHtml(i.major as string)}</td></tr>`,
    ).join('');

    _mpSetHTML(box,
      `<div class="flex gap-3 mb-2 text-xs">${lvls}</div>` +
      `<div class="overflow-auto">` +
      `<table class="w-full text-sm">` +
      `<thead class="bg-gray-50 text-xs text-gray-500"><tr>` +
      `<th class="py-1 px-2">\u7F16\u7801</th><th class="py-1 px-2">\u5BA1\u67E5\u9879</th>` +
      `<th class="py-1 px-2">\u7B49\u7EA7</th><th class="py-1 px-2">\u4E13\u4E1A</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div>`,
    );
  } catch (e) { _mpSetError(box, e); }
}

async function _mpLoadSamples(): Promise<void> {
  const box = document.getElementById('mp-samples') as HTMLElement | null;
  try {
    const data = await apiGet('/api/v1/model-params/samples?limit=20') as Record<string, unknown>;
    const samples = (data.data as Array<Record<string, unknown>>) || (data.samples as Array<Record<string, unknown>>) || [];
    if (samples.length === 0) {
      _mpSetHTML(box, '<p class="text-yellow-500 text-sm">\u65E0\u6837\u672C\u6570\u636E\uff08\u9700\u6709\u5BA1\u67E5\u8BB0\u5F55\u540E\u81EA\u52A8\u751F\u6210\uff09</p>');
      return;
    }
    const cards = samples.slice(0, 10).map((s) =>
      `<div class="card p-2 mb-2">` +
      `<div class="text-xs text-gray-400">${escHtml(s.created_at as string)}</div>` +
      `<div class="text-sm font-medium">${escHtml((s.title ?? s.func_id ?? '\u6837\u672C') as string)}</div>` +
      `<div class="text-xs text-mono">${escHtml(s.func_id as string)} | ${escHtml(s.dxf_file as string)}</div>` +
      `<div class="text-xs text-gray-500 mt-1">${s.query ? escHtml(s.query as string).slice(0, 200) : ''}</div>` +
      `</div>`,
    ).join('');
    _mpSetHTML(box, `<div class="text-xs text-gray-400 mb-2">\u5171 ${samples.length} \u6761\uff08\u524D 10 \u6761\uff09</div>` + cards);
  } catch (e) { _mpSetError(box, e); }
}

function switchModelParamTab(tab: string): void {
  if (_mpLoading && tab !== 'export') return;
  _mpLoading = true;

  Object.keys(MODEL_PARAMS_TABS).forEach((t) => {
    const btn = document.getElementById(`mptab-${t}`) as HTMLElement | null;
    const pane = document.getElementById(`mp-${t}`) as HTMLElement | null;
    if (btn) {
      btn.classList.toggle('active-tab', t === tab);
    }
    if (pane) {
      if (t === tab) {
        pane.classList.remove('hidden');
        pane.style.display = 'block';
      } else {
        pane.classList.add('hidden');
        pane.style.display = 'none';
      }
    }
  });

  if (tab === 'functions') _mpLoadFunctions();
  else if (tab === 'layer-rules') _mpLoadLayerRules();
  else if (tab === 'cd-items') _mpLoadCDItems();
  else if (tab === 'samples') _mpLoadSamples();
  else if (tab === 'export') {
    _mpLoading = false;
    return;
  }
}

async function downloadModelExport(format: string): Promise<void> {
  try {
    const url = getApiBase() + `/api/v1/model-params/export?format=${encodeURIComponent(format)}`;
    window.open(url, '_blank');
    showToast(`\u5DF2\u5F00\u59CB\u4E0B\u8F7D ${format} \u683C\u5F0F`);
  } catch (e) {
    showToast(`\u4E0B\u8F7D\u5931\u8D25: ${(e as Error).message}`);
  }
}

export {
  MODEL_PARAMS_TABS,
  switchModelParamTab,
  downloadModelExport,
};
