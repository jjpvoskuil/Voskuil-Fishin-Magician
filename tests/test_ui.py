import pandas as pd

from core import ui
from core.ui import inject_mobile_css, render_line_chart, render_square_thumbnail


class _FakeCol:
    """Minimal stand-in for an st.columns()/st.container() slot - just
    captures what render_line_chart() calls on it, without needing a real
    Streamlit runtime (this is plain function behavior, testable without
    AppTest)."""

    def __init__(self):
        self.line_chart_calls = []
        self.altair_chart_calls = []

    def line_chart(self, series):
        self.line_chart_calls.append(series)

    def altair_chart(self, chart, width=None):
        self.altair_chart_calls.append((chart, width))


def _series():
    return pd.Series([70.1, 71.2, 69.8], index=["Mon 8/17", "Tue 8/18", "Wed 8/19"])


def test_render_line_chart_with_no_y_domain_uses_plain_line_chart():
    # Punch-list #20: every trend chart except the two temperature ones
    # should render exactly as before (unchanged st.line_chart auto-scale)
    # - no altair_chart call at all in this path.
    col = _FakeCol()
    s = _series()
    render_line_chart(col, s, None)
    assert len(col.line_chart_calls) == 1
    assert col.line_chart_calls[0] is s
    assert col.altair_chart_calls == []


def test_render_line_chart_with_y_domain_uses_altair_chart_with_fixed_scale():
    col = _FakeCol()
    render_line_chart(col, _series(), (45, 95))
    assert col.line_chart_calls == []
    assert len(col.altair_chart_calls) == 1
    chart, width = col.altair_chart_calls[0]
    spec = chart.to_dict()
    assert spec["encoding"]["y"]["scale"]["domain"] == [45, 95]
    assert width == "stretch"


def test_render_line_chart_y_domain_is_a_different_range_each_time():
    # Confirms the domain isn't hardcoded somewhere inside render_line_chart
    # itself - it comes from whatever the caller passes.
    col = _FakeCol()
    render_line_chart(col, _series(), (0, 10))
    spec = col.altair_chart_calls[0][0].to_dict()
    assert spec["encoding"]["y"]["scale"]["domain"] == [0, 10]


def test_render_line_chart_x_axis_preserves_series_order_not_alphabetical():
    # This app's non-USACE trend charts use formatted day strings ("Mon
    # 8/17") as the index, not real dates - Altair's default nominal-axis
    # sort is alphabetical by value, which would scramble a "Mon/Tue/Wed"
    # sequence. sort=None on the X encoding must be set to preserve the
    # Series' own point order instead.
    col = _FakeCol()
    render_line_chart(col, _series(), (45, 95))
    spec = col.altair_chart_calls[0][0].to_dict()
    # Vega-Lite treats an explicit `sort: null` as "keep data order" -
    # different from the key being absent entirely, which defaults to
    # alphabetical for a nominal field. Check the key is actually present.
    assert "sort" in spec["encoding"]["x"]
    assert spec["encoding"]["x"]["sort"] is None


# --- Punch-list #74: render_square_thumbnail() must shrink with its real ---
# container instead of overflowing it. Real report (with a screenshot): a
# Tackle Box card's 160px-fixed thumbnail overlapped the neighboring card
# once inject_mobile_css()'s reflow narrowed the actual column below that -
# every grid this renders into (Tackle Box, Scan-a-lure, Spot Session's lure
# picker) reflows down to MOBILE_COLUMN_MIN_WIDTH_PX (120px) on a narrow
# screen, well under every real size_px this is called with (96, 120, 160).

def test_render_square_thumbnail_caps_width_instead_of_fixing_it(monkeypatch):
    """The emitted HTML must let the thumbnail shrink to its container
    (width:100%) capped at size_px (max-width), not pin both width AND
    height to a bare size_px - the old shape that couldn't shrink at all."""
    calls = []
    monkeypatch.setattr(ui.st, "markdown", lambda html, **kw: calls.append(html))

    item = {"image_filename": "", "image_url": "https://example.com/lure.jpg"}
    result = render_square_thumbnail(item, size_px=160)

    assert result is True
    assert len(calls) == 1
    html = calls[0]
    assert "width:100%;max-width:160px" in html, f"thumbnail isn't responsive: {html!r}"
    assert "aspect-ratio:1" in html, f"no aspect-ratio to keep it square once width shrinks: {html!r}"
    # The old, overflow-prone shape must be gone.
    assert "width:160px;height:160px" not in html


def test_render_square_thumbnail_no_photo_renders_nothing():
    item = {"image_filename": "", "image_url": ""}
    assert render_square_thumbnail(item, size_px=160) is False


# --- Punch-list #75: a selectbox's own closed-value text (not the open ---
# dropdown list, which punch-list #33 already covers) must not hard-clip a
# long lure/trailer label mid-character on a narrow screen. Real report: on
# a phone, picking a trailer with a long "Brand - Product - Color, size"
# label (e.g. "Strike King - Rage Tail Craw Soft Bait - Fire Craw, 4",
# 7-pack") showed the text cut off mid-word with no ellipsis. Confirmed via
# live Playwright/DOM inspection (not just reasoning about the CSS) that
# Streamlit 1.63's st.selectbox renders through a React Aria ComboBox
# <input role="combobox">, a genuinely different element from the
# [data-baseweb="select"] div punch-list #33's CSS targets - so that
# existing CSS doesn't reach this text at all. Also confirmed live that
# text-overflow/overflow alone were NOT enough - white-space: nowrap is
# required too, or the browser never treats the value as overflowing and
# still hard-clips with no dots. (Confirmed separately, also live: the
# ellipsis only paints once the field loses focus, since a focused native
# input scrolls to keep the caret visible instead - that's normal, standard
# browser behavior for every text input, not something this CSS can or
# should override.)

def test_inject_mobile_css_makes_selectbox_value_text_ellipsize(monkeypatch):
    """The closed selectbox value must get overflow:hidden + ellipsis, and
    critically white-space:nowrap too - without nowrap, ellipsis silently
    does nothing on this input and it still hard-clips (confirmed live)."""
    calls = []
    monkeypatch.setattr(ui.st, "markdown", lambda html, **kw: calls.append(html))

    inject_mobile_css()

    assert len(calls) == 1
    css = calls[0]
    assert '[data-testid="stSelectbox"] input[role="combobox"]' in css
    # Pull out just the block for that selector so the assertions below
    # can't accidentally match some other unrelated rule.
    block_start = css.index('[data-testid="stSelectbox"] input[role="combobox"]')
    block = css[block_start:block_start + 400]
    assert "text-overflow: ellipsis" in block
    assert "overflow: hidden" in block
    assert "white-space: nowrap" in block


def test_inject_mobile_css_shrinks_selectbox_font_only_on_mobile(monkeypatch):
    """The smaller selectbox font (so more of a long value fits before the
    ellipsis kicks in) must be scoped inside the mobile media query, not
    applied to every screen size."""
    calls = []
    monkeypatch.setattr(ui.st, "markdown", lambda html, **kw: calls.append(html))

    inject_mobile_css()

    css = calls[0]
    media_start = css.index(f"@media (max-width: {ui.MOBILE_BREAKPOINT_PX}px)")
    mobile_block = css[media_start:]
    assert 'input[role="combobox"]' in mobile_block
    assert "font-size: 12.5px" in mobile_block
    # And it must NOT be sitting in the unconditional (pre-media-query) CSS.
    unconditional_block = css[:media_start]
    assert "font-size: 12.5px" not in unconditional_block
