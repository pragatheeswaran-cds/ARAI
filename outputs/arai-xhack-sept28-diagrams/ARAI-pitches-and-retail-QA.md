# ARAI — Complete Presentation Rehearsal Handbook

For the XHack design review on Monday, 28 September 2026.

This handbook contains all 16 slide pitches, software-engineering analogies, transitions, a glossary, 45 retail-expert questions with suggested answers, and a one-minute overall pitch. Present slides 1–13 and use 14–16 as backup. The answers describe the current design, not completed implementation or measured model results.

---

# ARAI — presenter guide

Matches the 16-slide design presentation for 28 September 2026.

Present slides 1–13 in roughly 10–12 minutes, allowing time to point at the diagrams. Slides 14–16 are backup for questions. Practice aloud; your natural pace determines the final duration. The quoted text is the speaking script. The explanations and cues are rehearsal aids, not additional material to read aloud.

You do not need to introduce yourself as inexperienced in data science. Explain the problem, the design choices, and how the team will check whether they work. Say “we plan” for unimplemented behavior. Specifications and a clickable wireframe exist; trained results do not yet exist.

## 1. ARAI — introduction

**Say:**

“Good morning. Our idea is ARAI: Adaptive Return Abuse Intelligence, for online apparel returns. We want to help an analyst decide which cases deserve investigation and understand the evidence behind them. A customer returning many items is not automatically abusing the system. Our design combines customer behavior with product context to support that distinction. Today I’ll explain the proposed solution, architecture, evaluation approach, and delivery plan.”

**Engineering connection:** Think of an investigation workbench that prioritizes alerts and exposes supporting logs.

**Transition:** “Let me start with why return volume alone is an incomplete signal.”

## 2. Problem statement

**Say:**

“The same high return rate can have very different causes. One customer may be searching for the right fit. Another may have received a defective product. A third may be intentionally misusing the return process. If we treat all three alike, we can send analysts toward legitimate customers and miss the actual product problem. Our challenge is to identify useful investigations while keeping those alternative explanations visible.”

**Engineering connection:** A high error count tells you something needs attention; it does not identify the root cause by itself.

**Transition:** “Our solution adds that missing context to a prioritized queue.”

## 3. Proposed solution

**Say:**

“ARAI will organize eligible customers into a ranked investigation queue. Each case will include supporting return activity, product context, and relevant signals. The analyst can inspect the evidence and record a decision. We will compare machine learning against a simple return-rate ranking. If the model does not pass our quality checks, we will use that baseline and clearly disclose it. The system will support human review; it will not automatically deny refunds or suspend accounts.”

**Engineering connection:** The baseline is a simple reference implementation against which a more complex approach must justify itself.

**Transition:** “Four connected views make that workflow practical.”

## 4. Key features

**Say:**

“The first view is the customer queue and case details. The second is product analysis at style and SKU level, so analysts can see whether a product is causing widespread returns. Third, relationship evidence helps inspect shared identifiers without assuming that every shared household is suspicious. Fourth, a separate timing indicator highlights patterns potentially relevant to wardrobing—buying for temporary use and then returning. That timing signal is a prompt to investigate, not proof that an item was worn.”

**Engineering connection:** These are separate diagnostic views, not four independent verdicts.

**Transition:** “Here is how these capabilities fit into the architecture.”

## 5. Architecture diagram

**Say:**

“The architecture has two parts. At the top is the offline Python pipeline: create data, validate it, calculate features, train candidates, and evaluate them. Its output is a frozen model bundle. At the bottom is the application: React calls FastAPI, and one worker executes scoring using that saved bundle. PostgreSQL stores run state and audit information; artifact storage holds result files. From a software engineering perspective, the offline pipeline resembles a build-and-release process. The application loads the released artifact rather than training a model on every request.”

**Point at:** Top row left to right; bundle-to-worker arrow; UI → API → worker; both storage boxes.

**Engineering connection:** The bundle is a versioned release artifact. Unlike ordinary compilation, training learns parameter values from examples, so statistical evaluation is also required.

