"""Keyed random streams.

Every draw comes from a stream named by (world seed, entity, purpose), so one generation phase can never
advance another. That is what keeps base shopping and honest returns identical when abuse is switched off.
"""
from __future__ import annotations

import hashlib

import numpy as np


def _digest(world_seed: int, entity_key: str, purpose: str) -> bytes:
    return hashlib.sha256(f"{world_seed}|{entity_key}|{purpose}".encode()).digest()


def stream(world_seed: int, entity_key: str, purpose: str) -> np.random.Generator:
    """NumPy PCG64 seeded from the first 128 bits of SHA256(world_seed|entity_key|purpose)."""
    return np.random.Generator(np.random.PCG64(int.from_bytes(_digest(world_seed, entity_key, purpose)[:16], "big")))


def token(world_seed: int, entity_key: str, purpose: str, length: int = 12) -> str:
    """Opaque identifier suffix. Hash-derived so IDs carry no order, layer or persona information."""
    return _digest(world_seed, entity_key, purpose).hex()[:length].upper()


def keyed_uniform(world_seed: int, entity_key: str, purpose: str) -> float:
    """One uniform draw in [0, 1) for an entity, without building a generator (used for sparse keyed events)."""
    return int.from_bytes(_digest(world_seed, entity_key, purpose)[:8], "big") / 2.0 ** 64
