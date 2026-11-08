# 01-design r3 verifier probe transcript

Probe: `.scratch/face-recognition/verifier-probes/01-design-r3-selfcheck.py`
Run: `python .scratch/face-recognition/verifier-probes/01-design-r3-selfcheck.py` from repo root.
Result: **40 checks, 0 FAIL** (exit 0). Run at r3 verification against HEAD `6edd865`
(doc last touched by `eb0ff43`; `git diff HEAD -- docs/DESIGN-dashboard.md` empty).

## Inputs (sha256 verified by reading, same tree as r2 where unchanged)

- `docs/DESIGN-dashboard.md` — 226 lines, eb0ff43 version (worktree == HEAD)
- `.scratch/face-recognition/design/v2/mock.html` — 47986 bytes
- `mock-desktop.png` 1440x1000, `mock-mobile.png` 390x844 (PNG sig + IHDR read)

## Contrast recompute (WCAG 2.1 relative luminance, all exact within rounding)

| pair | doc | recomputed |
|---|---|---|
| --raised/--bg | 1.17 | 1.169 |
| --raised-hover/--bg | 1.33 | 1.331 |
| --line/--bg | 1.37 | 1.374 |
| --line-strong/--raised | 1.67 | 1.666 |
| --text/--bg | 16.65 | 16.652 |
| --text-2/--bg | 11.94 | 11.936 |
| --muted/--bg | 7.73 | 7.732 |
| --placeholder/--panel | 5.10 | 5.097 |
| --accent/--bg | 10.78 | 10.778 |
| --accent-hover/--bg | 12.22 | 12.223 |
| --on-accent/--accent | 8.97 | 8.968 |
| --ok/--bg | 9.83 | 9.834 |
| --warn/--bg | 10.16 | 10.156 |
| --alarm/--bg | 6.69 | 6.692 |
| --text/--panel (§2:68 hard floor) | 15.8 | 15.836 |
| peak dash composite/--bg | ~2.7 | 2.729 |

Composite `rgba(154,165,170,.5)` over `#0b0d0e` = channels (82.5, 89, 92) →
`#52595c` or `#53595c` depending on .5 rounding; doc writes 约 `#53595c`, hedged, OK.

## Mock ground truth (grep + read)

- `var(--panel)` occurrences in mock.html: exactly 1 — line 233 `.reg-row input`.
- `.rail` (:180) rule has no `background`; `.section` has no standalone rule at all
  (only `.section + .section` :181/:294, `.section h2` :183, `.section h2 .meta` :189,
  `.section { order:5 }` :290). Sections sit on body `--bg` (:62).
- `#spark` (:213) no background; JS `ctx.clearRect` (:495) → transparent canvas on `--bg`.
- Peak dash `strokeStyle = "rgba(154,165,170,.5)"` (:504), `setLineDash([3,3])` (:500),
  lineWidth 1 (:505), at `ceiling = 6*dpr` (:492,:502).
- Baseline `strokeStyle = "#252c30"` (:523) = `--line`, on transparent canvas → `--bg`.
- `var(--accent-soft)` uses: 0 (defined :38 only). ROI bg literal `#5fd3c60f` (:127);
  `.seg.active` solid `var(--accent)` (:172).
- `var(--alarm-soft)` uses: 2 — `#record.active` bg (:174), `.x:hover` bg (:265).
  `.bbox` bg literal `#f0715a1a` (:129); `.alarm` bg literal `#f0715a14` (:138).
- ≤900px order (:287-293): stage 1, controls 2, hint 3, registry 4, section 5.
- ≤900px section spacing (:294): margin-top 8 + padding-top 16.
- State copy in mock: `Saved as Alice Ng, 3 frames averaged` (:436 live DOM),
  `No face in frame, hold still` (:426, in commented alt-state block), `No names saved yet` (:428).

## Doc-side greps

- `grep -n 'panel' docs/DESIGN-dashboard.md` → 8 hits, all legit
  (:41 note, :46 fixed cell, :54 placeholder-on-panel, :66 new rule,
  :68 hard-floor-on-panel, :107 input bg, :166 §7 consistent, :197 §9 var).
- U+2014 count: 0. Line count: 226.
- `## ` section heads: §1..§10 all present (five required = §1-§5).
- Five-state copy verbatim in doc §8:179-183 (all 5 grepped present).
- `--muted`/`--alarm` rows: no `(对 --panel …)` remnant; `--line` row says `对 --bg 1.37:1`.

## Git readings

- `git show --stat eb0ff43` → 2 files: `docs/DESIGN-dashboard.md` (+8/-7) and
  `.scratch/face-recognition/issues/01-design-dashboard.md` (+20 r3 notes). Nothing else.
- `git show eb0ff43 -- docs/...` → 4 hunks, exactly the claimed 8 cell/row edits + new rule line.
- `git status --porcelain` → only untracked `.scratch/` artifacts + stray `nul`; worktree clean.
