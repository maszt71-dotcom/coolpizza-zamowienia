"""
Cool Pizza – panel zamówień i administracji

Uruchomienie lokalne:  streamlit run streamlit_app.py
Streamlit Cloud → Settings → Secrets:
    SUPABASE_URL = "https://sliqjrarbxwfpjhdrvbs.supabase.co"
    SUPABASE_KEY = "klucz service_role / sb_secret_..."   # tylko tutaj, nigdy na stronie
    KUCHNIA_PIN  = "1111"   # obsługa: tylko zamówienia
    ADMIN_PIN    = "9999"   # właściciel: wszystko
"""

from datetime import date, datetime, timedelta, timezone
from html import escape as e
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

TZ = ZoneInfo("Europe/Warsaw")
ODSWIEZ_S = 15

STATUSY = {
    "oczekuje_na_platnosc": ("CZEKA NA PŁATNOŚĆ", "#7c8a74"),
    "nowe":                 ("NOWE",              "#9be22d"),
    "przyjete":             ("W PRZYGOTOWANIU",   "#ffb020"),
    "w_drodze":             ("W DRODZE",          "#3fb6ff"),
    "do_odbioru":           ("DO ODBIORU",        "#3fb6ff"),
    "zrealizowane":         ("ZREALIZOWANE",      "#7c8a74"),
    "anulowane":            ("ANULOWANE",         "#ff5a4a"),
}
AKTYWNE = ["nowe", "przyjete", "w_drodze", "do_odbioru"]
PLATNOSC = {"online": "online (Autopay)", "gotowka": "gotówka", "karta": "karta przy odbiorze"}

