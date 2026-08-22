// ── P123 Phase 1 Step 2: 图纸审查面板 + 上下文选择模块 ───
import { appState } from './state';
import { apiGet } from './api-client';

export function showDrawingReviewPanel(show: boolean): void {
  const el = document.getElementById('drawing-review-panel') as HTMLElement | null;
  if (!el) return;
  el.classList.toggle('hidden', !show);
  if (show) {
    loadReviewContext();
    const select = document.getElementById('review-drawing-select') as HTMLSelectElement | null;
    const parsed = (window as unknown as Record<string, unknown>).parsedDrawings as unknown[];
    if (select && parsed && parsed.length > 0 && select.options.length <= 1) {
      const refresh = (window as unknown as Record<string, unknown>).refreshDrawingSelect;
      if (typeof refresh === 'function') refresh();
    }
  }
}

export function switchDrawingTab(tab: string): void {
  const btnMap: Record<string, string> = {
    single: 'dr-tab-single', batch: 'dr-tab-batch', multisheet: 'dr-tab-multisheet',
    feedback: 'dr-tab-feedback', thermal: 'dr-tab-thermal', structural: 'dr-tab-structural',
  };
  const panelMap: Record<string, string> = {
    single: 'dr-panel-single', batch: 'dr-panel-batch', multisheet: 'dr-panel-multisheet',
    feedback: 'dr-panel-feedback', thermal: 'dr-panel-thermal', structural: 'dr-panel-structural',
  };
  const sel = 'px-3 py-1.5 rounded text-xs font-medium bg-purple-100 text-purple-700';
  const unsel = 'px-3 py-1.5 rounded text-xs font-medium bg-gray-100 text-gray-600';
  for (const t in btnMap) {
    const el = document.getElementById(btnMap[t]) as HTMLElement | null;
    if (el) el.className = t === tab ? sel : unsel;
  }
  for (const t in panelMap) {
    const el = document.getElementById(panelMap[t]) as HTMLElement | null;
    if (el) el.classList.toggle('hidden', t !== tab);
  }
  const w = window as unknown as Record<string, (...args: unknown[]) => unknown>;
  if (tab === 'feedback' && typeof w.loadFeedbackStats === 'function') {
    w.loadFeedbackStats(); w.loadFeedbacks();
  }
  if (tab === 'structural' && typeof w.renderStructuralThresholds === 'function') {
    w.renderStructuralThresholds();
    w.renderStructuralViolations((window as unknown as Record<string, unknown>)._reviewStructuralViolations || []);
  }
  if (tab === 'thermal' && typeof w.renderThermalThresholds === 'function') {
    w.renderThermalThresholds();
    w.renderThermalViolations((window as unknown as Record<string, unknown>)._reviewThermalViolations || []);
  }
}

export async function loadReviewContext(): Promise<void> {
  const teamSel = document.getElementById('dr-team-select') as HTMLSelectElement | null;
  const projSel = document.getElementById('dr-project-select') as HTMLSelectElement | null;
  if (!teamSel || !projSel) return;
  const curTeam = appState.teamId;
  const curProj = appState.projectId;
  try {
    const teamsData = await apiGet('/collab/teams');
    const projectsData = await apiGet('/collab/projects');
    const teams = Array.isArray(teamsData)
      ? teamsData
      : ((teamsData as Record<string, unknown[]>).teams || []);
    const projects = Array.isArray(projectsData)
      ? projectsData
      : ((projectsData as Record<string, unknown[]>).projects || []);

    teamSel.innerHTML = '<option value="">👥 全部团队</option>';
    (teams as Array<Record<string, unknown>>).forEach((t) => {
      const opt = document.createElement('option');
      opt.value = String(t.id);
      opt.textContent = String(t.name);
      if (opt.value === curTeam) opt.selected = true;
      teamSel.appendChild(opt);
    });
    projSel.innerHTML = '<option value="">📋 全部项目</option>';
    (projects as Array<Record<string, unknown>>).forEach((p) => {
      const opt = document.createElement('option');
      opt.value = String(p.id);
      opt.textContent = String(p.name);
      if (opt.value === curProj) opt.selected = true;
      projSel.appendChild(opt);
    });
  } catch { /* non-fatal */ }
}

export function onReviewTeamSelect(): void {
  const el = document.getElementById('dr-team-select') as HTMLSelectElement | null;
  const teamId = el?.value || '';
  appState.setTeamId(teamId);
  appState.setProjectId('');
  const projSel = document.getElementById('dr-project-select') as HTMLSelectElement | null;
  if (projSel) projSel.value = '';
}

export function onReviewProjectSelect(): void {
  const el = document.getElementById('dr-project-select') as HTMLSelectElement | null;
  const projectId = el?.value || '';
  appState.setProjectId(projectId);
}

if (typeof window !== 'undefined') {
  window.showDrawingReviewPanel = showDrawingReviewPanel;
  window.switchDrawingTab = switchDrawingTab;
  window.loadReviewContext = loadReviewContext;
  window.onReviewTeamSelect = onReviewTeamSelect;
  window.onReviewProjectSelect = onReviewProjectSelect;
}