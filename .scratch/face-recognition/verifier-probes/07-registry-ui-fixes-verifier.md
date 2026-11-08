# 07 verifier probes — registry-ui-fixes (r1)

Verifier: independent gate. Target HEAD `171b9bc714751a548384a17a3ca6fe0e7dcc0d24`
(= 07-submitted `ef1da0a` + docs-only commit; repo tip later moved to `7671388`
for ticket 05 — out of scope).
Worktree: `C:\Users\joe\AppData\Local\Temp\verify-gate-7671388`, checked out at
`171b9bc`. Driver: `src/rvm/web/v07-driver.html` inside that copy (mine, written
this round; a verbatim copy is NOT kept in the probes dir — the worktree is
disposable; the dump files below carry the full behaviour evidence).

## Method

Same-origin iframe driver (04-gate method): the page iframes `/`, types into
`#face-name`, clicks `#face-remember` / `button.x`, prints DOM state into a
`#bar` banner captured by headless Chrome (`--headless=new --dump-dom` /
`--screenshot`, `--virtual-time-budget=30000`). All pacing is by real fetch
round-trips, never `setTimeout`.

- `race` wraps `w.fetch`: the real `GET /api/faces/known` fires immediately but
  its result is *delivered* 400 ms late (realFetch starts now → the server
  answers with the pre-write state; the caller sees it late). `POST` is a stub
  201 `{name:"Race Person",samples:3,known:["Race Person"]}` — a synthetic scene
  has no real face, same labelled limitation as the 04 gate.
- `racedel` (my extension of the ticket's 首攻靶「删除路径同样受保护」): the
  same 400 ms-late GET on the *seeded* server, but the write is a **real**
  `DELETE` of `Alice Ng` through the `×` button. The late GET carries the
  pre-delete two-row list; correct behaviour = it is dropped.
- Everything else hits the real server end-to-end.

Servers (main-repo `.venv` python, worktree cwd, `run_server.py --no-camera`):

- `:8231` empty registry (`%TEMP%\v07v\empty\known_faces.json`, never created —
  verified: directory stayed empty through every failed POST)
- `:8232` seeded `%TEMP%\v07v\seed\known_faces.json` =
  `{"version":1,"faces":{"Alice Ng":[0.1,0.2],"<img src=x onerror=window.__pwned=1>":[0.3,0.4]}}`
- `:8233` `--no-analysis` → real `analysis-disabled`
- `:8234` fresh `--no-camera` → real `models-loading` warmup window

## Probe lines (`07v-probe-lines.txt`, verbatim `#bar` readings)

| dump | reading | verdict |
|---|---|---|
| `07v-dom-race-green.html` | `race :: status="Saved as Race Person, 3 frames averaged" ok list="Race Person" ids="no face"` | **GREEN** — late GET dropped |
| `07v-dom-race-red-old.html` | `race :: status="Saved as…" ok list="No names saved yet" ids="no face"` | **RED on pre-fix bytes** — 04 FINDINGS-2 reproduced by me end-to-end |
| `07v-dom-firstload.html` | `firstload :: list="<img…> \| Alice Ng" ids="no face"` | ordinary first render NOT swallowed; XSS name is a text node |
| `07v-dom-racedel.html` | `racedel :: list="<img…>" before=[xss,Alice] after=[xss]` | delete path equally protected — stale pre-delete GET dropped |
| `07v-dom-delx.html` | `delx :: list="<img…>" before=[xss,Alice] after=[xss] status=""` | real DELETE end-to-end; seed file on disk confirms `[xss]` only |
| `07v-dom-noface.html` | `noface :: status="no face in frame, hold still" err` | **real** 409 copy #1/5 |
| `07v-dom-offclick.html` | `offclick :: status="analysis is off" ids="off"` | **real** click on `--no-analysis` → button IS clickable in `disabled` state; copy #2/5 |
| `07v-dom-loadingclick2.html` | `loadingclick :: status="models still loading" ids="loading"` | **real** click inside warmup → button IS clickable in `pending` state; copy #3/5 |
| `07v-dom-loadingclick.html` | `loadingclick :: status="no face in frame, hold still"` | attempt 1 missed warmup (sleep burned the window); still proves clickability; kept for honesty |
| `07v-dom-stubok.html` | `stubok :: status="Saved as Stub Person, 3 frames averaged" ok list="Alice Ng \| Stub Person"` | stub 201, copy #4/5 (success) |
| `07v-dom-stubmulti.html` | `stubmulti :: status="more than one face in frame" err` | stub 409, copy #5/5 — wait, #4; all five covered |
| `07v-dom-stubdup.html` | `stubdup :: status="Alice Ng is already saved" warn` | stub 409 `name-exists` |
| `07v-dom-mobile.html` | `mobile :: scrollW=390 clientW=390 regOrder=4 regTop=656` | 390 no overflow; `order=4` identical to the 04 gate reading |

## Red/green sha bookkeeping

- Fixed `app.js` sha256 `8a7ad6e16fcbd6a71bbecb70fe9485226f1547c2538b32b256b53bb51b22cac1`
  (recorded before swap, re-verified after restore — identical).
- Pre-fix bytes via `git show fdf03c9:src/rvm/web/app.js` → sha256
  `e443c812350595ef4fb7b8c26f34dcaf9e3e42989cb827ba1e563fdd487d6a13`,
  `namesStamp` count = 0. Red probe ran on those bytes; `git checkout` restored;
  sha256 back to `8a7ad6e1…`.
- gate-kit mutations (each sha1-verified restored):
  `if (stamp !== namesStamp) return;` → `if (false) return;` → directed test FAILED;
  `renderWrittenNames(body.known);` → `renderNames(body.known);` (×2) → `count==2` FAILED.

## Screenshots (seen with my own eyes)

- `07v-shot-race-green.png` — success line + `Race Person` row with its `×`.
- `07v-shot-offclick.png` — `analysis is off` status; ANALYSIS rows all `off`.
- `07v-shot-firstload.png` — seeded row rendered; XSS name as literal text, no
  injected element (taken after `racedel`, so only the xss row remained).
- `07v-shot-mobile.png` — 390-pinned iframe, single column, registry after
  controls, REMEMBER FACE reachable, no horizontal scroll.

## pytest

- Directed `pytest tests/test_app.py tests/test_report.py -q` → **67/0/0/0**
  (`junit-directed2.xml`; first run hit the documented intermittent `0xC0000409`
  shutdown abort after `[100%]`, rerun exited 0).
- Full `pytest -q` → **570/0/0/0, exit 0**, twice (`junit-full.xml`,
  `junit-full2.xml`). 570 + ticket 05's 3 integration tests (absent at `171b9bc`)
  = the worker's 573 — consistent.

## Disclosure

- One early stub batch used a literal `CAZ` placeholder in the URL and wrote a
  bogus `07v-dom-CAZ.html`; I deleted that seconds-old artifact of mine (nothing
  pre-existing was touched) and reran correctly — ledger entries 07-r1-007..010
  record it as noise.
- `loadingclick` attempt 1 (entry 016) missed the warmup window.
