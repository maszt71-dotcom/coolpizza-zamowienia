-- =============================================================
-- Cool Pizza – zamówienia online
-- Wklej całość w Supabase → SQL Editor → Run (jednorazowo).
-- Można w tym samym projekcie co rozliczenie pizzerii / kalisz_wpisy.
-- =============================================================

create table if not exists public.zamowienia (
  id          bigint generated always as identity primary key,
  utworzono   timestamptz not null default now(),
  lokal       text not null default 'ostrow',
  status      text not null default 'nowe'
              check (status in ('nowe','w_przygotowaniu','w_drodze','do_odbioru','zrealizowane','anulowane')),
  tryb        text not null check (tryb in ('dostawa','odbior')),
  kiedy       text,
  imie        text not null,
  telefon     text not null,
  adres       text,
  platnosc    text,
  uwagi       text,
  pozycje     jsonb not null,           -- [{name, desc, unit, qty}]
  produkty    numeric(10,2) not null,
  rabat       numeric(10,2) not null default 0,
  dostawa     numeric(10,2) not null default 0,
  razem       numeric(10,2) not null,
  kod_rabatowy text,
  zmieniono   timestamptz
);

create index if not exists zamowienia_utworzono_idx on public.zamowienia (utworzono desc);
create index if not exists zamowienia_status_idx    on public.zamowienia (status);

-- RLS włączone, BEZ polityk dla anon:
-- strona klienta nie może czytać ani zmieniać tabeli, może tylko wywołać funkcję poniżej.
-- Panel kuchni używa klucza service_role (omija RLS).
alter table public.zamowienia enable row level security;

-- -------------------------------------------------------------
-- Jedyne wejście ze strony: zloz_zamowienie(p jsonb) → numer zamówienia
-- -------------------------------------------------------------
create or replace function public.zloz_zamowienie(p jsonb)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id   bigint;
  v_tel  text := regexp_replace(coalesce(p->>'telefon',''), '\D', '', 'g');
  v_tryb text := p->>'tryb';
  v_raz  numeric;
begin
  if length(v_tel) < 9 or length(v_tel) > 12 then
    raise exception 'Podaj poprawny numer telefonu';
  end if;
  if coalesce(trim(p->>'imie'),'') = '' then
    raise exception 'Podaj imię';
  end if;
  if v_tryb not in ('dostawa','odbior') then
    raise exception 'Nieprawidłowy sposób odbioru';
  end if;
  if v_tryb = 'dostawa' and coalesce(trim(p->>'adres'),'') = '' then
    raise exception 'Podaj adres dostawy';
  end if;
  if jsonb_typeof(p->'pozycje') is distinct from 'array'
     or jsonb_array_length(p->'pozycje') = 0
     or jsonb_array_length(p->'pozycje') > 60 then
    raise exception 'Koszyk jest pusty';
  end if;

  v_raz := (p->>'razem')::numeric;
  if v_raz is null or v_raz <= 0 or v_raz > 5000 then
    raise exception 'Nieprawidłowa kwota zamówienia';
  end if;

  -- antyspam: max 3 zamówienia z jednego numeru w 10 minut
  if (select count(*) from zamowienia
      where telefon = v_tel and utworzono > now() - interval '10 minutes') >= 3 then
    raise exception 'Za dużo zamówień z tego numeru. Zadzwoń do lokalu: 62 307 07 07';
  end if;

  insert into zamowienia
    (tryb, kiedy, imie, telefon, adres, platnosc, uwagi, pozycje,
     produkty, rabat, dostawa, razem, kod_rabatowy)
  values
    (v_tryb,
     left(p->>'kiedy', 40),
     left(trim(p->>'imie'), 60),
     v_tel,
     left(p->>'adres', 200),
     left(p->>'platnosc', 40),
     left(p->>'uwagi', 500),
     p->'pozycje',
     coalesce((p->>'produkty')::numeric, v_raz),
     coalesce((p->>'rabat')::numeric, 0),
     coalesce((p->>'dostawa')::numeric, 0),
     v_raz,
     left(p->>'kod', 30))
  returning id into v_id;

  return 'CP-' || v_id;
end;
$$;

revoke all on function public.zloz_zamowienie(jsonb) from public;
grant execute on function public.zloz_zamowienie(jsonb) to anon, authenticated;
