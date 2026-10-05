"""Feature engineering (final-spec component 06, FEAT acceptance criteria) on hand-calculated fixtures."""
import numpy as np
import pandas as pd
import pytest

from arai import features as F
from tests.helpers import CUTOFF, make_tables, simple_order

SKUS = [("A", "S1", "Shirt", "M", 0, 30), ("B", "S1", "Shirt", "L", 0, 30), ("C", "S2", "Shirt", "M", 0, 30),
        ("D", "S3", "Jeans", "M", 0, 30), ("E", "S4", "Jacket", "M", 1, 45)]
DAY = "2026-01-10"                       # delivered long before the cutoff, so every line below is mature


def expectation_fixture():
    orders = [simple_order(f"O{i}", f"c{i}") for i in range(1, 8)] + [simple_order("O2b", "c2")]
    lines = [("O1", 1, "A", 2, "delivered", DAY),       # c1: buys two of A, returns one (partial quantity)
             ("O2", 1, "A", 1, "delivered", DAY), ("O2b", 1, "B", 1, "delivered", DAY),
             ("O3", 1, "B", 2, "delivered", DAY),
             ("O4", 1, "C", 1, "delivered", DAY),       # c4: sole buyer of a single-SKU style
             ("O5", 1, "D", 1, "delivered", DAY), ("O6", 1, "D", 1, "delivered", DAY),   # nobody returns jeans
             ("O7", 1, "E", 1, "delivered", DAY)]       # c7: the only jacket buyer, so the category has no peers
    returns = [("R1", 1, "O1", 1, 1, "wrong_size", "2026-01-15 10:00", "refunded"),
               ("R2", 1, "O2b", 1, 1, "didnt_fit", "2026-01-15 10:00", "refunded"),
               ("R4", 1, "O4", 1, 1, "wrong_size", "2026-01-15 10:00", "refunded")]
    return make_tables(SKUS, orders, lines, returns)


REFERENCE = F.Reference(category_rate={"Shirt": 0.2, "Jeans": 0.2, "Jacket": 0.15})


def test_two_level_expectation_matches_hand_calculation():
    result = F.compute_features(expectation_fixture(), CUTOFF, REFERENCE)
    f = result.features.set_index("customer_id")
    # c1: category peers (3-1)/(7-2)=0.4; style (2-1+20*0.4)/(6-2+20)=0.375; SKU (1-1+20*0.375)/(3-2+20)=7.5/21
    assert f.loc["c1", "raw_return_rate"] == pytest.approx(0.5)
    assert f.loc["c1", "expected_return_rate"] == pytest.approx(7.5 / 21)
    assert f.loc["c1", "residual_z"] == pytest.approx((1 - 2 * 7.5 / 21) / np.sqrt(2 * (7.5 / 21) * (13.5 / 21)))
    # c4 is the sole buyer of a single-SKU style: everything shrinks back to the self-excluded category rate 2/6
    assert f.loc["c4", "expected_return_rate"] == pytest.approx(1 / 3)
    assert f.loc["c4", "residual_z"] == pytest.approx((1 - 1 / 3) / np.sqrt((1 / 3) * (2 / 3)))
    # jeans: no peer ever returned, so the expectation and its variance are zero and the residual is null, not zero
    assert f.loc["c5", "expected_return_rate"] == 0 and pd.isna(f.loc["c5", "residual_z"])
    # jackets: no peers at all, so the frozen training category mean is used
    assert f.loc["c7", "expected_return_rate"] == pytest.approx(0.15)
    assert result.fallback_uses == 1


def test_a_category_without_peers_needs_the_frozen_reference():
    with pytest.raises(ValueError):
        F.compute_features(expectation_fixture(), CUTOFF, reference=None)


def test_feature_schema_is_the_ordered_contract():
    result = F.compute_features(expectation_fixture(), CUTOFF, REFERENCE)
    order = F.feature_order()
    assert len(order) == 43 and list(result.features.columns[1:44]) == order
    assert order[:17] == F.feature_order()[:17] and order[16] == "late_return_lines"     # contract 1.4 is the first 17, unchanged
    # raw link structure is evidence for the analyst, never a model input
    assert F.evidence_features() == ["max_identifier_fanout", "supported_neighbor_count"]
    assert not set(F.evidence_features()) & set(order)


