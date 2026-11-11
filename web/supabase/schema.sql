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
--   * Saved custom boards and reports (fm_saved): private to the angler who saved them.
--   * Punch list (fm_punch): every approved angler sees it and adds to it; admins edit/close/delete any item, others
--     their own. Item numbers come from fm_next_task_no() and are never reused, even after a delete.
--   * Tackle-box photos live in the private storage bucket fm-lures (approved anglers only).

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

create table if not exists public.fm_saved (
  id text primary key,
  owner text not null,                 -- email of the angler who saved it (only they see it)
  kind text not null check (kind in ('board', 'report')),
  data jsonb not null,                 -- {title, spec, …} — a saved custom leaderboard or report
  created_at timestamptz not null default now()
);

create table if not exists public.fm_punch (
  task_no integer primary key,         -- the "#98" people refer to; never reused
  owner text not null,                 -- email of who added it
  data jsonb not null                  -- {description, page, status, priority, author, created_at, updated_at, completed_at}
);
create table if not exists public.fm_punch_counter (
  id boolean primary key default true check (id),   -- one row
  next_no integer not null
);

create or replace function public.fm_me() returns text language sql stable as $$ select lower(coalesce(auth.jwt() ->> 'email', '')) $$;
create or replace function public.fm_is_approved() returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.fm_users where email = public.fm_me()) $$;
create or replace function public.fm_is_admin() returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.fm_users where email = public.fm_me() and role = 'admin') $$;
revoke all on function public.fm_is_approved(), public.fm_is_admin() from public, anon;
grant execute on function public.fm_me(), public.fm_is_approved(), public.fm_is_admin() to authenticated;

-- the next punch-list number (approved anglers only); counts up past any number ever used, so none is reused
create or replace function public.fm_next_task_no() returns integer language plpgsql security definer set search_path = public as $$
declare n integer; top integer;
begin
  if not public.fm_is_approved() then raise exception 'not approved' using errcode = '42501'; end if;
  select coalesce(max(task_no), 0) + 1 into top from public.fm_punch;
  insert into public.fm_punch_counter (id, next_no) values (true, top) on conflict (id) do nothing;
  update public.fm_punch_counter set next_no = greatest(next_no, top) + 1 where id returning next_no - 1 into n;
  return n;
end $$;
revoke all on function public.fm_next_task_no() from public, anon;
grant execute on function public.fm_next_task_no() to authenticated;
alter table public.fm_punch_counter enable row level security;
revoke all on public.fm_punch_counter from anon, authenticated;

do $$ declare t text; begin
  foreach t in array array['fm_users','fm_trips','fm_water_quality','fm_score_freeze','fm_lures','fm_spots','fm_saved','fm_punch'] loop
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

create policy "fm punch read"   on public.fm_punch for select to authenticated using (public.fm_is_approved());
create policy "fm punch add"    on public.fm_punch for insert to authenticated with check (public.fm_is_approved() and (owner = public.fm_me() or public.fm_is_admin()));
create policy "fm punch edit"   on public.fm_punch for update to authenticated using (public.fm_is_approved() and (owner = public.fm_me() or public.fm_is_admin()))
  with check (owner = public.fm_me() or public.fm_is_admin());
create policy "fm punch delete" on public.fm_punch for delete to authenticated using (public.fm_is_approved() and (owner = public.fm_me() or public.fm_is_admin()));

-- saved boards/reports: each angler sees and changes only their own
create policy "fm saved own" on public.fm_saved for all to authenticated
  using (public.fm_is_approved() and owner = public.fm_me()) with check (public.fm_is_approved() and owner = public.fm_me());

create policy "fm lures shared" on public.fm_lures for all to authenticated using (public.fm_is_approved()) with check (public.fm_is_approved());
create policy "fm spots shared" on public.fm_spots for all to authenticated using (public.fm_is_approved()) with check (public.fm_is_approved());

-- tackle-box photos: private bucket "fm-lures" (lures/<item_id>-<random>.jpg + _thumb.jpg); approved anglers only.
-- Wrapped so the local test database (no Supabase storage schema) can still run this file.
do $$ declare p record; begin
  if exists (select 1 from information_schema.schemata where schema_name = 'storage') then
    insert into storage.buckets (id, name, public) values ('fm-lures', 'fm-lures', false) on conflict (id) do nothing;
    for p in select policyname from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname like 'fm-lures %' loop
      execute format('drop policy %I on storage.objects', p.policyname);
    end loop;
    execute $q$create policy "fm-lures read"   on storage.objects for select to authenticated using (bucket_id = 'fm-lures' and public.fm_is_approved())$q$;
    execute $q$create policy "fm-lures add"    on storage.objects for insert to authenticated with check (bucket_id = 'fm-lures' and public.fm_is_approved())$q$;
    execute $q$create policy "fm-lures change" on storage.objects for update to authenticated using (bucket_id = 'fm-lures' and public.fm_is_approved()) with check (bucket_id = 'fm-lures' and public.fm_is_approved())$q$;
    execute $q$create policy "fm-lures remove" on storage.objects for delete to authenticated using (bucket_id = 'fm-lures' and public.fm_is_approved())$q$;
  end if;
end $$;

-- the first anglers (re-running keeps any name/role changes made in the app)
insert into public.fm_users (email, name, role) values
  ('jjpvoskuil@gmail.com', 'John', 'admin'),
  ('mattvoskuil@gmail.com', 'Matthew', 'admin'),
  ('akvoskuil94@gmail.com', 'Alex', 'member')
on conflict (email) do nothing;
