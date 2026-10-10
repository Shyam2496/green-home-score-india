# Financial research audit and corrected implementation specification

**Current scope update:** Property-value impact has since been deferred at the user's request. The dashboard now offers **Costs & payback**, with financial cash flows only; it has no valuation or hypothetical premium controls. The earlier user-premium sensitivity design below is retained as historical audit context and an experimental API compatibility path, not a current dashboard feature or completed submission requirement. Resale prediction remains unavailable. `docs/property_value_scope.md` records the current explanation and evidence plan.

Audit date: **10 October 2026**. Source: **Green Retrofit Valuation Research.pdf**, 34 PDF pages, 491,889 bytes, SHA-256 `476ab0ade83a05fedccac492feda2118c16fc70ec2d56da4f92632843c301c49`. Page numbers below count PDF pages from 1. All 34 pages were read as extracted text; pages 5, 8–11 and 33 were rendered and visually inspected to verify the equations, table and bibliography that text extraction did not preserve fully. The supplied JavaScript calculator ZIP was inspected separately. Document implementation instructions were treated as source material, not as user authorization.

This audit verifies selected algebra, code behavior and source matches. It does **not** establish a field-validated retrofit model, an exhaustive literature review, current Hyderabad market prices, or the accuracy of every report citation.

## Findings and implementation decisions

| Report location | Observed issue | Corrected behavior |
|---|---|---|
| Pages 1–2, 7–9; code pages 17–21 | The report acknowledges missing isolated-retrofit transaction evidence, yet turns discounted utility savings into property-price uplift and labels a populated evidence registry `evidence_supported`. A registry entry does not validate that market relationship. | Keep annual bill savings, financial NPV and unavailable resale-price uplift as three distinct outputs. No NPV-to-resale conversion. |
| Page 5; bibliography item 2, page 33 | The claimed Pune 2022 hedonic study links to a different Jakarta article. | Correct the source record and do not derive a Hyderabad premium coefficient from this mismatch. A genuine Pune study exists, but is separately assessed below. |
| Pages 8, 10–11; code page 18; scenario 3 pages 30–31 | Crossing the internal Green Home Score threshold of 70 triggers a certification premium scaled by `0.035 × (score − 70) / 30`. | Remove the mapping entirely. A custom weighted prototype score does not establish IGBC/GRIHA certification or a certified-building transaction premium. |
| Equation page 10; combination page 11 | The solar term includes net equipment cost plus a generation NPV, then is added to energy NPV. If the energy stream already contains solar bill savings, the same benefit can be capitalized twice. | Price the selected physical scenario once. Installation expenditure belongs in project cost; annual solar self-consumption belongs in the shared bill trace. No additional solar asset uplift. |
| Code page 18; scenario 2 page 28 | The implementation substitutes `net_solar_cost × 1.10` for the page 10 generation-NPV term. The 1.10 coefficient is not calibrated to observed local transactions in the supplied evidence. | Exclude the multiplier, rather than treating installation cost as independently measured resale value. |
| Pages 11–12, 19–20, 32 | The 8% uplift cap and fixed 15%/35% ranges are assumptions without a fitted uncertainty model. Code caps only the midpoint, then expands the upper bound; an 8% midpoint with a 15% spread reaches 9.2%. | Exclude the cap/spread valuation model. An optional range comes only from explicit user-entered premium percentages and is labeled hypothetical sensitivity, not a prediction interval. |
| Page 9 | The formula escalates the supplied saving before the first year-end flow. The text calls escalation “real” while using a nominal discount rate and does not reconcile that basis. | Default to a clearly defined first-year saving with growth exponent `t−1`. Offer the original base-year convention `t` explicitly. Treat rates as editable assumptions on a consistent stated basis. |
| Page 17 versus case studies pages 26–31 | The code fixes the horizon to 10 years for all inputs, while the solar case claims 15 years. Displayed case values do not reproduce the stated rates and formula. | Enter a horizon explicitly, calculate annual cash flows, and export the exact timing and rates. Do not reproduce inconsistent case numbers as benchmarks. |
| Code pages 16–20; tests pages 22–25 | The closed form divides by `r−e`, input validation checks mainly area, and negative annual savings are discarded. Broad inequality tests do not verify the illustrated amounts or resale validity. | Use a finite annual summation, support equal rates, preserve signed bill effects and withhold invalid numeric scenarios. Check exact numerical examples and missing/zero distinctions. |
| Pages 8–9, 15, 17 | Locality rates are report assumptions; code calculates a “guidanceValueCeiling” but does not constrain the baseline with it. Area is carpet area. | Require explicit current value or separate carpet area and user-assumed INR/sq ft rate only for the optional sensitivity. Do not inherit locality defaults, substitute built-up area or claim a verified guidance value. |
| Pages 10, 16, 18, 28 | Standard subsidy arithmetic is used as an automatic award; property type is used as a proxy for roof ownership/eligibility, and prior subsidized capacity is absent. | Default subsidy to zero. Require an explicitly confirmed amount/source for a newly applied PV measure. Site feasibility and subsidy eligibility remain separate. |

## Reproduced arithmetic

These are independent scalar calculations of the stated savings stream, not execution of the report's TypeScript. All amounts are INR. They are present values of **bill savings before installation, maintenance and replacement costs**, not project NPV or resale predictions.

| Scenario inputs | Report/base-year timing `t` | First-year timing `t−1` | Report's displayed amount |
|---|---:|---:|---:|
| `S=18,000`, `N=10`, `r=0.085`, `e=0.045` | 147,256.10 | 140,914.92 | 143,000, pages 26–27 |
| `S=65,000`, same rates, `N=10` as coded | 531,758.12 | 508,859.45 | Solar case instead claims a 15-year stream |
| `S=65,000`, same rates, `N=15` as solar narrative | 731,477.93 | 699,978.88 | 515,800, pages 28–29 |
| `S=38,000`, `N=10`, same rates | 310,873.98 | 297,487.06 | 302,100, pages 30–31 |

