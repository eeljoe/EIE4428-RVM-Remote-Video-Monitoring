# Review — SEAM-1 / Soundness（静态审票）

Scope: issues 01–04 vs spec.md AS-1..AS-7, to-tickets vertical-slice + wide-refactor rules. Read-only; evidence is line cites.

## Mechanical AS check — PASS

Spec Acceptance Statements AS-1..AS-7 all exist (spec.md:43-49). Every AC in all four tickets carries ≥1 bracketed AS ref; every cited ID resolves. Coverage: 01→{5,6,7}, 02→{1,3,4,5}, 03→{5,6,7}, 04→{1,2,4,5}; union = AS-1..7 = SEAM-1's AS list exactly (spec.md:61). No dangling refs, no criterion without a ref.

## (a) Horizontal slices dressed as vertical

- **[Important] 02 is a backend-layer slice.** It delivers schema+API+tests but no UI — the vertical-slice rule wants a complete path through every layer, and SEAM-1's demoable moment (browser register → name shown) only lands at 04. Mitigation: 02 is independently verifiable (its own pytest command + 409/503/restart probes), and merging 02+04 would blow the size cap, so the split is size-driven, not laziness. Still a layer cut by the letter of the checklist.
- 01 is docs-only, but the joe-harness rule mandates the 01 design-spec ticket for UI specs — sanctioned exception, not a violation.

## (b) Blocking-graph defects

Edges: 03→01, 04→{02,03}; frontier {01,02}. **No cycles.** No false edges — all three declared edges genuinely gate (01's design values feed 03; 02's endpoint contract feeds 04; 03/04 write domains overlap on index.html/app.js/style.css/test_app.py so serialization is required anyway). Frontier write domains are disjoint.

- **[Important] Missing closing integration ticket.** to-tickets: "spec 拆出 ≥2 张实现票,末尾追加一张集成测试票". Three impl tickets here, none closes. Spec's 完成条件 (spec.md:72) substitutes an 独立集成动态 gate — that covers dynamic verification but leaves two duties orphaned: a persistent cross-ticket happy-path test in the suite, and adoption of verifier-probes. Nobody owns either.
- **[Important] 02↔04 error contract unpinned.** AS-4 needs the UI to distinguish 无脸/多脸/重名 (three distinct 409 causes); 04's AC3 requires four distinct failure texts. Neither spec nor tickets pin a machine-readable discriminator — 04's 开工包 says "端点契约以 02 号票交付为准" (04:38). Whatever 02 ships becomes the contract; if its 409 body can't discriminate causes, 04's AC is unimplementable and rework bounces back to a resolved ticket.
- **[Nit] 04 lacks literal `Blocked by: 01`** required of every UI ticket (SKILL.md:153); transitively guaranteed via 03→01, so sequencing is safe but the mechanical rule fails.
- **[Nit] `Blocked by:` blank** on 01 and 02 instead of `None` (01:4, 02:4) — malformed vs template, harmless in effect.

## (c) Size / checkability

- **[Blocking] 02 cannot fit its own size cap.** Write domain lists 8 files; minimum required product edits are already 5 (recognition.py, face_store.py new, session.py, app.py, .gitignore) + 2 new test files + 1 modified — >3 files and realistically >300 lines. Split (e.g., face_store+endpoints vs recognition sampling+session) or waive explicitly.
- **[Important] 04 over cap:** 8 files. UI trio alone is 3; docs/report edits are shallow, but the cap is mechanical — either move docs to a 5th ticket or accept the breach knowingly.
- **[Important] 03 marginally over cap:** 4 files, and restyling ~715 lines of frontend (index 115 + css 190 + js 410) plausibly exceeds a 300-line diff.
- All ACs are checkable: px/ratio criteria are machine-verifiable; "画面为第一焦点"/"与参照图一致" adjudicate against committed mocks (design/v2/). "能按文档直接实现" (01) is subjective but bounded by its sibling ACs.
- **[Important] Missing `真机自检` field on all four tickets** — joe-harness forced field (SKILL.md:143-149); 03/04 are clearly 必须-class yet declare no probe path. Also missing 尺寸上限/步数估算 lines in every 开工包; anchors appear only as inline symbols, not the required symbol+grep format.

## (d) Wide refactors

None. The readability rework is confined to three web files — not a codebase-fanning mechanical change; expand–contract N/A.

## Red-team close

**Most dangerous spot: the 02→04 API contract seam.** Per-ticket gates can each pass while SEAM-1 fails: 02's gate only checks status codes 409/503, not body schema; 04 must render four distinct failure texts plus the name+similarity snapshot, against a contract defined only as "whatever 02 ships". If 02's 409 response doesn't discriminate 无脸/多脸/重名 (or its GET snapshot shape differs from what 04 renders), every ticket verifies green and the seam breaks at the final integration gate — the most expensive possible moment to discover it. Fix at ticket level: pin a `reason` enum + snapshot schema in the spec or in 02's ACs before dispatch.
