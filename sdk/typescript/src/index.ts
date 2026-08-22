/**
 * Truss Kernel API client — typed, dependency-free (fetch-based).
 *
 * Usage:
 *   import { TrussClient } from "@truss/client";
 *   const truss = new TrussClient({ baseUrl: "http://localhost:8000" });
 *   await truss.auth.login({ email, password });
 *   const leads = await truss.records.list("lead");
 *
 * Or with an API key (programmatic access):
 *   const truss = new TrussClient({ baseUrl, apiKey: "truss_sk_..." });
 */

export interface TrussClientOptions {
  baseUrl: string;
  /** JWT access token (interactive) */
  token?: string;
  /** API key truss_sk_... (programmatic) */
  apiKey?: string;
}

export class TrussApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`Truss API ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
}

/* ---------- shared types ---------- */

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: string;
  tenant_id: string;
  tenant_name: string;
}

export interface FieldDef {
  slug: string;
  name: string;
  type: string;
  required: boolean;
  position: number;
  options: Record<string, unknown>;
}

export interface ObjectDef {
  id: string;
  slug: string;
  name: string;
  name_plural: string;
  description: string;
  icon: string;
  plugin_id: string | null;
  fields: FieldDef[];
}

export interface RecordRow {
  id: string;
  object_id: string;
  data: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface RecordList {
  items: RecordRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface HistoryEntry {
  version: number;
  data: Record<string, unknown>;
  changed_by: string | null;
  actor_type: string;
  created_at: string | null;
}

export interface TrashItem {
  id: string;
  object: string;
  data: Record<string, unknown>;
  deleted_at: string | null;
}

export interface AiKey {
  id: string;
  name: string;
  provider: string;
  model: string;
  is_default: boolean;
  created_at: string | null;
}

export interface ChatTraceItem {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface ChatResult {
  reply: string;
  trace: ChatTraceItem[];
  tokens_used?: number;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  icon: string;
  status: string;
  permission_role: string;
  budget_tokens: number;
  tokens_used: number;
  runs_count: number;
  reports_to_agent_id: string | null;
  reports_to_user_id: string | null;
}

export interface AgentTask {
  id: string;
  agent_id: string;
  title: string;
  description: string;
  status: string;
  needs_review: boolean;
  goal_id: string | null;
  delegated_by_agent_id: string | null;
  result: { reply?: string; trace?: ChatTraceItem[] };
  error: string | null;
}

export interface Goal {
  id: string;
  title: string;
  metric: string;
  target_value: number;
  current_value: number;
  unit: string;
  status: string;
  owner_agent_id: string | null;
  parent_goal_id: string | null;
}

export interface Schedule {
  id: string;
  agent_id: string;
  name: string;
  kind: "interval" | "cron";
  interval_minutes: number | null;
  cron: string | null;
  title: string;
  prompt: string;
  enabled: boolean;
  next_run_at: string | null;
}

export interface Trigger {
  id: string;
  agent_id: string;
  name: string;
  event_type: string;
  object: string | null;
  title: string;
  prompt: string;
  enabled: boolean;
}

export interface Pipeline {
  id: string;
  name: string;
  steps: { agent_id: string; prompt: string }[];
  paused: boolean;
}

export interface AnalyticsResult {
  object: string;
  metric: string;
  field?: string;
  value?: number;
  rows?: { key?: string; value?: number; bucket?: string; count?: number }[];
  summary?: { count: number; sum: number; avg: number; min: number; max: number };
}

export interface AgentScorecard {
  agent_id: string;
  name: string;
  role: string;
  icon: string;
  status: string;
  tasks: { total: number; done: number; failed: number; rejected: number; pending: number };
  completion_rate: number | null;
  tokens: { total_used: number; budget: number; utilization: number | null };
}

export interface TimelineItem {
  kind: "event" | "task";
  id: string;
  type: string;
  title: string;
  detail: string;
  actor_type: string;
  at: string;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  key?: string; // only present on creation
}

export interface PublishResult {
  ok: boolean;
  plugin_id: string;
  version: string;
  installed: boolean;
  objects: number;
  tools: number;
}

/* ---------- client ---------- */

export class TrussClient {
  private baseUrl: string;
  private token: string | null;
  private apiKey: string | null;

  constructor(opts: TrussClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, "");
    this.token = opts.token ?? null;
    this.apiKey = opts.apiKey ?? null;
  }

  setToken(token: string) {
    this.token = token;
  }

  private async req<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const cred = this.apiKey ?? this.token;
    if (cred) headers["Authorization"] = `Bearer ${cred}`;
    const res = await fetch(this.baseUrl + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) throw new TrussApiError(res.status, data.detail ?? data);
    return data as T;
  }

  auth = {
    signup: (body: { email: string; password: string; full_name: string; tenant_name: string; tenant_slug: string }) =>
      this.req<AuthTokens & { user: Me }>("POST", "/api/auth/signup", body),
    login: (body: { email: string; password: string }) =>
      this.req<AuthTokens>("POST", "/api/auth/login", body),
    me: () => this.req<Me>("GET", "/api/auth/me"),
  };

  objects = {
    list: () => this.req<ObjectDef[]>("GET", "/api/objects"),
    get: (slug: string) => this.req<ObjectDef>("GET", `/api/objects/${slug}`),
  };

  records = {
    list: (object: string, params?: { search?: string; limit?: number; offset?: number }) => {
      const q = new URLSearchParams();
      if (params?.search) q.set("search", params.search);
      if (params?.limit) q.set("limit", String(params.limit));
      if (params?.offset) q.set("offset", String(params.offset));
      const qs = q.toString();
      return this.req<RecordList>("GET", `/api/records/${object}${qs ? "?" + qs : ""}`);
    },
    create: (object: string, data: Record<string, unknown>) =>
      this.req<RecordRow>("POST", `/api/records/${object}`, { data }),
    get: (object: string, id: string) => this.req<RecordRow>("GET", `/api/records/${object}/${id}`),
    update: (object: string, id: string, data: Record<string, unknown>) =>
      this.req<RecordRow>("PATCH", `/api/records/${object}/${id}`, { data }),
    delete: (object: string, id: string) => this.req<{ ok: boolean }>("DELETE", `/api/records/${object}/${id}`),
    history: (object: string, id: string) =>
      this.req<HistoryEntry[]>("GET", `/api/records/${object}/${id}/history`),
    trash: () => this.req<TrashItem[]>("GET", "/api/records/trash"),
    restore: (id: string) => this.req<RecordRow>("POST", `/api/records/trash/${id}/restore`),
  };

  ai = {
    addKey: (body: { name: string; provider: string; base_url?: string; model: string; api_key: string; is_default?: boolean }) =>
      this.req<AiKey>("POST", "/api/ai/keys", body),
    listKeys: () => this.req<AiKey[]>("GET", "/api/ai/keys"),
    chat: (message: string) => this.req<ChatResult>("POST", "/api/ai/chat", { message }),
  };

  agents = {
    list: () => this.req<Agent[]>("GET", "/api/agents"),
    hire: (body: { name: string; role?: string; icon?: string; ai_key_id?: string; permission_role?: string }) =>
      this.req<Agent>("POST", "/api/agents", body),
    assignTask: (agentId: string, body: { title: string; description?: string; needs_review?: boolean; goal_id?: string }) =>
      this.req<AgentTask>("POST", `/api/agents/${agentId}/tasks`, { agent_id: agentId, ...body }),
    runTask: (agentId: string, taskId: string) =>
      this.req<AgentTask>("POST", `/api/agents/${agentId}/tasks/${taskId}/run`),
    approveTask: (agentId: string, taskId: string) =>
      this.req<AgentTask>("POST", `/api/agents/${agentId}/tasks/${taskId}/approve`),
  };

  goals = {
    list: () => this.req<Goal[]>("GET", "/api/org/goals"),
    create: (body: { title: string; metric?: string; target_value?: number; owner_agent_id?: string }) =>
      this.req<Goal>("POST", "/api/org/goals", body),
  };

  orchestration = {
    listSchedules: () => this.req<Schedule[]>("GET", "/api/orchestration/schedules"),
    createSchedule: (body: { agent_id: string; name: string; kind: "interval" | "cron"; interval_minutes?: number; cron?: string; title: string; prompt: string }) =>
      this.req<Schedule>("POST", "/api/orchestration/schedules", body),
    listTriggers: () => this.req<Trigger[]>("GET", "/api/orchestration/triggers"),
    createTrigger: (body: { agent_id: string; name: string; event_type: string; object?: string; title: string; prompt: string }) =>
      this.req<Trigger>("POST", "/api/orchestration/triggers", body),
    listPipelines: () => this.req<Pipeline[]>("GET", "/api/orchestration/pipelines"),
    runPipeline: (id: string) => this.req<{ ok: boolean; steps: unknown[]; final_reply?: string }>("POST", `/api/orchestration/pipelines/${id}/run`),
  };

  insights = {
    query: (body: { object: string; metric: string; field?: string; value_field?: string; bucket?: string; days?: number }) =>
      this.req<AnalyticsResult>("POST", "/api/insights/query", body),
    scorecards: () => this.req<AgentScorecard[]>("GET", "/api/insights/agents"),
    timeline: (limit = 50) => this.req<TimelineItem[]>("GET", `/api/insights/timeline?limit=${limit}`),
  };

  keys = {
    create: (body: { name: string; scopes?: string[] }) => this.req<ApiKeyInfo>("POST", "/api/keys", body),
    list: () => this.req<ApiKeyInfo[]>("GET", "/api/keys"),
    revoke: (id: string) => this.req<{ ok: boolean }>("POST", `/api/keys/${id}/revoke`),
  };

  marketplace = {
    validate: (manifest: Record<string, unknown>) =>
      this.req<{ ok: boolean; errors?: string[] }>("POST", "/api/marketplace/validate", manifest),
    publish: (manifest: Record<string, unknown>, install = true) =>
      this.req<PublishResult>("POST", "/api/marketplace/publish", { manifest, install }),
  };

  dev = {
    openapi: () => this.req<Record<string, unknown>>("GET", "/api/dev/openapi.json"),
    reference: async () => {
      const cred = this.apiKey ?? this.token;
      const res = await fetch(this.baseUrl + "/api/dev/reference", {
        headers: cred ? { Authorization: `Bearer ${cred}` } : {},
      });
      return res.text();
    },
  };
}

export default TrussClient;
