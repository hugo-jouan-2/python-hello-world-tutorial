"""Entry point: run the dispatch on a CSV of hourly prices and print the result."""

from __future__ import annotations

import argparse
from pathlib import Path

from power_dispatch.dispatch import State, dispatch_day, load_prices, summarize

DEFAULT_PRICES_PATH = Path(__file__).resolve().parents[2] / "data" / "prices.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate the hourly dispatch of a power plant.")
    parser.add_argument(
        "prices",
        nargs="?",
        type=Path,
        default=DEFAULT_PRICES_PATH,
        help="CSV file with columns hour,price_eur_per_mwh",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="HOUR=STATE",
        help="Force OFF, PMIN or PMAX at a zero-based hour; repeat for several hours.",
    )
    args = parser.parse_args(argv)

    try:
        overrides = {}
        for item in args.override:
            hour, state = item.split("=", 1)
            index = int(hour)
            if index in overrides:
                raise ValueError(f"Duplicate override hour: {index}")
            overrides[index] = State(state)
        results = dispatch_day(load_prices(args.prices), overrides)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"{'hour':>4} {'price':>8} {'state':>6} {'MW':>7} {'PnL EUR':>10}")
    for result in results:
        print(
            f"{result.hour:>4} {result.price_eur_per_mwh:>8.2f} {result.state.value:>6} "
            f"{result.production_mw:>7.1f} {result.pnl_eur:>10.2f}"
        )

    summary = summarize(results)
    print(f"\nTotal production: {summary.energy_mwh:.1f} MWh")
    print(f"Total PnL: {summary.pnl_eur:.2f} EUR")
    print(f"Startups: {summary.startups}")
    print(
        f"Hours OFF / PMIN / PMAX: "
        f"{summary.hours_off} / {summary.hours_pmin} / {summary.hours_pmax}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