def test_renaming_identifiers_changes_no_feature():
    tables = expectation_fixture()
    renamed = {name: table.copy() for name, table in tables.items()}
    for name in ("customer_master", "sales_order", "return_order"):
        renamed[name]["customer_id"] = "X" + renamed[name]["customer_id"]
    for column in ("address_id", "device_id", "payment_id"):
        renamed["sales_order"][column] = "Z" + renamed["sales_order"][column]
    a = F.compute_features(tables, CUTOFF, REFERENCE).features
    b = F.compute_features(renamed, CUTOFF, REFERENCE).features
    pd.testing.assert_frame_equal(a.drop(columns="customer_id"), b.drop(columns="customer_id"))


def test_eligibility_is_exactly_three_mature_lines_and_recent_requests_do_not_move_the_mature_rate():
    orders = [simple_order("O1", "c1"), simple_order("O2", "c2"), simple_order("O3", "c3")]
    recent = "2026-09-01"                                   # delivered, but its 30-day window is still open at the cutoff
    lines = [("O1", 1, "A", 1, "delivered", DAY), ("O1", 2, "B", 1, "delivered", DAY), ("O1", 3, "C", 1, "delivered", DAY),
             ("O2", 1, "A", 1, "delivered", DAY), ("O2", 2, "B", 1, "delivered", DAY), ("O2", 3, "C", 1, "delivered", recent),
             ("O3", 1, "A", 1, "delivered", DAY), ("O3", 2, "B", 1, "shipped", None)]
    returns = [("R2", 1, "O2", 3, 1, "item_not_received", "2026-09-03 09:00", "pending")]
    f = F.compute_features(make_tables(SKUS, orders, lines, returns), CUTOFF, REFERENCE).features.set_index("customer_id")
    assert f.loc["c1", "mature_sale_lines"] == 3 and f.loc["c1", "eligible"]
    assert f.loc["c2", "mature_sale_lines"] == 2 and not f.loc["c2", "eligible"]
    assert f.loc["c2", "raw_return_rate"] == 0                # the unmatured claim is not in the mature rate
    assert f.loc["c2", "claim_share"] == 1                    # but it is visible in the composition of requests
    assert f.loc["c2", "open_window_share"] == pytest.approx(1 / 3)


def _graph_tables(extra_orders=()):
    orders = [("O1", "c1", "2026-01-01", "A1", "D1", "P1"), ("O2", "c2", "2026-01-01", "A1", "D1", "P2"),   # two shared types
              ("O3", "c3", "2026-01-01", "A1", "D3", "P3"),                                                 # address only
              ("O4", "c4", "2026-01-01", "A4", "D4", "P4")] + list(extra_orders)
    lines = [(o[0], 1, "A", 1, "delivered", DAY) for o in orders]
    return orders, lines


def test_an_edge_needs_two_shared_identifier_types():
    orders, lines = _graph_tables()
    result = F.compute_features(make_tables(SKUS, orders, lines), CUTOFF, REFERENCE)
    assert result.graph.neighbours == {"c1": {"c2"}, "c2": {"c1"}}
    f = result.features.set_index("customer_id")
    assert f.loc["c1", "supported_neighbor_count"] == 1 and f.loc["c3", "supported_neighbor_count"] == 0
    assert f.loc["c3", "max_identifier_fanout"] == 3 and f.loc["c4", "max_identifier_fanout"] == 1


def test_a_value_shared_by_more_than_25_accounts_is_dropped():
    crowd = [(f"X{i}", f"x{i}", "2026-01-01", "HOSTEL", "DEV", f"PX{i}") for i in range(26)]
    lines = [(o[0], 1, "A", 1, "delivered", DAY) for o in crowd]
    result = F.compute_features(make_tables(SKUS, crowd, lines), CUTOFF, REFERENCE)
    assert result.graph.dropped_values == 2 and result.graph.neighbours == {}        # an empty graph is valid
    assert (result.features["supported_neighbor_count"] == 0).all()
    assert (result.features["max_identifier_fanout"] == 25).all()                    # capped


def _claim_tables(second_claim_day, neighbour_device="D1"):
    orders = [("O1", "c1", "2026-01-01", "A1", "D1", "P1"), ("O2", "c2", "2026-01-01", "A1", neighbour_device, "P2")]
    lines = [("O1", 1, "A", 1, "delivered", DAY), ("O2", 1, "B", 1, "delivered", DAY)]      # same style, different SKUs
    returns = [("R1", 1, "O1", 1, 1, "item_not_received", "2026-01-12 10:00", "refunded"),
               ("R2", 1, "O2", 1, 1, "wrong_item_sent", f"{second_claim_day} 10:00", "refunded")]
    return make_tables(SKUS, orders, lines, returns)


