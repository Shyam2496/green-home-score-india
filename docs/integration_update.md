# Bill anchoring, recommendations and financial scenarios

This application update keeps the V2 trained models, synthetic experiments, frozen split, calibration and 11-home external audit unchanged. No model fitting or tuning was performed. The roughly 2,350 kWh/year external MAE remains a material limitation.

Changes focus on making household scenarios usable and reviewable:

- Blank annual electricity and active cooking-fuel fields, declared complete-year coverage, and explicit unknown versus zero handling.
- Clearly labeled fictional sample and model demonstration modes; provenance preserved in exported scenarios.
- Annual-consumption calculations that work without loading a trained predictor.
- Inspectable baseline allocation and scaling, individual/marginal retrofit traces, signed per-fuel savings and carbon terms, PV balance and fuel-switch equations.
- One shared flat-rate bill calculation for the headline, per-fuel breakdown and download.
- Goal-based candidate priorities and a suggested package, with every proposed addition recalculated for interactions and a complete decision record.
- Preliminary PV site screening and unconfirmed real-input permission defaults; fictional demo site assumptions are kept in separate controls.
- A downstream financial calculator using the selected package's signed per-fuel bill savings, explicit incremental installation quotes, maintenance/replacements, annual cash-flow records and payback.
- Explicit first-year versus report base-year savings timing and no automatic subsidy in **Costs & payback**.
- Property-value impact explicitly deferred in the dashboard and exports, with a documented explanation of the missing market evidence.

`reports/bill_anchored_example.json` is a fictional worked example using 3,000 kWh grid electricity and 85.2 kg LPG over a declared year. It is a reproducible scenario, not a real customer result or an accuracy benchmark. `reports/verification.txt` contains the current test result, and `reports/artifact_checks.json` checks that the original training and external-audit evidence still match their recorded hashes.

Actual bill anchoring forces agreement with entered totals. The appliance shares, engineering defaults, constant-service assumptions and future savings remain unvalidated. The seven-component score, feasibility-aware package planner, per-fuel accounting, financial scenarios and grounded explanation layer are integrated. Property-value impact is deferred because verified local transactions linked to known retrofits and comparable-property controls are missing. This remains an explicit submission gap, alongside full CO₂e coverage. Financial NPV is the discounted cash-flow scenario and is not resale appreciation.

`docs/recommendation_system.md` maps the full computation modules and documents the new decision API. The new module reuses the existing engine instead of fitting another ML model. `reports/recommendation_examples.json` demonstrates objective tradeoffs, site rejections and zero-modeled-benefit handling on fictional inputs.

`docs/financial_module.md` records how the supplied JavaScript calculator was adapted to the existing Python application. LPG and PNG keep their separate units and tariffs; stale quotes for unselected measures do not enter a package total. The 34-page research PDF was located and read, and `docs/financial_audit_spec.md` records internal inconsistencies and selected primary-source checks; it is not a claim of exhaustive citation validation. The ZIP's capitalization/solar-asset valuation proxy is excluded. Property-premium controls are omitted from the dashboard. An experimental user-percentage sensitivity helper remains only for API compatibility and is not part of the current product or submission feature claims. The financial module neither retrains the energy model nor makes the recommendation engine an investment optimizer. `docs/property_value_scope.md` gives the judging explanation and future evidence requirements.
