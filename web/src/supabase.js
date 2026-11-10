import { createClient } from "@supabase/supabase-js";
import { SUPABASE_URL, SUPABASE_KEY } from "./config.js";

export const configured = !SUPABASE_KEY.startsWith("PASTE");
// storageKey is this app's own, so signing out here doesn't sign you out of Deercast (same github.io address, same project).
export const supabase = configured
  ? createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce", storageKey: "fm-auth" } })
  : null;