def test_linked_claims_need_a_supported_neighbour_on_the_same_style_within_seven_days():
    linked = F.compute_features(_claim_tables("2026-01-19"), CUTOFF, REFERENCE)           # 7 days apart, different SKUs
    assert (linked.features.set_index("customer_id")["coordinated_claim_share"] == 1).all()
    assert linked.styles.set_index("style_id").loc["S1", "linked_claimers"] == 2
    apart = F.compute_features(_claim_tables("2026-01-20"), CUTOFF, REFERENCE)            # 8 days apart
    assert (apart.features.set_index("customer_id")["coordinated_claim_share"] == 0).all()
    unsupported = F.compute_features(_claim_tables("2026-01-19", neighbour_device="D2"), CUTOFF, REFERENCE)   # address only
    assert (unsupported.features.set_index("customer_id")["coordinated_claim_share"] == 0).all()
    no_claims = F.compute_features(expectation_fixture(), CUTOFF, REFERENCE).features
    assert no_claims["coordinated_claim_share"].isna().all()                              # null without own claims


def _style_tables(quality_returns, claimers):
    """A style with 20 buyers of SKU A; `quality_returns` of them complain about quality, `claimers` linked accounts claim."""
    orders, lines, returns = [], [], []
    for i in range(20):
        linked = i < claimers
        orders.append((f"O{i}", f"c{i}", "2026-01-01", "RING" if linked else f"A{i}", "RINGDEV" if linked else f"D{i}", f"P{i}"))
        lines.append((f"O{i}", 1, "A", 1, "delivered", DAY))
        if linked:
            returns.append((f"R{i}", 1, f"O{i}", 1, 1, "item_not_received", "2026-01-12 10:00", "refunded"))
        elif i >= 20 - quality_returns:
            returns.append((f"R{i}", 1, f"O{i}", 1, 1, "poor_quality", "2026-01-12 10:00", "refunded"))
        elif i % 2:
            returns.append((f"R{i}", 1, f"O{i}", 1, 1, "wrong_size", "2026-01-12 10:00", "refunded"))
    return make_tables(SKUS, orders, lines, returns)


@pytest.mark.parametrize("quality_returns, claimers, state", [
    (0, 0, "no_elevated_signal"), (8, 0, "quality"), (0, 3, "targeting"), (8, 3, "mixed_or_uncertain"), (0, 2, "no_elevated_signal")])
def test_style_states(quality_returns, claimers, state):
    style = F.compute_features(_style_tables(quality_returns, claimers), CUTOFF, REFERENCE).styles.set_index("style_id").loc["S1"]
    assert style["state"] == state
    assert style["linked_claimers"] == (claimers if claimers >= 2 else 0)


def test_style_without_support_or_returns_has_its_own_state():
    orders = [simple_order(f"O{i}", f"c{i}") for i in range(20)]
    lines = [(f"O{i}", 1, "A", 1, "delivered", DAY) for i in range(20)] + [("O0", 2, "D", 1, "delivered", DAY)]
    styles = F.compute_features(make_tables(SKUS, orders, lines), CUTOFF, REFERENCE).styles.set_index("style_id")
    assert styles.loc["S1", "state"] == "no_return_evidence"          # supported, nothing returned
    assert styles.loc["S3", "state"] == "insufficient_support"        # one sale line
    assert pd.isna(styles.loc["S3", "damage_share"])


def _wardrobing(item_lines=4, late_occasion=0, occasion_returned=0, z=np.nan, complaints=0, peers=10_000):
    evidence = pd.DataFrame({"customer_id": ["c1"], "item_return_lines": [item_lines], "late_occasion_return_lines": [late_occasion],
                             "occasion_units": [6], "occasion_returned_units": [occasion_returned], "occasion_expected_units": [1.0],
                             "occasion_excess_z": [z], "clean_style_complaint_lines": [complaints], "wardrobing_peer_units": [peers]})
    return F.wardrobing_indicator(evidence).iloc[0]


