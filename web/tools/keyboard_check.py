"""Check every text box stays visible above an iPhone-sized on-screen keyboard (John, 11-10: "make sure the keyboard
doesn't hide the field"). Fakes iOS behaviour: the keyboard covers the bottom KB px without resizing the page, reported
only through window.visualViewport. Needs the vite preview running.   python3 web/tools/keyboard_check.py
"""
import gzip, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
KB = 380   # iPhone keyboard + its accessory bar, portrait
FAKE_VV = """
(() => {
  const listeners = {};
  const vv = { height: innerHeight, width: innerWidth, offsetTop: 0, offsetLeft: 0, scale: 1,
    addEventListener: (t, f) => (listeners[t] ||= []).push(f), removeEventListener: () => {} };
  Object.defineProperty(window, "visualViewport", { value: vv, configurable: true });
  const fire = () => ["resize", "scroll"].forEach((t) => (listeners[t] || []).forEach((f) => f()));
  document.addEventListener("focusin", (e) => { if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) && !/checkbox|radio/.test(e.target.type)) { vv.height = innerHeight - %d; fire(); } });
  document.addEventListener("focusout", () => setTimeout(() => { if (!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) { vv.height = innerHeight; fire(); } }, 50));
})();
""" % KB

# (tab, button that opens the form or None, accessible names / labels of the boxes to tap)
CASES = [
    ("Forecast", "Lake setup", ["Water visibility / Secchi depth (ft)", "Water temp (°F)", "Fish depth (ft)", "Location", "Structure type"]),
    ("More", "Add", ["Google email", "Name (shown on trips and the leaderboard)"]),
    # Session: the demo has an open session, so these open from the live screen
    ("Session", "↻ Moved / conditions", ["Water temp (°F)", "Visibility (ft)", "Depth fish are showing on electronics (ft, optional)"]),
    ("Session", ["＋ Add a lure", "Search the tackle box"], ["Search"]),
]
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    ctx = b.new_context(**p.devices["iPhone 13"])
    fx = json.loads(gzip.open(Path(__file__).resolve().parents[1] / "src/lib/fixtures/engine.fixtures.json.gz").read())
    bundle = next(x for x in fx["bundles"] if x["anchor"] == "2026-11-10")["bundle"]
    ctx.route("**/api.open-meteo.com/**", lambda r: r.fulfill(json=bundle))
    ctx.route("**/waterservices.usgs.gov/**", lambda r: r.fulfill(json=fx["usgs"]["payload"]))
    ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
    ctx.add_init_script(FAKE_VV)
    pg = ctx.new_page()
    for tab, opener, fields in CASES:
        pg.goto("http://localhost:4173/Voskuil-Fishin-Magician/?demo"); pg.wait_for_timeout(700)
        pg.get_by_role("button", name=tab, exact=True).last.click(); pg.wait_for_timeout(400)
        for o in ([opener] if isinstance(opener, str) else opener or []):
            pg.get_by_role("button", name=o, exact=True).first.click(); pg.wait_for_timeout(400)
        for name in fields:
            box = pg.get_by_label(name, exact=True).first if pg.get_by_label(name, exact=True).count() else pg.get_by_label(name).first
            box.tap() if False else box.click(); pg.wait_for_timeout(1000)
            r = box.bounding_box(); limit = pg.viewport_size["height"] - KB
            ok = r and r["y"] >= 0 and r["y"] + r["height"] <= limit
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {tab} / {name}: box {int(r['y'])}-{int(r['y'] + r['height'])} px, keyboard starts at {limit} px")
            pg.screenshot(path=f"/tmp/kb-{tab}-{name[:12].replace(' ', '_').replace('/', '')}.png")
            pg.keyboard.press("Escape") if False else pg.evaluate("document.activeElement.blur()"); pg.wait_for_timeout(300)
    b.close()
print("ALL FIELDS VISIBLE ABOVE THE KEYBOARD" if not bad else f"{bad} FIELD(S) HIDDEN BY THE KEYBOARD")
sys.exit(1 if bad else 0)
