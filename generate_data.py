"""Generate the explicitly synthetic prototype dataset."""
import argparse
from pathlib import Path

from greenhome.ml import generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data" / "synthetic_homes.csv")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    generate_dataset(n=args.rows, seed=args.seed).to_csv(args.output, index=False)
    print(f"Wrote {args.rows:,} synthetic homes to {args.output}")


if __name__ == "__main__":
    main()
