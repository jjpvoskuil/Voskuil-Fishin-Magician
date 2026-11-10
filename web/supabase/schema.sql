-- Fishin Magician — database setup. Paste into Supabase (Deercast project) → SQL Editor → Run. Safe to re-run.
-- Contains NO trip data. Who can see or change what is enforced here (row-level security), not in the web page.
--
-- This app lives in the Deercast Supabase project, but only in its own fm_* tables and fm_* functions.
-- It never reads or changes Deercast's tables (app_users, grounds, hunts, …), and Deercast's rules don't apply here:
-- being on Deercast's list does NOT let anyone into Fishin Magician, and vice versa.
--
-- Rules:
--   * Only emails in fm_users are approved. Anyone else can finish Google sign-in but sees and saves nothing.
--   * Admins (role 'admin') add, rename and remove anglers.
--   * (More tables — trips, lures, spots, punch list, photos — are added here as each screen is rebuilt.)

create table if not exists public.fm_users (
  email text primary key check (email = lower(email)),
  name  text not null,
  role  text not null default 'member' check (role in ('member', 'admin'))
);

create or replace function public.fm_me() returns text language sql stable as $$ select lower(coalesce(auth.jwt() ->> 'email', '')) $$;
create or replace function public.fm_is_approved() returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.fm_users where email = public.fm_me()) $$;
create or replace function public.fm_is_admin() returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.fm_users where email = public.fm_me() and role = 'admin') $$;
revoke all on function public.fm_is_approved(), public.fm_is_admin() from public, anon;
grant execute on function public.fm_me(), public.fm_is_approved(), public.fm_is_admin() to authenticated;

do $$ declare t text; begin
  foreach t in array array['fm_users'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;

-- drop every existing policy on these tables, then create the current set
do $$ declare p record; begin
  for p in select policyname, tablename from pg_policies where schemaname = 'public' and tablename like 'fm\_%' loop
    execute format('drop policy %I on public.%I', p.policyname, p.tablename);
  end loop;
end $$;

-- everyone approved sees the angler list (names on trips/leaderboard); admins change it.
-- (upsert = insert-or-update also has to pass the read rule on the new row: admins are approved, so it does)
create policy "fm users read"  on public.fm_users for select to authenticated using (email = public.fm_me() or public.fm_is_approved());
create policy "fm users admin" on public.fm_users for all    to authenticated using (public.fm_is_admin()) with check (public.fm_is_admin());

-- the first anglers (re-running keeps any name/role changes made in the app)
insert into public.fm_users (email, name, role) values
  ('jjpvoskuil@gmail.com', 'John', 'admin'),
  ('mattvoskuil@gmail.com', 'Matthew', 'admin'),
  ('akvoskuil94@gmail.com', 'Alex', 'member')
on conflict (email) do nothing;
