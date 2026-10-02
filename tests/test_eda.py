"""Exploration helpers (final-spec component 05, EDA acceptance criteria)."""
import pytest

from arai import eda
from arai.settings import load_settings


def test_enrichment_fixture_and_null_on_zero_denominator():
    result = eda.enrichment(population=1000, positives=200, subset=300, subset_positives=40)
    assert result["enrichment"] == pytest.approx(0.667, abs=0.001) and result["recall"] == pytest.approx(0.20)
    assert eda.enrichment(1000, 0, 300, 0) == {"enrichment": None, "recall": None}
    assert eda.enrichment(1000, 200, 0, 0)["enrichment"] is None
    assert eda.ratio(0, 0) is None and eda.ratio(0, 5) == 0.0


def test_auc_from_ranks():
    assert eda.auc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0
    assert eda.auc([4, 3, 2, 1], [0, 0, 1, 1]) == 0.0
    assert eda.auc([1, 1, 1, 1], [0, 1, 0, 1]) == 0.5
    assert eda.auc([1, 2], [0, 0]) is None


def test_eligibility_report_reconciles_with_its_denominators(world):
    report = eda.eligibility(world)
    assert report["eligible_customers"] + report["excluded_customers"] == report["customers"] == world.n_customers
    assert report["abusers_eligible"] + report["abusers_excluded"] == report["abusers_all"]
    assert report["abusers_all"] == int(world.truth["customer_truth"]["y_abuse"].sum())
    assert report["prevalence_eligible"] == pytest.approx(report["abusers_eligible"] / report["eligible_customers"])


def test_every_code_used_deceptively_also_has_honest_use(world):
    codes = eda.code_overlap(world)
    assert codes.loc[codes["deceptive_or_temporary"] > 0, "code_has_honest_use"].all()
    claim_codes = ["item_not_received", "wrong_item_sent", "missing_parts", "empty_package"]
    assert (codes.loc[claim_codes, "honest"] > 0).all()


def test_benign_segments_are_eligible_honest_customers(world):
    segments = eda.benign_segments(world)
    for name in ("legit_heavy_returner", "defective_product_buyer", "benign_household"):
        members = segments[segments[name]]
        assert len(members) and members["eligible"].all() and (members["y_abuse"] == 0).all()


def test_targets_table_stays_close_on_measures_with_many_draws(world):
    table = eda.targets_vs_realised(world, load_settings(world.seed)).set_index("measure")
    for measure in ("mean action rate of propensity accounts", "carrier damage per delivered unit",
                    "cancelled share of lines", "household members, share of accounts",
                    "orders per account (target total / realised base orders)"):
        assert abs(table.loc[measure, "relative_deviation"]) < 0.25, measure


def test_assigned_sharing_differs_from_realised_usage(world):
    usage = eda.relationships(world)["usage"]
    assert (usage["mean_realised_usage"] > 0).all() and (usage["mean_realised_usage"] < 1).all()
    assert usage["never_used"].sum() > 0          # a member with few orders may never use the shared value
