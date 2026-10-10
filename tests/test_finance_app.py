"""Verify financial packages work while property-value estimation is deferred."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def sample_app(preset="Rooftop solar"):
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.radio(key="bill_mode").set_value("Try fictional sample").run()
    app.selectbox(key="preset").set_value(preset).run()
    assert not app.exception
    return app


def financial_record(app):
    return next(json.loads(item.value) for item in app.json if '"project_economics"' in item.value)


def test_finance_opt_in_requires_cost_and_does_not_award_subsidy():
    app = sample_app()
    assert app.checkbox(key="finance_enabled").value is False
    assert not any(item.label == "Net installation cost" for item in app.metric)
    app.checkbox(key="finance_enabled").check().run()
    assert not app.exception
    assert app.number_input(key="finance_cost_solar").value is None
    assert app.checkbox(key="finance_subsidy_confirmed").value is False
    assert "finance_value_enabled" not in [item.key for item in app.checkbox]
    assert not any(item.label == "Net installation cost" for item in app.metric)
    app.number_input(key="finance_cost_solar").set_value(180000.0).run()
    assert not app.exception
    finance = financial_record(app)
    assert finance["status"] == "scenario_only"
    assert finance["project_economics"]["net_initial_cost_inr"] == 180000
    assert finance["project_economics"]["solar_subsidy_inr"] == 0
    assert finance["report_value_scenario"] is None
    assert finance["resale_value_prediction"]["status"] == "unavailable"


def test_package_change_drops_old_costs_and_requires_new_costs():
    app = sample_app()
    app.checkbox(key="finance_enabled").check().run()
    app.number_input(key="finance_cost_solar").set_value(180000.0).run()
    assert financial_record(app)["project_economics"]["net_initial_cost_inr"] == 180000
    app.selectbox(key="preset").set_value("Switch cooking to induction").run()
    assert not app.exception
    assert app.number_input(key="finance_cost_induction").value is None
    assert not any(item.label == "Net installation cost" for item in app.metric)
    assert "finance_subsidy_confirmed" not in [item.key for item in app.checkbox]
    app.number_input(key="finance_cost_induction").set_value(5000.0).run()
    assert financial_record(app)["project_economics"]["net_initial_cost_inr"] == 5000


def test_property_value_is_deferred_and_old_premium_inputs_cannot_reappear():
    app = sample_app()
    assert any("Property-value impact is deferred" in item.value for item in app.info)
    assert "Costs & payback" in [item.label for item in app.tabs]
    # Old sessions may retain premium values from the previous release.
    app.session_state["finance_value_enabled"] = True
    app.session_state["finance_property_value"] = 7500000.0
    app.session_state["finance_premium"] = (1.0, 3.0)
    app.checkbox(key="finance_enabled").check().run()
    app.number_input(key="finance_cost_solar").set_value(180000.0).run()
    assert not app.exception
    finance = financial_record(app)
    assert finance["project_economics"]["net_initial_cost_inr"] == 180000
    assert finance["report_value_scenario"] is None
    assert finance["resale_value_prediction"]["status"] == "unavailable"
    assert finance["property_value_scope"]["status"] == "deferred"
    assert "finance_value_enabled" not in [item.key for item in app.checkbox]
    assert "finance_property_value" not in [item.key for item in app.number_input]
    assert "finance_premium" not in [item.key for item in app.slider]


def test_replacement_expense_and_confirmed_subsidy_are_explicit():
    app = sample_app()
    app.checkbox(key="finance_enabled").check().run()
    app.number_input(key="finance_cost_solar").set_value(180000.0)
    app.checkbox(key="finance_subsidy_confirmed").check().run()
    assert app.number_input(key="finance_subsidy").value is None
    assert not any(item.label == "Net installation cost" for item in app.metric)
    app.number_input(key="finance_subsidy").set_value(78000.0)
    app.text_input(key="finance_subsidy_source").set_value("Fictional approval example")
    app.checkbox(key="finance_replacement_enabled").check().run()
    assert app.number_input(key="finance_replacement_cost").value is None
    app.number_input(key="finance_replacement_cost").set_value(20000.0).run()
    assert not app.exception
    finance = financial_record(app)
    assert finance["project_economics"]["net_initial_cost_inr"] == 102000
    assert finance["project_economics"]["present_value_replacements_inr"] == pytest.approx(20000 / 1.085 ** 8)
    app.number_input(key="finance_years").set_value(5).run()
    assert not app.exception
    assert app.number_input(key="finance_replacement_year").value == 5
