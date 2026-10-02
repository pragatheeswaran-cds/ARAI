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


REFERENCE = F.Reference(category_rate={"Shirt": 0.2, "Jeans": 0.2, "Jacket": 0.15},
                        latency_median={"Shirt": 5.0, "Jeans": 5.0, "Jacket": 5.0},
                        latency_iqr={"Shirt": 4.0, "Jeans": 4.0, "Jacket": 0.0})


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
    assert len(order) == 18 and list(result.features.columns[1:19]) == order


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


def _wardrobing(latency_z, ratio, occasion, discretionary, bracketing, has_request=True):
    features = pd.DataFrame({"customer_id": ["c1"], "median_window_ratio": [ratio], "occasion_return_share": [occasion],
                             "discretionary_share": [discretionary], "bracketing_share": [bracketing]})
    days = 5.0 + 4.0 * latency_z                                  # reference: median 5 days, IQR 4 days for shirts
    requests = pd.DataFrame({"customer_id": ["c1"] if has_request else [], "category": ["Shirt"] if has_request else [],
                             "capped_days": [days] if has_request else []})
    return F.wardrobing_indicator(features, requests, REFERENCE).iloc[0]


def test_wardrobing_bands_use_integer_points_and_need_a_timing_signal():
    assert _wardrobing(1.0, 0.2, 0.9, 0.1, 0.5)["indicator_score"] == 45         # 30 + 15: the sum floating point missed
    assert _wardrobing(1.0, 0.2, 0.9, 0.1, 0.5)["status"] == "possible"
    assert _wardrobing(1.0, 0.8, 0.1, 0.1, 0.0)["indicator_score"] == 65 and _wardrobing(1.0, 0.8, 0.1, 0.1, 0.0)["status"] == "elevated"
    no_timing = _wardrobing(0.0, 0.2, 0.9, 0.9, 0.0)                              # 15 + 20 + 10 = 45 points, no timing signal
    assert no_timing["indicator_score"] == 45 and no_timing["status"] == "no_elevated_signal"
    assert _wardrobing(0.99, 0.74, 0.9, 0.9, 0.0)["status"] == "no_elevated_signal"
    assert _wardrobing(1.0, 0.2, 0.9, 0.1, 0.5, has_request=False)["status"] == "insufficient_evidence"
    incomplete = _wardrobing(1.0, 0.8, 0.9, 0.9, np.nan)
    assert incomplete["status"] == "incomplete" and pd.isna(incomplete["indicator_score"])


def test_wardrobing_latency_uses_capped_days_and_a_floor_on_the_spread():
    features = pd.DataFrame({"customer_id": ["c1"], "median_window_ratio": [0.1], "occasion_return_share": [0.0],
                             "discretionary_share": [0.0], "bracketing_share": [0.5]})
    jacket = pd.DataFrame({"customer_id": ["c1"], "category": ["Jacket"], "capped_days": [6.0]})     # IQR 0 -> divide by one day
    assert F.wardrobing_indicator(features, jacket, REFERENCE).iloc[0]["latency_z"] == pytest.approx(1.0)
    unknown = pd.DataFrame({"customer_id": ["c1"], "category": ["Dress"], "capped_days": [6.0]})     # no training baseline
    assert F.wardrobing_indicator(features, unknown, REFERENCE).iloc[0]["status"] == "incomplete"
    late = make_tables(SKUS, [simple_order("O1", "c1")], [("O1", 1, "A", 1, "delivered", DAY)],
                       [("R1", 1, "O1", 1, 1, "wrong_size", "2026-06-01 10:00", "rejected")])
    request = F.compute_features(late, CUTOFF, REFERENCE).requests.iloc[0]
    assert request["window_ratio"] == 2.0 and request["capped_days"] == 60                # capped at twice the 30-day window


def test_features_never_read_private_truth(world):
    result = F.compute_features(world.tables, world.snapshot_date, F.fit_reference([(world.tables, world.snapshot_date)]))
    assert set(result.features.columns) & {"y_abuse", "persona", "household_id", "coordination_group_id"} == set()
    summary_rate = result.features.set_index("customer_id")["raw_return_rate"]
    lines = world.tables["sales_order_line"]
    assert len(result.lines) == len(lines)                           # returns aggregated before the join: no duplicated exposure
    assert summary_rate.dropna().between(0, 1).all() and result.fallback_uses == 0
