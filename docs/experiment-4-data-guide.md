# ARAI experiment 4: synthetic data package

Data guide for the team. Experiment `EXP-20261005-04`, packaged 2026-10-05.

**Read this first.** Everything here is simulated. No real customer, order or return is in it. The data comes from
one simulator with stated assumptions, so it teaches method, not what real return abuse looks like. Section 7
says where the simulation is kinder than reality, and this package contains four worlds that show it directly.

If you already have the experiment 2 package: the format, the seven tables and the truth tables are the same.
What is new is in section 2 (new worlds, and four stress worlds with harsher behaviour), section 4 (one added
truth column), section 6 (a five-leg gate and a rebuilt wardrobing indicator) and section 7.

## 1. What is in the package

| Archive | Contents | Use it for |
|---|---|---|
| `...-1-operational-csv.zip` | The seven operational tables of every world as CSV, with each world's `manifest.json` | The data as a retailer would hold it. The contract format. |
| `...-2-operational-parquet.zip` | The same tables as typed Parquet | Faster loading; dates and numbers already typed |
| `...-3-private-truth.zip` | What the simulation knows about every world: who abused, which request was deceptive, which unit was defective | Labels for training and evaluation. **Never an input to a model.** |
| `...-4-configuration.zip` | The contracts, assets, component specifications and generator code exactly as they were when the data was generated; the experiment records | Understanding and reproducing the data |
| `...-5-features-and-results.zip` | The 43 model features per customer, style and SKU evidence, the wardrobing indicator, and the experiment's recorded results | A starting point for modelling, and figures to compare against |

Every archive carries this guide and `WORLDS.csv`, one row per world with its counts and truth totals.
`PACKAGE.json` lists each archive with its size and SHA-256.

Operational data and truth are in separate archives on purpose. Truth is what the simulation knows and a model
can never see. Keep the two apart on disk, and join truth only after features are frozen.

Inside the archives, worlds are grouped by role: `train/`, `validation/`, `test/`, `demo/`, `stress/`.

## 2. The worlds

Each world is an independent simulated retailer: 10,000 fresh customers, one year of history
(2025-09-10 to 2026-09-09), the same 300-SKU, 37-style apparel catalog, amounts in INR, times in India Standard
Time. Customer identifiers are prefixed with the world, for example `W5101-C00042`; nothing links two worlds.

| Role | Worlds | Seeds | How the experiment used them |
|---|---|---|---|
| train | W5101 to W5110 | 5101-5110 | Fitting, with five folds grouped by world (two worlds held out per fold) |
| validation | W5201 to W5205 | 5201-5205 | Choosing among nine candidates under the gate |
| test | W5301 to W5305 | 5301-5305 | The single final test |
| demo | W5401 | 5401 | The demonstration in the application; never in a scorecard |
| stress | W5501 to W5511 | 5501-5511 | One simulator setting changed per world; diagnostic only |

Typical size of one world: about 85,000 orders, 135,000 sale lines, 25,000 return requests with 27,000 return
lines. Outside the stress worlds, between 322 and 373 customers per world abused returns at least once (about
3.6%). About 5,650 customers per world have enough history to be ranked ("eligible"), of whom about 320 are
abusers (about 5.7%).

These worlds come from the same simulator settings as the worlds of experiment 2 (W31xx to W34xx). They are new
draws, not copies: no customer, order or return is shared.

**The validation and test worlds have been used.** They were untouched when the experiment read them, once.
Anything you tune on them now is tuned on seen data. For a fair test of a new idea, generate new worlds from new
seeds (section 8).

### The stress worlds

Seven change one setting of the simulation and leave return timing alone:

| World | What is changed |
|---|---|
| W5501, W5502 | Honest return propensity x1.2 and x0.8 |
| W5503 | Defect incidence x2 |
| W5504 | Household share x2 |
| W5505, W5506 | Abusers' action rate x0.5 and x2 |
| W5507 | All personas equally likely to abuse |

Four switch on the less generous behaviour of the simulator used in experiment 3. They are the worlds to study if
you want to see what a harder problem looks like:

