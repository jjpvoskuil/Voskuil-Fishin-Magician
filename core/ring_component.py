"""The Stringer's ring hero swipe support - a real Streamlit custom
component (punch-list, angler's own ask; SESSION_NOTES entry 176 has the
full story on why this needed to be a genuine component rather than
another `st.markdown(unsafe_allow_html=True)` block: Streamlit's markdown
pipeline does not execute injected `<script>` tags, confirmed live before
any of this was built, so recognizing a swipe gesture at all needs real
client-side JS running somewhere it's actually allowed to run).

`core/components/stringer_ring/index.html` is the component's entire
frontend - hand-written vanilla HTML/CSS/JS, no build step, no framework -
served directly from that folder via `declare_component(path=...)`. It
renders ONE ring/description/secondary-stat card (the same visual as the
markdown block it replaces) and, on a horizontal swipe past a small pixel
threshold, reports a bare `{"action": "prev"|"next", "nonce": <float>}`
back to Python - see that file's own comments for why the nonce exists
(a component's last value is otherwise sticky across reruns) and why the
title/buttons/dots above and around this card are deliberately NOT part
of it (kept as plain, already-working Streamlit widgets).
"""
from __future__ import annotations

import os

import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "components", "stringer_ring")
_stringer_ring_component = components.declare_component("stringer_ring", path=_COMPONENT_DIR)


def stringer_ring_card(
    *, legend: str, value: float, total: float, desc: str,
    sec_label: str, sec_value: str, key: str,
) -> dict | None:
    """Render one hero card (ring + description + secondary stat) and
    return {"action": "prev"|"next", "nonce": float} the instant a new
    swipe on it is detected, else None. `value`/`total` drive the ring's
    fill fraction exactly like the markdown block this replaces did
    (`pct = value / total if total else 0`, clamped 0-1 on the frontend).

    Callers are expected to track their own "last nonce I actually acted
    on" (typically in st.session_state) and only treat a return value as a
    NEW swipe when its nonce differs from that - see this module's own
    docstring and pages/8_Leaderboard.py's calling code for why a bare
    "prev"/"next" alone isn't enough.
    """
    return _stringer_ring_component(
        legend=legend, value=value, total=total, desc=desc,
        secLabel=sec_label, secValue=sec_value, key=key, default=None,
    )
