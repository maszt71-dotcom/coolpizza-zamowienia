"""
Cool Pizza – panel zamówień online (kuchnia / bufet)

Uruchomienie lokalnie:   streamlit run kuchnia_app.py
Streamlit Cloud: wrzuć ten plik + requirements.txt do repo, sekrety w App settings → Secrets.

.streamlit/secrets.toml:
    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_KEY = "service_role ..."   # klucz service_role – TYLKO tutaj, nigdy na stronie klienta
    KUCHNIA_PIN  = "1234"
"""

from datetime import datetime, timedelta, timezone
from html import escape as e
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

TZ = ZoneInfo("Europe/Warsaw")
ODSWIEZ_CO_S = 15

STATUSY = {
    "nowe":            ("NOWE",            "#9be22d"),
    "w_przygotowaniu": ("W PRZYGOTOWANIU", "#ffb020"),
    "w_drodze":        ("W DRODZE",        "#3fb6ff"),
    "do_odbioru":      ("DO ODBIORU",      "#3fb6ff"),
    "zrealizowane":    ("ZREALIZOWANE",    "#7c8a74"),
    "anulowane":       ("ANULOWANE",       "#ff5a4a"),
}
AKTYWNE = ["nowe", "w_przygotowaniu", "w_drodze", "do_odbioru"]


def nastepny_status(z: dict) -> tuple[str, str] | None:
    s = z["status"]
    if s == "nowe":
        return "w_przygotowaniu", "▶ Przyjmij do pieca"
    if s == "w_przygotowaniu":
        return ("w_drodze", "🛵 Wydaj kierowcy") if z["tryb"] == "dostawa" else ("do_odbioru", "✅ Gotowe do odbioru")
    if s in ("w_drodze", "do_odbioru"):
        return "zrealizowane", "✔ Zrealizowane"
    return None


# ---------------------------------------------------------------- konfiguracja
st.set_page_config(page_title="Cool Pizza – Zamówienia", page_icon="🍕", layout="wide")

