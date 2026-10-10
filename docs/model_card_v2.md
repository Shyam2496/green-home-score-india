# India Green Home energy model v2

This is a Hyderabad residential hackathon pilot, with exploratory configurations for seven other Indian cities. It is a working engineering and machine-learning prototype. Its household training labels are synthetic. It is not a validated predictor of real household bills, a BEE certification, or a causal model of retrofit savings.

## What improved

The original model used 3,000 independent synthetic homes, coarse cooling-season constants and two purchased-energy targets. V2 uses 12,000 correlated synthetic homes in 3,000 building/archetype groups, a stronger physical comparator, explicit solar conservation, and independent calibration groups. The experiments have different targets, distributions and noise, so their headline errors are not directly comparable.

Three targets are predicted separately, in kWh/year:

- Electricity consumed by the dwelling before rooftop solar.
- LPG input energy on a net calorific basis.
- PNG input energy on a net calorific basis.

Solar generation, self-consumption, exports and grid imports are calculated separately. Installing PV does not change predicted household demand. The compatibility field `annual_gas_kwh` is LPG plus PNG; it is never counted in addition to those fuels.

## Inputs and references

There are 28 input features: 20 numerical and eight categorical. The added details include AC capacity, label ISEER, set temperature, roof and wall U-values, exposed roof fraction, glazing/SHGC/shading, fan power/use, lighting hours, heated-water volume and other appliance demand. Unknown details use visible engineering defaults; users can enter known values in the dashboard.

Six engineered features add input-derived weather and physical end-use estimates. No household IDs, building IDs, reference label columns, target columns or post-solar imports enter the predictor. The physical features use the same equations that generate synthetic labels; that advantage is disclosed rather than treated as independent proof of accuracy.

Sources are recorded with exact API URLs, units, reference periods, quality checks and system assumptions in `data/climate_reference.json`:

- [NASA POWER](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/) supplies 2024 hourly gridded temperature and irradiation for eight representative city points. Each point has 8,784 valid hours and no missing temperature or irradiation hours. This is one weather year, not a climate normal or household observation.
- [JRC PVGIS](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en) supplies ERA5 2005–2023 modeled PV yield. The reference system is 1 kWp crystalline silicon, free-standing, 20° tilt, south-facing, with 14% user system losses. Hyderabad yield is 1,504.6 kWh/kWp/year. Actual roofs and shading can differ.
- [BEE Eco-Niwas Samhita 2024](https://beeindia.gov.in/WriteReadData/RTF1984/1772175926.pdf), Table 62, identifies Hyderabad as Composite. Its roof U-value limit of 1.2 W/m²K is a design reference. It is not a measured savings coefficient or the basis of an official rating in this app.

## Selection, splits and uncertainty

Seed 42 assigns building groups to training, validation, calibration and test in approximately 50/15/15/20 proportions. The bundled run has 6,000/1,800/1,800/2,400 rows and 1,500/450/450/600 groups. No group crosses a partition. Test group IDs remain frozen for an identical dataset fingerprint.

The training mean, physical baseline, Random Forest, Extra Trees, histogram gradient boosting and relative residual boosting compete on validation MAE. The mean candidate and other predictors apply the same known inactive-fuel zero rule. An unconditional mean is also reported. Training data alone fits preprocessing and estimators; calibration and test data never select a candidate. Selected and best learned alternatives are saved.

The physical baseline won all three targets in the bundled experiment. This is expected because it is the synthetic generator's conditional mean. The learned alternatives remain useful experiments, not grounds to claim a superior real-world model.

Relative split-conformal intervals target 90% marginal coverage. Calibration takes one label-independent representative per building group and uses the exact finite-sample order statistic of `abs(actual-prediction)/max(prediction,100)`. At least nine independent active calibration examples are required for a finite 90% interval. Structurally absent fuels have zero-width intervals. Exchangeability assumptions are required; subgroup, individual-house, drift and real-house coverage are not guaranteed.

The reports include MAE, RMSE, R², WAPE, active-fuel errors, interval widths and coverage, subgroup results, physical-direction checks and stress tests. Sparse fuel groups must be read separately from overall errors dominated by structural zeros. Stress-test truth comes from assumed physical rules or an explicit usage shift, not measured retrofit outcomes.

## External Hyderabad check

The [RESIDE-AC dataset](https://doi.org/10.6084/m9.figshare.16869439.v3) supplies real annual electricity bill labels for 11 anonymous Hyderabad homes under CC0. Only city, area, occupants, property type and AC count were safely mapped. Annual runtime, fabric, solar and other required inputs are missing. The bill year is unknown; monitored AC timestamps/paper indicate May 2019 while the repository description says May 2021.

These eleven labels were not used to train, select, calibrate or tune the model. The frozen, default-filled check has approximately **2,350 kWh/year MAE**, against mean observed imports of 2,573 kWh/year. It overpredicts every home and its synthetic intervals cover none of the eleven observations. These are poor results. Missing inputs and mismatched periods limit interpretation, but do not justify claiming real-house accuracy.

Use actual annual electricity and fuel bills to anchor retrofit scenarios. Those scenarios still depend on assumed end-use allocation and physical retrofit effects. The external result is preserved in `reports/external_audit.json` and the per-home prediction CSV. See `docs/external_data_audit.md` for source and mapping details.

## Physical and deployment limits

The model approximates an annual cooling schedule from all-hour cooling degree hours. ISEER is a seasonal rating rather than an hourly COP. Geometry, infiltration, solar heat transfer, cooking service and efficiency, hot-water delivery and annual PV matching contain explicit assumptions. Capacity-limited cooling is flagged; constant comfort is not established when capacity is insufficient. Humidity/latent cooling, space heating, hourly PV/load matching, appliance diversity and rebound are omitted.

Seven other cities have sourced weather and PV inputs, but these inputs do not establish local accuracy. Electricity-intensity score bounds remain illustrative, rather than validated city-specific benchmarks. Operational carbon uses separate fuel factors and an explicitly dated CEA proxy; it is CO₂, not complete lifecycle CO₂e. Property-value uplift and real tariff slabs remain outside this model improvement.

## Reproduce and replace synthetic labels

Run `python train.py --rows 12000 --seed 42`, then `python evaluate_external.py` and `python -m pytest -q`. All references required for offline prediction are cached. Joblib artifacts must be trusted before loading.

Measured training accepts `--data-csv` and `--provenance-json`. Supply unique anonymous row IDs, shared household/building group IDs, all observed model features and explicit full-year demand/LPG/PNG labels. The template is `data/measured_data_template.csv`. Grid imports must not be relabeled as total demand. Provenance must state source, licence, units, geography, full measurement dates and all target definitions. Declarations require independent audit; a manifest alone does not prove measurement quality.

Before real deployment, collect representative complete inputs and annual meters, keep a new independent geographic/temporal test set, calibrate on measured data, audit subgroup performance and validate retrofit outcomes against observed before/after consumption.

The original V2 model release on 10 October 2026 passed **129 tests**. Later application and recommendation updates keep the frozen model experiment unchanged; their current full-suite result is in `reports/verification.txt`. The dashboard and model evidence views were inspected. Dataset, model-source and external-audit fingerprints are checked when packaging; results are saved in `reports/artifact_checks.json`. See `docs/recommendation_system.md` for the added decision layer and its limitations.
