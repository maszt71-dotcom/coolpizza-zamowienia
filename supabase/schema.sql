-- =====================================================================
-- Cool Pizza – system zamówień online  (wersja 2)
-- Supabase → SQL Editor → wklej całość → Run.
-- Skrypt jest powtarzalny: można go uruchomić ponownie (nie kasuje danych v2).
-- Po nim uruchom seed.sql (menu, strefy, ustawienia) – tylko raz.
-- =====================================================================

-- Funkcja z prototypu v1 zwracała text – trzeba ją usunąć, bo v2 zwraca jsonb (zaraz jest tworzona na nowo).
drop function if exists public.zloz_zamowienie(jsonb);

-- Usunięcie prototypu v1 – TYLKO jeśli tabela ma starą budowę (kolumna jsonb "pozycje").
-- Tabela v2 nie ma tej kolumny, więc ponowne uruchomienie skryptu nie kasuje zamówień.
do $$ begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'zamowienia' and column_name = 'pozycje') then
    drop table public.zamowienia cascade;
  end if;
end $$;

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- katalog
create table if not exists lokale (
  id          int primary key,
  nazwa       text not null,
  adres       text not null,
  telefon     text not null,
  email       text,
  godz_od     time not null default '11:00',
  godz_do     time not null default '23:00',
  aktywny     boolean not null default true,
  kolejnosc   int not null default 0
);

create table if not exists kategorie (
  id          serial primary key,
  nazwa       text not null unique,
  kolejnosc   int not null default 0,
  aktywna     boolean not null default true
);

create table if not exists rozmiary (
  id          serial primary key,
  nazwa       text not null unique,          -- '30 cm'
  kolejnosc   int not null default 0,
  opakowanie  numeric(8,2) not null default 0 -- dopłata za opakowanie (brutto)
);

create table if not exists produkty (
  id          serial primary key,
  kategoria_id int not null references kategorie(id),
  nazwa       text not null,
  opis        text not null default '',      -- składniki
  tagi        text[] not null default '{}',  -- 'wege', 'ostra', 'ryba'
  cena        numeric(8,2),                  -- produkty bez rozmiarów (napoje, zestawy)
  dodatki     boolean not null default false, -- można dobrać płatne dodatki
  sos_gratis  int not null default 0,        -- ile darmowych sosów (0/1)
  kolejnosc   int not null default 0,
  aktywny     boolean not null default true,
  unique (kategoria_id, nazwa)
);

create table if not exists ceny (
  produkt_id  int not null references produkty(id) on delete cascade,
  rozmiar_id  int not null references rozmiary(id),
  cena        numeric(8,2) not null check (cena >= 0),
  primary key (produkt_id, rozmiar_id)
);

-- produkt chwilowo niedostępny w danym lokalu
create table if not exists niedostepne (
  lokal_id    int not null references lokale(id) on delete cascade,
  produkt_id  int not null references produkty(id) on delete cascade,
  primary key (lokal_id, produkt_id)
);

create table if not exists dodatki_grupy (
  id          serial primary key,
  nazwa       text not null unique,
  cena        numeric(8,2) not null default 0,
  kolejnosc   int not null default 0
);

create table if not exists dodatki (
  id          serial primary key,
  grupa_id    int not null references dodatki_grupy(id) on delete cascade,
  nazwa       text not null,
  cena        numeric(8,2),                 -- null = cena grupy
  aktywny     boolean not null default true,
  kolejnosc   int not null default 0,
  unique (grupa_id, nazwa)
);

create table if not exists sosy_gratis (
  id          serial primary key,
  nazwa       text not null unique,
  aktywny     boolean not null default true,
  kolejnosc   int not null default 0
);

create table if not exists strefy (
  id          serial primary key,
  lokal_id    int not null references lokale(id) on delete cascade,
  miejscowosc text not null,
  kod         text,
  oplata      numeric(8,2) not null default 0,
  aktywna     boolean not null default true,
  unique (lokal_id, miejscowosc)
);

create table if not exists ustawienia (
  klucz       text primary key,
  wartosc     jsonb not null,
  opis        text
);

