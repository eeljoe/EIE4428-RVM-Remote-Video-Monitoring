# overall-dynamic — probe readings (verbatim `#bar` / `#detail` lines)

Verifier: independent overall dynamic gate. HEAD `01d08b75d838c7aeb48d24e3ecbaedfba4919ec0`.
Worktree: `C:\Users\joe\AppData\Local\Temp\verify-overall-01d08b7` (gate-kit, ref 01d08b7).
Driver/viewport pages + stub launcher archived here as `overall-dynamic-driver.html`,
`overall-dynamic-viewport.html`, `overall-dynamic-stub-server.py`; live copies sat in the
worktree (`src/rvm/web/od-drive.html`, `od-vp.html`, `od_stub_server.py`) for same-origin
serving. Chrome `--headless=new` (system Chrome 156), `--dump-dom` / `--screenshot`
(two invocations per case — dump-dom readings below; PNGs alongside).

## What is real, what is stubbed

- **Real end-to-end**: every driver click types `value=` + `click()` on the real page;
  POST/GET/DELETE hit the real aiohttp handlers; `FaceStore` writes the real
  `data/known_faces.json` (default relative path, worktree cwd); restart loads the file.
- **Stubbed (labelled)**: a synthetic scene contains no real faces. On the `:8150` stub
  server, `FaceRecognizer.sample_faces`/`recognize` are replaced at the class boundary by
  `overall-dynamic-stub-server.py`, driven by a live JSON control file
  (`sample_n`, `sample_delay`, `recognize`). Everything else — warmup, models-ready gate,
  three-frame averaging, name checks, file write, mirror publish, HTTP layer, page render —
  is the real product. `recognize:"real"` switches back to the real landmarker.
- `:8099` = stock `run_server.py --no-camera`, `:8152` = stock `--no-analysis`, both
  unmodified product.

## Servers

| port | kind | registry file |
|---|---|---|
| :8099 | real `run_server.py --no-camera` | `.od/empty/known_faces.json` (never created) |
| :8150 | stub launcher, analysis on, interval 0.05 | `data/known_faces.json` (seeded → real writes) |
| :8152 | real `--no-analysis` | `.od/empty2/known_faces.json` |
| :8153/8154/8170 | real, warmup probes | temp |

## Probe lines

| dump/png | real/stub | reading |
|---|---|---|
| dom-state | real | `input=true btn=true btnText="REMEMBER FACE" status="" list="No names saved yet" xButtons=0 ids="0 faces, none known" conn="live"` |
| dom-noface | real | `status="no face in frame, hold still" class="status err"` — real 409 `no-face` |
| dom-list | real | `rows=3 names="<img src=x onerror=window.__pwned=1> | Alice Ng | Curl Probe" injectedElems=0 pwned=0 ids="no face"` |
| dom-reg | stub sample, real 201 | `status="Saved as Gate Person, 3 frames averaged" class="status ok" serverKnown=[xss,Alice,Curl,Gate]` |
| dom-reg2 | stub sample, real 201 | `status="Saved as Second Person, 3 frames averaged" class="status ok"` |
| dom-dup | real 409 | `status="Gate Person is already saved" class="status warn"` |
| dom-multi | stub sample(2), real 409 | `status="more than one face in frame" class="status err"` |
| dom-unavail | stub raise, real 503 | `status="face recogniser unavailable: stub landmarker failure (overall-dynamic gate)" class="status err"` |
| dom-off | real 503 | `status="analysis is off" ids="off"` |
| warmrace | real 503 | `1.66s HTTP:503 {"error":"the face models are still loading","reason":"models-loading"}` then `5.17s HTTP:409 {"reason":"no-face"}` |
| dom-loading | fabricated err body, real render | `status="models still loading" class="status"` |
| dom-ids | stub recognize, real render | `ids="Gate Person · 0.97"` |
| dom-nomatch | stub recognize, real render | `ids="no face"` (running, seen=1, identities=[]) |
| dom-noknown | stub recognize, real render | `ids="2 faces, none known"` |
| dom-subthresh | fabricated payload, real render | `fabricated0.59="Low Conf · 0.59" seenButNoMatch="no face"` |
| dom-restart | real (process killed+restarted) | `list="<img…> | Alice Ng | Curl Probe | Gate Person" xButtons=4 ids="no face"` |
| dom-delete | real DELETE via × | `removed="Gate Person" before=4 after=3 listNow=3 status="" ids="no face"`; file on disk 3 names |
| noblock.py | stub delay 0.35s×3, real POST | `POST took 1161 ms -> 201; status polls 34, max gap 0.167s; mjpeg bytes 65536` |
| dom-desktop | real, measured | `docW=1440/1440 docH=1000 minFont=12 labelMin=13 valueMin=15 minLH=1.5 minSectionGap=20 clippedDD=0 opsOffscreen=[]` |
| dom-mobile | real, measured | `docW=375/375 docH=1710 minFont=12 labelMin=14 valueMin=15 minLH=1.5 minSectionGap=16 clippedDD=0 opsOffscreen=[]` |

