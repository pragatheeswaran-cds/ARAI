# Baseline rehearsal fixture

What `arai baseline-rehearsal` serves: a second local instance in which the return-rate rule is the active ranking,
the way the product behaves when no model has passed the gate. It is the demo's optional cold open
(`docs/demo-script.md`, section 1d).

Tracked here, under `artifacts/`:

- `bundles/b-*/`: the baseline bundle of the current experiment (reference statistics and reference scores, no model);
- `experiments/<id>/published/experiment.json`: a copy of the published report rewritten with `selection_status:
  no_selected_model` and `final_test_status: not_run`. It is a rehearsal prop, not an experiment record; the records
  stay under `data/<contract>/artifacts/experiments/` and `records/`;
- `active/active.json`: the pointer that activates the baseline with the reason the banner shows.

Not tracked (ignored by git, created at first start): `postgres/`, the embedded database, and `artifacts/datasets/`,
the registered copy of the demo world. The demo world itself is read from `data/<contract>/artifacts/worlds/`, like
`arai local` does, so the first start on a machine needs the experiment's worlds in place.

The command rebuilds `bundles/`, `experiments/` and `active/` from the current artifacts when they are missing or name
a bundle that is not there, and `--fresh` rebuilds them and empties the database. After a rebuild, commit the fixture
if the bundle changed.
