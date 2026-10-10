"""Frozen, partial-feature RESIDE-AC sanity check. No training or tuning here."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from greenhome.ml import load_models, predict_energy, prediction_intervals
from greenhome.physics import input_assumptions
from greenhome.schema import DEFAULT_HOME


def main():
    root = Path(__file__).resolve().parent
    models = load_models(root)
    data_path = root / 'data' / 'reside_ac_external_audit.csv'
    data = pd.read_csv(data_path)
    rows = []
    for original in data.to_dict('records'):
        known = {key: original[key] for key in ['area_m2', 'occupants', 'city', 'property_type', 'ac_units']}
        known['occupants'] = int(known['occupants'])
        known['ac_units'] = int(known['ac_units'])
        # Remaining values are fixed defaults decided before reading bill labels.
        # Primary-AC summer runtime/2019 star label cannot describe all-AC annual use.
        home = {**DEFAULT_HOME, **known}
        prediction = predict_energy(home, models)
        intervals = prediction_intervals(home, prediction, models)
        assumed = {**{key: value for key, value in DEFAULT_HOME.items() if key not in known}, **input_assumptions(home)}
        actual = float(original['annual_grid_kwh_observed'])
        lo, hi = intervals['annual_grid_kwh']
        rows.append({
            'home_id': original['home_id'], 'observed_grid_kwh': actual,
            'predicted_grid_kwh_with_defaults': prediction['annual_grid_kwh'],
            'error_kwh': prediction['annual_grid_kwh'] - actual,
            'absolute_error_kwh': abs(prediction['annual_grid_kwh'] - actual),
            'synthetic_interval_lower_kwh': lo, 'synthetic_interval_upper_kwh': hi,
            'observed_in_synthetic_interval': lo <= actual <= hi,
            'observed_feature_names': ';'.join(known),
            'assumed_inputs_json': json.dumps(assumed, sort_keys=True),
        })
    output = pd.DataFrame(rows)
    error = output['error_kwh'].to_numpy()
    observed = output['observed_grid_kwh'].to_numpy()
    denominator = np.sum((observed - observed.mean()) ** 2)
    summary = {
        'scope': 'Frozen partial-feature sanity check, not full-feature accuracy validation',
        'n_homes': len(output), 'mae_kwh': float(np.mean(np.abs(error))),
        'rmse_kwh': float(np.sqrt(np.mean(error ** 2))),
        'mean_bias_kwh': float(np.mean(error)),
        'r2_partial_feature_check': float(1 - np.sum(error ** 2) / denominator) if denominator > 0 else None,
        'mean_observed_grid_kwh': float(observed.mean()),
        'mean_predicted_grid_kwh': float(output['predicted_grid_kwh_with_defaults'].mean()),
        'empirical_synthetic_interval_coverage': float(output['observed_in_synthetic_interval'].mean()),
    }
    mae = summary['mae_kwh']
    report = {
        'summary': f"{len(output)} public RESIDE-AC Hyderabad homes, using only five mapped household inputs and fixed defaults: electricity MAE {mae:,.0f} kWh/year. Missing annual usage, solar and fabric details, and an unknown bill year prevent a full-feature accuracy claim.",
        'metrics': summary,
        'model_metadata_sha256': hashlib.sha256((root / 'models' / 'metadata.json').read_bytes()).hexdigest(),
        'external_csv_sha256': hashlib.sha256(data_path.read_bytes()).hexdigest(),
        'source_doi': 'https://doi.org/10.6084/m9.figshare.16869439.v3',
        'paper_doi': 'https://doi.org/10.1186/s42162-022-00225-4',
        'license': 'CC0 1.0',
        'used_for_training_selection_calibration_or_tuning': False,
        'input_policy': 'Only area, occupants, property type, city and AC count mapped. All other values fixed from documented defaults. No tuning against the observed labels.',
        'limitations': [
            '11 homes from one city are too few and too narrow for national validation.',
            'Labels are annual electricity bill imports; solar presence and gross demand are unknown.',
            'Bill observation year is unknown; physics uses 2024 grid weather.',
            'Primary AC May2019 runtime and star rating are not annual all-AC usage/ISEER.',
            'No measured LPG or PNG labels; neither fuel is externally evaluated.',
            'Synthetic conformal intervals have no guaranteed real-house coverage.',
            'Paper/timestamps indicate May2019; repository description says May2021.',
        ],
    }
    (root / 'reports').mkdir(exist_ok=True)
    output.to_csv(root / 'reports' / 'external_audit_predictions.csv', index=False)
    (root / 'reports' / 'external_audit.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(report['summary'])


if __name__ == '__main__':
    main()
