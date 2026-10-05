# ARAI experiment 2: synthetic data package

Data guide for the team. Experiment `EXP-20261005-02`, packaged 2026-10-05.

**Read this first.** Everything here is simulated. No real customer, order or return is in it. The data comes from
one simulator with stated assumptions, so it teaches method, not what real return abuse looks like. Section 7
says where the simulation is kinder than reality.

## 1. What is in the package

| Archive | Contents | Use it for |
|---|---|---|
| `...-1-operational-csv.zip` | The seven operational tables of every world as CSV, with each world's `manifest.json` | The data as a retailer would hold it. The contract format. |
| `...-2-operational-parquet.zip` | The same tables as typed Parquet | Faster loading; dates and numbers already typed |
| `...-3-private-truth.zip` | What the simulation knows about every world: who abused, which request was deceptive, which unit was defective | Labels for training and evaluation. **Never an input to a model.** |
| `...-4-configuration.zip` | The contracts, assets, component specifications and generator code exactly as they were when the data was generated; the experiment records | Understanding and reproducing the data |
| `...-5-features-and-results.zip` | The 43 model features per customer, style and SKU evidence, and the experiment's recorded results | A starting point for modelling, and figures to compare against |

Every archive carries this guide and `WORLDS.csv`, one row per world with its counts and truth totals.
`PACKAGE.json` lists each archive with its size and SHA-256.

Operational data and truth are in separate archives on purpose. Truth is what the simulation knows and a model
can never see. Keep the two apart on disk, and join truth only after features are frozen.

Inside the archives, worlds are grouped by role: `train/`, `validation/`, `test/`, `demo/`, `stress/`.

## 2. The worlds

Each world is an independent simulated retailer: 10,000 fresh customers, one year of history
(2025-09-10 to 2026-09-09), the same 300-SKU, 37-style apparel catalog, amounts in INR, times in India Standard
Time. Customer identifiers are prefixed with the world, for example `W3101-C00042`; nothing links two worlds.

| Role | Worlds | Seeds | How the experiment used them |
|---|---|---|---|
| train | W3101 to W3110 | 3101-3110 | Fitting, with five folds grouped by world (two worlds held out per fold) |
| validation | W3201 to W3205 | 3201-3205 | Choosing among six candidates under the gate |
| test | W3301 to W3305 | 3301-3305 | The single final test |
| demo | W3401 | 3401 | The demonstration in the application; never in a scorecard |
| stress | W2501 to W2507 | 2501-2507 | One simulator setting changed per world; diagnostic only |

Typical size of one world: about 84,000 orders, 135,000 sale lines, 25,000 return requests with 27,000 return
lines. Outside the stress worlds, between 337 and 392 customers per world abused returns at least once (about 3.6%). About 5,650 customers
per world have enough history to be ranked ("eligible"), of whom about 320 are abusers (about 5.7%).

**The validation and test worlds have been used.** They were untouched when the experiment read them, once.
Anything you tune on them now is tuned on seen data. For a fair test of a new idea, generate new worlds from new
seeds (section 8).

The stress worlds change one thing each: honest return propensity x1.2 (W2501) and x0.8 (W2502), defect
incidence x2 (W2503), household share x2 (W2504), abusers' action rate x0.5 (W2505) and x2 (W2506), and all
personas equally likely to abuse (W2507). They were generated for the first experiment with the same simulator
settings and are otherwise like the training worlds.

## 3. Operational data: the seven tables

Full column lists, types, keys and allowed values are in `configuration/final-spec/contracts/data-schema.yaml`.

