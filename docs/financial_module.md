# Retrofit costs, cash flows and payback

`greenhome/finance.py` adapts the supplied `green_retrofit_financial_calculator.zip` to the Python dashboard. It consumes the currently applied physical retrofit scenario and the existing signed bill calculation. Three outputs stay distinct:

1. **Annual bill savings:** an estimate from the physical scenario and entered per-fuel rates.
2. **Lifetime financial NPV:** a financial scenario using explicit costs, horizon and cash-flow assumptions.
3. **Property-value impact:** deferred and unavailable because verified local transactions linked to known retrofits and comparable-property controls are missing.

The dashboard presents the implemented financial calculations in **Costs & payback**. Property-value impact is an explicit scope gap; valuation and hypothetical premium controls are omitted. NPV is a discounted cash-flow scenario, not resale appreciation. The module does not predict energy consumption, change the Green Home Score, establish subsidy eligibility, or fit a property-price model. See `docs/property_value_scope.md` for the demo explanation and evidence requirements.

The supplied ZIP contains a JavaScript engine, interface, tests and an integration example. The accompanying 34-page **Green Retrofit Valuation Research.pdf** was subsequently located and read in full; its key equations, code and bibliography were also visually checked. `docs/financial_audit_spec.md` records the page-indexed audit and selected source checks. Reading the report does not verify all its citations or empirical claims. No inherited locality price, guidance value or certification premium is silently applied.

## Inputs and provenance

An incremental installation cost is required for each applied retrofit ID. A missing or blank quote is unknown and withholds investment outputs; explicit zero means no incremental outlay. Enter the complete additional quoted cost, including relevant installation, wiring, surveys, permissions and tax. Costs for unselected measures are ignored and disclosed, so a stored quote cannot silently inflate a different package. Existing equipment and previously installed PV are outside the new installation total.

The calculation records quote provenance, the selected IDs, annual bill trace, horizon, timing convention, discount and escalation assumptions, annual maintenance, replacement events, and any confirmed subsidy source. Quotes and financial assumptions are supplied by the user, not learned from the synthetic household data. Sample inputs remain fictional.

The first-year monetary saving `S` comes from the shared `bill_savings_trace` calculation:

```text
S = electricity_saved_kWh × electricity_INR_per_kWh
  + LPG_saved_kWh ÷ (47.3 / 3.6) × LPG_INR_per_kg
  + PNG_saved_kWh × PNG_INR_per_net_CV_kWh
```

Each fuel contribution stays signed. A fuel switch can increase electricity spending while reducing LPG or PNG spending. The compatibility `annual_gas_kwh` total is never counted again. The new financial module does not collapse LPG and PNG into the ZIP's single generic gas rate.

## Cash-flow equations and timing

Let `C` be the sum of the selected incremental quotes, `U` an explicitly confirmed subsidy amount, `M` the fixed annual nominal maintenance assumption, `R_t` the entered nominal replacement outlay in year `t`, `e` annual bill escalation, `r` annual discount rate and `N` the chosen horizon. All operating flows occur at year end. For the default `first_year` convention, `S` is the saving during year 1:

```text
bill_saving_t = S × (1 + e)^(t - 1)
net_flow_t = bill_saving_t - M - R_t
discounted_net_flow_t = net_flow_t / (1 + r)^t
net_initial_cost = C - U
NPV = -net_initial_cost + sum(discounted_net_flow_t, t = 1..N)
```

The alternate `report_base_year` convention reproduces the ZIP's timing: `bill_saving_t = S × (1 + e)^t`. It escalates the supplied base amount before the first year-end payment. At nonzero escalation this produces a different result; the convention is recorded rather than mixing both definitions of `S`.

The present value of bill savings, maintenance and replacements is shown separately from net financial benefit. Annual maintenance is a constant nominal amount; it is not escalated automatically. Replacement amounts are entered as future nominal costs in particular years and are discounted once. A zero maintenance amount or an empty replacement list is an explicit scenario assumption, not evidence of a maintenance-free system. Choose a horizon supported by the equipment assumptions and include replacements when continued service requires them.

The ZIP's 4.5% escalation and 8.5% discount rate are editable research assumptions. They are not verified forecasts, current loan rates or investment recommendations. Future savings also assume the upstream physical service level and yearly savings persist over the chosen horizon. Financing, tax, depreciation, variable performance degradation, time-varying tariffs, export revenue and residual value are not modeled.

The subsidy reduces the initial outlay in this simplified scenario. Actual disbursement can occur later; the calculator does not model the funding gap or reimbursement date. Payback measures and their limits are reported separately from NPV. The simple ratio uses net initial cost divided by the positive entered annual saving `S` minus maintenance, under either timing convention; it ignores escalation, discounting and replacements. Discounted payback is the first time-zero or year-end point when cumulative discounted net cash flow becomes nonnegative and remains so through the modeled horizon. It includes maintenance and replacements, with no fractional-year interpolation. A later replacement can therefore delay recovery beyond an earlier temporary crossing. Neither metric guarantees realized recovery.

## Solar subsidy: dated guidance, no automatic award