**Transition:** “The next slide follows the data through those components.”

## 6. Data flow diagram

**Say:**

“The top row shows model development. We generate operational tables, check their quality, and convert records into numeric features. Those features are the inputs used to train and compare models. We keep the generator’s known answers—called private truth—separate. They help with training and evaluation, but must never become model inputs. The bottom row shows application use: register a dataset, validate it, calculate the same features, score with the frozen bundle, publish results, and review them in the UI. No training happens in this runtime flow.”

**Point at:** Offline row; amber private-truth boundary; runtime row.

**Engineering connection:** Do not pass the expected output from your test fixture into the function being tested. That would make the result misleadingly good. In machine learning this kind of shortcut is called leakage.

**Transition:** “Because this is a controlled demonstration, the dataset design matters.”

## 7. Synthetic data design

**Say:**

“We plan to generate synthetic shopping histories instead of claiming that we already have a real customer dataset. The catalog contains 300 SKUs across 37 styles. Each generated world is planned to contain 10,000 customer profiles and twelve months of activity. A world means a separate simulated dataset. We will include legitimate heavy returners, product defects, and benign shared households, as well as explicit misuse scenarios. This lets us test whether our approach handles counterexamples, rather than treating every frequent returner as suspicious.”

**Engineering connection:** Synthetic worlds resemble large integration-test fixtures with controlled scenarios. The same generator can still create common biases across worlds.

**Transition:** “Next is the most important question: how will we know whether the model helps?”

## 8. Model validation

**Say:**

“We separate learning, selection, and final testing. Ten worlds are used for training, five for choosing among candidates, five for the held-out test, and one for the demo. Our main comparison assumes analysts review the top five percent of eligible customers. Within that same review budget, the selected model must identify a higher proportion of known simulated abuse cases than the baseline. It must also avoid increasing false positives in each of our three benign groups. We freeze the selection before the final test. If it fails, we disclose that and use the baseline.”

**Engineering connection:** Validation is the environment used to choose among approaches. The held-out test is a final check whose answers must not guide repeated design choices.

**Plain language:** Precision means “Of the cases we selected for review, how many were labeled abuse?” False-positive rate means “Of the legitimate customers in this group, how many were selected?” These have different denominators.

**Transition:** “Those checks are useful only if an analyst can understand the resulting output.”

## 9. UI / UX

**Say:**

“This is our revised clickable wireframe. The displayed values are illustrative, not measured model results. The case view brings together the ranking, observed-versus-expected returns, and separate indicators. A percentile describes where a score sits relative to a stored reference distribution; it is not the probability that the customer is abusive. Analysts can inspect product context, question the signal, and append review notes. The intention is to make the evidence understandable and the investigation traceable.”

**Engineering connection:** Think of an observability dashboard: a useful summary with enough detail to investigate and challenge it.

**Transition:** “We can build this workflow with a compact technology stack.”

## 10. Technology stack

**Say:**

“Python, NumPy, and pandas handle data preparation and feature calculation. Scikit-learn provides our model candidates. FastAPI exposes the backend, and React with Vite provides the analyst interface. PostgreSQL stores operational metadata, while Parquet and other versioned files hold datasets and results. We plan a local-first deployment to keep the initial build manageable and portable. Codex and Claude can assist development, but the product does not depend on an LLM to generate its investigation ranking.”

**Engineering connection:** Most of the application is a familiar web system. The extra subsystem is an offline experimental pipeline producing a tested scoring artifact.

**Transition:** “We will integrate that system in stages.”

## 11. Implementation plan

**Say:**

“Our proposed plan starts with environment setup, contracts, and a small generated world. Next we complete data validation and features. Then we connect the simple baseline to the API and UI, so the full user journey works early. After that, we run the full model experiment and evaluate the selected candidate. The final week is reserved for acceptance checks and rehearsal. This sequence reduces integration risk and gives us a demonstration path even if machine learning does not beat the baseline. Owners and the exact demo date still need confirmation.”