st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"], .stMarkdown, .stButton button { font-family: 'DM Sans', sans-serif; }
.stApp { background: #0b0d0a; color: #eef3e8; }
h1, h2, h3 { font-family: 'Syne', sans-serif !important; letter-spacing: .3px; }
.card { background: rgba(30,36,27,.65); border: 1px solid #2c3428; border-radius: 16px;
        padding: 14px 16px 6px; backdrop-filter: blur(6px); margin-bottom: 6px; }
.card.nowe { border-color: #9be22d; box-shadow: 0 0 0 1px #9be22d55, 0 0 22px #9be22d22; }
.hdr { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
.nr { font-family:'Syne',sans-serif; font-weight:800; font-size:22px; }
.badge { font-size:11px; font-weight:700; letter-spacing:.8px; padding:3px 9px; border-radius:999px; color:#0b0d0a; }
.meta { color:#9aa591; font-size:13.5px; margin:4px 0 8px; }
.poz { margin:0 0 4px; font-size:15px; }
.poz small { color:#9aa591; display:block; margin-left:22px; }
.uw { background:#ffb02022; border-left:3px solid #ffb020; padding:6px 10px; border-radius:6px; margin:6px 0; font-size:14px; }
.suma { font-weight:700; font-size:17px; margin:6px 0 10px; }
.metric { background: rgba(30,36,27,.65); border:1px solid #2c3428; border-radius:14px; padding:12px 14px; }
.metric b { display:block; font-family:'Syne',sans-serif; font-size:26px; }
.metric span { color:#9aa591; font-size:12.5px; text-transform:uppercase; letter-spacing:.7px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- logowanie PIN
if not st.session_state.get("ok"):
    st.markdown("## 🍕 Cool Pizza – panel zamówień")
    pin = st.text_input("PIN", type="password")
    if st.button("Wejdź"):
        if pin == st.secrets.get("KUCHNIA_PIN", ""):
            st.session_state.ok = True
            st.rerun()
        else:
            st.error("Zły PIN.")
    st.stop()


@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def pobierz(od: datetime) -> list[dict]:
    r = (db().table("zamowienia").select("*")
         .gte("utworzono", od.astimezone(timezone.utc).isoformat())
         .order("utworzono", desc=True).limit(500).execute())
    return r.data or []


def zmien_status(zid: int, status: str):
    db().table("zamowienia").update(
        {"status": status, "zmieniono": datetime.now(timezone.utc).isoformat()}
    ).eq("id", zid).execute()


def zl(x) -> str:
    return f"{float(x or 0):,.2f} zł".replace(",", " ").replace(".", ",")


def godz(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).strftime("%H:%M")


def ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def minut_temu(iso: str) -> int:
    return int((datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() // 60)


# ---------------------------------------------------------------- nagłówek
c1, c2 = st.columns([3, 2])
with c1:
    st.markdown("## 🍕 Zamówienia online")
with c2:
    widok = st.radio("Widok", ["Aktywne", "Dzisiaj – wszystkie", "Historia 7 dni"],
                     horizontal=True, label_visibility="collapsed")


def karta(z: dict):
    label, kolor = STATUSY[z["status"]]
    tryb = "🛵 DOSTAWA" if z["tryb"] == "dostawa" else "🏃 ODBIÓR"
    poz = "".join(
        f'<p class="poz"><b>{int(p.get("qty", 1))}×</b> {e(str(p.get("name", "")))}'
        + (f'<small>{e(str(p["desc"]))}</small>' if p.get("desc") else "") + "</p>"
        for p in (z.get("pozycje") or [])
    )
    adres = f"📍 {e(z['adres'])}<br>" if z.get("adres") else ""
    uwagi = f'<div class="uw">📝 {e(z["uwagi"])}</div>' if z.get("uwagi") else ""
    st.markdown(f"""
    <div class="card {z['status']}">
      <div class="hdr"><span class="nr">CP-{z['id']}</span>
        <span class="badge" style="background:{kolor}">{label}</span></div>
      <div class="meta">{tryb} · ⏰ {e(z.get('kiedy') or '—')} · wpadło {godz(z['utworzono'])} ({minut_temu(z['utworzono'])} min)<br>
        👤 {e(z['imie'])} · 📞 <b style="color:#eef3e8">{e(z['telefon'])}</b><br>{adres}💳 {e(z.get('platnosc') or '—')}</div>
      {poz}{uwagi}
      <div class="suma">Razem: {zl(z['razem'])}{' · rabat ' + zl(z['rabat']) if float(z.get('rabat') or 0) else ''}</div>
    </div>""", unsafe_allow_html=True)

    nxt = nastepny_status(z)
    b1, b2 = st.columns([3, 1])
    if nxt and b1.button(nxt[1], key=f"n{z['id']}", use_container_width=True, type="primary"):
        zmien_status(z["id"], nxt[0])
        st.rerun()
    if z["status"] in AKTYWNE:
        if b2.button("✖", key=f"a{z['id']}", help="Anuluj zamówienie", use_container_width=True):
            st.session_state[f"anuluj_{z['id']}"] = True
        if st.session_state.get(f"anuluj_{z['id']}"):
            st.warning(f"Anulować CP-{z['id']}?")
            t1, t2 = st.columns(2)
            if t1.button("Tak, anuluj", key=f"ay{z['id']}", use_container_width=True):
                zmien_status(z["id"], "anulowane")
                st.session_state.pop(f"anuluj_{z['id']}")
                st.rerun()
            if t2.button("Nie", key=f"an{z['id']}", use_container_width=True):
                st.session_state.pop(f"anuluj_{z['id']}")
                st.rerun()


@st.fragment(run_every=ODSWIEZ_CO_S)
def panel():
    teraz = datetime.now(TZ)
    poczatek_dnia = teraz.replace(hour=0, minute=0, second=0, microsecond=0)
    od = poczatek_dnia - timedelta(days=6) if widok == "Historia 7 dni" else poczatek_dnia

    try:
        dane = pobierz(od)
    except Exception as e:
        st.error(f"Brak połączenia z bazą: {e}. Sprawdź, czy projekt Supabase nie jest wstrzymany.")
        return

    dzis = [z for z in dane if ts(z["utworzono"]) >= poczatek_dnia]
    ok = [z for z in dzis if z["status"] != "anulowane"]
    nowe = [z for z in dane if z["status"] == "nowe"]

    m = st.columns(4)
    for col, (lab, val) in zip(m, [
        ("Nowe", len(nowe)),
        ("W realizacji", sum(z["status"] in AKTYWNE[1:] for z in dane)),
        ("Dziś zamówień", len(ok)),
        ("Dziś obrót online", zl(sum(float(z["razem"]) for z in ok))),
    ]):
        col.markdown(f'<div class="metric"><span>{lab}</span><b>{val}</b></div>', unsafe_allow_html=True)

    # sygnał o nowym zamówieniu (działa po pierwszym kliknięciu w stronę – blokada autoplay przeglądarki)
    znane = st.session_state.setdefault("znane_nowe", {z["id"] for z in nowe})
    swieze = [z for z in nowe if z["id"] not in znane]
    if swieze:
        st.toast(f"🔔 Nowe zamówienie: {', '.join('CP-' + str(z['id']) for z in swieze)}")
        components.html("""<script>try{const a=new (window.AudioContext||window.webkitAudioContext)();
        [0,.25,.5].forEach(t=>{const o=a.createOscillator(),g=a.createGain();o.frequency.value=880;
        o.connect(g);g.connect(a.destination);g.gain.setValueAtTime(.25,a.currentTime+t);
        o.start(a.currentTime+t);o.stop(a.currentTime+t+.18)})}catch(e){}</script>""", height=0)
        znane.update(z["id"] for z in swieze)

    st.caption(f"Odświeżanie co {ODSWIEZ_CO_S} s · ostatnio {teraz.strftime('%H:%M:%S')}")

    if widok == "Aktywne":
        lista = sorted([z for z in dane if z["status"] in AKTYWNE],
                       key=lambda z: (AKTYWNE.index(z["status"]), z["utworzono"]))
        if not lista:
            st.info("Brak aktywnych zamówień.")
            return
        kol = st.columns(3)
        for i, z in enumerate(lista):
            with kol[i % 3]:
                karta(z)
    else:
        if not dane:
            st.info("Brak zamówień w tym okresie.")
            return
        df = pd.DataFrame([{
            "Nr": f"CP-{z['id']}",
            "Data": datetime.fromisoformat(z["utworzono"].replace("Z", "+00:00")).astimezone(TZ).strftime("%d.%m %H:%M"),
            "Status": STATUSY[z["status"]][0],
            "Tryb": z["tryb"],
            "Klient": z["imie"],
            "Telefon": z["telefon"],
            "Adres": z.get("adres") or "",
            "Pozycje": "; ".join(f"{p.get('qty', 1)}× {p.get('name', '')}" for p in z.get("pozycje") or []),
            "Płatność": z.get("platnosc") or "",
            "Razem": float(z["razem"]),
        } for z in dane])
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"Razem": st.column_config.NumberColumn(format="%.2f zł")})
        zreal = df[df["Status"] != "ANULOWANE"]
        st.markdown(f"**Suma (bez anulowanych): {zl(zreal['Razem'].sum())} · {len(zreal)} zamówień**")
        st.download_button("Pobierz CSV", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"zamowienia_online_{teraz:%Y%m%d}.csv", mime="text/csv")


panel()
