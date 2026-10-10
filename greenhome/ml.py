"""India-first energy models, grouped evaluation, and an honest physics fallback.

Bundled household labels are synthetic. Underlying electricity demand is learned
before solar; LPG and PNG stay separate. Retrofit effects use the scenario engine.
"""
from __future__ import annotations
import hashlib
import json
import math
import platform
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits
from .physics import (FABRIC_FACTOR, GLAZING_FACTOR, INPUT_RANGES, climate_parameters,
                      complete_home, electricity_balance, expected_end_uses, validate_home)
from .schema import CATEGORICAL_FEATURES, DEFAULT_HOME, FEATURES, NUMERIC_FEATURES, OPTIONS, TARGETS

ORIGIN = "synthetic_india_physics_v2"
PHYSICS_FEATURES = [f"physics_{target}" for target in TARGETS]
CLIMATE_FEATURES = ["climate_cooling_degree_hours", "climate_annual_ghi_kwh_m2", "climate_pv_yield_kwh_per_kw_year"]
ENGINEERED_FEATURES = CLIMATE_FEATURES + PHYSICS_FEATURES
INTERVAL_LEVEL = 0.90
LEARNED_NAMES = ["random_forest", "extra_trees", "hist_gradient_boosting", "residual_hist_gradient_boosting"]
MODEL_NAMES = ["physics_baseline", "mean_baseline"] + LEARNED_NAMES


class PhysicsFeatureBuilder(TransformerMixin, BaseEstimator):
    """Compute weather/physical features from X only; never access label columns."""
    def fit(self, X: pd.DataFrame, y: Any = None) -> "PhysicsFeatureBuilder":
        self.feature_names_in_ = np.asarray(FEATURES, dtype=object)
        self.n_features_in_ = len(FEATURES)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        homes = [complete_home(row) for row in X.to_dict("records")]
        result = pd.DataFrame(homes, index=X.index)[FEATURES]
        physics = [expected_end_uses(row) for row in homes]
        climate = [climate_parameters(row) for row in homes]
        for name in CLIMATE_FEATURES:
            result[name] = [float(row[name.removeprefix("climate_")]) for row in climate]
        for target in TARGETS:
            result[f"physics_{target}"] = [float(row[target]) for row in physics]
        return result

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return np.asarray(FEATURES + ENGINEERED_FEATURES, dtype=object)


class PhysicsColumnRegressor(RegressorMixin, BaseEstimator):
    """Zero-fit physical comparator, eligible when it beats learned models."""
    def __init__(self, target: str):
        self.target = target

    def fit(self, X: pd.DataFrame, y: Any = None) -> "PhysicsColumnRegressor":
        self.n_features_in_ = X.shape[1]
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X[f"physics_{self.target}"].to_numpy(dtype=float)


class ResidualBoostedRegressor(RegressorMixin, BaseEstimator):
    """Learn relative corrections to the physical estimate on training only."""
    def __init__(self, baseline_column: int, random_state: int = 42):
        self.baseline_column = baseline_column
        self.random_state = random_state

    def fit(self, X: Any, y: Any) -> "ResidualBoostedRegressor":
        values = np.asarray(X, dtype=float)
        baseline = values[:, self.baseline_column]
        residual = (np.asarray(y, dtype=float) - baseline) / np.maximum(100.0, baseline)
        self.estimator_ = HistGradientBoostingRegressor(max_iter=140, max_leaf_nodes=15,
            learning_rate=0.06, l2_regularization=2.0, min_samples_leaf=30, random_state=self.random_state)
        self.estimator_.fit(values, residual)
        self.n_features_in_ = values.shape[1]
        return self

    def predict(self, X: Any) -> np.ndarray:
        values = np.asarray(X, dtype=float)
        baseline = values[:, self.baseline_column]
        return baseline + self.estimator_.predict(values) * np.maximum(100.0, baseline)


def _preprocessing() -> ColumnTransformer:
    return ColumnTransformer([
        ("numeric", "passthrough", NUMERIC_FEATURES + ENGINEERED_FEATURES),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
    ], remainder="drop", verbose_feature_names_out=False)


def _pipeline(estimator: Any) -> Pipeline:
    return Pipeline([("physics_features", PhysicsFeatureBuilder()), ("preprocess", _preprocessing()), ("regressor", estimator)])


def _physics_pipeline(target: str) -> Pipeline:
    return Pipeline([("physics_features", PhysicsFeatureBuilder()), ("regressor", PhysicsColumnRegressor(target))])


def _structural_zero(frame: pd.DataFrame, target: str) -> np.ndarray:
    fuel = {"annual_lpg_kwh": "lpg", "annual_png_kwh": "png"}.get(target)
    return ~frame.cooking_fuel.eq(fuel).to_numpy() if fuel else np.zeros(len(frame), dtype=bool)


def _predictions(model: Pipeline, frame: pd.DataFrame, target: str) -> np.ndarray:
    prediction = np.maximum(0.0, model.predict(frame[FEATURES]))
    return np.where(_structural_zero(frame, target), 0.0, prediction)


