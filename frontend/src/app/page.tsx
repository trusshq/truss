"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Bot,
  Boxes,
  Cable,
  Check,
  Cog,
  Database,
  FileText,
  GitBranch,
  Headphones,
  KeyRound,
  Layers,
  ListChecks,
  Lock,
  Server,
  ShieldCheck,
  Sparkles,
  Target,
  Terminal,
  Webhook,
  Zap,
} from "lucide-react";
import { API_BASE, checkAuth } from "@/lib/api";
import {
  Marquee,
  Meteors,
  NumberTicker,
  Reveal,
  ShimmerButton,
  SpotlightCard,
  Stagger,
  StaggerItem,
  WordRotate,
} from "@/components/motion";
import { Icon } from "@iconify/react";

/* ------------------------------------------------------------------ */
/*  Truss — landing page                                               */
/*  Monochrome-first. Structural-engineering design language: the      */
/*  kernel is the load-bearing chord, plugins are the web members.     */
/*  No icon tiles above headings, no nested cards, no bounce easing.   */
/* ------------------------------------------------------------------ */

const CAPABILITIES = [
  "CRM", "INVOICES", "TASKS", "HELPDESK", "AUTOMATIONS", "AI AGENTS",
  "CONNECTORS", "EVENT BUS", "MULTI-TENANT", "BYOK AI", "RBAC", "SELF-HOSTED",
];

const STATS = [
  { value: "4", label: "apps ship in the box" },
  { value: "6", label: "kernel subsystems" },
  { value: "1", label: "JSON manifest per app" },
  { value: "0", label: "lines of code to add an app" },
];

const KERNEL_SPECS = [
  {
    n: "01",
    icon: Server,
    title: "Multi-tenant kernel",
    body: "Auth, JWT, role-based access, and hard tenant isolation. Every workspace is its own world on one process.",
    spec: "owner / admin / member / viewer",
  },
  {
    n: "02",
    icon: Database,
    title: "Metadata data layer",
    body: "Business objects are data, not DDL. Plugins declare objects and fields as JSON; records live in JSONB. No migrations to ship an app.",
    spec: "objects → fields → records",
  },
  {
    n: "03",
    icon: Boxes,
    title: "Plugin runtime",
    body: "Install, enable, disable. A full business app is one plugin.json — objects, AI tools, automations, and UI surfaces in a single manifest.",
    spec: "declarative · zero code",
  },
  {
    n: "04",
    icon: KeyRound,
    title: "BYOK AI runtime",
    body: "Bring any OpenAI-compatible endpoint — OpenAI, DeepSeek, OpenRouter, Groq, Ollama. Keys encrypted at rest, agents scoped to your tenant.",
    spec: "fernet vault · agent loop",
  },
  {
    n: "05",
    icon: Cog,
    title: "Automation engine",
    body: "Trigger → condition → action, interpreted from plugin manifests off the event bus. Atomic with the write that fired it, depth-guarded.",
    spec: "event-driven · audited",
  },
  {
    n: "06",
    icon: Cable,
    title: "Connectors",
    body: "Forward events to any webhook with HMAC signing, query external Postgres/Neon read-only. Your analytics, your warehouse, your keys.",
    spec: "outbox · signed delivery",
  },
];

const APPS = [
  { icon: "fluent-color:people-team-24", fallback: Target, name: "CRM", id: "truss-crm", desc: "Companies, contacts, leads, deals — Twenty-inspired, pipeline-ready.", objects: 4, automations: 1 },
  { icon: "fluent-color:receipt-24", fallback: FileText, name: "Invoices", id: "truss-invoices", desc: "Draft → Sent → Paid with amounts, due dates, and billing events.", objects: 1, automations: 2 },
  { icon: "fluent-color:task-list-square-24", fallback: ListChecks, name: "Tasks", id: "truss-tasks", desc: "To-dos with priority, due dates, and multiselect tags. Kanban-ready.", objects: 1, automations: 1 },
  { icon: "fluent-color:headset-24", fallback: Headphones, name: "Helpdesk", id: "truss-helpdesk", desc: "Support tickets with status, priority, and category queues.", objects: 1, automations: 2 },
];