**Engineering connection:** Deliver a vertical slice before optimizing an individual subsystem.

**Transition:** “There are three main risks we are explicitly planning around.”

## 12. Risks and feasibility

**Say:**

“First, a model might learn shortcuts in our synthetic generator. We will use separate worlds, benign counterexamples, and stress cases, while keeping claims limited to what we actually test. Second, no model may beat the baseline. That is an acceptable experiment outcome, and the application will still expose baseline ranking and evidence. Third, integration or long-running jobs could threaten the demo. We address that with an early end-to-end workflow, durable run state, recoverable results, and a rehearsal period.”

**Engineering connection:** A working software path can be committed to; improved model quality must be demonstrated experimentally.

**Transition:** “That brings us to what is ready and what we need from this review.”

## 13. Review outcome / closing

**Say:**

“We have sixteen component specifications, ninety defined acceptance criteria, and a portable clickable wireframe. These establish the implementation baseline; they do not mean the application has been built or the acceptance checks have passed. Today we want alignment on scope and architecture, clear ownership, and a confirmed demo date. Our next milestone is a small reproducible dataset connected to the baseline-to-UI workflow. The outcome we are aiming for is an investigation tool whose ranking can be inspected, tested, and challenged. Thank you.”

**Delivery cue:** Stop here and invite questions. Use the remaining slides when a question needs more detail.

## 14. Backup — feature design

**Say:**

“A feature is a numeric input derived from raw records. Instead of giving the model only a return count, we also calculate context. High returns for products that many other customers return may suggest a product issue. High returns for otherwise low-return products may deserve closer inspection. We exclude the customer from their own peer comparison and use observations whose return window has elapsed. Relationship features also require multiple identifier types and exclude overly common identifiers. These checks improve the meaning of the inputs before we compare models.”

**Engineering connection:** Features are derived fields with explicit contracts, deterministic calculations, and tests.

**If asked about k = 20:** It is the specified smoothing strength for combining sparse local evidence with broader product context; it is not a requirement for twenty customer returns.

## 15. Backup — model candidates

**Say:**

“We are comparing five candidates from three model families. Logistic regression provides a comparatively simple supervised approach. Two histogram boosting variants can learn more complex relationships between features. Two Isolation Forest variants look for unusual patterns without using abuse labels during fitting. Unusual behavior is not automatically abuse, so every candidate is evaluated against the same labeled scenarios and review budget. We will choose using validation results, then freeze and test the selection. We are not assuming that the most complex model will win.”

**Engineering connection:** Different implementations may solve the same ranking problem. Unlike exact-output algorithms, their usefulness is compared statistically on representative examples.

**Delivery cue:** Do not read every parameter on the slide. Explain the families and fair comparison; discuss settings only if asked.

## 16. Backup — serving and reproducibility

**Say:**

“Each scoring run starts with a registered dataset and a manifest describing its identity. The request identifies the model bundle and uses an idempotency key to avoid accidental duplicate execution. One worker validates and scores the data, then publishes complete results atomically. Run metadata and analyst notes remain traceable. This allows us to connect a result to its exact inputs and model version. We will first support a portable local setup, then consider optional hosted deployment after the local workflow is rehearsed.”

**Engineering connection:** This is familiar job-processing discipline: input validation, versioning, idempotency, durable state, and atomic publication.

## Data science vocabulary through a software engineering lens

