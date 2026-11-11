-- RLS tests for fm_punch + fm_next_task_no(). Run after schema.sql + test_users.sql setup.
\set QUIET on
create or replace function pg_temp.as_user(email text) returns void language plpgsql as $$ begin
  if email is null then perform set_config('role', 'anon', false); perform set_config('request.jwt.claims', '', false);
  else perform set_config('role', 'authenticated', false); perform set_config('request.jwt.claims', json_build_object('email', email)::text, false); end if;
end $$;
create or replace function pg_temp.expect(label text, got bigint, want bigint) returns void language plpgsql as $$ begin
  if got is distinct from want then raise exception 'FAIL %: got %, want %', label, got, want; end if; raise notice 'ok  %', label; end $$;
reset role; delete from public.fm_punch; delete from public.fm_punch_counter;
-- import (as the SQL editor = table owner): 2 old items, counter at 99
insert into public.fm_punch values (2, 'jjpvoskuil@gmail.com', '{"description":"old","status":"Done"}'), (98, 'jjpvoskuil@gmail.com', '{"description":"open one","status":"Open"}');
insert into public.fm_punch_counter values (true, 99) on conflict (id) do update set next_no = greatest(public.fm_punch_counter.next_no, excluded.next_no);

select pg_temp.as_user('akvoskuil94@gmail.com');
select pg_temp.expect('member sees the whole list', (select count(*) from public.fm_punch), 2);
select pg_temp.expect('first new number is 99', public.fm_next_task_no(), 99);
insert into public.fm_punch values (99, 'akvoskuil94@gmail.com', '{"description":"Alex idea"}');
update public.fm_punch set data = '{"description":"Alex idea v2"}' where task_no = 99;
select pg_temp.expect('member edits own item', (select count(*) from public.fm_punch where data->>'description' = 'Alex idea v2'), 1);
update public.fm_punch set data = '{"description":"hijack"}' where task_no = 98;
select pg_temp.expect('member cannot edit another''s item', (select count(*) from public.fm_punch where data->>'description' = 'hijack'), 0);
delete from public.fm_punch where task_no = 98;
select pg_temp.expect('member cannot delete another''s item', (select count(*) from public.fm_punch), 3);
do $$ begin insert into public.fm_punch values (500, 'jjpvoskuil@gmail.com', '{}'); raise exception 'FAIL added as someone else';
  exception when insufficient_privilege then raise notice 'ok  member cannot add as someone else'; end $$;
do $$ begin perform count(*) from public.fm_punch_counter; raise exception 'FAIL counter readable';
  exception when insufficient_privilege then raise notice 'ok  counter table not reachable directly'; end $$;
select pg_temp.as_user('mattvoskuil@gmail.com');
update public.fm_punch set data = '{"description":"done by Matt","status":"Done"}' where task_no = 99;
select pg_temp.expect('admin edits anyone''s item', (select count(*) from public.fm_punch where data->>'description' = 'done by Matt'), 1);
delete from public.fm_punch where task_no = 99;
select pg_temp.expect('admin deletes', (select count(*) from public.fm_punch), 2);
select pg_temp.expect('a deleted number is never reused', public.fm_next_task_no(), 100);
select pg_temp.as_user('stranger@gmail.com');
select pg_temp.expect('outsider sees nothing', (select count(*) from public.fm_punch), 0);
do $$ begin perform public.fm_next_task_no(); raise exception 'FAIL outsider got a number';
  exception when insufficient_privilege then raise notice 'ok  outsider gets no number'; end $$;
select pg_temp.as_user('deer@gmail.com');
select pg_temp.expect('Deercast-only user sees nothing', (select count(*) from public.fm_punch), 0);
select pg_temp.as_user(null);
do $$ begin perform public.fm_next_task_no(); raise exception 'FAIL signed out got a number';
  exception when insufficient_privilege then raise notice 'ok  signed out gets no number'; end $$;
reset role;
