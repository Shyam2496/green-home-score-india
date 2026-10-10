# External Indian household-data audit

Audit date: 10 October 2026. Public original-research sources were checked for licence, access, measured labels, coverage and feature compatibility. **No records described below were used to fit the bundled model.** Public availability alone does not imply representative sampling or compatibility with the model's targets.

| Source | Verified scope and licence | Decision |
|---|---|---|
| [RESIDE-AC, original IIIT Hyderabad research paper](https://doi.org/10.1186/s42162-022-00225-4), [Figshare dataset v3](https://doi.org/10.6084/m9.figshare.16869439.v3) | 11 Hyderabad homes with AC, 19 summer monitoring days, household/building/primary-AC surveys and annual electricity-bill totals. The dataset's API reports CC0 1.0; the paper is CC BY 4.0. Public ZIP downloaded and checksum verified. | Useful small, independent **sanity check**. Missing annual use, envelope, solar and fuel features prevent a complete observed-feature benchmark. Do not fit on these 11 homes or claim national accuracy. |
| [iAWE project](https://iawe.github.io/), [Home_Deployment repository](https://github.com/nipunbatra/Home_Deployment) | One Delhi home, about 73 summer days in 2013; meter/circuit/appliance sensing. Project documents sensor/network interruptions. No explicit data-reuse licence was verified in the inspected project/repository root; the linked data store redirected to authentication. | Reject for current training: licence/access unresolved, one home and incomplete annual coverage. Useful research context; no raw data imported. |
| [IIT Bombay Residential Data](https://figshare.com/s/a4aedbe2ae2aadc5618b?file=13842431) | Source describes 39 anonymized apartments retained from one campus building, December 2016–June 2018, hourly phase energy in Wh, CC BY 4.0. Page is marked shared privately and its download returned 403 during this audit. | Candidate for a future electricity time-series/scale benchmark after authorized access and coverage checks. Current metadata does not provide the full model feature schema or LPG/PNG labels. No raw data imported. |
| [CEEW Mathura/Bareilly smart-meter dataset, Harvard Dataverse](https://doi.org/10.7910/DVN/GOCHJH) | Official dataset API reports CC0 1.0 and unrestricted files. Original README and published daily aggregates inspected; 46 Bareilly and 38 Mathura meter IDs occur in these files. | Lawfully accessible electricity evidence, but no matched property/appliance features or fuel labels. Useful for coverage and meter-data ingestion research; not a benchmark of this full household model. |

## RESIDE-AC extraction and boundaries

`data/reside_ac_external_audit.csv` contains 11 published anonymous household records, with source DOI, licence, units, original property-type text, field availability and critical missing fields. `data/reside_ac_external_audit_manifest.json` records provenance, checksum, transformation choices and limitations.

Observed model-compatible fields are city (Hyderabad), floor area, occupant count, AC count and an explicitly mapped property type. Source spelling `tenemant` maps to an apartment proxy, consistent with the paper's low-rise-flat description; the original text is retained. Primary-AC type, tonnage, star rating and setpoint remain separate observed fields, because they do not describe every AC in a multi-AC home. Monitoring-derived primary-AC runtime remains explicitly a summer observation, not measured annual usage.

The annual electricity label is the published survey's electricity-bill total. Its exact billing period/year is not given. It is named `annual_grid_kwh_observed`, not asserted gross appliance demand. PV, exports, LPG and PNG are unlabeled. Across these 11 records the annual electricity total is 1,654–3,349 kWh/year (mean 2,573.3); this describes this selected sample only.

There is a source-date conflict: the Figshare v3 description says May 2021, while the downloaded monitoring CSV timestamps say May 2019. The paper's abstract also says 2019. The extraction preserves actual timestamps and records the conflict instead of inventing a resolution.

Original archive: Figshare file ID `38686209`, `dataset.zip`, 1,802,819 bytes. Published/computed MD5 both `dc02fa4f80433d9b26ad002a90aee5ae`. The manifest also records SHA-256. The extraction uses the survey CSVs and AC-status records; it does not infer kWh directly from current measurements without voltage/power-factor evidence. Income fields and addresses are not copied or joined.

Any external comparison must freeze the predictor first, list every missing-feature assumption, compare predicted **grid imports** with the bill label, report all 11 results and scenario sensitivity, and describe the result as an assumption-dependent sanity check. Neither low nor high error on this incomplete-feature sample establishes real-world validation. Its records must not be used to tune the frozen model after seeing the comparison.

Attribution: Tejaswini, D., Ramapragada, P., Gundepudi, S., Kandukuri, P. R., Garg, V., Mathur, J. and Gupta, R. (2022), *Residential electricity current and appliance dataset for AC-event detection from Indian dwellings*. [Dataset CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/); [paper CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Transformations are documented above.

## CEEW ingestion observations

The inspected daily files contain 28,119 Bareilly and 16,491 Mathura meter-day records. Bareilly dates span 9 May 2019–31 October 2021; Mathura dates span 1 May 2019–20 February 2021. Per-meter recorded-day counts range from 124–827 and 195–624 respectively. No duplicated meter/date keys, missing energy cells or negative daily kWh were found in these two aggregates. This does not prove continuous coverage, meter accuracy, or distinguish outages from low use.

Daily averages must not simply be multiplied by 365 and called measured annual labels. A future adapter must audit expected timestamps, gaps, meter resets, units and coverage, retain household groups across all years, and record the aggregation decision. All years from one meter must remain in one partition when testing transfer to unseen households. The dataset does not establish Hyderabad or nationwide performance.

## Gate for future supervised records

An acceptable real-data training file needs a lawful provenance/licence record, non-identifying household/building grouping IDs, the supported observed property features, separately labeled annual demand/import/fuel quantities with units and period, and explicit missing-data treatment. It must not silently fill missing fuel labels with zero, infer gross demand from bills when PV is unknown, or present synthetic assumptions as measurements. Repeated household/building records must remain together across train, validation, calibration and test. External samples used for model development need a new untouched evaluation set afterward.
