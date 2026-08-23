// ── P123 Phase 3: Hash 路由 ──────────────────────────────
// 替代 page-nav.ts 的硬编码 if/else + DOM 手动切换
// URL: /#/home /#/review /#/batch /#/settings
// 支持: 初始化导航 / hashchange 监听 / 编程式导航 / 历史按钮

import { showToast } from '../core/toast';

export type PageName =
  | 'home'
  | 'specs'
  | 'analysis'
  | 'history'
  | 'apikeys'
  | 'cases'
  | 'cd'
  | 'model-params'
  | 'collab'
  | 'drawings'
  | 'review'
  | 'compare'
  | 'reverse'
  | 'funcs'
  | 'settings'
  | 'docs';

export interface RouteConfig {
  page: PageName;
  load?: () => unknown | Promise<unknown>;
  title?: string;
}

/** 页面 → 加载函数映射（渐进式，旧 .js 文件通过 window 调用） */
const ROUTES: RouteConfig[] = [
  { page: 'home', load: () => (window as unknown as Record<string, unknown>).loadDashboard && ((window as unknown as Record<string, unknown>).loadDashboard as () => unknown)() },
  { page: 'specs', load: () => (window as unknown as Record<string, unknown>).loadSpecs && ((window as unknown as Record<string, unknown>).loadSpecs as () => unknown)() },
  { page: 'analysis', load: () => (window as unknown as Record<string, unknown>).loadAnalysis && ((window as unknown as Record<string, unknown>).loadAnalysis as () => unknown)() },
  { page: 'history', load: () => (window as unknown as Record<string, unknown>).renderHistoryList && ((window as unknown as Record<string, unknown>).renderHistoryList as () => unknown)() },
  { page: 'apikeys', load: () => (window as unknown as Record<string, unknown>).loadAdminKeys && ((window as unknown as Record<string, unknown>).loadAdminKeys as () => unknown)() },
  { page: 'cases', load: () => { const w = window as unknown as Record<string, unknown>; if (typeof w.loadCaseStats === 'function') (w.loadCaseStats as () => unknown)(); if (typeof w.loadCases === 'function') (w.loadCases as (p: number) => unknown)(0); }},
  { page: 'cd', load: () => (window as unknown as Record<string, unknown>).loadCDItems && ((window as unknown as Record<string, unknown>).loadCDItems as () => unknown)() },
  { page: 'model-params', load: () => (window as unknown as Record<string, unknown>).switchModelParamTab && ((window as unknown as Record<string, unknown>).switchModelParamTab as (t: string) => unknown)('functions') },
  { page: 'collab', load: () => { const w = window as unknown as Record<string, unknown>; if (w.collabToken) { if (typeof w.updateUserStatus === 'function') (w.updateUserStatus as (b: boolean) => unknown)(true); setTimeout(() => { if (typeof w.collabEnterMain === 'function') (w.collabEnterMain as () => unknown)(); }, 100); } }},
  { page: 'drawings', title: '图纸管理' },
  { page: 'review', title: '审查' },
  { page: 'compare', title: '对比' },
  { page: 'reverse', title: '反向重构' },
  { page: 'funcs', title: '原子函数' },
  { page: 'settings', title: '设置' },
  { page: 'docs', title: '文档' },
];

class Router {
  private _current: PageName = 'home';
  private _listeners: Array<(page: PageName) => void> = [];
  private _popstateBound: (() => void) | null = null;

  constructor() {
    // 启动时读取初始 hash
    this._popstateBound = () => this._onHashChange();
    window.addEventListener('popstate', this._popstateBound);
    window.addEventListener('hashchange', () => this._onHashChange());
    // 初始化：根据 URL hash 导航
    const initial = this._readHash();
    this._current = initial;
    this._activate(initial, true);
  }

  get current(): PageName {
    return this._current;
  }

  /** 编程式导航 */
  go(page: PageName): void {
    if (page === this._current) return;
    const route = ROUTES.find((r) => r.page === page);
    if (!route) {
      console.warn('No route for:', page);
      return;
    }
    window.location.hash = '#' + page;
  }

  /** 注册页面切换监听 */
  on(listener: (page: PageName) => void): () => void {
    this._listeners.push(listener);
    return () => {
      this._listeners = this._listeners.filter((l) => l !== listener);
    };
  }

  private _readHash(): PageName {
    const hash = window.location.hash.replace('#', '').replace('/', '');
    const route = ROUTES.find((r) => r.page === (hash as PageName));
    return route ? (hash as PageName) : 'home';
  }

  private _onHashChange(): void {
    const page = this._readHash();
    this._activate(page);
  }

  private _activate(page: PageName, silent = false): void {
    this._current = page;

    // DOM 切换
    document.querySelectorAll('.page').forEach((el) => {
      (el as HTMLElement).classList.toggle('active', (el as HTMLElement).id === 'page-' + page);
    });
    document.querySelectorAll('.sidebar-item').forEach((el) => {
      (el as HTMLElement).classList.toggle(
        'active',
        (el as HTMLElement).dataset.page === page,
      );
    });

    // 加载数据
    const route = ROUTES.find((r) => r.page === page);
    if (route?.load) {
      try {
        const result = route.load();
        if (result && typeof (result as Promise<unknown>).then === 'function') {
          (result as Promise<unknown>).catch((e) => {
            console.error('页面加载错误:', page, e);
          });
        }
      } catch (e) {
        console.error('页面加载错误:', page, e);
      }
    }

    if (!silent) {
      this._listeners.forEach((l) => l(page));
    }
  }
}

export const router = new Router();

// 向后兼容
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).router = router;
}