| Term | Meaning here | Helpful engineering analogy |
|---|---|---|
| Feature | A numeric measurement computed from records | A derived input field |
| Label / private truth | Known simulated outcome used to learn or evaluate | Expected result in a fixture; not a runtime input |
| Training | Learning model parameters from examples | An offline build step, with a statistical rather than exact correctness check |
| Model | Saved learned parameters plus an algorithm | A versioned function implementation |
| Inference / scoring | Applying a saved model to new inputs | Runtime execution |
| Baseline | Simple comparison approach: raw return-rate ranking | Reference implementation |
| Validation worlds | Data used to select among candidates | A comparison environment |
| Held-out test worlds | Data reserved for checking the frozen selection | An independent final acceptance check |
| Leakage | Giving the experiment information unavailable legitimately at scoring time | Accidentally feeding the answer into the implementation |
| Precision at 5% | Share of labeled abuse among the top 5% selected for review | Quality of the limited review queue |
| False-positive rate | Share of legitimate customers selected for review | Rate of unnecessary alerts among legitimate cases |
| Percentile | Score position relative to a reference score distribution | Relative placement, not certainty |
| Synthetic world | Independently generated simulated dataset | A reproducible scenario suite |
| Wardrobing indicator | Separate timing-based signal relevant to temporary-use investigation | A diagnostic hint, not proof of physical wear |

## Answers to likely questions

**Why machine learning if a rule can rank returns?**
“A learned model may combine several contextual signals better than return rate alone. We will measure that advantage rather than assume it. The simple rule remains our baseline and fallback.”

**What accuracy have you achieved?**
“We are at the design stage and have no trained results yet. The evaluation contract focuses on precision at a fixed review budget and false positives in specific benign groups.”

**Does success on synthetic data prove it works on real customers?**
“No. It demonstrates behavior on our simulated scenarios. Real-world use would require representative real-data evaluation and review of how the simulation differs from actual behavior.”

**Does a 90th-percentile score mean a 90% chance of abuse?**
“No. It describes the score’s position in a reference distribution. It is not a calibrated probability of abuse.”

**Why are there training, validation, and test datasets?**
“Training learns parameters, validation chooses the candidate, and the held-out test checks the frozen choice. Repeatedly changing the design based on the test would weaken its independence.”

**Why not automatically block customers?**
“This MVP is an investigation aid. Return behavior is ambiguous, so a reviewer needs the evidence and legitimate alternative explanations.”

**What happens if the selected model fails the final test?**
“We report the outcome and use the baseline. We do not keep trying runner-up models against the same test until one passes.”

**Why a single worker?**
“It keeps execution and recovery manageable for the MVP. We will measure runtime before considering additional concurrency.”

## Rehearsal plan

1. First practice the problem, solution, and closing without referring to algorithm names.
2. Explain slide 5 by pointing at the offline lane, saved bundle, and application lane.
3. Explain slide 6 as two journeys: creating a scoring artifact and using it.
4. Practice the difference between features and labels, and between precision and false-positive rate.
5. Time slides 1–13 aloud. Skip backup slides unless requested.
6. Replace wording that feels unnatural with your own words, while preserving the boundaries: ranking is not proof; percentile is not probability; synthetic results are not real-world proof; planned work is not completed work.

If you lose your place, return to this sentence: “We turn return records into contextual signals, compare rankings fairly, and present the evidence for human investigation.”


---

# Retail expert questions and suggested answers

These are rehearsal answers for the ARAI design presentation, not measured findings or new commitments. They reflect the current specification. Features described in future tense still require implementation. Real customer data, production enforcement, continuous retraining, and financial-benefit claims are outside this demonstration's scope.

## Business problem and value

### 1. What exactly is return abuse? How is it different from using the published return policy?

**Suggested answer:** “For this demonstration, we model submitted intentional deceptive claims and temporary-use returns. Frequent returns, commercial cost, or using the permitted return window do not by themselves establish abuse. The application only highlights suspected cases for investigation. For a real deployment, the retailer would need to agree on operational definitions and what evidence supports each decision.”

**Remember:** A model signal is not proof of intent or a policy violation.

### 2. Which abuse problem are you targeting first?

**Suggested answer:** “The MVP prioritizes customer investigations across simulated deceptive claims, coordination, and temporary-use scenarios. It produces one overall customer ranking, supported by product and relationship evidence. Wardrobing has a separate timing indicator. We are not claiming that the model independently predicts or confirms each abuse type.”

