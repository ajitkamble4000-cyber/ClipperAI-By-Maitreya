#!/usr/bin/env bash
# Combine every migration into infra/supabase/setup.sql: one script to paste into a NEW Supabase project
# (Dashboard → SQL Editor → New query → paste → Run). It runs in one transaction: all or nothing.
# Re-run this whenever a migration is added:  bash infra/scripts/build-setup-sql.sh
set -euo pipefail
cd "$(dirname "$0")/../supabase"
out=setup.sql
{
  echo "-- ClipperAI by Maitreya: complete database setup for a NEW Supabase project."
  echo "-- Paste into Supabase → SQL Editor → New query, then click Run. Generated from migrations/ by"
  echo "-- infra/scripts/build-setup-sql.sh; do not edit by hand. Run it once, on an empty project."
  echo
  echo "begin;"
  for f in migrations/*.sql; do
    echo
    echo "-- ======================================================================== $(basename "$f")"
    cat "$f"
  done
  echo
  echo "-- Record the migrations as applied (so the Supabase CLI won't re-run them later)."
  echo "create schema if not exists supabase_migrations;"
  echo "create table if not exists supabase_migrations.schema_migrations (version text primary key, statements text[], name text);"
  for f in migrations/*.sql; do
    b=$(basename "$f" .sql)
    echo "insert into supabase_migrations.schema_migrations (version, name) values ('${b%%_*}', '${b#*_}') on conflict do nothing;"
  done
  echo
  echo "commit;"
} > "$out"
echo "wrote infra/supabase/$out ($(wc -l < "$out") lines)"
