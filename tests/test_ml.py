"""Independent leakage, calibration, accounting and data-ingestion checks."""
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from greenhome.ml import (
    MODEL_NAMES, _fit_interval, _split_groups, generate_dataset, input_diagnostics,
    load_models, load_training_csv, predict_energy, prediction_intervals, train_models,
)
from greenhome.physics import electricity_balance
from greenhome.schema import DEFAULT_HOME, FEATURES, TARGETS


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    root = tmp_path_factory.mktemp("ml_experiment")
    # This seed has 12 independent active PNG calibration representatives.
    metrics = train_models(root, n=3000, seed=52)
    return root, metrics, load_models(root)


def test_synthetic_generator_is_seeded_and_labels_are_nonnegative():
    first = generate_dataset(n=200, seed=29)
    repeated = generate_dataset(n=200, seed=29)
    pd.testing.assert_frame_equal(first, repeated)
    assert first.home_id.is_unique
    assert first.group_id.duplicated().any()
    assert np.isfinite(first[TARGETS].to_numpy()).all()
    assert first[TARGETS].ge(0).all().all()
    assert first.data_origin.str.startswith("synthetic").all()
    assert not first[TARGETS].equals(generate_dataset(n=200, seed=30)[TARGETS])
    assert first.loc[first.cooking_fuel.ne("lpg"), "annual_lpg_kwh"].eq(0).all()
    assert first.loc[first.cooking_fuel.ne("png"), "annual_png_kwh"].eq(0).all()


def test_all_four_splits_are_group_disjoint_and_cover_every_home(experiment):
    root, metrics, _ = experiment
    homes = pd.read_csv(root / "data" / "training_homes.csv")
    assignments = pd.read_csv(root / "data" / "split_assignments.csv")
    assert assignments.home_id.is_unique
    assert set(assignments.home_id) == set(homes.home_id)
    assert assignments.groupby("group_id").split.nunique().eq(1).all()
    groups = {name: set(rows.group_id) for name, rows in assignments.groupby("split")}
    assert set(groups) == {"train", "validation", "calibration", "test"}
    for first, second in itertools.combinations(groups.values(), 2):
        assert first.isdisjoint(second)
    assert assignments.groupby("split").size().to_dict() == metrics["split_counts"]
    held = pd.read_csv(root / "reports" / "held_out_predictions.csv")
    assert set(held.home_id) == set(assignments.loc[assignments.split.eq("test"), "home_id"])
    representatives = pd.read_csv(root / "data" / "calibration_representatives.csv")
    assert representatives.group_id.is_unique
    assert set(representatives.group_id) == groups["calibration"]
    assert set(representatives.home_id).issubset(
        set(assignments.loc[assignments.split.eq("calibration"), "home_id"]))


def test_same_dataset_keeps_test_groups_frozen_when_training_seed_changes(experiment):
    root, metrics, _ = experiment
    homes = pd.read_csv(root / "data" / "training_homes.csv")
    before = json.loads((root / "data" / "split_manifest.json").read_text())
    # Use a separate manifest so the experiment's original assignments stay intact.
    scratch = root / "frozen_probe"
    (scratch / "data").mkdir(parents=True)
    (scratch / "data" / "split_manifest.json").write_text(json.dumps(before))
    parts, after = _split_groups(homes, seed=99, root=scratch,
                                fingerprint=metrics["dataset_sha256"])
    assert after["test_reused_for_same_dataset"]
    assert set(parts["test"].group_id) == set(before["frozen_test_group_ids"])
    exact_bytes = (root / "data" / "training_homes.csv").read_bytes()
    assert hashlib.sha256(exact_bytes).hexdigest() == metrics["dataset_sha256"]


def test_selection_uses_validation_and_keeps_physics_eligible(experiment):
    root, metrics, models = experiment
    assert metrics["features"] == FEATURES
    assert not set(FEATURES).intersection(TARGETS + [
        "home_id", "group_id", "solar_kw", "annual_grid_kwh", "data_origin"])
    assert all(not name.startswith("reference_") for name in FEATURES)
    for target in TARGETS:
        result = metrics["models"][target]
        expected = min(MODEL_NAMES, key=lambda name:
                       result["candidates"][name]["validation"]["mae_kwh"])
        assert result["selected"] == expected
        assert list(models[target].named_steps["physics_features"].feature_names_in_) == FEATURES
        assert (root / "models" / "candidates" / f"{target}__best_learned.joblib").is_file()


