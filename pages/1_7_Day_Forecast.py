import streamlit as st
from datetime import date

from core.appstate import get_weather_bundle, get_calibrated_weights, get_spots
from core.scoring import score_week
from core.lures import recommend, WATER_CLARITY_OPTIONS, STRUCTURE_TYPES
from core.videos import get_videos_for

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

with st.sidebar:
    st.header("Lure setup inputs")
    clarity = st.selectbox("Water clarity", WATER_CLARITY_OPTIONS, index=1)
    structure = st.selectbox("Structure type", STRUCTURE_TYPES, index=0)
    st.caption("Nolin doesn't have a live water-clarity feed, so set this from your last trip or local knowledge.")

for day in week:
    with st.expander(f"{day.the_date.strftime('%A, %B %d')} - overall {day.overall_score}/10 | "
                      f"{day.season.replace('_', ' ').title()} | {day.moon.name}", expanded=(day.the_date == date.today())):

        c1, c2 = st.columns([2, 1])
        with c1:
            st.write(f"**Estimated water temp:** {day.water_temp_f}°F  |  "
                     f"**24h pressure trend:** {day.pressure_trend_24h:+.1f} hPa  |  "
                     f"**Moon illumination:** {day.moon.illumination_pct:.0f}%")
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

        st.write("**Lure / color / technique by time of day:**")
        for seg in day.segments:
            rec = recommend(day.season, day.water_temp_f, seg.name, day.pressure_trend_24h, structure, clarity)
            with st.container(border=True):
                st.markdown(f"**{seg.name}** ({seg.start.strftime('%-I:%M %p')}-{seg.end.strftime('%-I:%M %p')}) - "
                            f"score {seg.score}/10")
                lc1, lc2, lc3 = st.columns(3)
                lc1.write(f"**Colors:** {', '.join(rec.colors)}")
                lc2.write(f"**Depth:** {rec.target_depth}")
                lc3.write(f"**Retrieve:** {rec.retrieve}")
                st.write(f"**Technique:** {rec.technique}")

                st.caption("**Lures** (tap one for a couple of how-to videos):")
                lure_cols = st.columns(len(rec.primary_lures))
                for lc, lure in zip(lure_cols, rec.primary_lures):
                    with lc:
                        with st.popover(lure, use_container_width=True):
                            for v in get_videos_for(lure):
                                st.markdown(f"- [{v['title']}]({v['url']})")

                if rec.also_worth_trying:
                    st.caption("**Also worth trying:**")
                    also_cols = st.columns(len(rec.also_worth_trying))
                    for ac, lure in zip(also_cols, rec.also_worth_trying):
                        with ac:
                            with st.popover(lure, use_container_width=True):
                                for v in get_videos_for(lure):
                                    st.markdown(f"- [{v['title']}]({v['url']})")

                if rec.rationale:
                    st.caption(" · ".join(rec.rationale))