create table if not exists kody_rabatowe (
  kod             text primary key,           -- WIELKIE LITERY
  typ             text not null check (typ in ('proc','kwota')),
  wartosc         numeric(8,2) not null check (wartosc > 0),
  max_uzyc        int,                         -- null = bez limitu
  max_na_klienta  int,                         -- po numerze telefonu
  wazny_od        timestamptz,
  wazny_do        timestamptz,
  min_wartosc     numeric(8,2) not null default 0,
  aktywny         boolean not null default true,
  uzyto           int not null default 0
);

-- ---------------------------------------------------------------- zamówienia
create table if not exists zamowienia (
  id              bigint generated always as identity primary key,
  numer           text not null,                 -- 3/06/10/2026 (jak w Appinecie)
  token           uuid not null default gen_random_uuid() unique,
  lokal_id        int not null references lokale(id),
  utworzono       timestamptz not null default now(),
  zmieniono       timestamptz,
  status          text not null default 'nowe' check (status in
                  ('oczekuje_na_platnosc','nowe','przyjete','w_drodze','do_odbioru','zrealizowane','anulowane')),
  tryb            text not null check (tryb in ('dostawa','odbior')),
  na_kiedy        timestamptz,                   -- null = jak najszybciej
  imie            text not null,
  nazwisko        text,
  telefon         text not null,
  email           text,
  miejscowosc     text,
  ulica           text,
  nr_domu         text,
  nr_lokalu       text,
  pietro          text,
  strefa_id       int references strefy(id),
  uwagi           text,
  faktura         boolean not null default false,
  nip             text,
  firma           text,
  adres_firmy     text,
  platnosc        text not null check (platnosc in ('online','gotowka','karta')),
  platnosc_status text not null default 'brak' check (platnosc_status in ('brak','oczekuje','oplacone','blad')),
  platnosc_proba  int not null default 0,
  autopay_remote_id text,
  produkty_suma   numeric(10,2) not null,
  opakowania      numeric(10,2) not null default 0,
  dostawa         numeric(10,2) not null default 0,
  rabat           numeric(10,2) not null default 0,
  razem           numeric(10,2) not null,
  kod_rabatowy    text references kody_rabatowe(kod),
  zrodlo          text not null default 'www'
);
create index if not exists zam_utworzono_idx on zamowienia (utworzono desc);
create index if not exists zam_status_idx    on zamowienia (status);
create index if not exists zam_tel_idx       on zamowienia (telefon, utworzono desc);

create table if not exists zamowienia_pozycje (
  id            bigint generated always as identity primary key,
  zamowienie_id bigint not null references zamowienia(id) on delete cascade,
  produkt_id    int references produkty(id),
  nazwa         text not null,
  rozmiar       text,
  ilosc         int not null check (ilosc between 1 and 50),
  cena_jedn     numeric(10,2) not null,
  opakowanie    numeric(10,2) not null default 0,
  sos_gratis    text,
  dodatki       jsonb not null default '[]',      -- [{nazwa, cena}]
  suma          numeric(10,2) not null
);
create index if not exists poz_zam_idx on zamowienia_pozycje (zamowienie_id);

create table if not exists platnosci_log (
  id            bigint generated always as identity primary key,
  utworzono     timestamptz not null default now(),
  zamowienie_id bigint references zamowienia(id) on delete set null,
  zdarzenie     text not null,
  dane          jsonb
);

-- RLS: włączone wszędzie, bez polityk → klucz publiczny (anon) nie czyta tabel.
-- Strona korzysta wyłącznie z funkcji poniżej; panel admina i Edge Functions – kluczem service_role.
do $$ declare t text; begin
  foreach t in array array['lokale','kategorie','rozmiary','produkty','ceny','niedostepne','dodatki_grupy',
    'dodatki','sosy_gratis','strefy','ustawienia','kody_rabatowe','zamowienia','zamowienia_pozycje','platnosci_log']
  loop execute format('alter table public.%I enable row level security', t); end loop;
end $$;

-- ---------------------------------------------------------------- pomocnicze
create or replace function _ust(p_klucz text, p_domysl jsonb default null)
returns jsonb language sql stable set search_path = public as $$
  select coalesce((select wartosc from ustawienia where klucz = p_klucz), p_domysl)
