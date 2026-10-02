"""How much of the result depends on the timing features (decision AM-31).

Out-of-fold precision at the review budget on the ten training worlds for one candidate, with all features,
without late_return_lines, and without any timing feature. Training worlds only: it reads no validation or test
world and changes no fitted model, so it can be recorded at any time.
"""
from __future__ import annotations

import json

from arai import evaluation, modeling
from arai.settings import load_settings

TIMING_FEATURES = ("late_return_lines", "late_window_share", "median_window_ratio")
VARIANTS = (("all features", ()), ("without late_return_lines", ("late_return_lines",)), ("without any timing feature", TIMING_FEATURES))


def timing_ablation(experiment_id: str, candidate_id: str, artifact_root=None, private_root=None) -> dict:
    settings = load_settings()
    out = modeling.experiment_dir(experiment_id, artifact_root)
    worlds = [f"W{s}" for s in settings.experiment["train_seeds"]]
    frame = evaluation.evaluation_frame(worlds, artifact_root, private_root)
    folds = modeling.fold_map(worlds)
    registered = next(c for c in modeling.candidates(settings) if c.id == candidate_id)
    baseline = evaluation.confusion(frame, evaluation.select(frame, "raw_return_rate"))
    rows = []
    for name, dropped in VARIANTS:
        features = [f for f in registered.features if f not in dropped]
        candidate = modeling.Candidate(registered.id, registered.ordinal, registered.family, registered.supervised,
                                       dict(registered.params), features)
        scores, _ = modeling.out_of_fold(candidate, frame, folds)
        scored = frame.assign(_score=scores)
        result = evaluation.confusion(scored, evaluation.select(scored, "_score"))
        rows.append({"variant": name, "features": len(features), "k": result["k"], "true_positives": result["true_positives"],
                     "precision": result["precision"], "recall_temporary_use_return": result["recall_temporary_use_return"]})
    payload = {"experiment_id": experiment_id, "candidate_id": candidate_id, "measured_on": "training worlds, out of fold, 5% budget",
               "timing_features": list(TIMING_FEATURES), "baseline_precision": baseline["precision"], "variants": rows}
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "reports" / "timing_ablation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