def test_saved_pipeline_reproduces_held_out_predictions_and_energy_balance(experiment):
    root, _, models = experiment
    reloaded = load_models(Path(root))
    held = pd.read_csv(root / "reports" / "held_out_predictions.csv")
    for _, row in held.head(8).iterrows():
        home = row[FEATURES + ["solar_kw"]].to_dict()
        first, second = predict_energy(home, models), predict_energy(home, reloaded)
        for target in TARGETS:
            assert second[target] == pytest.approx(first[target], abs=1e-9)
            assert second[target] == pytest.approx(row[f"predicted_{target}"], abs=0.00051)
        assert first["annual_electricity_demand_kwh"] == pytest.approx(
            first["annual_grid_kwh"] + first["annual_solar_self_consumed_kwh"])
        assert first["annual_solar_generation_kwh"] == pytest.approx(
            first["annual_solar_self_consumed_kwh"] + first["annual_solar_export_kwh"])
        assert first["annual_gas_kwh"] == first["annual_lpg_kwh"] + first["annual_png_kwh"]


def test_calibration_quantile_uses_only_one_independent_active_group_label(experiment):
    root, metrics, models = experiment
    homes = pd.read_csv(root / "data" / "training_homes.csv").set_index("home_id")
    representative_ids = pd.read_csv(root / "data" / "calibration_representatives.csv").home_id
    representatives = homes.loc[representative_ids]
    for target in TARGETS:
        fuel = {"annual_lpg_kwh": "lpg", "annual_png_kwh": "png"}.get(target)
        active = representatives if fuel is None else representatives.loc[
            representatives.cooking_fuel.eq(fuel)]
        predicted = np.array([predict_energy(row.to_dict(), models)[target]
                              for _, row in active.iterrows()])
        scores = np.sort(np.abs(active[target].to_numpy() - predicted) / np.maximum(100, predicted))
        rank = math.ceil((len(scores) + 1) * 0.90)
        assert rank <= len(scores)
        calibration = metrics["models"][target]["calibration"]
        assert calibration["calibration_n"] == len(scores)
        assert calibration["relative_radius"] == pytest.approx(scores[rank - 1])


def test_held_out_metrics_and_coverage_are_recomputed_from_saved_rows(experiment):
    root, metrics, _ = experiment
    held = pd.read_csv(root / "reports" / "held_out_predictions.csv")
    for target in TARGETS:
        error = np.abs(held[target] - held[f"predicted_{target}"])
        assert metrics["models"][target]["test"]["mae_kwh"] == pytest.approx(error.mean(), abs=0.0001)
        covered = held[target].between(held[f"interval_low_{target}"], held[f"interval_high_{target}"])
        interval = metrics["models"][target]["test_intervals"]
        assert interval["row_coverage"] == pytest.approx(covered.mean())
        assert interval["group_weighted_coverage"] == pytest.approx(
            covered.groupby(held.group_id).mean().mean())
    subgroups = pd.read_csv(root / "reports" / "subgroup_metrics.csv")
    assert {"city", "cooling", "cooking_fuel", "property_type", "solar"} == set(subgroups.dimension)
    assert "unobserved_35_percent_usage_shift" in metrics["stress_tests"]["cases"]


@pytest.mark.parametrize("fuel", ["lpg", "png", "induction"])
def test_fuel_masks_and_pv_invariance_hold_for_inference_and_intervals(experiment, fuel):
    _, _, models = experiment
    home = {**DEFAULT_HOME, "cooking_fuel": fuel, "solar_kw": 0}
    base = predict_energy(home, models)
    solar_home = {**home, "solar_kw": 8}
    solar = predict_energy(solar_home, models)
    intervals = prediction_intervals(solar_home, solar, models)
    for target in TARGETS:
        # Parallel tree reductions can differ by a few machine-precision bits.
        assert base[target] == pytest.approx(solar[target], rel=1e-12, abs=1e-9)
        assert intervals[target][0] <= solar[target] <= intervals[target][1]
    assert solar["annual_grid_kwh"] < base["annual_grid_kwh"]
    for target, active in [("annual_lpg_kwh", "lpg"), ("annual_png_kwh", "png")]:
        if fuel != active:
            assert solar[target] == 0
            assert intervals[target] == [0, 0]
    low, high = intervals["annual_electricity_demand_kwh"]
    assert intervals["annual_grid_kwh"] == pytest.approx([
        electricity_balance(solar_home, low)["annual_grid_kwh"],
        electricity_balance(solar_home, high)["annual_grid_kwh"]])


