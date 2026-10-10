"""Objective-aware retrofit decisions over the existing scenario calculations.

The energy, score, fuel-switch, carbon and PV equations remain in engine.py.
This module ranks signed standalone effects, then greedily adds the candidate
with the largest positive change in the whole package's chosen objective.
Every proposed package is rerun in the engine's canonical installation order,
so interacting savings are never added together. This is a transparent greedy
heuristic, not a global optimum, financial appraisal or validated causal model.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math

from .billing import bill_savings_trace
from .engine import RETROFITS, evaluate_scenario


OBJECTIVES = {
    "bill_savings": {"label": "Annual bill savings", "unit": "INR/year"},
    "energy_savings": {"label": "Purchased-energy savings", "unit": "kWh/year"},
    "carbon_savings": {"label": "Operational CO2 savings", "unit": "kg CO2/year"},
}

_LIMITATIONS = [
    "Priorities use illustrative retrofit effects and inferred end-use shares; annual bills do not measure individual end uses or validate retrofit savings.",
    "A greedy positive-increment heuristic is used, not an exhaustive global optimization. Interactions can change priorities.",
    "No installation costs, budget, payback, net present value or property-price uplift are assumed.",
    "Bill savings use flat entered rates, without slabs, fixed charges, taxes or export credits.",
    "Operational CO2 is separate from complete lifecycle CO2e; site assessments and permissions are still required.",
    "PV eligibility requires declared usable roof area and positive shading, structural and electrical checks; declarations are not independently verified surveys.",
]


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _bill(savings, tariffs):
    rates = tariffs if isinstance(tariffs, Mapping) else {}
    return bill_savings_trace(
        savings, electricity_rate=rates.get("electricity_rate"),
        lpg_price_kg=rates.get("lpg_price_kg"), png_rate=rates.get("png_rate"),
    )


def _objective_value(savings, objective, tariffs):
    if objective == "bill_savings":
        trace = _bill(savings, tariffs)
        return trace["total_inr_per_year"], trace.get("reason")
    key = {"energy_savings": "total_kwh", "carbon_savings": "carbon_kg"}.get(objective)
    value = savings.get(key) if key else None
    if not _finite(value):
        reason = ("Valid fuel-specific emission factors are required for carbon priorities."
                  if objective == "carbon_savings"
                  else "Valid household inputs and annual energy totals are required for priorities.")
        return None, reason
    return value, None


def recommend_retrofits(home, energy, *, objective="bill_savings", tariffs=None, factors=None):
    """Return signed candidate rankings and an interaction-aware suggested package.

    ``energy`` may be declared annual consumption; no fitted model is loaded.
    ``tariffs`` must supply ``electricity_rate`` (INR/kWh), ``lpg_price_kg``
    (INR/kg), and ``png_rate`` (INR/net-CV kWh) for bill priorities. Missing or
    invalid rates withhold bill priorities. Energy and carbon objectives remain
    independent of bill rates; invalid carbon factors only withhold carbon
    priorities. Core household/energy errors withhold all priorities.

    ``ranked_candidates`` sorts standalone objective effects; a negative row
    can still enter the package if its incremental package effect becomes
    positive after other actions. ``decision_incremental_benefit`` is that
    whole-package change at selection time. ``package_marginal_savings`` is
    instead its final canonical installation-order marginal. They are separate
    comparisons and must not be substituted for one another.

    ``decision_audit`` retains every candidate package considered per round.
    ``selected_ids`` and the returned ``scenario`` follow fixed engine stage
    order, regardless of the greedy decision order. Standalone effects must
    not be summed. Feasibility rejections include every known retrofit ID.
    This public decision API always requires the engine's explicit PV site
    checks, even if a caller passes require_site_checks=False. It never edits
    the caller's household mapping.
    """
    home = deepcopy(dict(home)) if isinstance(home, Mapping) else {}
    home["require_site_checks"] = True
    known_ids = [item["id"] for item in RETROFITS]
    # All IDs are requested solely to expose each blocked candidate's reason.
    all_candidates = evaluate_scenario(home, energy, known_ids, factors=factors)
    current = evaluate_scenario(home, energy, [], factors=factors)
    valid_objective = isinstance(objective, str) and objective in OBJECTIVES
    reasons = []
    if not valid_objective:
        reasons.append("Choose bill_savings, energy_savings or carbon_savings as the objective.")
    if current["calculation_trace"]["status"] != "available":
        reasons.extend(current["calculation_trace"].get("reasons", []))
    current_value, objective_reason = (_objective_value(current["savings"], objective, tariffs)
                                       if valid_objective else (None, None))
    if objective_reason:
        reasons.append(objective_reason)

    rows = []
    for item in current["recommendations"]:
        benefit, reason = (_objective_value(item["standalone_savings"], objective, tariffs)
                           if valid_objective else (None, reasons[0]))
        rows.append({
            "id": item["id"], "name": item["name"], "stage": item["stage"],
            "suitability": item["suitability"], "feasibility_reason": item["reason"],
            "standalone_savings": deepcopy(item["standalone_savings"]),
            "standalone_trace": deepcopy(item["standalone_trace"]),
            "standalone_bill_trace": _bill(item["standalone_savings"], tariffs),
            "objective_benefit": benefit, "objective_unavailable_reason": reason,
            "rank": None, "selected": False, "selection_round": None,
            "decision_incremental_benefit": None,
            "final_addition_objective_benefit": None,
            "package_marginal_savings": None,
            "package_marginal_objective_benefit": None,
            "package_marginal_trace": None,
            "selection_reason": "Priority unavailable until the relevant inputs are valid." if reasons else "Not yet evaluated in a package.",
        })
    if valid_objective and not reasons and any(row["objective_benefit"] is None for row in rows):
        reasons.append("Some candidate objective values are unavailable; priorities are withheld rather than comparing incomplete values.")
    available = not reasons and current_value is not None
    if not available:
        for row in rows:
            row["selection_reason"] = "Priority unavailable until the relevant inputs are valid."
    rows.sort(key=lambda row: (row["objective_benefit"] is None,
                              -row["objective_benefit"] if row["objective_benefit"] is not None else 0,
                              row["stage"], row["id"]))
    if available:
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank

    selected = []
    audit = []
    row_by_id = {row["id"]: row for row in rows}
    # A proposed package can recur; reuse its actual evaluated scenario.
    scenarios = {(): current}
    canonical_ids = [item["id"] for item in RETROFITS]
    if available:
        while True:
            evaluations = []
            for item in sorted(rows, key=lambda row: (row["stage"], row["id"])):
                if item["id"] in selected:
                    continue
                package = tuple(action for action in canonical_ids if action in selected or action == item["id"])
                if package not in scenarios:
                    scenarios[package] = evaluate_scenario(home, energy, list(package), factors=factors)
                scenario = scenarios[package]
                package_value, reason = _objective_value(scenario["savings"], objective, tariffs)
                incremental = package_value - current_value if package_value is not None else None
                if incremental is not None and not math.isfinite(incremental):
                    incremental, reason = None, "Incremental objective exceeds the supported numeric range."
                row_by_id[item["id"]]["final_addition_objective_benefit"] = incremental
                evaluations.append({
                    "id": item["id"], "stage": item["stage"],
                    "proposed_ids": list(package), "package_objective_benefit": package_value,
                    "incremental_objective_benefit": incremental,
                    "package_savings": deepcopy(scenario["savings"]),
                    "package_bill_trace": _bill(scenario["savings"], tariffs),
                    "unavailable_reason": reason,
                })
            positive = [item for item in evaluations if item["incremental_objective_benefit"] is not None
                        and item["incremental_objective_benefit"] > 0]
            winner = min(positive, key=lambda item: (-item["incremental_objective_benefit"], item["stage"], item["id"])) if positive else None
            audit.append({
                "round": len(audit) + 1, "current_ids": list(current["applied"]),
                "current_objective_benefit": current_value,
                "evaluations": evaluations,
                "chosen_id": winner["id"] if winner else None,
                "reason": "Largest strictly positive incremental objective benefit; ties use stage then ID." if winner else "No remaining feasible candidate has a strictly positive incremental objective benefit.",
            })
            if winner is None:
                break
            selected.append(winner["id"])
            current = scenarios[tuple(winner["proposed_ids"])]
            current_value = winner["package_objective_benefit"]
            row = row_by_id[winner["id"]]
            row.update({"selected": True, "selection_round": len(audit),
                        "decision_incremental_benefit": winner["incremental_objective_benefit"],
                        "final_addition_objective_benefit": None,
                        "selection_reason": "Selected for a strictly positive incremental benefit to the chosen package objective; verify site suitability."})
        final_rows = {item["id"]: item for item in current["recommendations"]}
        for row in rows:
            if row["selected"]:
                result = final_rows[row["id"]]
                marginal = result["sequential_savings"]
                marginal_value, _ = _objective_value(marginal, objective, tariffs)
                row.update({"package_marginal_savings": deepcopy(marginal),
                            "package_marginal_objective_benefit": marginal_value,
                            "package_marginal_trace": deepcopy(result["selected_marginal_trace"])})
            else:
                row["selection_reason"] = ("Not selected: adding it to the suggested package does not improve the chosen objective. Signed standalone effects remain visible."
                                           if row["final_addition_objective_benefit"] is not None
                                           else "Not selected: its incremental objective is unavailable.")

    return {
        "schema_version": "1.0", "status": "available" if available else "unavailable",
        "objective": objective if isinstance(objective, str) else None,
        "objective_label": OBJECTIVES[objective]["label"] if valid_objective else None,
        "objective_unit": OBJECTIVES[objective]["unit"] if valid_objective else None,
        "reasons": list(dict.fromkeys(reasons)), "ranked_candidates": rows,
        "selected_ids": list(current["applied"]), "scenario": current,
        "package_objective_benefit": current_value if available else None,
        "package_bill_trace": _bill(current["savings"], tariffs),
        "rejected": deepcopy(all_candidates["rejected"]), "decision_audit": audit,
        "assumed_inputs": deepcopy(current["calculation_trace"]["anchor"].get("assumed_inputs", {})),
        "flags": deepcopy(current["flags"]),
        "method": "Greedy largest positive whole-package increment; each package rerun in fixed engine stage order; standalone ranking is separate.",
        "limitations": list(_LIMITATIONS),
    }