Checked **10 October 2026**. Standard individual-household guidance is ₹30,000/kWp for the first 2 kWp, ₹18,000 for the next 1 kWp, and no additional central assistance beyond 3 kWp: a ₹78,000 cap. This schedule is stated in [MNRE's residential CFA guidelines, section 5(h)](https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2024/07/202407021768035484.pdf) and corroborated in the [February 2026 PIB scheme summary](https://newindiasamachar.pib.gov.in/WriteReadData/flipbook/2026/Feb/1st/English/files/basic-html/page35.html).

The MNRE guidelines distinguish module DC capacity, special-category rates, common-facility/RWA arrangements and prior subsidized capacity. Eligibility also involves a qualifying residential DISCOM connection, National Portal process, registered vendor, domestic-content requirements and DISCOM verification. The dashboard's site declarations do not verify those conditions. Consult the [official National Portal](https://pmsuryaghar.gov.in/) for the property's actual claim.

The app defaults to **zero subsidy**. A nonzero amount enters costs only for a newly applied PV measure after the user explicitly confirms an amount and records its source. The standard schedule is guidance, not an automatic deduction or a claim that the user qualifies. Existing PV capacity must not be treated as a fresh 3 kW claim. Additional state support and special-category rates are not estimated by this pilot.

The prototype's PV measure requires roof/site declarations for its particular rooftop installation. This is narrower than scheme eligibility: [MNRE's February 2025 policy update, item 2](https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2025/03/202503101999174139.pdf) describes the clarification allowing qualifying ground-mounted elevated installations and virtual-net-metering pathways. Blocking the prototype's rooftop measure does not establish that a household is ineligible for the wider scheme.

## Property-value impact is deferred

The resale-price prediction stays `unavailable`, regardless of financial NPV or Green Home Score. No property-value or premium-sensitivity feature is offered in the current dashboard. The exported feature scope records the deferral and its reason. This must be presented as unfinished scope for the hackathon submission, not as a validated result or a completed property module.

An experimental compatibility path remains in the Python API for callers that explicitly supply a hypothetical baseline and user-entered premium bounds. It is excluded from the dashboard and current feature claims. It computes only arithmetic sensitivity:

```text
hypothetical_premium_low = entered_baseline_value × entered_low_percent / 100
hypothetical_premium_high = entered_baseline_value × entered_high_percent / 100
hypothetical_post_value_range = entered_baseline_value + each entered-premium amount
```

For that API-only path, the low/high percentages and baseline are entirely supplied by the caller. A baseline can be an explicit total or separately supplied carpet area and assumed rate; the energy form's built-up area is not substituted. Any resulting range is `hypothetical_only`, not a confidence interval, appraisal or prediction that a buyer will pay that amount. It has no causal link to the retrofit's estimated savings and does not change the unavailable resale prediction.

No Green Home Score threshold triggers an IGBC, GRIHA or other certification premium. The original scenario engine's `value_impact` and the financial module's resale prediction remain unavailable. Financial calculations are `scenario_only`; neither they nor experimental compatibility helpers complete the deferred property-value requirement.

## Corrected implementation scope and ZIP audit notes

The integration retains separately priced annual savings, disclosed NPV timing, explicit costs and a cash-flow audit. It excludes the ZIP's automatic capitalization of bill-savings NPV into property uplift, the 8% valuation cap, the 35% spread, and the 1.10 solar asset multiplier. Financial value to the household is not automatically market value to a buyer. Combining capitalized solar savings with an installation-cost asset term can overlap; neither is implemented as a resale estimate.

The ZIP's generic electricity/gas example is replaced with the application's separate grid/LPG/PNG accounting. Installation costs refer to new applied actions, and a subsidy is user-confirmed rather than automatically awarded. Inherited Hyderabad market rates and government guidance-value assumptions are excluded. A Green Home Score of 70 does not establish formal building certification or support a certification premium.

Citation and methodological concerns are not resolved by arithmetic tests. The report's page 5 describes a Pune study, while bibliography item 2 on page 33 links a Jakarta study. A separate genuine Pune paper was located at its publisher, but it does not validate this report's score-to-premium equation for Hyderabad. The detailed audit separates citation mismatches, internal calculation issues and unestablished empirical assumptions. Defensible resale modeling would need appropriately licensed, geography-matched comparable sales and observed retrofit/certification details, with independent validation; the prototype does not have those labels.

## Integration and verification boundary

The Python entry point is:

```python
calculate_financial_scenario(
    scenario, bill_trace, installation_costs,
    years=10, discount_rate=0.085, escalation_rate=0.045,
    timing="first_year", annual_maintenance_inr=0,
    replacements=None,
    solar_subsidy_inr=None, solar_subsidy_confirmed=False,
    solar_subsidy_source="", cost_provenance="",
    value_scenario=None,
)
```

The financial result is a scenario with its assumptions and cash-flow record, or unavailable with reasons. It is evaluated after the manual or suggested retrofit package has been recalculated. Finance does not alter the recommendation engine's bill, energy or carbon objectives; those remain a greedy physical-savings heuristic, not a budget or investment optimizer.

The dashboard passes `value_scenario=None`. The argument remains an experimental compatibility option for explicit API callers, not a product feature or evidence of property-price prediction.

The automated result for the packaged application is recorded in `reports/verification.txt`. Arithmetic checks and scenario consistency establish implementation behavior, not the truth of supplied quotes, future tariffs, equipment lifetimes, retrofit savings or property resale uplift. The frozen energy training and eleven-home external audit remain unchanged, including the roughly 2,350 kWh/year audit MAE.
