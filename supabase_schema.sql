create extension if not exists "pgcrypto";

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  email text not null unique,
  password_hash text,
  avatar_url text,
  role text not null default 'user' check (role in ('user', 'admin')),
  created_at timestamptz not null default now(),
  last_login timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  token text unique,
  device_name text,
  platform text,
  refresh_token_hash text,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create table if not exists public.households (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  owner_id uuid not null references public.users(id) on delete restrict,
  invite_code text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.household_members (
  id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  role text not null default 'member' check (role in ('owner', 'admin', 'member')),
  created_at timestamptz not null default now(),
  unique (household_id, user_id)
);

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  household_id uuid references public.households(id) on delete cascade,
  dato date not null,
  kategori text not null,
  beloeb numeric(12,2) not null check (beloeb >= 0),
  type text not null check (type in ('Indtægt', 'Udgift')),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  household_id uuid references public.households(id) on delete cascade,
  name text not null,
  amount numeric(12,2) not null check (amount >= 0),
  billing_date date,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.savings_goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  household_id uuid references public.households(id) on delete cascade,
  title text not null,
  target_amount numeric(12,2) not null check (target_amount >= 0),
  current_amount numeric(12,2) not null default 0 check (current_amount >= 0),
  due_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  household_id uuid references public.households(id) on delete cascade,
  title text not null,
  message text not null,
  kind text not null default 'info',
  read boolean not null default false,
  created_at timestamptz not null default now()
);

alter table if exists public.users
  alter column id set default gen_random_uuid();

do $$
declare
  dependency record;
begin
  for dependency in
    select con.conname
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace rel_ns on rel_ns.oid = rel.relnamespace
    join pg_class ref on ref.oid = con.confrelid
    join pg_namespace ref_ns on ref_ns.oid = ref.relnamespace
    where rel_ns.nspname = 'public'
      and rel.relname = 'users'
      and con.contype = 'f'
      and ref_ns.nspname = 'auth'
      and ref.relname = 'users'
  loop
    execute format('alter table public.users drop constraint %I', dependency.conname);
  end loop;
end $$;

alter table if exists public.users
  add column if not exists updated_at timestamptz not null default now();

alter table if exists public.sessions
  add column if not exists token text,
  add column if not exists device_name text,
  add column if not exists platform text,
  add column if not exists refresh_token_hash text,
  add column if not exists revoked_at timestamptz;

alter table if exists public.households
  add column if not exists updated_at timestamptz not null default now();

alter table if exists public.transactions
  add column if not exists note text,
  add column if not exists updated_at timestamptz not null default now();

alter table if exists public.subscriptions
  add column if not exists updated_at timestamptz not null default now();

alter table if exists public.savings_goals
  add column if not exists updated_at timestamptz not null default now();

create index if not exists idx_users_email on public.users(email);
create index if not exists idx_sessions_user_expires on public.sessions(user_id, expires_at desc);
create unique index if not exists idx_sessions_token on public.sessions(token) where token is not null;
create index if not exists idx_households_owner on public.households(owner_id);
create index if not exists idx_household_members_household on public.household_members(household_id);
create index if not exists idx_household_members_user on public.household_members(user_id);
create index if not exists idx_transactions_user_date on public.transactions(user_id, dato desc);
create index if not exists idx_transactions_household_date on public.transactions(household_id, dato desc);
create index if not exists idx_subscriptions_user_active on public.subscriptions(user_id, active);
create index if not exists idx_subscriptions_household_active on public.subscriptions(household_id, active);
create index if not exists idx_savings_goals_user on public.savings_goals(user_id);
create index if not exists idx_savings_goals_household on public.savings_goals(household_id);
create index if not exists idx_notifications_user_created on public.notifications(user_id, created_at desc);
create index if not exists idx_notifications_household_created on public.notifications(household_id, created_at desc);

create or replace function public.is_household_member(target_household_id uuid)
returns boolean
language sql
stable
security definer
as $$
  select exists (
    select 1
    from public.household_members hm
    where hm.household_id = target_household_id
      and hm.user_id = auth.uid()
  );
$$;

