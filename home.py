import streamlit as st

from core.appstate import get_weather_bundle, get_calibrated_weights
from core.scoring import score_day
from core.weather import lake_today

st.set_page_config(page_title="Voskuil Fishin' Magician", page_icon="🎣", layout="wide")

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

if bundle is not None:
    try:
        today = score_day(bundle, lake_today(), weights=weights)

        st.subheader("Today at a glance")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Activity score", f"{today.overall_score} / 10")
        col2.metric("Est. water temp", f"{today.water_temp_f}°F")
        col3.metric("Moon phase", today.moon.name)
        col4.metric("Pressure trend (24h)", f"{today.pressure_trend_24h:+.1f} hPa")

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
st.caption(
    "Nolin River Lake summer/normal pool: 515 ft elevation, ~5,795 surface acres. "
    "Lake map locations are planning approximations - verify with your own GPS/chartplotter on the water."
)