def _metric(y: Any, prediction: Any) -> dict[str, Any]:
    actual, pred = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    if not len(actual):
        return {"n": 0, "mae_kwh": None, "rmse_kwh": None, "r2": None, "wape": None}
    denominator = float(np.abs(actual).sum())
    return {"n": len(actual), "mae_kwh": float(mean_absolute_error(actual, pred)),
        "rmse_kwh": float(np.sqrt(mean_squared_error(actual, pred))),
        "r2": float(r2_score(actual, pred)) if len(actual) > 1 and np.ptp(actual) > 1e-9 else None,
        "wape": float(np.abs(actual - pred).sum() / denominator) if denominator > 1e-9 else None}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _number(rng: np.random.Generator, value: float, sigma: float, low: float, high: float) -> float:
    return float(np.clip(rng.normal(value, sigma), low, high))


def generate_dataset(n: int = 12000, seed: int = 42) -> pd.DataFrame:
    """Correlated Indian demo homes; measured weather is separate from invented bills."""
    if not isinstance(n, int) or n < 200:
        raise ValueError("Generate at least 200 rows for four disjoint grouped partitions.")
    rng, records = np.random.default_rng(seed), []
    city_weights = [0.48, 0.10, 0.08, 0.08, 0.08, 0.06, 0.05, 0.07]
    for group_index in range(math.ceil(n / 4)):
        city = str(rng.choice(OPTIONS["city"], p=city_weights))
        property_type = str(rng.choice(OPTIONS["property_type"], p=[0.32, 0.18, 0.50]))
        area_mean = float(np.clip(rng.lognormal(np.log({"independent": 115, "row_house": 90, "apartment": 80}[property_type]), 0.29), 35, 250))
        insulation = str(rng.choice(OPTIONS["insulation"], p=[0.38, 0.42, 0.20]))
        glazing = str(rng.choice(OPTIONS["glazing"], p=[0.84, 0.16] if insulation == "poor" else [0.65, 0.35]))
        electric_noise, cooking_noise = rng.lognormal(-0.5 * 0.08**2, 0.08), rng.lognormal(-0.5 * 0.07**2, 0.07)
        for household_index in range(4):
            index = len(records)
            if index >= n:
                break
            area = round(_number(rng, area_mean, area_mean * 0.045, 35, 250), 1)
            occupants = int(np.clip(rng.poisson(2.1 + area / 140) + 1, 1, 8))
            fans_only = 0.50 if city in ("Bengaluru", "Pune") else 0.26
            cooling = str(rng.choice(OPTIONS["cooling"], p=[fans_only, (1 - fans_only) * 0.64, (1 - fans_only) * 0.36]))
            units = 0 if cooling == "fans_only" else int(np.clip(round(area / 55 + rng.normal(0, 0.55)), 1, 5))
            roof_access = bool(property_type != "apartment" or rng.random() < 0.25)
            hot_water = str(rng.choice(OPTIONS["hot_water"], p=[0.55, 0.13, 0.04, 0.28]))
            png_probability = 0.25 if city in ("Delhi", "Mumbai", "Pune") else 0.07
            cooking = str(rng.choice(["lpg", "png", "induction"], p=[0.85 - png_probability, png_probability, 0.15]))
            home = dict(DEFAULT_HOME)
            home.update({
                "area_m2": area, "occupants": occupants, "city": city, "property_type": property_type,
                "insulation": insulation, "glazing": glazing, "cooling": cooling, "ac_units": units,
                "ac_hours_per_day": 0.0 if not units else round(float(np.clip(rng.gamma(2.4, 2.2), 0.5, 16)), 1),
                "led_fraction": round(float(rng.beta(3.0 if insulation != "poor" else 2.0, 1.6)), 2),
                "smart_controls": bool(rng.random() < (0.52 if cooling == "ac_efficient" else 0.28)),
                "hot_water": hot_water, "cooking_fuel": cooking, "roof_access": roof_access,
                "solar_kw": round(float(rng.uniform(1, min(8, max(1.1, area / 13)))), 2) if roof_access and rng.random() < 0.18 else 0.0,
                "ac_capacity_ton": round(_number(rng, 1.5 if area > 80 else 1.1, 0.20, 0.75, 2.5), 2),
                "ac_iseer": round(_number(rng, 5.1 if cooling == "ac_efficient" else 3.4, 0.40, 2.5, 6.5), 2),
                "setpoint_c": round(_number(rng, 25.5, 1.4, 22, 30), 1),
                "roof_u_value": round(_number(rng, {"poor": 2.8, "average": 1.5, "good": 0.55}[insulation], 0.17, 0.2, 4), 2),
                "roof_exposed_fraction": float(property_type != "apartment" or household_index == 0),
                "wall_u_value": round(_number(rng, {"poor": 2.1, "average": 1.45, "good": 0.75}[insulation], 0.13, 0.3, 3.5), 2),
                "window_to_wall_ratio": round(_number(rng, 0.23, 0.055, 0.1, 0.5), 2),
                "window_shgc": round(_number(rng, 0.43 if glazing == "double" else 0.75, 0.05, 0.2, 0.9), 2),
                "window_shading_fraction": round(float(rng.beta(2.0, 3.0) * 0.9), 2),
                "fan_count": int(np.clip(round(area / 29 + rng.normal(0, 0.5)), 1, 10)),
                "fan_power_w": round(_number(rng, 30 if rng.random() < 0.35 else 67, 4.5, 20, 90), 1),
                "fan_hours_per_day": round(_number(rng, 8 if city in ("Bengaluru", "Pune") else 12, 2.0, 0, 24), 1),
                "lighting_hours_per_day": round(_number(rng, 4.5, 1.0, 1, 12), 1),
                "hot_water_litres_per_person_day": 0.0 if hot_water == "none" else round(_number(rng, 18 if city in ("Delhi", "Bengaluru", "Pune") else 12, 4, 0, 50), 1),
                "appliance_kwh_per_day": round(float(np.clip((1.0 + 0.62 * occupants + 0.012 * area) * rng.lognormal(-0.5 * 0.17**2, 0.17), 0.5, 12)), 2),
            })
            home = complete_home(home)
            problems = validate_home(home)
            if problems:
                raise ValueError("Invalid generated home: " + "; ".join(problems))
            reference, labels = expected_end_uses(home), {}
            for target in TARGETS:
                shared = electric_noise if target == "annual_electricity_demand_kwh" else cooking_noise
                sigma = 0.10 if target == "annual_electricity_demand_kwh" else 0.12
                labels[target] = round(max(0.0, float(reference[target]) * shared * float(rng.lognormal(-0.5 * sigma**2, sigma))), 2)
            row = {"home_id": f"SYN2-{seed}-{index:06d}", "group_id": f"BLDG-{seed}-{group_index:05d}"}
            row.update({feature: home[feature] for feature in FEATURES})
            row.update({"solar_kw": home["solar_kw"], "roof_access": roof_access, **labels})
            row.update(electricity_balance(home, labels["annual_electricity_demand_kwh"]))
            row["annual_gas_kwh"] = labels["annual_lpg_kwh"] + labels["annual_png_kwh"]
            row.update({f"reference_{key}": round(float(value), 3) for key, value in reference.items()
                        if isinstance(value, (int, float, np.number)) and np.isfinite(value)})
            row["data_origin"] = ORIGIN
            records.append(row)
    return pd.DataFrame(records)


