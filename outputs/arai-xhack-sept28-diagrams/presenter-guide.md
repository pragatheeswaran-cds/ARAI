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