| Table | One row per | Key | Notes |
|---|---|---|---|
| `customer_master` | customer | `customer_id` | Signup date. Status, loyalty tier and marketing channel are emitted as `unknown`. |
| `sku_master` | SKU | `sku` | Style, category, size, colour, price, return window (30, 45 or 60 days), occasion-wear flag, launch date |
| `reason_code` | reason code | `reason_code` | The codebook: 16 reasons with their class |
| `sales_order` | order | `order_id` | Customer, order date, channel, address, device and payment identifiers, totals |
| `sales_order_line` | order line | `order_id`, `order_line_no` | SKU, quantity, price, discount, line status, shipped and delivered dates, return window captured at sale |
| `return_order` | return request header | `return_order_id` | Customer, creation time, channel, refund method and total |
| `return_order_line` | return line | `return_order_id`, `return_line_no` | The sale line it refers to, quantity, reason code, request time, status, refund amount |

How they join: `sales_order_line.order_id -> sales_order`, `sales_order_line.sku -> sku_master`,
`return_order_line.(order_id, order_line_no) -> sales_order_line`, `return_order_line.return_order_id -> return_order`,
`return_order_line.reason_code -> reason_code`.

Conventions worth knowing before you compute anything:

- **Cutoff.** The snapshot is taken at 2026-09-09 23:59:59 IST. Nothing after it is in the data.
- **Line status.** `delivered`, `shipped`, `lost_in_transit`, `awaiting_dispatch`, `cancelled`. Only delivered lines
  can be returned.
- **Mature line.** A delivered line whose return window had closed by the cutoff. Return rates are only fair on
  mature lines; a line delivered last week has not had its chance to be returned.
- **Eligible customer.** At least three mature sale lines. The experiment ranks only eligible customers.
- **Return line status.** `pending`, `refunded`, `rejected`, `withdrawn`. Withdrawn requests are ignored by every
  feature.
- **Two kinds of request.** Four reason codes are transaction claims: `item_not_received`, `wrong_item_sent`,
  `missing_parts`, `empty_package`. Every other code is an item return. Two of the claims (`item_not_received`,
  `empty_package`) involve no item coming back.
- **Identifiers are opaque.** `address_id`, `device_id` and `payment_id` are for equality only. Two accounts using
  the same value is a fact about sharing, not about guilt.

## 4. Truth: what the simulation knows

Twelve tables per world plus `private-manifest.json`. The contract is
`configuration/final-spec/contracts/private-truth.yaml`. All join to operational data by the keys shown.

### The label

`customer_truth.y_abuse` is 1 if the customer completed at least one abusive action whose request is visible at
the cutoff. Three kinds of action exist, and a customer can have more than one:

- `deceptive_nonreceipt_claim`: the item arrived, and the customer claimed it did not.
- `deceptive_contents_claim`: the parcel was right, and the customer claimed wrong item, missing parts or empty package.
- `temporary_use_return`: the customer used the item and returned it ("wardrobing").

An action counts whether or not the refund was granted. Being in a household or a ring, or having a propensity
to abuse, is not abuse: only a completed action is. Every customer has a label; only eligible ones are ranked.

### The tables

| Table | One row per | What it tells you | Joins to |
|---|---|---|---|
| `customer_truth` | customer | `y_abuse`, one flag per kind of action, `coordinated_action_flag`, and membership of a household, a coordination group (ring) or a shared location | `customer_master` |
| `customer_profile` | customer | The simulator's inputs for the customer: persona, order and return targets, whether able to claim deceptively or to use temporarily, how often they act, and the honest overlays (heavy returner, power user, size bracketer) | `customer_master` |
| `action_truth` | abusive action, completed or not | Kind, the sale line and units, the return line it produced, time, ring and campaign if coordinated, and why an attempt was not completed | `return_order_line` by `return_order_id`, `return_line_no` |
| `unit_truth` | delivered unit | Whether it really arrived, was defective, was damaged in transit, failed in fulfilment and how, or was temporarily used | `sales_order_line`, plus `unit_index` |
| `line_truth` | sale line | The unit facts rolled up to the line | `sales_order_line` |
| `unit_allocation` | requested unit | Which request, honest or abusive, took which unit | `sales_order_line`, plus `unit_index` |
| `order_truth` | order | Whether it is an ordinary order, a ring's campaign order, or a household co-order | `sales_order` |
| `product_truth` | style | Defect-prone or ordinary, on the world's hot list, and whether a ring targeted it | `sku_master.style_id` |
| `sku_truth` | SKU | Whether the SKU has a fit issue | `sku_master` |
| `relationship_truth` | group membership and identifier | Which accounts were given which shared address, device or payment value, and how often each uses it | `customer_master` |
| `campaign` | ring campaign | The ring, the target style and the date | `action_truth.campaign_id` |
| `address_truth` | delivery address | How failure-prone deliveries to the address are | `sales_order.address_id` |

