# Package verification

Date: 2026-09-26, with an amendment section dated 2026-10-02 at the end. These results concern the delivered documents and prototype, not the future system. The sections before the amendment describe version 1.0 as checked on 2026-09-26; their counts (ninety criteria, 29 schemas) are the 1.0 values.

## Completed checks

- Sixteen separate component specifications; ninety unique acceptance criteria in the register, all runtime status NOT_RUN.
- Eight canonical YAML contracts parsed; duplicate-key rejection used.
- OpenAPI3.0.3 structurally validated:13 paths,29 typed schemas.
- Manifest JSON Schema validated as Draft2020-12.
- Eighteen unique ordered model features and31 disjoint fixture/stress/train/validation/test/demo seeds.
- Bundled catalog verified:300 rows,37 styles; reason reference16 rows.
- Original five v0.3 files unchanged against hashes captured before amendment work.
- Relative links/package hashes checked by the bundled standard-library verifier.
- Edge Chromium headless file:// walkthrough: queue/filter/search, case tabs, escaped note text, new-run note continuity, style/SKU navigation, evaluation truth reveal, fallback ranking, loading/empty/error/not-ready.
- Desktop and390px layouts checked; no page-level horizontal overflow across main views; tables scroll within panels.
- No JavaScript errors or HTTP(S) requests during browser walkthrough.

Initial mobile table overflow was found and corrected before these final browser checks. Initial shell text encoding artifacts were corrected in the wireframe.

See [browser check details](wireframe-checks.json), [overview](wireframe-overview.png), [case](wireframe-case.png), [style queue](wireframe-styles.png), [evaluation](wireframe-evaluation.png), and [mobile](wireframe-mobile.png).

## Limits

No generator, real dataset, feature implementation, trained model, API, PostgreSQL migration, React/Vite application, Docker runtime or VM was built or tested. Wireframe numbers are illustrative. Browser verification is not a full accessibility certification. Runtime compatibility/locks and each component's90 acceptance criteria remain implementation work.

The ZIP contains only the portable final-spec package. Authoring tools, installed inspection dependencies and laptop paths are excluded. Extract it to another location and run python tools/verify_package.py; changes to versioned files intentionally invalidate their recorded hashes.

## Transfer rehearsal

Final archive extracted into a separate directory containing spaces. The bundled integrity/link verifier passed from outside the extracted package root. This verifies relocation on the same Windows system, not execution on a second physical machine or another operating system.

## Amendment 1.1 checks (2026-10-02)

- Sixteen component specifications; 101 unique acceptance criteria in the register (eleven added), all runtime status NOT_RUN.
- All YAML contracts and assets re-parsed with duplicate-key rejection.
- OpenAPI3.0.3 structurally validated at version 1.1.0: 13 paths, 30 typed schemas; every required property is declared.
- Eighteen unique ordered model features and 31 disjoint seeds, unchanged in number.
- Catalog, profile, festival and reason-code assets are byte-identical to 1.0.
- Wireframe script passes a syntax check; Edge Chromium 154.0.4258.48 headless file:// walkthrough passed 37 checks with no JavaScript errors and no HTTP(S) requests. It covers the model-versus-rule comparison lists and their neutral wording, the return-rate rank column, linked-claim style evidence, the sixth style state, report-only reference rows, fallback scenarios hiding the comparison, boundary states, note escaping and cross-run retention, and 390px layouts.
- The five screenshots were recaptured from the amended wireframe.
- Relative links and package hashes re-checked by the bundled verifier after the manifest was regenerated.

Limits are unchanged: nothing is built or measured. The thresholds and distributions introduced by the amendment are engineering defaults, and the reasons given for several changes are estimates from configuration values. The 1.0 package remains available as ARAI-final-spec-v1.0.zip.

## Amendment 1.2 checks (2026-10-02)

- The package verifier passes after the register, document index and hashes were rebuilt with scripts/spec_package.py in the code repository.
- All YAML contracts and assets parse; the acceptance criteria are unchanged in number (101).
- The acceptance register now carries implementation evidence for part of the GEN, DATA, VAL and EDA criteria. Evidence paths are relative to the code repository root, outside this package. Every other criterion remains NOT_RUN.
- A generator, validator and exploration now exist in the code repository. No feature, model, API, database or application has been built, and no validation or test world has been generated.

## Amendment 1.3 checks (2026-10-02)

- The package verifier passes after the rebuild; all YAML contracts and assets parse; 101 acceptance criteria.
- The generator was changed to match and all fixture, training and stress worlds were regenerated and validated. The exploration's artefact audit confirms no claim-timing range, header line order or same-day order separates honest from abusive requests.
- Evidence in the acceptance register was re-recorded against the regenerated worlds. No validation or test world exists, and no feature, model, API, database or application has been built.
