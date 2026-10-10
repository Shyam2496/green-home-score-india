"""Cash-flow accounting and safe downstream contracts, not market validation."""
from copy import deepcopy
import json
import math

import pytest

from greenhome.billing import bill_savings_trace
from greenhome.engine import LPG_KWH_PER_KG, evaluate_scenario
from greenhome.finance import calculate_financial_scenario
from greenhome.schema import DEFAULT_HOME


def sample(*, electricity=1000.0, lpg=0.0, png=0.0, actions=None):
    actions = ["led_lighting"] if actions is None else actions
    return {"applied": actions, "savings": {"electricity_kwh": electricity, "lpg_kwh": lpg, "png_kwh": png},
            "calculation_trace": {"status": "available", "selected_steps": [
                {"retrofit_id": action, "status": "available", "physical_input_changes": {"solar_kw": {"before": 0, "after": 3}} if action == "solar" else {}}
                for action in actions]}}


def price(scenario, *, electricity=10, lpg=60, png=5):
    return bill_savings_trace(scenario["savings"], electricity_rate=electricity, lpg_price_kg=lpg, png_rate=png)


def calculate(scenario=None, costs=None, **options):
    scenario = sample() if scenario is None else scenario
    costs = {"led_lighting": 20000} if costs is None else costs
    defaults = {"years": 10, "discount_rate": .085, "escalation_rate": .045}
    return calculate_financial_scenario(scenario, price(scenario), costs, **{**defaults, **options})


def assert_finite_json(result):
    json.dumps(result, allow_nan=False)


def test_cashflows_reconcile_with_capex_and_operating_expenses():
    result = calculate(years=3, discount_rate=.1, escalation_rate=.05,
                       annual_maintenance_inr=100, replacements=[{"year": 2, "cost_inr": 900, "source": "Future nominal assumption"}])
    assert result["status"] == "scenario_only"
    econ = result["project_economics"]
    rows = result["annual_cashflows"]
    assert [row["bill_savings_inr"] for row in rows] == pytest.approx([10000, 10500, 11025])
    assert rows[1]["net_operating_cashflow_inr"] == 9500
    for row in rows:
        assert row["discounted_net_cashflow_inr"] == pytest.approx(row["net_operating_cashflow_inr"] / 1.1 ** row["year"])
    assert econ["discounted_net_benefit_inr"] == pytest.approx(-20000 + sum(row["discounted_net_cashflow_inr"] for row in rows))
    assert econ["present_value_net_operating_cashflow_inr"] == pytest.approx(econ["present_value_bill_savings_inr"] - econ["present_value_maintenance_inr"] - econ["present_value_replacements_inr"])
    assert econ["present_value_replacements_inr"] == pytest.approx(900 / 1.1 ** 2)
    assert rows[-1]["cumulative_discounted_net_inr"] == econ["discounted_net_benefit_inr"]
    assert_finite_json(result)


def test_timing_conventions_are_explicit_and_different():
    first = calculate(years=1, discount_rate=.1, escalation_rate=.05)
    report = calculate(years=1, discount_rate=.1, escalation_rate=.05, timing="report_base_year")
    assert first["project_economics"]["present_value_bill_savings_inr"] == pytest.approx(10000 / 1.1)
    assert report["project_economics"]["present_value_bill_savings_inr"] == pytest.approx(10500 / 1.1)
    assert first["annual_cashflows"][0]["escalation_exponent"] == 0
    assert report["annual_cashflows"][0]["escalation_exponent"] == 1
    assert "first year's" in first["assumptions"]["timing_definition"]


def test_equal_discount_and_escalation_no_formula_singularity():
    result = calculate(years=3, discount_rate=.1, escalation_rate=.1, timing="report_base_year")
    assert result["project_economics"]["present_value_bill_savings_inr"] == pytest.approx(30000)


@pytest.mark.parametrize("cost", [None, -1, True, "20000", float("nan"), float("inf"), 10**1000])
def test_missing_invalid_costs_withhold_investment_outputs(cost):
    result = calculate(costs={"led_lighting": cost})
    assert result["status"] == "unavailable"
    assert result["project_economics"] is None
    assert result["annual_cashflows"] == []
    assert any(item["code"] == "missing_or_invalid_cost" for item in result["errors"])
    assert_finite_json(result)