Things that are easy to get wrong:

- **Honest claims exist.** About 1.5% of delivered units genuinely fail (`unit_truth.genuine_fulfilment_cause`), and
  some addresses fail far more often than others (`address_truth.genuine_failure_multiplier`). A customer with
  several claims may simply live at a bad address. Honest customers with two or more genuinely failed units are
  the group a claim-driven model most often accuses wrongly; the experiment's gate has a leg for them.
- **Honest heavy returners exist.** 6% of active accounts return 28% to 48% of what they buy
  (`customer_profile.heavy_return_overlay`). A return-rate rule fills its review list with them.
- **Sharing is mostly honest.** 12% of customers are in households that share an address and often a device or a
  payment method. Rings share too. `customer_truth.household_id` and `coordination_group_id` say which is which.
- **Assigned is not observed.** `relationship_truth` says what a group was given; what an account actually used on
  an order is in `sales_order`.
- **Propensity is not action.** `customer_profile.claim_propensity` marks who could abuse. Many never did, or not
  visibly before the cutoff. The label is `customer_truth.y_abuse`.
- **A whole-parcel claim is one action.** It appears as several `action_truth` rows, the extra ones marked
  `parcel_companion`. Count opportunities, not rows.

## 5. The configuration that produced the data

All of it is in `...-4-configuration.zip`, taken from git commit `a7b79aa`, and each world's `manifest.json` and
`private-manifest.json` record the hashes of the configuration, the catalog, the generator code and the
dependency lock. The package script checks that this configuration reproduces the hash recorded in the worlds.

| File | What it fixes |
|---|---|
| `contracts/generator-config.yaml` (1.3) | The simulator's numbers: fulfilment, pricing, returns, claims, rings |
| `contracts/generator-policy.yaml` | How abuse propensity is allocated across personas |
| `assets/profile-config.yaml`, `festive-windows.yaml` | Customer personas and the festive calendar |
| `assets/sku_master_source.csv`, `reason_codes.csv` | The catalog and the reason codebook |
| `contracts/experiment.yaml` (2.0) | Seeds, eligibility, the 5% review budget, the six candidates, the four-leg gate |
| `contracts/features.yaml` (2.0) | The 43 ordered features |
| `contracts/data-schema.yaml`, `private-truth.yaml` | The operational and truth table contracts |
| `src/arai/settings.py` | Choices the specification leaves open (`IMPLEMENTATION_DEFAULTS`), also recorded in every `private-manifest.json` |
| `src/arai/generator/` | The generator itself |
| `components/02-synthetic-data-generation.md` | The generator described in prose |

The main settings, in plain numbers:

- **Who can abuse.** About 4% of accounts can make deceptive claims, 3% can use temporarily, 0.5% both; newer and
  high-intensity personas more often. 40% of those accounts are in rings of three to six.
- **How often they act.** Each such account acts on a share of its orders drawn once from Beta(1.2, 4.8), mean 0.20.
- **Genuine failures.** Per delivered unit: not received 0.5%, wrong item 0.4%, missing parts 0.4%, empty package
  0.2%, carrier damage 0.5%. Each address multiplies the first four by its own factor.
