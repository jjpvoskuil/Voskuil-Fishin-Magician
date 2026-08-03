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
Nolin River Lake, KY, built from weather/moon phase/solunar theory, with
per-time-segment lure/color/presentation recommendations, a click-anywhere
depth-contour map, trip logging that calibrates the model over time, and a
sidebar of shared inputs (water clarity, structure, water temp, fish depth,
thermocline depth, forage) that drives every recommendation.

Please clone the repo, then read SESSION_NOTES.md and README.md in full
before making any changes - SESSION_NOTES.md has the development history,
key design decisions, and known open items; README.md has the current
feature list and data-source documentation.

Workflow to follow (established over many prior sessions - see
SESSION_NOTES.md "Operating notes"):
- Do all work in a cloned working copy, never ask me to copy/paste code.
- After any change: clean __pycache__, run `pytest tests/ -q`, run the
  AppTest-based smoke test across all 5 pages, verify via a fresh
  `git clone` into a new temp dir before considering anything done.
- Commit with a descriptive message, then push directly with
  `git push` over `https://x-access-token:<PAT>@github.com/jjpvoskuil/Voskuil-Fishin-Magician.git`.
- Never echo the PAT back in a chat message, never commit it to any file.
- Update README.md (and SESSION_NOTES.md's development log, briefly) for
  any user-facing change.

Here's my GitHub PAT for this session (fine-grained, Contents: Read and
write, scoped to just this repo) - use it only inline in git commands:

<PASTE A FRESH PAT HERE - DO NOT REUSE AN OLD ONE>

If I forget to fill in a PAT above, ask me for one before attempting any
git push.
```
