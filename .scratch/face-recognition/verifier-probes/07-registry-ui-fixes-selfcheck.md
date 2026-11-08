# 07 真机自检 — 注册控件收口（race 探针 + 首次加载）

Worker self-check for ticket 07. All commands below were run on this machine
(Windows, repo root `EIE4428-RVM`). Product HEAD at the time of the runs:
`fdf03c903ac1841a98cc038fa5bb2c04d6fb6e9b` (my four product files were
uncommitted working-tree changes on top of it).

Probe page: `.scratch/face-recognition/verifier-probes/07-driver.html`
(a temporary copy was placed at `src/rvm/web/07-driver.html` for each run and
**deleted afterwards**; `git status -- src` shows no leftover). It iframes `/`
same-origin, so `w.fetch`, `w.loadNames()`, `#face-name`, `#face-remember` are the
real page's own objects. No product file other than `src/rvm/web/app.js` differs
between the red and green runs.

## Server commands (three runs, same port 8099)

Empty registry (green race + red race):

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099 --known-faces %TEMP%\v07\empty\known_faces.json
→ RVM serving on http://0.0.0.0:8099/  (320x240 @ 15 fps, source: synthetic)
→ GET /api/faces/known = {"known": []}
```

Seeded registry (first-load check), seed file `%TEMP%\v07\seed\known_faces.json`
= `{"version":1,"faces":{"Alice Ng":[0.1,0.2]}}`:

```
.venv\Scripts\python.exe run_server.py --no-camera --port 8099 --known-faces %TEMP%\v07\seed\known_faces.json
→ GET /api/faces/known = {"known": ["Alice Ng"]}
```

Red run served the pre-fix `app.js` from a `git archive fdf03c9` copy in
`%TEMP%\w07b` (`sha256 04032A36…A8A5CC`, served bytes contain no `namesStamp`):

```
(workdir %TEMP%\w07b) ..\..\EIE4428-RVM\.venv\Scripts\python.exe run_server.py --no-camera --port 8099 --known-faces %TEMP%\v07\empty\known_faces.json
→ GET /static/app.js served has namesStamp = False   (green run: True)
```

## Browser commands

Screenshots and DOM dumps are two separate Chrome invocations: new headless
refuses `--screenshot` together with `--dump-dom` ("Multiple targets are not
supported in headless mode"). The screenshot path was written to `%TEMP%`
because a non-ASCII `--screenshot=` path is mangled into two positional
arguments on this host; the PNG was then copied into this directory.

```
chrome --headless=new --disable-gpu --hide-scrollbars --no-first-run \
  --user-data-dir=%TEMP%\v07\p-g3 --window-size=1440,1000 --virtual-time-budget=20000 \
  --screenshot=%TEMP%\race-green.png "http://127.0.0.1:8099/static/07-driver.html?case=race"

chrome --headless=new --disable-gpu --hide-scrollbars --no-first-run \
  --user-data-dir=%TEMP%\v07\p-r4 --window-size=1440,1000 --virtual-time-budget=20000 \
  --dump-dom "http://127.0.0.1:8099/static/07-driver.html?case=race" > 07-dom-race-red-old.html
```

`case=firstload` and `case=race` were each captured the same way
(`07-dom-firstload.html`, `07-dom-race-green.html`, `07-dom-race-red-old.html`).

## Probe readings (`#bar` line, copied verbatim from the DOM dumps)

| run | served app.js | line |
|---|---|---|
| firstload, fixed | `namesStamp` present | `PROBE firstload :: row="Alice Ng" list="Alice Ng" knownNames=undefined` |
| race, fixed (green) | `namesStamp` present | `PROBE race :: status="Saved as Race Person, 3 frames averaged" class="status ok" list="Race Person" … ids="loading"` |
| race, pre-fix (red) | `04032A36…`, no stamp | `PROBE race :: status="Saved as Race Person, 3 frames averaged" class="status ok" list="No names saved yet" … ids="0 faces, none known"` |

Race shape: the read is a real `GET /api/faces/known` held 400 ms inside the
page's own `w.fetch`; the save is a stubbed `POST` answering 201 at once with
`known: ["Race Person"]` (a real save needs a human face, which the synthetic
scene does not have — stubbed, as in the 04 gate report). Only the timing of the
read is manufactured; the guard under test is the page's real `loadNames()`.

## Screenshots (1440×1000, seen with my own eyes)

- `07-firstload.png` — fixed page, seeded list: `Alice Ng` row + `×` under the
  button, banner `row="Alice Ng"`. Proves the stamp does not swallow the ordinary
  first read.
- `07-race-green.png` — fixed page: status line `Saved as Race Person, 3 frames
  averaged`, list `Race Person` with its `×`, banner `list="Race Person"`.
- `07-race-red-old.png` — pre-fix page: the same success status line, but the
  list reads `No names saved yet` and Face IDs `0 faces, none known`. This is the
  04 gate's FINDINGS-2 reproduced end-to-end in a browser against the old bytes.

## 03 readability (no regression)

`git diff --stat -- src/rvm/web/style.css src/rvm/web/index.html` is empty, so the
03 measurements (13px labels / 15px values, 7.7:1 grey, 390 order) cannot move;
the four tests that pin them pass:

```
.venv\Scripts\python.exe -m pytest tests/test_app.py -q -k "the_type_ladder_is_13px or mobile_keeps_body_text or grey_text_clears or narrow_layout_orders"
....  [100%]     (4 tests, 0 failures)
```

## Known environment noise (pre-existing, not from this ticket)

`pytest` on this box intermittently aborts during interpreter shutdown
(`exit -1073740791` = `0xC0000409`) **after** every test has passed and the
`[100%]` line is printed, so no summary line is written. Reproduced on the
**pre-change** tree: a `git archive fdf03c9` copy, `pytest tests/test_app.py -q`
→ 42 dots, `[100%]`, `exit -1073740791`, before any of my edits. Counts here were
therefore taken from `--junitxml` (written before the summary dies).