- **Ordinary returns.** Category base rates of 15% to 22%, raised for size bracketing, fit issues and defects.
  8% of styles are defect-prone (a quarter of their units are defective, against 1% elsewhere).
- **Timing.** An honest item return is requested at Beta(2, 5) of the return window, so early. A temporary-use
  return at Beta(5, 2), so late. Every claim, honest or not, follows one law: min(30, Gamma(2, 3)) days after delivery.
- **Rings.** Each world has a private hot list of four expensive styles. A ring picks one or two and runs two to
  four campaigns; members order the style and claim on it within days of each other.
- **Outcomes.** 2% of in-window requests are rejected, 3% of honest requests are withdrawn, 2% of honest item
  returns arrive after the window and are rejected.

## 6. What the experiment found on this data

For comparison with your own work. Precision is the share of reviewed customers who really abused, when the top
5% of eligible customers are sent for review.

| Ranking | Validation | Final test |
|---|---|---|
| Return rate alone | 0.265 | 0.240 |
| Five hand-written analyst rules | 0.370 | not tested |
| Selected model: boosted trees on 43 features | 0.737 | 0.737 |

The model also had to review each of four honest groups no more often than the return-rate rule does: heavy
returners, defective-product buyers, household members and repeat genuine claimants. It was trained with the
last group weighted six times. Details: `records/2026-10-05-experiment-2.md` in the configuration archive, and the
JSON reports in the features-and-results archive.

`features/<role>/<world>/features.parquet` holds the 43 features and an `eligible` flag for every customer, computed
from operational tables only. The definitions are in `contracts/features.yaml`.

## 7. Where this simulation is kinder than reality

A later experiment tested this directly and should shape how you read any number you get here.

- **Timing is too clean.** Honest customers here almost never return in the last quarter of the window; real ones
  do. A late return is close to proof of temporary use in this data and would not be in real data.
- **Claims are too clean.** Abusers claim on a fifth of their orders while genuine failures are rare, so claim
  frequency separates them well.
- **Abusive requests are never withdrawn and never arrive after the window.** A withdrawn or out-of-window item
  return is therefore always honest. That is an artefact, not a finding.
- **A solo abuser claims at most once per order**, while genuine failures can hit several lines of one order.

When the simulator was made less generous on timing and claim frequency (experiment 3), the same method fell from
0.737 to 0.548, and the return-rate rule from 0.240 to 0.186. The level moved; the ratio stayed at about three.
Compare methods on the same worlds. Do not quote a percentage as what a retailer would see.

## 8. Working with the data

Load one world:

```python
import pandas as pd
world = "operational-parquet/train/W3101"
orders = pd.read_parquet(f"{world}/sales_order.parquet")
lines = pd.read_parquet(f"{world}/sales_order_line.parquet")
returns = pd.read_parquet(f"{world}/return_order_line.parquet")
truth = pd.read_parquet("private-truth/train/W3101/customer_truth.parquet")   # labels: join last
```

From CSV, read everything as text first and convert: dates are `YYYY-MM-DD`, timestamps carry the `+05:30`
offset, money has two decimals, an empty cell means null.

Rules that keep results honest:

1. Build features from operational tables only. Join truth after the features are fixed.
2. Split by world, never by customer. Customers of one world share a catalog, a calendar and rings.
3. Compute anything "relative to other customers" inside one world, and leave the customer out of their own peer
   group.
4. Use mature lines for rates.
5. Treat the test worlds as seen.

To generate fresh, untouched worlds, check out commit `a7b79aa` of the repository and run
`uv sync` then `uv run arai generate --seed <new seed>`. The same seed and commit reproduce a world exactly; a new
seed gives a new one from the same simulator.

## 9. Integrity

`PACKAGE.json` has the SHA-256 of every archive. Inside, each world's `manifest.json` has the SHA-256 and row count
of each CSV, and `private-manifest.json` has those of each truth table and the hash of the operational manifest it
was written with. The package script verified all of them before packing.
