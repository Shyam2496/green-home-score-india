"""Accounting and directional checks for the declared physical baseline."""
import math

import pytest

from greenhome.physics import (
    complete_home, demand_from_grid, electricity_balance, expected_end_uses,
    input_assumptions, validate_home,
)
from greenhome.schema import DEFAULT_HOME, OPTIONS


def home(**changes):
    return {**DEFAULT_HOME, **changes}


@pytest.mark.parametrize("demand", [0.0, 100.0, 8000.0])
@pytest.mark.parametrize("solar_kw", [0.0, 3.0, 8.0])
@pytest.mark.parametrize("self_fraction", [0.0, 0.65, 1.0])
def test_solar_accounting_conserves_energy_and_inverts_grid(demand, solar_kw, self_fraction):
    property_data = home(solar_kw=solar_kw, solar_self_consumption_fraction=self_fraction)
    balance = electricity_balance(property_data, demand)
    assert all(math.isfinite(value) and value >= 0 for value in balance.values())
    assert demand == pytest.approx(balance["annual_grid_kwh"] + balance["annual_solar_self_consumed_kwh"])
    assert balance["annual_solar_generation_kwh"] == pytest.approx(
        balance["annual_solar_self_consumed_kwh"] + balance["annual_solar_export_kwh"])
    assert balance["annual_solar_self_consumed_kwh"] <= demand
    assert demand_from_grid(property_data, balance["annual_grid_kwh"]) == pytest.approx(demand)


@pytest.mark.parametrize("city", OPTIONS["city"])
def test_all_supported_cities_have_finite_nonnegative_baselines(city):
    end = expected_end_uses(home(city=city))
    assert all(math.isfinite(value) and value >= 0 for value in end.values())
    assert end["annual_electricity_demand_kwh"] > 0


def test_solar_changes_imports_and_exports_without_changing_demand():
    before = expected_end_uses(home(solar_kw=0))
    after = expected_end_uses(home(solar_kw=8))
    assert after["annual_electricity_demand_kwh"] == pytest.approx(before["annual_electricity_demand_kwh"])
    assert after["annual_grid_kwh"] < before["annual_grid_kwh"]
    assert after["annual_solar_export_kwh"] >= 0
    assert after["annual_lpg_kwh"] == before["annual_lpg_kwh"]


def test_higher_ac_efficiency_and_setpoint_reduce_cooling():
    base = home(ac_iseer=3.2, setpoint_c=24)
    low = expected_end_uses(base)
    efficient = expected_end_uses({**base, "ac_iseer": 5.2})
    warmer = expected_end_uses({**base, "setpoint_c": 28})
    assert 0 < efficient["cooling_kwh"] < low["cooling_kwh"]
    assert warmer["cooling_kwh"] <= low["cooling_kwh"]
    assert efficient["annual_lpg_kwh"] == low["annual_lpg_kwh"]


def test_roof_improvement_only_changes_cooling_when_roof_is_exposed():
    exposed = home(roof_exposed_fraction=1, roof_u_value=3.0)
    assert expected_end_uses({**exposed, "roof_u_value": 0.6})["cooling_kwh"] < expected_end_uses(exposed)["cooling_kwh"]
    unexposed = {**exposed, "roof_exposed_fraction": 0}
    assert expected_end_uses({**unexposed, "roof_u_value": 0.6})["cooling_kwh"] == pytest.approx(expected_end_uses(unexposed)["cooling_kwh"])


def test_led_and_shading_effects_are_limited_to_relevant_end_uses():
    base = home(led_fraction=0.0, window_shading_fraction=0.0)
    before = expected_end_uses(base)
    after = expected_end_uses({**base, "led_fraction": 1.0, "window_shading_fraction": 0.9})
    assert after["lighting_kwh"] < before["lighting_kwh"]
    assert after["cooling_kwh"] <= before["cooling_kwh"]
    assert after["fans_kwh"] == before["fans_kwh"]
    assert after["annual_lpg_kwh"] == before["annual_lpg_kwh"]