$$;

create or replace function _teraz_pl() returns timestamp language sql stable as $$
  select (now() at time zone 'Europe/Warsaw')
$$;

create or replace function _otwarte(p_lokal int, p_kiedy timestamptz default now())
returns boolean language sql stable set search_path = public as $$
  select exists (
    select 1 from lokale l
    where l.id = p_lokal and l.aktywny
      and (p_kiedy at time zone 'Europe/Warsaw')::time >= l.godz_od
      and (p_kiedy at time zone 'Europe/Warsaw')::time <  l.godz_do)
$$;

-- ---------------------------------------------------------------- menu dla strony
create or replace function menu_publiczne(p_lokal int default null)
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'lokale', (select coalesce(jsonb_agg(jsonb_build_object(
        'id', l.id, 'nazwa', l.nazwa, 'adres', l.adres, 'telefon', l.telefon, 'email', l.email,
        'godz_od', to_char(l.godz_od,'HH24:MI'), 'godz_do', to_char(l.godz_do,'HH24:MI'),
        'otwarte', _otwarte(l.id)) order by l.kolejnosc, l.id), '[]')
      from lokale l where l.aktywny),
    'ustawienia', jsonb_build_object(
        'min_zamowienie',        _ust('min_zamowienie','45'),
        'platnosc_online',       _ust('platnosc_online','true'),
        'platnosc_gotowka',      _ust('platnosc_gotowka','false'),
        'platnosc_karta',        _ust('platnosc_karta','false'),
        'zamawianie_wylaczone',  _ust('zamawianie_wylaczone','false'),
        'komunikat',             _ust('komunikat','""'),
        'czas_dostawy_min',      _ust('czas_dostawy_min','60'),
        'czas_odbioru_min',      _ust('czas_odbioru_min','30'),
        'regulamin_url',         _ust('regulamin_url','""'),
        'polityka_url',          _ust('polityka_url','""')),
    'rozmiary', (select coalesce(jsonb_agg(jsonb_build_object('id',r.id,'nazwa',r.nazwa,'opakowanie',r.opakowanie)
        order by r.kolejnosc), '[]') from rozmiary r),
    'kategorie', (select coalesce(jsonb_agg(jsonb_build_object(
        'id', k.id, 'nazwa', k.nazwa,
        'produkty', (select coalesce(jsonb_agg(jsonb_build_object(
            'id', p.id, 'nazwa', p.nazwa, 'opis', p.opis, 'tagi', to_jsonb(p.tagi),
            'cena', p.cena, 'dodatki', p.dodatki, 'sos_gratis', p.sos_gratis,
            'dostepny', not exists (select 1 from niedostepne n where n.produkt_id = p.id and n.lokal_id = p_lokal),
            'ceny', (select coalesce(jsonb_agg(jsonb_build_object('rozmiar_id', c.rozmiar_id, 'cena', c.cena)
                     order by r.kolejnosc), '[]')
                     from ceny c join rozmiary r on r.id = c.rozmiar_id where c.produkt_id = p.id))
            order by p.kolejnosc, p.id), '[]')
          from produkty p where p.kategoria_id = k.id and p.aktywny))
        order by k.kolejnosc, k.id), '[]')
      from kategorie k where k.aktywna),
    'dodatki', (select coalesce(jsonb_agg(jsonb_build_object(
        'grupa', g.nazwa, 'cena', g.cena,
        'lista', (select coalesce(jsonb_agg(jsonb_build_object('id', d.id, 'nazwa', d.nazwa,
                  'cena', coalesce(d.cena, g.cena)) order by d.kolejnosc, d.nazwa), '[]')
                  from dodatki d where d.grupa_id = g.id and d.aktywny))
        order by g.kolejnosc), '[]') from dodatki_grupy g),
    'sosy_gratis', (select coalesce(jsonb_agg(jsonb_build_object('id', s.id, 'nazwa', s.nazwa)
        order by s.kolejnosc), '[]') from sosy_gratis s where s.aktywny),
    'strefy', (select coalesce(jsonb_agg(jsonb_build_object('id', s.id, 'lokal_id', s.lokal_id,
        'miejscowosc', s.miejscowosc, 'kod', s.kod, 'oplata', s.oplata)
        order by s.oplata, s.miejscowosc), '[]') from strefy s where s.aktywna
        and (p_lokal is null or s.lokal_id = p_lokal))
  )
