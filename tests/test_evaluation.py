"""Evaluation and selection (final-spec components 08 and 09) on hand-labelled fixtures."""
import json
import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from arai import evaluation, experiment, selection
from arai.evaluation import SEGMENTS
from tests.helpers import CUTOFF, make_tables, simple_order


def scored(world_id, scores, labels, **segments) -> pd.DataFrame:
    n = len(scores)
    frame = pd.DataFrame({"world_id": world_id, "customer_id": [f"{world_id}-C{i:03d}" for i in range(n)],
                          "score": np.asarray(scores, dtype=float), "y_abuse": labels})
    for name in SEGMENTS:
        frame[name] = segments.get(name, [False] * n)
    for action in (*evaluation.ACTION_TYPES, "coordinated_action_flag"):
        frame[action] = False
    return frame


# ------------------------------------------------------------------ selection of the review set
def test_review_budget_is_a_ceiling_per_world_then_pooled():
    # world A: 21 eligible -> k = ceil(1.05) = 2 at 5%, 1 at 1%, 3 at 10%; world B: 40 eligible -> 2, 1, 4
    a = scored("WA", np.arange(21, 0, -1), [1, 0, 1] + [0] * 18)
    b = scored("WB", np.arange(40, 0, -1), [1, 1, 0, 1] + [0] * 36)
    frame = pd.concat([a, b], ignore_index=True)
    result = evaluation.evaluate(frame, "score")
    assert result[0.05]["k"] == 4 and result[0.05]["true_positives"] == 3            # A: 1 of 2, B: 2 of 2
    assert result[0.05]["precision"] == pytest.approx(3 / 4) and result[0.05]["recall"] == pytest.approx(3 / 5)
    assert result[0.01]["k"] == 2 and result[0.01]["precision"] == 1.0
    assert result[0.10]["k"] == 3 + 4 and result[0.10]["true_positives"] == 2 + 3
    per_world = evaluation.per_world(frame, evaluation.select(frame, "score"))
    assert per_world.loc["WA", "k"] == 2 and per_world.loc["WB", "k"] == 2


def test_ties_are_broken_by_the_public_hash_never_by_row_order():
    frame = scored("WA", [1.0] * 20, [0] * 20)                                        # everyone tied; k = 1
    chosen = frame.loc[evaluation.select(frame, "score"), "customer_id"].tolist()
    expected = min(frame["customer_id"], key=lambda c: evaluation.tie_key("WA", c))
    assert chosen == [expected]
    shuffled = frame.sample(frac=1.0, random_state=3).reset_index(drop=True)
    assert shuffled.loc[evaluation.select(shuffled, "score"), "customer_id"].tolist() == [expected]
    with pytest.raises(ValueError, match="missing or non-finite"):
        evaluation.select(frame.assign(score=[np.nan] + [1.0] * 19), "score")


def test_segment_rates_keep_their_denominators_and_a_zero_denominator_is_null():
    heavy = [True] * 4 + [False] * 16
    frame = scored("WA", np.arange(20, 0, -1), [0] * 20, legit_heavy_returner=heavy)
    result = evaluation.confusion(frame, evaluation.select(frame, "score"))
    assert result["legit_heavy_returner_size"] == 4 and result["legit_heavy_returner_selected"] == 1
    assert result["legit_heavy_returner_fpr"] == 0.25
    assert result["benign_household_size"] == 0 and result["benign_household_fpr"] is None       # never 0%
    assert result["recall"] is None                                                               # no positives at all


