-- Persistent acquisition state. Reader/web role has no access.
begin;
create table if not exists football.sync_cache (
  path text primary key,
  payload bytea not null,
  mtime double precision not null
);
create table if not exists football.sync_control (
  name text primary key,
  value jsonb not null
);
alter table football.sync_cache enable row level security;
alter table football.sync_control enable row level security;
do $$ declare t text; begin
  foreach t in array array['sync_cache','sync_control'] loop
    if not exists (select 1 from pg_policies where schemaname='football' and tablename=t and policyname='importer_sync') then
      execute format('create policy importer_sync on football.%I for all to football_importer using(true) with check(true)',t);
    end if;
    execute format('grant select,insert,update,delete on football.%I to football_importer',t);
  end loop;
end $$;
commit;
