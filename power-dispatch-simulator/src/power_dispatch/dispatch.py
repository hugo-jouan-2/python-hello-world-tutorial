"""Business logic of the hourly dispatch simulation."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

VARIABLE_COST_EUR_PER_MWH = 60.0
STARTUP_COST_EUR = 500.0
MIN_ON_HOURS = 3
MIN_OFF_HOURS = 2

PMIN_PRICE_THRESHOLD = 60.0
PMAX_PRICE_THRESHOLD = 80.0


class State(str, Enum):
    OFF = "OFF"
    PMIN = "PMIN"
    PMAX = "PMAX"


PRODUCTION_MW: dict[State, float] = {
    State.OFF: 0.0,
    State.PMIN: 50.0,
    State.PMAX: 100.0,
}


@dataclass(frozen=True)
class HourlyDispatch:
    hour: int
    price_eur_per_mwh: float
    state: State
    production_mw: float
    pnl_eur: float
    started: bool = False


def choose_state(price: float) -> State:
    """Pick the plant state for a given market price."""
    if price < PMIN_PRICE_THRESHOLD:
        return State.OFF
    if price < PMAX_PRICE_THRESHOLD:
        return State.PMIN
    return State.PMAX


def hourly_pnl(price: float, production_mw: float) -> float:
    """PnL of one hour, in EUR (production is held for a full hour)."""
    if production_mw == 0.0:
        return 0.0
    return (price - VARIABLE_COST_EUR_PER_MWH) * production_mw


def dispatch_hour(hour: int, price: float) -> HourlyDispatch:
    state = choose_state(price)
    production_mw = PRODUCTION_MW[state]
    return HourlyDispatch(
        hour=hour,
        price_eur_per_mwh=price,
        state=state,
        production_mw=production_mw,
        pnl_eur=hourly_pnl(price, production_mw),
    )


def dispatch_day(
    prices: Sequence[float], overrides: Mapping[int, State | str | None] | None = None
) -> list[HourlyDispatch]:
    """Dispatch hourly prices; explicit overrides take precedence over minimum durations.

    Initially OFF with its minimum downtime satisfied. Durations count the transition
    hour. No hours are appended when an ON commitment extends beyond the input.
    Override keys are zero-based positions in the price sequence.
    """
    manual = {}
    for hour, state in (overrides or {}).items():
        if type(hour) is not int or not 0 <= hour < len(prices):
            raise ValueError(f"Override hour out of range: {hour!r}")
        manual[hour] = State(state) if state is not None else None

    results = []
    was_on = False
    duration = MIN_OFF_HOURS
    for hour, price in enumerate(prices):
        state = manual.get(hour)
        if state is None:
            state = choose_state(price)
            if was_on and duration < MIN_ON_HOURS and state == State.OFF:
                state = State.PMIN
            elif not was_on and duration < MIN_OFF_HOURS:
                state = State.OFF
        is_on = state != State.OFF
        started = is_on and not was_on
        production = PRODUCTION_MW[state]
        results.append(
            HourlyDispatch(
                hour,
                price,
                state,
                production,
                hourly_pnl(price, production) - (STARTUP_COST_EUR if started else 0.0),
                started,
            )
        )
        duration = duration + 1 if is_on == was_on else 1
        was_on = is_on
    return results


@dataclass(frozen=True)
class DispatchSummary:
    energy_mwh: float
    pnl_eur: float
    startups: int
    hours_off: int
    hours_pmin: int
    hours_pmax: int


def summarize(results: Iterable[HourlyDispatch]) -> DispatchSummary:
    """Aggregate a simulation, accepting one-shot iterables as well as lists."""
    rows = list(results)
    return DispatchSummary(
        total_production(rows),
        total_pnl(rows),
        sum(row.started for row in rows),
        sum(row.state == State.OFF for row in rows),
        sum(row.state == State.PMIN for row in rows),
        sum(row.state == State.PMAX for row in rows),
    )


def total_pnl(results: Iterable[HourlyDispatch]) -> float:
    return sum(result.pnl_eur for result in results)


def total_production(results: Iterable[HourlyDispatch]) -> float:
    return sum(result.production_mw for result in results)


def load_prices(path: Path) -> list[float]:
    """Read prices from a CSV with columns `hour` and `price_eur_per_mwh`."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda row: int(row["hour"]))
    return [float(row["price_eur_per_mwh"]) for row in rows]