$$;

-- ---------------------------------------------------------------- wycena (jedno źródło prawdy)
-- p: { lokal_id, tryb, strefa_id, kod, telefon,
--      pozycje: [{produkt_id, rozmiar_id?, ilosc, sos_gratis_id?, dodatki:[id,...]}] }
create or replace function _wycen(p jsonb)
returns jsonb language plpgsql stable set search_path = public as $$
declare
  v_lokal   int := (p->>'lokal_id')::int;
  v_tryb    text := p->>'tryb';
  v_poz     jsonb;
  v_prod    produkty%rowtype;
  v_cena    numeric; v_opak numeric; v_rozm text;
  v_dod     jsonb; v_dod_suma numeric; v_dod_id int; v_d record;
  v_sos     text;
  v_ilosc   int;
  v_linie   jsonb := '[]';
  v_suma    numeric := 0; v_opak_suma numeric := 0;
  v_dostawa numeric := 0; v_rabat numeric := 0;
  v_kod     kody_rabatowe%rowtype; v_kod_txt text := upper(nullif(trim(p->>'kod'),''));
  v_kod_info text;
  v_min     numeric := (_ust('min_zamowienie','45'))::text::numeric;
  v_tel     text := regexp_replace(coalesce(p->>'telefon',''), '\D', '', 'g');
