// Cool Pizza – start płatności Autopay
// Wejście:  POST {"token": "<uuid zamówienia>"}
// Wyjście:  {"url": "https://pay.autopay.eu/payment", "fields": {ServiceID, OrderID, Amount, Description, CustomerEmail, Hash}}
// Strona wysyła te pola formularzem POST do bramki Autopay.
//
// Sekrety (Supabase → Edge Functions → Secrets):
//   AUTOPAY_CONFIG  = {"5":{"service_id":"123456","key":"klucz_wspoldzielony"},"2":{...}}   (klucz = id lokalu)
//   AUTOPAY_URL     = https://testpay.autopay.eu/payment   (test)  |  https://pay.autopay.eu/payment  (produkcja)
//   AUTOPAY_HASH    = sha256 (domyślnie) | sha512
// SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY Supabase ustawia sam.

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type, apikey, authorization, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type LokalCfg = { service_id: string; key: string };

export async function hashHex(text: string, algo = "sha256"): Promise<string> {
  const name = algo.toLowerCase() === "sha512" ? "SHA-512" : "SHA-256";
  const buf = await crypto.subtle.digest(name, new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Kolejność pól wg dokumentacji Autopay: ServiceID, OrderID, Amount, Description, GatewayID, Currency, CustomerEmail, ...
export async function polaStartu(cfg: LokalCfg, orderId: string, kwota: string, opis: string, email: string | null, algo = "sha256") {
  const fields: Record<string, string> = { ServiceID: cfg.service_id, OrderID: orderId, Amount: kwota, Description: opis };
  if (email) fields.CustomerEmail = email;
  const wartosci = [fields.ServiceID, fields.OrderID, fields.Amount, fields.Description, ...(email ? [email] : [])];
  fields.Hash = await hashHex([...wartosci, cfg.key].join("|"), algo);
  return fields;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

async function handler(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Metoda niedozwolona" }, 405);

  const env = (k: string) => (globalThis as any).Deno?.env.get(k) ?? "";
  let token = "";
  try { token = String((await req.json()).token ?? ""); } catch { /* puste body */ }
  if (!/^[0-9a-f-]{36}$/i.test(token)) return json({ error: "Brak numeru zamówienia" }, 400);

  // platnosc_start: sprawdza zamówienie, nalicza próbę, zwraca kwotę z bazy (nie z przeglądarki)
  const r = await fetch(`${env("SUPABASE_URL")}/rest/v1/rpc/platnosc_start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: env("SUPABASE_SERVICE_ROLE_KEY"),
      Authorization: `Bearer ${env("SUPABASE_SERVICE_ROLE_KEY")}`,
    },
    body: JSON.stringify({ p_token: token }),
  });
  const z = await r.json().catch(() => null);
  if (!r.ok) return json({ error: z?.message ?? "Nie udało się rozpocząć płatności" }, 400);

  let cfgAll: Record<string, LokalCfg> = {};
  try { cfgAll = JSON.parse(env("AUTOPAY_CONFIG") || "{}"); } catch { /* źle wpisany sekret */ }
  const cfg = cfgAll[String(z.lokal_id)];
  if (!cfg?.service_id || !cfg?.key) return json({ error: "Płatności online nie są skonfigurowane dla tego lokalu" }, 500);

  const fields = await polaStartu(cfg, z.order_id, z.kwota, `Cool Pizza zamowienie ${z.order_id}`, z.email, env("AUTOPAY_HASH") || "sha256");
  return json({ url: env("AUTOPAY_URL") || "https://testpay.autopay.eu/payment", fields });
}

if ((globalThis as any).Deno) (globalThis as any).Deno.serve(handler);
