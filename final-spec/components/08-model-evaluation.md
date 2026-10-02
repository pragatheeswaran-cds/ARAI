# Model and evidence evaluation

Version 1.5 (amended 2026-10-02) | Implementation baseline | Component EVAL

## Requirements and boundary

For every world/fraction: N=eligible, k=min(N,ceil(f*N)); N=0 invalid. Rank descending raw score, ties ascending SHA256(UTF-8 review-tie-v02|world_id|customer_id). Same rule/population for raw_return_rate baseline. Primary5%, sensitivity1/10%; rounded display cannot change order.

Pool counts after choosing k independently per world. Precision=sumTP/sumk; recall=sumTP/sumpositives; segment FPR=selected benign segment/all benign segment. Report per-world counts, overlapping action recall, eligible and excluded whole-population abuse coverage. Undefined ratios null; overlapping groups never sum as disjoint totals.

All benign groups require y=0 and eligibility: heavy returner raw rate>=90th percentile over ALL eligible customers including abusers (linear-interpolated quantile, include ties); defective buyer requested >=1 genuinely defective mature unit (not carrier damage); household member actually used an identifier also used by another household member. Graph-linked subset and heavy-return generator flag are diagnostics. Validation requires >=200 pooled per segment. Test1-199 is a coverage limitation; zero unverifiable. No test regeneration.

Use1000 paired whole-world bootstrap resamples seed20260926; percentile2.5/97.5 intervals and all five world results. Coarse uncertainty, no significant-improvement claim from point gate.

Style truth is defect and targeted (one group with >=3 accounts completing coordinated claims on the style). sub_threshold coordination is a separate truth level: reported, never counted as a correct detection. Cross-tab six evidence states versus defect/targeted/both/neither. Report targeting/quality signal precision+recall, all-style/supported-style recall, support, acting groups, low-link cases and campaign-order versus reused-purchase claims. Wardrobing elevated and elevated+possible precision/recall against actual temporary-use actions; false alerts among honest late returners (any request ratio>=.75) and mature size bracketers. Report overlap/eligibility.

Sealed style/wardrobing metrics report-only; development behavior tests mandatory. Zero true positives across all supported development targeting cases blocks claiming a demonstrated capability: revise only in development or explicitly replan. No injected sealed positives. Stress reports vary one mechanism at a time; same-generator seeds are not real-world generalization.

Report-only references use the candidates' population, k, tie rule and budgets and can never be selected or promoted. analyst_rulebook scores the number of fired rules (0-5), ties by descending raw_return_rate then the standard hash: raw_return_rate>=training p90; >=2 visible transaction-claim return lines; requested_refund_ratio>=training p90; >=1 supported neighbor with >=1 own claim line; late_window_share>=.50 with >=2 timed return lines. A null input does not fire. Percentiles come from eligible training customers (linear interpolation) and are frozen. volume_only_logreg shows how much of the ranking follows order volume alone. If a reference approaches or beats a candidate, say so plainly.

The heavy-returner segment is defined on the same quantity the baseline ranks by, so every baseline false positive is a heavy returner by construction and that leg cannot fail for a candidate that is not itself a rate; it is reported and not presented as evidence. Every report states how much of the result depends on the timing features: precision of the selected family with all features, without late_return_lines and without any timing feature (AM-31). A whole-parcel claim counts as one completed action when any of its lines is visible at the cutoff. Error account at the 5% budget: split false positives into heavy returner, defective buyer, household, repeat genuine claimant (y=0 with >=2 genuine fulfilment-failure units) and other, with overlaps shown and never summed; split false negatives by action type, completed-action count (1, 2-3, 4+) and eligibility. Report which selected positives the raw-return-rate baseline did not select and which baseline selections the model did not select, by the same groups. Calibration status, levers and achieved baseline/best precision (component 05) are part of every report.

## Inputs, outputs and dependencies

- Inputs: Frozen candidate/baseline scores and private evaluation truth.
- Outputs: Per-world/pooled metrics and uncertainty/robustness reports.
- Dependencies: Training and experiment contract.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| EVAL-AC-01 | Hand-labelled ceil/tie/pooled fixtures give correct precision/recall/FPR at1/5/10%. |
| EVAL-AC-02 | Segment<200 fails validation coverage; zero denominator never becomes0% FPR. |
| EVAL-AC-03 | Quantile ties/kept defective unit/unused household identifier/overlap fixtures have correct segment membership. |
| EVAL-AC-04 | Reports include paired whole-world intervals and per-world results without significance claims. |
| EVAL-AC-05 | Style/wardrobing misses, no-return state, coverage and null metrics are present. |
| EVAL-AC-06 | Private evaluation joins happen after score freeze; no truth on inference routes. |
| EVAL-AC-07 | Rulebook and volume-only references use the identical population/k/ties and training-only thresholds, are flagged report-only and cannot be selected. |
| EVAL-AC-08 | Error account gives false-positive and false-negative splits with denominators plus model-versus-baseline selection differences; the calibration disclosure is present. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
