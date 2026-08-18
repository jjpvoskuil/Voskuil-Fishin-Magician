import streamlit as st

from core.appstate import get_weather_bundle, get_calibrated_weights, get_lake_level
from core.scoring import score_day
from core.weather import lake_today
from core.lake_level import NORMAL_SUMMER_POOL_FT
from core.ui import inject_mobile_css

st.set_page_config(page_title="Voskuil Fishin' Magician", page_icon="🎣", layout="wide")
inject_mobile_css()

st.title("🎣 Voskuil Fishin' Magician")
st.caption("Largemouth bass fishing forecasts for Nolin River Lake, KY")

st.markdown(
    """
This app blends weather, moon phase, and solunar theory into a 1-10 daily
activity forecast for largemouth bass on Nolin River Lake, then recommends
where to fish and what to throw. Use the sidebar to navigate:

- **7 Day Forecast** - the full week, drill into any day for best times, lures, colors, and technique.
- **Lake Map** - click any spot on the lake, then **Spot Session** to get a live, on-the-water
  recommendation and log what actually happened so the model can learn from it.
- **Trip History** - filter and review your logged trips, and see how the model is calibrating.
"""
)

bundle = None
weights, n_trips = {}, 0
try:
    weights, n_trips = get_calibrated_weights()
    bundle = get_weather_bundle(7)
except Exception as e:
    st.error(f"Couldn't fetch live weather data right now: {e}")
    st.caption("This can happen if Open-Meteo is briefly unreachable - try refreshing in a minute.")

# Independent of the weather bundle above - a USGS outage shouldn't block
# the weather-derived metrics, and vice versa. Unlike everything else on
# this page (all weather-derived estimates), lake level is a genuine live
# measurement - USGS gauge 03310900 ("Nolin Lake near Kyrock, KY") reports
# the reservoir's actual real-time pool elevation. See core/lake_level.py.
lake_level = None
try:
    lake_level = get_lake_level()
except Exception:
    pass  # Shown as a footer caption fallback below rather than an st.error -
    # a missing "nice to have" live reading shouldn't read as alarming as a
    # failed weather fetch, which blocks the whole scored forecast above.

if bundle is not None:
    try:
        today = score_day(bundle, lake_today(), weights=weights)

        st.subheader("Today at a glance")
        cols = st.columns(5 if lake_level else 4)
        cols[0].metric("Activity score", f"{today.overall_score} / 10")
        cols[1].metric("Est. water temp", f"{today.water_temp_f}°F")
        cols[2].metric("Moon phase", today.moon.name)
        cols[3].metric("Pressure trend (24h)", f"{today.pressure_trend_24h:+.1f} hPa")
        if lake_level:
            cols[4].metric(
                "Lake level",
                f"{lake_level.elevation_ft:g} ft",
                delta=f"{lake_level.elevation_ft - NORMAL_SUMMER_POOL_FT:+.1f} ft vs. normal pool",
                delta_color="off",
                help=f"Live reading from USGS site 03310900 ({lake_level.site_name}), "
                     f"as of {lake_level.observed_at.strftime('%-I:%M %p %m/%d')}.",
            )

        best_segment = max(today.segments, key=lambda s: s.score)
        st.info(f"Best window today: **{best_segment.name}** ({best_segment.start.strftime('%-I:%M %p')} - "
                f"{best_segment.end.strftime('%-I:%M %p')}), score {best_segment.score}/10")

        if today.warnings:
            for w in today.warnings:
                st.warning(w)

        if n_trips > 0:
            st.caption(f"Model calibration: using {n_trips} logged trip(s) to nudge the default weights.")
        else:
            st.caption("Model calibration: no trips logged yet - using default weights. Log a trip to start improving it!")

    except ValueError as e:
        # Weather fetched fine, but today's date fell outside the returned window -
        # e.g. a briefly stale cached bundle right at the lake's local day rollover.
        st.warning(f"Today's forecast isn't available yet: {e}. Try refreshing in a moment.")

st.divider()
if lake_level is None:
    st.caption(
        "Couldn't fetch the live lake level just now (USGS site 03310900 may be briefly unreachable) - "
        "try refreshing in a minute."
    )
st.caption(
    f"Nolin River Lake summer/normal pool: {NORMAL_SUMMER_POOL_FT:g} ft elevation, ~5,795 surface acres. "
    "Lake map locations are planning approximations - verify with your own GPS/chartplotter on the water."
)
