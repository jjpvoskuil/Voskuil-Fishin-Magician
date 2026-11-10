"""Parity fixtures for web/src/lib/lures.js from core/lures.py (synthetic tackle box + trips only).
    TZ=UTC python3 web/tools/make_lure_fixtures.py
"""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web" / "tools"))
from core import lures, videos, scoring  # noqa: E402
from make_engine_fixtures import enc  # noqa: E402

rng = random.Random(4417)
cats = list(lures.LURE_PROFILES)
words = ["green pumpkin", "chartreuse", "black/blue", "shad", "white", "brown craw", "firetiger", "watermelon red", "junebug", "chrome", "bluegill", "red"]
inventory = []
for i in range(60):
    c = rng.choice(cats + ["", "not_a_category"])
    inventory.append({"item_id": f"i{i}", "brand": rng.choice(["Strike King", "Z-Man", "", "Berkley"]),
                      "description": f"{lures.LURE_PROFILES.get(c, {'name': 'Thing'})['name']} - {rng.choice(words)} {rng.choice(words)}",
                      "category": c, "quantity": rng.choice(["1", "2", "0", "", "x", 3]), "sku": str(rng.randrange(1000000)), "image_url": "", "image_filename": ""})
labels = [lures._item_label(it) for it in inventory]
spots = ["s1", "s2", "s3", ""]
trips = []
for i in range(400):
    seg = rng.choice(scoring.SEGMENTS)
    start_h = rng.randrange(5, 19)
    cond = {"lure_category": rng.choice(cats + [None]), "water_temp_f": rng.choice([55, 62.5, 70, 81, None, "x"]),
            "lure_start_time": f"{start_h:02d}:00:00", "lure_end_time": f"{start_h + rng.choice([0, 1, 2]):02d}:{rng.choice(['30', '00'])}:00"}
    trips.append({"segment": seg, "spot_id": rng.choice(spots), "structure_type": rng.choice(lures.STRUCTURE_TYPES + [""]),
                  "water_clarity": rng.choice(lures.WATER_CLARITY_OPTIONS), "fish_caught": rng.choice(["0", "0", "1", "2", "4", "", "z"]),
                  "biggest_fish_lb": rng.choice(["", "1.25", "3.5", "abc", None, "0"]), "lure_used": rng.choice(labels),
                  "conditions_json": json.dumps(cond)})
seasons = ["winter", "pre_spawn", "spawn", "summer_peak", "post_spawn_summer", "fall_turnover", "fall_feed_up"]
cases = []
for i in range(700):
    args = dict(season=rng.choice(seasons), water_temp_f=rng.choice([45, 55, 60, 62.5, 68, 69, 75, 84]), segment_name=rng.choice(scoring.SEGMENTS),
                pressure_trend_24h=rng.choice([-2, -1.5, 0, 1, 2, 3]), structure_type=rng.choice(lures.STRUCTURE_TYPES + ["Unknown"]),
                water_clarity=rng.choice(lures.WATER_CLARITY_OPTIONS), fish_depth_ft=rng.choice([None, None, 1, 2.5, 4, 6, 9.5, 12, 15, 22, 35]),
                forage=rng.choice([None, [], ["Gizzard Shad"], ["Crawfish", "Bluegill / Sunfish"], ["Stonerollers", "Threadfin Shad", "Shiners / Minnows"]]),
                thermocline_ft=rng.choice([None, 15.0, 60.0]), spot_id=rng.choice([None, "s1", "s2"]),
                fish_activity=rng.choice([None, "Very active", "Active", "Normal", "Sluggish", "Inactive / shut down"]),
                forage_activity=rng.choice([None, "Active / schooling", "Frenzied (busting bait)", "Some", "None seen"]),
                wind_mph=rng.choice([None, 3, 9.9, 10, 18.5]))
    inv = rng.choice(["none", "some", "all"]); hist = rng.choice(["none", "all"])
    r = lures.recommend(**args, inventory=None if inv == "none" else inventory[:20] if inv == "some" else inventory,
                        trip_history=None if hist == "none" else trips)
    cur = lures.curate_recommendation(r, None if inv == "none" else inventory[:20] if inv == "some" else inventory)
    cases.append({"args": args, "inv": inv, "hist": hist, "r": enc(r), "cur": [[b.key for b in cur.recommended], [b.key for b in cur.gaps]]})
