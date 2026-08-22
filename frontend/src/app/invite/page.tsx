"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, checkAuth, setToken, type AuthResponse, type InvitePublic, type Me } from "@/lib/api";

function InviteInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";

  const [invite, setInvite] = useState<InvitePublic | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  useEffect(() => {
    checkAuth().then(setMe);
    if (!token) {
      setError("No invite token in the link.");
      return;
    }
    api<InvitePublic>(`/api/workspace/invites/by-token/${token}`, { auth: false })
      .then(setInvite)
      .catch((e) => {
        const d = (e as { detail?: unknown }).detail;
        setError(typeof d === "string" ? d : "This invite is invalid, expired, or already used.");
      });
  }, [token]);

  const isMatchingUser = me !== null && invite !== null && me.email === invite.email;

  async function accept(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body: Record<string, string> = { token };
      if (!isMatchingUser) {
        body.password = password;
        if (fullName) body.full_name = fullName;
      }
      const res = await api<AuthResponse>("/api/workspace/invites/accept", {
        auth: false,
        method: "POST",
        body,
      });
      setToken(res.access_token);
      router.replace("/dashboard");
    } catch (err) {
      const d = (err as { detail?: unknown }).detail;
      setError(typeof d === "string" ? d : "Could not accept this invite.");
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-accent";

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="text-2xl">🏗️</span>
          <span className="text-lg font-bold">Truss</span>
        </div>

        <div className="rounded-2xl border border-border bg-card p-6">
          {error && !invite && (
            <div className="text-center">
              <p className="text-sm text-danger">{error}</p>
              <button
                onClick={() => router.replace("/login")}
                className="mt-4 rounded-lg border border-border px-4 py-1.5 text-sm text-muted transition hover:border-border-strong hover:text-foreground"
              >
                Back to sign in
              </button>
            </div>
          )}

          {invite && (
            <>
              <h1 className="text-center text-lg font-bold">You&apos;re invited 👋</h1>
              <p className="mt-2 text-center text-sm text-muted">
                Join <span className="font-semibold text-foreground">{invite.workspace_name}</span>{" "}
                (<span className="font-mono text-accent">{invite.workspace_slug}</span>) as{" "}
                <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold uppercase text-accent">
                  {invite.role}
                </span>
              </p>
              <p className="mt-1 text-center text-xs text-faint">
                Invite for {invite.email} · expires {new Date(invite.expires_at).toLocaleDateString()}
              </p>

              {isMatchingUser ? (
                <div className="mt-5 text-center">
                  <p className="text-xs text-muted">
                    You&apos;re signed in as <span className="font-medium text-foreground">{me.email}</span> — this
                    invite matches your account.
                  </p>
                  <button
                    onClick={(e) => accept(e as unknown as React.FormEvent)}
                    disabled={busy}
                    className="mt-3 w-full rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
                  >
                    {busy ? "Joining…" : "Accept invite & join workspace"}
                  </button>
                </div>
              ) : (
                <form onSubmit={accept} className="mt-5 space-y-3">
                  {me && (
                    <p className="rounded-lg bg-card-2 px-3 py-2 text-[11px] text-muted">
                      You&apos;re signed in as {me.email}, but this invite is for{" "}
                      <span className="font-medium text-foreground">{invite.email}</span>. Accepting will create a
                      new account and switch you to it.
                    </p>
                  )}
                  <label className="block text-xs">
                    <span className="mb-1 block text-muted">Full name</span>
                    <input className={inputCls} value={fullName} placeholder="Your name"
                      onChange={(e) => setFullName(e.target.value)} />
                  </label>
                  <label className="block text-xs">
                    <span className="mb-1 block text-muted">Create a password (min 8 characters)</span>
                    <input className={inputCls} type="password" required minLength={8} value={password}
                      onChange={(e) => setPassword(e.target.value)} />
                  </label>
                  {error && <p className="text-xs text-danger">{error}</p>}
                  <button
                    disabled={busy || password.length < 8}
                    className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent transition hover:brightness-110 disabled:opacity-50"
                  >
                    {busy ? "Joining…" : "Create account & join"}
                  </button>
                </form>
              )}
            </>
          )}

          {!invite && !error && (
            <div className="flex justify-center py-8">
              <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}
        </div>

        <p className="mt-4 text-center text-xs text-muted">
          Truss — the open-source business OS.{" "}
          <a href="/login" className="text-accent underline-offset-2 hover:underline">
            Sign in instead
          </a>
        </p>
      </div>
    </main>
  );
}

export default function InvitePage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center">
          <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </main>
      }
    >
      <InviteInner />
    </Suspense>
  );
}
