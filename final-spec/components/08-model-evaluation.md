# Model and evidence evaluation

Version 1.0 | Implementation baseline | Component EVAL

## Requirements and boundary

For every world/fraction: N=eligible, k=min(N,ceil(f*N)); N=0 invalid. Rank descending raw score, ties ascending SHA256(UTF-8 review-tie-v02|world_id|customer_id). Same rule/population for raw_return_rate baseline. Primary5%, sensitivity1/10%; rounded display cannot change order.

Pool counts after choosing k independently per world. Precision=sumTP/sumk; recall=sumTP/sumpositives; segment FPR=selected benign segment/all benign segment. Report per-world counts, overlapping action recall, eligible and excluded whole-population abuse coverage. Undefined ratios null; overlapping groups never sum as disjoint totals.

All benign groups require y=0 and eligibility: heavy returner raw rate>=90th percentile over ALL eligible customers including abusers (linear-interpolated quantile, include ties); defective buyer requested >=1 genuinely defective mature unit (not carrier damage); household member actually used an identifier also used by another household member. Graph-linked subset and heavy-return generator flag are diagnostics. Validation requires >=200 pooled per segment. Test1-199 is a coverage limitation; zero unverifiable. No test regeneration.

Use1000 paired whole-world bootstrap resamples seed20260926; percentile2.5/97.5 intervals and all five world results. Coarse uncertainty, no significant-improvement claim from point gate.

Style truth is defect and completed coordinated targeting. Cross-tab five evidence states versus defect/targeted/both/neither. Report targeting/quality predicate precision+recall, all-style/supported-style recall, support, acting groups, low-link cases. Wardrobing elevated and elevated+possible precision/recall against actual temporary-use actions; false alerts among honest late returners (any request ratio>=.75) and mature size bracketers. Report overlap/eligibility.

Sealed style/wardrobing metrics report-only; development behavior tests mandatory. Zero true positives across all supported development targeting cases blocks claiming a demonstrated capability: revise only in development or explicitly replan. No injected sealed positives. Stress reports vary one mechanism at a time; same-generator seeds are not real-world generalization.

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

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