| World | What is changed |
|---|---|
| W5508 | Honest customers return late: 12% of active accounts have the habit, and half of their item returns come back late in the window; one in twenty of everyone else's do |
| W5509 | 30% of temporary-use returns come back as early as honest ones |
| W5510 | Both of the above |
| W5511 | Both, and abusers act on 14% of their orders instead of 20% |

In W5508, W5510 and W5511 about 1,000 customers per world have the late-return habit
(`customer_profile.late_returner`; it is independent of abuse). A late return there is no longer a sign of anything.

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
| `customer_profile` | customer | The simulator's inputs for the customer: persona, order and return targets, whether able to claim deceptively or to use temporarily, how often they act, and the honest overlays (heavy returner, power user, size bracketer, late returner) | `customer_master` |
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

New since the experiment 2 package: `customer_profile.late_returner`. It is false for every customer except in
W5508, W5510 and W5511.

Things that are easy to get wrong:

- **Honest claims exist.** About 1.5% of delivered units genuinely fail (`unit_truth.genuine_fulfilment_cause`), and
  some addresses fail far more often than others (`address_truth.genuine_failure_multiplier`). A customer with
  several claims may simply live at a bad address. The experiment's gate protects two such groups separately:
  honest customers with two or more genuinely failed units, and honest customers with exactly one.
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

All of it is in `...-4-configuration.zip`, taken from git commit `0b0bf29`, and each world's `manifest.json` and
`private-manifest.json` record the hashes of the configuration, the catalog, the generator code and the
dependency lock. The package script checks that this configuration reproduces the hash recorded in the worlds.

| File | What it fixes |
|---|---|
| `contracts/generator-config.yaml` (4.0) | The simulator's numbers: fulfilment, pricing, returns, claims, rings. The block `amendment_4_0` is the one in force; `amendment_3_0` is the less generous behaviour, used only by stress worlds W5508 to W5511 |
| `contracts/generator-policy.yaml` | How abuse propensity is allocated across personas |
| `assets/profile-config.yaml`, `festive-windows.yaml` | Customer personas and the festive calendar |
| `assets/sku_master_source.csv`, `reason_codes.csv` | The catalog and the reason codebook |
| `contracts/experiment.yaml` (4.0) | Seeds, eligibility, the 5% review budget, the nine candidates, the five-leg gate |
| `contracts/features.yaml` (2.1) | The 43 ordered features and the wardrobing indicator |
| `contracts/data-schema.yaml`, `private-truth.yaml` | The operational and truth table contracts |
| `src/arai/settings.py` | Choices the specification leaves open (`IMPLEMENTATION_DEFAULTS`) and what each stress world changes (`STRESS_OVERRIDES`) |
| `src/arai/generator/` | The generator itself |
| `components/02-synthetic-data-generation.md` | The generator described in prose |

The main settings, in plain numbers (all worlds except where a stress world says otherwise):

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

These are the settings of experiment 2's data. A world of experiment 2 regenerated under this configuration came
out identical, table for table.

## 6. What the experiment found on this data

For comparison with your own work. Precision is the share of reviewed customers who really abused, when the top
5% of eligible customers are sent for review.

| Ranking | Validation | Final test |
|---|---|---|
| Return rate alone | 0.227 | 0.218 |
| Five hand-written analyst rules | 0.324 | not tested |
| Selected model: boosted trees on 43 features | 0.743 | 0.766 |

The model also had to review each of five honest groups no more often than the return-rate rule does: heavy
returners, defective-product buyers, household members, repeat genuine claimants (two or more genuinely failed
units) and customers with exactly one genuine failure. It was trained with the last two groups weighted six and
three times. Those weights use truth, which real data would not have.

Three things to know before quoting the result (details in `records/2026-10-05-experiment-4.md`):

- On the stress worlds where honest customers return late (W5508, W5510, W5511) the same frozen model reaches
  only 0.35 to 0.46, against 0.18 to 0.24 for the return-rate rule.
- The model meets the repeat-claimant leg narrowly. It reviews about 6% of that group on every set of worlds,
  while the rule's rate moves between 5.9% and 7.5%.
- Which of the weighted candidates was selected is noise: six passed validation within 1.5 points of each other.

