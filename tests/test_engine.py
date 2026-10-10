"""Public accounting, interaction and conservative-input invariants."""
from copy import deepcopy

import pytest

from greenhome.engine import evaluate_scenario, feasible_retrofits, score_home
from greenhome.physics import electricity_balance
from greenhome.schema import DEFAULT_HOME


BASELINE = {"annual_grid_kwh": 6500.0, "annual_gas_kwh": 1800.0}


def home(**changes):
    return {**deepcopy(DEFAULT_HOME), **changes}


def feasible_ids(property_data):
    return {item["id"] for item in feasible_retrofits(property_data)}


def assert_preserves_meter_totals(result, original):
    for key, value in original.items():
        assert result["after"][key] == pytest.approx(value)
    for energy in (result["baseline"], result["after"]):
        assert energy["annual_gas_kwh"] == pytest.approx(energy["annual_lpg_kwh"] + energy["annual_png_kwh"])


def test_score_is_weighted_bounded_and_auditable():
    result = score_home(home(), BASELINE)
    assert result["score"] is not None
    assert sum(item["weight"] for item in result["components"]) == pytest.approx(1)
    assert all(0 <= item["subscore"] <= 100 for item in result["components"])
    assert 0 <= result["score"] <= 100
    assert result["score"] == pytest.approx(sum(item["contribution"] for item in result["components"]))


def test_empty_package_preserves_baseline():
    result = evaluate_scenario(home(), BASELINE, [])
    assert_preserves_meter_totals(result, BASELINE)
    assert result["after"] == result["baseline"]
    assert result["savings"]["total_kwh"] == 0
    assert result["savings"]["carbon_kg"] == 0


def test_induction_switch_preserves_signed_per_fuel_savings():
    result = evaluate_scenario(home(), BASELINE, ["induction"])
    assert result["applied"] == ["induction"]
    assert result["after"]["annual_gas_kwh"] == 0
    assert result["after"]["annual_grid_kwh"] > BASELINE["annual_grid_kwh"]
    assert result["savings"]["electricity_kwh"] < 0
    assert result["savings"]["gas_kwh"] == BASELINE["annual_gas_kwh"]
    assert result["savings"]["total_kwh"] > 0
    # Energy and carbon need not move together with this dated grid factor.
    assert result["savings"]["carbon_kg"] < 0


def test_carbon_uses_each_fuels_signed_change_and_its_factor():
    result = evaluate_scenario(home(), BASELINE, ["induction"], factors={
        "electricity_kg_co2_per_kwh": 0.2, "lpg_kg_co2_per_kwh": 0.3,
    })
    saving = result["savings"]
    assert saving["carbon_kg"] == pytest.approx(
        saving["electricity_kwh"] * 0.2 + saving["gas_kwh"] * 0.3)
    assert saving["total_kwh"] == pytest.approx(saving["electricity_kwh"] + saving["gas_kwh"])


def test_insulation_and_efficient_ac_interact_and_order_is_stable():
    first = evaluate_scenario(home(), BASELINE, ["insulation"])
    second = evaluate_scenario(home(), BASELINE, ["efficient_ac"])
    package = evaluate_scenario(home(), BASELINE, ["efficient_ac", "insulation"])
    assert package["applied"] == ["insulation", "efficient_ac"]
    sum_individual = first["savings"]["total_kwh"] + second["savings"]["total_kwh"]
    assert 0 < package["savings"]["total_kwh"] < sum_individual
    repeated = evaluate_scenario(home(), BASELINE, ["insulation", "efficient_ac", "insulation"])
    assert repeated["after"] == package["after"]


def test_selected_marginal_savings_sum_to_selected_package():
    result = evaluate_scenario(home(), BASELINE, ["efficient_ac", "insulation", "induction"])
    selected = [item for item in result["recommendations"] if item["selected"]]
    unselected = [item for item in result["recommendations"] if not item["selected"]]
    for key in ("electricity_kwh", "gas_kwh", "total_kwh", "carbon_kg"):
        assert sum(item["sequential_savings"][key] for item in selected) == pytest.approx(result["savings"][key])
        assert all(item["sequential_savings"][key] is None for item in unselected)


