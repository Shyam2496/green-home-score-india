"""Audit records must reconcile with the exact bill-anchored scenario path."""
from copy import deepcopy
import json

import pytest

from greenhome.engine import evaluate_scenario
from greenhome.physics import electricity_balance
from greenhome.schema import DEFAULT_HOME


BILLS = {"annual_grid_kwh": 2400.0, "annual_lpg_kwh": 900.0,
         "annual_png_kwh": 0.0, "annual_gas_kwh": 900.0}


def home(**changes):
    return {**deepcopy(DEFAULT_HOME), **changes}


def assert_balance(energy):
    assert energy["annual_electricity_demand_kwh"] == pytest.approx(
        energy["annual_grid_kwh"] + energy["annual_solar_self_consumed_kwh"])
    assert energy["annual_solar_generation_kwh"] == pytest.approx(
        energy["annual_solar_self_consumed_kwh"] + energy["annual_solar_export_kwh"])
    assert energy["annual_gas_kwh"] == pytest.approx(
        energy["annual_lpg_kwh"] + energy["annual_png_kwh"])


def test_anchor_preserves_supplied_bills_and_discloses_inferred_allocation():
    property_data, bills = home(), deepcopy(BILLS)
    result = evaluate_scenario(property_data, bills, ["insulation"])
    trace = result["calculation_trace"]
    anchor = trace["anchor"]
    assert trace["status"] == "available"
    assert anchor["supplied_energy"] == bills
    assert anchor["baseline_energy"] == result["baseline"]
    assert anchor["end_use_allocation_measured"] is False
    assert "ac_iseer" in anchor["assumed_inputs"]
    assert sum(anchor["anchored_end_uses_kwh"].values()) == pytest.approx(2400)
    assert anchor["electricity_scale_factor"] == pytest.approx(2400 / anchor["nominal_gross_kwh"])
    assert anchor["anchored_gross_kwh"] == pytest.approx(2400)
    assert result["baseline"]["annual_lpg_kwh"] == 900
    assert property_data == home() and bills == BILLS


def test_selected_trace_chain_reconciles_package_energy_and_carbon():
    result = evaluate_scenario(home(), BILLS, ["solar", "induction", "efficient_ac", "insulation"])
    steps = result["calculation_trace"]["selected_steps"]
    assert [step["retrofit_id"] for step in steps] == result["applied"]
    assert steps[0]["before_energy"] == result["baseline"]
    assert steps[-1]["after_energy"] == result["after"]
    for previous, current in zip(steps, steps[1:]):
        assert previous["after_energy"] == current["before_energy"]
        assert previous["after_end_uses_kwh"] == current["before_end_uses_kwh"]
    for step in steps:
        assert step["comparison"] == "selected_package_marginal"
        assert_balance(step["before_energy"])
        assert_balance(step["after_energy"])
        assert sum(step["before_end_uses_kwh"].values()) == pytest.approx(step["before_energy"]["annual_electricity_demand_kwh"])
        assert sum(step["after_end_uses_kwh"].values()) == pytest.approx(step["after_energy"]["annual_electricity_demand_kwh"])
        assert sum(step["carbon_terms_kg"].values()) == pytest.approx(step["savings"]["carbon_kg"])
    for key in ("electricity_kwh", "lpg_kwh", "png_kwh", "total_kwh", "carbon_kg"):
        assert sum(step["savings"][key] for step in steps) == pytest.approx(result["savings"][key])


def test_standalone_and_package_marginal_have_distinct_comparison_states():
    result = evaluate_scenario(home(), BILLS, ["efficient_ac", "insulation"])
    ac = next(item for item in result["recommendations"] if item["id"] == "efficient_ac")
    standalone = ac["standalone_trace"]
    marginal = ac["selected_marginal_trace"]
    assert standalone["before_energy"] == result["baseline"]
    assert marginal["before_energy"]["annual_grid_kwh"] < result["baseline"]["annual_grid_kwh"]
    assert standalone["savings"]["electricity_kwh"] > marginal["savings"]["electricity_kwh"]
    single = evaluate_scenario(home(), BILLS, ["efficient_ac"])
    assert standalone["after_energy"] == single["after"]
    assert marginal["savings"] == ac["sequential_savings"]
    assert standalone["savings"] == ac["standalone_savings"]
    for step in (standalone, marginal):
        denominator = step["before_energy"]["annual_grid_kwh"] + step["before_energy"]["annual_gas_kwh"]
        assert step["savings_percent_denominator_kwh"] == pytest.approx(denominator)
        assert step["savings"]["percent"] == pytest.approx(100 * step["savings"]["total_kwh"] / denominator)


@pytest.mark.parametrize("fuel,efficiency", [("lpg", 0.55), ("png", 0.50)])
def test_fuel_switch_trace_uses_entered_fuel_not_nominal_cooking(fuel, efficiency):
    # Deliberately differs from the occupancy-derived nominal cooking demand.
    bills = {"annual_grid_kwh": 1000.0, "annual_lpg_kwh": 350.0 if fuel == "lpg" else 0.0,
             "annual_png_kwh": 350.0 if fuel == "png" else 0.0, "annual_gas_kwh": 350.0}
    result = evaluate_scenario(home(cooking_fuel=fuel), bills, ["induction"])
    step = result["calculation_trace"]["selected_steps"][0]
    conversion = step["fuel_switch_conversion"]
    assert conversion[f"source_{fuel}_kwh"] == 350
    assert conversion["useful_cooking_heat_kwh"] == pytest.approx(350 * efficiency)
    assert conversion["added_electricity_kwh"] == pytest.approx(350 * efficiency / 0.84)
    assert step["after_end_uses_kwh"]["cooking"] == pytest.approx(350 * efficiency / 0.84)
    assert step["end_use_ratios"]["cooking"] is None
    assert step["savings"]["electricity_kwh"] < 0
    assert step["carbon_terms_kg"]["electricity"] < 0
    assert step["savings"][f"{fuel}_kwh"] == 350