def test_cooking_fuels_are_separate_and_induction_adds_electricity():
    lpg = expected_end_uses(home(cooking_fuel="lpg"))
    png = expected_end_uses(home(cooking_fuel="png"))
    induction = expected_end_uses(home(cooking_fuel="induction"))
    assert lpg["annual_lpg_kwh"] > 0 and lpg["annual_png_kwh"] == 0
    assert png["annual_png_kwh"] > 0 and png["annual_lpg_kwh"] == 0
    assert induction["annual_lpg_kwh"] == induction["annual_png_kwh"] == 0
    assert induction["annual_electricity_demand_kwh"] > lpg["annual_electricity_demand_kwh"]
    assert induction["annual_electricity_demand_kwh"] > png["annual_electricity_demand_kwh"]
    for values in (lpg, png, induction):
        assert values["annual_gas_kwh"] == values["annual_lpg_kwh"] + values["annual_png_kwh"]


def test_unused_ac_is_valid_but_fan_only_cannot_claim_ac_usage():
    unused = home(ac_units=0, ac_hours_per_day=0)
    assert validate_home(unused) == []
    assert expected_end_uses(unused)["cooling_kwh"] == 0
    assert validate_home(home(cooling="fans_only"))
    fans = home(cooling="fans_only", ac_units=0, ac_hours_per_day=0)
    assert expected_end_uses(fans)["cooling_kwh"] == 0
    assert expected_end_uses(fans)["fans_kwh"] > 0


def test_capacity_limited_cooling_exposes_unmet_service():
    stressed = home(area_m2=250, ac_units=1, ac_capacity_ton=0.75,
        ac_hours_per_day=16, setpoint_c=22, roof_u_value=4, wall_u_value=3.5,
        window_to_wall_ratio=0.5, window_shgc=0.9, window_shading_fraction=0)
    small = expected_end_uses(stressed)
    larger = expected_end_uses({**stressed, "ac_capacity_ton": 2.5})
    assert small["capacity_limited_months"] > 0
    assert small["annual_unmet_cooling_kwh_thermal"] > 0
    assert larger["annual_unmet_cooling_kwh_thermal"] <= small["annual_unmet_cooling_kwh_thermal"]
    # Low use caused by unmet service must not be mistaken for efficiency.
    assert larger["cooling_kwh"] >= small["cooling_kwh"]


def test_defaults_are_disclosed_and_explicit_values_are_preserved():
    data = home(ac_iseer=4.4)
    completed = complete_home(data)
    assumptions = input_assumptions(data)
    assert completed["ac_iseer"] == 4.4
    assert "ac_iseer" not in assumptions
    assert assumptions["roof_u_value"] == completed["roof_u_value"]
    without_solar = {key: value for key, value in data.items() if key != "solar_kw"}
    assert "solar_kw" in input_assumptions(without_solar)


def test_numeric_strings_are_normalized_before_physical_calculation():
    numeric = expected_end_uses(home(occupants=3, ac_units=2))
    strings = expected_end_uses(home(occupants="3.0", ac_units="2"))
    assert strings == pytest.approx(numeric)


@pytest.mark.parametrize("change", [
    {"area_m2": float("nan")}, {"occupants": 2.5}, {"fan_count": 1.5},
    {"ac_iseer": 0}, {"solar_kw": -1}, {"solar_self_consumption_fraction": 1.1},
    {"roof_exposed_fraction": -0.1}, {"window_shgc": float("inf")},
    {"city": "unsupported_city"}, {"cooking_fuel": "unknown_fuel"},
])
def test_invalid_inputs_cannot_enter_end_use_model(change):
    assert validate_home(home(**change))
    with pytest.raises(ValueError):
        expected_end_uses(home(**change))


@pytest.mark.parametrize("energy", [-1, float("nan"), float("inf")])
def test_invalid_energy_is_rejected_by_balance_and_inverse(energy):
    with pytest.raises(ValueError):
        electricity_balance(home(), energy)
    with pytest.raises(ValueError):
        demand_from_grid(home(), energy)


@pytest.mark.parametrize("change", [{"solar_kw": -1}, {"solar_self_consumption_fraction": 2}])
def test_invalid_solar_inputs_are_rejected_by_public_accounting(change):
    with pytest.raises(ValueError):
        electricity_balance(home(**change), 1000)
    with pytest.raises(ValueError):
        demand_from_grid(home(**change), 1000)


def test_valid_numeric_strings_have_identical_public_physics_results():
    numeric = home(occupants=3, ac_units=2, fan_count=4)
    strings = home(occupants='3.0', ac_units='2', fan_count='4')
    assert validate_home(strings) == []
    assert expected_end_uses(strings) == pytest.approx(expected_end_uses(numeric))