def test_wardrobing_bands_need_a_late_occasion_return_and_support_for_it_with_integer_points():
    """Feature contract 2.1 (AM-52): a late return of occasion wear is the signal; what was returned decides whether it counts."""
    none = _wardrobing(item_lines=0)
    assert none["status"] == "insufficient_evidence" and pd.isna(none["indicator_score"])
    assert _wardrobing()["indicator_score"] == 0 and _wardrobing()["status"] == "no_elevated_signal"
    # the supporting evidence scores nothing without a late return, however strong
    unsupported = _wardrobing(occasion_returned=5, z=9.0, complaints=3)
    assert unsupported["indicator_score"] == 0 and not bool(unsupported["fired_occasion_excess"])
    # a late return alone reaches no band, however often: honest customers return late too
    late = _wardrobing(late_occasion=3)
    assert late["indicator_score"] == 40 and late["status"] == "no_elevated_signal" and bool(late["fired_late_occasion_return"])
    assert _wardrobing(late_occasion=1, occasion_returned=1, z=5.0)["indicator_score"] == 40      # one returned item is never an excess
    assert _wardrobing(late_occasion=1, occasion_returned=3, z=1.99)["indicator_score"] == 40     # below two standard deviations
    excess = _wardrobing(late_occasion=1, occasion_returned=3, z=2.0)
    assert excess["indicator_score"] == 70 and excess["status"] == "possible"
    complaint = _wardrobing(late_occasion=1, complaints=1)
    assert complaint["indicator_score"] == 70 and complaint["status"] == "possible"
    both = _wardrobing(late_occasion=1, occasion_returned=3, z=2.4, complaints=1)
    assert both["indicator_score"] == 100 and both["status"] == "elevated"
    assert sum(F.WARDROBING_POINTS.values()) == 100
    # too few other customers to compare with: no verdict and no fired signal
    thin = _wardrobing(late_occasion=1, occasion_returned=3, z=2.4, complaints=1, peers=F.WARDROBING_MIN_PEER_UNITS - 1)
    assert thin["status"] == "incomplete" and pd.isna(thin["indicator_score"]) and not bool(thin["fired_late_occasion_return"])
    assert _wardrobing(late_occasion=1, occasion_returned=3, z=2.4, complaints=1, peers=F.WARDROBING_MIN_PEER_UNITS)["status"] == "elevated"


def test_wardrobing_evidence_compares_occasion_returns_with_the_customers_other_returns_and_finds_clean_style_complaints(monkeypatch):
    skus = [("A", "S1", "Shirt", "M", 0, 30), ("E", "S4", "Jacket", "M", 1, 45), ("G", "S5", "Jeans", "M", 0, 30)]
    orders = [simple_order(f"O{i}", f"c{i}") for i in (1, 2, 3)]
    lines = [("O1", 1, "A", 4, "delivered", DAY), ("O1", 2, "E", 3, "delivered", DAY), ("O1", 3, "G", 1, "delivered", DAY),
             ("O2", 1, "A", 10, "delivered", DAY), ("O2", 2, "E", 5, "delivered", DAY), ("O2", 3, "G", 5, "delivered", DAY),
             ("O3", 1, "A", 10, "delivered", DAY), ("O3", 2, "E", 5, "delivered", DAY), ("O3", 3, "G", 5, "delivered", DAY)]
    returns = [("R1", 1, "O1", 2, 3, "didnt_suit", "2026-02-19 10:00", "refunded"),        # all three jackets, on day 40 of 45
               ("R1", 2, "O1", 3, 1, "poor_quality", "2026-01-15 10:00", "refunded"),      # jeans nobody else complains about
               ("R2", 1, "O2", 1, 2, "defective", "2026-01-15 10:00", "refunded"), ("R2", 2, "O2", 2, 1, "didnt_suit", "2026-01-15 10:00", "refunded"),
               ("R3", 1, "O3", 1, 2, "poor_quality", "2026-01-15 10:00", "refunded"), ("R3", 2, "O3", 2, 1, "didnt_suit", "2026-01-15 10:00", "refunded")]
    reference = F.Reference({"Shirt": 0.2, "Jeans": 0.2, "Jacket": 0.2})
    tables = make_tables(skus, orders, lines, returns)
    # three customers are too few to compare with: the evidence is computed, the indicator gives no verdict
    small = F.compute_features(tables, CUTOFF, reference)
    assert small.features.set_index("customer_id").loc["c1", "wardrobing_peer_units"] == 10            # the others bought ten jackets
    assert small.wardrobing.set_index("customer_id").loc["c1", "status"] == "incomplete"
    monkeypatch.setattr(F, "WARDROBING_MIN_PEER_UNITS", 5)
    result = F.compute_features(tables, CUTOFF, reference)
    f = result.features.set_index("customer_id")
    # c1: the others return 2 of 10 jackets and 4 of 30 other units. Own rate on other products, shrunk with 10 units:
    # (1 + 10 * 4/30) / (5 + 10); carried to occasion wear by (2/10) / (4/30); expected jackets = 3 * p
    p = (1 + 10 * 4 / 30) / 15 * (2 / 10) / (4 / 30)
    assert f.loc["c1", "occasion_units"] == 3 and f.loc["c1", "occasion_returned_units"] == 3
    assert f.loc["c1", "occasion_expected_units"] == pytest.approx(3 * p) == pytest.approx(0.7)
    assert f.loc["c1", "occasion_excess_z"] == pytest.approx((3 - 3 * p) / np.sqrt(3 * p * (1 - p)))
    assert f.loc["c2", "occasion_excess_z"] < 0                                    # one jacket of five is fewer than their own rate predicts
    # complaints: c1's is on a style no other buyer complains about; c2's and c3's shirt is complained about by the other
    assert f["clean_style_complaint_lines"].to_dict() == {"c1": 1, "c2": 0, "c3": 0}
    w = result.wardrobing.set_index("customer_id")
    assert w.loc["c1", "status"] == "elevated" and w.loc["c1", "indicator_score"] == 100                # 40 + 30 + 30
    assert w.loc["c2", "status"] == "no_elevated_signal" and w.loc["c2", "indicator_score"] == 0
    # the same returns made early: the supporting evidence is unchanged and, without a late return, counts for nothing
    early = [(*r[:6], "2026-01-15 10:00", r[7]) for r in returns]
    again = F.compute_features(make_tables(skus, orders, lines, early), CUTOFF, reference)
    assert again.features.set_index("customer_id").loc["c1", "occasion_excess_z"] == pytest.approx(f.loc["c1", "occasion_excess_z"])
    assert again.wardrobing.set_index("customer_id").loc["c1", ["status", "indicator_score"]].tolist() == ["no_elevated_signal", 0]


