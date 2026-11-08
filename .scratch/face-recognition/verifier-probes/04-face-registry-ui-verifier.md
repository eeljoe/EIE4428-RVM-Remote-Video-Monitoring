# 04 verifier probes — face registry UI (r1)

Verifier: independent gate, HEAD `f13f0dc2140f54a0dad59b8a44bb4989a02ab0a8`.
Worktree: `C:\Users\joe\AppData\Local\Temp\verify-04v-f13f0dc` (gate-kit, ref f13f0dc).

## Method (what is real, what is stubbed)

The real operator page (`/`) is iframed by a temporary same-origin driver page
`src/rvm/web/verify04-driver.html` inside the verification worktree (a copy is
archived here as `04-verifier-driver.html`). The driver types into `#face-name`,
clicks `#face-remember` / `button.x`, and prints the resulting DOM state into a
banner div that headless Edge (`--headless=new --screenshot --dump-dom
--virtual-time-budget`) captures in both the PNG and the DOM dump. Because
`--virtual-time-budget` fires timers instantly but holds on pending fetches,
every wait inside the driver is paced by real `GET /api/faces/known`
round-trips, not `setTimeout`.

Servers (main venv python, worktree cwd):

- `:8141` `--no-camera` → empty registry (`C:\…\v04-empty\known_faces.json`, never created)
- `:8142` `--no-camera` → seeded `{"version":1,"faces":{"Alice Ng":[1404 zeros],"Bob O'Neil \"Q\"":[…],"<img src=x onerror=window.__pwned=1>":[…]}}`
- `:8143` `--no-camera --no-analysis` → real `analysis-disabled`
- `:8148` fresh `--no-camera` → real `models-loading` (warmup window ~1.2–1.6 s on this box; driver clicks the moment `face-remember.onclick` exists, before the MJPEG-delayed iframe `load` event)

**Stubbed (labelled)**: `stub-ok`, `stub-multi`, `stub-dup`, `stub-loading`
override the iframe's `window.fetch` for `POST` only and return contract-shaped
bodies (201 / 409×2 / 503). A synthetic scene contains no real faces, so a real
201 / `multiple-faces` / `name-exists` response cannot be produced on this rig —
identical to the implementer's stated limitation. Everything else hits the real
server end-to-end. `race` delays the `GET` branch of fetch 400 ms (virtual)
while the stubbed POST resolves instantly; `subthresh` pushes a fabricated
out-of-contract payload through the real `w.render()` path.

## Probe outputs (rendered `#bar` lines, `04-verifier-probe-lines.txt`)

| case | real/stub | result |
|---|---|---|
| empty | real | `input=true btn=true btnText="REMEMBER FACE" status="" list="No names saved yet" xButtons=0 ids="0 faces, none known"` |
| click | real POST | `status="no face in frame, hold still" class="status err"` |
| clickempty | real POST | `status="the name must not be empty" class="status err"` |
| list | real GET | `rows=3 xButtons=3 names="<img src=x onerror=window.__pwned=1> | Alice Ng | Bob O'Neil \"Q\"" injectedElems=0 pwned=0 ids="no face"` |
| delete | real DELETE | `before=["<img…>","Alice Ng","Bob O'Neil \"Q\""] after=["Alice Ng","Bob O'Neil \"Q\""] listNow="Alice Ng | Bob O'Neil \"Q\"" status="" ids="no face"` |
| delname | real DELETE | `removed="Bob O'Neil \"Q\"" before=[2] after=["Alice Ng"]` |
| real-off | real POST | `status="analysis is off" ids="off"` |
| clickfast (loading.png) | real POST in warmup | `status="models still loading" ids="loading"` |
| stub-ok | stub POST 201 | `status="Saved as Stub Person, 3 frames averaged" class="status ok" list="Alice Ng | Stub Person" ids="no face"` |
| stub-multi | stub POST 409 | `status="more than one face in frame" class="status err"` |
| stub-dup | stub POST 409 | `status="Alice Ng is already saved" class="status warn"` |
| stub-loading | stub POST 503 | `status="models still loading" class="status"` |
| mobile | real | `scrollW=390 clientW=390 regOrder=4 regTop=656 list="Alice Ng" ids="no face"` |
| race | stub POST + delayed GET | **stale write**: `status="Saved as Race Person…" list="No names saved yet" ids="0 faces, none known"` |
| subthresh | fabricated payload | `ids="Low Conf · 0.59"` |

`deletexss` returned `ERROR row not found` — probe sequencing: the earlier
`delete` case had already removed the `<img…>` row (the row was first in the
seeded order), so the real DELETE of the XSS name is already proven by
`delete`. No product fault.

## Files

- `04-verifier-driver.html` — the driver page (verbatim copy of the worktree temp file)
- `04-verifier-<case>.png` — screenshots (banner line + rendered page)
- `04-dom/<case>.html` — `--dump-dom` output per case (contains the banner)
- `04-verifier-probe-lines.txt` — consolidated `#bar` lines

## Static/server checks

- `v04-empty/known_faces.json` absent after real 409/400 POSTs → failures write nothing.
- `v04-seed/known_faces.json` contains only `["Alice Ng"]` after the real deletes → persisted, rewritten.
- `GET /api/faces/known` before/after each delete probe → server truth matches the rendered list.
- `git diff 9681d6c…HEAD -- src/rvm/web/style.css src/rvm/web/index.html` → empty (registry shell was 03's; CSS/IDs unchanged).
- pytest `-q` full suite: 569 collected, all pass (ledger 04-r1-004).
- Mutations killed (ledger 04-r1-005/006 + one unwrapped run):
  `confidence < self.threshold`→`<=` (recognition.py) red;
  `"no face in frame, hold still"`→other copy (app.js) red;
  `who.textContent`→`innerHTML` (app.js) red.
