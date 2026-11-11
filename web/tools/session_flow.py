"""Walk the Spot Session on the demo backend (iPhone 13, light + dark) and screenshot each step.
    python3 web/tools/session_flow.py OUTDIR      (needs the BASE vite preview on :4173)"""
import gzip, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
fx = json.loads(gzip.open(ROOT / "src/lib/fixtures/engine.fixtures.json.gz").read())
bundle = next(b for b in fx["bundles"] if b["anchor"] == "2026-11-10")["bundle"]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
def full(pg, name):
    h = pg.locator("#screen-session").evaluate("e => e.scrollHeight")
    pg.set_viewport_size({"width": 390, "height": max(664, h + 70)}); pg.wait_for_timeout(250)
    pg.screenshot(path=str(out / name)); pg.set_viewport_size({"width": 390, "height": 664}); pg.wait_for_timeout(150)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for theme in ("light", "dark"):
        ctx = b.new_context(**p.devices["iPhone 13"])
        ctx.route("**/api.open-meteo.com/**", lambda r: r.fulfill(json=bundle))
        ctx.route("**/waterservices.usgs.gov/**", lambda r: r.abort())
        ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.add_init_script(f"localStorage.setItem('fm.theme', JSON.stringify({{mode:'{theme}',until:null}}))")
        pg.goto("http://localhost:4173/Voskuil-Fishin-Magician/?demo#session"); pg.wait_for_timeout(1200)
        full(pg, f"1-start-{theme}.png")
        if pg.get_by_role("button", name="End session").count():   # demo seeds an open session: exercise Live first
            pg.get_by_role("button", name="+ Fish").first.click(); pg.wait_for_timeout(400)
            pg.screenshot(path=str(out / f"1b-fish-{theme}.png"))
            pg.get_by_role("button", name="Save").first.click(); pg.wait_for_timeout(500)
            pg.locator(".rig select").first.select_option("drop_shot"); pg.wait_for_timeout(300)
            full(pg, f"1c-logged-{theme}.png")
            pg.get_by_role("button", name="Cancel", exact=True).click(); pg.wait_for_timeout(300)
            pg.screenshot(path=str(out / f"1d-cancel-{theme}.png"))
            pg.get_by_role("button", name="Delete session").click(); pg.wait_for_timeout(800)
        sel = pg.locator("select").first
        sel.select_option(index=1); pg.wait_for_timeout(500)
        tog = pg.get_by_role("button", name="Fishing with Fishing Buddy?")
        if tog.count():
            tog.first.click(); pg.wait_for_timeout(500)
            full(pg, f"2b-together-{theme}.png")
        full(pg, f"2-setup-{theme}.png")
        pg.get_by_role("button", name="Tackle box").click(); pg.wait_for_timeout(300)
        pg.get_by_role("textbox").last.fill("roboworm"); pg.wait_for_timeout(200)
        pg.get_by_role("button", name="Roboworm").first.click(); pg.wait_for_timeout(300)
        pg.get_by_role("button", name="Done").click(); pg.wait_for_timeout(300)
        pg.get_by_role("button", name="+ Add").first.click(); pg.wait_for_timeout(400)
        nt = pg.get_by_role("button", name="Add lure", exact=True)
        if nt.count(): nt.first.click(); pg.wait_for_timeout(300)
        full(pg, f"3-lures-{theme}.png")
        pg.get_by_role("button", name="Start session").click(); pg.wait_for_timeout(600)
        full(pg, f"4-live-{theme}.png")
        pg.get_by_role("button", name="+ Fish").first.click(); pg.wait_for_timeout(400)
        pg.screenshot(path=str(out / f"5-fish-{theme}.png"))
        pg.get_by_role("button", name="Save").first.click(); pg.wait_for_timeout(500)
        full(pg, f"6-logged-{theme}.png")
        # the buddy changes conditions on their phone: bump their open row in the demo store, reload, our session should follow
        pg.evaluate("""() => { const k = 'fm.demo.v3', st = JSON.parse(localStorage.getItem(k));
          for (const t of st.trips) if (t.owner && t.owner.startsWith('buddy') && t.conditions && !t.conditions.lure_end_time && t.conditions.source === 'spot_session') {
            t.conditions.water_temp_f = 52.5; t.conditions.wind_band = 'Moderate Chop'; t.conditions.conditions_set_at = '2099-01-01T00:00:00'; }
          localStorage.setItem(k, JSON.stringify(st)); }""")
        pg.reload(); pg.wait_for_timeout(1800)
        full(pg, f"7-followed-{theme}.png")
        print(theme, "followed:", pg.locator("body").inner_text().count("updated conditions") > 0 or "52.5" in pg.content())
        print(theme, "errors:", errs)
        ctx.close()
    b.close()
