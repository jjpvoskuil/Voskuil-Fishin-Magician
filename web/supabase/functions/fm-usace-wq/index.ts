// Supabase Edge Function "fm-usace-wq" (Fishin Magician). Fetches the Army Corps Nolin water-quality report page and
// hands its HTML to the app, because a web page can't read that site directly (it doesn't allow cross-site reads).
// Public data only; no secrets. Signed-in callers only (Supabase checks the JWT). Parsing happens in the app
// (web/src/lib/lake.js parseSurfaceWaterQuality), so it stays tested against the Python reference.
const REPORT_URL = "https://www.lrl-wc.usace.army.mil/reports/wq/NRR.html";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const r = await fetch(REPORT_URL, { headers: { "User-Agent": "FishinMagician/1.0 (+https://jjpvoskuil.github.io/Voskuil-Fishin-Magician/)" }, signal: AbortSignal.timeout(20000) });
    if (!r.ok) return json({ error: `USACE answered ${r.status}` }, 502);
    return json({ html: await r.text(), fetched_at: new Date().toISOString() });
  } catch (e) {
    return json({ error: `Couldn't reach USACE: ${e instanceof Error ? e.message : String(e)}` }, 502);
  }
});
