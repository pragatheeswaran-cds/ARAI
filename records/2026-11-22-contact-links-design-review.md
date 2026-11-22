# Independent review of the contact-links experiment, before any world existed

Date: 2026-11-22
Branch: `penpot-implementation`

## What was reviewed

The owner chose to use a shared phone number or mailbox as a ring signal and approved a new experiment for it
(decisions E1 to E8 in `records/2026-11-21-penpot-coverage-checklist.md`): `EXP-20261122-05`, seeds 6101 to 6514,
a relationship graph of five identifier types (any two shared make a link), a sixth gate leg for honest household
members who carry their household's shared phone or mailbox, and stress worlds that vary how often groups share.

The contract and the code were written and then reviewed by an independent critic before any world was generated
and before anything was committed. The reviewer read the uncommitted changes and measured on in-memory worlds
(seed 2001 at 1,000 customers; seeds 2002 and 2003 at 10,000). Nothing was written to disk by the review.

## Findings

| # | Finding | Severity given | What was done |
|---|---|---|---|
| 1 | The treatment is almost null. One of the 43 model features reads the graph (`coordinated_claim_share`); the other two graph readers are evidence only. On a 10,000-customer world the wider graph changes that feature for 10 of 5,701 eligible customers (9 abusers, 1 honest). The effect on precision at the 5 percent budget is well under one point, less than the difference between two sets of seeds, and the contract had no control arm | Fix before generating | The experiment was withdrawn by the owner (decision E9). See "Decision" below |
| 2 | The contract's expectation said three features read the graph. It is one model feature and two evidence-only measures | Fix before commit | The contract was never committed. AM-79 states the correct count |
| 3 | The sixth leg was 96 percent a subset of `benign_household` (181 of 190 on seed 2002) and mostly held people the wider graph does not touch: 60 of 190 gain a link | Fix before generating | No sixth leg exists; the gate of experiment 4 is unchanged |
| 4 | The contact stress worlds were three different seeds compared with nothing paired, varying an effect that touches 10 to 17 customers a world | Fix or drop the claim | No stress worlds were created |
| 5 | Nothing tied the graph used at serving time to the bundle's feature contract: the experiment 4 bundle would have scored a snapshot with contact columns on a graph it was not trained on | Fix before publish or merge | The model's graph stays in `features.py`, untouched; the wider graph is built in `service/links.py` after the scores exist, and a test requires every score, rank, selection and model input to be equal with and without the contact columns |
| 6 | Accounts in both a household and a ring (34 per 10,000): `contact_truth.used_shared_value` stayed true for a value the account no longer carried (5 of 525 rows), and a ring's region overwrote household regions (14 of 333 households) | Fix before generating | Fixed in the generator, with a test |
| 7 | Recycled phone numbers never produced a link, and no new link joined unrelated accounts: every new link was inside a true household or ring. The donor draw skipped the last account and could draw the account itself | Note | The donor draw is fixed. The absence of honest links between strangers is recorded as a limit of the simulator |
| 8 | With the kind rule unchanged, a ring linked only by a phone and a mailbox would mostly be labelled a household | Note | The kind rule now reads the shape of an edge: an edge that shares no address is not the shape of a household. It is unchanged for every snapshot without contact details |
| 9 | A development world, `W5601N10000`, was written into experiment 4's data folder | Note | It is the world the runbook's section 4.2 tells a reader to generate; it is unregistered and is left there as that example |
| 10 | Phone numbers were compared as raw text, so one number written two ways would not match and a placeholder shared by a few accounts would count as a link; `email_key("+x@d")` gave `@d` | Note | The evidence graph keys a phone by its last ten digits and ignores values too short or made of one repeated digit; `email_key` returns nothing for an empty local part |

## What the reviewer measured about the graph itself

| Seed (10,000 customers) | Links, three types | New links | Of which household | Of which ring | Of which unrelated | Ring members linked | Abusers linked |
|---|---|---|---|---|---|---|---|
| 2002 | 1,043 | 116 | 67 | 49 | 0 | 173 to 212 of 251 | 152 to 182 of 360 |
| 2003 | 1,087 | 83 | 51 | 32 | 0 | 189 to 211 of 253 | 158 to 173 of 357 |

So the wider graph matters for what an analyst sees: 22 to 39 more ring members a world become linked to their ring.
It hardly matters for the model, which reads one feature from it.

## Checked and found sound

- No label leakage: only equality between accounts is read, and no phone, email or region column reaches a feature.
  The share of linked accounts that are abusers is 0.19 to 0.20 with either graph.
- Every link of the three-type graph is kept. The fan-out cap of 25 applies to phones and mailboxes; the largest
  fan-out seen was 5 for a phone and 6 for a mailbox.
- Generation is deterministic, missing values are dropped, and `customer_master` has one row per customer.
- The retired seeds of experiment 4 were complete, and no path read experiment 4's data.

## Decision

Asked how to proceed with these findings, the owner chose to show the links and keep the model (decision E9): no
experiment 5. The experiment 4 model keeps scoring on the three order identifiers exactly as it was tested, and the
links through a phone or a mailbox are added to what analysts see: linked accounts, groups, rings, the Critical
level and the Network Graph (AM-79, API contract 3.3.0).

Left open, for a later decision: a paired control run that would measure the small effect on the model, and new
model features built on contact links, which would need an exploration and then an experiment of their own.
