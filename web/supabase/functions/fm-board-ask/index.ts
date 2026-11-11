// Supabase Edge Function "fm-board-ask" (Fishin Magician leaderboard + reports): turns a typed question such as
// "most lbs of bass caught on a jerkbait" into custom-board settings, or (mode "report") a request such as
// "fish per hour by water temperature in the fall" into report settings. It never sees the trip log and returns no
// numbers — the app computes the board from the log (lib/boards.js). Uses the same secret as fm-lure-scan
// (ANTHROPIC_API_KEY; optional ANTHROPIC_MODEL). Runs as the signed-in angler and only answers approved anglers.
//   POST {question, today, mode?: "board" | "report" | "punch", choices: {species[], anglers[], spots[], lure_types[[key, name]]}}
//   mode "punch" (Punch list "Tidy with Claude"): question = the angler's dictated note, choices = {page, pages[], context}
//   → {title, details, kind, priority, page, note}
//   → {measure, by, species[], lure_types[], spots[], anglers[], segments[], months[], temp_min, temp_max,
//      lure_text, color_text, from, to, period, who, title, note}
import { createClient } from "npm:@supabase/supabase-js@2";

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
const env = (k) => Deno.env.get(k);
const model = () => (env("ANTHROPIC_MODEL") || "claude-sonnet-5-5").trim();
const publicKey = () => { const k = env("SUPABASE_ANON_KEY"); if (k) return k; try { return Object.values(JSON.parse(env("SUPABASE_PUBLISHABLE_KEYS") || "{}"))[0]; } catch { return undefined; } };
class Friendly extends Error { constructor(msg, status = 502) { super(msg); this.status = status; } }

const MEASURES = ["fish", "lbs", "biggest", "longest", "avg_weight", "fish_per_hour", "outings"];
const GROUPS = ["angler", "lure", "lure_type", "color", "spot", "month", "segment", "species", "year", "outing", "fish", "none"];
const SEGMENTS = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"];
const strList = (v, max = 60) => (Array.isArray(v) ? v.map((x) => String(x).slice(0, 60)).filter(Boolean).slice(0, max) : []);
const arr = (items) => ({ type: "array", items });
const en = (list) => (list.length ? { type: "string", enum: list } : { type: "string" });

function tool(c) {
  return {
    name: "set_board",
    description: "Set up the leaderboard that answers the angler's question.",
    input_schema: { type: "object", additionalProperties: false, required: ["measure", "by", "title", "note"],
      properties: {
        measure: { type: "string", enum: MEASURES, description: "fish = fish caught; lbs = total weight; biggest = heaviest fish; longest; avg_weight; fish_per_hour; outings = number of sessions." },
        by: { type: "string", enum: GROUPS, description: "What each row of the ranking is. fish = each individual fish (only with biggest/longest); none = one total." },
        species: arr(en(c.species)), lure_types: arr(en(c.lure_types.map(([k]) => k))), spots: arr(en(c.spots)), anglers: arr(en(c.anglers)),
        segments: arr({ type: "string", enum: SEGMENTS }), months: arr({ type: "integer", minimum: 1, maximum: 12 }),
        temp_min: { type: "number", description: "Water temperature °F, lowest" }, temp_max: { type: "number", description: "Water temperature °F, highest" },
        lure_text: { type: "string", description: "Words that must appear in the lure name (a brand or model), only when no lure type fits." },
        color_text: { type: "string", description: "Words that must appear in the lure color." },
        from: { type: "string", description: "YYYY-MM-DD, first day, only for an explicit date range" }, to: { type: "string", description: "YYYY-MM-DD, last day" },
        period: { type: "string", enum: ["year", "30", "all", ""], description: "year = this calendar year, 30 = last 30 days, all = all time, empty = keep what's on screen." },
        who: { type: "string", enum: ["me", "all", ""], description: "me when the question is about the asker's own fishing (I/my/me)." },
        title: { type: "string", description: "Short board title, e.g. 'Most lbs of bass on a jerkbait'." },
        note: { type: "string", description: "One short sentence on how you read the question, or why part of it can't be answered from a trip log." },
      } },
  };
}

// ---- reports (mode "report"): any factor × metric, like the old Reports page
const FACTORS = ["spot", "structure_type", "water_color", "secchi_bucket", "water_clarity", "lure", "lure_category", "color", "technique", "segment",
  "season", "light_condition", "wind_band", "wind_direction", "precipitation", "water_temp_band", "water_temp_bucket", "pressure_trend_band",
  "moon_illumination_bin", "fish_activity", "forage_activity", "angler", "day_of_week", "date", "week_start"];