create or replace function public.is_household_admin(target_household_id uuid)
returns boolean
language sql
stable
security definer
as $$
  select exists (
    select 1
    from public.household_members hm
    where hm.household_id = target_household_id
      and hm.user_id = auth.uid()
      and hm.role in ('owner', 'admin')
  );
$$;

alter table public.users enable row level security;
alter table public.sessions enable row level security;
alter table public.households enable row level security;
alter table public.household_members enable row level security;
alter table public.transactions enable row level security;
alter table public.subscriptions enable row level security;
alter table public.savings_goals enable row level security;
alter table public.notifications enable row level security;

drop policy if exists "users can read own profile" on public.users;
create policy "users can read own profile"
on public.users
for select
using (id = auth.uid());

drop policy if exists "users can update own profile" on public.users;
create policy "users can update own profile"
on public.users
for update
using (id = auth.uid())
with check (id = auth.uid());

drop policy if exists "sessions are own only" on public.sessions;
create policy "sessions are own only"
on public.sessions
for all
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists "households readable by members" on public.households;
create policy "households readable by members"
on public.households
for select
using (owner_id = auth.uid() or public.is_household_member(id));

drop policy if exists "households manageable by owner" on public.households;
create policy "households manageable by owner"
on public.households
for update
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

drop policy if exists "households deletable by owner" on public.households;
create policy "households deletable by owner"
on public.households
for delete
using (owner_id = auth.uid());

drop policy if exists "members readable by household members" on public.household_members;
create policy "members readable by household members"
on public.household_members
for select
using (user_id = auth.uid() or public.is_household_member(household_id));

drop policy if exists "members manageable by household admin" on public.household_members;
create policy "members manageable by household admin"
on public.household_members
for all
using (public.is_household_admin(household_id) or user_id = auth.uid())
with check (public.is_household_admin(household_id) or user_id = auth.uid());

drop policy if exists "transactions readable by owner or household" on public.transactions;
create policy "transactions readable by owner or household"
on public.transactions
for select
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "transactions writable by owner or household member" on public.transactions;
create policy "transactions writable by owner or household member"
on public.transactions
for insert
with check (
  user_id = auth.uid()
  or (household_id is not null and public.is_household_member(household_id))
);

drop policy if exists "transactions editable by owner or household member" on public.transactions;
create policy "transactions editable by owner or household member"
on public.transactions
for update
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)))
with check (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "transactions deletable by owner or household member" on public.transactions;
create policy "transactions deletable by owner or household member"
on public.transactions
for delete
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "subscriptions readable" on public.subscriptions;
create policy "subscriptions readable"
on public.subscriptions
for select
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "subscriptions writable" on public.subscriptions;
create policy "subscriptions writable"
on public.subscriptions
for all
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)))
with check (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "savings readable" on public.savings_goals;
create policy "savings readable"
on public.savings_goals
for select
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "savings writable" on public.savings_goals;
create policy "savings writable"
on public.savings_goals
for all
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)))
with check (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "notifications readable" on public.notifications;
create policy "notifications readable"
on public.notifications
for select
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop policy if exists "notifications writable" on public.notifications;
create policy "notifications writable"
on public.notifications
for all
using (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)))
with check (user_id = auth.uid() or (household_id is not null and public.is_household_member(household_id)));

drop trigger if exists trg_users_updated_at on public.users;
create trigger trg_users_updated_at
before update on public.users
for each row execute function public.set_updated_at();

drop trigger if exists trg_households_updated_at on public.households;
create trigger trg_households_updated_at
before update on public.households
for each row execute function public.set_updated_at();

drop trigger if exists trg_transactions_updated_at on public.transactions;
create trigger trg_transactions_updated_at
before update on public.transactions
for each row execute function public.set_updated_at();

drop trigger if exists trg_subscriptions_updated_at on public.subscriptions;
create trigger trg_subscriptions_updated_at
before update on public.subscriptions
for each row execute function public.set_updated_at();

drop trigger if exists trg_savings_goals_updated_at on public.savings_goals;
create trigger trg_savings_goals_updated_at
before update on public.savings_goals
for each row execute function public.set_updated_at();
