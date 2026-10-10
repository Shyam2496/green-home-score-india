"""Transparent residential end-use baseline, not a calibrated building simulator.

Weather and PV references are cached from NASA POWER and JRC PVGIS. Envelope,
usage, schedule, cooking and self-consumption assumptions remain explicit. BEE
ENS thresholds are design references, never substituted for measured savings.
"""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

from .schema import DEFAULT_HOME, NUMERIC_FEATURES, OPTIONS

INPUT_RANGES = {
    'area_m2': [35, 250], 'occupants': [1, 8], 'solar_kw': [0, 8],
    'ac_units': [0, 5], 'ac_hours_per_day': [0, 16], 'led_fraction': [0, 1],
    'ac_capacity_ton': [.75, 2.5], 'ac_iseer': [2.5, 6.5], 'setpoint_c': [22, 30],
    'roof_u_value': [.2, 4], 'roof_exposed_fraction': [0, 1],
    'wall_u_value': [.3, 3.5], 'window_to_wall_ratio': [.1, .5],
    'window_shgc': [.2, .9], 'window_shading_fraction': [0, .9],
    'fan_count': [0, 10], 'fan_power_w': [20, 90], 'fan_hours_per_day': [0, 24],
    'lighting_hours_per_day': [1, 12], 'hot_water_litres_per_person_day': [0, 50],
    'appliance_kwh_per_day': [.5, 12], 'solar_self_consumption_fraction': [0, 1],
}
# Kept for legacy imports only. V2 calculates heat flows from U-values/SHGC.
FABRIC_FACTOR = {'poor': 1.18, 'average': 1.0, 'good': .82}
GLAZING_FACTOR = {'single': 1.0, 'double': .90}
ROOF_U_DEFAULTS = {'poor': 3.0, 'average': 1.2, 'good': .6}
WALL_U_DEFAULTS = {'poor': 2.2, 'average': 1.6, 'good': .8}
MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
REFERENCE_YEAR_DAYS = sum(MONTH_DAYS)


def complete_home(home: dict[str, Any]) -> dict[str, Any]:
    """Fill disclosed engineering defaults, preserving explicit values/extras."""
    result = {**DEFAULT_HOME, **home}
    area = float(result['area_m2'])
    occ = float(result['occupants'])
    defaults = {
        'ac_capacity_ton': 1.5,
        'ac_iseer': 5.2 if result['cooling'] == 'ac_efficient' else 3.2,
        'setpoint_c': 26.0,
        'roof_u_value': ROOF_U_DEFAULTS.get(result['insulation'], 3.0),
        'wall_u_value': WALL_U_DEFAULTS.get(result['insulation'], 2.2),
        'roof_exposed_fraction': {'independent': 1.0, 'row_house': .65, 'apartment': .15}.get(result['property_type'], 1.0),
        'window_to_wall_ratio': .2,
        'window_shgc': .4 if result['glazing'] == 'double' else .75,
        'window_shading_fraction': .25,
        'fan_count': max(1, math.ceil(area / 30)), 'fan_power_w': 55.0,
        'fan_hours_per_day': 10.0 if result['cooling'] == 'fans_only' else 6.0,
        'lighting_hours_per_day': 5.0, 'hot_water_litres_per_person_day': 20.0,
        'appliance_kwh_per_day': 1.6 + .35 * occ + .008 * area,
        'solar_self_consumption_fraction': .65,
    }
    for field, value in defaults.items():
        if field not in result:
            result[field] = value
    # Validation accepts numeric strings from CSV/forms. Normalize them here so
    # every public helper uses the same values after that validation succeeds.
    for field in INPUT_RANGES:
        value = result.get(field)
        if value is not None and not isinstance(value, bool):
            try:
                result[field] = float(value)
            except (TypeError, ValueError):
                pass  # validate_home reports invalid values without hiding them.
    return result


def input_assumptions(home: dict[str, Any]) -> dict[str, Any]:
    """List which feature values were assumed rather than supplied by the user."""
    full = complete_home(home)
    return {key: full[key] for key in NUMERIC_FEATURES + list(OPTIONS) + ['solar_kw', 'solar_self_consumption_fraction'] if key not in home}


