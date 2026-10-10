"""Check that explanation responses cannot introduce unsupported claims."""
import json
from unittest.mock import patch

import pytest

from greenhome.explanations import explain, fact_library, select_fact_ids


@pytest.fixture
def scenario():
    return {
        "baseline": {"annual_grid_kwh": 5000.0, "annual_gas_kwh": 1000.0},
        "after": {"annual_grid_kwh": 5500.0, "annual_gas_kwh": 0.0},
        "savings": {"electricity_kwh": -500.0, "gas_kwh": 1000.0, "percent": 8.333, "carbon_kg": -130.84},
        "applied": ["induction"],
        "recommendations": [{"id": "induction", "name": "Induction cooking"}],
        "flags": [],
    }


def test_offline_explanation_uses_only_computed_facts(scenario):
    facts = fact_library(scenario, "annual bills")
    answer = explain(scenario, "annual bills")
    assert answer["paragraphs"] == [facts[x] for x in answer["fact_ids"]]
    assert "an increase" in facts["carbon"]
    assert "-500" in facts["fuel_changes"]
    assert "limitation" in answer["fact_ids"]


def test_unknown_fact_is_rejected(scenario):
    with pytest.raises(ValueError, match="unsupported"):
        select_fact_ids({"fact_ids": ["guaranteed_50_percent_appreciation"]}, fact_library(scenario, "annual bills"))


def test_llm_invalid_fact_falls_back_without_rendering_claim(scenario):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"output": [{"content": [{"type": "output_text", "text": '{"fact_ids":["made_up"]}'}]}]}).encode()

    with patch("greenhome.explanations.request.urlopen", return_value=FakeResponse()):
        answer = explain(scenario, "annual bills", api_key="test-key")
    assert answer["mode"] == "Offline fallback"
    assert answer["error"]
    assert all("made_up" not in x for x in answer["paragraphs"])


def test_llm_valid_selection_preserves_exact_fact_text(scenario):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"output": [{"content": [{"type": "output_text", "text": '{"fact_ids":["carbon","fuel_changes"]}'}]}]}).encode()

    with patch("greenhome.explanations.request.urlopen", return_value=FakeResponse()):
        answer = explain(scenario, "annual bills", api_key="test-key")
    facts = fact_library(scenario, "annual bills")
    assert answer["mode"] == "AI-selected computed facts"
    assert answer["paragraphs"] == [facts[x] for x in answer["fact_ids"]]
    assert "limitation" in answer["fact_ids"]


@pytest.fixture
def financial_scenario():
    return {
        "status": "scenario_only",
        "project_economics": {
            "net_initial_cost_inr": 45000.0,
            "present_value_bill_savings_inr": 35000.0,
            "discounted_net_benefit_inr": -10000.0,
            "simple_payback": {"status": "reached", "years": 4.5},
            "discounted_payback": {"status": "not_reached", "years": None},
        },
        "report_value_scenario": {
            "status": "hypothetical_only",
            "baseline_value_inr": 10000000.0,
            "premium_low_percent": 2.0,
            "premium_high_percent": 5.0,
            "post_retrofit_hypothetical_value_range_inr": [10200000.0, 10500000.0],
        },
    }


def test_finance_explanation_retains_signed_loss_and_user_value_sensitivity(scenario, financial_scenario):
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    answer = explain(scenario, "annual bills")
    assert "net loss of ₹10,000" in facts["financial"]
    assert "net benefit" not in facts["financial"]
    assert "not verified quotes" in facts["financial"]
    assert "entered premium sensitivity of 2%–5%" in facts["property_value"]
    assert "not an estimated resale uplift" in facts["property_value"]
    assert "not a resale prediction" in facts["property_value"]
    assert {"financial", "property_value", "limitation"} <= set(answer["fact_ids"])
    assert len(answer["fact_ids"]) <= 7
    assert answer["paragraphs"] == [facts[x] for x in answer["fact_ids"]]


def test_finance_positive_net_benefit_is_not_described_as_loss(scenario, financial_scenario):
    financial_scenario["project_economics"]["discounted_net_benefit_inr"] = 10000.0
    scenario["financial_scenario"] = financial_scenario
    fact = fact_library(scenario, "annual bills")["financial"]
    assert "net benefit of ₹10,000" in fact
    assert "net loss" not in fact


