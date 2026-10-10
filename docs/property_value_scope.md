# Property-value impact: deferred scope

Property-value impact is deliberately deferred in this prototype. The dashboard has no property valuation or hypothetical premium controls. Scenario exports preserve the deferred status and reason; resale-price uplift remains unavailable. This is an explicit gap against the hackathon's property-value requirement, not a completed or validated feature.

## Judging and demo explanation

“We currently estimate household energy use, retrofit bill savings and operational carbon, then calculate installation costs, discounted financial cash flows and payback from explicit assumptions. We have deferred property-value impact because we do not have verified local transaction data linked to known retrofits and comparable-property controls. Financial NPV measures the assumed cash-flow benefit to the household; it does not establish what a buyer would pay for the property. Our custom Green Home Score also does not establish building certification or a resale premium. The app therefore marks this feature as deferred rather than presenting an unsupported appreciation estimate.”

## What the working finance feature means

Annual bill savings come from the selected physical scenario and entered fuel rates. Lifetime NPV then incorporates the entered horizon, discount/escalation assumptions, installation quotes, maintenance, replacements and any explicitly confirmed subsidy. Both are scenarios dependent on unvalidated retrofit savings and supplied inputs. Neither is converted into a property price, capitalization premium or certified-building uplift.

The reviewed research and supplied calculator provide useful cash-flow formulas, but do not supply a validated local resale model. The source audit is in `docs/financial_audit_spec.md`; the implemented finance boundary is in `docs/financial_module.md`. An experimental user-percentage arithmetic helper remains in the Python API for compatibility, outside the dashboard and current feature claims.

## Evidence needed before revisiting the feature

1. Obtain appropriately licensed, non-identifying completed local sale transactions with dates and consistent area measurements. Asking prices, locality averages and government guidance values must be distinguished from completed sale prices.
2. Link those transactions to documented retrofit type, installation date, capacity, condition and ownership rights. Record any formal certification independently of the prototype score. Identify homes without those changes for comparison.
3. Collect comparable-property controls such as locality, floor/carpet area, age, property type, floor, amenities and sale timing. Check missingness, repeated properties and selection bias before choosing a method.
4. Define the intended estimate and study design. An association between certified projects and prices is not automatically the causal effect of an individual retrofit; before/after or matched comparisons would need their own assumptions and checks.
5. Evaluate on untouched properties and time periods with suitable baselines, subgroup errors and uncertainty assessment. Record geographic limits and avoid applying coefficients to populations unsupported by the evidence.
6. Review the resulting evidence before deciding whether any property-value output is defensible. Until then, keep the feature deferred and report the scope gap plainly.

This is an evidence plan, not a commitment that the necessary data exist or that a reliable resale model will result.
