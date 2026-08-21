"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bot,
  Cable,
  Check,
  Cog,
  LayoutGrid,
  LogOut,
  Monitor,
  Moon,
  Palette,
  Plug,
  Puzzle,
  RotateCcw,
  Sun,
  Zap,
} from "lucide-react";
import {
  api,
  getToken,
  setToken,
  type AiKeyInfo,
  type ChatResult,
  type Me,
  type ObjectDef,
  type PluginInfo,
  type RecordRow,
} from "@/lib/api";
import { ACCENT_PRESETS, useTheme, type Density, type Radius, type ThemeMode } from "@/lib/theme";

type View =
  | { kind: "object"; slug: string }
  | { kind: "plugins" }
  | { kind: "events" }
  | { kind: "ai" }
  | { kind: "automations" }
  | { kind: "connectors" }
  | { kind: "settings" };

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [objects, setObjects] = useState<ObjectDef[]>([]);
  const [view, setView] = useState<View>({ kind: "plugins" });
  const [bootError, setBootError] = useState("");

  const refresh = useCallback(async () => {
    const [p, o] = await Promise.all([
      api<PluginInfo[]>("/api/plugins/catalog"),
      api<ObjectDef[]>("/api/objects"),
    ]);
    setPlugins(p);
    setObjects(o);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        setMe(await api<Me>("/api/auth/me"));
        await refresh();
      } catch (e) {
        if ((e as { status?: number }).status === 401) {
          setToken(null);
          router.replace("/login");
        } else {
          setBootError(String((e as Error).message ?? e));
        }
      }
    })();
  }, [router, refresh]);

  // UI surfaces from enabled plugins
  const surfaces = useMemo(() => {
    const out: { label: string; icon: string; object?: string; slug: string }[] = [];
    for (const p of plugins.filter((p) => p.installed && p.enabled)) {
      for (const s of p.ui) {
        if (s.view === "table" && s.object) {
          out.push({ label: s.label, icon: s.icon, object: s.object, slug: s.slug });
        }
      }
    }
    return out;
  }, [plugins]);

  if (bootError) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="max-w-md rounded-xl border border-danger/40 bg-card p-6 text-sm">
          <p className="font-semibold text-danger">Cannot reach the Truss kernel</p>
          <p className="mt-2 text-muted">{bootError}</p>
          <p className="mt-2 text-muted">
            Start it with: <code className="font-mono text-foreground">cd kernel && uv run uvicorn truss_kernel.main:app --port 8000</code>
          </p>
        </div>
      </main>
    );
  }

  if (!me) {
    return (
      <main className="flex min-h-screen items-center justify-center text-muted">Loading…</main>
    );
  }

  return (
    <main className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-card/50">
        <div className="flex items-center gap-2 border-b border-border px-4 py-4">
          <span className="text-xl">🏗️</span>
          <div>
            <div className="text-sm font-bold leading-tight">Truss</div>
            <div className="text-[11px] text-muted">{me.tenant_name}</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-muted">Apps</div>
          {surfaces.length === 0 && (
            <div className="px-2 py-1 text-xs text-muted">Install a plugin to see its apps →</div>
          )}
          {surfaces.map((s) => (
            <button
              key={s.slug}
              onClick={() => setView({ kind: "object", slug: s.object! })}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
                view.kind === "object" && view.slug === s.object
                  ? "bg-accent-soft text-accent"
                  : "hover:bg-card"
              }`}
            >
              <span>{s.icon}</span> {s.label}
            </button>
          ))}

          <div className="px-2 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-wider text-muted">Platform</div>
          <button
            onClick={() => setView({ kind: "plugins" })}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
              view.kind === "plugins" ? "bg-accent-soft text-accent" : "hover:bg-card"
            }`}
          >
            <Puzzle size={15} /> Plugins
          </button>
          <button
            onClick={() => setView({ kind: "ai" })}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
              view.kind === "ai" ? "bg-accent-soft text-accent" : "hover:bg-card"
            }`}
          >
            <Bot size={15} /> AI Agent
          </button>
          <button
            onClick={() => setView({ kind: "automations" })}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
              view.kind === "automations" ? "bg-accent-soft text-accent" : "hover:bg-card"
            }`}
          >
            <Cog size={15} /> Automations
          </button>
          <button
            onClick={() => setView({ kind: "connectors" })}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
              view.kind === "connectors" ? "bg-accent-soft text-accent" : "hover:bg-card"
            }`}
          >
            <Cable size={15} /> Connectors
          </button>
          <button
            onClick={() => setView({ kind: "events" })}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
              view.kind === "events" ? "bg-accent-soft text-accent" : "hover:bg-card"
            }`}
          >
            <Zap size={15} /> Events
          </button>
          <button
            onClick={() => setView({ kind: "settings" })}
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
              view.kind === "settings" ? "bg-accent-soft text-accent" : "hover:bg-card"
            }`}
          >
            <Palette size={15} /> Appearance
          </button>
        </nav>

        <div className="border-t border-border p-3 text-xs">
          <div className="truncate text-muted">{me.email}</div>
          <button
            onClick={() => {
              setToken(null);
              router.replace("/login");
            }}
            className="mt-1 flex items-center gap-1 text-muted underline-offset-2 hover:text-danger hover:underline"
          >
            <LogOut size={12} /> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <section className="min-w-0 flex-1 overflow-y-auto p-6">
        {view.kind === "plugins" && <PluginsView plugins={plugins} onChanged={refresh} />}
        {view.kind === "events" && <EventsView />}
        {view.kind === "ai" && <AiView onChanged={refresh} />}
        {view.kind === "automations" && <AutomationsView />}
        {view.kind === "connectors" && <ConnectorsView />}
        {view.kind === "settings" && <SettingsView />}
        {view.kind === "object" && (
          <ObjectView
            object={objects.find((o) => o.slug === view.slug) ?? null}
            onChanged={refresh}
          />
        )}
      </section>
    </main>
  );
}

/* ---------------- Plugins ---------------- */

function PluginsView({ plugins, onChanged }: { plugins: PluginInfo[]; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState("");

  async function act(pluginId: string, action: "install" | "enable" | "disable") {
    setBusy(pluginId + action);
    try {
      await api(`/api/plugins/${action}`, { method: "POST", body: { plugin_id: pluginId } });
      await onChanged();
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      <h1 className="text-xl font-bold">🧩 Plugins</h1>
      <p className="mt-1 text-sm text-muted">
        Everything in Truss is a plugin. Install, enable, disable — full control, no lock-in.
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {plugins.map((p) => (
          <div key={p.id} className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{p.icon}</span>
                <div>
                  <div className="font-semibold">
                    {p.name} <span className="ml-1 text-xs text-muted">v{p.version}</span>
                  </div>
                  <div className="text-xs text-muted">by {p.author || "unknown"}</div>
                </div>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  !p.installed
                    ? "bg-border text-muted"
                    : p.enabled
                      ? "bg-success/15 text-success"
                      : "bg-danger/15 text-danger"
                }`}
              >
                {!p.installed ? "not installed" : p.enabled ? "enabled" : "disabled"}
              </span>
            </div>

            <p className="mt-3 text-sm text-muted">{p.description}</p>

            <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
              {p.objects.map((o) => (
                <span key={o.slug} className="rounded-md bg-accent-soft px-2 py-0.5 text-accent">
                  {o.name}
                </span>
              ))}
              {p.tools.map((t) => (
                <span key={t.slug} className="rounded-md border border-border px-2 py-0.5 text-muted" title={t.description}>
                  🤖 {t.name}
                </span>
              ))}
            </div>

            {p.permissions.length > 0 && (
              <div className="mt-2 text-[11px] text-muted">
                permissions: <span className="font-mono">{p.permissions.join(", ")}</span>
              </div>
            )}

            <div className="mt-4 flex gap-2">
              {!p.installed && (
                <button
                  disabled={busy !== ""}
                  onClick={() => act(p.id, "install")}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
                >
                  {busy === p.id + "install" ? "…" : "Install"}
                </button>
              )}
              {p.installed && p.enabled && (
                <button
                  disabled={busy !== ""}
                  onClick={() => act(p.id, "disable")}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold hover:bg-card disabled:opacity-50"
                >
                  {busy === p.id + "disable" ? "…" : "Disable"}
                </button>
              )}
              {p.installed && !p.enabled && (
                <button
                  disabled={busy !== ""}
                  onClick={() => act(p.id, "enable")}
                  className="rounded-lg bg-success/20 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/30 disabled:opacity-50"
                >
                  {busy === p.id + "enable" ? "…" : "Enable"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- Object (generic table + create form) ---------------- */

function ObjectView({ object, onChanged }: { object: ObjectDef | null; onChanged: () => Promise<void> }) {
  const [rows, setRows] = useState<RecordRow[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!object) return;
    const qs = search ? `?search=${encodeURIComponent(search)}` : "";
    const res = await api<{ items: RecordRow[]; total: number }>(`/api/records/${object.slug}${qs}`);
    setRows(res.items);
    setTotal(res.total);
  }, [object, search]);

  useEffect(() => {
    setForm({});
    setError("");
    load().catch(() => {});
  }, [load]);

  if (!object) return <div className="text-muted">Object not found.</div>;

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!object) return;
    setBusy(true);
    setError("");
    try {
      const data: Record<string, unknown> = {};
      for (const f of object.fields) {
        const v = form[f.slug];
        if (v === undefined || v === "") continue;
        data[f.slug] = f.type === "number" || f.type === "currency" ? Number(v) : v;
      }
      await api(`/api/records/${object.slug}`, { method: "POST", body: { data } });
      setShowForm(false);
      setForm({});
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!object) return;
    await api(`/api/records/${object.slug}/${id}`, { method: "DELETE" });
    await load();
    await onChanged();
  }

  const input =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent";

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">
            {object.icon} {object.name_plural}
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            {object.description || "Records"} · {total} total
          </p>
        </div>
        <div className="flex gap-2">
          <input
            className={input + " w-48"}
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            {showForm ? "Close" : `+ New ${object.name}`}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={create} className="mt-4 grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-2">
          {object.fields.map((f) => (
            <label key={f.slug} className="block text-xs">
              <span className="mb-1 block text-muted">
                {f.name} {f.required && <span className="text-danger">*</span>}
              </span>
              {f.type === "select" ? (
                <select
                  className={input}
                  value={form[f.slug] ?? ""}
                  onChange={(e) => setForm({ ...form, [f.slug]: e.target.value })}
                  required={f.required}
                >
                  <option value="">—</option>
                  {(f.options.choices ?? []).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              ) : f.type === "textarea" ? (
                <textarea
                  className={input}
                  rows={2}
                  value={form[f.slug] ?? ""}
                  onChange={(e) => setForm({ ...form, [f.slug]: e.target.value })}
                  required={f.required}
                />
              ) : (
                <input
                  className={input}
                  type={f.type === "number" || f.type === "currency" ? "number" : f.type === "date" ? "date" : "text"}
                  value={form[f.slug] ?? ""}
                  onChange={(e) => setForm({ ...form, [f.slug]: e.target.value })}
                  required={f.required}
                />
              )}
            </label>
          ))}
          {error && <div className="text-xs text-danger md:col-span-2">{error}</div>}
          <div className="md:col-span-2">
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : "Create"}
            </button>
          </div>
        </form>
      )}

      <div className="mt-4 overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-card text-left text-xs uppercase tracking-wide text-muted">
              {object.fields.map((f) => (
                <th key={f.slug} className="px-3 py-2 font-medium">{f.name}</th>
              ))}
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border/50 last:border-0 hover:bg-card/50">
                {object.fields.map((f) => (
                  <td key={f.slug} className="max-w-[220px] truncate px-3 py-2">
                    {renderCell(r.data[f.slug], f.type)}
                  </td>
                ))}
                <td className="px-3 py-2 text-right">
                  <button onClick={() => remove(r.id)} className="text-xs text-muted hover:text-danger">
                    delete
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={object.fields.length + 1} className="px-3 py-8 text-center text-muted">
                  No {object.name_plural.toLowerCase()} yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderCell(v: unknown, type: string) {
  if (v === null || v === undefined || v === "") return <span className="text-muted">—</span>;
  if (type === "currency") return <span className="font-mono">${Number(v).toLocaleString()}</span>;
  if (type === "select")
    return <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs text-accent">{String(v)}</span>;
  return String(v);
}

