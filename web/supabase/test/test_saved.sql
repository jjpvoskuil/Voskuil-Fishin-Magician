-- RLS tests for fm_saved (saved custom boards / reports). Run after schema.sql + test_users.sql setup.
\set QUIET on
create or replace function pg_temp.as_user(email text) returns void language plpgsql as $$ begin
  if email is null then perform set_config('role', 'anon', false); perform set_config('request.jwt.claims', '', false);
  else perform set_config('role', 'authenticated', false); perform set_config('request.jwt.claims', json_build_object('email', email)::text, false); end if;
end $$;
create or replace function pg_temp.expect(label text, got bigint, want bigint) returns void language plpgsql as $$ begin
  if got is distinct from want then raise exception 'FAIL %: got %, want %', label, got, want; end if; raise notice 'ok  %', label; end $$;
reset role; delete from public.fm_saved;

select pg_temp.as_user('jjpvoskuil@gmail.com');
insert into public.fm_saved (id, owner, kind, data) values ('b1','jjpvoskuil@gmail.com','board','{"title":"Jerkbait lbs"}') on conflict (id) do update set data = excluded.data;
insert into public.fm_saved (id, owner, kind, data) values ('b1','jjpvoskuil@gmail.com','board','{"title":"Jerkbait lbs v2"}') on conflict (id) do update set data = excluded.data;
select pg_temp.expect('angler saves and re-saves own board', (select count(*) from public.fm_saved where data->>'title' = 'Jerkbait lbs v2'), 1);
do $$ begin insert into public.fm_saved (id, owner, kind, data) values ('b2','akvoskuil94@gmail.com','board','{}'); raise exception 'FAIL saved as someone else';
  exception when insufficient_privilege then raise notice 'ok  cannot save as someone else'; end $$;
do $$ begin insert into public.fm_saved (id, owner, kind, data) values ('b3','jjpvoskuil@gmail.com','junk','{}'); raise exception 'FAIL bad kind';
  exception when check_violation then raise notice 'ok  kind must be board or report'; end $$;
select pg_temp.as_user('akvoskuil94@gmail.com');
insert into public.fm_saved (id, owner, kind, data) values ('r1','akvoskuil94@gmail.com','report','{}');
select pg_temp.expect('member sees only own saved items', (select count(*) from public.fm_saved), 1);
update public.fm_saved set data = '{"title":"hacked"}' where id = 'b1';
delete from public.fm_saved where id = 'b1';
select pg_temp.as_user('mattvoskuil@gmail.com');
select pg_temp.expect('admin does not see others'' saved items', (select count(*) from public.fm_saved), 0);
select pg_temp.as_user('jjpvoskuil@gmail.com');
select pg_temp.expect('another angler could not change or delete it', (select count(*) from public.fm_saved where id = 'b1' and data->>'title' = 'Jerkbait lbs v2'), 1);
delete from public.fm_saved where id = 'b1';
select pg_temp.expect('owner deletes own', (select count(*) from public.fm_saved where id = 'b1'), 0);
select pg_temp.as_user('stranger@gmail.com');
select pg_temp.expect('outsider sees nothing', (select count(*) from public.fm_saved), 0);
do $$ begin insert into public.fm_saved (id, owner, kind, data) values ('x','stranger@gmail.com','board','{}'); raise exception 'FAIL outsider saved';
  exception when insufficient_privilege then raise notice 'ok  outsider cannot save'; end $$;
select pg_temp.as_user(null);
do $$ begin perform count(*) from public.fm_saved; raise exception 'FAIL signed-out read';
  exception when insufficient_privilege then raise notice 'ok  signed out cannot read'; end $$;
reset role;