def validate_home(home: dict[str, Any]) -> list[str]:
    errors = []
    try:
        full = complete_home(home)
    except (TypeError, ValueError, OverflowError):
        return ['Area and occupants must be finite numbers.']
    for field, (low, high) in INPUT_RANGES.items():
        value = full.get(field)
        if isinstance(value, bool):
            errors.append(f'{field} must be a number, not a boolean.')
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f'{field} must be numeric.')
            continue
        if not math.isfinite(number) or not low <= number <= high:
            errors.append(f'{field} must be between {low} and {high}.')
        if field in ('occupants', 'ac_units', 'fan_count') and math.isfinite(number) and not number.is_integer():
            errors.append(f'{field} must be a whole number.')
    for field, values in OPTIONS.items():
        value = full.get(field)
        if value not in values or (field == 'smart_controls' and not isinstance(value, bool)):
            errors.append(f'{field} must be one of {values}.')
    if full.get('cooling') == 'fans_only' and (full.get('ac_units') != 0 or full.get('ac_hours_per_day') != 0):
        errors.append('Fans-only homes must have zero AC units and AC hours.')
    return errors


@lru_cache(maxsize=1)
def climate_reference() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / 'data' / 'climate_reference.json'
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _at_setpoint(values: dict[str, list[float]], setpoint: float) -> list[float]:
    lower, upper = math.floor(setpoint), math.ceil(setpoint)
    weight = setpoint - lower
    return [(1 - weight) * a + weight * b for a, b in zip(values[str(lower)], values[str(upper)])]


def climate_parameters(home: dict[str, Any]) -> dict[str, float]:
    full = complete_home(home)
    city = climate_reference()['cities'][full['city']]
    return {
        'cooling_degree_hours': sum(_at_setpoint(city['monthly_cooling_degree_hours'], float(full['setpoint_c']))),
        'annual_ghi_kwh_m2': sum(v * days for v, days in zip(city['monthly_ghi_kwh_m2_day'], MONTH_DAYS)),
        'pv_yield_kwh_per_kw_year': float(city['pv_yield_kwh_per_kw_year']),
    }


def electricity_balance(home: dict[str, Any], demand_kwh: float) -> dict[str, float]:
    errors = validate_home(home)
    if errors:
        raise ValueError('; '.join(errors))
    full = complete_home(home)
    demand = float(demand_kwh)
    if not math.isfinite(demand) or demand < 0:
        raise ValueError('Electricity demand must be a finite nonnegative kWh/year value.')
    yield_kwh = climate_parameters(full)['pv_yield_kwh_per_kw_year']
    generation = float(full['solar_kw']) * yield_kwh
    # Annual matching is a scenario assumption. Hourly load/PV matching would be
    # needed for a defensible export/self-consumption estimate for a real house.
    self_use = min(generation * float(full['solar_self_consumption_fraction']), demand * .75)
    return {
        'annual_grid_kwh': demand - self_use,
        'annual_solar_generation_kwh': generation,
        'annual_solar_self_consumed_kwh': self_use,
        'annual_solar_export_kwh': generation - self_use,
    }


def demand_from_grid(home: dict[str, Any], grid_kwh: float) -> float:
    """Invert the same piecewise annual solar balance for meter-only inputs."""
    errors = validate_home(home)
    if errors:
        raise ValueError('; '.join(errors))
    full = complete_home(home)
    grid = float(grid_kwh)
    if not math.isfinite(grid) or grid < 0:
        raise ValueError('Grid import must be finite and nonnegative.')
    cap = float(full['solar_kw']) * climate_parameters(full)['pv_yield_kwh_per_kw_year'] * float(full['solar_self_consumption_fraction'])
    return min(4 * grid, grid + cap)


