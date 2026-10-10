"""Transparent India household score and indicative retrofit calculations.

The briefing's fixed weights (25/20/15/15/10/10/5) are retained. Its
EPC and space-heating components are explicitly adapted to appliance
efficiency and cooling/hot-water systems; this is neither EPC nor a BEE rating.
Scores and scenarios use documented rules, not synthetic ML target labels.

`annual_gas_kwh` is a compatibility aggregate of separately accounted LPG and
piped natural gas (PNG), both net calorific value energy. Carbon output is kg CO2,
not CO2e. CEA's dated generation-based national factor is a proxy for imported
electricity; transmission/distribution, lifecycle, other GHG and embodied
emissions are outside this prototype's boundary.

End uses are inferred, not metered. Baseline grid imports are apportioned with
the synthetic generator's nominal end-use equations. Existing PV self-use is
estimated first, then added back to imports; every scenario recomputes gross
demand, PV self-use and non-negative imports. PV exports receive no credit.
Packages are rerun in fabric -> appliance -> controls -> hot water -> cooking
-> PV order. Standalone savings must not be added. Sequential recommendation
savings are marginal steps in the selected package (unselected entries have
unavailable sequential savings). The complete feasible reference package uses
the separate recommended_sequential_savings and recommended_package fields.

Retrofit targets and end-use allocation remain illustrative engineering
assumptions with fixed occupancy, use and weather. Constant comfort is assumed
where modeled AC capacity suffices; unmet-load flags expose its limitation.
Savings are not causal
effects learned by the Random Forest, calibrated savings or guarantees.
Property value is unavailable: there is no local sales data/model supporting
an association or a causal effect. No retrofit invents an energy certificate.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math

from .schema import CATEGORICAL_FEATURES, OPTIONS
from .physics import (complete_home, expected_end_uses, electricity_balance,
                      demand_from_grid, validate_home, input_assumptions,
                      climate_parameters)

LPG_KWH_PER_KG = 47.3 / 3.6
DEFAULT_FACTORS = {
    "electricity_kg_co2_per_kwh": 0.716,
    "lpg_kg_co2_per_kwh": 63100 * 3.6e-6,
    "png_kg_co2_per_kwh": 56100 * 3.6e-6,
    "source_year": "CEA FY 2022-23; IPCC 2006",
    "basis": "Operational CO2 only; generation national proxy; LPG and PNG net CV; excludes T&D, WTT and embodied emissions",
    "electricity_source": "https://cea.nic.in/wp-content/uploads/baseline/2024/01/User_Guide__Version_19.0.pdf",
    "electricity_source_detail": "CEA CO2 Baseline Database v19, Annexure I: 0.716 tCO2/MWh, including renewables/captive; dated proxy, not latest",
    "lpg_source": "https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_2_Ch2_Stationary_Combustion.pdf",
    "lpg_source_detail": "IPCC 2006 Vol 2 Ch 2 Table 2.5: 63,100 kg CO2/TJ (net CV), multiplied by 0.0000036 TJ/kWh",
    "lpg_ncv_source": "https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_1_Ch1_Introduction.pdf",
    "lpg_ncv_source_detail": "IPCC 2006 Vol 2 Ch 1 Table 1.2: 47.3 TJ/Gg = 47.3 MJ/kg; 1 kWh = 3.6 MJ",
    "png_source": "https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_2_Ch2_Stationary_Combustion.pdf",
    "png_source_detail": "IPCC 2006 Vol 2 Ch 2 Table 2.5: natural gas 56,100 kg CO2/TJ, net CV, multiplied by 0.0000036 TJ/kWh; delivered PNG composition can differ",
}

ASSUMPTIONS = {
    "scope": "India homes; illustrative prototype, constant comfort and use; annual purchased energy = grid electricity imports + LPG + PNG net-CV kWh",
    "score_weights": {"Appliance efficiency": 0.25, "Electricity demand intensity": 0.20,
                      "Insulation": 0.15, "Cooling and hot water": 0.15,
                      "Windows and glazing": 0.10, "Renewable energy": 0.10,
                      "Smart energy management": 0.05},
    "cooling_subscore": "Fans-only100; AC clip(100*(actual ISEER-2.5)/4,0,100). This is an illustrative scoring range, not BEE star bands.",
    "appliance_subscore": "0.6 * cooling subscore + 0.4 * (100 * LED fraction)",
    "intensity_subscore": "clip(100*(225-gross electricity demand kWh/m2)/200,0,100); <=25 best, >=225 worst; illustrative uncalibrated bounds, not climate/BEE benchmark. Gross demand before PV avoids double crediting solar. Zero/missing baseline unavailable.",
    "insulation_subscore": "Roof clip(100*(3-Uroof)/2.4,0,100), walls clip(100*(2.2-Uwall)/1.4,0,100); roof weight=.6*exposed roof fraction, wall weight=1-roof weight. Illustrative engineering mappings.",
    "hot_water_subscore": {"electric_geyser": 35, "solar_heater": 95, "heat_pump": 85, "none": 100},
    "systems_subscore": "0.6 * cooling subscore + 0.4 * hot-water subscore",
    "glazing_subscore": ".35*clip(100*(5.7-Uwindow)/2.9)+.50*clip(100*(.75-SHGC)/.35)+.15*clip(100*shading/.75), each clip0..100. WindowU single5.7/double2.8. Illustrative mapping, no BEE rating.",
    "renewable_subscore": "max(min(solar_kw/3,1)*100, 60 if solar hot water else 0)",
    "smart_subscore": {"False": 0, "True": 100},
    "classification": "80-100 Highly efficient; 65-<80 Good; 50-<65 Moderate; 30-<50 Poor; <30 Very poor",
    "solar_new_capacity_kw": 3.0,
    "solar_roof_area_screen_m2": 30.0,
    "solar_roof_area_screen_source": "https://api.solarrooftop.gov.in/pdf/faq_new.pdf section 1.3: approximately 10 m2 shadow-free roof area per kW; actual module efficiency and layout vary",
    "solar_site_screen": "When require_site_checks=True, new 3 kW PV requires at least 30 m2 declared usable roof area plus affirmative shading, structural and electrical suitability declarations. This is a preliminary screen, not installation certification. Legacy callers without the screen retain conditional survey assumptions.",
    "solar_yield_kwh_per_kw": "Location-specific sourced PVGIS 5.3 ERA5 cache, 20-degree south-facing 1kWp, 14% user loss; multi-year 2005-2023",
    "solar_self_consumption_fraction": 0.65,
    "solar_gross_demand_cap": 0.75,
    "solar_import_rule": "physics.electricity_balance: self-used PV=min(0.75*gross demand,capacity*location yield*explicit self-consumption fraction); grid imports=gross-self-used; export not credited",
    "fabric_order": "Insulation and glazing reduce cooling load before efficient AC; fractions multiply, not add",
    "insulation_targets": "Roof U reduced to min(current,0.6) W/m2K; roof-only action leaves wall U unchanged. No roof cooling saving when exposed roof fraction is zero.",
    "glazing_targets": "Double glazing U=2.8 W/m2K in shared physics; SHGC=min(current,0.4), existing shading retained",
    "efficient_ac_target": "ISEER=max(current,5.2); capacity, setpoint and hours held constant; rating used as seasonal efficiency approximation, not hourly measured COP",
    "led_power_ratio": 0.30,
    "smart_cooling_ratio": 0.92,
    "solar_water_backup_ratio": 0.30,
    "lpg_stove_efficiency": 0.55,
    "png_stove_efficiency": 0.50,
    "induction_efficiency": 0.84,
    "induction_rule": "Electric cooking = anchored LPG*0.55/0.84 or PNG*0.50/0.84; electricity may rise and CO2 may rise. Efficiencies are explicit illustrative assumptions.",
    "end_use_allocation": "Shared physics.expected_end_uses supplies nominal end uses; scale these to baseline gross demand. Each action edits physical fields then applies new/old nominal end-use ratios, preserving paired interaction state. Fuel-switch service is anchored separately to the entered cooking fuel.",
    "existing_pv_gross_reconstruction": "Use supplied gross demand only if consistent with the same PV balance and meter imports; otherwise flag conflict. With meter-only inputs use physics.demand_from_grid to invert exactly the same balance. Behind-meter demand allocation remains assumed.",
    "value_impact": "Unavailable: no local transaction dataset or validated value model; no uplift invented from score changes",
    "unknowns": "Missing constraints block affected retrofits. Missing basic household fields and invalid/conflicting data make scenarios unavailable. Missing advanced engineering inputs use disclosed physics defaults. Space heating is outside scope, including cold-season demand in Delhi and other non-Hyderabad cities.",
    "climate_and_comfort": "NASA POWER 2024 UTC hourly temperature and irradiance are gridded references, not household measurements or climate normals. CDH*entered AC hours/24 approximates schedules. Humidity/latent cooling, space heating, wall solar gain and detailed dynamic thermal storage are omitted. Capacity limits can leave unmet thermal cooling load; in these cases constant comfort is not established and fabric upgrades may improve comfort without equal metered savings. Hyderabad is primary; other cities exploratory.",
}

RETROFITS = [
    {"id": "insulation", "name": "Roof insulation", "stage": 1},
    {"id": "glazing", "name": "Double glazing", "stage": 2},
    {"id": "led_lighting", "name": "Complete LED lighting", "stage": 3},
    {"id": "efficient_ac", "name": "Efficient inverter AC", "stage": 4},
    {"id": "smart_controls", "name": "Smart timers and controls", "stage": 5},
    {"id": "solar_water_heater", "name": "Solar water heating", "stage": 6},
    {"id": "induction", "name": "Induction cooking", "stage": 7},
    {"id": "solar", "name": "Rooftop solar PV (3 kW)", "stage": 8},
]


def _number(value, *, minimum=0.0, maximum=None):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        return None
    return number


def _bool(value):
    return value if isinstance(value, bool) else None


def _mapped(mapping, value):
    return mapping.get(value) if isinstance(value, str) else None


def _clip_score(value):
    return min(100.0, max(0.0, value))


CORE_ENERGY_KEYS = ("annual_grid_kwh", "annual_lpg_kwh", "annual_png_kwh")
ENERGY_KEYS = (*CORE_ENERGY_KEYS, "annual_gas_kwh", "annual_electricity_demand_kwh",
               "annual_solar_generation_kwh", "annual_solar_self_consumed_kwh", "annual_solar_export_kwh")
SAVINGS_KEYS = ("electricity_kwh", "lpg_kwh", "png_kwh", "gas_kwh", "total_kwh", "percent", "carbon_kg")


def _energy(energy, home):
    """Normalize legacy cooking-gas aggregate without double counting fuel labels."""
    energy = energy if isinstance(energy, Mapping) else {}
    values = {key: _number(energy.get(key)) for key in CORE_ENERGY_KEYS}
    flags = []
    fuel = home.get("cooking_fuel")
    explicit = "annual_lpg_kwh" in energy or "annual_png_kwh" in energy
    legacy = _number(energy.get("annual_gas_kwh"))
    if not explicit:
        values["annual_lpg_kwh"] = legacy if fuel != "png" else 0.0
        values["annual_png_kwh"] = legacy if fuel == "png" else 0.0
    else:
        # An omitted inactive fuel may safely be zero; an active label stays unknown.
        for selected_fuel in ("lpg", "png"):
            key = f"annual_{selected_fuel}_kwh"
            if key not in energy and fuel != selected_fuel:
                values[key] = 0.0
    gas = (values["annual_lpg_kwh"] + values["annual_png_kwh"]
           if values["annual_lpg_kwh"] is not None and values["annual_png_kwh"] is not None else None)
    values["annual_gas_kwh"] = gas
    if explicit and "annual_gas_kwh" in energy and (legacy is None or gas is None or not math.isclose(legacy, gas, rel_tol=1e-6, abs_tol=1e-5)):
        flags.append("Conflicting gas labels: annual_gas_kwh must equal annual_lpg_kwh + annual_png_kwh.")
    for key in CORE_ENERGY_KEYS:
        if values[key] is None:
            flags.append(f"Missing or invalid {key}; annual energy must be finite and non-negative.")
    if "annual_electricity_demand_kwh" in energy:
        values["annual_electricity_demand_kwh"] = _number(energy["annual_electricity_demand_kwh"])
        if values["annual_electricity_demand_kwh"] is None:
            flags.append("Missing or invalid annual_electricity_demand_kwh.")
    return values, flags


def _property_errors(home):
    home = home if isinstance(home, Mapping) else {}
    errors = []
    # Advanced fields may use disclosed physics defaults; basic household inputs
    # must be supplied and are never filled inside the scenario engine.
    for field in ("area_m2", "occupants", "solar_kw", "ac_units", "ac_hours_per_day", "led_fraction"):
        lower = 0.01 if field in ("area_m2", "occupants") else 0
        maximum = 1 if field == "led_fraction" else 24 if field == "ac_hours_per_day" else None
        if _number(home.get(field), minimum=lower, maximum=maximum) is None:
            errors.append(f"Missing or invalid {field}.")
        elif field in ("occupants", "ac_units") and not float(home[field]).is_integer():
            errors.append(f"Invalid {field}: counts must be whole numbers.")
    for field in CATEGORICAL_FEATURES:
        value = home.get(field)
        valid = _bool(value) is not None if field == "smart_controls" else isinstance(value, str) and value in OPTIONS[field]
        if not valid:
            errors.append(f"Missing or invalid {field}.")
    units = _number(home.get("ac_units"))
    hours = _number(home.get("ac_hours_per_day"))
    if home.get("cooling") == "fans_only" and ((units or 0) > 0 or (hours or 0) > 0):
        errors.append("Conflicting cooling data: fans_only must have zero AC units and AC hours.")
    if not errors:
        errors += validate_home(dict(home))
    return errors


def _fuel_errors(home, energy):
    fuel = home.get("cooking_fuel")
    errors = []
    for name in ("lpg", "png"):
        if fuel != name and (energy.get(f"annual_{name}_kwh") or 0) > 1e-6:
            errors.append(f"Conflicting fuel data: {fuel}-only cooking has positive {name.upper()} consumption; mixed cooking is outside this pilot.")
    return errors


def score_home(home: dict, energy: dict) -> dict:
    """Return the 0-100 weighted score and audit components; missing inputs => None.

    Component `weight` is a fraction. A missing component never silently earns
    zero and weights are never renormalized. Classifications use unrounded score.
    """
    home = home if isinstance(home, Mapping) else {}
    en, flags = _energy(energy, home)
    energy_errors = list(flags)
    property_errors = _property_errors(home)
    flags += property_errors + _fuel_errors(home, en)
    full = complete_home(dict(home)) if not property_errors else None
    if full and input_assumptions(dict(home)):
        flags.append("Score uses disclosed engineering defaults for advanced inputs; this illustrative score is not a BEE or ENS certification.")
    cool = (100.0 if full["cooling"] == "fans_only" else _clip_score(100*(float(full["ac_iseer"])-2.5)/4)) if full else None
    led = _number(home.get("led_fraction"), maximum=1)
    appliance = 0.6 * cool + 40 * led if cool is not None and led is not None else None
    area = _number(home.get("area_m2"), minimum=0.01)
    total = sum(en[key] for key in CORE_ENERGY_KEYS) if all(en[key] is not None for key in CORE_ENERGY_KEYS) else None
    purchased_intensity = total / area if total is not None and area else None
    gross = en.get("annual_electricity_demand_kwh")
    if full and en["annual_grid_kwh"] is not None:
        if "annual_electricity_demand_kwh" not in en:
            gross = demand_from_grid(full, en["annual_grid_kwh"])
        elif gross is not None and not math.isclose(electricity_balance(full, gross)["annual_grid_kwh"], en["annual_grid_kwh"], rel_tol=1e-6, abs_tol=.01):
            energy_errors.append("Conflicting electricity labels: gross demand does not match grid imports and the declared PV balance.")
            flags.append(energy_errors[-1])
    intensity = gross / area if gross is not None and area else None
    intensity_score = _clip_score(100*(225-intensity)/200) if intensity is not None and gross > 0 else None
    if total == 0:
        flags.append("Zero purchased-energy baseline: energy intensity subscore and improvement percentage are unavailable.")
    water = _mapped(ASSUMPTIONS["hot_water_subscore"], home.get("hot_water"))
    systems = 0.6 * cool + 0.4 * water if cool is not None and water is not None else None
    solar = _number(home.get("solar_kw"))
    renewable = max(min(solar / 3, 1) * 100, 60 if home.get("hot_water") == "solar_heater" else 0) if solar is not None and water is not None else None
    smart = _bool(home.get("smart_controls"))
    fabric = glazing = None
    if full:
        roof_weight = .6 * float(full["roof_exposed_fraction"])
        fabric = roof_weight * _clip_score(100*(3-float(full["roof_u_value"]))/2.4) + (1-roof_weight)*_clip_score(100*(2.2-float(full["wall_u_value"]))/1.4)
        window_u = 2.8 if full["glazing"] == "double" else 5.7
        glazing = .35*_clip_score(100*(5.7-window_u)/2.9) + .5*_clip_score(100*(.75-float(full["window_shgc"]))/ .35) + .15*_clip_score(100*float(full["window_shading_fraction"])/.75)
    subscores = [appliance, intensity_score, fabric, systems, glazing, renewable,
                 100 if smart is True else 0 if smart is False else None]
    components = []
    for (name, weight), subscore in zip(ASSUMPTIONS["score_weights"].items(), subscores):
        components.append({"name": name, "weight": weight, "subscore": subscore,
                           "contribution": weight * subscore if subscore is not None else None})
    missing = [c["name"] for c in components if c["subscore"] is None]
    # Inconsistent input must not produce an authoritative total from partial components.
    invalid = energy_errors + _property_errors(home) + _fuel_errors(home, en)
    score = sum(c["contribution"] for c in components) if not missing and not invalid else None
    classification = ("Unavailable" if score is None else "Highly efficient" if score >= 80 else
                      "Good" if score >= 65 else "Moderate" if score >= 50 else "Poor" if score >= 30 else "Very poor")
    return {"score": score, "classification": classification, "components": components,
            "flags": list(dict.fromkeys(flags)), "energy_intensity_kwh_m2": intensity,
            "electricity_demand_intensity_kwh_m2": intensity,
            "purchased_energy_intensity_kwh_m2": purchased_intensity,
            "missing_components": missing}


def _retrofit_decisions(home):
    home = home if isinstance(home, Mapping) else {}
    decisions = []
    for retrofit in RETROFITS:
        item = dict(retrofit)
        action = item["id"]
        rejection = None
        reason = ""
        suitability = "High"
        if home.get("retrofit_consent") is not True:
            rejection = "Retrofit consent is absent, unknown or declined."
        elif action in ("insulation", "glazing", "solar", "solar_water_heater") and home.get("heritage_restricted") is not False:
            rejection = "Heritage/planning restriction is present or unknown; a survey and consent are required."
        elif action in ("insulation", "solar", "solar_water_heater") and home.get("roof_access") is not True:
            rejection = "Roof access/permission is absent or unknown."
        elif action == "insulation":
            if _number(home.get("roof_exposed_fraction", 1.0)) == 0:
                rejection = "No exposed roof area; this roof-only retrofit cannot reduce the household cooling load."
            elif "roof_u_value" in home and _number(home.get("roof_u_value")) is not None and float(home["roof_u_value"]) <= .6:
                rejection = "Roof U-value is already at or better than the illustrative 0.6 W/m2K target."
            elif home.get("insulation") not in ("poor", "average") and (_number(home.get("roof_u_value")) or 0) <= .6:
                rejection = "Insulation is already good or its condition is unknown."
            else:
                reason = "Reduce exposed-roof U-value to at most 0.6 W/m2K before AC upgrades; wall properties stay as entered. Assumes roof/moisture/fire-safety survey. Fan-only comfort benefits are not credited as electricity savings."
        elif action == "glazing":
            if home.get("glazing") != "single":
                rejection = "Double glazing is already installed or glazing is unknown."
            else:
                suitability = "Medium"
                reason = "Reduce cooling heat gain where single glazing exists; ventilation, shading and a site survey remain necessary."
        elif action == "led_lighting":
            led = _number(home.get("led_fraction"), maximum=1)
            if led is None or led >= 1:
                rejection = "Lighting is already all LED or LED share is unknown."
            else:
                reason = "Replace remaining non-LED lamps at unchanged light output and operating hours."
        elif action == "efficient_ac":
            if home.get("cooling") not in ("ac_standard", "ac_efficient") or (_number(home.get("ac_units")) or 0) <= 0 or (_number(home.get("ac_iseer")) or (5.2 if home.get("cooling") == "ac_efficient" else 3.2)) >= 5.2:
                rejection = "Requires an existing standard AC; fan-only, already efficient or unknown systems are excluded."
            else:
                reason = "Improve actual AC ISEER to at least 5.2 after fabric changes; capacity, comfort setting and operating hours stay fixed. Verify the model's current BEE label and suitable sizing."
        elif action == "smart_controls":
            if home.get("smart_controls") is not False:
                rejection = "Controls are already installed or their status is unknown."
            else:
                reason = "Timers and temperature schedules reduce unnecessary AC use without assumed comfort changes. This model assigns no energy saving when no AC is used."
        elif action == "solar_water_heater":
            if home.get("external_space") is not True:
                rejection = "Tank/plumbing space is absent or unknown."
            elif home.get("hot_water") != "electric_geyser":
                rejection = "Requires an existing electric geyser; heat-pump/solar combinations need a separately specified backup system, and no-hot-water homes are excluded."
            else:
                suitability = "Medium"
                reason = "Replace part of electric hot-water demand with solar heat; assumes 70% annual solar share and space/plumbing suitability. Backup remains electric."
        elif action == "induction":
            if home.get("cooking_fuel") not in ("lpg", "png"):
                rejection = "Requires LPG or PNG cooking; induction is already installed or cooking fuel is unknown."
            elif home.get("electric_connection") is not True:
                rejection = "A suitable electricity connection is absent or unknown."
            else:
                suitability = "Medium"
                reason = "Switch the declared LPG or PNG cooking fuel to induction, preserving assumed useful cooking heat; compatible cookware and circuit assessment required. Electricity increases and operational CO2 can increase."
        elif action == "solar":
            capacity = _number(home.get("solar_kw"))
            if capacity is None or capacity > 0:
                rejection = "Solar PV is already installed or capacity is unknown; expansion cannot be sized without roof data."
            else:
                rejection = _solar_site_rejection(home)
                reason = ("Install illustrative 3 kW PV after efficiency changes; preliminary site declarations pass, but a professional structural/shading/electrical survey is still required. Credit only modeled self-use, with no export savings."
                          if home.get("require_site_checks") is True else
                          "Install illustrative 3 kW PV after efficiency changes; feasibility is conditional on usable roof area and a structural/shading/electrical survey. Credit only modeled self-use, with no export savings.")
        item.update({"feasible": rejection is None, "suitability": suitability,
                     "reason": rejection if rejection else reason})
        decisions.append(item)
    return decisions


def _solar_site_rejection(home):
    """Optional strict site screen; missing engineering evidence is never a pass.

    Legacy callers may explicitly disable or omit this additional screen. A
    malformed policy value must not silently disable it. Passing declarations
    do not establish installer-certified safety or achievable system capacity.
    """
    if "require_site_checks" in home and not isinstance(home["require_site_checks"], bool):
        return "Invalid solar site-check policy: require_site_checks must be a boolean; PV is blocked until corrected."
    if home.get("require_site_checks") is not True:
        return None
    failures = []
    area = _number(home.get("usable_roof_area_m2"))
    required_area = ASSUMPTIONS["solar_roof_area_screen_m2"]
    if area is None:
        failures.append("usable roof area is missing or invalid")
    elif area < required_area:
        failures.append(f"usable roof area is below the preliminary {required_area:g} m2 requirement for 3 kW")
    for field, label in (("solar_shading_ok", "shading suitability"),
                         ("solar_structure_ok", "structural suitability"),
                         ("solar_electrical_ok", "electrical suitability")):
        if home.get(field) is not True:
            failures.append(f"{label} is failed or unconfirmed")
    return "Solar site screen not passed: " + "; ".join(failures) + "." if failures else None


def feasible_retrofits(home: dict) -> list[dict]:
    """Only feasible candidates, ordered by interactions; suitability is provisional."""
    return [{key: item[key] for key in ("id", "name", "suitability", "reason", "stage")}
            for item in _retrofit_decisions(home) if item["feasible"]]


def _nominal_end_uses(home):
    """Unmetered allocation shared exactly with the synthetic-label physics."""
    reference = expected_end_uses(home)
    return {"cooling": reference["cooling_kwh"], "fans": reference["fans_kwh"],
            "lighting": reference["lighting_kwh"], "water": reference["hot_water_kwh"],
            "cooking": reference["cooking_electric_kwh"], "other": reference["other_kwh"]}


def _initial_state(home, energy):
    full = complete_home(dict(home))
    for constraint in ("roof_access", "external_space", "electric_connection", "heritage_restricted", "retrofit_consent"):
        if constraint not in home:
            full[constraint] = None
    nominal = _nominal_end_uses(full)
    gross_nominal = sum(nominal.values())
    imports = energy["annual_grid_kwh"]
    if "annual_electricity_demand_kwh" in energy:
        gross = energy["annual_electricity_demand_kwh"]
        if gross is None or not math.isclose(electricity_balance(full, gross)["annual_grid_kwh"], imports, rel_tol=1e-6, abs_tol=.01):
            raise ValueError("Conflicting electricity labels: supplied gross demand and grid imports do not match the declared PV balance.")
    else:
        gross = demand_from_grid(full, imports)
    scale = gross / gross_nominal if gross_nominal else 0
    return {"home": full, "end_uses": {key: value * scale for key, value in nominal.items()},
            "lpg": energy["annual_lpg_kwh"], "png": energy["annual_png_kwh"],
            "allocation_reference": {"nominal_end_uses_kwh": nominal,
                                     "nominal_gross_kwh": gross_nominal,
                                     "anchored_gross_kwh": gross,
                                     "electricity_scale_factor": scale}}


def _state_energy(state):
    gross = sum(state["end_uses"].values())
    lpg, png = max(0.0, state["lpg"]), max(0.0, state["png"])
    return {**electricity_balance(state["home"], gross), "annual_electricity_demand_kwh": gross,
            "annual_lpg_kwh": lpg, "annual_png_kwh": png, "annual_gas_kwh": lpg + png}


def _apply(state, action):
    home, end = state["home"], state["end_uses"]
    previous = _nominal_end_uses(home)
    fuel_switch = None
    if action == "insulation":
        home["roof_u_value"] = min(float(home["roof_u_value"]), .6)
        home["insulation"] = "good"
    elif action == "glazing":
        home["glazing"] = "double"
        home["window_shgc"] = min(float(home["window_shgc"]), .4)
    elif action == "led_lighting":
        home["led_fraction"] = 1.0
    elif action == "efficient_ac":
        home["cooling"] = "ac_efficient"
        home["ac_iseer"] = max(float(home["ac_iseer"]), 5.2)
    elif action == "smart_controls":
        home["smart_controls"] = True
    elif action == "solar_water_heater":
        home["hot_water"] = "solar_heater"
    elif action == "induction":
        useful_lpg = state["lpg"] * 0.55
        useful_png = state["png"] * 0.50
        added_electricity = (useful_lpg + useful_png) / 0.84
        fuel_switch = {"source_lpg_kwh": state["lpg"], "source_png_kwh": state["png"],
                       "lpg_efficiency": 0.55, "png_efficiency": 0.50,
                       "induction_efficiency": 0.84,
                       "useful_cooking_heat_kwh": useful_lpg + useful_png,
                       "added_electricity_kwh": added_electricity,
                       "equation": "added electricity = (entered LPG kWh * 0.55 + entered PNG kWh * 0.50) / 0.84"}
        end["cooking"] += added_electricity
        state["lpg"] = 0.0
        state["png"] = 0.0
        home["cooking_fuel"] = "induction"
    elif action == "solar":
        home["solar_kw"] = 3.0
    current = _nominal_end_uses(home)
    ratios = {}
    for key in end:
        if key == "cooking" and action == "induction":
            ratios[key] = None
            continue  # Anchored gas service, not electricity-allocation scale.
        if previous[key] > 0:
            ratios[key] = current[key] / previous[key]
            end[key] *= ratios[key]
        elif current[key] == 0:
            # This case may include induction cooking anchored from gas in an
            # earlier step; its nominal cooking value is then positive.
            ratios[key] = None  # 0/0 is undefined, never presented as a ratio.
            end[key] = 0.0
        else:
            ratios[key] = None
    return {"nominal_before_end_uses_kwh": previous,
            "nominal_after_end_uses_kwh": current,
            "end_use_ratios": ratios, "fuel_switch_conversion": fuel_switch}


def _savings(before, after, factors):
    if any(record.get(key) is None for record in (before, after) for key in CORE_ENERGY_KEYS):
        return dict.fromkeys(SAVINGS_KEYS)
    electricity = before["annual_grid_kwh"] - after["annual_grid_kwh"]
    lpg = before["annual_lpg_kwh"] - after["annual_lpg_kwh"]
    png = before["annual_png_kwh"] - after["annual_png_kwh"]
    gas = lpg + png
    total = electricity + gas
    baseline = before["annual_grid_kwh"] + before["annual_gas_kwh"]
    elec_factor = factors["electricity_kg_co2_per_kwh"]
    lpg_factor = factors["lpg_kg_co2_per_kwh"]
    png_factor = factors["png_kg_co2_per_kwh"]
    carbon = (electricity * elec_factor + lpg * lpg_factor + png * png_factor
              if all(value is not None for value in (elec_factor, lpg_factor, png_factor)) else None)
    return {"electricity_kwh": electricity, "lpg_kwh": lpg, "png_kwh": png, "gas_kwh": gas, "total_kwh": total,
            "percent": 100 * total / baseline if baseline > 0 else None, "carbon_kg": carbon}


def _effective_factors(factors):
    effective = deepcopy(DEFAULT_FACTORS)
    flags = []
    if factors is not None and not isinstance(factors, Mapping):
        factors = {"electricity_kg_co2_per_kwh": None, "lpg_kg_co2_per_kwh": None, "png_kg_co2_per_kwh": None}
    for key in ("electricity_kg_co2_per_kwh", "lpg_kg_co2_per_kwh", "png_kg_co2_per_kwh"):
        if factors is not None and key in factors:
            effective[key] = _number(factors[key])
            if effective[key] is None:
                flags.append(f"Invalid {key}; carbon reduction is unavailable.")
            elif effective[key] != DEFAULT_FACTORS[key]:
                effective[f"{key}_override"] = True
                flags.append(f"User-supplied {key}; default source metadata describes the reference, not verification of this override.")
    return effective, flags


def _anchor_trace(home, supplied_energy, normalized_energy, state, baseline):
    """Describe the allocation actually made by _initial_state, not a new fit."""
    allocation = deepcopy(state["allocation_reference"])
    full = state["home"]
    has_gross = "annual_electricity_demand_kwh" in normalized_energy
    return {
        "status": "available",
        "supplied_energy": deepcopy(dict(supplied_energy)) if isinstance(supplied_energy, Mapping) else {},
        "normalized_energy": deepcopy(normalized_energy),
        "baseline_energy": deepcopy(baseline),
        **allocation,
        "anchored_end_uses_kwh": deepcopy(state["end_uses"]),
        "end_use_allocation_measured": False,
        "assumed_inputs": input_assumptions(dict(home)),
        "electricity_anchor_rule": "supplied gross demand checked against the PV balance" if has_gross else "grid imports inverted through the assumed annual PV balance",
        "pv_assumptions": {
            "solar_kw": full["solar_kw"], "city": full["city"],
            "yield_kwh_per_kw_year": climate_parameters(full)["pv_yield_kwh_per_kw_year"],
            "self_consumption_fraction": full["solar_self_consumption_fraction"],
            "gross_demand_self_use_cap_fraction": 0.75,
            "export_credit": False,
            "generation_source": "Cached PVGIS 5.3 ERA5 2005-2023, 20-degree south-facing, 14% user loss",
            "measured_pv_flows": False,
        },
        "equations": [
            "scale = anchored gross electricity / sum(nominal electrical end uses)",
            "anchored end-use kWh = nominal end-use kWh * scale; these shares are inferred, not metered",
            "PV generation = installed kW * location yield; self-use = min(generation * self-consumption fraction, 0.75 * gross demand)",
            "grid imports = gross electricity - self-used PV; exports = generation - self-used PV; exports receive no savings credit",
            "meter-only gross electricity = min(4 * grid imports, grid imports + generation * self-consumption fraction)",
            "LPG and PNG retain the supplied fuel totals; their useful cooking heat is not scaled with electricity",
        ],
    }


def _apply_with_trace(state, action, factors, comparison):
    """Run one action once and retain the exact states used for its savings."""
    before_home = deepcopy(state["home"])
    before_end = deepcopy(state["end_uses"])
    before_energy = _state_energy(state)
    operation = _apply(state, action)
    after_energy = _state_energy(state)
    savings = _savings(before_energy, after_energy, factors)
    factor_values = {"electricity": factors["electricity_kg_co2_per_kwh"],
                     "lpg": factors["lpg_kg_co2_per_kwh"],
                     "png": factors["png_kg_co2_per_kwh"]}
    carbon_terms = {fuel: (savings[f"{fuel}_kwh"] * factor if factor is not None else None)
                    for fuel, factor in factor_values.items()}
    changes = {key: {"before": before_home.get(key), "after": value}
               for key, value in state["home"].items() if before_home.get(key) != value}
    end_equations = {}
    for key, before in before_end.items():
        ratio = operation["end_use_ratios"][key]
        rule = ("before + added electricity from anchored fuel conversion" if key == "cooking" and operation["fuel_switch_conversion"] is not None
                else "before * nominal after / nominal before" if ratio is not None
                else "zero nominal demand remains zero; 0/0 ratio is undefined")
        end_equations[key] = {"rule": rule, "before_kwh": before,
                              "ratio": ratio, "after_kwh": state["end_uses"][key]}
    return {
        "status": "available", "retrofit_id": action, "comparison": comparison,
        "physical_input_changes": changes,
        "before_end_uses_kwh": before_end,
        "after_end_uses_kwh": deepcopy(state["end_uses"]),
        **operation,
        "end_use_equations": end_equations,
        "before_energy": before_energy, "after_energy": after_energy,
        "savings": savings,
        "savings_percent_denominator_kwh": before_energy["annual_grid_kwh"] + before_energy["annual_gas_kwh"],
        "carbon_factor_values": factor_values, "carbon_terms_kg": carbon_terms,
        "carbon_status": "available" if savings["carbon_kg"] is not None else "unavailable: an emission factor is invalid",
        "equations": [
            "changed electrical end-use = previous anchored end-use * new nominal physics / previous nominal physics; zero-to-zero ratios are undefined",
            "fuel switching uses the separately anchored LPG/PNG useful cooking heat; it is not multiplied by the electricity scale",
            "recompute gross demand and the full PV balance after this step",
            "signed fuel saving = before - after; electricity saving may be negative",
            "signed CO2 saving = electricity saved * grid factor + LPG saved * LPG factor + PNG saved * PNG factor",
            "percent saving = 100 * total purchased-energy saving / this comparison's before purchased energy; undefined when the denominator is zero",
            "standalone comparisons start from the original baseline; package marginal comparisons start from the preceding package state",
        ],
    }


def evaluate_scenario(home: dict, energy: dict, selected: list[str], factors: dict | None = None) -> dict:
    """Recompute the selected package plus all feasible recommendation estimates.

    Returns baseline/after energy dicts; baseline_score/after_score audit dicts;
    savings with signed electricity_kwh, gas_kwh, total_kwh, percent, carbon_kg;
    recommendations with standalone and marginal sequential savings; rejected
    selections; applied IDs; factors provenance; and unavailable value_impact.
    Missing or conflicting core inputs return unavailable scenario estimates.
    """
    home = home if isinstance(home, Mapping) else {}
    baseline, flags = _energy(energy, home)
    normalized_energy = deepcopy(baseline)
    energy_errors = list(flags)
    effective, factor_flags = _effective_factors(factors)
    flags += factor_flags
    errors = energy_errors + _property_errors(home) + _fuel_errors(home, baseline)
    flags += errors
    flags += ["Retrofit estimates use assumed end-use allocation and constant comfort/use; site assessment required.",
              "India adaptation: appliance efficiency and cooling/hot water replace EPC and space-heating components; no certificate is predicted.",
              "Carbon is operational CO2 only using a dated CEA national generation proxy, not complete lifecycle CO2e."]
    if home.get("require_site_checks") is True:
        flags.append("Rooftop solar site screening is preliminary and based on user declarations: at least 30 m2 usable roof area for illustrative 3 kW PV plus shading, structural and electrical suitability. Actual module/layout needs vary; this is not installation certification.")
    elif "require_site_checks" in home and not isinstance(home["require_site_checks"], bool):
        flags.append("Invalid solar site-check policy: require_site_checks must be a boolean; solar PV is blocked until corrected.")
    else:
        flags.append("Rooftop solar feasibility remains conditional: roof permission alone does not establish usable area, shading, structural or electrical suitability. The illustrative 3 kW estimate assumes a site survey.")
    total = sum(baseline[key] for key in CORE_ENERGY_KEYS) if all(baseline[key] is not None for key in CORE_ENERGY_KEYS) else None
    if total == 0:
        flags.append("Zero purchased-energy baseline: improvement percentage is unavailable.")
    feasible = feasible_retrofits(home)
    decisions = {item["id"]: item for item in _retrofit_decisions(home)}
    requested = list(dict.fromkeys(str(value) for value in (selected or []))) if isinstance(selected, (list, tuple)) else []
    rejected = [{"id": action, "reason": decisions[action]["reason"] if action in decisions else "Unknown retrofit ID."}
                for action in requested if action not in decisions or not decisions[action]["feasible"]]
    applied = [item["id"] for item in feasible if item["id"] in requested]
    initial = None
    if not errors:
        try:
            initial = _initial_state(home, baseline)
            baseline = _state_energy(initial)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
            flags.append(str(exc))
    baseline_score = score_home(home, baseline)
    unavailable = bool(errors)
    if unavailable:
        null_energy = dict.fromkeys(ENERGY_KEYS)
        unavailable_trace = {"status": "unavailable", "reasons": list(dict.fromkeys(errors))}
        recommendations = [dict(item, selected=item["id"] in applied,
                                standalone_savings=_savings(baseline, null_energy, effective),
                                sequential_savings=_savings(baseline, null_energy, effective),
                                recommended_sequential_savings=_savings(baseline, null_energy, effective),
                                standalone_trace=dict(unavailable_trace, retrofit_id=item["id"], comparison="standalone"),
                                selected_marginal_trace=dict(unavailable_trace, retrofit_id=item["id"], comparison="selected_package_marginal"),
                                recommended_marginal_trace=dict(unavailable_trace, retrofit_id=item["id"], comparison="recommended_package_marginal")) for item in feasible]
        flags.append("Resolve missing/conflicting inputs before estimating scenarios; no default household values were substituted.")
        return {"baseline": baseline, "after": null_energy, "baseline_score": baseline_score,
                "after_score": score_home(home, null_energy), "savings": _savings(baseline, null_energy, effective),
                "recommendations": recommendations, "rejected": rejected, "applied": [],
                "home_after": deepcopy(dict(home)), "flags": list(dict.fromkeys(flags)), "factors": effective,
                "calculation_trace": {"schema_version": "1.0", **unavailable_trace,
                                      "anchor": {**unavailable_trace,
                                                 "supplied_energy": deepcopy(dict(energy)) if isinstance(energy, Mapping) else {},
                                                 "normalized_energy": normalized_energy,
                                                 "end_use_allocation_measured": False},
                                      "selected_steps": []},
                "recommended_package": {"after": null_energy, "savings": _savings(baseline, null_energy, effective), "applied": []},
                "value_impact": {"available": False, "reason": ASSUMPTIONS["value_impact"]}}
    assumed = input_assumptions(dict(home))
    if assumed:
        flags.append("Engineering defaults were assumed for: " + ", ".join(assumed) + ". Inspect advanced inputs before interpreting estimates.")
    flags += ["Gross electricity and PV self-use are separately accounted; exports receive no energy or carbon credit.",
              "Weather uses NASA POWER single-year 2024 gridded data; PV generation uses the separate PVGIS ERA5 2005-2023 reference. Synthetic training labels remain simulated.",
              "Hyderabad is the primary pilot. Space heating and humidity/latent cooling are not modeled; other cities are exploratory even though their weather/PV references are sourced."]
    if home.get("cooling") != "fans_only" and (float(home["ac_units"]) == 0 or float(home["ac_hours_per_day"]) == 0):
        flags.append("AC is installed but has zero entered use/capacity count; modeled AC demand and AC-related savings are zero.")
    diagnostics = expected_end_uses(initial["home"])
    if diagnostics.get("annual_unmet_cooling_kwh_thermal", 0) > .01:
        flags.append("Entered AC capacity cannot meet all modeled thermal cooling load; constant comfort is not established. Insulation may improve comfort with limited metered energy savings.")
    chosen, recommended_state = deepcopy(initial), deepcopy(initial)
    recommendations = []
    selected_steps = []
    for item in feasible:
        standalone = deepcopy(initial)
        standalone_trace = _apply_with_trace(standalone, item["id"], effective, "standalone")
        recommended_trace = _apply_with_trace(recommended_state, item["id"], effective, "recommended_package_marginal")
        if item["id"] in applied:
            selected_trace = _apply_with_trace(chosen, item["id"], effective, "selected_package_marginal")
            selected_steps.append(selected_trace)
            sequential = selected_trace["savings"]
        else:
            sequential = dict.fromkeys(SAVINGS_KEYS)
            selected_trace = {"status": "not_selected", "retrofit_id": item["id"],
                              "comparison": "selected_package_marginal",
                              "reason": "This retrofit is not in the selected package, so there is no selected-package marginal calculation."}
        recommendations.append(dict(item, selected=item["id"] in applied,
                                    standalone_savings=standalone_trace["savings"],
                                    sequential_savings=sequential,
                                    recommended_sequential_savings=recommended_trace["savings"],
                                    standalone_trace=standalone_trace,
                                    selected_marginal_trace=selected_trace,
                                    recommended_marginal_trace=recommended_trace))
    after = _state_energy(chosen)
    # Avoid representational drift on an empty package.
    if not applied:
        after = dict(baseline)
    if any(item["id"] == "induction" for item in recommendations):
        flags.append("Induction is a fuel-switch option: purchased energy may fall while operational CO2 rises; inspect signed per-fuel changes.")
    return {"baseline": baseline, "after": after, "baseline_score": baseline_score,
            "after_score": score_home(chosen["home"], after), "savings": _savings(baseline, after, effective),
            "recommendations": recommendations, "rejected": rejected, "applied": applied,
            "home_after": chosen["home"], "flags": list(dict.fromkeys(flags)), "factors": effective,
            "calculation_trace": {"schema_version": "1.0", "status": "available",
                                  "anchor": _anchor_trace(home, energy, normalized_energy, initial, baseline),
                                  "selected_steps": selected_steps},
            "recommended_package": {"after": _state_energy(recommended_state),
                                    "savings": _savings(baseline, _state_energy(recommended_state), effective),
                                    "applied": [item["id"] for item in feasible]},
            "value_impact": {"available": False, "reason": ASSUMPTIONS["value_impact"]}}
