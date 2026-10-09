# Return-analyst work and competitor consoles — research for the frontend redesign

2026-10-09 | Input to the OODA frontend redesign proposal (records/2026-10-09-ooda-frontend-redesign.md) | Branch `frontend`

## Method and limits

Secondary research only: vendor documentation, industry reports, practitioner writing and one
dated survey figure. No analyst was interviewed and no session was observed, so every workflow
claim below is an inference from published material, not a measured fact about our users. Vendor
figures are marked as vendor claims. Where a number is load-bearing for a design decision, the
decision is written to survive the number being wrong.

## 1. The scale of the job

- US merchandise returns were $685B in 2024 (13.21% of retail sales); 15.14% of returns were
  deemed fraudulent, costing retailers $103B (Appriss Retail / Deloitte annual study, 60+
  retailers plus Census data). Wardrobing was reported by 60% of surveyed retailers; stolen-tender
  returns by 55%; returns of stolen goods by 48%.
- Appriss's 2026 benchmark puts combined returns-and-shrink loss at $796B. Their stated position:
  stricter blanket policies are not reducing fraud — a vendor view, but consistent with the
  academic countermeasures literature and with our own design premise that the job is separating
  abuse from legitimate heavy returning, not suppressing returns.
- Forter estimates over 8% of returns violate merchant policy. The spread between 8% and 15%
  across sources is itself informative: nobody measures this well, which is why our evaluation
  page leads with caveats.

## 2. The analyst's day, synthesized

Across the sources, the same shape recurs — a queue consumed in sessions, case by case:

1. **Open the queue.** Flagged items arrive from automated decisioning; the analyst's first
   question is "what deserves attention now" (Microsoft Dynamics 365 Fraud Protection structures
   this as rule-routed queues; practitioner workflow guides insist every item has a next action
   and a due date).
2. **Assemble context per case.** Order history, return history, reason codes, identity links,
   addresses, device data. In the 2014 Merchant Risk Council survey, manual review averaged
   **15 minutes per order** — but the same source reports that an order reviewed *holistically*,
   with the evidence already assembled in one view, was decided **within one minute**. The gap is
   information assembly, not judgment. Appriss makes the same claim about its own tooling at
   investigation grain: briefings assembled by the system cut "45 minutes of manual work" to
   under 5 (vendor claim).
3. **Decide and record.** Practitioner guidance converges on: judge the whole record rather than
   one indicator; decide in minutes; avoid parking cases to wait for outside parties; close only
   with a recorded outcome and evidence.
4. **Escalate the exceptions.** Policy and financial calls go up a level with a summary, the
   evidence, and the requested decision — the analyst recommends, an accountable owner approves.
5. **Report.** Weekly metrics: review time, prevented loss, false-positive rate, cycle time.
   Reviewer-level performance dashboards (reviewed, confirmed, false-positive rate) are standard
   in D365 FP.

Two pressures dominate the literature on how this day goes wrong:

- **Alert fatigue.** When most of the queue is false positives, analysts sift noise, backlogs
  make the function reactive, and turnover follows (fraud.net; the SOC-burnout literature says
  the same). The design consequence is not "show fewer alerts" cosmetically — it is a small,
  honest, budgeted queue where clearing a case is a legitimate outcome, not a failure.
- **Context switching.** The 15-minute average is spent gathering, not thinking. Every tab,
  page-load and cross-reference the UI demands is paid on every case, hundreds of times a week.

## 3. Competitor teardown

| Product | Decision model | What the reviewer sees | Enforcement | What it hides |
|---|---|---|---|---|
| **Appriss Retail (Verify/Engage, Sidekick)** | Real-time return authorization; 2026 "Sidekick" agent opens investigations, assigns work, tracks outcomes | Assembled briefings per investigation; per-location patterns | Approve/warn/deny at the return counter | Model internals; a claimed "99.99% decision accuracy" with no stated denominator |
| **Signifyd Return Abuse** | Risk score per return with a threshold recommendation; vendor assumes liability below threshold | Returns Insights dashboard: journey view, returns classified fraud / abuse / wardrobing / bracketing; anomaly detection on return and contact rates; CLTV | Fast refunds for trusted customers; friction for risky ones | Why a given return scored as it did |
| **Forter Returns Abuse** | Real-time decision + recommendation at checkout and at return initiation | Primarily an API; identity-linking across a merchant network | Graduated: withhold free-returns perk → withhold free return shipping → account-level flag; merchant enforces its own policy | The linking logic; no analyst console described at all |
| **Riskified** | Automation-first; manual review treated as a cost to minimise | (Guidance, not console): judge the order as a whole; decide in minutes | Approve/decline with chargeback guarantee | Case-level reasoning |
| **Microsoft D365 Fraud Protection** | Rules route to manual-review queues | Curated review dashboard with transaction history; per-analyst performance dashboard | Custom remedy actions; decisions and labels feed back into models | — (closest to an honest reviewer tool, thinnest on returns specifically) |

