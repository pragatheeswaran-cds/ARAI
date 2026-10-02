# Package verification

Date: 2026-09-26. These results concern the delivered documents and prototype, not the future system.

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
