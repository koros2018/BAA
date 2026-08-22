// ── P123 Phase 1: 共享类型定义 ──────────────────────────
// 后端 API 响应通用结构，供各模块引用

export interface ApiResponse<T = unknown> {
  status: 'success' | 'error';
  data?: T;
  detail?: ApiError;
  message?: string;
  token?: string;
  user?: UserProfile;
}

export interface ApiError {
  status: 'error';
  error_code?: string;
  message?: string;
}

export interface UserProfile {
  id: string;
  username: string;
  email?: string;
  display_name?: string;
  role?: string;
  token?: string;
}

export interface ApiKeyItem {
  id: string;
  name: string;
  key: string;
  created: number;
}

export interface BackendKeyInfo {
  key_id: string;
  label?: string;
  permission: string;
  enabled: boolean;
  expires_at?: number | null;
  created_at?: number;
  usage?: { total_calls?: number; last_used?: number };
  has_raw_key?: boolean;
  raw_key?: string;
  info?: { permission?: string; expires_at?: number };
}

export interface BackendKeyVerifyResult {
  status: 'success' | 'error';
  valid?: boolean;
  key_info?: { key_id?: string; label?: string };
  message?: string;
}

export interface ToastType {
  type: 'info' | 'success' | 'error' | 'warn';
  duration?: number;
}

export interface ReviewSummary {
  total_entities: number;
  entity_types: Record<string, number>;
  total_checks: number;
  violations: number;
  violation_by_clause: Record<string, number>;
  score: number;
  avg_confidence: number;
  confidence_tier_counts: Record<string, number>;
}

export interface ReviewResult {
  status: 'success' | 'error';
  summary: ReviewSummary;
  details: unknown[];
  task_id?: string;
}

export interface BatchReviewResult {
  status: 'success';
  batch_summary: {
    total_files: number;
    success_files: number;
    failed_files: number;
  };
  results: Array<{
    filename: string;
    status: string;
    summary?: ReviewSummary;
    details?: unknown[];
  }>;
}

export interface AuthResponse {
  status: 'success' | 'error';
  token?: string;
  user?: UserProfile;
  detail?: ApiError;
}

export interface AuditItem {
  id: string;
  review_id?: string;
  violation_id?: string;
  status: 'unreviewed' | 'confirmed' | 'dismissed' | 'pending';
  reviewer_id?: string;
  review_note?: string;
  created_at?: number;
  updated_at?: number;
}