def test_explicit_zero_cost_is_distinct_from_unknown():
    unknown = calculate(costs={})
    free = calculate(costs={"led_lighting": 0})
    assert unknown["project_economics"] is None
    assert free["project_economics"]["net_initial_cost_inr"] == 0
    assert free["project_economics"]["simple_payback"]["years"] == 0
    assert free["project_economics"]["discounted_payback"]["years"] == 0


def test_changed_selected_package_requires_new_selected_cost_and_ignores_stale():
    result = calculate(sample(actions=["efficient_ac"]), {"led_lighting": 20000})
    assert result["status"] == "unavailable"
    assert result["costs"]["ignored_unselected_cost_ids"] == ["led_lighting"]
    result = calculate(sample(actions=["efficient_ac"]), {"led_lighting": 20000, "efficient_ac": 50000})
    assert result["project_economics"]["gross_installation_cost_inr"] == 50000
    assert [item["retrofit_id"] for item in result["costs"]["selected_installation_costs"]] == ["efficient_ac"]


def test_cost_provenance_preserved_and_not_verified():
    result = calculate(costs={"led_lighting": {"amount_inr": 1234, "source": "Quote A"}})
    assert result["costs"]["selected_installation_costs"] == [{"retrofit_id": "led_lighting", "amount_inr": 1234., "source": "Quote A", "independently_verified": False}]


def test_lpg_and_png_priced_separately_and_negative_electricity_preserved():
    scenario = sample(electricity=-100, lpg=2 * LPG_KWH_PER_KG, png=30)
    result = calculate(scenario, {"led_lighting": 100})
    assert result["annual_savings"]["total_inr_per_year"] == pytest.approx(-1000 + 120 + 150)
    assert [term["Unit"] for term in result["annual_savings"]["terms"]] == ["kWh", "kg", "kWh net CV"]
    assert result["project_economics"]["discounted_net_benefit_inr"] < 0
    assert result["project_economics"]["simple_payback"]["status"] == "not_reached"
    assert result["project_economics"]["discounted_payback"]["status"] == "not_reached"


def test_real_engine_selected_package_integrates_without_modifying_it():
    scenario = evaluate_scenario(deepcopy(DEFAULT_HOME), {"annual_grid_kwh": 6500, "annual_lpg_kwh": 1000, "annual_png_kwh": 0}, ["led_lighting", "induction"])
    original = deepcopy(scenario)
    result = calculate(scenario, {"led_lighting": 500, "induction": 2500})
    assert result["status"] == "scenario_only"
    assert scenario == original
    assert result["project_economics"]["gross_installation_cost_inr"] == 3000
    assert result["annual_savings"]["terms"][1]["Saved units/year"] == pytest.approx(1000 / LPG_KWH_PER_KG)


def test_reject_stale_bill_trace_after_changing_selected_savings():
    scenario = sample()
    trace = price(scenario)
    scenario["savings"]["electricity_kwh"] = 2000
    result = calculate_financial_scenario(scenario, trace, {"led_lighting": 500}, years=10, discount_rate=.1, escalation_rate=0)
    assert result["status"] == "unavailable"
    assert any(item["code"] == "conflicting_bill_trace" for item in result["errors"])


def test_conflicting_bill_total_rejected():
    scenario = sample()
    trace = price(scenario)
    trace["total_inr_per_year"] += 1
    result = calculate_financial_scenario(scenario, trace, {"led_lighting": 0}, years=2, discount_rate=0, escalation_rate=0)
    assert result["project_economics"] is None