begin
  if not exists (select 1 from lokale where id = v_lokal and aktywny) then
    raise exception 'Wybierz lokal';
  end if;
  if v_tryb not in ('dostawa','odbior') then raise exception 'Wybierz dostawę albo odbiór'; end if;
  if jsonb_typeof(p->'pozycje') is distinct from 'array' or jsonb_array_length(p->'pozycje') = 0 then
    raise exception 'Koszyk jest pusty';
  end if;
  if jsonb_array_length(p->'pozycje') > 40 then raise exception 'Za dużo pozycji w koszyku'; end if;

  for v_poz in select * from jsonb_array_elements(p->'pozycje') loop
    select * into v_prod from produkty where id = (v_poz->>'produkt_id')::int and aktywny;
    if not found then raise exception 'Produkt nie jest już dostępny – odśwież menu'; end if;
    if exists (select 1 from niedostepne where lokal_id = v_lokal and produkt_id = v_prod.id) then
      raise exception '„%” jest chwilowo niedostępny', v_prod.nazwa;
    end if;
    v_ilosc := coalesce((v_poz->>'ilosc')::int, 1);
    if v_ilosc < 1 or v_ilosc > 20 then raise exception 'Nieprawidłowa ilość'; end if;

    -- cena bazowa
    if exists (select 1 from ceny where produkt_id = v_prod.id) then
      select c.cena, r.opakowanie, r.nazwa into v_cena, v_opak, v_rozm
        from ceny c join rozmiary r on r.id = c.rozmiar_id
        where c.produkt_id = v_prod.id and c.rozmiar_id = (v_poz->>'rozmiar_id')::int;
      if not found then raise exception 'Wybierz rozmiar dla „%”', v_prod.nazwa; end if;
    else
      v_cena := v_prod.cena; v_opak := 0; v_rozm := null;
      if v_cena is null then raise exception 'Brak ceny dla „%”', v_prod.nazwa; end if;
    end if;

    -- sos gratis
    v_sos := null;
    if nullif(v_poz->>'sos_gratis_id','') is not null then
      if v_prod.sos_gratis < 1 then raise exception 'Ten produkt nie ma sosu gratis'; end if;
      select nazwa into v_sos from sosy_gratis where id = (v_poz->>'sos_gratis_id')::int and aktywny;
      if not found then raise exception 'Wybrany sos jest niedostępny'; end if;
    end if;

    -- płatne dodatki
    v_dod := '[]'; v_dod_suma := 0;
    if jsonb_typeof(v_poz->'dodatki') = 'array' and jsonb_array_length(v_poz->'dodatki') > 0 then
      if not v_prod.dodatki then raise exception 'Do „%” nie można dobrać dodatków', v_prod.nazwa; end if;
      if jsonb_array_length(v_poz->'dodatki') > 15 then raise exception 'Za dużo dodatków'; end if;
      for v_dod_id in select (x)::int from jsonb_array_elements_text(v_poz->'dodatki') x loop
        select d.nazwa, coalesce(d.cena, g.cena) as cena into v_d
          from dodatki d join dodatki_grupy g on g.id = d.grupa_id where d.id = v_dod_id and d.aktywny;
        if not found then raise exception 'Wybrany dodatek jest niedostępny'; end if;
        v_dod := v_dod || jsonb_build_object('nazwa', v_d.nazwa, 'cena', v_d.cena);
        v_dod_suma := v_dod_suma + v_d.cena;
      end loop;
    end if;

    v_linie := v_linie || jsonb_build_object(
      'produkt_id', v_prod.id, 'nazwa', v_prod.nazwa, 'rozmiar', v_rozm, 'ilosc', v_ilosc,
      'cena_jedn', v_cena + v_dod_suma, 'opakowanie', v_opak, 'sos_gratis', v_sos, 'dodatki', v_dod,
      'suma', (v_cena + v_dod_suma) * v_ilosc);
    v_suma := v_suma + (v_cena + v_dod_suma) * v_ilosc;
    v_opak_suma := v_opak_suma + v_opak * v_ilosc;
  end loop;

  -- dostawa
  if v_tryb = 'dostawa' and nullif(p->>'strefa_id','') is not null then
    select oplata into v_dostawa from strefy
      where id = (p->>'strefa_id')::int and lokal_id = v_lokal and aktywna;
    if not found then raise exception 'Nie dowozimy do tej miejscowości z wybranego lokalu'; end if;
  end if;

  -- kod rabatowy (rabat od wartości produktów)
  if v_kod_txt is not null then
    select * into v_kod from kody_rabatowe where kod = v_kod_txt;
    if not found or not v_kod.aktywny then v_kod_info := 'Kod jest nieaktywny';
    elsif v_kod.wazny_od is not null and now() < v_kod.wazny_od then v_kod_info := 'Kod jeszcze nie obowiązuje';
    elsif v_kod.wazny_do is not null and now() > v_kod.wazny_do then v_kod_info := 'Kod wygasł';
    elsif v_kod.max_uzyc is not null and v_kod.uzyto >= v_kod.max_uzyc then v_kod_info := 'Limit użyć kodu wyczerpany';
    elsif v_suma < v_kod.min_wartosc then v_kod_info := format('Kod działa od %s zł', v_kod.min_wartosc);
    elsif v_kod.max_na_klienta is not null and length(v_tel) >= 9 and
          (select count(*) from zamowienia z where z.kod_rabatowy = v_kod.kod and z.telefon = v_tel
             and z.status <> 'anulowane') >= v_kod.max_na_klienta then v_kod_info := 'Kod został już przez Ciebie wykorzystany';
    else
      v_rabat := case when v_kod.typ = 'proc' then round(v_suma * v_kod.wartosc / 100, 2)
                      else least(v_suma, v_kod.wartosc) end;
      v_kod_info := 'ok';
    end if;
  end if;

  return jsonb_build_object(
    'pozycje', v_linie,
    'produkty_suma', round(v_suma, 2),
    'opakowania', round(v_opak_suma, 2),
    'dostawa', round(v_dostawa, 2),
    'rabat', round(v_rabat, 2),
    'razem', round(v_suma + v_opak_suma + v_dostawa - v_rabat, 2),
    'kod', case when v_kod_info = 'ok' then v_kod_txt end,
    'kod_info', v_kod_info,
    'min_zamowienie', v_min,
    'brakuje_do_min', greatest(0, round(v_min - (v_suma - v_rabat), 2))
  );
end $$;

