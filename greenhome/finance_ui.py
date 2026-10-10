"""Streamlit controls for explicit, downstream financial scenarios."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .finance import calculate_financial_scenario

PROPERTY_VALUE_DEFERRAL = (
    "Property-value impact is deferred for this prototype. We do not have verified Hyderabad "
    "sale-price data linked to known retrofits and comparable property characteristics to validate "
    "a resale premium. Discounted energy-bill savings describe a financial scenario; they do not "
    "establish how much more a buyer would pay. Bill savings, installation costs and payback remain available."
)
PROPERTY_VALUE_SCOPE = {
    "status": "deferred", "prediction_status": "unavailable",
    "reason": PROPERTY_VALUE_DEFERRAL,
    "hypothetical_premium_controls_enabled": False,
}


def render_financial_scenario(scenario, bill_trace, *, baseline_source):
    """Return exactly the calculation shown, including unavailable inputs."""
    st.subheader("Costs and discounted bill savings")
    st.write("Use the selected what-if package from the Retrofit planner. Its signed electricity, LPG and PNG savings supply the bill calculation below.")
    st.caption(f"Energy baseline: {baseline_source}. Retrofit savings remain modeled estimates. Enter incremental installation costs for this package, including applicable taxes and installation work.")
    with st.expander("Why property-value impact is deferred"):
        st.write(PROPERTY_VALUE_DEFERRAL)
    if not st.checkbox("Calculate a financial scenario", key="finance_enabled"):
        st.info("Choose improvements, then enable the calculator and enter their costs. No installation price or subsidy is assumed.")
        return {"status": "not_requested", "project_economics": None, "report_value_scenario": None,
                "resale_value_prediction": {"status": "unavailable", "reason": PROPERTY_VALUE_DEFERRAL},
                "property_value_scope": dict(PROPERTY_VALUE_SCOPE)}

    applied = scenario.get("applied") or []
    labels = {row["id"]: row["name"] for row in scenario.get("recommendations", [])}
    if not applied:
        st.info("Select at least one feasible improvement in the Retrofit planner to assess its installation economics.")
    else:
        st.write("**Package being assessed:** " + " → ".join(labels.get(item, item) for item in applied))

    st.write("**Incremental installation costs**")
    st.caption("Blank means unknown. Enter zero only for an improvement with no incremental cost. Existing equipment is excluded. Changing the package recalculates costs and cash flows using only the improvements currently applied.")
    costs = {}
    columns = st.columns(2)
    for i, item in enumerate(applied):
        with columns[i % 2]:
            costs[item] = st.number_input(f"{labels.get(item, item)} — installed cost (₹)", min_value=0.0, max_value=100000000.0, value=None, step=1000.0, key=f"finance_cost_{item}")
    cost_source = st.text_input("Cost source / quote reference", value="User-entered estimates; not independently verified quotes", key="finance_cost_source")

    st.write("**Cash-flow assumptions**")
    st.caption("The starting 8.5% discount and 4.5% tariff escalation rates come from the supplied calculator. They are editable scenario assumptions, not current market forecasts. The horizon must stay within the effective life you assume for the package.")
    c1, c2, c3 = st.columns(3)
    years = c1.number_input("Analysis horizon (years)", min_value=1, max_value=50, value=10, key="finance_years")
    discount = c2.number_input("Discount rate (%/year)", min_value=0.0, max_value=50.0, value=8.5, step=0.5, key="finance_discount") / 100
    escalation = c3.number_input("Tariff escalation (%/year)", min_value=-20.0, max_value=50.0, value=4.5, step=0.5, key="finance_escalation") / 100
    timing_labels = {"Entered saving is the first-year amount": "first_year", "Report convention: escalate before year 1": "report_base_year"}
    timing_choice = st.selectbox("Savings timing", list(timing_labels), key="finance_timing")
    st.caption("All annual cash flows occur at year end. The first option keeps today's modeled saving in year 1 and escalates from year 2; the report convention escalates it in year 1 as well.")
    maintenance = st.number_input("Additional annual maintenance (₹/year)", min_value=0.0, max_value=10000000.0, value=0.0, step=500.0, key="finance_maintenance")
    st.caption("Maintenance is a constant nominal annual amount. Zero assumes no additional maintenance; it does not establish that equipment has no running or service costs.")
    replacements = []
    if st.checkbox("Include a replacement expense", key="finance_replacement_enabled"):
        r1, r2 = st.columns(2)
        # Keep an entered year valid when the analysis horizon is shortened.
        if st.session_state.get("finance_replacement_year", 1) > years:
            st.session_state["finance_replacement_year"] = int(years)
        replacement_year = r1.number_input("Replacement year", min_value=1, max_value=int(years), value=min(8, int(years)), key="finance_replacement_year")
        replacement_cost = r2.number_input("Replacement cost in that year's rupees (₹)", min_value=0.0, max_value=100000000.0, value=None, step=1000.0, key="finance_replacement_cost")
        replacement_source = st.text_input("Replacement assumption / source", key="finance_replacement_source")
        replacements.append({"year": replacement_year, "cost_inr": replacement_cost, "source": replacement_source})

    subsidy, subsidy_confirmed, subsidy_source = 0.0, False, "No subsidy assumed"
    if "solar" in applied:
        with st.expander("Solar subsidy", expanded=False):
            st.caption("The energy engine's new PV option is 3 kW. The standard central residential schedule may reach ₹78,000 for 3 kW, subject to scheme rules and approval. This calculator does not check eligibility or automatically award a subsidy.")
            st.markdown("[Official MNRE central subsidy guidelines](https://cdnbbsr.s3waas.gov.in/s3716e1b8c6cd17b771da77391355749f3/uploads/2024/07/202407021768035484.pdf)")
            st.caption("Standard individual-household schedule checked 10 October 2026. Special-category areas, shared installations and prior subsidy history can have different rules. Our solar site screen does not establish subsidy eligibility.")
            subsidy_confirmed = st.checkbox("I have a confirmed subsidy amount for this new installation", key="finance_subsidy_confirmed")
            if subsidy_confirmed:
                subsidy = st.number_input("Confirmed solar subsidy (₹)", min_value=0.0, max_value=100000000.0, value=None, step=1000.0, key="finance_subsidy")
                subsidy_source = st.text_input("Subsidy approval / confirmation reference", key="finance_subsidy_source")
            st.caption("A confirmed amount is treated as reducing cost at time zero. If reimbursement arrives later, this simplification can overstate its present value. Existing PV receives no new subsidy or asset credit.")

    calculation = calculate_financial_scenario(
        scenario, bill_trace, costs, years=int(years), discount_rate=discount,
        escalation_rate=escalation, timing=timing_labels[timing_choice],
        annual_maintenance_inr=maintenance, replacements=replacements,
        solar_subsidy_inr=subsidy, solar_subsidy_confirmed=subsidy_confirmed,
        solar_subsidy_source=subsidy_source, cost_provenance=cost_source,
        value_scenario=None,
    )
    calculation["property_value_scope"] = dict(PROPERTY_VALUE_SCOPE)
    calculation["resale_value_prediction"] = {"status": "unavailable", "reason": PROPERTY_VALUE_DEFERRAL}
    for error in calculation.get("errors", []):
        st.info(error["message"])
    for error in calculation.get("valuation_errors", []):
        st.info(error["message"])
    economics = calculation.get("project_economics")
    if economics:
        st.divider()
        st.subheader("Selected package economics")
        c1, c2, c3 = st.columns(3)
        c1.metric("Net installation cost", f"₹{economics['net_initial_cost_inr']:,.0f}")
        c2.metric("Present value of bill savings", f"₹{economics['present_value_bill_savings_inr']:,.0f}")
        c3.metric("Discounted net benefit", f"₹{economics['discounted_net_benefit_inr']:,.0f}")
        st.caption("Discounted net benefit = present value of bill savings − maintenance − replacement expenses − net installation cost. Positive does not guarantee a return; no resale uplift or export revenue is included.")
        for key, label in (("simple_payback", "Simple payback"), ("discounted_payback", "Discounted payback")):
            payback = economics[key]
            if payback.get("status") == "reached" and payback.get("years") is not None:
                st.write(f"**{label}:** {payback['years']:,.2f} years.")
            elif payback.get("years") is not None:
                st.write(f"**{label}:** {payback['years']:,.2f} years by the simple ratio, beyond the {years}-year analysis horizon.")
            else:
                st.write(f"**{label}:** not reached within the {years}-year analysis horizon.")
        st.caption("Simple payback uses un-escalated annual savings less annual maintenance and excludes replacements. Discounted payback is the first year-end recovery that remains non-negative through the modeled horizon, including replacements. It provides no assurance beyond that horizon.")
        with st.expander("Annual cash flows and calculation record"):
            cashflows = pd.DataFrame(calculation.get("annual_cashflows", [])).rename(columns={
                "year": "Year", "bill_savings_inr": "Bill saving (₹)",
                "maintenance_inr": "Maintenance (₹)", "replacement_inr": "Replacement (₹)",
                "net_operating_cashflow_inr": "Net cash flow (₹)",
                "discounted_net_cashflow_inr": "Discounted net cash flow (₹)",
                "cumulative_discounted_net_inr": "Cumulative discounted balance (₹)",
            })
            cashflow_columns = ["Year", "Bill saving (₹)", "Maintenance (₹)", "Replacement (₹)", "Net cash flow (₹)", "Discounted net cash flow (₹)", "Cumulative discounted balance (₹)"]
            st.dataframe(cashflows[cashflow_columns].round(2), hide_index=True, width="stretch")
            st.write("**Separate fuel bill terms**")
            st.dataframe(pd.DataFrame(bill_trace.get("terms", [])).round(2), hide_index=True, width="stretch")
            st.json(calculation, expanded=False)
    else:
        st.caption("Installation economics are withheld until required package costs and cash-flow inputs are valid.")

    for disclosure in calculation.get("disclosures", []):
        st.caption(disclosure)
    return calculation