### 3. Why apparel, and how do you account for size, fit, and style preferences?

**Suggested answer:** “Apparel is our chosen scope, and fit-related returns make context particularly important to the design. We compare customer behavior with the products they bought and expose style and SKU evidence. We include legitimate heavy-return scenarios in evaluation. We do not infer intent from a return count or claim that the model understands an individual customer's fit preference.”

### 4. Why not just use a return-rate rule?

**Suggested answer:** “That rule is our baseline. A model may combine product context and other signals better, but it must demonstrate that advantage at the same review budget. If it does not improve precision while meeting our benign-group checks, we use the disclosed baseline. We are not adding machine learning just to make the solution more complex.”

### 5. Who uses the system, and what decision do they make?

**Suggested answer:** “A Returns Analyst uses it to prioritize cases, inspect customer and product evidence, and record a review disposition and notes. The analyst may conclude that evidence is insufficient or that a product issue needs attention. Downstream operational action remains outside this MVP. The system cannot automatically deny refunds or suspend accounts.”

### 6. What business outcome would prove value?

**Suggested answer:** “Our first measurable objective is better investigation precision at a fixed review capacity, without increasing false positives in the specified legitimate-customer groups. In a future retail pilot, we would also want to measure review time and the usefulness of evidence. We cannot claim financial savings without actual review costs, recoverable losses, and outcome data.”

## Legitimate customer behavior

### 7. How do you distinguish ordering several sizes from abusing returns?

**Suggested answer:** “Multiple purchases and returns alone are not sufficient. We show product context and supporting history, and include legitimate heavy returners as an explicit evaluation group. The aim is to reduce unnecessary prioritization of those customers. We do not claim that the MVP has a definitive classifier for size-selection shopping.”

### 8. What if your size chart is inaccurate?

**Suggested answer:** “If many customers return the same products, that is relevant product evidence. The style and SKU views help the analyst investigate that explanation before attributing behavior to a customer. They do not prove that a size chart is wrong. Confirming the cause would require operational follow-up outside the model's score.”

### 9. What if a style or SKU has a genuine quality problem?

**Suggested answer:** “We examine return behavior across customers at style and SKU level and display suspected product issues with supporting evidence. This gives the analyst an alternative explanation for high returns. Product issues and customer misuse can also coexist, so a product signal does not automatically clear every customer associated with it.”

### 10. What about promotions, festivals, and occasion-based shopping?

**Suggested answer:** “Those are important contexts to investigate before operational use. Our current design does not establish that all campaign or occasion effects are modeled. The simulation and features define the contexts we can currently test. If a retail expert identifies a material missing scenario, we should record it as a gap and evaluate its impact rather than assume the model handles it.”

### 11. Could a shared address or device simply be a family or hostel?

**Suggested answer:** “Yes. Shared identity evidence is not proof of coordination. The design requires at least two identifier types for supported relationship evidence and excludes identifiers with excessive connections. We also include benign sharing in evaluation. Those safeguards reduce simplistic flags, but they do not establish intent.”

### 12. What happens to new customers or customers with little history?

**Suggested answer:** “Customers require at least three mature sale lines to enter the ranking. We show insufficient-history exclusions instead of assigning a misleading score. Three lines are an eligibility rule for this experiment, not a guarantee that every eligible customer's evidence is strong. We are not introducing a separate new-customer enforcement rule.”

## Retail data and operational detail

### 13. What data does the retailer need to provide? What if fields are missing?

**Suggested answer:** “The current contract uses seven linked tables: customer, SKU, reason code, sales order, sales line, return order, and return line, with a manifest. Their identifiers, dates, and relationships must satisfy the schema. Required-field and relationship failures must be reported and block invalid data from scoring. Optional information follows its explicit missing-data policy. The exact required fields are defined in the portable data contract.”

### 14. How do you distinguish requested, received, inspected, and refunded returns?

