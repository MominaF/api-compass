"use client";

import { Compass, LogOut } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { requireSupabase } from "@/lib/supabase";

export function AppHeader() {
  const { user } = useAuth();
  const [error, setError] = useState<string | null>(null);

  async function signOut() {
    setError(null);
    const result = await requireSupabase().auth.signOut();
    if (result.error) setError("Couldn't sign out. Try again.");
  }

  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4">
        <Link href="/dashboard" className="flex items-center gap-2">
          <Compass className="size-5 text-primary" aria-hidden />
          <span className="font-semibold tracking-tight">API COMPASS</span>
        </Link>
        <div className="flex min-w-0 items-center gap-3">
          {error && (
            <span role="alert" className="text-sm text-destructive">
              {error}
            </span>
          )}
          <span className="hidden truncate text-sm text-muted-foreground sm:block">{user?.email}</span>
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            <LogOut aria-hidden />
            Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}
