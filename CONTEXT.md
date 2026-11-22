# Apparel Returns Analysis

Analysis of suspected return abuse in Indian online apparel retail.

## Language

**Returns Analyst**:
The person who investigates customers for suspected return abuse and reviews evidence from their orders and returns.
_Avoid_: Return Analyst

**Customer Investigation**:
A review of a customer's return behaviour and supporting evidence to assess suspected abuse.

**Return-item Inspection**:
A physical examination of an individual returned garment to assess its identity and condition.
_Avoid_: QA when the intended meaning is physical inspection of a returned item

**Legitimate Heavy Returner**:
A customer with frequent legitimate returns; high return activity alone does not establish abuse.

**Suspected Return Abuse**:
Potential misuse of the returns process that warrants investigation, rather than a confirmed finding of misconduct.
_Avoid_: Confirmed fraud when only a risk signal is available

**Wardrobing Indicator**:
Behavioural evidence consistent with buying clothing for temporary use and then returning it. The indicator does not establish that a garment was worn.

**Commercial Cost**:
The economic burden associated with a customer's orders and returns, which can arise even when the customer follows the return policy.

**SKU Investigation**:
A review of a specific product variant's return patterns to understand why returns are elevated, including whether product quality contributes.

**Suspected SKU Quality Issue**:
A possible product problem that explains returns for a specific SKU. It does not establish misconduct by its buyers or rule out separate customer abuse.

**Suspected Abuse Targeting**:
Evidence that a SKU is being selected for return abuse, rather than elevated returns being explained solely by product quality.

**Unexplained Excess Returns**:
Return activity that remains unusually high after accounting for relevant purchasing context. It is an investigation signal, not proof of abuse.

**Pending Return Item**:
A submitted return item awaiting the inspection stage at which prioritization occurs; its eventual inspection result is not yet available to that decision.

**Case**:
One customer in one scored run, as a unit of review. It carries the customer's own number (CASE-03245 for W5401-C03245); it is not a single return.
_Avoid_: Using case for one return or one refund

**Risk Level**:
Where a customer stands against the review budget: Critical (selected for review and in a detected ring), High (selected for review otherwise), Medium (a score of 90 or above, not selected) and Low. A presentation rule over the results, not a model output.
_Avoid_: Tier in text shown to analysts; severity

**Case Status**:
Open (not yet taken up), In Review (opened by a reviewer), Escalated (handed to the investigation team) or Closed. A closed case says how it ended: cleared, confirmed after escalation, or not confirmed after escalation.
_Avoid_: Approved, rejected, awaiting approval (the earlier two-person workflow)

**Clear**:
A reviewer's decision that a case needs no further action; it closes the case as cleared.

**Escalate**:
A reviewer's decision to hand a case to the investigation team. A lead later closes it with the outcome.

**Lead**:
A person with the approver role, who closes an escalated case as confirmed or not confirmed.
_Avoid_: Second reviewer, approver in text shown to analysts

**Suspected**:
The word for anything that describes the customers selected for review rather than a confirmed case: suspected return rate, suspected loss trend.
_Avoid_: Fraud rate, fraud loss, false claim when nothing has been confirmed

**Linked-account Group**:
Accounts joined by shared identifiers. A ring is a group whose claims matched or whose members sit in the queue together; a household shares an address and a device and nothing else. Membership is evidence, not guilt.

**Contact Details**:
The region, email and phone of an account, optional in the data. They are shown to the analyst and are never model inputs.

**Evidence Graph**:
The links between accounts that an analyst is shown: any two shared identifier types out of address, device, payment method, phone number and mailbox. It is wider than the graph the model reads, which uses the three order identifiers only; it changes what is shown and never a score, a rank or a selection.
_Avoid_: Saying the model uses phone or email
