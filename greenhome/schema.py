"""India residential pilot schema. Demand and solar are accounted for separately."""
NUMERIC_FEATURES = [
    'area_m2', 'occupants', 'ac_units', 'ac_hours_per_day', 'led_fraction',
    'ac_capacity_ton', 'ac_iseer', 'setpoint_c', 'roof_u_value',
    'roof_exposed_fraction', 'wall_u_value', 'window_to_wall_ratio',
    'window_shgc', 'window_shading_fraction', 'fan_count', 'fan_power_w',
    'fan_hours_per_day', 'lighting_hours_per_day',
    'hot_water_litres_per_person_day', 'appliance_kwh_per_day',
]
CATEGORICAL_FEATURES = ['insulation', 'cooling', 'glazing', 'property_type', 'city', 'smart_controls', 'hot_water', 'cooking_fuel']
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGETS = ['annual_electricity_demand_kwh', 'annual_lpg_kwh', 'annual_png_kwh']
OPTIONS = {
    'insulation': ['poor', 'average', 'good'],
    'cooling': ['fans_only', 'ac_standard', 'ac_efficient'],
    'glazing': ['single', 'double'],
    'property_type': ['independent', 'row_house', 'apartment'],
    'city': ['Hyderabad', 'Delhi', 'Mumbai', 'Bengaluru', 'Chennai', 'Kolkata', 'Jaipur', 'Pune'],
    'smart_controls': [False, True],
    'hot_water': ['electric_geyser', 'solar_heater', 'heat_pump', 'none'],
    'cooking_fuel': ['lpg', 'png', 'induction'],
}
# Advanced engineering defaults are completed in physics.py; changing a basic
# selection then changes its associated default without silently fixing it here.
DEFAULT_HOME = {
    'area_m2': 95.0, 'occupants': 3, 'solar_kw': 0.0,
    'ac_units': 2, 'ac_hours_per_day': 6.0, 'led_fraction': 0.5,
    'insulation': 'poor', 'cooling': 'ac_standard',
    'glazing': 'single', 'property_type': 'independent', 'city': 'Hyderabad',
    'smart_controls': False, 'hot_water': 'electric_geyser', 'cooking_fuel': 'lpg',
    'roof_access': True, 'external_space': True, 'electric_connection': True,
    'heritage_restricted': False, 'retrofit_consent': True,
    'current_value_inr': 7500000.0,
}
