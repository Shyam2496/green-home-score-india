# Green Home Score — Indian homes prototype

A Python + Scikit-learn + Streamlit demonstrator for the IIIT Hyderabad hackathon, focused on a Hyderabad residential pilot. Version 2 models household electricity demand before solar, LPG and PNG separately. NASA POWER weather and JRC PVGIS solar references are cached for eight cities. Training consumption labels remain synthetic; a separate 11-home RESIDE-AC audit uses real annual bills with explicitly missing inputs.

For a prototype review, start with `docs/review_readiness.md` for the working scope, test evidence, demo walkthrough and outstanding brief requirements.

Read `docs/model_card_v2.md` and `reports/training_report.md` before presenting accuracy. The strongest validation candidate is deployed, including the transparent engineering baseline if it beats the learned models. High synthetic accuracy does not establish real-world accuracy.

The external default-filled Hyderabad check overpredicts substantially (about 2,350 kWh/year MAE). Use actual annual consumption totals for household scenario demonstrations. The app starts with blank inputs and also offers an explicitly fictional sample. The model card explains what evidence is still missing; the current automated test result is in `reports/verification.txt`.

The dashboard includes seven-component scoring, goal-based retrofit priorities, per-fuel savings, carbon and bill estimates, interaction-aware packages, model evaluation and grounded explanations. `greenhome/retrofit_engine.py` ranks measures for annual bill, purchased-energy or operational CO₂ savings and proposes a package by recalculating interactions. **Costs & payback** adds explicit installation quotes, maintenance, replacements, discounted cash flows and payback for the selected package. Property-value impact is deferred: this prototype has no verified local transaction evidence linked to known retrofits and comparable-property controls. Lifetime financial NPV is a cash-flow scenario, not resale appreciation. See `docs/property_value_scope.md` for the submission scope and evidence needed.

## Run

Use Python 3.12 (the tested runtime for the pinned dependencies). On Windows, double-click `start.bat` to create a local environment, install the listed dependencies and open Streamlit.

Or run these commands from the extracted project folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On macOS/Linux, create the environment with `python3.12 -m venv .venv` and activate with `source .venv/bin/activate`. Open http://localhost:8501 if the browser does not open automatically. Internet access is needed for the first dependency installation. The bundled fitted models support local use without an API key.

## Try the demo

1. Enter grid electricity in kWh and the chosen cooking fuel's consumption across the same complete 12 months. Active-fuel inputs start blank; unknown consumption is never silently zero. Partial-year totals are withheld, not extrapolated.
2. For a walkthrough, choose **Try fictional sample**. Alternatively, turn off annual totals to explore the unvalidated model demonstration. Fictional sample and model origins remain visible in exports.
3. For real inputs, confirm known installation constraints. Unconfirmed consent blocks recommendations; roof area, shading, structural and electrical declarations screen the illustrative PV option. Demo modes use clearly fictional site assumptions in separate controls.
4. Choose **Your priority**, inspect the ranked candidates and their tradeoffs, then click **Use suggested package**. You can edit the what-if package afterward. Standalone rank, package selection order and physical installation order are different comparisons.
5. Open **Inspect the savings calculations**. Inspect the inferred baseline allocation, changed inputs, before/after fuel totals, interactions and signed CO₂ terms. Induction can save purchased energy while increasing electricity, carbon or bills; the chosen goal determines whether it is suggested.
6. In the financial calculator, enter an incremental installation quote for each applied measure. A blank quote is unknown; enter zero only when the action has no additional cost. Review the horizon, discount/escalation assumptions and any maintenance or replacement costs. Solar subsidy starts at zero and requires a separately confirmed amount and source.
7. Download the scenario for the recommendation decision record, numerical traces, input provenance, solar balances, bill calculation, financial cash flows and explicitly deferred property-value scope. Review the external Hyderabad audit before interpreting estimates. Matching entered bills does not validate appliance shares or retrofit savings.

All savings are estimates. The custom score is not a certification, and the recommendations require an installation survey and relevant permissions.

## Reproduce training and tests

```powershell
python train.py --rows 12000 --seed 42
python evaluate_external.py
python -m pytest -q
```

