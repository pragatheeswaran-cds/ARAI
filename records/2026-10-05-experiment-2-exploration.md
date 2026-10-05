# Exploration for the second experiment: a gate leg for honest repeat claimants (2026-10-05)

Branch `v3`. Decisions AM-45 (the 0.75-0.85 target stays open) and AM-46 (a new experiment with a fourth gate leg).
This note records what was measured before the new experiment's contract is written. Nothing here is a result:
it is development work on the ten existing training worlds (W2101-W2110), out of fold with the five registered
folds, at the 5% budget, with the `hgb_leaf15` settings. No validation or test world was read and nothing was
written under `data/`.

The fourth leg, as measured here: honest eligible customers with two or more genuinely failed units (the
"repeat genuine claimant" group of the error account, 4,015 customers over the ten worlds). The return-rate rule
sends 6.7% of them for review; a candidate passes the leg if it sends no more.

## 1. The published feature set cannot pass the leg

| Model | Precision | Repeat claimants reviewed | Four-leg gate |
|---|---|---|---|
| Return-rate rule | 0.237 | 6.7% | reference |
| Current 17 features | 0.694 | 15.8% | fails the new leg |
| 15 features, claim features removed | 0.552 | 10.9% | fails the new leg |

Removing the claim features does not help: without them the model leans on return rate and still reviews this
group more often than the rule.

## 2. New claim features raise precision by five points

The 17 features describe claims only as a share of what a customer asked back. A customer who returns nothing
and has two genuine failures has a claim share of 100%. Two families were added, computed from operational
tables only:

- **Claim rates**: claim lines and claimed orders as counts, claimed orders per delivered order, claimed units per
  delivered unit, and the excess of claimed units over what the world's own claim rate predicts for the
  customer's volume.
- **Claim shape**: the share of a claimed order that was claimed, the share of claims covering a whole order, the
  days between first and last claim, the number of distinct claim days, the most claims in any fortnight, and
  the non-receipt share of claims.

| Features | Precision | Recall | Repeat claimants reviewed | Four-leg gate |
|---|---|---|---|---|
| Current 17 | 0.694 | 0.619 | 15.8% | fails the new leg |
| + claim rates | 0.732 | 0.652 | 13.3% | fails the new leg |
| + claim shape | 0.737 | 0.657 | 12.8% | fails the new leg |
| + rates + shape (28 features) | 0.745 | 0.665 | 12.3% | fails the new leg |
| + address and volume as well (32) | 0.749 | 0.668 | 12.2% | fails the new leg |

The other three legs pass in every row. The address feature (what happened to other accounts' deliveries at the
same address) adds almost nothing: only 16% of honest repeat claimants share an address with another account.

Among customers with two or more claim lines, honest repeat claimants outnumber abusers two to one (3,897
against 1,790). What separates them is rate, not kind: abusers claim on a median 30% of orders, honest repeat
claimants on 10.5%.

## 3. Weighting honest repeat claimants in training passes the leg

The model was trained with honest repeat claimants counting more as negatives. The weight uses private truth in
training only, exactly as the label does; nothing private is needed to score.

| Features | Weight | Precision | Repeat claimants reviewed | Four-leg gate |
|---|---|---|---|---|
| 17 | x10 | 0.636 | 7.6% | fails the new leg |
| 17 | x20 | 0.604 | 5.5% | passes |
| 28 | x3 | 0.732 | 8.0% | fails the new leg |
| 28 | x6 | 0.713 | 5.7% | passes |
| 28 | x10 | 0.696 | 4.3% | passes |
| 32 | x6 | 0.721 | 5.7% | passes |
| 32 | x10 | 0.703 | 4.2% | passes |

With the new features and a weight of six, a model passes all four legs at about 0.71 to 0.72: above the
published model's 0.694, which fails the new leg. Recall of deceptive claims falls from 0.79 to 0.70 for
non-receipt and from 0.73 to 0.65 for contents; recall of temporary-use returns rises from 0.65 to 0.69.

## 4. Where this leaves the target

- With the new features and no weighting the model reaches 0.745 to 0.749, the lower edge of the 0.75-0.85 target,
  and fails the new leg.
- With the leg passed it reaches 0.71 to 0.72, three to four points short of the target.