# ------------------------------------------------------------------ benign segments
def _segment_world():
    """Ten eligible customers. c0 returns 2 of 3 (the top tenth is a tie between c0 and c1, both kept)."""
    skus = [("A", "S1", "Shirt", "M", 0, 30)]
    orders, lines, returns = [], [], []
    for i in range(10):
        shared = "HOME" if i in (4, 5) else None                    # c4 and c5 are a household that shares an address
        orders.append(simple_order(f"O{i}", f"c{i}", address=shared))
        for n in (1, 2, 3):
            lines.append((f"O{i}", n, "A", 1, "delivered", "2026-01-10"))
    for i, returned in {0: 2, 1: 2, 2: 1, 3: 1, 9: 1}.items():
        for n in range(1, returned + 1):
            returns.append((f"R{i}", n, f"O{i}", n, 1, "poor_quality", "2026-01-12 10:00", "refunded"))
    tables = make_tables(skus, orders, lines, returns)
    truth = {
        "customer_truth": pd.DataFrame({"customer_id": [f"c{i}" for i in range(10)], "y_abuse": [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
                                        "household_id": [None, None, None, None, "H1", "H1", "H2", "H2", None, None]}),
        # c2 requested its defective unit; c8 received a defective unit and kept it; c9's defective unit is on its line 2, not returned
        # c3 had two units genuinely fail and c7 one; c1, the abuser, also had two
        "unit_truth": pd.DataFrame({"order_id": ["O2", "O8", "O9", "O3", "O3", "O7", "O1", "O1"],
                                    "order_line_no": [1, 1, 2, 2, 3, 1, 1, 2], "unit_index": [1] * 8,
                                    "received_defective_unit": [True, True, True, False, False, False, False, False],
                                    "genuine_fulfilment_cause": [None, None, None, "item_not_received", "wrong_item_sent", "empty_package",
                                                                 "missing_parts", "missing_parts"]}),
        "unit_allocation": pd.DataFrame({"order_id": ["O2", "O9"], "order_line_no": [1, 1], "unit_index": [1, 1],
                                         "reservation_kind": ["honest_request", "honest_request"]}),
    }
    world = SimpleNamespace(tables=tables, truth=truth, snapshot_date=pd.Timestamp(CUTOFF).date())
    counts = tables["sales_order_line"].merge(tables["sales_order"][["order_id", "customer_id"]], on="order_id")
    requested = tables["return_order_line"].merge(tables["sales_order"][["order_id", "customer_id"]], on="order_id") \
        .groupby("customer_id")["quantity_returned"].sum()
    features = pd.DataFrame({"customer_id": [f"c{i}" for i in range(10)], "eligible": True})
    features["raw_return_rate"] = features["customer_id"].map(requested).fillna(0) / 3
    return world, features


def test_benign_segments_follow_the_definitions():
    world, features = _segment_world()
    segments = evaluation.benign_segments(world, features).set_index("customer_id")
    # the 90th percentile is tied between c0 and c1; ties are included, but c1 is an abuser and so in no benign segment
    assert segments.index[segments["legit_heavy_returner"]].tolist() == ["c0"]
    # a kept defective unit (c8) and a defective unit that was not the one returned (c9) do not make a defective buyer
    assert segments.index[segments["defective_product_buyer"]].tolist() == ["c2"]
    # household members who never used a shared identifier (c6, c7) are not in the household segment
    assert segments.index[segments["benign_household"]].tolist() == ["c4", "c5"]
    # two genuinely failed units make an honest repeat claimant (c3); one does not (c7); an abuser never is one (c1)
    assert segments.index[segments["repeat_genuine_claimant"]].tolist() == ["c3"]
    assert not segments.loc["c1", list(SEGMENTS)].any()


def test_segments_may_overlap_and_are_counted_separately():
    frame = scored("WA", np.arange(20, 0, -1), [0] * 20, legit_heavy_returner=[True] + [False] * 19,
                   benign_household=[True] + [False] * 19)
    result = evaluation.confusion(frame, evaluation.select(frame, "score"))
    assert result["legit_heavy_returner_selected"] == 1 and result["benign_household_selected"] == 1


# ------------------------------------------------------------------ uncertainty and the error account
def test_bootstrap_is_paired_seeded_and_reports_intervals_not_significance():
    rng = np.random.default_rng(1)
    frames = []
    for w in range(5):
        y = (rng.random(200) < 0.1).astype(int)
        frames.append(scored(f"W{w}", y + rng.normal(scale=0.5, size=200), y).assign(noise=rng.random(200)))
    frame = pd.concat(frames, ignore_index=True)
    first = evaluation.bootstrap(frame, {"model": "score", "noise": "noise"}, baseline="noise")
    again = evaluation.bootstrap(frame, {"model": "score", "noise": "noise"}, baseline="noise")
    pd.testing.assert_frame_equal(first, again)
    assert list(first.columns) == ["precision", "lower_95", "upper_95", "difference_from_baseline_lower_95",
                                   "difference_from_baseline_upper_95"]
    assert first.loc["noise", ["difference_from_baseline_lower_95", "difference_from_baseline_upper_95"]].tolist() == [0.0, 0.0]
    assert first.loc["model", "lower_95"] <= first.loc["model", "precision"] <= first.loc["model", "upper_95"]


def test_error_account_splits_false_positives_and_false_negatives_with_denominators():
    labels = [1, 0, 0, 1, 1] + [0] * 35                                             # 40 eligible -> k = 2
    frame = scored("WA", np.arange(40, 0, -1), labels, legit_heavy_returner=[False, True] + [False] * 38)
    frame["temporary_use_return"] = [False, False, False, True, False] + [False] * 35
    frame["deceptive_contents_claim"] = [True, False, False, False, True] + [False] * 35
    frame["genuine_claim_units"] = [0, 3, 0, 0, 0] + [0] * 35
    frame["baseline"] = list(range(40))                                             # the rule picks the last two rows
    actions = pd.Series([4, 0, 0, 1, 2] + [0] * 35)
    account = evaluation.error_account(frame, evaluation.select(frame, "score"), evaluation.select(frame, "baseline"), actions)
    assert account["false_positives"] == {"false_positives": 1, "legit_heavy_returner": 1, "defective_product_buyer": 0,
                                          "benign_household": 0, "repeat_genuine_claimant": 1, "none_of_these": 0}
    fn = account["false_negatives"]
    assert fn["false_negatives"] == 2 and fn["temporary_use_return"] == 1 and fn["deceptive_contents_claim"] == 1
    assert fn["completed_actions_1"] == 1 and fn["positives_with_1_actions"] == 1 and fn["completed_actions_2-3"] == 1
    assert fn["completed_actions_4+"] == 0 and fn["positives_with_4+_actions"] == 1
    difference = account["model_versus_baseline"]
    assert difference["selected_by_model_only"] == 2 and difference["of_which_abusers"] == 1
    assert difference["selected_by_baseline_only"] == 2 and difference["of_which_honest"] == 2


# ------------------------------------------------------------------ the gate
BASE = {"precision": 0.20, "legit_heavy_returner_fpr": 0.40, "defective_product_buyer_fpr": 0.06, "benign_household_fpr": 0.04,
        "repeat_genuine_claimant_fpr": 0.07, **{s + "_size": 500 for s in SEGMENTS}}


def _result(**changes):
    return {**BASE, **changes}


def test_gate_needs_strictly_higher_precision_and_no_worse_segment_rate():
    assert selection.gate(_result(precision=0.5, benign_household_fpr=0.04), BASE) == (True, [])       # equal rate is allowed
    passed, reasons = selection.gate(_result(precision=0.9, benign_household_fpr=0.041), BASE)
    assert not passed and reasons == ["benign_household false-positive rate above the baseline"]
    passed, reasons = selection.gate(_result(precision=0.20, legit_heavy_returner_fpr=0.0), BASE)        # equal precision fails
    assert not passed and reasons == ["precision not above the baseline"]
    # the fourth leg (experiment contract 2.0): honest repeat claimants may not be reviewed more often than under the rule
    assert SEGMENTS == ("legit_heavy_returner", "defective_product_buyer", "benign_household", "repeat_genuine_claimant")
    passed, reasons = selection.gate(_result(precision=0.9, repeat_genuine_claimant_fpr=0.071), BASE)
    assert not passed and reasons == ["repeat_genuine_claimant false-positive rate above the baseline"]
    assert selection.gate(_result(precision=0.9, repeat_genuine_claimant_fpr=0.05), BASE) == (True, [])


def test_gate_refuses_thin_or_empty_segments():
    passed, reasons = selection.gate(_result(precision=0.5, defective_product_buyer_size=199), BASE)
    assert not passed and reasons == ["defective_product_buyer has fewer than 200 members"]
    passed, reasons = selection.gate(_result(precision=0.5, benign_household_fpr=None), BASE)
    assert not passed and reasons == ["benign_household false-positive rate undefined"]
    assert selection.gate(_result(precision=0.5, defective_product_buyer_size=199), BASE, require_coverage=False)[0]


def _card(rows):
    return pd.DataFrame(rows).set_index("ranking")


def test_choice_is_precision_then_worst_segment_rate_then_ordinal():
    rows = [{"ranking": "a", "role": "candidate", "status": "passed", "precision": 0.6, "worst_segment_fpr": 0.10, "ordinal": 1},
            {"ranking": "b", "role": "candidate", "status": "passed", "precision": 0.6, "worst_segment_fpr": 0.08, "ordinal": 3},
            {"ranking": "c", "role": "candidate", "status": "passed", "precision": 0.6, "worst_segment_fpr": 0.08, "ordinal": 2},
            {"ranking": "d", "role": "candidate", "status": "rejected", "precision": 0.9, "worst_segment_fpr": 0.01, "ordinal": 4},
            {"ranking": "rulebook", "role": "reference", "status": "report only", "precision": 0.95, "worst_segment_fpr": 0.0}]
    assert selection.choose(_card(rows)) == "c"                       # b and c tie on both; the lower ordinal wins
    assert selection.choose(_card(rows[3:])) is None                  # a rejected candidate and a reference: no winner, no promotion


def test_references_share_population_and_ties_and_can_never_be_selected():
    labels = [1] * 3 + [0] * 57
    frame = scored("WA", np.arange(60, 0, -1), labels)
    frame = frame.assign(raw_return_rate=np.linspace(0, 1, 60), candidate=frame["score"], rulebook=frame["score"] + 1)
    for name in SEGMENTS:
        frame[name] = [False] * 30 + [True] * 30                     # benign members the rule selects and the others do not
    rankings = {"raw_return_rate": "raw_return_rate", "candidate": "candidate", "analyst_rulebook": "rulebook"}
    card = selection.scorecard(frame, rankings, selectable={"candidate": 1}, require_coverage=False)
    assert (card["k"] == math.ceil(0.05 * 60)).all()                 # identical population and budget for every ranking
    assert card.loc["analyst_rulebook", "role"] == "reference" and card.loc["analyst_rulebook", "status"] == "report only"
    assert card.loc["candidate", "status"] == "passed" and selection.choose(card) == "candidate"
    only_reference = selection.scorecard(frame, rankings, selectable={}, require_coverage=False)
    assert selection.choose(only_reference) is None


def test_rulebook_thresholds_come_from_training_folds_only():
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({"world_id": np.repeat(["W1", "W2"], 100), "eligible": True, "raw_return_rate": rng.random(200),
                          "requested_refund_ratio": rng.random(200), "claim_lines": 0, "supported_neighbor_count": 0,
                          "late_window_share": 0.0, "timed_return_lines": 0})
    frame.loc[frame["world_id"] == "W2", "raw_return_rate"] += 10             # the held-out world is on another scale
    thresholds = selection.rulebook_thresholds(frame[frame["world_id"] == "W1"])
    assert thresholds["raw_return_rate_p90"] < 1.0
    scores = selection.rulebook_out_of_fold(frame, {"W1": 0, "W2": 1})
    held_out = frame["world_id"] == "W2"
    assert (np.floor(scores[held_out]) >= 1).all()                              # scored with W1's threshold: every row fires
    assert (np.floor(scores[~held_out]) <= 1).all() and (np.floor(scores[~held_out]) == 0).mean() > 0.4
    fired = selection.rulebook_score(pd.DataFrame({"raw_return_rate": [np.nan], "requested_refund_ratio": [np.nan], "claim_lines": [2],
                                                   "supported_neighbor_count": [1], "late_window_share": [np.nan],
                                                   "timed_return_lines": [0]}), thresholds)
    assert fired.iloc[0] == 2.0                                                 # null inputs do not fire; two claim rules do


# ------------------------------------------------------------------ the order of the experiment is enforced
def test_validation_needs_a_recorded_dry_run_and_the_test_needs_a_frozen_selection(tmp_path):
    with pytest.raises(RuntimeError, match="dry run must be recorded"):
        experiment.validate("EXP-T", artifact_root=tmp_path)
    with pytest.raises(RuntimeError, match="selection must be frozen"):
        experiment.final_test("EXP-T", artifact_root=tmp_path)
    out = tmp_path / "experiments" / "EXP-T"
    (out / "reports").mkdir(parents=True)
    unselected = {"selected_model_id": None, "selection_status": "no_selected_model", "final_test_status": "not_run"}
    (out / "selection.json").write_text(json.dumps(unselected))
    with pytest.raises(RuntimeError, match="no model was selected"):
        experiment.final_test("EXP-T", artifact_root=tmp_path)                  # fallback, never a fabricated promotion
    (out / "reports" / "dry_run.json").write_text("{}")
    with pytest.raises(RuntimeError, match="already frozen"):
        experiment.validate("EXP-T", artifact_root=tmp_path)
    with pytest.raises(RuntimeError, match="frozen selection"):
        experiment.train("EXP-T", artifact_root=tmp_path)


def test_the_final_test_runs_once_and_survives_a_crash_between_its_two_records(tmp_path):
    out = tmp_path / "experiments" / "EXP-T"
    (out / "reports").mkdir(parents=True)
    selected = {"selected_model_id": "hgb_leaf15", "selected_model_sha256": "0" * 64, "final_test_status": "not_run",
                "frozen_at": "2026-10-02T00:00:00Z"}
    # the report was written and the process died before the selection record was updated: finish the record, score nothing
    (out / "selection.json").write_text(json.dumps(selected))
    (out / "reports" / "test.json").write_text(json.dumps({"final_test_status": "failed", "recorded_at": "2026-10-02T10:00:00Z"}))
    assert experiment.final_test("EXP-T", artifact_root=tmp_path)["final_test_status"] == "failed"
    record = json.loads((out / "selection.json").read_text())
    assert record["final_test_status"] == "failed" and record["tested_at"] == "2026-10-02T10:00:00Z"
    with pytest.raises(RuntimeError, match="runs once"):
        experiment.final_test("EXP-T", artifact_root=tmp_path)                  # no second look, no runner-up
    (out / "reports" / "test.json").unlink()                                    # deleting the report does not buy another run
    with pytest.raises(RuntimeError, match="does not run twice"):
        experiment.final_test("EXP-T", artifact_root=tmp_path)
    # a model file that is not the one frozen at selection is refused before anything is scored
    (out / "selection.json").write_text(json.dumps(selected))
    (out / "candidates" / "hgb_leaf15").mkdir(parents=True)
    (out / "candidates" / "hgb_leaf15" / "model.skops").write_bytes(b"not the frozen model")
    with pytest.raises(RuntimeError, match="differs from the one frozen"):
        experiment.final_test("EXP-T", artifact_root=tmp_path)
    assert not (out / "reports" / "test.json").exists()
