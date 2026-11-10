#!/bin/bash
# Start a throwaway local PostgreSQL 16 that imitates Supabase's auth bits (auth.jwt(), anon/authenticated roles,
# storage stub), for testing schema.sql's row-level security before John runs it for real. Usage: source local_pg.sh
set -e
PGBIN=/usr/lib/postgresql/16/bin; export PGDATA=/tmp/fmpg; export PGPORT=55432 PGHOST=/tmp PGUSER=postgres
if ! su postgres -c "$PGBIN/pg_ctl -D $PGDATA status" >/dev/null 2>&1; then
  rm -rf $PGDATA; mkdir -p $PGDATA; chown postgres $PGDATA
  su postgres -c "$PGBIN/initdb -D $PGDATA -A trust >/dev/null"
  su postgres -c "$PGBIN/pg_ctl -D $PGDATA -o '-p $PGPORT -k /tmp' -l /tmp/fmpg.log start >/dev/null"
  sleep 1
  psql -q -d postgres <<'SQL'
create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
create schema auth; grant usage on schema auth to anon, authenticated;
create function auth.jwt() returns jsonb language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;
create function auth.uid() returns uuid language sql stable as $$ select nullif(auth.jwt() ->> 'sub', '')::uuid $$;
grant execute on all functions in schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;
SQL
fi
