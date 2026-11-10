// Made-up data for the browser-only demo backend (?demo). Not real anglers, trips, spots or catches.
import { addDays } from "./lib/py.js";
import { lakeToday } from "./lib/weather.js";

export const DEMO_EMAIL = "demo@example.com";
const BUDDY = "buddy@example.com";

/** small seeded random generator so the demo looks the same every time */
function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; }; }

const SPOTS = [["d1", "Demo Point", "Main-lake point"], ["d2", "Sample Cove", "Cove / pocket (shallow cover)"], ["d3", "Example Bluff", "Riprap / dam face"]];
const LURES = [["Strike King - KVD Squarebill 1.5 - Sexy Shad", "squarebill_crankbait"], ["Z-Man - ChatterBait Jackhammer - Green Pumpkin", "chatterbait"],
  ["Berkley - MaxScent Flat Worm - Watermelon Red", "finesse_shaky_head"], ["Booyah - Football Jig - Brown/Orange", "football_jig"], ["Rapala - Shadow Rap - Ghost Shad", "suspending_jerkbait"]];
const SEGS = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk"];
const START = { Dawn: 6, Morning: 8, Midday: 11, Afternoon: 14, Dusk: 16 };

export function demoTrips(today = lakeToday()) {
  const r = rng(20261110), pick = (a) => a[Math.floor(r() * a.length)], trips = [];
  let n = 0;
  for (let back = 75; back >= 0; back--) {
    if (back > 0 && r() < 0.6) continue;
    const day = addDays(today, -back);
    const anglers = back === 0 ? [["Demo Angler", DEMO_EMAIL, true], ["Fishing Buddy", BUDDY, false]] : [[r() < 0.6 ? "Demo Angler" : "Fishing Buddy", null, false]];
    for (const [angler, email0, open] of anglers) {
      const email = email0 || (angler === "Demo Angler" ? DEMO_EMAIL : BUDDY);
      const seg = back === 0 ? (open ? "Morning" : "Dawn") : pick(SEGS), [sid, sname, struct] = pick(SPOTS);
      const session = `ds${n}`;
      for (let k = 0; k < (r() < 0.5 ? 1 : 2); k++) {
        const [lure, cat] = pick(LURES), h = START[seg] + k, mins = 30 + Math.floor(r() * 80);
        const fish = Array.from({ length: Math.floor(r() * 4) }, () => ({ species: r() < 0.85 ? "Largemouth" : "Spotted", weight_lb: Math.round((0.8 + r() * 3.2) * 16) / 16, count: 1 }));
        const end = `${String(h + Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}:00`;
        trips.push({
          trip_id: `dt${n++}`, session_id: session, logged_at: `${day}T${String(h).padStart(2, "0")}:05:00`, trip_date: day, segment: seg,
          spot_id: sid, spot_name: sname, structure_type: struct, water_clarity: pick(["Green stained", "Brown stained", "Clear"]),
          lure_used: lure, color_used: lure.split(" - ").pop(), technique_used: "", fish_caught: String(fish.length),
          biggest_fish_lb: fish.length ? String(Math.max(...fish.map((f) => f.weight_lb))) : "", predicted_score: String(Math.round((4 + r() * 4) * 10) / 10), owner: email,
          conditions: { angler, source: "spot_session", fish, lure_category: cat, lure_start_time: `${String(h).padStart(2, "0")}:00:00`,
            lure_end_time: open && k === 0 ? "" : end, session_end_time: open ? "" : end, pressure_trend_24h: Math.round((r() * 6 - 3) * 10) / 10,
            avg_cloud_pct: pick([10, 30, 60, 90]), avg_wind_mph: pick([2, 6, 9, 13, 17]), moon_near_new_full: r() < 0.4, water_temp_f: Math.round((55 + r() * 15) * 10) / 10 },
        });
      }
    }
  }
  return trips;
}

export const DEMO_USACE_HTML = `<table><tr><td>Dam Site</td><td>${lakeToday().replace(/-/g, "").slice(0, 8)}, 0930</td><td>0</td><td>15.4</td><td>9.1</td></tr></table>`;

export function demoSeed() {
  return {
    users: [{ email: DEMO_EMAIL, name: "Demo Angler", role: "admin" }, { email: BUDDY, name: "Fishing Buddy", role: "member" }],
    trips: demoTrips(), water_quality: [], freezes: [], usace_html: DEMO_USACE_HTML,
  };
}
