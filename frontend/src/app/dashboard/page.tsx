"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  Bot,
  Boxes,
  Cable,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Cog,
  Command,
  Copy,
  Database,
  History,
  Home,
  Info,
  Kanban,
  LayoutGrid,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Palette,
  Pencil,
  Plug,
  Puzzle,
  RotateCcw,
  Search,
  Shield,
  Store,
  Sun,
  Trash2,
  UserCircle,
  UserPlus,
  Users,
  X,
  Zap,
} from "lucide-react";
import {
  api,
  API_BASE,
  getToken,
  setToken,
  type AgentInfo,
  type AgentRunResult,
  type AgentTaskInfo,
  type AiKeyInfo,
  type ApiKeyInfo,
  type HistoryEntry,
  type TrashItem,
  type ChatResult,
  type Invite,
  type MarketplacePlugin,
  type MarketplaceTemplate,
  type Me,
  type Member,
  type ObjectDef,
  type PluginInfo,
  type RecordRow,
  type RoleInfo,
  type Workspace,
} from "@/lib/api";
import { ACCENT_PRESETS, useTheme, type Density, type Radius, type ThemeMode } from "@/lib/theme";

type View =
  | { kind: "home" }
  | { kind: "object"; slug: string }
  | { kind: "kanban"; slug: string; object: string; groupBy: string }
  | { kind: "plugins" }
  | { kind: "marketplace" }
  | { kind: "events" }
  | { kind: "ai" }
  | { kind: "agents" }
  | { kind: "automations" }
  | { kind: "connectors" }
  | { kind: "settings" }
  | { kind: "workspace" }
  | { kind: "profile" };

/* ---------------- Toast store (module-level — any view can toast) ---------------- */

type ToastMsg = { id: number; message: string; kind: "success" | "error" | "info" };
let toastSeq = 0;
const toastListeners = new Set<(t: ToastMsg) => void>();

function toast(message: string, kind: ToastMsg["kind"] = "info") {
  const t = { id: ++toastSeq, message, kind };
  toastListeners.forEach((l) => l(t));
}

function Toaster() {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  useEffect(() => {
    const listener = (t: ToastMsg) => {
      setToasts((prev) => [...prev.slice(-3), t]);
      setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== t.id)), 3500);
    };
    toastListeners.add(listener);
    return () => {
      toastListeners.delete(listener);
    };
  }, []);
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast-in pointer-events-auto flex items-center gap-2 rounded-lg border bg-card px-4 py-2.5 text-sm shadow-xl ${
            t.kind === "success"
              ? "border-success/40 text-success"
              : t.kind === "error"
                ? "border-danger/40 text-danger"
                : "border-border text-foreground"
          }`}
        >
          {t.kind === "success" ? <Check size={14} /> : t.kind === "error" ? <X size={14} /> : <Info size={14} />}
          <span className="text-foreground">{t.message}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------------- Sidebar nav item ---------------- */

function NavItem({
  active,
  onClick,
  icon,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
        active ? "bg-accent-soft font-medium text-accent" : "hover:bg-card"
      }`}
    >
      {active && <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent" />}
      {icon}
      <span className="flex-1 truncate">{label}</span>
      {badge && <span className="rounded-md bg-background px-1.5 py-0.5 text-[10px] text-muted">{badge}</span>}
    </button>
  );
}

/* ---------------- Collapsible sidebar section ---------------- */

