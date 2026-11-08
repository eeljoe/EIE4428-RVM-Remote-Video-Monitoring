# overall-r2-dynamic — probe readings (verbatim `#bar` / `#detail` lines)

Verifier: independent overall dynamic gate, round 2. HEAD `4dc0acedb86393fc91c2eb9df487c371fc2d9252`.
Worktree: `C:\Users\joe\AppData\Local\Temp\verify-overall-r2-4dc0ace-4dc0ace` (gate-kit, ref 4dc0ace).
Driver/viewport/seam pages + stub launcher archived here as `overall-r2-dynamic-driver.html`,
`overall-r2-dynamic-viewport.html`, `overall-r2-dynamic-seam.html`, `overall-r2-dynamic-stub-server.py`;
live copies sat in the worktree (`src/rvm/web/od2-{drive,vp,seam}.html`, `od2_stub_server.py`)
for same-origin serving. Chrome `--headless=new` (system Chrome 156), `--dump-dom` /
`--screenshot` (two invocations per case). Ledger ticket `00`, round `2` → `ledger/00-r2.jsonl`.

## What is real, what is stubbed

- **Real end-to-end**: every driver click types `value=` + `click()` on the real page;
  POST/GET/DELETE hit the real aiohttp handlers; `FaceStore` writes the real
  `data/known_faces.json` (worktree cwd); process kill + restart loads the file.
- **Stubbed (labelled)**: the synthetic scene contains no real faces. On the `:8150`/
  `:8160` stub launcher only, `FaceRecognizer.sample_faces`/`recognize` are replaced at
  the class boundary by `od2_stub_server.py`, driven live by `.od2/ctl.json`
  (`sample_n`, `sample_delay`, `recognize`). Everything else — warmup, models-ready
  gate, three-frame averaging, name checks, file write, mirror publish, HTTP layer,
  page render — is the real product.
- `:8099` = stock `run_server.py --no-camera` (unmodified product), `:8152` = stock
  `--no-analysis`, `:8170/8171/8172` = stock warmup-race targets, `:8150` second half =
  stock `run_server.py` restarted on the persisted registry file.

## Probe lines

| dump/png | real/stub | reading |
|---|---|---|
| dom-state | real :8099 | `input=true btn=true btnText="REMEMBER FACE" status="" list="No names saved yet" xButtons=0 ids="0 faces, none known" conn="live"` |
| dom-noface | real :8099 | `status="no face in frame, hold still" class="status err" ids="0 faces, none known"` — real 409 `no-face` |
| dom-reg | stub sample, real 201 | `name="Gate Two" attempts=1 firstReply="Saved as Gate Two, 3 frames averaged" class="status ok" serverKnown=["Gate Two"]` |
| dom-regdot | stub sample, real 201 | `name="Alice Ng." firstReply="Saved as Alice Ng., 3 frames averaged" class="status ok" serverKnown=["Alice Ng.","Gate Two"]` |
| curl DELETE | real | `DELETE /api/faces/known/Alice%20Ng.` → `{"removed": true, "known": ["Gate Two"]}`; disk file `['Gate Two']` |
| dom-dup | real 409 | `status="Gate Two is already saved" class="status warn"` |
| dom-multi | stub sample(2), real 409 | `status="more than one face in frame" class="status err"`; roster unchanged `["Gate Two"]` |
| dom-unavail | stub raise, real 503 | `status="face recogniser unavailable: stub landmarker failure (overall-dynamic gate)" class="status err"` |
| dom-off | real :8152 | `status="analysis is off" ids="off"` |
| warmrace.txt | real :8172 | `503 {"error":"the face models are still loading","reason":"models-loading"}` ×3 then `409 {"reason":"samples-missing"}` |
| dom-loading | fabricated err body, real render | `reason=models-loading status="models still loading"` |
| dom-ids | stub recognize, real render | `ids="Gate Two · 0.97"` |
| dom-nomatch | stub recognize(running,seen=1,ids=[]), real render | `ids="no face"` |
| dom-noknown | stub recognize(no-known-faces,seen=2), real render | `ids="2 faces, none known"` |
| dom-subthresh | fabricated payload, real render | `fabricated0.59="Low Conf · 0.59" seenButNoMatch="no face"` |
| badname.txt | real :8099 | `a\b`,`a/b`,`../x` → 400 `bad-name` "path separator"; `.`,`..` → 400 "dot segment"; `\x08`,`\x7f`,`\t` → 400 "single line"; `..a`,`a..b`,`%2F`,`张小英` → pass validation → real 409 `no-face` |
| curl extras | real :8099 | `""`,`" "`,non-JSON,60-char → 400 `bad-name`; `DELETE Nobody` → 404 `{"reason":"bad-name"}`; `.od2/empty/` stayed 0 files |
| noblock.txt | stub delay 0.35s×3, real POST | `POST took 1429 ms -> 201; status polls 159, max gap 0.216s, errors []; mjpeg bytes 16384` |
| dom-restart | real (killed+stock restarted) | `rows=3 names="Gate Two | Slow Person | Slow Person Two" injectedElems=0 pwned=0 ids="no face"` |
| dom-delete | real DELETE via × | `removed="Slow Person" before=3 after=["Gate Two","Slow Person Two"] listNow="Gate Two | Slow Person Two"`; disk `['Gate Two','Slow Person Two']` |
| dom-desktop | real, measured | `docW=1440/1440 docH=1000 minFont=12 labelMin=13 valueMin=15 minContrast=1.70* minLH=1.5 bodyLH=1.50 minSectionGap=20 clippedDD=0 wide=1 opsOffscreen=[]` |
| dom-mobile | real, measured | `docW=375/375 docH=1735 minFont=12 labelMin=14 valueMin=15 minContrast=7.73 minLH=1.5 bodyLH=1.50 minSectionGap=24 clippedDD=0 wide=1 opsOffscreen=[]` |
| dom-seam | real, measured | `SEAM box=24px visual=25px line=1px solid rgb(37, 44, 48)`; `ALL box/visual/line: Stream=24/25/1 Transport=24/25/1 Analysis=24/25/1 Clips=24/25/1` |
| dom-order | real, 390 window | `stage@68 controls@443 hint@702 registry@747 Stream@959 Transport@1205 Analysis@1444 Clips@1740 hiddenOps=[] scrollW=511/511` |

