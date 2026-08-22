/// <reference types="vite/client" />

declare global {
  interface Window {
    showToast?(message: string, type?: string, duration?: number): void;
    HEADERS?(): Record<string, string>;
    getHeaders?(): Record<string, string>;
    API_BASE?(): string;
    apiGet?(path: string): Promise<unknown>;
    apiPostJSON?(path: string, body: unknown): Promise<unknown>;
    apiPostFile?(path: string, file: File, params?: Record<string, string>): Promise<unknown>;
    apiFetch?(path: string, options?: RequestInit): Promise<unknown>;
    apiPost?(path: string, body: unknown): Promise<unknown>;
    adminGet?(path: string): Promise<unknown>;
    adminPost?(path: string, body: unknown): Promise<unknown>;
    adminDelete?(path: string): Promise<unknown>;
    adminHeaders?(m?: string): Record<string, string>;

    // 工具函数
    formatDate?(iso: number | string | null | undefined): string;
    maskKey?(key: string): string;
    escHtml?(text: unknown): string;
    permissionBadge?(perm: string): string;
    enabledBadge?(enabled: boolean): string;
    uid?(): string;
    mergeDeep?(target: Record<string, unknown>, source: Record<string, unknown>): Record<string, unknown>;

    // 骨架屏
    showSkeleton?(id: string, targetId?: string): void;
    hideSkeleton?(id: string, targetId?: string): void;
    renderSkeletonContainer?(container: HTMLElement | null, rows?: number, className?: string): void;
    renderProgress?(el: HTMLElement | null, label?: string, pct?: number): void;

    // 状态
    getCurrentTeamId?(): string;
    getCurrentProjectId?(): string;
    setCurrentTeamId?(id: string): void;
    setCurrentProjectId?(id: string): void;
    loadApiBase?(): void;
    saveApiBase?(): void;

    // 密钥管理
    getApiKey?(): string;
    getActiveKeyValue?(): string;
    loadApiKeys?(): void;
    saveApiKeys?(): void;
    switchApiKey?(id: string): void;
    deleteCurrentApiKey?(): void;
    addApiKey?(): void;
    deleteApiKey?(id: string): void;
    copyApiKey?(id: string): void;
    populateTokenSelect?(): void;

    // 后端密钥管理
    initAdminToken?(): Promise<void>;
    loadAdminKeys?(): Promise<void>;
    openCreateKeyModal?(): void;
    closeCreateKeyModal?(): void;
    createAdminKey?(): Promise<void>;
    copyCreatedKey?(): void;
    closeKeyCreatedModal?(): void;
    showKeyDetail?(keyId: string): Promise<void>;
    showDetailRawKey?(): void;
    copyDetailRawKey?(): void;
    copyKeyFromDetail?(keyId: string): Promise<void>;
    closeKeyDetailModal?(): void;
    confirmRevokeKey?(keyId: string): Promise<void>;
    confirmDeleteKey?(keyId: string): Promise<void>;
    revokeAdminKey?(): Promise<void>;

    // 审查面板
    showDrawingReviewPanel?(show: boolean): void;
    switchDrawingTab?(tab: string): void;
    loadReviewContext?(): Promise<void>;
    onReviewTeamSelect?(): void;
    onReviewProjectSelect?(): void;

    // 导航
    navigateTo?(page: string): Promise<void>;
    testConnection?(): Promise<void>;

    // 其他模块暴露的全局函数
    collabToken?: string;
    collabApi?(path: string): Promise<unknown>;
    collabEnterMain?(): void;
    updateUserStatus?(v: boolean): void;
    loadDashboard?(): Promise<void>;
    loadSpecs?(): void;
    loadAnalysis?(): Promise<void>;
    renderHistoryList?(): void;
    loadCaseStats?(): void;
    loadCases?(page: number): void;
    loadCDItems?(): void;
    switchModelParamTab?(tab: string): void;
    refreshDrawingSelect?(): void;
    loadFeedbackStats?(): void;
    loadFeedbacks?(): void;
    renderStructuralThresholds?(): void;
    renderStructuralViolations?(items: unknown[]): void;
    renderThermalThresholds?(): void;
    renderThermalViolations?(items: unknown[]): void;
  }
}

export {};