/* ---------------- AI (BYOK keys + agent chat) ---------------- */

function AiView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [keys, setKeys] = useState<AiKeyInfo[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", base_url: "", model: "", api_key: "", is_default: true });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // chat state
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string; trace?: ChatResult["trace"] }[]>([]);
  const [input, setInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState("");

  const loadKeys = useCallback(async () => {
    setKeys(await api<AiKeyInfo[]>("/api/ai/keys"));
  }, []);

  useEffect(() => {
    loadKeys().catch(() => {});
  }, [loadKeys]);

  async function addKey(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/ai/keys", { method: "POST", body: form });
      setShowAdd(false);
      setForm({ name: "", base_url: "", model: "", api_key: "", is_default: true });
      await loadKeys();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  }

  async function removeKey(id: string) {
    await api(`/api/ai/keys/${id}`, { method: "DELETE" });
    await loadKeys();
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || chatBusy) return;
    const userMsg = input.trim();
    setInput("");
    setChatError("");
    setMessages((m) => [...m, { role: "user", content: userMsg }]);
    setChatBusy(true);
    try {
      const history = messages.slice(-10).map((m) => ({ role: m.role, content: m.content }));
      const res = await api<ChatResult>("/api/ai/chat", {
        method: "POST",
        body: { message: userMsg, history },
      });
      setMessages((m) => [...m, { role: "assistant", content: res.reply, trace: res.trace }]);
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setChatError(typeof d === "string" ? d : JSON.stringify(d));
      setMessages((m) => m.slice(0, -1)); // drop the user msg on failure
    } finally {
      setChatBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Keys manager */}
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">🔑 AI Keys</h1>
          <button
            onClick={() => setShowAdd((v) => !v)}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            {showAdd ? "Close" : "+ Add key"}
          </button>
        </div>
        <p className="mt-1 text-sm text-muted">
          Bring your own model. Any OpenAI-compatible endpoint works — DeepSeek, OpenRouter,
          Groq, Together, Ollama, vLLM, OpenAI. Keys are encrypted at rest and never shown again.
        </p>

        {showAdd && (
          <form onSubmit={addKey} className="mt-4 space-y-3 rounded-xl border border-border bg-card p-4">
            <input className={inputCls} placeholder="Name (e.g. deepseek)" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <input className={inputCls} placeholder="Base URL (e.g. https://api.deepseek.com/v1)" value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })} required />
            <input className={inputCls} placeholder="Model (e.g. deepseek-chat)" value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })} required />
            <input className={inputCls} type="password" placeholder="API key" value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              Default key
            </label>
            {error && <div className="text-xs text-danger">{error}</div>}
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : "Save key"}
            </button>
          </form>
        )}

        <div className="mt-4 space-y-2">
          {keys.map((k) => (
            <div key={k.id} className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {k.name}
                  {k.is_default && <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] text-success">default</span>}
                </div>
                <div className="truncate text-xs text-muted">
                  {k.model} · {k.base_url}
                  {k.api_key_masked && <span className="ml-2 font-mono">{k.api_key_masked}</span>}
                </div>
              </div>
              <button onClick={() => removeKey(k.id)} className="ml-3 text-xs text-muted hover:text-danger">
                delete
              </button>
            </div>
          ))}
          {keys.length === 0 && !showAdd && (
            <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
              No AI keys yet. Add one to unlock the agent.
            </div>
          )}
        </div>
      </div>

      {/* Agent chat */}
      <div className="flex flex-col">
        <h1 className="text-xl font-bold">🤖 Agent</h1>
        <p className="mt-1 text-sm text-muted">
          Talks to your enabled plugins&apos; tools under your permissions. Try:
          &ldquo;create a lead named Sam from Referral&rdquo; or &ldquo;search contacts for Jane&rdquo;.
        </p>

        <div className="mt-4 flex min-h-[320px] flex-1 flex-col rounded-xl border border-border bg-card">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                    m.role === "user" ? "bg-accent text-on-accent" : "bg-background border border-border"
                  }`}
                >
                  <div className="whitespace-pre-wrap">{m.content}</div>
                  {m.trace && m.trace.length > 0 && (
                    <div className="mt-2 space-y-1 border-t border-border pt-2">
                      {m.trace.map((t, j) => (
                        <div key={j} className="text-[11px] text-muted">
                          <span className="font-mono text-accent">🔧 {t.tool}</span>{" "}
                          {t.result.error ? (
                            <span className="text-danger">→ {String(t.result.error)}</span>
                          ) : (
                            <span className="text-success">→ ok</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {chatBusy && <div className="text-xs text-muted">Agent thinking…</div>}
            {chatError && <div className="text-xs text-danger">{chatError}</div>}
            {messages.length === 0 && !chatBusy && (
              <div className="pt-8 text-center text-sm text-muted">Ask the agent to work with your data.</div>
            )}
          </div>

          <form onSubmit={send} className="flex gap-2 border-t border-border p-3">
            <input
              className={inputCls}
              placeholder={keys.length === 0 ? "Add an AI key first…" : "Ask the agent…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={keys.length === 0 || chatBusy}
            />
            <button
              disabled={keys.length === 0 || chatBusy || !input.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Connectors ---------------- */

interface ConnectorType {
  type: string;
  label: string;
  required: string[];
  optional: string[];
  implemented: boolean;
  help: string;
}

interface ConnectorRow {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  description: string;
  config: Record<string, unknown>;
  implemented: boolean;
  created_at: string;
}

interface DeliveryRow {
  id: string;
  event_type: string;
  status: string;
  attempts: number;
  last_http_status: number | null;
  last_error: string;
  created_at: string;
}

const TYPE_ICONS: Record<string, string> = { webhook: "📡", postgres: "🐘", s3: "🪣", smtp: "📧" };

function ConnectorsView() {
  const [types, setTypes] = useState<ConnectorType[]>([]);
  const [connectors, setConnectors] = useState<ConnectorRow[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", type: "webhook", config: {} as Record<string, string>, description: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, string>>({});
  const [queryConn, setQueryConn] = useState<string | null>(null);
  const [querySql, setQuerySql] = useState("SELECT 1");
  const [queryResult, setQueryResult] = useState<{ columns: string[]; rows: Record<string, unknown>[] } | null>(null);
  const [queryError, setQueryError] = useState("");
  const [deliveries, setDeliveries] = useState<Record<string, DeliveryRow[]>>({});

  const load = useCallback(async () => {
    setTypes(await api<ConnectorType[]>("/api/connectors/types").catch(() => []));
    setConnectors(await api<ConnectorRow[]>("/api/connectors").catch(() => []));
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const selectedType = types.find((t) => t.type === form.type);

  async function addConnector(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/connectors", {
        method: "POST",
        body: { name: form.name, type: form.type, config: form.config, description: form.description },
      });
      setShowAdd(false);
      setForm({ name: "", type: "webhook", config: {}, description: "" });
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  }

  async function testConnector(id: string) {
    setTestResult((r) => ({ ...r, [id]: "…" }));
    try {
      const res = await api<{ ok: boolean; version?: string; error?: string; note?: string }>(
        `/api/connectors/${id}/test`,
        { method: "POST" }
      );
      setTestResult((r) => ({ ...r, [id]: res.ok ? `✓ ${res.version ? res.version.slice(0, 40) : res.note || "ok"}` : `✗ ${res.error}` }));
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setTestResult((r) => ({ ...r, [id]: `✗ ${typeof d === "string" ? d : JSON.stringify(d)}` }));
    }
  }

  async function removeConnector(id: string) {
    await api(`/api/connectors/${id}`, { method: "DELETE" });
    await load();
  }

  async function runQuery(id: string) {
    setQueryError("");
    setQueryResult(null);
    try {
      const res = await api<{ ok: boolean; columns?: string[]; rows?: Record<string, unknown>[]; error?: string }>(
        `/api/connectors/${id}/query`,
        { method: "POST", body: { sql: querySql, limit: 50 } }
      );
      if (res.ok) {
        setQueryResult({ columns: res.columns || [], rows: res.rows || [] });
      } else {
        setQueryError(res.error || "query failed");
      }
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setQueryError(typeof d === "string" ? d : JSON.stringify(d));
    }
  }

  async function loadDeliveries(id: string) {
    const rows = await api<DeliveryRow[]>(`/api/connectors/${id}/deliveries`).catch(() => []);
    setDeliveries((d) => ({ ...d, [id]: rows }));
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent";

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">🔌 Connectors</h1>
        <button
          onClick={() => setShowAdd((v) => !v)}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
        >
          {showAdd ? "Close" : "+ Add connector"}
        </button>
      </div>
      <p className="mt-1 text-sm text-muted">
        Bring your own infrastructure. Forward events to your analytics (BYO-PostHog!),
        query external Postgres/Neon databases read-only, and more. Configs are encrypted at rest.
      </p>

      {showAdd && (
        <form onSubmit={addConnector} className="mt-4 space-y-3 rounded-xl border border-border bg-card p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <input className={inputCls} placeholder="Name (e.g. posthog-sink)" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <select className={inputCls} value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value, config: {} })}>
              {types.map((t) => (
                <option key={t.type} value={t.type} disabled={!t.implemented}>
                  {TYPE_ICONS[t.type]} {t.label}{!t.implemented ? " (coming soon)" : ""}
                </option>
              ))}
            </select>
          </div>
          {selectedType && (
            <>
              <p className="text-xs text-muted">{selectedType.help}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {[...selectedType.required, ...selectedType.optional].map((field) => (
                  <input
                    key={field}
                    className={inputCls}
                    type={["password", "secret", "secret_access_key", "access_key_id"].includes(field) ? "password" : "text"}
                    placeholder={`${field}${selectedType.required.includes(field) ? " *" : ""}`}
                    value={form.config[field] || ""}
                    onChange={(e) => setForm({ ...form, config: { ...form.config, [field]: e.target.value } })}
                  />
                ))}
              </div>
            </>
          )}
          <input className={inputCls} placeholder="Description (optional)" value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })} />
          {error && <div className="text-xs text-danger">{error}</div>}
          <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
            {busy ? "…" : "Save connector"}
          </button>
        </form>
      )}

      <div className="mt-4 space-y-3">
        {connectors.map((c) => (
          <div key={c.id} className="rounded-lg border border-border bg-card px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold">
                {TYPE_ICONS[c.type] || "🔌"} {c.name}
                <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] text-accent">{c.type}</span>
                {!c.enabled && <span className="rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger">disabled</span>}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <button onClick={() => testConnector(c.id)} className="text-muted hover:text-accent">test</button>
                {c.type === "postgres" && (
                  <button onClick={() => setQueryConn(queryConn === c.id ? null : c.id)} className="text-muted hover:text-accent">query</button>
                )}
                {c.type === "webhook" && (
                  <button onClick={() => loadDeliveries(c.id)} className="text-muted hover:text-accent">deliveries</button>
                )}
                <button onClick={() => removeConnector(c.id)} className="text-muted hover:text-danger">delete</button>
              </div>
            </div>
            <div className="mt-1 truncate text-xs text-muted">
              {Object.entries(c.config).map(([k, v]) => `${k}=${v}`).join(" · ") || c.description}
            </div>
            {testResult[c.id] && (
              <div className={`mt-1 text-xs ${testResult[c.id].startsWith("✓") ? "text-success" : "text-danger"}`}>
                {testResult[c.id]}
              </div>
            )}

            {queryConn === c.id && (
              <div className="mt-3 space-y-2 border-t border-border pt-3">
                <div className="flex gap-2">
                  <input className={inputCls} value={querySql} onChange={(e) => setQuerySql(e.target.value)}
                    placeholder="SELECT * FROM table LIMIT 10" />
                  <button onClick={() => runQuery(c.id)}
                    className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90">
                    Run
                  </button>
                </div>
                {queryError && <div className="text-xs text-danger">{queryError}</div>}
                {queryResult && (
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-border bg-background">
                          {queryResult.columns.map((col) => (
                            <th key={col} className="px-3 py-1.5 font-semibold text-muted">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryResult.rows.map((row, i) => (
                          <tr key={i} className="border-b border-border last:border-0">
                            {queryResult.columns.map((col) => (
                              <td key={col} className="max-w-[200px] truncate px-3 py-1.5">{String(row[col] ?? "")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {queryResult.rows.length === 0 && (
                      <div className="px-3 py-2 text-xs text-muted">No rows returned.</div>
                    )}
                  </div>
                )}
              </div>
            )}

            {deliveries[c.id] && (
              <div className="mt-3 space-y-1 border-t border-border pt-3">
                <div className="text-xs font-semibold text-muted">Recent deliveries</div>
                {deliveries[c.id].slice(0, 10).map((d) => (
                  <div key={d.id} className="flex items-center justify-between text-xs">
                    <span>
                      <span className={d.status === "success" ? "text-success" : d.status === "failed" ? "text-danger" : "text-muted"}>
                        {d.status === "success" ? "✓" : d.status === "failed" ? "✗" : "⏳"}
                      </span>{" "}
                      <span className="font-mono">{d.event_type}</span>
                      {d.last_http_status && <span className="text-muted"> HTTP {d.last_http_status}</span>}
                    </span>
                    <span className="text-muted">{d.created_at?.replace("T", " ").slice(0, 19)}</span>
                  </div>
                ))}
                {deliveries[c.id].length === 0 && (
                  <div className="text-xs text-muted">No deliveries yet — trigger a record change.</div>
                )}
              </div>
            )}
          </div>
        ))}
        {connectors.length === 0 && !showAdd && (
          <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
            No connectors yet. Add a webhook to stream events to your own analytics.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Automations ---------------- */

interface AutomationRule {
  plugin_id: string;
  plugin_name: string;
  slug: string;
  name: string;
  trigger: string;
  object: string | null;
  condition: Record<string, unknown>;
  actions: Record<string, unknown>[];
}

interface AutomationRunRow {
  id: string;
  plugin_id: string;
  automation_slug: string;
  trigger_event: string;
  status: string;
  detail: Record<string, unknown>;
  created_at: string;
}

function AutomationsView() {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [runs, setRuns] = useState<AutomationRunRow[]>([]);

  useEffect(() => {
    api<AutomationRule[]>("/api/automations").then(setRules).catch(() => {});
    api<AutomationRunRow[]>("/api/automations/runs").then(setRuns).catch(() => {});
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold">⚙️ Automations</h1>
      <p className="mt-1 text-sm text-muted">
        Declarative rules from your enabled plugins: when an event matches the trigger and
        condition, the kernel runs the actions — no code, fully audited.
      </p>

      <h2 className="mt-6 text-sm font-semibold text-muted">Declared rules</h2>
      <div className="mt-2 space-y-2">
        {rules.map((r) => (
          <div key={`${r.plugin_id}/${r.slug}`} className="rounded-lg border border-border bg-card px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">{r.name}</div>
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] text-accent">{r.plugin_name}</span>
            </div>
            <div className="mt-1 text-xs text-muted">
              <span className="font-mono">when {r.trigger}</span>
              {r.object && <span className="font-mono"> on {r.object}</span>}
              {Object.keys(r.condition).length > 0 && (
                <span className="font-mono"> if {String(r.condition.field ?? "")} = {String(r.condition.equals ?? "")}</span>
              )}
              <span> → </span>
              {r.actions.map((a, i) => (
                <span key={i} className="font-mono">{String(a.action)}{i < r.actions.length - 1 ? ", " : ""}</span>
              ))}
            </div>
          </div>
        ))}
        {rules.length === 0 && (
          <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
            No automation rules — enable a plugin that declares some.
          </div>
        )}
      </div>

      <h2 className="mt-6 text-sm font-semibold text-muted">Recent runs</h2>
      <div className="mt-2 space-y-1">
        {runs.map((r) => (
          <div key={r.id} className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-2 text-xs">
            <div className="min-w-0 truncate">
              <span className={r.status === "success" ? "text-success" : "text-danger"}>
                {r.status === "success" ? "✓" : "✗"}
              </span>{" "}
              <span className="font-mono">{r.plugin_id}/{r.automation_slug}</span>
              <span className="text-muted"> ← {r.trigger_event}</span>
            </div>
            <span className="ml-3 shrink-0 text-muted">{r.created_at?.replace("T", " ").slice(0, 19)}</span>
          </div>
        ))}
        {runs.length === 0 && (
          <div className="rounded-lg border border-dashed border-border px-4 py-4 text-center text-xs text-muted">
            No runs yet. Trigger one — e.g. set a lead&apos;s status to Converted.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Events ---------------- */

function EventsView() {
  const [events, setEvents] = useState<
    { id: string; type: string; plugin_id: string; payload: unknown; created_at: string }[]
  >([]);

  useEffect(() => {
    api<typeof events>("/api/events?limit=50").then(setEvents).catch(() => {});
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold">⚡ Events</h1>
      <p className="mt-1 text-sm text-muted">
        The event seam — every action in the kernel lands here. Automation, analytics forwarding,
        and AI context all plug into this stream.
      </p>
      <div className="mt-6 space-y-2">
        {events.map((e) => (
          <div key={e.id} className="rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-xs text-accent">{e.type}</span>
              <span className="text-[11px] text-muted">
                {e.plugin_id && <span className="mr-2">🧩 {e.plugin_id}</span>}
                {new Date(e.created_at).toLocaleTimeString()}
              </span>
            </div>
            <pre className="mt-1 overflow-x-auto text-[11px] text-muted">{JSON.stringify(e.payload)}</pre>
          </div>
        ))}
        {events.length === 0 && <div className="text-sm text-muted">No events yet.</div>}
      </div>
    </div>
  );
}

/* ---------------- Appearance / Settings ---------------- */

function SettingsView() {
  const { theme, resolvedMode, setMode, setAccent, setDensity, setRadius, reset } = useTheme();
  const [customHex, setCustomHex] = useState("");

  const isPreset = ACCENT_PRESETS.some((p) => p.id === theme.accent);
  const currentHex = !isPreset && /^#[0-9a-fA-F]{3,8}$/.test(theme.accent) ? theme.accent : "";

  function applyCustom(hex: string) {
    setCustomHex(hex);
    if (/^#[0-9a-fA-F]{6}$/.test(hex)) setAccent(hex);
  }

  const segBtn = (active: boolean) =>
    `flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition ${
      active ? "bg-accent text-on-accent" : "text-muted hover:bg-card-2 hover:text-foreground"
    }`;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <Palette size={20} /> Appearance
          </h1>
          <p className="mt-1 text-sm text-muted">
            Full control over how Truss looks. Default is monochrome — add color only if you want it.
            Everything saves automatically and persists across sessions.
          </p>
        </div>
        <button
          onClick={reset}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-border-strong hover:text-foreground"
        >
          <RotateCcw size={13} /> Reset
        </button>
      </div>

      {/* Theme mode */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Theme</h2>
        <p className="mt-0.5 text-xs text-muted">Light, dark, or follow your system.</p>
        <div className="mt-3 flex rounded-lg border border-border bg-card p-1">
          <button onClick={() => setMode("light")} className={segBtn(theme.mode === "light")}>
            <Sun size={15} /> Light
          </button>
          <button onClick={() => setMode("dark")} className={segBtn(theme.mode === "dark")}>
            <Moon size={15} /> Dark
          </button>
          <button onClick={() => setMode("system")} className={segBtn(theme.mode === "system")}>
            <Monitor size={15} /> System
          </button>
        </div>
        {theme.mode === "system" && (
          <p className="mt-2 text-[11px] text-faint">Currently following system: {resolvedMode}</p>
        )}
      </section>

      {/* Accent color */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Accent color</h2>
        <p className="mt-0.5 text-xs text-muted">
          Mono keeps everything black &amp; white. Pick a preset or any custom color.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {ACCENT_PRESETS.map((p) => {
            const active = theme.accent === p.id;
            return (
              <button
                key={p.id}
                onClick={() => setAccent(p.id)}
                title={p.label}
                className={`flex h-10 w-10 items-center justify-center rounded-lg border transition ${
                  active ? "border-accent ring-2 ring-accent/40" : "border-border hover:border-border-strong"
                }`}
              >
                {p.id === "mono" ? (
                  <span className="flex h-6 w-6 overflow-hidden rounded-full border border-border">
                    <span className="h-full w-1/2 bg-foreground" />
                    <span className="h-full w-1/2 bg-background" />
                  </span>
                ) : (
                  <span className="h-6 w-6 rounded-full" style={{ background: p.value }} />
                )}
              </button>
            );
          })}

          {/* custom color picker */}
          <label
            className={`flex h-10 cursor-pointer items-center gap-2 rounded-lg border px-3 transition ${
              !isPreset ? "border-accent ring-2 ring-accent/40" : "border-border hover:border-border-strong"
            }`}
            title="Custom color"
          >
            <input
              type="color"
              value={currentHex || "#e8a33d"}
              onChange={(e) => applyCustom(e.target.value)}
              className="h-6 w-6 cursor-pointer appearance-none rounded border-0 bg-transparent p-0"
            />
            <span className="text-xs text-muted">Custom</span>
          </label>
        </div>

        {/* hex input for exact values */}
        <div className="mt-3 flex items-center gap-2">
          <input
            value={customHex || currentHex}
            onChange={(e) => applyCustom(e.target.value)}
            placeholder="#e8a33d"
            className="w-32 rounded-lg border border-border bg-card px-3 py-1.5 font-mono text-xs outline-none focus:border-accent"
          />
          <span className="text-[11px] text-faint">Enter an exact hex value</span>
        </div>
      </section>

      {/* Density */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Density</h2>
        <p className="mt-0.5 text-xs text-muted">How much space the interface uses.</p>
        <div className="mt-3 flex rounded-lg border border-border bg-card p-1">
          <button onClick={() => setDensity("comfortable")} className={segBtn(theme.density === "comfortable")}>
            Comfortable
          </button>
          <button onClick={() => setDensity("compact")} className={segBtn(theme.density === "compact")}>
            Compact
          </button>
        </div>
      </section>

      {/* Corner radius */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Corner radius</h2>
        <p className="mt-0.5 text-xs text-muted">From sharp industrial edges to soft rounded corners.</p>
        <div className="mt-3 flex rounded-lg border border-border bg-card p-1">
          {(["sharp", "soft", "rounded"] as Radius[]).map((r) => (
            <button key={r} onClick={() => setRadius(r)} className={segBtn(theme.radius === r)}>
              {r[0].toUpperCase() + r.slice(1)}
            </button>
          ))}
        </div>
      </section>

      {/* Live preview */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Preview</h2>
        <div className="mt-3 rounded-xl border border-border bg-card p-5">
          <div className="flex flex-wrap items-center gap-3">
            <button className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent">
              Primary action
            </button>
            <button className="rounded-lg border border-border px-4 py-2 text-sm font-medium">
              Secondary
            </button>
            <span className="rounded-md bg-accent-soft px-2 py-1 text-xs text-accent">Badge</span>
            <span className="text-xs text-success">Success</span>
            <span className="text-xs text-danger">Danger</span>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <div className="rounded-lg border border-border bg-card-2 p-3 text-xs">
              <div className="font-semibold">Card</div>
              <div className="mt-1 text-muted">Nested surface</div>
            </div>
            <div className="rounded-lg border border-border bg-card-2 p-3 text-xs">
              <div className="font-mono text-accent">mono/token</div>
              <div className="mt-1 text-muted">Code accent</div>
            </div>
            <div className="rounded-lg border border-border bg-card-2 p-3 text-xs">
              <div className="flex items-center gap-1.5 font-semibold">
                <LayoutGrid size={13} /> Icon
              </div>
              <div className="mt-1 text-muted">Lucide set</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
