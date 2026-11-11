-- RLS tests for fm_trips, fm_water_quality, fm_score_freeze. Run after schema.sql + test_users.sql setup.
\set QUIET on
create or replace function pg_temp.as_user(email text) returns void language plpgsql as $$ begin
  if email is null then perform set_config('role', 'anon', false); perform set_config('request.jwt.claims', '', false);
  else perform set_config('role', 'authenticated', false); perform set_config('request.jwt.claims', json_build_object('email', email)::text, false); end if;
end $$;
create or replace function pg_temp.expect(label text, got bigint, want bigint) returns void language plpgsql as $$ begin
  if got is distinct from want then raise exception 'FAIL %: got %, want %', label, got, want; end if; raise notice 'ok  %', label; end $$;
reset role; delete from public.fm_trips; delete from public.fm_water_quality; delete from public.fm_score_freeze;

-- John and Alex each log a trip (upsert, like the app does)
select pg_temp.as_user('jjpvoskuil@gmail.com');
insert into public.fm_trips values ('t1','jjpvoskuil@gmail.com','2026-11-10',null,'{"fish_caught":"2"}') on conflict (id) do update set data = excluded.data;
select pg_temp.as_user('akvoskuil94@gmail.com');
insert into public.fm_trips values ('t2','akvoskuil94@gmail.com','2026-11-10',null,'{"fish_caught":"1"}') on conflict (id) do update set data = excluded.data;
do $$ begin insert into public.fm_trips values ('t3','jjpvoskuil@gmail.com','2026-11-10',null,'{}'); raise exception 'FAIL member logged a trip as someone else';
  exception when insufficient_privilege then raise notice 'ok  member cannot log a trip as someone else'; end $$;
select pg_temp.expect('member sees everyone''s trips', (select count(*) from public.fm_trips), 2);
update public.fm_trips set data = '{"fish_caught":"9"}' where id = 't1';
select pg_temp.expect('member cannot edit another''s trip', (select count(*) from public.fm_trips where data->>'fish_caught' = '9'), 0);
delete from public.fm_trips where id = 't1';
select pg_temp.expect('member cannot delete another''s trip', (select count(*) from public.fm_trips), 2);
update public.fm_trips set data = '{"fish_caught":"3"}' where id = 't2';
select pg_temp.expect('member edits own trip', (select count(*) from public.fm_trips where id = 't2' and data->>'fish_caught' = '3'), 1);
do $$ begin update public.fm_trips set owner = 'jjpvoskuil@gmail.com' where id = 't2'; raise exception 'FAIL member gave a trip away';
  exception when insufficient_privilege then raise notice 'ok  member cannot hand a trip to someone else'; end $$;
-- admin (Matt) fixes and imports anyone's trips
select pg_temp.as_user('mattvoskuil@gmail.com');
update public.fm_trips set data = '{"fish_caught":"4"}' where id = 't2';
select pg_temp.expect('admin edits anyone''s trip', (select count(*) from public.fm_trips where data->>'fish_caught' = '4'), 1);
insert into public.fm_trips values ('imp1','akvoskuil94@gmail.com','2026-08-01',null,'{}') on conflict (id) do update set data = excluded.data;
select pg_temp.expect('admin imports a trip for someone else', (select count(*) from public.fm_trips), 3);
-- outsiders, signed-out and Deercast-only people see and change nothing
select pg_temp.as_user('stranger@gmail.com');
select pg_temp.expect('outsider sees no trips', (select count(*) from public.fm_trips), 0);
do $$ begin insert into public.fm_trips values ('x','stranger@gmail.com','2026-11-10',null,'{}'); raise exception 'FAIL outsider logged a trip';
  exception when insufficient_privilege then raise notice 'ok  outsider cannot log trips'; end $$;
select pg_temp.as_user('deer@gmail.com');
select pg_temp.expect('Deercast-only user sees no trips', (select count(*) from public.fm_trips), 0);
select pg_temp.expect('Deercast-only user sees no freezes', (select count(*) from public.fm_score_freeze), 0);
select pg_temp.as_user(null);
do $$ begin perform 1 from public.fm_trips; raise exception 'FAIL anon read trips'; exception when insufficient_privilege then raise notice 'ok  signed out cannot read trips'; end $$;

-- water quality + score freezes: add-only for anglers ("insert … on conflict do nothing", like the app)
select pg_temp.as_user('akvoskuil94@gmail.com');
insert into public.fm_water_quality values ('2026-10-20T10:15:00','{"do_mg_l":9.48}') on conflict do nothing;
insert into public.fm_water_quality values ('2026-10-20T10:15:00','{"do_mg_l":1}') on conflict do nothing;
select pg_temp.expect('reading added once, never overwritten', (select count(*) from public.fm_water_quality where data->>'do_mg_l' = '9.48'), 1);
insert into public.fm_score_freeze values ('2026-11-10','Dawn','{"score":7.0}') on conflict do nothing;
insert into public.fm_score_freeze values ('2026-11-10','Dawn','{"score":2.0}') on conflict do nothing;
select pg_temp.expect('frozen score kept', (select count(*) from public.fm_score_freeze where data->>'score' = '7.0'), 1);
update public.fm_score_freeze set data = '{"score":1}';
delete from public.fm_score_freeze; delete from public.fm_water_quality;
select pg_temp.expect('member cannot change/delete a frozen score', (select count(*) from public.fm_score_freeze where data->>'score' = '7.0'), 1);
select pg_temp.expect('member cannot delete readings', (select count(*) from public.fm_water_quality), 1);
select pg_temp.as_user('jjpvoskuil@gmail.com');
delete from public.fm_score_freeze;
select pg_temp.expect('admin can delete a frozen score', (select count(*) from public.fm_score_freeze), 0);
-- tackle box + spots: shared by all approved anglers, invisible to everyone else
select pg_temp.as_user('akvoskuil94@gmail.com');
insert into public.fm_lures values ('l1','{"brand":"Z-Man"}') on conflict (id) do update set data = excluded.data;
insert into public.fm_spots values ('s1','{"name":"Stripe Island Point"}') on conflict (id) do update set data = excluded.data;
select pg_temp.as_user('jjpvoskuil@gmail.com');
update public.fm_lures set data = '{"brand":"Z-Man","quantity":"2"}' where id = 'l1';
select pg_temp.expect('anglers share and edit the tackle box', (select count(*) from public.fm_lures where data->>'quantity' = '2'), 1);
select pg_temp.as_user('stranger@gmail.com');
select pg_temp.expect('outsider sees no lures', (select count(*) from public.fm_lures), 0);
select pg_temp.expect('outsider sees no spots', (select count(*) from public.fm_spots), 0);
do $$ begin insert into public.fm_spots values ('x','{}'); raise exception 'FAIL outsider added a spot';
  exception when insufficient_privilege then raise notice 'ok  outsider cannot add spots'; end $$;
select pg_temp.as_user('deer@gmail.com');
select pg_temp.expect('Deercast-only user sees no lures', (select count(*) from public.fm_lures), 0);
select pg_temp.as_user('mattvoskuil@gmail.com');
delete from public.fm_lures; delete from public.fm_spots;
select pg_temp.expect('angler removes from the shared tackle box', (select count(*) from public.fm_lures), 0);
reset role;
\echo ALL shared-table TESTS PASSED
