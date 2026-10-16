-- Paste this whole file into the Supabase SQL editor and run it. Safe to run more than once.

-- Profiles: one row per auth user, created automatically on sign-up.
create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  display_name text,
  credits integer not null default 30,
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)));
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Videos: one row per generation request.
do $$ begin
  create type public.video_status as enum ('queued', 'generating', 'ready', 'failed');
exception when duplicate_object then null; end $$;

create table if not exists public.videos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade default auth.uid(),
  prompt text not null check (char_length(prompt) between 3 and 500),
  scenes smallint check (scenes between 1 and 8),
  voice text not null default 'Kore',
  quality text not null default 'medium' check (quality in ('low', 'medium', 'high')),
  status public.video_status not null default 'queued',
  title text,
  storage_path text,          -- path inside the "videos" bucket, set by the server
  duration_seconds real,
  error text,
  is_public boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists videos_user_created_idx on public.videos (user_id, created_at desc);

-- Row level security
alter table public.profiles enable row level security;
alter table public.videos enable row level security;

drop policy if exists "read own profile" on public.profiles;
create policy "read own profile" on public.profiles
  for select using (auth.uid() = id);

drop policy if exists "update own profile name" on public.profiles;
create policy "update own profile name" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);
-- credits are only changed by the server (service role); clients may only rename themselves
revoke update on public.profiles from authenticated;
grant update (display_name) on public.profiles to authenticated;

drop policy if exists "read own or public videos" on public.videos;
create policy "read own or public videos" on public.videos
  for select using (auth.uid() = user_id or is_public);

drop policy if exists "queue own videos" on public.videos;
create policy "queue own videos" on public.videos
  for insert with check (auth.uid() = user_id and status = 'queued');

drop policy if exists "share own videos" on public.videos;
create policy "share own videos" on public.videos
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
-- clients may only toggle sharing and rename; status/paths come from the server
revoke update on public.videos from authenticated;
grant update (is_public, title) on public.videos to authenticated;

drop policy if exists "delete own videos" on public.videos;
create policy "delete own videos" on public.videos
  for delete using (auth.uid() = user_id);

-- Credits are only ever changed by the API server (service role), through these two functions.
-- spend_credits checks and subtracts in one statement, so two requests can't spend the same credits.
create or replace function public.spend_credits(p_user uuid, p_amount integer)
returns boolean language sql security definer set search_path = public as $$
  with spent as (
    update public.profiles set credits = credits - p_amount
    where id = p_user and credits >= p_amount
    returning 1
  )
  select exists (select 1 from spent);
$$;

create or replace function public.refund_credits(p_user uuid, p_amount integer)
returns void language sql security definer set search_path = public as $$
  update public.profiles set credits = credits + greatest(p_amount, 0) where id = p_user;
$$;

revoke all on function public.spend_credits(uuid, integer) from public, anon, authenticated;
revoke all on function public.refund_credits(uuid, integer) from public, anon, authenticated;
grant execute on function public.spend_credits(uuid, integer) to service_role;
grant execute on function public.refund_credits(uuid, integer) to service_role;

-- Live status updates in the app (skipped if already enabled)
do $$ begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'videos'
  ) then
    alter publication supabase_realtime add table public.videos;
  end if;
end $$;

-- Storage: private bucket, files stored as <user_id>/<video_id>.mp4
insert into storage.buckets (id, name, public)
values ('videos', 'videos', false)
on conflict (id) do nothing;

drop policy if exists "read own or public video files" on storage.objects;
create policy "read own or public video files" on storage.objects
  for select using (
    bucket_id = 'videos' and (
      (storage.foldername(name))[1] = auth.uid()::text
      or exists (select 1 from public.videos v where v.storage_path = name and v.is_public)
    )
  );

drop policy if exists "delete own video files" on storage.objects;
create policy "delete own video files" on storage.objects
  for delete using (bucket_id = 'videos' and (storage.foldername(name))[1] = auth.uid()::text);

-- Give users who signed up before this script ran their profile (and starting credits)
insert into public.profiles (id, display_name)
select id, coalesce(raw_user_meta_data->>'full_name', split_part(email, '@', 1))
from auth.users
on conflict (id) do nothing;

-- Make the new tables visible to the API right away
notify pgrst, 'reload schema';
