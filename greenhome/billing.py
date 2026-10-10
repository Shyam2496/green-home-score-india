"""Validate declared annual consumption without inventing missing bill values."""
from __future__ import annotations

import math

from .engine import LPG_KWH_PER_KG


def annual_bill_baseline(*, grid_kwh, cooking_fuel, lpg_kg=None, png_kwh=None,
                         months=12, fictional=False):
    """Return normalized energy and provenance, or errors and no baseline.

    Inputs are user declarations, not independently verified meter records.
    This pilot supports one cooking fuel and complete 12-month totals only.
    Unknown active-fuel consumption is distinct from an explicit zero.
    """
    errors = []
    if isinstance(months, bool) or months != 12:
        errors.append("Enter totals covering the same complete 12 months. Partial-year totals are not annualized.")
    if cooking_fuel not in ("lpg", "png", "induction"):
        errors.append("Choose LPG, PNG or induction as the single cooking fuel for this pilot.")

    def consumption(value, label):
        if value is None:
            errors.append(f"Enter {label}; unknown consumption cannot be treated as zero.")
            return None
        if isinstance(value, bool):
            errors.append(f"{label.capitalize()} must be a finite, non-negative number.")
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float("nan")
        if not math.isfinite(number) or number < 0:
            errors.append(f"{label.capitalize()} must be a finite, non-negative number.")
            return None
        return number

    grid = consumption(grid_kwh, "annual grid electricity in kWh")
    lpg = consumption(lpg_kg, "annual LPG consumption in kilograms") if cooking_fuel == "lpg" else 0.0
    png = consumption(png_kwh, "annual PNG consumption in kWh, net calorific value") if cooking_fuel == "png" else 0.0
    for fuel, raw in (("lpg", lpg_kg), ("png", png_kwh)):
        if fuel != cooking_fuel and raw is not None:
            amount = consumption(raw, f"inactive {fuel.upper()} consumption")
            if amount is not None and amount != 0:
                errors.append("Mixed cooking fuels are not supported in this pilot; select a single fuel and enter its total.")
    provenance = {
        "source": "fictional_sample" if fictional else "user_declared_annual_consumption",
        "coverage_months": months,
        "coverage_verified": False,
        "annualized": False,
        "entered_units": {"grid": "kWh", "lpg": "kg", "png": "kWh_net_calorific_value"},
        "entered_totals": {"grid_kwh": grid_kwh, "lpg_kg": lpg_kg, "png_kwh": png_kwh},
        "inactive_fuel_zero_basis": "declared_single_cooking_fuel",
        "lpg_kwh_per_kg": LPG_KWH_PER_KG,
        "end_use_allocation_measured": False,
        "note": "Fictional demonstration values." if fictional else "User-entered consumption totals; no bill documents or meters were independently checked.",
    }
    energy = None if errors else {
        "annual_grid_kwh": grid,
        "annual_lpg_kwh": lpg * LPG_KWH_PER_KG,
        "annual_png_kwh": png,
        "annual_gas_kwh": lpg * LPG_KWH_PER_KG + png,
    }
    return {"energy": energy, "provenance": provenance, "errors": errors}


def bill_savings_trace(savings, *, electricity_rate, lpg_price_kg, png_rate):
    """One signed flat-rate calculation used by both display and export."""
    def valid(value, nonnegative=False):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (not nonnegative or value >= 0)

    if not all(valid(savings.get(key)) for key in ("electricity_kwh", "lpg_kwh", "png_kwh")):
        return {"status": "unavailable", "reason": "Finite signed savings are required for all three fuels.", "terms": [], "total_inr_per_year": None}
    if not all(valid(rate, nonnegative=True) for rate in (electricity_rate, lpg_price_kg, png_rate)):
        return {"status": "unavailable", "reason": "Rates must be finite, non-negative numbers.", "terms": [], "total_inr_per_year": None}
    terms = [
        {"Fuel": "Grid electricity", "Saved units/year": savings["electricity_kwh"], "Unit": "kWh", "Rate (INR/unit)": electricity_rate},
        {"Fuel": "LPG", "Saved units/year": savings["lpg_kwh"] / LPG_KWH_PER_KG, "Unit": "kg", "Rate (INR/unit)": lpg_price_kg},
        {"Fuel": "PNG", "Saved units/year": savings["png_kwh"], "Unit": "kWh net CV", "Rate (INR/unit)": png_rate},
    ]
    for term in terms:
        term["Saving (INR/year)"] = term["Saved units/year"] * term["Rate (INR/unit)"]
    if not all(math.isfinite(term["Saving (INR/year)"]) for term in terms) or not math.isfinite(sum(term["Saving (INR/year)"] for term in terms)):
        return {"status": "unavailable", "reason": "Bill calculation exceeds the supported numeric range.", "terms": [], "total_inr_per_year": None}
    return {"status": "available", "terms": terms,
            "total_inr_per_year": sum(term["Saving (INR/year)"] for term in terms),
            "equation": "sum(signed fuel savings in billing units × flat user-entered rate)",
            "lpg_kwh_per_kg": LPG_KWH_PER_KG}