**Suggested answer:** “Those are different operational events, and we must not treat them as interchangeable. Our demonstration uses the events and dates explicitly represented by its data contract; pending inspection routing is excluded. Synthetic abuse labels refer to submitted intentional deceptive claims or temporary-use returns, regardless of whether a refund succeeds. A real retailer's return lifecycle would need explicit mapping before integration.”

### 15. Are cancellations, failed deliveries, exchanges, and partial returns handled separately?

**Suggested answer:** “They should not be silently counted as equivalent customer returns. Our contract represents sales and returns at line level, but that does not establish full support for every retail lifecycle. We should verify each requested workflow against the schema and generator rules. Any unsupported scenario needs an explicit mapping or scope extension before claiming support.”

**Remember:** Do not claim a complete exchange or failed-delivery workflow without checking its specified representation.

### 16. What about different return windows or historical policy changes?

**Suggested answer:** “Maturity is based on delivery plus the captured return window at the observation cutoff. That avoids assuming a single current policy for every historical purchase. For an integration, we would need reliable historical policy information or an agreed mapping; otherwise we cannot honestly reconstruct the observation window.”

### 17. Can you trust customer-selected return reasons?

**Suggested answer:** “We should treat a stated reason as an observation, not verified intent. Customers may choose imperfect categories, and abuse can involve deceptive claims. Private truth is kept separately in the simulation. We do not equate a customer-selected reason with confirmed abuse or confirmed product failure.”

### 18. Can you separate customer behavior from seller, warehouse, carrier, or fulfillment failures?

**Suggested answer:** “The current design provides product context and legitimate defect scenarios. It does not establish complete attribution across sellers, warehouses, and carriers. That would require corresponding operational data and evaluation scenarios. We should describe those causes as possible explanations when evidence is missing, rather than blame the customer.”

### 19. Why wait for the return window to elapse?

**Suggested answer:** “A recent delivery has had less time to produce a return than an older delivery. Treating both as completed outcomes would distort comparisons. We use mature observations based on delivery, the captured return window, and a fixed cutoff. This makes the observation opportunity more comparable.”

## Evidence and customer protection

### 20. Without images or inspection evidence, how can you identify wardrobing?

**Suggested answer:** “We cannot establish physical wear from timing alone. Our independent, image-free indicator highlights timing patterns relevant to a temporary-use investigation. It is clearly labeled as an indicator and shown with supporting signals. It is not a finding that the customer wore the item.”

### 21. Does returning near the deadline really indicate abuse?

**Suggested answer:** “Not by itself. A customer may legitimately use the full permitted window. Timing must be interpreted in category and behavioral context, and even then it remains evidence to review. That is why we keep the wardrobing indicator separate and avoid automatic enforcement.”

### 22. What evidence would justify escalating a case?

**Suggested answer:** “The analyst should inspect the underlying transactions, product context, history, and any supported relationship or timing signals. The score alone is not sufficient. The MVP records the review, but does not define a production enforcement threshold. Escalation policy and required corroboration would need agreement with the retailer.”

### 23. Will ARAI block refunds or restrict accounts?

**Suggested answer:** “No. Those actions are explicitly outside this MVP. ARAI prioritizes investigations and exposes evidence. It does not contain automatic refund or account-suspension actions.”

### 24. Can an analyst disagree with the ranking?

**Suggested answer:** “Yes. Analysts can record review dispositions and append notes, including explanations that challenge the score. Corrections preserve history rather than rewriting earlier notes. This feedback is not automatically used for retraining, and the prototype's local note behavior should not be confused with the planned persisted application.”

### 25. How do you avoid repeatedly targeting legitimate high-value customers?

**Suggested answer:** “We evaluate false positives in specific legitimate groups, require mature history, expose product context, and retain review notes. These are safeguards, not a guarantee for every customer segment. The current design does not establish lifetime-value-aware ranking, repeat-review suppression, or dedicated protection metrics for high-value customers. Those would need explicit evaluation before being promised.”

## Synthetic data and model credibility

### 26. Who decided whether the synthetic scenarios represent retail behavior?

