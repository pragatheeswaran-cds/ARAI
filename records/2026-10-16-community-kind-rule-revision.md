# Community kind rule, revised (2026-10-16)

Decision D3 as first recorded (AM-57, checked in `records/2026-10-15-community-kind-check.md`) calls a group of
linked accounts a `ring` on one coordinated claim match, two or more members selected for review, or a member with a
coordinated claim share above zero. The functional review of 15 Oct 2026
(`reports/qa/2026-10-15/functional-review.md`, finding 1) found that on W5401 four of the 35 rings held no abuser:
each was one household sharing an address and a device, whose members had genuine carrier failures and claimed "not
received" on the same style within a week. Four of the five honest customers marked Escalate came from them. This
record is the offline check behind the revision (AM-66).

## The revision

Where some edge of the community shares a payment instrument, the first rule stands. Where every edge shares only an
address and a device, the shape of a household, a community is a `ring` only with **two or more coordinated claim
matches or two or more members selected for review**. The rule still reads observed evidence only
(`arai.service.scoring.community_kind`). It changes the community's kind and therefore the gate outcome of its
selected members (Escalate or Hold, a presentation rule); no score, rank or selection changes.

## Method

`scripts/community_rule_check.py` scores each world with the active model bundle (`m-4faf6b8a2475c708f15608b1`), so
"selected for review" is the model's real queue, recomputes the first rule from the scored communities and the
members' coordinated claim shares, and compares both rules with the generator's relationship truth: a community is
`coordination` when two or more members share a generated coordination group, otherwise `household` when they share a
household. It also counts rings that hold no abuser at all. Truth is read only by this script.

```
uv run python scripts/community_rule_check.py --world W5201 W5202 W5203 W5204 W5205 W5401
```

The five validation worlds did not inform the revision; W5401 is where the finding was made.

## Result

| World | Communities | Rings, first rule (coordination / household / no abuser) | Rings, revised (coordination / household / no abuser) | Changed |
|---|---|---|---|---|
| W5201 | 259 | 37 (29 / 8 / 6) | 33 (29 / 4 / 4) | 4 |
| W5202 | 256 | 36 (33 / 3 / 2) | 34 (33 / 1 / 0) | 2 |
| W5203 | 241 | 30 (30 / 0 / 0) | 29 (29 / 0 / 0) | 1 |
| W5204 | 250 | 38 (34 / 4 / 2) | 36 (34 / 2 / 1) | 2 |
| W5205 | 229 | 28 (27 / 1 / 1) | 27 (27 / 0 / 0) | 1 |
| W5401 | 250 | 35 (30 / 5 / 4) | 31 (30 / 1 / 0) | 4 |
| **Pooled** | 1,485 | **204 (183 / 21 / 15)** | **190 (182 / 8 / 5)** | 14 |

- Rings that hold a coordination group: 89.7% of rings under the first rule (183 of 204), 95.8% under the revision
  (182 of 190).
- Rings with no abuser in them: 15 under the first rule, 5 under the revision.
- On the five validation worlds alone the revision changes 10 communities: 9 are households in truth (6 with no
  abuser, 3 with one abuser among their members) and 1 is a coordination group (W5203-L9A02511A4ABF, five members,
  two abusers, one in the queue). That one is the cost: its queued member moves from Escalate to Hold and stays in the
  queue; the group still shows on the Linked accounts tab with its edges and its one matching claim.
- On W5401 the revision changes exactly the four communities of the finding (W5401-LB468D504E82F,
  W5401-L1B37F7382819, W5401-L8837EFCAF00B, W5401-LC36C354B2FBA), all households with no abuser.

Every changed community has edges of address and device only, one coordinated claim match, and at most one member in
the queue, which is what the revision targets.

## What stays as it was

Communities sharing a payment instrument keep the first rule; 29 of the 31 true rings on W5401 share one. Membership,
community ids, edges, match counts and every customer's score, rank and selection are unchanged. Runs scored before
the revision keep the kinds they were scored with; a new run of the same world carries the revised kinds.