def test_a_late_return_is_an_item_return_in_the_last_quarter_of_its_window():
    # 30-day window, delivered 2026-01-10: day 22 is before the last quarter, 23 and 30 are inside it, 31 is too late
    orders = [simple_order(f"O{i}", f"c{i}") for i in range(1, 6)]
    lines = [(f"O{i}", 1, "A", 1, "delivered", DAY) for i in range(1, 6)]
    returns = [("R1", 1, "O1", 1, 1, "didnt_suit", "2026-02-01 10:00", "refunded"),          # day 22
               ("R2", 1, "O2", 1, 1, "didnt_suit", "2026-02-02 10:00", "refunded"),          # day 23 (ratio .767)
               ("R3", 1, "O3", 1, 1, "didnt_suit", "2026-02-09 10:00", "refunded"),          # day 30: the last day
               ("R4", 1, "O4", 1, 1, "didnt_suit", "2026-02-10 10:00", "rejected"),          # day 31: after the window
               ("R5", 1, "O5", 1, 1, "item_not_received", "2026-02-05 10:00", "refunded")]   # a claim is not an item return
    result = F.compute_features(make_tables(SKUS, orders, lines, returns), CUTOFF, REFERENCE)
    late = result.features.set_index("customer_id")["late_return_lines"]
    assert late.to_dict() == {"c1": 0, "c2": 1, "c3": 1, "c4": 0, "c5": 0}
    assert result.wardrobing.set_index("customer_id").loc["c5", "status"] == "insufficient_evidence"
    f = result.features.set_index("customer_id")
    assert f.loc["c4", "late_window_share"] == 1 and f.loc["c4", "median_window_ratio"] == pytest.approx(31 / 30)
    very_late = make_tables(SKUS, [simple_order("O1", "c1")], [("O1", 1, "A", 1, "delivered", DAY)],
                            [("R1", 1, "O1", 1, 1, "wrong_size", "2026-06-01 10:00", "rejected")])
    assert F.compute_features(very_late, CUTOFF, REFERENCE).requests.iloc[0]["window_ratio"] == 2.0     # capped at twice the window


def test_withdrawn_requests_are_ignored_everywhere():
    orders = [simple_order("O1", "c1"), simple_order("O2", "c2")]
    lines = [("O1", 1, "A", 1, "delivered", DAY), ("O1", 2, "B", 1, "delivered", DAY), ("O2", 1, "A", 1, "delivered", DAY)]
    returns = [("R1", 1, "O1", 1, 1, "didnt_suit", "2026-02-05 10:00", "withdrawn"),
               ("R1", 2, "O1", 2, 1, "wrong_size", "2026-01-12 10:00", "refunded")]
    result = F.compute_features(make_tables(SKUS, orders, lines, returns), CUTOFF, REFERENCE)
    f = result.features.set_index("customer_id").loc["c1"]
    assert f["raw_return_rate"] == 0.5 and f["discretionary_share"] == 0 and f["all_requested_units"] == 1
    assert f["late_return_lines"] == 0 and result.wardrobing.set_index("customer_id").loc["c1", "item_return_lines"] == 1
    assert len(result.requests) == 1


