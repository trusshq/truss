"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, checkAuth, type AuthResponse } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Already have a valid session? Skip straight to the dashboard.
  useEffect(() => {
    checkAuth().then((me) => {
      if (me) router.replace("/dashboard");
    });
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      let res: AuthResponse;
      if (mode === "signup") {
        res = await api<AuthResponse>("/api/auth/signup", {
          auth: false,
          method: "POST",
          body: {
            email,
            password,
            full_name: fullName,
            tenant_name: tenantName || tenantSlug,
            tenant_slug: tenantSlug,
          },
        });
      } else {
        res = await api<AuthResponse>("/api/auth/login", {
          auth: false,
          method: "POST",
          body: { email, password },
        });
      }
      setToken(res.access_token);
      router.push("/dashboard");
    } catch (err) {
      const detail = (err as { detail?: unknown })?.detail;
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent";

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <a href="/" className="inline-block">
            <span className="font-mono text-2xl font-bold text-accent">▲</span>
            <div className="mt-1 text-2xl font-bold tracking-tight">Truss</div>
          </a>
          <p className="mt-1 text-sm text-muted">
            The open-source business OS. Plugins in, business out.
          </p>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <div className="mb-4 flex rounded-lg border border-border p-1">
            {(["signup", "login"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  mode === m ? "bg-accent-soft text-accent" : "text-muted hover:text-foreground"
                }`}
              >
                {m === "signup" ? "Create workspace" : "Sign in"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            {mode === "signup" && (
              <>
                <input className={input} placeholder="Your name" value={fullName}
                  onChange={(e) => setFullName(e.target.value)} />
                <input className={input} placeholder="Workspace name (e.g. Acme Inc)" value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)} />
                <input className={input} placeholder="Workspace slug (acme)" value={tenantSlug}
                  onChange={(e) => setTenantSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} required />
              </>
            )}
            <input className={input} type="email" placeholder="Email" value={email}
              onChange={(e) => setEmail(e.target.value)} required />
            <input className={input} type="password" placeholder="Password (min 8 chars)" value={password}
              onChange={(e) => setPassword(e.target.value)} required minLength={8} />

            {error && <div className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</div>}

            <button
              disabled={busy}
              className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
            >
              {busy ? "…" : mode === "signup" ? "Create workspace" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-muted">
          Kernel: <span className="font-mono">127.0.0.1:8000</span> · self-hosted · your data stays local
        </p>
      </div>
    </main>
  );
}
