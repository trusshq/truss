/* Truss kernel API client (browser). Token kept in localStorage. */

export const API_BASE = process.env.NEXT_PUBLIC_TRUSS_API ?? "http://127.0.0.1:8000";

const TOKEN_KEY = "***";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean } = {}
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (opts.auth !== false && token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API_BASE + path, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }

  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

/* ---------- types ---------- */

export interface FieldDef {
  id: string;
  slug: string;
  name: string;
  type: string;
  required: boolean;
  position: number;
  options: { choices?: string[]; related_object?: string };
}

export interface ObjectDef {
  id: string;
  slug: string;
  name: string;
  name_plural: string;
  description: string;
  icon: string;
  plugin_id: string;
  is_builtin: boolean;
  fields: FieldDef[];
}

export interface RecordRow {
  id: string;
  object_id: string;
  data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  icon: string;
  permissions: string[];
  objects: { slug: string; name: string }[];
  tools: { slug: string; name: string; description: string }[];
  automations: { slug: string; name: string }[];
  ui: { slug: string; label: string; icon: string; view: string; object?: string; config?: { group_by?: string } }[];
  installed: boolean;
  enabled: boolean;
  settings: Record<string, unknown>;
}

export interface Me {
  user_id: string;
  email: string;
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
}

/** Silent auth check: returns the session's Me, or null (clears stale tokens). */
export async function checkAuth(): Promise<Me | null> {
  if (!getToken()) return null;
  try {
    return await api<Me>("/api/auth/me");
  } catch (e) {
    if ((e as { status?: number }).status === 401) setToken(null);
    return null;
  }
}

export interface AuthResponse {
  access_token: string;
  tenant_id: string;
  tenant_slug: string;
  role: string;
  user_id: string;
  email: string;
}

export interface AiKeyInfo {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  model: string;
  api_key_masked: string | null;
  is_default: boolean;
  created_at: string;
}

export interface ChatTraceItem {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface ChatResult {
  reply: string;
  trace: ChatTraceItem[];
  steps: number;
  model: string;
}

export interface MarketplacePlugin {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  icon: string;
  category: string;
  downloads: number;
  rating: number;
  objects: string[];
  permissions: string[];
  installed: boolean;
  enabled: boolean;
}

export interface MarketplaceTemplate {
  id: string;
  name: string;
  icon: string;
  description: string;
  plugins: string[];
  record_count: number;
}