st.set_page_config(page_title="Cool Pizza – panel", page_icon="🍕", layout="wide")
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"], .stMarkdown, .stButton button { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Syne', sans-serif !important; letter-spacing: .3px; }
.card { background: rgba(30,36,27,.65); border: 1px solid #2c3428; border-radius: 16px; padding: 14px 16px 8px; margin-bottom: 6px; }
.card.nowe { border-color: #9be22d; box-shadow: 0 0 0 1px #9be22d55, 0 0 22px #9be22d22; }
.hdr { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
.nr { font-family:'Syne',sans-serif; font-weight:800; font-size:21px; }
.badge { font-size:11px; font-weight:700; letter-spacing:.8px; padding:3px 9px; border-radius:999px; color:#0b0d0a; }
.meta { color:#9aa591; font-size:13.5px; margin:4px 0 8px; line-height:1.5; }
.meta b { color:#eef3e8; }
.poz { margin:0 0 4px; font-size:15px; }
.poz small { color:#9aa591; display:block; margin-left:24px; }
.uw { background:#ffb02022; border-left:3px solid #ffb020; padding:6px 10px; border-radius:6px; margin:6px 0; font-size:14px; }
.suma { font-weight:700; font-size:17px; margin:6px 0 8px; }
.plat-ok { color:#9be22d; } .plat-no { color:#ffb020; }
.metric { background: rgba(30,36,27,.65); border:1px solid #2c3428; border-radius:14px; padding:12px 14px; }
.metric b { display:block; font-family:'Syne',sans-serif; font-size:26px; }
.metric span { color:#9aa591; font-size:12.5px; text-transform:uppercase; letter-spacing:.7px; }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ logowanie
if "rola" not in st.session_state:
    st.markdown("## 🍕 Cool Pizza – panel")
    pin = st.text_input("PIN", type="password")
    if st.button("Wejdź", type="primary"):
        if pin and pin == st.secrets.get("ADMIN_PIN"):
            st.session_state.rola = "admin"
        elif pin and pin == st.secrets.get("KUCHNIA_PIN"):
            st.session_state.rola = "kuchnia"
        else:
            st.error("Zły PIN.")
            st.stop()
        st.rerun()
    st.stop()

ADMIN = st.session_state.rola == "admin"


@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def q(tabela: str, select: str = "*", **eq):
    zap = db().table(tabela).select(select)
    for k, v in eq.items():
        zap = zap.eq(k, v)
    return zap.execute().data or []


def zl(x) -> str:
    return f"{float(x or 0):,.2f} zł".replace(",", " ").replace(".", ",")


def ts(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ) if iso else None


def ok(msg: str):
    st.toast(msg, icon="✅")


# ------------------------------------------------------------------ dane wspólne
@st.cache_data(ttl=60)
def lokale():
    return q("lokale", "*")


LOKALE = {l["id"]: l["nazwa"].replace("COOL PIZZA ", "") for l in sorted(lokale(), key=lambda l: l["kolejnosc"])}

with st.sidebar:
    st.markdown("### 🍕 Cool Pizza")
    lokal_id = st.selectbox("Lokal", list(LOKALE), format_func=LOKALE.get)
    st.caption("Zalogowano: " + ("właściciel" if ADMIN else "obsługa"))
    if st.button("Wyloguj"):
        st.session_state.clear()
        st.rerun()

zakladki = ["🔥 Zamówienia", "📊 Raport"] + (["🍕 Menu i ceny", "🚫 Dostępność", "➕ Dodatki", "🛵 Strefy dostawy",
                                             "🏷️ Kody rabatowe", "⚙️ Ustawienia"] if ADMIN else [])
T = dict(zip(zakladki, st.tabs(zakladki)))


# ================================================================== ZAMÓWIENIA
def nastepny(z: dict):
    s = z["status"]
    if s == "nowe":
        return "przyjete", "▶ Przyjmij do pieca"
    if s == "przyjete":
        return ("w_drodze", "🛵 Wydaj kierowcy") if z["tryb"] == "dostawa" else ("do_odbioru", "✅ Gotowe do odbioru")
    if s in ("w_drodze", "do_odbioru"):
        return "zrealizowane", "✔ Zrealizowane"
    return None


def zmien_status(zid: int, status: str):
    db().table("zamowienia").update({"status": status, "zmieniono": datetime.now(timezone.utc).isoformat()}).eq("id", zid).execute()


def karta(z: dict, poz: list[dict]):
    label, kolor = STATUSY[z["status"]]
    tryb = "🛵 DOSTAWA" if z["tryb"] == "dostawa" else "🏃 ODBIÓR"
    kiedy = ts(z["na_kiedy"]).strftime("%d.%m %H:%M") if z.get("na_kiedy") else "jak najszybciej"
    wplyw = ts(z["utworzono"])
    min_temu = int((datetime.now(TZ) - wplyw).total_seconds() // 60)
    adres = ""
    if z["tryb"] == "dostawa":
        a = f"{z.get('ulica') or ''} {z.get('nr_domu') or ''}"
        if z.get("nr_lokalu"):
            a += f"/{z['nr_lokalu']}"
        if z.get("pietro"):
            a += f", piętro {z['pietro']}"
        adres = f"📍 <b>{e(a.strip())}</b>, {e(z.get('miejscowosc') or '')}<br>"
    plat_ok = z["platnosc"] != "online" or z["platnosc_status"] == "oplacone"
    plat = f'<span class="{"plat-ok" if plat_ok else "plat-no"}">💳 {PLATNOSC[z["platnosc"]]}' \
           f'{" – OPŁACONE" if z["platnosc"] == "online" and plat_ok else (" – NIEOPŁACONE" if z["platnosc"] == "online" else " – do pobrania")}</span>'
    fv = f"🧾 Faktura: {e(z.get('firma') or '')}, NIP {e(z.get('nip') or '')}<br>" if z.get("faktura") else ""
    linie = "".join(
        f'<p class="poz"><b>{int(p["ilosc"])}×</b> {e(p["nazwa"])}{" " + e(p["rozmiar"]) if p.get("rozmiar") else ""}'
        + (f'<small>sos gratis: {e(p["sos_gratis"])}</small>' if p.get("sos_gratis") else "")
        + (f'<small>+ {e(", ".join(d["nazwa"] for d in p["dodatki"]))}</small>' if p.get("dodatki") else "")
        + "</p>" for p in poz)
    uw = f'<div class="uw">📝 {e(z["uwagi"])}</div>' if z.get("uwagi") else ""
    st.markdown(f"""
    <div class="card {z['status']}">
      <div class="hdr"><span class="nr">{e(z['numer'])}</span><span class="badge" style="background:{kolor}">{label}</span></div>
      <div class="meta">{tryb} · ⏰ <b>{kiedy}</b> · wpadło {wplyw:%H:%M} ({min_temu} min)<br>
        👤 <b>{e(z['imie'])} {e(z.get('nazwisko') or '')}</b> · 📞 <b>{e(z['telefon'])}</b><br>{adres}{fv}{plat}</div>
      {linie}{uw}
      <div class="suma">Razem: {zl(z['razem'])}
        <small style="font-weight:400;color:#9aa591">{' · dostawa ' + zl(z['dostawa']) if float(z['dostawa']) else ''}{' · rabat ' + zl(z['rabat']) + ' (' + e(z.get('kod_rabatowy') or '') + ')' if float(z['rabat']) else ''}</small></div>
    </div>""", unsafe_allow_html=True)

    nxt = nastepny(z)
    c1, c2 = st.columns([3, 1])
    if nxt and c1.button(nxt[1], key=f"n{z['id']}", use_container_width=True, type="primary"):
        zmien_status(z["id"], nxt[0])
        st.rerun()
    if z["status"] in AKTYWNE:
        if c2.button("✖", key=f"a{z['id']}", help="Anuluj zamówienie", use_container_width=True):
            st.session_state[f"anuluj_{z['id']}"] = True
        if st.session_state.get(f"anuluj_{z['id']}"):
            if z["platnosc"] == "online" and z["platnosc_status"] == "oplacone":
                st.warning("Zamówienie jest opłacone online – zwrot zrób w panelu Autopay.")
            st.warning(f"Anulować {z['numer']}?")
            t1, t2 = st.columns(2)
            if t1.button("Tak, anuluj", key=f"ay{z['id']}", use_container_width=True):
                zmien_status(z["id"], "anulowane")
                st.session_state.pop(f"anuluj_{z['id']}")
                st.rerun()
            if t2.button("Nie", key=f"an{z['id']}", use_container_width=True):
                st.session_state.pop(f"anuluj_{z['id']}")
                st.rerun()


@st.fragment(run_every=ODSWIEZ_S)
def panel_zamowien():
    teraz = datetime.now(TZ)
    od = (teraz - timedelta(hours=36)).astimezone(timezone.utc).isoformat()
    try:
        dane = (db().table("zamowienia").select("*").eq("lokal_id", lokal_id).gte("utworzono", od)
                .order("utworzono").execute().data or [])
    except Exception as ex:
        st.error(f"Brak połączenia z bazą: {ex}")
        return
    dzis = [z for z in dane if ts(z["utworzono"]).date() == teraz.date() and z["status"] not in ("anulowane", "oczekuje_na_platnosc")]
    aktywne = [z for z in dane if z["status"] in AKTYWNE]
    czekaja = [z for z in dane if z["status"] == "oczekuje_na_platnosc"]

    m = st.columns(4)
    for col, (lab, val) in zip(m, [("Nowe", sum(z["status"] == "nowe" for z in dane)),
                                   ("W realizacji", len(aktywne)),
                                   ("Dziś zamówień", len(dzis)),
                                   ("Dziś obrót", zl(sum(float(z["razem"]) for z in dzis)))]):
        col.markdown(f'<div class="metric"><span>{lab}</span><b>{val}</b></div>', unsafe_allow_html=True)

    znane = st.session_state.setdefault("znane", {z["id"] for z in dane if z["status"] == "nowe"})
    swieze = [z for z in dane if z["status"] == "nowe" and z["id"] not in znane]
    if swieze:
        st.toast("🔔 Nowe zamówienie: " + ", ".join(z["numer"] for z in swieze))
        components.html("""<script>try{const a=new (window.AudioContext||window.webkitAudioContext)();
        [0,.25,.5].forEach(t=>{const o=a.createOscillator(),g=a.createGain();o.frequency.value=880;o.connect(g);
        g.connect(a.destination);g.gain.setValueAtTime(.25,a.currentTime+t);o.start(a.currentTime+t);
        o.stop(a.currentTime+t+.18)})}catch(e){}</script>""", height=0)
        znane.update(z["id"] for z in swieze)

    st.caption(f"Odświeżanie co {ODSWIEZ_S} s · {teraz:%H:%M:%S} · dźwięk działa po pierwszym kliknięciu w stronę")
    if not aktywne:
        st.info("Brak aktywnych zamówień.")
    else:
        ids = [z["id"] for z in aktywne]
        poz = db().table("zamowienia_pozycje").select("*").in_("zamowienie_id", ids).order("id").execute().data or []
        aktywne.sort(key=lambda z: (AKTYWNE.index(z["status"]), z.get("na_kiedy") or z["utworzono"]))
        kol = st.columns(3)
        for i, z in enumerate(aktywne):
            with kol[i % 3]:
                karta(z, [p for p in poz if p["zamowienie_id"] == z["id"]])
    if czekaja:
        with st.expander(f"⏳ Czekają na płatność online ({len(czekaja)}) – nie przygotowywać"):
            for z in czekaja:
                st.write(f"{z['numer']} · {ts(z['utworzono']):%H:%M} · {z['imie']} · {z['telefon']} · {zl(z['razem'])} · "
                         f"płatność: {z['platnosc_status']}")


with T["🔥 Zamówienia"]:
    panel_zamowien()


# ================================================================== RAPORT
with T["📊 Raport"]:
    c1, c2 = st.columns(2)
    d_od = c1.date_input("Od", date.today() - timedelta(days=6), format="DD.MM.YYYY")
    d_do = c2.date_input("Do", date.today(), format="DD.MM.YYYY")
    start = datetime.combine(d_od, datetime.min.time(), TZ).astimezone(timezone.utc).isoformat()
    koniec = datetime.combine(d_do + timedelta(days=1), datetime.min.time(), TZ).astimezone(timezone.utc).isoformat()
    rows = (db().table("zamowienia").select("*").eq("lokal_id", lokal_id).gte("utworzono", start).lt("utworzono", koniec)
            .order("utworzono", desc=True).limit(2000).execute().data or [])
    if not rows:
        st.info("Brak zamówień w tym okresie.")
    else:
        df = pd.DataFrame([{
            "Nr": z["numer"], "Data": ts(z["utworzono"]).strftime("%d.%m.%Y %H:%M"), "Status": STATUSY[z["status"]][0],
            "Tryb": z["tryb"], "Klient": f"{z['imie']} {z.get('nazwisko') or ''}".strip(), "Telefon": z["telefon"],
            "Miejscowość": z.get("miejscowosc") or "", "Płatność": PLATNOSC[z["platnosc"]],
            "Opłacone": "tak" if z["platnosc_status"] == "oplacone" else ("—" if z["platnosc"] != "online" else "nie"),
            "Produkty": float(z["produkty_suma"]), "Dostawa": float(z["dostawa"]), "Rabat": float(z["rabat"]),
            "Razem": float(z["razem"]), "Faktura": z.get("nip") or "",
        } for z in rows])
        wazne = df[~df["Status"].isin(["ANULOWANE", "CZEKA NA PŁATNOŚĆ"])]
        m = st.columns(4)
        for col, (lab, val) in zip(m, [("Zamówień", len(wazne)), ("Obrót", zl(wazne["Razem"].sum())),
                                       ("Średni koszyk", zl(wazne["Razem"].mean() if len(wazne) else 0)),
                                       ("W tym dostawa", zl(wazne["Dostawa"].sum()))]):
            col.markdown(f'<div class="metric"><span>{lab}</span><b>{val}</b></div>', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f zł") for c in ["Produkty", "Dostawa", "Rabat", "Razem"]})
        st.download_button("Pobierz CSV", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"zamowienia_{d_od:%Y%m%d}_{d_do:%Y%m%d}.csv", mime="text/csv")


# ================================================================== ADMIN
CALKOWITE = {"kolejnosc", "max_uzyc", "max_na_klienta", "sos_gratis"}


def _json(kol: str, v):
    """Wartość z tabeli pandas → typ akceptowany przez bazę (numpy → Python, NaN → None, 5.0 → 5 dla liczb całkowitych)."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    v = v.item() if hasattr(v, "item") else v
    if kol in CALKOWITE and isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def zapisz_zmiany(tabela: str, przed: pd.DataFrame, po: pd.DataFrame, klucz: str, kolumny: list[str]) -> int:
    """Zapisuje tylko zmienione wiersze (porównanie po kluczu)."""
    n = 0
    p = przed.set_index(klucz)
    for _, r in po.iterrows():
        k = _json(klucz, r[klucz])
        if k in p.index and any(_json(c, p.at[k, c]) != _json(c, r[c]) for c in kolumny):
            db().table(tabela).update({c: _json(c, r[c]) for c in kolumny}).eq(klucz, k).execute()
            n += 1
    return n


if ADMIN:
    # ---------------------------------------------------------- MENU I CENY
    with T["🍕 Menu i ceny"]:
        kat = q("kategorie", "*")
        roz = sorted(q("rozmiary", "*"), key=lambda r: r["kolejnosc"])
        prod = q("produkty", "*")
        ceny = q("ceny", "*")
        kat_n = {k["id"]: k["nazwa"] for k in kat}
        wybrana = st.selectbox("Kategoria", sorted(kat, key=lambda k: k["kolejnosc"]), format_func=lambda k: k["nazwa"])
        pk = sorted([p for p in prod if p["kategoria_id"] == wybrana["id"]], key=lambda p: (p["kolejnosc"], p["id"]))
        ma_rozm = any(c["produkt_id"] in {p["id"] for p in pk} for c in ceny)

        df = pd.DataFrame([{
            "id": p["id"], "Aktywny": p["aktywny"], "Kolejność": p["kolejnosc"], "Nazwa": p["nazwa"], "Opis": p["opis"],
            "Tagi": ", ".join(p["tagi"]), "Dodatki": p["dodatki"], "Sos gratis": p["sos_gratis"],
            **({r["nazwa"]: next((float(c["cena"]) for c in ceny if c["produkt_id"] == p["id"] and c["rozmiar_id"] == r["id"]), None)
                for r in roz} if ma_rozm else {"Cena": float(p["cena"] or 0)}),
        } for p in pk])
        st.caption("Edytuj w tabeli i kliknij Zapisz. Wyłącz „Aktywny”, żeby ukryć produkt. Tagi: wege, ostra, ryba.")
        ed = st.data_editor(df, hide_index=True, use_container_width=True, disabled=["id"], key=f"menu_{wybrana['id']}",
                            column_config={"Opis": st.column_config.TextColumn(width="large"),
                                           "Sos gratis": st.column_config.NumberColumn(min_value=0, max_value=1)})
        if st.button("💾 Zapisz menu", type="primary"):
            n = 0
            for (_, a), (_, b) in zip(df.iterrows(), ed.iterrows()):
                zm = {}
                for kol, pole in [("Aktywny", "aktywny"), ("Kolejność", "kolejnosc"), ("Nazwa", "nazwa"), ("Opis", "opis"),
                                  ("Dodatki", "dodatki"), ("Sos gratis", "sos_gratis")]:
                    if _json(pole, a[kol]) != _json(pole, b[kol]):
                        zm[pole] = _json(pole, b[kol])
                if a["Tagi"] != b["Tagi"]:
                    zm["tagi"] = [t.strip() for t in str(b["Tagi"]).split(",") if t.strip()]
                if not ma_rozm and a["Cena"] != b["Cena"]:
                    zm["cena"] = float(b["Cena"])
                if zm:
                    db().table("produkty").update(zm).eq("id", int(b["id"])).execute()
                    n += 1
                if ma_rozm:
                    for r in roz:
                        if a[r["nazwa"]] != b[r["nazwa"]] and not pd.isna(b[r["nazwa"]]):
                            db().table("ceny").upsert({"produkt_id": int(b["id"]), "rozmiar_id": r["id"],
                                                       "cena": float(b[r["nazwa"]])}).execute()
                            n += 1
            ok(f"Zapisano zmian: {n}")
            st.rerun()

        with st.expander("➕ Dodaj produkt"):
            with st.form("nowy_produkt", clear_on_submit=True):
                k = st.selectbox("Kategoria", kat, format_func=lambda k: k["nazwa"], index=[x["id"] for x in kat].index(wybrana["id"]))
                n_naz = st.text_input("Nazwa")
                n_opis = st.text_input("Opis / składniki")
                z_rozm = st.checkbox("Ceny wg rozmiarów (pizza)", value=ma_rozm)
                cols = st.columns(len(roz) if z_rozm else 1)
                ceny_n = {r["id"]: cols[i].number_input(r["nazwa"], min_value=0.0, step=0.5) for i, r in enumerate(roz)} if z_rozm \
                    else {None: cols[0].number_input("Cena", min_value=0.0, step=0.5)}
                if st.form_submit_button("Dodaj") and n_naz.strip():
                    nowy = db().table("produkty").insert({
                        "kategoria_id": k["id"], "nazwa": n_naz.strip().upper() if z_rozm else n_naz.strip(), "opis": n_opis.strip(),
                        "cena": None if z_rozm else ceny_n[None], "dodatki": z_rozm, "sos_gratis": 1 if z_rozm else 0,
                        "kolejnosc": max([p["kolejnosc"] for p in pk] or [0]) + 1}).execute().data[0]
                    if z_rozm:
                        db().table("ceny").insert([{"produkt_id": nowy["id"], "rozmiar_id": rid, "cena": c}
                                                   for rid, c in ceny_n.items() if c > 0]).execute()
                    ok("Dodano produkt")
                    st.rerun()

        with st.expander("📐 Rozmiary i opakowania"):
            dr = pd.DataFrame([{"id": r["id"], "Rozmiar": r["nazwa"], "Opakowanie (zł)": float(r["opakowanie"])} for r in roz])
            er = st.data_editor(dr, hide_index=True, disabled=["id", "Rozmiar"], key="rozm")
            if st.button("Zapisz opakowania"):
                for _, r in er.iterrows():
                    db().table("rozmiary").update({"opakowanie": float(r["Opakowanie (zł)"])}).eq("id", int(r["id"])).execute()
                ok("Zapisano")
                st.rerun()

    # ---------------------------------------------------------- DOSTĘPNOŚĆ
    with T["🚫 Dostępność"]:
        st.caption(f"Produkty chwilowo niedostępne w lokalu **{LOKALE[lokal_id]}** (np. skończył się składnik). "
                   "Klient widzi je jako „chwilowo niedostępne”.")
        prod = sorted(q("produkty", "id,nazwa,aktywny"), key=lambda p: p["nazwa"])
        nied = {n["produkt_id"] for n in q("niedostepne", "*", lokal_id=lokal_id)}
        wyb = st.multiselect("Niedostępne teraz", [p["id"] for p in prod if p["aktywny"]],
                             default=[i for i in nied if any(p["id"] == i for p in prod)],
                             format_func=lambda i: next(p["nazwa"] for p in prod if p["id"] == i))
        if st.button("💾 Zapisz dostępność", type="primary"):
            for pid in nied - set(wyb):
                db().table("niedostepne").delete().eq("lokal_id", lokal_id).eq("produkt_id", pid).execute()
            for pid in set(wyb) - nied:
                db().table("niedostepne").insert({"lokal_id": lokal_id, "produkt_id": pid}).execute()
            ok("Zapisano")
            st.rerun()

    # ---------------------------------------------------------- DODATKI
    with T["➕ Dodatki"]:
        gr = sorted(q("dodatki_grupy", "*"), key=lambda g: g["kolejnosc"])
        st.markdown("**Ceny grup**")
        dg = pd.DataFrame([{"id": g["id"], "Grupa": g["nazwa"], "Cena": float(g["cena"]), "Kolejność": g["kolejnosc"]} for g in gr])
        eg = st.data_editor(dg, hide_index=True, disabled=["id"], key="grupy")
        if st.button("Zapisz grupy"):
            n = zapisz_zmiany("dodatki_grupy", dg.rename(columns={"Grupa": "nazwa", "Cena": "cena", "Kolejność": "kolejnosc"}),
                              eg.rename(columns={"Grupa": "nazwa", "Cena": "cena", "Kolejność": "kolejnosc"}), "id", ["nazwa", "cena", "kolejnosc"])
            ok(f"Zapisano: {n}")
            st.rerun()

        st.markdown("**Dodatki** (puste pole „Cena własna” = cena grupy)")
        gn = {g["id"]: g["nazwa"] for g in gr}
        dd = pd.DataFrame([{"id": d["id"], "Aktywny": d["aktywny"], "Grupa": gn[d["grupa_id"]], "Nazwa": d["nazwa"],
                            "Cena własna": None if d["cena"] is None else float(d["cena"]), "Kolejność": d["kolejnosc"]}
                           for d in sorted(q("dodatki", "*"), key=lambda d: (d["grupa_id"], d["kolejnosc"]))])
        ed = st.data_editor(dd, hide_index=True, disabled=["id", "Grupa"], key="dodatki", use_container_width=True)
        if st.button("Zapisz dodatki"):
            mapa = {"Aktywny": "aktywny", "Nazwa": "nazwa", "Cena własna": "cena", "Kolejność": "kolejnosc"}
            n = zapisz_zmiany("dodatki", dd.rename(columns=mapa), ed.rename(columns=mapa), "id", list(mapa.values()))
            ok(f"Zapisano: {n}")
            st.rerun()
        with st.form("nowy_dodatek", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            g = c1.selectbox("Grupa", gr, format_func=lambda g: g["nazwa"])
            n = c2.text_input("Nazwa dodatku")
            if c3.form_submit_button("Dodaj") and n.strip():
                db().table("dodatki").insert({"grupa_id": g["id"], "nazwa": n.strip(), "kolejnosc": 99}).execute()
                ok("Dodano")
                st.rerun()

        st.markdown("**Sosy gratis do pizzy**")
        sg = pd.DataFrame([{"id": s["id"], "Aktywny": s["aktywny"], "Nazwa": s["nazwa"], "Kolejność": s["kolejnosc"]}
                           for s in sorted(q("sosy_gratis", "*"), key=lambda s: s["kolejnosc"])])
        es = st.data_editor(sg, hide_index=True, disabled=["id"], key="sosy")
        if st.button("Zapisz sosy"):
            mapa = {"Aktywny": "aktywny", "Nazwa": "nazwa", "Kolejność": "kolejnosc"}
            n = zapisz_zmiany("sosy_gratis", sg.rename(columns=mapa), es.rename(columns=mapa), "id", list(mapa.values()))
            ok(f"Zapisano: {n}")
            st.rerun()

    # ---------------------------------------------------------- STREFY
    with T["🛵 Strefy dostawy"]:
        st.caption(f"Miejscowości, do których dowozi **{LOKALE[lokal_id]}**, i dopłata za dostawę. "
                   "Aby usunąć strefę, wyłącz „Aktywna” (historia zamówień zostaje).")
        sf = sorted(q("strefy", "*", lokal_id=lokal_id), key=lambda s: (float(s["oplata"]), s["miejscowosc"]))
        ds = pd.DataFrame([{"id": s["id"], "Aktywna": s["aktywna"], "Miejscowość": s["miejscowosc"], "Kod": s["kod"],
                            "Dopłata": float(s["oplata"])} for s in sf])
        es = st.data_editor(ds, hide_index=True, disabled=["id"], key="strefy", use_container_width=True)
        if st.button("💾 Zapisz strefy", type="primary"):
            mapa = {"Aktywna": "aktywna", "Miejscowość": "miejscowosc", "Kod": "kod", "Dopłata": "oplata"}
            n = zapisz_zmiany("strefy", ds.rename(columns=mapa), es.rename(columns=mapa), "id", list(mapa.values()))
            ok(f"Zapisano: {n}")
            st.rerun()
        with st.form("nowa_strefa", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            m_ = c1.text_input("Miejscowość")
            k_ = c2.text_input("Kod pocztowy")
            o_ = c3.number_input("Dopłata (zł)", min_value=0.0, step=5.0)
            if c4.form_submit_button("Dodaj") and m_.strip():
                db().table("strefy").insert({"lokal_id": lokal_id, "miejscowosc": m_.strip(), "kod": k_.strip() or None,
                                             "oplata": o_}).execute()
                ok("Dodano strefę")
                st.rerun()

    # ---------------------------------------------------------- KODY
    with T["🏷️ Kody rabatowe"]:
        kody = q("kody_rabatowe", "*")
        if kody:
            dk = pd.DataFrame([{"Kod": k["kod"], "Aktywny": k["aktywny"], "Typ": k["typ"], "Wartość": float(k["wartosc"]),
                                "Min. wartość": float(k["min_wartosc"]), "Limit użyć": k["max_uzyc"],
                                "Limit na klienta": k["max_na_klienta"],
                                "Ważny do": ts(k["wazny_do"]).strftime("%d.%m.%Y %H:%M") if k["wazny_do"] else "",
                                "Użyto": k["uzyto"]} for k in kody])
            ek = st.data_editor(dk, hide_index=True, disabled=["Kod", "Typ", "Użyto", "Ważny do"], key="kody", use_container_width=True)
            if st.button("Zapisz kody"):
                mapa = {"Aktywny": "aktywny", "Wartość": "wartosc", "Min. wartość": "min_wartosc",
                        "Limit użyć": "max_uzyc", "Limit na klienta": "max_na_klienta", "Kod": "kod"}
                n = zapisz_zmiany("kody_rabatowe", dk.rename(columns=mapa), ek.rename(columns=mapa), "kod",
                                  ["aktywny", "wartosc", "min_wartosc", "max_uzyc", "max_na_klienta"])
                ok(f"Zapisano: {n}")
                st.rerun()
        else:
            st.info("Brak kodów rabatowych.")
        with st.form("nowy_kod", clear_on_submit=True):
            st.markdown("**Nowy kod**")
            c1, c2, c3 = st.columns(3)
            kod = c1.text_input("Kod (np. COOL10)")
            typ = c2.selectbox("Typ", ["proc", "kwota"], format_func=lambda t: "procent %" if t == "proc" else "kwota zł")
            war = c3.number_input("Wartość", min_value=0.5, step=0.5, value=10.0)
            c4, c5, c6 = st.columns(3)
            lim = c4.number_input("Limit użyć (0 = bez)", min_value=0, step=1)
            lim_k = c5.number_input("Limit na klienta (0 = bez)", min_value=0, step=1, value=1)
            do = c6.date_input("Ważny do (włącznie)", value=None, format="DD.MM.YYYY")
            minw = st.number_input("Minimalna wartość produktów (zł)", min_value=0.0, step=5.0)
            if st.form_submit_button("Utwórz kod") and kod.strip():
                db().table("kody_rabatowe").insert({
                    "kod": kod.strip().upper(), "typ": typ, "wartosc": war, "max_uzyc": lim or None,
                    "max_na_klienta": lim_k or None, "min_wartosc": minw,
                    "wazny_do": datetime.combine(do, datetime.max.time(), TZ).isoformat() if do else None}).execute()
                ok("Utworzono kod")
                st.rerun()

    # ---------------------------------------------------------- USTAWIENIA
    with T["⚙️ Ustawienia"]:
        u = {r["klucz"]: r["wartosc"] for r in q("ustawienia", "klucz,wartosc")}
        with st.form("ustawienia"):
            st.markdown("**Zamawianie**")
            c1, c2 = st.columns(2)
            wyl = c1.toggle("Wyłącz zamawianie online", value=bool(u.get("zamawianie_wylaczone", False)))
            minz = c2.number_input("Minimalna wartość zamówienia (zł)", min_value=0.0, step=5.0, value=float(u.get("min_zamowienie", 45)))
            kom = st.text_input("Komunikat na górze strony (puste = brak)", value=u.get("komunikat", ""))
            c3, c4 = st.columns(2)
            cd = c3.number_input("Czas dostawy (min)", min_value=10, step=5, value=int(u.get("czas_dostawy_min", 60)))
            co = c4.number_input("Czas do odbioru (min)", min_value=5, step=5, value=int(u.get("czas_odbioru_min", 30)))
            st.markdown("**Płatności**")
            c5, c6, c7 = st.columns(3)
            p_on = c5.toggle("Online (Autopay)", value=bool(u.get("platnosc_online", True)))
            p_got = c6.toggle("Gotówka przy odbiorze", value=bool(u.get("platnosc_gotowka", False)))
            p_kar = c7.toggle("Karta przy odbiorze", value=bool(u.get("platnosc_karta", False)))
            st.markdown("**Dokumenty**")
            reg = st.text_input("Link do regulaminu", value=u.get("regulamin_url", ""))
            pol = st.text_input("Link do polityki prywatności", value=u.get("polityka_url", ""))
            if st.form_submit_button("💾 Zapisz ustawienia", type="primary"):
                if not (p_on or p_got or p_kar):
                    st.error("Włącz przynajmniej jedną formę płatności.")
                else:
                    db().table("ustawienia").upsert([{"klucz": k, "wartosc": v} for k, v in {
                        "zamawianie_wylaczone": wyl, "min_zamowienie": minz, "komunikat": kom, "czas_dostawy_min": cd,
                        "czas_odbioru_min": co, "platnosc_online": p_on, "platnosc_gotowka": p_got, "platnosc_karta": p_kar,
                        "regulamin_url": reg, "polityka_url": pol}.items()]).execute()
                    ok("Zapisano ustawienia")

        st.markdown("**Lokale – godziny otwarcia**")
        for l in sorted(lokale(), key=lambda l: l["kolejnosc"]):
            with st.form(f"lok_{l['id']}"):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**{l['nazwa']}**  \n{l['adres']} · {l['telefon']}")
                go = c2.time_input("Od", datetime.strptime(l["godz_od"][:5], "%H:%M").time(), step=900)
                gd = c3.time_input("Do", datetime.strptime(l["godz_do"][:5], "%H:%M").time(), step=900)
                ak = c4.toggle("Aktywny", value=l["aktywny"])
                if st.form_submit_button("Zapisz"):
                    db().table("lokale").update({"godz_od": go.strftime("%H:%M"), "godz_do": gd.strftime("%H:%M"),
                                                 "aktywny": ak}).eq("id", l["id"]).execute()
                    lokale.clear()
                    ok("Zapisano godziny")
