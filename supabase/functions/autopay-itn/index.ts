// Cool Pizza – powiadomienia ITN z Autopay (wynik płatności)
// Autopay wysyła POST z parametrem "transactions" = XML zakodowany Base64.
// Sprawdzamy podpis (Hash), zapisujemy wynik w bazie i odpowiadamy XML-em confirmationList.
// Adres tej funkcji wpisujesz w panelu Autopay jako „Adres dla komunikatów ITN”.
// Sekrety jak w autopay-start: AUTOPAY_CONFIG, AUTOPAY_HASH.

type LokalCfg = { service_id: string; key: string };

export async function hashHex(text: string, algo = "sha256"): Promise<string> {
  const name = algo.toLowerCase() === "sha512" ? "SHA-512" : "SHA-256";
  const buf = await crypto.subtle.digest(name, new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const dekoduj = (s: string) =>
  s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");

// Wartości wszystkich elementów-liści w kolejności dokumentu (bez <hash>)
export function liscie(xml: string): { tag: string; val: string }[] {
  const out: { tag: string; val: string }[] = [];
  for (const m of xml.matchAll(/<([A-Za-z][\w]*)>([^<]*)<\/\1>/g)) out.push({ tag: m[1], val: dekoduj(m[2].trim()) });
  return out;
}

export type Transakcja = { orderID: string; remoteID: string; amount: string; paymentStatus: string; [k: string]: string };

export async function analizujITN(xml: string, cfgAll: Record<string, LokalCfg>, algo = "sha256") {
  const wszystkie = liscie(xml);
  const serviceID = wszystkie.find((l) => l.tag === "serviceID")?.val ?? "";
  const hash = wszystkie.find((l) => l.tag === "hash")?.val ?? "";
  const cfg = Object.values(cfgAll).find((c) => String(c.service_id) === serviceID);
  const transakcje: Transakcja[] = [...xml.matchAll(/<transaction>([\s\S]*?)<\/transaction>/g)].map((m) =>
    Object.fromEntries(liscie(m[1]).map((l) => [l.tag, l.val])) as Transakcja
  );
  if (!cfg) return { serviceID, cfg: null, hashOk: false, transakcje };
  const doPodpisu = wszystkie.filter((l) => l.tag !== "hash").map((l) => l.val);
  const oczekiwany = await hashHex([...doPodpisu, cfg.key].join("|"), algo);
  return { serviceID, cfg, hashOk: oczekiwany.toLowerCase() === hash.toLowerCase(), transakcje };
}

export async function odpowiedz(serviceID: string, potw: { orderID: string; ok: boolean }[], key: string, algo = "sha256") {
  const wartosci = [serviceID, ...potw.flatMap((p) => [p.orderID, p.ok ? "CONFIRMED" : "NOTCONFIRMED"])];
  const h = await hashHex([...wartosci, key].join("|"), algo);
  return `<?xml version="1.0" encoding="UTF-8"?>
<confirmationList>
<serviceID>${serviceID}</serviceID>
<transactionsConfirmations>
${potw.map((p) => `<transactionConfirmed>
<orderID>${p.orderID}</orderID>
<confirmation>${p.ok ? "CONFIRMED" : "NOTCONFIRMED"}</confirmation>
</transactionConfirmed>`).join("\n")}
</transactionsConfirmations>
<hash>${h}</hash>
</confirmationList>`;
}

function b64utf8(s: string) {
  const bin = atob(s.replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

async function handler(req: Request): Promise<Response> {
  const env = (k: string) => (globalThis as any).Deno?.env.get(k) ?? "";
  if (req.method !== "POST") return new Response("Metoda niedozwolona", { status: 405 });

  let xml = "";
  try {
    const form = await req.formData();
    xml = b64utf8(String(form.get("transactions") ?? ""));
  } catch {
    return new Response("Brak parametru transactions", { status: 400 });
  }

  let cfgAll: Record<string, LokalCfg> = {};
  try { cfgAll = JSON.parse(env("AUTOPAY_CONFIG") || "{}"); } catch { /* źle wpisany sekret */ }
  const algo = env("AUTOPAY_HASH") || "sha256";
  const a = await analizujITN(xml, cfgAll, algo);
  if (!a.cfg) return new Response("Nieznany serwis", { status: 400 });

  const potw: { orderID: string; ok: boolean }[] = [];
  for (const t of a.transakcje) {
    let ok = false;
    if (a.hashOk) {
      const r = await fetch(`${env("SUPABASE_URL")}/rest/v1/rpc/platnosc_wynik`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: env("SUPABASE_SERVICE_ROLE_KEY"),
          Authorization: `Bearer ${env("SUPABASE_SERVICE_ROLE_KEY")}`,
        },
        body: JSON.stringify({
          p_order_id: t.orderID, p_remote_id: t.remoteID ?? null, p_status: t.paymentStatus ?? "",
          p_kwota: Number(t.amount), p_dane: t,
        }),
      });
      ok = r.ok && (await r.json().catch(() => false)) === true;
    }
    potw.push({ orderID: t.orderID, ok });
  }

  return new Response(await odpowiedz(a.serviceID, potw, a.cfg.key, algo), {
    status: 200, headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
}

if ((globalThis as any).Deno) (globalThis as any).Deno.serve(handler);