**Suggested answer:** “The specification defines controlled scenarios, but that is not the same as external domain validation. We want retail reviewers to challenge the assumptions, scenario coverage, and plausible behavior. Before operational use, those assumptions would need comparison with representative real data. The current demonstration should be described as a simulation.”

### 27. How do you know the model is not learning generator shortcuts?

**Suggested answer:** “We separate private truth from feature inputs, use independently generated worlds, include benign counterexamples, and run stress cases. These help expose shortcuts, but they cannot eliminate every shared generator bias. Different random seeds alone are not proof of realism. We will limit conclusions to the conditions actually evaluated.”

### 28. How do you define the correct answer when intent is uncertain?

**Suggested answer:** “In the simulation, we control the generated actions and keep their intended outcomes in private truth. Labels come from specified completed abusive actions, not high return volume or persona names. In real data, intent may be uncertain, so reviewed outcomes and an explicit labeling policy would be needed. We do not claim that synthetic certainty transfers to real customers.”

### 29. What happens when real behavior differs from your simulation?

**Suggested answer:** “Performance may change, potentially substantially. We would first compare data coverage, feature behavior, and investigation outcomes on representative real cases. The demonstration does not authorize deployment of the synthetic-trained model as a proven production detector. Any pilot should be bounded and reviewed before expansion.”

### 30. Why should a retailer trust a model evaluated only on synthetic data?

**Suggested answer:** “They should treat it as evidence of a controlled experiment and a proposed workflow, not proof of production accuracy. Synthetic data lets us develop the pipeline and test defined scenarios with known outcomes. Real-world trust would require additional validation using representative data and reviewed case outcomes.”

### 31. What would you need before a real-data pilot?

**Suggested answer:** “We would need an agreed use case and review policy, authorized access to representative data, explicit lifecycle mapping, and a credible way to review outcomes. We would establish the baseline and analyst capacity, then assess results with human review before considering operational expansion. These are future pilot requirements, not work already completed by this MVP.”

### 32. What if none of your models improves on the baseline?

**Suggested answer:** “We report that result and serve the clearly labeled raw-return-rate baseline with the same evidence views. If the frozen candidate fails the final test, we do not keep trying runner-ups against that test until one passes. A negative model result is still useful, and the investigation workflow remains demonstrable.”

## Analyst workflow, economics, and rollout

### 33. How many cases can an analyst review each day?

**Suggested answer:** “We have not measured that yet. Capacity depends on evidence complexity, investigation depth, and the analyst's other work. We would measure review time in a realistic walkthrough or pilot before translating the queue into daily staffing requirements. The experiment's percentage budget is not a measured capacity estimate.”

### 34. Why select the top five percent?

**Suggested answer:** “Five percent is the specified experimental review budget. It provides a consistent basis for comparing candidates against the baseline. We also plan sensitivity checks at one and ten percent. An operational review budget should be agreed from actual analyst capacity and business priorities.”

### 35. Does the ranking prioritize likelihood, financial exposure, or ease of investigation?

**Suggested answer:** “The current ranking prioritizes cases using the selected scoring approach, evaluated by abuse-label precision at a fixed review budget. It is not a calibrated probability, expected-loss estimate, or review-effort score. We should not present it as optimizing all three objectives.”

### 36. Could small-value cases crowd out a few costly cases?

**Suggested answer:** “Yes, that is a possible limitation of a count-based review objective. Our current design does not establish an expected-loss ranking. Financial prioritization would require reliable value, recovery, and review-cost information and a separately agreed evaluation objective. It is a legitimate extension to consider, rather than a benefit we can already claim.”

### 37. What does the analyst get beyond existing reports?

**Suggested answer:** “The proposed value is a connected workflow: a review queue linked to transaction evidence, expected-versus-observed returns, style and SKU context, relationship evidence, and review notes. We should compare that workflow with the retailer's current tools before claiming it saves time. The design aims to reduce the effort of assembling evidence across separate reports.”

### 38. What happens after review, and who owns the action?