@pytest.mark.parametrize("changes", [
    {"years": 0}, {"years": 2.5}, {"years": True}, {"years": float("inf")},
    {"discount_rate": -1}, {"discount_rate": "0.1"}, {"discount_rate": float("nan")},
    {"escalation_rate": float("inf")}, {"annual_maintenance_inr": -1},
    {"timing": "unknown"}, {"timing": []},
    {"replacements": [{"year": 11, "cost_inr": 1}]},
    {"replacements": [{"year": True, "cost_inr": 1}]},
    {"replacements": [{"year": 2, "cost_inr": float("nan")}]},
    {"replacements": "not a list"},
])
def test_invalid_assumptions_return_structured_errors_and_finite_json(changes):
    result = calculate(**changes)
    assert result["status"] == "unavailable"
    assert result["project_economics"] is None
    assert all(set(item) == {"code", "field", "message"} for item in result["errors"])
    assert_finite_json(result)


def test_simple_payback_and_discounted_recovery_are_distinct():
    result = calculate(years=4, discount_rate=.1, escalation_rate=0)
    economics = result["project_economics"]
    assert economics["simple_payback"]["years"] == 2
    assert economics["discounted_payback"]["years"] == 3
    assert "No fractional" in economics["discounted_payback"]["definition"]


def test_later_replacement_can_reverse_an_earlier_recovery():
    result = calculate(costs={"led_lighting": 5000}, years=3, discount_rate=0, escalation_rate=0,
                       replacements=[{"year": 3, "cost_inr": 40000}])
    assert result["annual_cashflows"][0]["cumulative_discounted_net_inr"] > 0
    assert result["annual_cashflows"][-1]["cumulative_discounted_net_inr"] < 0
    assert result["project_economics"]["simple_payback"]["years"] == .5
    assert result["project_economics"]["discounted_payback"]["status"] == "not_reached"


def test_multiple_replacements_in_same_year_are_all_counted():
    result = calculate(years=2, discount_rate=0, escalation_rate=0,
                       replacements=[{"year": 2, "cost_inr": 400}, {"year": 2, "cost_inr": 600}])
    assert result["annual_cashflows"][1]["replacement_inr"] == 1000


def test_supported_extreme_rates_still_produce_finite_json():
    result = calculate(years=50, discount_rate=-.99, escalation_rate=2, annual_maintenance_inr=1e12)
    assert result["status"] == "scenario_only"
    assert_finite_json(result)


def test_tiny_positive_saving_does_not_export_infinite_payback():
    result = calculate(sample(electricity=1e-308), {"led_lighting": 1e12})
    assert result["project_economics"]["simple_payback"]["status"] == "not_reached"
    assert_finite_json(result)


def test_no_subsidy_or_existing_asset_credit_assumed():
    existing = sample()
    existing["home_after"] = {"solar_kw": 3}
    result = calculate(existing)
    assert result["costs"]["new_solar_capacity_kw"] == 0
    assert result["project_economics"]["solar_subsidy_inr"] == 0
    assert result["report_value_scenario"] is None
    assert result["resale_value_prediction"]["status"] == "unavailable"


def test_user_confirmed_subsidy_requires_new_solar_and_provenance():
    scenario = sample(actions=["solar"])
    result = calculate(scenario, {"solar": 180000}, solar_subsidy_inr=78000,
                       solar_subsidy_confirmed=True, solar_subsidy_source="User-declared approved award")
    assert result["status"] == "scenario_only"
    assert result["project_economics"]["net_initial_cost_inr"] == 102000
    assert result["costs"]["new_solar_capacity_kw"] == 3
    assert result["costs"]["subsidy_independently_verified"] is False


@pytest.mark.parametrize("options", [
    {"solar_subsidy_inr": 78000},
    {"solar_subsidy_inr": None, "solar_subsidy_confirmed": True},
    {"solar_subsidy_inr": 78000, "solar_subsidy_confirmed": True},
    {"solar_subsidy_inr": 180001, "solar_subsidy_confirmed": True, "solar_subsidy_source": "User award"},
    {"solar_subsidy_inr": float("nan")},
    {"solar_subsidy_inr": -1},
])
def test_invalid_subsidy_withholds_outputs(options):
    result = calculate(sample(actions=["solar"]), {"solar": 180000}, **options)
    assert result["project_economics"] is None
    assert_finite_json(result)


