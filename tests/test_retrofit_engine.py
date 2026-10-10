"""Public decision priorities must preserve signs, interactions and unknowns."""
from copy import deepcopy

import pytest

from greenhome.engine import RETROFITS, evaluate_scenario
from greenhome.retrofit_engine import recommend_retrofits
from greenhome.schema import DEFAULT_HOME


ENERGY = {"annual_grid_kwh": 6500.0, "annual_lpg_kwh": 1800.0, "annual_png_kwh": 0.0}
TARIFFS = {"electricity_rate": 8.0, "lpg_price_kg": 65.0, "png_rate": 5.0}


def home(**changes):
    return {**deepcopy(DEFAULT_HOME), "usable_roof_area_m2": 50.0,
            "solar_shading_ok": True, "solar_structure_ok": True,
            "solar_electrical_ok": True, **changes}


def rows_by_id(result):
    return {row["id"]: row for row in result["ranked_candidates"]}


def test_package_is_rerun_and_each_decision_improves_whole_package_objective():
    result = recommend_retrofits(home(), ENERGY, tariffs=TARIFFS)
    assert result["status"] == "available"
    assert result["selected_ids"]
    expected = evaluate_scenario(home(require_site_checks=True), ENERGY, result["selected_ids"])
    assert result["scenario"]["after"] == expected["after"]
    assert result["selected_ids"] == [item["id"] for item in RETROFITS if item["id"] in result["selected_ids"]]
    increments = []
    for round_ in result["decision_audit"]:
        if round_["chosen_id"] is None:
            assert all(item["incremental_objective_benefit"] <= 0 for item in round_["evaluations"])
            continue
        chosen = next(item for item in round_["evaluations"] if item["id"] == round_["chosen_id"])
        assert chosen["incremental_objective_benefit"] > 0
        assert chosen["incremental_objective_benefit"] == max(item["incremental_objective_benefit"] for item in round_["evaluations"])
        assert chosen["incremental_objective_benefit"] == pytest.approx(chosen["package_objective_benefit"] - round_["current_objective_benefit"])
        increments.append(chosen["incremental_objective_benefit"])
    assert sum(increments) == pytest.approx(result["package_objective_benefit"])
    selected = [row for row in result["ranked_candidates"] if row["selected"]]
    assert sum(row["package_marginal_objective_benefit"] for row in selected) == pytest.approx(result["package_objective_benefit"])
    assert result["package_bill_trace"]["total_inr_per_year"] == pytest.approx(result["package_objective_benefit"])


def test_pv_interaction_can_make_negative_standalone_bill_option_positive_in_package():
    result = recommend_retrofits(home(), ENERGY, tariffs=TARIFFS)
    induction = rows_by_id(result)["induction"]
    assert induction["objective_benefit"] < 0
    assert induction["standalone_savings"]["electricity_kwh"] < 0
    assert induction["selected"] is True
    assert induction["decision_incremental_benefit"] > 0
    # Installation puts induction before PV; this differs from selecting it
    # after a package that already contains PV. Both comparisons stay explicit.
    assert induction["package_marginal_objective_benefit"] < 0
    assert induction["package_marginal_trace"]["comparison"] == "selected_package_marginal"


def test_carbon_priority_excludes_incrementally_harmful_induction_but_keeps_signed_row():
    result = recommend_retrofits(home(), ENERGY, objective="carbon_savings")
    assert result["status"] == "available"
    induction = rows_by_id(result)["induction"]
    assert induction["objective_benefit"] < 0
    assert induction["selected"] is False
    assert induction["final_addition_objective_benefit"] < 0
    assert induction["package_marginal_savings"] is None
    assert "does not improve" in induction["selection_reason"]


def test_energy_priority_does_not_sum_interacting_standalone_savings():
    result = recommend_retrofits(home(), ENERGY, objective="energy_savings")
    assert result["status"] == "available"
    assert result["package_objective_benefit"] == pytest.approx(result["scenario"]["savings"]["total_kwh"])
    assert sum(row["standalone_savings"]["total_kwh"] for row in result["ranked_candidates"] if row["selected"]) > result["package_objective_benefit"]
    assert sum(row["package_marginal_savings"]["total_kwh"] for row in result["ranked_candidates"] if row["selected"]) == pytest.approx(result["package_objective_benefit"])


def test_all_unknown_pv_checks_block_solar_without_mutating_caller():
    property_data = deepcopy(DEFAULT_HOME)
    property_data["require_site_checks"] = False
    before = deepcopy(property_data)
    result = recommend_retrofits(property_data, ENERGY, objective="energy_savings")
    assert "solar" not in rows_by_id(result)
    assert "solar" in {item["id"] for item in result["rejected"]}
    assert property_data == before


@pytest.mark.parametrize("field,value", [
    ("usable_roof_area_m2", None), ("usable_roof_area_m2", 29.0),
    ("solar_shading_ok", None), ("solar_structure_ok", False),
    ("solar_electrical_ok", None), ("roof_access", False),
])
def test_explicit_pv_site_and_permission_constraints_are_enforced(field, value):
    result = recommend_retrofits(home(**{field: value}), ENERGY, objective="energy_savings")
    assert "solar" not in result["selected_ids"]
    assert any(item["id"] == "solar" and item["reason"] for item in result["rejected"])


