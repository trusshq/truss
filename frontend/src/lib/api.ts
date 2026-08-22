/* Truss kernel API client (browser). Token kept in localStorage.
 *
 * API base resolution:
 *  - NEXT_PUBLIC_TRUSS_API unset  -> http://127.0.0.1:8000 (Vercel demo / local dev:
 *    the browser talks to a kernel you run on your own machine)
 *  - NEXT_PUBLIC_TRUSS_API=""     -> same-origin /api/* (Docker self-host: Next
 *    rewrites /api/* to the kernel service, so no CORS and no hardcoded host)
 */

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
  full_name?: string;
  title?: string;
  phone?: string;
  avatar_url?: string;
  timezone?: string;
  locale?: string;
  last_login_at?: string | null;
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

/* ---------- workspace / members / invites ---------- */

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string;
  website: string;
  industry: string;
  company_size: string;
  logo_url: string;
  timezone: string;
  locale: string;
  settings: Record<string, unknown>;
  created_at: string | null;
}

export interface MemberUser {
  id: string;
  email: string;
  full_name: string;
  title: string;
  phone: string;
  avatar_url: string;
  timezone: string;
  locale: string;
  last_login_at: string | null;
  created_at: string | null;
}

export interface Member {
  membership_id: string;
  role: string;
  joined_at: string | null;
  user: MemberUser;
}

export interface Invite {
  id: string;
  email: string;
  role: string;
  token: string;
  status: "pending" | "accepted" | "revoked" | "expired";
  expires_at: string;
  accepted_at: string | null;
  created_at: string | null;
}

export interface RoleInfo {
  role: string;
  label: string;
  description: string;
  capabilities: Record<string, boolean>;
}

export interface InvitePublic {
  email: string;
  role: string;
  workspace_name: string;
  workspace_slug: string;
  expires_at: string;
}

/* ---------- AI employees (agents) ---------- */

export interface TrashItem {
  id: string;
  object: string;
  data: Record<string, unknown>;
  deleted_at: string | null;
  created_at: string | null;
}

export interface HistoryEntry {
  version: number;
  data: Record<string, unknown>;
  changed_by: string | null;
  actor_type: string;
  created_at: string | null;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
  key?: string; // plaintext, only on creation
}

/* ---------- Phase B: org chart / goals / notifications ---------- */

export interface OrgNode {
  id: string;
  kind: string;
  name: string;
  role: string;
  icon: string;
  status: string;
  reports_to_agent: string | null;
  reports_to_user: string | null;
  manager_name?: string;
  children: OrgNode[];
}

export interface GoalInfo {
  id: string;
  title: string;
  description: string;
  metric: string;
  target_value: number;
  current_value: number;
  unit: string;
  progress: number;
  status: string;
  owner_agent_id: string | null;
  owner_user_id: string | null;
  parent_goal_id: string | null;
  due_at: string;
  created_at: string | null;
}

export interface NotificationInfo {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  actor_id: string | null;
  actor_type: string;
  read: boolean;
  created_at: string | null;
}

export interface BudgetRow {
  agent_id: string;
  name: string;
  icon: string;
  status: string;
  tokens_used: number;
  budget_tokens: number;
  utilization: number | null;
  runs_count: number;
  over_budget: boolean;
}

export interface BudgetLedger {
  agents: BudgetRow[];
  total_tokens_used: number;
  total_budget: number;
  uncapped_agents: number;
}

export interface ReviewInbox {
  pending_tasks: (AgentTaskInfo & { agent_name: string })[];
  count: number;
}

export interface TaskCommentInfo {
  id: string;
  task_id: string;
  body: string;
  author_id: string | null;
  author_type: string;
  mentions: string[];
  created_at: string | null;
}

/* ---------- Phase C: autonomous orchestration ---------- */

export interface ScheduleInfo {
  id: string;
  agent_id: string;
  name: string;
  title: string;
  prompt: string;
  kind: "interval" | "cron";
  every_minutes: number;
  cron: string;
  enabled: boolean;
  needs_review: boolean;
  last_run_at: string;
  next_run_at: string;
  runs_count: number;
  last_status: string;
  last_error: string;
  created_at: string | null;
}

export interface TriggerInfo {
  id: string;
  agent_id: string;
  name: string;
  event_type: string;
  object_slug: string;
  title: string;
  prompt: string;
  enabled: boolean;
  needs_review: boolean;
  cooldown_seconds: number;
  last_fired_at: string;
  fires_count: number;
  created_at: string | null;
}

export interface PipelineStepInfo {
  agent_id: string;
  title: string;
  prompt: string;
}

export interface PipelineInfo {
  id: string;
  name: string;
  description: string;
  status: "active" | "paused";
  steps: PipelineStepInfo[];
  runs_count: number;
  last_run_at: string;
  last_status: string;
  created_at: string | null;
}

export interface PipelineRunStep {
  step: number;
  agent_id: string;
  agent: string;
  task_id: string;
  ok: boolean;
  reply: string;
  error: string;
}

export interface PipelineRunResult {
  ok: boolean;
  steps: PipelineRunStep[];
  final_reply?: string;
  error?: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  persona: string;
  icon: string;
  status: "active" | "paused" | "terminated";
  ai_key_id: string | null;
  model_override: string;
  permission_role: string;
  allowed_plugins: string[];
  budget_tokens: number;
  tokens_used: number;
  runs_count: number;
  reports_to_agent_id: string | null;
  reports_to_user_id: string | null;
  settings: Record<string, unknown>;
  created_at: string | null;
}

export interface AgentTaskInfo {
  id: string;
  agent_id: string;
  title: string;
  description: string;
  status: "proposed" | "approved" | "running" | "done" | "failed" | "rejected";
  needs_review: boolean;
  priority: number;
  created_by: string | null;
  approved_by: string | null;
  goal_id: string | null;
  delegated_by_agent_id: string | null;
  result: { reply?: string; trace?: ChatTraceItem[] };
  error: string;
  steps: number;
  tokens_used: number;
  started_at: string;
  finished_at: string;
  created_at: string | null;
}

export interface AgentRunResult {
  task: AgentTaskInfo;
  run: { ok: boolean; reply?: string; trace?: ChatTraceItem[]; steps?: number; tokens?: number; error?: string };
}
