"""Financial scenarios downstream of signed, separately priced fuel savings.

No prices, installation quotes, subsidy eligibility or transaction-value effects
are predicted here. Optional user-entered property premium sensitivity is an
explicitly hypothetical scenario, independent of empirical valuation output.
All cash flows occur at year end; capex/subsidy occur at time zero.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from numbers import Real

from .billing import bill_savings_trace
from .engine import LPG_KWH_PER_KG, RETROFITS


TIMING_OPTIONS = {
    "first_year": "Entered annual saving is the first year's saving: S * (1+e) ** (t-1).",
    "report_base_year": "Entered annual saving is a base-year amount: S * (1+e) ** t; follows the supplied report's timing.",
}
MEASURE_IDS = frozenset(item["id"] for item in RETROFITS)


def _number(value, minimum=-math.inf, maximum=math.inf):
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) and minimum <= result <= maximum else None


def _error(errors, code, field, message):
    errors.append({"code": code, "field": field, "message": message})


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _validated_bill_trace(scenario, trace, errors):
    """Reprice upstream fuel deltas; reject stale or conflicting bill records."""
    if not isinstance(trace, Mapping) or trace.get("status") != "available":
        _error(errors, "missing_bill_trace", "bill_trace", "A valid signed per-fuel bill calculation is required.")
        return None
    savings = scenario.get("savings")
    if not isinstance(savings, Mapping) or any(_number(savings.get(key), -1e8, 1e8) is None for key in ("electricity_kwh", "lpg_kwh", "png_kwh")):
        _error(errors, "invalid_energy_savings", "scenario.savings", "Finite signed electricity, LPG and PNG savings within the supported range are required.")
        return None
    terms = trace.get("terms")
    names = {"Grid electricity": ("electricity_rate", "electricity_kwh", "kWh", 1),
             "LPG": ("lpg_price_kg", "lpg_kwh", "kg", LPG_KWH_PER_KG),
             "PNG": ("png_rate", "png_kwh", "kWh net CV", 1)}
    rates = {}
    if not isinstance(terms, list) or len(terms) != 3:
        _error(errors, "invalid_bill_terms", "bill_trace.terms", "Exactly one electricity, LPG and PNG billing term is required.")
        return None
    for term in terms:
        if not isinstance(term, Mapping) or not isinstance(term.get("Fuel"), str) or term.get("Fuel") not in names:
            _error(errors, "invalid_bill_terms", "bill_trace.terms", "Unexpected fuel in the bill calculation.")
            continue
        rate_key, savings_key, unit, conversion = names[term["Fuel"]]
        rate = _number(term.get("Rate (INR/unit)"), 0, 1000)
        units = _number(term.get("Saved units/year"))
        money = _number(term.get("Saving (INR/year)"))
        if (rate_key in rates or rate is None or units is None or money is None or term.get("Unit") != unit
                or not math.isclose(units, savings[savings_key] / conversion, rel_tol=1e-9, abs_tol=1e-7)
                or not math.isclose(money, units * rate if rate is not None else math.inf, rel_tol=1e-9, abs_tol=1e-7)):
            _error(errors, "conflicting_bill_trace", "bill_trace.terms", "Fuel billing units, rates or savings do not match this selected scenario.")
        elif rate is not None:
            rates[rate_key] = rate
    if len(rates) != 3:
        return None
    expected = bill_savings_trace({key: float(savings[key]) for key in ("electricity_kwh", "lpg_kwh", "png_kwh")}, **rates)
    total = _number(trace.get("total_inr_per_year"), -1e12, 1e12)
    if total is None or not math.isclose(total, expected["total_inr_per_year"], rel_tol=1e-9, abs_tol=1e-7):
        _error(errors, "conflicting_bill_total", "bill_trace.total_inr_per_year", "The supplied bill total must equal this scenario's signed per-fuel calculation.")
        return None
    return expected


def _value_scenario(config, errors):
    """Apply explicit user-entered premiums; never derive value from savings."""
    if config is None:
        return None
    if not isinstance(config, Mapping):
        _error(errors, "invalid_value_config", "value_scenario", "Valuation settings must be a mapping.")
        return None
    if config.get("enabled", False) is False:
        return None
    if config.get("enabled") is not True:
        _error(errors, "invalid_value_opt_in", "value_scenario.enabled", "Enable the hypothetical value scenario explicitly.")
        return None
    baseline = _number(config.get("baseline_value_inr"), 1, 1e15)
    carpet_raw, rate_raw = config.get("carpet_area_sqft"), config.get("assumed_rate_inr_per_sqft")
    if config.get("baseline_value_inr") is not None:
        if baseline is None:
            _error(errors, "invalid_baseline_value", "value_scenario.baseline_value_inr", "Enter a finite positive total baseline property value.")
        if carpet_raw is not None or rate_raw is not None:
            _error(errors, "ambiguous_baseline_value", "value_scenario", "Use either an explicit total value or explicit carpet area and an assumed rate, not both.")
        source = "User-supplied total property value; not independently verified"
    else:
        carpet = _number(carpet_raw, .01, 1e7)
        rate = _number(rate_raw, .01, 1e8)
        if carpet is None or rate is None:
            _error(errors, "missing_baseline_value", "value_scenario", "Supply a total property value, or separately declared carpet area (sq ft) and assumed INR/sq ft rate. Built-up energy-model area is not substituted.")
        else:
            baseline = carpet * rate
        source = "Explicit user carpet area multiplied by user-assumed rate; not verified market data"
    low = _number(config.get("premium_low_percent"), 0, 100)
    high = _number(config.get("premium_high_percent"), 0, 100)
    if low is None or high is None or low > high:
        _error(errors, "invalid_hypothetical_premiums", "value_scenario", "Explicit hypothetical low/high premium percentages from 0 to 100 are required, with low no greater than high.")
    forbidden = {"cap_ratio", "scenario_spread", "spread", "include_solar_asset_proxy", "solar_asset_multiplier"}
    if any(key in config for key in forbidden):
        _error(errors, "unsupported_automatic_value_proxy", "value_scenario", "NPV capitalization, automatic caps/spreads and solar equipment value proxies are not supported. Enter hypothetical premium bounds explicitly.")
    if errors:
        return None
    uplift = [baseline * low / 100, baseline * high / 100]
    return {"status": "hypothetical_only", "baseline_value_inr": baseline, "baseline_source": source,
            "baseline_source_detail": _text(config.get("source", config.get("baseline_source"))),
            "carpet_area_sqft": _number(carpet_raw, .01) if carpet_raw is not None else None,
            "assumed_rate_inr_per_sqft": _number(rate_raw, .01) if rate_raw is not None else None,
            "premium_low_percent": low, "premium_high_percent": high,
            "valuation_uplift_range_inr": uplift,
            "post_retrofit_hypothetical_value_range_inr": [baseline + amount for amount in uplift],
            "definition": "Arithmetic sensitivity using user-entered hypothetical premium bounds; no premium is predicted.",
            "disclosures": [
                "These are user-entered hypothetical premiums, not observed transaction uplift, appraisal, confidence intervals or evidence that buyers will pay this amount.",
                "Hypothetical uplift = user baseline value * user premium percent / 100. Neither NPV, score, solar capacity nor installation cost determines the premium.",
                "Empirical resale-value prediction remains unavailable without credible local transaction evidence.",
                "No score threshold, IGBC/GRIHA certification or certification premium is inferred.",
            ]}


def calculate_financial_scenario(scenario, bill_trace, installation_costs, *, years,
                                 discount_rate, escalation_rate, timing="first_year",
                                 annual_maintenance_inr=0, replacements=None,
                                 solar_subsidy_inr=None, solar_subsidy_confirmed=False,
                                 solar_subsidy_source="", cost_provenance="",
                                 value_scenario=None):
    """Return an auditable investment scenario or structured validation errors.

    ``installation_costs`` maps *applied* retrofit IDs to explicit incremental
    amounts, or ``{amount_inr, source}`` records. Unknown is never zero. Stale
    unselected costs are ignored and disclosed. Replacement amounts are future
    nominal year-end expenses; maintenance is constant nominal annual expense.
    Subsidy is solely a user-declared confirmed amount with a source, never an
    automatically awarded or predicted scheme payment.
    """
    errors, valuation_errors = [], []
    disclosures = [
        "Financial scenario only. Upstream energy savings remain unvalidated retrofit estimates; this module does not improve their accuracy.",
        "Signed electricity, LPG and PNG bill effects are priced separately with the upstream flat user rates; fixed charges, slabs and export income are excluded.",
        "Costs apply only to this selected package and must be incremental. Existing equipment and PV assets are not new project expenditure.",
        "Capex and a declared confirmed subsidy are modeled at time zero; all operating cash flows and replacements occur at year end.",
        "Maintenance is a constant nominal annual amount. Replacement expenses are entered future nominal amounts and are not escalated again.",
        "Financing, tax, degradation, residual value and other incentives are excluded; no automatic subsidy eligibility or payment is assumed.",
    ]
    result = {"schema_version": "1.0", "status": "unavailable", "currency": "INR",
              "errors": errors, "valuation_errors": valuation_errors, "annual_savings": None,
              "costs": None, "assumptions": None, "annual_cashflows": [],
              "project_economics": None, "report_value_scenario": None,
              "resale_value_prediction": {"status": "unavailable", "reason": "No credible local transaction evidence or validated resale-price model is available."},
              "disclosures": disclosures}
    if not isinstance(scenario, Mapping):
        _error(errors, "invalid_scenario", "scenario", "An evaluated selected scenario is required.")
        return result
    applied = scenario.get("applied")
    if not isinstance(applied, list) or any(not isinstance(action, str) or action not in MEASURE_IDS for action in applied) or len(set(applied)) != len(applied):
        _error(errors, "invalid_applied_measures", "scenario.applied", "Applied measures must be a unique list of known retrofit IDs.")
        return result
    if not applied:
        _error(errors, "no_package", "scenario.applied", "Select and apply at least one feasible retrofit before analyzing project finances.")
        return result
    trace = scenario.get("calculation_trace")
    if not isinstance(trace, Mapping) or trace.get("status") != "available":
        _error(errors, "unavailable_energy_scenario", "scenario.calculation_trace", "Resolve energy-scenario errors before calculating investment outputs.")
    annual = _validated_bill_trace(scenario, bill_trace, errors)
    result["annual_savings"] = annual
    horizon = _number(years, 1, 50)
    if horizon is None or not horizon.is_integer():
        _error(errors, "invalid_horizon", "years", "Analysis years must be an integer from 1 to 50.")
    discount, escalation = _number(discount_rate, -.99, 2), _number(escalation_rate, -.99, 2)
    maintenance = _number(annual_maintenance_inr, 0, 1e12)
    if discount is None:
        _error(errors, "invalid_discount", "discount_rate", "Discount rate must be a finite ratio between -0.99 and 2.")
    if escalation is None:
        _error(errors, "invalid_escalation", "escalation_rate", "Escalation rate must be a finite ratio between -0.99 and 2.")
    if maintenance is None:
        _error(errors, "invalid_maintenance", "annual_maintenance_inr", "Annual incremental maintenance must be a finite non-negative amount.")
    if not isinstance(timing, str) or timing not in TIMING_OPTIONS:
        _error(errors, "invalid_timing", "timing", "Choose first_year or report_base_year cash-flow timing.")
    costs, ignored = [], []
    if not isinstance(installation_costs, Mapping):
        _error(errors, "missing_costs", "installation_costs", "Explicit incremental costs are required for every applied measure.")
        installation_costs = {}
    ignored = [str(key) for key in installation_costs if key not in applied]
    if ignored:
        disclosures.append("Unselected cost entries were ignored: " + ", ".join(ignored) + ".")
    for action in applied:
        entry = installation_costs.get(action)
        amount = _number(entry.get("amount_inr") if isinstance(entry, Mapping) else entry, 0, 1e12)
        source = _text(entry.get("source")) if isinstance(entry, Mapping) else _text(cost_provenance)
        if amount is None:
            _error(errors, "missing_or_invalid_cost", f"installation_costs.{action}", f"Enter a finite non-negative incremental cost for {action}; unknown cost cannot be treated as zero.")
        else:
            costs.append({"retrofit_id": action, "amount_inr": amount,
                          "source": source or "User-entered amount; no supporting quote supplied",
                          "independently_verified": False})
    new_solar = "solar" in applied
    if new_solar:
        steps = trace.get("selected_steps", []) if isinstance(trace, Mapping) else []
        solar_steps = [step for step in steps if isinstance(step, Mapping) and step.get("retrofit_id") == "solar"] if isinstance(steps, list) else []
        changes = solar_steps[0].get("physical_input_changes") if len(solar_steps) == 1 else None
        change = changes.get("solar_kw", {}) if isinstance(changes, Mapping) else {}
        if (not solar_steps or solar_steps[0].get("status") != "available" or not isinstance(change, Mapping)
                or _number(change.get("before")) != 0 or _number(change.get("after")) != 3):
            _error(errors, "invalid_new_solar", "scenario.calculation_trace.selected_steps", "Solar finance requires the selected engine step installing NEW 3 kW PV from zero existing capacity.")
    subsidy = 0.0 if solar_subsidy_inr is None else _number(solar_subsidy_inr, 0, 1e12)
    source = _text(solar_subsidy_source)
    solar_cost = next((item["amount_inr"] for item in costs if item["retrofit_id"] == "solar"), 0.0)
    if solar_subsidy_confirmed is True and solar_subsidy_inr is None:
        _error(errors, "missing_confirmed_subsidy_amount", "solar_subsidy_inr", "Enter the explicitly confirmed subsidy amount; a blank confirmed amount cannot be treated as zero.")
    elif subsidy is None:
        _error(errors, "invalid_subsidy", "solar_subsidy_inr", "Confirmed subsidy must be a finite non-negative amount.")
    elif subsidy > 0 and (not new_solar or solar_subsidy_confirmed is not True or not source or subsidy > solar_cost):
        _error(errors, "unverified_subsidy", "solar_subsidy_inr", "A positive subsidy requires selected new PV, explicit confirmation, source provenance and an amount no greater than its gross cost.")
    if not isinstance(solar_subsidy_confirmed, bool):
        _error(errors, "invalid_subsidy_confirmation", "solar_subsidy_confirmed", "Subsidy confirmation must be a boolean.")
    replacement_records = []
    if replacements is None:
        replacements = []
    if not isinstance(replacements, list):
        _error(errors, "invalid_replacements", "replacements", "Replacements must be a list of future nominal year/cost records.")
        replacements = []
    for index, item in enumerate(replacements):
        year = _number(item.get("year"), 1, horizon or 50) if isinstance(item, Mapping) else None
        cost = _number(item.get("cost_inr"), 0, 1e12) if isinstance(item, Mapping) else None
        if year is None or not year.is_integer() or cost is None:
            _error(errors, "invalid_replacement", f"replacements.{index}", "Replacement year must be an integer within the analysis horizon and cost a finite non-negative future nominal amount.")
        else:
            replacement_records.append({"year": int(year), "cost_inr": cost, "source": _text(item.get("source")) or "User-entered future nominal expense"})
    result["costs"] = {"selected_installation_costs": costs, "ignored_unselected_cost_ids": ignored,
                       "new_solar_capacity_kw": 3.0 if new_solar else 0.0,
                       "solar_gross_cost_inr": solar_cost,
                       "solar_subsidy_inr": subsidy,
                       "solar_subsidy_source": source or ("No subsidy assumed" if not subsidy else ""),
                       "solar_subsidy_user_confirmed": solar_subsidy_confirmed is True,
                       "subsidy_independently_verified": False,
                       "replacements": replacement_records}
    result["assumptions"] = {"years": int(horizon) if horizon is not None and horizon.is_integer() else None,
                             "discount_rate": discount, "escalation_rate": escalation,
                             "timing": timing if isinstance(timing, str) and timing in TIMING_OPTIONS else None,
                             "timing_definition": TIMING_OPTIONS.get(timing) if isinstance(timing, str) else None,
                             "annual_maintenance_inr": maintenance,
                             "currency": "INR", "cashflow_timing": "year_end", "capex_timing": "time_zero"}
    if errors:
        return result
    gross = sum(item["amount_inr"] for item in costs)
    net_initial = gross - subsidy
    annual_saving = annual["total_inr_per_year"]
    cumulative, pv_bill, pv_maintenance, pv_replacements = -net_initial, 0.0, 0.0, 0.0
    rows = []
    for year in range(1, int(horizon) + 1):
        exponent = year - 1 if timing == "first_year" else year
        bill = annual_saving * (1 + escalation) ** exponent
        replacement = sum(item["cost_inr"] for item in replacement_records if item["year"] == year)
        factor = (1 + discount) ** (-year)
        net = bill - maintenance - replacement
        discounted_bill, discounted_maintenance, discounted_replacement = bill * factor, maintenance * factor, replacement * factor
        discounted_net = net * factor
        cumulative += discounted_net
        pv_bill += discounted_bill
        pv_maintenance += discounted_maintenance
        pv_replacements += discounted_replacement
        row = {"year": year, "escalation_exponent": exponent, "bill_savings_inr": bill,
               "maintenance_inr": maintenance, "replacement_inr": replacement,
               "net_operating_cashflow_inr": net, "discount_factor": factor,
               "discounted_bill_savings_inr": discounted_bill,
               "discounted_maintenance_inr": discounted_maintenance,
               "discounted_replacement_inr": discounted_replacement,
               "discounted_net_cashflow_inr": discounted_net,
               "cumulative_discounted_net_inr": cumulative}
        if not all(math.isfinite(value) for value in row.values()):
            _error(errors, "numeric_overflow", "annual_cashflows", "Cash flows exceed the supported numeric range; outputs are withheld.")
            return result
        rows.append(row)
    simple_definition = "Net initial cost / (entered annual bill saving - annual maintenance); ignores escalation, discounting and replacement expenses. Not a discounted recovery forecast."
    simple_annual = annual_saving - maintenance
    simple_years = net_initial / simple_annual if simple_annual > 0 else None
    if simple_years is not None and not math.isfinite(simple_years):
        simple_years = None
    simple_status = "reached" if simple_years is not None and simple_years <= horizon else "not_reached"
    simple = {"status": simple_status, "years": simple_years, "definition": simple_definition,
              "reason": None if simple_status == "reached" else "No positive annual operating saving, or simple payback exceeds the analysis horizon."}
    cumulative_points = [-net_initial] + [row["cumulative_discounted_net_inr"] for row in rows]
    recovery = next((index for index in range(len(cumulative_points)) if min(cumulative_points[index:]) >= 0), None)
    discounted = {"status": "reached" if recovery is not None else "not_reached", "years": recovery,
                  "definition": "First time-zero/year-end point where cumulative discounted net cash flow is non-negative and stays so through the modeled horizon; includes maintenance and replacements. No fractional-year interpolation.",
                  "reason": None if recovery is not None else "No lasting discounted recovery within the modeled horizon."}
    economics = {"present_value_bill_savings_inr": pv_bill,
                 "present_value_maintenance_inr": pv_maintenance,
                 "present_value_replacements_inr": pv_replacements,
                 "present_value_net_operating_cashflow_inr": pv_bill - pv_maintenance - pv_replacements,
                 "gross_installation_cost_inr": gross, "solar_subsidy_inr": subsidy,
                 "net_initial_cost_inr": net_initial,
                 "discounted_net_benefit_inr": cumulative,
                 "simple_payback": simple, "discounted_payback": discounted}
    result.update(status="scenario_only", annual_cashflows=rows, project_economics=economics)
    result["report_value_scenario"] = _value_scenario(value_scenario, valuation_errors)
    return result


# Short alias for notebooks; one implementation for app, exports and tests.
calculate_finance = calculate_financial_scenario