def load_training_csv(csv_path: Path, provenance_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate declared external annual observations; never silently invent labels."""
    provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    if "licence" in provenance and "license" not in provenance:
        provenance["license"] = provenance["licence"]
    required = ["data_kind", "source", "license", "units", "geographic_scope"]
    missing = [key for key in required if not provenance.get(key)]
    if missing:
        raise ValueError("Provenance manifest missing: " + ", ".join(missing))
    if provenance["data_kind"] not in ("measured", "synthetic") or provenance["units"] != "kWh/year":
        raise ValueError("Declare data_kind measured|synthetic and units kWh/year.")
    if provenance["data_kind"] == "measured":
        for name in ("measurement_start", "measurement_end", "target_definitions"):
            if not provenance.get(name):
                raise ValueError(f"Measured provenance requires {name}.")
        start, end = pd.Timestamp(provenance["measurement_start"]), pd.Timestamp(provenance["measurement_end"])
        if (end - start).days + 1 not in (365, 366):
            raise ValueError("Measured labels require a complete 365/366-day interval, not annualized partial bills.")
        if set(provenance["target_definitions"]) != set(TARGETS):
            raise ValueError("Declare measured definitions for electricity demand, LPG and PNG separately.")
    elif not provenance.get("label_rule_version"):
        raise ValueError("Synthetic CSV provenance requires label_rule_version.")
    frame = pd.read_csv(csv_path)
    columns = ["home_id", "group_id"] + FEATURES + TARGETS
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError("CSV missing explicit fields: " + ", ".join(missing) + ". Grid imports cannot substitute for electricity demand.")
    if len(frame) < 200 or frame.group_id.nunique() < 30:
        raise ValueError("Need at least 200 annual rows and 30 independent household/building groups.")
    if frame[columns].isna().any().any() or not frame.home_id.is_unique:
        raise ValueError("Required fields must be complete; home_id unique per row; group_id joins repeated households/buildings.")
    if provenance["data_kind"] == "measured" and "data_origin" in frame and frame.data_origin.astype(str).str.contains("synthetic", case=False).any():
        raise ValueError("Synthetic rows cannot be declared measured data.")
    for target in TARGETS:
        frame[target] = pd.to_numeric(frame[target], errors="raise")
        if not np.isfinite(frame[target]).all() or (frame[target] < 0).any():
            raise ValueError(f"{target} must contain finite nonnegative annual labels.")
        if (frame.loc[_structural_zero(frame, target), target] > 1e-6).any():
            raise ValueError(f"{target} conflicts with the declared cooking fuel.")
    for index, row in frame.iterrows():
        problems = validate_home(row.to_dict())
        if problems:
            raise ValueError(f"Invalid row {index}: " + "; ".join(problems))
    frame["data_origin"] = provenance["data_kind"] + "_csv_declared"
    if "solar_kw" not in frame:
        frame["solar_kw"] = 0.0
        provenance["solar_accounting_limitation"] = "PV capacity absent: evaluate demand and cooking targets only."
    return frame, provenance


def _split_groups(frame: pd.DataFrame, seed: int, root: Path, fingerprint: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    path = root / "data" / "split_manifest.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if previous.get("dataset_sha256") == fingerprint:
        groups = set(previous["frozen_test_group_ids"])
        mask = frame.group_id.isin(groups)
        test, remaining, reused = frame.loc[mask], frame.loc[~mask], True
    else:
        a, b = next(GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=seed).split(frame, groups=frame.group_id))
        remaining, test, reused = frame.iloc[a], frame.iloc[b], False
        groups = set(test.group_id)
    a, b = next(GroupShuffleSplit(n_splits=1, test_size=0.15 / 0.80, random_state=seed + 1).split(remaining, groups=remaining.group_id))
    train_cal, validation = remaining.iloc[a], remaining.iloc[b]
    a, b = next(GroupShuffleSplit(n_splits=1, test_size=0.15 / 0.65, random_state=seed + 2).split(train_cal, groups=train_cal.group_id))
    parts = {"train": train_cal.iloc[a].copy(), "validation": validation.copy(), "calibration": train_cal.iloc[b].copy(), "test": test.copy()}
    assignments = pd.concat([part[["home_id", "group_id"]].assign(split=name) for name, part in parts.items()])
    assignments.sort_values("home_id").to_csv(root / "data" / "split_assignments.csv", index=False)
    manifest = {"dataset_sha256": fingerprint, "seed": seed, "frozen_test_group_ids": sorted(groups),
        "test_reused_for_same_dataset": reused,
        "method": "GroupShuffleSplit approximately 50/15/15/20 train/validation/calibration/test by group; seed, seed+1, seed+2.",
        "row_counts": {name: len(part) for name, part in parts.items()},
        "group_counts": {name: int(part.group_id.nunique()) for name, part in parts.items()}}
    _write_json(path, manifest)
    return parts, manifest


def _calibration_representatives(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 101)
    return pd.DataFrame([part.iloc[int(rng.integers(len(part)))] for _, part in frame.groupby("group_id", sort=True)]).reset_index(drop=True)


def _fit_interval(y: Any, prediction: Any) -> dict[str, Any]:
    actual, pred = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    scores = np.abs(actual - pred) / np.maximum(100.0, pred)
    rank = math.ceil((len(scores) + 1) * INTERVAL_LEVEL)
    if rank > len(scores) or not len(scores):
        raise ValueError("At least 9 independent active calibration groups are required for a finite 90% conformal interval.")
    return {"relative_radius": float(np.sort(scores)[rank - 1]), "calibration_n": len(scores),
            "quantile_level": rank / len(scores), "order_statistic_rank": rank}


def _interval_bounds(prediction: Any, radius: float, zero: Any = None) -> tuple[np.ndarray, np.ndarray]:
    pred = np.asarray(prediction, dtype=float)
    delta = float(radius) * np.maximum(100.0, pred)
    lower, upper = np.maximum(0.0, pred - delta), pred + delta
    if zero is not None:
        lower, upper = np.where(zero, 0.0, lower), np.where(zero, 0.0, upper)
    return lower, upper


def _interval_metrics(frame: pd.DataFrame, target: str, lower: np.ndarray, upper: np.ndarray) -> dict[str, Any]:
    actual = frame[target].to_numpy()
    covered = (actual >= lower) & (actual <= upper)
    averages = pd.DataFrame({"group": frame.group_id.to_numpy(), "covered": covered}).groupby("group").covered.mean()
    active = ~_structural_zero(frame, target)
    return {"nominal_coverage": INTERVAL_LEVEL, "row_coverage": float(covered.mean()), "group_weighted_coverage": float(averages.mean()),
        "mean_width_kwh": float(np.mean(upper - lower)), "active_n": int(active.sum()),
        "active_coverage": float(covered[active].mean()) if active.any() else None,
        "active_mean_width_kwh": float(np.mean((upper - lower)[active])) if active.any() else None}


def _subgroups(frame: pd.DataFrame, target: str, prediction: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> list[dict[str, Any]]:
    dimensions = {key: frame[key].astype(str) for key in ("city", "cooling", "cooking_fuel", "property_type")}
    dimensions["solar"] = pd.Series(np.where(frame.solar_kw > 0, "installed", "none"), index=frame.index)
    records, actual = [], frame[target].to_numpy()
    for dimension, values in dimensions.items():
        for value in sorted(values.unique()):
            mask = values.eq(value).to_numpy()
            records.append({"target": target, "dimension": dimension, "value": value, **_metric(actual[mask], prediction[mask]),
                "coverage": float(((actual[mask] >= lower[mask]) & (actual[mask] <= upper[mask])).mean()),
                "mean_interval_width_kwh": float(np.mean((upper - lower)[mask]))})
    return records


def _stress_audit(frame: pd.DataFrame, selected: dict[str, Pipeline], intervals: dict[str, Any]) -> dict[str, Any]:
    sample = frame.head(400).copy()
    result: dict[str, Any] = {"interpretation": "Sensitivity and drift diagnostics only. Counterfactual truth is assumed physics, not measured climate or retrofit outcomes.", "cases": {}}
    high_use = sample.copy()
    high_use["ac_hours_per_day"] = np.where(high_use.cooling.eq("fans_only"), 0.0, 16.0)
    high_use["setpoint_c"] = 22.0
    envelope = sample.copy()
    envelope["roof_u_value"], envelope["wall_u_value"] = np.clip(envelope.roof_u_value * 1.50, 0.2, 4.0), np.clip(envelope.wall_u_value * 1.30, 0.3, 3.5)
    for name, stress in {"high_ac_hours_and_low_setpoint": high_use, "weaker_envelope": envelope}.items():
        reference = [expected_end_uses(row) for row in stress[FEATURES].to_dict("records")]
        result["cases"][name] = {target: _metric([row[target] for row in reference], _predictions(selected[target], stress, target)) for target in TARGETS}
    drift = {}
    for target in TARGETS:
        prediction = _predictions(selected[target], sample, target)
        low, high = _interval_bounds(prediction, intervals[target]["relative_radius"], _structural_zero(sample, target))
        shifted, active = sample[target].to_numpy() * 1.35, ~_structural_zero(sample, target)
        drift[target] = {**_metric(shifted, prediction), "active_coverage_under_unobserved_35_percent_shift": float(((shifted >= low) & (shifted <= high))[active].mean()) if active.any() else None}
    result["cases"]["unobserved_35_percent_usage_shift"] = drift
    result["ood_rejection_examples"] = {"area_m2_300": "Rejected by supported input bounds.", "unknown_city": "Rejected until weather/schema are documented."}
    return result


def _monotonicity_audit(frame: pd.DataFrame, model: Pipeline) -> dict[str, Any]:
    sample, checks = frame.head(400).copy(), {}
    baseline = _predictions(model, sample, "annual_electricity_demand_kwh")
    for feature, amount, maximum in (("led_fraction", 0.20, 1.0), ("ac_iseer", 0.50, 6.5), ("window_shading_fraction", 0.10, 0.90)):
        changed = sample.copy()
        changed[feature] = np.minimum(maximum, changed[feature] + amount)
        after = _predictions(model, changed, "annual_electricity_demand_kwh")
        checks[feature] = {"n": len(sample), "unexpected_demand_increases": int((after > baseline + 1e-6).sum()), "mean_demand_change_kwh": float((after - baseline).mean())}
    return {"interpretation": "Directional prediction consistency, not causal savings.", "checks": checks,
            "solar_invariance": "solar_kw excluded from model FEATURES: installed PV changes imports, not predicted dwelling demand."}


def train_models(root: Path, n: int = 12000, seed: int = 42, data_csv: Path | None = None, provenance_json: Path | None = None) -> dict[str, Any]:
    """Train candidates; select validation; calibrate separately; report frozen test."""
    root = Path(root)
    for folder in ("data", "models", "models/candidates", "reports"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    if data_csv is not None:
        if provenance_json is None:
            raise ValueError("--data-csv requires --provenance-json.")
        frame, provenance = load_training_csv(Path(data_csv), Path(provenance_json))
    else:
        frame = generate_dataset(n=n, seed=seed)
        provenance = {"data_kind": "synthetic", "source": "greenhome.ml.generate_dataset + greenhome.physics",
            "license": "Generated synthetic data; no separate owner licence declared", "units": "kWh/year",
            "geographic_scope": "Hyderabad-first synthetic Indian homes", "label_rule_version": ORIGIN, "measured_household_count": 0}
    csv = frame.to_csv(index=False, lineterminator="\n")
    fingerprint = hashlib.sha256(csv.encode("utf-8")).hexdigest()
    (root / "data" / "training_homes.csv").write_bytes(csv.encode("utf-8"))
    if provenance["data_kind"] == "synthetic":
        (root / "data" / "synthetic_homes.csv").write_bytes(csv.encode("utf-8"))
    _write_json(root / "data" / "provenance.json", provenance)
    parts, split = _split_groups(frame, seed, root, fingerprint)
    train, validation, calibration, test = (parts[name] for name in ("train", "validation", "calibration", "test"))
    representatives = _calibration_representatives(calibration, seed)
    representatives[["home_id", "group_id"]].to_csv(root / "data" / "calibration_representatives.csv", index=False)
    metrics: dict[str, Any] = {"version": "2.0", "data_origin": str(frame.data_origin.iloc[0]), "provenance": provenance,
        "seed": seed, "n_rows": len(frame), "dataset_sha256": fingerprint, "features": FEATURES, "engineered_features": ENGINEERED_FEATURES, "targets": TARGETS,
        "split_counts": split["row_counts"], "split_group_counts": split["group_counts"], "split_method": split["method"], "frozen_test_reused": split["test_reused_for_same_dataset"],
        "selection_rule": "Lowest validation MAE among physics, training mean with known fuel-absence gate, RF, ExtraTrees, HistGB, residual HistGB. Unconditional mean is an additional comparator. Calibration/test do not select candidates.",
        "supported_input_ranges": INPUT_RANGES, "supported_categories": OPTIONS, "interval_level": INTERVAL_LEVEL,
        "interval_method": "Relative split conformal |y-pred|/max(pred,100), finite-sample90%quantile; one label-independent random representative per calibration group; absent fuels[0,0].",
        "interval_limits": "Marginal exchangeability of independent group representatives required; row/subgroup/drift coverage not guaranteed.",
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__, "joblib": joblib.__version__},
        "code_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() for name in ("ml.py", "physics.py", "schema.py")},
        "target_units": {"annual_electricity_demand_kwh": "dwelling electricity demand before solar,kWh/year", "annual_lpg_kwh": "LPG input energy,kWh/year", "annual_png_kwh": "PNG input energy,kWh/year"},
        "models": {}, "limitations": ["Bundled household labels are synthetic; no nationwide accuracy or causal retrofit claim follows.",
            "Physics is also the generator conditional mean; its expected advantage does not establish real superiority.",
            "Real CSV features must be observed, with declared provenance; source metadata requires independent audit.",
            "No property-sale labels/value uplift are invented; aggregate gas is a compatibility LPG+PNG energy sum."]}
    selected_models, interval_info, subgroup_rows, settings = {}, {}, [], {}
    held = test[["home_id", "group_id"] + FEATURES + ["solar_kw"] + TARGETS].copy()
    with threadpool_limits(limits=4):
        for index, target in enumerate(TARGETS):
            candidates = {"mean_baseline": _pipeline(DummyRegressor(strategy="mean")), "physics_baseline": _physics_pipeline(target),
                "random_forest": _pipeline(RandomForestRegressor(n_estimators=96, max_depth=16, min_samples_leaf=4, n_jobs=4, random_state=seed)),
                "extra_trees": _pipeline(ExtraTreesRegressor(n_estimators=96, max_depth=18, min_samples_leaf=3, n_jobs=4, random_state=seed)),
                "hist_gradient_boosting": _pipeline(HistGradientBoostingRegressor(max_iter=160, max_leaf_nodes=15, learning_rate=0.06, l2_regularization=2.0, min_samples_leaf=30, random_state=seed)),
                "residual_hist_gradient_boosting": _pipeline(ResidualBoostedRegressor(len(NUMERIC_FEATURES) + len(CLIMATE_FEATURES) + index, seed))}
            comparison = {}
            for name, pipeline in candidates.items():
                pipeline.fit(train[FEATURES], train[target])
                pred = _predictions(pipeline, validation, target)
                comparison[name] = {"validation": _metric(validation[target], pred)}
                if not index:
                    settings[name] = {key: value for key, value in pipeline.named_steps["regressor"].get_params(deep=False).items() if isinstance(value, (str, int, float, bool, type(None)))}
            chosen = min(MODEL_NAMES, key=lambda name: comparison[name]["validation"]["mae_kwh"])
            learned = min(LEARNED_NAMES, key=lambda name: comparison[name]["validation"]["mae_kwh"])
            comparison["unconditional_mean_comparator"] = {"validation": _metric(validation[target], np.maximum(0, candidates["mean_baseline"].predict(validation[FEATURES])))}
            selected = candidates[chosen]
            selected_models[target] = selected
            cal_pred = _predictions(selected, representatives, target)
            active_cal = ~_structural_zero(representatives, target)
            cal_info = _fit_interval(representatives.loc[active_cal, target], cal_pred[active_cal])
            if cal_info["relative_radius"] is None:
                raise ValueError(f"No independent active calibration groups for {target}; add examples before estimating intervals.")
            interval_info[target] = cal_info
            val_pred, test_pred = _predictions(selected, validation, target), _predictions(selected, test, target)
            low, high = _interval_bounds(test_pred, cal_info["relative_radius"], _structural_zero(test, target))
            info = {"selected": chosen, "best_learned": learned, "candidates": comparison,
                "validation": _metric(validation[target], val_pred), "test": _metric(test[target], test_pred),
                "calibration": cal_info, "test_intervals": _interval_metrics(test, target, low, high),
                "active_fuel_test": _metric(test.loc[~_structural_zero(test, target), target], test_pred[~_structural_zero(test, target)])}
            for name in ("mean_baseline", "physics_baseline"):
                baseline = _predictions(candidates[name], test, target)
                comparison[name]["test"] = _metric(test[target], baseline)
                held[f"{name}_{target}"] = np.round(baseline, 4)
            comparison["unconditional_mean_comparator"]["test"] = _metric(test[target], np.maximum(0, candidates["mean_baseline"].predict(test[FEATURES])))
            held[f"predicted_{target}"] = np.round(test_pred, 4)
            held[f"interval_low_{target}"], held[f"interval_high_{target}"] = np.round(low, 4), np.round(high, 4)
            subgroup_rows.extend(_subgroups(test, target, test_pred, low, high))
            metrics["models"][target] = info
            joblib.dump(selected, root / "models" / f"{target}.joblib", compress=3)
            joblib.dump(candidates[learned], root / "models" / "candidates" / f"{target}__best_learned.joblib", compress=3)
        metrics["candidate_settings"] = settings
        metrics["stress_tests"] = _stress_audit(test, selected_models, interval_info)
        metrics["monotonicity"] = _monotonicity_audit(test, selected_models["annual_electricity_demand_kwh"])
    balances = [electricity_balance(row, demand) for row, demand in zip(held.to_dict("records"), held.predicted_annual_electricity_demand_kwh)]
    for key in balances[0]:
        held[f"predicted_{key}"] = [round(float(row[key]), 4) for row in balances]
    held["predicted_annual_gas_kwh"] = held.predicted_annual_lpg_kwh + held.predicted_annual_png_kwh
    held.sort_values("home_id").to_csv(root / "reports" / "held_out_predictions.csv", index=False)
    pd.DataFrame(subgroup_rows).to_csv(root / "reports" / "subgroup_metrics.csv", index=False)
    _write_json(root / "reports" / "stress_tests.json", metrics["stress_tests"])
    _write_json(root / "reports" / "monotonicity.json", metrics["monotonicity"])
    metrics["training_feature_distribution"] = {feature: {"min": float(train[feature].min()), "p01": float(train[feature].quantile(0.01)), "p99": float(train[feature].quantile(0.99)), "max": float(train[feature].max())} for feature in NUMERIC_FEATURES}
    _write_json(root / "reports" / "metrics.json", metrics)
    _write_json(root / "models" / "metadata.json", metrics)
    (root / "reports" / "data_generation.md").write_text(DATA_GENERATION_DOCUMENTATION, encoding="utf-8")
    (root / "reports" / "training_report.md").write_text(_training_report(metrics), encoding="utf-8")
    return metrics


def _training_report(metrics: dict[str, Any]) -> str:
    rows, tests = [], []
    for target, info in metrics["models"].items():
        for name, detail in info["candidates"].items():
            m = detail["validation"]
            r2 = 'NA' if m['r2'] is None else f"{m['r2']:.3f}"
            rows.append(f"|{target}|{name}|{m['mae_kwh']:.1f}|{m['rmse_kwh']:.1f}|{r2}|")
        m, coverage = info["test"], info["test_intervals"]
        r2 = 'NA' if m['r2'] is None else f"{m['r2']:.3f}"
        cov = 'NA' if coverage['active_coverage'] is None else f"{coverage['active_coverage']:.1%}"
        width = 'NA' if coverage['active_mean_width_kwh'] is None else f"{coverage['active_mean_width_kwh']:.1f}"
        tests.append(f"|{target}|{info['selected']}|{m['mae_kwh']:.1f}|{r2}|{cov}|{width}|")
    return (f"# India-first model evaluation v2\n\nData: **{metrics['data_origin']}**, {metrics['n_rows']:,} rows. "
        f"Group-disjoint row counts: {metrics['split_counts']}; group counts: {metrics['split_group_counts']}. "
        "Assignments and dataset SHA-256 are saved. Test groups stay frozen for an identical dataset.\n\n"
        "## Validation comparison\n\n|Target|Candidate|MAE kWh/year|RMSE kWh/year|R²|\n|---|---|---:|---:|---:|\n" + "\n".join(rows) + "\n\n"
        "Candidates/preprocessing fit training only; validation MAE selects physics or the learned candidate. "
        "Calibration and test never select candidates. No final refit uses those partitions. "
        "Selected and best learned pipelines are retained. Mean with a known fuel-absence gate is eligible; unconditional mean is an additional simple comparator.\n\n"
        "## Frozen held-out test and uncertainty\n\n|Target|Selected|Test MAE kWh/year|Test R²|Active 90%coverage|Active width kWh/year|\n|---|---|---:|---:|---:|---:|\n" + "\n".join(tests) + "\n\n"
        "Calibration uses one label-independent random representative per building/household group. "
        "Scores=|actual−prediction|/max(prediction,100); finite-sample90%split-conformal quantile establishes bounds. "
        "Structurally absent fuels have[0,0]intervals. Marginal exchangeable-group coverage does not guarantee each house, "
        "subgroup, correlated row or future drift. Row/group-weighted empirical coverage and active-fuel widths are recorded.\n\n"
        "## Accounting and limits\n\nElectricity demand precedes solar. Solar_kw is excluded from X. "
        "Shared accounting preserves demand=grid+self-consumption and PVgeneration=self-consumption+export. "
        "LPG/PNG remain separate; annual_gas_kwh is their compatibility energy sum.\n\n"
        "The physical comparator is also the synthetic generator conditional mean, so its advantage is expected. "
        "Synthetic accuracy does not establish real Indian bill or causal retrofit accuracy. "
        "Weather/solar sources do not turn invented household labels into measured bills. "
        "See subgroup_metrics.csv, stress_tests.json,monotonicity.json. Counterfactual stress truth is assumed physics; "
        "the unobserved35%usage shift deliberately exposes coverage deterioration. No property-sale uplift is fabricated. "
        "External CSV training requires observed full-year demand/LPG/PNG targets, observed input fields, group IDs and declared provenance; "
        "supplier declarations require independent audit.\n")


def load_models(root: Path) -> dict[str, Any]:
    """Load trusted local artifacts only; joblib/pickle files execute code."""
    root = Path(root)
    result = {target: joblib.load(root / "models" / f"{target}.joblib") for target in TARGETS}
    result["_metadata"] = json.loads((root / "models" / "metadata.json").read_text(encoding="utf-8"))
    return result


def _validated_home(home: dict[str, Any]) -> pd.DataFrame:
    problems = validate_home(home)
    if problems:
        raise ValueError("; ".join(problems))
    completed = complete_home(home)
    return pd.DataFrame([{feature: completed[feature] for feature in FEATURES}], columns=FEATURES)


def predict_energy(home: dict[str, Any], models: dict[str, Any]) -> dict[str, float]:
    """Predict demand/fuels, then calculate imports, self-use and exports."""
    frame = _validated_home(home)
    completed = complete_home(home)
    with threadpool_limits(limits=4):
        result = {target: float(_predictions(models[target], frame, target)[0]) for target in TARGETS}
    result.update({key: float(value) for key, value in electricity_balance(completed, result["annual_electricity_demand_kwh"]).items()})
    result["annual_gas_kwh"] = result["annual_lpg_kwh"] + result["annual_png_kwh"]
    return result


def prediction_intervals(home: dict[str, Any], energy: dict[str, float], models: dict[str, Any]) -> dict[str, list[float]]:
    """90% calibration ranges, with compatibility grid and aggregate-gas aliases."""
    frame, intervals = _validated_home(home), {}
    completed = complete_home(home)
    for target in TARGETS:
        radius = models["_metadata"]["models"][target]["calibration"]["relative_radius"]
        low, high = _interval_bounds([energy[target]], radius, _structural_zero(frame, target))
        intervals[target] = [float(low[0]), float(high[0])]
    intervals["annual_grid_kwh"] = [float(electricity_balance(completed, value)["annual_grid_kwh"]) for value in intervals["annual_electricity_demand_kwh"]]
    intervals["annual_gas_kwh"] = [intervals["annual_lpg_kwh"][i] + intervals["annual_png_kwh"][i] for i in range(2)]
    return intervals


def input_diagnostics(home: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    """Training-only marginal rarity flags, not a multivariate OOD guarantee."""
    errors = validate_home(home)
    if errors:
        return {"supported": False, "errors": errors, "rare_training_features": []}
    completed, rare = complete_home(home), []
    for feature, distribution in models["_metadata"].get("training_feature_distribution", {}).items():
        value = completed.get(feature)
        if isinstance(value, (int, float)) and (value < distribution["p01"] or value > distribution["p99"]):
            rare.append(feature)
    return {"supported": not errors, "errors": errors, "rare_training_features": rare}


DATA_GENERATION_DOCUMENTATION = """# V2 synthetic Indian-home data and label rules

All bundled household energy labels and behavioral distributions are synthetic. No real annual bills are fabricated.
Weather/solar caches contain separately sourced physical inputs. Sources and parameters live in physics.py and the source-evidence report;
using measured weather does not make the simulated household labels measured or validate this end-use simulator.

## Correlated sampling

Default12,000rows,seed42,four-household building/archetype groups. City probabilities in schema order:
Hyderabad48%,Delhi10%,Mumbai8%,Bengaluru8%,Chennai8%,Kolkata6%,Jaipur5%,Pune7%. These are demo weights,not population estimates.
Group-shared city/type/area/insulation/glazing create dependency; group IDs remain together in all partitions.
Type independent/row/apartment probabilities.32/.18/.50; median areas115/90/80m²,log-sigma.29,bounds35–250m².
Within-group area normal variation4.5%;occupants=clipped(Poisson(2.1+area/140)+1,1,8).
Insulation poor/average/good probabilities.38/.42/.20;single-glazing probability.84ifpoor,.65otherwise.
Fans-only probability.50inBengaluru/Pune,.26elsewhere;remaining standard64%/efficient36%. AC units correlatearea/55,bounded1–5.
Fans-only ACunits/hourszero. ACdailyhours=clipped(gamma(2.4,2.2),.5,16). Capacitymean1.5ton above80m²,1.1otherwise;
ISEERmean5.1efficient,3.4standard,withboundednoise;setpointmean25.5°C.
RoofU means2.8/1.5/.55andwallU2.1/1.45/.75byinsulation;independent/rowroof fullyexposed,oneof4apartments exposed.
Windowratio mean.23;SHGCmean.43double/.75single;shading=.9×Beta(2,3). Fans correlatearea/29;35%mean30W,others67W.
Fan hoursmean8inBengaluru/Pune,12elsewhere;lightinghoursmean4.5. LED/controls correlateinsulation/cooling.
Appliance kWh/day=(1+.62×occupants+.012×area)×mean-one lognormal(log-sigma.17),bounded.5–12.
Water systems geyser/solar/heat-pump/none probabilities.55/.13/.04/.28;litres varycity/heaterpresence.
PNGprobability.25Delhi/Mumbai/Pune,.07elsewhere;induction.15,remainingLPG. Availability-inspired demo probabilities,not surveyestimates.
Roofaccess/property constrain PVsampling; solar_kw never enters demand-model X. Exact bounded draws are inspectable in generate_dataset.

## Label rules and accounting

Shared expected_end_uses computes physical mean demand(beforePV),LPGinputenergy,PNGinputenergy from documented assumptions.
Household label=physicalmean×sharedgroupnoise×independenthouseholdnoise,allmean-one lognormal.
Sharedlogsigmas.08electric/.07cooking;individualsigmas.10electric/.12cooking. Absentfuelsremainexactzero.
These invented behavior/measurement distributions are not measured Indian uncertainty benchmarks.
Reference_* columns expose means but never enter X;IDs,origin,labels,postsolarimports,referencecolumnsareexcluded.
Engineering features add only input-derived weather(CDH,GHI,PVyield)andphysicsmean estimates.
electricity_balance(home,observeddemand) derives imports,self-use,generation,exports, preserving bothenergybalances.
LPG and PNG remain separate;annual_gas_kwh compatibility=sumLPG+PNG in common kWhinputenergy. No saleslabels/valueupliftfabricated.

## Evaluation

Groupdisjoint50/15/15/20train/validation/calibration/test. Frozen testgroups keyed exactdatasetSHA256.
Trainingalonefitscandidates/preprocessing;validationaloneselects;independentcalibrationestablishes90%relativeconformalranges;
testreportsMAE/RMSE/R²,WAPE,activefuelcoverage/width,subgroups,stress. Constant-targetR²andzero-denominatorWAPEarenull.
Calibrationusesone label-independentrandomrepresentativepergroup;exchangeabilityofindependentgroupsrequired.
Row/subgroup/driftcoverageisempirical,notguaranteed. Physicsbaselineeligible,andlikelybestbecauseitisthegeneratorconditionalmean.
Selectedandbestlearnedpipelinearepreserved;noMLwinisforced. Stressreferencesassumedphysicsor35%unobservedusageshift,notrealcausallabels.

## External CSV

train.py --data-csv observations.csv --provenance-json provenance.json requires explicitfullannualobservations.
Columns:home_id(uniquerow),group_id(sharedhousehold/building),allFEATURES,andallthreeTARGETS.
Imports-onlycannotreplaceelectricitydemand;missingrequiredphysicalfeaturesarerejectedratherthaninvented.
Manifest:data_kind(measured|synthetic),source,license,units(kWh/year),geographic_scope.
Measuredalso:measurement_start/endcover365/366days,target_definitionsforallTARGETS.Synthetic:label_rule_version.
Declaredprovenanceisnotauditverification.Defaultmodelsremainsyntheticuntilreplacedwithsuitablelicensedmeasureddata.
Auditrepresentativeness,leakage,climate/yeartransfer,calibration,subgroupsandretrofitcausalitybeforerealdecisionuse.
"""
