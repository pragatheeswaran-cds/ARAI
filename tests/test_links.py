"""The evidence graph (decision AM-79): what an analyst is shown, beside what the model reads."""
import pandas as pd

from arai import features as F
from arai.service import links, scoring


def _orders(rows):
    return pd.DataFrame(rows, columns=["customer_id", "address_id", "device_id", "payment_id"])


def _accounts(rows):
    return pd.DataFrame(rows, columns=["customer_id", "phone", "email"])


def _pairs(graph):
    return {(e.customer_a, e.customer_b) for e in graph.edges.itertuples()}


def test_a_phone_and_a_mailbox_are_identifier_types_and_any_two_of_five_make_a_link():
    orders = _orders([("A", "ad1", "de1", "pa1"), ("B", "ad2", "de2", "pa2"), ("C", "ad3", "de3", "pa3"),
                      ("D", "ad3", "de4", "pa4"), ("E", "ad5", "de5", "pa5"), ("F", "ad6", "de6", "pa6")])
    accounts = _accounts([("A", "+91 50000 00001", "g1+1@example.com"), ("B", "050000 00001", "G1+2@Example.com"),
                          ("C", "+91 50000 00002", "c@example.com"), ("D", "+91 50000 00002", "d@example.com"),
                          ("E", "+91 50000 00003", "e@example.com"), ("F", "+91 50000 00003", "f@example.com")])
    graph = links.build_graph(orders, accounts)
    edges = {(e.customer_a, e.customer_b): e.shared_types for e in graph.edges.itertuples()}
    # A and B: one number written two ways and aliases of one mailbox, no order identifier in common. C and D: an address
    # and a phone. E and F share a phone alone: no link, which keeps a recycled number or a family phone from linking.
    assert edges == {("A", "B"): ["email", "phone"], ("C", "D"): ["address", "phone"]}
    assert graph.neighbours == {"A": {"B"}, "B": {"A"}, "C": {"D"}, "D": {"C"}}
    assert set(graph.fanout) == {"address_id", "device_id", "payment_id", "phone_id", "email_id"}
    measures = links.link_measures(graph, orders, accounts, pd.Index(list("ABCDEF"), name="customer_id"))
    assert measures["supported_neighbor_count"].to_dict() == {"A": 1, "B": 1, "C": 1, "D": 1, "E": 0, "F": 0}
    assert measures["max_identifier_fanout"].to_dict() == {"A": 2, "B": 2, "C": 2, "D": 2, "E": 2, "F": 2}


def test_placeholders_and_missing_values_never_link_accounts():
    assert links.phone_key("+91 50080 85758") == links.phone_key("05008085758") == links.phone_key("5008085758") == "5008085758"
    assert [links.phone_key(v) for v in (None, "", "NA", "0", "0000000000", "12345")] == [None] * 6
    orders = _orders([("A", "ad1", "de1", "pa1"), ("B", "ad1", "de2", "pa2"), ("C", "ad1", "de3", "pa3")])
    accounts = _accounts([("A", "0000000000", None), ("B", "0000000000", "not an address"), ("C", None, None)])
    assert len(links.build_graph(orders, accounts).edges) == 0                        # an address, and placeholders: one type only


def test_without_contact_columns_the_evidence_graph_is_the_models_graph(world):
    orders, master = world.tables["sales_order"], world.tables["customer_master"]
    model = F.build_graph(orders)
    for customers in (None, master.drop(columns=["phone", "email"])):
        shown = links.build_graph(orders, customers)
        pd.testing.assert_frame_equal(shown.edges, model.edges)
        assert shown.neighbours == model.neighbours and shown.dropped_values == model.dropped_values
    wider = links.build_graph(orders, master)
    assert _pairs(model) < _pairs(wider)                                              # every link stays, and some are new
    kept = wider.edges.set_index(["customer_a", "customer_b"]).loc[sorted(_pairs(model))]
    assert (kept["shared_types"].map(lambda types: len(set(types) & {"address", "device", "payment"})) >= 2).all()
    new = wider.edges.set_index(["customer_a", "customer_b"]).loc[sorted(_pairs(wider) - _pairs(model))]
    assert new["shared_types"].map(lambda types: bool({"phone", "email"} & set(types))).all()
    # in a generated world a new link joins members of one household or of one coordination group, never strangers
    truth = world.truth["customer_truth"].set_index("customer_id")
    same = lambda a, b, column: pd.notna(truth.loc[a, column]) and truth.loc[a, column] == truth.loc[b, column]
    assert all(same(a, b, "household_id") or same(a, b, "coordination_group_id") for a, b in _pairs(wider) - _pairs(model))


def test_the_kind_rule_is_unchanged_on_order_identifiers_and_reads_the_shape_of_contact_edges():
    kind = scoring.community_kind
    household = [{"types": ["address", "device"]}]
    assert kind(household, selected=1, matched=1, share_positive=True) == "household"       # AM-66: one matching claim is not enough
    assert kind(household, selected=2, matched=0, share_positive=False) == "ring"
    assert kind([{"types": ["address", "payment"]}], selected=1, matched=1, share_positive=False) == "ring"
    # a family that shares an address and a phone has the shape of a household, as before
    assert kind([{"types": ["address", "phone"]}], selected=1, matched=1, share_positive=True) == "household"
    # accounts at different addresses joined by a phone and a mailbox do not live together: the first rule applies
    apart = [{"types": ["email", "phone"]}]
    assert kind(apart, selected=1, matched=1, share_positive=False) == "ring"
    assert kind(apart, selected=1, matched=0, share_positive=False) == "household"
