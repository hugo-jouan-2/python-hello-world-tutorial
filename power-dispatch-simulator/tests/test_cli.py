import pytest

from power_dispatch.cli import main


def test_cli_overrides_and_summary(tmp_path, capsys):
    prices = tmp_path / "prices.csv"
    prices.write_text("hour,price_eur_per_mwh\n0,90\n1,90\n2,90\n")
    assert main([str(prices), "--override", "0=OFF", "--override", "1=PMIN"]) == 0
    output = capsys.readouterr().out
    assert "Total production: 150.0 MWh" in output
    assert "Total PnL: 4000.00 EUR" in output
    assert "Startups: 1" in output
    assert "Hours OFF / PMIN / PMAX: 1 / 1 / 1" in output


@pytest.mark.parametrize(
    "args",
    [
        ["--override", "bad"],
        ["--override", "0=BAD"],
        ["--override", "0=OFF", "--override", "0=PMIN"],
        ["--override", "999=OFF"],
    ],
)
def test_cli_rejects_invalid_overrides(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
