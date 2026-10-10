# Prototype review readiness

Checked 10 October 2026. This application is ready for a functional prototype review. It is not a fully validated service or a completed implementation of every requirement in the original PS2 brief.

## Working review scope

- Household input validation and complete-year bill anchoring, with a clearly labeled fictional demonstration.
- Seven-component Green Home Score and efficiency classification, using documented India adaptations.
- Goal-based, feasibility-aware retrofit recommendations and interaction-aware what-if packages.
- Separate electricity, LPG and PNG savings; signed operational CO2 and bill calculations.
- Installation costs, maintenance/replacement assumptions, discounted financial cash flows and payback.
- Computed explanations, optional grounded LLM fact selection, numerical traces and scenario export.
- Source, data preparation and training scripts, fitted artifacts, architecture, model/evaluation reports, held-out predictions and Responsible AI notes.

The current full test run passed **327 tests in 35.09 seconds**. These checks establish software behavior and consistency; they do not establish real-house predictive accuracy, actual retrofit savings or future financial returns. Recorded training and external-audit artifacts remain frozen.

The six pinned dependency releases were checked against official PyPI metadata and are publicly available. Python **3.12** is the tested runtime and is required by the NumPy pin. A clean installation on a separate reviewer's machine has not been verified; follow the packaged setup instructions and report any environment-specific failure.

## Disclosures for the reviewer

1. **Property-value impact is deferred by design.** No resale estimate or premium control is offered. It remains a gap against the brief's property-value requirement. The explanation is in `docs/property_value_scope.md`.
2. **Real-house performance remains unproven.** Training labels are synthetic, and the physical baseline won model selection. The independent, default-filled eleven-home Hyderabad check has approximately 2,350 kWh/year electricity MAE. Actual bills anchor the demonstration but do not validate inferred end-use shares or future retrofit effects.
3. **Carbon is operational CO2.** Full CO2e coverage is outside the present implementation.
4. **Live GenAI targets are not demonstrated.** Offline grounding and failure handling are tested. A recorded live-provider evaluation against the brief's groundedness, factual-accuracy and unsupported-claim targets is still required.
5. **Technology coverage is limited.** Heat-pump water heating is a baseline input, not a selectable retrofit; the pilot does not cover every possible heating, glazing or shading alternative. Goal-based recommendations are not budget or investment optimization.

Synthetic data are permitted by the brief, but synthetic tests must be described as such. The optional memory extension is not implemented and is not a prerequisite for reviewing the core prototype.

## Suggested review walkthrough

1. Follow `README.md` to start the local dashboard. Choose **Try fictional sample** for the initial walkthrough.
2. Inspect the score and documented assumptions. Change installation constraints and review blocked measures.
3. Choose a recommendation goal, apply the suggested package and compare individual savings with package interactions. Inspect the induction fuel-switch tradeoff.
4. In **Costs & payback**, enter illustrative costs with fictional provenance. Inspect missing-cost handling, cash flows and payback.
5. Show the property-value deferral explanation, model evidence and external audit. Download the current scenario to inspect its inputs, calculations and scope.

Submit this as an **India-focused hackathon prototype for review**, with the disclosures above. Review readiness does not imply full brief compliance or guarantee acceptance by the organisers.
