# OODA frontend redesign — proposed amendment to component 13

2026-10-09 | Status: **proposal for the owner's confirmation**, per the amendment process in
final-spec/DECISIONS.md. Nothing in final-spec is changed by this record. | Branch `frontend`
| Companion: records/2026-10-09-analyst-ux-research.md (findings F1–F8 cited below)

## 1. Why OODA, and its limits here

Boyd's loop — Observe, Orient, Decide, Act, then observe again — describes a decision cycle run
repeatedly under time pressure, which is exactly a review session: an analyst cycles through the
loop once per case, dozens of times per sitting. Two of Boyd's points carry the design:

- **Orientation is the most important phase.** The analyst's scarce resource is not data but an
  assembled picture. Research finding F1 (15 minutes average per manual review vs ~1 minute when
  the record is seen whole) says the same thing in retail terms: the UI's one job is to collapse
  orientation time.
- **Tempo wins.** Shorter honest cycles beat longer thorough-feeling ones; the loop closes — the
  outcome of Act is the input to the next Observe.

One limit, stated plainly: Boyd's Act means acting on the adversary. Our Act is deliberately
smaller — an append-only disposition and a handoff. The spec forbids enforcement from this UI
(no account or refund actions), and this proposal keeps that. OODA here shapes the *layout and
tempo* of review; it does not smuggle in enforcement.

## 2. The mapping

| Phase | Analyst's question | Surface (route, unchanged) | What changes |
|---|---|---|---|
| **Observe** | What deserves my attention in this run, and what changed since I last looked? | /overview, /runs/:id/customers, /runs/:id/styles | Overview becomes a working start-of-session board; queue becomes a worklist with session progress |
| **Orient** | What does this customer's whole record show — against expectation, over time, in links? | /runs/:id/customers/:cid | The four tabs become one case canvas; evidence juxtaposed, not sequenced |
| **Decide** | Which disposition does the evidence support, and is it enough? | same route | A persistent decision rail; dispositions one keystroke away, never a page away |
| **Act** | What happens with my decision, and what does the day add up to? | case, queue, /experiments/:id | Hand-off case summary; session recap; the evaluation page stays the untouched home of truth |

Everything below is within the existing seven routes; UI-AC-01 navigation is unchanged.

## 3. Observe — the run board and the worklist

**Overview → run board.** Keep every existing element (eligible/excluded/selected counts, model
kind, evaluation status, rule-vs-model disagreement lists with neutral wording, fallback banner).
Add, in this order of prominence:

1. **Review budget strip**: `selected N · dispositioned D · remaining N−D`, as counts with a
   plain progress bar. The 5% budget is the product's honesty about attention (F3); showing it
   burn down is what makes a session finishable rather than infinite.
2. **Since-you-last-looked line**: cases that gained a note or disposition since this reviewer
   name's last recorded note (derived from existing append-only reviews; no new storage). Absent
   when there is no prior note — never fabricated.
3. The two disagreement panels stay exactly as specced (AM-10) — they are the Observe-phase
   anomaly surface and already use the required neutral wording.

**Customer queue → worklist.** Keep filters, search, comparison views, tags, dual ranks. Add:

- Default sort within the review set: **undispositioned first**, then batch rank. The queue's job
  is "what's next", not re-reading finished work (F4).
- A **disposition glyph column** — text glyphs (`—`, `inv`, `leg`, `unr`), not color alone, per
  the accessibility requirement.
- **Session progress** repeated in the header (`D of N dispositioned`).
- **Keyboard**: `j/k` row movement, `Enter` opens the case, `[`/`]` previous/next case from
  inside a case, preserving every filter. Labelled in a `?` shortcut sheet (keyboard operation is
  already an acceptance requirement, UI-AC-05; this makes it fast, not merely possible).

Style queue: unchanged except the same glyph/progress treatment. It is the Observe surface for
product-side anomalies and already carries the six states.

## 4. Orient — the case canvas

