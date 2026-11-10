-- RLS test for fm_users. Run as postgres after schema.sql: psql -v ON_ERROR_STOP=1 -f test_users.sql
\set QUIET on
create or replace function pg_temp.as_user(email text) returns void language plpgsql as $$ begin
  if email is null then perform set_config('role', 'anon', false); perform set_config('request.jwt.claims', '', false);
  else perform set_config('role', 'authenticated', false); perform set_config('request.jwt.claims', json_build_object('email', email)::text, false); end if;
end $$;
create or replace function pg_temp.expect(label text, got bigint, want bigint) returns void language plpgsql as $$ begin
  if got is distinct from want then raise exception 'FAIL %: got %, want %', label, got, want; end if; raise notice 'ok  %', label; end $$;

-- signed out: no access at all
select pg_temp.as_user(null);
do $$ begin perform 1 from public.fm_users; raise exception 'FAIL anon could read fm_users'; exception when insufficient_privilege then raise notice 'ok  signed out cannot read'; end $$;
-- outsider (signed in with Google, not on the list): sees nothing, cannot add self
select pg_temp.as_user('stranger@gmail.com');
select pg_temp.expect('outsider sees 0 anglers', (select count(*) from public.fm_users), 0);
do $$ begin insert into public.fm_users values ('stranger@gmail.com', 'Me', 'admin'); raise exception 'FAIL outsider added self';
  exception when insufficient_privilege then raise notice 'ok  outsider cannot add self'; end $$;
-- Deercast's list must not let anyone in here
reset role; create table if not exists public.app_users (email text primary key, name text, role text);
insert into public.app_users values ('deer@gmail.com', 'Deer Only', 'admin') on conflict do nothing;
select pg_temp.as_user('deer@gmail.com');
select pg_temp.expect('Deercast-only user sees 0 anglers', (select count(*) from public.fm_users), 0);
-- member (Alex): sees all, cannot change anything
select pg_temp.as_user('akvoskuil94@gmail.com');
select pg_temp.expect('member sees 3 anglers', (select count(*) from public.fm_users), 3);
update public.fm_users set role = 'admin' where email = 'akvoskuil94@gmail.com';
select pg_temp.expect('member cannot promote self', (select count(*) from public.fm_users where role = 'admin'), 2);
delete from public.fm_users where email = 'jjpvoskuil@gmail.com';
select pg_temp.expect('member cannot delete', (select count(*) from public.fm_users), 3);
do $$ begin insert into public.fm_users values ('pal@gmail.com', 'Pal', 'member'); raise exception 'FAIL member added someone';
  exception when insufficient_privilege then raise notice 'ok  member cannot add'; end $$;
-- admin (Matt): add via upsert, rename, delete
select pg_temp.as_user('mattvoskuil@gmail.com');
insert into public.fm_users values ('pal@gmail.com', 'Pal', 'member') on conflict (email) do update set name = excluded.name;
insert into public.fm_users values ('pal@gmail.com', 'Pal R', 'member') on conflict (email) do update set name = excluded.name;
select pg_temp.expect('admin upsert add + rename', (select count(*) from public.fm_users where name = 'Pal R'), 1);
select pg_temp.as_user('pal@gmail.com');
select pg_temp.expect('new angler now sees the list', (select count(*) from public.fm_users), 4);
select pg_temp.as_user('jjpvoskuil@gmail.com');
delete from public.fm_users where email = 'pal@gmail.com';
select pg_temp.expect('admin delete', (select count(*) from public.fm_users), 3);
do $$ begin insert into public.fm_users values ('Caps@Gmail.com', 'x', 'member'); raise exception 'FAIL mixed-case email accepted';
  exception when check_violation then raise notice 'ok  emails must be lower case'; end $$;
reset role;
\echo ALL fm_users TESTS PASSED
