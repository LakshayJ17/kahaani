"use client";

// Sign-in. In production this is Google through Supabase Auth; the API checks the token.
// For local development without Supabase, the API can allow a simple named "dev" sign-in.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
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
  available: boolean; // false when sign-in isn't configured on this server
  signIn: () => Promise<void>;
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
      auth: { persistSession: true, detectSessionInUrl: true, flowType: "pkce" },
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
      .finally(() => setReady(true));
    return () => unsubscribe();
  }, [refresh]);

  const signIn = useCallback(async () => {
    const cfg = await loadConfig();
    if (supabase) {
      await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}${window.location.pathname}` },
      });
      return;
    }
    if (cfg.devAuth) {
      const name = window.prompt("Development sign-in: type any name")?.trim();
      if (!name) return;
      try {
        localStorage.setItem(DEV_KEY, name.toLowerCase().replace(/[^a-z0-9]/g, ""));
      } catch {}
      await refresh();
    }
  }, [refresh]);

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut();
    try {
      localStorage.removeItem(DEV_KEY);
      sessionStorage.clear();
    } catch {}
    setMe(null);
  }, []);

  const value = useMemo(
    () => ({ ready, me, available, signIn, signOut, refresh, headers: authHeaders }),
    [ready, me, available, signIn, signOut, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
