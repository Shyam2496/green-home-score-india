# Model and calculation methodology — v2

This is an India residential pilot, with Hyderabad as its primary demonstration and eight supported city reference points. Sourced weather/PV references, a transparent end-use calculation, regression candidates and assumed retrofit scenarios have distinct roles. This is not a calibrated building simulator, BEE certification, national household predictor or property appraisal.

## Prediction and accounting targets

Modeled targets are annual **gross electricity demand**, LPG energy and piped natural gas (PNG) energy, in kWh/year: `annual_electricity_demand_kwh`, `annual_lpg_kwh`, `annual_png_kwh`. Installed solar is excluded from regression features. It changes imports/exports analytically after demand prediction, so more PV cannot silently change predicted appliance demand.

`annual_grid_kwh` is purchased electricity. `annual_gas_kwh` is the compatibility sum of LPG + PNG; never count that aggregate again alongside its constituents. One declared cooking fuel is supported. Missing fuel labels in measured data do not mean zero use.

Bundled training labels remain **synthetic**, with generating rules in `reports/data_generation.md`. The frozen 11-home RESIDE-AC audit is separate from training and has incomplete features: it supports an assumption-dependent sanity check, not real-data accuracy claims. See `docs/model_card_v2.md` and `docs/external_data_audit.md`.

## Inputs and units

`greenhome/schema.py` defines features/categories; `greenhome/physics.py` defines ranges and disclosed defaults.

| Numeric field | Unit / supported range |
|---|---|
| area_m2 | Floor area, 35–250 m² |
| occupants | Integer 1–8 |
| ac_units; ac_hours_per_day | Integer 0–5 units; 0–16 hours/day |
| led_fraction | 0–1 share of lighting |
| ac_capacity_ton; ac_iseer; setpoint_c | 0.75–2.5 refrigeration tons per AC; ISEER 2.5–6.5; 22–30 °C |
| roof_u_value; wall_u_value | 0.2–4 and 0.3–3.5 W/m²K |
| roof_exposed_fraction | 0–1 |
| window_to_wall_ratio | 0.1–0.5 |
| window_shgc; window_shading_fraction | 0.2–0.9 SHGC; 0–0.9 shading fraction |
| fan_count; fan_power_w; fan_hours_per_day | Integer 0–10; 20–90 W; 0–24 hours/day |
| lighting_hours_per_day | 1–12 hours/day |
| hot_water_litres_per_person_day | 0–50 litres/person/day |
| appliance_kwh_per_day | 0.5–12 kWh/day |
| solar_kw | 0–8 kWp; accounting input, excluded from regression features |
| solar_self_consumption_fraction | 0–1 annual matching assumption; excluded from regression features |

Categories: insulation poor/average/good; cooling fans_only/ac_standard/ac_efficient; glazing single/double; property independent/row_house/apartment; city Hyderabad/Delhi/Mumbai/Bengaluru/Chennai/Kolkata/Jaipur/Pune; Boolean smart controls; hot water electric_geyser/solar_heater/heat_pump/none; cooking lpg/png/induction.

Fan-only homes require zero AC units/hours. Installed but unused AC baselines can have zero use. Counts must be integers, numbers finite and categories supported. Public convenience completion fills missing values with declared defaults; `input_assumptions` lists assumptions. Explicit invalid inputs are rejected. A measured-data training adapter must require observed fields, rather than relabel convenience defaults as measurements.

Feasibility fields (roof_access, external_space, electric_connection, heritage_restricted, retrofit_consent) are separate from prediction features. Unknown constraints block affected installations. Property-value impact is deferred; no property value is a trained valuation label in this prototype.

The new decision API and dashboard additionally require affirmative preliminary PV site checks and at least 30 m² usable roof area for the fixed 3 kW option. Actual permissions start unconfirmed; fictional demonstration site values are explicitly separate. These are user declarations, not certified findings. See `docs/recommendation_system.md` for the sourced area screen, API and complete-system status.

## Sourced references and their limits

`data/climate_reference.json` caches URLs, coordinates, periods, derivations and quality metadata for each city; inference works without a live weather request.

- **NASA POWER:** hourly grid/model-derived temperature and solar radiation for 2024 using UTC days. Monthly means, GHI, cooling days and cooling-degree hours above 22–30 °C are derived; fractional setpoints interpolate thresholds. This leap year has **366 days**, and is not a climate normal, typical year or measured home weather.
- **JRC PVGIS 5.3:** location-specific annual PV yield using PVGIS-ERA5 2005–2023, crystalline silicon, 1 kWp, 20° south-facing fixed tilt, free-standing mounting and 14% user loss. This is gross generation, not household self-consumption. Its period differs from the weather year; actual roof shading/geometry can differ.
- **BEE Eco-Niwas Samhita 2024:** climate-zone reference (Table 62), roof U-value design threshold 1.2 W/m²K (section 5.2.1.3), and ISEER definition. These are design references, not measured U-values or retrofit-savings coefficients. RETV excludes the roof and is not calculated here.

