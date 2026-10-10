"""PV screening must distinguish conditional estimates from site declarations."""
from copy import deepcopy

import pytest

from greenhome.engine import evaluate_scenario, feasible_retrofits
from greenhome.schema import DEFAULT_HOME


BASELINE = {"annual_grid_kwh": 6000.0, "annual_lpg_kwh": 1000.0,
            "annual_png_kwh": 0.0}


def screened_home(**changes):
    return {**deepcopy(DEFAULT_HOME), "require_site_checks": True,
            "usable_roof_area_m2": 30.0, "solar_shading_ok": True,
            "solar_structure_ok": True, "solar_electrical_ok": True,
            **changes}


def solar_is_candidate(home):
    return any(item["id"] == "solar" for item in feasible_retrofits(home))


def test_passing_preliminary_screen_allows_pv_without_claiming_certification():
    result = evaluate_scenario(screened_home(), BASELINE, ["solar"])
    assert result["applied"] == ["solar"]
    assert result["home_after"]["solar_kw"] == 3.0
    assert result["savings"]["electricity_kwh"] > 0
    assert any("not installation certification" in flag for flag in result["flags"])
    solar = next(item for item in result["recommendations"] if item["id"] == "solar")
    assert "professional" in solar["reason"]
    assert "survey" in solar["reason"]


@pytest.mark.parametrize("area", [None, -1, 0, 29.999, float("nan"),
                                  float("inf"), True, "unknown"])
def test_insufficient_or_unknown_usable_area_blocks_pv(area):
    home = screened_home(usable_roof_area_m2=area)
    result = evaluate_scenario(home, BASELINE, ["solar", "led_lighting"])
    assert "solar" not in result["applied"]
    assert "led_lighting" in result["applied"]
    rejection = next(item for item in result["rejected"] if item["id"] == "solar")
    assert "roof area" in rejection["reason"]
    assert all(item["id"] != "solar" for item in result["recommendations"])
    assert "solar" not in result["recommended_package"]["applied"]


def test_missing_area_is_unknown_and_exact_threshold_is_allowed():
    home = screened_home()
    del home["usable_roof_area_m2"]
    assert not solar_is_candidate(home)
    assert solar_is_candidate(screened_home(usable_roof_area_m2=30))
    assert solar_is_candidate(screened_home(usable_roof_area_m2=35))


@pytest.mark.parametrize("field", ["solar_shading_ok", "solar_structure_ok",
                                   "solar_electrical_ok"])
@pytest.mark.parametrize("value", [False, None, 1, "yes"])
def test_site_suitability_requires_affirmative_boolean_declaration(field, value):
    home = screened_home(**{field: value})
    original = deepcopy(home)
    result = evaluate_scenario(home, BASELINE, ["solar"])
    assert result["applied"] == []
    assert result["after"] == result["baseline"]
    assert result["savings"]["total_kwh"] == 0
    assert "unconfirmed" in result["rejected"][0]["reason"]
    assert home == original


def test_screen_reports_all_missing_evidence_together():
    home = screened_home()
    for field in ("usable_roof_area_m2", "solar_shading_ok",
                  "solar_structure_ok", "solar_electrical_ok"):
        del home[field]
    result = evaluate_scenario(home, BASELINE, ["solar"])
    reason = result["rejected"][0]["reason"]
    for evidence in ("roof area", "shading", "structural", "electrical"):
        assert evidence in reason


@pytest.mark.parametrize("invalid_policy", [None, 0, 1, "false", "true", [], {}])
def test_malformed_site_check_policy_cannot_bypass_screen(invalid_policy):
    home = screened_home(require_site_checks=invalid_policy)
    result = evaluate_scenario(home, BASELINE, ["solar"])
    assert not solar_is_candidate(home)
    assert result["applied"] == []
    assert "must be a boolean" in result["rejected"][0]["reason"]
    assert any("blocked" in flag for flag in result["flags"])


@pytest.mark.parametrize("policy_present", [False, True])
def test_legacy_calls_preserve_conditional_pv_estimates(policy_present):
    home = deepcopy(DEFAULT_HOME)
    if policy_present:
        home["require_site_checks"] = False
    result = evaluate_scenario(home, BASELINE, ["solar"])
    assert result["applied"] == ["solar"]
    assert any("feasibility remains conditional" in flag for flag in result["flags"])
    solar = next(item for item in result["recommendations"] if item["id"] == "solar")
    assert "conditional" in solar["reason"]


@pytest.mark.parametrize("constraint,value,reason", [
    ("roof_access", False, "Roof access"),
    ("roof_access", None, "Roof access"),
    ("retrofit_consent", False, "consent"),
    ("heritage_restricted", True, "Heritage"),
    ("heritage_restricted", None, "Heritage"),
])
def test_passing_site_screen_never_overrides_existing_permissions(constraint, value, reason):
    result = evaluate_scenario(screened_home(**{constraint: value}), BASELINE, ["solar"])
    assert result["applied"] == []
    assert reason in result["rejected"][0]["reason"]


def test_existing_pv_is_not_expanded_by_new_system_site_screen():
    result = evaluate_scenario(screened_home(solar_kw=1.0), BASELINE, ["solar"])
    assert result["applied"] == []
    assert result["home_after"]["solar_kw"] == 1.0
    assert "already installed" in result["rejected"][0]["reason"]