`*` the 1.70 reading is the `.alarm` overlay (`#ffb3a6` on translucent `#f0715a14`) —
the probe treats the alpha background as opaque; the alarm reads clearly in the PNGs
and the mobile run (alarm off) reported `minContrast=7.73`. Same artefact as r1.
`wide=1` is `SPAN.sr-only` — intentional screen-reader text, not an overflow.
`scrollW=511/511` in dom-order is a driver-iframe width artefact; the pinned-iframe
measurements (`docW=375/375`, `docW=1440/1440`) are authoritative — no h-overflow.

## File / API cross-checks

- `.od2/empty/` (:8099) and `.od2/empty2/` (:8152) stayed 0 files after all real
  400/409/503 POSTs → failure paths write nothing.
- `data/known_faces.json` after regs/deletes: `{"version":1,"faces":{name:[1434 floats]}}`;
  names == `GET /api/faces/known` == rendered list at every checkpoint.
- Registry file loaded by the *stock* `run_server.py` after process kill → 3 names in
  API + 3 rendered rows (restart under the unstubbed product, not the launcher).

## pytest / mutations (clean worktree)

- Full `python -m pytest -q` in worktree → 594 dots to `[100%]`, exit 0 (00-r2-043).
- gate-kit mutations (sha1-verified restore each, verified post-hoc identical):
  - `style.css` seam rule `margin-top:8px;padding-top:16px;border-top:1px solid var(--line)` → `margin-top:0;padding-top:0;border-top:none` → `test_the_registry_to_stream_boundary_keeps_its_rule_and_20px` FAILED (real run, AttributeError on unmatched rule)
  - `session.py` `if cleaned in (".", "..")` → `("~", "~~")` → `test_a_name_that_could_never_be_deleted_is_refused_before_it_is_stored` FAILED for params `[.]`, `[..]`, `[ . ]`
  - `recognition.py` `confidence < self.threshold` → `<=` → 2 threshold tests FAILED

## Honesty notes

- Ledger entries 00-r2-009/017/041 are my own probe invocation errors (nested quoting
  through the ledger's cmd shell: warmrace bash one-liner, venv path with unicode+spaces
  twice). Superseded by 010 (script file), 018/019 (system python), 043 (script file).
  Not product failures.
- 00-r2-018 (first noblock run) used `/stream.mjpg` — 404; the route is
  `/api/stream.mjpg`. Probe fixed, rerun as 019 with MJPEG bytes flowing.
- The `models still loading` copy is proven via the real `faceFailure` renderer
  (fabricated contract body); the real 503 `models-loading` reason is proven at API
  level (warmrace ×3). A real UI click inside the ~2 s warmup window is not reliably
  reachable, same as r1.
- `w.render` fed a fabricated out-of-contract 0.59 payload displays `Low Conf · 0.59` —
  the panel trusts the server contract (server never ships sub-threshold names);
  the in-contract `seen=1, identities=[]` correctly renders `no face`. Disclosed, not
  counted as a defect — same ruling as r1 and the 04 gate.