## Contrast (real computed styles, WCAG rel. luminance)

- desktop groups: `h2 f13 c11.94 | labels f13 c7.73 | values f15 c7.73* | controls f13-15 c8.97 | status+names f13 c7.73 | osd+peak f12-20 c1.7†`
- mobile groups: `h2 f14 c11.94 | labels f14 c7.73 | values f15 c7.73* | controls f14-15 c8.97 | status+names f14 c7.73 | osd+peak f12-20 c1.7†`
- `*` the 7.73 value-group reading is the grey `pending` placeholder (`dd.pending`); live values are `--text` 16.65.
- `†` 1.7 is a **measurement artifact**: `.alarm` overlay `#ffb3a6` on translucent `#f0715a14` — probe treats the alpha bg as opaque; effective background is the video/`#000`, and the alarm reads clearly in screenshots. Second desktop run (alarm off) reported `minContrast=7.73`.

## netlog

`overall-dynamic-netlog.json` → `overall-dynamic-netlog-scan.py`: 30 URL_REQUEST events,
**20 page-initiated — all `127.0.0.1:8099`** (index, style.css, app.js, /ws, /api/*,
favicon). `REMOTE page-initiated: none`. Remaining remote hits are Chrome-internal service
traffic (update/accounts/gstatic) with no page initiator.

## stderr (console/page errors)

`*.err` files next to each dump/png: 0 `Uncaught`, 0 `net::ERR` page-side, 0 SEVERE.

## File / API cross-checks

- `.od/empty/` stayed empty after real 409/400 POSTs → failures write nothing.
- `data/known_faces.json` after real deletes/regs: `{"version":1,"faces":{name:[1434 floats]}}`, names == server known == rendered list at every checkpoint.
- `DELETE /api/faces/known/Nobody` → `404 {"error":"'Nobody' is not registered","reason":"bad-name"}`.
- `POST {"name":""}` / 50-char name / non-JSON body → `400 bad-name` each.
- `getComputedStyle` at ≤900: `main.layout` grid `row-gap:16px`; `.section` margin-top 8 + padding-top 16 + border-top 1 — but Stream (first `.section` in `.rail`) has none → registry→Stream boundary = 16px, no divider line (other boundaries = 24px + 1px line). See FINDINGS F-1.

## pytest / mutations (clean worktree)

- Full `python -m pytest -q` → all dots to 100%, exit 0 (ledger 00-r1-021; worker's 573).
- gate-kit mutations (sha1-verified restored each):
  - `app.js` no-face copy → `WRONG COPY` → `test_the_registry_status_line_carries_the_five_outcomes` FAILED (00-r1-022)
  - `recognition.py` `confidence < threshold` → `<=` → 2 threshold tests FAILED (00-r1-023)
  - `session.py` `np.mean(np.stack(embeddings))` → `np.zeros(8)` → `test_registering_a_face_averages_the_last_three_analysed_frames` FAILED (00-r1-025)

## Honesty notes

- `overall-dynamic-reg-ok.png`/`reg-ok2.png` show `already saved` warn, not the ok copy:
  dump-dom and screenshot are two Chrome invocations, so the PNG run re-registers the same
  name. The 201 reading lives in `dom-reg.html`/`dom-reg2.html`; `overall-dynamic-reg-ok.png`
  (Third Person, shot-only run) carries the ok copy — this dual-run artifact is disclosed
  rather than hidden.
- Ledger entries 00-r1-002/024 are my own probe invocation errors (bash-vs-cmd, multiline
  find), not product failures.
- The `models still loading` on-screen copy is proven via the real `faceFailure` renderer
  (fabricated contract body); the real 503 `models-loading` reason is proven at API level
  (warmrace). A real UI click inside the ~1.6 s warmup window is not reliably reachable:
  Chrome boot+iframe-wire costs more than the window.