def test_trend_compares_the_last_90_delivery_days_with_the_90_before():
    # cutoff 2026-09-09: delivery on 2026-06-12 is 89 days back (recent), 2026-06-11 is 90 days back (earlier window)
    skus = [("A", "S1", "Shirt", "M", 0, 7), ("B", "S1", "Shirt", "L", 0, 7)]
    orders = [simple_order("O1", "c1"), simple_order("O2", "c1", date="2026-01-02"), simple_order("O3", "c2")]
    lines = [("O1", 1, "A", 1, "delivered", "2026-06-12"), ("O2", 1, "A", 1, "delivered", "2026-06-11"),
             ("O3", 1, "A", 1, "delivered", "2026-06-12")]
    returns = [("R1", 1, "O1", 1, 1, "wrong_size", "2026-06-13 10:00", "refunded")]
    f = F.compute_features(make_tables(skus, orders, lines, returns), CUTOFF, REFERENCE).features.set_index("customer_id")
    assert f.loc["c1", "trend_90d"] == 1.0              # recent rate 1/1 minus earlier rate 0/1
    assert pd.isna(f.loc["c2", "trend_90d"])            # nothing delivered in the earlier window: null, not zero


def test_requested_refund_ratio_uses_net_value_after_discount():
    tables = make_tables(SKUS, [simple_order("O1", "c1")], [("O1", 1, "A", 2, "delivered", DAY), ("O1", 2, "B", 1, "delivered", DAY)],
                         [("R1", 1, "O1", 1, 1, "wrong_size", "2026-01-12 10:00", "refunded")])
    tables["sales_order_line"].loc[tables["sales_order_line"]["order_line_no"] == 1, ["line_discount", "line_total"]] = [400.0, 1600.0]
    f = F.compute_features(tables, CUTOFF, REFERENCE).features.set_index("customer_id")
    assert f.loc["c1", "requested_refund_ratio"] == pytest.approx(800.0 / 2600.0)       # one unit at 800 of 1,600 + 1,000


def test_coordinated_claim_share_counts_each_own_line_once():
    # c1 has two supported neighbours claiming on the same style in the same week, and a second claim nobody shares
    orders = [("O1", "c1", "2026-01-01", "A1", "D1", "P1"), ("O2", "c2", "2026-01-01", "A1", "D1", "P2"),
              ("O3", "c3", "2026-01-01", "A1", "D1", "P3"), ("O4", "c1", "2026-01-02", "A1", "D1", "P1")]
    lines = [("O1", 1, "A", 1, "delivered", DAY), ("O2", 1, "A", 1, "delivered", DAY), ("O3", 1, "B", 1, "delivered", DAY),
             ("O4", 1, "D", 1, "delivered", DAY)]
    returns = [("R1", 1, "O1", 1, 1, "item_not_received", "2026-01-12 10:00", "refunded"),
               ("R2", 1, "O2", 1, 1, "wrong_item_sent", "2026-01-13 10:00", "refunded"),
               ("R3", 1, "O3", 1, 1, "missing_parts", "2026-01-14 10:00", "refunded"),
               ("R4", 1, "O4", 1, 1, "item_not_received", "2026-01-12 10:00", "refunded")]
    result = F.compute_features(make_tables(SKUS, orders, lines, returns), CUTOFF, REFERENCE)
    assert result.features.set_index("customer_id").loc["c1", "coordinated_claim_share"] == 0.5   # one of two lines, once
    own = result.requests[result.requests["customer_id"] == "c1"].set_index("order_id")
    assert own.loc["O1", "linked_neighbours"] == 2 and not own.loc["O4", "linked"]


def _share_tables(claim_lines, linked):
    """One style, 40 buyers of SKU A, `claim_lines` single claims of which the first `linked` come from one linked group."""
    orders, lines, returns = [], [], []
    for i in range(40):
        ring = i < linked
        orders.append((f"O{i}", f"c{i}", "2026-01-01", "RING" if ring else f"A{i}", "RINGDEV" if ring else f"D{i}", f"P{i}"))
        lines.append((f"O{i}", 1, "A", 1, "delivered", DAY))
        if i < claim_lines:
            returns.append((f"R{i}", 1, f"O{i}", 1, 1, "item_not_received", "2026-01-12 10:00", "refunded"))
    return make_tables(SKUS, orders, lines, returns)


