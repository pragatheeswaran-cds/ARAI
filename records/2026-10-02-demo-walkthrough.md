# Demonstration walkthrough, 2026-10-02

World `W2401` (seed 2401, 10,000 customers) is the demonstration world. It was generated normally, with no
injected case, after the final test, and it is in no scorecard. The cases below were chosen offline with the
private truth of that world (`scratchpad/pick_demo.py`); **the application never shows that truth on a customer
or style page**. It appears only on the Evaluation page, behind a button, labelled as simulation.

In this world the run scores 5,690 eligible customers and selects 285 for review. Of those 285 the model's list
holds 179 abusers (63%) and the return-rate rule's list 55 (19%). One world is noisier than five: the test
figure is 71.5% against 23.9%.

## The story, in the order to tell it

Open **Overview**. The two lists "selected by the model, not by the rule" and "selected by the rule, not by the
model" each hold 215 customers. The whole explanation is in the difference between those two lists.

### Why the return-rate rule misranks (one case each)

| Reason | Customer | What the case page shows | Model / rule |
|---|---|---|---|
| Honest heavy returns | `W2401-C04139` | 31 mature sale lines, returns 67% of what they buy, no claim, no late return, no link. Everything is an ordinary size or preference return made early in the window. | Rule rank 86 (selected); model rank 1,083 (not selected) |
| Abuse inside an ordinary return rate | `W2401-C02960` | Return rate 20%, exactly what is expected for the products bought. But two of the three requests are claims (wrong item sent, empty package), one of them with nothing sent back. | Model rank 177 (selected); rule rank 2,286 |
| Thin history | `W2401-C02803` | Two mature sale lines, so not ranked by either; the page still shows two claims, one matched by a linked account. "Not ranked" is not "low risk". | Not ranked |
| Linked accounts | `W2401-C09245` | 14 claims; five accounts share two identifier types with this one; the Relationships tab shows same-style claims within 7 days; the style page (`BE-JKT-02`) shows 20 linked claimants. | Model rank 22 (selected); rule rank 428 |

### The other situations the scope names

| Situation | Customer or style | What to show |
|---|---|---|
| Defective-product buyer | `W2401-C08261` | Returned three of four units, one as "not as described" on style `BB-TSH-01`, whose page shows a quality signal (39% quality-reason share). Rule selects (rank 38); model does not (rank 1,122). |
| Benign sharing (household) | `W2401-C01882` | Two linked accounts and six claims over 51 sale lines, none matched by a linked account's claim. Shown as evidence, not counted against the customer; not selected (rank 403). |
| Temporary use | `W2401-C01370` | Return rate 32%, no claim; four item returns in the last quarter of the window; wardrobing indicator elevated. Model rank 3; rule rank 1,164. |
| Mixed | `W2401-C08137` | Claims and late returns together; both rankings select it (rank 14 in each). |
| Style targeting | `BE-JKT-02`, `BB-JKT-01`, `BA-SHT-03` | Targeting state: 9 to 20 linked claimants, linked-claim share 11-16%. |
| Style quality | `BB-TSH-01`, `BC-TSH-03`, `BE-DRS-02` | Quality state: quality-reason share 38-40%. |

### Where the model is wrong (say this before the jury asks)

| Error | Customer or style | What happened |
|---|---|---|
| False positive | `W2401-C02654` | An honest customer with six genuine delivery-failure claims over 12 sale lines. Selected (rank 100). The model cannot tell repeated genuine failures at a bad address from repeated false claims; nor could a person from these fields alone. |
| Missed abuser | `W2401-C05676` | One abusive action, once. Rank 315, just outside the review list. A third of abusers act only once and most of them are missed. |
| Missed style | `BC-TSH-02` | A ring targeted this style, but too few of its claims were linked for the signal to fire. |

Then open **Evaluation**: the scorecard, the error account and the timing disclosure say the same things with
numbers, and the truth reveal shows how many of each list were really abusers in this simulated world.

## What to say and what not to say

- Say: the rule reads one number; abuse shows in what is returned and how; no single signal sees every kind of
  abuse; a hand-written rulebook gets part of the way (35%); the model weighs the signals (71% on test worlds).
- Say: without any timing feature the model family is at 56%; the timing signal is sharper in this simulation
  than in life.
- Say: the development target of 75-85% was not met, and nothing was tuned to reach it.
- Do not say: fraud detected, confidence, probability, significant, or that this would work on real returns.
- The percentile on screen is a position among training scores, not a probability.

## Limits of this walkthrough

The IDs above belong to world `W2401` as generated at commit `62bb9aa`; regenerating with other code or
configuration changes them. The cases were chosen with truth and are therefore favourable illustrations, not a
sample; the Evaluation page is the measurement.
