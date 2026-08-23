// ── P123 Phase 1: API 客户端模块 ─────────────────────────
// 从 baa-core.js 拆出 HEADERS/getHeaders/API_BASE/apiGet/apiPost/apiPostFile
// 兼容旧 window 全局 API（向后兼容）

import type { ApiError } from './types';

interface ApiConfig {
  apiBase: () => string;
  getActiveKeyValue: () => string;
  currentTeamId: () => string;
  currentProjectId: () => string;
}

let _config: ApiConfig | null = null;
let _adminToken = '';

/** 初始化 API 客户端（Vite 模块入口调用一次） */
export function initApiClient(config: ApiConfig): void {
  _config = config;
}

/** 设置 admin token（密钥管理页专用） */
export function setAdminToken(token: string): void {
  _adminToken = token;
}

/** 获取当前 API base URL */
export function getApiBase(): string {
  return _config ? _config.apiBase() : 'http://localhost:8000';
}

/** 审查用 headers（API Key + team/project 上下文） */
export function getReviewHeaders(): Record<string, string> {
  if (!_config) return {};
  const h: Record<string, string> = {};
  const key = _config.getActiveKeyValue();
  if (key) h['Authorization'] = 'Bearer ' + key;
  const teamId = _config.currentTeamId();
  const projectId = _config.currentProjectId();
  if (teamId) h['X-Team-Id'] = teamId;
  if (projectId) h['X-Project-Id'] = projectId;
  return h;
}

/** 非审查 API headers（规范库、密钥管理等） */
export function getHeaders(): Record<string, string> {
  return getReviewHeaders();
}

/** Admin headers（密钥管理专用） */
export function getAdminHeaders(method = 'GET'): Record<string, string> {
  const h: Record<string, string> = {};
  if (_adminToken) h['Authorization'] = 'Bearer ' + _adminToken;
  if (method && method !== 'GET') h['Content-Type'] = 'application/json';
  return h;
}

function _errorInfo(r: Response, data: unknown): string {
  if (typeof data === 'object' && data !== null) {
    const d = data as Record<string, unknown>;
    if (d.detail) return String(d.detail);
    if (d.message) return String(d.message);
  }
  return JSON.stringify(data || `HTTP ${r.status}`);
}

async function _check(r: Response): Promise<unknown> {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error('API错误 (' + r.status + '): ' + _errorInfo(r, data));
  return data;
}

/** GET 请求 */
export async function apiGet(path: string): Promise<unknown> {
  return _check(await fetch(getApiBase() + path, {
    method: 'GET',
    headers: getHeaders(),
  }));
}

/** POST JSON 请求 */
export async function apiPostJSON(path: string, body: unknown): Promise<unknown> {
  return _check(await fetch(getApiBase() + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getHeaders() },
    body: JSON.stringify(body),
  }));
}

/** 通用 fetch + JSON */
export async function apiFetch(path: string, options: RequestInit = {}): Promise<unknown> {
  const r = await fetch(getApiBase() + path, {
    headers: { 'Content-Type': 'application/json', ...getHeaders(), ...options.headers },
    ...options,
  });
  return r.json();
}

/** 文件上传 POST */
export async function apiPostFile(
  path: string,
  file: File,
  extraParams: Record<string, string> = {},
): Promise<unknown> {
  const form = new FormData();
  form.append('file', file);
  const params = new URLSearchParams(extraParams);
  const url =
    getApiBase() + path + (params.toString() ? '?' + params.toString() : '');
  const r = await fetch(url, {
    method: 'POST',
    headers: getReviewHeaders(),
    body: form,
  });
  return _check(r);
}

/** Admin GET */
export async function adminGet(path: string): Promise<unknown> {
  return fetch(getApiBase() + path, {
    method: 'GET',
    headers: getAdminHeaders('GET'),
  }).then((r) => r.json());
}

/** Admin POST */
export async function adminPost(path: string, body: unknown): Promise<unknown> {
  return fetch(getApiBase() + path, {
    method: 'POST',
    headers: getAdminHeaders('POST'),
    body: JSON.stringify(body),
  }).then((r) => r.json());
}

/** Admin DELETE */
export async function adminDelete(path: string): Promise<unknown> {
  return fetch(getApiBase() + path, {
    method: 'DELETE',
    headers: getAdminHeaders('DELETE'),
  }).then((r) => r.json());
}

// ── 向后兼容：挂载到 window ────────────────────────────────
if (typeof window !== 'undefined') {
  // 兼容旧全局 API 函数名
  window.HEADERS = () => getReviewHeaders();
  window.getHeaders = () => getHeaders();
  window.API_BASE = () => getApiBase();
  window.apiGet = apiGet;
  window.apiPostJSON = apiPostJSON;
  window.apiPostFile = apiPostFile;
  window.apiFetch = apiFetch;
  window.adminGet = adminGet;
  window.adminPost = adminPost;
  window.adminDelete = adminDelete;
  window.adminHeaders = (m?: string) => getAdminHeaders(m);
  // 兼容旧 baa-core.js 的 apiPost（与 apiPostJSON 功能相同）
  window.apiPost = (path: string, body: unknown) => apiPostJSON(path, body);
}