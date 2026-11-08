# Worker report — 07 registry-ui-fixes (r1)

TICKET: `.scratch/face-recognition/issues/07-registry-ui-fixes.md`
BASE: `fdf03c9` (HEAD when I started; ticket 05 was claimed in parallel by another
session — I never staged or touched its files)
COMMITS: `3a4cfc3` (认领), `ef1da0a` (实现 + 测试 + 实现说明),
`171b9bc` (实现说明里两处行号回对源码，仅票文件)
SELFCHECK: `.scratch/face-recognition/verifier-probes/07-registry-ui-fixes-selfcheck.md`

## COMMITS

- `3a4cfc3` `chore: 认领 07 注册控件收口` — ticket file only, `Status: claimed`.
- `ef1da0a` `fix: 07 名单晚到读防回写，README 与实现对齐，清理孤儿 docstring` —
  exactly five paths: `README.md`, `src/rvm/web/app.js`, `tests/test_app.py`,
  `tests/test_report.py`, the ticket file (实现说明 six sections). Product+test
  insertions 58, under the 300-line / 4-file cap.
- `171b9bc` `docs: 07 实现说明的行号回对源码` — ticket file only; the cited
  `app.js` ranges were off by two lines (`493-507` not `495-508`, `576-600` not
  `577-600`). No product byte changed.

## IMPLEMENTED (per the 04 gate's REMEDIATION tags)

- `[spec]` **README.md:126-128** — the sentence `the button is unavailable for
  exactly those two states` is replaced by "the button stays clickable in both of
  those states, and pressing it puts `analysis is off` or `models still loading`
  on the status line instead of saving". Only that sentence changed
  (`git show ef1da0a -- README.md` = 1 line out, 2 lines in, a wrap).
- `[impl]` **`src/rvm/web/app.js:495-508` + `:593`/`:608` + `:618-627`** —
  `namesStamp` is a counter bumped only by `renderWrittenNames()`, which wraps
  `renderNames()` for the two write paths (save at `:593`, delete at `:608`).
  `loadNames()` takes the stamp before its `await` and, after the answer arrives,
  returns without rendering when the stamp moved (`if (stamp !== namesStamp)
  return;`). A page nobody wrote to keeps `stamp === namesStamp`, so the ordinary
  first load still renders (proved on the real server, see below).
- `[test]` **`tests/test_report.py:274-297`** — the orphan docstring is no longer
  a dead statement: it is the class docstring of the restored
  `TestMeasuredClaimsMatchTheImplementation`, which now owns the two
  registry-unrelated assertions again. Both tests keep their original bodies and
  stay in the collected suite.
- `[test, new]` **`tests/test_app.py:731`**
  `test_a_late_list_read_cannot_overwrite_a_written_list` — pins the stamp taken
  before the request, the guard before `renderNames`, the counter increment, and
  that both write paths (`save` and `delete`) go through `renderWrittenNames`
  (`count == 2`).

## TESTS

Coverage manifest: `node tools/coverage-tests.mjs` reports **no coverage
requirement** for `README.md`, `src/rvm/web/app.js`, `tests/test_app.py`,
`tests/test_report.py` — nothing was owed there.

### Red: the directed test fails on the pre-fix bytes

Pre-fix `app.js` obtained with `git archive fdf03c9` into `%TEMP%\w07b`
(`sha256 04032A36…A8A5CC`), new test file copied in, `PYTHONPATH` pinned to that
copy's `src` (`import rvm` → `%TEMP%\w07b\src\rvm\__init__.py`), no edits to the
working tree:

```
$ cd %TEMP%\w07b ; $env:PYTHONPATH="%TEMP%\w07b\src"
$ ...\.venv\Scripts\python.exe -m pytest tests/test_app.py -q -k "late_list_read"
...
>       assert re.search(r"const\s+stamp\s*=\s*namesStamp", before_request)
E       AssertionError: assert None
E        +  where None = <function search ...>('const\\s+stamp\\s*=\\s*namesStamp', '() {\r\n  try {\r\n    const body = ')
tests\test_app.py:748: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_app.py::test_a_late_list_read_cannot_overwrite_a_written_list
EXIT=-1073740791        (0xC0000409 at interpreter shutdown; see caveat below)
```

Same test on the fixed tree (`ef1da0a`): passes — 67/0 in the run below.