**Suggested answer:** “The analyst records a disposition and notes in this MVP. Any subsequent customer, product, or policy action belongs to the retailer's agreed operational process. We have not built automated enforcement or downstream workflow integration. Identifying that operational owner is an important question for the design review.”

### 39. How will you measure whether the evidence is useful?

**Suggested answer:** “Our acceptance criteria check that evidence is accessible, consistent, and traceable. They do not establish business usefulness by themselves. A future user evaluation could measure time to review, missing information, and whether analysts can reach a justified disposition. Those measures should be agreed with the people doing the work.”

### 40. How will you detect changing behavior or deteriorating results after deployment?

**Suggested answer:** “The MVP uses frozen snapshots and bundles; continuous retraining is out of scope. Versioned inputs and outputs support reproducibility, but that is not a complete production monitoring solution. Before broader deployment, we would need an agreed process to review data changes and measured outcomes and to revalidate replacement models. We should not describe that future capability as already implemented.”

## Additional questions you may receive

### 41. What accuracy have you achieved?

**Suggested answer:** “We are at the design stage and do not have trained performance results yet. Our primary checks are precision at the review budget and false-positive rates in the specified benign groups. We will report measured results after the experiment rather than invent an accuracy target or outcome.”

### 42. Does a 90th-percentile score mean a 90% chance of abuse?

**Suggested answer:** “No. It describes score position relative to a stored reference distribution. It does not mean a 90% probability of abuse, and it is also different from the customer's rank within the current scoring batch.”

### 43. Why do you need separate training, validation, and test worlds?

**Suggested answer:** “Training learns the model parameters, validation chooses among candidates, and the held-out test checks the frozen choice. If we keep changing the model based on test results, that test becomes part of selection and loses its independent role. The demo world is separate again.”

### 44. Will analyst notes automatically improve the model?

**Suggested answer:** “No. Notes support review history and traceability in the current design. Automatically treating notes as correct labels or using them for retraining would introduce new quality and workflow requirements. Continuous retraining is outside this MVP.”

### 45. How strong is the audit trail if reviewers share a login?

**Suggested answer:** “The proposed notes preserve run and model context and are append-only. However, local reviewer names are self-entered, and a shared VM login does not establish verified individual identity. We should not claim enterprise-grade reviewer accountability. Individual authentication and stronger access controls would require a separate production design.”

## One-minute overall pitch

“ARAI is an investigation assistant for online apparel returns. The problem is that a high return rate can reflect fit issues, product defects, or intentional misuse, and the number alone cannot tell us which.

“We propose a ranked customer queue connected to transaction evidence, product context, relationship signals, and a separate timing indicator. A human analyst reviews the evidence; the system does not automatically deny refunds or suspend accounts.

“We will build and evaluate the ranking offline using controlled synthetic data. A model must improve on a simple return-rate baseline without worsening false positives in our specified legitimate groups. If it fails, we disclose that and use the baseline.

“Our specifications and clickable wireframe are ready. The next step is a small reproducible dataset connected to the API and UI, followed by the full experiment. This is a testable design and implementation plan, not a claim of proven production fraud detection.”

## How to handle an unexpected question

Use three short statements:

1. **Current scope:** “In our current design, we support…”
2. **Evidence:** “We check that through…”
3. **Limit or next step:** “We have not established X yet; that would require…”

For a genuinely missing retail workflow, say: “That is not covered sufficiently by our current design. I would record it as a requirement gap and check the data and operational impact before committing to an implementation.”

## Five answers to memorize first

- **High returns:** “High returns alone are not proof of abuse; we show context and supporting evidence.”
- **Wardrobing:** “Timing is an investigation signal, not proof of physical wear.”
- **Synthetic data:** “Synthetic success validates the tested simulation, not real-world effectiveness.”
- **Score:** “A percentile is relative position, not a probability of abuse.”
- **Status:** “The design and wireframe are ready; model performance and runtime acceptance results are not yet available.”
