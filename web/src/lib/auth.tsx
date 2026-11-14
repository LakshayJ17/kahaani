"use client";

// Sign-in. In production this is Google through Supabase Auth; the API checks the token.
// For local development without Supabase, the API can allow a simple named "dev" sign-in.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { API_BASE } from "./api-base";

export interface Me {
  id: string;
  email: string | null;
  name: string | null;
  consent: boolean;
  booksToday: number;
  booksPerDay: number;
  saved: number;
  maxSaved: number;
}

interface Config {
  supabaseUrl: string | null;
  supabaseAnonKey: string | null;
  devAuth: boolean;
}

interface AuthState {
  ready: boolean;
  me: Me | null;
  /** True after "sign in" is clicked, while the browser heads to Google. */
  signingIn: boolean;
  available: boolean; // false when sign-in isn't configured on this server
  /** Sign in, then land on `next` (the book studio by default). */
  signIn: (next?: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  headers: () => Promise<Record<string, string>>;
}

const DEV_KEY = "kahaani-dev-user";
const AuthContext = createContext<AuthState | null>(null);

let supabase: SupabaseClient | null = null;
let config: Config | null = null;

async function loadConfig(): Promise<Config> {
  if (config) return config;
  const res = await fetch(`${API_BASE}/api/config`);
  config = (await res.json()) as Config;
  if (config.supabaseUrl && config.supabaseAnonKey && !supabase) {
    supabase = createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth: {
        persistSession: true,
        detectSessionInUrl: true,
        flowType: "pkce",
      },
    });
  }
  return config;
}

export async function authHeaders(): Promise<Record<string, string>> {
  const cfg = await loadConfig();
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  if (cfg.devAuth) {
    let name: string | null = null;
    try {
      name = localStorage.getItem(DEV_KEY);
    } catch {}
    return name ? { "X-Dev-User": name } : {};
  }
  return {};
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [available, setAvailable] = useState(true);
  const [signingIn, setSigningIn] = useState(false);

  const refresh = useCallback(async () => {
    const headers = await authHeaders();
    if (!Object.keys(headers).length) {
      setMe(null);
      return;
    }
    const res = await fetch(`${API_BASE}/api/me`, { headers });
    setMe(res.ok ? ((await res.json()) as Me) : null);
  }, []);

  useEffect(() => {
    // Back from Google with a sign-in code: say so while the session is set up.
    const returning = new URLSearchParams(window.location.search).has("code");
    if (returning) queueMicrotask(() => setSigningIn(true));
    // Coming back with the browser's Back button instead of signing in.
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted) setSigningIn(false);
    };
    window.addEventListener("pageshow", onShow);

    let unsubscribe = () => {};
    loadConfig()
      .then(async (cfg) => {
        setAvailable(!!supabase || cfg.devAuth);
        if (supabase) {
          const { data } = supabase.auth.onAuthStateChange(() => {
            refresh();
          });
          unsubscribe = () => data.subscription.unsubscribe();
        }
        await refresh();
      })
      .catch(() => setAvailable(false))
      .finally(() => {
        setReady(true);
        setSigningIn(false);
      });
    return () => {
      unsubscribe();
      window.removeEventListener("pageshow", onShow);
    };
  }, [refresh]);

  const signIn = useCallback(
    async (next: string = "/create/") => {
      setSigningIn(true);
      const cfg = await loadConfig().catch(() => null);
      if (!cfg) {
        setSigningIn(false);
        return;
      }
      if (supabase) {
        const { error } = await supabase.auth.signInWithOAuth({
          provider: "google",
          options: { redirectTo: `${window.location.origin}${next}` },
        });
        // On success the page is leaving for Google, so keep showing the busy state.
        if (error) setSigningIn(false);
        return;
      }
      setSigningIn(false);
      if (cfg.devAuth) {
        const name = window
          .prompt("Development sign-in: type any name")
          ?.trim();
        if (!name) return;
        try {
          localStorage.setItem(
            DEV_KEY,
            name.toLowerCase().replace(/[^a-z0-9]/g, ""),
          );
        } catch {}
        await refresh();
        if (window.location.pathname !== next) window.location.assign(next);
      }
    },
    [refresh],
  );

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut();
    try {
      localStorage.removeItem(DEV_KEY);
      sessionStorage.clear();
    } catch {}
    setMe(null);
  }, []);

  const value = useMemo(
    () => ({
      ready,
      me,
      signingIn,
      available,
      signIn,
      signOut,
      refresh,
      headers: authHeaders,
    }),
    [ready, me, signingIn, available, signIn, signOut, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
