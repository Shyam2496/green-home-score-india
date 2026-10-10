"""Exercise user-facing what-if, permissions, and zero-baseline flows."""
from pathlib import Path
import json

from streamlit.testing.v1 import AppTest


def test_dashboard_flows():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.checkbox(key="use_bills").uncheck().run()
    assert not app.exception
    assert app.metric[0].label == "Green Home Score"
    assert "Unavailable" not in app.metric[0].value
    app.selectbox(key="preset").set_value("Switch cooking to induction").run()
    assert not app.exception
    assert app.multiselect(key="selected_retrofits").value == ["induction"]
    assert "-" in app.metric[2].value  # Default grid proxy can increase CO2.

    app.checkbox(key="demo_roof_access").uncheck().run()
    app.selectbox(key="preset").set_value("Rooftop solar").run()
    assert not app.exception
    assert "solar" not in app.multiselect(key="selected_retrofits").options
    assert app.multiselect(key="selected_retrofits").value == []

    app.checkbox(key="use_bills").check().run()
    app.number_input(key="bill_grid").set_value(0.0)
    app.number_input(key="bill_lpg").set_value(0.0).run()
    assert not app.exception
    assert app.metric[0].value == "Unavailable"
    assert app.metric[1].delta == "No valid baseline"

    app.checkbox(key="use_bills").uncheck().run()
    app.selectbox(key="cooling").set_value("fans_only").run()
    app.selectbox(key="city").set_value("Bengaluru").run()
    assert not app.exception
    assert app.selectbox(key="city").value == "Bengaluru"
    assert "Unavailable" not in app.metric[0].value


def test_png_and_detailed_inputs_work_in_dashboard():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.checkbox(key="use_bills").uncheck().run()
    app.selectbox(key="cooking_fuel").set_value("png").run()
    assert not app.exception
    app.checkbox(key="detailed_inputs").check().run()
    app.number_input(key="ac_iseer").set_value(4.0).run()
    assert not app.exception
    app.selectbox(key="preset").set_value("Switch cooking to induction").run()
    assert not app.exception
    assert app.multiselect(key="selected_retrofits").value == ["induction"]


def test_annual_inputs_are_blank_complete_and_do_not_load_predictor(monkeypatch):
    import greenhome.ml

    def forbidden(*args, **kwargs):
        raise AssertionError("Annual consumption mode must not require a trained predictor")

    monkeypatch.setattr(greenhome.ml, "load_models", forbidden)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.number_input(key="bill_grid").value is None
    assert app.number_input(key="bill_lpg").value is None
    assert not app.metric
    app.number_input(key="bill_grid").set_value(3000.0).run()
    assert not app.metric  # Unknown LPG is not zero.
    app.number_input(key="bill_lpg").set_value(85.2).run()
    assert not app.exception
    assert app.metric[4].label == "Annual grid import"
    assert app.metric[4].value == "3,000 kWh"
    app.checkbox(key="retrofit_consent").check()
    app.checkbox(key="roof_access").check()
    app.selectbox(key="heritage_status").set_value("None confirmed").run()
    app.selectbox(key="preset").set_value("Cooling & lighting").run()
    trace = next(json.loads(item.value) for item in app.json if "selected_steps" in item.value)
    assert trace["anchor"]["provenance"]["source"] == "user_declared_annual_consumption"
    assert trace["anchor"]["baseline_energy"]["annual_grid_kwh"] == 3000
    assert len(trace["selected_steps"]) == 5
    assert not any("90% target electricity interval" in item.value for item in app.caption)
    app.number_input(key="bill_months").set_value(6).run()
    assert not app.exception
    assert not app.metric
    assert any("Partial-year" in item.value for item in app.info)


def test_fictional_sample_is_explicit_and_png_does_not_request_lpg():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.radio(key="bill_mode").set_value("Try fictional sample").run()
    assert not app.exception
    assert any("Fictional sample mode" in item.value for item in app.warning)
    trace = next(json.loads(item.value) for item in app.json if "selected_steps" in item.value)
    assert trace["anchor"]["provenance"]["source"] == "fictional_sample"
    app.radio(key="bill_mode").set_value("Enter my totals").run()
    app.selectbox(key="cooking_fuel").set_value("png").run()
    assert "bill_lpg" not in [item.key for item in app.number_input]
    app.number_input(key="bill_grid").set_value(2400.0)
    app.number_input(key="bill_png").set_value(900.0).run()
    assert not app.exception
    assert app.metric[7].value == "900 kWh"


def test_suggested_package_recalculates_and_respects_solar_site_inputs():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.radio(key="bill_mode").set_value("Try fictional sample").run()
    app.selectbox(key="recommendation_goal").set_value("Reduce operational CO₂").run()
    app.button(key="use_suggested").click().run()
    assert not app.exception
    assert app.multiselect(key="selected_retrofits").value
    assert app.selectbox(key="preset").value == "Choose improvements"
    assert not app.metric[2].value.startswith("-")
    app.number_input(key="demo_usable_roof_area_m2").set_value(20.0).run()
    assert not app.exception
    assert "solar" not in app.multiselect(key="selected_retrofits").value
    assert any("30" in row.value and "Solar" in row.value for row in app.markdown)
    app.button(key="use_suggested").click().run()
    assert "solar" not in app.multiselect(key="selected_retrofits").value


def test_actual_bills_do_not_imply_installation_permissions():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert app.checkbox(key="retrofit_consent").value is False
    assert app.number_input(key="usable_roof_area_m2").value is None
    assert app.selectbox(key="heritage_status").value == "Unknown"
    app.number_input(key="bill_grid").set_value(3000.0)
    app.number_input(key="bill_lpg").set_value(85.2).run()
    assert not app.exception
    assert not app.multiselect(key="selected_retrofits").value
    assert app.button(key="use_suggested").disabled
    app.checkbox(key="retrofit_consent").check().run()
    assert not app.exception
    # Consent alone admits appliance measures, but not unknown roof/facade work.
    app.button(key="use_suggested").click().run()
    chosen = app.multiselect(key="selected_retrofits").value
    assert "led_lighting" in chosen
    assert "solar" not in chosen and "insulation" not in chosen
