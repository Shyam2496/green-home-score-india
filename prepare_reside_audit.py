"""Extract only published anonymous survey fields for external sanity checks."""
import hashlib
import argparse
import json
from pathlib import Path
import zipfile

import pandas as pd

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive", type=Path, help="Downloaded original RESIDE-AC v3 dataset.zip")
args = parser.parse_args()
ARCHIVE = args.archive
DEST = Path(__file__).resolve().parent / "data"
DEST.mkdir(parents=True, exist_ok=True)
SOURCE = "https://doi.org/10.6084/m9.figshare.16869439.v3"
PAPER = "https://doi.org/10.1186/s42162-022-00225-4"
with zipfile.ZipFile(ARCHIVE) as archive:
    folder = "dataset/Household information/"
    dwelling = pd.read_csv(archive.open(folder + "DwellingDetails.csv"))
    building = pd.read_csv(archive.open(folder + "buildingdetails.csv"))
    ac = pd.read_csv(archive.open(folder + "ACDetails.csv"))
    joined = dwelling.merge(building, on="HouseID", validate="one_to_one").merge(ac, on="HouseID", validate="one_to_one")
    rows = []
    for _, row in joined.iterrows():
        source_id = int(row["HouseID"])
        monitoring = pd.read_csv(archive.open(f"dataset/Garud/G{source_id:02d}.csv"))
        timestamps = pd.to_datetime(monitoring["datetime"], dayfirst=True)
        monitored_days = (timestamps.max() - timestamps.min()).total_seconds() / 86400 + 1 / 1440
        rows.append({
            "home_id": f"RESIDE-AC-{source_id:02d}",
            "source_house_id": source_id,
            "city": "Hyderabad",
            "area_m2": float(row["area(sqm)"]),
            "occupants": int(row["occupants(#)"]),
            "property_type": {"stand-alone home": "independent", "tenemant": "apartment"}.get(str(row["Dwelling type"]).strip(), ""),
            "property_type_source": str(row["Dwelling type"]),
            "property_type_mapping_note": "stand-alone home to independent; source spelling tenemant to apartment proxy, consistent with paper's low-rise flat category",
            "ac_units": int(row["AC(#)"]),
            "annual_grid_kwh_observed": float(row["Annual Electricity Consumption (kWh)"]),
            "annual_label_unit": "kWh/year (electricity bills)",
            "annual_label_period_known": False,
            "primary_ac_type_observed": str(row["primary AC type"]),
            "primary_ac_tonnage_observed": float(row["primary AC tonnage"]),
            "primary_ac_star_rating_observed": row["primary AC star rating"],
            "primary_ac_setpoint_c_observed": float(row["primary AC setpoint as given by homeowner (oC)"]),
            "primary_ac_hours_per_day_summer_observed": float(monitoring["AC Status"].mean() * 24),
            "electric_geyser_count_observed": int(row["Electric Geyser(#)"]),
            "refrigerator_count_observed": int(row["Refrigerator(#)"]),
            "water_pump_count_observed": int(row["Water pump(#)"]),
            "monitored_start_ist": timestamps.min().isoformat(),
            "monitored_end_ist": timestamps.max().isoformat(),
            "monitored_days": monitored_days,
            "observed_model_features": "city;area_m2;occupants;property_type;ac_units",
            "unobserved_critical_fields": "solar_kw;insulation;glazing;led_fraction;smart_controls;annual_ac_usage;roof_exposure;cooking_fuel;lpg_kwh;png_kwh;all_ac_efficiencies;hot_water_service",
            "source_doi": SOURCE,
            "paper_doi": PAPER,
            "data_license": "CC0 1.0",
            "data_origin": "real_external_audit_only",
        })
output = pd.DataFrame(rows).sort_values("home_id")
output.to_csv(DEST / "reside_ac_external_audit.csv", index=False)
manifest = {
    "source_doi": SOURCE, "paper_doi": PAPER,
    "authors": "Dharani Tejaswini, Pavan Ramapragada, Sraavani Gundepudi, Prabhakar Rao Kandukuri, Vishal Garg, Jyotirmay Mathur, Rajat Gupta",
    "dataset_license": "CC0 1.0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "paper_license": "CC BY 4.0", "retrieved_date": "2026-10-10",
    "archive_file_id": 38686209,
    "archive_md5": hashlib.md5(ARCHIVE.read_bytes()).hexdigest(),
    "archive_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
    "n_homes": len(output),
    "annual_label_summary_kwh": output.annual_grid_kwh_observed.describe().to_dict(),
    "observed_model_fields": ["city", "area_m2", "occupants", "property_type", "ac_units"],
    "no_training": True,
    "limitations": [
        "Eleven selected AC-using Hyderabad dwellings cannot establish nationwide or prospective accuracy.",
        "Annual electricity bill period and year are not specified in the survey file.",
        "Figshare description says May 2021; the downloaded monitoring timestamps say May 2019. The conflict is preserved.",
        "AC metadata and monitored AC status describe the primary AC, not necessarily every AC unit in a home.",
        "Summer primary-AC runtime is not a measured annual-use feature; do not silently map it to annual usage.",
        "Solar generation/exports and LPG/PNG are not labeled; electricity bill labels are not asserted gross demand.",
        "Missing model features must remain marked as assumed in any scenario-based external sanity check.",
        "Property type tenemant is mapped to an apartment proxy; original source spelling is retained.",
        "No household identifiers are joined to addresses or private data. Income fields are not copied.",
    ],
}
(DEST / "reside_ac_external_audit_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(f"Wrote {len(output)} audit-only homes; no fitting performed.")
print(output[["home_id", "property_type", "area_m2", "annual_grid_kwh_observed"]].to_string(index=False))
