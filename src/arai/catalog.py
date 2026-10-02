"""Catalog adapter: the team's 300-SKU source file becomes the operational sku_master table.

Only the named transforms of final-spec component 04 are applied: sku_id->sku, color->colour,
color_id->colour_id and booleans->0/1. Nothing else is altered, and the source hash is recorded.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RENAMES = {"sku_id": "sku", "color": "colour", "color_id": "colour_id"}
BOOLEAN_COLUMNS = ("is_occasion_wear", "active_flag")
SKU_COLUMNS = ["sku", "style_id", "brand", "category", "size", "colour", "colour_id", "unit_price", "price_band",
               "return_window_days", "is_occasion_wear", "launch_date", "active_flag"]
REASON_COLUMNS = ["reason_code", "description", "claim_class", "intent_class", "fault_attribution",
                  "requires_item_return", "is_high_risk"]


@dataclass
class Catalog:
    sku_master: pd.DataFrame      # operational table, one row per SKU, sorted by sku
    styles: pd.DataFrame          # one row per style: category, median price, occasion flag, first launch
    reason_code: pd.DataFrame
    source_sha256: str
    transforms: list[str]

    # arrays aligned with sku_master rows, for fast lookups during generation
    sku_style: np.ndarray         # style index of each SKU
    sku_price_paise: np.ndarray
    sku_window: np.ndarray
    sku_launch: np.ndarray        # datetime64[D]
    sku_occasion: np.ndarray      # bool
    sku_size: np.ndarray
    sku_colour: np.ndarray


def load_catalog(spec_root: Path) -> Catalog:
    source = Path(spec_root) / "assets" / "sku_master_source.csv"
    raw = pd.read_csv(source, dtype=str, keep_default_na=False)
    transforms = [f"rename {old}->{new}" for old, new in RENAMES.items()]
    sku = raw.rename(columns=RENAMES)
    for column in BOOLEAN_COLUMNS:
        values = set(sku[column])
        if not values <= {"True", "False"}:
            raise ValueError(f"catalog column {column} has non-boolean values: {sorted(values)}")
        sku[column] = (sku[column] == "True").astype(int)
        transforms.append(f"{column} True/False->1/0")
    sku["unit_price"] = sku["unit_price"].astype(float)
    sku["return_window_days"] = sku["return_window_days"].astype(int)
    sku = sku[SKU_COLUMNS].sort_values("sku", kind="stable").reset_index(drop=True)
    if sku["sku"].duplicated().any():
        raise ValueError("catalog has duplicate SKUs")
    if (sku["unit_price"] * 100 % 1 != 0).any():
        raise ValueError("catalog prices must be whole paise")

    launch = pd.to_datetime(sku["launch_date"]).to_numpy().astype("datetime64[D]")
    styles = (sku.assign(launch=launch)
              .groupby("style_id", sort=True)
              .agg(category=("category", "first"), median_price=("unit_price", "median"),
                   is_occasion_wear=("is_occasion_wear", "max"), first_launch=("launch", "min"), skus=("sku", "size"))
              .reset_index())
    style_index = {s: i for i, s in enumerate(styles["style_id"])}
    reasons = pd.read_csv(Path(spec_root) / "assets" / "reason_codes.csv", dtype=str, keep_default_na=False)
    reasons[["requires_item_return", "is_high_risk"]] = reasons[["requires_item_return", "is_high_risk"]].astype(int)
    return Catalog(
        sku_master=sku, styles=styles, reason_code=reasons[REASON_COLUMNS],
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), transforms=transforms,
        sku_style=sku["style_id"].map(style_index).to_numpy(),
        sku_price_paise=np.rint(sku["unit_price"].to_numpy() * 100).astype(np.int64),
        sku_window=sku["return_window_days"].to_numpy(), sku_launch=launch,
        sku_occasion=sku["is_occasion_wear"].to_numpy().astype(bool),
        sku_size=sku["size"].to_numpy(dtype=object), sku_colour=sku["colour"].to_numpy(dtype=object),
    )
