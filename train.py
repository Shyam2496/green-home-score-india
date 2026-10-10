"""Train and evaluate the reproducible synthetic baseline energy models."""
import argparse
import json
from pathlib import Path

from greenhome.ml import train_models


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--data-csv", type=Path, default=None, help="Observed annual demand/LPG/PNG rows with complete model features and group IDs")
    parser.add_argument("--provenance-json", type=Path, default=None, help="Explicit source, license, units, period and target definitions")
    args = parser.parse_args()
    report = train_models(root=args.root, n=args.rows, seed=args.seed, data_csv=args.data_csv, provenance_json=args.provenance_json)
    summary = {target: {"selected": info["selected"], "validation": info["validation"], "test": info["test"]}
               for target, info in report["models"].items()}
    print(json.dumps(summary, indent=2))
    print("Data origin:", report["data_origin"])
    print("Bundled household labels are synthetic; these metrics do not establish real-home accuracy.")


if __name__ == "__main__":
    main()
