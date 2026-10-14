import json
import uuid

import numpy as np
import pandas as pd
import pytest

from arai.generator import generate_world, write_world

FIXTURE_SEED = 2001


@pytest.fixture(scope="session")
def world():
    return generate_world(FIXTURE_SEED)


@pytest.fixture(scope="session")
def world_without_abuse():
    return generate_world(FIXTURE_SEED, abuse_enabled=False)


@pytest.fixture(scope="session")
def written(world, tmp_path_factory):
    root = tmp_path_factory.mktemp("worlds")
    return write_world(world, artifact_root=root / "artifacts", private_root=root / "private")


# ---------------------------------------------------------------------- a small trained experiment for serving tests
@pytest.fixture(scope="session")
def trained(world, tmp_path_factory):
    """An experiment directory with one fitted candidate and the baseline statistics, built from the fixture world.

    The fixture world's customers are split into ten pseudo-worlds only so that the fold map has ten groups.
    Returns {"artifact_root", "experiment_dir", "frame", "reference"}.
    """
    from arai import features as F
    from arai import modeling

    artifact_root = tmp_path_factory.mktemp("serving")
    experiment_dir = artifact_root / "experiments" / "EXP-TEST"
    reference = F.fit_reference([(world.tables, world.snapshot_date)])
    features = F.compute_features(world.tables, world.snapshot_date, reference).features
    frame = features.merge(world.truth["customer_truth"][["customer_id", "y_abuse"]], on="customer_id")
    frame = frame[frame["eligible"]].reset_index(drop=True)
    names = [f"T{i:02d}" for i in range(10)]
    frame["world_id"] = [names[i % 10] for i in range(len(frame))]
    folds = modeling.fold_map(names)
    candidate = next(c for c in modeling.candidates() if c.id == "logreg_c1")
    modeling.train_candidate(candidate, frame, folds, experiment_dir / "candidates" / "logreg_c1")
    forest = next(c for c in modeling.candidates() if c.id == "iforest_256")
    modeling.train_candidate(forest, frame, folds, experiment_dir / "candidates" / "iforest_256")
    (experiment_dir / "baseline").mkdir(parents=True)
    (experiment_dir / "baseline" / "baseline.json").write_text(json.dumps({"kind": "baseline_fallback", "reference": reference.to_dict()}))
    pd.DataFrame({"score": np.sort(frame["raw_return_rate"].to_numpy())}).to_parquet(
        experiment_dir / "baseline" / "reference_scores.parquet", index=False)
    (experiment_dir / "config.json").write_text(json.dumps({
        "experiment_id": "EXP-TEST", "training_worlds": names, "features_sha256": {}, "experiment_config_sha256": "0" * 64}))
    return {"artifact_root": artifact_root, "experiment_dir": experiment_dir, "frame": frame, "reference": reference}


# ---------------------------------------------------------------------- PostgreSQL for storage and API tests
@pytest.fixture(scope="session")
def postgres(tmp_path_factory):
    """A private PostgreSQL server for the test session (no Docker needed)."""
    import pgserver

    server = pgserver.get_server(tmp_path_factory.mktemp("pg"))
    yield server.get_uri()
    server.cleanup()


@pytest.fixture
def database_url(postgres):
    """A fresh, empty database for one test."""
    import psycopg

    name = "t_" + uuid.uuid4().hex[:16]
    with psycopg.connect(postgres, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    base, _, query = postgres.partition("?")                      # the host may be a socket directory: keep the query untouched
    return base.rsplit("/", 1)[0] + "/" + name + ("?" + query if query else "")