const BYO = [
  { icon: Sparkles, t: "AI keys", b: "Any OpenAI-compatible endpoint — OpenAI, DeepSeek, OpenRouter, Groq, Ollama, vLLM. Encrypted at rest, masked in the API, never logged." },
  { icon: Database, t: "Databases", b: "Point connectors at external Postgres or Neon and query them read-only from inside Truss." },
  { icon: Webhook, t: "Analytics", b: "Forward every kernel event to your own webhook — PostHog, a warehouse, anything — with HMAC-signed payloads." },
  { icon: Server, t: "Infrastructure", b: "One docker compose file. Postgres, Redis, kernel. Your hardware, your cloud, your basement." },
];

const ROADMAP = [
  { phase: "Phase 0", title: "Kernel", status: "done", body: "Multi-tenancy, auth/RBAC, metadata data layer, plugin runtime, event seam." },
  { phase: "Phase 1", title: "BYOK AI", status: "done", body: "Encrypted key vault, OpenAI-compatible client, agent loop under RBAC." },
  { phase: "Phase 2", title: "Automations", status: "done", body: "Declarative trigger→condition→action engine off the event bus." },
  { phase: "Phase 3", title: "Connectors", status: "done", body: "Webhook forwarding, external Postgres/Neon, delivery outbox + retry." },
  { phase: "Phase 4", title: "App suite", status: "done", body: "CRM, Invoices, Tasks, Helpdesk — each a pure plugin.json." },
  { phase: "Next", title: "Marketplace", status: "next", body: "Community plugins, templates, and a hosted tier for teams." },
];

const FAQ = [
  { q: "Is Truss really open source?", a: "Yes. Apache 2.0. The kernel, the plugin runtime, and all four first-party apps. Fork it, self-host it, extend it — no license fees, no lock-in." },
  { q: "Do I have to use your AI?", a: "No. Truss has no built-in model. You bring your own API key and endpoint for any OpenAI-compatible provider, including fully local ones like Ollama. Your keys are encrypted at rest and never leave your machine." },
  { q: "How do I add my own app?", a: "Write a plugin.json — declare objects, fields, AI tools, automations, and UI surfaces. Drop it in the plugins folder and install it from the dashboard. No backend code, no migrations." },
  { q: "Where does my data live?", a: "In your own Postgres. Truss never phones home. The event seam lets you forward activity to your own analytics if you want — it's opt-in and signed." },
  { q: "Can I run it in production?", a: "The kernel is a modular monolith behind one process with a Postgres backing store. Docker Compose gets you there in one command. Scale horizontally by adding kernel instances behind a load balancer." },
];

/* Auth-aware "Open Dashboard" button. */
function DashboardButton({ primary = true, label }: { primary?: boolean; label?: string }) {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    checkAuth().then((me) => setAuthed(!!me));
  }, []);

  async function go() {
    setBusy(true);
    const me = await checkAuth();
    router.push(me ? "/dashboard" : "/login");
  }

  return (
    <button
      onClick={go}
      disabled={busy}
      className={
        primary
          ? "group inline-flex items-center gap-2 rounded-lg bg-foreground px-5 py-2.5 text-sm font-semibold text-background transition hover:opacity-90 disabled:opacity-60"
          : "inline-flex items-center gap-2 rounded-lg border border-border-strong px-5 py-2.5 text-sm font-medium text-foreground transition hover:border-foreground disabled:opacity-60"
      }
    >
      {busy ? "Checking session…" : (label ?? (authed ? "Open Dashboard" : "Open Dashboard"))}
      {!busy && <ArrowRight size={15} aria-hidden className="transition-transform group-hover:translate-x-0.5" />}
    </button>
  );
}

/* Inline GitHub mark (lucide dropped brand icons). */
function GithubIcon({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.88-1.36-3.88-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.78 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.24 2.76.12 3.05.74.81 1.18 1.83 1.18 3.09 0 4.41-2.69 5.38-5.26 5.66.41.36.78 1.06.78 2.14 0 1.54-.02 2.79-.02 3.17 0 .3.21.67.8.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

/* Live kernel status dot. */
function KernelStatus() {
  const [up, setUp] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/api/health`)
      .then((r) => alive && setUp(r.ok))
      .catch(() => alive && setUp(false));
    return () => { alive = false; };
  }, []);
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${up === null ? "bg-muted" : up ? "bg-success" : "bg-danger"}`} />
      kernel {up === null ? "…" : up ? "online" : "offline"} · 127.0.0.1:8000
    </span>
  );
}