const METRICS = ["total_fish", "fish_per_hour", "biggest_fish", "average_fish_weight", "trip_count"];
function reportTool(c) {
  return {
    name: "set_report",
    description: "Set up the report (a bar chart of one metric across the values of one factor) that answers the angler's request.",
    input_schema: { type: "object", additionalProperties: false, required: ["factor", "metric", "title", "note"],
      properties: {
        factor: { type: "string", enum: FACTORS, description: "What the bars are. segment = time of day; light_condition = sky; wind_band = wind strength; " +
          "pressure_trend_band = barometric pressure trend; moon_illumination_bin = moon % the night before; water_temp_bucket = water temperature in " +
          "custom steps (tempWidth); water_temp_band = broad temperature bands; secchi_bucket = water clarity in feet; lure_category = lure type; " +
          "season; date = each day; week_start = each week." },
        metric: { type: "string", enum: METRICS, description: "fish_per_hour = catch rate (best for comparing conditions); total_fish; biggest_fish; average_fish_weight; trip_count." },
        species: en(c.species), lure_types: arr(en(c.lure_types.map(([k]) => k))), spots: arr(en(c.spots)), anglers: arr(en(c.anglers)),
        segments: arr({ type: "string", enum: SEGMENTS }),
        tempWidth: { type: "number", description: "°F per bar for water_temp_bucket (default 2)" }, secchiWidth: { type: "number", description: "ft per bar for secchi_bucket (default 0.5)" },
        from: { type: "string", description: "YYYY-MM-DD, only for an explicit date range or season of a specific year" }, to: { type: "string", description: "YYYY-MM-DD" },
        period: { type: "string", enum: ["year", "90", "30", "all", ""], description: "year = this calendar year, 90/30 = last 90/30 days, all = all time, empty = keep what's on screen." },
        who: { type: "string", enum: ["me", "all", ""], description: "me when the request is about the asker's own fishing (I/my/me)." },
        title: { type: "string", description: "Short report title, e.g. 'Fish per hour by water temp'." },
        note: { type: "string", description: "One short sentence on how you read the request, or what part a trip log can't answer." },
      } },
  };
}
const reportPrompt = (q, today, c) =>
  `Today is ${today}. Anglers on Nolin River Lake, Kentucky log bass-fishing trips (date, angler, spot, structure, lure, lure type, color, technique, ` +
  `time of day, sky, wind, precipitation, water temperature and clarity, pressure trend, moon, and each fish's species and weight). ` +
  `Turn this request into report settings by calling set_report:\n\n"${q}"\n\n` +
  `Pick filter values only from these lists.\nSpecies logged: ${c.species.join("; ") || "none"}.\n` +
  `Lure types (key = name): ${c.lure_types.map(([k, n]) => `${k} = ${n}`).join("; ") || "none"}.\n` +
  `Spots: ${c.spots.join("; ") || "none"}.\nAnglers: ${c.anglers.join("; ") || "none"}.\n` +
  `Rules: "does X matter / how does X affect / best X" = factor X with metric fish_per_hour unless a size or count is asked for. ` +
  `A species filter takes one species; for "bass" in general leave species empty. A lure word means every matching lure type. ` +
  `Leave a filter out when the request doesn't limit it. Answer only by calling set_report.`;

// ---- punch list (mode "punch"): tidy a dictated note into a clear item; nothing is saved here
function punchTool(pages) {
  return {
    name: "set_item",
    description: "Write the angler's note up as one clear punch-list item for the app's developer (Claude).",
    input_schema: { type: "object", additionalProperties: false, required: ["title", "details", "kind", "priority", "page", "note"],
      properties: {
        title: { type: "string", description: "Short imperative title, under 70 characters, e.g. 'Make the + Fish button bigger'." },
        details: { type: "string", description: "What's wrong or wanted, then what it should do instead — in the angler's own terms, 1–4 short sentences or bullet lines. Keep every specific (numbers, names, lures, screens). Invent nothing." },
        kind: { type: "string", enum: ["Bug", "Change", "Idea"], description: "Bug = something broken or wrong; Change = adjust something that works; Idea = new feature." },
        priority: { type: "string", enum: ["High", "Medium", "Low"], description: "High only if it blocks fishing/logging or loses data, or the angler says it's urgent." },
        page: pages.length ? { type: "string", enum: pages } : { type: "string" },
        note: { type: "string", description: "Empty, or one short question if the note is genuinely unclear." },
      } },
  };
}
const punchPrompt = (q, c) =>
  `An angler using the Fishin Magician phone app (bass fishing on Nolin Lake) dictated this note for the app's punch list` +
  `${c.page ? ` while on the ${c.page} screen` : ""}${c.context ? ` (${c.context})` : ""}:\n\n"${q}"\n\n` +
  `Tidy it into one item by calling set_item. Fix dictation errors, keep their meaning and every detail, add nothing they didn't say. ` +
  `If it's about the screen they were on, use that page. Answer only by calling set_item.`;