Training uses seed 42 by default. Buildings are split 50/15/15/20 into training, selection validation, uncertainty calibration and final test groups. The final test is not used to choose a model. Separate calibration groups set relative 90% conformal intervals; synthetic coverage does not transfer automatically to real houses. Inspect `python train.py --help` for measured-CSV training options and required provenance. Repeating training replaces experiment artifacts; keep the original final test frozen during development.

`evaluate_external.py` never fits a model. It evaluates the frozen bundle on eleven Hyderabad bill labels using five safely mapped household inputs and fixed defaults for unknown details. Its error is a partial-feature sanity check. Do not turn it into a claim of fully validated household prediction or tune defaults against those labels.

To reproduce the external field extraction, download the original RESIDE-AC v3 `dataset.zip` from the cited Figshare DOI, then run `python prepare_reside_audit.py path/to/dataset.zip`. The extraction retains anonymous household and survey fields, excludes income, and records the source checksum and mapping limits.

Generated artifacts:

| Location | Contents |
|---|---|
| `data/synthetic_homes.csv` | Synthetic households and annual per-fuel labels |
| `data/split_assignments.csv` | Household/building IDs and their four disjoint splits |
| `data/climate_reference.json` | Sourced weather/PV values, units, periods and API URLs |
| `data/reside_ac_external_audit.csv` | External Hyderabad bill labels and safely mapped inputs |
| `models/*.joblib` | Per-target saved preprocessing and fitted estimator |
| `models/metadata.json` | Training settings and selected models |
| `reports/metrics.json` | Candidate MAE/RMSE/R², calibration, subgroup and stress evidence |
| `reports/external_audit.json` | Frozen real-bill sanity check, missing inputs and limitations |
| `reports/held_out_predictions.csv` | Test labels and model predictions |
| `reports/training_report.md` | Generated training results |
| `reports/data_generation.md` | Synthetic label rules and assumptions |

Load only trusted Joblib files; Python model deserialization can execute code.

## Optional LLM explanations

The default deterministic explanation requires no credentials. To enable the optional OpenAI mode, set `OPENAI_API_KEY` in your environment or use the app's password input. `OPENAI_MODEL` defaults to `gpt-4.1-mini`.

The optional model selects fact identifiers through the Responses API. The displayed text is assembled from trusted, already-computed fact strings. It cannot supply independent numeric estimates. Invalid output or a provider failure falls back to deterministic explanations. The external provider path needs a valid key and network connection; an included offline test does not prove live-provider availability.

Do not enter real customer identifiers or confidential data. The explanation provider receives computed scenario facts when optional mode is enabled.

## Project map

| File / directory | Purpose |
|---|---|
| `app.py` | Interactive dashboard |
| `greenhome/schema.py` | Supported features, options and sample home |
| `greenhome/ml.py` | Synthetic data, training, persistence and inference |
| `greenhome/physics.py` | Disclosed heat-load/end-use baseline and solar conservation |
| `greenhome/engine.py` | Score, feasibility, scenarios and per-fuel accounting |
| `greenhome/retrofit_engine.py` | Goal-based priorities, interaction-aware suggested package and decision audit |
| `greenhome/billing.py` | Annual-consumption validation, provenance and signed bill calculations |
| `greenhome/finance.py` | Selected-package costs, discounted cash flows and payback; resale prediction unavailable |
| `greenhome/explanations.py` | Trusted facts and optional grounded LLM selection |
| `tests/` | Accounting, scenario, split and persistence checks |
| `docs/methodology.md` | Schema, score and calculation assumptions |
| `docs/architecture.md` | Pipeline diagram and what-if flow |
| `docs/evaluation.md` | Evaluation method and limitations |
| `docs/responsible_ai.md` | Privacy, bias, grounding and oversight |
| `docs/recommendation_system.md` | Decision method, module status, PV screening and API example |
| `docs/financial_module.md` | Financial equations, timing conventions, cost provenance, subsidy guidance and valuation limits |
| `docs/financial_audit_spec.md` | Page-indexed research audit, selected source checks and corrected implementation scope |
| `docs/property_value_scope.md` | Deferred property-value feature, demo explanation and future evidence requirements |
| `docs/submission_checklist.md` | Mapping to the brief's nine deliverables |

This adaptation uses Indian homes, INR, cooling/appliances and separate LPG/PNG cooking. `annual_gas_kwh` is the compatibility sum of LPG and PNG energy; do not count it again alongside those fuels. It retains the brief's seven component weights and consistent per-fuel methodology.
