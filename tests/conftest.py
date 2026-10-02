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