/* Warren truss diagram. */
function TrussDiagram() {
  const bottom: [number, number][] = [[40, 200], [140, 200], [240, 200], [340, 200], [440, 200]];
  const top: [number, number][] = [[90, 110], [190, 110], [290, 110], [390, 110]];
  const diagLabels = ["crm", "invoices", "tasks", "helpdesk", "ai", "automations", "connectors", "events"];
  const diags: [[number, number], [number, number]][] = [
    [bottom[0], top[0]], [top[0], bottom[1]], [bottom[1], top[1]], [top[1], bottom[2]],
    [bottom[2], top[2]], [top[2], bottom[3]], [bottom[3], top[3]], [top[3], bottom[4]],
  ];
  const Member = ({ a, b, load = false, delay }: { a: [number, number]; b: [number, number]; load?: boolean; delay: number }) => {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    return (
      <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
        stroke={load ? "var(--foreground)" : "var(--muted)"}
        strokeWidth={load ? 2.5 : 1.5}
        className={`truss-member ${load ? "load-path" : ""}`}
        style={{ ["--len" as string]: len, ["--delay" as string]: `${delay}s` }} />
    );
  };
  return (
    <svg viewBox="0 0 480 250" className="w-full" role="img" aria-label="Truss structural diagram: the kernel chord carries the load, plugin members transfer it">
      {bottom.slice(0, -1).map((p, k) => <Member key={`b${k}`} a={p} b={bottom[k + 1]} load delay={0.1 + k * 0.12} />)}
      {top.slice(0, -1).map((p, k) => <Member key={`t${k}`} a={p} b={top[k + 1]} delay={0.5 + k * 0.12} />)}
      {diags.map(([a, b], k) => <Member key={`d${k}`} a={a} b={b} delay={0.8 + k * 0.1} />)}
      {[...bottom, ...top].map((p, k) => (
        <circle key={`n${k}`} cx={p[0]} cy={p[1]} r={4} fill="var(--background)" stroke="var(--foreground)" strokeWidth={1.5}
          className="truss-node" style={{ ["--delay" as string]: `${1.4 + k * 0.05}s` }} />
      ))}
      {diags.map(([a, b], k) => (
        <text key={`l${k}`} x={(a[0] + b[0]) / 2 + (k % 2 === 0 ? -14 : 8)} y={(a[1] + b[1]) / 2}
          fill="var(--muted)" fontSize={8.5} fontFamily="var(--font-mono)"
          className="truss-node" style={{ ["--delay" as string]: `${1.7 + k * 0.06}s` }}>
          {diagLabels[k]}
        </text>
      ))}
      <text x={40} y={228} fill="var(--foreground)" fontSize={9} fontFamily="var(--font-mono)" className="truss-node" style={{ ["--delay" as string]: "2.2s" }}>
        KERNEL — LOAD-BEARING CHORD
      </text>
      <text x={300} y={96} fill="var(--muted)" fontSize={9} fontFamily="var(--font-mono)" className="truss-node" style={{ ["--delay" as string]: "2.3s" }}>
        PLUGINS — WEB MEMBERS
      </text>
    </svg>
  );
}

