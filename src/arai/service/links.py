"""The links an analyst is shown between accounts (decision AM-79): the evidence graph.

The model's features are computed on the graph of the three order identifiers (address, device, payment method), as the
bundle of EXP-20261005-04 was trained and tested; `arai.features` is part of that bundle's code and is not touched. What
the analyst sees is wider where the snapshot carries contact details (data contract 1.2): the phone number of an account
and the mailbox behind its email address are two more identifier types, and two accounts are linked when they share any
two of the five. Every link of the three-identifier graph is therefore a link here, and a snapshot without contact
columns gives exactly the three-identifier graph. The text of a phone number or an address is never read for anything
but equality, and nothing here reaches a score, a rank or a selection.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from arai import features as F
from arai.operational import email_key

ACCOUNT_IDENTIFIERS = {"phone_id": "phone", "email_id": "email"}      # identifier type -> customer_master column


def phone_key(phone) -> str | None:
    """The last ten digits of a phone number, so the same number written with or without a country code or a leading
    zero is one value. None for a missing value, one too short to be a number, or one repeated digit: a placeholder such
    as "NA" or "0000000000" must not link accounts."""
    if not isinstance(phone, str):
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    return digits if len(digits) >= 7 and len(set(digits)) > 1 else None


def identifier_frames(orders: pd.DataFrame, customers: pd.DataFrame | None = None) -> dict:
    """identifier type -> distinct (customer_id, value) rows: the three identifiers of each order and, where
    customer_master carries them, the account's phone number and mailbox (aliases of one mailbox are one value)."""
    frames = {kind: orders[["customer_id", kind]].dropna().drop_duplicates() for kind in F.IDENTIFIERS}
    if customers is not None:
        for kind, column in ACCOUNT_IDENTIFIERS.items():
            if column in customers.columns:
                values = customers[column].map(email_key if column == "email" else phone_key)
                frame = pd.DataFrame({"customer_id": customers["customer_id"].to_numpy(), kind: values.to_numpy()})
                frames[kind] = frame.dropna().drop_duplicates()
    return frames


def build_graph(orders: pd.DataFrame, customers: pd.DataFrame | None = None) -> F.Graph:
    """The evidence graph, with the rules of `features.build_graph`: a value shared by more than 25 accounts is dropped,
    an edge needs at least two shared identifier types, several shared values of one type count once."""
    shared, fanout, dropped = {}, {}, 0
    for kind, frame in identifier_frames(orders, customers).items():
        accounts = frame.groupby(kind)["customer_id"].unique()
        sizes = accounts.map(len)
        fanout[kind] = sizes
        dropped += int((sizes > F.FANOUT_CAP).sum())
        for value, members in accounts[(sizes >= 2) & (sizes <= F.FANOUT_CAP)].items():
            for pair in combinations(sorted(members), 2):
                shared.setdefault(pair, {}).setdefault(kind, []).append(len(members))
    rows, neighbours = [], {}
    for (a, b), kinds in shared.items():
        if len(kinds) < 2:
            continue
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)
        rows.append({"customer_a": a, "customer_b": b, "shared_types": sorted(k.replace("_id", "") for k in kinds),
                     "shared_value_count": sum(len(v) for v in kinds.values()),
                     "max_value_fanout": max(max(v) for v in kinds.values()),
                     "weight": sum(1.0 / np.log2(1 + min(v)) for v in kinds.values())})
    edges = pd.DataFrame(rows, columns=["customer_a", "customer_b", "shared_types", "shared_value_count", "max_value_fanout", "weight"])
    return F.Graph(edges=edges, neighbours=neighbours, fanout=fanout, dropped_values=dropped)


def link_measures(graph: F.Graph, orders: pd.DataFrame, customers: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """The two evidence-only link measures over the evidence graph, per customer: the largest number of accounts using one
    of the customer's identifiers (capped like the feature) and the number of accounts linked to the customer."""
    frames = identifier_frames(orders, customers)
    own = pd.concat([frame.assign(fanout=frame[kind].map(graph.fanout[kind]))[["customer_id", "fanout"]] for kind, frame in frames.items()])
    out = pd.DataFrame(index=index)
    out["max_identifier_fanout"] = own.groupby("customer_id")["fanout"].max().clip(upper=F.FANOUT_CAP).reindex(index, fill_value=0).astype(int)
    out["supported_neighbor_count"] = pd.Series({c: len(n) for c, n in graph.neighbours.items()}, dtype=float) \
        .reindex(index, fill_value=0).astype(int)
    return out
