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
    adminGet?(path: string): Promise<unknown>;
    adminPost?(path: string, body: unknown): Promise<unknown>;
    adminDelete?(path: string): Promise<unknown>;
    adminHeaders?(m?: string): Record<string, string>;
  }
}

export {};