texts = ["Strike King 5XD crankbait", "Z-Man ChatterBait Jackhammer", "Berkley PowerBait MaxScent Fluke", "Yamamoto Senko", "rage tail craw texas rig",
         "Booyah buzz bait", "spoon", "jig + craw trailer", "something unknown (big)", "Paddle-tail swimbait", "Frog", "Duh Spoon flutter", "Thunder Cricket"]
fx = {"cases": cases, "inventory": inventory, "trips": trips,
      "gaps": lures.find_inventory_gaps(inventory),
      "guess": [[t, lures.guess_category_from_text(t)] for t in texts] + [["", lures.guess_category_from_text("", None)]],
      "videos_for": [[t, videos.get_videos_for(t)] for t in texts],
      "trailer": [[it, lures.is_trailer_eligible(it)] for it in inventory[:30]] + [[{"category": "texas_rig_creature", "brand": "x", "description": "Rage Craw"}, lures.is_trailer_eligible({"category": "texas_rig_creature", "brand": "x", "description": "Rage Craw"})]]}
import gzip
from core import daily_leaderboard as dl, activity_log  # noqa: E402
from datetime import date
board_rows = []
for i in range(260):
    d = date(2026, 11, rng.randrange(1, 15)).isoformat()
    cond = {"angler": rng.choice(["John", "Matthew", "Alex", " ", "", "Pal"]), "source": rng.choice(["spot_session", "manual", None])}
    if rng.random() < 0.15:
        cond["session_end_time"] = "18:00:00"
    if rng.random() < 0.7:
        cond["fish"] = [rng.choice([{"species": rng.choice(["Largemouth", "Spotted", "Crappie", "", None, "largemouth"]), "weight_lb": rng.choice([0, 1.25, 2.6, "3.1", "", None, "x", 4.0]),
                                     "count": rng.choice([None, 1, 2, "3", "x", 0, -2])}, "bad"]) for _ in range(rng.randrange(0, 4))]
    board_rows.append({"trip_date": d, "fish_caught": rng.choice(["0", "1", "2.0", "", "x", 3]), "biggest_fish_lb": rng.choice(["", "2.5", "x", None, "0"]), "conditions_json": json.dumps(cond)})
board = []
for today in ["2026-11-03", "2026-11-08", "2026-11-10", "2026-11-14", "2026-11-20"]:
    day, week = dl.build_daily_activity(board_rows, today), dl.build_weekly_activity(board_rows, date.fromisoformat(today))
    board.append({"today": today, "week_bounds": [x.isoformat() for x in dl.week_bounds(date.fromisoformat(today))],
                  "day": enc(day), "week": enc(week), "awards_day": enc(dl.daily_awards(day)), "awards_week": enc(dl.daily_awards(week)),
                  "table_day": dl.leaderboard_table_rows(day), "table_week": dl.leaderboard_table_rows(week), "total_week": dl.grand_total(week)})
fx["board_rows"] = board_rows; fx["board"] = board
fx["lb_oz"] = [[w, activity_log.format_weight_lb_oz(w)] for w in [0, 0.03125, 0.0625, 0.5, 1, 1.03125, 3.53, 2.96875, "2.5", "x", None, -1, 15.99]]
out = ROOT / "web" / "src" / "lib" / "fixtures" / "lures.fixtures.json.gz"
out.write_bytes(gzip.compress(json.dumps(fx, separators=(",", ":"), ensure_ascii=False).encode(), mtime=0))
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(cases)} cases)")