def test_subsidy_for_existing_pv_is_rejected():
    result = calculate(solar_subsidy_inr=1000, solar_subsidy_confirmed=True, solar_subsidy_source="Existing installation")
    assert result["status"] == "unavailable"


@pytest.mark.parametrize("change", [{"before": 1, "after": 3}, {"before": 0, "after": 5}, None])
def test_new_pv_requires_trace_of_zero_to_three_kw(change):
    scenario = sample(actions=["solar"])
    scenario["calculation_trace"]["selected_steps"][0]["physical_input_changes"] = {"solar_kw": change}
    result = calculate(scenario, {"solar": 180000})
    assert result["status"] == "unavailable"
    assert any(error["code"] == "invalid_new_solar" for error in result["errors"])


def hypothetical(**changes):
    return {"enabled": True, "baseline_value_inr": 10000000,
            "premium_low_percent": 1, "premium_high_percent": 3,
            "source": "User sensitivity assumptions", **changes}


def test_hypothetical_premiums_are_user_inputs_with_no_npv_link():
    first = calculate(value_scenario=hypothetical())
    second = calculate(sample(electricity=-1000), {"led_lighting": 1000000}, value_scenario=hypothetical())
    assert first["report_value_scenario"] == second["report_value_scenario"]
    scenario = first["report_value_scenario"]
    assert scenario["status"] == "hypothetical_only"
    assert scenario["valuation_uplift_range_inr"] == [100000, 300000]
    assert scenario["post_retrofit_hypothetical_value_range_inr"] == [10100000, 10300000]
    assert first["resale_value_prediction"]["status"] == "unavailable"
    assert "not observed transaction" in scenario["disclosures"][0]


def test_explicit_carpet_area_rate_can_define_hypothetical_baseline():
    config = hypothetical(baseline_value_inr=None, carpet_area_sqft=1000, assumed_rate_inr_per_sqft=7500)
    result = calculate(value_scenario=config)
    assert result["report_value_scenario"]["baseline_value_inr"] == 7500000
    assert result["report_value_scenario"]["carpet_area_sqft"] == 1000


@pytest.mark.parametrize("options", [
    {"baseline_value_inr": None}, {"baseline_value_inr": float("nan")},
    {"carpet_area_sqft": 1000, "assumed_rate_inr_per_sqft": 7500},
    {"premium_low_percent": None}, {"premium_high_percent": float("inf")},
    {"premium_low_percent": 4, "premium_high_percent": 2},
    {"premium_low_percent": -1}, {"premium_high_percent": 101},
    {"cap_ratio": .08}, {"scenario_spread": .35},
    {"include_solar_asset_proxy": True}, {"solar_asset_multiplier": 1.1},
])
def test_invalid_optional_value_inputs_do_not_disable_valid_investment_analysis(options):
    result = calculate(value_scenario=hypothetical(**options))
    assert result["status"] == "scenario_only"
    assert result["project_economics"] is not None
    assert result["report_value_scenario"] is None
    assert result["valuation_errors"]
    assert_finite_json(result)


def test_disabled_hypothetical_output_requires_no_property_data():
    result = calculate(value_scenario={"enabled": False})
    assert result["valuation_errors"] == []
    assert result["report_value_scenario"] is None


@pytest.mark.parametrize("broken", [None, {}, {"applied": ["unknown"]}, {"applied": [["solar"]]},
                                     {"applied": ["solar", "solar"]}])
def test_malformed_scenarios_have_structured_errors(broken):
    result = calculate_financial_scenario(broken, {}, {}, years=1, discount_rate=0, escalation_rate=0)
    assert result["status"] == "unavailable"
    assert result["errors"]
    assert_finite_json(result)


def test_unavailable_energy_scenario_cannot_produce_investment_metrics():
    scenario = sample()
    scenario["calculation_trace"]["status"] = "unavailable"
    result = calculate(scenario)
    assert result["project_economics"] is None


def test_empty_package_withholds_investment_outputs():
    result = calculate(sample(electricity=0, actions=[]), {})
    assert result["status"] == "unavailable"
    assert result["project_economics"] is None
    assert result["errors"][0]["code"] == "no_package"
    assert result["report_value_scenario"] is None
