import pytest

from power_dispatch.dispatch import (
    State,
    choose_state,
    dispatch_day,
    hourly_pnl,
    load_prices,
    summarize,
    total_pnl,
    total_production,
)


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (0.0, State.OFF),
        (59.99, State.OFF),
        (60.0, State.PMIN),
        (79.99, State.PMIN),
        (80.0, State.PMAX),
        (150.0, State.PMAX),
    ],
)
def test_choose_state_thresholds(price: float, expected: State) -> None:
    assert choose_state(price) == expected


def test_choose_state_handles_negative_price() -> None:
    assert choose_state(-10.0) == State.OFF


def test_hourly_pnl_is_zero_when_plant_is_off() -> None:
    assert hourly_pnl(20.0, 0.0) == 0.0


def test_hourly_pnl_at_pmin_and_pmax() -> None:
    assert hourly_pnl(70.0, 50.0) == 500.0
    assert hourly_pnl(100.0, 100.0) == 4000.0


def test_pnl_is_negative_only_below_variable_cost() -> None:
    assert hourly_pnl(55.0, 50.0) < 0
    assert hourly_pnl(60.0, 50.0) == 0.0


def test_dispatch_day_maps_each_hour() -> None:
    results = dispatch_day([50.0, 70.0, 90.0])

    assert [result.hour for result in results] == [0, 1, 2]
    assert [result.state for result in results] == [State.OFF, State.PMIN, State.PMAX]
    assert [result.production_mw for result in results] == [0.0, 50.0, 100.0]
    assert [result.pnl_eur for result in results] == [0.0, 0.0, 3000.0]


def test_dispatch_day_on_empty_input() -> None:
    assert dispatch_day([]) == []


def test_totals() -> None:
    results = dispatch_day([50.0, 70.0, 90.0])

    assert total_production(results) == 150.0
    assert total_pnl(results) == 3000.0


def test_load_prices_sorts_by_hour(tmp_path) -> None:
    path = tmp_path / "prices.csv"
    path.write_text("hour,price_eur_per_mwh\n2,90.0\n0,50.0\n1,70.0\n", encoding="utf-8")

    assert load_prices(path) == [50.0, 70.0, 90.0]


@pytest.mark.parametrize("price, expected", [(70.0, 0.0), (90.0, 2500.0)])
def test_startup_cost_for_both_on_states(price, expected):
    results = dispatch_day([price, price, price])
    assert [r.started for r in results] == [True, False, False]
    assert results[0].pnl_eur == expected
    assert results[1].pnl_eur == expected + 500.0


def test_minimum_on_includes_pmin_and_pmax():
    results = dispatch_day([90, 70, 0, 0])
    assert [r.state for r in results] == [State.PMAX, State.PMIN, State.PMIN, State.OFF]
    assert results[2].pnl_eur == -3000


def test_minimum_off_and_restart_cost():
    results = dispatch_day([90, 90, 90, 0, 90, 90])
    assert [r.state for r in results] == [
        State.PMAX,
        State.PMAX,
        State.PMAX,
        State.OFF,
        State.OFF,
        State.PMAX,
    ]
    assert results[5].started
    assert results[5].pnl_eur == 2500


def test_overrides_force_all_states_and_reset_durations():
    results = dispatch_day([90, 90, 0, 0, 0, 0], {1: "OFF", 2: "PMAX", 3: State.PMIN})
    assert [r.state for r in results] == [
        State.PMAX,
        State.OFF,
        State.PMAX,
        State.PMIN,
        State.PMIN,
        State.OFF,
    ]
    assert [r.started for r in results] == [True, False, True, False, False, False]
    assert results[2].pnl_eur == -6500


def test_forced_shutdown_starts_minimum_off():
    results = dispatch_day([90] * 4, {1: State.OFF})
    assert [r.state for r in results] == [State.PMAX, State.OFF, State.OFF, State.PMAX]


def test_none_override_uses_automatic_logic():
    prices = [90, 0, 0, 0, 90, 90]
    assert dispatch_day(prices, {1: None}) == dispatch_day(prices)


@pytest.mark.parametrize("overrides", [{-1: "OFF"}, {1: "OFF"}, {0: "BAD"}, {0.5: "OFF"}])
def test_invalid_overrides(overrides):
    with pytest.raises(ValueError):
        dispatch_day([90], overrides)


def test_summary_accepts_iterator():
    summary = summarize(iter(dispatch_day([90, 70, 0, 0, 90, 90])))
    assert summary.energy_mwh == 300
    assert summary.pnl_eur == 2500
    assert summary.startups == 2
    assert (summary.hours_off, summary.hours_pmin, summary.hours_pmax) == (2, 2, 2)


def test_empty_summary():
    summary = summarize([])
    assert (summary.energy_mwh, summary.pnl_eur, summary.startups) == (0, 0, 0)
    assert (summary.hours_off, summary.hours_pmin, summary.hours_pmax) == (0, 0, 0)


def test_end_of_horizon_keeps_last_startup():
    result = dispatch_day([90])[0]
    assert result.started
    assert result.pnl_eur == 2500