The page 9 closed form is algebraically consistent with `S × sum(((1+e)/(1+r))**t, t=1..N)` when `r != e`; the discrepancy is not a sign error in that algebra. Its equal-rate limit is `N×S` for report timing and `N×S/(1+r)` for first-year timing. Annual summation handles both without dividing by zero. Changing timing is a disclosed interpretation of `S`, not a claim that one can recover the report's inconsistent examples by rounding.

The integrated calculator's financial NPV subtracts incremental capex and operating expenses. The report's displayed “energy NPV” does not subtract those items; the terms must not be used interchangeably.

## Selected source checks

**Pune/Jakarta mismatch.** Report bibliography item 2 links [Sidig, Ratri and Wibowo's Jakarta article, DOI 10.1108/JPIF-10-2023-0089](https://www.researchgate.net/publication/381481759_What_is_the_value_of_green_building_features_An_empirical_analysis_of_green_building_development_in_Jakarta_Indonesia). Its author-associated record identifies Jakarta and a qualitative questionnaire/interview approach. The publisher/DOI endpoint was inaccessible during this audit; the article's full text was not obtained. This supports a source mismatch, not an exhaustive evaluation of that paper.

A genuine [Nallathiga et al. Pune paper is available from Atlantis Press](https://www.atlantis-press.com/article/125968849.pdf), DOI `10.2991/ahsseh.k.220105.002`. Its methodology describes a 2018 survey of 50 projects, 21 green and 29 non-green; the price comparison uses developer offer prices and descriptive area/project means. The inspected paper does not present the controlled hedonic model attributed to it by the report. It concerns bundled project attributes, not a measured causal effect of an individual Hyderabad retrofit. Its headline approximate premium is not adopted as a model coefficient.

**Formal certification.** The [official IGBC Green Homes page](https://www.igbc.in/igbcgreenhomes) describes its own credits, mandatory requirements and certification process. Numerically crossing 70 in this application's different seven-component score provides none of that evidence. No certification status or premium is inferred.

**Scope of reference 7.** [Groh's 2023 dissertation in the University of Regensburg repository](https://epub.uni-regensburg.de/53402/5/Doktorarbeit%20Alexander%20Groh.pdf) discusses green-retrofit economics, including German multifamily asking-rent and retrofit data. It is relevant background for distinguishing energy savings, costs and market effects; it does not supply a fitted Hyderabad capitalization coefficient. Only relevant scope passages were checked, not the dissertation's complete evidence chain.

**Subsidy.** The standard individual-household schedule was checked against official MNRE guidance and a 2026 PIB summary. Eligibility, special-category rates, prior assisted capacity and common-facility arrangements require additional facts. The dated links and limits are in `docs/financial_module.md`; no scheme payment is automatically granted by the app.

Other report claims—including 2026 land-rate revisions, registration/tax percentages, “no published Indian evidence” assertions and all market-rate defaults—were not fully source-validated in this audit and are excluded from the calculator's asserted facts. The report frequently cites `writing-block.md` as reference 1; that item is not an independent empirical data source.

## Implementation-ready contract

1. **Freeze upstream evidence.** Reuse the selected physical scenario and its exact signed grid/LPG/PNG bill trace. No fitting, synthetic-data tuning or external-audit changes occur in the finance integration.
2. **Validate costs by selection.** Require a finite nonnegative incremental cost for every applied action. Missing/blank is unknown, explicit zero is accepted. Ignore and disclose stale unselected quotes. Preserve quote sources and input origin.
3. **Calculate financial cash flows.** Enter integer horizon, discount/escalation assumptions and timing. Apply maintenance as a fixed nominal annual outlay and replacements as entered nominal year-end expenses. Subtract costs once. Retain negative savings. Export each year's escalation exponent, discount factor, cash-flow components and cumulative discounted amount.
4. **Keep subsidy explicit.** Zero is the default. A positive solar subsidy requires an applied new-PV step, confirmation, source and an amount no greater than that PV quote. A published schedule is guidance, not proof of a household claim. The simplified cash flow places confirmed assistance at time zero and discloses the reimbursement-timing omission.
5. **Separate paybacks.** Report the simple ratio's assumptions and an end-year discounted recovery including maintenance/replacements. Discounted recovery must persist through the modeled horizon; a temporary crossing before a later expense is insufficient. Neither is an optimized investment recommendation.
6. **Withhold resale prediction.** Always return unavailable resale-price uplift. The optional sensitivity starts disabled and requires an explicit baseline and explicit user low/high percentages with provenance. Compute only `baseline × entered_percent / 100`; do not derive the premium from savings, NPV, score, solar cost or certification.
7. **Keep status and scope visible.** Financial outputs are `scenario_only`, optional user sensitivity is `hypothetical_only`, and unsupported resale uplift is `unavailable`. Invalid optional sensitivity settings need not erase otherwise valid financial cash flows. No `evidence_supported` property-price label is created.
8. **Verify behavior, not market truth.** Cover signed induction effects, distinct LPG/PNG pricing, stale bill traces, missing quotes versus zero, equal rates, both timing conventions, replacement-induced delayed recovery, no automatic subsidy, optional sensitivity opt-in and JSON-safe invalid inputs. Current application tests are recorded in `reports/verification.txt`; passing them does not validate future savings or resale value.

The corresponding equations and exclusions are documented in `docs/financial_module.md`. Budget optimization, transaction-value model training, financing/tax calculations, full equipment degradation, export remuneration and a live market-rate feed remain outside this implementation.
