# Evaluation — India energy model v2

The canonical experiment evidence is in reports/metrics.json and reports/training_report.md. This release uses 12,000 synthetic household rows in 3,000 building/archetype groups. Training, selection validation, calibration and final test contain 6,000/1,800/1,800/2,400 rows. Group IDs never cross partitions. The final test groups are frozen for an identical dataset fingerprint.

## Model comparison

Electricity demand before solar, LPG and PNG are separate targets. The training mean, transparent physical baseline, Random Forest, Extra Trees, histogram gradient boosting and a relative residual boosted model compete by validation MAE. Each applies the known inactive-fuel zero rule. An unconditional mean comparator is also reported. No candidate is selected using calibration or test results; there is no final refit on those partitions.

The physical baseline won all three targets in the bundled experiment. Because the same physical equations generate synthetic labels, that result is expected and does not prove real-world superiority. Selected and best learned alternatives are retained as trusted local Joblib artifacts. Exact versions and source hashes accompany the experiment.

## Error and uncertainty

Reports include MAE and RMSE in kWh/year, dimensionless R² and WAPE, subgroup sample sizes, active-fuel errors, interval width and empirical coverage. Read active LPG/PNG slices separately: overall fuel errors can appear small because absent fuels are exactly zero.

The 90% relative split-conformal intervals use a separate calibration partition, one label-independent representative per group, and the exact finite-sample order statistic of absolute error divided by max(prediction,100). At least nine independent active examples are required for a finite 90% interval. Exchangeable independent-group assumptions are necessary. Coverage is not guaranteed for a subgroup, particular dwelling, correlated row, future drift or real-world population. Grid intervals transform demand bounds through the same monotone PV accounting function.

Subgroup reports cover city, property type, cooling, cooking fuel and installed solar. Direction checks inspect LED share, ISEER and window shading. Stress cases change cooling use, envelope properties and an unobserved 35% consumption shift. Stress-reference values are assumed physics, not measured retrofit or climate-change outcomes.

## External evidence

The frozen external check uses real annual electricity bill labels for eleven anonymous Hyderabad homes in RESIDE-AC. Five household inputs are safely mapped; unknown annual usage, fabric, solar and other inputs use fixed disclosed defaults. No external labels are used for training, selection, calibration or tuning.

The default-filled check overpredicts every home: MAE approximately 2,350 kWh/year, against mean observed imports of 2,573 kWh/year. None of the eleven bills falls in the synthetic uncertainty interval. Missing features and an unknown bill year limit interpretation, but these poor results mean real-house accuracy is not established. No LPG or PNG validation is available. See reports/external_audit.json, external_audit_predictions.csv and docs/external_data_audit.md.

For household demonstrations, actual annual electricity and fuel bills are the recommended baseline. Retrofit estimates still rely on modeled end-use allocation and assumed physical changes. A new representative measured dataset and an independent temporal/geographic holdout are needed before claiming useful real-house prediction.

## Verification

The test suite checks independent group partitions, exact calibration rank, saved prediction reproduction, input/provenance rejection, per-fuel accounting, PV conservation and inversion, signed carbon, interacting retrofits and dashboard flows including PNG and advanced inputs. Final test output is saved in reports/verification.txt.

These tests establish reproducibility and internal consistency, not actual retrofit effectiveness. The live dashboard is inspected separately after model training. Optional external LLM calls require credentials and are not validated by offline tests.

## Explanation evaluation

The default explanation renders computed facts. Optional LLM mode selects supported fact identifiers and cannot supply new numeric estimates. Invalid identifiers or provider errors fall back to deterministic explanations. The hackathon targets for groundedness, factual accuracy and unsupported claims remain targets until a recorded live-provider evaluation is completed. Model improvements in this release do not imply that those separate GenAI targets have been met.