The target and the new leg pull against each other on these features. Closing the gap with the leg passed needs
either features that tell genuine repeat failures from deceptive claims better than rate and shape do, or a
dated change to a permitted calibration lever, disclosed as such.

## 5. Second round: the target is reached with the leg passed

The owner chose to explore further before freezing a contract. Four more families were tried on top of the 28
features, each computed from operational tables only:

- **Timing grain** (7): the largest and second-largest point in the window at which an item was returned, the mean,
  returns made between half and three quarters of the window, and late or mid-late returns of occasion wear.
- **Signs that claims are genuine** (5): orders with two different kinds of failure, the most claim lines in one
  order, whether claimed orders are larger than the customer's usual order, units per order.
- **Style context** (2): how often other customers claim on the styles this customer claimed on, self excluded.
- **Claim value** (1): whether claimed units are dearer than what the customer usually buys.

| Features | Weight | Precision | Repeat claimants reviewed (rule 6.7%) | Four-leg gate |
|---|---|---|---|---|
| 28 | x1 / x4 / x6 | 0.745 / 0.722 / 0.713 | 12.3% / 7.2% / 5.7% | fail / fail / pass |
| 28 + timing grain | x1 / x4 / x6 | 0.767 / 0.745 / 0.736 | 11.5% / 6.4% / 5.5% | fail / pass / pass |
| 28 + genuine signs | x1 / x4 / x6 | 0.748 / 0.723 / 0.713 | 12.2% / 6.9% / 5.5% | fail / fail / pass |
| 28 + style context | x1 / x4 / x6 | 0.755 / 0.738 / 0.728 | 10.9% / 6.3% / 5.3% | fail / pass / pass |
| 28 + claim value | x1 / x4 / x6 | 0.747 / 0.720 / 0.714 | 12.2% / 7.1% / 5.6% | fail / fail / pass |
| 28 + all four (43 features) | x1 / x4 / x6 | 0.773 / 0.761 / 0.750 | 10.3% / 5.9% / 4.9% | fail / pass / pass |

With 43 features and a weight of four the model reaches 0.761 and passes all four legs; with a weight of six,
0.750. Timing grain and style context carry the gain; the "genuine signs" and claim value add almost nothing alone.
The share of one-action abusers found rises from 26% to 37%.

## 6. Check on worlds that took no part in choosing

The features and the weight were chosen on the training worlds, so the out-of-fold figures flatter them. The
same models, fitted on all ten training worlds, were scored on the seven stress worlds, which were not used to
choose anything.

| World | Published 17 | 43, x1 | 43, x4 | 43, x6 | Rule |
|---|---|---|---|---|---|
| W2501 ordinary propensity x1.2 | 0.681 | 0.780 | 0.770 | 0.755 | 0.227 |
| W2502 ordinary propensity x0.8 | 0.708 | 0.792 | 0.796 | 0.789 | 0.289 |
| W2503 defect incidence x2 | 0.710 | 0.797 | 0.790 | 0.783 | 0.254 |
| W2504 household share x2 | 0.700 | 0.774 | 0.756 | 0.756 | 0.223 |
| W2505 action rate x0.5 | 0.523 | 0.575 | 0.561 | 0.565 | 0.144 |
| W2506 action rate x2 | 0.846 | 0.913 | 0.895 | 0.885 | 0.441 |
| W2507 persona multipliers all 1 | 0.677 | 0.759 | 0.738 | 0.730 | 0.213 |
| Four-leg gate passed | 0 of 7 | 0 of 7 | 5 of 7 | 6 of 7 | |

The gain holds on unseen worlds: five to eight points over the published model wherever the action rate is
unchanged. The one failure at a weight of six is W2505, by 8.2% against 8.0% on the new leg.

Out of fold, world by world: at a weight of four the model reviews repeat claimants more often than the rule in
4 of the 10 training worlds although the pooled rate passes; at six, in 1 of 10. The pooled margin at four (5.9%
against 6.7%) is thin for five validation worlds.

## Caveats

- Out-of-fold figures on training worlds that have been looked at many times. The feature families and the
  weight were chosen on them; a contract must fix the candidates before any new validation world exists.
- The weight is a simulation-only device: real data has no ground truth for which claims were genuine.
- Adding features to the contract changes the feature schema, so on this branch the published bundle of
  EXP-20261002-01 stops loading until the new experiment publishes its own. Branch `v2` stays the state that can
  be demonstrated.
