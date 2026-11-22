"""Households, coordination groups, shared locations and the identifiers each order actually uses.

Group membership is private. The only thing the operational data sees is which address, device and payment
identifier an order carried, so assigned sharing and observed links legitimately differ.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from arai.generator.context import Context
from arai.operational import email_key  # noqa: F401  (the mailbox key lives with the operational data; importable from here)
from arai.rng import stream, token

TYPES = ("address", "device", "payment")
ID_LETTER = {"address": "A", "device": "D", "payment": "P"}
# final-spec component 02: probability that a group shares each identifier type
SHARE_PROBABILITY = {
    "household": {"address": 1.0, "device": 0.7, "payment": 0.3},
    "coordination": {"address": 0.4, "device": 0.8, "payment": 0.7},
    "shared_location": {"address": 1.0, "device": 0.0, "payment": 0.0},
}
USAGE_RANGE = {"household": (0.6, 0.9), "coordination": (0.7, 1.0)}
# account-level contact details (data contract 1.2, AM-78): one region, one email and one phone per account. A group may
# share a phone number or an email mailbox (members then carry aliases of it: handle+1@, handle+2@); a few unrelated
# accounts carry a recycled phone number. Membership stays private; only the three columns are operational.
CONTACT_TYPES = ("phone", "email")
CONTACT_SHARE_PROBABILITY = {"household": {"phone": 0.30, "email": 0.05}, "coordination": {"phone": 0.60, "email": 0.50}}
RECYCLED_PHONE_SHARE = 0.005
REGIONS = ("north", "south", "west", "east", "central", "northeast")
REGION_WEIGHTS = (0.28, 0.27, 0.22, 0.13, 0.07, 0.03)
COORDINATION_SAME_REGION = 0.7
EMAIL_DOMAIN = "example.com"                      # reserved for documentation: never a real mailbox
CONTACT_TRUTH_COLUMNS = ["world_id", "group_id", "customer_id", "identifier_type", "group_type", "shared_value", "used_shared_value"]


@dataclass
class Relationships:
    own: dict                      # type -> list (per customer) of that customer's own identifier values
    offers: list                   # per customer: {type: [(shared_value, usage_probability), ...]}
    groups: dict                   # group_id -> {"type": ..., "members": [customer index, ...]}
    truth: pd.DataFrame            # relationship_truth rows
    contact: pd.DataFrame = field(repr=False, default=None)        # customer_id, region, email, phone (operational)
    contact_truth: pd.DataFrame = field(repr=False, default=None)  # which group offered which shared phone or mailbox
    household_id: np.ndarray = field(repr=False, default=None)
    coordination_group_id: np.ndarray = field(repr=False, default=None)
    shared_location_id: np.ndarray = field(repr=False, default=None)
    primary_probability: float = 0.8

    def draw_identifiers(self, rng, customer: int, n_orders: int) -> dict:
        """Identifier used on each of a customer's orders, per type.

        Each membership offering a type is used independently with the member's sampled probability. If several
        offer on the same order, one is chosen with equal chance. If none does, the customer's own value is used.
        """
        used = {}
        for kind in TYPES:
            own = self.own[kind][customer]
            pick_primary = rng.random(n_orders) < self.primary_probability
            values = np.where(pick_primary | (len(own) == 1), own[0], own[-1]).astype(object)
            offered = self.offers[customer].get(kind, [])
            if offered:
                on = np.column_stack([rng.random(n_orders) < p for _, p in offered])
                priority = np.where(on, rng.random(on.shape), -1.0)
                choice = priority.argmax(axis=1)
                shared = np.array([value for value, _ in offered], dtype=object)[choice]
                values = np.where(on.any(axis=1), shared, values)
            used[kind] = values
        return used


def _partition(rng, members: np.ndarray, lo: int, hi: int) -> list:
    """Cut members into consecutive groups of size lo..hi; a remainder smaller than lo stays ungrouped."""
    groups, start = [], 0
    while len(members) - start >= lo:
        size = min(int(rng.integers(lo, hi + 1)), len(members) - start)
        groups.append(members[start:start + size])
        start += size
    return groups


def build_relationships(ctx: Context, profiles: pd.DataFrame) -> Relationships:
    s, n, seed, world = ctx.s, ctx.n, ctx.seed, ctx.world_id
    accepted, impl = s.accepted, s.impl
    rng = stream(seed, "world", "relationships")
    ids = ctx.customer_ids

    def own_values(kind: str, second_probability: float) -> list:
        second = rng.random(n) < second_probability
        return [[f"{world}-{ID_LETTER[kind]}{token(seed, ids[i], kind + ':' + str(k))}" for k in range(1 + second[i])]
                for i in range(n)]

    own = {"address": own_values("address", 0.0),
           "device": own_values("device", impl["second_device_probability"]),
           "payment": own_values("payment", impl["second_payment_probability"])}

    household_share = accepted["household_member_share"] * s.overrides.get("household_share_scale", 1.0)
    household_members = rng.permutation(n)[:int(round(min(1.0, household_share) * n))]
    propensity = np.flatnonzero(profiles["claim_propensity"].to_numpy() | profiles["temporary_use_propensity"].to_numpy())
    coordination_members = rng.permutation(propensity)[:int(round(accepted["grouped_propensity_share"] * len(propensity)))]
    lo, hi = accepted["shared_location_size"]
    location_count = int(round(rng.uniform(*accepted["shared_location_share"]) * n))
    if location_count < lo:
        location_count = lo if n >= impl["shared_location_min_world"] else 0
    location_members = rng.permutation(n)[:location_count]

    plans = [("household", _partition(rng, household_members, *accepted["household_size"])),
             ("coordination", _partition(rng, coordination_members, *accepted["abuse_group_size"])),
             ("shared_location", _partition(rng, location_members, lo, hi))]
    usage_range = dict(USAGE_RANGE, shared_location=tuple(impl["shared_location_usage"]))

    offers = [dict() for _ in range(n)]
    groups, rows = {}, []
    labels = {kind: np.full(n, None, dtype=object) for kind, _ in plans}
    for kind, partition in plans:
        for k, members in enumerate(partition):
            group_id = f"{world}-G{token(seed, kind + ':' + str(k), 'group')}"
            group_rng = stream(seed, group_id, "sharing")
            groups[group_id] = {"type": kind, "members": [int(i) for i in members]}
            labels[kind][members] = group_id
            for identifier in TYPES:
                if group_rng.random() >= SHARE_PROBABILITY[kind][identifier]:
                    continue
                value = f"{world}-{ID_LETTER[identifier]}{token(seed, group_id, identifier)}"
                for i in members:
                    probability = float(group_rng.uniform(*usage_range[kind]))
                    offers[i].setdefault(identifier, []).append((value, probability))
                    rows.append((world, group_id, ids[i], identifier, kind, value, probability))
    truth = pd.DataFrame(rows, columns=["world_id", "group_id", "customer_id", "identifier_type", "group_type",
                                        "shared_value", "sampled_usage_probability"])
    contact, contact_truth = build_contact(ctx, groups)
    return Relationships(own=own, offers=offers, groups=groups, truth=truth, contact=contact, contact_truth=contact_truth,
                         household_id=labels["household"], coordination_group_id=labels["coordination"],
                         shared_location_id=labels["shared_location"],
                         primary_probability=impl["primary_identifier_probability"])


def phone_number(value: int) -> str:
    """A synthetic Indian-format number. Real mobile numbers start with 6 to 9; these start with 5, so none is a real one."""
    digits = f"5{int(value) % 10 ** 9:09d}"
    return f"+91 {digits[:5]} {digits[5:]}"


def build_contact(ctx: Context, groups: dict) -> tuple:
    """(contact, contact_truth): the region, email and phone of every account, and the private record of what was shared.

    Every draw comes from streams named for contact details, so adding them changes no other part of a world. A household
    lives in one region; a coordination group mostly does. A group shares a phone or a mailbox with the probabilities above,
    and each member then uses the shared one with a sampled probability, as with the order identifiers.
    """
    n, seed, world, ids = ctx.n, ctx.seed, ctx.world_id, ctx.customer_ids
    rng = stream(seed, "world", "contact")
    region = rng.choice(np.array(REGIONS, dtype=object), size=n, p=np.array(REGION_WEIGHTS))
    phone = np.array([phone_number(v) for v in rng.integers(0, 10 ** 9, size=n)], dtype=object)
    email = np.array([f"c{token(seed, ids[i], 'email').lower()}@{EMAIL_DOMAIN}" for i in range(n)], dtype=object)
    recycled = np.flatnonzero(rng.random(n) < RECYCLED_PHONE_SHARE)
    if n > 1:
        for i in recycled:                                  # a number that once belonged to another account, any but its own
            donor = int(rng.integers(0, n - 1))
            phone[i] = phone[donor + (donor >= i)]
    in_household = {i for group in groups.values() if group["type"] == "household" for i in group["members"]}
    rows = []
    for group_id, group in groups.items():
        kind, members = group["type"], group["members"]
        if kind not in CONTACT_SHARE_PROBABILITY:
            continue
        group_rng = stream(seed, group_id, "contact")
        if kind == "household":
            region[members] = region[members[0]]
        elif group_rng.random() < COORDINATION_SAME_REGION:
            movable = [i for i in members if i not in in_household]      # a ring member keeps the region of their household
            region[movable] = region[members[0]]
        for identifier in CONTACT_TYPES:
            if group_rng.random() >= CONTACT_SHARE_PROBABILITY[kind][identifier]:
                continue
            if identifier == "phone":
                shared = phone_number(int(group_rng.integers(0, 10 ** 9)))
            else:
                shared = f"g{token(seed, group_id, 'email').lower()}@{EMAIL_DOMAIN}"
            for position, i in enumerate(members):
                used = bool(group_rng.random() < group_rng.uniform(*USAGE_RANGE[kind]))
                if used and identifier == "phone":
                    phone[i] = shared
                elif used:
                    local, _, domain = shared.partition("@")
                    email[i] = f"{local}+{position + 1}@{domain}"
                rows.append((world, group_id, ids[i], identifier, kind, shared, used))
    contact = pd.DataFrame({"customer_id": ids, "region": region, "email": email, "phone": phone})
    # an account in a household and in a ring can be offered two shared values of one type and carries the last one it
    # took. The record says what each account carries in the end, not what it took along the way.
    at = {customer: i for i, customer in enumerate(ids)}
    rows = [(w, g, customer, identifier, kind, shared,
             bool((phone[at[customer]] if identifier == "phone" else email_key(email[at[customer]])) == shared))
            for w, g, customer, identifier, kind, shared, _ in rows]
    return contact, pd.DataFrame(rows, columns=CONTACT_TRUTH_COLUMNS)