-- podgląd koszyka dla strony (te same wyliczenia co przy zamówieniu)
create or replace function podglad_koszyka(p jsonb)
returns jsonb language sql stable security definer set search_path = public as $$
  select _wycen(p)
$$;

-- ---------------------------------------------------------------- złożenie zamówienia
create or replace function zloz_zamowienie(p jsonb)
returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare
  w         jsonb;
  v_lokal   int  := (p->>'lokal_id')::int;
  v_tryb    text := p->>'tryb';
  v_tel     text := regexp_replace(coalesce(p->>'telefon',''), '\D', '', 'g');
  v_email   text := nullif(lower(trim(p->>'email')),'');
  v_plat    text := p->>'platnosc';
  v_kiedy   timestamptz := nullif(p->>'na_kiedy','')::timestamptz;
  v_id      bigint; v_token uuid; v_numer text; v_dzis int;
  v_poz     jsonb;
begin
  if (_ust('zamawianie_wylaczone','false'))::text::boolean then
    raise exception 'Zamawianie online jest chwilowo wyłączone. Zadzwoń do lokalu.';
  end if;

  w := _wycen(p);

  if (w->>'brakuje_do_min')::numeric > 0 then
    raise exception 'Minimalna wartość zamówienia to % zł (brakuje % zł)', w->>'min_zamowienie', w->>'brakuje_do_min';
  end if;
  if nullif(p->>'kod','') is not null and w->>'kod_info' <> 'ok' then
    raise exception '%', w->>'kod_info';
  end if;

  -- termin
  if v_kiedy is null then
    if not _otwarte(v_lokal) then raise exception 'Lokal jest teraz zamknięty – wybierz godzinę realizacji'; end if;
  else
    if v_kiedy < now() + interval '20 minutes' or v_kiedy > now() + interval '2 days' then
      raise exception 'Nieprawidłowa godzina realizacji';
    end if;
    if not _otwarte(v_lokal, v_kiedy) then raise exception 'Lokal jest wtedy zamknięty'; end if;
  end if;

  -- klient
  if length(v_tel) < 9 or length(v_tel) > 12 then raise exception 'Podaj poprawny numer telefonu'; end if;
  if coalesce(trim(p->>'imie'),'') = '' then raise exception 'Podaj imię'; end if;
  if v_email is not null and v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'Nieprawidłowy e-mail'; end if;
  if v_tryb = 'dostawa' then
    if nullif(p->>'strefa_id','') is null then raise exception 'Wybierz miejscowość dostawy'; end if;
    if coalesce(trim(p->>'ulica'),'') = '' or coalesce(trim(p->>'nr_domu'),'') = '' then
      raise exception 'Podaj ulicę i numer domu';
    end if;
  end if;
  if coalesce((p->>'faktura')::boolean, false) then
    if regexp_replace(coalesce(p->>'nip',''), '\D', '', 'g') !~ '^\d{10}$' then raise exception 'NIP musi mieć 10 cyfr'; end if;
    if coalesce(trim(p->>'firma'),'') = '' then raise exception 'Podaj nazwę firmy do faktury'; end if;
  end if;

  -- płatność
  if v_plat = 'online' then
    if not (_ust('platnosc_online','true'))::text::boolean then raise exception 'Płatność online jest wyłączona'; end if;
    if v_email is null then raise exception 'Do płatności online podaj e-mail'; end if;
  elsif v_plat = 'gotowka' then
    if not (_ust('platnosc_gotowka','false'))::text::boolean then raise exception 'Płatność gotówką jest wyłączona'; end if;
  elsif v_plat = 'karta' then
    if not (_ust('platnosc_karta','false'))::text::boolean then raise exception 'Płatność kartą przy odbiorze jest wyłączona'; end if;
  else
    raise exception 'Wybierz sposób płatności';
  end if;

  -- antyspam
  if (select count(*) from zamowienia where telefon = v_tel and utworzono > now() - interval '10 minutes') >= 3 then
    raise exception 'Za dużo zamówień z tego numeru. Zadzwoń do lokalu.';
  end if;

  -- numer dzienny per lokal: 3/06/10/2026
  perform pg_advisory_xact_lock(hashtext('zam_numer_' || v_lokal));
  select count(*) + 1 into v_dzis from zamowienia
    where lokal_id = v_lokal and (utworzono at time zone 'Europe/Warsaw')::date = _teraz_pl()::date;
  v_numer := v_dzis || '/' || to_char(_teraz_pl(), 'DD/MM/YYYY');

  insert into zamowienia (numer, lokal_id, status, tryb, na_kiedy, imie, nazwisko, telefon, email,
    miejscowosc, ulica, nr_domu, nr_lokalu, pietro, strefa_id, uwagi,
    faktura, nip, firma, adres_firmy, platnosc, platnosc_status,
    produkty_suma, opakowania, dostawa, rabat, razem, kod_rabatowy)
  values (v_numer, v_lokal,
    case when v_plat = 'online' then 'oczekuje_na_platnosc' else 'nowe' end,
    v_tryb, v_kiedy, left(trim(p->>'imie'),60), left(nullif(trim(p->>'nazwisko'),''),60), v_tel, v_email,
    case when v_tryb = 'dostawa' then (select miejscowosc from strefy where id = (p->>'strefa_id')::int) end,
    case when v_tryb = 'dostawa' then left(trim(p->>'ulica'),120) end,
    case when v_tryb = 'dostawa' then left(trim(p->>'nr_domu'),20) end,
    case when v_tryb = 'dostawa' then left(nullif(trim(p->>'nr_lokalu'),''),20) end,
    case when v_tryb = 'dostawa' then left(nullif(trim(p->>'pietro'),''),20) end,
    case when v_tryb = 'dostawa' then (p->>'strefa_id')::int end,
    left(nullif(trim(p->>'uwagi'),''),500),
    coalesce((p->>'faktura')::boolean,false),
    nullif(regexp_replace(coalesce(p->>'nip',''),'\D','','g'),''),
    left(nullif(trim(p->>'firma'),''),200), left(nullif(trim(p->>'adres_firmy'),''),300),
    v_plat, case when v_plat = 'online' then 'oczekuje' else 'brak' end,
    (w->>'produkty_suma')::numeric, (w->>'opakowania')::numeric, (w->>'dostawa')::numeric,
    (w->>'rabat')::numeric, (w->>'razem')::numeric, w->>'kod')
  returning id, token into v_id, v_token;

  for v_poz in select * from jsonb_array_elements(w->'pozycje') loop
    insert into zamowienia_pozycje (zamowienie_id, produkt_id, nazwa, rozmiar, ilosc, cena_jedn, opakowanie, sos_gratis, dodatki, suma)
    values (v_id, (v_poz->>'produkt_id')::int, v_poz->>'nazwa', v_poz->>'rozmiar', (v_poz->>'ilosc')::int,
      (v_poz->>'cena_jedn')::numeric, (v_poz->>'opakowanie')::numeric, v_poz->>'sos_gratis', v_poz->'dodatki',
      (v_poz->>'suma')::numeric);
  end loop;

  if w->>'kod' is not null then
    update kody_rabatowe set uzyto = uzyto + 1 where kod = w->>'kod';
  end if;

  return jsonb_build_object('id', v_id, 'numer', v_numer, 'token', v_token,
    'razem', w->'razem', 'platnosc', v_plat,
    'status', case when v_plat = 'online' then 'oczekuje_na_platnosc' else 'nowe' end);