def test_negative_present_value_savings_remains_signed(scenario, financial_scenario):
    financial_scenario["project_economics"].update({
        "present_value_bill_savings_inr": -5000.0,
        "discounted_net_benefit_inr": -50000.0,
    })
    scenario["financial_scenario"] = financial_scenario
    fact = fact_library(scenario, "annual bills")["financial"]
    assert "present value of bill savings is ₹-5,000" in fact
    assert "net loss of ₹50,000" in fact


def test_missing_costs_withhold_stale_financial_outcomes(scenario, financial_scenario):
    # A previous completed result must not survive an unavailable current calculation.
    financial_scenario.update({"status": "unavailable", "errors": [{"code": "missing_cost", "field": "costs", "message": "Enter the installation cost."}]})
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    answer = explain(scenario, "annual bills")
    assert "financial_unavailable" in answer["fact_ids"]
    assert not {"financial", "simple_payback", "discounted_payback", "property_value"} & set(facts)
    assert all("₹" not in paragraph for paragraph in answer["paragraphs"])


def test_no_completed_economics_produces_no_value_or_payback_claim(scenario, financial_scenario):
    financial_scenario["project_economics"] = None
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    assert "financial_unavailable" in facts
    assert not {"financial", "property_value", "simple_payback", "discounted_payback"} & set(facts)


@pytest.mark.parametrize("bad_amount", [float("nan"), float("inf"), True, "45000"])
def test_invalid_financial_amounts_are_never_explained(scenario, financial_scenario, bad_amount):
    financial_scenario["project_economics"]["net_initial_cost_inr"] = bad_amount
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    assert "financial_unavailable" in facts
    assert "financial" not in facts
    assert "property_value" not in facts


def test_legacy_automatic_property_proxy_is_not_explained(scenario, financial_scenario):
    del financial_scenario["report_value_scenario"]["premium_low_percent"]
    del financial_scenario["report_value_scenario"]["premium_high_percent"]
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    assert "financial" in facts
    assert "property_value" not in facts


@pytest.mark.parametrize("value_change", [
    {"status": "predicted"},
    {"premium_low_percent": float("nan")},
    {"premium_low_percent": 8.0, "premium_high_percent": 2.0},
    {"post_retrofit_hypothetical_value_range_inr": [10500000.0, 10200000.0]},
])
def test_invalid_property_sensitivity_does_not_hide_valid_finance(scenario, financial_scenario, value_change):
    financial_scenario["report_value_scenario"].update(value_change)
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    assert "financial" in facts
    assert "property_value" not in facts


def test_payback_facts_use_only_completed_payback_fields(scenario, financial_scenario):
    scenario["financial_scenario"] = financial_scenario
    facts = fact_library(scenario, "annual bills")
    assert "4.50 years" in facts["simple_payback"]
    assert "not reached within the analysis horizon" in facts["discounted_payback"]
    financial_scenario["project_economics"]["simple_payback"]["years"] = float("nan")
    assert "simple_payback" not in fact_library(scenario, "annual bills")


def test_discounted_payback_fact_requires_lasting_recovery_through_horizon(scenario, financial_scenario):
    financial_scenario["project_economics"]["discounted_payback"] = {"status": "reached", "years": 8}
    scenario["financial_scenario"] = financial_scenario
    fact = fact_library(scenario, "annual bills")["discounted_payback"]
    assert "8.00 years" in fact
    assert "stays so through the modeled horizon" in fact
    assert "beyond that horizon is not established" in fact
    assert "later expenses can reverse" not in fact


def test_simple_payback_beyond_horizon_is_explained_as_such(scenario, financial_scenario):
    financial_scenario["project_economics"]["simple_payback"] = {"status": "not_reached", "years": 25}
    scenario["financial_scenario"] = financial_scenario
    fact = fact_library(scenario, "annual bills")["simple_payback"]
    assert "25.00 years, exceeding the analysis horizon" in fact


def test_finance_not_requested_leaves_existing_offline_default_unchanged(scenario):
    original = explain(scenario, "annual bills")
    scenario["financial_scenario"] = {"status": "not_requested", "project_economics": None}
    assert explain(scenario, "annual bills") == original


def test_unavailable_fact_distinguishes_entered_costs_from_verified_quotes(scenario, financial_scenario):
    scenario["financial_scenario"] = financial_scenario
    unavailable = fact_library(scenario, "annual bills")["unavailable"]
    assert "verified installation quotes" in unavailable
    assert "Entered costs remain scenario assumptions" in unavailable
    assert "cannot establish property appreciation, installation cost" not in unavailable
