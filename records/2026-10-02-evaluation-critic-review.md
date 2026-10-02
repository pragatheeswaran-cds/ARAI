# Independent review of evaluation and selection, before the final test, 2026-10-02

Reviewer: an independent critic agent on the Fable model, briefed as a chief data scientist. It worked read-only
on commit `4da2cbd`, after the selection was frozen and before any test or demo world existed. It re-scored the
validation worlds with the frozen estimators and its own selection code. "M" marks a number the critic measured,
"R" one taken from a record. The text below is the critic's report, lightly reformatted.

Action taken is in `records/2026-10-02-validation-and-selection.md` (section "Before the final test").

## Verdict

**Safe to generate the test worlds and run the final test once: yes, after two small code fixes in
`experiment.final_test()` and a commit.** The validation scorecard reproduces exactly from the frozen estimators
and private truth (all eight rankings, every count and segment rate, the gate verdicts and the choice of
`hgb_leaf15`), nothing was refitted, the provenance block is truthful, and test and demo worlds do not exist.
The two things to fix before the single run are about the run itself, not the result. One disclosure gap (the
AM-31 timing ablation is absent from every machine report) should be closed in `publishing.py`.

## Findings

**MAJOR 1. The frozen-model check does not read the model file** (`experiment.final_test`). It compares the
hash in the candidate's training record with the hash in `selection.json`: two text files, never `model.skops`.
M: the file's hash equals both records today, so there is no present harm, but the stated check is not
implemented. Fix: hash the file and compare with the selection record, before anything is scored.

**MAJOR 2. A crash window leaves the experiment unrecoverable** (`final_test`). The test report is written,
then `selection.json` is rewritten in place. A failure between the two leaves a report (every rerun raises "runs
once") and a selection that says `not_run` (publication never promotes). Fix: write through a staging file and
a rename, and make the once-only guard also read the selection record, so deleting the report is not a second
look.

**MAJOR 3. The AM-31 timing-ablation disclosure is in no report** (`experiment`, `publishing.build_report`).
Specification 08 says every report states how much of the result depends on the timing features. M: neither
`dry_run.json`, `validation.json` nor the built experiment payload mentions it; the numbers exist only in the
Markdown record. Fix: publish three rows from a small ablation report and one limitation sentence.

**MINOR 4. Test-world freshness is not guarded.** Validation refuses manifests older than the dry run; the test
accepts any W2301-W2305. None exists now. Fix: refuse test manifests older than the freeze and check their
generator code and configuration hashes against the training worlds.

**MINOR 5. The household leg can fail on five worlds by chance.** M: on W2204 the model's household rate is
above the rule's (0.0337 against 0.0308); pooled it is 0.0195 against 0.0304 (68 against 106 of 3,487).
Resampling the five validation worlds 20,000 times, the pooled household leg fails in 144 (0.7%); precision and
the other legs never. The test gate has roughly a 1% chance of failing with a model that is fine; if it fails,
the rule says no promotion and no runner-up, so say this before the run, not after.

**MINOR 6. Count-valued metrics carry ratio-shaped numerators and denominators** (`publishing._account_metrics`).
M: 16 metric rows have a value that is not numerator over denominator. A page displaying the value as a rate
would mislabel it. Fix: make each split a share and each total a bare count.

**MINOR 7. Report presentation.** Bootstrap bounds on precision carry no note that they are spread over
resampled worlds; the heavy-returner rate is shown without the circularity note the specification requires.
Validation has no Markdown record yet; write it before the test so the test cannot colour how validation is
described. Commit the working tree so the test's provenance is a clean commit.

## Checked and found sound (measured unless noted)

The commit, scoring code hash, generator code hash, lock hash and all five validation manifest hashes match the
records; the experiment configuration hash matches. Validation manifests were written 16:46:48-16:48:30Z, after
the second dry-run record (16:46:16Z) and before the freeze (16:49:15Z). Validation features were built with
the training-frozen category reference and used no fallback. All five model files were last written before
validation and their hashes match the records. Independent re-scoring reproduces every scorecard row exactly:
rule 345 of 1,420 (0.2430), logistic 904 (0.6366), boosted 15 leaves 1,004 (0.7070), boosted 31 leaves 1,002
(0.7056), isolation forests 314 and 343, volume 91, rulebook 501; segment sizes 2,379 / 5,418 / 3,487; the
isolation forests fail precision and the household leg; the choice is `hgb_leaf15`. The error account
reproduces exactly (416 false positives, 308 repeat claimants, 47 in no group; 595 false negatives split 321 /
231 / 43 over 451 / 610 / 538 positives; 1,042 model-only selections with 728 abusers; 1,042 rule-only with 973
honest, all heavy returners). No positive has zero completed actions. Wardrobing evidence reproduces (211
elevated, 199 true, 623 temporary-use eligible customers). `final_test` scores only the chosen model and the
baseline, fits nothing, has no runner-up path, and its passed / failed / unverifiable logic follows the
specification. Publication promotes only on a passed test. The experiment payload builds and matches the schema.

## Headline honesty

Validation 0.707 (resampling spread 0.692-0.722, per world 0.683-0.730) is inside the 0.69-0.71 the dry-run
record predicted; the optimism from picking the winner is at most two true positives among three near-identical
candidates, so the test should land around 0.69-0.72 and the rule around 0.22-0.27. Say: "0.71 against 0.24 on
five held-out simulated worlds; 0.56 without any timing feature; a result about this simulation, not about real
returns." Do not say "significant", do not cite the heavy-returner leg as evidence, and do not present the
0.75-0.85 target as met.

## Not checked

Generator correctness for new seeds; service and web code beyond the report shape; notebooks; stress worlds;
bundle building on the test outcome.