end $$;

-- ---------------------------------------------------------------- status dla klienta
create or replace function status_zamowienia(p_token uuid)
returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'id', z.id, 'numer', z.numer, 'status', z.status, 'platnosc', z.platnosc,
    'platnosc_status', z.platnosc_status, 'tryb', z.tryb, 'razem', z.razem,
    'utworzono', z.utworzono, 'na_kiedy', z.na_kiedy,
    'lokal', (select jsonb_build_object('nazwa', l.nazwa, 'telefon', l.telefon) from lokale l where l.id = z.lokal_id),
    'pozycje', (select coalesce(jsonb_agg(jsonb_build_object('nazwa', q.nazwa, 'rozmiar', q.rozmiar,
               'ilosc', q.ilosc, 'suma', q.suma) order by q.id), '[]')
               from zamowienia_pozycje q where q.zamowienie_id = z.id))
  from zamowienia z where z.token = p_token
$$;

-- ---------------------------------------------------------------- płatności (tylko service_role)
-- start nowej próby płatności: zwraca dane do podpisu Autopay
create or replace function platnosc_start(p_token uuid)
returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare z zamowienia%rowtype;
begin
  select * into z from zamowienia where token = p_token for update;
  if not found then raise exception 'Nie ma takiego zamówienia'; end if;
  if z.platnosc <> 'online' then raise exception 'To zamówienie nie jest płatne online'; end if;
  if z.platnosc_status = 'oplacone' then raise exception 'Zamówienie jest już opłacone'; end if;
  if z.status <> 'oczekuje_na_platnosc' then raise exception 'Zamówienie nie czeka na płatność'; end if;
  if z.utworzono < now() - interval '2 hours' then raise exception 'Zamówienie wygasło – złóż nowe'; end if;
  if z.platnosc_proba >= 5 then raise exception 'Za dużo prób płatności – zadzwoń do lokalu'; end if;
  update zamowienia set platnosc_proba = platnosc_proba + 1, platnosc_status = 'oczekuje', zmieniono = now()
    where id = z.id;
  insert into platnosci_log (zamowienie_id, zdarzenie, dane)
    values (z.id, 'start', jsonb_build_object('proba', z.platnosc_proba + 1, 'kwota', z.razem));
  return jsonb_build_object('id', z.id, 'lokal_id', z.lokal_id, 'numer', z.numer,
    'order_id', 'CP' || z.id || '-' || (z.platnosc_proba + 1),
    'kwota', to_char(z.razem, 'FM999999990.00'), 'email', z.email);
