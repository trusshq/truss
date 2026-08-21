"use client";

/* Truss theme system.
 *
 * Default is MONOCHROME — pure black & white. Color is opt-in: the user picks
 * an accent preset or a custom hex, and chooses light / dark / system.
 * Everything persists to localStorage and applies via CSS variables on <html>,
 * so it works across the landing page, login, and dashboard with zero flash.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark" | "system";
export type Density = "comfortable" | "compact";
export type Radius = "sharp" | "soft" | "rounded";

export interface ThemeState {
  mode: ThemeMode;
  /** "mono" = black & white (default), or a preset id, or a raw hex string */
  accent: string;
  density: Density;
  radius: Radius;
}

export const DEFAULT_THEME: ThemeState = {
  mode: "dark",
  accent: "mono",
  density: "comfortable",
  radius: "soft",
};

/** Curated accent presets. "mono" keeps everything black & white. */
export const ACCENT_PRESETS: { id: string; label: string; value: string }[] = [
  { id: "mono", label: "Mono", value: "" },
  { id: "amber", label: "Amber", value: "#e8a33d" },
  { id: "blue", label: "Blue", value: "#4f8cff" },
  { id: "green", label: "Green", value: "#34d399" },
  { id: "red", label: "Red", value: "#f87171" },
  { id: "violet", label: "Violet", value: "#a78bfa" },
  { id: "cyan", label: "Cyan", value: "#22d3ee" },
];

const STORAGE_KEY = "***";

interface ThemeContextValue {
  theme: ThemeState;
  resolvedMode: "light" | "dark";
  setMode: (m: ThemeMode) => void;
  setAccent: (a: string) => void;
  setDensity: (d: Density) => void;
  setRadius: (r: Radius) => void;
  reset: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function loadTheme(): ThemeState {
  if (typeof window === "undefined") return DEFAULT_THEME;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THEME;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_THEME, ...parsed };
  } catch {
    return DEFAULT_THEME;
  }
}

/** Resolve an accent token to a concrete color. mono → inherit foreground. */
function accentColor(accent: string): string | null {
  if (accent === "mono") return null; // use foreground
  const preset = ACCENT_PRESETS.find((p) => p.id === accent);
  if (preset) return preset.value || null;
  if (/^#[0-9a-fA-F]{3,8}$/.test(accent)) return accent;
  return null;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeState>(DEFAULT_THEME);
  const [systemDark, setSystemDark] = useState(true);
  const [mounted, setMounted] = useState(false);

  // hydrate from storage + listen to OS preference
  useEffect(() => {
    setTheme(loadTheme());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    setMounted(true);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const resolvedMode: "light" | "dark" =
    theme.mode === "system" ? (systemDark ? "dark" : "light") : theme.mode;

  // apply to <html>
  useEffect(() => {
    if (!mounted) return;
    const root = document.documentElement;
    root.setAttribute("data-theme", resolvedMode);
    root.setAttribute("data-density", theme.density);
    root.setAttribute("data-radius", theme.radius);

    const color = accentColor(theme.accent);
    if (color) {
      root.style.setProperty("--accent", color);
      root.style.setProperty("--accent-is-mono", "0");
    } else {
      // monochrome: accent inherits the foreground color
      root.style.removeProperty("--accent");
      root.style.setProperty("--accent-is-mono", "1");
    }

    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(theme));
    } catch {
      /* storage unavailable */
    }
  }, [theme, resolvedMode, mounted]);

  const setMode = useCallback((m: ThemeMode) => setTheme((t) => ({ ...t, mode: m })), []);
  const setAccent = useCallback((a: string) => setTheme((t) => ({ ...t, accent: a })), []);
  const setDensity = useCallback((d: Density) => setTheme((t) => ({ ...t, density: d })), []);
  const setRadius = useCallback((r: Radius) => setTheme((t) => ({ ...t, radius: r })), []);
  const reset = useCallback(() => setTheme(DEFAULT_THEME), []);

  const value = useMemo(
    () => ({ theme, resolvedMode, setMode, setAccent, setDensity, setRadius, reset }),
    [theme, resolvedMode, setMode, setAccent, setDensity, setRadius, reset]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