### What they converge on

1. **Automation decides; humans handle exceptions and set policy.** Nobody staffs a queue for
   every return.
2. **Graduated enforcement, never one hammer.** Forter's ladder (lose a perk → lose free
   shipping → account flag) is the clearest articulation; friction is "reserved only for
   abusers."
3. **Identity linking is core evidence**, always present, never explained.
4. **Named behaviours** (wardrobing, bracketing, claims abuse) rather than a single fraud label.
5. **The feedback loop is institutionalised** — decisions and labels return to the models, and
   reviewer performance is itself measured.

### Where they are weak — and where ARAI already differs deliberately

Every one of these products presents a **verdict** (score, band, accuracy claim) and hides the
reasoning. Our spec forbids exactly that — no bands, no confidence percentages, no
loss-prevented claims, neutral selected-by wording, caveats before results (UI-AC-04,
AM-10/AM-38). The teardown's practical lesson is that this is not just an honesty position — it
is the open UX gap. None of these consoles helps an analyst *see the evidence fast*; they help
an analyst *accept a verdict fast*. A reviewer tool that assembles the whole record into one
field of view, states what it shows and does not show, and lets the human decide, is both the
compliant design and the differentiated one.

## 4. Findings carried into the redesign

| # | Finding | Source | Design consequence |
|---|---|---|---|
| F1 | Review time is dominated by assembly (15 min avg vs ~1 min holistic) | MRC via Riskified | One-screen case canvas; no evidence behind tabs |
| F2 | Whole-record judgment beats single-indicator fixation | Riskified | Evidence blocks juxtaposed, each with shows / does-not-show wording |
| F3 | Alert fatigue comes from unbudgeted, mostly-false queues | fraud.net | Keep the 5% budget visible; make likely_legitimate a first-class, fast outcome |
| F4 | Every open item needs a next action; closure needs a recorded outcome | practitioner workflow guides | Dispositions mandatory to leave a case "done"; unresolved is explicit, not silent |
| F5 | Analysts recommend, owners approve; escalation carries a summary | same | A case summary that can be handed upward verbatim |
| F6 | Graduated response, not verdicts | Forter | Dispositions stay observational; enforcement remains out of scope |
| F7 | Reviewer performance and decisions feed back | Microsoft D365 FP | Session recap; dispositions persist cross-run (already specced) |
| F8 | Verdict-first consoles are the norm; evidence-first is the gap | whole teardown | Keep and sharpen the honesty constraints; they are the product |

## Sources

- Appriss Retail / Deloitte 2024 returns study (via Silicon press release): totals, fraud share, wardrobing prevalence
- Appriss Retail Sidekick launch, Business Wire, 2026: investigation workflow, 45-min→5-min vendor claim; 2026 benchmark $796B
- Signifyd Return Abuse Prevention product page: scoring, classification, Returns Insights
- Forter Returns Abuse solution brief and docs.forter.com: graduated enforcement, identity linking, API decision model
- Riskified, "How online retailers optimize manual reviews": MRC 15-minute figure, holistic-review finding
- Microsoft Dynamics 365 Fraud Protection manual-review blog: queues, routing, per-analyst dashboards, feedback loop
- fraud.net, "Drowning in alerts": alert fatigue, false positives, turnover (qualitative)
- Stealth Agents return-fraud review process guide: the 7-stage workflow, escalation and closure discipline
- InfoSec Institute, "OODA and cybersecurity": phase definitions and tempo (used in the companion redesign document)
