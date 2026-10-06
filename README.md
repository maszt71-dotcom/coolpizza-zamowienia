# Cool Pizza – zamówienia online

Własny system zamówień dla Cool Pizza (Ostrów Wielkopolski, Kalisz), zbudowany na wzór obecnej zamawiarki Appinet.

| Część | Plik | Gdzie działa |
|---|---|---|
| Strona zamówień dla klienta | `web/index.html` | Netlify / Cloudflare Pages |
| Baza, ceny, logika zamówień | `supabase/schema.sql`, `supabase/seed.sql` | Supabase (`coolpizza-zamowienia`) |
| Płatności Autopay | `supabase/functions/autopay-start`, `autopay-itn` | Supabase Edge Functions |
| Panel kuchni i administracji | `streamlit_app.py` | Streamlit Community Cloud |

## Co potrafi

**Klient:** wybór lokalu, menu z bazy (rozmiary 30–60 cm, sos gratis, płatne dodatki), strefy dostawy z dopłatą per miejscowość,
minimum zamówienia, kody rabatowe, zamówienie na teraz lub na godzinę, dane do faktury, płatność online Autopay (BLIK, przelew, karta)
lub przy odbiorze, strona statusu zamówienia z ponowieniem płatności.

**Bezpieczeństwo:** ceny, dostawę, rabat i minimum liczy baza (`_wycen`) – podmiana ceny w przeglądarce nic nie da.
Strona używa tylko klucza publicznego, który nie widzi żadnej tabeli (RLS), tylko 4 funkcje.
Płatność: podpis SHA-256, weryfikacja podpisu i kwoty w ITN, zamówienie trafia do kuchni dopiero po opłaceniu.

**Panel (PIN obsługi):** zamówienia na żywo ze statusami Nowe → W przygotowaniu → W drodze / Do odbioru → Zrealizowane,
dźwięk przy nowym zamówieniu, raport z CSV.
**Panel (PIN właściciela):** dodatkowo menu i ceny, dostępność produktów per lokal, dodatki i sosy, strefy dostawy,
kody rabatowe, ustawienia (płatności, minimum, wyłączenie zamawiania, komunikat), godziny otwarcia.

## Wdrożenie

### 1. Baza (Supabase → SQL Editor)
1. Wklej `supabase/schema.sql` → **Run**.
2. Wklej `supabase/seed.sql` → **Run** (jeden raz – menu, dodatki, strefy, ustawienia z Appinetu).

### 2. Płatności (Supabase → Edge Functions)
1. **Deploy a new function** → nazwa `autopay-start` → wklej `supabase/functions/autopay-start/index.ts` → Deploy.
2. To samo dla `autopay-itn`.
3. W **obu** funkcjach: Details → **wyłącz „Enforce JWT verification”** (Autopay i strona nie wysyłają tokenu JWT).
4. **Edge Functions → Secrets**:
   - `AUTOPAY_CONFIG` = `{"5":{"service_id":"TWOJ_SERVICE_ID","key":"TWOJ_KLUCZ"}}` (5 = Ostrów, 2 = Kalisz)
   - `AUTOPAY_URL` = `https://testpay.autopay.eu/payment` (testy) → potem `https://pay.autopay.eu/payment`
5. W panelu Autopay ustaw dla serwisu:
   - adres ITN: `https://sliqjrarbxwfpjhdrvbs.supabase.co/functions/v1/autopay-itn`
   - adres powrotu: adres strony, np. `https://zamow.coolpizza.pl/`

> Adres ITN jest jeden na serwis Autopay. Na czas testów poproś Autopay o **drugi serwis**,
> żeby nie odciąć potwierdzeń płatności obecnej strony Appinet.

### 3. Panel – Streamlit Cloud
Create app → repo `coolpizza-zamowienia`, branch `main`, plik `streamlit_app.py`.
Secrets: patrz `.streamlit/secrets.toml.example`.

### 4. Strona – Netlify
Import from Git → to repo, *Publish directory*: `web`, bez komendy build. Potem domena, np. `zamow.coolpizza.pl`.

## Testy
`supabase/tests.sql` – testy bazy (wycena, płatność, walidacje, uprawnienia). Wycena sprawdzona na prawdziwych
zamówieniach z Appinetu (#1821: 98,50 zł, #1823: 45,50 zł). Pełny przepływ (strona → zamówienie → podpis →
atrapa Autopay → ITN → status) przetestowany lokalnie na PostgreSQL + PostgREST.

## Do sprawdzenia przed startem
- [ ] Strefy: 36 z 45 miejscowości z Appinetu (9 panel nie pokazał). Kody pocztowe 1:1 z Appinetu – Czartki, Czajków i Nowe Skalmierzyce do weryfikacji.
- [ ] Opakowania: Appinet ma ustawienie `{24:1.00;50:3.00}` (prawdopodobnie +1 zł dla 40 cm) – tu domyślnie 0 zł, ustaw w panelu → Menu → Rozmiary.
- [ ] Regulamin i polityka prywatności – obecne linki prowadzą do stron Appinetu; potrzebne własne dokumenty.
- [ ] Napoli, Marsjańska i Sushi oznaczone jako „ryba” (w Appinecie były „bez mięsa”).
- [ ] Maile/SMS z potwierdzeniem – kolejny etap.
