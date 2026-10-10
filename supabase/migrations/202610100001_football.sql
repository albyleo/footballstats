-- Run as database owner in Supabase SQL Editor. Safe to rerun; no data is dropped.
begin;
create schema if not exists football;
revoke all on schema football from public;
do $$ begin
  if not exists(select 1 from pg_roles where rolname = 'football_reader') then
    create role football_reader login noinherit;
  end if;
  if not exists(select 1 from pg_roles where rolname = 'football_importer') then
    create role football_importer login noinherit;
  end if;
end $$;

create table if not exists football.teams (
  provider text not null, id text not null, name text not null,
  primary key(provider,id)
);
create table if not exists football.players (
  provider text not null, id text not null, name text not null,
  primary key(provider,id)
);
create table if not exists football.fixtures (
  provider text not null, id text not null, match_date date not null,
  league text not null, season text not null,
  primary key(provider,id)
);
create table if not exists football.team_match_stats (
  provider text not null, fixture_id text not null, team_id text not null,
  payload jsonb not null check(jsonb_typeof(payload) = 'object'),
  primary key(provider,fixture_id,team_id),
  foreign key(provider,fixture_id) references football.fixtures(provider,id),
  foreign key(provider,team_id) references football.teams(provider,id)
);
create table if not exists football.player_match_stats (
  provider text not null, fixture_id text not null, player_id text not null, team_id text not null,
  payload jsonb not null check(jsonb_typeof(payload) = 'object'),
  primary key(provider,fixture_id,player_id,team_id),
  foreign key(provider,fixture_id) references football.fixtures(provider,id),
  foreign key(provider,player_id) references football.players(provider,id),
  foreign key(provider,team_id) references football.teams(provider,id)
);
create table if not exists football.dataset_state (
  id integer primary key check(id = 1), revision bigint not null default 0,
  metadata jsonb not null default '{}'::jsonb, updated_at timestamptz not null default now()
);
insert into football.dataset_state(id) values(1) on conflict do nothing;
create index if not exists fixtures_league_season_date on football.fixtures(league,season,match_date);

-- The schema is private (do not add it to exposed Data API schemas).
-- RLS also denies anon/authenticated; only the two dedicated roles have policies.
do $$ declare t text; begin
  foreach t in array array['teams','players','fixtures','team_match_stats','player_match_stats','dataset_state'] loop
    execute format('alter table football.%I enable row level security', t);
    if not exists(select 1 from pg_policies where schemaname='football' and tablename=t and policyname='reader_select') then
      execute format('create policy reader_select on football.%I for select to football_reader using (true)',t);
      execute format('create policy importer_all on football.%I for all to football_importer using (true) with check (true)',t);
    end if;
    execute format('grant select on football.%I to football_reader',t);
    execute format('grant select,insert,update,delete on football.%I to football_importer',t);
  end loop;
end $$;
grant usage on schema football to football_reader, football_importer;
alter role football_reader set default_transaction_read_only = on;
commit;