`features/<role>/<world>/features.parquet` holds the 43 features and an `eligible` flag for every customer, computed
from operational tables only. The definitions are in `contracts/features.yaml`.

### The wardrobing indicator

`features/<role>/<world>/wardrobing.parquet` holds a rule-based indicator of temporary use, separate from the
model. Its signal is occasion wear returned in the last quarter of the return window. That alone gives no band.
It counts when what the customer returned supports it: occasion wear returned far more often than their other
returns predict (`occasion_excess_z`), or a quality complaint on a style nobody else complains about
(`clean_style_complaint_lines`). One kind of support gives `possible`, both give `elevated`.

On the test worlds the `elevated` band is right for 89 of 90 customers and contains 15% of the customers with a
temporary-use return. On W5508, W5510 and W5511 it is right for 76% to 93%. An indicator built without any
timing was tried first and dropped: without a late return its alerts were right about one time in ten. So timing
is still what tells temporary use apart in this simulation; the supporting evidence only decides when to trust it.

## 7. Where this simulation is kinder than reality

- **Timing is too clean.** Outside W5508, W5510 and W5511, honest customers almost never return in the last
  quarter of the window; real ones do. A late return is close to proof of temporary use in the main worlds and
  would not be in real data.
- **Claims are too clean.** Abusers claim on a fifth of their orders while genuine failures are rare, so claim
  frequency separates them well.
- **Abusive requests are never withdrawn and never arrive after the window.** A withdrawn or out-of-window item
  return is therefore always honest. That is an artefact, not a finding.
- **A solo abuser claims at most once per order**, while genuine failures can hit several lines of one order.
- **The catalogue is small.** With 37 styles and a marked defect truth, "a style nobody else complains about" is
  easy to establish. Most complaints on such styles are still genuine defects reported by honest customers.

What happened when the simulation was made less generous:

- Experiment 3 trained and tested on worlds like W5511. The same method reached 0.548 against 0.186 for the rule.
- A model trained on the generous worlds and scored on W5511 reaches 0.35. A model does not carry over from one
  timing behaviour to the other; it has to be trained on the behaviour it will meet.

Compare methods on the same worlds. Do not quote a percentage as what a retailer would see. A useful exercise
with this package: build something on the training worlds, then score it on W5508 to W5511 and see what is left.

## 8. Working with the data

Load one world:

```python
import pandas as pd
world = "operational-parquet/train/W5101"
orders = pd.read_parquet(f"{world}/sales_order.parquet")
lines = pd.read_parquet(f"{world}/sales_order_line.parquet")
returns = pd.read_parquet(f"{world}/return_order_line.parquet")
truth = pd.read_parquet("private-truth/train/W5101/customer_truth.parquet")   # labels: join last
```

From CSV, read everything as text first and convert: dates are `YYYY-MM-DD`, timestamps carry the `+05:30`
offset, money has two decimals, an empty cell means null.

Rules that keep results honest:

1. Build features from operational tables only. Join truth after the features are fixed.
2. Split by world, never by customer. Customers of one world share a catalog, a calendar and rings.
3. Compute anything "relative to other customers" inside one world, and leave the customer out of their own peer
   group.
4. Use mature lines for rates.
5. Treat the validation and test worlds as seen.
6. Keep the stress worlds out of training. Each differs from the training worlds in a known way, which is what
   makes them useful as a check.

To generate fresh, untouched worlds, check out commit `0b0bf29` of the repository and run `uv sync` then
`uv run arai generate --seed <new seed>`, with a seed that no experiment has used (the command refuses the seeds
of earlier experiments). The same seed and commit reproduce a world exactly; a new seed gives a new one from the
same simulator. A seed that is not in the contract gives a 1,000-customer world unless `--customers 10000` is
passed, and the world is then named with that size, for example `W9001N10000`.

## 9. Integrity

`PACKAGE.json` has the SHA-256 of every archive. Inside, each world's `manifest.json` has the SHA-256 and row count
of each CSV, and `private-manifest.json` has those of each truth table and the hash of the operational manifest it
was written with. The package script verified all of them before packing.