end $$;

-- wynik z ITN Autopay. Zwraca true, gdy powiadomienie pasuje do zamówienia.
create or replace function platnosc_wynik(p_order_id text, p_remote_id text, p_status text, p_kwota numeric, p_dane jsonb)
returns boolean language plpgsql volatile security definer set search_path = public as $$
declare v_id bigint; z zamowienia%rowtype;
begin
  v_id := nullif(substring(p_order_id from '^CP(\d+)-\d+$'), '')::bigint;
  select * into z from zamowienia where id = v_id for update;
  if not found then
    insert into platnosci_log (zdarzenie, dane) values ('itn_nieznane', p_dane);
    return false;
  end if;
  insert into platnosci_log (zamowienie_id, zdarzenie, dane) values (z.id, 'itn_' || lower(p_status), p_dane);
  if p_kwota <> z.razem then
    insert into platnosci_log (zamowienie_id, zdarzenie, dane)
      values (z.id, 'itn_zla_kwota', jsonb_build_object('oczekiwano', z.razem, 'otrzymano', p_kwota));
    return false;
  end if;
  if p_status = 'SUCCESS' and z.platnosc_status <> 'oplacone' then
    update zamowienia set platnosc_status = 'oplacone', autopay_remote_id = p_remote_id,
      status = case when status = 'oczekuje_na_platnosc' then 'nowe' else status end, zmieniono = now()
      where id = z.id;
  elsif p_status = 'FAILURE' and z.platnosc_status <> 'oplacone' then
    update zamowienia set platnosc_status = 'blad', autopay_remote_id = p_remote_id, zmieniono = now()
      where id = z.id;
  end if;
  return true;   -- PENDING też potwierdzamy (Autopay przestanie ponawiać)
end $$;

-- ---------------------------------------------------------------- uprawnienia
revoke all on all functions in schema public from public, anon, authenticated;
grant execute on function menu_publiczne(int)            to anon, authenticated;
grant execute on function podglad_koszyka(jsonb)         to anon, authenticated;
grant execute on function zloz_zamowienie(jsonb)         to anon, authenticated;
grant execute on function status_zamowienia(uuid)        to anon, authenticated;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'grant execute on function platnosc_start(uuid) to service_role';
    execute 'grant execute on function platnosc_wynik(text,text,text,numeric,jsonb) to service_role';
  end if;
end $$;
