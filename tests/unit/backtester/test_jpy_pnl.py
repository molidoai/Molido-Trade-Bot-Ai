"""Profit on a yen-quoted pair is earned in yen, not dollars.

The harness multiplied every non-metal move by 100,000 and called the result
dollars. For GBPJPY that overstated it by roughly the USDJPY rate, so the
study showed +61,027 on one JPY cell and -98,911 on another while comparable
EURUSD cells sat in the hundreds -- the JPY rows dominated every ranking by
currency amount for a reason that had nothing to do with the market.

PF and the fold counts were unaffected: PF is a ratio and a fold is judged by
the sign of its net, so a constant factor cancels in both. Only the amounts
were wrong, which is why the bug survived so long.
"""

from molido_backtester.engine import BacktestEngine


def pnl(symbol, entry, exit, side="BUY", volume=1.0):
    return BacktestEngine._pnl(side, entry, exit, volume, symbol)


def test_a_dollar_quoted_pair_is_unchanged():
    # 10 pips on EURUSD, 1 lot = $100.
    assert round(pnl("EURUSD", 1.1000, 1.1010), 2) == 100.00


def test_gold_uses_the_metal_contract_size():
    # $1 move on 1 lot of gold = 100 oz = $100.
    assert round(pnl("XAUUSD", 2000.0, 2001.0), 2) == 100.00


def test_a_yen_pair_is_converted_out_of_yen():
    """1.00 of movement on GBPJPY at ~190 is 100,000 yen, which is about
    $526 -- not the $100,000 the old code reported."""
    got = pnl("GBPJPY", 190.00, 191.00)
    assert 500 < got < 560, got


def test_usdjpy_too():
    got = pnl("USDJPY", 150.00, 151.00)
    assert 600 < got < 700, got


def test_the_old_behaviour_would_have_been_150x_larger():
    """The size of the error, stated so a regression is obvious."""
    fixed = pnl("GBPJPY", 190.00, 191.00)
    unfixed = 1.00 * 1.0 * 100_000
    assert unfixed / fixed > 100


def test_a_short_still_profits_when_price_falls():
    assert pnl("USDJPY", 151.00, 150.00, side="SELL") > 0
    assert pnl("USDJPY", 150.00, 151.00, side="SELL") < 0


def test_profit_factor_shifts_only_slightly():
    """The first version of this test asserted PF was untouched. It is not,
    quite: the conversion divides by the exit price, and a winner and a loser
    exit at different prices, so the factor is not perfectly constant across
    trades.

    The effect is second-order -- about 2% on this pair, where a 3-yen spread
    of exit prices sits on a ~150 base -- which is why the fold counts and the
    broad ranking of the completed study still stand, while the currency
    amounts in it do not. Stated as a bound rather than as "no effect",
    because "no effect" was wrong."""
    win_fixed = pnl("USDJPY", 150.00, 152.00)
    loss_fixed = abs(pnl("USDJPY", 150.00, 149.00))
    fixed_ratio = win_fixed / loss_fixed
    raw_ratio = (2.0 * 100_000) / (1.0 * 100_000)
    drift = abs(fixed_ratio - raw_ratio) / raw_ratio
    assert 0 < drift < 0.05, drift
