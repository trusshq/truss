"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  BookOpen,
  Boxes,
  Cable,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Code2,
  Cog,
  Coins,
  Command,
  Copy,
  Database,
  Download,
  FileText,
  FileSignature,
  FolderKanban,
  History,
  Home,
  Inbox,
  Info,
  Kanban,
  LayoutGrid,
  LifeBuoy,
  LogOut,
  Megaphone,
  Menu,
  MessageSquare,
  Monitor,
  Moon,
  Network,
  Palette,
  Package,
  Paperclip,
  Pencil,
  Plug,
  Puzzle,
  Receipt,
  Repeat,
  RotateCcw,
  Search,
  Send,
  Shield,
  Store,
  Sun,
  Target,
  Trash2,
  Truck,
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
  type AgentScorecard,
  type AgentTaskInfo,
  type AiKeyInfo,
  type AnalyticsResult,
  type ApiKeyInfo,
  type BudgetLedger,
  type GoalInfo,
  type GlobalSearchResult,
  type HistoryEntry,
  type NotificationInfo,
  type ObjectCount,
  type OrgNode,
  type PipelineInfo,
  type PipelineRunResult,
  type ReviewInbox,
  type ScheduleInfo,
  type TaskCommentInfo,
  type TimelineItem,
  type TrashItem,
  type TriggerInfo,
  type WorkspaceOverview,
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
import { ACCENT_PRESETS, useTheme, type Density, type FontFamily, type FontScale, type Motion, type Radius, type ThemeMode } from "@/lib/theme";

