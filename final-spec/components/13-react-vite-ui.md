# React/Vite frontend and analyst workflows

Version 1.0 | Implementation baseline | Component UI

## Requirements and boundary

Use React/Vite for implementation. Standalone wireframe is interactive specification, not production code. Rewrite components with typed API; never ship inline mock metrics. Prototype runs offline without external fonts/assets and labels illustrative data.

Routes: /overview, /datasets, /runs/:run_id/customers, /runs/:run_id/customers/:customer_id, /runs/:run_id/styles, /runs/:run_id/styles/:style_id, /experiments/:experiment_id. Default dataset selection when no ready run. Persistent run/model/cutoff/synthetic context. Support back/deep links. Snapshot cutoff immutable; evidence date filters never recompute historical risk.

Overview has eligible/excluded/selected counts, model kind and evaluation status. No loss prevented or operational FPR without labels. Queue defaults selected-for-review; search opaque ID, eligibility/all filters, measured evidence tags and review disposition. Score tooltip distinguishes training percentile, batch rank and probability. No High/Critical risk bands.

Case shows observed-vs-expected quantities/denominators, timeline, style links, supported relationship table, independent wardrobing with fired signals, and append-only notes. Say suspected/indicator, not detected fraud type/confidence. Review corrections append; notes cross runs of same world/customer and retain origin model/run. No trained labels.

Style queue primary; quality/targeting/mixed/insufficient/no-return, continuous axes, support, customer links, SKU drill-down. Product evidence never clears customer automatically. All products apparel/INR.

Evaluation: baseline/all candidates, coverage/gates/rejection reasons, selection separate from final-test status, benign FPR/denominators, action recall,1/5/10% sensitivity, uncertainty, report-only style/wardrobing. Truth reveal only here and labelled simulation.

Dataset page shows manifest validation/cutoff/history/schema; run progress/errors/retry/hash; no training button. Persistent baseline banner and label; missing bundle blocks run. Loading/empty/error/insufficient-evidence states on every data surface. Labelled keyboard controls/focus/table headers, non-color status labels, responsive layout required.

Local identity notice: no authenticated reviewer. VM shared login still free-text attribution. Replace PDF employee profile with reviewer-name input. Remove fake notifications and unsupported bulk enforcement. Preserve useful PDF sidebar/table/case structure with documented changes.

## Inputs, outputs and dependencies

- Inputs: Typed API and revised clickable wireframe; original PDF visual reference.
- Outputs: Accessible React/Vite SPA.
- Dependencies: Inference/API; wireframe/changes-from-pdf.md.

## Acceptance criteria

| ID | Pass condition and required evidence |
|---|---|
| UI-AC-01 | Walkthrough traverses dataset/run/queue/case/style/SKU/notes/evaluation with stable context and back. |
| UI-AC-02 | Prototype opens offline via file://; production consumes API instead of inline metrics. |
| UI-AC-03 | Fallback/loading/failed/empty/insufficient-history states truthful and distinct. |
| UI-AC-04 | No AI confidence/USD/non-apparel/calibrated bands/loss-prevented claims remain. |
| UI-AC-05 | Keyboard user filters, opens cases, navigates tabs, appends note and returns. |
| UI-AC-06 | Implemented notes persist cross-run; prototype labels memory-only behavior. |
| UI-AC-07 | Truth reveal isolated to evaluation; examples never presented as measured results. |

Acceptance status: **NOT_RUN**. Record executed results and artifact hashes; prose requirements are not implementation evidence.