@pytest.mark.parametrize("change", [
    {"area_m2": None}, {"area_m2": float("nan")}, {"occupants": 2.5},
    {"city": "unsupported_city"}, {"solar_kw": -1}, {"ac_iseer": 0},
])
def test_inference_rejects_invalid_or_unsupported_features(experiment, change):
    _, _, models = experiment
    with pytest.raises(ValueError):
        predict_energy({**DEFAULT_HOME, **change}, models)


def test_training_only_rarity_flags_are_not_ood_guarantees(experiment):
    _, _, models = experiment
    result = input_diagnostics({**DEFAULT_HOME, "area_m2": 250}, models)
    assert result["supported"]
    assert "area_m2" in result["rare_training_features"]
    assert not input_diagnostics({**DEFAULT_HOME, "city": "unknown"}, models)["supported"]


@pytest.fixture
def csv_fixture(tmp_path):
    frame = generate_dataset(200, seed=7)
    manifest = {"data_kind": "synthetic", "source": "pytest fixture only",
                "license": "test fixture", "units": "kWh/year",
                "geographic_scope": "simulated India", "label_rule_version": "fixture"}
    return tmp_path, frame, manifest


def write_fixture(fixture):
    folder, frame, manifest = fixture
    csv, provenance = folder / "annual.csv", folder / "provenance.json"
    frame.to_csv(csv, index=False)
    provenance.write_text(json.dumps(manifest))
    return csv, provenance


def test_explicit_synthetic_csv_retains_groups_and_never_becomes_measured(csv_fixture):
    csv, provenance = write_fixture(csv_fixture)
    loaded, manifest = load_training_csv(csv, provenance)
    assert manifest["data_kind"] == "synthetic"
    assert loaded.data_origin.eq("synthetic_csv_declared").all()
    assert loaded.group_id.duplicated().any()


@pytest.mark.parametrize("defect", [
    "missing_group", "missing_feature", "missing_demand", "duplicate_id",
    "one_group", "negative_target", "fuel_conflict", "nonannual_units",
    "no_license", "synthetic_declared_measured", "partial_annual_label",
])
def test_external_csv_gate_rejects_incomplete_or_conflicting_claims(csv_fixture, defect):
    _, frame, manifest = csv_fixture
    if defect == "missing_group":
        frame.drop(columns="group_id", inplace=True)
    elif defect == "missing_feature":
        frame.drop(columns="roof_u_value", inplace=True)
    elif defect == "missing_demand":
        frame.drop(columns="annual_electricity_demand_kwh", inplace=True)
    elif defect == "duplicate_id":
        frame.loc[1, "home_id"] = frame.loc[0, "home_id"]
    elif defect == "one_group":
        frame["group_id"] = "one_building"
    elif defect == "negative_target":
        frame.loc[0, TARGETS[0]] = -1
    elif defect == "fuel_conflict":
        frame.loc[0, "cooking_fuel"] = "induction"
        frame.loc[0, "annual_lpg_kwh"] = 100
    elif defect == "nonannual_units":
        manifest["units"] = "kWh/day"
    elif defect == "no_license":
        manifest.pop("license")
    else:
        manifest.update(data_kind="measured", measurement_start="2024-01-01",
                        measurement_end="2024-12-31",
                        target_definitions={name: "fixture definition" for name in TARGETS})
        if defect == "partial_annual_label":
            manifest["measurement_end"] = "2024-05-31"
    with pytest.raises(ValueError):
        load_training_csv(*write_fixture(csv_fixture))


def test_too_few_calibration_groups_cannot_claim_finite_ninety_percent_bounds():
    with pytest.raises(ValueError, match="calibration|groups|nine|9"):
        _fit_interval(np.ones(8), np.ones(8))