def test_existing_solar_empty_package_preserves_meter_totals():
    result = evaluate_scenario(home(solar_kw=8.0), BASELINE, [])
    assert_preserves_meter_totals(result, BASELINE)
    assert result["after"] == result["baseline"]
    assert result["savings"]["total_kwh"] == 0


def test_solar_reduces_imports_with_nonnegative_totals():
    result = evaluate_scenario(home(), BASELINE, ["solar"])
    assert 0 <= result["after"]["annual_grid_kwh"] < BASELINE["annual_grid_kwh"]
    assert result["after"]["annual_gas_kwh"] == BASELINE["annual_gas_kwh"]
    assert result["home_after"]["solar_kw"] > 0


@pytest.mark.parametrize("field,value,blocked", [
    ("roof_access", False, {"insulation", "solar", "solar_water_heater"}),
    ("roof_access", None, {"insulation", "solar", "solar_water_heater"}),
    ("heritage_restricted", True, {"insulation", "glazing", "solar", "solar_water_heater"}),
    ("heritage_restricted", None, {"insulation", "glazing", "solar", "solar_water_heater"}),
])
def test_affected_retrofits_are_removed_when_constraints_fail(field, value, blocked):
    assert blocked.isdisjoint(feasible_ids(home(**{field: value})))


@pytest.mark.parametrize("consent", [False, None])
def test_absent_or_unknown_consent_blocks_all_retrofits(consent):
    result = evaluate_scenario(home(retrofit_consent=consent), BASELINE, ["solar", "efficient_ac"])
    assert result["recommendations"] == []
    assert result["applied"] == []
    assert {item["id"] for item in result["rejected"]} == {"solar", "efficient_ac"}
    assert all(item["reason"] for item in result["rejected"])
    assert_preserves_meter_totals(result, BASELINE)


@pytest.mark.parametrize("connection", [False, None])
def test_unknown_or_absent_electric_connection_blocks_induction(connection):
    assert "induction" not in feasible_ids(home(electric_connection=connection))


def test_missing_electric_connection_blocks_induction():
    property_data = home()
    del property_data["electric_connection"]
    assert "induction" not in feasible_ids(property_data)


def test_zero_baseline_has_no_percentage_or_energy_intensity_score():
    zeros = {key: 0.0 for key in BASELINE}
    result = evaluate_scenario(home(), zeros, ["solar"])
    assert result["savings"]["percent"] is None
    assert result["baseline_score"]["score"] is None
    assert all(value >= 0 for value in result["after"].values())
    assert result["flags"]


@pytest.mark.parametrize("property_data,energy", [
    (home(area_m2=None), BASELINE),
    (home(cooling="fans_only"), BASELINE),
    (home(cooking_fuel="induction"), BASELINE),
    (home(occupants=2.5), BASELINE),
    (home(ac_units=1.5), BASELINE),
    (home(), {"annual_grid_kwh": 6500.0}),
    (home(), {"annual_grid_kwh": -1.0, "annual_gas_kwh": 1800.0}),
])
def test_missing_or_conflicting_data_never_produces_savings(property_data, energy):
    original = deepcopy(property_data)
    result = evaluate_scenario(property_data, energy, ["solar", "efficient_ac"])
    assert result["savings"]["total_kwh"] is None
    assert result["savings"]["percent"] is None
    assert all(value is None for value in result["after"].values())
    assert result["applied"] == []
    assert result["flags"]
    assert property_data == original


def test_unknown_retrofit_and_invalid_carbon_factor_are_explained():
    result = evaluate_scenario(home(), BASELINE, ["not_a_retrofit", "led_lighting"], factors={
        "electricity_kg_co2_per_kwh": -1,
    })
    assert result["rejected"][0]["id"] == "not_a_retrofit"
    assert result["rejected"][0]["reason"]
    assert result["savings"]["total_kwh"] > 0
    assert result["savings"]["carbon_kg"] is None
    assert result["value_impact"]["available"] is False


