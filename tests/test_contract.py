"""The contracts are the single source of the numbers and code lists the code uses (final-spec components 06 to 08)."""
import numpy as np
import pandas as pd
import yaml

from arai import contract, diagnostics, evaluation, features, operational, ranking, validation
from arai.generator import assemble, returns
from arai.paths import SPEC_ROOT

EXPERIMENT = yaml.safe_load((SPEC_ROOT / "contracts" / "experiment.yaml").read_text(encoding="utf-8"))
GROUPS = yaml.safe_load((SPEC_ROOT / "contracts" / "reason-groups.yaml").read_text(encoding="utf-8"))["feature_groups"]


def test_scoring_and_evaluation_take_their_numbers_from_the_experiment_contract():
    assert features.ELIGIBLE_MIN_LINES == EXPERIMENT["eligibility"]["min_mature_sale_lines"]
    assert ranking.PRIMARY_FRACTION == EXPERIMENT["budgets"]["primary_fraction"]
    assert list(evaluation.SENSITIVITY_FRACTIONS) == EXPERIMENT["budgets"]["sensitivity_fractions"]
    assert evaluation.BOOTSTRAP_REPETITIONS == EXPERIMENT["uncertainty"]["world_bootstrap_repetitions"]
    assert evaluation.BOOTSTRAP_SEED == EXPERIMENT["uncertainty"]["seed"]
    assert list(evaluation.BOOTSTRAP_PERCENTILES) == EXPERIMENT["uncertainty"]["interval_percentiles"]
    assert contract.primary_fraction() == 0.05 and contract.eligibility_min_lines() == 3       # the values every record was made with


def test_reason_code_groups_come_from_the_contract_and_the_generator_agrees_with_them():
    assert features.CLAIM_CODES == tuple(GROUPS["transaction_claim"]["codes"])
    assert features.COMPLAINT_CODES == tuple(GROUPS["item_complaint_customer"]["codes"])
    assert features.QUALITY_CODES == tuple(GROUPS["item_complaint_sku_quality"]["codes"])
    assert features.DISCRETIONARY_CODES == tuple(GROUPS["discretionary"]["codes"])
    # the generator keeps its own ordered lists (their order drives its random draws); they must name the same codes
    assert set(returns.CLAIM_CODES) == set(GROUPS["transaction_claim"]["codes"])
    assert set(returns.DEFECT_CODES) == set(GROUPS["item_complaint_sku_quality"]["codes"])
    assert set(returns.FIT_CODES) == set(GROUPS["fit"]["codes"])
    assert set(returns.DISCRETIONARY_CODES) == set(GROUPS["discretionary"]["codes"])
    assert set(returns.NO_ITEM_CODES) == set(GROUPS["no_item_return"]["codes"])
    codebook = pd.read_csv(SPEC_ROOT / "assets" / "reason_codes.csv", dtype=str)
    assert {code for group in GROUPS.values() for code in group["codes"]} <= set(codebook["reason_code"])


def test_the_seven_tables_have_one_definition_per_side():
    assert validation.TABLES is operational.TABLES
    assert tuple(assemble.OPERATIONAL_TABLES) == tuple(operational.TABLES)


def test_exploration_uses_the_review_rule_and_the_segments_of_evaluation(world):
    summary = diagnostics.customer_summary(world)
    eligible = summary[summary["eligible"]].assign(world_id=world.world_id)
    chosen = diagnostics.top_fraction(world, summary, "raw_return_rate")
    expected = eligible[evaluation.select(eligible, "raw_return_rate")]
    assert set(chosen["customer_id"]) == set(expected["customer_id"]) and len(chosen) == ranking.budget(len(eligible))
    from arai import eda
    explored = eda.benign_segments(world)
    direct = evaluation.benign_segments(world, summary[["customer_id", "eligible", "raw_return_rate"]])
    pd.testing.assert_frame_equal(explored, direct)
    assert np.isfinite(eligible["raw_return_rate"]).all()


def test_the_contract_names_the_data_folder_of_its_experiment(tmp_path):
    """AM-51: an experiment keeps its worlds, records and database in a folder of its own."""
    from arai import paths
    assert EXPERIMENT["data_root"] == f"data/{EXPERIMENT['experiment_id']}"
    assert paths.contract_data_root() == paths.REPO_ROOT / "data" / EXPERIMENT["experiment_id"]
    earlier = {seed for record in EXPERIMENT["supersedes"]["experiments"] for seeds in record["retired_seeds"].values() for seed in seeds}
    current = {seed for key in ("train_seeds", "validation_seeds", "test_seeds", "demo_seeds") for seed in EXPERIMENT[key]}
    assert not earlier & (current | set(EXPERIMENT["stress_seeds"]))                 # no world of an earlier experiment is reused
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "experiment.yaml").write_text("experiment_id: EXP-EARLIER\n", encoding="utf-8")
    assert paths.contract_data_root(tmp_path) == paths.REPO_ROOT / "data"            # a contract that names none keeps the old layout


def test_the_reference_runtime_mounts_the_data_folder_and_a_database_of_the_contracts_experiment():
    from arai import paths
    compose = (paths.REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count(f"./{EXPERIMENT['data_root']}/artifacts}}:/data/artifacts") == 2          # API and worker
    volume = "pgdata_" + EXPERIMENT["experiment_id"].lower().replace("-", "_")
    assert compose.count(volume) == 2 and "pgdata:" not in compose                                 # never the database of another experiment
    assert "private" not in compose.split("services:")[1]                                          # truth is never mounted