def test_input_change_and_end_use_ratio_trace_identifies_roof_only_effect():
    result = evaluate_scenario(home(roof_u_value=3.0, wall_u_value=2.2), BILLS, ["insulation"])
    step = result["calculation_trace"]["selected_steps"][0]
    assert step["physical_input_changes"]["roof_u_value"] == {"before": 3.0, "after": 0.6}
    assert "wall_u_value" not in step["physical_input_changes"]
    assert 0 < step["end_use_ratios"]["cooling"] < 1
    assert step["after_end_uses_kwh"]["cooling"] == pytest.approx(
        step["before_end_uses_kwh"]["cooling"] * step["end_use_ratios"]["cooling"])
    for key in ("fans", "lighting", "water", "other"):
        assert step["after_end_uses_kwh"][key] == pytest.approx(step["before_end_uses_kwh"][key])


def test_pv_anchor_and_step_show_demand_and_imports_separately():
    result = evaluate_scenario(home(solar_kw=3), BILLS, ["efficient_ac"])
    anchor = result["calculation_trace"]["anchor"]
    assert result["baseline"]["annual_grid_kwh"] == pytest.approx(BILLS["annual_grid_kwh"])
    assert anchor["anchored_gross_kwh"] > BILLS["annual_grid_kwh"]
    assert anchor["pv_assumptions"]["solar_kw"] == 3
    assert anchor["pv_assumptions"]["export_credit"] is False
    assert anchor["pv_assumptions"]["measured_pv_flows"] is False
    assert_balance(anchor["baseline_energy"])
    step = result["calculation_trace"]["selected_steps"][0]
    assert step["after_energy"]["annual_solar_export_kwh"] >= step["before_energy"]["annual_solar_export_kwh"]


def test_checked_gross_input_is_kept_distinct_from_meter_only_inference():
    property_data = home(solar_kw=3)
    demand = 6000.0
    bills = {**BILLS, **electricity_balance(property_data, demand), "annual_electricity_demand_kwh": demand}
    result = evaluate_scenario(property_data, bills, [])
    anchor = result["calculation_trace"]["anchor"]
    assert anchor["supplied_energy"] == bills
    assert "supplied gross" in anchor["electricity_anchor_rule"]
    assert anchor["anchored_gross_kwh"] == pytest.approx(demand)


def test_unselected_and_full_reference_package_traces_are_unambiguous():
    result = evaluate_scenario(home(), BILLS, [])
    assert result["calculation_trace"]["selected_steps"] == []
    previous = result["baseline"]
    for item in result["recommendations"]:
        unselected = item["selected_marginal_trace"]
        assert unselected["status"] == "not_selected"
        assert "savings" not in unselected
        reference = item["recommended_marginal_trace"]
        assert reference["before_energy"] == previous
        assert reference["savings"] == item["recommended_sequential_savings"]
        previous = reference["after_energy"]
    assert previous == result["recommended_package"]["after"]


def test_unavailable_trace_records_input_errors_without_inferred_outputs():
    bad = {**BILLS, "annual_grid_kwh": -1}
    result = evaluate_scenario(home(), bad, ["solar"])
    trace = result["calculation_trace"]
    assert trace["status"] == "unavailable" and trace["reasons"]
    assert trace["anchor"]["supplied_energy"] == bad
    assert "anchored_gross_kwh" not in trace["anchor"]
    assert "anchored_end_uses_kwh" not in trace["anchor"]
    assert trace["selected_steps"] == []
    for item in result["recommendations"]:
        for name in ("standalone_trace", "selected_marginal_trace", "recommended_marginal_trace"):
            assert item[name]["status"] == "unavailable"
            assert "after_energy" not in item[name]


def test_invalid_carbon_factor_does_not_invent_a_term_or_hide_valid_energy():
    result = evaluate_scenario(home(), BILLS, ["induction"], factors={"electricity_kg_co2_per_kwh": -1})
    step = result["calculation_trace"]["selected_steps"][0]
    assert step["status"] == "available"
    assert step["carbon_status"].startswith("unavailable")
    assert step["carbon_terms_kg"]["electricity"] is None
    assert step["carbon_terms_kg"]["lpg"] > 0
    assert step["savings"]["carbon_kg"] is None
    assert step["savings"]["total_kwh"] is not None


def test_zero_baseline_trace_has_no_invalid_percentage_or_undefined_float():
    result = evaluate_scenario(home(cooling="fans_only", ac_units=0, ac_hours_per_day=0),
                               {key: 0.0 for key in BILLS}, ["solar", "led_lighting"])
    for step in result["calculation_trace"]["selected_steps"]:
        assert step["savings_percent_denominator_kwh"] == 0
        assert step["savings"]["percent"] is None
        assert step["end_use_ratios"]["cooling"] is None
    # Export must have actual JSON nulls, never NaN/Infinity for 0/0 ratios.
    json.dumps(result, allow_nan=False)
