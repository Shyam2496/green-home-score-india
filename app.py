"""Indian Green Home Score: run with python -m streamlit run app.py."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from greenhome.schema import DEFAULT_HOME, OPTIONS, FEATURES
from greenhome.ml import load_models, predict_energy, prediction_intervals, input_diagnostics
from greenhome.physics import complete_home, input_assumptions, climate_parameters
from greenhome.engine import DEFAULT_FACTORS, LPG_KWH_PER_KG, score_home, feasible_retrofits, evaluate_scenario
from greenhome.explanations import explain
from greenhome.billing import annual_bill_baseline, bill_savings_trace
from greenhome.retrofit_engine import recommend_retrofits
from greenhome.finance_ui import render_financial_scenario, PROPERTY_VALUE_DEFERRAL, PROPERTY_VALUE_SCOPE

ROOT = Path(__file__).resolve().parent
LABELS = {
    "independent": "Independent house", "row_house": "Row house", "apartment": "Apartment",
    "fans_only": "Fans only", "ac_standard": "Standard AC", "ac_efficient": "Efficient inverter AC",
    "electric_geyser": "Electric geyser", "solar_heater": "Solar water heater", "heat_pump": "Heat pump water heater", "none": "No water heating",
    "lpg": "LPG", "png": "Piped natural gas (PNG)", "induction": "Induction", "poor": "Low / no insulation", "average": "Partial insulation", "good": "Good insulation",
    "single": "Single glazing", "double": "Double glazing",
}

st.set_page_config(page_title="Green Home Score · India", page_icon="🌿", layout="wide")
st.markdown("""<style>
.stApp {background:#f6f8f3;} [data-testid="stSidebar"] {background:#edf2e8;}
.block-container {padding-top:4.5rem; max-width:1320px;}
h1,h2,h3 {color:#163e2c;} [data-testid="stMetricValue"] {color:#1d5b3c;}
[data-testid="stMetric"] {border-bottom:2px solid #bfd5aa; padding-bottom:1rem;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def models(version):
    return load_models(ROOT)


@st.cache_data
def report(version):
    path = ROOT / "reports" / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


@st.cache_data(show_spinner=False)
def decision_plan(home, baseline, objective, tariffs, factors, version):
    return recommend_retrofits(home, baseline, objective=objective, tariffs=tariffs, factors=factors)


def choose(label, field, default):
    return st.selectbox(label, OPTIONS[field], index=OPTIONS[field].index(default), format_func=lambda x: LABELS.get(x, x), key=field)


def fmt(value, unit=""):
    return "Unavailable" if value is None else f"{value:,.0f}{unit}"


def show_step_trace(step):
    if step.get("status") != "available":
        st.info(step.get("reason", "No calculation is available for this comparison."))
        return
    before, after = step["before_energy"], step["after_energy"]
    saved = step["savings"]
    st.dataframe(pd.DataFrame([
        {"Fuel": label, "Before (kWh/year)": before[key], "After (kWh/year)": after[key], "Saving (kWh/year)": saved[saving]}
        for label, key, saving in [("Grid electricity", "annual_grid_kwh", "electricity_kwh"), ("LPG", "annual_lpg_kwh", "lpg_kwh"), ("PNG", "annual_png_kwh", "png_kwh")]
    ]).round(2), hide_index=True, width="stretch")
    st.caption(f"Saving = before − after. Percentage denominator: {step['savings_percent_denominator_kwh']:,.2f} kWh purchased energy before this step. Percentages from different steps must not be added.")
    terms = step["carbon_terms_kg"]
    if saved.get("carbon_kg") is None or any(value is None for value in terms.values()):
        st.info("CO₂ calculation unavailable: one or more emission factors are invalid.")
    else:
        st.write("**CO₂ calculation:** " + " + ".join(f"{key}: {value:+,.2f} kg" for key, value in terms.items()) + f" = {saved['carbon_kg']:+,.2f} kg/year saved.")
        st.caption("Fuel saving × CO₂ factor: " + "; ".join(f"{key} {saved[f'{key}_kwh']:+,.2f} kWh × {step['carbon_factor_values'][key]:.5f} kg/kWh" for key in terms))
    changes = step["physical_input_changes"]
    if changes:
        st.write("**Changed inputs:** " + "; ".join(f"{key.replace('_', ' ')}: {value['before']} → {value['after']}" for key, value in changes.items()))
    st.dataframe(pd.DataFrame([
        {"Electricity use": key.title(), "Before (kWh/year)": value,
         "Physics change ratio": step["end_use_ratios"].get(key),
         "After (kWh/year)": step["after_end_uses_kwh"][key]}
        for key, value in step["before_end_uses_kwh"].items()
    ]).round(4), hide_index=True, width="stretch")
    if step.get("fuel_switch_conversion"):
        st.write("**Cooking conversion:**")
        st.json(step["fuel_switch_conversion"], expanded=True)
    for equation in step.get("equations", []):
        st.caption(equation)


with st.sidebar:
    st.title("Your home")
    st.caption("India · Annual household energy")
    home = dict(DEFAULT_HOME)
    home["city"] = choose("City", "city", "Hyderabad")
    home["property_type"] = choose("Home type", "property_type", "independent")
    area_unit = st.radio("Area unit", ["m²", "sq ft"], horizontal=True, key="area_unit")
    area = st.number_input("Built-up area", min_value=35.0 if area_unit == "m²" else 377.0, max_value=250.0 if area_unit == "m²" else 2690.0, value=95.0 if area_unit == "m²" else 1023.0, step=5.0 if area_unit == "m²" else 50.0, key=f"area_{area_unit}")
    home["area_m2"] = area if area_unit == "m²" else area / 10.7639104
    home["occupants"] = st.number_input("People at home", min_value=1, max_value=8, value=3, key="occupants")
    home["cooling"] = choose("Cooling", "cooling", "ac_standard")
    if home["cooling"] == "fans_only":
        home["ac_units"], home["ac_hours_per_day"] = 0, 0.0
    else:
        home["ac_units"] = st.number_input("Number of AC units", min_value=1, max_value=5, value=2, key="ac_units")
        home["ac_hours_per_day"] = st.slider("AC hours per day in cooling season", 0.5, 16.0, 6.0, 0.5, key="ac_hours")
    home["cooking_fuel"] = choose("Cooking fuel", "cooking_fuel", "lpg")
    use_bills = st.checkbox("Use annual consumption totals (recommended)", value=True, key="use_bills")
    bills, bill_input = None, None
    if use_bills:
        bill_mode = st.radio("Consumption source", ["Enter my totals", "Try fictional sample"], key="bill_mode")
        fictional = bill_mode == "Try fictional sample"
        if fictional:
            grid, lpg_kg, png_kwh, months = 3000.0, 85.2 if home["cooking_fuel"] == "lpg" else None, 1100.0 if home["cooking_fuel"] == "png" else None, 12
            st.caption(f"Fictional annual sample: {grid:,.0f} kWh grid electricity" + (f", {lpg_kg:g} kg LPG." if lpg_kg is not None else f", {png_kwh:,.0f} kWh PNG." if png_kwh is not None else ", induction cooking included in electricity."))
        else:
            st.caption("Add consumption units across the same complete 12 months, including all meters serving this home. Enter kWh, not the rupee amount. Unknown fuel use must stay blank.")
            months = st.number_input("Months covered by these totals", min_value=1, max_value=12, value=12, key="bill_months")
            grid = st.number_input("Annual grid electricity (kWh)", min_value=0.0, max_value=100000.0, value=None, step=100.0, placeholder="Sum of 12 months", key="bill_grid")
            lpg_kg = st.number_input("Annual LPG consumed (kg)", min_value=0.0, max_value=1000.0, value=None, step=14.2, placeholder="Kilograms over the same year", key="bill_lpg") if home["cooking_fuel"] == "lpg" else None
            png_kwh = st.number_input("Annual PNG consumed (kWh, net CV)", min_value=0.0, max_value=20000.0, value=None, step=100.0, placeholder="Use the bill's energy conversion", key="bill_png") if home["cooking_fuel"] == "png" else None
            if home["cooking_fuel"] == "lpg":
                st.caption("Use kilograms consumed. Refill purchases approximate consumption only if stored cylinder stock is unchanged. Do not enter a cylinder count here.")
            elif home["cooking_fuel"] == "png":
                st.caption("If your PNG bill lists volume only, convert it using your supplier's net calorific value; a universal volume conversion is not assumed.")
        bill_input = annual_bill_baseline(grid_kwh=grid, cooking_fuel=home["cooking_fuel"], lpg_kg=lpg_kg, png_kwh=png_kwh, months=months, fictional=fictional)
        bills = bill_input["energy"]
        st.caption("Single cooking fuel pilot. LPG and PNG used together require a separate model. Turn off annual totals to explore the unvalidated model demonstration.")
    with st.expander("Fabric & appliances", expanded=False):
        home["insulation"] = choose("Roof / envelope insulation", "insulation", "poor")
        home["glazing"] = choose("Windows", "glazing", "single")
        home["led_fraction"] = st.slider("Share of lights that are LEDs", 0, 100, 50, 10, key="led_percent") / 100
        home["hot_water"] = choose("Water heating", "hot_water", "electric_geyser")
        home["solar_kw"] = st.slider("Existing rooftop solar (kW)", 0.0, 8.0, 0.0, 0.5, key="solar_kw")
        home["smart_controls"] = st.checkbox("Smart timers / energy controls installed", key="smart_controls")
    with st.expander("Detailed energy inputs", expanded=False):
        detailed = st.checkbox("Enter known building and appliance details", key="detailed_inputs")
        if detailed:
            defaults = complete_home(home)
            if home["cooling"] != "fans_only":
                home["ac_capacity_ton"] = st.number_input("Capacity per AC (ton)", .75, 2.5, float(defaults["ac_capacity_ton"]), .25, key="ac_capacity_ton")
                home["ac_iseer"] = st.number_input("AC label ISEER", 2.5, 6.5, float(defaults["ac_iseer"]), .1, key="ac_iseer")
                home["setpoint_c"] = st.slider("AC set temperature (°C)", 22.0, 30.0, 26.0, .5, key="setpoint_c")
            home["roof_u_value"] = st.number_input("Roof U-value (W/m²K)", .2, 4.0, float(defaults["roof_u_value"]), .1, key="roof_u_value")
            home["roof_exposed_fraction"] = st.slider("Share of home directly under exposed roof", 0.0, 1.0, float(defaults["roof_exposed_fraction"]), .05, key="roof_exposed_fraction")
            home["wall_u_value"] = st.number_input("Wall U-value (W/m²K)", .3, 3.5, float(defaults["wall_u_value"]), .1, key="wall_u_value")
            home["window_to_wall_ratio"] = st.slider("Window share of exposed wall area", .1, .5, .2, .05, key="window_to_wall_ratio")
            home["window_shgc"] = st.slider("Window solar heat gain coefficient", .2, .9, float(defaults["window_shgc"]), .05, key="window_shgc")
            home["window_shading_fraction"] = st.slider("Window shading fraction", 0.0, .9, .25, .05, key="window_shading_fraction")
            home["fan_count"] = st.number_input("Number of fans", 0, 10, int(defaults["fan_count"]), key="fan_count")
            home["fan_power_w"] = st.number_input("Power per fan (W)", 20.0, 90.0, 55.0, 5.0, key="fan_power_w")
            home["fan_hours_per_day"] = st.slider("Fan hours per day", 0.0, 24.0, float(defaults["fan_hours_per_day"]), .5, key="fan_hours_per_day")
            home["lighting_hours_per_day"] = st.slider("Lighting hours per day", 1.0, 12.0, 5.0, .5, key="lighting_hours_per_day")
            home["hot_water_litres_per_person_day"] = st.number_input("Heated water (litres/person/day)", 0.0, 50.0, 20.0, 5.0, key="hot_water_litres_per_person_day")
            home["appliance_kwh_per_day"] = st.number_input("Other appliances (kWh/day)", .5, 12.0, float(defaults["appliance_kwh_per_day"]), .1, key="appliance_kwh_per_day")
        st.caption("Unknown details use disclosed assumptions. ISEER is a seasonal rating; the cooling calculation is an approximation.")
    with st.expander("Installation constraints", expanded=False):
        demo_constraints = not use_bills or bill_input["provenance"]["source"] == "fictional_sample"
        constraint_prefix = "demo_" if demo_constraints else ""
        if demo_constraints:
            st.caption("Fictional site assumptions: permissions, equipment space and preliminary solar checks are assumed suitable. Change them to explore restrictions.")
        else:
            st.caption("Confirm only details you know. Unconfirmed permissions and site checks block the affected recommendations; they are not inferred from bills.")
        home["roof_access"] = st.checkbox("Roof use permission confirmed", value=demo_constraints, key=constraint_prefix + "roof_access")
        home["external_space"] = st.checkbox("Equipment space confirmed", value=demo_constraints, key=constraint_prefix + "external_space")
        home["electric_connection"] = st.checkbox("Suitable induction circuit confirmed", value=demo_constraints, key=constraint_prefix + "electric_connection")
        home["retrofit_consent"] = st.checkbox("Owner / society retrofit consent confirmed", value=demo_constraints, key=constraint_prefix + "retrofit_consent")
        heritage = st.selectbox("Heritage / facade restrictions", ["Unknown", "None confirmed", "Restrictions present"], index=1 if demo_constraints else 0, key=constraint_prefix + "heritage_status")
        home["heritage_restricted"] = {"Unknown": None, "None confirmed": False, "Restrictions present": True}[heritage]
        home["require_site_checks"] = True
        home["usable_roof_area_m2"] = st.number_input("Usable shadow-free roof area (m²)", min_value=0.0, max_value=1000.0, value=50.0 if demo_constraints else None, step=5.0, key=constraint_prefix + "usable_roof_area_m2")
        home["solar_shading_ok"] = st.checkbox("Solar shading assessment acceptable", value=demo_constraints, key=constraint_prefix + "solar_shading_ok")
        home["solar_structure_ok"] = st.checkbox("Roof structural suitability confirmed", value=demo_constraints, key=constraint_prefix + "solar_structure_ok")
        home["solar_electrical_ok"] = st.checkbox("Solar electrical / connection suitability confirmed", value=demo_constraints, key=constraint_prefix + "solar_electrical_ok")
        home["site_checks_provenance"] = "fictional_demo_assumptions" if demo_constraints else "user_declarations_not_independently_verified"
        st.caption("The illustrative 3 kW PV option uses a preliminary 30 m² roof screen. Final panel layout, structure, electrical design and permissions require an installation assessment.")
        st.markdown("[Government rooftop solar area guidance](https://api.solarrooftop.gov.in/pdf/faq_new.pdf)")
    with st.expander("Tariffs & carbon assumptions", expanded=False):
        tariff = st.number_input("Your effective electricity rate (₹/kWh)", 0.0, 30.0, 8.0, 0.5, key="tariff")
        lpg_price = st.number_input("Your LPG price (₹/kg)", 0.0, 200.0, 65.0, 1.0, key="lpg_price")
        png_price = st.number_input("Your PNG effective rate (₹/kWh net CV)", 0.0, 20.0, 5.0, .5, key="png_price")
        st.caption("Illustrative default prices. Enter your own bill rates; fixed charges, slabs and subsidies are excluded.")
        ef_grid = st.number_input("Grid CO₂ (kg/kWh)", 0.0, 2.0, float(DEFAULT_FACTORS["electricity_kg_co2_per_kwh"]), 0.01, format="%.3f", key="ef_grid")
        ef_lpg = st.number_input("LPG CO₂ (kg/kWh net CV)", 0.0, 1.0, float(DEFAULT_FACTORS["lpg_kg_co2_per_kwh"]), 0.01, format="%.5f", key="ef_lpg")
        ef_png = st.number_input("PNG CO₂ (kg/kWh net CV)", 0.0, 1.0, float(DEFAULT_FACTORS["png_kg_co2_per_kwh"]), 0.01, format="%.5f", key="ef_png")
        st.caption("Dated CEA national average proxy and IPCC LPG combustion factor. Sources in Assumptions.")

st.caption("INDIAN HOUSEHOLDS / HACKATHON PROTOTYPE")
st.title("Green Home Score")
st.write("Compare cooling, lighting, hot water, cooking and solar choices for an Indian home.")
st.info("Hyderabad pilot: engineering baseline and ML candidates evaluated on synthetic homes, with cached NASA weather and PVGIS solar references. Real-home checking is limited. Savings remain modeled estimates; this score is not a BEE certification.", icon="ℹ️")

if use_bills and bills is None:
    st.subheader("Start with a complete year of consumption")
    st.write("Enter your household's annual electricity and cooking-fuel totals in the sidebar. These totals anchor the comparison; appliance shares and retrofit savings still use assumptions.")
    for error in bill_input["errors"]:
        st.info(error)
    st.caption("For a walkthrough, choose ‘Try fictional sample’ in the sidebar. Its values are explicitly labeled as fictional.")
    st.stop()
metadata_file = ROOT / "models" / "metadata.json"
artifact_version = metadata_file.stat().st_mtime_ns if metadata_file.exists() else 0
if not use_bills:
    try:
        energy_models = models(artifact_version)
        predicted = predict_energy(home, energy_models)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        st.error(f"The model demonstration is unavailable: {exc}. You can still use annual consumption totals.")
        st.stop()
baseline = bills if bills is not None else {key: float(predicted[key]) for key in ("annual_grid_kwh", "annual_gas_kwh", "annual_lpg_kwh", "annual_png_kwh", "annual_electricity_demand_kwh")}
baseline_provenance = bill_input["provenance"] if use_bills else {"source": "model_demonstration", "training_labels": "synthetic", "real_home_accuracy_established": False, "end_use_allocation_measured": False}
baseline_source = ("fictional annual consumption sample" if baseline_provenance["source"] == "fictional_sample" else "your declared 12-month electricity and fuel totals") if use_bills else "selected baseline / ML model evaluated on synthetic profiles"
if use_bills:
    if baseline_provenance["source"] == "fictional_sample":
        st.warning("Fictional sample mode. These totals are demonstration inputs, not records from a real household.")
    else:
        st.success("Comparison anchored to your declared annual consumption totals.")
    st.caption("Matching entered totals is by construction. It does not validate the inferred appliance shares or future retrofit savings. Bill coverage and units are user declarations.")
factors = {key: value for key, value in {"electricity_kg_co2_per_kwh": ef_grid, "lpg_kg_co2_per_kwh": ef_lpg, "png_kg_co2_per_kwh": ef_png}.items() if value != DEFAULT_FACTORS[key]}
if not use_bills:
    selected_name = energy_models["_metadata"]["models"]["annual_electricity_demand_kwh"]["selected"].replace("_", " ")
    st.caption(f"Electricity predictor selected by validation: {selected_name}.")
    if (ROOT / "reports" / "external_audit.json").exists():
        st.warning("The small Hyderabad bill check showed substantial overprediction with default inputs. Use actual annual bills to anchor household retrofit comparisons; default-only predictions are demonstrations.")
    diagnostics = input_diagnostics(home, energy_models)
    if diagnostics["rare_training_features"]:
        st.caption("Inputs near the edge of the synthetic training examples: " + ", ".join(diagnostics["rare_training_features"]) + ".")
overview = st.container()
score_tab, plan_tab, finance_tab, compare_tab, evidence_tab, assumptions_tab = st.tabs(["Your score", "Retrofit planner", "Costs & payback", "Compare homes", "Model evidence", "Assumptions"])

with plan_tab:
    st.subheader("Choose improvements for your goal")
    feasible = feasible_retrofits(home)
    names = {r["id"]: r["name"] for r in feasible}
    objective_labels = {"Lower annual bills": "bill_savings", "Use less purchased energy": "energy_savings", "Reduce operational CO₂": "carbon_savings"}
    goal = st.selectbox("Your priority", list(objective_labels), key="recommendation_goal")
    calculation_version = tuple((ROOT / "greenhome" / name).stat().st_mtime_ns for name in ("engine.py", "retrofit_engine.py", "billing.py"))
    recommendation = decision_plan(home, baseline, objective_labels[goal], {"electricity_rate": tariff, "lpg_price_kg": lpg_price, "png_rate": png_price}, factors, calculation_version)
    unit = recommendation.get("objective_unit") or ""
    if recommendation["status"] == "available":
        if recommendation["selected_ids"]:
            st.write("**Suggested package:** " + " → ".join(names.get(x, x) for x in recommendation["selected_ids"]))
            st.write(f"Estimated benefit for this goal: **{recommendation['package_objective_benefit']:,.0f} {unit}**.")
        else:
            st.info("No screened improvement currently offers a positive modeled benefit for this goal. Review the installation constraints and the reasons below.")
    else:
        for reason in recommendation["reasons"]:
            st.info(reason)
    st.caption("Suggestions are built by recalculating each possible addition to the package. Installation order preserves interactions. Enter costs separately in Costs & payback; the recommendation goal does not optimize investment return.")
    priority_rows = [{"Priority alone": row["rank"], "Improvement": row["name"], f"Saving alone ({unit})": row["objective_benefit"], "In suggested package": row["selected"], "Suitability": row["suitability"]} for row in recommendation["ranked_candidates"]]
    if priority_rows:
        st.dataframe(pd.DataFrame(priority_rows).round(2), hide_index=True, width="stretch")
        candidates_by_name = {row["name"]: row for row in recommendation["ranked_candidates"]}
        with st.expander("Why these priorities and tradeoffs?"):
            candidate_name = st.selectbox("Improvement to review", list(candidates_by_name), key="review_recommendation")
            candidate = candidates_by_name[candidate_name]
            st.write(candidate["feasibility_reason"])
            st.write(candidate["selection_reason"])
            standalone = candidate["standalone_savings"]
            st.write(f"Alone: electricity saved {fmt(standalone.get('electricity_kwh'))} kWh/year; LPG saved {fmt(standalone.get('lpg_kwh'))} kWh/year; PNG saved {fmt(standalone.get('png_kwh'))} kWh/year; CO₂ saved {fmt(standalone.get('carbon_kg'))} kg/year; bill saving ₹{fmt(candidate['standalone_bill_trace'].get('total_inr_per_year'))}/year.")
            if candidate["selected"]:
                st.caption(f"Benefit of adding it when chosen: {fmt(candidate['decision_incremental_benefit'])} {unit}. Its final installation-order marginal: {fmt(candidate['package_marginal_objective_benefit'])} {unit}. These compare different package states; a measure can help the full package while having a negative standalone result.")
            st.caption("Negative savings mean increased consumption, emissions or spending. Zero modeled energy saving does not establish that an improvement has no comfort benefit.")
    with st.expander("Blocked improvements and decision record"):
        if recommendation["rejected"]:
            for blocked in recommendation["rejected"]:
                st.write(f"**{blocked['id'].replace('_', ' ').title()}:** {blocked['reason']}")
        else:
            st.caption("No candidate is blocked by the declared constraints.")
        st.json({"objective": recommendation["objective"], "method": recommendation["method"], "decision_audit": recommendation["decision_audit"], "limitations": recommendation["limitations"]}, expanded=False)
    if st.button("Use suggested package", key="use_suggested", disabled=recommendation["status"] != "available" or not recommendation["selected_ids"]):
        st.session_state["selected_retrofits"] = recommendation["selected_ids"]
        st.session_state["preset"] = "Choose improvements"
        st.session_state["last_preset"] = "Choose improvements"
    st.subheader("Explore your what-if package")
    presets = {"Choose improvements": [], "Cooling & lighting": [x for x in ("insulation", "glazing", "led_lighting", "efficient_ac", "smart_controls") if x in names], "Rooftop solar": ["solar"] if "solar" in names else [], "Switch cooking to induction": ["induction"] if "induction" in names else [], "All feasible improvements": list(names)}
    preset = st.selectbox("What-if scenario", list(presets), key="preset")
    # A preset change resets the selection; manual edits persist within that preset.
    if st.session_state.get("last_preset") != preset:
        st.session_state["selected_retrofits"] = presets[preset]
        st.session_state["last_preset"] = preset
    st.session_state["selected_retrofits"] = [x for x in st.session_state.get("selected_retrofits", []) if x in names]
    selected = st.multiselect("Selected improvements", list(names), format_func=lambda x: names[x], key="selected_retrofits")
    result = evaluate_scenario(home, baseline, selected, factors=factors)
    result.get("calculation_trace", {}).get("anchor", {}).update({"source": baseline_source, "provenance": baseline_provenance})
    savings = result.get("savings") or {}
    bill_trace = bill_savings_trace(savings, electricity_rate=tariff, lpg_price_kg=lpg_price, png_rate=png_price)
    bill_saving = bill_trace["total_inr_per_year"]
    scenario_flags = result.get("flags", [])
    if scenario_flags:
        if (result.get("after") or {}).get("annual_grid_kwh") is None:
            for flag in scenario_flags:
                st.warning(flag)
        else:
            with st.expander("Calculation notes"):
                for flag in scenario_flags:
                    st.caption(flag)
    for rejected in result.get("rejected", []):
        st.warning(f"{rejected['id']}: {rejected['reason']}")
    rows = []
    for rec in result.get("recommendations", []):
        standalone = rec.get("standalone_savings") or {}
        incremental = rec.get("sequential_savings") or {}
        rows.append({"Improvement": rec["name"], "Suitability": rec["suitability"], "In package": rec.get("selected", False), "Electricity saved alone (kWh/yr)": standalone.get("electricity_kwh"), "Cooking fuel saved alone (kWh/yr)": standalone.get("gas_kwh"), "Incremental package saving (kWh/yr)": incremental.get("total_kwh") if rec.get("selected") else None, "Why": rec["reason"]})
    if rows:
        st.dataframe(pd.DataFrame(rows).round(0), hide_index=True, width="stretch")
    else:
        st.info("No feasible improvements remain under the current property details and permissions.")
    st.caption("Savings shown alone use the same baseline. Selected package savings account for sequence and interactions. Negative savings mean higher fuel consumption.")
    if result.get("applied"):
        st.write("**Installation sequence:** " + " → ".join(names.get(x, x) for x in result["applied"]))
    with st.expander("Inspect the savings calculations", expanded=False):
        trace = result.get("calculation_trace", {})
        anchor = trace.get("anchor", {})
        if trace.get("status") == "available":
            st.write("**Baseline allocation**")
            st.caption(f"Electricity demand used: {anchor['anchored_gross_kwh']:,.2f} kWh/year. Scale applied to the engineering estimate: {anchor['electricity_scale_factor']:.4f}. Each electricity use below is inferred, not separately metered.")
            st.dataframe(pd.DataFrame([{"Electricity use": key.title(), "Engineering estimate (kWh/year)": value, "Anchored allocation (kWh/year)": anchor["anchored_end_uses_kwh"][key]} for key, value in anchor["nominal_end_uses_kwh"].items()]).round(2), hide_index=True, width="stretch")
            if home["solar_kw"] > 0:
                st.caption("With existing solar, grid imports alone do not measure gross electricity demand. The annual solar matching assumptions infer that demand; zero-import solar households cannot be represented by the current matching rule.")
            comparisons = {}
            for rec in result.get("recommendations", []):
                comparisons[f"{rec['name']} · alone against baseline"] = rec["standalone_trace"]
                if rec.get("selected"):
                    comparisons[f"{rec['name']} · next step in your package"] = rec["selected_marginal_trace"]
                comparisons[f"{rec['name']} · next step in all-feasible reference package"] = rec["recommended_marginal_trace"]
            if comparisons:
                calculation = st.selectbox("Calculation to inspect", list(comparisons), key="trace_calculation")
                show_step_trace(comparisons[calculation])
            st.write("**Selected package bill calculation**")
            if bill_trace["status"] == "available":
                st.dataframe(pd.DataFrame(bill_trace["terms"]).round(2), hide_index=True, width="stretch")
                st.write(f"Sum of signed fuel savings × entered rates = ₹{bill_saving:,.2f}/year. Fixed charges, slabs, subsidies and installation costs are excluded.")
            st.caption("Package savings compare the original baseline with the final state. All intermediate steps, factors, PV balances and equations are included in the scenario download. No validated uncertainty interval for retrofit savings is available.")
            st.json(trace, expanded=False)
        else:
            st.info("Correct the invalid or conflicting inputs before inspecting a numerical calculation.")
    energy_after = result.get("after") or {}
    st.bar_chart(pd.DataFrame({"Current": {"Grid electricity": baseline["annual_grid_kwh"], "LPG energy": baseline.get("annual_lpg_kwh", 0), "PNG energy": baseline.get("annual_png_kwh", 0)}, "Selected package": {"Grid electricity": energy_after.get("annual_grid_kwh"), "LPG energy": energy_after.get("annual_lpg_kwh", 0), "PNG energy": energy_after.get("annual_png_kwh", 0)}}), stack=False, y_label="kWh per year", color=["#8b9c84", "#246344"])
with overview:
    before_score = (result.get("baseline_score") or {}).get("score")
    after_score = (result.get("after_score") or {}).get("score")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Green Home Score", fmt(before_score, " / 100"), delta=f"{after_score - before_score:+.1f} with package" if before_score is not None and after_score is not None else None)
    c2.metric("Energy saved (kWh/year)", fmt(savings.get("total_kwh")), delta=f"{savings['percent']:.1f}%" if savings.get("percent") is not None else "No valid baseline")
    c3.metric("CO₂ saved (kg/year)", fmt(savings.get("carbon_kg")))
    c4.metric("Indicative bill saving / year", "Unavailable" if bill_saving is None else f"₹{bill_saving:,.0f}")
    st.caption(f"Baseline: {baseline_source}. Energy and bill savings are estimates. Flat tariffs are user assumptions.")

with score_tab:
    st.subheader("How your score is calculated")
    current_score = result["baseline_score"]
    st.write(f"**Classification:** {current_score['classification']}")
    for flag in current_score.get("flags", []):
        st.warning(flag)
    components = [{"Component": row["name"], "Weight": f"{row['weight']:.0%}", "Sub-score / 100": row["subscore"], "Weighted points": row["contribution"]} for row in current_score["components"]]
    st.dataframe(pd.DataFrame(components).round(1), hide_index=True, width="stretch")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Annual grid import", fmt(baseline.get("annual_grid_kwh"), " kWh"))
    e2.metric("Annual LPG", fmt(baseline.get("annual_lpg_kwh", 0) / LPG_KWH_PER_KG, " kg"))
    e3.metric("Electricity demand intensity", fmt(current_score.get("energy_intensity_kwh_m2"), " kWh/m²"))
    e4.metric("Annual PNG", fmt(baseline.get("annual_png_kwh", 0), " kWh"))
    if use_bills and home["solar_kw"] > 0:
        st.caption("Your bill measures grid imports. Total electricity demand and its intensity are inferred using the declared annual solar self-consumption assumptions.")
    if not use_bills:
        intervals = prediction_intervals(home, predicted, energy_models)
        lo, hi = intervals["annual_grid_kwh"]
        st.caption(f"90% target electricity interval from separate synthetic calibration groups: {lo:,.0f}–{hi:,.0f} kWh/year. Coverage on real homes and retrofit savings is unverified.")
        pv = climate_parameters(home)
        st.caption(f"Electricity demand before solar: {predicted['annual_electricity_demand_kwh']:,.0f} kWh/year · solar generation: {predicted['annual_solar_generation_kwh']:,.0f} kWh/year · exports: {predicted['annual_solar_export_kwh']:,.0f} kWh/year. PV reference yield: {pv['pv_yield_kwh_per_kw_year']:,.0f} kWh/kWp/year.")
    with st.expander("Values assumed for missing details"):
        st.json(input_assumptions(home), expanded=False)
    st.caption("The seven weights follow the challenge brief. Appliance efficiency and cooling / hot water replace UK-specific rating and heating inputs. This is an explicitly adapted India prototype score.")
    st.subheader("Property-value impact — deferred")
    st.info(PROPERTY_VALUE_DEFERRAL)
    st.caption("Open Costs & payback for installation economics. Resale-value uplift remains outside this prototype's implemented scope.")

with finance_tab:
    financial_scenario = render_financial_scenario(result, bill_trace, baseline_source=baseline_source)

with plan_tab:
    st.subheader("Explanation from calculated facts")
    explanation_result = {**result, "financial_scenario": financial_scenario}
    offline = explain(explanation_result, baseline_source)
    for paragraph in offline["paragraphs"]:
        st.write(paragraph)
    with st.expander("Optional AI explanation", expanded=False):
        st.caption("Uses official OpenAI Responses API. Only computed facts and your question are sent. No address or account details are needed. The AI selects facts; the app renders their verified wording.")
        st.caption("Choose the what-if package and optional Costs & payback inputs first. Calculations rerun before explanation. This question explains the selected scenario; it does not edit property or retrofit inputs.")
        question = st.text_input("Question about the calculated scenario", "Why do electricity and LPG change differently?", key="ai_question")
        api_key = st.text_input("OpenAI API key (optional)", type="password", key="api_key") or os.getenv("OPENAI_API_KEY", "")
        model = st.text_input("API model", value=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), key="ai_model")
        if st.button("Explain this scenario with AI", disabled=not bool(api_key), key="explain_ai"):
            with st.spinner("Selecting supported facts…"):
                answer = explain(explanation_result, baseline_source, api_key=api_key, question=question, model=model)
            if answer["error"]:
                st.warning(answer["error"])
            st.caption(answer["mode"])
            for paragraph in answer["paragraphs"]:
                st.write(paragraph)

with compare_tab:
    st.subheader("Rank demo homes by improvement potential")
    st.caption("Synthetic profiles ranked by feasible reduction in purchased energy. These are demo cases, not addresses or customers.")
    path = ROOT / "data" / "synthetic_homes.csv"
    if path.exists():
        @st.cache_data
        def demo_ranking(factor_grid, factor_lpg, factor_png, version):
            data = pd.read_csv(path).head(24)
            ranking = []
            for _, row in data.iterrows():
                demo = dict(DEFAULT_HOME)
                demo.update({key: row[key] for key in FEATURES})
                demo["solar_kw"] = float(row.get("solar_kw", 0))
                # Synthetic roof eligibility is explicit and not inferred from a real address.
                demo["roof_access"] = demo["property_type"] != "apartment"
                demo.update({"require_site_checks": True, "usable_roof_area_m2": min(50.0, float(demo["area_m2"])), "solar_shading_ok": True, "solar_structure_ok": True, "solar_electrical_ok": True, "site_checks_provenance": "fictional_demo_assumptions"})
                demo_energy = {key: float(row[key]) for key in ("annual_grid_kwh", "annual_gas_kwh", "annual_lpg_kwh", "annual_png_kwh")}
                package = [x["id"] for x in feasible_retrofits(demo)]
                scenario = evaluate_scenario(demo, demo_energy, package, factors={"electricity_kg_co2_per_kwh": factor_grid, "lpg_kg_co2_per_kwh": factor_lpg, "png_kg_co2_per_kwh": factor_png})
                ds = scenario.get("savings") or {}
                ranking.append({"Demo home": row.get("home_id", str(row.name)), "City": demo["city"], "Home type": LABELS[demo["property_type"]], "Score": scenario["baseline_score"]["score"], "Potential (%)": ds.get("percent"), "Electricity saving (kWh/yr)": ds.get("electricity_kwh"), "Cooking fuel saving (kWh/yr)": ds.get("gas_kwh"), "CO₂ reduction (kg/yr)": ds.get("carbon_kg")})
            return pd.DataFrame(ranking).sort_values("Potential (%)", ascending=False, na_position="last")
        st.dataframe(demo_ranking(ef_grid, ef_lpg, ef_png, artifact_version).round(1), hide_index=True, width="stretch")
    else:
        st.info("Run python generate_data.py to create the demo dataset.")

with evidence_tab:
    st.subheader("Training & held-out evidence")
    st.write("Three targets: household electricity demand before solar, LPG, and PNG. Mean and engineering baselines compete with tree ensembles and a residual model. Building groups stay separate across training, validation, calibration, and final testing.")
    metrics = report(artifact_version)
    metric_rows = []
    for target, info in metrics.get("models", {}).items():
        for candidate, details in info.get("candidates", {}).items():
            val = details.get("validation", {})
            metric_rows.append({"Target": {"annual_electricity_demand_kwh": "Electricity demand", "annual_lpg_kwh": "LPG", "annual_png_kwh": "PNG"}.get(target, target), "Candidate": candidate.replace("_", " ").title(), "Selected": candidate == info.get("selected"), "Validation MAE (kWh/yr)": val.get("mae_kwh"), "Validation R²": val.get("r2"), "Test MAE (selected or baseline)": (info.get("test", {}) if candidate == info.get("selected") else details.get("test", {})).get("mae_kwh")})
    if metric_rows:
        st.dataframe(pd.DataFrame(metric_rows).round(3), hide_index=True, width="stretch")
    st.caption("Group-disjoint 50% training / 15% validation / 15% calibration / 20% test. Calibration uses one label-independent representative per building group. Exact counts and seed below.")
    with st.expander("Full metrics & model metadata"):
        st.json(metrics, expanded=False)
    st.warning("These metrics measure how well the model reproduces the synthetic generator. They do not establish predictive accuracy on Indian households or causal retrofit savings.")
    audit_file = ROOT / "reports" / "external_audit.json"
    if audit_file.exists():
        external = json.loads(audit_file.read_text(encoding="utf-8"))
        st.subheader("Small external Hyderabad sanity check")
        st.write(external["summary"])
        st.caption("No external labels used for training, selection, calibration, or tuning. Missing inputs and different weather/bill periods limit this check.")
        st.json(external, expanded=False)
    for filename, label in [("metrics.json", "Download training metrics"), ("held_out_predictions.csv", "Download held-out predictions"), ("external_audit.json", "Download external audit")]:
        file = ROOT / "reports" / filename
        if file.exists():
            st.download_button(label, file.read_bytes(), file_name=filename, mime="application/json" if filename.endswith("json") else "text/csv", key=filename)

with assumptions_tab:
    st.subheader("Assumptions you can inspect")
    st.write("Every numerical output comes from the energy models or explicit calculations. The optional LLM only orders supported facts after the scenario has been recalculated.")
    st.write("**Scope:** Hyderabad residential pilot; seven other city configurations are exploratory. NASA POWER 2024 hourly grid weather drives approximate heat loads. PVGIS ERA5 2005–2023 supplies modeled solar yield for a 20° south-facing system with 14% system loss. Household behavior, engineering defaults, retrofit effects and annual solar matching remain assumptions.")
    st.write("**Carbon:** operational CO₂ only. The grid default is a dated CEA national proxy for FY2022–23, not a current local DISCOM or marginal factor. LPG and PNG use separate IPCC net-calorific combustion factors. No embodied emissions, upstream fuel supply or solar export credit.")
    st.json(result.get("factors", DEFAULT_FACTORS), expanded=False)
    st.markdown("[BEE Eco-Niwas Samhita 2024](https://beeindia.gov.in/WriteReadData/RTF1984/1772175926.pdf) · [NASA POWER hourly data](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/) · [JRC PVGIS API](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en) · [CEA CO₂ database v19](https://cea.nic.in/wp-content/uploads/baseline/2024/01/User_Guide__Version_19.0.pdf) · [IPCC combustion factors](https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_2_Ch2_Stationary_Combustion.pdf)")
    st.write("**Missing or conflicting data:** the calculation layer withholds unsupported scores and scenarios. A bill inconsistent with the stated cooking fuel needs correction. Rooftop and society permissions determine which measures appear.")
    st.write("**Next evidence needed:** consented meter / bill data, local weather, actual AC performance, roof area and shading, contractor feasibility, measured retrofit outcomes, and local comparable sales for value impact.")
    methodology = ROOT / "docs" / "methodology.md"
    if methodology.exists():
        st.download_button("Download methodology", methodology.read_bytes(), "methodology.md", "text/markdown", key="download_method")

st.divider()
recommendation["scenario"].get("calculation_trace", {}).get("anchor", {}).update({"source": baseline_source, "provenance": baseline_provenance})
export = {"home": home, "assumed_inputs": input_assumptions(home), "baseline_source": baseline_source, "baseline_provenance": baseline_provenance, "recommendation_plan": recommendation, "scenario": result, "financial_scenario": financial_scenario, "bill_saving_inr_per_year": bill_saving, "bill_calculation": bill_trace, "tariff_assumptions": {"electricity_inr_per_kwh": tariff, "lpg_inr_per_kg": lpg_price, "png_inr_per_kwh": png_price}, "data_status": "synthetic_training_sourced_weather_and_solar_limited_external_check"}
export["property_value_scope"] = dict(PROPERTY_VALUE_SCOPE)
st.download_button("Download this scenario", json.dumps(export, indent=2, default=str), "green_home_india_scenario.json", "application/json", key="download_scenario")
st.caption("Hackathon prototype · No real customer records · Estimates require local validation")
