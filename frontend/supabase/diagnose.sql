-- Read-only: shows what runs when a new user signs up, and the tables it touches.
\echo '== triggers on auth.users =='
select tgname, pg_get_triggerdef(oid) as definition
from pg_trigger where tgrelid = 'auth.users'::regclass and not tgisinternal;

\echo '== trigger functions =='
select p.proname, pg_get_functiondef(p.oid) as source
from pg_proc p join pg_trigger t on t.tgfoid = p.oid
where t.tgrelid = 'auth.users'::regclass and not t.tgisinternal;

\echo '== public tables =='
select table_name from information_schema.tables where table_schema = 'public' order by 1;

\echo '== public.profiles columns =='
select column_name, data_type, is_nullable, column_default
from information_schema.columns where table_schema = 'public' and table_name = 'profiles'
order by ordinal_position;

\echo '== constraints on public.profiles =='
select conname, pg_get_constraintdef(oid) from pg_constraint
where conrelid = to_regclass('public.profiles');
