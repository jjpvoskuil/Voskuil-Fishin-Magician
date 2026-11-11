"""Generate parity fixtures for the JavaScript engine port (web/src/lib/engine.test.js) from the Python reference.

Run from the repo root, ALWAYS with TZ=UTC (the live Streamlit server runs in UTC, and core/astro.py treats naive
datetimes as the server's local time - so UTC is what the real app computes):

    TZ=UTC python3 web/tools/make_engine_fixtures.py

Everything here is made up (synthetic weather and trips) - no real trip data goes into the committed fixtures.
"""
from __future__ import annotations
import dataclasses, json, math, random, sys
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import time as _t
assert _t.timezone == 0 and not _t.daylight, "run with TZ=UTC"

from core import astro, onwater, scoring, calibration, thermocline  # noqa: E402
from core.weather import WeatherBundle, pressure_trend_hpa_per_24h, estimate_water_temp_f, HOURLY_VARS  # noqa: E402

rng = random.Random(20261110)
OUT = ROOT / "web" / "src" / "lib" / "fixtures" / "engine.fixtures.json.gz"


def enc(o):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, date):
        return o.isoformat()
    if dataclasses.is_dataclass(o):
        return {f.name: enc(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, dict):
        return {(k if isinstance(k, str) else "|".join(map(str, k))): enc(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [enc(x) for x in o]
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None
    return o


def sun_times(d: date):
    """Rough sunrise/sunset for Nolin Lake in local clock time (only needs to be plausible)."""
    doy = d.timetuple().tm_yday
    dst = date(d.year, 3, 8) <= d < date(d.year, 11, 1)
    day_len = 12 + 2.4 * math.sin(2 * math.pi * (doy - 80) / 365)
    noon = 12.0 + 0.2 * math.sin(2 * math.pi * (doy - 10) / 365) + (1 if dst else 0)
    rise, set_ = noon - day_len / 2, noon + day_len / 2
    def fmt(h):
        hh, mm = int(h), int(round((h - int(h)) * 60)) % 60
        return datetime.combine(d, dtime(hh, mm)).isoformat(timespec="minutes")
    return fmt(rise), fmt(set_)


def make_bundle(anchor: date, style: str) -> dict:
    start, end = anchor - timedelta(days=14), anchor + timedelta(days=7)
    doy0 = anchor.timetuple().tm_yday
    base_t = 55 + 25 * math.sin(2 * math.pi * (doy0 - 110) / 365)
    hourly = {k: [] for k in ["time"] + HOURLY_VARS}
    daily = {"time": [], "sunrise": [], "sunset": [], "temperature_2m_max": [], "temperature_2m_min": []}
    p = 1015.0
    d = start
    while d < end:
        rise, set_ = sun_times(d)
        daily["time"].append(d.isoformat()); daily["sunrise"].append(rise); daily["sunset"].append(set_)
        temps = []
        stormy = style == "stormy" and rng.random() < 0.4
        for h in range(24):
            t = base_t + 10 * math.sin(2 * math.pi * (h - 9) / 24) + rng.uniform(-3, 3)
            temps.append(t)
            p += rng.uniform(-0.6, 0.6) + (-0.4 if stormy else 0)
            p = min(max(p, 990), 1035)
            hourly["time"].append(datetime.combine(d, dtime(h, 0)).isoformat(timespec="minutes"))
            hourly["temperature_2m"].append(round(t, 1))
            hourly["surface_pressure"].append(None if style == "gappy" and rng.random() < 0.05 else round(p, 1))
            cc = rng.choice([0, 5, 15, 30, 50, 70, 90, 100]) if style != "clear" else rng.choice([0, 5, 10, 20])
            hourly["cloudcover"].append(None if style == "gappy" and rng.random() < 0.1 else cc)
            hourly["windspeed_10m"].append(round(rng.uniform(0, 25 if stormy else 15), 1))
            hourly["winddirection_10m"].append(rng.randrange(0, 360))
            prob = rng.choice([0, 0, 10, 30, 60, 90]) if style != "clear" else 0
            hourly["precipitation_probability"].append(None if style == "gappy" and rng.random() < 0.1 else prob)
            hourly["precipitation"].append(round(rng.uniform(0, 0.3 if stormy else 0.04), 2) if prob else 0.0)
        daily["temperature_2m_max"].append(None if style == "gappy" and rng.random() < 0.2 else round(max(temps), 1))
        daily["temperature_2m_min"].append(round(min(temps), 1))
        d += timedelta(days=1)
    return {"hourly": hourly, "daily": daily}


def main():
    fx = {"weights": scoring.DEFAULT_WEIGHTS}

    # moon phase + solunar
    t0 = datetime(2026, 1, 1, 0, 0)
    fx["moon"] = []
    for i in range(160):
        t = t0 + timedelta(days=i * 2.37, minutes=i * 37)
        fx["moon"].append({"t": t.isoformat(), "r": enc(astro.moon_phase(t))})
    fx["solunar"] = []
    for i in range(45):
        d = date(2026, 1, 3) + timedelta(days=i * 8 + (i % 3))
        tz = -5 if i % 4 else -6
        fx["solunar"].append({"d": d.isoformat(), "tz": tz, "r": enc(astro.solunar_times(d, 37.2783, -86.2475, tz))})

    # onwater / thermocline grids
    temps = [x / 2 for x in range(60, 200)] + [49.999, 50.0, 62.0, 62.5, 63.0, 76.0, 76.5, 84.0, 84.0005, 84.001]
    fx["water_temp_band"] = [[t, onwater.water_temp_band(t)["label"]] for t in temps]
    fx["season_stage"] = [[doy, t, scoring.season_stage(doy, t)] for doy in (30, 60, 100, 150, 151, 200, 250, 251, 300, 350) for t in (45, 50, 55, 59.9, 60, 64.9, 65, 70, 74.9, 75, 79.9, 80, 90)]
    fx["wind_band"] = [[m, onwater.wind_band(m)["label"]] for m in [0, 1, 3, 3.5, 4, 9, 9.5, 10, 16, 16.5, 17, 30]]
    fx["wind_dir"] = [[deg, onwater.wind_direction_for_degrees(deg)] for deg in [0, 22.4, 22.5, 44.9, 45, 180, 337.4, 337.5, 359.9, 360, 725, -10]]
    fx["light"] = [[c, onwater.light_condition_for_cloud_pct(c)] for c in [0, 12.5, 13, 32.5, 33, 60, 61, 85, 86, 100]]
    fx["clarity"] = [[s, sc, st, onwater.resolve_water_clarity(s, sc, st)] for s in (0.5, 1.5, 2.5, 4.0, 6) for sc in (None, "Green stained", "Brown stained", "Weird") for st in (False, True)]
    fx["precip_opt"] = [[i, p, onwater.precipitation_option_for_forecast(i, p)] for i in (0, 0.14, 0.15, 0.54, 0.55, 1.14, 1.15) for p in (0, 19.9, 20, 54.9, 55, 82.4, 82.5)]
    fx["thermo"] = [[f"2026-{m:02d}-15", thermocline.estimate_thermocline_band_ft(date(2026, m, 15)), thermocline.default_thermocline_input_ft(date(2026, m, 15))] for m in range(1, 13)]
    fx["thermo_caveat"] = [[th, fd, thermocline.thermocline_caveat(th, fd)] for th in (None, 15.0, 16.5) for fd in (None, 10.0, 16.5, 22.4, 22.5)]

    # segment scores over many combinations
    fx["segment"] = []
    seasons = ["winter", "pre_spawn", "spawn", "summer_peak", "post_spawn_summer", "fall_turnover", "fall_feed_up"]
    clarities = [None, "Clear", "Green stained", "Brown stained", "Muddy"]
    for i in range(500):
        moon_t = t0 + timedelta(days=rng.uniform(0, 300))
        args = dict(
            segment_name=rng.choice(scoring.SEGMENTS), season=rng.choice(seasons),
            avg_cloud_pct=rng.choice([0, 10, 25, 25.5, 40, 59.9, 60, 90, 100]), avg_wind_mph=rng.choice([0, 1.9, 2, 3.9, 4, 9, 14, 14.1, 20, 20.1, 25]),
            total_precip_in=rng.choice([0, 0.0, 0.1, 0.5, 0.51, 1.0, 1.01, 2]), max_precip_prob_pct=rng.choice([0, 50, 70, 71, 85, 86, 100]),
            pressure_trend_24h=rng.choice([-3, -1.5, -1.49, 0, 0.3, 0.31, 1.99, 2.0, 4]),
            solunar_overlap=rng.choice([None, "minor", "major"]),
            water_temp_f=rng.choice([None, 45, 49.999, 55, 62.4, 62.5, 70, 77, 80, 81.3, 86.4, 92.9, 95]),
            water_clarity=rng.choice(clarities), forage_present=rng.choice([None, False, True]),
            location_adjustment=rng.choice([0.0, 0.0, 0.214, -0.31]), location_adjustment_n=rng.choice([None, 5, 12]),
        )
        weights = None if i % 3 else {"cloud_clear_sky_penalty": -0.6, "wind_sweet_spot_bonus": 0.62, "moon_dawn_new_bonus": 1.0}
        r = scoring.manual_segment_score(**args, weights=weights, at_time=moon_t)
        fx["segment"].append({"args": enc(args), "weights": weights, "at": moon_t.isoformat(), "r": enc(r)})

    # whole forecasts from synthetic weather
    fx["bundles"] = []
    for anchor, style in [(date(2026, 3, 5), "normal"), (date(2026, 3, 10), "gappy"), (date(2026, 5, 2), "stormy"),
                          (date(2026, 7, 15), "clear"), (date(2026, 9, 20), "normal"), (date(2026, 10, 29), "stormy"),
                          (date(2026, 11, 10), "normal"), (date(2026, 12, 27), "gappy")]:
        b = make_bundle(anchor, style)
        wb = WeatherBundle(hourly=b["hourly"], daily=b["daily"])
        entry = {"anchor": anchor.isoformat(), "style": style, "bundle": b,
                 "week": enc(scoring.score_week(wb, anchor, 8)),  # 8: the last day has no data and must be skipped
                 "week_w": enc(scoring.score_week(wb, anchor, 3, {"pressure_falling": 1.8, "season_spring_fall_bonus": 1.0})),
                 "trend": [], "water": [], "rt": []}
        for _ in range(12):
            at_t = datetime.combine(anchor, dtime(0, 0)) + timedelta(minutes=rng.randrange(-3 * 1440, 6 * 1440))
            entry["trend"].append([at_t.isoformat(), pressure_trend_hpa_per_24h(wb, at_t)])
        for k in range(-2, 8):
            d = anchor + timedelta(days=k)
            entry["water"].append([d.isoformat(), estimate_water_temp_f(wb, d, d.timetuple().tm_yday)])
        for seg in scoring.SEGMENTS:
            at_t = datetime.combine(anchor, dtime(rng.randrange(0, 24), rng.randrange(0, 60)))
            entry["rt"].append([seg, at_t.isoformat(), enc(scoring.realtime_context_from_bundle(wb, seg, anchor, at_time=at_t))])
        fx["bundles"].append(entry)

    # calibration from synthetic trips
    trips = []
    spots = [("s1", "Stripe Island Point"), ("s2", "Dam Bluff"), ("s3", "Moutardier Flats"), ("s4", "Wax Cove")]
    for i in range(320):
        d = date(2026, 8, 1) + timedelta(days=rng.randrange(0, 100))
        seg = rng.choice(scoring.SEGMENTS)
        spot = rng.choice(spots + [("", "")])
        start = dtime(rng.randrange(5, 20), rng.randrange(0, 60), rng.randrange(0, 60), rng.choice([0, 0, 123456]))
        dur = rng.choice([0.02, 0.1, 0.5, 1, 1.5, 2.5, 4, 6.5])
        end_dt = datetime.combine(d, start) + timedelta(hours=dur)
        end = end_dt.time() if end_dt.date() == d else dtime(23, 59)
        cond = {"pressure_trend_24h": rng.choice([-2, -1.5, 0, 1, 2, 3, None]), "moon_near_new_full": rng.choice([True, False]),
                "avg_cloud_pct": rng.choice([0, 30, 60, 90, None]), "avg_wind_mph": rng.choice([0, 3, 4, 10, 14, 18, None]),
                "lure_start_time": start.isoformat(), "lure_end_time": end.isoformat()}
        if rng.random() < 0.05:
            cond["times_estimated"] = True
        if rng.random() < 0.03:
            cond.pop("lure_end_time")
        fish = rng.choice(["0", "1", "2", "3", "5", "", "x", "2.0", "-1"]) if rng.random() < 0.95 else rng.choice(["0", "1"])
        trips.append({"trip_id": f"t{i}", "trip_date": d.isoformat() if rng.random() > 0.02 else "bad-date", "segment": seg,
                      "spot_id": spot[0], "spot_name": spot[1], "fish_caught": fish, "conditions_json": json.dumps(cond)})
    trips.append({"trip_id": "bad", "trip_date": "2026-08-02", "segment": "Dawn", "spot_id": "s1", "fish_caught": "1", "conditions_json": "[1,2]"})
    fx["trips"] = trips
    fx["trip_rate"] = [calibration.trip_fish_per_hour(t) for t in trips]
    fx["calibrated"] = calibration.calibrate_weights(trips)
    fx["calibrated_small"] = calibration.calibrate_weights(trips[:25])
    fx["location"] = enc(calibration.location_adjustments(trips))
    fx["dawn_rates_all"] = enc(calibration.moon_illumination_dawn_rates(trips))
    fx["dawn_rates_window"] = enc(calibration.moon_illumination_dawn_rates(trips, date(2026, 8, 10), date(2026, 9, 25)))
    fx["daily_catch"] = enc(calibration.daily_dawn_morning_catch(trips, date(2026, 8, 25), date(2026, 9, 14)))

    # score freezing (core/forecast_freeze.apply_freeze)
    import tempfile
    from core import forecast_freeze
    fb = next(b for b in fx["bundles"] if b["anchor"] == "2026-11-10")["bundle"]
    fx["freeze"] = []
    for now_s, pre in [("2026-11-10T05:00:00", None), ("2026-11-10T13:30:00", None), ("2026-11-10T13:30:00", ("Dawn", 9.9)), ("2026-11-11T07:00:00", ("Morning", 1.0))]:
        tmp = Path(tempfile.mkdtemp()) / "f.csv"
        forecast_freeze.ensure_file_exists(tmp)
        day = scoring.score_day(WeatherBundle(hourly=fb["hourly"], daily=fb["daily"]), date(2026, 11, 10))
        frozen_rows = []
        if pre:
            seg = next(s for s in day.segments if s.name == pre[0])
            frozen_rows = [{"the_date": "2026-11-10", "segment_name": pre[0], "score": pre[1], "solunar_overlap": "major", "notes": ["x"], "breakdown": [["Base", 5.0, "y"], ["Pretend", pre[1] - 5.0, "z"]]}]
            import csv as _csv
            with open(tmp, "a", newline="") as f:
                _csv.DictWriter(f, fieldnames=forecast_freeze.FIELDNAMES).writerow({"the_date": "2026-11-10", "segment_name": pre[0], "score": pre[1], "solunar_overlap": "major",
                    "notes_json": json.dumps(["x"]), "breakdown_json": json.dumps([["Base", 5.0, "y"], ["Pretend", pre[1] - 5.0, "z"]]), "frozen_at": "2026-11-10T08:00:00"})
        now = datetime.fromisoformat(now_s)
        names = forecast_freeze.apply_freeze(day, now=now, path=tmp)
        saved = [r for r in forecast_freeze._read_all_rows(tmp) if r["frozen_at"] == now.isoformat()]
        fx["freeze"].append({"now": now_s, "frozen": frozen_rows, "names": names, "day": enc(day),
                             "saved": [{"segment_name": r["segment_name"], "score": float(r["score"])} for r in saved]})

    # lake level (USGS) + USACE surface water quality parsing
    from core import lake_level, lake_water_quality as lwq
    from unittest import mock
    usgs = {"value": {"timeSeries": [{"sourceInfo": {"siteName": "NOLIN RIVER LAKE NEAR KYROCK, KY"},
             "values": [{"value": [{"value": "491.83", "dateTime": "2026-11-10T11:00:00.000-06:00"},
                                    {"value": "491.825", "dateTime": "2026-11-10T11:15:00.000-06:00"}]}]}]}}
    class R:
        def __init__(self, j=None, t=""): self._j, self.text = j, t
        def raise_for_status(self): pass
        def json(self): return self._j
    with mock.patch("core.lake_level.requests.get", return_value=R(usgs)):
        fx["usgs"] = {"payload": usgs, "latest": enc(lake_level.fetch_lake_level()), "history": enc(lake_level.fetch_lake_level_history())}
    html = """<table><tr><th>Station</th></tr>
<tr><td>Upper Lake</td><td>20261020, 0930</td><td>0</td><td>17.1</td><td>9.2</td></tr>
<tr><td> Dam Site </td><td>20261020, 1000</td><td>5</td><td>16.8</td><td>8.9</td></tr>
<tr><TD>Dam Site</TD><td>20261020, 1015</td><td> 0 </td><td>17.35</td><td>9.48</td></tr>
<tr><td>Dam Site</td><td>20260806, 1400</td><td>0</td><td>30.3</td><td>10.66</td></tr></table>"""
    with mock.patch("core.lake_water_quality.requests.get", return_value=R(t=html)):
        fx["usace"] = {"html": html, "r": enc(lwq.fetch_surface_water_quality())}
    with mock.patch("core.lake_water_quality.requests.get", return_value=R(t="<tr><td>x</td></tr>")):
        try:
            lwq.fetch_surface_water_quality(); fx["usace_missing"] = None
        except ValueError as e:
            fx["usace_missing"] = str(e)
    fx["do_sat"] = [[t, lwq._do_saturation_concentration_mg_l(t, 515.0)] for t in (0, 5.5, 12, 20, 25.3, 30, 34)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    import gzip
    OUT.write_bytes(gzip.compress(json.dumps(fx, separators=(",", ":")).encode(), mtime=0))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
