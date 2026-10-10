"""Bills cannot silently become invented annual measurements."""
import pytest

from greenhome.billing import annual_bill_baseline, bill_savings_trace
from greenhome.engine import LPG_KWH_PER_KG


@pytest.mark.parametrize("grid,lpg", [(None, 85.2), (3000, None)])
def test_unknown_active_consumption_blocks_baseline(grid, lpg):
    result = annual_bill_baseline(grid_kwh=grid, cooking_fuel="lpg", lpg_kg=lpg)
    assert result["energy"] is None
    assert any("unknown" in error for error in result["errors"])


def test_explicit_zero_is_preserved_and_coverage_is_not_verified():
    result = annual_bill_baseline(grid_kwh=0, cooking_fuel="lpg", lpg_kg=0)
    assert not result["errors"]
    assert all(value == 0 for value in result["energy"].values())
    assert result["provenance"]["coverage_verified"] is False


@pytest.mark.parametrize("months", [1, 6, 11, None, True])
def test_partial_or_unknown_period_is_not_extrapolated(months):
    result = annual_bill_baseline(grid_kwh=2000, cooking_fuel="induction", months=months)
    assert result["energy"] is None
    assert result["provenance"]["annualized"] is False


def test_lpg_units_and_fictional_origin_survive_normalization():
    result = annual_bill_baseline(grid_kwh=3000, cooking_fuel="lpg", lpg_kg=85.2, fictional=True)
    assert result["energy"]["annual_lpg_kwh"] == pytest.approx(85.2 * LPG_KWH_PER_KG)
    assert result["energy"]["annual_png_kwh"] == 0
    assert result["provenance"]["source"] == "fictional_sample"
    assert result["provenance"]["entered_totals"]["lpg_kg"] == 85.2


def test_png_and_induction_need_no_unknown_inactive_fuel():
    png = annual_bill_baseline(grid_kwh=2500, cooking_fuel="png", png_kwh=900)
    assert png["energy"]["annual_png_kwh"] == 900
    assert png["energy"]["annual_lpg_kwh"] == 0
    induction = annual_bill_baseline(grid_kwh=2500, cooking_fuel="induction")
    assert induction["energy"]["annual_gas_kwh"] == 0


def test_mixed_fuel_is_not_silently_dropped():
    result = annual_bill_baseline(grid_kwh=2500, cooking_fuel="png", png_kwh=900, lpg_kg=14.2)
    assert result["energy"] is None
    assert any("Mixed" in error for error in result["errors"])


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), "bad", True])
def test_invalid_energy_is_withheld(value):
    assert annual_bill_baseline(grid_kwh=value, cooking_fuel="induction")["energy"] is None


def test_signed_bill_trace_reconciles_fuel_units_and_total():
    trace = bill_savings_trace({"electricity_kwh": -400, "lpg_kwh": 14.2 * LPG_KWH_PER_KG, "png_kwh": 0}, electricity_rate=8, lpg_price_kg=65, png_rate=5)
    assert trace["terms"][0]["Saving (INR/year)"] == -3200
    assert trace["terms"][1]["Saved units/year"] == pytest.approx(14.2)
    assert trace["total_inr_per_year"] == pytest.approx(-3200 + 14.2 * 65)
    assert bill_savings_trace({}, electricity_rate=8, lpg_price_kg=65, png_rate=5)["total_inr_per_year"] is None


@pytest.mark.parametrize("invalid", [None, -1, float("nan"), float("inf"), True, "8"])
def test_invalid_bill_rate_withholds_cost_without_invalid_json(invalid):
    import json
    result = bill_savings_trace({"electricity_kwh": 100, "lpg_kwh": 0, "png_kwh": 0}, electricity_rate=invalid, lpg_price_kg=65, png_rate=5)
    assert result["status"] == "unavailable"
    assert result["total_inr_per_year"] is None
    json.dumps(result, allow_nan=False)


def test_nonfinite_saving_and_overflow_do_not_escape_cost_validation():
    savings = {"electricity_kwh": float("nan"), "lpg_kwh": 0, "png_kwh": 0}
    assert bill_savings_trace(savings, electricity_rate=8, lpg_price_kg=65, png_rate=5)["status"] == "unavailable"
    savings["electricity_kwh"] = 1e308
    assert bill_savings_trace(savings, electricity_rate=8, lpg_price_kg=65, png_rate=5)["status"] == "unavailable"