@pytest.mark.parametrize("fuel", ["lpg", "png"])
def test_explicit_fuels_are_counted_once_and_carbon_uses_each_factor(fuel):
    energy = {"annual_grid_kwh": 6500.0, "annual_lpg_kwh": 1800.0 if fuel == "lpg" else 0.0,
              "annual_png_kwh": 1800.0 if fuel == "png" else 0.0, "annual_gas_kwh": 1800.0}
    result = evaluate_scenario(home(cooking_fuel=fuel), energy, ["induction"], factors={
        "electricity_kg_co2_per_kwh": 0.2, "lpg_kg_co2_per_kwh": 0.3,
        "png_kg_co2_per_kwh": 0.4,
    })
    saving = result["savings"]
    assert saving["gas_kwh"] == pytest.approx(saving["lpg_kwh"] + saving["png_kwh"])
    assert saving["total_kwh"] == pytest.approx(saving["electricity_kwh"] + saving["lpg_kwh"] + saving["png_kwh"])
    assert saving["carbon_kg"] == pytest.approx(
        saving["electricity_kwh"] * 0.2 + saving["lpg_kwh"] * 0.3 + saving["png_kwh"] * 0.4)
    assert result["after"]["annual_lpg_kwh"] == result["after"]["annual_png_kwh"] == 0


def test_legacy_gas_label_maps_to_declared_png_cooking():
    result = evaluate_scenario(home(cooking_fuel="png"), BASELINE, [])
    assert result["baseline"]["annual_lpg_kwh"] == 0
    assert result["baseline"]["annual_png_kwh"] == BASELINE["annual_gas_kwh"]
    assert_preserves_meter_totals(result, BASELINE)


@pytest.mark.parametrize("change", [
    {"annual_lpg_kwh": 1800.0, "annual_png_kwh": 0.0, "annual_gas_kwh": 99.0},
    {"annual_electricity_demand_kwh": 6501.0},
])
def test_conflicting_expanded_energy_labels_withhold_scenarios(change):
    result = evaluate_scenario(home(), {**BASELINE, **change}, ["solar"])
    assert result["savings"]["total_kwh"] is None
    assert result["applied"] == []
    assert result["flags"]


def test_pv_does_not_improve_gross_electricity_intensity_component():
    before_home = home(solar_kw=0)
    after_home = home(solar_kw=3)
    demand = 8000.0
    before = score_home(before_home, {**electricity_balance(before_home, demand),
        "annual_electricity_demand_kwh": demand, "annual_gas_kwh": 1800.0})
    after = score_home(after_home, {**electricity_balance(after_home, demand),
        "annual_electricity_demand_kwh": demand, "annual_gas_kwh": 1800.0})
    assert before["electricity_demand_intensity_kwh_m2"] == after["electricity_demand_intensity_kwh_m2"]
    assert before["components"][1]["subscore"] == after["components"][1]["subscore"]
    assert after["purchased_energy_intensity_kwh_m2"] < before["purchased_energy_intensity_kwh_m2"]
    assert after["components"][5]["subscore"] > before["components"][5]["subscore"]
    for index, (old_component, new_component) in enumerate(zip(before["components"], after["components"])):
        if index != 5:
            assert new_component["subscore"] == pytest.approx(old_component["subscore"])


def test_scenario_pv_flows_conserve_energy():
    result = evaluate_scenario(home(), BASELINE, ["efficient_ac", "solar"])
    for energy in (result["baseline"], result["after"]):
        assert energy["annual_electricity_demand_kwh"] == pytest.approx(
            energy["annual_grid_kwh"] + energy["annual_solar_self_consumed_kwh"])
        assert energy["annual_solar_generation_kwh"] == pytest.approx(
            energy["annual_solar_self_consumed_kwh"] + energy["annual_solar_export_kwh"])
