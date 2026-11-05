import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

let client: SupabaseClient | null = null;

/** The browser's Supabase client, or null when the environment isn't configured. */
export function getSupabase(): SupabaseClient | null {
  if (!url || !publishableKey) return null;
  client ??= createClient(url, publishableKey);
  return client;
}

export function requireSupabase(): SupabaseClient {
  const supabase = getSupabase();
  if (!supabase) {
    throw new Error("Sign-in isn't configured. Add the Supabase settings to frontend/.env.local.");
  }
  return supabase;
}
