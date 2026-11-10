// Supabase project address + its PUBLISHABLE key. Both are meant to be public: on their own they unlock nothing —
// the row-level security rules in supabase/schema.sql decide who sees what.
// This app shares the Deercast Supabase project (its own fm_* tables, own allow-list fm_users, own RLS).
// Never put a "secret" / "service_role" key here (or anywhere in web/).
export const SUPABASE_URL = "https://gzxobsvhzscouehlrxeg.supabase.co";
export const SUPABASE_KEY = "sb_publishable_9EiV7Ezzy3jRCzHI5eszhQ_p0CgW5jo";
// Nolin River Lake — used for the automatic light/dark switch (sunrise/sunset) and forecasts.
export const LAKE = { lat: 37.33, lon: -86.17, tz: "America/Chicago", name: "Nolin River Lake" };