def test_unknown_consent_rejects_every_known_option_without_inventing_a_package():
    result = recommend_retrofits(home(retrofit_consent=None), ENERGY, tariffs=TARIFFS)
    assert result["status"] == "available"
    assert result["ranked_candidates"] == []
    assert result["selected_ids"] == []
    assert {item["id"] for item in result["rejected"]} == {item["id"] for item in RETROFITS}
    assert result["package_objective_benefit"] == 0


@pytest.mark.parametrize("rates", [None, {}, {**TARIFFS, "electricity_rate": None},
                                   {**TARIFFS, "lpg_price_kg": -1},
                                   {**TARIFFS, "png_rate": float("nan")}])
def test_invalid_rates_withhold_bill_priorities_only(rates):
    bill = recommend_retrofits(home(), ENERGY, tariffs=rates)
    assert bill["status"] == "unavailable"
    assert bill["selected_ids"] == []
    assert bill["decision_audit"] == []
    assert all(row["rank"] is None for row in bill["ranked_candidates"])
    energy = recommend_retrofits(home(), ENERGY, objective="energy_savings", tariffs=rates)
    assert energy["status"] == "available"
    assert energy["selected_ids"]


def test_invalid_carbon_factor_withholds_carbon_but_preserves_energy_and_bill_priorities():
    factors = {"electricity_kg_co2_per_kwh": None}
    carbon = recommend_retrofits(home(), ENERGY, objective="carbon_savings", factors=factors)
    assert carbon["status"] == "unavailable"
    assert carbon["selected_ids"] == []
    assert all(row["objective_benefit"] is None for row in carbon["ranked_candidates"])
    for objective in ("energy_savings", "bill_savings"):
        result = recommend_retrofits(home(), ENERGY, objective=objective, tariffs=TARIFFS, factors=factors)
        assert result["status"] == "available"
        assert result["scenario"]["savings"]["carbon_kg"] is None


@pytest.mark.parametrize("property_data,energy", [
    (home(area_m2=None), ENERGY),
    (home(), {**ENERGY, "annual_lpg_kwh": None}),
    (home(), {**ENERGY, "annual_png_kwh": 100}),
    (home(), {**ENERGY, "annual_gas_kwh": 1}),
])
def test_invalid_core_inputs_never_receive_priorities(property_data, energy):
    result = recommend_retrofits(property_data, energy, tariffs=TARIFFS)
    assert result["status"] == "unavailable"
    assert result["reasons"]
    assert result["selected_ids"] == []
    assert result["package_objective_benefit"] is None
    assert all(row["rank"] is None for row in result["ranked_candidates"])


def test_equal_zero_effects_use_stage_order_and_no_positive_package_is_invented():
    zero_tariffs = dict.fromkeys(TARIFFS, 0.0)
    result = recommend_retrofits(home(), ENERGY, tariffs=zero_tariffs)
    assert result["status"] == "available"
    assert result["selected_ids"] == []
    assert result["package_objective_benefit"] == 0
    assert [row["id"] for row in result["ranked_candidates"]] == [item["id"] for item in RETROFITS]
    assert len(result["decision_audit"]) == 1
    assert result["decision_audit"][0]["chosen_id"] is None


def test_png_is_preserved_separately_and_assumed_engineering_inputs_are_exposed():
    result = recommend_retrofits(home(cooking_fuel="png"),
                                {"annual_grid_kwh": 6500., "annual_lpg_kwh": 0., "annual_png_kwh": 1800.},
                                objective="energy_savings")
    induction = rows_by_id(result)["induction"]
    assert induction["standalone_savings"]["lpg_kwh"] == 0
    assert induction["standalone_savings"]["png_kwh"] == 1800
    assert "ac_iseer" in result["assumed_inputs"]
    assert result["scenario"]["baseline"]["annual_gas_kwh"] == 1800


def test_objective_is_checked_and_candidate_overflow_does_not_produce_ranks():
    result = recommend_retrofits(home(), ENERGY, objective="payback", tariffs=TARIFFS)
    assert result["status"] == "unavailable"
    assert result["selected_ids"] == []
    result = recommend_retrofits(home(), ENERGY, tariffs={**TARIFFS, "electricity_rate": 1e308})
    assert result["status"] == "unavailable"
    assert all(row["rank"] is None for row in result["ranked_candidates"])
    assert result["selected_ids"] == []


def test_no_predictor_is_loaded_and_repeated_priorities_are_deterministic(monkeypatch):
    import greenhome.ml

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Bill-based decisions must not call a fitted predictor")

    monkeypatch.setattr(greenhome.ml, "predict_energy", forbidden)
    monkeypatch.setattr(greenhome.ml, "load_models", forbidden)
    first = recommend_retrofits(home(), ENERGY, tariffs=TARIFFS)
    second = recommend_retrofits(home(), ENERGY, tariffs=TARIFFS)
    assert first == second