type View =
  | { kind: "home" }
  | { kind: "chat" }
  | { kind: "object"; slug: string }
  | { kind: "kanban"; slug: string; object: string; groupBy: string }
  | { kind: "apphome"; slug: string; label: string; icon: string; objects: string[] }
  | { kind: "plugins" }
  | { kind: "marketplace" }
  | { kind: "events" }
  | { kind: "ai" }
  | { kind: "agents" }
  | { kind: "aihub" }
  | { kind: "org" }
  | { kind: "goals" }
  | { kind: "review" }
  | { kind: "autopilot" }
  | { kind: "insights" }
  | { kind: "reports" }
  | { kind: "forms" }
  | { kind: "files" }
  | { kind: "calendar" }
  | { kind: "kb" }
  | { kind: "time" }
  | { kind: "expenses" }
  | { kind: "projects" }
  | { kind: "inventory" }
  | { kind: "hr" }
  | { kind: "approvals" }
  | { kind: "quotes" }
  | { kind: "purchase_orders" }
  | { kind: "contracts" }
  | { kind: "tickets" }
  | { kind: "campaigns" }
  | { kind: "assets" }
  | { kind: "subscriptions" }
  | { kind: "developer" }
  | { kind: "automations" }
  | { kind: "connectors" }
  | { kind: "settings" }
  | { kind: "workspace" }
  | { kind: "billing" }
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
  homeSurfaces,
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
  homeSurfaces: { label: string; icon: string; slug: string; objects: string[] }[];
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

      {/* Nav — the only scrollable region; header & footer stays pinned */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        <NavItem
          active={view.kind === "home"}
          onClick={() => go({ kind: "home" })}
          icon={<Home size={15} />}
          label="Home"
        />
        <NavItem
          active={view.kind === "chat"}
          onClick={() => go({ kind: "chat" })}
          icon={<MessageSquare size={15} />}
          label="Chat"
        />

        {/* Apps — app homes + every table view, grouped in one dropdown */}
        <NavSection
          icon={<LayoutGrid size={15} />}
          label="Apps"
          count={homeSurfaces.length + tableSurfaces.length}
          open={openSections.apps}
          onToggle={() => toggleSection("apps")}
          active={view.kind === "object" || view.kind === "apphome"}
        >
          {homeSurfaces.length === 0 && tableSurfaces.length === 0 && (
            <div className="px-2 py-1 text-xs text-muted">Install a plugin to see its apps →</div>
          )}
          {homeSurfaces.map((s) => (
            <NavItem
              key={s.slug}
              active={view.kind === "apphome" && view.slug === s.slug}
              onClick={() => go({ kind: "apphome", slug: s.slug, label: s.label, icon: s.icon, objects: s.objects })}
              icon={<span className="text-[13px] leading-none">{s.icon}</span>}
              label={`${s.label} Home`}
            />
          ))}
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

        {/* AI Employees — the hub: overview, roster, org chart, goals, review, autopilot */}
        <NavSection
          icon={<Bot size={15} />}
          label="AI Employees"
          open={openSections.aihub}
          onToggle={() => toggleSection("aihub")}
          active={["aihub", "agents", "org", "goals", "review", "autopilot"].includes(view.kind)}
        >
          <NavItem active={view.kind === "aihub"} onClick={() => go({ kind: "aihub" })} icon={<LayoutGrid size={15} />} label="Overview" />
          <NavItem active={view.kind === "agents"} onClick={() => go({ kind: "agents" })} icon={<Users size={15} />} label="Employees" />
          <NavItem active={view.kind === "org"} onClick={() => go({ kind: "org" })} icon={<Network size={15} />} label="Org Chart" />
          <NavItem active={view.kind === "goals"} onClick={() => go({ kind: "goals" })} icon={<Target size={15} />} label="Goals" />
          <NavItem active={view.kind === "review"} onClick={() => go({ kind: "review" })} icon={<Inbox size={15} />} label="Review Inbox" />
          <NavItem active={view.kind === "autopilot"} onClick={() => go({ kind: "autopilot" })} icon={<Zap size={15} />} label="Autopilot" />
        </NavSection>

        {/* Marketplace — standalone top-level section */}
        <NavItem
          active={view.kind === "marketplace"}
          onClick={() => go({ kind: "marketplace" })}
          icon={<Store size={15} />}
          label="Marketplace"
        />

        {/* Insights — standalone */}
        <NavItem
          active={view.kind === "insights"}
          onClick={() => go({ kind: "insights" })}
          icon={<BarChart3 size={15} />}
          label="Insights"
        />

        {/* Reports — standalone */}
        <NavItem
          active={view.kind === "reports"}
          onClick={() => go({ kind: "reports" })}
          icon={<FileText size={15} />}
          label="Reports"
        />

        {/* Forms — standalone */}
        <NavItem
          active={view.kind === "forms"}
          onClick={() => go({ kind: "forms" })}
          icon={<Inbox size={15} />}
          label="Forms"
        />

        {/* Files — standalone */}
        <NavItem
          active={view.kind === "files"}
          onClick={() => go({ kind: "files" })}
          icon={<Paperclip size={15} />}
          label="Files"
        />

        {/* Calendar — standalone */}
        <NavItem
          active={view.kind === "calendar"}
          onClick={() => go({ kind: "calendar" })}
          icon={<CalendarDays size={15} />}
          label="Calendar"
        />

        {/* Knowledge Base — standalone */}
        <NavItem
          active={view.kind === "kb"}
          onClick={() => go({ kind: "kb" })}
          icon={<BookOpen size={15} />}
          label="Knowledge Base"
        />

        {/* Time Tracking — standalone */}
        <NavItem
          active={view.kind === "time"}
          onClick={() => go({ kind: "time" })}
          icon={<Clock size={15} />}
          label="Time Tracking"
        />

        {/* Expenses — standalone */}
        <NavItem
          active={view.kind === "expenses"}
          onClick={() => go({ kind: "expenses" })}
          icon={<Receipt size={15} />}
          label="Expenses"
        />

        {/* Projects — standalone */}
        <NavItem
          active={view.kind === "projects"}
          onClick={() => go({ kind: "projects" })}
          icon={<FolderKanban size={15} />}
          label="Projects"
        />

        {/* Inventory — standalone */}
        <NavItem
          active={view.kind === "inventory"}
          onClick={() => go({ kind: "inventory" })}
          icon={<Package size={15} />}
          label="Inventory"
        />

        {/* HR / People — standalone */}
        <NavItem
          active={view.kind === "hr"}
          onClick={() => go({ kind: "hr" })}
          icon={<Users size={15} />}
          label="People"
        />

        {/* Approvals — unified inbox */}
        <NavItem
          active={view.kind === "approvals"}
          onClick={() => go({ kind: "approvals" })}
          icon={<CheckCircle2 size={15} />}
          label="Approvals"
        />

        {/* Quotes — sales quotes & proposals */}
        <NavItem
          active={view.kind === "quotes"}
          onClick={() => go({ kind: "quotes" })}
          icon={<FileText size={15} />}
          label="Quotes"
        />

        {/* Purchase Orders — procurement */}
        <NavItem
          active={view.kind === "purchase_orders"}
          onClick={() => go({ kind: "purchase_orders" })}
          icon={<Truck size={15} />}
          label="Purchase Orders"
        />

        {/* Contracts — renewals & value tracking */}
        <NavItem
          active={view.kind === "contracts"}
          onClick={() => go({ kind: "contracts" })}
          icon={<FileSignature size={15} />}
          label="Contracts"
        />

        {/* Tickets — support helpdesk */}
        <NavItem
          active={view.kind === "tickets"}
          onClick={() => go({ kind: "tickets" })}
          icon={<LifeBuoy size={15} />}
          label="Tickets"
        />

        {/* Campaigns — marketing */}
        <NavItem
          active={view.kind === "campaigns"}
          onClick={() => go({ kind: "campaigns" })}
          icon={<Megaphone size={15} />}
          label="Campaigns"
        />

        {/* Assets — company asset tracking */}
        <NavItem
          active={view.kind === "assets"}
          onClick={() => go({ kind: "assets" })}
          icon={<Package size={15} />}
          label="Assets"
        />

        {/* Subscriptions — recurring billing & MRR */}
        <NavItem
          active={view.kind === "subscriptions"}
          onClick={() => go({ kind: "subscriptions" })}
          icon={<Repeat size={15} />}
          label="Subscriptions"
        />

        {/* Automations — automations, connectors, events */}
        <NavSection
          icon={<Cog size={15} />}
          label="Automations"
          open={openSections.automations}
          onToggle={() => toggleSection("automations")}
          active={["automations", "connectors", "events"].includes(view.kind)}
        >
          <NavItem active={view.kind === "automations"} onClick={() => go({ kind: "automations" })} icon={<Cog size={15} />} label="Automations" />
          {me.role !== "viewer" && (
            <NavItem active={view.kind === "connectors"} onClick={() => go({ kind: "connectors" })} icon={<Cable size={15} />} label="Connectors" />
          )}
          <NavItem active={view.kind === "events"} onClick={() => go({ kind: "events" })} icon={<Zap size={15} />} label="Audit Log" />
        </NavSection>

        {/* Developer — standalone */}
        <NavItem
          active={view.kind === "developer"}
          onClick={() => go({ kind: "developer" })}
          icon={<Code2 size={15} />}
          label="Developer"
        />

        {/* Plugins — standalone */}
        <NavItem
          active={view.kind === "plugins"}
          onClick={() => go({ kind: "plugins" })}
          icon={<Puzzle size={15} />}
          label="Plugins"
        />

        {/* Account — workspace, profile, appearance */}
        <NavSection
          icon={<UserCircle size={15} />}
          label="Account"
          open={openSections.account}
          onToggle={() => toggleSection("account")}
          active={["workspace", "profile", "settings", "billing"].includes(view.kind)}
        >
          <NavItem active={view.kind === "workspace"} onClick={() => go({ kind: "workspace" })} icon={<Boxes size={15} />} label="Workspace" badge={me.role} />
          <NavItem active={view.kind === "billing"} onClick={() => go({ kind: "billing" })} icon={<Coins size={15} />} label="Billing" />
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
          <NotificationsBell />
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
    const defaults = { apps: true, boards: true, aihub: true, automations: true, account: false };
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

  // Ctrl/Cmd+K command palette + keyboard shortcuts
  useEffect(() => {
    let lastKey = "";
    let lastTime = 0;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if (e.key === "Escape") setPaletteOpen(false);

      // ignore shortcuts while typing in inputs/textareas/selects
      const el = e.target as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;

      const k = e.key.toLowerCase();
      const now = Date.now();
      const gSeq = lastKey === "g" && now - lastTime < 900;

      if (k === "/") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("truss:focus-search"));
        lastKey = "";
        return;
      }
      if (gSeq) {
        const nav: Record<string, View> = {
          h: { kind: "home" },
          a: { kind: "agents" },
          p: { kind: "plugins" },
          m: { kind: "marketplace" },
          e: { kind: "events" },
          i: { kind: "ai" },
          s: { kind: "settings" },
        };
        if (nav[k]) {
          e.preventDefault();
          setView(nav[k]);
        }
        lastKey = "";
        return;
      }
      lastKey = k;
      lastTime = now;
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

  // App home surfaces (view: "dashboard") — polished per-plugin landing pages
  const homeSurfaces = useMemo(() => {
    const out: { label: string; icon: string; slug: string; objects: string[] }[] = [];
    for (const p of plugins.filter((p) => p.installed && p.enabled)) {
      for (const s of p.ui) {
        if (s.view === "dashboard") {
          out.push({ label: s.label, icon: s.icon, slug: s.slug, objects: s.config?.objects ?? [] });
        }
      }
    }
    return out;
  }, [plugins]);

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
    homeSurfaces,
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
            {view.kind === "chat" && <ChatView me={me} onChanged={refresh} />}
            {view.kind === "apphome" && (
              <AppHomeView
                label={view.label}
                icon={view.icon}
                objects={view.objects}
                allObjects={objects}
                setView={setView}
              />
            )}
            {view.kind === "plugins" && <PluginsView plugins={plugins} onChanged={refresh} />}
            {view.kind === "marketplace" && <MarketplaceView onChanged={refresh} />}
            {view.kind === "events" && <EventsView />}
            {view.kind === "ai" && <AiView onChanged={refresh} />}
            {view.kind === "aihub" && <AiHubView onChanged={refresh} />}
            {view.kind === "agents" && <AgentsView onChanged={refresh} />}
            {view.kind === "org" && <OrgView onChanged={refresh} />}
            {view.kind === "goals" && <GoalsView onChanged={refresh} />}
            {view.kind === "review" && <ReviewView onChanged={refresh} />}
            {view.kind === "autopilot" && <AutopilotView onChanged={refresh} />}
            {view.kind === "insights" && <InsightsView />}
            {view.kind === "developer" && <DeveloperView />}
            {view.kind === "automations" && <AutomationsView />}
            {view.kind === "connectors" && <ConnectorsView />}
            {view.kind === "settings" && <SettingsView />}
            {view.kind === "workspace" && <WorkspaceView me={me} onMeChanged={refresh} />}
            {view.kind === "billing" && <BillingView isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "reports" && <ReportsView canEdit={me.role !== "viewer"} />}
            {view.kind === "forms" && <FormsView isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "files" && <FilesView canEdit={me.role !== "viewer"} />}
            {view.kind === "calendar" && <CalendarView canEdit={me.role !== "viewer"} />}
            {view.kind === "kb" && <KBView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "time" && <TimeView canEdit={me.role !== "viewer"} />}
            {view.kind === "expenses" && <ExpensesView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "projects" && <ProjectsView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "inventory" && <InventoryView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "hr" && <HRView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "approvals" && <ApprovalsView isAdmin={me.role === "owner" || me.role === "admin"} setView={setView} />}
            {view.kind === "quotes" && <QuotesView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "purchase_orders" && <PurchaseOrdersView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "contracts" && <ContractsView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "tickets" && <TicketsView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "campaigns" && <CampaignsView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "assets" && <AssetsView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
            {view.kind === "subscriptions" && <SubscriptionsView canEdit={me.role !== "viewer"} isAdmin={me.role === "owner" || me.role === "admin"} />}
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
  const [aiKeysCount, setAiKeysCount] = useState(0);
  const [agentsCount, setAgentsCount] = useState(0);
  const [membersCount, setMembersCount] = useState(1);
  const [checklistDismissed, setChecklistDismissed] = useState(false);
  const [kpis, setKpis] = useState<Record<string, number> | null>(null);

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
    // onboarding signals
    api<AiKeyInfo[]>("/api/ai/keys").then((k) => setAiKeysCount(k.length)).catch(() => {});
    api<AgentInfo[]>("/api/agents").then((a) => setAgentsCount(a.length)).catch(() => {});
    api<{ members?: unknown[] } | unknown[]>("/api/workspace/members")
      .then((m) => setMembersCount(Array.isArray(m) ? m.length : (m as { members?: unknown[] }).members?.length ?? 1))
      .catch(() => {});
    // Phase W: unified KPI snapshot across all modules
    api<Record<string, number>>("/api/dashboard")
      .then(setKpis)
      .catch(() => {});
  }, [objects]);

  const totalRecords = Object.values(counts).reduce((a, b) => a + b, 0);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  // onboarding checklist — computed from live workspace state
  const checklist = [
    { label: "Install a plugin", done: enabled.length > 0, view: { kind: "marketplace" } as View },
    { label: "Create your first record", done: totalRecords > 0, view: (objects[0] ? { kind: "object", slug: objects[0].slug } : { kind: "marketplace" }) as View },
    { label: "Add an AI key", done: aiKeysCount > 0, view: { kind: "ai" } as View },
    { label: "Hire an AI employee", done: agentsCount > 0, view: { kind: "agents" } as View },
    { label: "Invite a teammate", done: membersCount > 1, view: { kind: "settings" } as View },
  ];
  const doneCount = checklist.filter((c) => c.done).length;
  const allDone = doneCount === checklist.length;

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-bold">
        {greeting}, {me.email.split("@")[0]} 👋
      </h1>
      <p className="mt-1 text-sm text-muted">
        {me.tenant_name} · {enabled.length} active plugin{enabled.length === 1 ? "" : "s"} ·{" "}
        {totalRecords} records across {objects.length} objects
      </p>

      {/* onboarding checklist */}
      {!allDone && !checklistDismissed && (
        <div className="mt-5 rounded-xl border border-accent/30 bg-accent/5 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold">🚀 Get started</span>
              <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-semibold text-accent">
                {doneCount}/{checklist.length}
              </span>
            </div>
            <button onClick={() => setChecklistDismissed(true)} className="text-xs text-muted hover:text-foreground">Dismiss</button>
          </div>
          <div className="mt-3 grid gap-1.5 sm:grid-cols-2">
            {checklist.map((c) => (
              <button
                key={c.label}
                onClick={() => !c.done && setView(c.view)}
                disabled={c.done}
                className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm transition ${
                  c.done ? "text-muted" : "hover:bg-accent/10"
                }`}
              >
                <span className={`flex h-4 w-4 items-center justify-center rounded-full border text-[10px] ${
                  c.done ? "border-success bg-success/20 text-success" : "border-border"
                }`}>
                  {c.done ? "✓" : ""}
                </span>
                <span className={c.done ? "line-through" : ""}>{c.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

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

      {/* Phase W: workspace pulse — aggregated KPIs across all modules */}
      {kpis && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-muted">Workspace pulse</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <button onClick={() => setView({ kind: "projects" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><FolderKanban size={13} /> Projects</div>
              <div className="mt-2 text-2xl font-bold">{kpis.projects_active}</div>
              <div className="mt-1 text-[11px] text-muted">active of {kpis.projects_total}</div>
            </button>
            <button onClick={() => setView({ kind: "expenses" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><Receipt size={13} /> Expenses</div>
              <div className="mt-2 text-2xl font-bold">{kpis.expenses_submitted + kpis.expenses_pending}</div>
              <div className="mt-1 text-[11px] text-muted">{kpis.expenses_submitted} awaiting review · {fmtMoney(kpis.expenses_approved_cents)} approved</div>
            </button>
            <button onClick={() => setView({ kind: "inventory" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><Package size={13} /> Inventory</div>
              <div className="mt-2 text-2xl font-bold">{kpis.products_total}</div>
              <div className={`mt-1 text-[11px] ${kpis.products_low_stock > 0 ? "text-warning" : "text-muted"}`}>
                {kpis.products_low_stock > 0 ? `${kpis.products_low_stock} low stock` : "stock healthy"}
              </div>
            </button>
            <button onClick={() => setView({ kind: "hr" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><Users size={13} /> People</div>
              <div className="mt-2 text-2xl font-bold">{kpis.employees_total}</div>
              <div className={`mt-1 text-[11px] ${kpis.leave_pending > 0 ? "text-warning" : "text-muted"}`}>
                {kpis.leave_pending > 0 ? `${kpis.leave_pending} leave pending` : "no leave pending"}
              </div>
            </button>
            <button onClick={() => setView({ kind: "calendar" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><CalendarDays size={13} /> Calendar</div>
              <div className="mt-2 text-2xl font-bold">{kpis.upcoming_events_7d}</div>
              <div className="mt-1 text-[11px] text-muted">events next 7 days</div>
            </button>
            <button onClick={() => setView({ kind: "time" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><Clock size={13} /> Time</div>
              <div className="mt-2 text-2xl font-bold">{fmtDuration(kpis.time_minutes_7d)}</div>
              <div className="mt-1 text-[11px] text-muted">logged last 7 days</div>
            </button>
            <button onClick={() => setView({ kind: "agents" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><Bot size={13} /> AI employees</div>
              <div className="mt-2 text-2xl font-bold">{kpis.agents_total}</div>
              <div className="mt-1 text-[11px] text-muted">{kpis.agents_active} active</div>
            </button>
            <button onClick={() => setView({ kind: "kb" })} className="rounded-xl border border-border bg-card p-4 text-left transition hover:border-border-strong">
              <div className="flex items-center gap-2 text-xs text-muted"><BookOpen size={13} /> Knowledge base</div>
              <div className="mt-2 text-2xl font-bold">{kpis.kb_published}</div>
              <div className="mt-1 text-[11px] text-muted">{kpis.forms_total} public form{kpis.forms_total === 1 ? "" : "s"}</div>
            </button>
          </div>
        </div>
      )}

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
  const [hits, setHits] = useState<GlobalSearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  // Debounced live global search (Phase I) — records, agents, goals
  useEffect(() => {
    if (!open) return;
    const needle = q.trim();
    if (needle.length < 2) {
      setHits(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const res = await api<GlobalSearchResult>(`/api/search?q=${encodeURIComponent(needle)}&limit=5`);
        setHits(res);
      } catch {
        setHits(null);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, open]);

  const navItems = useMemo(() => {
    const platform: { label: string; icon: React.ReactNode; view: View }[] = [
      { label: "Home", icon: <Home size={14} />, view: { kind: "home" } },
      { label: "Chat", icon: <MessageSquare size={14} />, view: { kind: "chat" } },
      { label: "Plugins", icon: <Puzzle size={14} />, view: { kind: "plugins" } },
      { label: "Marketplace", icon: <Store size={14} />, view: { kind: "marketplace" } },
      { label: "AI Keys", icon: <Bot size={14} />, view: { kind: "ai" } },
      { label: "AI Employees", icon: <Users size={14} />, view: { kind: "agents" } },
      { label: "Automations", icon: <Cog size={14} />, view: { kind: "automations" } },
      { label: "Connectors", icon: <Cable size={14} />, view: { kind: "connectors" } },
      { label: "Audit Log", icon: <Zap size={14} />, view: { kind: "events" } },
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
    return [...apps, ...platform];
  }, [surfaces]);

  // Combined result list: nav matches first, then live record/agent/goal hits
  const items = useMemo(() => {
    type PaletteItem = { label: string; sub?: string; icon: React.ReactNode; view: View };
    const needle = q.trim().toLowerCase();
    const navMatches: PaletteItem[] = (needle
      ? navItems.filter((i) => i.label.toLowerCase().includes(needle))
      : navItems
    ).map((i) => ({ label: i.label, icon: i.icon, view: i.view }));
    const recordHits: PaletteItem[] = (hits?.records ?? []).map((r) => ({
      label: `${r.title}`,
      sub: `${r.icon} ${r.object_name}${r.snippet ? " · " + r.snippet : ""}`,
      icon: <span className="text-sm leading-none">{r.icon}</span>,
      view: { kind: "object", slug: r.object } as View,
    }));
    const agentHits: PaletteItem[] = (hits?.agents ?? []).map((a) => ({
      label: a.name,
      sub: `🤖 AI employee · ${a.role || "no role"}`,
      icon: <span className="text-sm leading-none">{a.icon || "🤖"}</span>,
      view: { kind: "agents" } as View,
    }));
    const goalHits: PaletteItem[] = (hits?.goals ?? []).map((g) => ({
      label: g.title,
      sub: `🎯 Goal · ${g.status}`,
      icon: <span className="text-sm leading-none">🎯</span>,
      view: { kind: "goals" } as View,
    }));
    return [...navMatches, ...recordHits, ...agentHits, ...goalHits];
  }, [q, navItems, hits]);

  useEffect(() => {
    if (open) {
      setQ("");
      setSel(0);
      setHits(null);
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
            placeholder="Search everything — apps, records, people, goals…"
            className="w-full bg-transparent py-3 text-sm outline-none placeholder:text-faint"
          />
          {searching && (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border border-accent border-t-transparent" />
          )}
          <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted">esc</kbd>
        </div>
        <div className="max-h-72 overflow-y-auto p-1.5">
          {items.map((item, i) => (
            <button
              key={`${item.label}-${i}`}
              onClick={() => setView(item.view)}
              onMouseEnter={() => setSel(i)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition ${
                i === sel ? "bg-accent-soft text-accent" : "hover:bg-card-2"
              }`}
            >
              {item.icon}
              <span className="min-w-0 flex-1">
                <span className="block truncate">{item.label}</span>
                {item.sub && (
                  <span className="block truncate text-[11px] text-muted">{item.sub}</span>
                )}
              </span>
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
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set());
  const [showCols, setShowCols] = useState(false);
  const PAGE_SIZE = 25;

  // per-object column visibility, persisted to localStorage
  useEffect(() => {
    if (!object) return;
    try {
      const raw = localStorage.getItem(`truss.cols.${object.slug}`);
      setHiddenCols(raw ? new Set(JSON.parse(raw) as string[]) : new Set());
    } catch {
      setHiddenCols(new Set());
    }
    setShowCols(false);
  }, [object?.slug]);

  function toggleCol(slug: string) {
    if (!object) return;
    setHiddenCols((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      try {
        localStorage.setItem(`truss.cols.${object.slug}`, JSON.stringify([...next]));
      } catch {
        /* private mode */
      }
      return next;
    });
  }

  const visibleFields = object ? object.fields.filter((f) => !hiddenCols.has(f.slug)) : [];

  // debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  // "/" keyboard shortcut focuses this search box
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onFocus = () => searchRef.current?.focus();
    window.addEventListener("truss:focus-search", onFocus);
    return () => window.removeEventListener("truss:focus-search", onFocus);
  }, []);

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
          <div className="relative">
            <button
              onClick={() => setShowCols((v) => !v)}
              className={`flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm transition hover:border-border-strong ${showCols ? "text-foreground" : "text-muted"}`}
            >
              <LayoutGrid size={13} /> Columns
            </button>
            {showCols && (
              <div className="absolute right-0 z-20 mt-1 w-48 rounded-xl border border-border bg-card p-2 shadow-lg">
                {object.fields.map((f) => (
                  <label key={f.slug} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-background">
                    <input type="checkbox" checked={!hiddenCols.has(f.slug)} onChange={() => toggleCol(f.slug)} />
                    {f.name}
                  </label>
                ))}
              </div>
            )}
          </div>
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
              ref={searchRef}
              className={input + " w-52 pl-8"}
              placeholder={`Search ${object.name_plural.toLowerCase()}…  ( / )`}
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
              {visibleFields.map((f) => (
                <th key={f.slug} className="px-3 py-2 font-medium">{f.name}</th>
              ))}
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-b border-border/50">
                  {visibleFields.map((f) => (
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
                  {visibleFields.map((f) => (
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
                <td colSpan={visibleFields.length + 1} className="px-3 py-10 text-center text-muted">
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

/* ---------------- AI (BYOK keys only — agent chat moved to the Chat view) ---------------- */

function AiView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [keys, setKeys] = useState<AiKeyInfo[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", base_url: "", model: "", api_key: "", is_default: true });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
      await onChanged();
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
    await onChanged();
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-accent";

  return (
    <div className="mx-auto max-w-3xl">
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
        Bring your own AI provider. Keys power the Chat agent and your AI employees.
        For the conversational control surface, use the <strong>Chat</strong> view.
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
            No AI keys yet. Add one to unlock the Chat agent and AI employees.
          </div>
        )}
      </div>
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

/* ---------------- Phase B: Notifications bell ---------------- */

function NotificationsBell() {
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationInfo[]>([]);

  const poll = useCallback(async () => {
    try {
      const res = await api<{ items: NotificationInfo[]; unread_count: number }>("/api/org/notifications?limit=12");
      setItems(res.items);
      setUnread(res.unread_count);
    } catch {
      /* not logged in yet */
    }
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(poll, 30000);
    return () => clearInterval(t);
  }, [poll]);

  async function markRead(n: NotificationInfo) {
    try {
      await api(`/api/org/notifications/${n.id}/read`, { method: "POST" });
      await poll();
    } catch {
      /* ignore */
    }
  }

  async function readAll() {
    try {
      await api("/api/org/notifications/read-all", { method: "POST" });
      await poll();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => {
          setOpen((v) => !v);
          if (!open) poll();
        }}
        title="Notifications"
        className="relative shrink-0 rounded-md p-1.5 text-muted transition hover:bg-accent-soft hover:text-accent"
      >
        <Bell size={14} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-danger px-0.5 text-[8px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute bottom-10 left-0 z-30 w-80 rounded-xl border border-border bg-card p-2 shadow-xl">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-xs font-semibold">Notifications</span>
            {unread > 0 && (
              <button onClick={readAll} className="text-[10px] text-accent hover:underline">
                Mark all read
              </button>
            )}
          </div>
          <div className="mt-1 max-h-72 space-y-1 overflow-y-auto">
            {items.length === 0 && (
              <div className="px-2 py-4 text-center text-xs text-muted">No notifications yet.</div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                onClick={() => !n.read && markRead(n)}
                className={`block w-full rounded-lg px-2 py-1.5 text-left transition ${n.read ? "opacity-60" : "hover:bg-background"}`}
              >
                <div className="flex items-center gap-1.5">
                  {!n.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
                  <span className="truncate text-xs font-medium">{n.title}</span>
                </div>
                {n.body && <div className="mt-0.5 line-clamp-2 text-[10px] text-muted">{n.body}</div>}
                <div className="mt-0.5 text-[9px] text-faint">
                  {n.actor_type === "agent" ? "🤖 " : ""}
                  {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase B: Org Chart ---------------- */

function OrgView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [tree, setTree] = useState<OrgNode[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [budget, setBudget] = useState<BudgetLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [assignFor, setAssignFor] = useState<string | null>(null);
  const [managerPick, setManagerPick] = useState("");

  const load = useCallback(async () => {
    try {
      const [t, a, b] = await Promise.all([
        api<OrgNode[]>("/api/org/tree"),
        api<AgentInfo[]>("/api/agents"),
        api<BudgetLedger>("/api/org/budget"),
      ]);
      setTree(t);
      setAgents(a);
      setBudget(b);
    } catch {
      /* boot may race */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function setManager(agentId: string) {
    const body: Record<string, unknown> = {};
    if (managerPick === "") {
      body.reports_to_agent_id = null;
      body.reports_to_user_id = null;
    } else if (managerPick === "me") {
      body.reports_to_user_id = "me";
    } else {
      body.reports_to_agent_id = managerPick;
    }
    try {
      if (managerPick === "me") {
        // resolve current user id via /api/auth/me
        const me = await api<{ id?: string; user_id?: string }>("/api/auth/me");
        body.reports_to_user_id = me.id ?? me.user_id;
        delete body.reports_to_agent_id;
      }
      await api(`/api/agents/${agentId}`, { method: "PATCH", body });
      toast("Reporting line updated", "success");
      setAssignFor(null);
      setManagerPick("");
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Update failed", "error");
    }
  }

  function NodeCard({ node, depth }: { node: OrgNode; depth: number }) {
    const row = budget?.agents.find((a) => a.agent_id === node.id);
    return (
      <div style={{ marginLeft: depth * 24 }}>
        <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <span className="text-xl">{node.icon}</span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold">{node.name}</span>
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                  node.status === "active"
                    ? "bg-success/15 text-success"
                    : node.status === "paused"
                      ? "bg-warning/15 text-warning"
                      : "bg-danger/15 text-danger"
                }`}
              >
                {node.status}
              </span>
            </div>
            <div className="text-[11px] text-muted">
              {node.role || "—"}
              {row && row.budget_tokens > 0 && (
                <span className="ml-2">
                  · {row.tokens_used.toLocaleString()}/{row.budget_tokens.toLocaleString()} tokens
                </span>
              )}
              {node.manager_name && <span className="ml-2">· reports to {node.manager_name} (human)</span>}
            </div>
          </div>
          <div className="relative">
            <button
              onClick={() => {
                setAssignFor(assignFor === node.id ? null : node.id);
                setManagerPick(node.reports_to_agent ?? "");
              }}
              className="rounded-md border border-border px-2 py-1 text-[11px] text-muted transition hover:border-border-strong hover:text-foreground"
            >
              Manager
            </button>
            {assignFor === node.id && (
              <div className="absolute right-0 z-20 mt-1 w-52 rounded-xl border border-border bg-card p-2 shadow-lg">
                <select
                  className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-xs outline-none"
                  value={managerPick}
                  onChange={(e) => setManagerPick(e.target.value)}
                >
                  <option value="">— no manager (top level) —</option>
                  <option value="me">👤 Me (human)</option>
                  {agents
                    .filter((a) => a.id !== node.id && a.status !== "terminated")
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.icon} {a.name}
                      </option>
                    ))}
                </select>
                <button
                  onClick={() => setManager(node.id)}
                  className="mt-2 w-full rounded-lg bg-accent px-2 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110"
                >
                  Save
                </button>
              </div>
            )}
          </div>
        </div>
        {node.children.length > 0 && (
          <div className="mt-2 space-y-2 border-l border-border pl-3">
            {node.children.map((c) => (
              <NodeCard key={c.id} node={c} depth={0} />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Org Chart</h1>
          <p className="mt-0.5 text-xs text-muted">
            Your AI team&apos;s reporting structure. Managers can delegate tasks to direct reports.
          </p>
        </div>
        {budget && (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-xs">
            <Coins size={13} className="text-accent" />
            <span className="text-muted">
              {budget.total_tokens_used.toLocaleString()} tokens used
              {budget.total_budget > 0 && ` / ${budget.total_budget.toLocaleString()} budgeted`}
            </span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="mt-6 space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : tree.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-border p-8 text-center">
          <Network size={24} className="mx-auto text-faint" />
          <p className="mt-2 text-sm text-muted">No AI employees yet — hire some to build your org.</p>
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {tree.map((n) => (
            <NodeCard key={n.id} node={n} depth={0} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase B: Goals ---------------- */

function GoalsView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [goals, setGoals] = useState<GoalInfo[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ title: "", metric: "", target_value: "", unit: "", owner_agent_id: "", parent_goal_id: "" });

  const load = useCallback(async () => {
    try {
      const [g, a] = await Promise.all([api<GoalInfo[]>("/api/org/goals"), api<AgentInfo[]>("/api/agents")]);
      setGoals(g);
      setAgents(a);
    } catch {
      /* boot race */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/org/goals", {
        method: "POST",
        body: {
          title: form.title,
          metric: form.metric,
          target_value: parseFloat(form.target_value) || 0,
          unit: form.unit,
          owner_agent_id: form.owner_agent_id || null,
          parent_goal_id: form.parent_goal_id || null,
        },
      });
      toast("Goal created", "success");
      setShowForm(false);
      setForm({ title: "", metric: "", target_value: "", unit: "", owner_agent_id: "", parent_goal_id: "" });
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function bump(g: GoalInfo, delta: number) {
    try {
      await api(`/api/org/goals/${g.id}`, {
        method: "PATCH",
        body: { current_value: Math.max(0, g.current_value + delta) },
      });
      await load();
      await onChanged();
    } catch {
      toast("Update failed", "error");
    }
  }

  const agentName = (id: string | null) => agents.find((a) => a.id === id)?.name ?? "You";
  const topLevel = goals.filter((g) => !g.parent_goal_id);
  const childrenOf = (id: string) => goals.filter((g) => g.parent_goal_id === id);

  const input = "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition focus:border-accent";

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Goals</h1>
          <p className="mt-0.5 text-xs text-muted">
            Measurable objectives for your AI team. Sub-goals roll progress up to their parent.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
        >
          {showForm ? "Cancel" : "+ New goal"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={create} className="mt-4 grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-2">
          <label className="block text-xs md:col-span-2">
            <span className="mb-1 block text-muted">Title *</span>
            <input className={input} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Metric</span>
            <input className={input} placeholder="meetings" value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Target</span>
            <input className={input} type="number" min="0" step="any" value={form.target_value} onChange={(e) => setForm({ ...form, target_value: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Unit</span>
            <input className={input} placeholder="meetings" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Owner</span>
            <select className={input} value={form.owner_agent_id} onChange={(e) => setForm({ ...form, owner_agent_id: e.target.value })}>
              <option value="">👤 Me</option>
              {agents.filter((a) => a.status !== "terminated").map((a) => (
                <option key={a.id} value={a.id}>{a.icon} {a.name}</option>
              ))}
            </select>
          </label>
          <label className="block text-xs md:col-span-2">
            <span className="mb-1 block text-muted">Parent goal (optional — makes this a sub-goal)</span>
            <select className={input} value={form.parent_goal_id} onChange={(e) => setForm({ ...form, parent_goal_id: e.target.value })}>
              <option value="">— none (top-level) —</option>
              {topLevel.map((g) => (
                <option key={g.id} value={g.id}>{g.title}</option>
              ))}
            </select>
          </label>
          <div className="md:col-span-2">
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : "Create goal"}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="mt-6 space-y-2">{[0, 1].map((i) => <div key={i} className="skeleton h-20 w-full rounded-xl" />)}</div>
      ) : goals.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-border p-8 text-center">
          <Target size={24} className="mx-auto text-faint" />
          <p className="mt-2 text-sm text-muted">No goals yet — set a measurable objective for your team.</p>
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {topLevel.map((g) => (
            <div key={g.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{g.title}</span>
                    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${g.status === "achieved" ? "bg-success/15 text-success" : g.status === "dropped" ? "bg-danger/15 text-danger" : "bg-accent/15 text-accent"}`}>
                      {g.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted">
                    {agentName(g.owner_agent_id ?? g.owner_user_id)} · {g.metric || "no metric"}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <button onClick={() => bump(g, -1)} className="rounded-md border border-border px-2 py-1 text-xs text-muted hover:text-foreground">−</button>
                  <button onClick={() => bump(g, 1)} className="rounded-md border border-border px-2 py-1 text-xs text-muted hover:text-foreground">+</button>
                </div>
              </div>
              {g.target_value > 0 && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-[11px] text-muted">
                    <span>{g.current_value} / {g.target_value} {g.unit}</span>
                    <span>{Math.round(g.progress * 100)}%</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-border">
                    <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.min(100, g.progress * 100)}%` }} />
                  </div>
                </div>
              )}
              {childrenOf(g.id).length > 0 && (
                <div className="mt-3 space-y-2 border-l border-border pl-3">
                  {childrenOf(g.id).map((c) => (
                    <div key={c.id} className="flex items-center justify-between gap-2 rounded-lg bg-background px-3 py-2">
                      <div className="min-w-0">
                        <span className="block truncate text-xs font-medium">{c.title}</span>
                        <span className="text-[10px] text-muted">{agentName(c.owner_agent_id ?? c.owner_user_id)}</span>
                      </div>
                      {c.target_value > 0 && (
                        <div className="w-28">
                          <div className="h-1 overflow-hidden rounded-full bg-border">
                            <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, c.progress * 100)}%` }} />
                          </div>
                          <div className="mt-0.5 text-right text-[10px] text-muted">{Math.round(c.progress * 100)}%</div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase B: Review Inbox ---------------- */

function ReviewView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [inbox, setInbox] = useState<ReviewInbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setInbox(await api<ReviewInbox>("/api/org/review"));
    } catch {
      /* boot race */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(t: AgentTaskInfo & { agent_name: string }, action: "approve" | "reject" | "run") {
    setBusyId(t.id);
    try {
      if (action === "run") {
        await api(`/api/agents/${t.agent_id}/tasks/${t.id}/run`, { method: "POST" });
        toast(`Ran "${t.title}"`, "success");
      } else {
        await api(`/api/agents/${t.agent_id}/tasks/${t.id}/${action}`, { method: "POST" });
        toast(`${action === "approve" ? "Approved" : "Rejected"} "${t.title}"`, action === "approve" ? "success" : "info");
      }
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-bold">Review Inbox</h1>
      <p className="mt-0.5 text-xs text-muted">
        Everything awaiting your approval across all AI employees.
      </p>

      {loading ? (
        <div className="mt-6 space-y-2">{[0, 1].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : !inbox || inbox.pending_tasks.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-border p-8 text-center">
          <Inbox size={24} className="mx-auto text-faint" />
          <p className="mt-2 text-sm text-muted">Inbox zero — nothing needs your approval. 🎉</p>
        </div>
      ) : (
        <div className="mt-6 space-y-2">
          {inbox.pending_tasks.map((t) => (
            <div key={t.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{t.title}</span>
                    {t.priority > 0 && (
                      <span className="rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">P{t.priority}</span>
                    )}
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted">
                    {t.agent_name}
                    {t.delegated_by_agent_id && " · delegated by manager"}
                    {t.description && <span className="block truncate">{t.description}</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    disabled={busyId === t.id}
                    onClick={() => act(t, "approve")}
                    className="rounded-lg bg-success/15 px-3 py-1.5 text-xs font-semibold text-success transition hover:bg-success/25 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    disabled={busyId === t.id}
                    onClick={() => act(t, "reject")}
                    className="rounded-lg bg-danger/15 px-3 py-1.5 text-xs font-semibold text-danger transition hover:bg-danger/25 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase C: Autopilot (schedules / triggers / pipelines) ---------------- */

function AutopilotView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [tab, setTab] = useState<"schedules" | "triggers" | "pipelines">("schedules");
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [schedules, setSchedules] = useState<ScheduleInfo[]>([]);
  const [triggers, setTriggers] = useState<TriggerInfo[]>([]);
  const [pipelines, setPipelines] = useState<PipelineInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [runResult, setRunResult] = useState<PipelineRunResult | null>(null);

  // schedule form
  const [sForm, setSForm] = useState({ agent_id: "", name: "", title: "", prompt: "", kind: "interval", every_minutes: "60", cron: "", needs_review: false });
  // trigger form
  const [tForm, setTForm] = useState({ agent_id: "", name: "", event_type: "record.created", object_slug: "", title: "", prompt: "", needs_review: false });
  // pipeline form
  const [pForm, setPForm] = useState({ name: "", description: "", steps: [{ agent_id: "", title: "", prompt: "" }] });

  const load = useCallback(async () => {
    try {
      const [a, s, t, p] = await Promise.all([
        api<AgentInfo[]>("/api/agents"),
        api<ScheduleInfo[]>("/api/orchestration/schedules"),
        api<TriggerInfo[]>("/api/orchestration/triggers"),
        api<PipelineInfo[]>("/api/orchestration/pipelines"),
      ]);
      setAgents(a);
      setSchedules(s);
      setTriggers(t);
      setPipelines(p);
    } catch {
      /* boot race */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const agentName = (id: string) => agents.find((a) => a.id === id)?.name ?? id.slice(0, 8);
  const agentIcon = (id: string) => agents.find((a) => a.id === id)?.icon ?? "🤖";
  const input = "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition focus:border-accent";

  async function createSchedule(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/orchestration/schedules", {
        method: "POST",
        body: {
          agent_id: sForm.agent_id, name: sForm.name, title: sForm.title, prompt: sForm.prompt,
          kind: sForm.kind, every_minutes: parseInt(sForm.every_minutes) || 60,
          cron: sForm.cron, needs_review: sForm.needs_review,
        },
      });
      toast("Schedule created", "success");
      setShowForm(false);
      setSForm({ agent_id: "", name: "", title: "", prompt: "", kind: "interval", every_minutes: "60", cron: "", needs_review: false });
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function createTrigger(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/orchestration/triggers", {
        method: "POST",
        body: {
          agent_id: tForm.agent_id, name: tForm.name, event_type: tForm.event_type,
          object_slug: tForm.object_slug, title: tForm.title, prompt: tForm.prompt,
          needs_review: tForm.needs_review,
        },
      });
      toast("Trigger created", "success");
      setShowForm(false);
      setTForm({ agent_id: "", name: "", event_type: "record.created", object_slug: "", title: "", prompt: "", needs_review: false });
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function createPipeline(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/orchestration/pipelines", {
        method: "POST",
        body: {
          name: pForm.name, description: pForm.description,
          steps: pForm.steps.filter((s) => s.agent_id),
        },
      });
      toast("Pipeline created", "success");
      setShowForm(false);
      setPForm({ name: "", description: "", steps: [{ agent_id: "", title: "", prompt: "" }] });
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function toggleSchedule(s: ScheduleInfo) {
    try {
      await api(`/api/orchestration/schedules/${s.id}`, { method: "PATCH", body: { enabled: !s.enabled } });
      await load();
    } catch {
      toast("Update failed", "error");
    }
  }

  async function toggleTrigger(t: TriggerInfo) {
    try {
      await api(`/api/orchestration/triggers/${t.id}`, { method: "PATCH", body: { enabled: !t.enabled } });
      await load();
    } catch {
      toast("Update failed", "error");
    }
  }

  async function runPipeline(p: PipelineInfo) {
    setBusy(true);
    setRunResult(null);
    try {
      const res = await api<{ run: PipelineRunResult }>(`/api/orchestration/pipelines/${p.id}/run`, {
        method: "POST",
        body: { input: "" },
      });
      setRunResult(res.run);
      toast(res.run.ok ? "Pipeline completed" : "Pipeline failed", res.run.ok ? "success" : "error");
      await load();
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Run failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function remove(kind: "schedules" | "triggers" | "pipelines", id: string) {
    try {
      await api(`/api/orchestration/${kind}/${id}`, { method: "DELETE" });
      toast("Deleted", "info");
      await load();
      await onChanged();
    } catch {
      toast("Delete failed", "error");
    }
  }

  const tabs = [
    { id: "schedules" as const, label: "Schedules", count: schedules.length },
    { id: "triggers" as const, label: "Triggers", count: triggers.length },
    { id: "pipelines" as const, label: "Pipelines", count: pipelines.length },
  ];

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Autopilot</h1>
          <p className="mt-0.5 text-xs text-muted">
            Your AI employees working on their own — on a schedule, reacting to events, or in pipelines.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
        >
          {showForm ? "Cancel" : "+ New " + tab.slice(0, -1)}
        </button>
      </div>

      {/* tabs */}
      <div className="mt-4 flex gap-1 rounded-lg border border-border bg-card p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setShowForm(false); setRunResult(null); }}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm transition ${tab === t.id ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}
          >
            {t.label} <span className="opacity-60">({t.count})</span>
          </button>
        ))}
      </div>

      {/* forms */}
      {showForm && tab === "schedules" && (
        <form onSubmit={createSchedule} className="mt-4 grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-2">
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Agent *</span>
            <select className={input} value={sForm.agent_id} onChange={(e) => setSForm({ ...sForm, agent_id: e.target.value })} required>
              <option value="">— pick an agent —</option>
              {agents.filter((a) => a.status !== "terminated").map((a) => (
                <option key={a.id} value={a.id}>{a.icon} {a.name}</option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Name *</span>
            <input className={input} value={sForm.name} onChange={(e) => setSForm({ ...sForm, name: e.target.value })} required />
          </label>
          <label className="block text-xs md:col-span-2">
            <span className="mb-1 block text-muted">Task title *</span>
            <input className={input} value={sForm.title} onChange={(e) => setSForm({ ...sForm, title: e.target.value })} required />
          </label>
          <label className="block text-xs md:col-span-2">
            <span className="mb-1 block text-muted">Prompt</span>
            <textarea className={input} rows={2} value={sForm.prompt} onChange={(e) => setSForm({ ...sForm, prompt: e.target.value })} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Kind</span>
            <select className={input} value={sForm.kind} onChange={(e) => setSForm({ ...sForm, kind: e.target.value })}>
              <option value="interval">Every N minutes</option>
              <option value="cron">Cron expression</option>
            </select>
          </label>
          {sForm.kind === "interval" ? (
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Every (minutes)</span>
              <input className={input} type="number" min="1" value={sForm.every_minutes} onChange={(e) => setSForm({ ...sForm, every_minutes: e.target.value })} />
            </label>
          ) : (
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Cron (min hour dom month dow)</span>
              <input className={input} placeholder="0 9 * * *" value={sForm.cron} onChange={(e) => setSForm({ ...sForm, cron: e.target.value })} />
            </label>
          )}
          <label className="flex items-center gap-2 text-xs md:col-span-2">
            <input type="checkbox" checked={sForm.needs_review} onChange={(e) => setSForm({ ...sForm, needs_review: e.target.checked })} />
            Require human approval before each run
          </label>
          <div className="md:col-span-2">
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : "Create schedule"}
            </button>
          </div>
        </form>
      )}

      {showForm && tab === "triggers" && (
        <form onSubmit={createTrigger} className="mt-4 grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-2">
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Agent *</span>
            <select className={input} value={tForm.agent_id} onChange={(e) => setTForm({ ...tForm, agent_id: e.target.value })} required>
              <option value="">— pick an agent —</option>
              {agents.filter((a) => a.status !== "terminated").map((a) => (
                <option key={a.id} value={a.id}>{a.icon} {a.name}</option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Name *</span>
            <input className={input} value={tForm.name} onChange={(e) => setTForm({ ...tForm, name: e.target.value })} required />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Event type *</span>
            <select className={input} value={tForm.event_type} onChange={(e) => setTForm({ ...tForm, event_type: e.target.value })}>
              <option value="record.created">record.created</option>
              <option value="record.updated">record.updated</option>
              <option value="record.deleted">record.deleted</option>
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-muted">Object filter (optional)</span>
            <input className={input} placeholder="lead" value={tForm.object_slug} onChange={(e) => setTForm({ ...tForm, object_slug: e.target.value })} />
          </label>
          <label className="block text-xs md:col-span-2">
            <span className="mb-1 block text-muted">Task title * <span className="text-faint">(placeholders: {"{event} {object} {record_id}"})</span></span>
            <input className={input} value={tForm.title} onChange={(e) => setTForm({ ...tForm, title: e.target.value })} required />
          </label>
          <label className="block text-xs md:col-span-2">
            <span className="mb-1 block text-muted">Prompt</span>
            <textarea className={input} rows={2} value={tForm.prompt} onChange={(e) => setTForm({ ...tForm, prompt: e.target.value })} />
          </label>
          <label className="flex items-center gap-2 text-xs md:col-span-2">
            <input type="checkbox" checked={tForm.needs_review} onChange={(e) => setTForm({ ...tForm, needs_review: e.target.checked })} />
            Require human approval before each run
          </label>
          <div className="md:col-span-2">
            <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy ? "…" : "Create trigger"}
            </button>
          </div>
        </form>
      )}

      {showForm && tab === "pipelines" && (
        <form onSubmit={createPipeline} className="mt-4 space-y-3 rounded-xl border border-border bg-card p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Name *</span>
              <input className={input} value={pForm.name} onChange={(e) => setPForm({ ...pForm, name: e.target.value })} required />
            </label>
            <label className="block text-xs">
              <span className="mb-1 block text-muted">Description</span>
              <input className={input} value={pForm.description} onChange={(e) => setPForm({ ...pForm, description: e.target.value })} />
            </label>
          </div>
          {pForm.steps.map((step, i) => (
            <div key={i} className="grid gap-2 rounded-lg border border-border bg-background p-3 md:grid-cols-3">
              <label className="block text-xs">
                <span className="mb-1 block text-muted">Step {i + 1} agent *</span>
                <select className={input} value={step.agent_id} onChange={(e) => {
                  const steps = [...pForm.steps];
                  steps[i] = { ...steps[i], agent_id: e.target.value };
                  setPForm({ ...pForm, steps });
                }} required>
                  <option value="">— pick —</option>
                  {agents.filter((a) => a.status !== "terminated").map((a) => (
                    <option key={a.id} value={a.id}>{a.icon} {a.name}</option>
                  ))}
                </select>
              </label>
              <label className="block text-xs">
                <span className="mb-1 block text-muted">Step title</span>
                <input className={input} value={step.title} onChange={(e) => {
                  const steps = [...pForm.steps];
                  steps[i] = { ...steps[i], title: e.target.value };
                  setPForm({ ...pForm, steps });
                }} />
              </label>
              <label className="block text-xs">
                <span className="mb-1 block text-muted">Step prompt</span>
                <input className={input} value={step.prompt} onChange={(e) => {
                  const steps = [...pForm.steps];
                  steps[i] = { ...steps[i], prompt: e.target.value };
                  setPForm({ ...pForm, steps });
                }} />
              </label>
            </div>
          ))}
          <div className="flex gap-2">
            <button type="button" onClick={() => setPForm({ ...pForm, steps: [...pForm.steps, { agent_id: "", title: "", prompt: "" }] })} className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-foreground">
              + Add step
            </button>
            {pForm.steps.length > 1 && (
              <button type="button" onClick={() => setPForm({ ...pForm, steps: pForm.steps.slice(0, -1) })} className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-foreground">
                − Remove last
              </button>
            )}
          </div>
          <button disabled={busy} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
            {busy ? "…" : "Create pipeline"}
          </button>
        </form>
      )}

      {/* lists */}
      {loading ? (
        <div className="mt-6 space-y-2">{[0, 1].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="mt-6 space-y-2">
          {tab === "schedules" && (schedules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-8 text-center">
              <Zap size={24} className="mx-auto text-faint" />
              <p className="mt-2 text-sm text-muted">No schedules yet — set an agent to run on a timer or cron.</p>
            </div>
          ) : schedules.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base">{agentIcon(s.agent_id)}</span>
                  <span className="truncate text-sm font-semibold">{s.name}</span>
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${s.enabled ? "bg-success/15 text-success" : "bg-border text-muted"}`}>
                    {s.enabled ? "on" : "off"}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] text-muted">
                  {agentName(s.agent_id)} · {s.kind === "cron" ? `cron: ${s.cron}` : `every ${s.every_minutes}m`} · {s.runs_count} runs
                  {s.last_status && <span> · last: {s.last_status}</span>}
                  {s.next_run_at && <span> · next: {new Date(s.next_run_at).toLocaleString()}</span>}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <button onClick={() => toggleSchedule(s)} className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted hover:text-foreground">
                  {s.enabled ? "Pause" : "Enable"}
                </button>
                <button onClick={() => remove("schedules", s.id)} className="rounded-lg border border-border px-2.5 py-1 text-xs text-danger hover:bg-danger/10">
                  Delete
                </button>
              </div>
            </div>
          )))}

          {tab === "triggers" && (triggers.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-8 text-center">
              <Zap size={24} className="mx-auto text-faint" />
              <p className="mt-2 text-sm text-muted">No triggers yet — make an agent react when records change.</p>
            </div>
          ) : triggers.map((t) => (
            <div key={t.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base">{agentIcon(t.agent_id)}</span>
                  <span className="truncate text-sm font-semibold">{t.name}</span>
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${t.enabled ? "bg-success/15 text-success" : "bg-border text-muted"}`}>
                    {t.enabled ? "on" : "off"}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] text-muted">
                  {agentName(t.agent_id)} · on <span className="font-mono text-accent">{t.event_type}</span>
                  {t.object_slug && <span> ({t.object_slug})</span>} · fired {t.fires_count}×
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <button onClick={() => toggleTrigger(t)} className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted hover:text-foreground">
                  {t.enabled ? "Pause" : "Enable"}
                </button>
                <button onClick={() => remove("triggers", t.id)} className="rounded-lg border border-border px-2.5 py-1 text-xs text-danger hover:bg-danger/10">
                  Delete
                </button>
              </div>
            </div>
          )))}

          {tab === "pipelines" && (pipelines.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-8 text-center">
              <Zap size={24} className="mx-auto text-faint" />
              <p className="mt-2 text-sm text-muted">No pipelines yet — chain agents so one&apos;s output feeds the next.</p>
            </div>
          ) : pipelines.map((p) => (
            <div key={p.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{p.name}</span>
                    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${p.status === "active" ? "bg-success/15 text-success" : "bg-border text-muted"}`}>
                      {p.status}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted">
                    {p.steps.length} steps · {p.runs_count} runs
                    {p.last_status && <span> · last: {p.last_status}</span>}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    {p.steps.map((st, i) => (
                      <span key={i} className="flex items-center gap-1 rounded-full bg-background px-2 py-0.5 text-[10px] text-muted">
                        {i > 0 && <span className="text-faint">→</span>}
                        {agentIcon(st.agent_id)} {agentName(st.agent_id)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button disabled={busy || p.status !== "active"} onClick={() => runPipeline(p)} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                    Run
                  </button>
                  <button onClick={() => remove("pipelines", p.id)} className="rounded-lg border border-border px-2.5 py-1 text-xs text-danger hover:bg-danger/10">
                    Delete
                  </button>
                </div>
              </div>
              {runResult && (
                <div className="mt-3 space-y-1.5 border-t border-border pt-3">
                  {runResult.steps.map((st) => (
                    <div key={st.step} className="rounded-lg bg-background px-3 py-2 text-xs">
                      <div className="flex items-center gap-1.5">
                        <span className={st.ok ? "text-success" : "text-danger"}>{st.ok ? "✓" : "✗"}</span>
                        <span className="font-medium">{st.agent}</span>
                      </div>
                      {st.reply && <div className="mt-1 line-clamp-2 text-muted">{st.reply}</div>}
                      {st.error && <div className="mt-1 text-danger">{st.error}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase G: App Home — polished per-plugin landing page ---------------- */

function AppHomeView({
  label,
  icon,
  objects,
  allObjects,
  setView,
}: {
  label: string;
  icon: string;
  objects: string[];
  allObjects: ObjectDef[];
  setView: (v: View) => void;
}) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [pipeline, setPipeline] = useState<{ key: string; value: number }[]>([]);
  const [pipelineTotal, setPipelineTotal] = useState(0);
  const [recent, setRecent] = useState<Record<string, RecordRow[]>>({});
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const countPromises = objects.map(async (slug) => {
          try {
            const res = await api<AnalyticsResult>("/api/insights/query", {
              method: "POST",
              body: { object: slug, metric: "count" },
            });
            return [slug, res.value ?? 0] as const;
          } catch {
            return [slug, 0] as const;
          }
        });
        const recentPromises = objects.map(async (slug) => {
          try {
            const res = await api<{ items: RecordRow[] }>(`/api/records/${slug}?limit=5`);
            return [slug, res.items] as const;
          } catch {
            return [slug, []] as const;
          }
        });

        const [countResults, recentResults] = await Promise.all([
          Promise.all(countPromises),
          Promise.all(recentPromises),
        ]);
        setCounts(Object.fromEntries(countResults));
        setRecent(Object.fromEntries(recentResults));

        // Pipeline breakdown for deals
        if (objects.includes("deal")) {
          try {
            const res = await api<AnalyticsResult>("/api/insights/query", {
              method: "POST",
              body: { object: "deal", metric: "group_by", field: "stage", value_field: "amount" },
            });
            const rows = (res.rows ?? [])
              .filter((r) => r.key !== undefined)
              .map((r) => ({ key: r.key as string, value: r.value ?? 0 }));
            setPipeline(rows);
            setPipelineTotal(rows.reduce((s, r) => s + r.value, 0));
          } catch {
            setPipeline([]);
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [objects]);

  const objDef = (slug: string) => allObjects.find((o) => o.slug === slug);
  const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
  const fmtMoney = (n: number) => `$${n >= 1000 ? `${(n / 1000).toFixed(1)}k` : n.toFixed(0)}`;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-8 w-48" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-20" />)}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* header */}
      <div className="flex items-center gap-3">
        <span className="text-3xl">{icon}</span>
        <div>
          <h1 className="text-xl font-bold">{label}</h1>
          <p className="text-sm text-muted">Your {label.toLowerCase()} workspace at a glance.</p>
        </div>
      </div>

      {/* stat cards — one per object */}
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {objects.map((slug) => {
          const def = objDef(slug);
          return (
            <button
              key={slug}
              onClick={() => setView({ kind: "object", slug })}
              className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-left transition hover:border-accent/40 hover:shadow-sm"
            >
              <span className="text-xl">{def?.icon || "📄"}</span>
              <div>
                <div className="text-2xl font-bold leading-none">{fmt(counts[slug] ?? 0)}</div>
                <div className="mt-1 text-xs text-muted">{def?.name_plural || slug}</div>
              </div>
            </button>
          );
        })}
      </div>

      {/* pipeline breakdown (deals) */}
      {objects.includes("deal") && pipeline.length > 0 && (
        <section className="mt-6 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">💰 Pipeline by Stage</h2>
            <span className="text-sm font-bold text-accent">{fmtMoney(pipelineTotal)} total</span>
          </div>
          <div className="mt-3 space-y-2">
            {pipeline.map((p) => {
              const pct = pipelineTotal > 0 ? Math.round((p.value / pipelineTotal) * 100) : 0;
              return (
                <div key={p.key} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 text-xs text-muted">{p.key}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-border">
                    <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-16 shrink-0 text-right text-xs font-medium">{fmtMoney(p.value)}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* recent records per object */}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {objects.map((slug) => {
          const def = objDef(slug);
          const rows = recent[slug] ?? [];
          if (rows.length === 0) return null;
          const titleField = def?.fields?.[0]?.slug ?? "name";
          return (
            <section key={slug} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">{def?.icon} Recent {def?.name_plural || slug}</h2>
                <button
                  onClick={() => setView({ kind: "object", slug })}
                  className="text-xs text-accent hover:underline"
                >
                  View all →
                </button>
              </div>
              <div className="mt-3 space-y-1.5">
                {rows.map((r) => (
                  <div key={r.id} className="flex items-center justify-between rounded-lg border border-border bg-card-2 px-3 py-2">
                    <span className="truncate text-sm font-medium">{String(r.data[titleField] ?? r.id.slice(0, 8))}</span>
                    <span className="ml-2 shrink-0 text-[11px] text-muted">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------- Phase F: AI Employees hub dashboard ---------------- */

function AiHubView({ onChanged }: { onChanged: () => Promise<void> }) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [goals, setGoals] = useState<GoalInfo[]>([]);
  const [inbox, setInbox] = useState<ReviewInbox | null>(null);
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [a, g, ov] = await Promise.all([
          api<AgentInfo[]>("/api/agents"),
          api<GoalInfo[]>("/api/org/goals"),
          api<WorkspaceOverview>("/api/insights/overview"),
        ]);
        setAgents(a);
        setGoals(g);
        setOverview(ov);
        try {
          setInbox(await api<ReviewInbox>("/api/org/review"));
        } catch {
          setInbox(null);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const active = agents.filter((a) => a.status === "active").length;
  const activeGoals = goals.filter((g) => g.status === "active");
  const pending = inbox?.count ?? 0;

  const stat = (label: string, value: string | number, icon: React.ReactNode, tone = "") => (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4">
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${tone || "bg-accent-soft text-accent"}`}>
        {icon}
      </div>
      <div>
        <div className="text-2xl font-bold leading-none">{value}</div>
        <div className="mt-1 text-xs text-muted">{label}</div>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-8 w-48" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-20" />)}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <Bot size={20} /> AI Employees
          </h1>
          <p className="mt-1 text-sm text-muted">
            Your autonomous workforce at a glance — roster, goals, and what needs your review.
          </p>
        </div>
      </div>

      {/* stat cards */}
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {stat("Employees", agents.length, <Users size={18} />)}
        {stat("Active now", active, <Zap size={18} />, "bg-success/10 text-success")}
        {stat("Active goals", activeGoals.length, <Target size={18} />)}
        {stat("Awaiting review", pending, <Inbox size={18} />, pending > 0 ? "bg-warning/10 text-warning" : "")}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {/* roster */}
        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Roster</h2>
          <div className="mt-3 space-y-2">
            {agents.length === 0 && <p className="text-xs text-muted">No employees yet — hire one from the Employees tab or via Chat.</p>}
            {agents.slice(0, 6).map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-lg border border-border bg-card-2 px-3 py-2">
                <div className="flex items-center gap-2.5">
                  <span className="text-lg">{a.icon || "🤖"}</span>
                  <div>
                    <div className="text-sm font-medium">{a.name}</div>
                    <div className="text-[11px] text-muted">{a.role || "—"}</div>
                  </div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  a.status === "active" ? "bg-success/10 text-success" :
                  a.status === "terminated" ? "bg-danger/10 text-danger" : "bg-card text-muted"
                }`}>{a.status}</span>
              </div>
            ))}
          </div>
        </section>

        {/* goals */}
        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Goals</h2>
          <div className="mt-3 space-y-2">
            {goals.length === 0 && <p className="text-xs text-muted">No goals yet — set one from the Goals tab or via Chat.</p>}
            {goals.slice(0, 6).map((g) => {
              const pct = g.target_value > 0 ? Math.min(100, Math.round((g.current_value / g.target_value) * 100)) : 0;
              return (
                <div key={g.id} className="rounded-lg border border-border bg-card-2 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{g.title}</span>
                    <span className="text-[11px] text-muted">{pct}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-border">
                    <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>

      {/* overview rollup if available */}
      {overview && (
        <div className="mt-4 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Workspace pulse</h2>
          <div className="mt-3 grid gap-3 text-center sm:grid-cols-4">
            <div><div className="text-xl font-bold">{overview.agents_total}</div><div className="text-[11px] text-muted">total agents</div></div>
            <div><div className="text-xl font-bold">{overview.agents_active}</div><div className="text-[11px] text-muted">active</div></div>
            <div><div className="text-xl font-bold">{overview.tasks_total ?? "—"}</div><div className="text-[11px] text-muted">tasks</div></div>
            <div><div className="text-xl font-bold">{activeGoals.length}</div><div className="text-[11px] text-muted">active goals</div></div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase F: Chat — the control surface ---------------- */

const CHAT_SUGGESTIONS = [
  "Hire an AI employee named Scout for lead research",
  "How many leads do we have?",
  "Create a goal: close 10 deals this quarter",
  "Assign a task to review this week's pipeline",
  "What objects are in my workspace?",
  "List my AI employees",
];

function ChatView({ me, onChanged }: { me: Me; onChanged: () => Promise<void> }) {
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string; trace?: ChatResult["trace"] }[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setInput("");
    setError("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setBusy(true);
    try {
      const history = messages.slice(-10).map((m) => ({ role: m.role, content: m.content }));
      const res = await api<ChatResult>("/api/ai/chat", {
        method: "POST",
        body: { message: msg, history },
      });
      setMessages((m) => [...m, { role: "assistant", content: res.reply, trace: res.trace }]);
      await onChanged();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
      setMessages((m) => m.slice(0, -1));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="pb-3">
        <h1 className="flex items-center gap-2 text-xl font-bold">
          <MessageSquare size={20} /> Chat
        </h1>
        <p className="mt-1 text-sm text-muted">
          Talk to your workspace. Create AI employees, search and edit records, set goals —
          anything your role ({me.role}) allows.
        </p>
      </div>

      {/* message stream */}
      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-border bg-card p-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
              <Bot size={24} />
            </div>
            <div>
              <p className="text-sm font-semibold">What should we do?</p>
              <p className="mt-1 text-xs text-muted">Try one of these, or type anything.</p>
            </div>
            <div className="flex max-w-md flex-wrap justify-center gap-2">
              {CHAT_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-border bg-card-2 px-3 py-1.5 text-xs text-muted transition hover:border-accent-border hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                m.role === "user"
                  ? "bg-accent text-on-accent"
                  : "border border-border bg-card-2 text-foreground"
              }`}
            >
              <p className="whitespace-pre-wrap">{m.content}</p>
              {m.trace && m.trace.length > 0 && (
                <div className="mt-2 space-y-1 border-t border-border pt-2">
                  {m.trace.map((t, j) => (
                    <div key={j} className="flex items-center gap-1.5 text-[11px] text-faint">
                      <Zap size={10} />
                      <span className="font-mono">{t.tool}</span>
                      {t.result && (t.result as { error?: string }).error ? (
                        <span className="text-danger">failed</span>
                      ) : (
                        <span className="text-success">ok</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl border border-border bg-card-2 px-4 py-2.5 text-sm text-muted">
              <span className="skeleton h-3 w-16" /> thinking…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="mt-2 text-xs text-danger">{error}</p>}

      {/* composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything — hire, search, create, edit…"
          className="flex-1 rounded-xl border border-border bg-card px-4 py-2.5 text-sm outline-none transition focus:border-accent"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent transition disabled:opacity-40"
        >
          <Send size={15} /> Send
        </button>
      </form>
    </div>
  );
}

/* ---------------- Phase E: Developer portal ---------------- */

function DeveloperView() {
  const [reference, setReference] = useState("");
  const [manifestText, setManifestText] = useState("");
  const [validation, setValidation] = useState<{ ok: boolean; errors?: string[]; plugin_id?: string; version?: string; objects?: number; tools?: number } | null>(null);
  const [validating, setValidating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<{ ok: boolean; plugin_id?: string; version?: string; updated?: boolean; error?: string } | null>(null);
  const [published, setPublished] = useState<{ id: string; name: string; version: string; description: string; objects: number; tools: number }[]>([]);

  const loadPublished = useCallback(async () => {
    try {
      const res = await api<{ items: { id: string; name: string; version: string; description: string; objects: number; tools: number }[] }>("/api/marketplace/published");
      setPublished(res.items);
    } catch {
      setPublished([]);
    }
  }, []);

  useEffect(() => {
    api<string>("/api/dev/reference", { raw: true }).then(setReference).catch(() => setReference(""));
    loadPublished();
  }, [loadPublished]);

  async function validateManifest() {
    setValidating(true);
    setValidation(null);
    try {
      const parsed = JSON.parse(manifestText);
      const res = await api<{ ok: boolean; errors?: string[]; plugin_id?: string; version?: string; objects?: number; tools?: number }>(
        "/api/marketplace/validate",
        { method: "POST", body: parsed }
      );
      setValidation(res);
    } catch (err) {
      setValidation({ ok: false, errors: [err instanceof SyntaxError ? "Invalid JSON: " + err.message : "Request failed"] });
    } finally {
      setValidating(false);
    }
  }

  async function publishManifest() {
    setPublishing(true);
    setPublishResult(null);
    try {
      const parsed = JSON.parse(manifestText);
      const res = await api<{ ok: boolean; plugin_id: string; version: string; updated: boolean }>(
        "/api/marketplace/publish",
        { method: "POST", body: { manifest: parsed, install: true } }
      );
      setPublishResult({ ok: true, plugin_id: res.plugin_id, version: res.version, updated: res.updated });
      toast(res.updated ? `Updated ${res.plugin_id} to v${res.version}` : `Published ${res.plugin_id} v${res.version}`, "success");
      setManifestText("");
      await loadPublished();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      const msg = typeof d === "string" ? d : Array.isArray((d as { errors?: string[] })?.errors)
        ? ((d as { errors: string[] }).errors).join("; ")
        : "Publish failed";
      setPublishResult({ ok: false, error: msg });
    } finally {
      setPublishing(false);
    }
  }

  async function unpublish(id: string) {
    try {
      await api(`/api/marketplace/publish/${id}`, { method: "DELETE" });
      toast(`Unpublished ${id} (installs disabled, data preserved)`, "success");
      await loadPublished();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Unpublish failed", "error");
    }
  }

  const quickstart = `import { TrussClient } from "@truss/client";

const truss = new TrussClient({ baseUrl: "http://localhost:8000" });
await truss.auth.login({ email, password });

const leads = await truss.records.list("lead");
await truss.records.create("lead", { name: "Acme", email: "a@b.co" });
const stats = await truss.insights.query({ object: "deal", metric: "sum", field: "amount" });`;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">Developer</h1>
        <p className="mt-0.5 text-xs text-muted">Build on Truss: typed SDK, plugin manifest validation, and the full API reference.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* TS client quickstart */}
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">TypeScript client</h2>
          <p className="mt-1 text-xs text-muted">Typed, dependency-free client for the kernel API. Lives in <code className="rounded bg-background px-1">sdk/typescript</code>.</p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-background p-3 text-[11px] leading-relaxed text-foreground">{quickstart}</pre>
          <div className="mt-3 flex gap-2">
            <a href={`${API_BASE}/docs`} target="_blank" rel="noreferrer" className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition hover:text-foreground">Interactive docs (/docs)</a>
            <a href={`${API_BASE}/api/dev/openapi.json`} target="_blank" rel="noreferrer" className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition hover:text-foreground">OpenAPI spec</a>
          </div>
        </div>

        {/* manifest validator + publisher */}
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Plugin manifest validator &amp; publisher</h2>
          <p className="mt-1 text-xs text-muted">Paste a plugin.json — dry-run it against the Plugin SDK, or publish it to this instance&apos;s marketplace. Re-publish with a higher version to update.</p>
          <textarea
            className="mt-3 h-40 w-full rounded-lg border border-border bg-background p-3 font-mono text-[11px] outline-none transition focus:border-accent"
            placeholder='{"id": "my-plugin", "name": "My Plugin", "version": "0.1.0", ...}'
            value={manifestText}
            onChange={(e) => setManifestText(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <button
              disabled={validating || !manifestText.trim()}
              onClick={validateManifest}
              className="rounded-lg border border-border px-4 py-1.5 text-sm font-semibold text-foreground transition hover:bg-card-2 disabled:opacity-50"
            >
              {validating ? "Validating…" : "Validate"}
            </button>
            <button
              disabled={publishing || !manifestText.trim()}
              onClick={publishManifest}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
            >
              {publishing ? "Publishing…" : "Publish"}
            </button>
          </div>
          {validation && (
            <div className="mt-3">
              {validation.ok ? (
                <div className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
                  ✓ Valid — {validation.plugin_id} v{validation.version} ({validation.objects} object(s), {validation.tools} tool(s))
                </div>
              ) : (
                <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  <div className="font-semibold">Invalid manifest:</div>
                  <ul className="mt-1 list-inside list-disc space-y-0.5">
                    {(validation.errors ?? []).map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
          {publishResult && (
            <div className="mt-3">
              {publishResult.ok ? (
                <div className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
                  ✓ {publishResult.updated ? "Updated" : "Published"} {publishResult.plugin_id} v{publishResult.version} — installed into this workspace.
                </div>
              ) : (
                <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  {publishResult.error}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* published plugins on this instance */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">Published plugins</h2>
        <p className="mt-1 text-xs text-muted">Community plugins published to this instance. Unpublishing disables installs but preserves data.</p>
        <div className="mt-3 space-y-2">
          {published.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
              <div className="min-w-0">
                <div className="text-sm font-semibold">{p.name} <span className="font-mono text-[11px] text-muted">v{p.version}</span></div>
                <div className="truncate text-xs text-muted">{p.id} · {p.objects} object(s) · {p.tools} tool(s)</div>
              </div>
              <button onClick={() => unpublish(p.id)} className="ml-3 shrink-0 text-xs text-muted transition hover:text-danger">
                unpublish
              </button>
            </div>
          ))}
          {published.length === 0 && (
            <div className="rounded-lg border border-dashed border-border px-4 py-5 text-center text-xs text-muted">
              Nothing published yet. Paste a manifest above and hit Publish.
            </div>
          )}
        </div>
      </div>

      {/* API reference */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">API reference</h2>
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-background p-3 text-[11px] leading-relaxed text-muted">
          {reference || "Loading…"}
        </pre>
      </div>

      {/* API keys — programmatic access */}
      <ApiAccessPanel />

      {/* Developer settings */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">Developer settings</h2>
        <p className="mt-1 text-xs text-muted">Endpoints and environment for building against this workspace.</p>
        <div className="mt-3 space-y-2 text-xs">
          <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
            <span className="text-muted">Kernel API base</span>
            <code className="font-mono text-foreground">{API_BASE}</code>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
            <span className="text-muted">Interactive docs</span>
            <a href={`${API_BASE}/docs`} target="_blank" rel="noreferrer" className="font-mono text-accent hover:underline">{API_BASE}/docs</a>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
            <span className="text-muted">OpenAPI spec</span>
            <a href={`${API_BASE}/api/dev/openapi.json`} target="_blank" rel="noreferrer" className="font-mono text-accent hover:underline">{API_BASE}/api/dev/openapi.json</a>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
            <span className="text-muted">Auth</span>
            <span className="text-muted">Bearer token via <code className="font-mono text-foreground">/api/auth/login</code> or an API key below</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Phase D: Insights ---------------- */

function InsightsView() {
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [objects, setObjects] = useState<ObjectCount[]>([]);
  const [cards, setCards] = useState<AgentScorecard[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(true);

  // analytics explorer state
  const [qObject, setQObject] = useState("");
  const [qMetric, setQMetric] = useState("count");
  const [qField, setQField] = useState("");
  const [qResult, setQResult] = useState<AnalyticsResult | null>(null);
  const [qBusy, setQBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ov, objs, cs, tl] = await Promise.all([
        api<WorkspaceOverview>("/api/insights/overview"),
        api<ObjectCount[]>("/api/insights/objects"),
        api<AgentScorecard[]>("/api/insights/agents"),
        api<TimelineItem[]>("/api/insights/timeline?limit=30"),
      ]);
      setOverview(ov);
      setObjects(objs);
      setCards(cs);
      setTimeline(tl);
      if (!qObject && objs.length > 0) setQObject(objs[0].slug);
    } catch {
      /* boot race */
    } finally {
      setLoading(false);
    }
  }, [qObject]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedObj = objects.find((o) => o.slug === qObject);
  const input = "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition focus:border-accent";

  async function runQuery() {
    if (!qObject) return;
    setQBusy(true);
    setQResult(null);
    try {
      const body: Record<string, unknown> = { object: qObject, metric: qMetric };
      if (qField) body.field = qField;
      const res = await api<AnalyticsResult>("/api/insights/query", { method: "POST", body });
      setQResult(res);
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Query failed", "error");
    } finally {
      setQBusy(false);
    }
  }

  const pct = (n: number | null) => (n === null ? "—" : `${Math.round(n * 100)}%`);
  const maxRow = qResult?.rows?.length ? Math.max(...qResult.rows.map((r) => r.value ?? 0), 1) : 1;
  const maxCount = qResult?.rows?.length ? Math.max(...qResult.rows.map((r) => r.count ?? 0), 1) : 1;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">Insights</h1>
        <p className="mt-0.5 text-xs text-muted">Analytics, agent performance, and everything that happened.</p>
      </div>

      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-24 w-full rounded-xl" />)}</div>
      ) : (
        <>
          {/* overview stats */}
          {overview && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                { label: "AI employees", value: `${overview.agents_active} / ${overview.agents_total}`, sub: "active / total" },
                { label: "Tasks", value: String(overview.tasks_total), sub: `${overview.tasks_done} done · ${overview.tasks_failed} failed` },
                { label: "Completion rate", value: pct(overview.completion_rate), sub: "done vs finished" },
                { label: "Tokens used", value: overview.tokens_total.toLocaleString(), sub: "across all agents" },
              ].map((s) => (
                <div key={s.label} className="rounded-xl border border-border bg-card p-4">
                  <div className="text-[11px] uppercase tracking-wide text-muted">{s.label}</div>
                  <div className="mt-1 text-2xl font-bold">{s.value}</div>
                  <div className="mt-0.5 text-[11px] text-faint">{s.sub}</div>
                </div>
              ))}
            </div>
          )}

          {/* object counts */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">Records by object</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {objects.map((o) => (
                <div key={o.slug} className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
                  <span className="text-base">{o.icon}</span>
                  <div>
                    <div className="text-sm font-semibold leading-none">{o.count}</div>
                    <div className="mt-0.5 text-[10px] text-muted">{o.name_plural}</div>
                  </div>
                </div>
              ))}
              {objects.length === 0 && <p className="text-xs text-muted">No objects yet.</p>}
            </div>
          </div>

          {/* analytics explorer */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">Analytics explorer</h2>
            <div className="mt-3 grid gap-2 md:grid-cols-4">
              <select className={input} value={qObject} onChange={(e) => { setQObject(e.target.value); setQField(""); setQResult(null); }}>
                {objects.map((o) => <option key={o.slug} value={o.slug}>{o.icon} {o.name}</option>)}
              </select>
              <select className={input} value={qMetric} onChange={(e) => { setQMetric(e.target.value); setQResult(null); }}>
                <option value="count">Count</option>
                <option value="group_by">Group by field</option>
                <option value="sum">Sum</option>
                <option value="avg">Average</option>
                <option value="min">Min</option>
                <option value="max">Max</option>
                <option value="time_series">Trend over time</option>
              </select>
              {(qMetric === "group_by" || ["sum", "avg", "min", "max"].includes(qMetric)) && (
                <select className={input} value={qField} onChange={(e) => setQField(e.target.value)}>
                  <option value="">— field —</option>
                  {(selectedObj?.fields ?? []).map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              )}
              <button disabled={qBusy || !qObject} onClick={runQuery} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                {qBusy ? "…" : "Run"}
              </button>
            </div>

            {qResult && (
              <div className="mt-4">
                {qResult.metric === "count" && (
                  <div className="text-3xl font-bold">{qResult.value}</div>
                )}
                {["sum", "avg", "min", "max"].includes(qResult.metric) && (
                  <div className="flex items-end gap-3">
                    <div className="text-3xl font-bold">{Number(qResult.value ?? 0).toLocaleString()}</div>
                    {qResult.summary && (
                      <div className="pb-1 text-[11px] text-muted">
                        sum {qResult.summary.sum.toLocaleString()} · avg {Math.round(qResult.summary.avg).toLocaleString()} · min {qResult.summary.min.toLocaleString()} · max {qResult.summary.max.toLocaleString()}
                      </div>
                    )}
                  </div>
                )}
                {qResult.metric === "group_by" && qResult.rows && (
                  <div className="space-y-1.5">
                    {qResult.rows.map((r) => (
                      <div key={r.key ?? ""} className="flex items-center gap-2">
                        <div className="w-32 truncate text-xs text-muted">{r.key ?? ""}</div>
                        <div className="h-4 flex-1 overflow-hidden rounded bg-background">
                          <div className="h-full rounded bg-accent/70" style={{ width: `${Math.max(2, ((r.value ?? 0) / maxRow) * 100)}%` }} />
                        </div>
                        <div className="w-16 text-right text-xs font-semibold">{Number(r.value ?? 0).toLocaleString()}</div>
                      </div>
                    ))}
                  </div>
                )}
                {qResult.metric === "time_series" && qResult.rows && (
                  <div className="flex h-24 items-end gap-1">
                    {qResult.rows.map((r, i) => (
                      <div key={i} className="flex-1 rounded-t bg-accent/70" style={{ height: `${Math.max(4, ((r.count ?? 0) / maxCount) * 100)}%` }} title={`${r.bucket ?? ""}: ${r.count ?? 0}`} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* agent scorecards */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">AI employee performance</h2>
            <div className="mt-3 space-y-2">
              {cards.length === 0 && <p className="text-xs text-muted">No AI employees yet.</p>}
              {cards.map((c) => (
                <div key={c.agent_id} className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-background px-4 py-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="text-lg">{c.icon}</span>
                    <div>
                      <div className="truncate text-sm font-semibold">{c.name}</div>
                      <div className="text-[10px] text-muted">{c.role || "—"}</div>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-sm font-bold">{c.tasks.done}<span className="text-faint">/{c.tasks.total}</span></div>
                    <div className="text-[10px] text-muted">done</div>
                  </div>
                  <div className="text-center">
                    <div className="text-sm font-bold">{pct(c.completion_rate)}</div>
                    <div className="text-[10px] text-muted">success</div>
                  </div>
                  <div className="text-center">
                    <div className="text-sm font-bold">{c.tokens.total_used.toLocaleString()}</div>
                    <div className="text-[10px] text-muted">tokens</div>
                  </div>
                  {c.tokens.utilization !== null && (
                    <div className="text-center">
                      <div className={`text-sm font-bold ${c.tokens.utilization > 0.9 ? "text-danger" : ""}`}>{pct(c.tokens.utilization)}</div>
                      <div className="text-[10px] text-muted">budget</div>
                    </div>
                  )}
                  <div className="ml-auto">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${c.status === "active" ? "bg-success/15 text-success" : "bg-border text-muted"}`}>{c.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* activity timeline */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">Activity</h2>
            <div className="mt-3 space-y-0">
              {timeline.length === 0 && <p className="text-xs text-muted">Nothing yet.</p>}
              {timeline.map((it) => (
                <div key={it.kind + it.id} className="relative flex gap-3 pb-4 last:pb-0">
                  <div className="flex flex-col items-center">
                    <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${it.kind === "task" ? "bg-accent" : it.actor_type === "agent" ? "bg-success" : "bg-border"}`} />
                    <span className="w-px flex-1 bg-border" />
                  </div>
                  <div className="min-w-0 pb-1">
                    <div className="text-xs">
                      <span className="font-semibold">{it.actor_name || (it.actor_type === "agent" ? "🤖" : "👤")}</span>{" "}
                      <span className="text-muted">{it.title}</span>
                      {it.detail && <span className="text-faint"> — {it.detail}</span>}
                    </div>
                    <div className="mt-0.5 text-[10px] text-faint">{it.at ? new Date(it.at).toLocaleString() : ""}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
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

/* ---------------- Phase AE: Subscriptions ---------------- */

interface PlanDef {
  id: string;
  name: string;
  description: string;
  interval: string;
  price_cents: number;
  currency: string;
  active: boolean;
  created_at: string | null;
}
interface SubDef {
  id: string;
  plan_id: string;
  customer: string;
  status: string;
  current_period_end: string;
  cancelled_at: string;
  created_at: string | null;
}

const SUB_STATUS_STYLE: Record<string, string> = {
  active: "bg-success/10 text-success",
  paused: "bg-warning/10 text-warning",
  cancelled: "bg-background text-muted",
};

function SubscriptionsView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [plans, setPlans] = useState<PlanDef[]>([]);
  const [subs, setSubs] = useState<SubDef[]>([]);
  const [mrr, setMrr] = useState<{ mrr_cents: number; active_subscriptions: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  // plan form
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [pName, setPName] = useState("");
  const [pInterval, setPInterval] = useState("monthly");
  const [pPrice, setPPrice] = useState("");

  // subscription form
  const [showSubForm, setShowSubForm] = useState(false);
  const [sPlan, setSPlan] = useState("");
  const [sCustomer, setSCustomer] = useState("");
  const [sPeriodEnd, setSPeriodEnd] = useState("");

  const load = useCallback(async () => {
    try {
      const [plansRes, subsRes, mrrRes] = await Promise.all([
        api<{ items: PlanDef[] }>("/api/subscriptions/plans"),
        api<{ items: SubDef[] }>(`/api/subscriptions${statusFilter ? `?status=${statusFilter}` : ""}`),
        api<{ mrr_cents: number; active_subscriptions: number }>("/api/subscriptions/mrr"),
      ]);
      setPlans(plansRes.items);
      setSubs(subsRes.items);
      setMrr(mrrRes);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const planById = (id: string) => plans.find((p) => p.id === id);

  async function createPlan() {
    if (!pName.trim()) {
      toast("Enter a plan name", "error");
      return;
    }
    setBusy("create-plan");
    try {
      await api("/api/subscriptions/plans", {
        method: "POST",
        body: { name: pName.trim(), interval: pInterval, price_cents: Math.max(0, Math.round((parseFloat(pPrice) || 0) * 100)) },
      });
      toast("Plan created", "success");
      setShowPlanForm(false);
      setPName(""); setPInterval("monthly"); setPPrice("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function createSub() {
    if (!sPlan || !sCustomer.trim()) {
      toast("Pick a plan and enter a customer", "error");
      return;
    }
    setBusy("create-sub");
    try {
      await api("/api/subscriptions", {
        method: "POST",
        body: { plan_id: sPlan, customer: sCustomer.trim(), current_period_end: sPeriodEnd },
      });
      toast("Subscription created", "success");
      setShowSubForm(false);
      setSPlan(""); setSCustomer(""); setSPeriodEnd("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function subAction(sub: SubDef, act: "pause" | "resume" | "cancel" | "reactivate") {
    setBusy(sub.id);
    try {
      await api(`/api/subscriptions/${sub.id}/${act}`, { method: "POST", body: {} });
      toast(`Subscription ${act === "pause" ? "paused" : act === "resume" ? "resumed" : act === "cancel" ? "cancelled" : "reactivated"}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeSub(sub: SubDef) {
    setBusy(sub.id);
    try {
      await api(`/api/subscriptions/${sub.id}`, { method: "DELETE" });
      toast(`Deleted subscription for ${sub.customer}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removePlan(plan: PlanDef) {
    setBusy(plan.id);
    try {
      await api(`/api/subscriptions/plans/${plan.id}`, { method: "DELETE" });
      toast(`Deleted plan ${plan.name}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Subscriptions</h1>
          <p className="mt-0.5 text-xs text-muted">Recurring billing — plans, customer subscriptions, and MRR.</p>
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
            <button onClick={() => setShowPlanForm((v) => !v)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
              {showPlanForm ? "Close" : "+ New plan"}
            </button>
            <button onClick={() => setShowSubForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
              {showSubForm ? "Close" : "+ New subscription"}
            </button>
          </div>
        )}
      </div>

      {/* MRR card */}
      {mrr && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="text-[10px] uppercase tracking-wide text-muted">Monthly recurring revenue</div>
            <div className="mt-1 text-2xl font-bold text-accent">{fmtCents(mrr.mrr_cents)}</div>
          </div>
          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="text-[10px] uppercase tracking-wide text-muted">Active subscriptions</div>
            <div className="mt-1 text-2xl font-bold">{mrr.active_subscriptions}</div>
          </div>
        </div>
      )}

      {/* plan form */}
      {showPlanForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New plan</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted">
              Name
              <input value={pName} onChange={(e) => setPName(e.target.value)} placeholder="Pro"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Interval
              <select value={pInterval} onChange={(e) => setPInterval(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                <option value="monthly">monthly</option>
                <option value="yearly">yearly</option>
              </select>
            </label>
            <label className="text-xs text-muted">
              Price
              <input type="number" min={0} step="0.01" value={pPrice} onChange={(e) => setPPrice(e.target.value)} placeholder="49.00"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button onClick={createPlan} disabled={busy === "create-plan" || !pName.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create-plan" ? "Creating…" : "Create plan"}
            </button>
            <button onClick={() => setShowPlanForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
          </div>
        </div>
      )}

      {/* subscription form */}
      {showSubForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New subscription</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted">
              Plan
              <select value={sPlan} onChange={(e) => setSPlan(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                <option value="">Select a plan…</option>
                {plans.filter((p) => p.active).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({fmtCents(p.price_cents)}/{p.interval === "monthly" ? "mo" : "yr"})</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted">
              Customer
              <input value={sCustomer} onChange={(e) => setSCustomer(e.target.value)} placeholder="Acme Corp"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Period ends
              <input type="date" value={sPeriodEnd} onChange={(e) => setSPeriodEnd(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button onClick={createSub} disabled={busy === "create-sub" || !sPlan || !sCustomer.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create-sub" ? "Creating…" : "Create subscription"}
            </button>
            <button onClick={() => setShowSubForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
          </div>
        </div>
      )}

      {/* plans */}
      <div>
        <h2 className="mb-2 text-sm font-semibold">Plans</h2>
        {loading ? (
          <div className="skeleton h-16 w-full rounded-xl" />
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {plans.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{p.name}</span>
                    {!p.active && <span className="rounded-full bg-background px-2 py-0.5 text-[10px] text-muted">inactive</span>}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">{fmtCents(p.price_cents)} / {p.interval === "monthly" ? "month" : "year"}</div>
                </div>
                {isAdmin && (
                  <button onClick={() => removePlan(p)} disabled={busy === p.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                )}
              </div>
            ))}
            {plans.length === 0 && (
              <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted md:col-span-2">
                No plans yet. Create one to start selling subscriptions.
              </div>
            )}
          </div>
        )}
      </div>

      {/* subscriptions */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Subscriptions</h2>
          <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
            {["", "active", "paused", "cancelled"].map((st) => (
              <button key={st} onClick={() => setStatusFilter(st)}
                className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
                {st || "All"}
              </button>
            ))}
          </div>
        </div>
        {loading ? (
          <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="skeleton h-14 w-full rounded-xl" />)}</div>
        ) : (
          <div className="space-y-2">
            {subs.map((sub) => {
              const plan = planById(sub.plan_id);
              return (
                <div key={sub.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{sub.customer}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${SUB_STATUS_STYLE[sub.status] ?? "bg-background text-muted"}`}>{sub.status}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {plan ? `${plan.name} · ${fmtCents(plan.price_cents)}/${plan.interval === "monthly" ? "mo" : "yr"}` : "unknown plan"}
                      {sub.current_period_end && <span> · renews {sub.current_period_end}</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {canEdit && sub.status === "active" && (
                      <>
                        <button onClick={() => subAction(sub, "pause")} disabled={busy === sub.id}
                          className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Pause</button>
                        <button onClick={() => subAction(sub, "cancel")} disabled={busy === sub.id}
                          className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Cancel</button>
                      </>
                    )}
                    {canEdit && sub.status === "paused" && (
                      <button onClick={() => subAction(sub, "resume")} disabled={busy === sub.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Resume</button>
                    )}
                    {canEdit && sub.status === "cancelled" && (
                      <button onClick={() => subAction(sub, "reactivate")} disabled={busy === sub.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Reactivate</button>
                    )}
                    {isAdmin && (
                      <button onClick={() => removeSub(sub)} disabled={busy === sub.id}
                        className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                    )}
                  </div>
                </div>
              );
            })}
            {subs.length === 0 && (
              <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
                No subscriptions yet. Create one to start tracking recurring revenue.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Phase AD: Assets ---------------- */

interface AssetDef {
  id: string;
  tag: string;
  name: string;
  category: string;
  description: string;
  cost_cents: number;
  currency: string;
  purchase_date: string;
  status: string;
  assignee_id: string | null;
  location: string;
  created_at: string | null;
}
interface AssetHistoryDef {
  id: string;
  asset_id: string;
  action: string;
  detail: string;
  actor_id: string | null;
  created_at: string | null;
}

const ASSET_STATUS_STYLE: Record<string, string> = {
  available: "bg-success/10 text-success",
  assigned: "bg-accent/10 text-accent",
  maintenance: "bg-warning/10 text-warning",
  retired: "bg-background text-muted",
};

function AssetsView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [assets, setAssets] = useState<AssetDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<string, AssetHistoryDef[]>>({});

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fCategory, setFCategory] = useState("General");
  const [fDesc, setFDesc] = useState("");
  const [fCost, setFCost] = useState("");
  const [fDate, setFDate] = useState("");
  const [fLocation, setFLocation] = useState("");

  const load = useCallback(async () => {
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const res = await api<{ items: AssetDef[]; total: number }>(`/api/assets${qs}`);
      setAssets(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function createAsset() {
    if (!fName.trim()) {
      toast("Enter an asset name", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/assets", {
        method: "POST",
        body: {
          name: fName.trim(), category: fCategory, description: fDesc,
          cost_cents: Math.max(0, Math.round((parseFloat(fCost) || 0) * 100)),
          purchase_date: fDate, location: fLocation.trim(),
        },
      });
      toast("Asset created", "success");
      setShowForm(false);
      setFName(""); setFCategory("General"); setFDesc(""); setFCost(""); setFDate(""); setFLocation("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(a: AssetDef, act: "return" | "maintenance" | "retire" | "restore") {
    setBusy(a.id);
    try {
      await api(`/api/assets/${a.id}/${act}`, { method: "POST", body: {} });
      toast(`Asset ${act === "return" ? "returned" : act + (act === "maintenance" ? "" : act === "retire" ? "d" : "d")}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeAsset(a: AssetDef) {
    setBusy(a.id);
    try {
      await api(`/api/assets/${a.id}`, { method: "DELETE" });
      toast(`Deleted ${a.tag}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function toggleExpand(a: AssetDef) {
    const next = expanded === a.id ? null : a.id;
    setExpanded(next);
    if (next && !history[a.id]) {
      try {
        const res = await api<{ items: AssetHistoryDef[] }>(`/api/assets/${a.id}/history`);
        setHistory((prev) => ({ ...prev, [a.id]: res.items }));
      } catch {
        setHistory((prev) => ({ ...prev, [a.id]: [] }));
      }
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Assets</h1>
          <p className="mt-0.5 text-xs text-muted">Track company assets — assign, maintain, and retire with a full audit trail.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New asset"}
          </button>
        )}
      </div>

      {/* status filter */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        {["", "available", "assigned", "maintenance", "retired"].map((st) => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
            {st || "All"}
          </button>
        ))}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New asset</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="MacBook Pro 16"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Category
              <input value={fCategory} onChange={(e) => setFCategory(e.target.value)} placeholder="Laptop"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Description
              <textarea value={fDesc} onChange={(e) => setFDesc(e.target.value)} rows={2} placeholder="What is this asset?"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Cost
              <input type="number" min={0} step="0.01" value={fCost} onChange={(e) => setFCost(e.target.value)} placeholder="2499.00"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Purchase date
              <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Location
              <input value={fLocation} onChange={(e) => setFLocation(e.target.value)} placeholder="HQ"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button onClick={createAsset} disabled={busy === "create" || !fName.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create asset"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
          </div>
        </div>
      )}

      {/* asset list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {assets.map((a) => (
            <div key={a.id} className="rounded-xl border border-border bg-card">
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <button onClick={() => toggleExpand(a)} className="flex min-w-0 items-center gap-3 text-left">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{a.tag}</span>
                      <span className="text-sm">{a.name}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${ASSET_STATUS_STYLE[a.status] ?? "bg-background text-muted"}`}>{a.status}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {a.category}
                      {a.location && <span> · {a.location}</span>}
                      {a.cost_cents > 0 && <span> · {fmtCents(a.cost_cents)}</span>}
                      {a.purchase_date && <span> · bought {a.purchase_date}</span>}
                    </div>
                  </div>
                </button>
                <div className="flex shrink-0 items-center gap-2">
                  {canEdit && a.status === "assigned" && (
                    <button onClick={() => action(a, "return")} disabled={busy === a.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent disabled:opacity-50">Return</button>
                  )}
                  {canEdit && (a.status === "available" || a.status === "assigned") && (
                    <button onClick={() => action(a, "maintenance")} disabled={busy === a.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Maintenance</button>
                  )}
                  {canEdit && a.status !== "retired" && (
                    <button onClick={() => action(a, "retire")} disabled={busy === a.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Retire</button>
                  )}
                  {canEdit && (a.status === "retired" || a.status === "maintenance") && (
                    <button onClick={() => action(a, "restore")} disabled={busy === a.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Restore</button>
                  )}
                  {isAdmin && (
                    <button onClick={() => removeAsset(a)} disabled={busy === a.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                  )}
                </div>
              </div>
              {/* expanded: description + history */}
              {expanded === a.id && (
                <div className="border-t border-border px-4 py-3">
                  {a.description && <p className="text-xs text-muted">{a.description}</p>}
                  <div className="mt-3 space-y-2">
                    <div className="text-xs font-semibold text-muted">History</div>
                    {(history[a.id] ?? []).map((h) => (
                      <div key={h.id} className="flex items-center gap-2 rounded-lg bg-background px-3 py-2 text-xs">
                        <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent">{h.action}</span>
                        {h.detail && <span className="text-muted">{h.detail}</span>}
                        {h.created_at && <span className="ml-auto text-[10px] text-muted">{new Date(h.created_at).toLocaleString()}</span>}
                      </div>
                    ))}
                    {(history[a.id] ?? []).length === 0 && <p className="text-xs text-muted">No history yet.</p>}
                  </div>
                </div>
              )}
            </div>
          ))}
          {assets.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No assets yet. Add one to start tracking company equipment.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase AC: Campaigns ---------------- */

interface CampaignDef {
  id: string;
  name: string;
  channel: string;
  subject: string;
  content: string;
  audience: string;
  audience_size: number;
  status: string;
  scheduled_for: string;
  sent_at: string;
  sent_count: number;
  opened_count: number;
  clicked_count: number;
  open_rate: number;
  click_rate: number;
  created_at: string | null;
}

const CAMPAIGN_STATUS_STYLE: Record<string, string> = {
  draft: "bg-background text-muted",
  scheduled: "bg-accent/10 text-accent",
  sent: "bg-warning/10 text-warning",
  completed: "bg-success/10 text-success",
};
const CAMPAIGN_CHANNEL_ICON: Record<string, string> = {
  email: "✉️",
  sms: "💬",
  social: "📣",
  ads: "🎯",
};

function CampaignsView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [campaigns, setCampaigns] = useState<CampaignDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fChannel, setFChannel] = useState("email");
  const [fSubject, setFSubject] = useState("");
  const [fContent, setFContent] = useState("");
  const [fAudience, setFAudience] = useState("");
  const [fSize, setFSize] = useState("");
  const [fScheduled, setFScheduled] = useState("");

  const load = useCallback(async () => {
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const res = await api<{ items: CampaignDef[]; total: number }>(`/api/campaigns${qs}`);
      setCampaigns(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function createCampaign() {
    if (!fName.trim()) {
      toast("Enter a campaign name", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/campaigns", {
        method: "POST",
        body: {
          name: fName.trim(), channel: fChannel, subject: fSubject, content: fContent,
          audience: fAudience.trim(), audience_size: Math.max(0, parseInt(fSize) || 0),
          scheduled_for: fScheduled,
        },
      });
      toast("Campaign created", "success");
      setShowForm(false);
      setFName(""); setFChannel("email"); setFSubject(""); setFContent("");
      setFAudience(""); setFSize(""); setFScheduled("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(c: CampaignDef, act: "schedule" | "send" | "complete") {
    setBusy(c.id);
    try {
      await api(`/api/campaigns/${c.id}/${act}`, { method: "POST", body: {} });
      toast(`Campaign ${act === "send" ? "sent" : act + (act === "schedule" ? "d" : "d")}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeCampaign(c: CampaignDef) {
    setBusy(c.id);
    try {
      await api(`/api/campaigns/${c.id}`, { method: "DELETE" });
      toast(`Deleted ${c.name}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Campaigns</h1>
          <p className="mt-0.5 text-xs text-muted">Marketing pushes across email, SMS, social, and ads — with performance tracking.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New campaign"}
          </button>
        )}
      </div>

      {/* status filter */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        {["", "draft", "scheduled", "sent", "completed"].map((st) => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
            {st || "All"}
          </button>
        ))}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New campaign</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Summer Sale"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Channel
              <select value={fChannel} onChange={(e) => setFChannel(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                {["email", "sms", "social", "ads"].map((ch) => <option key={ch} value={ch}>{ch}</option>)}
              </select>
            </label>
            <label className="text-xs text-muted">
              Subject
              <input value={fSubject} onChange={(e) => setFSubject(e.target.value)} placeholder="50% off"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Audience size
              <input type="number" min={0} value={fSize} onChange={(e) => setFSize(e.target.value)} placeholder="1000"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Audience
              <input value={fAudience} onChange={(e) => setFAudience(e.target.value)} placeholder="all active customers"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Content
              <textarea value={fContent} onChange={(e) => setFContent(e.target.value)} rows={2} placeholder="Message body"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Scheduled for
              <input type="datetime-local" value={fScheduled} onChange={(e) => setFScheduled(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button onClick={createCampaign} disabled={busy === "create" || !fName.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create campaign"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
          </div>
        </div>
      )}

      {/* campaign list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {campaigns.map((c) => (
            <div key={c.id} className="rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-base">{CAMPAIGN_CHANNEL_ICON[c.channel] ?? "📣"}</span>
                    <span className="text-sm font-semibold">{c.name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${CAMPAIGN_STATUS_STYLE[c.status] ?? "bg-background text-muted"}`}>{c.status}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {c.subject || c.channel}{c.audience && <span> · {c.audience}</span>}
                    {c.scheduled_for && c.status === "scheduled" && <span> · scheduled {new Date(c.scheduled_for).toLocaleString()}</span>}
                    {c.sent_at && <span> · sent {new Date(c.sent_at).toLocaleString()}</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {canEdit && c.status === "draft" && (
                    <>
                      <button onClick={() => action(c, "schedule")} disabled={busy === c.id || !c.scheduled_for}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent disabled:opacity-50">Schedule</button>
                      <button onClick={() => action(c, "send")} disabled={busy === c.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Send now</button>
                    </>
                  )}
                  {canEdit && c.status === "scheduled" && (
                    <button onClick={() => action(c, "send")} disabled={busy === c.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Send now</button>
                  )}
                  {canEdit && c.status === "sent" && (
                    <button onClick={() => action(c, "complete")} disabled={busy === c.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Complete</button>
                  )}
                  {isAdmin && (
                    <button onClick={() => removeCampaign(c)} disabled={busy === c.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                  )}
                </div>
              </div>
              {/* performance metrics */}
              {(c.status === "sent" || c.status === "completed") && (
                <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-3 sm:grid-cols-5">
                  <div><div className="text-[10px] text-muted">Sent</div><div className="text-sm font-bold">{c.sent_count}</div></div>
                  <div><div className="text-[10px] text-muted">Opened</div><div className="text-sm font-bold">{c.opened_count}</div></div>
                  <div><div className="text-[10px] text-muted">Clicked</div><div className="text-sm font-bold">{c.clicked_count}</div></div>
                  <div><div className="text-[10px] text-muted">Open rate</div><div className="text-sm font-bold text-accent">{c.open_rate}%</div></div>
                  <div><div className="text-[10px] text-muted">Click rate</div><div className="text-sm font-bold text-success">{c.click_rate}%</div></div>
                </div>
              )}
            </div>
          ))}
          {campaigns.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No campaigns yet. Create one to start reaching your audience.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase AB: Support Tickets ---------------- */

interface TicketDef {
  id: string;
  number: string;
  subject: string;
  description: string;
  requester_email: string;
  category: string;
  priority: string;
  status: string;
  assignee_id: string | null;
  sla_hours: number;
  sla_breached: boolean;
  resolved_at: string;
  closed_at: string;
  created_at: string | null;
}
interface TicketCommentDef {
  id: string;
  body: string;
  internal: boolean;
  author_id: string | null;
  created_at: string | null;
}

const TICKET_STATUS_STYLE: Record<string, string> = {
  open: "bg-accent/10 text-accent",
  in_progress: "bg-warning/10 text-warning",
  resolved: "bg-success/10 text-success",
  closed: "bg-background text-muted",
};
const TICKET_PRIORITY_STYLE: Record<string, string> = {
  low: "bg-background text-muted",
  medium: "bg-accent/10 text-accent",
  high: "bg-warning/10 text-warning",
  urgent: "bg-danger/10 text-danger",
};

function TicketsView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [tickets, setTickets] = useState<TicketDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, TicketCommentDef[]>>({});
  const [commentDraft, setCommentDraft] = useState("");

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fSubject, setFSubject] = useState("");
  const [fDesc, setFDesc] = useState("");
  const [fEmail, setFEmail] = useState("");
  const [fCategory, setFCategory] = useState("General");
  const [fPriority, setFPriority] = useState("medium");

  const load = useCallback(async () => {
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const res = await api<{ items: TicketDef[]; total: number }>(`/api/tickets${qs}`);
      setTickets(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function createTicket() {
    if (!fSubject.trim()) {
      toast("Enter a subject", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/tickets", {
        method: "POST",
        body: {
          subject: fSubject.trim(), description: fDesc, requester_email: fEmail.trim(),
          category: fCategory, priority: fPriority,
        },
      });
      toast("Ticket created", "success");
      setShowForm(false);
      setFSubject(""); setFDesc(""); setFEmail(""); setFCategory("General"); setFPriority("medium");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(t: TicketDef, act: "start" | "resolve" | "close" | "reopen") {
    setBusy(t.id);
    try {
      await api(`/api/tickets/${t.id}/${act}`, { method: "POST", body: {} });
      toast(`Ticket ${act === "start" ? "started" : act + (act === "close" ? "d" : act === "reopen" ? "ed" : "d")}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeTicket(t: TicketDef) {
    setBusy(t.id);
    try {
      await api(`/api/tickets/${t.id}`, { method: "DELETE" });
      toast(`Deleted ${t.number}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function toggleExpand(t: TicketDef) {
    const next = expanded === t.id ? null : t.id;
    setExpanded(next);
    if (next && !comments[t.id]) {
      try {
        const res = await api<{ items: TicketCommentDef[] }>(`/api/tickets/${t.id}/comments`);
        setComments((prev) => ({ ...prev, [t.id]: res.items }));
      } catch {
        setComments((prev) => ({ ...prev, [t.id]: [] }));
      }
    }
  }

  async function addComment(t: TicketDef) {
    if (!commentDraft.trim()) return;
    setBusy(t.id);
    try {
      await api(`/api/tickets/${t.id}/comments`, { method: "POST", body: { body: commentDraft.trim() } });
      setCommentDraft("");
      const res = await api<{ items: TicketCommentDef[] }>(`/api/tickets/${t.id}/comments`);
      setComments((prev) => ({ ...prev, [t.id]: res.items }));
      toast("Comment added", "success");
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Comment failed", "error");
    } finally {
      setBusy(null);
    }
  }

  const breachedCount = tickets.filter((t) => t.sla_breached).length;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Support Tickets</h1>
          <p className="mt-0.5 text-xs text-muted">Helpdesk — track, assign, and resolve customer issues with SLAs.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New ticket"}
          </button>
        )}
      </div>

      {/* SLA breach banner */}
      {breachedCount > 0 && (
        <div className="rounded-xl border border-danger/40 bg-danger/5 px-4 py-3 text-sm font-semibold text-danger">
          {breachedCount} ticket{breachedCount > 1 ? "s have" : " has"} breached SLA — prioritize these.
        </div>
      )}

      {/* status filter */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        {["", "open", "in_progress", "resolved", "closed"].map((st) => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
            {st ? st.replace("_", " ") : "All"}
          </button>
        ))}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New ticket</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted md:col-span-2">
              Subject
              <input value={fSubject} onChange={(e) => setFSubject(e.target.value)} placeholder="Cannot login"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Description
              <textarea value={fDesc} onChange={(e) => setFDesc(e.target.value)} rows={2} placeholder="What is happening?"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Requester email
              <input value={fEmail} onChange={(e) => setFEmail(e.target.value)} placeholder="cust@example.com"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Category
              <input value={fCategory} onChange={(e) => setFCategory(e.target.value)} placeholder="General"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Priority
              <select value={fPriority} onChange={(e) => setFPriority(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                {["low", "medium", "high", "urgent"].map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button onClick={createTicket} disabled={busy === "create" || !fSubject.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create ticket"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
          </div>
        </div>
      )}

      {/* ticket list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {tickets.map((t) => (
            <div key={t.id} className="rounded-xl border border-border bg-card">
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <button onClick={() => toggleExpand(t)} className="flex min-w-0 items-center gap-3 text-left">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{t.number}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${TICKET_STATUS_STYLE[t.status] ?? "bg-background text-muted"}`}>{t.status.replace("_", " ")}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${TICKET_PRIORITY_STYLE[t.priority] ?? "bg-background text-muted"}`}>{t.priority}</span>
                      {t.sla_breached && <span className="rounded-full bg-danger/10 px-2 py-0.5 text-[10px] font-semibold text-danger">SLA breached</span>}
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {t.subject}
                      {t.requester_email && <span> · {t.requester_email}</span>}
                      <span> · SLA {t.sla_hours}h</span>
                    </div>
                  </div>
                </button>
                <div className="flex shrink-0 items-center gap-2">
                  {canEdit && t.status === "open" && (
                    <>
                      <button onClick={() => action(t, "start")} disabled={busy === t.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent disabled:opacity-50">Start</button>
                      <button onClick={() => action(t, "resolve")} disabled={busy === t.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Resolve</button>
                    </>
                  )}
                  {canEdit && t.status === "in_progress" && (
                    <button onClick={() => action(t, "resolve")} disabled={busy === t.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Resolve</button>
                  )}
                  {canEdit && t.status === "resolved" && (
                    <>
                      <button onClick={() => action(t, "close")} disabled={busy === t.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50">Close</button>
                      <button onClick={() => action(t, "reopen")} disabled={busy === t.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Reopen</button>
                    </>
                  )}
                  {canEdit && t.status === "closed" && (
                    <button onClick={() => action(t, "reopen")} disabled={busy === t.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Reopen</button>
                  )}
                  {isAdmin && (
                    <button onClick={() => removeTicket(t)} disabled={busy === t.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                  )}
                </div>
              </div>
              {/* expanded: description + comments */}
              {expanded === t.id && (
                <div className="border-t border-border px-4 py-3">
                  {t.description && <p className="text-xs text-muted">{t.description}</p>}
                  <div className="mt-3 space-y-2">
                    <div className="text-xs font-semibold text-muted">Comments</div>
                    {(comments[t.id] ?? []).map((c) => (
                      <div key={c.id} className={`rounded-lg px-3 py-2 text-xs ${c.internal ? "bg-warning/5 border border-warning/30" : "bg-background"}`}>
                        <span>{c.body}</span>
                        {c.internal && <span className="ml-2 rounded-full bg-warning/10 px-2 py-0.5 text-[10px] text-warning">internal</span>}
                        {c.created_at && <span className="ml-2 text-[10px] text-muted">{new Date(c.created_at).toLocaleString()}</span>}
                      </div>
                    ))}
                    {(comments[t.id] ?? []).length === 0 && <p className="text-xs text-muted">No comments yet.</p>}
                    {canEdit && (
                      <div className="flex items-center gap-2">
                        <input value={commentDraft} onChange={(e) => setCommentDraft(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") addComment(t); }}
                          placeholder="Add a comment…"
                          className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground outline-none focus:border-accent" />
                        <button onClick={() => addComment(t)} disabled={busy === t.id || !commentDraft.trim()}
                          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">Post</button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
          {tickets.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No tickets yet. Create one to start tracking support issues.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase AA: Contracts ---------------- */

interface ContractDef {
  id: string;
  number: string;
  name: string;
  counterparty: string;
  notes: string;
  currency: string;
  value_cents: number;
  status: string;
  start_date: string;
  end_date: string;
  auto_renew: boolean;
  renewal_notice_days: number;
  days_until_end?: number | null;
  created_at: string | null;
}

const CONTRACT_STATUS_STYLE: Record<string, string> = {
  draft: "bg-background text-muted",
  active: "bg-success/10 text-success",
  expired: "bg-warning/10 text-warning",
  cancelled: "bg-danger/10 text-danger",
};

function ContractsView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [contracts, setContracts] = useState<ContractDef[]>([]);
  const [renewals, setRenewals] = useState<ContractDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fCounterparty, setFCounterparty] = useState("");
  const [fValue, setFValue] = useState("");
  const [fStart, setFStart] = useState("");
  const [fEnd, setFEnd] = useState("");
  const [fAutoRenew, setFAutoRenew] = useState(false);
  const [fNotice, setFNotice] = useState("30");

  const load = useCallback(async () => {
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const [res, ren] = await Promise.all([
        api<{ items: ContractDef[]; total: number }>(`/api/contracts${qs}`),
        api<{ items: ContractDef[]; total: number }>("/api/contracts/renewals"),
      ]);
      setContracts(res.items);
      setRenewals(ren.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function createContract() {
    if (!fName.trim()) {
      toast("Enter a contract name", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/contracts", {
        method: "POST",
        body: {
          name: fName.trim(),
          counterparty: fCounterparty.trim(),
          value_cents: Math.max(0, Math.round((parseFloat(fValue) || 0) * 100)),
          start_date: fStart,
          end_date: fEnd,
          auto_renew: fAutoRenew,
          renewal_notice_days: Math.max(0, parseInt(fNotice) || 30),
        },
      });
      toast("Contract created", "success");
      setShowForm(false);
      setFName(""); setFCounterparty(""); setFValue(""); setFStart(""); setFEnd("");
      setFAutoRenew(false); setFNotice("30");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(c: ContractDef, act: "activate" | "cancel" | "expire") {
    setBusy(c.id);
    try {
      await api(`/api/contracts/${c.id}/${act}`, { method: "POST", body: {} });
      toast(`Contract ${act === "activate" ? "activated" : act + (act === "cancel" ? "led" : "d")}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeContract(c: ContractDef) {
    setBusy(c.id);
    try {
      await api(`/api/contracts/${c.id}`, { method: "DELETE" });
      toast(`Deleted ${c.number}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Contracts</h1>
          <p className="mt-0.5 text-xs text-muted">Agreements with customers &amp; vendors — value, dates, and renewals.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New contract"}
          </button>
        )}
      </div>

      {/* renewal alerts */}
      {renewals.length > 0 && (
        <div className="rounded-xl border border-warning/40 bg-warning/5 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-warning">
            <FileSignature size={14} />
            {renewals.length} contract{renewals.length > 1 ? "s" : ""} need{renewals.length === 1 ? "s" : ""} renewal attention
          </div>
          <div className="mt-2 space-y-1">
            {renewals.map((r) => (
              <div key={r.id} className="flex items-center justify-between text-xs">
                <span>{r.number} · {r.name} ({r.counterparty || "—"})</span>
                <span className={r.days_until_end !== null && r.days_until_end! < 0 ? "font-semibold text-danger" : "text-muted"}>
                  {r.days_until_end !== null && r.days_until_end! < 0
                    ? `ended ${Math.abs(r.days_until_end!)} days ago`
                    : `${r.days_until_end} days left`}
                  {r.auto_renew && " · auto-renew"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* status filter */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        {["", "draft", "active", "expired", "cancelled"].map((st) => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
            {st || "All"}
          </button>
        ))}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New contract</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Annual SaaS"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Counterparty
              <input value={fCounterparty} onChange={(e) => setFCounterparty(e.target.value)} placeholder="Acme Corp"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Value ($)
              <input type="number" min={0} step="0.01" value={fValue} onChange={(e) => setFValue(e.target.value)} placeholder="12000.00"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Renewal notice (days)
              <input type="number" min={0} value={fNotice} onChange={(e) => setFNotice(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Start date
              <input type="date" value={fStart} onChange={(e) => setFStart(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              End date
              <input type="date" value={fEnd} onChange={(e) => setFEnd(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <label className="mt-3 flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={fAutoRenew} onChange={(e) => setFAutoRenew(e.target.checked)} className="accent-accent" />
            Auto-renew
          </label>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button onClick={createContract} disabled={busy === "create" || !fName.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create contract"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
          </div>
        </div>
      )}

      {/* contract list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {contracts.map((c) => (
            <div key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{c.number}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${CONTRACT_STATUS_STYLE[c.status] ?? "bg-background text-muted"}`}>{c.status}</span>
                  {c.auto_renew && <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent">auto-renew</span>}
                </div>
                <div className="mt-0.5 text-xs text-muted">
                  {c.name}{c.counterparty && <span> · {c.counterparty}</span>}
                  {c.start_date && c.end_date && <span> · {c.start_date} → {c.end_date}</span>}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="text-sm font-bold">{fmtCents(c.value_cents, c.currency)}</span>
                {canEdit && c.status === "draft" && (
                  <button onClick={() => action(c, "activate")} disabled={busy === c.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Activate</button>
                )}
                {canEdit && c.status === "active" && (
                  <>
                    <button onClick={() => action(c, "expire")} disabled={busy === c.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">Expire</button>
                    <button onClick={() => action(c, "cancel")} disabled={busy === c.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Cancel</button>
                  </>
                )}
                {canEdit && c.status === "draft" && (
                  <button onClick={() => action(c, "cancel")} disabled={busy === c.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Cancel</button>
                )}
                {isAdmin && (
                  <button onClick={() => removeContract(c)} disabled={busy === c.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                )}
              </div>
            </div>
          ))}
          {contracts.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No contracts yet. Create one to start tracking agreements and renewals.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase Z: Purchase Orders ---------------- */

interface POLineItem {
  product_id: string;
  description: string;
  quantity: number;
  unit_cost_cents: number;
}
interface PODef {
  id: string;
  number: string;
  vendor_name: string;
  notes: string;
  currency: string;
  status: string;
  expected_date: string;
  line_items: POLineItem[];
  total_cents: number;
  received_at: string;
  created_at: string | null;
}
interface ProductPick {
  id: string;
  name: string;
  sku: string;
  quantity: number;
}

const PO_STATUS_STYLE: Record<string, string> = {
  draft: "bg-background text-muted",
  sent: "bg-accent/10 text-accent",
  received: "bg-success/10 text-success",
  cancelled: "bg-danger/10 text-danger",
};

function PurchaseOrdersView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [pos, setPos] = useState<PODef[]>([]);
  const [products, setProducts] = useState<ProductPick[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fVendor, setFVendor] = useState("");
  const [fExpected, setFExpected] = useState("");
  const [fItems, setFItems] = useState<POLineItem[]>([]);

  const load = useCallback(async () => {
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const [poRes, prodRes] = await Promise.all([
        api<{ items: PODef[]; total: number }>(`/api/purchase-orders${qs}`),
        api<{ items: ProductPick[] } | ProductPick[]>("/api/inventory/products"),
      ]);
      setPos(poRes.items);
      setProducts(Array.isArray(prodRes) ? prodRes : prodRes.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function addProductLine(productId: string) {
    const prod = products.find((p) => p.id === productId);
    if (!prod) return;
    setFItems((prev) => [...prev, { product_id: prod.id, description: prod.name, quantity: 1, unit_cost_cents: 0 }]);
  }

  function updateLine(idx: number, patch: Partial<POLineItem>) {
    setFItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  async function createPO() {
    if (!fVendor.trim()) {
      toast("Enter a vendor name", "error");
      return;
    }
    if (fItems.length === 0) {
      toast("Add at least one product line", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/purchase-orders", {
        method: "POST",
        body: { vendor_name: fVendor.trim(), expected_date: fExpected, line_items: fItems },
      });
      toast("Purchase order created", "success");
      setShowForm(false);
      setFVendor(""); setFExpected(""); setFItems([]);
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(po: PODef, act: "send" | "receive" | "cancel") {
    setBusy(po.id);
    try {
      await api(`/api/purchase-orders/${po.id}/${act}`, { method: "POST", body: {} });
      toast(`PO ${act === "receive" ? "received into inventory" : act + (act === "cancel" ? "led" : "ed")}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removePO(po: PODef) {
    setBusy(po.id);
    try {
      await api(`/api/purchase-orders/${po.id}`, { method: "DELETE" });
      toast(`Deleted ${po.number}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  const formTotal = fItems.reduce((a, i) => a + i.quantity * i.unit_cost_cents, 0);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Purchase Orders</h1>
          <p className="mt-0.5 text-xs text-muted">Procurement orders — send to vendors and receive into inventory.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New PO"}
          </button>
        )}
      </div>

      {/* status filter */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        {["", "draft", "sent", "received", "cancelled"].map((st) => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
            {st || "All"}
          </button>
        ))}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New purchase order</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Vendor
              <input value={fVendor} onChange={(e) => setFVendor(e.target.value)} placeholder="Supplier Co"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Expected date
              <input type="date" value={fExpected} onChange={(e) => setFExpected(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          {/* product lines */}
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted">Products</span>
              <select onChange={(e) => { if (e.target.value) { addProductLine(e.target.value); e.target.value = ""; } }}
                className="rounded-lg border border-border bg-background px-2 py-1 text-xs text-foreground outline-none focus:border-accent" defaultValue="">
                <option value="" disabled>+ Add product…</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.sku}) — {p.quantity} in stock</option>
                ))}
              </select>
            </div>
            {fItems.map((item, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <span className="flex-1 truncate text-sm">{item.description}</span>
                <input type="number" min={1} value={item.quantity} onChange={(e) => updateLine(idx, { quantity: Math.max(1, parseInt(e.target.value) || 1) })}
                  className="w-16 rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                <input type="number" min={0} step={100} value={item.unit_cost_cents} onChange={(e) => updateLine(idx, { unit_cost_cents: Math.max(0, parseInt(e.target.value) || 0) })}
                  placeholder="¢" className="w-24 rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                <span className="w-20 text-right text-xs text-muted">{fmtCents(item.quantity * item.unit_cost_cents)}</span>
                <button onClick={() => setFItems((p) => p.filter((_, i) => i !== idx))} className="text-muted hover:text-danger"><Trash2 size={13} /></button>
              </div>
            ))}
            {fItems.length === 0 && <p className="text-xs text-muted">No products added yet. Use the dropdown above.</p>}
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-sm font-semibold">Total: {fmtCents(formTotal)}</span>
            <div className="flex items-center gap-2">
              <button onClick={createPO} disabled={busy === "create" || !fVendor.trim() || fItems.length === 0}
                className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                {busy === "create" ? "Creating…" : "Create PO"}
              </button>
              <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* PO list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {pos.map((po) => (
            <div key={po.id} className="rounded-xl border border-border bg-card">
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <button onClick={() => setExpanded(expanded === po.id ? null : po.id)} className="flex min-w-0 items-center gap-3 text-left">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{po.number}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${PO_STATUS_STYLE[po.status] ?? "bg-background text-muted"}`}>{po.status}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {po.vendor_name || "—"}
                      {po.expected_date && <span> · expected {po.expected_date}</span>}
                      {po.received_at && <span> · received {new Date(po.received_at).toLocaleDateString()}</span>}
                    </div>
                  </div>
                </button>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="text-sm font-bold">{fmtCents(po.total_cents, po.currency)}</span>
                  {canEdit && po.status === "draft" && (
                    <>
                      <button onClick={() => action(po, "send")} disabled={busy === po.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent disabled:opacity-50">Send</button>
                      <button onClick={() => action(po, "cancel")} disabled={busy === po.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Cancel</button>
                    </>
                  )}
                  {canEdit && po.status === "sent" && (
                    <>
                      <button onClick={() => action(po, "receive")} disabled={busy === po.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Receive</button>
                      <button onClick={() => action(po, "cancel")} disabled={busy === po.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Cancel</button>
                    </>
                  )}
                  {isAdmin && (
                    <button onClick={() => removePO(po)} disabled={busy === po.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                  )}
                </div>
              </div>
              {/* expanded line items */}
              {expanded === po.id && (
                <div className="border-t border-border px-4 py-3">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-muted">
                        <th className="pb-1">Product</th>
                        <th className="pb-1 text-right">Qty</th>
                        <th className="pb-1 text-right">Unit cost</th>
                        <th className="pb-1 text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {po.line_items.map((li, i) => (
                        <tr key={i} className="border-t border-border/50">
                          <td className="py-1">{li.description}</td>
                          <td className="py-1 text-right">{li.quantity}</td>
                          <td className="py-1 text-right">{fmtCents(li.unit_cost_cents, po.currency)}</td>
                          <td className="py-1 text-right">{fmtCents(li.quantity * li.unit_cost_cents, po.currency)}</td>
                        </tr>
                      ))}
                      <tr className="border-t border-border font-bold">
                        <td colSpan={3} className="py-1 text-right">Total</td>
                        <td className="py-1 text-right">{fmtCents(po.total_cents, po.currency)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
          {pos.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No purchase orders yet. Create one to start procuring stock.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase Y: Quotes ---------------- */

interface QuoteLineItem {
  description: string;
  quantity: number;
  unit_price_cents: number;
}
interface QuoteDef {
  id: string;
  number: string;
  customer_name: string;
  title: string;
  notes: string;
  currency: string;
  status: string;
  valid_until: string;
  line_items: QuoteLineItem[];
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  invoice_record_id: string | null;
  created_at: string | null;
}

const QUOTE_STATUS_STYLE: Record<string, string> = {
  draft: "bg-background text-muted",
  sent: "bg-accent/10 text-accent",
  accepted: "bg-success/10 text-success",
  declined: "bg-danger/10 text-danger",
  converted: "bg-warning/10 text-warning",
};

function fmtCents(c: number, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(c / 100);
}

function QuotesView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [quotes, setQuotes] = useState<QuoteDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fCustomer, setFCustomer] = useState("");
  const [fTitle, setFTitle] = useState("");
  const [fValidUntil, setFValidUntil] = useState("");
  const [fItems, setFItems] = useState<QuoteLineItem[]>([{ description: "", quantity: 1, unit_price_cents: 0 }]);

  const load = useCallback(async () => {
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const res = await api<{ items: QuoteDef[]; total: number }>(`/api/quotes${qs}`);
      setQuotes(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function updateItem(idx: number, patch: Partial<QuoteLineItem>) {
    setFItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  async function createQuote() {
    if (!fCustomer.trim()) {
      toast("Enter a customer name", "error");
      return;
    }
    const items = fItems.filter((i) => i.description.trim());
    if (items.length === 0) {
      toast("Add at least one line item", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/quotes", {
        method: "POST",
        body: { customer_name: fCustomer.trim(), title: fTitle, valid_until: fValidUntil, line_items: items },
      });
      toast("Quote created", "success");
      setShowForm(false);
      setFCustomer(""); setFTitle(""); setFValidUntil("");
      setFItems([{ description: "", quantity: 1, unit_price_cents: 0 }]);
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(q: QuoteDef, act: "send" | "accept" | "decline" | "convert") {
    setBusy(q.id);
    try {
      await api(`/api/quotes/${q.id}/${act}`, { method: "POST", body: {} });
      toast(`Quote ${act === "convert" ? "converted to invoice" : act + "ed"}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeQuote(q: QuoteDef) {
    setBusy(q.id);
    try {
      await api(`/api/quotes/${q.id}`, { method: "DELETE" });
      toast(`Deleted ${q.number}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  const formTotal = fItems.reduce((a, i) => a + i.quantity * i.unit_price_cents, 0);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Quotes</h1>
          <p className="mt-0.5 text-xs text-muted">Sales quotes &amp; proposals — send, accept, and convert to invoices.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New quote"}
          </button>
        )}
      </div>

      {/* status filter */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        {["", "draft", "sent", "accepted", "declined", "converted"].map((st) => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${statusFilter === st ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
            {st || "All"}
          </button>
        ))}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New quote</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted">
              Customer
              <input value={fCustomer} onChange={(e) => setFCustomer(e.target.value)} placeholder="Acme Corp"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Title
              <input value={fTitle} onChange={(e) => setFTitle(e.target.value)} placeholder="Website redesign"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Valid until
              <input type="date" value={fValidUntil} onChange={(e) => setFValidUntil(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          {/* line items */}
          <div className="mt-4 space-y-2">
            <div className="text-xs font-semibold text-muted">Line items</div>
            {fItems.map((item, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <input value={item.description} onChange={(e) => updateItem(idx, { description: e.target.value })} placeholder="Description"
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                <input type="number" min={1} value={item.quantity} onChange={(e) => updateItem(idx, { quantity: Math.max(1, parseInt(e.target.value) || 1) })}
                  className="w-16 rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                <input type="number" min={0} step={100} value={item.unit_price_cents} onChange={(e) => updateItem(idx, { unit_price_cents: Math.max(0, parseInt(e.target.value) || 0) })}
                  placeholder="¢" className="w-24 rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                <span className="w-20 text-right text-xs text-muted">{fmtCents(item.quantity * item.unit_price_cents)}</span>
                {fItems.length > 1 && (
                  <button onClick={() => setFItems((p) => p.filter((_, i) => i !== idx))} className="text-muted hover:text-danger"><Trash2 size={13} /></button>
                )}
              </div>
            ))}
            <button onClick={() => setFItems((p) => [...p, { description: "", quantity: 1, unit_price_cents: 0 }])}
              className="text-xs text-accent hover:underline">+ Add line</button>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-sm font-semibold">Total: {fmtCents(formTotal)}</span>
            <div className="flex items-center gap-2">
              <button onClick={createQuote} disabled={busy === "create" || !fCustomer.trim()}
                className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                {busy === "create" ? "Creating…" : "Create quote"}
              </button>
              <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* quote list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {quotes.map((q) => (
            <div key={q.id} className="rounded-xl border border-border bg-card">
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <button onClick={() => setExpanded(expanded === q.id ? null : q.id)} className="flex min-w-0 items-center gap-3 text-left">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{q.number}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${QUOTE_STATUS_STYLE[q.status] ?? "bg-background text-muted"}`}>{q.status}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {q.customer_name || "—"}{q.title && <span> · {q.title}</span>}
                      {q.valid_until && <span> · valid until {q.valid_until}</span>}
                    </div>
                  </div>
                </button>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="text-sm font-bold">{fmtCents(q.total_cents, q.currency)}</span>
                  {canEdit && q.status === "draft" && (
                    <button onClick={() => action(q, "send")} disabled={busy === q.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent disabled:opacity-50">Send</button>
                  )}
                  {canEdit && q.status === "sent" && (
                    <>
                      <button onClick={() => action(q, "accept")} disabled={busy === q.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">Accept</button>
                      <button onClick={() => action(q, "decline")} disabled={busy === q.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">Decline</button>
                    </>
                  )}
                  {canEdit && q.status === "accepted" && (
                    <button onClick={() => action(q, "convert")} disabled={busy === q.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-warning disabled:opacity-50">→ Invoice</button>
                  )}
                  {isAdmin && (
                    <button onClick={() => removeQuote(q)} disabled={busy === q.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"><Trash2 size={12} /></button>
                  )}
                </div>
              </div>
              {/* expanded line items */}
              {expanded === q.id && (
                <div className="border-t border-border px-4 py-3">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-muted">
                        <th className="pb-1">Description</th>
                        <th className="pb-1 text-right">Qty</th>
                        <th className="pb-1 text-right">Unit</th>
                        <th className="pb-1 text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {q.line_items.map((li, i) => (
                        <tr key={i} className="border-t border-border/50">
                          <td className="py-1">{li.description}</td>
                          <td className="py-1 text-right">{li.quantity}</td>
                          <td className="py-1 text-right">{fmtCents(li.unit_price_cents, q.currency)}</td>
                          <td className="py-1 text-right">{fmtCents(li.quantity * li.unit_price_cents, q.currency)}</td>
                        </tr>
                      ))}
                      <tr className="border-t border-border font-semibold">
                        <td colSpan={3} className="py-1 text-right">Subtotal</td>
                        <td className="py-1 text-right">{fmtCents(q.subtotal_cents, q.currency)}</td>
                      </tr>
                      {q.tax_cents > 0 && (
                        <tr><td colSpan={3} className="py-0.5 text-right text-muted">Tax</td><td className="py-0.5 text-right">{fmtCents(q.tax_cents, q.currency)}</td></tr>
                      )}
                      <tr className="font-bold">
                        <td colSpan={3} className="py-1 text-right">Total</td>
                        <td className="py-1 text-right">{fmtCents(q.total_cents, q.currency)}</td>
                      </tr>
                    </tbody>
                  </table>
                  {q.invoice_record_id && (
                    <p className="mt-2 text-[11px] text-muted">Converted to invoice record {q.invoice_record_id.slice(0, 8)}…</p>
                  )}
                </div>
              )}
            </div>
          ))}
          {quotes.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No quotes yet. Create your first quote to get started.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase X: Approvals Center ---------------- */

interface ApprovalItem {
  kind: "expense" | "leave" | "agent_task";
  id: string;
  title: string;
  detail: string;
  created_at: string | null;
  agent_id?: string;
}

const APPROVAL_KIND_META: Record<string, { label: string; icon: React.ReactNode; view: View }> = {
  expense: { label: "Expense", icon: <Receipt size={13} />, view: { kind: "expenses" } },
  leave: { label: "Leave", icon: <Users size={13} />, view: { kind: "hr" } },
  agent_task: { label: "AI task", icon: <Bot size={13} />, view: { kind: "agents" } },
};

function ApprovalsView({ isAdmin, setView }: { isAdmin: boolean; setView: (v: View) => void }) {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [byKind, setByKind] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<{ items: ApprovalItem[]; total: number; by_kind: Record<string, number> }>("/api/approvals");
      setItems(res.items);
      setByKind(res.by_kind);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(item: ApprovalItem, action: "approve" | "reject") {
    setBusy(item.id);
    try {
      let path = "";
      if (item.kind === "expense") path = `/api/expenses/${item.id}/${action}`;
      else if (item.kind === "leave") path = `/api/hr/leave/${item.id}/${action}`;
      else if (item.kind === "agent_task") path = `/api/agents/${item.agent_id}/tasks/${item.id}/${action}`;
      await api(path, { method: "POST", body: {} });
      toast(`${APPROVAL_KIND_META[item.kind].label} ${action}d`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Action failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">Approvals</h1>
        <p className="mt-0.5 text-xs text-muted">
          Everything waiting on a decision — expenses, leave, and AI tasks in one inbox.
        </p>
      </div>

      {/* summary chips */}
      <div className="flex flex-wrap items-center gap-2">
        {(["expense", "leave", "agent_task"] as const).map((k) => (
          <button key={k} onClick={() => setView(APPROVAL_KIND_META[k].view)}
            className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted transition hover:text-foreground">
            {APPROVAL_KIND_META[k].icon}
            {APPROVAL_KIND_META[k].label}
            <span className="font-semibold text-foreground">{byKind[k] ?? 0}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-12 text-center">
          <CheckCircle2 size={28} className="mx-auto text-success" />
          <p className="mt-2 text-sm font-semibold">All caught up</p>
          <p className="mt-1 text-xs text-muted">Nothing is waiting for your approval.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const meta = APPROVAL_KIND_META[item.kind];
            return (
              <div key={`${item.kind}-${item.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
                    {meta.icon}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">{item.title}</span>
                      <span className="rounded-full bg-background px-2 py-0.5 text-[10px] text-muted">{meta.label}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {item.detail}
                      {item.created_at && <span> · {new Date(item.created_at).toLocaleString()}</span>}
                    </div>
                  </div>
                </div>
                {isAdmin && (
                  <div className="flex shrink-0 items-center gap-2">
                    <button onClick={() => act(item, "approve")} disabled={busy === item.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">
                      Approve
                    </button>
                    <button onClick={() => act(item, "reject")} disabled={busy === item.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                      Reject
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase V: HR / People ---------------- */

interface EmployeeDef {
  id: string;
  name: string;
  email: string;
  title: string;
  department: string;
  hire_date: string;
  status: string;
  notes: string;
  created_at: string;
}
interface LeaveDef {
  id: string;
  employee_id: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: string;
  review_note: string;
  created_at: string;
}

const EMPLOYEE_STATUS_STYLE: Record<string, string> = {
  active: "bg-success/10 text-success",
  on_leave: "bg-warning/10 text-warning",
  terminated: "bg-danger/10 text-danger",
};
const LEAVE_STATUS_STYLE: Record<string, string> = {
  pending: "bg-warning/10 text-warning",
  approved: "bg-success/10 text-success",
  rejected: "bg-danger/10 text-danger",
};

function HRView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [tab, setTab] = useState<"employees" | "leave">("employees");
  const [employees, setEmployees] = useState<EmployeeDef[]>([]);
  const [leaves, setLeaves] = useState<LeaveDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // employee form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fEmail, setFEmail] = useState("");
  const [fTitle, setFTitle] = useState("");
  const [fDept, setFDept] = useState("General");
  const [fHire, setFHire] = useState("");

  // leave form
  const [showLeaveForm, setShowLeaveForm] = useState(false);
  const [lEmployee, setLEmployee] = useState("");
  const [lType, setLType] = useState("vacation");
  const [lStart, setLStart] = useState("");
  const [lEnd, setLEnd] = useState("");
  const [lReason, setLReason] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("q", search.trim());
      const qs = params.toString();
      const [emps, lvs] = await Promise.all([
        api<{ items: EmployeeDef[] }>(`/api/hr/employees${qs ? `?${qs}` : ""}`),
        api<{ items: LeaveDef[] }>("/api/hr/leave"),
      ]);
      setEmployees(emps.items);
      setLeaves(lvs.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    load();
  }, [load]);

  const empName = (id: string) => employees.find((e) => e.id === id)?.name ?? "Unknown";

  async function createEmployee() {
    if (!fName.trim() || !fEmail.trim()) {
      toast("Enter a name and email", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/hr/employees", {
        method: "POST",
        body: { name: fName.trim(), email: fEmail.trim(), title: fTitle, department: fDept, hire_date: fHire },
      });
      toast(`Added ${fName.trim()}`, "success");
      setShowForm(false);
      setFName(""); setFEmail(""); setFTitle(""); setFDept("General"); setFHire("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function removeEmployee(e: EmployeeDef) {
    setBusy(e.id);
    try {
      await api(`/api/hr/employees/${e.id}`, { method: "DELETE" });
      toast(`Removed ${e.name}`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function createLeave() {
    if (!lEmployee || !lStart || !lEnd) {
      toast("Pick an employee and both dates", "error");
      return;
    }
    setBusy("leave");
    try {
      await api("/api/hr/leave", {
        method: "POST",
        body: { employee_id: lEmployee, leave_type: lType, start_date: lStart, end_date: lEnd, reason: lReason },
      });
      toast("Leave request submitted", "success");
      setShowLeaveForm(false);
      setLEmployee(""); setLStart(""); setLEnd(""); setLReason("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Submit failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function reviewLeave(l: LeaveDef, action: "approve" | "reject") {
    setBusy(l.id);
    try {
      await api(`/api/hr/leave/${l.id}/${action}`, { method: "POST", body: {} });
      toast(`Leave ${action}d`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Review failed", "error");
    } finally {
      setBusy(null);
    }
  }

  const pendingLeaves = leaves.filter((l) => l.status === "pending").length;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">People</h1>
          <p className="mt-0.5 text-xs text-muted">Employee directory and leave requests.</p>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && tab === "employees" && (
            <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
              {showForm ? "Close" : "+ Add employee"}
            </button>
          )}
          {canEdit && tab === "leave" && (
            <button onClick={() => setShowLeaveForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
              {showLeaveForm ? "Close" : "+ Request leave"}
            </button>
          )}
        </div>
      </div>

      {/* tabs */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 w-fit">
        <button onClick={() => setTab("employees")}
          className={`rounded-md px-4 py-1.5 text-sm transition ${tab === "employees" ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
          Employees ({employees.length})
        </button>
        <button onClick={() => setTab("leave")}
          className={`rounded-md px-4 py-1.5 text-sm transition ${tab === "leave" ? "bg-accent text-on-accent font-semibold" : "text-muted hover:text-foreground"}`}>
          Leave{pendingLeaves > 0 ? ` (${pendingLeaves} pending)` : ""}
        </button>
      </div>

      {tab === "employees" && (
        <>
          {/* employee form */}
          {showForm && isAdmin && (
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="text-sm font-semibold">Add employee</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <label className="text-xs text-muted">
                  Name
                  <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Alice Chen"
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="text-xs text-muted">
                  Email
                  <input value={fEmail} onChange={(e) => setFEmail(e.target.value)} placeholder="alice@company.com"
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="text-xs text-muted">
                  Title
                  <input value={fTitle} onChange={(e) => setFTitle(e.target.value)} placeholder="Engineer"
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="text-xs text-muted">
                  Department
                  <input value={fDept} onChange={(e) => setFDept(e.target.value)} placeholder="Engineering"
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="text-xs text-muted">
                  Hire date
                  <input type="date" value={fHire} onChange={(e) => setFHire(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button onClick={createEmployee} disabled={busy === "create" || !fName.trim() || !fEmail.trim()}
                  className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                  {busy === "create" ? "Adding…" : "Add employee"}
                </button>
                <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* search */}
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, email, or title…"
            className="w-64 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />

          {/* employee list */}
          {loading ? (
            <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
          ) : (
            <div className="space-y-2">
              {employees.map((e) => (
                <div key={e.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent text-sm font-bold">
                      {e.name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-semibold">{e.name}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${EMPLOYEE_STATUS_STYLE[e.status] ?? "bg-background text-muted"}`}>
                          {e.status.replace("_", " ")}
                        </span>
                      </div>
                      <div className="mt-0.5 text-xs text-muted">
                        {e.title || "—"} · {e.department}{e.hire_date && <span> · hired {e.hire_date}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-muted">{e.email}</span>
                    {isAdmin && (
                      <button onClick={() => removeEmployee(e)} disabled={busy === e.id}
                        className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {employees.length === 0 && (
                <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
                  No employees yet. Add your first team member.
                </div>
              )}
            </div>
          )}
        </>
      )}

      {tab === "leave" && (
        <>
          {/* leave form */}
          {showLeaveForm && canEdit && (
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="text-sm font-semibold">Request leave</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <label className="text-xs text-muted">
                  Employee
                  <select value={lEmployee} onChange={(e) => setLEmployee(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                    <option value="">Select…</option>
                    {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                </label>
                <label className="text-xs text-muted">
                  Type
                  <select value={lType} onChange={(e) => setLType(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                    <option value="vacation">Vacation</option>
                    <option value="sick">Sick</option>
                    <option value="personal">Personal</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <label className="text-xs text-muted">
                  Reason
                  <input value={lReason} onChange={(e) => setLReason(e.target.value)} placeholder="Optional"
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="text-xs text-muted">
                  Start date
                  <input type="date" value={lStart} onChange={(e) => setLStart(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="text-xs text-muted">
                  End date
                  <input type="date" value={lEnd} onChange={(e) => setLEnd(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                </label>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button onClick={createLeave} disabled={busy === "leave" || !lEmployee || !lStart || !lEnd}
                  className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                  {busy === "leave" ? "Submitting…" : "Submit request"}
                </button>
                <button onClick={() => setShowLeaveForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* leave list */}
          {loading ? (
            <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
          ) : (
            <div className="space-y-2">
              {leaves.map((l) => (
                <div key={l.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">{empName(l.employee_id)}</span>
                      <span className="rounded-full bg-background px-2 py-0.5 text-[10px] capitalize text-muted">{l.leave_type}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${LEAVE_STATUS_STYLE[l.status] ?? "bg-background text-muted"}`}>
                        {l.status}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {l.start_date} → {l.end_date}{l.reason && <span> · {l.reason}</span>}
                      {l.review_note && <span> · note: {l.review_note}</span>}
                    </div>
                  </div>
                  {isAdmin && l.status === "pending" && (
                    <div className="flex shrink-0 items-center gap-2">
                      <button onClick={() => reviewLeave(l, "approve")} disabled={busy === l.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">
                        Approve
                      </button>
                      <button onClick={() => reviewLeave(l, "reject")} disabled={busy === l.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {leaves.length === 0 && (
                <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
                  No leave requests yet.
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ---------------- Phase U: Inventory ---------------- */

interface ProductDef {
  id: string;
  name: string;
  sku: string;
  description: string;
  category: string;
  price_cents: number;
  currency: string;
  quantity: number;
  reorder_point: number;
  low_stock: boolean;
  active: boolean;
  created_at: string;
}

function InventoryView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [products, setProducts] = useState<ProductDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [lowOnly, setLowOnly] = useState(false);
  const [search, setSearch] = useState("");

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fSku, setFSku] = useState("");
  const [fCategory, setFCategory] = useState("General");
  const [fPrice, setFPrice] = useState("");
  const [fQty, setFQty] = useState("");
  const [fReorder, setFReorder] = useState("");

  // adjust form
  const [adjusting, setAdjusting] = useState<ProductDef | null>(null);
  const [adjKind, setAdjKind] = useState<"in" | "out" | "set">("in");
  const [adjDelta, setAdjDelta] = useState("");
  const [adjReason, setAdjReason] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (lowOnly) params.set("low_stock", "true");
      if (search.trim()) params.set("q", search.trim());
      const qs = params.toString();
      const res = await api<{ items: ProductDef[] }>(`/api/inventory/products${qs ? `?${qs}` : ""}`);
      setProducts(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [lowOnly, search]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    const price = Math.round(parseFloat(fPrice || "0") * 100);
    const qty = parseInt(fQty || "0", 10);
    const reorder = parseInt(fReorder || "0", 10);
    if (!fName.trim() || !fSku.trim() || !Number.isFinite(price) || price < 0 || !Number.isFinite(qty) || qty < 0) {
      toast("Enter a name, SKU, and valid price/quantity", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/inventory/products", {
        method: "POST",
        body: { name: fName.trim(), sku: fSku.trim(), category: fCategory, price_cents: price, quantity: qty, reorder_point: reorder },
      });
      toast(`Product "${fName.trim()}" created`, "success");
      setShowForm(false);
      setFName(""); setFSku(""); setFPrice(""); setFQty(""); setFReorder("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function adjust() {
    if (!adjusting) return;
    const delta = parseInt(adjDelta || "0", 10);
    if (!Number.isFinite(delta)) {
      toast("Enter a valid quantity", "error");
      return;
    }
    setBusy("adjust");
    try {
      await api(`/api/inventory/products/${adjusting.id}/adjust`, {
        method: "POST",
        body: { kind: adjKind, delta, reason: adjReason },
      });
      toast(`Stock ${adjKind === "in" ? "received" : adjKind === "out" ? "removed" : "set"}`, "success");
      setAdjusting(null);
      setAdjDelta(""); setAdjReason("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Adjust failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function remove(p: ProductDef) {
    setBusy(p.id);
    try {
      await api(`/api/inventory/products/${p.id}`, { method: "DELETE" });
      toast(`Deleted "${p.name}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  const lowCount = products.filter((p) => p.low_stock).length;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Inventory</h1>
          <p className="mt-0.5 text-xs text-muted">Track products, stock levels, and adjustments.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New product"}
          </button>
        )}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New product</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Wireless Mouse"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              SKU
              <input value={fSku} onChange={(e) => setFSku(e.target.value)} placeholder="WM-001"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Category
              <input value={fCategory} onChange={(e) => setFCategory(e.target.value)} placeholder="Electronics"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Price (USD)
              <input value={fPrice} onChange={(e) => setFPrice(e.target.value)} placeholder="25.00" inputMode="decimal"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Initial quantity
              <input value={fQty} onChange={(e) => setFQty(e.target.value)} placeholder="50" inputMode="numeric"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Reorder point
              <input value={fReorder} onChange={(e) => setFReorder(e.target.value)} placeholder="10" inputMode="numeric"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={create} disabled={busy === "create" || !fName.trim() || !fSku.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create product"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* adjust panel */}
      {adjusting && canEdit && (
        <div className="rounded-xl border border-accent/40 bg-card p-4">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-sm font-semibold">Adjust stock: {adjusting.name} <span className="font-mono text-xs text-muted">({adjusting.sku})</span></h2>
            <button onClick={() => setAdjusting(null)} className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground">
              Close
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted">
              Type
              <select value={adjKind} onChange={(e) => setAdjKind(e.target.value as "in" | "out" | "set")}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                <option value="in">Receive (in)</option>
                <option value="out">Ship / consume (out)</option>
                <option value="set">Set absolute</option>
              </select>
            </label>
            <label className="text-xs text-muted">
              Quantity
              <input value={adjDelta} onChange={(e) => setAdjDelta(e.target.value)} placeholder="10" inputMode="numeric"
                className="mt-1 w-28 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="min-w-0 flex-1 text-xs text-muted">
              Reason
              <input value={adjReason} onChange={(e) => setAdjReason(e.target.value)} placeholder="restock, order #123…"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <button onClick={adjust} disabled={busy === "adjust" || !adjDelta.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "adjust" ? "Applying…" : "Apply"}
            </button>
          </div>
          <div className="mt-2 text-xs text-muted">Current stock: <span className="font-mono font-semibold text-foreground">{adjusting.quantity}</span></div>
        </div>
      )}

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name or SKU…"
          className="w-56 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
        <button onClick={() => setLowOnly((v) => !v)}
          className={`rounded-lg border px-3 py-1.5 text-sm transition ${lowOnly ? "border-warning bg-warning/10 text-warning" : "border-border text-muted hover:text-foreground"}`}>
          Low stock{lowCount > 0 ? ` (${lowCount})` : ""}
        </button>
      </div>

      {/* list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {products.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${p.low_stock ? "bg-warning/10 text-warning" : "bg-background text-muted"}`}>
                  <Package size={16} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{p.name}</span>
                    <span className="font-mono text-xs text-muted">{p.sku}</span>
                    {p.low_stock && (
                      <span className="rounded-full bg-warning/10 px-2 py-0.5 text-[10px] text-warning">low stock</span>
                    )}
                    {!p.active && (
                      <span className="rounded-full bg-background px-2 py-0.5 text-[10px] text-muted">inactive</span>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {p.category} · {fmtMoney(p.price_cents, p.currency)} · reorder at {p.reorder_point}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`font-mono text-sm font-semibold ${p.low_stock ? "text-warning" : "text-foreground"}`}>
                  {p.quantity} in stock
                </span>
                {canEdit && (
                  <button onClick={() => { setAdjusting(p); setAdjKind("in"); setAdjDelta(""); setAdjReason(""); }} disabled={busy === p.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50">
                    Adjust
                  </button>
                )}
                {isAdmin && (
                  <button onClick={() => remove(p)} disabled={busy === p.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {products.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No products yet. Add one to start tracking inventory.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase T: Projects ---------------- */

interface ProjectDef {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: string;
  budget_cents: number;
  currency: string;
  start_date: string;
  end_date: string;
  owner_id: string | null;
  created_at: string;
}
interface ProjectSummary {
  project_id: string;
  status: string;
  budget_cents: number;
  spent_cents: number;
  remaining_cents: number;
  budget_used_pct: number | null;
  time_minutes: number;
  time_entries: number;
  expenses: number;
  milestones_total: number;
  milestones_done: number;
  milestones: { id: string; title: string; due_date: string; status: string; notes: string }[];
}

const PROJECT_STATUSES = ["planning", "active", "on_hold", "completed", "cancelled"];
const PROJECT_STATUS_STYLE: Record<string, string> = {
  planning: "bg-background text-muted",
  active: "bg-success/10 text-success",
  on_hold: "bg-warning/10 text-warning",
  completed: "bg-accent/10 text-accent",
  cancelled: "bg-danger/10 text-danger",
};

function ProjectsView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [projects, setProjects] = useState<ProjectDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  // detail
  const [selected, setSelected] = useState<ProjectDef | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fDesc, setFDesc] = useState("");
  const [fBudget, setFBudget] = useState("");
  const [fStart, setFStart] = useState("");
  const [fEnd, setFEnd] = useState("");
  const [fMilestone, setFMilestone] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString();
      const res = await api<{ items: ProjectDef[] }>(`/api/projects${qs ? `?${qs}` : ""}`);
      setProjects(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const loadSummary = useCallback(async (id: string) => {
    try {
      const s = await api<ProjectSummary>(`/api/projects/${id}/summary`);
      setSummary(s);
    } catch {
      setSummary(null);
    }
  }, []);

  useEffect(() => {
    if (selected) loadSummary(selected.id);
    else setSummary(null);
  }, [selected, loadSummary]);

  async function create() {
    const cents = Math.round(parseFloat(fBudget || "0") * 100);
    if (!fName.trim() || !Number.isFinite(cents) || cents < 0) {
      toast("Enter a name and a valid budget", "error");
      return;
    }
    setBusy("create");
    try {
      const p = await api<ProjectDef>("/api/projects", {
        method: "POST",
        body: { name: fName.trim(), description: fDesc, budget_cents: cents, start_date: fStart, end_date: fEnd, status: "active" },
      });
      toast(`Project "${p.name}" created`, "success");
      if (fMilestone.trim()) {
        await api(`/api/projects/${p.id}/milestones`, { method: "POST", body: { title: fMilestone.trim() } });
      }
      setShowForm(false);
      setFName(""); setFDesc(""); setFBudget(""); setFStart(""); setFEnd(""); setFMilestone("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function setStatus(p: ProjectDef, status: string) {
    setBusy(p.id);
    try {
      await api(`/api/projects/${p.id}`, { method: "PATCH", body: { status } });
      toast(`"${p.name}" → ${status.replace("_", " ")}`, "success");
      await load();
      if (selected?.id === p.id) setSelected({ ...p, status });
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Update failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function remove(p: ProjectDef) {
    setBusy(p.id);
    try {
      await api(`/api/projects/${p.id}`, { method: "DELETE" });
      toast(`Deleted "${p.name}"`, "info");
      if (selected?.id === p.id) setSelected(null);
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function addMilestone() {
    if (!selected || !fMilestone.trim()) return;
    setBusy("milestone");
    try {
      await api(`/api/projects/${selected.id}/milestones`, { method: "POST", body: { title: fMilestone.trim() } });
      toast("Milestone added", "success");
      setFMilestone("");
      await loadSummary(selected.id);
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Add failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function toggleMilestone(m: { id: string; status: string }) {
    if (!selected) return;
    setBusy(m.id);
    try {
      await api(`/api/projects/${selected.id}/milestones/${m.id}`, {
        method: "PATCH",
        body: { status: m.status === "done" ? "pending" : "done" },
      });
      await loadSummary(selected.id);
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Update failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Projects</h1>
          <p className="mt-0.5 text-xs text-muted">Budgeted work with milestones. Link time and expenses to track actuals.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New project"}
          </button>
        )}
      </div>

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New project</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted md:col-span-2">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Website Redesign"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Description
              <input value={fDesc} onChange={(e) => setFDesc(e.target.value)} placeholder="Optional"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Budget (USD)
              <input value={fBudget} onChange={(e) => setFBudget(e.target.value)} placeholder="5000" inputMode="decimal"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              First milestone
              <input value={fMilestone} onChange={(e) => setFMilestone(e.target.value)} placeholder="Kickoff (optional)"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Start date
              <input type="date" value={fStart} onChange={(e) => setFStart(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              End date
              <input type="date" value={fEnd} onChange={(e) => setFEnd(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={create} disabled={busy === "create" || !fName.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create project"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* filter */}
      <div className="flex items-center gap-2">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
          <option value="">All statuses</option>
          {PROJECT_STATUSES.map((st) => <option key={st} value={st}>{st.replace("_", " ")}</option>)}
        </select>
      </div>

      {/* detail panel */}
      {selected && (
        <div className="rounded-xl border border-accent/40 bg-card p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">{selected.name}</h2>
              <p className="mt-0.5 text-xs text-muted">{selected.description || "No description"}</p>
            </div>
            <button onClick={() => setSelected(null)} className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground">
              Close
            </button>
          </div>
          {summary ? (
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div>
                <div className="text-xs text-muted">Budget</div>
                <div className="mt-1 text-lg font-bold">{fmtMoney(summary.budget_cents)}</div>
                <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-background">
                  <div
                    className={`h-full rounded-full ${summary.budget_used_pct != null && summary.budget_used_pct > 90 ? "bg-danger" : "bg-accent"}`}
                    style={{ width: `${Math.min(100, summary.budget_used_pct ?? 0)}%` }}
                  />
                </div>
                <div className="mt-1 text-xs text-muted">
                  {fmtMoney(summary.spent_cents)} spent · {fmtMoney(summary.remaining_cents)} left
                  {summary.budget_used_pct != null && <span> · {summary.budget_used_pct}%</span>}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted">Time logged</div>
                <div className="mt-1 text-lg font-bold">{fmtDuration(summary.time_minutes)}</div>
                <div className="mt-1 text-xs text-muted">{summary.time_entries} entr{summary.time_entries === 1 ? "y" : "ies"} · {summary.expenses} expense{summary.expenses === 1 ? "" : "s"}</div>
              </div>
              <div>
                <div className="text-xs text-muted">Milestones</div>
                <div className="mt-1 text-lg font-bold">{summary.milestones_done}/{summary.milestones_total}</div>
                <div className="mt-1 text-xs text-muted">completed</div>
              </div>
            </div>
          ) : (
            <div className="skeleton mt-4 h-20 w-full rounded-lg" />
          )}

          {/* milestones */}
          <div className="mt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Milestones</h3>
            <div className="mt-2 space-y-1.5">
              {summary?.milestones.map((m) => (
                <div key={m.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
                  <button onClick={() => toggleMilestone(m)} disabled={busy === m.id || !canEdit} className="flex min-w-0 items-center gap-2 text-left disabled:opacity-50">
                    <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${m.status === "done" ? "border-success bg-success text-white" : "border-border"}`}>
                      {m.status === "done" && <Check size={10} />}
                    </span>
                    <span className={`truncate text-sm ${m.status === "done" ? "text-muted line-through" : "text-foreground"}`}>{m.title}</span>
                  </button>
                  {m.due_date && <span className="shrink-0 text-xs text-muted">{m.due_date}</span>}
                </div>
              ))}
              {summary && summary.milestones.length === 0 && (
                <div className="text-xs text-faint">No milestones yet.</div>
              )}
            </div>
            {canEdit && (
              <div className="mt-2 flex items-center gap-2">
                <input value={fMilestone} onChange={(e) => setFMilestone(e.target.value)} placeholder="Add a milestone…"
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
                <button onClick={addMilestone} disabled={busy === "milestone" || !fMilestone.trim()}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
                  Add
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {projects.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <button onClick={() => setSelected(p)} className="flex min-w-0 items-center gap-3 text-left">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background text-muted">
                  <FolderKanban size={16} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{p.name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${PROJECT_STATUS_STYLE[p.status] ?? "bg-background text-muted"}`}>
                      {p.status.replace("_", " ")}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    <span className="font-mono">/{p.slug}</span>
                    {p.budget_cents > 0 && <span> · budget {fmtMoney(p.budget_cents, p.currency)}</span>}
                    {p.start_date && <span> · {p.start_date} → {p.end_date || "…"}</span>}
                  </div>
                </div>
              </button>
              <div className="flex shrink-0 items-center gap-2">
                {canEdit && p.status !== "completed" && p.status !== "cancelled" && (
                  <button onClick={() => setStatus(p, "completed")} disabled={busy === p.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">
                    Complete
                  </button>
                )}
                {isAdmin && (
                  <button onClick={() => remove(p)} disabled={busy === p.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {projects.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No projects yet. Create one to organize budgeted work.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase S: Expenses ---------------- */

interface ExpenseDef {
  id: string;
  title: string;
  category: string;
  amount_cents: number;
  currency: string;
  occurred_on: string;
  notes: string;
  status: string;
  submitted_by: string | null;
  receipt_file_id: string | null;
  reviewed_by: string | null;
  review_note: string;
  reviewed_at: string | null;
  created_at: string;
}
interface ExpenseSummary {
  total_cents: number;
  count: number;
  by_status: { label: string; cents: number }[];
  by_category: { label: string; cents: number }[];
}

const EXPENSE_CATEGORIES = ["General", "Travel", "Meals", "Software", "Equipment", "Office", "Marketing", "Other"];

function fmtMoney(cents: number, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);
}

const EXPENSE_STATUS_STYLE: Record<string, string> = {
  draft: "bg-background text-muted",
  submitted: "bg-warning/10 text-warning",
  approved: "bg-success/10 text-success",
  rejected: "bg-danger/10 text-danger",
  reimbursed: "bg-accent/10 text-accent",
};

function ExpensesView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [expenses, setExpenses] = useState<ExpenseDef[]>([]);
  const [summary, setSummary] = useState<ExpenseSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fTitle, setFTitle] = useState("");
  const [fCategory, setFCategory] = useState("General");
  const [fAmount, setFAmount] = useState("");
  const [fCurrency, setFCurrency] = useState("USD");
  const [fDate, setFDate] = useState("");
  const [fNotes, setFNotes] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      const qs = params.toString();
      const [e, s] = await Promise.all([
        api<{ items: ExpenseDef[] }>(`/api/expenses${qs ? `?${qs}` : ""}`),
        api<ExpenseSummary>("/api/expenses/summary"),
      ]);
      setExpenses(e.items);
      setSummary(s);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [statusFilter, categoryFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    const cents = Math.round(parseFloat(fAmount || "0") * 100);
    if (!fTitle.trim() || !Number.isFinite(cents) || cents < 0) {
      toast("Enter a title and a valid amount", "error");
      return;
    }
    setBusy("create");
    try {
      await api("/api/expenses", {
        method: "POST",
        body: {
          title: fTitle.trim(),
          category: fCategory,
          amount_cents: cents,
          currency: fCurrency,
          occurred_on: fDate,
          notes: fNotes,
        },
      });
      toast(`Expense "${fTitle.trim()}" created`, "success");
      setShowForm(false);
      setFTitle(""); setFAmount(""); setFDate(""); setFNotes("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function action(id: string, verb: "submit" | "approve" | "reject" | "reimburse") {
    setBusy(id);
    try {
      const body = verb === "approve" || verb === "reject" ? { note: "" } : undefined;
      await api(`/api/expenses/${id}/${verb}`, { method: "POST", body });
      toast(`Expense ${verb === "approve" ? "approved" : verb === "reject" ? "rejected" : verb === "reimburse" ? "reimbursed" : "submitted"}`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : `${verb} failed`, "error");
    } finally {
      setBusy(null);
    }
  }

  async function remove(e: ExpenseDef) {
    setBusy(e.id);
    try {
      await api(`/api/expenses/${e.id}`, { method: "DELETE" });
      toast(`Deleted "${e.title}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Expenses</h1>
          <p className="mt-0.5 text-xs text-muted">Track spend, submit for approval, and reimburse.</p>
        </div>
        {canEdit && (
          <button onClick={() => setShowForm((v) => !v)} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            {showForm ? "Close" : "+ New expense"}
          </button>
        )}
      </div>

      {/* summary */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="text-xs text-muted">Total</div>
            <div className="mt-1 text-2xl font-bold">{fmtMoney(summary.total_cents)}</div>
            <div className="mt-0.5 text-xs text-muted">{summary.count} expense{summary.count === 1 ? "" : "s"}</div>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="text-xs text-muted">By status</div>
            <div className="mt-2 space-y-1">
              {summary.by_status.slice(0, 4).map((r) => (
                <div key={r.label} className="flex items-center justify-between text-xs">
                  <span className="capitalize text-muted">{r.label}</span>
                  <span className="font-mono">{fmtMoney(r.cents)}</span>
                </div>
              ))}
              {summary.by_status.length === 0 && <div className="text-xs text-faint">No data</div>}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="text-xs text-muted">By category</div>
            <div className="mt-2 space-y-1">
              {summary.by_category.slice(0, 4).map((r) => (
                <div key={r.label} className="flex items-center justify-between text-xs">
                  <span className="text-muted">{r.label}</span>
                  <span className="font-mono">{fmtMoney(r.cents)}</span>
                </div>
              ))}
              {summary.by_category.length === 0 && <div className="text-xs text-faint">No data</div>}
            </div>
          </div>
        </div>
      )}

      {/* create form */}
      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New expense</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted md:col-span-2">
              Title
              <input value={fTitle} onChange={(e) => setFTitle(e.target.value)} placeholder="Flight to client"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Category
              <select value={fCategory} onChange={(e) => setFCategory(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="text-xs text-muted">
              Amount
              <input value={fAmount} onChange={(e) => setFAmount(e.target.value)} placeholder="450.00" inputMode="decimal"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Currency
              <select value={fCurrency} onChange={(e) => setFCurrency(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="INR">INR</option>
              </select>
            </label>
            <label className="text-xs text-muted">
              Date
              <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-3">
              Notes
              <input value={fNotes} onChange={(e) => setFNotes(e.target.value)} placeholder="Optional details"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={create} disabled={busy === "create" || !fTitle.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "create" ? "Creating…" : "Create draft"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="submitted">Submitted</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="reimbursed">Reimbursed</option>
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
          <option value="">All categories</option>
          {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {expenses.map((e) => (
            <div key={e.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background text-muted">
                  <Receipt size={16} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{e.title}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${EXPENSE_STATUS_STYLE[e.status] ?? "bg-background text-muted"}`}>
                      {e.status}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {e.category}
                    {e.occurred_on && <span> · {e.occurred_on}</span>}
                    {e.notes && <span> · {e.notes}</span>}
                    {e.review_note && <span> · review: {e.review_note}</span>}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="font-mono text-sm font-semibold">{fmtMoney(e.amount_cents, e.currency)}</span>
                {canEdit && (e.status === "draft" || e.status === "rejected") && (
                  <button onClick={() => action(e.id, "submit")} disabled={busy === e.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50">
                    Submit
                  </button>
                )}
                {isAdmin && e.status === "submitted" && (
                  <>
                    <button onClick={() => action(e.id, "approve")} disabled={busy === e.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">
                      Approve
                    </button>
                    <button onClick={() => action(e.id, "reject")} disabled={busy === e.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                      Reject
                    </button>
                  </>
                )}
                {isAdmin && e.status === "approved" && (
                  <button onClick={() => action(e.id, "reimburse")} disabled={busy === e.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent disabled:opacity-50">
                    Reimburse
                  </button>
                )}
                {canEdit && (e.status === "draft" || e.status === "rejected") && (
                  <button onClick={() => remove(e)} disabled={busy === e.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {expenses.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No expenses yet. Add one to start tracking spend.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase R: Time Tracking ---------------- */

interface TimeEntry {
  id: string;
  description: string;
  started_at: string;
  stopped_at: string | null;
  duration_minutes: number | null;
  running: boolean;
  object: string | null;
  record_id: string | null;
  user_id: string | null;
  notes: string;
  created_at: string;
}
interface TimeSummary {
  total_minutes: number;
  entries: number;
  by_object: { label: string; minutes: number }[];
  by_user: { label: string; minutes: number }[];
}

function fmtDuration(mins: number | null) {
  if (mins == null) return "—";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function TimeView({ canEdit }: { canEdit: boolean }) {
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [summary, setSummary] = useState<TimeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [timerDesc, setTimerDesc] = useState("");

  const load = useCallback(async () => {
    try {
      const [e, s] = await Promise.all([
        api<{ items: TimeEntry[] }>("/api/time"),
        api<TimeSummary>("/api/time/summary"),
      ]);
      setEntries(e.items);
      setSummary(s);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runningEntry = entries.find((e) => e.running);

  async function startTimer() {
    setBusy("timer");
    try {
      await api("/api/time/timer/start", { method: "POST", body: { description: timerDesc.trim() } });
      toast("Timer started", "success");
      setTimerDesc("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Start failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function stopTimer(id: string) {
    setBusy("timer");
    try {
      await api(`/api/time/${id}/timer/stop`, { method: "POST" });
      toast("Timer stopped", "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Stop failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function deleteEntry(e: TimeEntry) {
    setBusy(e.id);
    try {
      await api(`/api/time/${e.id}`, { method: "DELETE" });
      toast("Entry deleted", "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">Time Tracking</h1>
        <p className="mt-0.5 text-xs text-muted">Log work or run a live timer. Entries can link to any record.</p>
      </div>

      {/* timer / summary row */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">{runningEntry ? "Timer running" : "Start a timer"}</h2>
          {runningEntry ? (
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{runningEntry.description || "(no description)"}</div>
                <div className="mt-0.5 text-xs text-muted">
                  started {new Date(runningEntry.started_at).toLocaleTimeString()}
                  {runningEntry.object && <span> · {runningEntry.object}</span>}
                </div>
              </div>
              <button
                onClick={() => stopTimer(runningEntry.id)}
                disabled={busy === "timer"}
                className="shrink-0 rounded-lg bg-danger px-4 py-1.5 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-50"
              >
                {busy === "timer" ? "Stopping…" : "Stop"}
              </button>
            </div>
          ) : canEdit ? (
            <div className="mt-3 flex items-center gap-2">
              <input
                value={timerDesc}
                onChange={(e) => setTimerDesc(e.target.value)}
                placeholder="What are you working on?"
                className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent"
              />
              <button
                onClick={startTimer}
                disabled={busy === "timer"}
                className="shrink-0 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
              >
                {busy === "timer" ? "Starting…" : "Start"}
              </button>
            </div>
          ) : (
            <div className="mt-3 text-xs text-muted">You need edit access to run a timer.</div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Logged time</h2>
          {summary ? (
            <div className="mt-3">
              <div className="text-2xl font-bold">{fmtDuration(summary.total_minutes)}</div>
              <div className="mt-0.5 text-xs text-muted">{summary.entries} completed entr{summary.entries === 1 ? "y" : "ies"}</div>
              {summary.by_object.length > 0 && (
                <div className="mt-2 space-y-1">
                  {summary.by_object.slice(0, 4).map((r) => (
                    <div key={r.label} className="flex items-center justify-between text-xs">
                      <span className="text-muted">{r.label}</span>
                      <span className="font-mono">{fmtDuration(r.minutes)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="skeleton mt-3 h-16 w-full rounded-lg" />
          )}
        </div>
      </div>

      {/* entries list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-14 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {entries.map((e) => (
            <div key={e.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${e.running ? "bg-success/10 text-success" : "bg-background text-muted"}`}>
                  <Clock size={16} />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{e.description || "(no description)"}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {new Date(e.started_at).toLocaleString()}
                    {e.object && <span> · {e.object}{e.record_id ? ` #${e.record_id.slice(0, 8)}` : ""}</span>}
                    {e.notes && <span> · {e.notes}</span>}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`font-mono text-sm ${e.running ? "font-bold text-success" : "text-foreground"}`}>
                  {e.running ? "● running" : fmtDuration(e.duration_minutes)}
                </span>
                {canEdit && !e.running && (
                  <button
                    onClick={() => deleteEntry(e)}
                    disabled={busy === e.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {entries.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No time logged yet. Start a timer or log an entry.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase Q: Knowledge Base ---------------- */

interface KBArticle {
  id: string;
  title: string;
  slug: string;
  body?: string;
  category: string;
  tags: string[];
  status: string;
  object: string | null;
  record_id: string | null;
  created_at: string;
  updated_at: string;
}

function KBView({ canEdit, isAdmin }: { canEdit: boolean; isAdmin: boolean }) {
  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // editor state
  const [editing, setEditing] = useState<KBArticle | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [fTitle, setFTitle] = useState("");
  const [fSlug, setFSlug] = useState("");
  const [fBody, setFBody] = useState("");
  const [fCategory, setFCategory] = useState("");
  const [fTags, setFTags] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filter.trim()) params.set("q", filter.trim());
      if (statusFilter) params.set("status", statusFilter);
      const qs = params.toString();
      const res = await api<{ items: KBArticle[] }>(`/api/kb${qs ? `?${qs}` : ""}`);
      setArticles(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [filter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function openNew() {
    setEditing(null);
    setFTitle("");
    setFSlug("");
    setFBody("");
    setFCategory("");
    setFTags("");
    setShowEditor(true);
  }

  async function openEdit(a: KBArticle) {
    setBusy(a.id);
    try {
      const full = await api<KBArticle>(`/api/kb/${a.id}`);
      setEditing(full);
      setFTitle(full.title);
      setFSlug(full.slug);
      setFBody(full.body ?? "");
      setFCategory(full.category);
      setFTags(full.tags.join(", "));
      setShowEditor(true);
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Load failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (!fTitle.trim()) return;
    setBusy("save");
    const tags = fTags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      if (editing) {
        await api(`/api/kb/${editing.id}`, {
          method: "PATCH",
          body: { title: fTitle.trim(), body: fBody, category: fCategory.trim(), tags },
        });
        toast(`Updated "${fTitle.trim()}"`, "success");
      } else {
        if (!fSlug.trim()) {
          toast("Slug is required for a new article", "error");
          setBusy(null);
          return;
        }
        await api("/api/kb", {
          method: "POST",
          body: { title: fTitle.trim(), slug: fSlug.trim(), body: fBody, category: fCategory.trim(), tags },
        });
        toast(`Created "${fTitle.trim()}"`, "success");
      }
      setShowEditor(false);
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Save failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function publish(a: KBArticle) {
    setBusy(a.id);
    try {
      await api(`/api/kb/${a.id}/publish`, { method: "POST" });
      toast(`Published "${a.title}"`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Publish failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function unpublish(a: KBArticle) {
    setBusy(a.id);
    try {
      await api(`/api/kb/${a.id}/unpublish`, { method: "POST" });
      toast(`Unpublished "${a.title}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Unpublish failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function remove(a: KBArticle) {
    setBusy(a.id);
    try {
      await api(`/api/kb/${a.id}`, { method: "DELETE" });
      toast(`Deleted "${a.title}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Knowledge Base</h1>
          <p className="mt-0.5 text-xs text-muted">Team wiki + public help center. Publish articles to share them without login.</p>
        </div>
        {canEdit && (
          <button onClick={openNew} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110">
            + New article
          </button>
        )}
      </div>

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search articles…"
          className="w-56 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
        </select>
      </div>

      {/* editor */}
      {showEditor && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">{editing ? `Edit: ${editing.title}` : "New article"}</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Title
              <input value={fTitle} onChange={(e) => setFTitle(e.target.value)} placeholder="Getting started"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Slug {editing ? <span className="text-faint">(fixed)</span> : <span className="text-faint">(lowercase, digits, hyphens)</span>}
              <input value={fSlug} onChange={(e) => setFSlug(e.target.value.toLowerCase())} disabled={!!editing} placeholder="getting-started"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground outline-none focus:border-accent disabled:opacity-50" />
            </label>
            <label className="text-xs text-muted">
              Category
              <input value={fCategory} onChange={(e) => setFCategory(e.target.value)} placeholder="Guides"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Tags <span className="text-faint">(comma separated)</span>
              <input value={fTags} onChange={(e) => setFTags(e.target.value)} placeholder="onboarding, basics"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Body <span className="text-faint">(markdown)</span>
              <textarea value={fBody} onChange={(e) => setFBody(e.target.value)} rows={8} placeholder="# Heading&#10;Write your article…"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={save} disabled={busy === "save" || !fTitle.trim()}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50">
              {busy === "save" ? "Saving…" : editing ? "Save changes" : "Create article"}
            </button>
            <button onClick={() => setShowEditor(false)} className="rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* list */}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {articles.map((a) => (
            <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{a.title}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${a.status === "published" ? "bg-success/10 text-success" : "bg-background text-muted"}`}>
                    {a.status}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted">
                  <span className="font-mono">/{a.slug}</span>
                  {a.category && <span> · {a.category}</span>}
                  {a.tags.length > 0 && <span> · {a.tags.join(", ")}</span>}
                  {" · updated "}{new Date(a.updated_at).toLocaleString()}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {canEdit && (
                  <>
                    <button onClick={() => openEdit(a)} disabled={busy === a.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50">
                      <Pencil size={12} className="mr-1 inline" />Edit
                    </button>
                    {a.status === "draft" ? (
                      <button onClick={() => publish(a)} disabled={busy === a.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-success disabled:opacity-50">
                        Publish
                      </button>
                    ) : (
                      <button onClick={() => unpublish(a)} disabled={busy === a.id}
                        className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50">
                        Unpublish
                      </button>
                    )}
                  </>
                )}
                {isAdmin && (
                  <button onClick={() => remove(a)} disabled={busy === a.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {articles.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No articles yet. Write one to start your team wiki.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase P: Calendar ---------------- */

interface CalEvent {
  id: string;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string | null;
  all_day: boolean;
  location: string;
  attendees: string[];
  object: string | null;
  record_id: string | null;
  created_at: string;
}

function CalendarView({ canEdit }: { canEdit: boolean }) {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fTitle, setFTitle] = useState("");
  const [fDate, setFDate] = useState("");
  const [fTime, setFTime] = useState("09:00");
  const [fDuration, setFDuration] = useState("60");
  const [fLocation, setFLocation] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api<{ items: CalEvent[] }>("/api/calendar");
      setEvents(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createEvent() {
    if (!fTitle.trim() || !fDate) return;
    setBusy("create");
    try {
      const start = new Date(`${fDate}T${fTime || "09:00"}`);
      const end = new Date(start.getTime() + parseInt(fDuration || "60", 10) * 60000);
      await api("/api/calendar", {
        method: "POST",
        body: { title: fTitle.trim(), starts_at: start.toISOString(), ends_at: end.toISOString(), location: fLocation.trim() },
      });
      toast(`Scheduled "${fTitle.trim()}"`, "success");
      setShowForm(false);
      setFTitle("");
      setFDate("");
      setFLocation("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function deleteEvent(ev: CalEvent) {
    setBusy(ev.id);
    try {
      await api(`/api/calendar/${ev.id}`, { method: "DELETE" });
      toast(`Deleted "${ev.title}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  // ---- month grid ----
  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const firstDow = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array.from({ length: firstDow }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const today = new Date();
  const isToday = (day: number) =>
    day === today.getDate() && month === today.getMonth() && year === today.getFullYear();

  const eventsOn = (day: number) =>
    events.filter((e) => {
      const d = new Date(e.starts_at);
      return d.getDate() === day && d.getMonth() === month && d.getFullYear() === year;
    });

  const upcoming = events
    .filter((e) => new Date(e.starts_at) >= new Date())
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
    .slice(0, 8);

  const monthLabel = cursor.toLocaleString(undefined, { month: "long", year: "numeric" });

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Calendar</h1>
          <p className="mt-0.5 text-xs text-muted">Workspace scheduling. Events can link to any record.</p>
        </div>
        {canEdit && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            {showForm ? "Cancel" : "+ New event"}
          </button>
        )}
      </div>

      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New event</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted md:col-span-2">
              Title
              <input value={fTitle} onChange={(e) => setFTitle(e.target.value)} placeholder="Deal review"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Date
              <input type="date" value={fDate} onChange={(e) => setFDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-muted">
                Time
                <input type="time" value={fTime} onChange={(e) => setFTime(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
              </label>
              <label className="text-xs text-muted">
                Duration (min)
                <input type="number" min={5} step={5} value={fDuration} onChange={(e) => setFDuration(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
              </label>
            </div>
            <label className="text-xs text-muted md:col-span-2">
              Location
              <input value={fLocation} onChange={(e) => setFLocation(e.target.value)} placeholder="Zoom / Office"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <button
            onClick={createEvent}
            disabled={busy === "create" || !fTitle.trim() || !fDate}
            className="mt-3 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
          >
            {busy === "create" ? "Scheduling…" : "Schedule event"}
          </button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* month grid */}
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <button onClick={() => setCursor(new Date(year, month - 1, 1))} className="rounded-lg border border-border px-2 py-1 text-muted transition hover:text-foreground">
              <ChevronLeft size={14} />
            </button>
            <span className="text-sm font-semibold">{monthLabel}</span>
            <button onClick={() => setCursor(new Date(year, month + 1, 1))} className="rounded-lg border border-border px-2 py-1 text-muted transition hover:text-foreground">
              <ChevronRight size={14} />
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-semibold uppercase text-muted">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => <div key={d} className="py-1">{d}</div>)}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {cells.map((day, i) => (
              <div
                key={i}
                className={`min-h-[64px] rounded-lg border p-1 text-left ${day === null ? "border-transparent" : isToday(day) ? "border-accent bg-accent-soft" : "border-border bg-background"}`}
              >
                {day !== null && (
                  <>
                    <div className={`text-[11px] ${isToday(day) ? "font-bold text-accent" : "text-muted"}`}>{day}</div>
                    <div className="mt-0.5 space-y-0.5">
                      {eventsOn(day).slice(0, 3).map((e) => (
                        <div key={e.id} className="truncate rounded bg-accent px-1 py-0.5 text-[9px] font-medium text-on-accent" title={e.title}>
                          {e.title}
                        </div>
                      ))}
                      {eventsOn(day).length > 3 && <div className="text-[9px] text-muted">+{eventsOn(day).length - 3} more</div>}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* upcoming list */}
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Upcoming</h2>
          <div className="mt-3 space-y-2">
            {loading ? (
              [0, 1, 2].map((i) => <div key={i} className="skeleton h-12 w-full rounded-lg" />)
            ) : upcoming.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted">Nothing scheduled.</div>
            ) : (
              upcoming.map((e) => (
                <div key={e.id} className="rounded-lg border border-border bg-background p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold">{e.title}</div>
                      <div className="mt-0.5 text-[10px] text-muted">
                        {new Date(e.starts_at).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        {e.location && <span> · {e.location}</span>}
                      </div>
                      {e.object && <div className="mt-0.5 text-[10px] text-accent">{e.object}{e.record_id ? ` #${e.record_id.slice(0, 8)}` : ""}</div>}
                    </div>
                    {canEdit && (
                      <button onClick={() => deleteEvent(e)} disabled={busy === e.id} className="shrink-0 text-muted transition hover:text-danger disabled:opacity-50">
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Phase O: File Storage ---------------- */

interface FileDef {
  id: string;
  name: string;
  content_type: string;
  size: number;
  object: string | null;
  record_id: string | null;
  created_at: string;
}

function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function FilesView({ canEdit }: { canEdit: boolean }) {
  const [files, setFiles] = useState<FileDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<{ items: FileDef[] }>("/api/files");
      setFiles(res.items);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function uploadFiles(list: FileList | File[]) {
    const token = getToken();
    for (const file of Array.from(list)) {
      setBusy(file.name);
      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch(`${API_BASE}/api/files`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: fd,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(typeof err.detail === "string" ? err.detail : `Upload failed (${res.status})`);
        }
        toast(`Uploaded "${file.name}"`, "success");
      } catch (err) {
        toast(err instanceof Error ? err.message : "Upload failed", "error");
      } finally {
        setBusy(null);
      }
    }
    await load();
  }

  async function downloadFile(f: FileDef) {
    const token = getToken();
    try {
      const res = await fetch(`${API_BASE}/api/files/${f.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = f.name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Download failed", "error");
    }
  }

  async function deleteFile(f: FileDef) {
    setBusy(f.id);
    try {
      await api(`/api/files/${f.id}`, { method: "DELETE" });
      toast(`Deleted "${f.name}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">Files</h1>
        <p className="mt-0.5 text-xs text-muted">Workspace file storage. Upload anything up to 25 MB — attach files to records from any object view.</p>
      </div>

      {canEdit && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files); }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-10 text-center transition ${dragOver ? "border-accent bg-accent-soft" : "border-border hover:border-accent"}`}
        >
          <Paperclip size={24} className="text-muted" />
          <div className="mt-2 text-sm font-medium">{busy ? `Uploading ${busy}…` : "Drop files here or click to browse"}</div>
          <div className="mt-0.5 text-xs text-muted">Max 25 MB per file</div>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files?.length) uploadFiles(e.target.files); e.target.value = ""; }}
          />
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-14 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background text-muted">
                  <Paperclip size={16} />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{f.name}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {fmtBytes(f.size)} · {f.content_type}
                    {f.object && <span> · {f.object}{f.record_id ? ` #${f.record_id.slice(0, 8)}` : ""}</span>}
                    {" · "}{new Date(f.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button onClick={() => downloadFile(f)} className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground">
                  <Download size={12} className="mr-1 inline" />Download
                </button>
                {canEdit && (
                  <button
                    onClick={() => deleteFile(f)}
                    disabled={busy === f.id}
                    className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {files.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No files yet. Drop something above to get started.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase N: Public Forms ---------------- */

interface FormDef {
  id: string;
  slug: string;
  name: string;
  description: string;
  object: string;
  fields: string[];
  active: boolean;
  submissions: number;
  created_at: string;
}

function FormsView({ isAdmin }: { isAdmin: boolean }) {
  const [forms, setForms] = useState<FormDef[]>([]);
  const [objects, setObjects] = useState<{ slug: string; name: string; fields: { slug: string; name: string; type: string; required: boolean }[] }[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  // create form state
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fSlug, setFSlug] = useState("");
  const [fObject, setFObject] = useState("");
  const [fFields, setFFields] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const [f, o] = await Promise.all([
        api<{ items: FormDef[] }>("/api/forms"),
        api<{ slug: string; name: string; fields: { slug: string; name: string; type: string; required: boolean }[] }[]>("/api/objects"),
      ]);
      setForms(f.items);
      setObjects(o);
      if (!fObject && o.length) setFObject(o[0].slug);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [fObject]);

  useEffect(() => {
    load();
  }, [load]);

  const selectedObject = objects.find((o) => o.slug === fObject);

  async function createForm() {
    if (!fName.trim() || !fSlug.trim() || !fObject) return;
    setBusy("create");
    try {
      await api("/api/forms", {
        method: "POST",
        body: { slug: fSlug.trim(), name: fName.trim(), object: fObject, fields: fFields },
      });
      toast(`Form "${fName.trim()}" created`, "success");
      setShowForm(false);
      setFName("");
      setFSlug("");
      setFFields([]);
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function toggleActive(form: FormDef) {
    setBusy(form.id);
    try {
      await api(`/api/forms/${form.id}`, { method: "PATCH", body: { active: !form.active } });
      toast(form.active ? `Deactivated "${form.name}"` : `Activated "${form.name}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Update failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function deleteForm(form: FormDef) {
    setBusy(form.id);
    try {
      await api(`/api/forms/${form.id}`, { method: "DELETE" });
      toast(`Deleted "${form.name}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  function copyLink(slug: string) {
    const url = `${window.location.origin}/forms/${slug}`;
    navigator.clipboard.writeText(url).then(
      () => toast("Public link copied", "success"),
      () => toast(url, "info")
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Forms</h1>
          <p className="mt-0.5 text-xs text-muted">Public intake forms. Share a link — submissions become real records and fire your automations.</p>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            {showForm ? "Cancel" : "+ New form"}
          </button>
        )}
      </div>

      {showForm && isAdmin && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New form</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Lead intake"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Public slug <span className="text-faint">(lowercase, digits, hyphens)</span>
              <input value={fSlug} onChange={(e) => setFSlug(e.target.value.toLowerCase())} placeholder="lead-intake"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Object
              <select value={fObject} onChange={(e) => { setFObject(e.target.value); setFFields([]); }}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                {objects.map((o) => <option key={o.slug} value={o.slug}>{o.name} ({o.slug})</option>)}
              </select>
            </label>
          </div>
          {selectedObject && (
            <div className="mt-3">
              <div className="text-xs text-muted">Fields to expose <span className="text-faint">(none selected = all non-hidden fields)</span></div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {selectedObject.fields.map((f) => {
                  const on = fFields.includes(f.slug);
                  return (
                    <button
                      key={f.slug}
                      onClick={() => setFFields((prev) => on ? prev.filter((s) => s !== f.slug) : [...prev, f.slug])}
                      className={`rounded-full px-2.5 py-1 text-xs transition ${on ? "bg-accent text-on-accent" : "bg-background text-muted hover:text-foreground"}`}
                    >
                      {f.name}{f.required ? " *" : ""}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <button
            onClick={createForm}
            disabled={busy === "create" || !fName.trim() || !fSlug.trim() || !fObject}
            className="mt-3 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
          >
            {busy === "create" ? "Creating…" : "Create form"}
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="skeleton h-20 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {forms.map((form) => (
            <div key={form.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{form.name}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${form.active ? "bg-success/10 text-success" : "bg-background text-muted"}`}>
                    {form.active ? "active" : "inactive"}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted">
                  <span className="font-mono">/{form.slug}</span> → {form.object} · {form.fields.length || "all"} field(s) · {form.submissions} submission(s)
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button onClick={() => copyLink(form.slug)} className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground">
                  <Copy size={12} className="mr-1 inline" />Copy link
                </button>
                {isAdmin && (
                  <>
                    <button
                      onClick={() => toggleActive(form)}
                      disabled={busy === form.id}
                      className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50"
                    >
                      {form.active ? "Deactivate" : "Activate"}
                    </button>
                    <button
                      onClick={() => deleteForm(form)}
                      disabled={busy === form.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"
                    >
                      <Trash2 size={12} />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
          {forms.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No forms yet. Create one to collect intake from anyone with the link — no login required.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase M: Saved Reports ---------------- */

interface ReportDef {
  id: string;
  name: string;
  description: string;
  query: { object: string; metric: string; field?: string; value_field?: string; bucket?: string; days?: number; limit?: number };
  cron: string;
  next_run_at: string | null;
  created_at: string;
}
interface ReportRunRow {
  id: string;
  status: string;
  trigger: string;
  result: Record<string, unknown>;
  error: string | null;
  created_at: string;
}

const METRICS = ["count", "group_by", "sum", "avg", "min", "max", "summary", "time_series"];

function ReportsView({ canEdit }: { canEdit: boolean }) {
  const [reports, setReports] = useState<ReportDef[]>([]);
  const [objects, setObjects] = useState<{ slug: string; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [runs, setRuns] = useState<Record<string, ReportRunRow[]>>({});
  const [busy, setBusy] = useState<string | null>(null);

  // create form
  const [showForm, setShowForm] = useState(false);
  const [fName, setFName] = useState("");
  const [fObject, setFObject] = useState("");
  const [fMetric, setFMetric] = useState("count");
  const [fField, setFField] = useState("");
  const [fCron, setFCron] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, o] = await Promise.all([
        api<{ items: ReportDef[] }>("/api/reports"),
        api<{ slug: string; name: string }[]>("/api/objects"),
      ]);
      setReports(r.items);
      setObjects(o);
      if (!fObject && o.length) setFObject(o[0].slug);
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, [fObject]);

  useEffect(() => {
    load();
  }, [load]);

  async function createReport() {
    if (!fName.trim() || !fObject) return;
    setBusy("create");
    try {
      const query: ReportDef["query"] = { object: fObject, metric: fMetric };
      if (fField.trim()) query.field = fField.trim();
      await api("/api/reports", { method: "POST", body: { name: fName.trim(), query, cron: fCron.trim() } });
      toast(`Report "${fName.trim()}" created`, "success");
      setShowForm(false);
      setFName("");
      setFField("");
      setFCron("");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Create failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function runReport(id: string) {
    setBusy(id);
    try {
      const run = await api<ReportRunRow>(`/api/reports/${id}/run`, { method: "POST" });
      toast(run.status === "ok" ? "Report ran" : `Report error: ${run.error}`, run.status === "ok" ? "success" : "error");
      await loadRuns(id);
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Run failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function loadRuns(id: string) {
    try {
      const res = await api<{ items: ReportRunRow[] }>(`/api/reports/${id}/runs`);
      setRuns((prev) => ({ ...prev, [id]: res.items }));
    } catch {
      /* ignore */
    }
  }

  async function deleteReport(id: string, name: string) {
    setBusy(id);
    try {
      await api(`/api/reports/${id}`, { method: "DELETE" });
      toast(`Deleted "${name}"`, "info");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Delete failed", "error");
    } finally {
      setBusy(null);
    }
  }

  function toggleExpand(id: string) {
    const next = expanded === id ? null : id;
    setExpanded(next);
    if (next) loadRuns(id);
  }

  function describeQuery(q: ReportDef["query"]) {
    const parts = [q.metric, "on", q.object];
    if (q.field) parts.push(`(${q.field})`);
    return parts.join(" ");
  }

  function renderResult(result: Record<string, unknown>) {
    if ("value" in result) return <span className="font-mono text-lg font-bold">{String(result.value)}</span>;
    if ("rows" in result && Array.isArray(result.rows)) {
      const rows = result.rows as { label?: string; value?: number; count?: number }[];
      const max = Math.max(...rows.map((r) => r.value ?? r.count ?? 0), 1);
      return (
        <div className="space-y-1.5">
          {rows.map((r, i) => {
            const v = r.value ?? r.count ?? 0;
            return (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="w-28 truncate text-muted">{r.label ?? "—"}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round((v / max) * 100)}%` }} />
                </div>
                <span className="w-14 text-right font-mono">{v}</span>
              </div>
            );
          })}
        </div>
      );
    }
    return <pre className="overflow-x-auto rounded-lg bg-background p-2 text-[11px] text-muted">{JSON.stringify(result, null, 2)}</pre>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Reports</h1>
          <p className="mt-0.5 text-xs text-muted">Saved analytics queries. Run on demand or on a cron schedule — every run is snapshotted.</p>
        </div>
        {canEdit && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110"
          >
            {showForm ? "Cancel" : "+ New report"}
          </button>
        )}
      </div>

      {showForm && canEdit && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">New report</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs text-muted">
              Name
              <input value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Weekly lead count"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted">
              Object
              <select value={fObject} onChange={(e) => setFObject(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                {objects.map((o) => <option key={o.slug} value={o.slug}>{o.name} ({o.slug})</option>)}
              </select>
            </label>
            <label className="text-xs text-muted">
              Metric
              <select value={fMetric} onChange={(e) => setFMetric(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent">
                {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="text-xs text-muted">
              Field <span className="text-faint">(for group_by / sum / avg / …)</span>
              <input value={fField} onChange={(e) => setFField(e.target.value)} placeholder="source"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent" />
            </label>
            <label className="text-xs text-muted md:col-span-2">
              Schedule <span className="text-faint">(optional 5-field cron, e.g. &quot;0 9 * * 1&quot; = Mondays 9am)</span>
              <input value={fCron} onChange={(e) => setFCron(e.target.value)} placeholder="0 9 * * 1"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground outline-none focus:border-accent" />
            </label>
          </div>
          <button
            onClick={createReport}
            disabled={busy === "create" || !fName.trim() || !fObject}
            className="mt-3 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
          >
            {busy === "create" ? "Creating…" : "Create report"}
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="skeleton h-20 w-full rounded-xl" />)}</div>
      ) : (
        <div className="space-y-2">
          {reports.map((r) => (
            <div key={r.id} className="rounded-xl border border-border bg-card">
              <div className="flex items-center justify-between gap-3 px-4 py-3">
                <button onClick={() => toggleExpand(r.id)} className="min-w-0 flex-1 text-left">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{r.name}</span>
                    {r.cron && <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[10px] text-accent">⏱ {r.cron}</span>}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted">
                    {describeQuery(r.query)}
                    {r.next_run_at && <span> · next run {new Date(r.next_run_at).toLocaleString()}</span>}
                  </div>
                </button>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() => runReport(r.id)}
                    disabled={busy === r.id}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground disabled:opacity-50"
                  >
                    {busy === r.id ? "Running…" : "Run"}
                  </button>
                  {canEdit && (
                    <button
                      onClick={() => deleteReport(r.id, r.name)}
                      disabled={busy === r.id}
                      className="rounded-lg border border-border px-2 py-1 text-xs text-muted transition hover:text-danger disabled:opacity-50"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                  <span className="text-faint">{expanded === r.id ? "▾" : "▸"}</span>
                </div>
              </div>
              {expanded === r.id && (
                <div className="border-t border-border px-4 py-3">
                  <h3 className="text-xs font-semibold text-muted">Run history</h3>
                  <div className="mt-2 space-y-3">
                    {(runs[r.id] ?? []).slice(0, 5).map((run) => (
                      <div key={run.id} className="rounded-lg border border-border bg-background p-3">
                        <div className="flex items-center justify-between text-[11px] text-muted">
                          <span>
                            <span className={`mr-2 rounded-full px-2 py-0.5 text-[10px] ${run.status === "ok" ? "bg-success/10 text-success" : "bg-danger/10 text-danger"}`}>{run.status}</span>
                            {run.trigger} · {new Date(run.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="mt-2">
                          {run.status === "ok" ? renderResult(run.result) : <span className="text-xs text-danger">{run.error}</span>}
                        </div>
                      </div>
                    ))}
                    {(runs[r.id] ?? []).length === 0 && (
                      <div className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted">No runs yet — hit Run.</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
          {reports.length === 0 && (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
              No saved reports yet. Create one to snapshot an analytics query on demand or on a schedule.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Phase L: Billing ---------------- */

interface PlanInfo {
  id: string;
  name: string;
  price_cents: number;
  limits: { members: number | null; records: number | null; agents: number | null };
  description: string;
}
interface SubInfo {
  plan: string;
  plan_name: string;
  status: string;
  seats: number;
  cancel_at_period_end: boolean;
  current_period_end: string;
  price_cents_per_seat: number;
}
interface UsageInfo {
  plan: string;
  usage: { members: number; records: number; agents: number };
  limits: { members: number | null; records: number | null; agents: number | null };
  headroom: { members: number | null; records: number | null; agents: number | null };
}
interface InvoiceInfo {
  id: string;
  number: string;
  amount_cents: number;
  currency: string;
  status: string;
  lines: { description?: string; qty?: number };
  period_start: string;
  period_end: string;
  created_at: string;
}

function BillingView({ isAdmin }: { isAdmin: boolean }) {
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [sub, setSub] = useState<SubInfo | null>(null);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [invoices, setInvoices] = useState<InvoiceInfo[]>([]);
  const [seats, setSeats] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [p, s, u, inv] = await Promise.all([
        api<{ items: PlanInfo[] }>("/api/billing/plans"),
        api<SubInfo>("/api/billing/subscription"),
        api<UsageInfo>("/api/billing/usage"),
        api<{ items: InvoiceInfo[] }>("/api/billing/invoices"),
      ]);
      setPlans(p.items);
      setSub(s);
      setUsage(u);
      setInvoices(inv.items);
      setSeats(s.seats);
    } catch {
      /* keep last state */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function checkout(planId: string) {
    setBusy(planId);
    try {
      const res = await api<{ plan: string; invoice: string; amount_cents: number }>(
        "/api/billing/checkout",
        { method: "POST", body: { plan: planId, seats } }
      );
      toast(`Switched to ${planId} — invoice ${res.invoice} ($${(res.amount_cents / 100).toFixed(2)})`, "success");
      await load();
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      toast(typeof d === "string" ? d : "Checkout failed", "error");
    } finally {
      setBusy(null);
    }
  }

  async function cancelSub() {
    setBusy("cancel");
    try {
      await api("/api/billing/cancel", { method: "POST" });
      toast("Subscription will cancel at period end", "info");
      await load();
    } catch {
      toast("Cancel failed", "error");
    } finally {
      setBusy(null);
    }
  }

  const money = (cents: number) => `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
  const limitLabel = (n: number | null) => (n === null ? "Unlimited" : n.toLocaleString());

  const usageRows: { key: keyof UsageInfo["usage"]; label: string }[] = [
    { key: "members", label: "Members" },
    { key: "records", label: "Records" },
    { key: "agents", label: "AI employees" },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-bold">Billing</h1>
        <p className="mt-0.5 text-xs text-muted">Plan, usage, and invoices. Self-hosted checkout is a mock payment flow.</p>
      </div>

      {loading ? (
        <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="skeleton h-28 w-full rounded-xl" />)}</div>
      ) : (
        <>
          {/* current subscription */}
          {sub && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
              <div>
                <div className="text-sm font-semibold">
                  {sub.plan_name} plan · {sub.seats} seat{sub.seats !== 1 ? "s" : ""}
                  {sub.cancel_at_period_end && <span className="ml-2 rounded-full bg-danger/10 px-2 py-0.5 text-[11px] text-danger">cancels {new Date(sub.current_period_end).toLocaleDateString()}</span>}
                </div>
                <div className="mt-0.5 text-xs text-muted">
                  {money(sub.price_cents_per_seat)}/seat/month · renews {new Date(sub.current_period_end).toLocaleDateString()}
                </div>
              </div>
              {isAdmin && !sub.cancel_at_period_end && sub.plan !== "free" && (
                <button
                  onClick={cancelSub}
                  disabled={busy === "cancel"}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition hover:text-danger disabled:opacity-50"
                >
                  {busy === "cancel" ? "Cancelling…" : "Cancel at period end"}
                </button>
              )}
            </div>
          )}

          {/* usage vs limits */}
          {usage && (
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="text-sm font-semibold">Usage</h2>
              <div className="mt-3 space-y-3">
                {usageRows.map(({ key, label }) => {
                  const used = usage.usage[key];
                  const cap = usage.limits[key];
                  const pct = cap === null ? 0 : Math.min(100, Math.round((used / Math.max(cap, 1)) * 100));
                  return (
                    <div key={key}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted">{label}</span>
                        <span className="font-mono">{used.toLocaleString()} / {limitLabel(cap)}</span>
                      </div>
                      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-background">
                        <div
                          className={`h-full rounded-full transition-all ${pct >= 90 ? "bg-danger" : pct >= 70 ? "bg-warning" : "bg-accent"}`}
                          style={{ width: cap === null ? "4%" : `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* plan picker */}
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">Plans</h2>
              {isAdmin && (
                <label className="flex items-center gap-2 text-xs text-muted">
                  Seats
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={seats}
                    onChange={(e) => setSeats(Math.max(1, Number(e.target.value) || 1))}
                    className="w-20 rounded-lg border border-border bg-background px-2 py-1 text-sm outline-none focus:border-accent"
                  />
                </label>
              )}
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {plans.map((p) => {
                const current = sub?.plan === p.id;
                return (
                  <div key={p.id} className={`rounded-xl border p-4 ${current ? "border-accent bg-accent-soft" : "border-border bg-background"}`}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-sm font-semibold">{p.name}</span>
                      <span className="text-sm font-bold">{p.price_cents === 0 ? "Free" : `${money(p.price_cents)}/seat/mo`}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted">{p.description}</p>
                    <ul className="mt-2 space-y-1 text-[11px] text-muted">
                      <li>👥 {limitLabel(p.limits.members)} members</li>
                      <li>🗂 {limitLabel(p.limits.records)} records</li>
                      <li>🤖 {limitLabel(p.limits.agents)} AI employees</li>
                    </ul>
                    {isAdmin && (
                      <button
                        onClick={() => checkout(p.id)}
                        disabled={current || busy !== null}
                        className={`mt-3 w-full rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${
                          current ? "cursor-default border border-border text-muted" : "bg-accent text-on-accent hover:brightness-110"
                        }`}
                      >
                        {current ? "Current plan" : busy === p.id ? "Switching…" : `Switch to ${p.name}`}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* invoices */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">Invoices</h2>
            <div className="mt-3 space-y-2">
              {invoices.map((inv) => (
                <div key={inv.id} className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-xs">
                  <div className="min-w-0">
                    <span className="font-mono font-semibold">{inv.number}</span>
                    <span className="ml-2 text-muted">{inv.lines.description}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="text-muted">{new Date(inv.period_start).toLocaleDateString()} – {new Date(inv.period_end).toLocaleDateString()}</span>
                    <span className="font-semibold">{money(inv.amount_cents)}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${inv.status === "paid" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>{inv.status}</span>
                  </div>
                </div>
              ))}
              {invoices.length === 0 && (
                <div className="rounded-lg border border-dashed border-border px-4 py-5 text-center text-xs text-muted">
                  No invoices yet — they appear when you switch to a paid plan.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ---------------- Events ---------------- */

function EventsView() {
  const [events, setEvents] = useState<
    { id: string; type: string; summary: string; actor_name: string; plugin_id: string | null; payload: unknown; created_at: string }[]
  >([]);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ items: typeof events }>("/api/audit?limit=100").then((r) => setEvents(r.items)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // group filter chips by event-type prefix (record, plugin, agent, ...)
  const prefixes = useMemo(() => {
    const s = new Set(events.map((e) => e.type.split(".")[0]));
    return [...s].sort();
  }, [events]);

  const shown = filter ? events.filter((e) => e.type.startsWith(filter)) : events;

  function exportCsv() {
    const qs = filter ? `?type=${encodeURIComponent(filter)}` : "";
    // download via anchor with auth header is not possible; open in new tab (token in localStorage is sent by api(), so use fetch+blob)
    api<Blob>(`/api/audit/export.csv${qs}`, { raw: true }).then((text) => {
      const blob = new Blob([text as unknown as string], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "audit-log.csv";
      a.click();
      URL.revokeObjectURL(url);
    }).catch(() => {});
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">⚡ Audit Log</h1>
          <p className="mt-1 text-sm text-muted">
            Every action in the workspace — who did what, when. Filter by category, expand for the full
            payload, or export to CSV for compliance.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-border-strong hover:text-foreground"
          >
            <Download size={12} /> Export CSV
          </button>
          <button
            onClick={load}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-border-strong hover:text-foreground"
          >
            <RotateCcw size={12} /> Refresh
          </button>
        </div>
      </div>

      {prefixes.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          <button
            onClick={() => setFilter("")}
            className={`rounded-full px-2.5 py-1 text-xs transition ${
              filter === "" ? "bg-accent text-on-accent" : "bg-card text-muted hover:text-foreground"
            }`}
          >
            All ({events.length})
          </button>
          {prefixes.map((t) => (
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
              <span className="min-w-0 flex-1">
                <span className="block truncate">{e.summary}</span>
                <span className="block truncate text-[11px] text-muted">
                  {e.actor_name} · <span className="font-mono text-accent">{e.type}</span>
                  {e.plugin_id && <span> · 🧩 {e.plugin_id}</span>}
                </span>
              </span>
              <span className="shrink-0 text-[11px] text-muted">
                {new Date(e.created_at).toLocaleString()}
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
            {filter ? `No events in category ${filter}.` : "No events yet."}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Appearance / Settings ---------------- */

function SettingsView() {
  const { theme, resolvedMode, setMode, setAccent, setDensity, setRadius, setFontFamily, setFontScale, setMotion, reset } = useTheme();
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

      {/* Font family */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Font</h2>
        <p className="mt-0.5 text-xs text-muted">The typeface used across the interface.</p>
        <div className="mt-3 flex rounded-lg border border-border bg-card p-1">
          {([["sans", "Sans"], ["serif", "Serif"], ["mono", "Mono"]] as [FontFamily, string][]).map(([f, label]) => (
            <button key={f} onClick={() => setFontFamily(f)} className={segBtn(theme.fontFamily === f)}>
              {label}
            </button>
          ))}
        </div>
      </section>

      {/* Font size */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Font size</h2>
        <p className="mt-0.5 text-xs text-muted">Scale all text up or down, independent of density.</p>
        <div className="mt-3 flex rounded-lg border border-border bg-card p-1">
          {([["sm", "Small"], ["md", "Medium"], ["lg", "Large"]] as [FontScale, string][]).map(([s, label]) => (
            <button key={s} onClick={() => setFontScale(s)} className={segBtn(theme.fontScale === s)}>
              {label}
            </button>
          ))}
        </div>
      </section>

      {/* Motion */}
      <section className="mt-8">
        <h2 className="text-sm font-semibold">Motion</h2>
        <p className="mt-0.5 text-xs text-muted">Reduce animations for a calmer, lower-distraction experience.</p>
        <div className="mt-3 flex rounded-lg border border-border bg-card p-1">
          {([["full", "Full"], ["reduced", "Reduced"]] as [Motion, string][]).map(([m, label]) => (
            <button key={m} onClick={() => setMotion(m)} className={segBtn(theme.motion === m)}>
              {label}
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
