-- Testy bazy (lokalny PostgreSQL). Uruchomienie: psql -f schema.sql -f seed.sql -f tests.sql
\set ON_ERROR_STOP 0
\pset footer off
create or replace function pg_temp.koszyk(p_tryb text, p_strefa text, p_kod text default null, p_plat text default 'online')
returns jsonb language sql as $$
  select jsonb_build_object('lokal_id',5,'tryb',p_tryb,
    'strefa_id',(select id from strefy where miejscowosc=p_strefa),
    'imie','Test','telefon','600 100 200','email','test@example.com','ulica','Testowa','nr_domu','1',
    'platnosc',p_plat,'kod',p_kod,
    -- realizacja jutro o 13:00 (żeby test nie zależał od godziny uruchomienia)
    'na_kiedy', (((now() at time zone 'Europe/Warsaw')::date + 1 + time '13:00') at time zone 'Europe/Warsaw'),
    'pozycje',jsonb_build_array(jsonb_build_object(
       'produkt_id',(select id from produkty where nazwa='CLASIC'),
       'rozmiar_id',(select id from rozmiary where nazwa='50 cm'),'ilosc',1)))
$$;

\echo '--- 1. zamówienie online (dostawa Przygodzice 75 + 20 = 95.00)'
select zloz_zamowienie(pg_temp.koszyk('dostawa','Przygodzice')) - 'token' as wynik;
select numer, status, platnosc_status, razem from zamowienia order by id desc limit 1;

\echo '--- 2. start płatności i ITN SUCCESS z dobrą kwotą → status nowe/oplacone'
select platnosc_start((select token from zamowienia order by id desc limit 1)) as start;
select platnosc_wynik('CP' || (select max(id) from zamowienia) || '-1', 'RMT1', 'SUCCESS', 95.00, '{}') as itn_ok;
select status, platnosc_status, autopay_remote_id from zamowienia order by id desc limit 1;

\echo '--- 3. ITN z ZŁĄ kwotą → odrzucone, status bez zmian'
select zloz_zamowienie(pg_temp.koszyk('odbior',null)) ->> 'numer' as numer2;
select platnosc_start((select token from zamowienia order by id desc limit 1)) ->> 'order_id' as order_id;
select platnosc_wynik('CP' || (select max(id) from zamowienia) || '-1', 'RMT2', 'SUCCESS', 1.00, '{}') as itn_zla_kwota;
select status, platnosc_status from zamowienia order by id desc limit 1;

\echo '--- 4. błędy walidacji (oczekiwane komunikaty)'
select zloz_zamowienie(pg_temp.koszyk('dostawa',null));                          -- brak miejscowości
select zloz_zamowienie(pg_temp.koszyk('dostawa','Przygodzice', null, 'gotowka')); -- gotówka wyłączona
select zloz_zamowienie(pg_temp.koszyk('dostawa','Przygodzice') || '{"email":""}');-- online bez e-maila
select zloz_zamowienie(pg_temp.koszyk('odbior',null) || jsonb_build_object('pozycje',jsonb_build_array(jsonb_build_object(
  'produkt_id',(select id from produkty where nazwa='PEPSI 0,5 L'),'ilosc',1))));    -- poniżej minimum 45 zł
select zloz_zamowienie(pg_temp.koszyk('odbior',null,'NIEMA'));                      -- zły kod

\echo '--- 5. kod rabatowy 10% (95 → produkty 75, rabat 7.50, razem 87.50)'
insert into kody_rabatowe (kod, typ, wartosc, max_na_klienta) values ('TEST10','proc',10,1) on conflict do nothing;
select podglad_koszyka(pg_temp.koszyk('dostawa','Przygodzice','test10')) - 'pozycje' as podglad;

\echo '--- 6. niedostępny produkt'
insert into niedostepne values (5, (select id from produkty where nazwa='CLASIC')) on conflict do nothing;
select podglad_koszyka(pg_temp.koszyk('odbior',null));
delete from niedostepne;

\echo '--- 7. uprawnienia klucza publicznego (anon)'
set role anon;
select count(*) from zamowienia;                                         -- ma być: brak dostępu
select platnosc_start((select gen_random_uuid()));                       -- ma być: brak dostępu
select jsonb_array_length(menu_publiczne(5)->'kategorie') as anon_menu_ok;
reset role;

\echo '--- 8. ponowne uruchomienie schematu nie kasuje zamówień'
select count(*) as zamowien_przed from zamowienia;
