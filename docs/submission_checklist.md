# Submission map

The condensed brief requests nine deliverables. Paths below are relative to the project root.

| Brief deliverable | Prototype evidence |
|---|---|
| A — working dashboard | `app.py`; Streamlit run command in `README.md` |
| B — source, data preparation, run instructions | `greenhome/`, `generate_data.py`, `train.py`, `README.md`, `data/synthetic_homes.csv` |
| C — selected models and inference | `models/annual_electricity_demand_kwh.joblib`, `models/annual_lpg_kwh.joblib`, `models/annual_png_kwh.joblib`, best learned alternatives, metadata and `greenhome/ml.py` |
| D — score mappings | `docs/methodology.md` and `greenhome/engine.py` |
| E — LLM implementation and evaluation | `PROMPT` and Responses API implementation in `greenhome/explanations.py`, `docs/evaluation.md`; deterministic mode works without credentials |
| F — architecture diagram | `docs/architecture.md` |
| G — validation and baseline comparison | `reports/training_report.md`, `reports/metrics.json`, `reports/external_audit.json`, subgroup/stress reports and `docs/model_card_v2.md` |
| H — Responsible AI note | `docs/responsible_ai.md` |
| I — held-out predictions, schema and labels | `reports/held_out_predictions.csv`, `data/split_assignments.csv`, `reports/data_generation.md` and `docs/methodology.md` |

## Demo checks

1. Choose the explicitly fictional annual sample for a walkthrough, or enter complete 12-month consumption totals. Show the seven score components and separate fuel totals. Unknown active fuel use must withhold results.
2. Compare individual roof-insulation and efficient-AC results with their combined package. Package savings must reflect interactions.
3. Select induction cooking for an LPG-using home. LPG should fall while electricity rises; an increase appears as a negative saving.
4. Disable roof suitability and inspect the solar feasibility reason. Enable heritage restrictions or disable consent and inspect the conservative recommendation changes.
5. Enter zero annual fuel totals. Percentage improvement must read unavailable, without division by zero.
6. Make a what-if selection and show that computed outputs refresh before the explanation.
7. Show model validation results, the simple baseline, synthetic-data limitations and held-out predictions.
8. Open the savings calculation inspector. Compare an AC measure alone with its marginal effect after insulation; inspect the changed inputs, end-use ratios, signed carbon terms and percentage denominator.
9. Download the scenario and show the input origin, coverage declaration, before/after states, package steps and bill-rate contributions. Confirm fictional inputs stay labeled fictional.
10. Change the recommendation goal between annual bills, purchased energy and operational CO₂. Review signed tradeoffs, apply the suggested package and inspect the decision record. Standalone ranks must not be confused with interaction order or summed savings.
11. Enter an unknown/too-small roof or leave solar suitability unconfirmed. The 3 kW option must be blocked with reasons. Actual bill entry must not automatically imply owner consent.
12. Enter installation quotes for the selected package. Leave one quote blank to show that unknown costs withhold investment outputs; then enter an explicit zero or quote to continue. Changing the physical selection must change the included cost items and financial cash flows.
13. Inspect annual bill savings, maintenance, any replacement outlay, discount factors and cumulative cash flow. Compare the first-year and report base-year timing conventions. Subsidy must stay zero until a confirmed amount and source are supplied for a newly applied PV measure.
14. Show annual bill savings and lifetime financial NPV in **Costs & payback**, then show the deferred property-value explanation. No property-premium control or resale estimate should appear. The exported feature scope must retain the deferral reason. Financial NPV and Green Home Score must not be described as property appreciation.

Automated checks complement these demos; they do not validate an actual retrofit installation or a property's market value.

## Evidence still needed

Real-home prediction and retrofit savings are not established by the current data. The financial calculator evaluates entered costs and assumptions; actual quotes, equipment service lives and realized cash flows still need verification. **Property-value impact is deferred and is an explicit submission gap.** The prototype has no verified local transactions linked to known retrofit histories and comparable-property controls; lifetime financial NPV does not substitute for that evidence. The dashboard omits valuation and hypothetical premium controls. Carbon covers operational CO₂ rather than the brief's full CO₂e boundary. The optional live LLM path needs an API key and a provider evaluation; deterministic explanations work offline. These remain explicit limitations for the submission, not completed evidence claims.

See `docs/recommendation_system.md` for the implemented module map and goal-based decision method. Technology coverage is a pilot subset: heat-pump water heating is a baseline input, not an available retrofit action, and glazing/shading alternatives are not exhaustive.

See `docs/financial_module.md` for selected-package cost accounting, NPV timing and subsidy guidance, and `docs/property_value_scope.md` for the deferred feature and future evidence plan.
