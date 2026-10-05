# Cool Pizza – zamówienia online

Własny system zamówień dla Cool Pizza, ul. Śmigielskiego 20, Ostrów Wielkopolski.

| Część | Plik | Gdzie działa |
|---|---|---|
| Strona zamówień dla klienta | `web/index.html` | Netlify / Cloudflare Pages / dowolny hosting |
| Baza i funkcja przyjmowania zamówień | `supabase/schema.sql` | Supabase (projekt `coolpizza-zamowienia`) |
| Panel kuchni | `streamlit_app.py` | Streamlit Community Cloud |

## Uruchomienie

### 1. Baza (zrobione)
`supabase/schema.sql` wklejony w Supabase → SQL Editor → Run.

### 2. Panel kuchni
1. share.streamlit.io → **Create app** → wybierz to repo, branch `main`, plik `streamlit_app.py`.
2. **Advanced settings → Secrets** – wklej zawartość `.streamlit/secrets.toml.example` z prawdziwym kluczem secret i PIN-em.
3. Jeśli pojawi się „Invalid API key”, użyj klucza **service_role** z zakładki *Legacy API Keys*.

### 3. Strona zamówień
Netlify → **Add new site → Import from Git** → to repo, *Publish directory*: `web`, bez komendy build.
Każdy `git push` aktualizuje stronę automatycznie.

## Konfiguracja strony
Wszystko w bloku `CONFIG` na początku skryptu w `web/index.html`:
- `dostawa.koszt`, `dostawa.darmowaOd`, `dostawa.minimum`
- `kody` – kody rabatowe
- `supabase.url`, `supabase.anonKey` – klucz **publishable** (publiczny z założenia)

Menu i ceny: tablice `TIER`, `PIZZE`, `ADDONS`, `OTHER`.

## Bezpieczeństwo
- Strona używa tylko klucza publishable. Może wyłącznie wywołać funkcję `zloz_zamowienie` – nie czyta i nie zmienia tabeli (RLS bez polityk dla `anon`).
- Klucz secret / service_role jest tylko w Secrets panelu kuchni. Nigdy w repo.
- Panel kuchni chroniony PIN-em.

## Do zrobienia przed pełnym startem
- [ ] Regulamin i polityka prywatności (RODO)
- [ ] Koszt i strefy dostawy
- [ ] Przeliczanie cen po stronie bazy
- [ ] Menu Kalisz
- [ ] Płatności online, SMS z potwierdzeniem
