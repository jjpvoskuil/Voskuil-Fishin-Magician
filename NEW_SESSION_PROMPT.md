# New-session prompt

Copy everything in the code block below into the first message of a new
Claude chat to pick this project back up. Fill in a **freshly generated**
GitHub PAT each time - never reuse one from a previous conversation, and
generate a new fine-grained token (Contents: Read and write, scoped to just
this repo) rather than pasting an old one back in.

```
I'm continuing work on my Nolin River Lake bass fishing forecast app.

Repo: https://github.com/jjpvoskuil/Voskuil-Fishin-Magician (branch main)
Stack: Streamlit (hosted on Streamlit Community Cloud), Python, pytest.

What it does: a 7-day largemouth bass activity forecast (1-10 scale) for
Nolin River Lake, KY, built from weather/moon phase/solunar theory and an
evidence-weighted scoring model, with per-time-segment lure/color/
presentation recommendations checked against your tackle inventory, a
click-anywhere fish-attractor/saved-spot map, an on-the-water "Spot
Session" page for live conditions plus logging (the only way to log a trip
now), a filterable/inline-editable Trip History page with per-trip edit/
delete, a tackle inventory with a photo-to-Cabela's-lookup "Scan a
lure" flow, and a Development page punch list for tracking app fixes/
adjustments between sessions (each item has a stable number, e.g. "#7").
The app is phone-friendly (bigger sidebar toggle, wide column rows reflow
on narrow screens) and works well added to an iPhone home screen via
Safari's Add to Home Screen.

Please clone the repo, then read SESSION_NOTES.md and README.md in full
before making any changes - SESSION_NOTES.md has the development history,
key design decisions, and known open items; README.md has the current
feature list and data-source documentation. Also check the Development
page's punch list (`data/dev_tasks.csv`) for open items - if I haven't
already told you which number(s) to work on this session, ask me before
starting.

Workflow to follow (established over many prior sessions - see
SESSION_NOTES.md "Operating notes"):
- Do all work in a cloned working copy, never ask me to copy/paste code.
- After any change: clean __pycache__, run `pytest tests/ -q`, run an
  AppTest-based smoke test across every page that can run in this sandbox
  (the 7-Day Forecast page needs a mocked weather bundle - this sandbox has
  no outbound network access to Open-Meteo - see tests/test_scoring.py's
  `_fake_bundle()` for the fixture shape other tests already use), and
  verify via a fresh `git clone` into a new temp dir before considering
  anything done.
- Commit with a descriptive message, then push directly with
  `git push` over
  `https://x-access-token:<PAT>@github.com/jjpvoskuil/Voskuil-Fishin-Magician.git`.
  If that push fails with a 403 from a "git proxy" (not a GitHub auth
  error) even with a fresh, valid PAT, this cloud sandbox has its own
  transparent proxy that blocks pushes to repos outside its "authorized
  sources" - work around it for just that one command:
  `env -u https_proxy -u HTTPS_PROXY git push ...`.
- Never echo the PAT back in a chat message, never commit it to any file.
- Update README.md (and SESSION_NOTES.md's development log, briefly) for
  any user-facing change.

Here's my GitHub PAT for this session (fine-grained, Contents: Read and
write, scoped to just this repo) - use it only inline in git commands:

<PASTE A FRESH PAT HERE - DO NOT REUSE AN OLD ONE>

If I forget to fill in a PAT above, ask me for one before attempting any
git push.
```
