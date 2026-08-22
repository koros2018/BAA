// ── P123 Phase 1 Step 2: 全局状态模块 ────────────────────
// 从 baa-core.js 拆出 currentTeamId/currentProjectId 状态
// 兼容旧 var currentTeamId/currentProjectId 全局变量

export class AppState {
  private _teamId = localStorage.getItem('baa_team_id') || '';
  private _projectId = localStorage.getItem('baa_project_id') || '';
  private _historyTeamFilter = '';
  private _historyProjectFilter = '';

  get teamId(): string {
    return this._teamId;
  }
  get projectId(): string {
    return this._projectId;
  }
  get historyTeamFilter(): string {
    return this._historyTeamFilter;
  }
  get historyProjectFilter(): string {
    return this._historyProjectFilter;
  }

  setTeamId(id: string): void {
    this._teamId = id || '';
    localStorage.setItem('baa_team_id', this._teamId);
  }
  setProjectId(id: string): void {
    this._projectId = id || '';
    localStorage.setItem('baa_project_id', this._projectId);
  }

  setHistoryTeamFilter(v: string): void {
    this._historyTeamFilter = v;
  }
  setHistoryProjectFilter(v: string): void {
    this._historyProjectFilter = v;
  }

  loadApiBase(): void {
    const saved = localStorage.getItem('baa_api_base');
    const input = document.getElementById('api-base') as HTMLInputElement;
    if (saved && input) input.value = saved;
  }

  saveApiBase(): void {
    const input = document.getElementById('api-base') as HTMLInputElement;
    if (input) localStorage.setItem('baa_api_base', input.value);
  }
}

// 单例
export const appState = new AppState();

// ── 向后兼容：挂载到 window ──────────────────────────────
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'currentTeamId', {
    get: () => appState.teamId,
    set: (v: string) => appState.setTeamId(v),
  });
  Object.defineProperty(window, 'currentProjectId', {
    get: () => appState.projectId,
    set: (v: string) => appState.setProjectId(v),
  });
  window.setCurrentTeamId = (id?: string) => appState.setTeamId(id || '');
  window.setCurrentProjectId = (id?: string) => appState.setProjectId(id || '');
  window.getCurrentTeamId = () => appState.teamId;
  window.getCurrentProjectId = () => appState.projectId;
  window.loadApiBase = () => appState.loadApiBase();
  window.saveApiBase = () => appState.saveApiBase();
}