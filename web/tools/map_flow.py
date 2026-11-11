"""Walk the Lake Map on the demo backend (iPhone 13, light + dark). Map tiles don't load in the sandbox (blank background).
    python3 web/tools/map_flow.py OUTDIR   (needs the BASE vite preview on :4173)"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for theme in ("light", "dark"):
        ctx = b.new_context(**p.devices["iPhone 13"], geolocation={"latitude": 37.3285, "longitude": -86.1405}, permissions=["geolocation"])
        for pat in ("**/api.open-meteo.com/**", "**/waterservices.usgs.gov/**", "**/fonts.googleapis.com/**", "**/arcgisonline.com/**", "**/tile.openstreetmap.org/**"):
            ctx.route(pat, lambda r: r.abort())
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(f"localStorage.setItem('fm.theme', JSON.stringify({{mode:'{theme}',until:null}}))")
        pg.goto("http://localhost:4173/Voskuil-Fishin-Magician/?demo#map"); pg.wait_for_timeout(1500)
        pg.screenshot(path=str(out / f"m1-map-{theme}.png"))
        pg.get_by_role("button", name="Hot spots").click(); pg.wait_for_timeout(500)
        pg.get_by_role("button", name="Any time").click(); pg.wait_for_timeout(300)
        pg.screenshot(path=str(out / f"m2-hot-{theme}.png"))
        pg.locator(".rank-row").first.click(); pg.wait_for_timeout(600)
        pg.screenshot(path=str(out / f"m3-spot-{theme}.png"))
        pg.get_by_role("button", name="Close").last.click(); pg.wait_for_timeout(400)
        pg.get_by_role("button", name="Save where I am").click(); pg.wait_for_selector("text=Name this spot", timeout=8000)
        pg.locator(".sheet input[type=text]").fill("Test Point"); pg.get_by_role("button", name="Main-lake point").click()
        pg.screenshot(path=str(out / f"m4-name-{theme}.png"))
        pg.get_by_role("button", name="Save spot").click(); pg.wait_for_timeout(900)
        pg.screenshot(path=str(out / f"m5-saved-{theme}.png"))
        pg.get_by_role("button", name="Fish here now").click(); pg.wait_for_timeout(1000)
        print(theme, "session spot:", pg.locator("#screen-session select").first.input_value() != "", "| kicker:", pg.locator("#screen-session .kicker").first.inner_text()[:40], "| errors:", errs)
        ctx.close()
    b.close()