function NavSection({
  icon,
  label,
  count,
  open,
  onToggle,
  active,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  count?: number;
  open: boolean;
  onToggle: () => void;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <button
        onClick={onToggle}
        className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
          active ? "font-medium text-accent" : "hover:bg-card"
        }`}
      >
        {icon}
        <span className="flex-1 truncate">{label}</span>
        {count !== undefined && count > 0 && (
          <span className="rounded-md bg-background px-1.5 py-0.5 text-[10px] text-muted">{count}</span>
        )}
        <ChevronDown
          size={13}
          className={`shrink-0 text-muted transition-transform duration-150 ${open ? "" : "-rotate-90"}`}
        />
      </button>
      {open && (
        <div className="ml-[15px] mt-0.5 space-y-0.5 border-l border-border pl-2.5">{children}</div>
      )}
    </div>
  );
}

/* ---------------- Sidebar content (shared by desktop rail + mobile drawer) ---------------- */

function SidebarContent({
  me,
  view,
  setView,
  openSections,
  toggleSection,
  tableSurfaces,
  boardSurfaces,
  onNavigate,
  onOpenPalette,
  onSignOut,
}: {
  me: Me;
  view: View;
  setView: (v: View) => void;
  openSections: Record<string, boolean>;
  toggleSection: (id: string) => void;
  tableSurfaces: { label: string; icon: string; object?: string; slug: string; view: string; groupBy?: string }[];
  boardSurfaces: { label: string; icon: string; object?: string; slug: string; view: string; groupBy?: string }[];
  onNavigate?: () => void;
  onOpenPalette: () => void;
  onSignOut: () => void;
}) {
  const go = (v: View) => {
    setView(v);
    onNavigate?.();
  };

  return (
    <>
      {/* Brand */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3.5">
        <span className="text-xl">🏗️</span>
        <div className="min-w-0">
          <div className="text-sm font-bold leading-tight">Truss</div>
          <div className="truncate text-[11px] text-muted">{me.tenant_name}</div>
        </div>
      </div>

      {/* command palette trigger */}
      <button
        onClick={onOpenPalette}
        className="mx-2 mt-2 flex items-center gap-2 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs text-muted transition hover:border-border-strong hover:text-foreground"
      >
        <Search size={13} />
        <span className="flex-1 text-left">Search or jump to…</span>
        <kbd className="flex items-center gap-0.5 rounded border border-border px-1 py-0.5 font-mono text-[10px]">
          <Command size={9} />K
        </kbd>
      </button>

      {/* Nav — the only scrollable region; header & footer stay pinned */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        <NavItem
          active={view.kind === "home"}
          onClick={() => go({ kind: "home" })}
          icon={<Home size={15} />}
          label="Home"
        />

        {/* Apps — every table view, grouped in one dropdown */}
        <NavSection
          icon={<LayoutGrid size={15} />}
          label="Apps"
          count={tableSurfaces.length}
          open={openSections.apps}
          onToggle={() => toggleSection("apps")}
          active={view.kind === "object"}
        >
          {tableSurfaces.length === 0 && (
            <div className="px-2 py-1 text-xs text-muted">Install a plugin to see its apps →</div>
          )}
          {tableSurfaces.map((s) => (
            <NavItem
              key={s.slug}
              active={view.kind === "object" && view.slug === s.object}
              onClick={() => go({ kind: "object", slug: s.object! })}
              icon={<span className="text-[13px] leading-none">{s.icon}</span>}
              label={s.label}
            />
          ))}
        </NavSection>

        {/* Boards — every kanban board, grouped in one dropdown */}
        <NavSection
          icon={<Kanban size={15} />}
          label="Boards"
          count={boardSurfaces.length}
          open={openSections.boards}
          onToggle={() => toggleSection("boards")}
          active={view.kind === "kanban"}
        >
          {boardSurfaces.length === 0 && (
            <div className="px-2 py-1 text-xs text-muted">No boards yet — enable a plugin with a board view.</div>
          )}
          {boardSurfaces.map((s) => (
            <NavItem
              key={s.slug}
              active={view.kind === "kanban" && view.slug === s.slug}
              onClick={() =>
                go(
                  s.groupBy
                    ? { kind: "kanban", slug: s.slug, object: s.object!, groupBy: s.groupBy }
                    : { kind: "object", slug: s.object! }
                )
              }
              icon={<span className="text-[13px] leading-none">{s.icon}</span>}
              label={s.label}
            />
          ))}
        </NavSection>

        {/* Platform — plugins, marketplace, AI, automations, connectors, events */}
        <NavSection
          icon={<Puzzle size={15} />}
          label="Platform"
          open={openSections.platform}
          onToggle={() => toggleSection("platform")}
          active={["plugins", "marketplace", "ai", "automations", "connectors", "events"].includes(view.kind)}
        >
          <NavItem active={view.kind === "plugins"} onClick={() => go({ kind: "plugins" })} icon={<Puzzle size={15} />} label="Plugins" />
          <NavItem active={view.kind === "marketplace"} onClick={() => go({ kind: "marketplace" })} icon={<Store size={15} />} label="Marketplace" />
          {me.role !== "viewer" && (
            <NavItem active={view.kind === "ai"} onClick={() => go({ kind: "ai" })} icon={<Bot size={15} />} label="AI Agent" />
          )}
          <NavItem active={view.kind === "agents"} onClick={() => go({ kind: "agents" })} icon={<Users size={15} />} label="AI Employees" />
          <NavItem active={view.kind === "automations"} onClick={() => go({ kind: "automations" })} icon={<Cog size={15} />} label="Automations" />
          {me.role !== "viewer" && (
            <NavItem active={view.kind === "connectors"} onClick={() => go({ kind: "connectors" })} icon={<Cable size={15} />} label="Connectors" />
          )}
          <NavItem active={view.kind === "events"} onClick={() => go({ kind: "events" })} icon={<Zap size={15} />} label="Events" />
        </NavSection>

        {/* Account — workspace, profile, appearance */}
        <NavSection
          icon={<UserCircle size={15} />}
          label="Account"
          open={openSections.account}
          onToggle={() => toggleSection("account")}
          active={["workspace", "profile", "settings"].includes(view.kind)}
        >
          <NavItem active={view.kind === "workspace"} onClick={() => go({ kind: "workspace" })} icon={<Boxes size={15} />} label="Workspace" badge={me.role} />
          <NavItem active={view.kind === "profile"} onClick={() => go({ kind: "profile" })} icon={<UserCircle size={15} />} label="Profile" />
          <NavItem active={view.kind === "settings"} onClick={() => go({ kind: "settings" })} icon={<Palette size={15} />} label="Appearance" />
        </NavSection>
      </nav>

      {/* Footer — always visible, never pushed off-screen */}
      <div className="border-t border-border p-2">
        <div className="flex items-center gap-2 rounded-lg px-2 py-1.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
            {(me.full_name || me.email).slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium">{me.full_name || me.email}</div>
            <div className="truncate text-[10px] text-muted">{me.email}</div>
          </div>
          <button
            onClick={onSignOut}
            title="Sign out"
            className="shrink-0 rounded-md p-1.5 text-muted transition hover:bg-danger/15 hover:text-danger"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [objects, setObjects] = useState<ObjectDef[]>([]);
  const [view, setView] = useState<View>({ kind: "home" });
  const [bootError, setBootError] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  // Section open/close state persists across reloads
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() => {
    const defaults = { apps: true, boards: true, platform: true, account: false };
    if (typeof window === "undefined") return defaults;
    try {
      const saved = localStorage.getItem("truss.sidebar.sections");
      return saved ? { ...defaults, ...JSON.parse(saved) } : defaults;
    } catch {
      return defaults;
    }
  });
  const toggleSection = (id: string) =>
    setOpenSections((s) => {
      const next = { ...s, [id]: !s[id] };
      try {
        localStorage.setItem("truss.sidebar.sections", JSON.stringify(next));
      } catch {
        /* private mode */
      }
      return next;
    });

  // Ctrl/Cmd+K command palette
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    const out: { label: string; icon: string; object?: string; slug: string; view: string; groupBy?: string }[] = [];
    for (const p of plugins.filter((p) => p.installed && p.enabled)) {
      for (const s of p.ui) {
        if ((s.view === "table" || s.view === "kanban") && s.object) {
          out.push({ label: s.label, icon: s.icon, object: s.object, slug: s.slug, view: s.view, groupBy: s.config?.group_by });
        }
      }
    }
    return out;
  }, [plugins]);

  const tableSurfaces = useMemo(() => surfaces.filter((s) => s.view === "table"), [surfaces]);
  const boardSurfaces = useMemo(() => surfaces.filter((s) => s.view === "kanban"), [surfaces]);

  // Auto-open the section that contains the active view (e.g. after a palette jump)
  useEffect(() => {
    setOpenSections((s) => {
      const next = { ...s };
      if (view.kind === "object") next.apps = true;
      if (view.kind === "kanban") next.boards = true;
      if (["plugins", "marketplace", "ai", "automations", "connectors", "events"].includes(view.kind)) next.platform = true;
      if (["workspace", "profile", "settings"].includes(view.kind)) next.account = true;
      return next;
    });
  }, [view]);

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

  const signOut = () => {
    setToken(null);
    router.replace("/login");
  };

  const sidebarProps = {
    me,
    view,
    setView,
    openSections,
    toggleSection,
    tableSurfaces,
    boardSurfaces,
    onOpenPalette: () => setPaletteOpen(true),
    onSignOut: signOut,
  };

  return (
    <main className="flex h-screen overflow-hidden">
      {/* Desktop sidebar — fixed to viewport height; only the nav scrolls */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/50 md:flex">
        <SidebarContent {...sidebarProps} />
      </aside>

      {/* Mobile drawer */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileNavOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col border-r border-border bg-card shadow-xl">
            <SidebarContent {...sidebarProps} onNavigate={() => setMobileNavOpen(false)} />
          </aside>
        </div>
      )}

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <div className="flex items-center gap-2 border-b border-border bg-card/50 px-3 py-2 md:hidden">
          <button
            onClick={() => setMobileNavOpen(true)}
            className="rounded-lg border border-border p-1.5 text-muted transition hover:text-foreground"
            title="Open navigation"
          >
            <Menu size={16} />
          </button>
          <span className="text-base">🏗️</span>
          <span className="text-sm font-bold">Truss</span>
          <span className="truncate text-[11px] text-muted">{me.tenant_name}</span>
          <button
            onClick={() => setPaletteOpen(true)}
            className="ml-auto rounded-lg border border-border p-1.5 text-muted transition hover:text-foreground"
            title="Search"
          >
            <Search size={15} />
          </button>
        </div>

        {/* Content — the only region that scrolls with page content */}
        <section className="min-h-0 flex-1 overflow-y-auto p-6">
          <div key={JSON.stringify(view)} className="view-in">
            {view.kind === "home" && (
              <HomeView me={me} plugins={plugins} objects={objects} surfaces={surfaces} setView={setView} />
            )}
            {view.kind === "plugins" && <PluginsView plugins={plugins} onChanged={refresh} />}
            {view.kind === "marketplace" && <MarketplaceView onChanged={refresh} />}
            {view.kind === "events" && <EventsView />}
            {view.kind === "ai" && <AiView onChanged={refresh} />}
            {view.kind === "agents" && <AgentsView onChanged={refresh} />}
            {view.kind === "automations" && <AutomationsView />}
            {view.kind === "connectors" && <ConnectorsView />}
            {view.kind === "settings" && <SettingsView />}
            {view.kind === "workspace" && <WorkspaceView me={me} onMeChanged={refresh} />}
            {view.kind === "profile" && <ProfileView me={me} onMeChanged={refresh} />}
            {view.kind === "object" && (
              <ObjectView
                object={objects.find((o) => o.slug === view.slug) ?? null}
                onChanged={refresh}
              />
            )}
            {view.kind === "kanban" && (
              <KanbanView
                object={objects.find((o) => o.slug === view.object) ?? null}
                groupBy={view.groupBy}
                onChanged={refresh}
              />
            )}
          </div>
        </section>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        surfaces={surfaces}
        setView={(v) => {
          setView(v);
          setPaletteOpen(false);
        }}
      />
      <Toaster />
    </main>
  );
}

/* ---------------- Home (overview) ---------------- */

function HomeView({
  me,
  plugins,
  objects,
  surfaces,
  setView,
}: {
  me: Me;
  plugins: PluginInfo[];
  objects: ObjectDef[];
  surfaces: { label: string; icon: string; object?: string; slug: string; view: string; groupBy?: string }[];
  setView: (v: View) => void;
}) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [recentEvents, setRecentEvents] = useState<
    { id: string; type: string; created_at: string }[]
  >([]);

  const enabled = plugins.filter((p) => p.installed && p.enabled);

  useEffect(() => {
    // record counts per object (parallel, capped)
    Promise.all(
      objects.slice(0, 12).map(async (o) => {
        try {
          const res = await api<{ total: number }>(`/api/records/${o.slug}?limit=1`);
          return [o.slug, res.total] as const;
        } catch {
          return [o.slug, 0] as const;
        }
      })
    ).then((pairs) => setCounts(Object.fromEntries(pairs)));
    api<{ id: string; type: string; created_at: string }[]>("/api/events?limit=6")
      .then(setRecentEvents)
      .catch(() => {});
  }, [objects]);

  const totalRecords = Object.values(counts).reduce((a, b) => a + b, 0);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-bold">
        {greeting}, {me.email.split("@")[0]} 👋
      </h1>
      <p className="mt-1 text-sm text-muted">
        {me.tenant_name} · {enabled.length} active plugin{enabled.length === 1 ? "" : "s"} ·{" "}
        {totalRecords} records across {objects.length} objects
      </p>

      {/* stat cards */}
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <button
          onClick={() => setView({ kind: "plugins" })}
          className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong"
        >
          <div className="flex items-center gap-2 text-xs text-muted">
            <Puzzle size={13} /> Active plugins
          </div>
          <div className="mt-2 text-2xl font-bold">{enabled.length}</div>
          <div className="mt-1 text-[11px] text-muted">{plugins.length - enabled.length} available</div>
        </button>
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Database size={13} /> Records
          </div>
          <div className="mt-2 text-2xl font-bold">{totalRecords}</div>
          <div className="mt-1 text-[11px] text-muted">{objects.length} object types</div>
        </div>
        <button
          onClick={() => setView({ kind: "events" })}
          className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong"
        >
          <div className="flex items-center gap-2 text-xs text-muted">
            <Activity size={13} /> Recent activity
          </div>
          <div className="mt-2 truncate text-sm font-semibold text-accent">
            {recentEvents[0]?.type ?? "—"}
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {recentEvents[0] ? new Date(recentEvents[0].created_at).toLocaleString() : "no events yet"}
          </div>
        </button>
        <button
          onClick={() => setView({ kind: "ai" })}
          className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong"
        >
          <div className="flex items-center gap-2 text-xs text-muted">
            <Bot size={13} /> AI Agent
          </div>
          <div className="mt-2 text-sm font-semibold">Ask your data</div>
          <div className="mt-1 text-[11px] text-muted">bring your own model key</div>
        </button>
      </div>

      {/* apps grid */}
      <h2 className="mt-8 text-sm font-semibold text-muted">Your apps</h2>
      {surfaces.length === 0 ? (
        <div className="mt-3 rounded-xl border border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted">No apps yet — install a plugin to get started.</p>
          <button
            onClick={() => setView({ kind: "marketplace" })}
            className="mt-3 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            Browse the Marketplace
          </button>
        </div>
      ) : (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {surfaces.map((s) => (
            <button
              key={s.slug}
              onClick={() =>
                s.view === "kanban" && s.groupBy
                  ? setView({ kind: "kanban", slug: s.slug, object: s.object!, groupBy: s.groupBy })
                  : setView({ kind: "object", slug: s.object! })
              }
              className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 text-left transition hover:border-border-strong hover:bg-card-2"
            >
              <span className="text-xl">{s.icon}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{s.label}</span>
                <span className="block text-[11px] text-muted">
                  {s.view === "kanban" ? "Board" : `${counts[s.object ?? ""] ?? "…"} records`}
                </span>
              </span>
              {s.view === "kanban" && <LayoutGrid size={14} className="text-faint" />}
            </button>
          ))}
        </div>
      )}

      {/* recent events */}
      <h2 className="mt-8 text-sm font-semibold text-muted">Latest events</h2>
      <div className="mt-3 space-y-1.5">
        {recentEvents.map((e) => (
          <div
            key={e.id}
            className="flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2 text-xs"
          >
            <span className="font-mono text-accent">{e.type}</span>
            <span className="text-muted">{new Date(e.created_at).toLocaleString()}</span>
          </div>
        ))}
        {recentEvents.length === 0 && (
          <div className="rounded-lg border border-dashed border-border px-4 py-4 text-center text-xs text-muted">
            No events yet — create a record or install a plugin.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Command palette (Ctrl+K) ---------------- */

function CommandPalette({
  open,
  onClose,
  surfaces,
  setView,
}: {
  open: boolean;
  onClose: () => void;
  surfaces: { label: string; icon: string; object?: string; slug: string; view: string; groupBy?: string }[];
  setView: (v: View) => void;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);

  const items = useMemo(() => {
    const platform: { label: string; icon: React.ReactNode; view: View }[] = [
      { label: "Home", icon: <Home size={14} />, view: { kind: "home" } },
      { label: "Plugins", icon: <Puzzle size={14} />, view: { kind: "plugins" } },
      { label: "Marketplace", icon: <Store size={14} />, view: { kind: "marketplace" } },
      { label: "AI Agent", icon: <Bot size={14} />, view: { kind: "ai" } },
      { label: "AI Employees", icon: <Users size={14} />, view: { kind: "agents" } },
      { label: "Automations", icon: <Cog size={14} />, view: { kind: "automations" } },
      { label: "Connectors", icon: <Cable size={14} />, view: { kind: "connectors" } },
      { label: "Events", icon: <Zap size={14} />, view: { kind: "events" } },
      { label: "Appearance", icon: <Palette size={14} />, view: { kind: "settings" } },
    ];
    const apps = surfaces.map((s) => ({
      label: s.label,
      icon: <span className="text-sm leading-none">{s.icon}</span>,
      view:
        s.view === "kanban" && s.groupBy
          ? ({ kind: "kanban", slug: s.slug, object: s.object!, groupBy: s.groupBy } as View)
          : ({ kind: "object", slug: s.object! } as View),
    }));
    const all = [...apps, ...platform];
    if (!q.trim()) return all;
    const needle = q.toLowerCase();
    return all.filter((i) => i.label.toLowerCase().includes(needle));
  }, [q, surfaces]);

  useEffect(() => {
    if (open) {
      setQ("");
      setSel(0);
    }
  }, [open]);

  useEffect(() => {
    setSel(0);
  }, [q]);

  if (!open) return null;

  return (
    <div
      className="palette-backdrop fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[15vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="palette-panel w-full max-w-lg overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search size={15} className="text-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSel((s) => Math.min(s + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSel((s) => Math.max(s - 1, 0));
              } else if (e.key === "Enter" && items[sel]) {
                setView(items[sel].view);
              }
            }}
            placeholder="Search apps and views…"
            className="w-full bg-transparent py-3 text-sm outline-none placeholder:text-faint"
          />
          <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted">esc</kbd>
        </div>
        <div className="max-h-72 overflow-y-auto p-1.5">
          {items.map((item, i) => (
            <button
              key={item.label}
              onClick={() => setView(item.view)}
              onMouseEnter={() => setSel(i)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition ${
                i === sel ? "bg-accent-soft text-accent" : "hover:bg-card-2"
              }`}
            >
              {item.icon}
              <span className="flex-1">{item.label}</span>
              {i === sel && <span className="text-[10px] text-muted">↵</span>}
            </button>
          ))}
          {items.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-muted">No matches for “{q}”</div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Plugins ---------------- */

function PluginsView({ plugins, onChanged }: { plugins: PluginInfo[]; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState("");

  async function act(pluginId: string, action: "install" | "enable" | "disable") {
    setBusy(pluginId + action);
    try {
      await api(`/api/plugins/${action}`, { method: "POST", body: { plugin_id: pluginId } });
      toast(`Plugin ${action === "install" ? "installed" : action + "d"}: ${pluginId}`, "success");
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : `${action} failed`, "error");
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

/* ---------------- Marketplace (community plugins + templates) ---------------- */

function MarketplaceView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [plugins, setPlugins] = useState<MarketplacePlugin[]>([]);
  const [templates, setTemplates] = useState<MarketplaceTemplate[]>([]);
  const [tab, setTab] = useState<"plugins" | "templates">("plugins");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const [p, t] = await Promise.all([
      api<{ items: MarketplacePlugin[] }>("/api/marketplace/plugins"),
      api<{ items: MarketplaceTemplate[] }>("/api/marketplace/templates"),
    ]);
    setPlugins(p.items);
    setTemplates(t.items);
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  async function installPlugin(id: string) {
    setBusy(id);
    setMessage("");
    try {
      await api(`/api/marketplace/plugins/${id}/install`, { method: "POST" });
      toast(`Installed ${id}`, "success");
      setMessage(`Installed ${id} — its objects and views are live now.`);
      await load();
      await onChanged();
    } catch (e) {
      toast("Install failed", "error");
      setMessage(`Install failed: ${String((e as { detail?: unknown }).detail ?? e)}`);
    } finally {
      setBusy("");
    }
  }

  async function applyTemplate(id: string) {
    setBusy(id);
    setMessage("");
    try {
      const res = await api<{ plugins_installed: string[]; records_seeded: number }>(
        `/api/marketplace/templates/${id}/apply`,
        { method: "POST", body: { seed: true } }
      );
      toast(`Template "${id}" applied`, "success");
      setMessage(`Template applied: ${res.plugins_installed.length} plugin(s), ${res.records_seeded} sample records.`);
      await load();
      await onChanged();
    } catch (e) {
      toast("Apply failed", "error");
      setMessage(`Apply failed: ${String((e as { detail?: unknown }).detail ?? e)}`);
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">🛍️ Marketplace</h1>
          <p className="mt-0.5 text-sm text-muted">
            Community plugins and starter templates — install in one click, no code.
          </p>
        </div>
        <div className="flex rounded-lg border border-border bg-card p-0.5">
          {(["plugins", "templates"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1 text-sm font-medium capitalize transition ${
                tab === t ? "bg-accent text-on-accent" : "text-muted hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {message && (
        <div className="mt-3 rounded-lg border border-border bg-card px-3 py-2 text-sm">{message}</div>
      )}

      {tab === "plugins" && (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {plugins.map((p) => (
            <div key={p.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{p.icon}</span>
                  <div>
                    <div className="font-semibold">{p.name}</div>
                    <div className="text-xs text-muted">
                      by {p.author} · v{p.version} · {p.category}
                    </div>
                  </div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div>⭐ {p.rating}</div>
                  <div>{p.downloads.toLocaleString()} installs</div>
                </div>
              </div>
              <p className="mt-2 text-sm text-muted">{p.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {p.objects.map((o) => (
                  <span key={o} className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs text-accent">
                    {o}
                  </span>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[11px] text-muted">{p.permissions.join(" · ")}</span>
                {p.installed ? (
                  <span className="flex items-center gap-1 text-xs font-semibold text-success">
                    <Check size={13} /> Installed
                  </span>
                ) : (
                  <button
                    disabled={busy !== ""}
                    onClick={() => installPlugin(p.id)}
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
                  >
                    {busy === p.id ? "Installing…" : "Install"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "templates" && (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {templates.map((t) => (
            <div key={t.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{t.icon}</span>
                <div>
                  <div className="font-semibold">{t.name}</div>
                  <div className="text-xs text-muted">
                    {t.plugins.length} plugin(s) · {t.record_count} sample records
                  </div>
                </div>
              </div>
              <p className="mt-2 text-sm text-muted">{t.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {t.plugins.map((pid) => (
                  <span key={pid} className="rounded-md bg-background px-1.5 py-0.5 font-mono text-xs text-muted">
                    {pid}
                  </span>
                ))}
              </div>
              <div className="mt-3 text-right">
                <button
                  disabled={busy !== ""}
                  onClick={() => applyTemplate(t.id)}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
                >
                  {busy === t.id ? "Applying…" : "Use this template"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Object (generic table + create form) ---------------- */

function ObjectView({ object, onChanged }: { object: ObjectDef | null; onChanged: () => Promise<void> }) {
  const [rows, setRows] = useState<RecordRow[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<RecordRow | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [trash, setTrash] = useState<TrashItem[]>([]);
  const [showTrash, setShowTrash] = useState(false);
  const PAGE_SIZE = 25;

  // debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    if (!object) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (debouncedSearch) params.set("search", debouncedSearch);
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(page * PAGE_SIZE));
    const res = await api<{ items: RecordRow[]; total: number }>(`/api/records/${object.slug}?${params}`);
    setRows(res.items);
    setTotal(res.total);
    setLoading(false);
  }, [object, debouncedSearch, page]);

  useEffect(() => {
    setForm({});
    setError("");
    load().catch(() => setLoading(false));
  }, [load]);

  // reset page when switching objects
  useEffect(() => {
    setPage(0);
    setSearch("");
    setShowForm(false);
    setEditing(null);
  }, [object?.slug]);

  if (!object) return <div className="text-muted">Object not found.</div>;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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
        if (f.type === "number" || f.type === "currency") data[f.slug] = Number(v);
        else if (f.type === "multiselect") data[f.slug] = v.split(",").map((s) => s.trim()).filter(Boolean);
        else data[f.slug] = v;
      }
      if (editing) {
        await api(`/api/records/${object.slug}/${editing.id}`, { method: "PATCH", body: { data } });
        toast(`${object.name} updated`, "success");
      } else {
        await api(`/api/records/${object.slug}`, { method: "POST", body: { data } });
        toast(`${object.name} created`, "success");
      }
      setShowForm(false);
      setEditing(null);
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

  function startEdit(r: RecordRow) {
    const f: Record<string, string> = {};
    if (object) {
      for (const field of object.fields) {
        const v = r.data[field.slug];
        if (v !== null && v !== undefined) {
          f[field.slug] = Array.isArray(v) ? v.join(", ") : String(v);
        }
      }
    }
    setForm(f);
    setEditing(r);
    setShowForm(true);
    setError("");
  }

  async function remove(id: string) {
    if (!object) return;
    try {
      await api(`/api/records/${object.slug}/${id}`, { method: "DELETE" });
      toast(`${object.name} moved to trash`, "success");
      setConfirmDelete(null);
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    }
  }

  async function openHistory(id: string) {
    if (!object) return;
    if (historyFor === id) {
      setHistoryFor(null);
      return;
    }
    try {
      const h = await api<HistoryEntry[]>(`/api/records/${object.slug}/${id}/history`);
      setHistory(h);
      setHistoryFor(id);
    } catch {
      toast("Could not load history", "error");
    }
  }

  async function loadTrash() {
    if (!object) return;
    try {
      const t = await api<TrashItem[]>(`/api/records/trash?object_slug=${object.slug}`);
      setTrash(t);
    } catch {
      setTrash([]);
    }
  }

  async function restore(id: string) {
    try {
      await api(`/api/records/trash/${id}/restore`, { method: "POST" });
      toast("Record restored", "success");
      await loadTrash();
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Restore failed", "error");
    }
  }

  useEffect(() => {
    if (showTrash) loadTrash();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showTrash, object?.slug]);

  async function exportCsv() {
    if (!object) return;
    try {
      const res = await fetch(`${API_BASE}/api/records/${object.slug}/export.csv`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error("export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${object.slug}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSV exported", "success");
    } catch {
      toast("Export failed", "error");
    }
  }

  async function importCsv(file: File | undefined) {
    if (!file || !object) return;
    try {
      const text = await file.text();
      const res = await api<{ created: number; skipped: number }>(`/api/records/${object.slug}/import`, {
        method: "POST",
        body: { csv_text: text, skip_errors: true },
      });
      toast(`Imported ${res.created} record(s)${res.skipped ? `, ${res.skipped} skipped` : ""}`, res.skipped ? "info" : "success");
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Import failed", "error");
    }
  }

  const input =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition focus:border-accent";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">
            {object.icon} {object.name_plural}
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            {object.description || "Records"} · {total} total
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => exportCsv()}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted transition hover:border-border-strong hover:text-foreground"
          >
            ⬇ Export CSV
          </button>
          <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted transition hover:border-border-strong hover:text-foreground">
            ⬆ Import CSV
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => importCsv(e.target.files?.[0])} />
          </label>
          <button
            onClick={() => setShowTrash((v) => !v)}
            className={`flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm transition hover:border-border-strong ${showTrash ? "text-foreground" : "text-muted"}`}
          >
            <Trash2 size={13} /> Trash
          </button>
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input
              className={input + " w-52 pl-8"}
              placeholder={`Search ${object.name_plural.toLowerCase()}…`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            onClick={() => {
              if (showForm) {
                setShowForm(false);
                setEditing(null);
                setForm({});
              } else {
                setShowForm(true);
              }
            }}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            {showForm ? "Close" : `+ New ${object.name}`}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={create} className="mt-4 grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-2">
          {editing && (
            <div className="flex items-center gap-1.5 text-xs text-muted md:col-span-2">
              <Pencil size={11} />
              Editing record <span className="font-mono">{editing.id.slice(0, 8)}…</span>
            </div>
          )}
          {object.fields.map((f) => (
            <label key={f.slug} className="block text-xs">
              <span className="mb-1 block text-muted">
                {f.name} {f.required && <span className="text-danger">*</span>}
                {f.type === "multiselect" && <span className="ml-1 text-faint">(comma-separated)</span>}
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
          <div className="flex gap-2 md:col-span-2">
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : editing ? "Save changes" : "Create"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setEditing(null);
                setForm({});
              }}
              className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:border-border-strong hover:text-foreground"
            >
              Cancel
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
            {loading &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-b border-border/50">
                  {object.fields.map((f) => (
                    <td key={f.slug} className="px-3 py-2.5">
                      <div className="skeleton h-4 w-3/4" />
                    </td>
                  ))}
                  <td className="px-3 py-2.5"><div className="skeleton ml-auto h-4 w-12" /></td>
                </tr>
              ))}
            {!loading &&
              rows.map((r) => (
                <tr key={r.id} className="group border-b border-border/50 last:border-0 hover:bg-card/50">
                  {object.fields.map((f) => (
                    <td key={f.slug} className="max-w-[220px] truncate px-3 py-2">
                      {renderCell(r.data[f.slug], f.type)}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1 opacity-0 transition group-hover:opacity-100">
                      <button
                        onClick={() => openHistory(r.id)}
                        title="History"
                        className={`rounded-md p-1.5 transition hover:bg-accent-soft hover:text-accent ${historyFor === r.id ? "text-accent" : "text-muted"}`}
                      >
                        <History size={13} />
                      </button>
                      <button
                        onClick={() => startEdit(r)}
                        title="Edit"
                        className="rounded-md p-1.5 text-muted transition hover:bg-accent-soft hover:text-accent"
                      >
                        <Pencil size={13} />
                      </button>
                      {confirmDelete === r.id ? (
                        <span className="flex items-center gap-1">
                          <button
                            onClick={() => remove(r.id)}
                            className="rounded-md bg-danger/15 px-2 py-1 text-[11px] font-semibold text-danger hover:bg-danger/25"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="rounded-md px-1.5 py-1 text-[11px] text-muted hover:text-foreground"
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(r.id)}
                          title="Delete"
                          className="rounded-md p-1.5 text-muted transition hover:bg-danger/15 hover:text-danger"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={object.fields.length + 1} className="px-3 py-10 text-center text-muted">
                  {debouncedSearch
                    ? `No ${object.name_plural.toLowerCase()} match “${debouncedSearch}”.`
                    : `No ${object.name_plural.toLowerCase()} yet — create the first one.`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* history panel */}
      {historyFor && (
        <div className="mt-4 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">Version history · record {historyFor.slice(0, 8)}…</h3>
            <button onClick={() => setHistoryFor(null)} className="text-xs text-muted hover:text-foreground">Close</button>
          </div>
          {history.length === 0 && <p className="mt-2 text-xs text-muted">No history recorded.</p>}
          <div className="mt-2 space-y-2">
            {history.map((h) => (
              <div key={h.version} className="rounded-lg border border-border bg-background p-2.5">
                <div className="flex items-center gap-2 text-xs">
                  <span className="rounded-full bg-accent/15 px-2 py-0.5 font-semibold text-accent">v{h.version}</span>
                  <span className={h.actor_type === "agent" ? "rounded-full bg-purple-500/15 px-2 py-0.5 font-semibold text-purple-400" : "rounded-full bg-slate-500/15 px-2 py-0.5 text-muted"}>
                    {h.actor_type === "agent" ? "🤖 AI employee" : "👤 user"}
                  </span>
                  <span className="text-muted">{h.created_at ? new Date(h.created_at).toLocaleString() : ""}</span>
                </div>
                <pre className="mt-1.5 overflow-x-auto text-[11px] text-muted">{JSON.stringify(h.data, null, 2)}</pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* trash panel */}
      {showTrash && (
        <div className="mt-4 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">🗑 Trash · {object.name_plural}</h3>
            <button onClick={() => setShowTrash(false)} className="text-xs text-muted hover:text-foreground">Close</button>
          </div>
          {trash.length === 0 && <p className="mt-2 text-xs text-muted">Trash is empty.</p>}
          <div className="mt-2 space-y-2">
            {trash.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg border border-border bg-background p-2.5">
                <div className="min-w-0">
                  <div className="truncate text-sm">{Object.values(t.data).slice(0, 3).map((v) => String(v)).join(" · ") || t.id.slice(0, 8)}</div>
                  <div className="text-[11px] text-muted">deleted {t.deleted_at ? new Date(t.deleted_at).toLocaleString() : ""}</div>
                </div>
                <button onClick={() => restore(t.id)} className="flex items-center gap-1 rounded-md bg-emerald-500/15 px-2.5 py-1 text-xs font-semibold text-emerald-500 hover:bg-emerald-500/25">
                  <RotateCcw size={12} /> Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* pagination */}
      {total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-between text-xs text-muted">
          <span>
            Page {page + 1} of {totalPages} · showing {rows.length} of {total}
          </span>
          <div className="flex gap-1">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 transition hover:border-border-strong hover:text-foreground disabled:opacity-40"
            >
              <ChevronLeft size={12} /> Prev
            </button>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
              className="flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 transition hover:border-border-strong hover:text-foreground disabled:opacity-40"
            >
              Next <ChevronRight size={12} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function renderCell(v: unknown, type: string) {
  if (v === null || v === undefined || v === "") return <span className="text-muted">—</span>;
  if (type === "currency") return <span className="font-mono">${Number(v).toLocaleString()}</span>;
  if (type === "select")
    return <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs text-accent">{String(v)}</span>;
  if (type === "multiselect" && Array.isArray(v))
    return (
      <span className="flex flex-wrap gap-1">
        {v.map((x) => (
          <span key={String(x)} className="rounded-md bg-card-2 px-1.5 py-0.5 text-xs text-muted">
            {String(x)}
          </span>
        ))}
      </span>
    );
  return String(v);
}

/* ---------------- Kanban board (grouped by a select field, drag to move) ---------------- */

function KanbanView({
  object,
  groupBy,
  onChanged,
}: {
  object: ObjectDef | null;
  groupBy: string;
  onChanged: () => Promise<void>;
}) {
  const [rows, setRows] = useState<RecordRow[]>([]);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [quickAddCol, setQuickAddCol] = useState<string | null>(null);
  const [quickAddTitle, setQuickAddTitle] = useState("");

  const groupField = object?.fields.find((f) => f.slug === groupBy);
  const columns = groupField?.options.choices ?? [];

  const load = useCallback(async () => {
    if (!object) return;
    const res = await api<{ items: RecordRow[]; total: number }>(`/api/records/${object.slug}?limit=200`);
    setRows(res.items);
  }, [object]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  if (!object) return <div className="text-muted">Object not found.</div>;
  if (!groupField) return <div className="text-muted">No grouping field "{groupBy}".</div>;

  // title field = first text-ish field for the card label
  const titleField =
    object.fields.find((f) => f.type === "text" && f.slug !== groupBy) ?? object.fields[0];
  const subField = object.fields.find((f) => f.type === "currency") ?? null;
  // extra chip fields: select fields other than the group field (max 1)
  const chipField = object.fields.find((f) => f.type === "select" && f.slug !== groupBy) ?? null;
  const dateField = object.fields.find((f) => f.type === "date") ?? null;

  async function moveTo(recordId: string, value: string) {
    if (!object) return;
    setBusy(true);
    try {
      await api(`/api/records/${object.slug}/${recordId}`, {
        method: "PATCH",
        body: { data: { [groupBy]: value } },
      });
      toast(`Moved to ${value}`, "success");
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Move failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function quickAdd(e: React.FormEvent, col: string) {
    e.preventDefault();
    if (!object || !quickAddTitle.trim()) return;
    setBusy(true);
    try {
      await api(`/api/records/${object.slug}`, {
        method: "POST",
        body: { data: { [titleField.slug]: quickAddTitle.trim(), [groupBy]: col } },
      });
      toast(`${object.name} added to ${col}`, "success");
      setQuickAddTitle("");
      setQuickAddCol(null);
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">
            {object.icon} {object.name_plural} · Board
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            Grouped by {groupField.name} · drag cards to move · {rows.length} total
          </p>
        </div>
        {busy && <span className="text-xs text-muted">saving…</span>}
      </div>

      <div className="mt-4 flex gap-3 overflow-x-auto pb-4">
        {columns.map((col) => {
          const cards = rows.filter((r) => String(r.data[groupBy] ?? "") === col);
          const colTotal = subField
            ? cards.reduce((sum, r) => sum + (Number(r.data[subField.slug]) || 0), 0)
            : null;
          return (
            <div
              key={col}
              onDragOver={(e) => {
                e.preventDefault();
                setOverCol(col);
              }}
              onDragLeave={() => setOverCol((c) => (c === col ? null : c))}
              onDrop={(e) => {
                e.preventDefault();
                setOverCol(null);
                if (dragId) moveTo(dragId, col);
                setDragId(null);
              }}
              className={`flex w-64 shrink-0 flex-col rounded-xl border bg-card/40 transition ${
                overCol === col ? "border-accent bg-accent-soft/40" : "border-border"
              }`}
            >
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <span className="text-sm font-semibold">{col}</span>
                <span className="flex items-center gap-1.5">
                  {colTotal !== null && colTotal > 0 && (
                    <span className="font-mono text-[11px] text-muted">${colTotal.toLocaleString()}</span>
                  )}
                  <span className="rounded-md bg-background px-1.5 py-0.5 text-xs text-muted">
                    {cards.length}
                  </span>
                </span>
              </div>
              <div className="flex min-h-[80px] flex-1 flex-col gap-2 p-2">
                {cards.map((r) => (
                  <div
                    key={r.id}
                    draggable
                    onDragStart={() => setDragId(r.id)}
                    onDragEnd={() => setDragId(null)}
                    className={`kanban-card cursor-grab rounded-lg border border-border bg-card p-3 active:cursor-grabbing ${
                      dragId === r.id ? "dragging" : ""
                    }`}
                  >
                    <div className="text-sm font-medium">
                      {String(r.data[titleField.slug] ?? "—")}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {subField && r.data[subField.slug] != null && (
                        <span className="font-mono text-xs text-muted">
                          ${Number(r.data[subField.slug]).toLocaleString()}
                        </span>
                      )}
                      {chipField && r.data[chipField.slug] != null && (
                        <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent">
                          {String(r.data[chipField.slug])}
                        </span>
                      )}
                      {dateField && r.data[dateField.slug] != null && (
                        <span className="text-[10px] text-faint">{String(r.data[dateField.slug])}</span>
                      )}
                    </div>
                  </div>
                ))}
                {cards.length === 0 && quickAddCol !== col && (
                  <div className="rounded-lg border border-dashed border-border px-2 py-4 text-center text-xs text-muted">
                    Drop here
                  </div>
                )}
                {quickAddCol === col ? (
                  <form onSubmit={(e) => quickAdd(e, col)} className="space-y-1.5">
                    <input
                      autoFocus
                      value={quickAddTitle}
                      onChange={(e) => setQuickAddTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Escape") {
                          setQuickAddCol(null);
                          setQuickAddTitle("");
                        }
                      }}
                      placeholder={`${object.name} title…`}
                      className="w-full rounded-lg border border-accent bg-background px-2.5 py-1.5 text-xs outline-none"
                    />
                    <div className="flex gap-1">
                      <button
                        disabled={busy || !quickAddTitle.trim()}
                        className="rounded-md bg-accent px-2 py-1 text-[11px] font-semibold text-on-accent disabled:opacity-50"
                      >
                        Add
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setQuickAddCol(null);
                          setQuickAddTitle("");
                        }}
                        className="rounded-md px-2 py-1 text-[11px] text-muted hover:text-foreground"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <button
                    onClick={() => {
                      setQuickAddCol(col);
                      setQuickAddTitle("");
                    }}
                    className="rounded-lg px-2 py-1.5 text-left text-xs text-faint transition hover:bg-card hover:text-muted"
                  >
                    + Add {object.name.toLowerCase()}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
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
  const chatEndRef = useRef<HTMLDivElement>(null);

  // auto-scroll to newest message
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatBusy]);

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
    <div className="space-y-6">
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
            {chatBusy && (
              <div className="flex items-center gap-2 text-xs text-muted">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border border-accent border-t-transparent" />
                Agent thinking…
              </div>
            )}
            {chatError && <div className="text-xs text-danger">{chatError}</div>}
            {messages.length === 0 && !chatBusy && (
              <div className="pt-8 text-center">
                <p className="text-sm text-muted">Ask the agent to work with your data.</p>
                <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                  {["Create a lead named Sam from Referral", "How many deals are in Negotiation?", "List open tickets"].map((s) => (
                    <button
                      key={s}
                      onClick={() => setInput(s)}
                      className="rounded-full border border-border px-2.5 py-1 text-xs text-muted transition hover:border-border-strong hover:text-foreground"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
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

    <ApiAccessPanel />
    </div>
  );
}

/* ---------------- API Access (programmatic keys) ---------------- */

function ApiAccessPanel() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["records:read", "records:write", "objects:read"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newKey, setNewKey] = useState("");

  const ALL_SCOPES = ["records:read", "records:write", "objects:read", "agents:read"];

  const load = useCallback(async () => {
    setKeys(await api<ApiKeyInfo[]>("/api/keys"));
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<ApiKeyInfo>("/api/keys", { method: "POST", body: { name, scopes } });
      setNewKey(res.key || "");
      setName("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    await api(`/api/keys/${id}`, { method: "DELETE" });
    await load();
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent";

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">🔌 API Access</h1>
        <button
          onClick={() => { setShowAdd((v) => !v); setNewKey(""); }}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
        >
          {showAdd ? "Close" : "+ New key"}
        </button>
      </div>
      <p className="mt-1 text-sm text-muted">
        Programmatic access to your workspace. Keys act as you but are capped by scopes.
        The full key is shown once at creation — store it safely.
      </p>

      {newKey && (
        <div className="mt-3 rounded-xl border border-success/40 bg-success/10 p-3">
          <div className="text-xs font-semibold text-success">Key created — copy it now, it won&apos;t be shown again:</div>
          <code className="mt-1 block break-all rounded bg-background px-2 py-1 font-mono text-xs">{newKey}</code>
        </div>
      )}

      {showAdd && (
        <form onSubmit={create} className="mt-3 space-y-3 rounded-xl border border-border bg-card p-4">
          <input className={inputCls} placeholder="Key name (e.g. ci-pipeline)" value={name}
            onChange={(e) => setName(e.target.value)} required />
          <div>
            <div className="mb-1 text-xs text-muted">Scopes</div>
            <div className="flex flex-wrap gap-2">
              {ALL_SCOPES.map((sc) => (
                <label key={sc} className="flex items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs">
                  <input type="checkbox" checked={scopes.includes(sc)}
                    onChange={(e) => setScopes(e.target.checked ? [...scopes, sc] : scopes.filter((x) => x !== sc))} />
                  {sc}
                </label>
              ))}
            </div>
          </div>
          {error && <div className="text-xs text-danger">{error}</div>}
          <button disabled={busy || !name} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
            {busy ? "…" : "Create key"}
          </button>
        </form>
      )}

      <div className="mt-3 space-y-2">
        {keys.map((k) => (
          <div key={k.id} className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold">
                {k.name}
                {k.revoked_at && <span className="rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger">revoked</span>}
              </div>
              <div className="truncate font-mono text-xs text-muted">{k.key_prefix}</div>
              <div className="mt-0.5 flex flex-wrap gap-1">
                {k.scopes.map((sc) => (
                  <span key={sc} className="rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">{sc}</span>
                ))}
              </div>
            </div>
            {!k.revoked_at && (
              <button onClick={() => revoke(k.id)} className="ml-3 text-xs text-muted hover:text-danger">revoke</button>
            )}
          </div>
        ))}
        {keys.length === 0 && !showAdd && (
          <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
            No API keys yet. Create one to access Truss from scripts and CI.
          </div>
        )}
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
      toast(`Connector "${form.name}" added`, "success");
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
    toast("Connector removed", "success");
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
              {Object.entries(c.config)
                .map(([k, v]) =>
                  /password|secret|key|token/i.test(k) ? `${k}=••••••` : `${k}=${v}`
                )
                .join(" · ") || c.description}
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
                    className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:brightness-110">
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

/* ---------------- AI Employees (Agents) ---------------- */

const AGENT_ICONS = ["🤖", "📞", "💼", "🧾", "🎧", "📊", "🔧", "✍️", "🛡️", "🚀"];

function AgentsView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selected, setSelected] = useState<AgentInfo | null>(null);
  const [tasks, setTasks] = useState<AgentTaskInfo[]>([]);
  const [showHire, setShowHire] = useState(false);
  const [form, setForm] = useState({ name: "", role: "", persona: "", icon: "🤖", permission_role: "member", budget_tokens: 0 });
  const [taskForm, setTaskForm] = useState({ title: "", description: "", needs_review: false });
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [runningTask, setRunningTask] = useState<string | null>(null);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setAgents(await api<AgentInfo[]>("/api/agents"));
  }, []);

  const loadTasks = useCallback(async (agentId: string) => {
    setTasks(await api<AgentTaskInfo[]>(`/api/agents/${agentId}/tasks`));
  }, []);

  useEffect(() => {
    loadAgents().catch(() => {});
  }, [loadAgents]);

  useEffect(() => {
    if (selected) loadTasks(selected.id).catch(() => {});
  }, [selected, loadTasks]);

  async function hire(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api<AgentInfo>("/api/agents", { method: "POST", body: form });
      setShowHire(false);
      setForm({ name: "", role: "", persona: "", icon: "🤖", permission_role: "member", budget_tokens: 0 });
      await loadAgents();
      setSelected(created);
      toast(`${created.icon} ${created.name} hired`, "success");
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  }

  async function assignTask(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/agents/${selected.id}/tasks`, {
        method: "POST",
        body: { agent_id: selected.id, ...taskForm },
      });
      setShowTaskForm(false);
      setTaskForm({ title: "", description: "", needs_review: false });
      await loadTasks(selected.id);
      toast("Task assigned", "success");
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  }

  async function runTask(taskId: string) {
    if (!selected) return;
    setRunningTask(taskId);
    try {
      const res = await api<AgentRunResult>(`/api/agents/${selected.id}/tasks/${taskId}/run`, { method: "POST" });
      await loadTasks(selected.id);
      await loadAgents();
      await onChanged();
      if (res.run.ok) toast(`✓ ${selected.name} finished the task`, "success");
      else toast(`Task failed: ${res.run.error || "unknown"}`, "error");
      setExpandedTask(taskId);
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Run failed", "error");
    } finally {
      setRunningTask(null);
    }
  }

  async function approveTask(taskId: string) {
    if (!selected) return;
    await api(`/api/agents/${selected.id}/tasks/${taskId}/approve`, { method: "POST" });
    await loadTasks(selected.id);
    toast("Task approved", "success");
  }

  async function rejectTask(taskId: string) {
    if (!selected) return;
    await api(`/api/agents/${selected.id}/tasks/${taskId}/reject`, { method: "POST" });
    await loadTasks(selected.id);
  }

  async function pauseAgent() {
    if (!selected) return;
    const updated = await api<AgentInfo>(`/api/agents/${selected.id}/pause`, { method: "POST" });
    setSelected(updated);
    await loadAgents();
  }

  async function resumeAgent() {
    if (!selected) return;
    const updated = await api<AgentInfo>(`/api/agents/${selected.id}/resume`, { method: "POST" });
    setSelected(updated);
    await loadAgents();
  }

  async function terminateAgent() {
    if (!selected) return;
    if (!confirm(`Terminate ${selected.name}? Their tasks will be removed.`)) return;
    await api(`/api/agents/${selected.id}`, { method: "DELETE" });
    setSelected(null);
    setTasks([]);
    await loadAgents();
    toast("Agent terminated", "info");
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent";

  const statusBadge = (s: AgentInfo["status"]) => {
    const map = { active: "bg-emerald-500/15 text-emerald-500", paused: "bg-amber-500/15 text-amber-500", terminated: "bg-red-500/15 text-red-500" };
    return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${map[s]}`}>{s}</span>;
  };

  const taskBadge = (s: AgentTaskInfo["status"]) => {
    const map: Record<string, string> = {
      proposed: "bg-slate-500/15 text-slate-400",
      approved: "bg-blue-500/15 text-blue-400",
      running: "bg-purple-500/15 text-purple-400",
      done: "bg-emerald-500/15 text-emerald-500",
      failed: "bg-red-500/15 text-red-500",
      rejected: "bg-slate-500/15 text-slate-500",
    };
    return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${map[s] || ""}`}>{s}</span>;
  };

  // ---------- detail view ----------
  if (selected) {
    return (
      <div>
        <button onClick={() => setSelected(null)} className="mb-4 flex items-center gap-1 text-sm text-muted hover:text-foreground">
          <ChevronLeft size={14} /> All agents
        </button>

        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-card text-2xl">{selected.icon}</div>
            <div>
              <h1 className="text-xl font-bold">{selected.name}</h1>
              <p className="text-sm text-muted">{selected.role || "General assistant"} · {statusBadge(selected.status)}</p>
            </div>
          </div>
          <div className="flex gap-2">
            {selected.status === "active" ? (
              <button onClick={pauseAgent} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-card">⏸ Pause</button>
            ) : selected.status === "paused" ? (
              <button onClick={resumeAgent} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-card">▶ Resume</button>
            ) : null}
            <button onClick={terminateAgent} className="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-400 hover:bg-red-500/10">Terminate</button>
          </div>
        </div>

        {/* stats */}
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-border bg-card p-3">
            <div className="text-xs text-muted">Runs</div>
            <div className="text-lg font-bold">{selected.runs_count}</div>
          </div>
          <div className="rounded-xl border border-border bg-card p-3">
            <div className="text-xs text-muted">Tokens used</div>
            <div className="text-lg font-bold">{selected.tokens_used.toLocaleString()}</div>
          </div>
          <div className="rounded-xl border border-border bg-card p-3">
            <div className="text-xs text-muted">Budget</div>
            <div className="text-lg font-bold">{selected.budget_tokens > 0 ? selected.budget_tokens.toLocaleString() : "∞"}</div>
          </div>
        </div>

        {selected.persona && (
          <div className="mt-4 rounded-xl border border-border bg-card p-3">
            <div className="text-xs font-semibold text-muted">PERSONA</div>
            <p className="mt-1 text-sm">{selected.persona}</p>
          </div>
        )}

        {/* tasks */}
        <div className="mt-6 flex items-center justify-between">
          <h2 className="text-lg font-bold">Tasks</h2>
          <button onClick={() => setShowTaskForm((v) => !v)} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent hover:brightness-110">
            {showTaskForm ? "Close" : "+ Assign task"}
          </button>
        </div>

        {showTaskForm && (
          <form onSubmit={assignTask} className="mt-3 space-y-3 rounded-xl border border-border bg-card p-4">
            <input className={inputCls} placeholder="Task title (e.g. Qualify the new inbound lead)" value={taskForm.title}
              onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })} required />
            <textarea className={inputCls} rows={2} placeholder="Details (optional)" value={taskForm.description}
              onChange={(e) => setTaskForm({ ...taskForm, description: e.target.value })} />
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={taskForm.needs_review}
                onChange={(e) => setTaskForm({ ...taskForm, needs_review: e.target.checked })} />
              Require my approval before running
            </label>
            {error && <div className="text-xs text-danger">{error}</div>}
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : "Assign"}
            </button>
          </form>
        )}

        <div className="mt-3 space-y-2">
          {tasks.length === 0 && <p className="text-sm text-muted">No tasks yet. Assign one above.</p>}
          {tasks.map((t) => (
            <div key={t.id} className="rounded-xl border border-border bg-card p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {taskBadge(t.status)}
                  <span className="text-sm font-medium">{t.title}</span>
                </div>
                <div className="flex items-center gap-2">
                  {t.status === "proposed" && (
                    <>
                      <button onClick={() => approveTask(t.id)} className="rounded-md bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-500 hover:bg-emerald-500/25">Approve</button>
                      <button onClick={() => rejectTask(t.id)} className="rounded-md bg-red-500/15 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-500/25">Reject</button>
                    </>
                  )}
                  {(t.status === "approved" || t.status === "failed") && (
                    <button onClick={() => runTask(t.id)} disabled={runningTask === t.id || selected.status !== "active"}
                      className="rounded-md bg-accent px-2 py-1 text-xs font-semibold text-on-accent hover:brightness-110 disabled:opacity-50">
                      {runningTask === t.id ? "Running…" : "▶ Run"}
                    </button>
                  )}
                  <button onClick={() => setExpandedTask(expandedTask === t.id ? null : t.id)}
                    className="rounded-md border border-border px-2 py-1 text-xs text-muted hover:bg-background">
                    {expandedTask === t.id ? "Hide" : "Details"}
                  </button>
                </div>
              </div>
              {t.description && <p className="mt-1 text-xs text-muted">{t.description}</p>}
              {t.error && <p className="mt-1 text-xs text-red-400">{t.error}</p>}
              {expandedTask === t.id && (
                <div className="mt-2 space-y-2 border-t border-border pt-2">
                  {t.result?.reply && (
                    <div>
                      <div className="text-[10px] font-semibold text-muted">AGENT REPLY</div>
                      <p className="mt-0.5 text-sm">{t.result.reply}</p>
                    </div>
                  )}
                  {t.result?.trace && t.result.trace.length > 0 && (
                    <div>
                      <div className="text-[10px] font-semibold text-muted">TOOL TRACE ({t.result.trace.length} calls)</div>
                      <div className="mt-1 space-y-1">
                        {t.result.trace.map((tr, i) => (
                          <div key={i} className="rounded-md bg-background px-2 py-1 text-xs">
                            <span className="font-mono text-accent">{tr.tool}</span>
                            <span className="text-muted"> {JSON.stringify(tr.args).slice(0, 120)}</span>
                            {tr.result?.error ? <span className="text-red-400"> → {String(tr.result.error).slice(0, 100)}</span> : null}
                            {tr.result?.created ? <span className="text-emerald-500"> → created</span> : null}
                            {tr.result?.updated ? <span className="text-emerald-500"> → updated</span> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="text-[10px] text-muted">{t.steps} steps · {t.tokens_used} tokens</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ---------- list view ----------
  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">🤖 AI Employees</h1>
        <button onClick={() => setShowHire((v) => !v)} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent hover:brightness-110">
          {showHire ? "Close" : "+ Hire agent"}
        </button>
      </div>
      <p className="mt-1 text-sm text-muted">
        Hire AI employees that work your business data autonomously. Each agent operates under its own
        permissions, follows its persona, and every action is audited. Assign tasks, approve the ones that
        need a human eye, and watch them work.
      </p>

      {showHire && (
        <form onSubmit={hire} className="mt-4 space-y-3 rounded-xl border border-border bg-card p-4">
          <div className="grid grid-cols-2 gap-3">
            <input className={inputCls} placeholder="Name (e.g. Sam the SDR)" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <input className={inputCls} placeholder="Role (e.g. Sales Development Rep)" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })} />
          </div>
          <textarea className={inputCls} rows={2} placeholder="Persona — how should this employee behave? (optional)" value={form.persona}
            onChange={(e) => setForm({ ...form, persona: e.target.value })} />
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">Icon:</span>
            {AGENT_ICONS.map((ic) => (
              <button key={ic} type="button" onClick={() => setForm({ ...form, icon: ic })}
                className={`rounded-md p-1 text-lg ${form.icon === ic ? "bg-accent/20 ring-1 ring-accent" : "hover:bg-card"}`}>
                {ic}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted">Permission level</label>
              <select className={inputCls} value={form.permission_role}
                onChange={(e) => setForm({ ...form, permission_role: e.target.value })}>
                <option value="member">Member (can edit records)</option>
                <option value="viewer">Viewer (read-only)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted">Token budget (0 = unlimited)</label>
              <input className={inputCls} type="number" min={0} value={form.budget_tokens}
                onChange={(e) => setForm({ ...form, budget_tokens: parseInt(e.target.value) || 0 })} />
            </div>
          </div>
          {error && <div className="text-xs text-danger">{error}</div>}
          <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent hover:brightness-110 disabled:opacity-50">
            {busy ? "Hiring…" : "Hire agent"}
          </button>
        </form>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.length === 0 && !showHire && (
          <div className="col-span-full rounded-xl border border-dashed border-border p-8 text-center">
            <div className="text-3xl">🤖</div>
            <p className="mt-2 text-sm text-muted">No AI employees yet. Hire your first one to start automating work.</p>
          </div>
        )}
        {agents.map((a) => (
          <button key={a.id} onClick={() => setSelected(a)}
            className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-accent/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{a.icon}</span>
                <div>
                  <div className="font-semibold">{a.name}</div>
                  <div className="text-xs text-muted">{a.role || "General assistant"}</div>
                </div>
              </div>
              {statusBadge(a.status)}
            </div>
            <div className="mt-3 flex items-center gap-4 text-xs text-muted">
              <span>{a.runs_count} runs</span>
              <span>{a.tokens_used.toLocaleString()} tokens</span>
            </div>
          </button>
        ))}
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
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(() => {
    api<typeof events>("/api/events?limit=50").then(setEvents).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const types = useMemo(() => {
    const s = new Set(events.map((e) => e.type));
    return [...s].sort();
  }, [events]);

  const shown = filter ? events.filter((e) => e.type === filter) : events;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">⚡ Events</h1>
          <p className="mt-1 text-sm text-muted">
            The event seam — every action in the kernel lands here. Automation, analytics forwarding,
            and AI context all plug into this stream.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-border-strong hover:text-foreground"
        >
          <RotateCcw size={12} /> Refresh
        </button>
      </div>

      {types.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          <button
            onClick={() => setFilter("")}
            className={`rounded-full px-2.5 py-1 text-xs transition ${
              filter === "" ? "bg-accent text-on-accent" : "bg-card text-muted hover:text-foreground"
            }`}
          >
            All ({events.length})
          </button>
          {types.map((t) => (
            <button
              key={t}
              onClick={() => setFilter(filter === t ? "" : t)}
              className={`rounded-full px-2.5 py-1 font-mono text-xs transition ${
                filter === t ? "bg-accent text-on-accent" : "bg-card text-muted hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 space-y-2">
        {shown.map((e) => (
          <div key={e.id} className="rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
            <button
              onClick={() => setExpanded(expanded === e.id ? null : e.id)}
              className="flex w-full items-center justify-between gap-3 text-left"
            >
              <span className="font-mono text-xs text-accent">{e.type}</span>
              <span className="text-[11px] text-muted">
                {e.plugin_id && <span className="mr-2">🧩 {e.plugin_id}</span>}
                {new Date(e.created_at).toLocaleTimeString()}
                <span className="ml-2 text-faint">{expanded === e.id ? "▾" : "▸"}</span>
              </span>
            </button>
            {expanded === e.id && (
              <pre className="mt-2 overflow-x-auto rounded-lg bg-background p-3 text-[11px] leading-relaxed text-muted">
                {JSON.stringify(e.payload, null, 2)}
              </pre>
            )}
          </div>
        ))}
        {shown.length === 0 && (
          <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
            {filter ? `No events of type ${filter}.` : "No events yet."}
          </div>
        )}
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

/* ---------------- Workspace (settings, members, invites, roles) ---------------- */

const ROLE_BADGE: Record<string, string> = {
  owner: "bg-accent text-on-accent",
  admin: "bg-accent-soft text-accent",
  member: "bg-card-2 text-foreground",
  viewer: "bg-card-2 text-muted",
};

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ROLE_BADGE[role] ?? ROLE_BADGE.member}`}>
      {role}
    </span>
  );
}

function WorkspaceView({ me, onMeChanged }: { me: Me; onMeChanged: () => Promise<void> }) {
  const [tab, setTab] = useState<"general" | "members" | "invites" | "roles" | "danger">("general");
  const [ws, setWs] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [confirmDeleteWs, setConfirmDeleteWs] = useState(false);
  const router = useRouter();

  const isAdmin = me.role === "owner" || me.role === "admin";
  const isOwner = me.role === "owner";

  const load = useCallback(async () => {
    try {
      const [w, m, i, r] = await Promise.all([
        api<Workspace>("/api/workspace"),
        api<Member[]>("/api/workspace/members"),
        api<Invite[]>("/api/workspace/invites"),
        api<RoleInfo[]>("/api/workspace/roles"),
      ]);
      setWs(w);
      setMembers(m);
      setInvites(i);
      setRoles(r);
      setForm({
        name: w.name,
        description: w.description,
        website: w.website,
        industry: w.industry,
        company_size: w.company_size,
        logo_url: w.logo_url,
        timezone: w.timezone,
        locale: w.locale,
      });
    } catch {
      /* non-admin may lack invite access; workspace + members still load above */
    }
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  async function saveWorkspace(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/workspace", { method: "PATCH", body: form });
      toast("Workspace settings saved", "success");
      await load();
      await onMeChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Save failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setBusy(true);
    try {
      await api("/api/workspace/invites", { method: "POST", body: { email: inviteEmail.trim(), role: inviteRole } });
      toast(`Invite sent to ${inviteEmail}`, "success");
      setInviteEmail("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Invite failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(membershipId: string, role: string) {
    setBusy(true);
    try {
      await api(`/api/workspace/members/${membershipId}`, { method: "PATCH", body: { role } });
      toast("Role updated", "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Role change failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(membershipId: string) {
    setBusy(true);
    try {
      await api(`/api/workspace/members/${membershipId}`, { method: "DELETE" });
      toast("Member removed", "success");
      setConfirmRemove(null);
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Remove failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function revokeInvite(id: string) {
    setBusy(true);
    try {
      await api(`/api/workspace/invites/${id}`, { method: "DELETE" });
      toast("Invite revoked", "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Revoke failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function deleteWorkspace() {
    setBusy(true);
    try {
      await api("/api/workspace", { method: "DELETE" });
      toast("Workspace deleted", "success");
      setToken(null);
      router.replace("/login");
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
      setBusy(false);
    }
  }

  function copyInviteLink(token: string) {
    const link = `${window.location.origin}/invite?token=${token}`;
    navigator.clipboard.writeText(link).then(
      () => toast("Invite link copied", "success"),
      () => toast("Copy failed", "error")
    );
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition focus:border-accent disabled:opacity-50";
  const tabs = [
    { id: "general" as const, label: "General", icon: <Boxes size={13} /> },
    { id: "members" as const, label: `Members (${members.length})`, icon: <Users size={13} /> },
    { id: "invites" as const, label: "Invites", icon: <UserPlus size={13} /> },
    { id: "roles" as const, label: "Roles & permissions", icon: <Shield size={13} /> },
    ...(isOwner ? [{ id: "danger" as const, label: "Danger zone", icon: <Trash2 size={13} /> }] : []),
  ];

  return (
    <div className="max-w-4xl">
      <h1 className="flex items-center gap-2 text-xl font-bold">
        <Boxes size={20} /> Workspace
      </h1>
      <p className="mt-1 text-sm text-muted">
        Namespace, profile, members and access control for <span className="font-mono text-accent">{me.tenant_slug}</span>.
      </p>

      <div className="mt-4 flex flex-wrap gap-1 border-b border-border pb-px">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition ${
              tab === t.id
                ? "border-accent font-semibold text-accent"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ---- General ---- */}
      {tab === "general" && ws && (
        <form onSubmit={saveWorkspace} className="mt-6 space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Workspace name</span>
              <input className={inputCls} value={form.name ?? ""} disabled={!isAdmin}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Namespace (slug)</span>
              <div className="flex items-center gap-1 rounded-lg border border-border bg-card-2 px-3 py-1.5 text-sm">
                <span className="text-faint">truss.app/</span>
                <span className="font-mono">{ws.slug}</span>
              </div>
            </label>
            <label className="block text-xs md:col-span-2">
              <span className="mb-1 block text-muted">Description</span>
              <textarea className={inputCls} rows={2} value={form.description ?? ""} disabled={!isAdmin}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Website</span>
              <input className={inputCls} value={form.website ?? ""} disabled={!isAdmin} placeholder="https://…"
                onChange={(e) => setForm({ ...form, website: e.target.value })} />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Industry</span>
              <input className={inputCls} value={form.industry ?? ""} disabled={!isAdmin} placeholder="Software, Retail, …"
                onChange={(e) => setForm({ ...form, industry: e.target.value })} />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Company size</span>
              <select className={inputCls} value={form.company_size ?? ""} disabled={!isAdmin}
                onChange={(e) => setForm({ ...form, company_size: e.target.value })}>
                <option value="">—</option>
                {["1", "2-10", "11-50", "51-200", "201-1000", "1000+"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Logo URL</span>
              <input className={inputCls} value={form.logo_url ?? ""} disabled={!isAdmin} placeholder="https://…/logo.png"
                onChange={(e) => setForm({ ...form, logo_url: e.target.value })} />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Timezone</span>
              <input className={inputCls} value={form.timezone ?? ""} disabled={!isAdmin} placeholder="Asia/Kolkata"
                onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Locale</span>
              <input className={inputCls} value={form.locale ?? ""} disabled={!isAdmin} placeholder="en-US"
                onChange={(e) => setForm({ ...form, locale: e.target.value })} />
            </label>
          </div>
          {isAdmin && (
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "Saving…" : "Save workspace settings"}
            </button>
          )}
          {!isAdmin && (
            <p className="text-xs text-muted">You need admin rights to edit workspace settings.</p>
          )}
        </form>
      )}

      {/* ---- Members ---- */}
      {tab === "members" && (
        <div className="mt-6">
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-card text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-3 py-2 font-medium">Member</th>
                  <th className="px-3 py-2 font-medium">Title</th>
                  <th className="px-3 py-2 font-medium">Role</th>
                  <th className="px-3 py-2 font-medium">Last active</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {members.map((m) => {
                  const isSelf = m.user.id === me.user_id;
                  const canManage = isAdmin && m.role !== "owner" && !isSelf;
                  return (
                    <tr key={m.membership_id} className="border-b border-border/50 last:border-0 hover:bg-card/50">
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent">
                            {(m.user.full_name || m.user.email).slice(0, 1).toUpperCase()}
                          </span>
                          <div className="min-w-0">
                            <div className="truncate font-medium">
                              {m.user.full_name || m.user.email}
                              {isSelf && <span className="ml-1.5 text-[10px] text-faint">(you)</span>}
                            </div>
                            <div className="truncate text-xs text-muted">{m.user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted">{m.user.title || "—"}</td>
                      <td className="px-3 py-2.5">
                        {canManage ? (
                          <select
                            value={m.role}
                            disabled={busy}
                            onChange={(e) => changeRole(m.membership_id, e.target.value)}
                            className="rounded-lg border border-border bg-background px-2 py-1 text-xs outline-none focus:border-accent"
                          >
                            {(me.role === "owner" ? ["admin", "member", "viewer"] : ["member", "viewer"]).map((r) => (
                              <option key={r} value={r}>{r}</option>
                            ))}
                          </select>
                        ) : (
                          <RoleBadge role={m.role} />
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted">
                        {m.user.last_login_at ? new Date(m.user.last_login_at).toLocaleString() : "never"}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {canManage && (
                          confirmRemove === m.membership_id ? (
                            <span className="flex items-center justify-end gap-1">
                              <button onClick={() => removeMember(m.membership_id)}
                                className="rounded-md bg-danger/15 px-2 py-1 text-[11px] font-semibold text-danger hover:bg-danger/25">
                                Confirm
                              </button>
                              <button onClick={() => setConfirmRemove(null)}
                                className="rounded-md px-1.5 py-1 text-[11px] text-muted hover:text-foreground">
                                Cancel
                              </button>
                            </span>
                          ) : (
                            <button onClick={() => setConfirmRemove(m.membership_id)} title="Remove member"
                              className="rounded-md p-1.5 text-muted transition hover:bg-danger/15 hover:text-danger">
                              <Trash2 size={13} />
                            </button>
                          )
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---- Invites ---- */}
      {tab === "invites" && (
        <div className="mt-6 space-y-5">
          {isAdmin && (
            <form onSubmit={sendInvite} className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-card p-4">
              <label className="block flex-1 text-xs">
                <span className="mb-1 block text-muted">Email address</span>
                <input className={inputCls} type="email" required value={inviteEmail} placeholder="teammate@company.com"
                  onChange={(e) => setInviteEmail(e.target.value)} />
              </label>
              <label className="block text-xs">
                <span className="mb-1 block text-muted">Role</span>
                <select className={inputCls + " w-32"} value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                  {(me.role === "owner" ? ["admin", "member", "viewer"] : ["member", "viewer"]).map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>
              <button disabled={busy || !inviteEmail.trim()}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                <UserPlus size={14} /> Send invite
              </button>
            </form>
          )}

          <div className="space-y-2">
            {invites.map((i) => (
              <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
                <div className="min-w-0">
                  <span className="font-medium">{i.email}</span>
                  <span className="ml-2"><RoleBadge role={i.role} /></span>
                  <span className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    i.status === "pending" ? "bg-accent-soft text-accent"
                    : i.status === "accepted" ? "bg-success/15 text-success"
                    : "bg-card-2 text-faint"
                  }`}>
                    {i.status}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted">
                  {i.status === "pending" && (
                    <>
                      <span>expires {new Date(i.expires_at).toLocaleDateString()}</span>
                      {isAdmin && (
                        <>
                          <button onClick={() => copyInviteLink(i.token)} title="Copy invite link"
                            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 transition hover:border-border-strong hover:text-foreground">
                            <Copy size={11} /> Link
                          </button>
                          <button onClick={() => revokeInvite(i.id)}
                            className="rounded-md px-2 py-1 text-danger/80 transition hover:bg-danger/10 hover:text-danger">
                            Revoke
                          </button>
                        </>
                      )}
                    </>
                  )}
                  {i.status !== "pending" && <span>{i.accepted_at ? `accepted ${new Date(i.accepted_at).toLocaleDateString()}` : ""}</span>}
                </div>
              </div>
            ))}
            {invites.length === 0 && (
              <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
                No invites yet{isAdmin ? " — send one above." : "."}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ---- Roles matrix ---- */}
      {tab === "roles" && (
        <div className="mt-6 overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-3 py-2 font-medium">Capability</th>
                {roles.map((r) => (
                  <th key={r.role} className="px-3 py-2 text-center font-medium">{r.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {roles.length > 0 &&
                Object.keys(roles[0].capabilities).map((cap) => (
                  <tr key={cap} className="border-b border-border/50 last:border-0">
                    <td className="px-3 py-2 text-xs">
                      {cap.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </td>
                    {roles.map((r) => (
                      <td key={r.role} className="px-3 py-2 text-center">
                        {r.capabilities[cap] ? (
                          <Check size={14} className="mx-auto text-success" />
                        ) : (
                          <X size={14} className="mx-auto text-faint" />
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
          <div className="space-y-1 border-t border-border bg-card/50 px-4 py-3">
            {roles.map((r) => (
              <p key={r.role} className="text-[11px] text-muted">
                <span className="font-semibold text-foreground">{r.label}:</span> {r.description}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* ---- Danger zone ---- */}
      {tab === "danger" && isOwner && (
        <div className="mt-6 rounded-xl border border-danger/40 bg-danger/5 p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-danger">
            <Trash2 size={15} /> Delete this workspace
          </h2>
          <p className="mt-1 text-xs text-muted">
            Permanently deletes <span className="font-mono">{me.tenant_slug}</span> — all members, records,
            plugins, automations and connectors. This cannot be undone.
          </p>
          {confirmDeleteWs ? (
            <div className="mt-3 flex items-center gap-2">
              <button onClick={deleteWorkspace} disabled={busy}
                className="rounded-lg bg-danger px-4 py-1.5 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-50">
                {busy ? "Deleting…" : "Yes, delete everything"}
              </button>
              <button onClick={() => setConfirmDeleteWs(false)}
                className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted hover:text-foreground">
                Cancel
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirmDeleteWs(true)}
              className="mt-3 rounded-lg border border-danger/50 px-4 py-1.5 text-sm font-semibold text-danger transition hover:bg-danger/10">
              Delete workspace…
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Profile ---------------- */

function ProfileView({ me, onMeChanged }: { me: Me; onMeChanged: () => Promise<void> }) {
  const [form, setForm] = useState({
    full_name: me.full_name ?? "",
    title: me.title ?? "",
    phone: me.phone ?? "",
    avatar_url: me.avatar_url ?? "",
    timezone: me.timezone ?? "UTC",
    locale: me.locale ?? "en-US",
  });
  const [busy, setBusy] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [pwBusy, setPwBusy] = useState(false);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/auth/profile", { method: "PATCH", body: form });
      toast("Profile saved", "success");
      await onMeChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Save failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    if (pw.next !== pw.confirm) {
      toast("New passwords do not match", "error");
      return;
    }
    setPwBusy(true);
    try {
      await api("/api/auth/password", { method: "POST", body: { current_password: pw.current, new_password: pw.next } });
      toast("Password changed", "success");
      setPw({ current: "", next: "", confirm: "" });
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Password change failed", "error");
    } finally {
      setPwBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition focus:border-accent";

  return (
    <div className="max-w-2xl">
      <h1 className="flex items-center gap-2 text-xl font-bold">
        <UserCircle size={20} /> Profile
      </h1>
      <p className="mt-1 text-sm text-muted">
        Your personal details, visible to teammates in {me.tenant_name}.
      </p>

      {/* identity card */}
      <div className="mt-6 flex items-center gap-4 rounded-xl border border-border bg-card p-5">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-xl font-bold text-accent">
          {(me.full_name || me.email).slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0">
          <div className="truncate font-semibold">{me.full_name || me.email}</div>
          <div className="truncate text-xs text-muted">{me.email}</div>
          <div className="mt-1 flex items-center gap-2">
            <RoleBadge role={me.role} />
            {me.last_login_at && (
              <span className="text-[10px] text-faint">
                last login {new Date(me.last_login_at).toLocaleString()}
              </span>
            )}
          </div>
        </div>
      </div>

      <form onSubmit={saveProfile} className="mt-6 space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Full name</span>
            <input className={inputCls} value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Job title</span>
            <input className={inputCls} value={form.title} placeholder="Founder, Sales lead, …"
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Phone</span>
            <input className={inputCls} value={form.phone} placeholder="+91 …"
              onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Avatar URL</span>
            <input className={inputCls} value={form.avatar_url} placeholder="https://…/me.png"
              onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Timezone</span>
            <input className={inputCls} value={form.timezone} placeholder="Asia/Kolkata"
              onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Locale</span>
            <input className={inputCls} value={form.locale} placeholder="en-US"
              onChange={(e) => setForm({ ...form, locale: e.target.value })} />
          </label>
        </div>
        <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
          {busy ? "Saving…" : "Save profile"}
        </button>
      </form>

      {/* password */}
      <form onSubmit={changePassword} className="mt-8 rounded-xl border border-border bg-card p-5">
        <h2 className="text-sm font-semibold">Change password</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Current</span>
            <input className={inputCls} type="password" required value={pw.current}
              onChange={(e) => setPw({ ...pw, current: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">New (min 8)</span>
            <input className={inputCls} type="password" required minLength={8} value={pw.next}
              onChange={(e) => setPw({ ...pw, next: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Confirm new</span>
            <input className={inputCls} type="password" required value={pw.confirm}
              onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
          </label>
        </div>
        <button disabled={pwBusy || !pw.current || !pw.next}
          className="mt-3 rounded-lg border border-border px-4 py-1.5 text-sm font-medium transition hover:border-border-strong disabled:opacity-50">
          {pwBusy ? "Changing…" : "Update password"}
        </button>
      </form>
    </div>
  );
}
