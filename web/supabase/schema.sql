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
--   * Trips (fm_trips): one row per lure fished, like the old trip_log.csv. Every approved angler sees everyone's trips
--     (leaderboard, history, the score's learning); you add trips only as yourself, and edit/delete your own —
--     admins can edit/delete anyone's (fixing mistakes, imports).
--   * Lake water-quality readings (fm_water_quality) and frozen forecast scores (fm_score_freeze): shared, any
--     approved angler can add a new one; nobody can change or delete one (admins can delete).
--   * The tackle box (fm_lures) and saved lake spots (fm_spots) are shared by all anglers, as in the old app: any
--     approved angler can add, edit and remove them.
--   * (More tables — punch list, photos — are added here as each screen is rebuilt.)

create table if not exists public.fm_users (
  email text primary key check (email = lower(email)),
  name  text not null,
  role  text not null default 'member' check (role in ('member', 'admin'))
);

create table if not exists public.fm_trips (
  id text primary key,
  owner text not null,                 -- email of the angler who logged it
  trip_date text not null,             -- YYYY-MM-DD (lake-local)
  session_id text,
  data jsonb not null                  -- the full trip row (old trip_log.csv columns; conditions as an object)
);
create index if not exists fm_trips_date on public.fm_trips (trip_date);
create table if not exists public.fm_water_quality (
  observed_at text primary key,        -- USACE survey time, YYYY-MM-DDTHH:MM:SS (lake-local)
  data jsonb not null                  -- {water_temp_f, do_mg_l, do_saturation_pct, station}
);
create table if not exists public.fm_score_freeze (
  the_date text not null, segment_name text not null,
  data jsonb not null,                 -- {score, solunar_overlap, notes, breakdown, frozen_at}
  primary key (the_date, segment_name)
);

create table if not exists public.fm_lures (
  id text primary key,                 -- item_id
  data jsonb not null                  -- the old lure_inventory.csv row (brand, description, category, quantity, …)
);
create table if not exists public.fm_spots (
  id text primary key,                 -- spot_id
  data jsonb not null                  -- the old lake_spots.csv row (name, lat, lon, location_type, depths, notes, …)
);

create or replace function public.fm_me() returns text language sql stable as $$ select lower(coalesce(auth.jwt() ->> 'email', '')) $$;
create or replace function public.fm_is_approved() returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.fm_users where email = public.fm_me()) $$;
create or replace function public.fm_is_admin() returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.fm_users where email = public.fm_me() and role = 'admin') $$;
revoke all on function public.fm_is_approved(), public.fm_is_admin() from public, anon;
grant execute on function public.fm_me(), public.fm_is_approved(), public.fm_is_admin() to authenticated;

do $$ declare t text; begin
  foreach t in array array['fm_users','fm_trips','fm_water_quality','fm_score_freeze','fm_lures','fm_spots'] loop
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

create policy "fm trips read"   on public.fm_trips for select to authenticated using (public.fm_is_approved());
create policy "fm trips add"    on public.fm_trips for insert to authenticated with check (public.fm_is_approved() and (owner = public.fm_me() or public.fm_is_admin()));
create policy "fm trips edit"   on public.fm_trips for update to authenticated using (public.fm_is_approved() and (owner = public.fm_me() or public.fm_is_admin()))
  with check (owner = public.fm_me() or public.fm_is_admin());
create policy "fm trips delete" on public.fm_trips for delete to authenticated using (public.fm_is_approved() and (owner = public.fm_me() or public.fm_is_admin()));

create policy "fm wq read"   on public.fm_water_quality for select to authenticated using (public.fm_is_approved());
create policy "fm wq add"    on public.fm_water_quality for insert to authenticated with check (public.fm_is_approved());
create policy "fm wq delete" on public.fm_water_quality for delete to authenticated using (public.fm_is_admin());
create policy "fm freeze read"   on public.fm_score_freeze for select to authenticated using (public.fm_is_approved());
create policy "fm freeze add"    on public.fm_score_freeze for insert to authenticated with check (public.fm_is_approved());
create policy "fm freeze delete" on public.fm_score_freeze for delete to authenticated using (public.fm_is_admin());

create policy "fm lures shared" on public.fm_lures for all to authenticated using (public.fm_is_approved()) with check (public.fm_is_approved());
create policy "fm spots shared" on public.fm_spots for all to authenticated using (public.fm_is_approved()) with check (public.fm_is_approved());

-- the first anglers (re-running keeps any name/role changes made in the app)
insert into public.fm_users (email, name, role) values
  ('jjpvoskuil@gmail.com', 'John', 'admin'),
  ('mattvoskuil@gmail.com', 'Matthew', 'admin'),
  ('akvoskuil94@gmail.com', 'Alex', 'member')
on conflict (email) do nothing;
