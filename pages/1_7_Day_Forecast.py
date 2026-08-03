import streamlit as st
from datetime import date

from core.appstate import get_weather_bundle, get_calibrated_weights, get_spots
from core.scoring import score_week, effective_season_and_temp
from core.lures import recommend
from core.ui import render_lure_recommendation, render_lake_setup_sidebar

st.set_page_config(page_title="7 Day Forecast - Nolin Lake", page_icon="📅", layout="wide")
st.title("📅 7-Day Largemouth Bass Forecast")

weights, n_trips = get_calibrated_weights()
bundle = get_weather_bundle(7)
week = score_week(bundle, date.today(), 7, weights=weights)

st.caption(
    "Scores are 1 (least active) to 10 (most active), built from pressure trend, moon phase, "
    "solunar windows, cloud cover, wind, and season. " +
    (f"Calibrated using {n_trips} logged trips." if n_trips else "Using default weights - log trips to calibrate.")
)

cols = st.columns(7)
for col, day in zip(cols, week):
    with col:
        st.metric(day.the_date.strftime("%a %m/%d"), f"{day.overall_score}/10")

st.divider()

lake_setup = render_lake_setup_sidebar(include_structure=True, default_water_temp_f=week[0].water_temp_f)
clarity = lake_setup.water_clarity
structure = lake_setup.structure_type

for day in week:
    with st.expander(f"{day.the_date.strftime('%A, %B %d')} - overall {day.overall_score}/10 | "
                      f"{day.season.replace('_', ' ').title()} | {day.moon.name}", expanded=(day.the_date == date.today())):

        c1, c2 = st.columns([2, 1])
        with c1:
            eff_season, eff_water_temp = effective_season_and_temp(day, lake_setup.water_temp_override_f)
            st.write(f"**Water temp (Lake Setup Options):** {eff_water_temp}°F  |  "
                     f"**24h pressure trend:** {day.pressure_trend_24h:+.1f} hPa  |  "
                     f"**Moon illumination:** {day.moon.illumination_pct:.0f}%")
            if eff_season != day.season:
                st.caption(f"Your water temp puts this day in the {eff_season.replace('_', ' ').title()} pattern for "
                           f"lure selection (the weather-only estimate would be {day.season.replace('_', ' ').title()}).")
            st.write(f"**Sunrise:** {day.sunrise.strftime('%-I:%M %p')}  |  "
                     f"**Sunset:** {day.sunset.strftime('%-I:%M %p')}")
            ws = day.weather_summary
            st.write(f"Avg cloud cover {ws['avg_cloud_pct']:.0f}%, avg wind {ws['avg_wind_mph']:.0f} mph, "
                     f"high/low {ws['temp_hi_f']}°/{ws['temp_lo_f']}°F, "
                     f"precip chance {ws['max_precip_prob_pct']:.0f}%")
            for w in day.warnings:
                st.warning(w)

        with c2:
            best = max(day.segments, key=lambda s: s.score)
            st.success(f"Best window: **{best.name}**\n\n{best.start.strftime('%-I:%M %p')} - {best.end.strftime('%-I:%M %p')}")

        st.write("**Time-of-day breakdown:**")
        seg_cols = st.columns(len(day.segments))
        for sc, seg in zip(seg_cols, day.segments):
            with sc:
                st.metric(seg.name, f"{seg.score}/10", help="\n".join(seg.notes) if seg.notes else None)
                if seg.solunar_overlap:
                    st.caption(f"☾ solunar {seg.solunar_overlap}")

        st.write("**Lure setup by time of day** (expand a window for full lure blocks):")
        best_name = max(day.segments, key=lambda s: s.score).name
        for seg in day.segments:
            rec = recommend(eff_season, eff_water_temp, seg.name, day.pressure_trend_24h, structure, clarity,
                             fish_depth_ft=lake_setup.fish_depth_ft)
            with st.expander(
                f"{seg.name} ({seg.start.strftime('%-I:%M %p')}-{seg.end.strftime('%-I:%M %p')}) - score {seg.score}/10",
                expanded=(seg.name == best_name),
            ):
                render_lure_recommendation(rec)
