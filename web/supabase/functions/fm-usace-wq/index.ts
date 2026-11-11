// Supabase Edge Function "fm-usace-wq" (Fishin Magician). Fetches the Army Corps Nolin water-quality report page and
// hands its HTML to the app, because a web page can't read that site directly (it doesn't allow cross-site reads).
// Public data only; no secrets. Signed-in callers only (Supabase checks the JWT). Parsing happens in the app
// (web/src/lib/lake.js parseSurfaceWaterQuality), so it stays tested against the Python reference.
const REPORT_URL = "https://www.lrl-wc.usace.army.mil/reports/wq/NRR.html";
// The USACE server doesn't send its intermediate certificate (browsers fetch it on their own; servers don't), so
// TLS fails with "invalid peer certificate: UnknownIssuer". We supply DigiCert's public intermediate ourselves.
// DigiCert Global G2 TLS RSA SHA256 2020 CA1 — valid until 2031-03-29,
// SHA-256 C8:02:5F:9F:C6:5F:DF:C9:5B:3C:A8:CC:78:67:B9:A5:87:B5:27:79:73:95:79:17:46:3F:C8:13:D0:B6:25:A9
// (from http://cacerts.digicert.com/DigiCertGlobalG2TLSRSASHA2562020CA1-1.crt)
const USACE_INTERMEDIATE = `-----BEGIN CERTIFICATE-----
MIIEyDCCA7CgAwIBAgIQDPW9BitWAvR6uFAsI8zwZjANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0yMTAzMzAwMDAwMDBaFw0zMTAzMjkyMzU5NTlaMFkxCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxMzAxBgNVBAMTKkRpZ2lDZXJ0IEdsb2Jh
bCBHMiBUTFMgUlNBIFNIQTI1NiAyMDIwIENBMTCCASIwDQYJKoZIhvcNAQEBBQAD
ggEPADCCAQoCggEBAMz3EGJPprtjb+2QUlbFbSd7ehJWivH0+dbn4Y+9lavyYEEV
cNsSAPonCrVXOFt9slGTcZUOakGUWzUb+nv6u8W+JDD+Vu/E832X4xT1FE3LpxDy
FuqrIvAxIhFhaZAmunjZlx/jfWardUSVc8is/+9dCopZQ+GssjoP80j812s3wWPc
3kbW20X+fSP9kOhRBx5Ro1/tSUZUfyyIxfQTnJcVPAPooTncaQwywa8WV0yUR0J8
osicfebUTVSvQpmowQTCd5zWSOTOEeAqgJnwQ3DPP3Zr0UxJqyRewg2C/Uaoq2yT
zGJSQnWS+Jr6Xl6ysGHlHx+5fwmY6D36g39HaaECAwEAAaOCAYIwggF+MBIGA1Ud
EwEB/wQIMAYBAf8CAQAwHQYDVR0OBBYEFHSFgMBmx9833s+9KTeqAx2+7c0XMB8G
A1UdIwQYMBaAFE4iVCAYlebjbuYP+vq5Eu0GF485MA4GA1UdDwEB/wQEAwIBhjAd
BgNVHSUEFjAUBggrBgEFBQcDAQYIKwYBBQUHAwIwdgYIKwYBBQUHAQEEajBoMCQG
CCsGAQUFBzABhhhodHRwOi8vb2NzcC5kaWdpY2VydC5jb20wQAYIKwYBBQUHMAKG
NGh0dHA6Ly9jYWNlcnRzLmRpZ2ljZXJ0LmNvbS9EaWdpQ2VydEdsb2JhbFJvb3RH
Mi5jcnQwQgYDVR0fBDswOTA3oDWgM4YxaHR0cDovL2NybDMuZGlnaWNlcnQuY29t
L0RpZ2lDZXJ0R2xvYmFsUm9vdEcyLmNybDA9BgNVHSAENjA0MAsGCWCGSAGG/WwC
ATAHBgVngQwBATAIBgZngQwBAgEwCAYGZ4EMAQICMAgGBmeBDAECAzANBgkqhkiG
9w0BAQsFAAOCAQEAkPFwyyiXaZd8dP3A+iZ7U6utzWX9upwGnIrXWkOH7U1MVl+t
wcW1BSAuWdH/SvWgKtiwla3JLko716f2b4gp/DA/JIS7w7d7kwcsr4drdjPtAFVS
slme5LnQ89/nD/7d+MS5EHKBCQRfz5eeLjJ1js+aWNJXMX43AYGyZm0pGrFmCW3R
bpD0ufovARTFXFZkAdl9h6g4U5+LXUZtXMYnhIHUfoyMo5tS58aI7Dd8KvvwVVo4
chDYABPPTHPbqjc1qCmBaZx2vN4Ye5DUys/vZwP9BFohFrH/6j/f3IL16/RZkiMN
JCqVJUzKoZHm1Lesh3Sz8W2jmdv51b2EQJ8HmA==
-----END CERTIFICATE-----`;
// deno-lint-ignore no-explicit-any
const client = (Deno as any).createHttpClient?.({ caCerts: [USACE_INTERMEDIATE] });
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

async function getReport(): Promise<Response> {
  let last: unknown;
  for (let attempt = 0; attempt < 3; attempt++) { // the USACE server sometimes drops the first connection
    if (attempt) await new Promise((r) => setTimeout(r, 1500));
    try {
      return await fetch(REPORT_URL, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; FishinMagician/1.0; +https://jjpvoskuil.github.io/Voskuil-Fishin-Magician/)" },
      signal: AbortSignal.timeout(20000),
      // @ts-ignore Deno-specific fetch option
      ...(client ? { client } : {}),
      });
    } catch (e) { last = e; }
  }
  throw last;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const r = await getReport();
    if (!r.ok) return json({ error: `USACE answered ${r.status}` }, 502);
    return json({ html: await r.text(), fetched_at: new Date().toISOString() });
  } catch (e) {
    return json({ error: `Couldn't reach USACE${client ? "" : " (no custom-certificate support here)"}: ${e instanceof Error ? e.message : String(e)}` }, 502);
  }
});
