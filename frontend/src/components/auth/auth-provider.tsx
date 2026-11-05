"use client";

import type { User } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { getSupabase } from "@/lib/supabase";

type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: User };

const AuthContext = createContext<AuthState>({ status: "loading", user: null });

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>(() =>
    getSupabase() ? { status: "loading", user: null } : { status: "anonymous", user: null },
  );
  const previousUserId = useRef<string | null>(null);

  useEffect(() => {
    const supabase = getSupabase();
    if (!supabase) return;
    // Fires immediately with the stored session, then on every sign-in, sign-out and refresh.
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      const user = session?.user ?? null;
      // Never let one user's cached data be shown to the next user on this browser.
      if (previousUserId.current !== (user?.id ?? null)) {
        if (previousUserId.current) queryClient.clear();
        previousUserId.current = user?.id ?? null;
      }
      setState(user ? { status: "authenticated", user } : { status: "anonymous", user: null });
    });
    return () => data.subscription.unsubscribe();
  }, [queryClient]);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}