def test_style_signal_boundaries():
    at = F.compute_features(_share_tables(40, 3), CUTOFF, REFERENCE).styles.set_index("style_id").loc["S1"]
    assert at["linked_claim_share"] == pytest.approx(0.075) and at["targeting_signal"]          # exactly .075 with three claimants
    below = F.compute_features(_share_tables(40, 2), CUTOFF, REFERENCE).styles.set_index("style_id").loc["S1"]
    assert below["linked_claimers"] == 2 and not below["targeting_signal"]                       # two claimants never fire

    def quality_style(complaints, others):
        orders = [simple_order(f"O{i}", f"c{i}") for i in range(20)]
        lines = [(f"O{i}", 1, "A", 1, "delivered", DAY) for i in range(20)]
        reasons = ["poor_quality"] * complaints + ["wrong_size"] * others
        returns = [(f"R{i}", 1, f"O{i}", 1, 1, reason, "2026-01-12 10:00", "refunded") for i, reason in enumerate(reasons)]
        return F.compute_features(make_tables(SKUS, orders, lines, returns), CUTOFF, REFERENCE).styles.set_index("style_id").loc["S1"]

    quality = quality_style(3, 7)
    assert quality["damage_share"] == pytest.approx(0.3) and quality["quality_signal"]          # exactly 3 of 10 requested units
    under = quality_style(2, 8)
    assert under["damage_share"] == pytest.approx(0.2) and not under["quality_signal"]


def test_features_never_read_private_truth(world):
    result = F.compute_features(world.tables, world.snapshot_date, F.fit_reference([(world.tables, world.snapshot_date)]))
    assert set(result.features.columns) & {"y_abuse", "persona", "household_id", "coordination_group_id"} == set()
    summary_rate = result.features.set_index("customer_id")["raw_return_rate"]
    lines = world.tables["sales_order_line"]
    assert len(result.lines) == len(lines)                           # returns aggregated before the join: no duplicated exposure
    assert summary_rate.dropna().between(0, 1).all() and result.fallback_uses == 0


def test_features_are_built_without_private_truth_and_ignore_it(world, tmp_path, monkeypatch):
    """FEAT-AC-07: with operational inputs fixed, private truth can be absent or changed and no feature moves."""
    from arai import dataset, paths
    from arai.generator.world import write_world

    write_world(world, artifact_root=tmp_path / "artifacts", private_root=tmp_path / "private")
    reference = dataset.reference_from_worlds([world.world_id], artifact_root=tmp_path / "artifacts")
    first = dataset.build_features(world.world_id, reference, artifact_root=tmp_path / "artifacts").features
    # change every label and then remove private truth altogether: the feature path never opens it
    truth = pd.read_parquet(tmp_path / "private" / world.world_id / "customer_truth.parquet")
    truth.assign(y_abuse=1 - truth["y_abuse"]).to_parquet(tmp_path / "private" / world.world_id / "customer_truth.parquet")
    monkeypatch.setattr(paths, "PRIVATE_TRUTH_ROOT", tmp_path / "nowhere")
    second = dataset.build_features(world.world_id, reference, artifact_root=tmp_path / "artifacts").features
    pd.testing.assert_frame_equal(first, second)


# ------------------------------------------------------------------ feature contract 2.0: claims and timing in context
def context_fixture():
    """Three customers, hand-calculable.

    a: three orders (3, 1 and 1 units). Claims the whole of O1 with two different reasons on 12 Jan, and O2 on 30 Jan.
    b: no claim; one item return at half of its window and one late return of occasion wear.
    c: ten units of style S1 and one claim, so that 'other customers on the same style' is not empty for a.
    """
    skus = [("A", "S1", "Shirt", "M", 0, 30), ("B", "S2", "Dress", "M", 1, 30)]
    orders = [simple_order("O1", "a"), simple_order("O2", "a", date="2026-01-02"), simple_order("O3", "a", date="2026-01-03"),
              simple_order("O4", "b"), simple_order("O5", "b", date="2026-01-02"), simple_order("O6", "c")]
    lines = [("O1", 1, "A", 2, "delivered", DAY), ("O1", 2, "B", 1, "delivered", DAY), ("O2", 1, "A", 1, "delivered", DAY),
             ("O3", 1, "A", 1, "delivered", DAY), ("O4", 1, "A", 2, "delivered", DAY), ("O5", 1, "B", 1, "delivered", DAY),
             ("O6", 1, "A", 10, "delivered", DAY)]
    returns = [("R1", 1, "O1", 1, 2, "item_not_received", "2026-01-12 10:00", "refunded"),
               ("R1", 2, "O1", 2, 1, "wrong_item_sent", "2026-01-12 11:00", "refunded"),
               ("R2", 1, "O2", 1, 1, "item_not_received", "2026-01-30 10:00", "pending"),
               ("R3", 1, "O4", 1, 1, "didnt_suit", "2026-01-25 10:00", "refunded"),          # day 15 of 30: half of the window
               ("R4", 1, "O5", 1, 1, "changed_my_mind", "2026-02-03 10:00", "refunded"),     # day 24 of 30: late, occasion wear
               ("R5", 1, "O6", 1, 1, "missing_parts", "2026-01-13 10:00", "refunded")]
    return make_tables(skus, orders, lines, returns)


