# Complete computation and recommendation system

The energy predictor is one input to this system. Household annual-consumption totals can replace prediction without loading a fitted model. The recommendation layer reuses the existing physical scenario calculations; it does not train another energy model or let an LLM calculate outcomes.

| Module | Implementation and current scope |
|---|---|
| Annual energy baseline | Frozen V2 gross electricity, LPG and PNG models, or declared complete-year consumption totals |
| Green Home Score | Seven weighted components and efficiency classifications in `greenhome/engine.py`; custom India adaptations are documented |
| Feasibility | Consent, roof permission, heritage, equipment space and circuit checks; new PV also requires preliminary area, shading, structure and electrical declarations |
| Prioritized recommendations | `greenhome/retrofit_engine.py`: bill, purchased-energy or operational CO₂ objective, signed candidate rankings and a suggested package |
| Savings and what-if | Existing paired end-use calculations, fuel switching, PV balance and fixed interaction order; before/after per-fuel estimates and exact-state traces |
| Carbon and bills | Separate grid/LPG/PNG terms, signed fuel changes, documented factors and entered flat rates; compatibility gas total is not counted again |
| Retrofit finance | `greenhome/finance.py`: explicit selected-action quotes, maintenance/replacement assumptions, discounted cash flows and payback, using the same signed per-fuel bill savings |
| Property value | Deferred and unavailable: no verified local transaction evidence linked to known retrofits and comparable-property controls; no dashboard premium or valuation feature |
| Explanation and dashboard | Streamlit what-ifs rerun calculations first, then deterministic or optional grounded LLM fact selection explains the computed results |

## Priorities and package selection

`recommend_retrofits(home, energy, objective=..., tariffs=..., factors=...)` assesses the existing engine's feasible candidates and reports all blocked candidates with reasons. New API calls always enable strict PV screening, even if a caller supplies a false policy flag. Unknown or invalid core household/energy data withholds priorities. Missing rates withhold bill priorities; invalid emissions factors withhold carbon priorities independently of energy ranking.

Available objectives are `bill_savings`, `energy_savings` and `carbon_savings`. The input tariff keys are `electricity_rate` in INR/kWh, `lpg_price_kg` in INR/kg and `png_rate` in INR/net-CV kWh. No price values are invented by the decision API. The UI passes its disclosed, editable rates.

First, candidates are ranked by signed standalone benefit for the selected objective. Then the decision layer repeatedly evaluates every remaining candidate added to the current suggested package. Each proposed package reruns `evaluate_scenario` in its physical installation order. The candidate with the greatest strictly positive incremental package benefit is chosen; ties use stage then ID. Selection stops when no addition improves the objective. This is a deterministic greedy heuristic, not a globally optimal solution or investment appraisal. Zero-modeled-benefit measures are retained for inspection but are not chosen merely because their physical suitability is High.

Standalone priority, decision selection order and installation order have separate meanings. For example, induction can raise bills alone yet help a package with PV by changing self-consumption. Its benefit when added to that package can be positive while its final installation-order marginal, before PV is applied, is negative. The API exposes `objective_benefit`, `decision_incremental_benefit` and `package_marginal_objective_benefit` separately. The full `decision_audit` records every considered package and its incremental objective. These numbers must not be substituted for one another or summed as standalone savings.

The final suggested `scenario` is a normal engine result, including seven-component before/after scores, per-fuel savings, carbon, unavailable property-value status and calculation traces. The dashboard keeps the user's what-if package editable; clicking **Use suggested package** recalculates that package before explanations. **Costs & payback** then assesses that selected physical scenario with explicit costs. It does not change recommendation rankings or optimize the package by NPV, budget or payback. The optional AI question explains the selected scenario; free text does not independently edit property inputs.

## Preliminary solar screening

The dashboard and new decision API require `usable_roof_area_m2 >= 30` for the illustrative fixed 3 kW option and affirmative `solar_shading_ok`, `solar_structure_ok` and `solar_electrical_ok` declarations, alongside the existing permission/consent checks. The area screen uses the government rooftop FAQ's approximate 10 m²/kWp guidance. Actual module efficiency and layout vary. [Government rooftop solar FAQ, section 1.3](https://api.solarrooftop.gov.in/pdf/faq_new.pdf).

This screen is based on declarations; it is not a design, structural certification or approval from a DISCOM. Actual panel placement, roof loading, electrical design, fire access, shading, connection and permissions still need qualified assessment. It does not size a smaller system for a smaller roof. The legacy calculation API can retain conditional survey assumptions when strict screening is not requested; the dashboard and decision API always request it.

Real-input permission controls start unconfirmed and roof area starts blank. Fictional annual samples and model demos use a separate set of explicitly labeled fictional site controls so demo permissions do not carry into a real household entry.

## Python example

```python
from greenhome.schema import DEFAULT_HOME
from greenhome.retrofit_engine import recommend_retrofits

# Fictional complete-year inputs and fictional preliminary site declarations.
home = {**DEFAULT_HOME, "usable_roof_area_m2": 50.0,
        "solar_shading_ok": True, "solar_structure_ok": True,
        "solar_electrical_ok": True}
energy = {"annual_grid_kwh": 6500.0,
          "annual_lpg_kwh": 1800.0, "annual_png_kwh": 0.0}
plan = recommend_retrofits(
    home, energy, objective="bill_savings",
    tariffs={"electricity_rate": 8.0, "lpg_price_kg": 65.0, "png_rate": 5.0},
)
print(plan["selected_ids"], plan["package_objective_benefit"])
```

`reports/recommendation_examples.json` contains reproducible fictional examples across the three objectives plus missing-site and fan-only cases. These are behavioral demonstrations, not empirical validation labels.

## Remaining evidence and coverage gaps

Real-home energy prediction, inferred end-use shares and retrofit savings still need independent measurement. The roughly 2,350 kWh/year external audit error is unchanged. Installation quotes and financial assumptions now support downstream cash-flow and payback scenarios; they do not establish realized savings or investment-optimal recommendations. Budget optimization is not implemented. Property-value impact is explicitly deferred; financial NPV is not converted into a property premium. This is a submission gap, not a completed feature. Carbon is operational CO₂ rather than full CO₂e, and the optional live LLM path has not met the brief's targets through a recorded provider evaluation. Heat-pump hot water is a baseline input but not a retrofit candidate; heat pumps and shading alternatives are not exhaustively covered. The system is a reviewable hackathon prototype, not a completed production or field-validated service. See `docs/financial_module.md` for the finance boundary and `docs/property_value_scope.md` for the evidence plan.