The current case is four sequential tabs (evidence, timeline, relationships, notes). Tabs hide;
orientation needs juxtaposition (F1, F2). The proposal: one scrollable canvas at desktop width,
the tabs kept as jump links into its sections so deep links and UI-AC-01 walkthroughs still work.

```
┌────────────┬──────────────────────────────────────────────┬───────────────┐
│ IDENTITY   │  WHAT THE RECORD SHOWS (plain words, AM-38)  │ DECISION RAIL │
│ opaque id  │──────────────────────────────────────────────│ disposition   │
│ eligibility│  VOLUME vs EXPECTED      │  TIMING           │  ○ needs_inv  │
│ model rank │  observed/expected qty   │  late returns,    │  ○ likely_leg │
│ rule rank  │  with denominators       │  window shares,   │  ○ unresolved │
│ (neutral   │                          │  wardrobing pts   │ reason tags   │
│  wording)  │──────────────────────────┼───────────────────│ [from fired   │
│ score      │  CLAIMS MIX              │  RELATIONSHIPS    │  signals]     │
│ tooltip    │  claim lines, share,     │  supported links, │ note (free)   │
│ as specced │  item-return lines       │  same-style claim │ reviewer name │
│            │                          │  timing table     │ [append]      │
│ jump links │──────────────────────────┴───────────────────│───────────────│
│ volume/    │  TIMELINE (full width, zoomable strip)       │ prior notes,  │
│ timing/    │──────────────────────────────────────────────│ oldest first, │
│ claims/    │  STYLES TOUCHED (links to style pages)       │ cross-run     │
│ links/notes│                                              │ with origin   │
└────────────┴──────────────────────────────────────────────┴───────────────┘
```

Rules of the canvas:

- **The lede is the existing plain-words statement** of what the record shows and does not show
  (AM-38). It opens the canvas; nothing sits above it.
- **Four evidence quadrants** correspond to the four question families the detection actually
  uses: volume against expectation, timing, claims mix, relationships. Each quadrant ends with
  one `shows / does not show` line (already required per surface; here it is per block, same
  wording discipline — suspected/indicator, never detected/confidence).
- **Every number keeps its denominator** (already specced for observed-vs-expected; extended as
  a rule to every quadrant).
- **Empty is stated, not hidden**: a quadrant with nothing elevated renders "no elevated signal
  in this record", because the absence is orientation too (F2).
- Narrow screens stack the quadrants; the decision rail docks to the bottom. The responsive
  requirement is unchanged.

Nothing new is computed. The canvas is a re-layout of data the four tabs already fetch.

## 5. Decide — the decision rail

The decision moves from "a form somewhere on the notes tab" to a rail that is always in view.
Contents, top to bottom:

