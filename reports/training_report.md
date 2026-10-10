# India-first model evaluation v2

Data: **synthetic_india_physics_v2**, 12,000 rows. Group-disjoint row counts: {'train': 6000, 'validation': 1800, 'calibration': 1800, 'test': 2400}; group counts: {'train': 1500, 'validation': 450, 'calibration': 450, 'test': 600}. Assignments and dataset SHA-256 are saved. Test groups stay frozen for an identical dataset.

## Validation comparison

|Target|Candidate|MAE kWh/year|RMSE kWh/year|R²|
|---|---|---:|---:|---:|
|annual_electricity_demand_kwh|mean_baseline|1099.0|1429.7|-0.005|
|annual_electricity_demand_kwh|physics_baseline|397.6|522.3|0.866|
|annual_electricity_demand_kwh|random_forest|408.5|544.3|0.854|
|annual_electricity_demand_kwh|extra_trees|408.8|542.9|0.855|
|annual_electricity_demand_kwh|hist_gradient_boosting|406.9|558.9|0.846|
|annual_electricity_demand_kwh|residual_hist_gradient_boosting|402.1|529.0|0.862|
|annual_electricity_demand_kwh|unconditional_mean_comparator|1099.0|1429.7|-0.005|
|annual_lpg_kwh|mean_baseline|399.0|610.7|0.393|
|annual_lpg_kwh|physics_baseline|107.9|172.9|0.951|
|annual_lpg_kwh|random_forest|111.6|178.9|0.948|
|annual_lpg_kwh|extra_trees|112.5|180.4|0.947|
|annual_lpg_kwh|hist_gradient_boosting|111.2|177.9|0.948|
|annual_lpg_kwh|residual_hist_gradient_boosting|109.8|176.5|0.949|
|annual_lpg_kwh|unconditional_mean_comparator|652.6|784.0|-0.000|
|annual_png_kwh|mean_baseline|150.7|498.0|0.095|
|annual_png_kwh|physics_baseline|18.6|73.0|0.981|
|annual_png_kwh|random_forest|19.3|77.2|0.978|
|annual_png_kwh|extra_trees|21.1|85.0|0.974|
|annual_png_kwh|hist_gradient_boosting|19.9|80.0|0.977|
|annual_png_kwh|residual_hist_gradient_boosting|18.6|74.8|0.980|
|annual_png_kwh|unconditional_mean_comparator|302.2|523.5|-0.000|

Candidates/preprocessing fit training only; validation MAE selects physics or the learned candidate. Calibration and test never select candidates. No final refit uses those partitions. Selected and best learned pipelines are retained. Mean with a known fuel-absence gate is eligible; unconditional mean is an additional simple comparator.

## Frozen held-out test and uncertainty

|Target|Selected|Test MAE kWh/year|Test R²|Active 90%coverage|Active width kWh/year|
|---|---|---:|---:|---:|---:|
|annual_electricity_demand_kwh|physics_baseline|408.0|0.870|88.7%|1667.5|
|annual_lpg_kwh|physics_baseline|110.2|0.947|92.8%|667.1|
|annual_png_kwh|physics_baseline|16.2|0.979|88.3%|672.4|

Calibration uses one label-independent random representative per building/household group. Scores=|actual−prediction|/max(prediction,100); finite-sample90%split-conformal quantile establishes bounds. Structurally absent fuels have[0,0]intervals. Marginal exchangeable-group coverage does not guarantee each house, subgroup, correlated row or future drift. Row/group-weighted empirical coverage and active-fuel widths are recorded.

## Accounting and limits

Electricity demand precedes solar. Solar_kw is excluded from X. Shared accounting preserves demand=grid+self-consumption and PVgeneration=self-consumption+export. LPG/PNG remain separate; annual_gas_kwh is their compatibility energy sum.

The physical comparator is also the synthetic generator conditional mean, so its advantage is expected. Synthetic accuracy does not establish real Indian bill or causal retrofit accuracy. Weather/solar sources do not turn invented household labels into measured bills. See subgroup_metrics.csv, stress_tests.json,monotonicity.json. Counterfactual stress truth is assumed physics; the unobserved35%usage shift deliberately exposes coverage deterioration. No property-sale uplift is fabricated. External CSV training requires observed full-year demand/LPG/PNG targets, observed input fields, group IDs and declared provenance; supplier declarations require independent audit.