const prompt = (q, today, c) =>
  `Today is ${today}. Anglers on Nolin River Lake, Kentucky log bass-fishing trips (date, angler, spot, lure, lure type, color, time of day, ` +
  `water temperature, and each fish's species, weight and length). Turn this question into leaderboard settings by calling set_board:\n\n"${q}"\n\n` +
  `Pick filter values only from these lists.\nSpecies logged: ${c.species.join("; ") || "none"}.\n` +
  `Lure types (key = name): ${c.lure_types.map(([k, n]) => `${k} = ${n}`).join("; ") || "none"}.\n` +
  `Spots: ${c.spots.join("; ") || "none"}.\nAnglers: ${c.anglers.join("; ") || "none"}.\n` +
  `Rules: "bass" means the black bass species in the list (largemouth, smallmouth, spotted/Kentucky), not white bass or other fish unless named. ` +
  `A lure word like jerkbait, crankbait, chatterbait, swimbait, jig or drop shot means every matching lure type (e.g. crankbait = all crankbait types). ` +
  `"Most lbs"/"most weight" = lbs; "most fish" = fish; "biggest"/"heaviest" = biggest; "best lure" without a measure = fish by lure. ` +
  `Who-questions rank by angler; "where" = spot; "when" = month or time of day. Leave a filter out when the question doesn't limit it. ` +
  `Seasons: spring = Mar–May, summer = Jun–Aug, fall = Sep–Nov, winter = Dec–Feb (use months). Answer only by calling set_board.`;

async function claude(req) {
  const key = (env("ANTHROPIC_API_KEY") || "").trim().replace(/^["']+|["']+$/g, "").trim();
  if (!key) throw new Friendly("The AI key isn't set — add ANTHROPIC_API_KEY under Supabase → Edge Functions → Secrets.", 500);
  for (let attempt = 0; ; attempt++) {
    const r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST",
      headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" }, body: JSON.stringify(req) });
    if (r.ok) return await r.json();
    const text = await r.text(), low = text.toLowerCase();
    if ((r.status === 429 || r.status === 529 || r.status >= 500) && attempt < 3) { await new Promise((res) => setTimeout(res, 1500 * (attempt + 1))); continue; }
    if (r.status === 401) throw new Friendly("The Anthropic API key wasn't accepted — replace ANTHROPIC_API_KEY in Supabase → Edge Functions → Secrets.");
    if (low.includes("credit balance") || low.includes("billing")) throw new Friendly("The Anthropic account is out of credit — add credit at platform.claude.com/settings/billing.");
    if (r.status === 404 || (low.includes("model") && low.includes("not found"))) throw new Friendly("The AI model name isn't recognized (" + model() + ") — set ANTHROPIC_MODEL in Supabase secrets.");
    let detail = text.slice(0, 300); try { detail = JSON.parse(text).error.message || detail; } catch { /* keep raw text */ }
    throw new Friendly("AI error " + r.status + ": " + detail);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    if (req.method !== "POST") throw new Friendly("Use POST.", 405);
    const sb = createClient(env("SUPABASE_URL"), publicKey(), { global: { headers: { Authorization: req.headers.get("Authorization") || "" } }, auth: { persistSession: false } });
    const ap = await sb.rpc("fm_is_approved");
    if (ap.error || ap.data !== true) throw new Friendly("You're not on the Fishin Magician list.", 403);
    const body = await req.json().catch(() => ({}));
    const q = String(body.question || "").trim().slice(0, body.mode === "punch" ? 3000 : 300);
    if (q.length < 3) throw new Friendly("Type a question first.", 400);
    const today = /^\d{4}-\d{2}-\d{2}$/.test(body.today) ? body.today : new Date().toISOString().slice(0, 10);
    const ch = body.choices || {};
    if (body.mode === "punch") {
      const pages = strList(ch.pages, 30), pc = { page: String(ch.page || "").slice(0, 60), context: String(ch.context || "").slice(0, 300) };
      const t = punchTool(pages);
      for (let i = 0; i < 2; i++) {
        const msg = await claude({ model: model(), max_tokens: 1500, tools: [t], tool_choice: { type: "auto" }, messages: [{ role: "user", content: punchPrompt(q, pc) }] });
        const use = (msg.content || []).find((b) => b.type === "tool_use" && b.name === t.name);
        if (use) return reply(200, use.input);
      }
      throw new Friendly("The AI didn't tidy that note — save it as you wrote it, or try again.");
    }
    const c = { species: strList(ch.species), anglers: strList(ch.anglers), spots: strList(ch.spots, 120),
      lure_types: (Array.isArray(ch.lure_types) ? ch.lure_types : []).filter((x) => Array.isArray(x) && x.length === 2).map(([k, n]) => [String(k).slice(0, 40), String(n).slice(0, 60)]).slice(0, 60) };
    const report = body.mode === "report", t = report ? reportTool(c) : tool(c);
    for (let i = 0; i < 2; i++) {
      // tool_choice "auto" (newer models reject forcing a tool); the prompt says to answer only via the tool
      const msg = await claude({ model: model(), max_tokens: 2048, tools: [t], tool_choice: { type: "auto" },
        messages: [{ role: "user", content: (report ? reportPrompt : prompt)(q, today, c) }] });
      const use = (msg.content || []).find((b) => b.type === "tool_use" && b.name === t.name);
      if (use) return reply(200, use.input);
    }
    throw new Friendly(report ? "The AI answered without setting up a report — try wording it differently." : "The AI answered without setting up a board — try wording it differently.");
  } catch (e) {
    return reply(e instanceof Friendly ? e.status : 500, { error: e instanceof Friendly ? e.message : "Something went wrong: " + String(e).slice(0, 200) });
  }
});