def test_claims_are_measured_against_what_was_bought_and_how_orders_were_claimed():
    reference = F.Reference(category_rate={"Shirt": 0.2, "Dress": 0.2})
    f = F.compute_features(context_fixture(), CUTOFF, reference).features.set_index("customer_id")
    a = f.loc["a"]
    assert (a["claim_lines"], a["claim_order_count"], a["claim_distinct_days"], a["max_claim_lines_per_order"]) == (3, 2, 2, 2)
    assert a["claim_order_rate"] == pytest.approx(2 / 3) and a["claim_unit_rate"] == pytest.approx(4 / 5)
    assert a["claimed_share_of_claim_orders"] == 1.0 and a["whole_order_claim_share"] == 1.0   # both claimed orders in full
    assert a["claim_day_span"] == 18 and a["claims_in_densest_fortnight"] == 2                # 30 Jan is outside 12 Jan + 14 days
    assert a["nonreceipt_share_of_claims"] == pytest.approx(2 / 3)
    assert a["multi_code_claim_orders"] == 1 and a["multi_code_claim_share"] == 0.5           # O1 has two kinds of failure
    assert a["units_per_order"] == pytest.approx(5 / 3) and a["claimed_order_size_ratio"] == pytest.approx(2 / (5 / 3))
    assert a["claim_value_ratio"] == 1.0                                                      # every unit costs the same here
    # peers exclude the customer: the other two bought 13 units and claimed 1
    expected = 5 * (1 / 13)
    assert a["claim_excess_z"] == pytest.approx((4 - expected) / expected ** 0.5)
    # style S1: others bought 12 and claimed 1; style S2: the other buyer claimed nothing; the snapshot rate is 5 of 18
    assert a["claim_style_others_rate_max"] == pytest.approx((1 / 12) / (5 / 18))
    assert a["claim_style_others_rate_mean"] == pytest.approx(((1 / 12) / (5 / 18) + 0) / 2)
    b = f.loc["b"]                                                                            # no claim: counts are zero, shares are null
    assert (b["claim_lines"], b["claim_order_count"], b["claims_in_densest_fortnight"], b["multi_code_claim_orders"]) == (0, 0, 0, 0)
    assert b["claim_order_rate"] == 0 and b["claim_unit_rate"] == 0
    assert b[["claimed_share_of_claim_orders", "claim_day_span", "nonreceipt_share_of_claims", "claim_style_others_rate_mean",
              "claim_value_ratio", "claimed_order_size_ratio"]].isna().all()


def test_timing_is_read_in_finer_grain_than_late_or_not():
    reference = F.Reference(category_rate={"Shirt": 0.2, "Dress": 0.2})
    f = F.compute_features(context_fixture(), CUTOFF, reference).features.set_index("customer_id")
    b = f.loc["b"]
    assert b["item_ratio_max"] == pytest.approx(0.8) and b["item_ratio_second"] == pytest.approx(0.5) and b["item_ratio_mean"] == pytest.approx(0.65)
    assert (b["mid_late_lines"], b["late_return_lines"], b["late_occasion_return_lines"], b["mid_or_late_occasion_lines"],
            b["item_in_window_lines"]) == (1, 1, 1, 1, 2)
    a = f.loc["a"]                                                                            # claims are never item returns
    assert a["item_in_window_lines"] == 0 and a["mid_late_lines"] == 0 and pd.isna(a["item_ratio_max"]) and pd.isna(a["item_ratio_second"])


def test_new_features_survive_a_snapshot_without_any_return():
    tables = make_tables([("A", "S1", "Shirt", "M", 0, 30)], [simple_order("O1", "a"), simple_order("O2", "b")],
                         [("O1", 1, "A", 1, "delivered", DAY), ("O2", 1, "A", 2, "delivered", DAY)])
    f = F.compute_features(tables, CUTOFF, F.Reference(category_rate={"Shirt": 0.2})).features
    assert (f[["claim_lines", "claim_distinct_days", "claims_in_densest_fortnight", "item_in_window_lines", "mid_late_lines"]] == 0).all().all()
    assert f[["item_ratio_max", "claim_day_span", "claim_excess_z"]].isna().all().all() and f["units_per_order"].tolist() == [1.0, 2.0]