Sources: [NASA POWER hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/), [JRC PVGIS API](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en), [BEE ENS 2024](https://beeindia.gov.in/WriteReadData/RTF1984/1772175926.pdf). MNRE's calculator landing page was inspected; no numeric MNRE benchmark is claimed.

## Physical baseline

The shared model estimates cooling, fans, lighting, other appliances, hot water and cooking before solar. Paired retrofit scenarios hold comfort, occupancy, weather and use constant.

Cooling uses envelope UA, exposed areas, monthly cooling-degree hours, approximate schedules, solar/internal gains, AC capacity and ISEER. Degree hours are scaled by AC hours/24, not measured time-of-day use. Assumptions include room height 2.8 m, 0.5 air changes/hour, vertical irradiance 0.35 × GHI, roof absorptance 0.6 and external heat transfer 20 W/m²K. Cooling is capacity-limited and divided by ISEER as a seasonal-efficiency proxy. Unmet thermal load and capacity-limited months are diagnostics; constant comfort cannot be assumed in those cases. Humidity/latent loads, thermal dynamics, space heating and actual compressor controls are not modeled. Non-Hyderabad configurations are exploratory, especially for warm-humid conditions and cold seasons.

Default roof U-values poor/average/good are 3.0/1.2/0.6; wall defaults 2.2/1.6/0.8 W/m²K. These are assumptions, not measured or universally prescribed Indian values. `physics.complete_home` also exposes fan power/use, lighting, appliance and hot-water defaults.

Useful cooking heat is assumed 190 kWh/person/year. LPG stove efficiency is 0.55, PNG 0.50 and induction 0.84. Hot-water demand uses litres, specific heat, a 45 °C target and a bounded outdoor-temperature-derived inlet proxy; geyser efficiency 0.90, heat-pump COP 2.5 and solar backup share 0.30 are assumptions.

The physical baseline is eligible for validation selection and may beat learned candidates on labels generated from those same rules. It is not merely a weak mean comparator.

## Solar, savings and interactions

For gross demand D, location yield Y, installed kWp P and explicit annual self-consumption fraction f: generation G = P × Y; self-use S = min(f × G, 0.75 × D); imports I = D − S; exports X = G − S. Therefore D = I + S and G = S + X. Exports remain visible but receive no energy/bill/carbon credit.

Meter-only inputs invert the same balance: D = min(4 × I, I + f × G). This reconstructs demand under an assumption, not a behind-the-meter measurement. Supplied demand/imports must agree with the same balance.

Per-fuel saving = baseline − after. A negative saving means increased use. Purchased energy = grid imports + LPG + PNG, counted once. Improvement potential = 100 × total saving / baseline purchased energy; unavailable for zero/missing baseline.

Standalone recommendations share the original baseline. Packages rerun in roof insulation → glazing → LED → efficient AC → controls → solar hot water → induction → PV order. New/old physical end-use ratios preserve anchored baseline totals and interactions. Selected marginal steps telescope to package totals; do not sum standalone savings.

The decision layer ranks standalone benefits for an explicit bill, purchased-energy or operational CO₂ objective. It then chooses the greatest positive whole-package increment after rerunning each candidate addition. This greedy decision order is separate from physical installation order. The final package, candidate rankings, decision increments and installation-order marginals are exported separately. The downstream financial calculator evaluates entered quotes and payback for the selected package; cost and budget do not enter the recommendation objective, and a globally optimal investment package is not inferred.

## Annual-consumption inputs and calculation traces

The dashboard starts in annual-consumption mode with blank electricity and active cooking-fuel fields. The user declares totals spanning the same complete 12 months. The application does not verify invoice coverage; it records this limit in `baseline_provenance`. Partial-year entries are not extrapolated, and missing active-fuel use is not converted to zero. Inactive fuels are zero only under the explicitly declared single-cooking-fuel scope. Mixed cooking fuels are unsupported. LPG is entered as kilograms consumed, not a cylinder count; refill purchases approximate use only if stored stock is unchanged. PNG requires supplier-specific net-calorific energy units; no universal volume conversion is assumed.

An explicit fictional sample mode and a separate model-demonstration mode remain available. Their origins travel in the download. Annual consumption mode does not load or require a fitted predictor. Its input totals anchor the engineering scenario directly; this improves relevance of the starting total without validating end-use allocation or causal savings. Bill rupee amounts are not consumption labels.

Without existing PV, gross annual demand equals entered grid imports. With existing PV, gross demand is inferred by the annual matching rule above. Under the 75% cap, zero imports imply zero inferred demand, so genuine zero-import solar homes cannot be represented reliably. Measured behind-the-meter flows and hourly matching are not available in this form.

`evaluate_scenario` returns `calculation_trace` schema 1.0 with exact supplied/normalized energy, baseline energy, nominal and anchored end-use allocation, scale factor, assumed inputs and PV assumptions. Each recommendation contains `standalone_trace`, `selected_marginal_trace` and `recommended_marginal_trace`; `selected_steps` records the package chain. Traces retain the exact states that the scenario engine evaluated, rather than a second savings algorithm. Each available step contains physical input changes, numerical end-use ratios, useful-heat fuel conversion when relevant, before/after energy, signed per-fuel savings, the percentage denominator, carbon factors and signed carbon terms. Unselected or unavailable comparisons have explicit status; undefined ratios use JSON null.

Marginal percentages use the immediately preceding state's purchased energy as denominator. These percentages must not be added. Signed kWh and CO₂ marginal savings telescope to final package totals. The dashboard presents individual traces and the download retains every recommendation and package step. It also records per-fuel bill units, rates, contributions and their sum using the same calculation as the headline. No synthetic prediction interval is transferred to bill totals, inferred appliance shares or retrofit savings.

Roof insulation reduces roof U to at most 0.6, preserving wall U. Double glazing uses U=2.8 and SHGC no greater than 0.4, preserving shading. AC upgrade targets ISEER≥5.2 with hours, capacity and setpoint fixed. Solar water heating is limited to existing electric-geyser service. Induction adds displaced LPG ×0.55/0.84 or PNG ×0.50/0.84 electricity. Electricity and CO₂ can rise despite lower purchased energy. Site suitability and consent remain necessary.

## Green Home Score

The brief's weights are preserved with explicit India adaptations; the total is the weighted sum of 0–100 sub-scores.

| Component | Weight | Sub-score |
|---|---:|---|
| Appliance efficiency | 25% | 0.6 × cooling score + 0.4 × (100 × LED fraction) |
| Electricity demand intensity | 20% | clip(100 × (225 − gross electricity demand kWh/m²) / 200, 0, 100); unaffected by PV |
| Insulation | 15% | Weighted roof/wall U-value scores described below |
| Cooling and hot water | 15% | 0.6 × cooling score + 0.4 × hot-water score |
| Glazing | 10% | 0.35 × window-U score + 0.50 × SHGC score + 0.15 × shading score |
| Renewables | 10% | max(min(solar kWp/3, 1) ×100, 60 if solar hot water, else 0) |
| Smart management | 5% | absent 0; present 100 |

All clips below bound each sub-score to 0–100. Cooling score is 100 for fans only; otherwise clip(100 × (ISEER − 2.5) / 4), an illustrative range rather than BEE star bands. Water scores: geyser 35, solar 95, heat pump 85, none 100.

Roof score = clip(100 × (3 − roof U) / 2.4); wall score = clip(100 × (2.2 − wall U) / 1.4). Roof weight within this component is 0.6 × exposed roof fraction and wall weight is the remainder. Window-U score = clip(100 × (5.7 − window U) / 2.9), with U=5.7 single or 2.8 double. SHGC score = clip(100 × (0.75 − SHGC) / 0.35). Shading score = clip(100 × shading fraction / 0.75).

Intensity and engineering mappings are custom, unvalidated score assumptions, not an Indian climate peer benchmark or BEE certification. Gross-demand intensity avoids giving PV a second credit within the efficiency component; purchased-energy intensity is reported separately. Zero/missing baseline makes intensity unavailable; missing components do not renormalize weights. Unrounded classification: ≥80 Highly efficient; ≥65 Good; ≥50 Moderate; ≥30 Poor; otherwise Very poor.

## Carbon, bills and property value

Operational CO₂ reduction = electricity saving × electricity factor + LPG saving × LPG factor + PNG saving × PNG factor. This is **CO₂, not full CO₂e**; other greenhouse gases, upstream supply, T&D, embodied impacts and exports are excluded.

| Factor | Default / net-calorific basis | Source |
|---|---|---|
| Grid | 0.716 kg CO₂/kWh; dated FY2022–23 national generation proxy | [CEA v19 Annexure I](https://cea.nic.in/wp-content/uploads/baseline/2024/01/User_Guide__Version_19.0.pdf) |
| LPG | 63,100 kg CO₂/TJ ×0.0000036 = 0.22716 kg CO₂/kWh | [IPCC 2006 Vol2 Ch2 Table2.5](https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_2_Ch2_Stationary_Combustion.pdf) |
| PNG | 56,100 kg CO₂/TJ ×0.0000036 = 0.20196 kg CO₂/kWh; actual composition can differ | [IPCC 2006 Vol2 Ch2 Table2.5](https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_2_Ch2_Stationary_Combustion.pdf) |
| LPG conversion | 47.3 MJ/kg ÷3.6 = 13.139 kWh/kg; 14.2 kg ≈186.57 kWh | [IPCC Vol2 Ch1 Table1.2](https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/2_Volume2/V2_1_Ch1_Introduction.pdf) |

The grid factor is a disclosed dated proxy, not a current local DISCOM/marginal factor. Overrides carry assumption flags. The brief's full CO₂e boundary remains a limitation.

Bills use the app's tariff assumptions, not a verified DISCOM slab/subsidy schedule. The financial module projects those signed bill savings with explicit timing, costs and maintenance/replacement assumptions. Property-value impact is deferred because verified local transactions linked to known retrofits and comparable-property controls are missing. The dashboard omits property-premium controls; financial NPV is not converted into resale appreciation. See `docs/financial_module.md` and `docs/property_value_scope.md`.
