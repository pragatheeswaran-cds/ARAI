# Community kind rule against relationship truth (2026-10-15)

Frontend data plan WP1, decision D3. The rule that labels a group of linked accounts `ring` or `household` at
scoring time reads observed evidence only. Before shipping it, the plan asked for an offline check against the
generator's private `relationship_truth` on two training worlds, with the confusion recorded. This is that record.

## What was checked

`scripts/community_check.py --seed 5101 5102` generates the two worlds, builds the features and the supported
relationship graph exactly as the service does, groups the supported edges into communities with
`arai.service.scoring._communities`, and compares each community's kind with the truth:

- **Rule (observed only).** `ring` when any edge of the community has a coordinated claim match (both accounts
  claimed on the same style within 7 days), or two or more members are selected for review, or a member has a
  coordinated claim share above zero; `household` otherwise.
- **Truth (private, read only here).** A community is `coordination` when two or more of its members share a
  generated coordination group; otherwise `household` when they share a generated household; otherwise
  `shared_location`; otherwise `unrelated`.
- **Selected for review** in this check is the top 5% of the raw return rate (the baseline ranking), because the
  check runs without a model bundle. In a real run it is the model's queue, so the second ring condition can fire
  on a different set.

Communities are connected components of the supported edges. A component of thirteen or more members is split by
Louvain on the edge weight with a fixed seed; one component in W5102 was large enough and split into three.

## Result

| World | Customers | Supported edges | Communities | Sizes | Generated coordination groups | Communities holding a coordination pair |
|---|---|---|---|---|---|---|
| W5101 | 10,000 | 1,050 | 249 (all components) | 2: 95, 3: 69, 4: 41, 5: 26, 6: 9, 7: 5, 8: 1, 9: 2, 10: 1 | 53 | 46 |
| W5102 | 10,000 | 1,103 | 264 (261 components, 3 Louvain parts) | 2: 95, 3: 76, 4: 49, 5: 32, 6: 10, 8: 2 | 57 | 43 |

Confusion, both worlds pooled (rows: what the rule says; columns: what the truth says):

| Rule says | coordination | household | shared_location | unrelated |
|---|---|---|---|---|
| ring | 55 | 11 | 0 | 0 |
| household | 34 | 413 | 0 | 0 |

- Of the 66 communities the rule calls a ring, 55 hold a generated coordination pair (83%).
- Of the 89 communities that hold a coordination pair, the rule calls 55 a ring (62%). The 34 it calls a
  household are coordination groups whose members had not yet claimed on the same style within seven days and
  had at most one member in the top 5% by raw return rate.
- No community was `unrelated` or `shared_location` only: a supported edge (two shared identifier types, values
  shared by more than 25 accounts dropped) is always a generated household or coordination group in these worlds.
- 11 households are called rings. Each had two members in the top 5% by raw return rate, which is the one ring
  condition that does not read a claim; against the model's queue this condition fires on a different set.

## What this means for the demo

The rule is a useful observable label, not a detector: a ring label is right about five times in six, and about
a third of the generated coordination groups are not labelled, because nothing observable yet separates them from
a household. The UI words it as "linked accounts, ring pattern" or "linked accounts, household pattern", never as
a finding about a member. Membership of any group is evidence about a relationship, not guilt. Truth is never read
at scoring time; this check is the only place the two are joined.