### Green: fixed tree

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py tests/test_report.py -q --junitxml=…\tgt-j.xml
EXIT=-1073740791        (progress: 67 dots, [100%], no F/E; summary lost to the abort)
junit: tests=67 failures=0 errors=0 skipped=0
```

```
$ .venv\Scripts\python.exe -m pytest -q --junitxml=…\full-j.xml
EXIT=0
junit: tests=573 failures=0 errors=0 skipped=0 time=30.751
```

(573 includes the other session's untracked `tests/test_integration_faces.py`,
which lives in its ticket's write domain, not mine.)

The four 03-readability pins, rerun on the fixed tree:

```
$ .venv\Scripts\python.exe -m pytest tests/test_app.py -q -k "the_type_ladder_is_13px or mobile_keeps_body_text or grey_text_clears or narrow_layout_orders"
....  [100%]   junit: tests=4 failures=0
```

`git diff --stat -- src/rvm/web/style.css src/rvm/web/index.html` on `ef1da0a`
is empty, so the 03 numbers (13px/15px/7.7:1) and the 390 order cannot have
moved; the four tests above are the re-measurement that they still hold.

### Caveat: the interpreter abort is pre-existing, not mine

On this machine `pytest` intermittently dies at interpreter shutdown with
`exit -1073740791` (`0xC0000409`) **after** every test passed and `[100%]`
printed, which is why the summary line is missing from `-q` output. Reproduced
on the **pre-change** tree: `%TEMP%\w07b` (archive of `fdf03c9`, untouched
tests), `pytest tests/test_app.py -q` → 42 dots, `[100%]`, `EXIT=-1073740791`.
The full-suite run above exited 0 in the same shell, so it is intermittent.
Counts are taken from `--junitxml`, which is written before the crash.

### 真机自检（必须）

Path: `.scratch/face-recognition/verifier-probes/07-registry-ui-fixes-selfcheck.md`
(commands, ports, hashes and the verbatim `#bar` lines). Server:
`run_server.py --no-camera --port 8099`, real bytes both sides; the read is a
real `GET /api/faces/known` held 400 ms inside the page's own `fetch`, the save is
a stubbed 201 (a synthetic scene has no real face — labelled, as in the 04 gate).

| run | served app.js | probe reading | screenshot |
|---|---|---|---|
| first load, fixed | has `namesStamp` | `row="Alice Ng" list="Alice Ng"` | `07-firstload.png` |
| race, fixed | has `namesStamp` | `status="Saved as Race Person, 3 frames averaged" list="Race Person"` | `07-race-green.png` |
| race, pre-fix | no `namesStamp` | same status, `list="No names saved yet"`, `ids="0 faces, none known"` | `07-race-red-old.png` |

I looked at all three PNGs myself: green shows the `Race Person` row with its
`×` under the button; red shows the success line above `No names saved yet` and
`0 faces, none known` — the 04 FINDINGS-2 defect, end to end, on old bytes.
DOM dumps: `07-dom-firstload.html`, `07-dom-race-green.html`,
`07-dom-race-red-old.html`; driver source `07-driver.html` (its temporary copy at
`src/rvm/web/07-driver.html` was deleted after the runs; `git status -- src`
is clean).

## AS → evidence

- **AS-2** (display): unchanged readout path; the stamp only decides *whether* a
  list answer is rendered. `tests/test_app.py:758` still pins the
  `name · 0.82` / `N faces, none known` formats; the three screenshots show the
  Face IDs line and the list rendered by the real page.
- **AS-3** (persistence/consistency): the late-read guard + save/delete both
  stamped; real-server race probe red→green; `tests/test_app.py:731`.
- **AS-5** (no regression): full suite 573/0, readonly pins 4/4, `style.css` /
  `index.html` untouched, README now states the implemented behaviour.

## 收尾自检

Claims checked one by one against `git show ef1da0a` and the files on disk:

1. README changed exactly one sentence — **hit** (`git show -- README.md`).
2. `app.js` guard exists at the cited lines and both writes use the stamped
   helper — **hit** (`grep -n 'namesStamp\|renderWrittenNames'` → 500 504 505
   593 608 617 619 622; the test's own line pin: `tests/test_app.py:731`).
3. New test at `tests/test_app.py:731`, red on old bytes, green on new — **hit**.
4. `test_report.py` docstring is now a class docstring, assertions where they
   were — **hit**.
5. Self-check doc + 3 PNGs + 3 DOM dumps on disk — **hit** (paths above).
6. Ticket `Status:` still `claimed`, 实现说明 inserted before `## Verdicts` —
   **hit**.
7. Only my five paths committed across `3a4cfc3`/`ef1da0a`/`171b9bc`; the other
   session's `tests/test_integration_faces.py` left untracked — **hit**.

7 claims, 7 hits, 0 misses.

## 回执

| 票号 | 交票 或 受阻 | 提交哈希 | 报告路径 | 一句原因 |
|---|---|---|---|---|
| 07 | 交票 | ef1da0a | reports/07-r1-worker.md | README 一句对齐、loadNames 加版本戳防回写（真机红→绿）、孤儿 docstring 归位；573/0 全套绿 |