1. The three existing dispositions, unchanged in name and storage:
   `needs_investigation · likely_legitimate · unresolved`. Append-only, reviewer name required,
   exactly the current semantics. `unresolved` is presented as a legitimate outcome ("the record
   does not support a conclusion"), not a failure state (F3, F4).
2. **Reason tags**: a tap-to-include list built from the case's fired signals and evidence tags
   (already in the API), prefixed into the note text — structure without new storage or
   vocabulary. Free text follows.
3. **Keyboard**: `1/2/3` select disposition, `n` focuses the note, `Ctrl+Enter` appends, `]`
   next case. One honest cycle, no mouse (tempo; UI-AC-05 made fast).
4. What the rail deliberately does **not** contain: any recommendation, default, preselection,
   score threshold or color steer. The model selected the case into the queue; the disposition
   is the human's. Competitors preselect verdicts; that is the gap we keep open (F8).

## 6. Act — the loop closes

- **Hand-off summary** (needs one amendment decision): a "copy case summary" control producing
  plain text — id, ranks with neutral wording, the shows/does-not-show statement, disposition and
  note. Research F5: the analyst recommends, an accountable owner approves; today that handoff is
  manual re-typing. This adds no enforcement and no new claim — it exports exactly what the
  screen already says. Flagged because component 13 removed "unsupported bulk enforcement" and
  this must not read as an enforcement feature: it is clipboard text, one case at a time.
- **Session recap** on the run board: cases dispositioned this session by disposition, notes
  appended. Derived from existing review records; no reviewer analytics, no leaderboard —
  per-analyst performance dashboards (D365-style) are explicitly not proposed for a tool with
  free-text attribution and no authentication.
- **Cross-run continuity** already exists (notes cross runs of the same world/customer and retain
  origin) and is surfaced in the prior-notes list — Act feeding the next Observe.
- **Evaluation page: untouched.** Truth reveal stays isolated there with its caveats first
  (UI-AC-07, AM-38). The loop's measurement half already exists and is the strongest part of the
  current UI.

## 7. Considered and rejected

| Competitor-standard feature | Rejected because |
|---|---|
| Risk bands / severity colors | UI-AC-04; no calibrated probability exists; bands are verdicts |
| Confidence percentages, AI recommendation | UI-AC-04, D-039; fabricated certainty |
| USD "loss prevented" counters | UI-AC-04; no measured savings exist |
| Auto-disposition / bulk actions | Spec removed unsupported bulk enforcement; decisions are the human's |
| Preselected disposition from the score | Anchors the reviewer; the selection into the queue is already the model's contribution |
| Per-analyst performance dashboard | No authenticated identity; free-text attribution would make it fiction |
| Network graph visualization | Already deliberately bounded to the relationship table; stretch goal stands |

## 8. Acceptance-criteria compliance

| Criterion | Effect of this proposal |
|---|---|
| UI-AC-01 walkthrough/back/context | Routes unchanged; tabs become jump links; verify deep links land on canvas sections |
| UI-AC-02 offline prototype / typed API | Unchanged; canvas uses existing endpoints only |
| UI-AC-03 truthful states | Each quadrant gets loading/empty/error/insufficient states; "no elevated signal" rendered, never blank |
| UI-AC-04 no confidence/USD/bands | Strengthened (section 7) |
| UI-AC-05 keyboard | Extended: full review cycle without mouse; shortcut sheet added |
| UI-AC-06 notes persist cross-run | Unchanged storage; surfaced in rail |
| UI-AC-07 truth reveal isolation | Untouched |
| UI-AC-08 rank comparison, neutral wording | Kept on run board, queue and case rail; hidden under fallback as today |
| UI-AC-09 evaluation wording/codes | Untouched |

## 9. Proposed amendment rows (for DECISIONS.md, on confirmation)

| ID (candidate) | Decision | Replaces |
|---|---|---|
| AM-4x.1 | Case page is a single evidence canvas with four question-family blocks, plain-words lede first, tabs retained as jump anchors | Four sequential tabs |
| AM-4x.2 | A persistent decision rail with the three existing dispositions, signal-derived reason tags, and no recommendation or preselection | Disposition form on the notes tab |
| AM-4x.3 | Queue defaults to undispositioned-first within the review set; disposition glyphs; session progress; `j/k/[/]/1/2/3` keyboard cycle | Rank-only ordering, navigation-only keyboard |
| AM-4x.4 | Run board adds the budget strip and a since-last-note line derived from append-only reviews | Counts without session framing |
| AM-4x.5 | Copy-case-summary exports the on-screen record as plain text, one case at a time; explicitly not an enforcement action | No export |

## 10. Implementation order on `frontend`

Each step is independently shippable and testable against the register:

1. Queue: default sort, glyph column, progress header, keyboard (`CustomerQueue.tsx`,
   `CustomerTable.tsx`) — smallest, immediately felt.
2. Decision rail: extract from the notes tab into a persistent component on the case route.
3. Case canvas: re-layout of existing tab content into quadrants + lede + jump anchors
   (`CustomerCase.tsx`); the largest step; UI-AC-01/03 re-verified here.
4. Run board additions (`Overview.tsx`).
5. Copy-case-summary (only if AM-4x.5 is confirmed).
6. Update the clickable wireframe and `changes-from-pdf.md`, re-run `scripts/spec_package.py`,
   record the amendment rows — the spec stays the contract.

Steps 1–4 change no API, no storage and no wording rules. The only new decision the owner must
make before implementation starts is AM-4x.5.
