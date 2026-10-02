# Generator implementation record, 2026-10-02

> **Superseded in part the same day.** Findings 1 and 2 below were resolved by specification amendment 1.2
> (longer tenures, ring campaigns that start at ring formation, targeting threshold 0.05), and the two missing
> boundary fixtures now have tests. The numbers in this record describe the generator before those changes;
> current figures are in `records/2026-10-02-eda.md`.

First implementation of the synthetic world generator (final-spec v1.1, components 02, 03 and 04) on branch `v1`.
This is a development record in the sense of the specification: it lists the choices the specification leaves
open and what the first worlds showed. Nothing here is a measured model result.

## What exists

- `src/arai/generator/`: profiles and abuse propensity, relationships, base orders and fulfilment, honest returns,
  ring campaigns with abuse-layer campaign orders, solo abusive actions, snapshot assembly and private truth.
- `src/arai/validation.py`: structural validator for the seven operational tables and the manifest.
- `src/arai/diagnostics.py`: offline checks that join private truth (development worlds only).
- `notebooks/01_synthetic_data_generation.ipynb`: the same pipeline stage by stage, with checks and charts.
- `tests/`: 32 tests covering reproducibility, the abuse-off property, label reconstruction, the catalog adapter,
  campaign orders, targeting truth, CSV/Parquet parity, the manifest and one rejection per validator rule class.

Run it with `uv sync`, then `uv run arai generate --seed 2001`, `uv run pytest` or `uv run jupyter lab`.

## Choices the specification leaves open

These live in `IMPLEMENTATION_DEFAULTS` in `src/arai/settings.py` or next to the code that uses them. They are
part of the configuration hash in every manifest.

| Choice | Value | Reason |
|---|---|---|
| Power users | 8% of Loyalists only, 55-140 orders | The team's config calls them the "Loyalist heavy tail"; applying 8% to every account would double order volume |
| Order intensity cap | At most one order per eligible day | A 3-day-old account with a 48-order target would otherwise place 16 orders a day |
| Soft persona boundaries (`bleed_prob`) | One of order target, festive share or return propensity redrawn from another persona | The team's config describes the idea but not the mechanism |
| Bracketing | 10% of accounts; on 35% of their multi-line orders the second line is another size of the first line's style and colour | The specification names bracketers but gives no rate |
| Fit-issue SKUs | 10% of SKUs; a returned unit of one gives a fit reason 80% of the time | Same |
| Defect-prone styles | Exactly round(8% x 37) = 3 styles per world | Independent draws left fixture world 2001 with none, which would starve the defective-buyer segment |
| Genuine claim timing | Same distribution as solo deceptive claims (0 to 10 days) | Otherwise timing alone would separate honest from deceptive claims |
| Coordinated claim delay | Gamma(2, 3 days) after delivery, capped at 30 days, for reused purchases too | The specification says "after delivery" |
| Late honest requests | Exactly floor(2% of honest item returns), chosen at random, requested 1 to `window` days late | The specification says "at most" 2% |
| Withdrawal | Only honest non-claim requests, 0-2 days after the request | Abusive requests never withdraw (specification) |
| Return headers | A header covers its first request date and the next day; abusive lines join an honest header covering their date and are numbered after the honest lines | Keeps honest line identifiers identical with abuse on or off |
| Identifiers | Order, return, address, device and payment IDs are hash-derived | Row order and ID order carry no information about layer or intent |
| Own identifiers | One address; a second device for 30% and a second payment method for 40% of accounts; the primary is used 80% of the time | Not specified |
| Shared-location groups | None in worlds under 500 customers; otherwise at least one group of 26 | A 1,000-customer fixture needs one group above the fan-out cap |
| Abuse switched off | Propensities and group membership stay; only campaigns and solo actions are disabled | Group sharing shapes base orders, so removing groups would change honest data |
| World ID | `W<seed>`, plus `N<customers>` or an override hash when the world is not the standard one for its seed | An ID must bind to one content |

## What the first worlds showed

Measured on fixture worlds 2001-2003 (1,000 customers) and one full-size scratch world (seed 9001, 10,000
customers, not part of the experiment and not used for any decision).

| Measure | Full-size scratch world |
|---|---|
| Generate / write / validate | 11 s / 4 s / 5 s |
| Orders, sale lines, return lines | 99,342 / 158,572 / 29,022 |
| Campaign orders | 138 |
| Eligible customers (3 or more mature sale lines) | 56.6% |
| Abusers: all / eligible / excluded for thin history | 347 / 293 / 54 |
| Prevalence among eligible customers | 5.2% |
| Return-rate rule, precision in the top 5% | 21.9% (62 of 283) |
| Claim-count rule, precision in the top 5% | 35.7% (101 of 283) |
| Damage share of the three defect-prone styles | 0.38, 0.41, 0.44 (others at most 0.06) |
| Linked-claim share of the three targeted styles | 0.13, 0.07, 0.07 (other styles at most 0.02) |

Realised rates match their targets: claim, temporary-use and joint propensity 4.0%, 3.0% and 0.5%; mean action
rate 0.20; genuine fulfilment failures 1.47% of delivered units; carrier damage 0.54%.

In the fixture worlds the review list is only about 30 customers, so the return-rate rule's precision ranges
from 10% to 18% across the three seeds. Fixture worlds are for correctness, not for rates.

## Findings that need a decision

1. **Targeting threshold.** The targeted styles are clearly separated from the rest (0.07-0.13 against at most
   0.02), but the 0.10 default detects only one of three in the full-size world. Either lower the threshold to
   about 0.05, or make campaigns denser. The main cause of thin campaigns is that 164 of 303 attempts fail (129 complete)
   because the campaign date falls before the member signed up; drawing campaign dates from the period in which
   the ring's members exist would remove most of that. Both are development-world changes the specification
   allows before validation generation, with a dated record.
2. **Everyone is a new customer.** Profile tenures are at most 365 days, so the whole customer base signed up
   during the history window and weekly orders climb from near zero to about 500 (fixture world). This comes
   from the team's profile configuration and is unchanged here. It also makes the festive peaks, which fall
   early in the window, smaller than the specification's multipliers suggest.
3. **The quality threshold change holds up.** The defect-prone styles sit at 0.38-0.44, so they clear the
   amended 0.30 threshold and would have missed the original 0.50.
4. **Difficulty.** The return-rate rule is already inside its 20-30% target band in the scratch world without
   any tuning. Whether the best model lands in 75-85% is not known until the features and candidates exist.

## Acceptance criteria exercised

The tests exercise parts of GEN-AC-01, 02, 04, 05, 06, 07 (label side), 09 and 10, DATA-AC-01, 02, 04 and 06, and
VAL-AC-01 and 03. `final-spec/acceptance-register.csv` is not updated: the register asks for a dated, reviewed
sign-off per criterion, and several criteria are only partly covered. Not yet covered: the quantity-three
boundary fixture of GEN-AC-03, the all-dormant boundary fixture, idempotent re-registration (DATA-AC-05), the
coverage reports of GEN-AC-08 as a saved artifact, and every criterion from features onward.