def expected_end_uses(home: dict[str, Any]) -> dict[str, float]:
    errors = validate_home(home)
    if errors:
        raise ValueError('; '.join(errors))
    h = complete_home(home)
    city = climate_reference()['cities'][h['city']]
    area, occ = float(h['area_m2']), int(h['occupants'])
    active_days = _at_setpoint(city['monthly_cooling_days'], float(h['setpoint_c']))
    degree_hours = _at_setpoint(city['monthly_cooling_degree_hours'], float(h['setpoint_c']))
    hours = float(h['ac_hours_per_day'])
    conditioned_fraction = min(1.0, float(h['ac_units']) * 18.0 / area)
    wall_exposure = {'independent': 1.0, 'row_house': .65, 'apartment': .4}[h['property_type']]
    facade_area = 4 * math.sqrt(area) * 2.8 * wall_exposure
    window_area = facade_area * float(h['window_to_wall_ratio'])
    window_u = 2.8 if h['glazing'] == 'double' else 5.7
    ua = ((facade_area - window_area) * float(h['wall_u_value'])
          + window_area * window_u + area * float(h['roof_exposed_fraction']) * float(h['roof_u_value'])
          + .33 * .5 * area * 2.8) * conditioned_fraction
    cooling = 0.0
    unmet_cooling = 0.0
    capacity_limited_months = 0
    if h['cooling'] != 'fans_only' and h['ac_units'] > 0 and hours > 0:
        for i, days in enumerate(MONTH_DAYS):
            runtime = hours * active_days[i]
            conduction = ua * degree_hours[i] * hours / 24 / 1000
            irradiation = float(city['monthly_ghi_kwh_m2_day'][i]) * active_days[i]
            # Vertical irradiance=.35*GHI; roof absorptance=.6 and external heat
            # transfer=20 W/m²K are exposed modeling assumptions, not BEE factors.
            window_gain = irradiation * .35 * window_area * float(h['window_shgc']) * (1 - float(h['window_shading_fraction']))
            roof_gain = irradiation * .6 / 20 * float(h['roof_u_value']) * area * float(h['roof_exposed_fraction'])
            solar_gain = (window_gain + roof_gain) * conditioned_fraction * min(hours / 12, 1)
            internal_gain = .08 * occ * conditioned_fraction * runtime
            thermal = (conduction + solar_gain + internal_gain) * (.92 if h['smart_controls'] else 1)
            capacity_limit = float(h['ac_units']) * float(h['ac_capacity_ton']) * 3.517 * runtime
            unmet_cooling += max(0.0, thermal - capacity_limit)
            capacity_limited_months += int(thermal > capacity_limit + 1e-8)
            cooling += min(thermal, capacity_limit) / float(h['ac_iseer'])
    fan_days = min(REFERENCE_YEAR_DAYS, max(180.0, sum(active_days) + 30))
    fans = float(h['fan_count']) * float(h['fan_power_w']) / 1000 * float(h['fan_hours_per_day']) * fan_days
    lighting = area * .008 * float(h['lighting_hours_per_day']) * REFERENCE_YEAR_DAYS * (1 - .70 * float(h['led_fraction']))
    other = float(h['appliance_kwh_per_day']) * REFERENCE_YEAR_DAYS
    useful_water = sum(occ * float(h['hot_water_litres_per_person_day']) * 4.186 / 3600
                       * max(0.0, 45 - min(30, max(10, float(temp) - 3))) * days
                       for temp, days in zip(city['monthly_temperature_c'], MONTH_DAYS))
    water = {'electric_geyser': useful_water / .90, 'solar_heater': .30 * useful_water / .90,
             'heat_pump': useful_water / 2.5, 'none': 0.0}[h['hot_water']]
    cooking_useful = 190.0 * occ  # Annual useful cooking heat assumption.
    lpg = cooking_useful / .55 if h['cooking_fuel'] == 'lpg' else 0.0
    png = cooking_useful / .50 if h['cooking_fuel'] == 'png' else 0.0
    electric_cooking = cooking_useful / .84 if h['cooking_fuel'] == 'induction' else 0.0
    demand = cooling + fans + lighting + other + water + electric_cooking
    balance = electricity_balance(h, demand)
    return {
        'cooling_kwh': cooling, 'fans_kwh': fans, 'lighting_kwh': lighting,
        'other_kwh': other, 'hot_water_kwh': water, 'cooking_electric_kwh': electric_cooking,
        'cooking_gas_kwh': lpg + png, 'gross_electric_kwh': demand,
        'solar_self_kwh': balance['annual_solar_self_consumed_kwh'],
        'annual_electricity_demand_kwh': demand, 'annual_lpg_kwh': lpg,
        'annual_png_kwh': png, 'annual_gas_kwh': lpg + png,
        'annual_unmet_cooling_kwh_thermal': unmet_cooling,
        'capacity_limited_months': float(capacity_limited_months),
        **balance,
    }
