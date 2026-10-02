# Independent review before validation worlds are generated, 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a chief data scientist. It worked read-only
on commit `26edcfd` and the working tree, reproduced the out-of-fold scores and the dry-run scorecard with its
own code, and re-measured the v1.4 generator fixes on the regenerated training worlds. The text below is the
critic's report, lightly reformatted. "M" marks a number the critic measured, "R" one taken from a record.

Action taken on each finding is in `records/2026-10-02-gate-dry-run.md` (section "Review before validation")
and `final-spec/DECISIONS.md` (amendment 1.5).

## Verdict

**Safe to generate validation worlds and freeze selection: yes, after fixes, none of which needs regeneration
or retraining.** The training procedure is clean: every out-of-fold score is reproduced to 4e-9 (logistic) and
exactly (boosted) by independent fold refits, nothing is fitted on held-out worlds, the scorecard and all three
segment definitions reproduce exactly from private truth, the bootstrap is paired, and the experiment order is
enforced in code. The AM-29 generator fixes hold and the companion mechanism introduces only trace artefacts.
The three supervised candidates have effectively zero chance of failing a gate leg on five validation worlds by
chance (M). To do first: (1) disclose the real size of the dependence on the simulation's timing law, 13 points
of precision and two thirds of temporary-use recall, and decide now whether that is acceptable, since it
cannot be changed after selection; (2) commit the working tree, which moved during the review, and record code
hashes in the selection record; (3) fix two bookkeeping defects in the error account. The heavy-returner leg of
the gate is circular and should be described as such, not fixed.

## Findings

**MAJOR 1. The model's gain rests on the simulation's return-timing law more than the record says**
(`features.py`, late returns; the dry-run and feature records). M: honest item-return lines in the last quarter
of the window are 0.46% (1,087 of 234,472) against 47.5% for temporary-use lines (Beta(2,5) against Beta(5,2):
a likelihood ratio of about 100). P(abuser | two or more late returns) = 0.94. Out-of-fold ablation, boosted 15
leaves / logistic, precision at 5%: 17 features 0.694 / 0.614; without `late_return_lines` 0.652 / 0.552;
without all three timing features (`late_return_lines`, `late_window_share`, `median_window_ratio`) **0.561 /
0.504**; temporary-use recall 0.64, 0.52, 0.21. Judgement: this is the intended wardrobing behaviour, honest
customers can and do occupy the band, so it is not a mechanical leak like line position or header order; but
its sharpness is a generator law, and the record discloses the limit without the magnitude. "A request after
the window is not a late return" is defensible on its own terms (all 4,178 after-window lines are honest and
99.5% rejected), but it is also honest-only by construction and alone worth 3.7 points (0.658 with after-window
lines counted). Fix: add the ablation triplet to the dry-run record and the demonstration narrative; label the
wardrobing indicator's 0.94 precision as law-driven; if the owner wants a result that does not depend on this
law, the honest timing law must be softened now, because after validation it is frozen.

**MAJOR 2. Working tree diverged from the reviewed commit during the review** (new `ranking.py`, `service/`,
`operational.py`; `evaluation.select`, `modeling.load_pipeline` and `bundles.py` refactored). M: the generator
code hash still matches all 20 world manifests; the new ranking helper is equivalent (an independent tie-break
selection reproduces every scorecard row). But validation would run on uncommitted code, and `selection.json`
records no commit, code or world-manifest hash. Fix: commit first; write the repository commit, code hashes and
the validation manifests' hashes into the selection and validation records; guard `validate()` so the
validation manifests postdate the dry run, and `train()` / `dry_run()` so no validation world exists.

**MINOR 3. The heavy-returner leg is circular** (`evaluation.benign_segments`). The segment is honest customers
at or above the 90th percentile of raw return rate and the baseline ranks on raw return rate, so 100% of its
2,165 false positives are heavy returners and no candidate that is not itself a rate can fail this leg. "44%
of honest heavy returners land in the rule's list" is true by construction. Fix: say so; leave the gate as is.

**MINOR 4. Companion actions can orphan a label** (`abuse._companion`, `evaluation.private_counts`,
`error_account`). Companions draw their own delay, so 4 companions over ten worlds are visible while the
parent claim falls after the cutoff; one W2108 customer is y = 1 with zero non-companion completed actions.
`private_counts` excludes companions, so such a customer gets 0 and falls out of every bucket. Fix: treat a
parent as completed if any of its lines is visible, and assert that the buckets sum to the positives.

**MINOR 5. Residual request-level differences, two of them new with companions** (read by no feature). Ten
worlds: partial-parcel non-receipt (two or more lines claimed, not all delivered lines) 41 solo and 1 ring
against 11 honest, because a solo parcel claim takes only unreserved units; an order with a non-receipt claim
and an item return on another line: 376 abusive against 505 honest (43%, against about 24% of claim lines being
abusive); ring claims on single-line orders 0.539 against 0.339 (known). Signups: 2,545 in August 2026 against
3,100-3,900 in other full months, a 30% dip that the record calls "no step".

**MINOR 6. The explanation is supported, but the record should say what the model actually is.** 73% of the
boosted model's 867 false positives are repeat genuine claimants, 82% have a claim line, 27% a late line. A
hand rule `claim_lines + late_return_lines` scores 0.509, so the model adds 18 points by weighting rate, volume
and linked claims. Model selections average 23.6 mature lines against 14.6 for the rule and 20.2 overall:
volume helps the model although the volume-only reference is weak. Recall by completed actions 1 / 2-3 / 4+:
0.27 / 0.64 / 0.89. The model selects 2 of about 298 non-acting ring members (0.7%), so the earlier worry about
them is moot.

## Checked and found sound (all measured)

Fold map and out-of-fold exclusion; imputer and scaler fitted per fold; rulebook thresholds fold-local for the
dry run and frozen for validation; the frozen feature reference is used by no development world; isolation
forests never see labels; k as a ceiling per world, hash tie-break, pooled counts, strict precision, "no
higher" segment rate, choice order; segment membership re-derived from truth with no differences; bootstrap
paired; order guards, no refit, no runner-up, test runs once; nothing in `validate()` feeds back into
estimators or thresholds. AM-29: first-line share 0.430 / 0.440 / 0.438, reason mix within 3 points,
whole-parcel 0.366 / 0.218 / 0.339, companions never at the same instant, same-header and same-status rates
equal across kinds, refund arithmetic identical, label equals any completed action in 10 of 10 worlds,
companion units all in the allocation table, targeting truth unchanged with or without companions. Gate risk:
20,000 five-world resamples give P(any leg fails) 0.0000 for the boosted model, 0.0003 for the logistic (one
world has its household rate 0.004 above the rule), 0.81 for the isolation forests; the 15-leaf model wins 96%
of resamples. The frozen estimators pass the gate on all seven stress worlds (0.52 against 0.14 at half the
action rate; 0.85 against 0.44 at double). In-sample final-fit precision is 0.733 against 0.694 out of fold,
so expect about 0.69-0.71 on validation.

## Not checked

Notebooks and report tables; bundles and serving code beyond the diff; fixture worlds beyond integrity; whether
a softer honest timing law would keep the baseline in band; the demonstration plan; wardrobing indicator
numbers beyond the customer-level counts above.