export default function LandingPage() {
  return (
    <main className="min-h-screen">
      {/* ---------- nav ---------- */}
      <header className="sticky top-0 z-20 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <GitBranch size={18} className="text-foreground" />
            <span className="text-[15px] font-bold tracking-tight">Truss</span>
            <span className="hidden rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted sm:inline">v0.1 · open source</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden md:inline"><KernelStatus /></span>
            <a href="/login" className="text-sm text-muted transition hover:text-foreground">Sign in</a>
            <DashboardButton />
          </div>
        </div>
      </header>

      {/* ---------- hero ---------- */}
      <section className="blueprint relative overflow-hidden border-b border-border">
        <Meteors count={10} />
        <div className="relative mx-auto grid max-w-6xl gap-10 px-6 pb-16 pt-16 lg:grid-cols-[1.15fr_1fr] lg:items-center lg:pb-24 lg:pt-24">
          <div>
            <p className="animate-rise font-mono text-[11px] uppercase tracking-[0.2em] text-muted" style={{ ["--delay" as string]: "0s" }}>
              Open source · Plugin-first · Self-hosted
            </p>
            <h1 className="animate-rise mt-4 text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl" style={{ ["--delay" as string]: "0.08s" }}>
              One kernel carries
              <br />
              the{" "}
              <span className="underline decoration-2 underline-offset-8">
                <WordRotate words={["whole load.", "CRM.", "invoices.", "tickets.", "agents."]} />
              </span>
            </h1>
            <p className="animate-rise mt-5 max-w-xl text-base leading-relaxed text-muted sm:text-lg" style={{ ["--delay" as string]: "0.16s" }}>
              Truss is the open-source business OS. CRM, invoicing, tasks, helpdesk —
              every app is a plugin on a single kernel. Bring your own AI keys,
              own your data, extend it all with one JSON manifest.
            </p>
            <div className="animate-rise mt-8 flex flex-wrap items-center gap-3" style={{ ["--delay" as string]: "0.24s" }}>
              <DashboardButton />
              <DashboardButton primary={false} label="Create a workspace" />
            </div>
            <p className="animate-rise mt-6 flex items-center gap-2 font-mono text-[11px] text-muted" style={{ ["--delay" as string]: "0.32s" }}>
              <Terminal size={13} /> docker compose up · Apache 2.0 · your data never leaves your machine
            </p>
          </div>
          <div className="animate-rise rounded-xl border border-border bg-card/60 p-4" style={{ ["--delay" as string]: "0.2s" }}>
            <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-muted">
              <span>Fig. 01 — load distribution</span>
              <span>scale 1:1</span>
            </div>
            <TrussDiagram />
          </div>
        </div>
      </section>

      {/* ---------- capability ticker ---------- */}
      <div className="border-b border-border bg-card/40 py-3">
        <Marquee>
          {CAPABILITIES.map((c, k) => (
            <span key={k} className="flex items-center gap-8 whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
              {c} <span className="text-foreground">▲</span>
            </span>
          ))}
        </Marquee>
      </div>

      {/* ---------- stats band ---------- */}
      <section className="border-b border-border">
        <div className="mx-auto grid max-w-6xl grid-cols-2 divide-x divide-border px-6 md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="px-6 py-8 first:pl-0">
              <div className="text-4xl font-bold tracking-tight">
                <NumberTicker value={parseInt(s.value, 10)} />
              </div>
              <div className="mt-1 text-xs text-muted">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- kernel specs (ledger) ---------- */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Section 02</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">The kernel carries the load</h2>
          </div>
          <p className="max-w-sm text-sm text-muted">
            Six structural members. Everything else — every app, every integration — bolts on.
          </p>
        </div>
        <div className="divide-y divide-border border-y border-border">
          {KERNEL_SPECS.map((s) => (
            <div key={s.n} className="group grid gap-2 py-6 transition-colors hover:bg-card/40 sm:grid-cols-[56px_40px_220px_1fr_auto] sm:items-baseline sm:gap-5 sm:px-2">
              <span className="font-mono text-sm text-muted">{s.n}</span>
              <s.icon size={18} className="hidden text-muted sm:block" />
              <h3 className="text-base font-semibold">{s.title}</h3>
              <p className="text-sm leading-relaxed text-muted">{s.body}</p>
              <span className="font-mono text-[10px] uppercase tracking-wider text-faint">{s.spec}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- apps in the box ---------- */}
      <section className="border-y border-border bg-card/30">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="mb-10">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Section 03</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Four apps ship in the box</h2>
            <p className="mt-3 max-w-xl text-sm text-muted">
              Each one is nothing but a plugin.json — proof that a full business app
              is a manifest on Truss, not a codebase. Install, enable, use. Or write your own.
            </p>
          </div>
          <Stagger className="grid gap-4 md:grid-cols-2">
            {APPS.map((a) => (
              <StaggerItem key={a.id}>
                <SpotlightCard className="group h-full p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-card-2">
                        <Icon icon={a.icon} width={20} height={20} />
                      </span>
                      <div>
                        <div className="font-semibold">{a.name}</div>
                        <div className="font-mono text-[10px] text-muted">{a.id}</div>
                      </div>
                    </div>
                    <ArrowRight size={16} className="text-faint opacity-0 transition group-hover:opacity-100" />
                  </div>
                  <p className="mt-3 text-sm text-muted">{a.desc}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[10px] uppercase tracking-wider text-faint">
                    <span className="rounded border border-border px-2 py-0.5">{a.objects} object{a.objects > 1 ? "s" : ""}</span>
                    <span className="rounded border border-border px-2 py-0.5">{a.automations} automation{a.automations > 1 ? "s" : ""}</span>
                    <span className="rounded border border-border px-2 py-0.5">AI tools</span>
                  </div>
                </SpotlightCard>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      </section>

      {/* ---------- BYO everything ---------- */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Section 04</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Bring your own everything</h2>
            <ul className="mt-6 space-y-5">
              {BYO.map(({ icon: Icon, t, b }) => (
                <li key={t} className="grid gap-1 sm:grid-cols-[150px_1fr] sm:gap-6">
                  <span className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted">
                    <Icon size={14} /> {t}
                  </span>
                  <span className="text-sm leading-relaxed text-muted">{b}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-border bg-card/60 p-5 font-mono text-[12.5px] leading-relaxed">
            <div className="mb-3 flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
              <span className="ml-2 text-[10px] uppercase tracking-wider text-muted">terminal</span>
            </div>
            <pre className="overflow-x-auto text-muted">
{`$ git clone github.com/trusshq/truss
$ cd truss && docker compose up -d

▲ kernel online · 4 plugins discovered
  truss-crm  truss-invoices
  truss-tasks  truss-helpdesk

$ open http://localhost:3000`}
            </pre>
          </div>
        </div>
      </section>

      {/* ---------- roadmap ---------- */}
      <section className="border-y border-border bg-card/30">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="mb-10">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Section 05</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Built in the open</h2>
            <p className="mt-3 max-w-xl text-sm text-muted">
              Every phase shipped as working, tested software. Here's where the structure stands.
            </p>
          </div>
          <Stagger className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {ROADMAP.map((r) => (
              <StaggerItem key={r.phase}>
                <div className="h-full rounded-xl border border-border bg-card p-5 transition hover:border-border-strong">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">{r.phase}</span>
                    {r.status === "done" ? (
                      <span className="flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success">
                        <Check size={11} /> shipped
                      </span>
                    ) : (
                      <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-muted">next</span>
                    )}
                  </div>
                  <div className="mt-2 font-semibold">{r.title}</div>
                  <p className="mt-1 text-sm text-muted">{r.body}</p>
                </div>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      </section>

      {/* ---------- FAQ ---------- */}
      <section className="mx-auto max-w-3xl px-6 py-20">
        <div className="mb-10 text-center">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Section 06</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Questions, answered</h2>
        </div>
        <div className="divide-y divide-border border-y border-border">
          {FAQ.map((f) => (
            <details key={f.q} className="group py-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold">
                {f.q}
                <span className="text-muted transition-transform group-open:rotate-45">+</span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-muted">{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ---------- final CTA ---------- */}
      <section className="border-t border-border bg-card/30">
        <div className="mx-auto max-w-6xl px-6 py-20 text-center">
          <Layers size={28} className="mx-auto text-foreground" />
          <h2 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
            Stop renting your business software.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-muted">
            Create a workspace in ten seconds. The kernel is already running.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <ShimmerButton onClick={() => (window.location.href = "/dashboard")}>
              Open Dashboard <ArrowRight size={15} />
            </ShimmerButton>
            <DashboardButton primary={false} label="Create a workspace" />
          </div>
          <div className="mt-6 flex items-center justify-center gap-4 text-xs text-muted">
            <span className="flex items-center gap-1.5"><ShieldCheck size={13} /> Apache 2.0</span>
            <span className="flex items-center gap-1.5"><Lock size={13} /> Self-hosted</span>
            <span className="flex items-center gap-1.5"><Zap size={13} /> Plugin-first</span>
          </div>
        </div>
      </section>

      {/* ---------- footer ---------- */}
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-6">
          <span className="flex items-center gap-2 font-mono text-[11px] text-muted">
            <GitBranch size={13} /> © 2026 Truss · Apache 2.0
          </span>
          <div className="flex items-center gap-4 text-[11px] text-muted">
            <a href="https://github.com/trusshq" target="_blank" rel="noreferrer" className="flex items-center gap-1.5 transition hover:text-foreground">
              <GithubIcon size={13} /> github.com/trusshq
            </a>
            <KernelStatus />
          </div>
        </div>
      </footer>
    </main>
  );
}
